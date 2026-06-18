#!/usr/bin/env python3

import unittest

import pandas as pd

from review_payoff_asymmetry import bootstrap_metrics, payoff_metrics, summarize_group


class ReviewPayoffAsymmetryTests(unittest.TestCase):
    def test_payoff_and_profit_factor_are_distinct(self):
        metrics = payoff_metrics(pd.Series([20.0, 20.0, -10.0, -10.0, -10.0]))
        self.assertAlmostEqual(metrics["payoff_ratio"], 2.0)
        self.assertAlmostEqual(metrics["profit_factor"], 4.0 / 3.0)
        self.assertAlmostEqual(metrics["win_rate"], 0.4)
        self.assertAlmostEqual(metrics["breakeven_win_rate"], 1.0 / 3.0)

    def test_largest_winner_robustness(self):
        metrics = payoff_metrics(pd.Series([100.0, 10.0, -20.0, -20.0]))
        self.assertGreater(metrics["profit_factor"], 2.0)
        self.assertLess(metrics["profit_factor_without_largest_winner"], 1.0)

    def test_bootstrap_handles_all_winning_samples(self):
        metrics = bootstrap_metrics(pd.Series([10.0] * 5), repetitions=100, seed=42)
        self.assertEqual(metrics["payoff_ratio_ci_low"], float("inf"))
        self.assertEqual(metrics["profit_factor_ci_low"], float("inf"))
        self.assertEqual(metrics["expectancy_ci_low"], 10.0)

    def test_confidence_gate_requires_winners_and_losers(self):
        group = pd.DataFrame({"net_pnl": [10.0] * 20})
        metrics = summarize_group(group, repetitions=100, seed=42)
        self.assertFalse(metrics["passes_confidence_gate"])


if __name__ == "__main__":
    unittest.main()
