#!/usr/bin/env python3

import unittest

import pandas as pd

from monitor_formula_prospective import (
    load_new_trades,
    select_nonoverlapping,
    summarize,
    trading_day_bootstrap,
)


class MonitorFormulaProspectiveTests(unittest.TestCase):
    def test_empty_summary_is_collecting_state(self):
        summary = summarize(pd.DataFrame())
        self.assertEqual(summary["trades"], 0)
        self.assertEqual(summary["net_pnl"], 0.0)
        self.assertFalse(summary["passes_payoff_gate"])

    def test_summary_splits_chronologically(self):
        rows = pd.DataFrame(
            {
                "trading_day": ["2026-06-15", "2026-06-15", "2026-06-16", "2026-06-16"],
                "direction": ["long", "short", "long", "short"],
                "net_pnl": [10.0, -5.0, 20.0, -2.0],
                "profitable": [True, False, True, False],
            }
        )
        summary = summarize(rows)
        self.assertEqual(summary["trades"], 4)
        self.assertEqual(summary["first_half_pnl"], 5.0)
        self.assertEqual(summary["second_half_pnl"], 18.0)
        self.assertGreater(summary["payoff_ratio"], 1.0)

    def test_select_nonoverlapping_uses_exit_time(self):
        rows = pd.DataFrame(
            {
                "decision_time": pd.to_datetime(
                    ["2026-06-15T10:00:00Z", "2026-06-15T10:01:00Z", "2026-06-15T10:03:00Z"]
                ),
                "exit_time": pd.to_datetime(
                    ["2026-06-15T10:02:00Z", "2026-06-15T10:04:00Z", "2026-06-15T10:05:00Z"]
                ),
                "net_pnl": [1.0, 2.0, 3.0],
            }
        )
        selected = select_nonoverlapping(rows)
        self.assertEqual(selected["net_pnl"].tolist(), [1.0, 3.0])

    def test_loader_reconstructs_cost_and_removes_overlap(self):
        rows = pd.DataFrame(
            {
                "timeframe": [1, 1],
                "variant": ["vwap_delta_rejection", "vwap_delta_rejection"],
                "trading_day": ["2026-06-15", "2026-06-15"],
                "signal_time": ["2026-06-15T10:00:00Z", "2026-06-15T10:01:00Z"],
                "entry_time": ["2026-06-15T10:00:00Z", "2026-06-15T10:01:00Z"],
                "exit_time": ["2026-06-15T10:02:00Z", "2026-06-15T10:03:00Z"],
                "r": [1.0, 1.0],
                "risk_points": [10.0, 10.0],
                "direction": ["long", "long"],
            }
        )
        path = self.create_temp_csv(rows)
        selected = load_new_trades(path, "2026-06-12", 3.98, 1.0)
        self.assertEqual(len(selected), 1)
        self.assertAlmostEqual(selected.iloc[0]["gross_pnl"], 22.0)
        self.assertAlmostEqual(selected.iloc[0]["net_pnl"], 17.02)

    def test_trading_day_bootstrap_is_deterministic(self):
        rows = pd.DataFrame(
            {
                "trading_day": ["a", "a", "b", "b"],
                "net_pnl": [10.0, -2.0, 8.0, -1.0],
            }
        )
        first = trading_day_bootstrap(rows, 100, 7)
        second = trading_day_bootstrap(rows, 100, 7)
        self.assertEqual(first, second)
        self.assertGreater(first["expectancy_ci_low"], 0)

    def create_temp_csv(self, rows: pd.DataFrame):
        import tempfile
        from pathlib import Path

        handle = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        handle.close()
        path = Path(handle.name)
        rows.to_csv(path, index=False)
        self.addCleanup(path.unlink)
        return path


if __name__ == "__main__":
    unittest.main()
