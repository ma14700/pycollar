import contextlib
import datetime
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core.contract_backtest import contract_window, contract_scope, contract_choices
from core import engine, tq_provider, tq_worker, optimizer


class ContractBacktestTests(unittest.TestCase):
    def test_pre_delivery_windows_and_year_boundary(self):
        for month, start, end in [('2605', '2025-12-01', '2026-04-23'),
                                  ('2701', '2026-08-01', '2026-12-23'),
                                  ('2402', '2023-09-01', '2024-01-23'),
                                  ('2403', '2023-10-01', '2024-02-23'),
                                  ('2612', '2026-07-01', '2026-11-23')]:
            with self.subTest(month=month):
                self.assertEqual(contract_window(month), {'contract_month': month, 'start_date': start, 'end_date': end})

    def test_invalid_months_and_incompatible_scopes_are_rejected(self):
        for month in ['', '605', '202605', '2600', '2613', 2605, None]:
            with self.subTest(month=month), self.assertRaises(ValueError):
                contract_window(month)
        for args in [('JM0', '2605', 'stock'), ('JM0', '2605', 'futures', 'akshare'),
                     ('JM0', '2605', 'futures', 'tqsdk', 'weighted'), ('JM2701', '2605')]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                contract_scope(*args)
        self.assertEqual(contract_scope('jm0', '2605')['symbol'], 'JM2605')
        self.assertEqual(contract_scope('JM2605', '2605')['symbol'], 'JM2605')

    def test_contract_choices_keep_real_contracts_and_handle_czce_years(self):
        now = datetime.datetime(2026, 10, 29)
        result = contract_choices('JM0', ['DCE.jm2605', 'DCE.jm2701', 'DCE.jm2701',
                                         'DCE.j2605', 'KQ.m@DCE.jm', 'DCE.jm2613', 'DCE.jm1005'], now)
        self.assertEqual([item['value'] for item in result], ['2701', '2605'])
        self.assertEqual(result[1]['symbol'], 'JM2605')
        czce = contract_choices('SA0', ['CZCE.SA605', 'CZCE.SA701'], now)
        self.assertEqual([item['value'] for item in czce], ['2701', '2605'])
        self.assertEqual(czce[0]['resolved_symbol'], 'CZCE.SA701')
        rollover = contract_choices('SA0', ['CZCE.SA001'], datetime.datetime(2029, 10, 1))
        self.assertEqual(rollover[0]['value'], '3001')

    def frame(self, start='2025-09-01', end='2026-06-30'):
        dates = pd.bdate_range(start, end)
        prices = 110 + 10 * np.sin(np.arange(len(dates)) / 7)
        frame = pd.DataFrame({'Open': prices, 'Close': prices, 'High': prices + 2,
                              'Low': prices - 2, 'Volume': 100}, index=dates)
        frame.attrs['data_info'] = {'history_complete': True, 'resolved_symbol': 'DCE.jm2605'}
        return frame

    def test_engine_uses_only_the_specific_contract_and_locked_window(self):
        with patch.object(engine, 'fetch_data', return_value=self.frame()) as fetch, contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('JM0', 'daily', {'fixed_size': 1, 'print_log': False},
                data_provider='tqsdk', contract_month='2605', start_date='2020-01-01', end_date='2030-01-01')
        self.assertNotIn('error', result)
        self.assertEqual(fetch.call_args.kwargs['symbol'], 'JM2605')
        self.assertEqual(fetch.call_args.kwargs['end_date'], '2026-04-23')
        self.assertEqual(result['data_info']['symbol'], 'JM2605')
        self.assertEqual(result['contract_info']['start_date'], '2025-12-01')
        self.assertEqual(result['data_info']['end'][:10], '2026-04-23')
        dates = pd.to_datetime(result['kline_data']['dates'])
        self.assertTrue((dates >= '2025-12-01').all())
        self.assertTrue((dates < '2026-04-24').all())
        for trade in result['trades']:
            self.assertGreaterEqual(trade['date'], '2025-12-01')
            self.assertLess(trade['date'], '2026-04-24')

    def test_future_contract_uses_available_bars_without_inventing_future_prices(self):
        frame = self.frame('2026-06-01', '2026-10-29')
        with patch.object(engine, 'fetch_data', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('JM0', 'daily', {'print_log': False},
                data_provider='tqsdk', contract_month='2701')
        self.assertNotIn('error', result)
        self.assertEqual(result['contract_info']['end_date'], '2026-12-23')
        self.assertEqual(result['data_info']['end'][:10], '2026-10-29')

    def test_listing_after_window_start_is_distinct_from_a_truncated_series(self):
        frame = self.frame('2026-02-01', '2026-05-31')
        with patch.object(engine, 'fetch_data', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('JM0', 'daily', {'print_log': False},
                data_provider='tqsdk', contract_month='2605')
        self.assertNotIn('error', result)
        frame.attrs['data_info']['history_complete'] = False
        with patch.object(engine, 'fetch_data', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
            truncated = engine.BacktestEngine().run('JM0', 'daily', {}, data_provider='tqsdk', contract_month='2605')
        self.assertIn('error', truncated)

    def test_window_without_any_contract_prices_fails_instead_of_using_warmup(self):
        with patch.object(engine, 'fetch_data', return_value=self.frame('2025-06-01', '2025-11-30')), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('JM0', 'daily', {}, data_provider='tqsdk', contract_month='2605')
        self.assertIn('error', result)

    def test_worker_queries_actual_expired_and_active_contracts_and_closes(self):
        api = MagicMock()
        api.query_quotes.return_value = ['DCE.jm2605', 'DCE.jm2701']
        sdk = SimpleNamespace(TqApi=MagicMock(return_value=api), TqAuth=MagicMock())
        with patch.dict(sys.modules, {'tqsdk': sdk}), patch.object(tq_worker, 'credentials', return_value=('user', 'secret')):
            result = tq_worker.collect({'action': 'contracts', 'exchange': 'DCE', 'product': 'jm'})
        self.assertEqual(result['contracts'], ['DCE.jm2605', 'DCE.jm2701'])
        api.query_quotes.assert_called_once_with(ins_class='FUTURE', exchange_id='DCE', product_id='jm', expired=None)
        api.close.assert_called_once()

    def test_specific_contract_quote_uses_last_candle_even_after_expiry(self):
        api = MagicMock()
        api.is_serial_ready.return_value = True
        api.get_kline_serial.return_value = pd.DataFrame({'datetime': [pd.Timestamp('2026-05-15', tz='Asia/Shanghai').value], 'close': [1200.]})
        sdk = SimpleNamespace(TqApi=MagicMock(return_value=api), TqAuth=MagicMock())
        with patch.dict(sys.modules, {'tqsdk': sdk}), patch.object(tq_worker, 'credentials', return_value=('user', 'secret')):
            result = tq_worker.collect({'action': 'contract_quote', 'symbol': 'DCE.jm2605'})
        self.assertEqual(result['price'], 1200)
        self.assertIn('2026-05-15', result['date'])
        api.get_quote.assert_not_called()
        api.close.assert_called_once()
        with patch.object(tq_provider, 'run_worker', return_value=result) as worker:
            tq_provider.fetch_tq_quote('JM2605')
        self.assertEqual(worker.call_args.args[0], {'action': 'contract_quote', 'symbol': 'DCE.jm2605'})

    def test_optimizer_keeps_specific_contract_mode(self):
        opt = optimizer.StrategyOptimizer()
        with patch.object(opt.engine, 'run', return_value={'metrics': {'initial_cash': 10000, 'final_value': 10100}}) as run, contextlib.redirect_stdout(io.StringIO()):
            opt.optimize('JM2605', 'daily', {}, max_trials=1, data_provider='tqsdk', contract_month='2605')
        self.assertEqual(run.call_args.kwargs['contract_month'], '2605')
        self.assertEqual(run.call_args.args[0], 'JM2605')

    def test_api_saves_actual_contract_and_ignores_manually_supplied_dates(self):
        from server import main as api
        metrics = dict(initial_cash=10000, final_value=10100, net_profit=100,
                       sharpe_ratio=0, max_drawdown=0, total_trades=1, win_rate=100)
        db = MagicMock()
        request = api.BacktestRequest(symbol='JM0', period='daily', strategy_params={},
            data_provider='tqsdk', contract_month='2605', auto_optimize=False,
            start_date='2020-01-01', end_date='2030-01-01')
        with patch.object(api, 'BacktestEngine') as cls, contextlib.redirect_stdout(io.StringIO()):
            cls.return_value.run.return_value = {'metrics': metrics}
            api.run_backtest(request, db)
        kwargs = cls.return_value.run.call_args.kwargs
        self.assertEqual(kwargs['symbol'], 'JM2605')
        self.assertEqual(kwargs['start_date'], '2025-12-01')
        self.assertEqual(kwargs['end_date'], '2026-04-23')
        self.assertEqual(db.add.call_args.args[0].symbol, 'JM2605')

    def test_worker_identifies_complete_history_from_bar_ids(self):
        api = MagicMock()
        api.is_serial_ready.return_value = True
        columns = {'id': [0, 1], 'datetime': [1, 2], 'open': [100, 100], 'high': [102, 102],
                   'low': [98, 98], 'close': [100, 100], 'volume': [1, 1], 'close_oi': [1, 1]}
        api.get_kline_serial.return_value = pd.DataFrame(columns)
        sdk = SimpleNamespace(TqApi=MagicMock(return_value=api), TqAuth=MagicMock())
        with patch.dict(sys.modules, {'tqsdk': sdk}), patch.object(tq_worker, 'credentials', return_value=('user', 'secret')):
            complete = tq_worker.collect({'action': 'bars', 'symbol': 'DCE.jm2605', 'period': 'daily'})
            self.assertTrue(complete['history_complete'])
            api.get_kline_serial.return_value['id'] = [100, 101]
            truncated = tq_worker.collect({'action': 'bars', 'symbol': 'DCE.jm2605', 'period': 'daily'})
            self.assertFalse(truncated['history_complete'])


if __name__ == '__main__':
    unittest.main()
