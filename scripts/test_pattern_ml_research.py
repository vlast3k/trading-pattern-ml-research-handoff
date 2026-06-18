#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from pattern_ml_research import (
    HistoricalAnalogBaseline,
    ResearchConfig,
    Standardizer,
    choose_threshold,
    label_direction,
    select_nonoverlapping,
)


def synthetic_bars() -> pd.DataFrame:
    index = pd.date_range("2026-04-01T13:30:00Z", periods=40, freq="min")
    frame = pd.DataFrame(
        {
            "open": np.full(40, 100.0),
            "high": np.full(40, 100.5),
            "low": np.full(40, 99.5),
            "close": np.full(40, 100.0),
            "quality": np.full(40, True),
            "atr_14": np.full(40, 1.0),
        },
        index=index,
    )
    return frame


class PatternMlResearchTests(unittest.TestCase):
    def config(self) -> ResearchConfig:
        root = Path(tempfile.gettempdir())
        return ResearchConfig(root, root / "baseline.csv", root / "out", horizon_minutes=5)

    def test_same_bar_stop_target_tie_is_pessimistic_stop(self):
        bars = synthetic_bars()
        bars.iloc[1, bars.columns.get_loc("high")] = 102.5
        bars.iloc[1, bars.columns.get_loc("low")] = 98.5
        label = label_direction(bars, 0, 1, self.config())
        self.assertIsNotNone(label)
        self.assertEqual(label["outcome"], "stop")
        self.assertEqual(label["gross_r"], -1.0)

    def test_label_rejects_gap_in_future_horizon(self):
        bars = synthetic_bars().drop(synthetic_bars().index[3])
        label = label_direction(bars, 0, 1, self.config())
        self.assertIsNone(label)

    def test_standardizer_uses_training_statistics(self):
        scaler = Standardizer().fit(np.array([[1.0], [3.0], [np.nan]]))
        transformed = scaler.transform(np.array([[2.0], [100.0]]))
        self.assertAlmostEqual(float(transformed[0, 0]), 0.0)
        self.assertGreater(float(transformed[1, 0]), 10.0)

    def test_analog_returns_training_row_ids(self):
        model = HistoricalAnalogBaseline(neighbors=2).fit(
            np.array([[0.0], [1.0], [10.0]]),
            np.array([0.0, 1.0, 0.0]),
            np.array([11, 12, 13]),
        )
        score, neighbors = model.predict_proba(np.array([[0.8]]), return_neighbors=True)
        self.assertGreater(float(score[0]), 0.5)
        self.assertEqual(set(neighbors[0]), {11, 12})

    def test_nonoverlap_uses_actual_exit_time(self):
        frame = pd.DataFrame(
            {
                "decision_time": pd.to_datetime(
                    ["2026-04-01T13:30:00Z", "2026-04-01T13:35:00Z", "2026-04-01T13:40:00Z"]
                ),
                "exit_time": pd.to_datetime(
                    ["2026-04-01T13:38:00Z", "2026-04-01T13:36:00Z", "2026-04-01T13:45:00Z"]
                ),
                "score": [0.9, 0.8, 0.7],
                "direction": [1, -1, 1],
            }
        )
        selected = select_nonoverlapping(frame, 0.5)
        self.assertEqual(len(selected), 2)
        self.assertEqual(list(selected["score"]), [0.9, 0.7])

    def test_threshold_abstains_when_development_is_not_profitable(self):
        frame = pd.DataFrame(
            {
                "decision_time": pd.date_range("2026-04-01T13:30:00Z", periods=20, freq="35min"),
                "exit_time": pd.date_range("2026-04-01T13:35:00Z", periods=20, freq="35min"),
                "score": np.linspace(0.4, 0.9, 20),
                "direction": np.ones(20),
                "target_before_stop": np.zeros(20),
                "gross_r": -np.ones(20),
                "net_r": -np.ones(20),
                "net_pnl": -np.ones(20),
                "trading_day": ["2026-04-01"] * 20,
            }
        )
        self.assertGreater(choose_threshold(frame), 1.0)


if __name__ == "__main__":
    unittest.main()
