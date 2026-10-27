import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core.candle_compare import boundary, compare_market_candles, find_similar_candles


def sample():
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, 180))
    df = pd.DataFrame({'Open': close - 0.1, 'High': close + 0.8, 'Low': close - 0.8, 'Close': close}, index=pd.date_range('2025-01-01', periods=180))
    # Known perfect earlier pattern at a different price and amplitude.
    df.iloc[-10:] = df.iloc[30:40].to_numpy() * 2 + 500
    return df


def ma_sample():
    rng = np.random.default_rng(170)
    close = 100 + np.cumsum(rng.normal(0, 0.3, 720))
    df = pd.DataFrame({'Open': close - 0.1, 'High': close + 0.8, 'Low': close - 0.8, 'Close': close},
                      index=pd.date_range('2023-01-01', periods=720))
    # Both candidates have identical candle shapes. Only the later candidate
    # also shares all 143 preceding bars needed by the longest selected SMA.
    df.iloc[207:370] = df.iloc[557:720].to_numpy() * 2 + 500
    df.iloc[180:200] = df.iloc[700:720].to_numpy()
    return df


class CandleCompareTests(unittest.TestCase):
    def test_selected_mas_change_ranking_for_identical_candles(self):
        df = ma_sample()
        plain = find_similar_candles(df, window_size=20, continuation_bars=0)
        self.assertEqual(plain['matches'][0]['start'], str(df.index[180]))
        for periods in ([20], [60], [144], [20, 60, 144]):
            result = find_similar_candles(df, window_size=20, continuation_bars=0, ma_periods=periods)
            self.assertEqual(result['matches'][0]['start'], str(df.index[350]))
            self.assertEqual(result['matches'][0]['similarity'], 100)
            self.assertEqual(result['parameters']['ma_periods'], periods)
            for item in result['matches']:
                for period in periods:
                    self.assertTrue(all(value is not None for value in item['ma'][f'ma{period}']))
            json.dumps(result, allow_nan=False)

    def test_selected_ma_score_uses_equal_price_and_ma_weights(self):
        df = ma_sample()
        result = find_similar_candles(df, window_size=20, continuation_bars=0, ma_periods=[60],
                                      search_start=str(df.index[180]), search_end=str(df.index[199]))
        old, target = df.iloc[180:200], df.iloc[-20:]
        ma = df.Close.rolling(60).mean()
        old_scale, target_scale = old.Close.std(ddof=0), target.Close.std(ddof=0)
        old_ma = (ma.iloc[180:200].to_numpy() - old.Close.mean()) / old_scale
        target_ma = (ma.iloc[-20:].to_numpy() - target.Close.mean()) / target_scale
        # OHLC shapes are affine equivalents, so their distance is zero.
        expected = 100 * np.exp(-np.sqrt(0.5 * np.mean((old_ma - target_ma) ** 2)))
        self.assertAlmostEqual(result['matches'][0]['similarity'], round(expected, 2))

    def test_selected_ma_requires_target_history_and_valid_periods(self):
        with self.assertRaisesRegex(ValueError, '历史不足'):
            find_similar_candles(sample().iloc[:100], window_size=10, ma_periods=[144])
        for periods in ([55], [60.0], ['20'], '20'):
            with self.assertRaisesRegex(ValueError, '仅支持'):
                find_similar_candles(sample(), window_size=10, ma_periods=periods)
        result = find_similar_candles(ma_sample(), window_size=20, ma_periods=[60, 20, 60])
        self.assertEqual(result['parameters']['ma_periods'], [20, 60])

    def test_selected_mas_do_not_use_data_after_target_cutoff(self):
        df = ma_sample()
        args = dict(window_size=20, ma_periods=[20, 60, 144], target_end=str(df.index[600]))
        first = find_similar_candles(df, **args)
        df.iloc[601:] = df.iloc[601:] * 10
        self.assertEqual(first, find_similar_candles(df, **args))

    def test_normalized_ma_preserves_price_location_and_continuation_scale(self):
        df = ma_sample()
        result = find_similar_candles(df, window_size=20, ma_periods=[60])
        target = result['target']
        mean, scale = df.Close.iloc[-20:].mean(), df.Close.iloc[-20:].std(ddof=0)
        expected = (df.Close.rolling(60).mean().iloc[-20] - mean) / scale
        self.assertAlmostEqual(target['normalized_ma']['ma60'][0], expected, places=6)
        item = result['matches'][0]
        start = df.index.get_loc(pd.Timestamp(item['start']))
        window = df.Close.iloc[start:start + 20]
        expected_next = (df.Close.rolling(60).mean().iloc[start + 20] - window.mean()) / window.std(ddof=0)
        self.assertAlmostEqual(item['following']['normalized_ma']['ma60'][0], expected_next, places=6)

    def test_affine_equivalent_pattern_ranks_first(self):
        df = sample()
        result = find_similar_candles(df, window_size=10, top_k=5, min_similarity=0)
        self.assertEqual(result['matches'][0]['start'], str(df.index[30]))
        self.assertEqual(result['matches'][0]['similarity'], 100)
        self.assertEqual(result['target']['bars'], 10)
        self.assertEqual(result['target']['start'], str(df.index[-10]))
        json.dumps(result, allow_nan=False)

    def test_perfect_match_passes_100_point_threshold(self):
        result = find_similar_candles(sample(), window_size=10, min_similarity=100)
        self.assertEqual(len(result['matches']), 1)
        self.assertEqual(result['matches'][0]['similarity'], 100)

    def test_patterns_and_continuations_are_before_target(self):
        df = sample()
        result = find_similar_candles(df, window_size=10, min_similarity=0, top_k=20, continuation_bars=20)
        ranges = []
        for item in result['matches']:
            self.assertLess(pd.Timestamp(item['end']), pd.Timestamp(result['target']['start']))
            self.assertLess(pd.Timestamp(item['following']['end']), pd.Timestamp(result['target']['start']))
            self.assertEqual(item['following']['bars'], 20)
            start = df.index.get_loc(pd.Timestamp(item['start']))
            self.assertTrue(all(abs(start - previous) >= 10 for previous in ranges))
            ranges.append(start)

    def test_search_range_bounds_entire_matching_window(self):
        df = sample()
        result = find_similar_candles(df, window_size=10, min_similarity=0,
                                      search_start=str(df.index[30]), search_end=str(df.index[39]))
        self.assertEqual(len(result['matches']), 1)
        self.assertEqual(result['matches'][0]['start'], str(df.index[30]))
        self.assertEqual(result['matches'][0]['end'], str(df.index[39]))

    def test_no_data_after_historical_target_is_used(self):
        df = sample()
        cutoff = str(df.index[110])
        first = find_similar_candles(df, window_size=10, target_end=cutoff, min_similarity=0)
        changed = df.copy()
        changed.iloc[111:] = changed.iloc[111:] * 10 + 300
        second = find_similar_candles(changed, window_size=10, target_end=cutoff, min_similarity=0)
        self.assertEqual(first, second)

    def test_no_following_mode(self):
        result = find_similar_candles(sample(), window_size=10, min_similarity=0, continuation_bars=0)
        item = result['matches'][0]
        self.assertEqual(item['following']['dates'], [])
        self.assertIsNone(item['following_return_pct'])

    def test_following_return_uses_match_end_price(self):
        df = sample()
        result = find_similar_candles(df, window_size=10, min_similarity=0, continuation_bars=5)
        item = result['matches'][0]
        expected = (df.Close.iloc[44] / df.Close.iloc[39] - 1) * 100
        self.assertAlmostEqual(item['following_return_pct'], expected, places=4)

    def test_target_averages_use_history_before_visible_window(self):
        df = sample()
        result = find_similar_candles(df, window_size=10, min_similarity=0)
        start = len(df) - 10
        for period in (20, 55, 144):
            values = result['target']['ma'][f'ma{period}']
            self.assertEqual(len(values), 10)
            expected = df.Close.iloc[start - period + 1:start + 1].mean()
            self.assertAlmostEqual(values[0], expected, places=6)

    def test_match_and_following_share_trailing_averages(self):
        df = sample()
        result = find_similar_candles(df, window_size=10, min_similarity=0, continuation_bars=20)
        item = result['matches'][0]
        self.assertAlmostEqual(item['ma']['ma20'][0], df.Close.iloc[11:31].mean(), places=6)
        self.assertAlmostEqual(item['following']['ma']['ma20'][0], df.Close.iloc[21:41].mean(), places=6)
        self.assertTrue(all(value is None for value in item['ma']['ma55']))
        self.assertTrue(all(value is None for value in item['following']['ma']['ma55'][:14]))
        self.assertAlmostEqual(item['following']['ma']['ma55'][14], df.Close.iloc[:55].mean(), places=6)
        self.assertTrue(all(value is None for value in item['ma']['ma144']))
        json.dumps(result, allow_nan=False)

    def test_no_match_is_explicit(self):
        df = sample()
        result = find_similar_candles(df, window_size=10, min_similarity=99.99,
                                      search_start=str(df.index[0]), search_end=str(df.index[9]))
        self.assertEqual(result['matches'], [])
        self.assertIn('没有找到', result['message'])

    def test_flat_target_is_rejected(self):
        df = sample()
        df.iloc[-10:] = [100, 101, 99, 100]
        with self.assertRaisesRegex(ValueError, '几乎不变'):
            find_similar_candles(df, window_size=10)

    def test_flat_candidates_are_skipped(self):
        df = sample()
        df.iloc[0:10] = [100, 101, 99, 100]
        result = find_similar_candles(df, window_size=10, min_similarity=0,
                                      search_start=str(df.index[0]), search_end=str(df.index[9]))
        self.assertEqual(result['scanned_windows'], 0)
        self.assertEqual(result['matches'], [])

    def test_insufficient_data_is_explained(self):
        with self.assertRaisesRegex(ValueError, '至少 40 根'):
            find_similar_candles(sample().iloc[:30], window_size=10, continuation_bars=20)
        with self.assertRaisesRegex(ValueError, '不足 10 根'):
            find_similar_candles(sample(), window_size=10, target_end='2024-01-01')

    def test_invalid_ranges_and_prices(self):
        with self.assertRaisesRegex(ValueError, '不能晚于'):
            find_similar_candles(sample(), window_size=10, search_start='2025-02-01', search_end='2025-01-01')
        df = sample()
        df.iloc[0, 1] = 1
        with self.assertRaisesRegex(ValueError, '高低价'):
            find_similar_candles(df, window_size=10)
        df = sample()
        df.iloc[0, 3] = np.nan
        with self.assertRaisesRegex(ValueError, '价格'):
            find_similar_candles(df, window_size=10)

    def test_time_boundaries_include_end_day_and_convert_timezone(self):
        self.assertEqual(boundary('2025-01-01', end=True), pd.Timestamp('2025-01-01 23:59:59.999999999'))
        self.assertEqual(boundary('2025-01-01T01:00:00Z'), pd.Timestamp('2025-01-01 09:00'))
        with self.assertRaises(ValueError):
            boundary('not-a-date')

    def test_provider_and_period_are_preserved(self):
        with patch('core.candle_compare.fetch_data', return_value=sample()) as fetch:
            result = compare_market_candles('SH0', period='5', window_size=10, min_similarity=0)
        self.assertEqual(fetch.call_args.kwargs['data_provider'], 'tqsdk')
        self.assertEqual(fetch.call_args.kwargs['period'], '5')
        self.assertEqual(result['data_info']['provider'], 'tqsdk')

    def test_ambiguous_legacy_minute_or_index_is_rejected(self):
        with patch('core.candle_compare.fetch_data') as fetch:
            for period, source in [('5', 'main'), ('daily', 'weighted')]:
                with self.assertRaisesRegex(ValueError, '请选择天勤'):
                    compare_market_candles('SH0', period=period, data_source=source, data_provider='akshare')
            fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
