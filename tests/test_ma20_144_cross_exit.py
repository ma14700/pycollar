import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import backtrader as bt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import engine, strategy
from core.execution_delay import SignalDelayBroker
from test_ma20_144_strategy import price_frame


LONG = 'MA20MA144CrossExitLongOnlyStrategy'
SHORT = 'MA20MA144CrossExitShortOnlyStrategy'
BOTH = 'MA20MA144CrossExitLongShortStrategy'
NAMES = [BOTH, LONG, SHORT]


def simulate(name, data=None, entry=1, exit=1, **params):
    class Recorder(getattr(strategy, name)):
        def __init__(self):
            super().__init__()
            self.fills, self.sizes = [], []

        def next(self):
            super().next()
            self.sizes.append(self.position.size)

        def notify_order(self, order):
            if order.status == order.Completed:
                self.fills.append((len(self) - 1, order.executed.size, order.executed.price))
            super().notify_order(order)

    cerebro = bt.Cerebro()
    cerebro.setbroker(SignalDelayBroker(entry_delay_bars=entry, exit_delay_bars=exit))
    cerebro.broker.setcash(1_000_000)
    cerebro.adddata(bt.feeds.PandasData(dataname=price_frame() if data is None else data))
    cerebro.addstrategy(Recorder, **{'fixed_size': 2, 'print_log': False, 'disable_auto_close': True, **params})
    return cerebro.run()[0]


class MA144CrossExitTests(unittest.TestCase):
    def test_long_closes_on_144_death_cross_and_ignores_earlier_55_cross(self):
        result = simulate(LONG)
        # Independent fixture: 20/144 crosses at 264+, 434-, 591+, 766-.
        # Old 20/55 exits would occur at 377 and 756 instead.
        self.assertEqual([(bar, size) for bar, size, _ in result.fills],
                         [(265, 2), (435, -2), (592, 2), (767, -2)])
        self.assertEqual(set(result.sizes), {0, 2})
        self.assertTrue(all(size == 2 for size in result.sizes[378 - 144:435 - 144]))

    def test_short_closes_on_144_golden_cross_and_never_opens_long(self):
        result = simulate(SHORT)
        self.assertEqual([(bar, size) for bar, size, _ in result.fills], [(435, -2), (592, 2), (767, -2)])
        self.assertEqual(set(result.sizes), {0, -2})
        self.assertEqual(result.position.size, -2)

    def test_both_directions_reverse_at_every_cross_without_increasing_position_size(self):
        for mirror in (False, True):
            data = price_frame(300 - price_frame().Close.to_numpy()) if mirror else price_frame()
            sign = -1 if mirror else 1
            with self.subTest(mirror=mirror):
                result = simulate(BOTH, data)
                self.assertEqual([(bar, size) for bar, size, _ in result.fills],
                                 [(265, 2 * sign), (435, -4 * sign), (592, 4 * sign), (767, -4 * sign)])
                self.assertEqual(set(result.sizes), {0, -2, 2})
                self.assertEqual(result.position.size, -2 * sign)
                for bar, _, price in result.fills:
                    self.assertEqual(price, data.iloc[bar].Open)

    def test_trend_already_in_place_does_not_create_an_entry(self):
        for name in NAMES:
            for prices in (np.linspace(80, 180, 230), np.linspace(180, 80, 230)):
                with self.subTest(name=name, rising=prices[-1] > prices[0]):
                    self.assertEqual(simulate(name, price_frame(prices)).fills, [])

    def test_entry_and_exit_delays_remain_independent(self):
        for name, expected in [(LONG, [(267, 2), (436, -2), (594, 2), (768, -2)]),
                               (SHORT, [(437, -2), (593, 2), (769, -2)]),
                               (BOTH, [(267, 2), (437, -4), (594, 4), (769, -4)])]:
            with self.subTest(name=name):
                result = simulate(name, entry=3, exit=2)
                self.assertEqual([(bar, size) for bar, size, _ in result.fills], expected)

    def test_reversal_uses_the_larger_exit_delay(self):
        result = simulate(BOTH, entry=2, exit=4)
        self.assertEqual([(bar, size) for bar, size, _ in result.fills],
                         [(266, 2), (438, -4), (595, 4), (770, -4)])

    def test_backtest_end_cancels_pending_reversal_and_only_closes_existing_position(self):
        result = simulate(BOTH, price_frame().iloc[:439], entry=3, exit=4, disable_auto_close=False)
        self.assertEqual([(bar, size) for bar, size, _ in result.fills], [(267, 2), (438, -2)])
        self.assertEqual(result.position.size, 0)

    def test_engine_records_reversals_with_correct_position_delays_and_end_liquidation(self):
        data = price_frame()
        with patch.object(engine, 'fetch_data', return_value=data), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('JM0', 'daily', {'fixed_size': 2, 'entry_delay_bars': 2, 'exit_delay_bars': 4}, strategy_name=BOTH)
        self.assertNotIn('error', result)
        self.assertEqual([trade['action'] for trade in result['trades']], ['买多', '反手做空', '反手做多', '反手做空', '平空'])
        self.assertEqual([trade['position'] for trade in result['trades']], [2, -2, 2, -2, 0])
        for trade, bar, delay in zip(result['trades'], [266, 438, 595, 770, len(data) - 1], [2, 4, 4, 4, 1]):
            self.assertEqual(trade['date'][:10], str(data.index[bar].date()))
            self.assertEqual(trade['price'], data.iloc[bar].Open)
            self.assertEqual(trade['execution_delay_bars'], delay)
            self.assertEqual(trade['signal_date'][:10], str(data.index[bar - delay].date()))
        self.assertEqual(result['metrics']['total_trades'], 4)

    def test_start_date_skips_old_entry_crosses(self):
        data = price_frame()
        for name, first in [(LONG, (592, 2)), (SHORT, (435, -2)), (BOTH, (435, -2))]:
            with self.subTest(name=name):
                result = simulate(name, data, start_date=str(data.index[300].date()))
                self.assertEqual(result.fills[0][:2], first)

    def test_backtest_end_liquidates_long_and_short(self):
        for name, limit, size in [(LONG, 360, 2), (SHORT, 500, -2), (BOTH, 360, 2)]:
            with self.subTest(name=name):
                result = simulate(name, price_frame().iloc[:limit], disable_auto_close=False)
                self.assertEqual(result.position.size, 0)
                self.assertEqual(result.fills[-1][:2], (limit - 1, -size))

    def test_engine_registration_defaults_executed_averages_and_trade_directions(self):
        data = price_frame()
        for name in NAMES:
            with self.subTest(name=name), patch.object(engine, 'fetch_data', return_value=data), contextlib.redirect_stdout(io.StringIO()):
                result = engine.BacktestEngine().run('JM0', 'daily', {'fixed_size': 2, 'print_log': False}, strategy_name=name)
                self.assertNotIn('error', result)
                self.assertEqual(result['strategy_info']['name'], name)
                self.assertEqual(result['strategy_info']['params']['exit_period'], 144)
                ma = result['kline_data']['ma']
                self.assertEqual([ma[key] for key in ['strategy_fast_label', 'strategy_slow_label', 'strategy_exit_label']],
                                 ['MA20', 'MA144', 'MA144'])
                self.assertEqual(ma['strategy_slow'], ma['strategy_exit'])
                self.assertEqual(ma['strategy_exit'][-1], round(data.Close.iloc[-144:].mean(), 2))
                if name != BOTH:
                    sign = 1 if name == LONG else -1
                    self.assertTrue(all(trade['position'] * sign >= 0 for trade in result['trades']))

    def test_short_history_is_rejected_before_execution(self):
        for name in NAMES:
            with self.subTest(name=name), patch.object(engine, 'fetch_data', return_value=price_frame().iloc[:144]), contextlib.redirect_stdout(io.StringIO()):
                result = engine.BacktestEngine().run('JM0', 'daily', {}, strategy_name=name)
                self.assertIn('145', result['error'])


if __name__ == '__main__':
    unittest.main()
