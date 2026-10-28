import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import backtrader as bt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import engine, strategy


STRATEGIES = [
    'MA55BreakoutStrategy', 'MA55TouchExitStrategy', 'MA20MA55CrossoverStrategy',
    'MA20MA60CrossoverStrategy', 'MA5MA20CrossoverStrategy', 'MA5MA55CrossoverStrategy',
    'MA20MA55RiskRewardStrategy', 'StockMA20MA55LongOnlyStrategy',
    'MA20MA55PartialTakeProfitStrategy', 'DualMAFixedTPSLStrategy', 'DKXStrategy',
    'DKXPartialTakeProfitStrategy', 'DKXFixedTPSLStrategy', 'TrendFollowingStrategy',
    'MA20MA144LongOnlyStrategy', 'MA20MA144ShortOnlyStrategy', 'MA20MA144LongShortStrategy',
    'MA20MA55LongOnlyStrategy', 'MA20MA55ShortOnlyStrategy',
]


def price_frame(prices=None, period='D'):
    if prices is None:
        x = np.arange(320)
        prices = 110 + 12 * np.sin(x / 10) + 3 * np.sin(x / 3)
    return pd.DataFrame({'Open': prices, 'High': np.array(prices) + 2,
                         'Low': np.array(prices) - 2, 'Close': prices, 'Volume': 1000},
                        index=pd.date_range('2025-01-01', periods=len(prices), freq=period))


class TomorrowStrategyTests(unittest.TestCase):
    def detail(self, frame, name='TrendFollowingStrategy', params=None, **kwargs):
        with patch.object(engine, 'fetch_data', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
            return engine.BacktestEngine().analyze_detail('JM0', 'daily', params or {},
                                                          strategy_name=name, data_provider='tqsdk', **kwargs)

    def test_every_strategy_matches_unwrapped_backtrader_execution(self):
        for name in STRATEGIES:
            for overrides in ({}, {'fast_period': '3', 'slow_period': '9', 'fixed_size': '4',
                                  'take_profit_points': 3, 'stop_loss_points': 2,
                                  'sl_value': 2, 'tp_value': 3, 'atr_multiplier': 0.8}):
                with self.subTest(strategy=name, custom=bool(overrides)):
                    frame = price_frame()
                    detail = self.detail(frame, name, overrides)
                    self.assertNotIn('error', detail)
                    cerebro = bt.Cerebro()
                    cerebro.broker.setcash(10000000)
                    cerebro.broker.setcommission(commission=0.0001, margin=0,
                                                  mult=detail['strategy_info']['params']['contract_multiplier'])
                    cerebro.adddata(bt.feeds.PandasData(dataname=frame))
                    cerebro.addstrategy(getattr(strategy, name), **detail['strategy_info']['params'])
                    cerebro.addanalyzer(bt.analyzers.Transactions, _name='transactions')
                    expected = cerebro.run()[0]
                    self.assertEqual(detail['position_state']['size'], expected.position.size)
                    if expected.position.size:
                        self.assertAlmostEqual(detail['position_state']['entry_price'], expected.position.price)
                    expected_trades = [(date.strftime('%Y-%m-%d %H:%M:%S'), event[0], event[1])
                                       for date, events in expected.analyzers.transactions.get_analysis().items()
                                       for event in events]
                    actual_trades = [(trade['date'], trade['size'], trade['price']) for trade in detail['trades']]
                    self.assertEqual(len(actual_trades), len(expected_trades))
                    for actual, expected_trade in zip(actual_trades, expected_trades):
                        self.assertEqual(actual[:2], expected_trade[:2])
                        self.assertAlmostEqual(actual[2], expected_trade[2], places=9)

    def test_list_and_details_keep_the_same_position_for_every_strategy(self):
        for name in STRATEGIES:
            with self.subTest(strategy=name):
                frame = price_frame()
                with patch.object(engine, 'fetch_data', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
                    row = engine.BacktestEngine().analyze_batch(['JM0'], 'daily', {},
                            strategy_name=name, data_provider='tqsdk')[0]
                    self.assertNotIn('error', row)
                    detail = engine.BacktestEngine().analyze_detail(**row['analysis_request'])
                for key, value in detail['position_state'].items():
                    self.assertEqual(row[key], value)

    def test_normal_backtest_closes_but_tomorrow_keeps_live_position(self):
        frame = price_frame([100] * 25 + [90] * 15 + [110] * 10)
        params = {'fast_period': 3, 'slow_period': 9, 'fixed_size': 2}
        detail = self.detail(frame, params=params)
        self.assertEqual(detail['position_state']['size'], 2)
        self.assertTrue(detail['trades'][-1]['opens_position'])
        with patch.object(engine, 'fetch_data', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
            backtest = engine.BacktestEngine().run('JM0', 'daily', params)
        self.assertEqual(backtest['position_state']['size'], 0)

    def test_details_do_not_include_bars_after_analysis(self):
        frame = price_frame()
        before = self.detail(frame.iloc[:200])
        with patch.object(engine, 'fetch_data', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
            after = engine.BacktestEngine().analyze_detail(**before['analysis_request'])
        self.assertEqual(before['trades'], after['trades'])
        self.assertEqual(before['position_state'], after['position_state'])
        self.assertEqual(len(after['kline_data']['dates']), 200)

    def test_default_and_ema_lines_are_actual_executed_indicators(self):
        for name, params in [('TrendFollowingStrategy', {}), ('TrendFollowingStrategy', {'use_expma': True}),
                             ('DualMAFixedTPSLStrategy', {'ma_type': 'EMA'})]:
            with self.subTest(strategy=name, params=params):
                frame = price_frame()
                detail = self.detail(frame, name, params)
                cerebro = bt.Cerebro()
                cerebro.adddata(bt.feeds.PandasData(dataname=frame))
                cerebro.addstrategy(getattr(strategy, name), **detail['strategy_info']['params'])
                executed = cerebro.run()[0]
                for key in ['fast', 'slow']:
                    expected = [round(float(v), 2) if np.isfinite(v) else None
                                for v in getattr(executed, f'ma_{key}').array]
                    self.assertEqual(detail['kline_data']['ma'][f'strategy_{key}'], expected)
                self.assertEqual(detail['kline_data']['ma']['strategy_fast_period'], 10 if name == 'TrendFollowingStrategy' else 20)

    def test_bracket_orders_cannot_both_fill_in_one_candle(self):
        for name in ['DualMAFixedTPSLStrategy', 'DKXFixedTPSLStrategy', 'MA20MA55RiskRewardStrategy']:
            for direction in [1, -1]:
                with self.subTest(strategy=name, direction=direction):
                    base = getattr(strategy, name)

                    class OneEntry(base):
                        def next(self):
                            if len(self) == 60:
                                self.order = self.order_target_size(target=direction * 4)

                    frame = price_frame([100] * 70)
                    # Both stop and target prices are touched after the bracket is placed.
                    frame.iloc[61, frame.columns.get_loc('High')] = 300
                    frame.iloc[61, frame.columns.get_loc('Low')] = 1
                    cerebro = bt.Cerebro()
                    cerebro.broker.setcash(10000000)
                    cerebro.adddata(bt.feeds.PandasData(dataname=frame))
                    cerebro.addstrategy(OneEntry, disable_auto_close=True, print_log=False)
                    cerebro.addanalyzer(bt.analyzers.Transactions, _name='transactions')
                    result = cerebro.run()[0]
                    trades = [event for events in result.analyzers.transactions.get_analysis().values() for event in events]
                    self.assertEqual(len(trades), 2, 'Exactly one entry and one protective exit')
                    self.assertEqual(result.position.size, 0, 'A protective exit must not open the opposite position')

    def test_invalid_strategy_never_silently_uses_default(self):
        detail = self.detail(price_frame(), 'MissingStrategy')
        self.assertIn('MissingStrategy', detail['error'])

    def test_rolled_off_history_requires_a_new_analysis(self):
        frame = price_frame()
        original = self.detail(frame)
        with patch.object(engine, 'fetch_data', return_value=frame.iloc[10:]), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().analyze_detail(**original['analysis_request'])
        self.assertIn('重新分析', result['error'])

    def test_snapshot_preserves_independent_execution_delays(self):
        frame = price_frame()
        original = self.detail(frame, params={'entry_delay_bars': 3, 'exit_delay_bars': 4})
        request = original['analysis_request']
        self.assertEqual(request['strategy_params']['entry_delay_bars'], 3)
        self.assertEqual(request['strategy_params']['exit_delay_bars'], 4)
        with patch.object(engine, 'fetch_data', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
            replayed = engine.BacktestEngine().analyze_detail(**request)
        self.assertEqual(original['trades'], replayed['trades'])
        self.assertEqual(original['position_state'], replayed['position_state'])

    def test_strategy_callbacks_do_not_duplicate_dashboard_execution_logs(self):
        detail = self.detail(price_frame(), 'DualMAFixedTPSLStrategy',
                             {'fast_period': 3, 'slow_period': 9, 'fixed_size': 4,
                              'sl_value': 2, 'tp_value': 3})
        executions = [line for line in detail['logs'] if any(
            marker in line for marker in ('交易执行', '买入成交', '卖出成交'))]
        self.assertEqual(len(executions), len(detail['trades']))
        self.assertGreater(detail['metrics']['total_trades'], 0)

    def test_partial_take_profit_does_not_reset_holding_duration(self):
        prices = [100] * 25 + [110] * 8 + [90] * 12 + list(range(110, 150))
        detail = self.detail(price_frame(prices), 'MA20MA55PartialTakeProfitStrategy',
                             {'fast_period': 3, 'slow_period': 9, 'fixed_size': 8, 'take_profit_points': 3})
        self.assertEqual(detail['position_state']['size'], 1)
        opening = next(trade for trade in detail['trades'] if trade['opens_position'] and trade['size'] > 0)
        entry_index = detail['kline_data']['dates'].index(opening['date'])
        self.assertEqual(detail['position_state']['hold_bars'], len(prices) - entry_index - 1)
        reductions = [trade for trade in detail['trades'] if trade['action'] == '平多']
        self.assertGreaterEqual(len(reductions), 3)

    def test_latest_bar_signal_is_pending_and_not_marked_as_filled(self):
        frame = price_frame([100] * 25 + [110] * 8 + [90] * 12 + [120])
        detail = self.detail(frame, params={'fast_period': 2, 'slow_period': 5})
        self.assertEqual(detail['position_state']['size'], -1)
        self.assertEqual(len(detail['pending_orders']), 1)
        self.assertEqual(detail['pending_orders'][0]['type'], 'buy')
        self.assertNotEqual(detail['trades'][-1]['date'], detail['kline_data']['dates'][-1])


if __name__ == '__main__':
    unittest.main()
