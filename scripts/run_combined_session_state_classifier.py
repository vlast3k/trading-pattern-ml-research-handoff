#!/usr/bin/env python3
"""Issue #24 combined session-state classifier audit.

This combines the accepted Phase 1 state variables from Issues #22, #27, and
#23 using only fixed, predeclared intersections. It does not train a model,
optimize thresholds, run strategy signals, or approve trading.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path("config/combined_session_state_classifier_config.json"))
    p.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--force", action="store_true")
    p.add_argument("--include-supplemental", action="store_true", help="Also compute separated Databento 2026 Q1 combined output.")
    p.add_argument("--local-parity", action="store_true", help="Also compute under-sampled local Ninja sanity output.")
    return p.parse_args()


def repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except Exception:  # noqa: BLE001
        return path.as_posix()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, lineterminator="\n")


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_primary_tables(cfg: dict[str, Any]) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for key, path_text in cfg["primary_input_reports"].items():
        path = Path(path_text)
        if not path.exists():
            raise FileNotFoundError(f"Missing primary input table {key}: {path}")
        tables[key] = pd.read_csv(path)
    return tables


def child_modules() -> dict[str, Any]:
    return {
        "coiled_spring": load_module(Path("scripts/run_coiled_spring_globex_rth_morning.py"), "issue22_coiled"),
        "lunch_lull": load_module(Path("scripts/run_lunch_lull_exhaustion.py"), "issue27_lunch"),
        "inside_day_trap": load_module(Path("scripts/run_inside_day_trap.py"), "issue23_inside"),
    }


def build_child_tables_from_raw(
    cfg: dict[str, Any],
    modules: dict[str, Any],
    source_path: Path,
    window: dict[str, Any],
    cohort: str,
) -> dict[str, pd.DataFrame]:
    child_cfgs = {name: load_json(Path(path)) for name, path in cfg["child_configs"].items()}

    coiled = modules["coiled_spring"]
    coiled_raw = coiled.read_ohlcv(source_path, child_cfgs["coiled_spring"], cohort)
    coiled_table = coiled.build_session_table(coiled_raw, child_cfgs["coiled_spring"], window, cohort)

    lunch = modules["lunch_lull"]
    lunch_raw = lunch.read_ohlcv(source_path, child_cfgs["lunch_lull"], cohort)
    lunch_table = lunch.build_session_table(lunch_raw, child_cfgs["lunch_lull"], window, cohort)

    inside = modules["inside_day_trap"]
    inside_raw = inside.read_ohlcv(source_path, child_cfgs["inside_day_trap"], cohort)
    inside_filtered = inside.filter_by_local_session_date(inside_raw, child_cfgs["inside_day_trap"], window)
    inside_table = inside.build_session_table(inside_filtered, child_cfgs["inside_day_trap"])
    if not inside_table.empty:
        inside_table = inside.add_rest_vwap_cross_counts(inside_table, inside_filtered, child_cfgs["inside_day_trap"])

    return {
        "coiled_spring": coiled_table,
        "lunch_lull": lunch_table,
        "inside_day_trap": inside_table,
    }


def normalize_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin(["true", "1", "yes"])


def combined_session_table(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    coiled = tables["coiled_spring"].copy()
    lunch = tables["lunch_lull"].copy()
    inside = tables["inside_day_trap"].copy()

    coiled_keep = coiled[[
        "root",
        "session_date",
        "cohort",
        "globex_state",
        "globex_range_ratio",
        "rth_morning_range_div_atr20",
        "closed_outside_globex_range",
        "failed_breakout_reentry",
    ]].rename(columns={"cohort": "coiled_cohort"})

    lunch_keep = lunch[[
        "root",
        "session_date",
        "cohort",
        "morning_state",
        "morning_range_ratio",
        "lunch_range_div_morning_range",
        "lunch_range_contraction",
        "trend_continuation_failure",
        "vwap_cross",
    ]].rename(columns={"cohort": "lunch_cohort"})

    inside_keep = inside[[
        "root",
        "session_date",
        "state",
        "sub_state",
        "rest_rth_range_div_first_hour_range",
        "new_rth_high_or_low_after_10_30",
        "new_session_high_or_low_after_10_30",
        "chop_index",
        "first_hour_vwap_cross_count",
    ]].rename(columns={"state": "inside_state", "sub_state": "inside_sub_state"})

    out = coiled_keep.merge(lunch_keep, on=["root", "session_date"], how="inner")
    out = out.merge(inside_keep, on=["root", "session_date"], how="inner")
    if out.empty:
        return out

    for col in [
        "closed_outside_globex_range",
        "failed_breakout_reentry",
        "lunch_range_contraction",
        "trend_continuation_failure",
        "vwap_cross",
        "new_rth_high_or_low_after_10_30",
        "new_session_high_or_low_after_10_30",
    ]:
        out[col] = normalize_bool(out[col])

    out["year"] = pd.to_datetime(out["session_date"]).dt.year
    out["month"] = pd.to_datetime(out["session_date"]).dt.strftime("%Y-%m")
    out["week"] = pd.to_datetime(out["session_date"]).dt.strftime("%G-W%V")
    out["eligible_primary_states"] = (
        (out["globex_state"] != "unclassified")
        & (out["morning_state"] != "unclassified")
        & (out["inside_state"].isin(["trapped", "broken"]))
    )
    return out.sort_values(["root", "session_date"]).reset_index(drop=True)


def mask_for_conditions(df: pd.DataFrame, conditions: dict[str, str]) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for col, value in conditions.items():
        mask &= df[col] == value
    return mask


def individual_mask(df: pd.DataFrame, label: str) -> pd.Series:
    mapping = {
        "globex_compression": ("globex_state", "compression"),
        "globex_expansion": ("globex_state", "expansion"),
        "inside_trapped": ("inside_state", "trapped"),
        "inside_broken": ("inside_state", "broken"),
        "morning_exhaustion": ("morning_state", "exhaustion"),
    }
    if label not in mapping:
        raise KeyError(f"Unknown individual label: {label}")
    col, value = mapping[label]
    return df[col] == value


def metric_value(part: pd.DataFrame, metric: str) -> float:
    if part.empty:
        return float("nan")
    if metric == "median_rest_rth_range_div_first_hour_range":
        return float(part["rest_rth_range_div_first_hour_range"].median())
    if metric == "new_session_high_or_low_after_10_30_rate":
        return float(part["new_session_high_or_low_after_10_30"].mean())
    if metric == "median_lunch_range_div_morning_range":
        return float(part["lunch_range_div_morning_range"].median())
    if metric == "lunch_range_contraction_rate":
        return float(part["lunch_range_contraction"].mean())
    if metric == "mean_chop_index":
        return float(part["chop_index"].mean())
    raise KeyError(f"Unknown metric: {metric}")


def better_delta(value: float, baseline: float, direction: str) -> float:
    if pd.isna(value) or pd.isna(baseline):
        return float("nan")
    return value - baseline if direction == "higher" else baseline - value


def common_outcomes(part: pd.DataFrame) -> dict[str, Any]:
    if part.empty:
        return {
            "days": 0,
            "median_rest_rth_range_div_first_hour_range": float("nan"),
            "new_session_high_or_low_after_10_30_rate": float("nan"),
            "median_lunch_range_div_morning_range": float("nan"),
            "lunch_range_contraction_rate": float("nan"),
            "mean_chop_index": float("nan"),
            "mean_first_hour_vwap_cross_count": float("nan"),
            "vwap_cross_rate": float("nan"),
        }
    return {
        "days": int(len(part)),
        "median_rest_rth_range_div_first_hour_range": float(part["rest_rth_range_div_first_hour_range"].median()),
        "new_session_high_or_low_after_10_30_rate": float(part["new_session_high_or_low_after_10_30"].mean()),
        "median_lunch_range_div_morning_range": float(part["lunch_range_div_morning_range"].median()),
        "lunch_range_contraction_rate": float(part["lunch_range_contraction"].mean()),
        "mean_chop_index": float(part["chop_index"].mean()),
        "mean_first_hour_vwap_cross_count": float(part["first_hour_vwap_cross_count"].mean()),
        "vwap_cross_rate": float(part["vwap_cross"].mean()),
    }


def combined_state_summary(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    eligible = df[df["eligible_primary_states"]].copy()
    for root, root_df in eligible.groupby("root"):
        rows.append({
            "root": root,
            "combined_state": "unconditional_eligible",
            "target_window": "all",
            "question": "All sessions with classified child-state inputs.",
            **common_outcomes(root_df),
        })
        for cand in cfg["candidate_combined_states"]:
            part = root_df[mask_for_conditions(root_df, cand["conditions"])]
            rows.append({
                "root": root,
                "combined_state": cand["name"],
                "target_window": cand["target_window"],
                "question": cand["question"],
                **common_outcomes(part),
            })
    return pd.DataFrame(rows)


def outcomes_by_combined_state(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    summary = combined_state_summary(df, cfg)
    cols = [
        "root",
        "combined_state",
        "target_window",
        "days",
        "median_rest_rth_range_div_first_hour_range",
        "new_session_high_or_low_after_10_30_rate",
        "median_lunch_range_div_morning_range",
        "lunch_range_contraction_rate",
        "mean_chop_index",
        "mean_first_hour_vwap_cross_count",
        "vwap_cross_rate",
    ]
    return summary[cols]


def comparison_single_vs_combined(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    eligible = df[df["eligible_primary_states"]].copy()
    min_improvement = float(cfg["phase1_gates"]["min_material_improvement"])
    for root, root_df in eligible.groupby("root"):
        unconditional = root_df
        for cand in cfg["candidate_combined_states"]:
            combined = root_df[mask_for_conditions(root_df, cand["conditions"])]
            for metric in cand["metrics"]:
                metric_name = metric["name"]
                direction = metric["direction"]
                unconditional_value = metric_value(unconditional, metric_name)
                combined_value = metric_value(combined, metric_name)
                best_label = ""
                best_value = float("nan")
                best_delta = -float("inf")
                best_days = 0
                for label in cand["best_individual_labels"]:
                    part = root_df[individual_mask(root_df, label)]
                    value = metric_value(part, metric_name)
                    delta = better_delta(value, unconditional_value, direction)
                    if delta > best_delta:
                        best_delta = delta
                        best_label = label
                        best_value = value
                        best_days = int(len(part))
                lift_unconditional = better_delta(combined_value, unconditional_value, direction)
                lift_best = better_delta(combined_value, best_value, direction)
                rows.append({
                    "root": root,
                    "target_window": cand["target_window"],
                    "combined_state": cand["name"],
                    "metric": metric_name,
                    "direction": direction,
                    "combined_days": int(len(combined)),
                    "unconditional_days": int(len(unconditional)),
                    "best_individual_label": best_label,
                    "best_individual_days": best_days,
                    "unconditional_value": unconditional_value,
                    "best_individual_value": best_value,
                    "combined_value": combined_value,
                    "lift_vs_unconditional": lift_unconditional,
                    "lift_vs_best_individual": lift_best,
                    "materially_improves_best_individual": bool(lift_best >= min_improvement),
                })
    return pd.DataFrame(rows)


def year_splits(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    eligible = df[df["eligible_primary_states"]].copy()
    for (root, year), root_df in eligible.groupby(["root", "year"]):
        rows.append({
            "root": root,
            "year": int(year),
            "combined_state": "unconditional_eligible",
            **common_outcomes(root_df),
        })
        for cand in cfg["candidate_combined_states"]:
            part = root_df[mask_for_conditions(root_df, cand["conditions"])]
            rows.append({
                "root": root,
                "year": int(year),
                "combined_state": cand["name"],
                **common_outcomes(part),
            })
    return pd.DataFrame(rows)


def concentration_checks(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    gates = cfg["phase1_gates"]
    eligible = df[df["eligible_primary_states"]].copy()
    for root, root_df in eligible.groupby("root"):
        for cand in cfg["candidate_combined_states"]:
            part = root_df[mask_for_conditions(root_df, cand["conditions"])]
            if part.empty:
                rows.append({
                    "root": root,
                    "combined_state": cand["name"],
                    "days": 0,
                    "years_with_min_rows": 0,
                    "largest_month_share": float("nan"),
                    "largest_week_share": float("nan"),
                    "sparse": True,
                    "concentrated": False,
                })
                continue
            years = int((part.groupby("year").size() >= int(gates["min_days_per_state_per_year"])).sum())
            month_share = float(part.groupby("month").size().max() / len(part))
            week_share = float(part.groupby("week").size().max() / len(part))
            rows.append({
                "root": root,
                "combined_state": cand["name"],
                "days": int(len(part)),
                "years_with_min_rows": years,
                "largest_month_share": month_share,
                "largest_week_share": week_share,
                "sparse": bool(len(part) < int(gates["min_combined_days"])),
                "concentrated": bool(
                    month_share > float(gates["max_largest_month_share"])
                    or week_share > float(gates["max_largest_week_share"])
                ),
            })
    return pd.DataFrame(rows)


def verdict_and_reasons(df: pd.DataFrame, cfg: dict[str, Any], comparison: pd.DataFrame, concentration: pd.DataFrame) -> tuple[str, list[str]]:
    if df.empty:
        return "incomplete_reproducibility", ["no_joined_sessions"]
    gates = cfg["phase1_gates"]
    reasons: list[str] = []
    passing_candidates: list[str] = []
    for (root, candidate), part in comparison.groupby(["root", "combined_state"]):
        c = concentration[(concentration["root"] == root) & (concentration["combined_state"] == candidate)]
        if c.empty:
            reasons.append(f"{root}:{candidate}:missing_concentration")
            continue
        crow = c.iloc[0]
        if bool(crow["sparse"]):
            reasons.append(f"{root}:{candidate}:too_sparse:{int(crow['days'])}")
            continue
        if int(crow["years_with_min_rows"]) < int(gates["min_years_with_combined"]):
            reasons.append(f"{root}:{candidate}:insufficient_years:{int(crow['years_with_min_rows'])}")
            continue
        if bool(crow["concentrated"]):
            reasons.append(f"{root}:{candidate}:concentrated")
            continue
        improved = int(part["materially_improves_best_individual"].sum())
        if improved >= int(gates["min_metrics_improved_per_candidate"]):
            passing_candidates.append(f"{root}:{candidate}")

    if not passing_candidates:
        reasons.append("no_non_sparse_combined_state_materially_improves_best_individual_across_required_metrics")
        return "session_regime_proxy_rejected", sorted(set(reasons))
    return "session_regime_proxy_diagnostic_only", []


def state_inputs_used(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_22_coiled_spring": {
            "source": "reports/coiled_spring_globex_rth_morning_20260624",
            "state": "Globex range / prior 20 completed Globex-session median range",
            "compression": "ratio < 0.7",
            "neutral": "0.7 <= ratio <= 1.3",
            "expansion": "ratio > 1.3",
            "accepted_interpretation": "Volatility/session-state input only; not a standalone breakout filter.",
            "preserved_primary_metrics": {
                "MNQ_compression_median_RTH_morning_range_ATR20": 0.437,
                "MNQ_expansion_median_RTH_morning_range_ATR20": 0.740,
                "NQ_compression_median_RTH_morning_range_ATR20": 0.437,
                "NQ_expansion_median_RTH_morning_range_ATR20": 0.724
            }
        },
        "issue_27_lunch_lull_exhaustion": {
            "source": "reports/lunch_lull_exhaustion_20260624",
            "state": "RTH morning range / prior 20 completed RTH-morning median range",
            "exhaustion": "ratio > 1.5",
            "standard": "ratio <= 1.5",
            "accepted_interpretation": "Strongest Phase 1 state; predicts lunch compression, not yet a tradable signal.",
            "preserved_primary_metrics": {
                "MNQ_exhaustion_median_lunch_morning_range": 0.522,
                "MNQ_unconditional_median_lunch_morning_range": 0.700,
                "MNQ_exhaustion_contraction_rate": 0.433,
                "MNQ_unconditional_contraction_rate": 0.210,
                "NQ_exhaustion_median_lunch_morning_range": 0.524,
                "NQ_unconditional_median_lunch_morning_range": 0.698,
                "NQ_exhaustion_contraction_rate": 0.430,
                "NQ_unconditional_contraction_rate": 0.211
            }
        },
        "issue_23_inside_day_trap": {
            "source": "reports/inside_day_trap_20260624",
            "state": "First RTH hour inside or broken versus completed Globex range",
            "trapped": "first_hour_high < Globex_high and first_hour_low > Globex_low",
            "broken": "first_hour_high >= Globex_high or first_hour_low <= Globex_low",
            "accepted_interpretation": "Context input; delayed/internal RTH expansion, not a standalone chop or directional signal.",
            "preserved_primary_metrics": {
                "MNQ_trapped_median_rest_first_hour_range": 1.519,
                "MNQ_unconditional_median_rest_first_hour_range": 1.344,
                "MNQ_trapped_new_full_session_extreme_rate": 0.770,
                "MNQ_unconditional_new_full_session_extreme_rate": 0.846,
                "NQ_trapped_median_rest_first_hour_range": 1.534,
                "NQ_unconditional_median_rest_first_hour_range": 1.348,
                "NQ_trapped_new_full_session_extreme_rate": 0.775,
                "NQ_unconditional_new_full_session_extreme_rate": 0.849
            }
        },
        "candidate_combined_states": cfg["candidate_combined_states"],
        "prohibitions": [
            "no_strategy_signals",
            "no_threshold_optimization",
            "no_complex_model",
            "no_paper_or_live_trading_approval",
            "no_NinjaTrader_execution",
            "no_broker_or_IBKR_work"
        ]
    }


def write_source_lineage(path: Path, cfg: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    lines = [
        "# Source Lineage",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| Source | Path | Rows | Role |",
        "|---|---|---:|---|",
    ]
    for src in sources:
        lines.append(f"| {src['source']} | `{src['path']}` | {src['rows']} | {src['role']} |")
    lines.extend([
        "",
        "## Combination Method",
        "",
        "Primary evidence joins the merged child issue session-state tables on `root` and `session_date`.",
        "Supplemental and local parity tables, when requested, are rebuilt through the accepted child audit scripts using their frozen state definitions and the same source data conventions.",
        "",
        "No model is trained. No thresholds are optimized. Only predeclared intersections from Issue #24 are evaluated.",
        "",
        "## Data Windows",
        "",
        f"Primary window: `{cfg['primary_date_filter']['start']}` through `{cfg['primary_date_filter']['end']}`.",
        f"Supplemental window: `{cfg['supplemental_date_filter']['start']}` through `{cfg['supplemental_date_filter']['end']}` when requested.",
        "Local Ninja parity is under-sampled recency/sanity context only, not confirmatory evidence.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_verdict(path: Path, cfg: dict[str, Any], verdict: str, reasons: list[str], comparison: pd.DataFrame, out_dir: Path) -> None:
    lunch_rows = comparison[
        (comparison["target_window"] == "lunch")
        & (comparison["metric"].isin(["median_lunch_range_div_morning_range", "lunch_range_contraction_rate"]))
    ].copy()
    rest_rows = comparison[comparison["target_window"] == "rest_of_rth"].copy()
    lines = [
        "# Combined Session-State Classifier Verdict",
        "",
        f"Issue: {cfg['issue_url']}",
        f"Parent roadmap: {cfg['parent_issue_url']}",
        "",
        f"Verdict: `{verdict}`",
        "",
        "This is a combined Phase 1 state-classifier audit only. It does not run RSI, VWAP-reversion, continuation, Donchian, or any other strategy signal and cannot approve trading.",
        "",
        "## Interpretation",
        "",
    ]
    if verdict == "session_regime_proxy_rejected":
        lines.append("- The fixed combined intersections did not materially improve over the relevant best individual state inputs under the frozen gates.")
        lines.append("- The strongest individual input remains Lunch Lull Exhaustion from Issue #27; adding Globex or first-hour labels did not create a superior lunch classifier.")
        lines.append("- Some intersections look better in-sample, but the promising lunch-compression subset is too sparse to accept.")
    elif verdict == "session_regime_proxy_diagnostic_only":
        lines.append("- At least one fixed combined state improves over its relevant individual inputs, but this remains diagnostic context only.")
    else:
        lines.append("- Reproducibility is incomplete or inconclusive.")
    lines.extend(["", "Gate reasons:"])
    lines.extend([f"- {reason}" for reason in reasons] or ["- none"])
    lines.extend([
        "",
        "Guardrails:",
        "- No strategy signal was run.",
        "- No RSI was run or inferred.",
        "- No paper/live approval.",
        "- No NinjaTrader execution.",
        "- No broker/IBKR work.",
        "- No primary validation candidate.",
        "",
        "## Lunch Comparison Against Best Individual",
        "",
        "| Root | Combined State | Metric | Best Individual | Best Value | Combined Value | Lift vs Best |",
        "|---|---|---|---|---:|---:|---:|",
    ])
    for _, row in lunch_rows.sort_values(["root", "combined_state", "metric"]).iterrows():
        lines.append(
            f"| {row['root']} | {row['combined_state']} | {row['metric']} | {row['best_individual_label']} | "
            f"{row['best_individual_value']:.3f} | {row['combined_value']:.3f} | {row['lift_vs_best_individual']:.3f} |"
        )
    lines.extend([
        "",
        "## Rest-Of-RTH Comparison",
        "",
        "| Root | Combined State | Metric | Best Individual | Best Value | Combined Value | Lift vs Best |",
        "|---|---|---|---|---:|---:|---:|",
    ])
    for _, row in rest_rows.sort_values(["root", "combined_state", "metric"]).iterrows():
        lines.append(
            f"| {row['root']} | {row['combined_state']} | {row['metric']} | {row['best_individual_label']} | "
            f"{row['best_individual_value']:.3f} | {row['combined_value']:.3f} | {row['lift_vs_best_individual']:.3f} |"
        )
    lines.extend([
        "",
        "## Artifacts",
        "",
        f"- Report directory: `{repo_rel(out_dir)}`",
        "- Required tables: `state_inputs_used.json`, `combined_state_summary.csv`, `outcomes_by_combined_state.csv`, `comparison_single_vs_combined.csv`, `year_splits.csv`, `supplemental_2026_q1.csv`, `local_ninja_parity_check.csv`, `triage_metadata.json`.",
        f"- Final verdict: `{verdict}`.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def lineage_entry(source: str, path: Path, df: pd.DataFrame, role: str) -> dict[str, Any]:
    return {"source": source, "path": repo_rel(path), "rows": int(len(df)), "role": role}


def process_window(tables: dict[str, pd.DataFrame], cfg: dict[str, Any]) -> dict[str, pd.DataFrame]:
    combined = combined_session_table(tables)
    comparison = comparison_single_vs_combined(combined, cfg) if not combined.empty else pd.DataFrame()
    concentration = concentration_checks(combined, cfg) if not combined.empty else pd.DataFrame()
    return {
        "combined_session_table": combined,
        "combined_state_summary": combined_state_summary(combined, cfg) if not combined.empty else pd.DataFrame(),
        "outcomes_by_combined_state": outcomes_by_combined_state(combined, cfg) if not combined.empty else pd.DataFrame(),
        "comparison_single_vs_combined": comparison,
        "year_splits": year_splits(combined, cfg) if not combined.empty else pd.DataFrame(),
        "concentration_or_stability_checks": concentration,
    }


def add_window_column(df: pd.DataFrame, window: str) -> pd.DataFrame:
    out = df.copy()
    if not out.empty:
        out.insert(0, "window", window)
    return out


def main() -> int:
    args = parse_args()
    cfg = load_json(args.config)
    out_dir = args.out_dir or Path("reports") / f"combined_session_state_classifier_{args.date}"
    top_report = Path(f"COMBINED_SESSION_STATE_CLASSIFIER_{args.date}.md")
    if out_dir.exists():
        if not args.force:
            raise SystemExit(f"Output exists: {out_dir}; pass --force")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    primary_tables = read_primary_tables(cfg)
    primary = process_window(primary_tables, cfg)
    comparison = primary["comparison_single_vs_combined"]
    concentration = primary["concentration_or_stability_checks"]
    verdict, reasons = verdict_and_reasons(primary["combined_session_table"], cfg, comparison, concentration)

    write_csv(primary["combined_session_table"], out_dir / "combined_session_table.csv")
    write_csv(primary["combined_state_summary"], out_dir / "combined_state_summary.csv")
    write_csv(primary["outcomes_by_combined_state"], out_dir / "outcomes_by_combined_state.csv")
    write_csv(comparison, out_dir / "comparison_single_vs_combined.csv")
    write_csv(primary["year_splits"], out_dir / "year_splits.csv")
    write_csv(concentration, out_dir / "concentration_or_stability_checks.csv")

    sources: list[dict[str, Any]] = []
    for key, path_text in cfg["primary_input_reports"].items():
        path = Path(path_text)
        sources.append(lineage_entry(key, path, primary_tables[key], "primary_merged_child_issue_table"))

    modules = child_modules()
    supplemental_out = pd.DataFrame()
    if args.include_supplemental:
        data_path = Path(cfg["data_sources"]["databento_ohlcv_1m"])
        supplemental_tables = build_child_tables_from_raw(
            cfg,
            modules,
            data_path,
            cfg["supplemental_date_filter"],
            cfg["supplemental_date_filter"]["label"],
        )
        supplemental = process_window(supplemental_tables, cfg)
        supplemental_out = add_window_column(supplemental["comparison_single_vs_combined"], cfg["supplemental_date_filter"]["label"])
        sources.append(lineage_entry("databento_ohlcv_1m_full_view", data_path, supplemental_tables["coiled_spring"], "supplemental_recomputed_child_states"))
    write_csv(supplemental_out, out_dir / "supplemental_2026_q1.csv")

    local_out = pd.DataFrame()
    if args.local_parity:
        local_path = Path(cfg["data_sources"]["local_ninja_ohlcv_1m"])
        if local_path.exists():
            local_tables = build_child_tables_from_raw(
                cfg,
                modules,
                local_path,
                {
                    "start": "1900-01-01",
                    "end": "2100-12-31",
                    "label": "local_ninja_under_sampled_sanity_only",
                },
                "local_ninja_under_sampled_sanity_only",
            )
            local = process_window(local_tables, cfg)
            local_out = add_window_column(local["comparison_single_vs_combined"], "local_ninja_under_sampled_sanity_only")
            sources.append(lineage_entry("local_ninja_ohlcv_1m", local_path, local_tables["coiled_spring"], "under_sampled_recency_sanity_only"))
    write_csv(local_out, out_dir / "local_ninja_parity_check.csv")

    state_inputs = state_inputs_used(cfg)
    (out_dir / "state_inputs_used.json").write_text(json.dumps(state_inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_source_lineage(out_dir / "source_lineage.md", cfg, sources)
    write_verdict(out_dir / "VERDICT.md", cfg, verdict, reasons, comparison, out_dir)
    write_verdict(top_report, cfg, verdict, reasons, comparison, out_dir)

    metadata = {
        "schema_version": 1,
        "issue": cfg["issue_url"],
        "parent_issue": cfg["parent_issue_url"],
        "phase": "combined_state_classifier_audit_only",
        "verdict": verdict,
        "gate_reasons": reasons,
        "primary_date_filter": cfg["primary_date_filter"],
        "supplemental_included": bool(args.include_supplemental),
        "local_parity_included": bool(args.local_parity),
        "strategy_signals_ran": False,
        "rsi_ran": False,
        "model_trained": False,
        "thresholds_optimized": False,
        "permitted_verdicts": cfg["permitted_verdicts"],
        "forbidden_verdicts": cfg["forbidden_verdicts"],
        "outputs": sorted([
            top_report.name,
            "VERDICT.md",
            "combined_session_table.csv",
            "combined_state_summary.csv",
            "comparison_single_vs_combined.csv",
            "concentration_or_stability_checks.csv",
            "local_ninja_parity_check.csv",
            "outcomes_by_combined_state.csv",
            "source_lineage.md",
            "state_inputs_used.json",
            "supplemental_2026_q1.csv",
            "triage_metadata.json",
            "year_splits.csv",
        ]),
    }
    (out_dir / "triage_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out_dir}; verdict={verdict}; top_report={top_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
