import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import backtrader as bt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import engine, strategy


def price_frame(prices=None):
    if prices is None:
        prices = np.concatenate([
            np.linspace(160, 80, 230), np.linspace(80, 180, 140),
            np.full(10, 130), np.full(50, 180), np.full(160, 70),
            np.linspace(70, 190, 160), np.full(80, 130),
        ])
    prices = np.asarray(prices, dtype=float)
    return pd.DataFrame({'Open': prices + 0.5, 'High': prices + 2,
                         'Low': prices - 2, 'Close': prices, 'Volume': 100},
                        index=pd.date_range('2023-01-01', periods=len(prices)))


def run_strategy(frame, strategy_class=None, **params):
    selected_class = strategy_class or strategy.MA20MA144LongOnlyStrategy
    class Recorder(selected_class):
        def __init__(self):
            super().__init__()
            self.fills = []
            self.position_sizes = []

        def notify_order(self, order):
            if order.status == order.Completed:
                self.fills.append((len(self) - 1, order.executed.size, order.executed.price))
            super().notify_order(order)

        def next(self):
            super().next()
            self.position_sizes.append(self.position.size)

    cerebro = bt.Cerebro()
    cerebro.adddata(bt.feeds.PandasData(dataname=frame))
    cerebro.broker.setcash(1_000_000)
    cerebro.addstrategy(Recorder, **{'fixed_size': 2, 'print_log': False,
                                    'disable_auto_close': True, **params})
    return cerebro.run()[0]


class MA20MA144StrategyTests(unittest.TestCase):
    def test_actual_20_144_entry_and_20_55_exit_fill_at_next_open(self):
        frame = price_frame()
        result = run_strategy(frame)
        # Independent fixture crossings: entry at 264/591, exit at 377/756.
        self.assertEqual([(bar, size) for bar, size, _ in result.fills],
                         [(265, 2), (378, -2), (592, 2), (757, -2)])
        for bar, _, price in result.fills:
            self.assertAlmostEqual(price, frame.iloc[bar].Open)
        self.assertTrue(all(size in (0, 2) for size in result.position_sizes))

    def test_exit_waits_for_new_144_cross_even_after_55_recovery(self):
        frame = price_frame()
        result = run_strategy(frame)
        ma20 = frame.Close.rolling(20).mean()
        ma55 = frame.Close.rolling(55).mean()
        ma144 = frame.Close.rolling(144).mean()
        # MA20/55 recover at 393, while MA20 remains above MA144 after exit.
        self.assertLess(ma20.iloc[392], ma55.iloc[392])
        self.assertGreater(ma20.iloc[393], ma55.iloc[393])
        self.assertTrue((ma20.iloc[378:430] > ma144.iloc[378:430]).all())
        self.assertFalse(any(378 < bar < 592 for bar, _, _ in result.fills))

    def test_already_above_144_is_not_a_new_golden_cross(self):
        result = run_strategy(price_frame(np.linspace(80, 200, 300)))
        self.assertEqual(result.fills, [])

    def test_start_window_does_not_enter_on_a_pre_window_cross(self):
        frame = price_frame()
        result = run_strategy(frame, start_date=frame.index[300].date())
        self.assertEqual([(bar, size) for bar, size, _ in result.fills], [(592, 2), (757, -2)])

    def test_platform_end_of_backtest_closes_remaining_long(self):
        frame = price_frame().iloc[:360]
        result = run_strategy(frame, disable_auto_close=False)
        self.assertEqual([(bar, size) for bar, size, _ in result.fills], [(265, 2), (359, -2)])

    def test_engine_registration_signals_and_all_three_chart_averages(self):
        frame = price_frame()
        params = {'fast_period': 20, 'slow_period': 144, 'exit_period': 55, 'fixed_size': 2}
        with patch.object(engine, 'fetch_data', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('RB0', 'daily', params,
                strategy_name='MA20MA144LongOnlyStrategy', data_provider='tqsdk')
        self.assertNotIn('error', result)
        self.assertEqual([trade['action'] for trade in result['trades']], ['买多', '平多', '买多', '平多'])
        ma = result['kline_data']['ma']
        self.assertEqual(ma['strategy_fast_label'], 'MA20')
        self.assertEqual(ma['strategy_slow_label'], 'MA144')
        self.assertEqual(ma['strategy_exit_label'], 'MA55')
        self.assertEqual(ma['strategy_exit'][:54], [None] * 54)
        self.assertAlmostEqual(ma['strategy_exit'][377], round(frame.Close.iloc[323:378].mean(), 2))
        self.assertNotIn('start_date', params)

    def test_short_history_returns_clear_error_instead_of_indicator_crash(self):
        with patch.object(engine, 'fetch_data', return_value=price_frame(np.arange(100, 200))), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('RB0', 'daily', {}, strategy_name='MA20MA144LongOnlyStrategy')
        self.assertIn('145', result['error'])
        self.assertIn('100', result['error'])


class MA20MA144ShortStrategyTests(unittest.TestCase):
    def short_frame(self):
        original = price_frame()
        close = 300 - original.Close
        return pd.DataFrame({'Open': close + .5, 'High': close + 2, 'Low': close - 2,
                             'Close': close, 'Volume': 100}, index=original.index)

    def simulate(self, data=None, **params):
        return run_strategy(self.short_frame() if data is None else data,
                            strategy_class=strategy.MA20MA144ShortOnlyStrategy, **params)

    def test_death_cross_opens_short_and_golden_cross_closes_at_next_open(self):
        data = self.short_frame()
        result = self.simulate(data)
        self.assertEqual([(bar, size) for bar, size, _ in result.fills],
                         [(265, -2), (378, 2), (592, -2), (757, 2)])
        for bar, _, price in result.fills:
            self.assertEqual(price, data.iloc[bar].Open)
        self.assertTrue(all(size in (0, -2) for size in result.position_sizes))

    def test_exit_requires_new_144_death_cross_to_reenter(self):
        data = self.short_frame()
        result = self.simulate(data)
        fast, medium, slow = (data.Close.rolling(period).mean() for period in (20, 55, 144))
        self.assertGreater(fast.iloc[392], medium.iloc[392])
        self.assertLess(fast.iloc[393], medium.iloc[393])
        self.assertTrue((fast.iloc[378:430] < slow.iloc[378:430]).all())
        self.assertFalse(any(378 < bar < 592 for bar, _, _ in result.fills))

    def test_already_below_144_does_not_enter_without_a_new_cross(self):
        result = self.simulate(price_frame(np.linspace(220, 80, 300)))
        self.assertEqual(result.fills, [])

    def test_start_date_skips_earlier_short_signal(self):
        data = self.short_frame()
        result = self.simulate(data, start_date=data.index[300].date())
        self.assertEqual([(bar, size) for bar, size, _ in result.fills], [(592, -2), (757, 2)])

    def test_sample_end_closes_remaining_short(self):
        result = self.simulate(self.short_frame().iloc[:360], disable_auto_close=False)
        self.assertEqual([(bar, size) for bar, size, _ in result.fills], [(265, -2), (359, 2)])

    def test_engine_supports_short_delays_and_all_three_chart_averages(self):
        data = self.short_frame()
        params = {'fast_period': 20, 'slow_period': 144, 'exit_period': 55,
                  'fixed_size': 2, 'entry_delay_bars': 2, 'exit_delay_bars': 3}
        with patch.object(engine, 'fetch_data', return_value=data), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('RB0', 'daily', params, strategy_name='MA20MA144ShortOnlyStrategy')
        self.assertNotIn('error', result)
        self.assertEqual([trade['action'] for trade in result['trades']], ['卖空', '平空', '卖空', '平空'])
        for trade, bar in zip(result['trades'], [266, 380, 593, 759]):
            self.assertEqual(trade['date'][:10], str(data.index[bar].date()))
            self.assertEqual(trade['price'], data.iloc[bar].Open)
        ma = result['kline_data']['ma']
        self.assertEqual([ma[key] for key in ['strategy_fast_label', 'strategy_slow_label', 'strategy_exit_label']], ['MA20', 'MA144', 'MA55'])
        self.assertEqual(params['entry_delay_bars'], 2)

    def test_short_history_has_same_clear_minimum_requirement(self):
        with patch.object(engine, 'fetch_data', return_value=price_frame(np.arange(100, 200))), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('RB0', 'daily', {}, strategy_name='MA20MA144ShortOnlyStrategy')
        self.assertIn('145', result['error'])


class MA20MA144LongShortStrategyTests(unittest.TestCase):
    def simulate(self, frame=None, **params):
        return run_strategy(price_frame() if frame is None else frame,
                            strategy_class=strategy.MA20MA144LongShortStrategy, **params)

    def test_combines_long_and_short_entries_with_directional_exits(self):
        frame = price_frame()
        result = self.simulate(frame)
        # Independent pandas SMA crossings: 20/144 at 264+, 434-, 591+, 766-;
        # 20/55 exits the long at 377- and the short at 591+.
        self.assertEqual([(bar, size) for bar, size, _ in result.fills],
                         [(265, 2), (378, -2), (435, -2), (592, 2), (767, -2)])
        for bar, _, price in result.fills:
            self.assertEqual(price, frame.iloc[bar].Open)
        self.assertEqual(set(result.position_sizes), {-2, 0, 2})

    def test_mirrored_prices_open_short_first_and_close_long_on_death_cross(self):
        frame = price_frame(300 - price_frame().Close.to_numpy())
        result = self.simulate(frame)
        self.assertEqual([(bar, size) for bar, size, _ in result.fills],
                         [(265, -2), (378, 2), (435, 2), (592, -2), (767, 2)])
        self.assertEqual(set(result.position_sizes), {-2, 0, 2})

    def test_no_reentry_on_55_cross_or_reversal_on_simultaneous_exit_entry(self):
        result = self.simulate()
        # 20/55 golden cross at 393 does not reopen the exited long.
        self.assertFalse(any(378 < bar < 435 for bar, _, _ in result.fills))
        # At 591 both entry and exit crosses are golden: close the short only.
        self.assertEqual([fill[1] for fill in result.fills if fill[0] == 592], [2])
        self.assertFalse(any(592 < bar < 767 for bar, _, _ in result.fills))

    def test_start_date_skips_old_signals_in_both_directions(self):
        for frame in (price_frame(), price_frame(300 - price_frame().Close.to_numpy())):
            with self.subTest(first_price=frame.Close.iloc[0]):
                result = self.simulate(frame, start_date=frame.index[300].date())
                self.assertEqual([bar for bar, _, _ in result.fills], [435, 592, 767])

    def test_sample_end_liquidates_either_direction(self):
        for frame, sign in ((price_frame(), 1), (price_frame(300 - price_frame().Close.to_numpy()), -1)):
            with self.subTest(sign=sign):
                result = self.simulate(frame.iloc[:360], disable_auto_close=False)
                self.assertEqual([(bar, size) for bar, size, _ in result.fills],
                                 [(265, 2 * sign), (359, -2 * sign)])
                self.assertEqual(result.position.size, 0)

    def test_engine_uses_delays_in_both_directions_and_plots_three_averages(self):
        frame = price_frame()
        params = {'fast_period': 20, 'slow_period': 144, 'exit_period': 55,
                  'fixed_size': 2, 'entry_delay_bars': 2, 'exit_delay_bars': 3}
        with patch.object(engine, 'fetch_data', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('RB0', 'daily', params,
                                                strategy_name='MA20MA144LongShortStrategy')
        self.assertNotIn('error', result)
        self.assertEqual([trade['action'] for trade in result['trades']],
                         ['买多', '平多', '卖空', '平空', '卖空', '平空'])
        for trade, bar in zip(result['trades'], [266, 380, 436, 594, 768, len(frame) - 1]):
            self.assertEqual(trade['date'][:10], str(frame.index[bar].date()))
            self.assertEqual(trade['price'], frame.iloc[bar].Open)
        ma = result['kline_data']['ma']
        self.assertEqual([ma[key] for key in ['strategy_fast_label', 'strategy_slow_label', 'strategy_exit_label']],
                         ['MA20', 'MA144', 'MA55'])
        self.assertNotIn('start_date', params)

    def test_short_history_returns_clear_minimum_requirement(self):
        with patch.object(engine, 'fetch_data', return_value=price_frame(np.arange(100, 200))), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('RB0', 'daily', {}, strategy_name='MA20MA144LongShortStrategy')
        self.assertIn('145', result['error'])


if __name__ == '__main__':
    unittest.main()
