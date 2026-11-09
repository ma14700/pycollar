import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import backtrader as bt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core.strategy import MA20MA55RR3Strategy
from core.execution_delay import SignalDelayBroker
from core.engine import BacktestEngine


def candles(count=20):
    return pd.DataFrame({'Open': 100., 'High': 101., 'Low': 99., 'Close': 100., 'Volume': 100},
                        index=pd.date_range('2025-01-01', periods=count))


def run_case(data=None, signals=None, entry=0, exit=0, **params):
    signals = {5: 1} if signals is None else signals

    class Controlled(MA20MA55RR3Strategy):
        def __init__(self):
            super().__init__()
            self.fills = []

        def _entry_signal(self):
            return signals.get(len(self.data) - 1, 0)

        def notify_order(self, order):
            if order.status == order.Completed:
                self.fills.append((len(self.data) - 1, order.executed.size,
                                   order.executed.price, order.executed.psize, dict(order.info)))
            super().notify_order(order)

    cerebro = bt.Cerebro()
    cerebro.setbroker(SignalDelayBroker(entry_delay_bars=entry, exit_delay_bars=exit))
    cerebro.broker.setcash(100000)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.adddata(bt.feeds.PandasData(dataname=candles() if data is None else data))
    cerebro.addstrategy(Controlled, **{'fast_period': 2, 'slow_period': 3, 'atr_period': 2,
                                      'print_log': False, 'disable_auto_close': True, **params})
    return cerebro.run()[0]


class RiskRewardTests(unittest.TestCase):
    def test_long_and_short_targets_and_net_r(self):
        for direction in (1, -1):
            df = candles()
            df.iloc[7, df.columns.get_loc('High' if direction > 0 else 'Low')] = 113 if direction > 0 else 87
            result = run_case(df, {5: direction})
            self.assertEqual([(f[1], f[2]) for f in result.fills],
                             [(direction, 100), (-direction, 100 + direction * 12)])
            record = result.risk_reward_trades[0]
            self.assertEqual(record['risk_points'], 4)
            self.assertEqual(record['exit_reason'], 'take_profit')
            self.assertAlmostEqual(record['net_r'], (12 - .1 - abs(result.fills[1][2]) * .001) / 4)
            self.assertEqual(result.position.size, 0)
            self.assertFalse(result.broker.get_orders_open())

    def test_entry_bar_both_touched_stop_first_and_no_duplicate_orders(self):
        for direction in (1, -1):
            df = candles()
            df.iloc[6, df.columns.get_loc('High')] = 120
            df.iloc[6, df.columns.get_loc('Low')] = 80
            result = run_case(df, {5: direction})
            self.assertEqual([f[0] for f in result.fills], [6, 6])
            self.assertEqual(result.fills[1][2], 100 - direction * 4)
            self.assertEqual(result.risk_reward_trades[0]['exit_reason'], 'stop_loss')
            self.assertFalse(result.broker.get_orders_open())
            self.assertEqual(result.position.size, 0)

    def test_actual_fill_and_signal_atr_frozen_across_delayed_entry(self):
        df = candles()
        df.loc[df.index[6:8], ['High', 'Low']] = [150, 50]
        df.loc[df.index[8:], ['Open', 'High', 'Low', 'Close']] = [110, 111, 109, 110]
        result = run_case(df, entry=3)
        self.assertEqual(result.fills[0][:3], (8, 1, 110))
        self.assertEqual(result.rr_trade['risk_points'], 4)
        self.assertEqual(result.sl_order.created.price, 106)
        self.assertEqual(result.tp_order.created.price, 122)

    def test_gap_stop_and_target_use_open_before_intrabar_range(self):
        for direction in (1, -1):
            for take_profit in (False, True):
                df = candles()
                gap = 120 if (direction > 0) == take_profit else 80
                df.loc[df.index[7], ['Open', 'High', 'Low', 'Close']] = [gap, 125, 75, gap]
                result = run_case(df, {5: direction})
                self.assertEqual(result.fills[1][2], gap)
                self.assertEqual(result.risk_reward_trades[0]['exit_reason'], 'take_profit' if take_profit else 'stop_loss')
                self.assertEqual(len(result.fills), 2)

    def test_default_ignores_opposite_cross_and_enabled_only_closes(self):
        signals = {5: 1, 8: -1}
        fixed = run_case(signals=signals)
        self.assertEqual(len(fixed.fills), 1)
        early = run_case(signals=signals, exit_on_opposite_cross=True, exit=3)
        self.assertEqual([f[:2] for f in early.fills], [(6, 1), (11, -1)])
        self.assertEqual(early.risk_reward_trades[0]['exit_reason'], 'opposite_cross')
        self.assertFalse(early.broker.get_orders_open())

    def test_stop_cancels_delayed_cross_exit_and_waits_for_fresh_signal(self):
        df = candles()
        df.iloc[9, df.columns.get_loc('Low')] = 95
        result = run_case(df, {5: 1, 8: -1}, exit_on_opposite_cross=True, exit=4)
        self.assertEqual([f[:2] for f in result.fills], [(6, 1), (9, -1)])
        self.assertEqual(result.risk_reward_trades[0]['exit_reason'], 'stop_loss')
        self.assertFalse(result.broker.get_orders_open())

    def test_due_cross_exit_fills_at_open_before_later_intrabar_stop(self):
        df = candles()
        df.iloc[9, df.columns.get_loc('Low')] = 95
        result = run_case(df, {5: 1, 8: -1}, exit_on_opposite_cross=True)
        self.assertEqual(result.fills[1][2], 100)
        self.assertEqual(result.risk_reward_trades[0]['exit_reason'], 'opposite_cross')

    def test_end_cancels_pending_entries_and_liquidates_once(self):
        result = run_case(signals={17: 1}, entry=4, disable_auto_close=False)
        self.assertEqual(result.fills, [])
        self.assertFalse(result.broker.get_orders_open())
        result = run_case(signals={5: -1, 17: 1}, exit=5, exit_on_opposite_cross=True,
                          disable_auto_close=False)
        self.assertEqual([f[:2] for f in result.fills], [(6, -1), (19, 1)])
        self.assertEqual(result.risk_reward_trades[0]['exit_reason'], 'end_of_backtest')
        self.assertFalse(result.broker.get_orders_open())

    def test_invalid_parameters_rejected_before_fetch(self):
        for params in ({'atr_period': 0}, {'atr_multiplier': float('nan')},
                       {'risk_reward_ratio': -3}, {'fixed_size': 1.5},
                       {'fast_period': 55, 'slow_period': 20},
                       {'exit_on_opposite_cross': 'invalid'}, {'size_mode': 'atr_risk'}):
            with patch('core.engine.fetch_data') as fetch, contextlib.redirect_stdout(io.StringIO()):
                result = BacktestEngine().run('JM0', '60', params, strategy_name='MA20MA55RR3Strategy')
            self.assertIn('error', result)
            fetch.assert_not_called()

    def test_engine_same_bar_execution_history_and_accounting(self):
        df = candles(85)
        df['Close'] = [100.] * 55 + [99.] * 5 + [101.] * 25
        df['Open'] = df['Close']
        df['High'] = df['Close'] + 1
        df['Low'] = df['Close'] - 1
        df.loc[df.index[61:], 'High'] = 150
        df.loc[df.index[61:], 'Low'] = 50
        with patch('core.engine.fetch_data', return_value=df), contextlib.redirect_stdout(io.StringIO()):
            result = BacktestEngine().run('JM0', '60', {'print_log': False, 'fixed_size': 1,
                                                      'fast_period': 2, 'slow_period': 3, 'atr_period': 2},
                                         start_date=str(df.index[60].date()), strategy_name='MA20MA55RR3Strategy')
        self.assertNotIn('error', result)
        self.assertGreater(len(result['risk_reward_trades']), 0)
        trades = result['trades']
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0]['date'], trades[1]['date'])
        self.assertEqual(result['risk_reward_trades'][0]['exit_reason'], 'stop_loss')
        for opening, closing in zip(trades[::2], trades[1::2]):
            self.assertTrue(opening['opens_position'])
            self.assertFalse(closing['opens_position'])
            self.assertEqual(closing['position'], 0)
            self.assertEqual(closing['entry_price'], opening['price'])
        self.assertAlmostEqual(sum(t['net_profit'] for t in result['risk_reward_trades']),
                               result['metrics']['net_profit'], places=6)


if __name__ == '__main__':
    unittest.main()
