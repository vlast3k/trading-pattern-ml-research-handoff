#!/usr/bin/env python3
"""Issue #19 ATR-regime conditioning audit.

Runs Phase 1 state audit for TR_{t-1}/ATR20. Phase 2 is optional and
intentionally diagnostic-only. This script cannot approve paper/live trading or
directly promote a primary validation candidate.
"""
from __future__ import annotations

import argparse, json, math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path("config/atr_regime_conditioning_config.json"))
    p.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--force", action="store_true")
    p.add_argument("--run-phase2", action="store_true", help="Run diagnostic Donchian A/B scaffold after Phase 1 passes.")
    p.add_argument("--local-parity", action="store_true", help="Run Phase 1 summary on local Ninja OHLCV if present.")
    return p.parse_args()


def repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except Exception:  # noqa: BLE001
        return path.as_posix()


def pick(cols: list[str], aliases: list[str]) -> str | None:
    by_norm = {c.lower().replace(" ", "_"): c for c in cols}
    for alias in aliases:
        hit = by_norm.get(alias.lower().replace(" ", "_"))
        if hit:
            return hit
    return None


def read_ohlcv(path: Path, cfg: dict[str, Any], label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    raw = pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path)
    cols = list(raw.columns)
    aliases = cfg["column_aliases"]
    m = {k: pick(cols, v) for k, v in aliases.items()}
    required = ["timestamp", "open", "high", "low", "close"]
    missing = [k for k in required if not m.get(k)]
    if missing:
        raise ValueError(f"Missing columns {missing} in {path}; available={cols[:40]}")
    out = pd.DataFrame({
        "timestamp": pd.to_datetime(raw[m["timestamp"]], utc=True, errors="coerce"),
        "open": pd.to_numeric(raw[m["open"]], errors="coerce"),
        "high": pd.to_numeric(raw[m["high"]], errors="coerce"),
        "low": pd.to_numeric(raw[m["low"]], errors="coerce"),
        "close": pd.to_numeric(raw[m["close"]], errors="coerce"),
    })
    out["volume"] = pd.to_numeric(raw[m["volume"]], errors="coerce").fillna(0) if m.get("volume") else 0.0
    if m.get("root"):
        out["root"] = raw[m["root"]].astype(str).str.upper()
    elif m.get("symbol"):
        out["root"] = raw[m["symbol"]].astype(str).str.extract(r"([A-Z]+)", expand=False).fillna("UNKNOWN").str.upper()
    else:
        out["root"] = cfg.get("default_root", "MNQ")
    roots = {r.upper() for r in cfg.get("roots", ["MNQ"])}
    out = out[out["root"].isin(roots)].dropna(subset=required).sort_values(["root", "timestamp"])
    out["source_label"] = label
    out["source_path"] = repo_rel(path)
    if out.empty:
        raise ValueError(f"No rows after filtering roots={sorted(roots)} from {path}")
    return out.reset_index(drop=True)


def add_session_date(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    local_ts = out["timestamp"].dt.tz_convert(cfg.get("session_timezone", "America/New_York"))
    out["session_date"] = local_ts.dt.date.astype(str)
    return out


def daily_state(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    x = add_session_date(df, cfg)
    d = x.groupby(["root", "session_date"], as_index=False).agg(
        timestamp_first=("timestamp", "min"), timestamp_last=("timestamp", "max"),
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
        volume=("volume", "sum"), source_label=("source_label", "first"), source_path=("source_path", "first"),
    ).sort_values(["root", "session_date"]).reset_index(drop=True)
    tick = float(cfg.get("tick_size", 0.25))
    d["tr"] = d["high"] - d["low"]
    d["close_to_close_return_points"] = d.groupby("root")["close"].diff()
    denom = d["tr"].clip(lower=tick)
    d["trendiness"] = (d["close"] - d["open"]).abs() / denom
    d["signed_trendiness"] = (d["close"] - d["open"]) / denom
    sd = cfg["state_definition"]
    shifted = d.groupby("root")["tr"].shift(1)
    d["prior_day_tr"] = shifted
    d["atr20"] = shifted.groupby(d["root"]).rolling(int(sd["atr_window_days"]), min_periods=int(sd["atr_window_days"])).mean().reset_index(level=0, drop=True)
    d["range_ratio"] = d["prior_day_tr"] / d["atr20"]
    d["state"] = "unclassified"
    d.loc[d["range_ratio"] < float(sd["compression_threshold"]), "state"] = "compression"
    d.loc[(d["range_ratio"] >= float(sd["compression_threshold"])) & (d["range_ratio"] <= float(sd["expansion_threshold"])), "state"] = "neutral"
    d.loc[d["range_ratio"] > float(sd["expansion_threshold"]), "state"] = "expansion"
    d["state_next"] = d.groupby("root")["state"].shift(-1)
    d["range_ratio_bin"] = pd.cut(d["range_ratio"], [-math.inf, .7, .9, 1.1, 1.3, math.inf], labels=["lt_0_7", "0_7_to_0_9", "0_9_to_1_1", "1_1_to_1_3", "gt_1_3"])
    return d


def behavior(d: pd.DataFrame, group: str) -> pd.DataFrame:
    x = d[(d["state"] != "unclassified") & d[group].notna()].copy()
    rows = []
    for (root, key), p in x.groupby(["root", group], observed=False):
        same = (p["state"] == p["state_next"]).dropna()
        rows.append({
            "root": root, group: str(key), "days": len(p),
            "mean_range": p["tr"].mean(), "median_range": p["tr"].median(),
            "mean_close_to_close_return_points": p["close_to_close_return_points"].mean(),
            "median_close_to_close_return_points": p["close_to_close_return_points"].median(),
            "mean_trendiness": p["trendiness"].mean(), "median_trendiness": p["trendiness"].median(),
            "mean_signed_trendiness": p["signed_trendiness"].mean(), "median_signed_trendiness": p["signed_trendiness"].median(),
            "same_state_next_day_probability": same.mean() if len(same) else float("nan"),
        })
    return pd.DataFrame(rows)


def distribution(d: pd.DataFrame) -> pd.DataFrame:
    x = d[d["state"] != "unclassified"].copy()
    x["year"] = pd.to_datetime(x["session_date"]).dt.year
    out = x.groupby(["root", "year", "state"], as_index=False).size().rename(columns={"size": "days"})
    out["share"] = out["days"] / out.groupby(["root", "year"])["days"].transform("sum")
    return out


def phase1_gate(d: pd.DataFrame, cfg: dict[str, Any]) -> tuple[bool, list[str]]:
    g, x, reasons = cfg["phase1_gates"], d[d["state"] != "unclassified"], []
    for state in ["compression", "expansion"]:
        n = int((x["state"] == state).sum())
        if n < int(g["min_days_per_primary_state"]):
            reasons.append(f"{state}_too_sparse:{n}")
    med = x.groupby("state")["tr"].median().to_dict()
    if med.get("expansion", -math.inf) <= med.get("compression", math.inf):
        reasons.append("expansion_median_range_not_above_compression")
    dist = distribution(d)
    for state in ["compression", "expansion"]:
        years = dist[(dist["state"] == state) & (dist["days"] >= int(g["min_days_per_state_per_year"]))]["year"].nunique()
        if years < int(g["min_years_with_primary_states"]):
            reasons.append(f"{state}_not_stable_across_years")
    return not reasons, reasons


def empty_signal_outputs(out: Path, reason: str) -> None:
    cols = ["signal", "state", "slippage_ticks_per_side", "trades", "net_dollars", "profit_factor", "skip_reason"]
    for name in ["signal_performance_by_state.csv", "signal_controls_unconditional.csv", "concentration_by_state.csv"]:
        pd.DataFrame(columns=cols).assign(skip_reason=reason).to_csv(out / name, index=False)


def write_lineage(out: Path, cfg: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    lines = ["# Source Lineage", "", f"Generated: {datetime.now(timezone.utc).isoformat()}", "", "| Source | Path | Rows | First | Last | Role |", "|---|---|---:|---|---|---|"]
    for s in sources:
        lines.append(f"| {s['label']} | `{s['path']}` | {s['rows']} | {s['first']} | {s['last']} | {s['role']} |")
    lines += ["", "## Session convention", "", f"Daily session date = timestamp converted to `{cfg.get('session_timezone')}` and local calendar date.", "", "## Lookahead guard", "", "State for day t uses prior-day TR and ATR over completed prior sessions only."]
    (out / "source_lineage.md").write_text("\n".join(lines), encoding="utf-8")


def write_verdict(out: Path, cfg: dict[str, Any], ok: bool, reasons: list[str], phase2: bool) -> str:
    verdict = "regime_proxy_rejected" if not ok else ("regime_proxy_useful_but_no_signal_edge" if not phase2 else "conditional_signal_edge_diagnostic_only")
    text = ["# ATR Regime Conditioning Verdict", "", f"Issue: {cfg.get('issue_url')}", "", f"Verdict: `{verdict}`", "", "This is a regime-conditioning research audit. It cannot approve paper/live trading and cannot directly promote a primary validation candidate.", "", "## Phase 1", "", f"Status: {'pass' if ok else 'fail'}", "", "Reasons:"]
    text += [f"- {r}" for r in reasons] or ["- none"]
    text += ["", "## Phase 2", "", f"Ran: {phase2}", "", "Guardrails:", "- Forbidden verdicts: pass_forward_validation, paper_ready, live_ready, primary_validation_candidate.", "- Any candidate validation must be opened as a separate issue."]
    (out / "VERDICT.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    return verdict


def source_info(df: pd.DataFrame, label: str, path: Path, role: str) -> dict[str, Any]:
    return {"label": label, "path": repo_rel(path), "rows": len(df), "first": df["timestamp"].min().isoformat(), "last": df["timestamp"].max().isoformat(), "role": role}


def main() -> None:
    a = parse_args(); cfg = json.loads(a.config.read_text(encoding="utf-8"))
    out = a.out_dir or Path(f"reports/atr_regime_conditioning_{a.date}")
    if out.exists() and any(out.iterdir()) and not a.force:
        raise SystemExit(f"{out} exists and is non-empty; pass --force")
    out.mkdir(parents=True, exist_ok=True)
    path = Path(cfg["data_sources"]["databento_ohlcv_1m"])
    df = read_ohlcv(path, cfg, "databento_ohlcv_1m")
    sources = [source_info(df, "databento_ohlcv_1m", path, "primary_long_history")]
    d = daily_state(df, cfg)
    d.to_csv(out / "daily_state_table.csv", index=False)
    distribution(d).to_csv(out / "state_distribution_by_year.csv", index=False)
    behavior(d, "state").to_csv(out / "next_day_behavior_by_state.csv", index=False)
    behavior(d, "range_ratio_bin").to_csv(out / "bin_grid_diagnostics.csv", index=False)
    ok, reasons = phase1_gate(d, cfg)
    phase2 = bool(a.run_phase2 and ok)
    empty_signal_outputs(out, "phase2_not_implemented_in_initial_scaffold" if phase2 else ("phase2_not_requested" if not a.run_phase2 else "phase1_failed"))
    if a.local_parity:
        lp = Path(cfg["data_sources"].get("local_ninja_ohlcv_1m", ""))
        if lp.exists():
            local = read_ohlcv(lp, cfg, "local_ninja_ohlcv_1m")
            sources.append(source_info(local, "local_ninja_ohlcv_1m", lp, "local_parity_recency_check"))
            behavior(daily_state(local, cfg), "state").to_csv(out / "local_ninja_parity_check.csv", index=False)
        else:
            pd.DataFrame([{"status": "not_available", "path": lp.as_posix()}]).to_csv(out / "local_ninja_parity_check.csv", index=False)
    else:
        pd.DataFrame([{"status": "not_requested"}]).to_csv(out / "local_ninja_parity_check.csv", index=False)
    state_def = {"proxy": "prior_day_TR/ATR20", "session_timezone": cfg.get("session_timezone"), **cfg["state_definition"]}
    (out / "state_definition.json").write_text(json.dumps(state_def, indent=2) + "\n", encoding="utf-8")
    write_lineage(out, cfg, sources)
    v = write_verdict(out, cfg, ok, reasons, phase2)
    meta = {"schema_version": 1, "issue": cfg.get("issue_url"), "verdict": v, "phase1_ok": ok, "phase1_reasons": reasons, "phase2_ran": phase2, "outputs": sorted(p.name for p in out.iterdir())}
    (out / "triage_metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    Path(f"ATR_REGIME_CONDITIONING_{a.date}.md").write_text((out / "VERDICT.md").read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Wrote {out}; verdict={v}")


if __name__ == "__main__":
    main()
