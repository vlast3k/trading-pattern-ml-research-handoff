#!/usr/bin/env python3
"""Rank current strategy families for Issue #9.

This is a first-pass product/research triage runner. It scans existing report
CSVs, infers strategy families from file/row text, normalizes common metrics,
and writes a ranked family report. It is not an optimizer and does not search
new strategy parameters.

The worker should fix mappings if local report columns differ, run the script,
and then commit generated artifacts.
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


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def first_col(cols: list[str], aliases: list[str]) -> str | None:
    lookup = {norm(c): c for c in cols}
    for a in aliases:
        if norm(a) in lookup:
            return lookup[norm(a)]
    return None


def as_float(v: Any) -> float | None:
    if v is None or pd.isna(v):
        return None
    if isinstance(v, str):
        v = v.replace("$", "").replace(",", "").replace("%", "").strip()
        if not v:
            return None
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def money(v: Any) -> str:
    x = as_float(v)
    return "n/a" if x is None else f"${x:,.0f}"


def num(v: Any, digits: int = 2) -> str:
    x = as_float(v)
    return "n/a" if x is None else f"{x:.{digits}f}"


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def discover_csvs(config: dict[str, Any], max_csv_mb: float, include_large: bool) -> list[Path]:
    found: dict[str, Path] = {}
    skips = [p.lower() for p in config.get("skip_path_patterns", [])]
    for pattern in config.get("csv_include_globs", ["reports/**/*.csv", "*.csv"]):
        for path in Path.cwd().glob(pattern):
            if not path.is_file():
                continue
            ps = path.as_posix().lower()
            if any(s in ps for s in skips):
                continue
            if not include_large and path.stat().st_size > max_csv_mb * 1024 * 1024:
                continue
            found[path.as_posix()] = path
    return [found[k] for k in sorted(found)]


def infer_family(text: str, patterns: dict[str, list[str]]) -> str:
    lo = text.lower()
    hits: list[tuple[int, str]] = []
    for family, pats in patterns.items():
        best = None
        for pat in pats:
            idx = lo.find(pat.lower())
            if idx >= 0:
                best = idx if best is None else min(best, idx)
        if best is not None:
            hits.append((best, family))
    return sorted(hits)[0][1] if hits else "unknown_other"


def normalize_largest_share(v: float | None) -> float | None:
    if v is None:
        return None
    return v / 100.0 if 1.0 < v <= 100.0 else v


def read_rows(path: Path, config: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        return [], f"read_error:{exc}"
    aliases = config["metric_aliases"]
    cols = list(df.columns)
    net = first_col(cols, aliases["net_dollars"])
    pf = first_col(cols, aliases["profit_factor"])
    dd = first_col(cols, aliases["max_drawdown_dollars"])
    trades = first_col(cols, aliases["trades"])
    largest = first_col(cols, aliases["largest_winner_share"])
    net_ex = first_col(cols, aliases["net_without_largest"])
    variant = first_col(cols, aliases.get("variant", []))
    timeframe = first_col(cols, aliases.get("timeframe", []))
    status = first_col(cols, aliases.get("status", []))
    if not any([net, pf, dd, trades, largest, net_ex]):
        return [], "no_mapped_metric_columns"
    out: list[dict[str, Any]] = []
    for i, r in df.iterrows():
        label = " ".join([path.as_posix(), str(r.get(variant, "")), str(r.get(status, "")), str(r.get(timeframe, ""))])
        family = infer_family(label, config["family_patterns"])
        variant_value = str(r.get(variant, path.stem)).strip() if variant else path.stem
        out.append({
            "source_file": path.as_posix(),
            "source_row": int(i),
            "family": family,
            "variant": variant_value or path.stem,
            "candidate_id": f"{family}:{variant_value or path.stem}:{path.as_posix()}:{i}",
            "timeframe": as_float(r.get(timeframe)) if timeframe else None,
            "status_raw": str(r.get(status, "")).strip() if status else "",
            "net_dollars": as_float(r.get(net)) if net else None,
            "profit_factor": as_float(r.get(pf)) if pf else None,
            "max_drawdown_dollars": as_float(r.get(dd)) if dd else None,
            "trades": as_float(r.get(trades)) if trades else None,
            "largest_winner_share": normalize_largest_share(as_float(r.get(largest)) if largest else None),
            "net_without_largest": as_float(r.get(net_ex)) if net_ex else None,
        })
    return out, None


def score(row: pd.Series, thresholds: dict[str, Any]) -> tuple[float, str, str]:
    s = 0.0
    reasons: list[str] = []
    net = row.get("net_dollars")
    pf = row.get("profit_factor")
    trades = row.get("trades")
    dd = row.get("max_drawdown_dollars")
    largest = row.get("largest_winner_share")
    net_ex = row.get("net_without_largest")
    raw_status = str(row.get("status_raw") or "").lower()

    if pd.notna(net):
        if net > 0:
            s += 20; reasons.append("positive_net")
        else:
            s -= 25; reasons.append("non_positive_net")
    if pd.notna(pf):
        if pf >= thresholds["min_profit_factor_primary_validation"]:
            s += 25; reasons.append("pf_primary_level")
        elif pf >= thresholds["min_profit_factor_research_monitor"]:
            s += 12; reasons.append("pf_monitor_level")
        else:
            s -= 15; reasons.append("weak_pf")
    if pd.notna(trades):
        if trades >= thresholds["min_trades_primary_validation"]:
            s += 20; reasons.append("sample_primary_level")
        elif trades >= thresholds["min_trades_research_monitor"]:
            s += 10; reasons.append("sample_monitor_level")
        else:
            s -= 12; reasons.append("thin_sample")
    if pd.notna(dd):
        if dd <= thresholds["preferred_max_drawdown_one_contract_mnq"]:
            s += 15; reasons.append("preferred_drawdown")
        elif dd <= thresholds["max_drawdown_one_contract_mnq"]:
            s += 5; reasons.append("acceptable_drawdown")
        else:
            s -= 18; reasons.append("drawdown_too_high")
    if pd.notna(net_ex):
        if net_ex > thresholds["min_net_without_largest"]:
            s += 20; reasons.append("positive_ex_largest")
        else:
            s -= 25; reasons.append("largest_winner_dependency")
    if pd.notna(largest):
        if largest <= thresholds["max_largest_winner_share"]:
            s += 10; reasons.append("largest_share_ok")
        else:
            s -= 15; reasons.append("largest_share_high")
    if "pass" in raw_status or "primary" in raw_status:
        s += 8; reasons.append("source_status_positive")
    if "fail" in raw_status or "reject" in raw_status:
        s -= 8; reasons.append("source_status_negative")

    status = "diagnostic_only"
    if s >= 70:
        status = "primary_validation_candidate"
    elif s >= 45:
        status = "research_monitor"
    elif s < 0:
        status = "reject"
    return s, status, ",".join(reasons)


def score_rank(status: str) -> int:
    return {"reject": 1, "diagnostic_only": 2, "research_monitor": 3, "primary_validation_candidate": 4}.get(status, 0)


def build_outputs(candidates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if candidates.empty:
        return pd.DataFrame(rows)
    for family, g in candidates.groupby("family", sort=False):
        g = g.sort_values("triage_score", ascending=False)
        best = g.iloc[0]
        statuses = list(g["suggested_status"].dropna())
        fam_status = max(statuses, key=score_rank) if statuses else "diagnostic_only"
        rows.append({
            "family": family,
            "family_score": float(best["triage_score"]),
            "family_status": fam_status,
            "best_candidate_id": best["candidate_id"],
            "best_variant": best["variant"],
            "best_source_file": best["source_file"],
            "best_net_dollars": best.get("net_dollars"),
            "best_profit_factor": best.get("profit_factor"),
            "best_trades": best.get("trades"),
            "best_max_drawdown_dollars": best.get("max_drawdown_dollars"),
            "best_largest_winner_share": best.get("largest_winner_share"),
            "best_net_without_largest": best.get("net_without_largest"),
            "candidate_rows_seen": int(len(g)),
            "top_reasons": best.get("score_reasons", ""),
        })
    return pd.DataFrame(rows).sort_values(["family_score", "best_net_dollars"], ascending=[False, False], na_position="last")


def choose_decision(families: pd.DataFrame) -> tuple[str, str]:
    if families.empty:
        return "reject the current set and broaden discovery", "No usable comparable rows were found; worker should add report-specific mappings."
    best = families.iloc[0]
    if best["family_status"] in {"primary_validation_candidate", "research_monitor"}:
        return "advance one family to a focused validation task", f"Best current lane: `{best['family']}` via `{best['best_variant']}`."
    if (families["family_score"] > 0).any():
        return "keep all families diagnostic and collect specific forward data", "Some positive evidence exists, but no family clears validation-level gates."
    return "reject the current set and broaden discovery", "No family clears diagnostic scoring convincingly."


def write_report(path: Path, families: pd.DataFrame, candidates: pd.DataFrame, skipped: pd.DataFrame, decision: tuple[str, str]) -> None:
    lines: list[str] = []
    lines.append(f"# Strategy Family Triage - {datetime.now(timezone.utc).date().isoformat()}")
    lines.append("")
    lines.append("This report supports Issue #9: rank current strategy families for next practical validation. It is not a parameter search or deployment decision.")
    lines.append("")
    lines.append("## Primary recommendation")
    lines.append("")
    lines.append(f"**{decision[0]}**")
    lines.append("")
    lines.append(decision[1])
    lines.append("")
    lines.append("## Ranked families")
    lines.append("")
    if families.empty:
        lines.append("No usable family rows were found. Update config mappings or add explicit source reports.")
    else:
        lines.append("| Rank | Family | Status | Score | Best variant | Net | PF | Trades | Max DD | Net ex-largest | Largest share | Source |")
        lines.append("|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|")
        for rank, r in enumerate(families.itertuples(index=False), start=1):
            largest = "n/a" if pd.isna(r.best_largest_winner_share) else f"{r.best_largest_winner_share * 100:.1f}%"
            lines.append(f"| {rank} | `{r.family}` | `{r.family_status}` | {r.family_score:.1f} | `{r.best_variant}` | {money(r.best_net_dollars)} | {num(r.best_profit_factor)} | {num(r.best_trades, 0)} | {money(r.best_max_drawdown_dollars)} | {money(r.best_net_without_largest)} | {largest} | `{r.best_source_file}` |")
    lines.append("")
    lines.append("## Top candidate rows")
    lines.append("")
    if candidates.empty:
        lines.append("No normalized candidate rows.")
    else:
        lines.append("| Rank | Family | Suggested status | Score | Variant | Net | PF | Trades | Reasons | Source |")
        lines.append("|---:|---|---|---:|---|---:|---:|---:|---|---|")
        for rank, r in enumerate(candidates.head(25).itertuples(index=False), start=1):
            lines.append(f"| {rank} | `{r.family}` | `{r.suggested_status}` | {r.triage_score:.1f} | `{r.variant}` | {money(r.net_dollars)} | {num(r.profit_factor)} | {num(r.trades, 0)} | `{r.score_reasons}` | `{r.source_file}` |")
    lines.append("")
    lines.append("## Worker review notes")
    lines.append("")
    lines.append("- This is a scaffold. If the top row is a known overfit selector or comes from the wrong cohort, override it in the final Issue #9 conclusion.")
    lines.append("- Update `config/strategy_family_triage_config.json` when local report columns are not recognized.")
    lines.append("- The final decision must still be one of: advance one family; keep all diagnostic and collect specific forward data; reject/broaden discovery.")
    if not skipped.empty:
        lines.append("")
        lines.append("## Skipped CSV files")
        lines.append("")
        lines.append("| File | Reason |")
        lines.append("|---|---|")
        for r in skipped.itertuples(index=False):
            lines.append(f"| `{r.source_file}` | `{r.reason}` |")
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
    for csv in discover_csvs(config, args.max_csv_mb, args.include_large_csv):
        new_rows, reason = read_rows(csv, config)
        rows.extend(new_rows)
        if reason:
            skipped.append({"source_file": csv.as_posix(), "reason": reason})

    candidates = pd.DataFrame(rows)
    thresholds = config["thresholds"]
    if not candidates.empty:
        scored = candidates.apply(lambda r: score(r, thresholds), axis=1)
        candidates["triage_score"] = [x[0] for x in scored]
        candidates["suggested_status"] = [x[1] for x in scored]
        candidates["score_reasons"] = [x[2] for x in scored]
        candidates = candidates.sort_values(["triage_score", "net_dollars"], ascending=[False, False], na_position="last")
    families = build_outputs(candidates)
    skipped_df = pd.DataFrame(skipped)
    decision = choose_decision(families)

    candidates.to_csv(out_dir / "candidate_rows.csv", index=False)
    families.to_csv(out_dir / "family_rankings.csv", index=False)
    skipped_df.to_csv(out_dir / "skipped_csvs.csv", index=False)
    metadata = {
        "generated_by": "scripts/run_strategy_family_triage.py",
        "issue": "https://github.com/vlast3k/trading-pattern-ml-research-handoff/issues/9",
        "decision": decision[0],
        "decision_rationale": decision[1],
        "config": args.config.as_posix(),
        "csv_files_seen": len(discover_csvs(config, args.max_csv_mb, args.include_large_csv)),
        "candidate_rows": int(len(candidates)),
        "family_rows": int(len(families)),
    }
    (out_dir / "triage_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    report = Path(f"STRATEGY_FAMILY_TRIAGE_{args.date}.md")
    write_report(report, families, candidates, skipped_df, decision)
    print(report)
    print(out_dir / "family_rankings.csv")
    print(decision[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
