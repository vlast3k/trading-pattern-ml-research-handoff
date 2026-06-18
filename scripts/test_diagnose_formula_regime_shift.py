#!/usr/bin/env python3

import unittest

import numpy as np
import pandas as pd

from diagnose_formula_regime_shift import assign_period, population_stability_index


class DiagnoseFormulaRegimeShiftTests(unittest.TestCase):
    def test_assign_period_excludes_gap_days(self):
        days = pd.Series(["2026-05-15", "2026-05-16", "2026-05-18", "2026-05-25"])
        self.assertEqual(
            assign_period(days).tolist(),
            ["late_development", "excluded", "validation", "final_test"],
        )

    def test_psi_is_zero_for_identical_populations(self):
        values = pd.Series(np.arange(100, dtype=float))
        self.assertAlmostEqual(population_stability_index(values, values), 0.0)

    def test_psi_detects_distribution_shift(self):
        reference = pd.Series(np.arange(100, dtype=float))
        shifted = pd.Series(np.arange(100, dtype=float) + 1000.0)
        self.assertGreater(population_stability_index(reference, shifted), 1.0)

    def test_psi_detects_binary_category_shift(self):
        reference = pd.Series(np.zeros(100))
        shifted = pd.Series(np.ones(100))
        self.assertGreater(population_stability_index(reference, shifted), 1.0)


if __name__ == "__main__":
    unittest.main()
