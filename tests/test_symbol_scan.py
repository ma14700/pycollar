import contextlib
import io
import unittest
from unittest.mock import patch

import backtrader as bt
import pandas as pd

from server.core import engine


def minute_bars(closes):
    return pd.DataFrame({
        'Open': [value + 1 for value in closes], 'Close': closes,
        'High': [value + 3 for value in closes], 'Low': [value - 3 for value in closes], 'Volume': 100,
    }, index=pd.date_range('2026-11-17 09:00', periods=len(closes), freq='5min'))


class ScriptedStrategy(engine.strategy.BaseStrategy):
    def next(self):
        if len(self) in (2, 9, 12):
            self.buy(size=2)
        elif len(self) == 6:
            self.close()


class ProtectiveStrategy(engine.strategy.BaseStrategy):
    def next(self):
        if len(self) == 2:
            self.buy(size=1)
        if len(self) == 3:
            self.close(price=100, exectype=bt.Order.Stop)
            self.close(price=150, exectype=bt.Order.Limit)


class SymbolScanTests(unittest.TestCase):
    def setUp(self):
        self.engine = engine.BacktestEngine()
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(patch.object(engine.strategy, 'ScriptedStrategy', ScriptedStrategy, create=True))
        self.enterContext(patch.object(engine.strategy, 'ProtectiveStrategy', ProtectiveStrategy, create=True))

    def test_minute_crosses_on_same_date_are_all_reported_and_ordered(self):
        data = minute_bars([110, 105, 100, 95, 105, 110, 95, 90, 105, 115, 90, 85, 110, 117])
        params = {'fast_period': 2, 'slow_period': 3}
        with patch.object(engine, 'fetch_data', return_value=data):
            row, = self.engine.scan_signals(['JM0'], '5', 11, params, data_provider='tqsdk')
        signals = row['raw_signals']
        self.assertEqual(len(signals), 5)
        self.assertEqual(len({signal['signal_time'] for signal in signals}), 5)
        self.assertEqual(signals[0]['action'], '反手做多')
        self.assertEqual(signals[0]['offset'], 2)
        self.assertEqual(signals[0]['signal_price'], 110)
        self.assertEqual(signals[0]['fill_price'], 118)
        self.assertEqual(signals[0]['fill_time'], str(data.index[-1]))

    def test_exit_to_flat_is_not_reversal_and_pending_uses_submission_bar(self):
        data = minute_bars(list(range(100, 112)))
        params = {'entry_delay_bars': 4, 'exit_delay_bars': 2}
        with patch.object(engine, 'fetch_data', return_value=data):
            row, = self.engine.scan_signals(['JM0'], '60', 12, params, 'ScriptedStrategy', data_provider='gm')
        last, delayed, closed, opened = row['raw_signals']
        self.assertEqual((closed['action'], closed['signal_time'], closed['fill_time']),
                         ('平多', str(data.index[5]), str(data.index[7])))
        self.assertEqual((opened['signal_price'], opened['fill_price']), (101, 106))
        self.assertEqual((delayed['status'], delayed['signal_time'], delayed['signal_price'], delayed['fill_price']),
                         ('pending', str(data.index[8]), 108, None))
        self.assertEqual((last['status'], last['offset']), ('pending', 1))
        with patch.object(engine, 'fetch_data', return_value=data):
            recent, = self.engine.scan_signals(['JM0'], '60', 6, params, 'ScriptedStrategy', data_provider='gm')
        self.assertNotIn('平多', [row['action'] for row in recent['raw_signals']])

    def test_resting_protection_only_appears_when_triggered_and_keeps_gap_price(self):
        data = minute_bars([109, 110, 109, 108, 94, 93])
        with patch.object(engine, 'fetch_data', return_value=data):
            row, = self.engine.scan_signals(['JM0'], '5', 6, {}, 'ProtectiveStrategy', data_provider='gm')
        closed, opened = row['raw_signals']
        self.assertEqual((closed['action'], closed['trigger_basis'], closed['signal_time'], closed['signal_price'],
                          closed['fill_price']), ('平多', '保护价', str(data.index[4]), 100, 95))
        self.assertEqual(opened['action'], '开多')

    def test_detail_replays_same_provider_parameters_and_bar_boundaries(self):
        data = minute_bars(list(range(100, 112)))
        expanded = minute_bars(list(range(100, 114)))
        with patch.object(engine, 'fetch_data', side_effect=[data, expanded]) as fetch:
            row, = self.engine.scan_signals(['JM0'], '60', 12, {'entry_delay_bars': 4},
                                           'ScriptedStrategy', data_provider='gm', data_source='weighted', synthesize_60=True)
            detail = self.engine.analyze_detail(**row['analysis_request'])
        for call in fetch.call_args_list:
            self.assertEqual((call.kwargs['data_provider'], call.kwargs['data_source'], call.kwargs['synthesize_60']),
                             ('gm', 'weighted', True))
        self.assertEqual(detail['data_info'], row['data_info'])
        self.assertEqual([trade['price'] for trade in detail['trades']],
                         [signal['fill_price'] for signal in reversed(row['raw_signals']) if signal['status'] == 'filled'])

    def test_missing_data_and_insufficient_history_remain_distinct_rows(self):
        data = minute_bars([100, 101, 102])
        with patch.object(engine, 'fetch_data', side_effect=[None, data]):
            missing, short = self.engine.scan_signals(['MISSING', 'JM0'], '5', 5, {}, data_provider='tqsdk')
        self.assertEqual((missing['symbol'], missing['status']), ('MISSING', 'error'))
        self.assertIn('未找到', missing['error'])
        self.assertEqual((short['status'], short['available_bars'], short['raw_signals']), ('insufficient_history', 0, []))
