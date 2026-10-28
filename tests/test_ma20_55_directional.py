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
from core import strategy, engine
from core.execution_delay import SignalDelayBroker


def price_frame(prices=None):
    # With 20/55 SMA, golden crosses occur at bars 120/240;
    # death crosses occur at bars 180/300 (zero-based signal bars).
    prices = np.asarray(prices if prices is not None else
                        [120] * 60 + [90] * 60 + [140] * 60 + [80] * 60 + [150] * 60 + [100] * 60, dtype=float)
    return pd.DataFrame({'Open': prices + .25, 'Close': prices,
                         'High': prices + 1, 'Low': prices - 1, 'Volume': 100},
                        index=pd.date_range('2025-01-01', periods=len(prices)))


def simulate(name, frame=None, entry=1, exit=1, auto_close=False):
    class Recorder(getattr(strategy, name)):
        def __init__(self):
            super().__init__()
            self.fills, self.holding_sizes = [], []

        def next(self):
            super().next()
            self.holding_sizes.append(self.position.size)

        def notify_order(self, order):
            if order.status == order.Completed:
                self.fills.append((len(self) - 1, order.executed.size, order.executed.price))
            super().notify_order(order)

    cerebro = bt.Cerebro()
    cerebro.setbroker(SignalDelayBroker(entry_delay_bars=entry, exit_delay_bars=exit))
    cerebro.broker.setcash(1000000)
    cerebro.adddata(bt.feeds.PandasData(dataname=price_frame() if frame is None else frame))
    cerebro.addstrategy(Recorder, fixed_size=2, print_log=False, disable_auto_close=not auto_close)
    return cerebro.run()[0]


class MA20MA55DirectionalTests(unittest.TestCase):
    def test_long_only_enters_golden_cross_and_exits_death_cross_without_reversal(self):
        frame = price_frame()
        result = simulate('MA20MA55LongOnlyStrategy', frame)
        self.assertEqual([(bar, size) for bar, size, _ in result.fills], [(121, 2), (181, -2), (241, 2), (301, -2)])
        self.assertTrue(all(size in (0, 2) for size in result.holding_sizes))
        self.assertEqual(result.position.size, 0)
        for bar, _, price in result.fills:
            self.assertEqual(price, frame.iloc[bar].Open)

    def test_short_only_enters_death_cross_and_exits_golden_cross_without_reversal(self):
        result = simulate('MA20MA55ShortOnlyStrategy')
        self.assertEqual([(bar, size) for bar, size, _ in result.fills], [(181, -2), (241, 2), (301, -2)])
        self.assertTrue(all(size in (0, -2) for size in result.holding_sizes))
        self.assertEqual(result.position.size, -2)

    def test_a_persistent_trend_without_a_new_cross_does_not_open_a_position(self):
        for name in ['MA20MA55LongOnlyStrategy', 'MA20MA55ShortOnlyStrategy']:
            for prices in [np.linspace(80, 180, 200), np.linspace(180, 80, 200)]:
                with self.subTest(strategy=name, rising=prices[-1] > prices[0]):
                    self.assertEqual(simulate(name, price_frame(prices)).fills, [])

    def test_independent_delays_apply_to_entry_and_exit(self):
        long = simulate('MA20MA55LongOnlyStrategy', entry=3, exit=2)
        self.assertEqual([(bar, size) for bar, size, _ in long.fills], [(123, 2), (182, -2), (243, 2), (302, -2)])
        short = simulate('MA20MA55ShortOnlyStrategy', entry=3, exit=2)
        self.assertEqual([(bar, size) for bar, size, _ in short.fills], [(183, -2), (242, 2), (303, -2)])

    def test_normal_backtest_closes_remaining_long_or_short_at_end(self):
        for name, direction in [('MA20MA55LongOnlyStrategy', 1), ('MA20MA55ShortOnlyStrategy', -1)]:
            with self.subTest(strategy=name):
                frame = price_frame().iloc[:260] if direction > 0 else price_frame()
                result = simulate(name, frame, auto_close=True)
                self.assertEqual(result.position.size, 0)
                self.assertEqual(result.fills[-1][:2], (len(frame) - 1, -direction * 2))

    def test_both_strategies_are_registered_and_return_only_their_own_direction(self):
        frame = price_frame()
        for name, direction in [('MA20MA55LongOnlyStrategy', 1), ('MA20MA55ShortOnlyStrategy', -1)]:
            with self.subTest(strategy=name), patch.object(engine, 'fetch_data', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
                result = engine.BacktestEngine().run('JM0', 'daily', {'fixed_size': 2, 'print_log': False}, strategy_name=name)
                self.assertNotIn('error', result)
                self.assertEqual(result['strategy_info']['name'], name)
                self.assertTrue(all(trade['position'] * direction >= 0 for trade in result['trades']))
                self.assertEqual(result['kline_data']['ma']['strategy_fast_label'], 'MA20')
                self.assertEqual(result['kline_data']['ma']['strategy_slow_label'], 'MA55')

    def test_insufficient_history_is_explained_before_running_the_strategy(self):
        for name in ['MA20MA55LongOnlyStrategy', 'MA20MA55ShortOnlyStrategy']:
            with self.subTest(strategy=name), patch.object(engine, 'fetch_data', return_value=price_frame().iloc[:40]), contextlib.redirect_stdout(io.StringIO()):
                result = engine.BacktestEngine().run('JM0', 'daily', {}, strategy_name=name)
                self.assertIn('56', result['error'])


if __name__ == '__main__':
    unittest.main()
