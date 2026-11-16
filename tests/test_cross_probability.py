import unittest
from unittest.mock import patch

import pandas as pd

from server.core.cross_probability import analyze_crosses, cross_signals, market_cross_probability, optimize_cross_horizons, point_profit_stats


class CrossProbabilityTests(unittest.TestCase):
    def setUp(self):
        values = [100] * 60 + list(range(101, 131)) + list(range(129, 79, -1)) + list(range(81, 131))
        self.df = pd.DataFrame({'Close': values}, index=pd.date_range('2020-01-01', periods=len(values)))

    def test_reverse_exit_closes_early_and_respects_range_and_delay(self):
        group = analyze_crosses(self.df, ['20/60'], observation_bars=60, reverse_exit=True)[0]
        first = group['events'][0]
        self.assertEqual((first['end'], first['bars'], first['exit_reason']), ('2020-04-24 00:00:00', 54, 'reverse'))
        self.assertEqual(first['next_opposite'], first['end'])
        short = analyze_crosses(self.df, ['20/60'], observation_bars=5, reverse_exit=True)[0]
        self.assertEqual((short['events'][0]['bars'], short['events'][0]['exit_reason']), (5, 'horizon'))
        bounded = analyze_crosses(self.df, ['20/60'], end='2020-04-24', observation_bars=60, reverse_exit=True)[0]
        self.assertEqual(len(bounded['events']), 1)
        before = analyze_crosses(self.df, ['20/60'], end='2020-04-23', observation_bars=60, reverse_exit=True)[0]
        self.assertEqual(len(before['events']), 0)
        self.assertIsNone(before['excluded'][0]['next_opposite'])
        delayed = analyze_crosses(self.df, ['20/60'], observation_bars=60, observation_delay=54, reverse_exit=True)[0]
        self.assertEqual(delayed['expired'], 2)

    def test_reverse_optimization_matches_individual_samples(self):
        for delay in (0, 2, 54):
            for item in optimize_cross_horizons(self.df, ['20/60'], end='2020-06-15', observation_delay=delay, max_bars=70, reverse_exit=True):
                for point in item['series']:
                    summary = analyze_crosses(self.df, ['20/60'], end='2020-06-15', observation_delay=delay, observation_bars=point['bars'], reverse_exit=True)[0]['summary'][item['direction']]
                    self.assertEqual((point['total'], point['wins'], point['match_pct']), (summary['total'], summary['profit_count'], summary['match_pct']))
                    for field in ('gross_profit_points', 'gross_loss_points', 'profit_count', 'loss_count', 'profit_loss_ratio'):
                        self.assertEqual(point[field], summary[field])

    def test_unsorted_string_dates_are_normalized_before_sorting(self):
        unordered = self.df.copy()
        unordered.index = [f'{date.year}-{date.month}-{date.day}' for date in unordered.index]
        for delay in (0, 2):
            self.assertEqual(analyze_crosses(unordered, ['20/60'], observation_bars=5, observation_delay=delay),
                             analyze_crosses(self.df, ['20/60'], observation_bars=5, observation_delay=delay))
            self.assertEqual(optimize_cross_horizons(unordered, ['20/60'], observation_delay=delay, max_bars=5),
                             optimize_cross_horizons(self.df, ['20/60'], observation_delay=delay, max_bars=5))

    def test_market_normalizes_timezone_and_numeric_strings_before_charting(self):
        prices = self.df.assign(Open=self.df.Close, High=self.df.Close + 1, Low=self.df.Close - 1).astype(str)
        prices.index = prices.index.tz_localize('Asia/Shanghai').tz_convert('UTC')
        with patch('server.core.cross_probability.fetch_data', return_value=prices):
            result = market_cross_probability('JM0', 'daily', 'akshare', 'main', ['20/60'], end='2020-04-24', optimize=True, max_search_bars=5)
        chart = result['chart']
        self.assertEqual(chart['dates'][-1], '2020-04-24 00:00:00')
        self.assertEqual(chart['ohlc'][-1], [105.0, 105.0, 104.0, 106.0])
        self.assertEqual(chart['ma']['55'][-1], self.df.loc[:'2020-04-24','Close'].tail(55).mean())
        self.assertEqual(result['data_info']['provider_name'], '新浪财经')
        self.assertTrue(result['groups'][0]['events'])

    def test_profit_loss_ratio_uses_averages_and_excludes_flat_samples(self):
        stats=point_profit_stats([10, 30, -5, -15, 0])
        self.assertEqual((stats['profit_count'],stats['loss_count']), (2,2))
        self.assertEqual((stats['avg_profit_points'],stats['avg_loss_points'],stats['profit_loss_ratio']), (20,10,2))
        for changes in ([],[0,0],[10,5],[-10,-5]):
            self.assertIsNone(point_profit_stats(changes)['profit_loss_ratio'])

    def test_optimization_point_statistics_match_individual_events_for_long_and_short(self):
        for item in optimize_cross_horizons(self.df, ['20/55'], observation_delay=2, max_bars=8):
            for point in item['series']:
                group=analyze_crosses(self.df,['20/55'],observation_delay=2,observation_bars=point['bars'])[0]
                summary=group['summary'][item['direction']]
                for field in ('gross_profit_points','gross_loss_points','profit_count','loss_count','profit_loss_ratio'):
                    self.assertEqual(point[field],summary[field])

    def test_completed_crosses_and_flat_results_use_all_closed_samples(self):
        result = analyze_crosses(self.df, ['20/60'])[0]
        self.assertEqual(result['summary']['golden']['match_pct'], 100.0)
        self.assertEqual(result['summary']['death']['match_pct'], 0.0)
        self.assertEqual(result['summary']['death']['flat'], 1)
        self.assertEqual(result['pending'], 1)
        self.assertEqual(result['events'][0]['start'], '2020-03-01 00:00:00')
        self.assertEqual(result['events'][0]['end'], '2020-04-24 00:00:00')
        self.assertEqual(result['events'][0]['bars'], 54)

    def test_equal_lines_do_not_generate_same_direction_duplicates(self):
        values = pd.Series([float('nan'), 0, 1, 0, 1, 0, 0, -1, 0, -1, 0, 1], dtype=float)
        golden, death = cross_signals(values)
        self.assertEqual(list(golden.nonzero()[0]), [2, 11])
        self.assertEqual(list(death.nonzero()[0]), [7])

    def test_each_unfinished_or_expired_signal_has_an_auditable_reason(self):
        result = analyze_crosses(self.df, ['20/60'], observation_delay=54)[0]
        self.assertEqual(len(result['excluded']), result['expired'] + result['pending'])
        self.assertEqual([event['signal'] for event in result['excluded']],
                         ['2020-03-01 00:00:00', '2020-04-24 00:00:00', '2020-06-13 00:00:00'])
        self.assertIn('反向交叉', result['excluded'][0]['reason'])
        self.assertIn('未完成', result['excluded'][-1]['reason'])

    def test_range_uses_prior_history_but_excludes_outcomes_after_end(self):
        result = analyze_crosses(self.df, ['20/60'], start='2020-03-01', end='2020-04-23')[0]
        self.assertEqual(result['pending'], 1)
        self.assertEqual(result['summary']['golden']['total'], 0)
        self.assertIsNone(result['summary']['golden']['up_pct'])
        result = analyze_crosses(self.df, ['20/60'], start='2020-03-01', end='2020-04-24')[0]
        self.assertEqual(result['summary']['golden']['up'], 1)
        self.assertEqual(result['pending'], 1)

    def test_death_cross_matches_falling_prices(self):
        inverse = self.df.copy()
        inverse['Close'] = 200 - inverse['Close']
        result = analyze_crosses(inverse, ['20/60'])[0]
        self.assertEqual(result['summary']['death']['down'], 1)
        self.assertEqual(result['summary']['death']['match_pct'], 100.0)

    def test_fixed_horizon_uses_exact_following_close_even_across_opposite_cross(self):
        short = analyze_crosses(self.df, ['20/60'], observation_bars=1)[0]
        first = short['events'][0]
        self.assertEqual((first['start'], first['end'], first['bars']), ('2020-03-01 00:00:00', '2020-03-02 00:00:00', 1))
        self.assertEqual((first['start_close'], first['end_close'], first['outcome']), (101.0, 102.0, 'up'))
        long = analyze_crosses(self.df, ['20/60'], observation_bars=60)[0]
        self.assertEqual(long['events'][0]['end'], '2020-04-30 00:00:00')
        self.assertEqual(long['events'][0]['end_close'], 99.0)
        self.assertEqual(long['events'][0]['outcome'], 'down')
        self.assertEqual(long['pending'], 1)

    def test_fixed_horizon_respects_end_date_and_rejects_invalid_values(self):
        result = analyze_crosses(self.df, ['20/60'], end='2020-03-01', observation_bars=1)[0]
        self.assertEqual(result['pending'], 1)
        self.assertFalse(result['events'])
        for value in (0, -1, 1.5, True, 10001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                analyze_crosses(self.df, ['20/60'], observation_bars=value)

    def test_delay_then_fixed_observation_uses_shifted_close_and_exact_count(self):
        result = analyze_crosses(self.df, ['20/60'], observation_bars=5, observation_delay=2)[0]
        event = result['events'][0]
        self.assertEqual(event['signal'], '2020-03-01 00:00:00')
        self.assertEqual(event['start'], '2020-03-03 00:00:00')
        self.assertEqual(event['end'], '2020-03-08 00:00:00')
        self.assertEqual((event['signal_close'], event['start_close'], event['end_close'], event['bars']), (101, 103, 108, 5))
        self.assertAlmostEqual(event['return_pct'], (108 / 103 - 1) * 100, places=5)

    def test_delay_in_reverse_mode_excludes_cross_at_or_before_start(self):
        result = analyze_crosses(self.df, ['20/60'], observation_delay=54)[0]
        self.assertEqual(result['expired'], 2)
        self.assertEqual(result['pending'], 1)
        self.assertFalse(result['events'])
        result = analyze_crosses(self.df, ['20/60'], observation_delay=53)[0]
        self.assertEqual(result['events'][0]['bars'], 1)
        self.assertEqual(result['events'][0]['start'], '2020-04-23 00:00:00')

    def test_delay_respects_cutoff_and_rejects_invalid_values(self):
        result = analyze_crosses(self.df, ['20/60'], end='2020-03-07', observation_delay=2, observation_bars=5)[0]
        self.assertEqual(result['pending'], 1)
        self.assertFalse(result['events'])
        for value in (-1, 1.5, True, None, 10001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                analyze_crosses(self.df, ['20/60'], observation_delay=value)
        default = analyze_crosses(self.df, ['20/60'])[0]
        explicit = analyze_crosses(self.df, ['20/60'], observation_delay=0)[0]
        self.assertEqual(default, explicit)

    def test_no_warmup_and_invalid_prices_do_not_create_samples(self):
        result = analyze_crosses(self.df.head(100), ['20/144'])[0]
        self.assertEqual(result['summary']['golden']['total'], 0)
        invalid = self.df.copy()
        invalid.iloc[0, 0] = 0
        with self.assertRaises(ValueError):
            analyze_crosses(invalid, ['20/60'])
        with self.assertRaises(ValueError):
            analyze_crosses(self.df, [])

    def test_specific_contract_uses_existing_on_demand_cache(self):
        with patch('server.core.cross_probability.fetch_data', return_value=self.df) as fetch:
            result = market_cross_probability('JM2605', 'daily', 'tqsdk', 'main', ['20/60'])
        self.assertTrue(fetch.call_args.kwargs['cache_contract'])
        self.assertEqual(result['symbol'], 'JM2605')

    def test_chart_contains_candles_and_warmed_averages_until_end(self):
        prices = self.df.assign(Open=self.df.Close, High=self.df.Close + 1, Low=self.df.Close - 1)
        with patch('server.core.cross_probability.fetch_data', return_value=prices):
            result = market_cross_probability('JM0', 'daily', 'tqsdk', 'main', ['20/60'], end='2020-04-24')
        chart = result['chart']
        self.assertEqual(chart['dates'][-1], '2020-04-24 00:00:00')
        self.assertEqual(chart['ohlc'][-1], [105.0, 105.0, 104.0, 106.0])
        self.assertIsNotNone(chart['ma']['55'][-1])
        self.assertEqual(set(chart['ma']), {'20','55','144'})
        self.assertEqual(chart['ma']['55'][-1], prices.loc[:'2020-04-24','Close'].tail(55).mean())

    def test_2055_pair_uses_same_cross_detection_in_analysis_and_optimization(self):
        groups = analyze_crosses(self.df,['20/55'],observation_bars=5,observation_delay=2)
        result = optimize_cross_horizons(self.df,['20/55'],observation_delay=2,max_bars=5)
        self.assertTrue(groups[0]['events'])
        for item in result:
            summary=groups[0]['summary'][item['direction']]
            self.assertEqual((item['series'][-1]['total'],item['series'][-1]['match_pct']),
                             (summary['total'],summary['match_pct']))

    def test_55144_pair_uses_same_cross_detection_in_analysis_and_optimization(self):
        prices = [120]*160 + [90]*160 + [140]*160 + [80]*160 + [150]*160
        df = pd.DataFrame({'Close':prices},index=pd.date_range('2024-01-01',periods=len(prices)))
        group = analyze_crosses(df,['55/144'],observation_bars=5,observation_delay=2)[0]
        result = optimize_cross_horizons(df,['55/144'],observation_delay=2,max_bars=5)
        self.assertTrue(group['events'])
        for item in result:
            summary=group['summary'][item['direction']]
            self.assertEqual((item['series'][-1]['total'],item['series'][-1]['match_pct']),
                             (summary['total'],summary['match_pct']))

    def test_optimization_matches_individual_analyses_for_delays_and_cutoff(self):
        results = optimize_cross_horizons(self.df, ['20/60'], end='2020-06-20', observation_delay=2, max_bars=12)
        for item in results:
            for point in item['series']:
                group = analyze_crosses(self.df, ['20/60'], end='2020-06-20', observation_delay=2, observation_bars=point['bars'])[0]
                summary = group['summary'][item['direction']]
                self.assertEqual((point['total'], point['match_pct']), (summary['total'], summary['match_pct']))
            if item['best']:
                highest = max(row['wins'] / row['total'] for row in item['series'] if row['total'])
                first = next(row for row in item['series'] if row['total'] and row['wins'] / row['total'] == highest)
                self.assertEqual(item['best'], first)

    def test_optimization_no_samples_and_bounds(self):
        result = optimize_cross_horizons(self.df.head(100), ['20/144'], max_bars=3)
        self.assertTrue(all(item['best'] is None for item in result))
        self.assertTrue(all(row['match_pct'] is None for item in result for row in item['series']))
        for value in (0, 1001, 1.5, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                optimize_cross_horizons(self.df, ['20/60'], max_bars=value)

    def test_best_result_includes_the_exact_samples_and_chart_from_same_data(self):
        prices = self.df.assign(Open=self.df.Close, High=self.df.Close + 1, Low=self.df.Close - 1)
        with patch('server.core.cross_probability.fetch_data', return_value=prices) as fetch:
            result = market_cross_probability('JM0', 'daily', 'tqsdk', 'main', ['20/60'], observation_delay=2, optimize=True, max_search_bars=8)
        self.assertEqual(fetch.call_count, 1)
        for item in result['optimization']:
            if item['best'] is None:
                self.assertFalse(item['events'])
                continue
            self.assertEqual(len(item['events']), item['best']['total'])
            self.assertEqual(sum(event['outcome'] == ('up' if item['direction'] == 'golden' else 'down') for event in item['events']), item['best']['wins'])
            for event in item['events']:
                self.assertEqual(event['bars'], item['best']['bars'])
                self.assertIn(event['signal'], result['chart']['dates'])
                self.assertIn(event['end'], result['chart']['dates'])

    def test_specific_contract_uses_backtest_window_for_all_samples_and_optimization(self):
        import numpy as np
        dates = pd.date_range('2025-08-01', '2027-02-01')
        close = 100 + 20 * np.sin(np.arange(len(dates)) / 9)
        prices = pd.DataFrame({'Close':close, 'Open':close, 'High':close+1, 'Low':close-1}, index=dates)
        with patch('server.core.cross_probability.fetch_data', return_value=prices):
            may = market_cross_probability('JM2605','daily','tqsdk','main',['20/60'], start='2024-01-01',end='2027-12-31',observation_bars=5,optimize=True,max_search_bars=12)
            jan = market_cross_probability('JM2701','daily','tqsdk','main',['20/60'], start='2024-01-01',end='2027-12-31',observation_bars=5,optimize=True,max_search_bars=12)
        for result, start, end in [(may,'2025-12-01','2026-04-23'),(jan,'2026-08-01','2026-12-23')]:
            self.assertEqual(result['analysis_window'], {'start':start,'end':end,'contract_window':True})
            self.assertTrue(result['groups'][0]['events'])
            for event in result['groups'][0]['events']:
                self.assertGreaterEqual(event['signal'][:10], start)
                self.assertLessEqual(event['end'][:10], end)
            for item in result['optimization']:
                for event in item['events']:
                    self.assertGreaterEqual(event['signal'][:10], start)
                    self.assertLessEqual(event['end'][:10], end)
            self.assertLessEqual(result['chart']['dates'][-1][:10], end)
            self.assertLess(result['chart']['dates'][0][:10], start)  # prior bars warm the moving averages


if __name__ == '__main__':
    unittest.main()
