import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import engine


class ChartMovingAverageTests(unittest.TestCase):
    def run_chart(self, count=240, start=None):
        close = 100 + np.arange(count, dtype=float)
        frame = pd.DataFrame({'Open': close, 'High': close + 2, 'Low': close - 2,
                              'Close': close, 'Volume': 100},
                             index=pd.date_range('2025-01-01', periods=count))
        with patch.object(engine, 'fetch_data', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('RB0', 'daily',
                {'fast_period': 20, 'slow_period': 55, 'fixed_size': 1}, start_date=start)
        self.assertNotIn('error', result)
        return result['kline_data']

    def test_short_visible_range_uses_prior_history(self):
        chart = self.run_chart(start='2025-07-20')  # Original bar index 200.
        self.assertEqual(len(chart['dates']), 40)
        self.assertEqual(chart['ma']['ma144'][0], 228.5)
        self.assertEqual(chart['ma']['ma20'][0], 290.5)
        self.assertEqual(chart['ma']['ma55'][0], 273.0)
        self.assertEqual(chart['ma']['strategy_fast'], chart['ma']['ma20'])
        self.assertEqual(chart['ma']['strategy_slow'], chart['ma']['ma55'])

    def test_144_requires_complete_history_and_contains_no_nan(self):
        chart = self.run_chart(count=160)
        self.assertEqual(chart['ma']['ma144'][:143], [None] * 143)
        self.assertEqual(chart['ma']['ma144'][143], 171.5)
        self.assertEqual(chart['ma']['ma144'][-1], 187.5)

    def test_appending_future_bars_does_not_change_past_averages(self):
        before = self.run_chart(count=160)['ma']
        after = self.run_chart(count=240)['ma']
        for key in ['ma20', 'ma55', 'ma144', 'strategy_fast', 'strategy_slow']:
            self.assertEqual(before[key], after[key][:160])
