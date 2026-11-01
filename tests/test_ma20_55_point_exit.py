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
from test_ma20_55_directional import price_frame

NAME = 'MA20MA55PointExitStrategy'


def simulate(frame, direction=None, auto_close=False, entry=1, exit=1, **params):
    class Recorder(getattr(strategy, NAME)):
        def __init__(self):
            super().__init__()
            self.fills, self.sizes = [], []

        def next(self):
            if direction is None:
                super().next()
            elif self.pre_next() and len(self) == 60:
                self.order = self.order_target_size(target=direction * 2)
            self.sizes.append(self.position.size)

        def notify_order(self, order):
            if order.status == order.Completed:
                self.fills.append((len(self) - 1, order.executed.size, order.executed.price))
            super().notify_order(order)

    cerebro = bt.Cerebro()
    cerebro.setbroker(SignalDelayBroker(entry_delay_bars=entry, exit_delay_bars=exit))
    cerebro.broker.setcash(1_000_000)
    cerebro.adddata(bt.feeds.PandasData(dataname=frame))
    cerebro.addstrategy(Recorder, **{'fixed_size': 2, 'print_log': False, 'disable_auto_close': not auto_close,
                                    'take_profit_points': 10, 'stop_loss_points': 5, **params})
    return cerebro.run()[0]


def flat_frame():
    return pd.DataFrame({'Open':100., 'High':101., 'Low':99., 'Close':100., 'Volume':100},
                        index=pd.date_range('2025-01-01', periods=70))


class MA55PointExitTests(unittest.TestCase):
    def test_long_and_short_profit_targets_close_all_at_configured_price_points(self):
        for sign, high, low, target in [(1,111,99,110),(-1,101,89,90)]:
            with self.subTest(direction=sign):
                frame = flat_frame()
                frame.iloc[61,frame.columns.get_loc('High')] = high
                frame.iloc[61,frame.columns.get_loc('Low')] = low
                result = simulate(frame, sign)
                self.assertEqual(result.fills, [(60,2*sign,100),(61,-2*sign,target)])
                self.assertEqual(result.position.size,0)

    def test_stop_loss_is_oco_and_takes_priority_if_both_levels_touched(self):
        for sign, target in [(1,95),(-1,105)]:
            with self.subTest(direction=sign):
                frame = flat_frame()
                frame.iloc[61,frame.columns.get_loc('High')] = 120
                frame.iloc[61,frame.columns.get_loc('Low')] = 80
                result = simulate(frame, sign)
                self.assertEqual(result.fills, [(60,2*sign,100),(61,-2*sign,target)])
                self.assertEqual(result.position.size,0)

    def test_gap_through_stop_executes_at_open_not_an_unavailable_stop_price(self):
        frame = flat_frame()
        frame.loc[frame.index[61],['Open','High','Low','Close']] = [90,91,89,90]
        result = simulate(frame,1)
        self.assertEqual(result.fills[-1],(61,-2,90))

    def test_targets_use_actual_fill_not_signal_price_and_do_not_reenter_without_cross(self):
        frame = price_frame().iloc[:160].copy()
        frame.iloc[122,frame.columns.get_loc('High')] = 151
        result = simulate(frame)
        self.assertEqual(result.fills,[(121,2,140.25),(122,-2,150.25)])
        self.assertEqual(result.position.size,0)

    def test_reversals_cancel_old_protection_without_losing_delayed_order(self):
        result = simulate(price_frame(),entry=2,exit=4,take_profit_points=10000,stop_loss_points=10000)
        self.assertEqual([(bar,size) for bar,size,_ in result.fills],[(122,2),(184,-4),(244,4),(304,-4)])
        self.assertTrue(all(abs(size)<=2 for size in result.sizes))

    def test_forced_end_close_cancels_protection_before_final_bar_touch(self):
        for sign in (1,-1):
            frame = flat_frame()
            frame.iloc[-1,frame.columns.get_loc('High')] = 200
            frame.iloc[-1,frame.columns.get_loc('Low')] = 1
            result = simulate(frame,sign,auto_close=True)
            self.assertEqual(result.fills,[(60,2*sign,100),(69,-2*sign,100)])
            self.assertEqual(result.position.size,0)

    def test_invalid_point_distances_fail_before_fetching_data(self):
        for key in ('take_profit_points','stop_loss_points'):
            for value in (0,-1,float('nan'),float('inf')):
                with self.subTest(key=key,value=value), patch.object(engine,'fetch_data') as fetch, contextlib.redirect_stdout(io.StringIO()):
                    result = engine.BacktestEngine().run('JM0','daily',{key:value},strategy_name=NAME)
                    self.assertIn('error',result)
                    fetch.assert_not_called()

    def test_engine_retains_point_parameters_and_real_executed_averages(self):
        with patch.object(engine,'fetch_data',return_value=price_frame()), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('JM0','daily',{'take_profit_points':12.5,'stop_loss_points':6.25,'fixed_size':2},strategy_name=NAME)
        self.assertNotIn('error',result)
        self.assertEqual(result['strategy_info']['params']['take_profit_points'],12.5)
        self.assertEqual(result['strategy_info']['params']['stop_loss_points'],6.25)
        self.assertEqual(result['kline_data']['ma']['strategy_fast_label'],'MA20')
        self.assertEqual(result['kline_data']['ma']['strategy_slow_label'],'MA55')


if __name__ == '__main__':
    unittest.main()
