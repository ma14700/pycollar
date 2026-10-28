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
from core.execution_delay import SignalDelayBroker, execution_delay_params


def frame(count=14):
    price = np.arange(count, dtype=float) + 100
    return pd.DataFrame({'Open': price, 'High': price + 3, 'Low': price - 3,
                         'Close': price + 1, 'Volume': 100},
                        index=pd.bdate_range('2025-01-02', periods=count))


def simulate(signals, entry=1, exit=1, data=None, auto_close=False, legacy=False):
    class SignalStrategy(strategy.BaseStrategy):
        def __init__(self):
            super().__init__()
            self.fills = []
            self.canceled = []

        def next(self):
            if not self.pre_next() or self.order:
                return
            signal = signals.get(len(self) - 1)
            if signal == 'buy': self.order = self.buy(size=2)
            elif signal == 'sell': self.order = self.sell(size=2)
            elif signal == 'reverse': self.order = self.order_target_size(target=-2)
            elif signal == 'close': self.order = self.close()
            elif signal == 'limit': self.order = self.buy(size=2, price=103, exectype=bt.Order.Limit)
            elif signal == 'stop': self.order = self.buy(size=2, price=105, exectype=bt.Order.Stop)

        def notify_order(self, order):
            if order.status == order.Completed:
                self.fills.append((len(self) - 1, order.executed.size, order.executed.price, dict(order.info)))
            elif order.status == order.Canceled:
                self.canceled.append(dict(order.info))
            super().notify_order(order)

    cerebro = bt.Cerebro()
    if not legacy: cerebro.setbroker(SignalDelayBroker(**execution_delay_params({'entry_delay_bars': entry, 'exit_delay_bars': exit})))
    cerebro.adddata(bt.feeds.PandasData(dataname=frame() if data is None else data))
    cerebro.broker.setcash(100000)
    cerebro.addstrategy(SignalStrategy, print_log=False, disable_auto_close=not auto_close)
    return cerebro.run()[0]


class ExecutionDelayTests(unittest.TestCase):
    def test_default_one_preserves_legacy_next_open_prices(self):
        signals = {1: 'buy', 6: 'close'}
        current, legacy = simulate(signals), simulate(signals, legacy=True)
        self.assertEqual([fill[:3] for fill in current.fills], [fill[:3] for fill in legacy.fills])
        self.assertEqual([fill[:2] for fill in current.fills], [(2, 2), (7, -2)])

    def test_entry_and_exit_delays_are_independent_and_use_open(self):
        data = frame()
        result = simulate({1: 'buy', 6: 'close'}, entry=3, exit=2, data=data)
        self.assertEqual([fill[:2] for fill in result.fills], [(4, 2), (8, -2)])
        for bar, _, price, _ in result.fills:
            self.assertEqual(price, data.iloc[bar].Open)
            self.assertNotEqual(price, data.iloc[bar].High)
        self.assertEqual(result.fills[0][3]['execution_delay_bars'], 3)
        self.assertEqual(result.fills[1][3]['execution_delay_bars'], 2)

    def test_short_entry_and_buy_to_close_use_the_correct_delays(self):
        result = simulate({1: 'sell', 6: 'close'}, entry=2, exit=3)
        self.assertEqual([fill[:2] for fill in result.fills], [(3, -2), (9, 2)])

    def test_delay_counts_bars_across_weekends_and_keeps_pending_order(self):
        data = frame()
        result = simulate({1: 'buy', 2: 'buy', 3: 'buy'}, entry=3, data=data)
        self.assertEqual([fill[:2] for fill in result.fills], [(4, 2)])
        self.assertGreater((data.index[4] - data.index[1]).days, 3)

    def test_reversal_uses_larger_delay_as_one_atomic_order(self):
        result = simulate({1: 'buy', 6: 'reverse'}, entry=2, exit=4)
        self.assertEqual([fill[:2] for fill in result.fills], [(3, 2), (10, -4)])
        self.assertEqual(result.fills[-1][3]['execution_kind'], 'reversal')

    def test_end_cancels_delayed_entry_instead_of_opening_on_last_bar(self):
        result = simulate({8: 'buy'}, entry=5, data=frame(14), auto_close=True)
        self.assertEqual(result.fills, [])
        self.assertTrue(result.canceled[0]['end_of_backtest'])
        self.assertEqual(result.position.size, 0)

    def test_end_forced_close_bypasses_exit_delay_without_duplicate_close(self):
        result = simulate({1: 'buy', 6: 'close'}, entry=2, exit=20, data=frame(12), auto_close=True)
        self.assertEqual([fill[:2] for fill in result.fills], [(3, 2), (11, -2)])
        self.assertEqual(result.fills[-1][3]['execution_kind'], 'forced_exit')
        self.assertEqual(result.position.size, 0)

    def test_orders_past_end_do_not_get_a_synthetic_fill(self):
        result = simulate({8: 'buy'}, entry=20, data=frame(12))
        self.assertEqual(result.fills, [])

    def test_limit_and_stop_orders_still_use_touch_rules(self):
        limit = simulate({1: 'limit'}, entry=10)
        stop = simulate({1: 'stop'}, entry=10)
        self.assertEqual(limit.fills[0][:3], (2, 2, 102))
        self.assertEqual(stop.fills[0][:3], (2, 2, 105))

    def test_invalid_delays_fail_before_loading_market_data(self):
        for value in [0, -1, 1.5, True, None, '', '2.0', 'bad']:
            with self.subTest(value=value), patch.object(engine, 'fetch_data') as fetch:
                result = engine.BacktestEngine().run('RB0', 'daily', {'entry_delay_bars': value})
                self.assertIn('大于等于 1', result['error'])
                fetch.assert_not_called()
        self.assertEqual(execution_delay_params({}), {'entry_delay_bars': 1, 'exit_delay_bars': 1})

    def test_ma20_144_engine_fills_at_configured_bars_and_records_signal_time(self):
        prices = np.concatenate([np.linspace(160, 80, 230), np.linspace(80, 180, 140),
                                 np.full(10, 130), np.full(50, 180), np.full(160, 70),
                                 np.linspace(70, 190, 160), np.full(80, 130)])
        data = pd.DataFrame({'Open': prices + .5, 'High': prices + 3, 'Low': prices - 3,
                             'Close': prices, 'Volume': 100}, index=pd.date_range('2023-01-01', periods=len(prices)))
        params = {'fixed_size': 2, 'entry_delay_bars': 3, 'exit_delay_bars': 4}
        with patch.object(engine, 'fetch_data', return_value=data), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('RB0', 'daily', params, strategy_name='MA20MA144LongOnlyStrategy')
        self.assertNotIn('error', result)
        expected = [(267, 3), (381, 4), (594, 3), (760, 4)]
        self.assertEqual(len(result['trades']), 4)
        for trade, (bar, delay) in zip(result['trades'], expected):
            self.assertEqual(trade['date'][:10], str(data.index[bar].date()))
            self.assertEqual(trade['price'], data.iloc[bar].Open)
            self.assertEqual(trade['execution_delay_bars'], delay)
            self.assertEqual(trade['signal_date'][:10], str(data.index[bar-delay].date()))
        self.assertEqual(params['entry_delay_bars'], 3)


if __name__ == '__main__':
    unittest.main()
