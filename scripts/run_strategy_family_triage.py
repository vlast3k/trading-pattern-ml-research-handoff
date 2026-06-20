#!/usr/bin/env python3
"""Rank current strategy families for Issue #9.

This first-pass runner scans existing report CSVs, normalizes common trading
metrics, infers broad family buckets, and writes candidate/family ranking
artifacts. It is not an optimizer and does not search new strategy parameters.
The worker should fix config mappings if local reports use different columns.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path("config/strategy_family_triage_config.json"))
    p.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--include-large-csv", action="store_true")
    p.add_argument("--max-csv-mb", type=float, default=25.0)
    return p.parse_args()


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def first_col(columns: list[str], aliases: list[str]) -> str | None:
    by_norm = {norm(c): c for c in columns}
    for alias in aliases:
        if norm(alias) in by_norm:
            return by_norm[norm(alias)]
    return None


def as_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def money(value: Any) -> str:
    number = as_float(value)
    return "n/a" if number is None else f"${number:,.0f}"


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def discover_csvs(config: dict[str, Any], max_csv_mb: float, include_large: bool) -> list[Path]:
    found: dict[str, Path] = {}
    skips = [s.lower() for s in config.get("skip_path_patterns", [])]
    for pattern in config.get("csv_include_globs", ["reports/**/*.csv", "*.csv"]):
        for path in Path.cwd().glob(pattern):
            if not path.is_file():
                continue
            lower = path.as_posix().lower()
            if any(skip in lower for skip in skips):
                continue
            if not include_large and path.stat().st_size > max_csv_mb * 1024 * 1024:
                continue
            found[path.as_posix()] = path
    return [found[key] for key in sorted(found)]


def infer_family(text: str, patterns: dict[str, list[str]]) -> str:
    lower = text.lower()
    for family, parts in patterns.items():
        if any(part.lower() in lower for part in parts):
            return family
    return "unknown_other"


def normalize_share(value: float | None) -> float | None:
    if value is None:
        return None
    return value / 100.0 if value > 1.0 else value


def read_candidate_rows(path: Path, config: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    try:
        frame = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        return [], f"read_error:{exc}"

    aliases = config["metric_aliases"]
    columns = list(frame.columns)
    mapped = {name: first_col(columns, names) for name, names in aliases.items()}
    if not any(mapped.get(name) for name in ["net_dollars", "profit_factor", "max_drawdown_dollars", "trades"]):
        return [], "no_mapped_metric_columns"

    rows: list[dict[str, Any]] = []
    for idx, row in frame.iterrows():
        variant_col = mapped.get("variant")
        status_col = mapped.get("status")
        timeframe_col = mapped.get("timeframe")
        variant = str(row.get(variant_col, path.stem)).strip() if variant_col else path.stem
        label = " ".join([path.as_posix(), variant, str(row.get(status_col, "")), str(row.get(timeframe_col, ""))])
        family = infer_family(label, config["family_patterns"])
        rows.append({
            "source_file": path.as_posix(),
            "source_row": int(idx),
            "family": family,
            "variant": variant,
            "candidate_id": f"{family}:{variant}:{path.as_posix()}:{idx}",
            "status_raw": str(row.get(status_col, "")).strip() if status_col else "",
            "net_dollars": as_float(row.get(mapped.get("net_dollars"))) if mapped.get("net_dollars") else None,
            "profit_factor": as_float(row.get(mapped.get("profit_factor"))) if mapped.get("profit_factor") else None,
            "max_drawdown_dollars": as_float(row.get(mapped.get("max_drawdown_dollars"))) if mapped.get("max_drawdown_dollars") else None,
            "trades": as_float(row.get(mapped.get("trades"))) if mapped.get("trades") else None,
            "largest_winner_share": normalize_share(as_float(row.get(mapped.get("largest_winner_share"))) if mapped.get("largest_winner_share") else None),
            "net_without_largest": as_float(row.get(mapped.get("net_without_largest"))) if mapped.get("net_without_largest") else None,
        })
    return rows, None


def score(row: pd.Series, thresholds: dict[str, Any]) -> tuple[float, str, str]:
    score_value = 0.0
    reasons: list[str] = []

    net = row.get("net_dollars")
    pf = row.get("profit_factor")
    trades = row.get("trades")
    dd = row.get("max_drawdown_dollars")
    largest = row.get("largest_winner_share")
    net_ex = row.get("net_without_largest")
    raw_status = str(row.get("status_raw") or "").lower()

    if pd.notna(net):
        score_value += 20 if net > 0 else -25
        reasons.append("positive_net" if net > 0 else "non_positive_net")
    if pd.notna(pf):
        if pf >= thresholds["min_profit_factor_primary_validation"]:
            score_value += 25; reasons.append("pf_primary_level")
        elif pf >= thresholds["min_profit_factor_research_monitor"]:
            score_value += 12; reasons.append("pf_monitor_level")
        else:
            score_value -= 15; reasons.append("weak_pf")
    if pd.notna(trades):
        if trades >= thresholds["min_trades_primary_validation"]:
            score_value += 20; reasons.append("sample_primary_level")
        elif trades >= thresholds["min_trades_research_monitor"]:
            score_value += 10; reasons.append("sample_monitor_level")
        else:
            score_value -= 12; reasons.append("thin_sample")
    if pd.notna(dd):
        if dd <= thresholds["preferred_max_drawdown_one_contract_mnq"]:
            score_value += 15; reasons.append("preferred_drawdown")
        elif dd <= thresholds["max_drawdown_one_contract_mnq"]:
            score_value += 5; reasons.append("acceptable_drawdown")
        else:
            score_value -= 18; reasons.append("drawdown_too_high")
    if pd.notna(net_ex):
        score_value += 20 if net_ex > thresholds["min_net_without_largest"] else -25
        reasons.append("positive_ex_largest" if net_ex > thresholds["min_net_without_largest"] else "largest_winner_dependency")
    if pd.notna(largest):
        score_value += 10 if largest <= thresholds["max_largest_winner_share"] else -15
        reasons.append("largest_share_ok" if largest <= thresholds["max_largest_winner_share"] else "largest_share_high")
    if "pass" in raw_status or "primary" in raw_status:
        score_value += 8; reasons.append("source_status_positive")
    if "fail" in raw_status or "reject" in raw_status:
        score_value -= 8; reasons.append("source_status_negative")

    status = "diagnostic_only"
    if score_value >= 70:
        status = "primary_validation_candidate"
    elif score_value >= 45:
        status = "research_monitor"
    elif score_value < 0:
        status = "reject"
    return score_value, status, ",".join(reasons)


def rank_families(candidates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if candidates.empty:
        return pd.DataFrame(rows)
    for family, group in candidates.groupby("family", sort=False):
        best = group.sort_values("triage_score", ascending=False).iloc[0]
        rows.append({
            "family": family,
            "family_score": float(best["triage_score"]),
            "family_status": best["suggested_status"],
            "best_candidate_id": best["candidate_id"],
            "best_variant": best["variant"],
            "best_source_file": best["source_file"],
            "best_net_dollars": best.get("net_dollars"),
            "best_profit_factor": best.get("profit_factor"),
            "best_trades": best.get("trades"),
            "best_max_drawdown_dollars": best.get("max_drawdown_dollars"),
            "best_largest_winner_share": best.get("largest_winner_share"),
            "best_net_without_largest": best.get("net_without_largest"),
            "candidate_rows_seen": int(len(group)),
        })
    return pd.DataFrame(rows).sort_values("family_score", ascending=False)


def choose_decision(families: pd.DataFrame) -> tuple[str, str]:
    if families.empty:
        return "reject the current set and broaden discovery", "No comparable rows were found; update config/report mappings."
    best = families.iloc[0]
    if best["family_status"] in {"primary_validation_candidate", "research_monitor"}:
        return "advance one family to a focused validation task", f"Best current lane: `{best['family']}` via `{best['best_variant']}`."
    if (families["family_score"] > 0).any():
        return "keep all families diagnostic and collect specific forward data", "Some evidence is positive, but no family clears validation-level gates."
    return "reject the current set and broaden discovery", "No family clears diagnostic scoring convincingly."


def write_markdown(path: Path, families: pd.DataFrame, candidates: pd.DataFrame, skipped: pd.DataFrame, decision: tuple[str, str]) -> None:
    lines = [
        f"# Strategy Family Triage - {datetime.now(timezone.utc).date().isoformat()}",
        "",
        "This report supports Issue #9. It is a scaffolded ranking, not a deployment decision.",
        "",
        "## Primary recommendation",
        "",
        f"**{decision[0]}**",
        "",
        decision[1],
        "",
        "## Ranked families",
        "",
    ]
    if families.empty:
        lines.append("No usable family rows were found. Update config mappings or source reports.")
    else:
        lines.append("| Rank | Family | Status | Score | Best variant | Net | PF | Trades | Max DD | Net ex-largest | Source |")
        lines.append("|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|")
        for idx, row in enumerate(families.itertuples(index=False), start=1):
            lines.append(f"| {idx} | `{row.family}` | `{row.family_status}` | {row.family_score:.1f} | `{row.best_variant}` | {money(row.best_net_dollars)} | {row.best_profit_factor if pd.notna(row.best_profit_factor) else 'n/a'} | {row.best_trades if pd.notna(row.best_trades) else 'n/a'} | {money(row.best_max_drawdown_dollars)} | {money(row.best_net_without_largest)} | `{row.best_source_file}` |")
    lines.extend(["", "## Worker notes", "", "- If a known overfit or wrong-cohort row ranks first, override the scaffold in the final product conclusion.", "- Final Issue #9 recommendation must be exactly one of the three choices in the issue body."])
    if not skipped.empty:
        lines.extend(["", "## Skipped CSV files", "", "| File | Reason |", "|---|---|"])
        for row in skipped.itertuples(index=False):
            lines.append(f"| `{row.source_file}` | `{row.reason}` |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    out_dir = args.out_dir or Path("reports") / f"strategy_family_triage_{args.date}"
    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        raise SystemExit(f"Refusing to overwrite non-empty output dir without --force: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for csv_path in discover_csvs(config, args.max_csv_mb, args.include_large_csv):
        new_rows, reason = read_candidate_rows(csv_path, config)
        rows.extend(new_rows)
        if reason:
            skipped.append({"source_file": csv_path.as_posix(), "reason": reason})

    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        scored = candidates.apply(lambda row: score(row, config["thresholds"]), axis=1)
        candidates["triage_score"] = [item[0] for item in scored]
        candidates["suggested_status"] = [item[1] for item in scored]
        candidates["score_reasons"] = [item[2] for item in scored]
        candidates = candidates.sort_values(["triage_score", "net_dollars"], ascending=[False, False], na_position="last")

    families = rank_families(candidates)
    skipped_df = pd.DataFrame(skipped)
    decision = choose_decision(families)

    candidates.to_csv(out_dir / "candidate_rows.csv", index=False)
    families.to_csv(out_dir / "family_rankings.csv", index=False)
    skipped_df.to_csv(out_dir / "skipped_csvs.csv", index=False)
    (out_dir / "triage_metadata.json").write_text(json.dumps({
        "generated_by": "scripts/run_strategy_family_triage.py",
        "issue": "https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/9",
        "decision": decision[0],
        "decision_rationale": decision[1],
        "candidate_rows": int(len(candidates)),
        "family_rows": int(len(families)),
    }, indent=2) + "\n", encoding="utf-8")
    report = Path(f"STRATEGY_FAMILY_TRIAGE_{args.date}.md")
    write_markdown(report, families, candidates, skipped_df, decision)
    print(report)
    print(out_dir / "family_rankings.csv")
    print(decision[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
