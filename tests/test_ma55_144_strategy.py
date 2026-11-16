import contextlib
import io
import unittest
from unittest.mock import patch

from tests.test_ma20_55_directional import engine, price_frame, simulate


NAMES = ('MA55MA144CrossoverStrategy', 'MA55MA144LongOnlyStrategy', 'MA55MA144ShortOnlyStrategy')


def frame():
    return price_frame([120]*160 + [90]*160 + [140]*160 + [80]*160 + [150]*160 + [100]*160)


class MA55144Tests(unittest.TestCase):
    def test_crossovers_reverse_or_close_only_in_specified_direction(self):
        expected = {
            NAMES[0]: [(321,2),(481,-4),(641,4),(801,-4)],
            NAMES[1]: [(321,2),(481,-2),(641,2),(801,-2)],
            NAMES[2]: [(481,-2),(641,2),(801,-2)],
        }
        data = frame()
        for name in NAMES:
            with self.subTest(name=name):
                result = simulate(name, data)
                self.assertEqual([(bar,size) for bar,size,_ in result.fills], expected[name])
                self.assertTrue(all(price == data.iloc[bar].Open for bar,_,price in result.fills))
                if name == NAMES[1]: self.assertTrue(all(size >= 0 for size in result.holding_sizes))
                if name == NAMES[2]: self.assertTrue(all(size <= 0 for size in result.holding_sizes))

    def test_entry_exit_and_reversal_delays(self):
        data=frame()
        self.assertEqual([(bar,size) for bar,size,_ in simulate(NAMES[1],data,entry=3,exit=2).fills],[(323,2),(482,-2),(643,2),(802,-2)])
        self.assertEqual([(bar,size) for bar,size,_ in simulate(NAMES[2],data,entry=3,exit=2).fills],[(483,-2),(642,2),(803,-2)])
        self.assertEqual([(bar,size) for bar,size,_ in simulate(NAMES[0],data,entry=3,exit=2).fills],[(323,2),(483,-4),(643,4),(803,-4)])

    def test_backtest_defaults_and_actual_indicator_labels(self):
        data=frame()
        for name in NAMES:
            with self.subTest(name=name), patch.object(engine, 'fetch_data', return_value=data), contextlib.redirect_stdout(io.StringIO()):
                result=engine.BacktestEngine().run('JM0','daily',{'fixed_size':2},strategy_name=name)
                self.assertNotIn('error',result)
                self.assertEqual(result['strategy_info']['params']['fast_period'],55)
                self.assertEqual(result['strategy_info']['params']['slow_period'],144)
                self.assertEqual(result['kline_data']['ma']['strategy_fast_label'],'MA55')
                self.assertEqual(result['kline_data']['ma']['strategy_slow_label'],'MA144')

    def test_insufficient_history_is_reported(self):
        for name in NAMES:
            with self.subTest(name=name), patch.object(engine,'fetch_data',return_value=frame().iloc[:100]), contextlib.redirect_stdout(io.StringIO()):
                self.assertIn('145',engine.BacktestEngine().run('JM0','daily',{},strategy_name=name)['error'])

    def test_invalid_period_order_is_rejected_before_fetch(self):
        for name in NAMES:
            with self.subTest(name=name), patch.object(engine,'fetch_data') as fetch, contextlib.redirect_stdout(io.StringIO()):
                result=engine.BacktestEngine().run('JM0','daily',{'fast_period':144,'slow_period':55},strategy_name=name)
                self.assertIn('快均线周期',result['error'])
                fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
