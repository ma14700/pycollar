import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import tq_provider as tq, tq_worker, data_loader, engine, optimizer
from core.constants import FUTURES_MULTIPLIERS


def bars(times, prices=None):
    prices = prices if prices is not None else [100] * len(times)
    return [{"datetime": pd.Timestamp(t, tz='Asia/Shanghai').value,
             "open": p, "high": p + 2, "low": p - 2, "close": p,
             "volume": 100, "close_oi": 200} for t, p in zip(times, prices)]


class TqProviderTests(unittest.TestCase):
    def test_weekly_aggregates_full_ohlcv_and_excludes_unfinished_week(self):
        daily = tq.normalize_serial(bars(pd.bdate_range('2025-01-06', '2025-01-15').astype(str),
                                        list(range(100, 108))), 'daily', now='2025-01-15 16:00')
        weekly = tq.completed_weekly_bars(daily, now='2025-01-15 16:00')
        self.assertEqual(list(weekly.index), [pd.Timestamp('2025-01-10')])
        self.assertEqual(list(weekly.iloc[0]), [100, 106, 98, 104, 500, 200])

    def test_weekly_completion_uses_beijing_friday_close(self):
        daily = tq.normalize_serial(bars(['2025-01-06', '2025-01-10']), 'daily', now='2025-01-11')
        self.assertTrue(tq.completed_weekly_bars(daily, now='2025-01-10T07:14:00Z').empty)
        self.assertEqual(len(tq.completed_weekly_bars(daily, now='2025-01-10T07:15:00Z')), 1)

    def test_weekly_uses_tq_daily_and_filters_after_aggregation(self):
        raw = bars(pd.bdate_range('2025-01-06', '2025-01-17').astype(str), list(range(100, 110)))
        with patch.object(tq, 'run_worker', return_value={'bars': raw}) as worker:
            weekly = tq.fetch_tq_data('RB0', 'weekly', '2025-01-08', '2025-01-15')
        self.assertEqual(worker.call_args.args[0]['period'], 'daily')
        self.assertEqual(len(weekly), 1)
        self.assertEqual(weekly.iloc[0].Open, 100)
        self.assertEqual(weekly.attrs['data_info']['provider'], 'tqsdk')
        self.assertEqual(weekly.attrs['data_info']['period'], 'weekly')

    def test_symbol_mapping(self):
        for symbol, kind, expected in [
            ('RB0', 'main', 'KQ.m@SHFE.rb'), ('SH0', 'main', 'KQ.m@CZCE.SH'),
            ('LH0', 'weighted', 'KQ.i@DCE.lh'), ('IF0', 'main', 'KQ.m@CFFEX.IF'),
            ('SC0', 'main', 'KQ.m@INE.sc'), ('SI0', 'main', 'KQ.m@GFEX.si'),
            ('rb2701', 'main', 'SHFE.rb2701'), ('SH2701', 'main', 'CZCE.SH701'),
        ]:
            self.assertEqual(tq.tq_symbol(symbol, kind), expected)
        for product in FUTURES_MULTIPLIERS:
            self.assertTrue(tq.tq_symbol(product + '0').startswith('KQ.m@'))

    def test_invalid_symbols_and_series_are_rejected(self):
        for symbol, kind in [('FAKE0', 'main'), ('sh600000', 'main'), ('RB2701', 'weighted'), ('RB0', 'other')]:
            with self.assertRaises(ValueError):
                tq.tq_symbol(symbol, kind)

    def test_beijing_time_and_unfinished_minute(self):
        raw = bars(['2025-01-03 21:00', '2025-01-03 21:05', '2025-01-03 21:10'])
        df = tq.normalize_serial(raw, '5', now='2025-01-03 21:12')
        self.assertEqual(list(df.index), [pd.Timestamp('2025-01-03 21:00'), pd.Timestamp('2025-01-03 21:05')])
        self.assertEqual(list(df.columns), ['Open', 'High', 'Low', 'Close', 'Volume', 'OpenInterest'])

    def test_daily_completion_and_placeholder_filter(self):
        raw = bars(['2025-01-02', '2025-01-03'])
        raw.insert(0, {**raw[0], 'datetime': 0})
        df = tq.normalize_serial(raw, 'daily', now='2025-01-03 14:00')
        self.assertEqual(list(df.index), [pd.Timestamp('2025-01-02')])
        self.assertEqual(len(tq.normalize_serial(raw, 'daily', now='2025-01-03 15:16')), 2)

    def test_bad_ohlc_rejected(self):
        raw = bars(['2025-01-02'])
        raw[0]['high'] = 50
        with self.assertRaises(ValueError):
            tq.normalize_serial(raw, 'daily', now='2025-01-03')

    def test_sorted_and_deduplicated(self):
        raw = bars(['2025-01-03', '2025-01-02', '2025-01-02'])
        df = tq.normalize_serial(raw, 'daily', now='2025-01-04')
        self.assertEqual(len(df), 2)
        self.assertTrue(df.index.is_monotonic_increasing)

    def test_date_filter_metadata_and_no_fallback(self):
        with patch.object(tq, 'run_worker', return_value={'bars': bars(['2025-01-02', '2025-01-03', '2025-01-06'])}):
            df = tq.fetch_tq_data('RB0', 'daily', '2025-01-03', '2025-01-03')
            self.assertEqual(len(df), 1)
            self.assertEqual(df.attrs['data_info']['resolved_symbol'], 'KQ.m@SHFE.rb')
            with self.assertRaisesRegex(ValueError, '免费滚动窗口'):
                tq.fetch_tq_data('RB0', 'daily', '2020-01-01', '2020-01-31')

    def test_routing_does_not_call_legacy_on_tq_failure(self):
        with patch.object(tq, 'fetch_tq_data', side_effect=ValueError('account missing')) as new, patch.object(data_loader, 'fetch_futures_data') as old:
            with self.assertRaises(ValueError):
                data_loader.fetch_data('RB0', '5', data_provider='tqsdk')
            new.assert_called_once()
            old.assert_not_called()
        with self.assertRaisesRegex(ValueError, '仅支持期货'):
            data_loader.fetch_data('sh600000', data_provider='tqsdk', market_type='stock')

    def test_legacy_routing_unchanged(self):
        with patch.object(data_loader, 'fetch_futures_data', return_value='legacy'):
            self.assertEqual(data_loader.fetch_data('RB0'), 'legacy')

    def test_credentials_status_never_exposes_secrets(self):
        with patch.object(tq, 'credentials', return_value=('private-user', 'private-password')):
            result = tq.provider_status()
            self.assertTrue(result['configured'])
            self.assertNotIn('private', json.dumps(result))

    def test_missing_config_fails_before_connecting(self):
        with patch.object(tq, 'credentials', return_value=('', '')), patch.object(tq.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'TQ_USERNAME'):
                tq.run_worker({'action': 'bars'})
            run.assert_not_called()

    def test_worker_timeout_and_diagnostics_are_sanitized(self):
        with patch.object(tq, 'credentials', return_value=('user', 'secret')), patch.object(tq.importlib.util, 'find_spec', return_value=True):
            with patch.object(tq.subprocess, 'run', side_effect=subprocess.TimeoutExpired('secret', 60)):
                with self.assertRaisesRegex(ValueError, '60 秒') as error:
                    tq.run_worker({'action': 'bars'})
                self.assertNotIn('secret', str(error.exception))
            with patch.object(tq.subprocess, 'run', return_value=SimpleNamespace(stdout='secret traceback', returncode=1)):
                with self.assertRaisesRegex(ValueError, '天勤连接失败') as error:
                    tq.run_worker({'action': 'bars'})
                self.assertNotIn('secret', str(error.exception))

    def test_sdk_rolling_series_and_close(self):
        serial = pd.DataFrame(bars(['2025-01-02', '2025-01-03']))
        from unittest.mock import MagicMock
        api = MagicMock()
        api.get_kline_serial.return_value = serial
        api.is_serial_ready.return_value = True
        sdk = SimpleNamespace(TqApi=MagicMock(return_value=api), TqAuth=MagicMock())
        with patch.dict(sys.modules, {'tqsdk': sdk}), patch.object(tq_worker, 'credentials', return_value=('user', 'secret')):
            result = tq_worker.collect({'action': 'bars', 'symbol': 'KQ.m@SHFE.rb', 'period': '5'})
            api.get_kline_serial.assert_called_once_with('KQ.m@SHFE.rb', 300, data_length=10000)
            api.close.assert_called_once()
            self.assertIsInstance(result['bars'][0]['datetime'], int)
            sdk.TqApi.assert_called_once_with(auth=sdk.TqAuth.return_value, disable_print=True)

    def test_sdk_closed_when_fetch_raises(self):
        from unittest.mock import MagicMock
        api = MagicMock()
        api.get_kline_serial.side_effect = RuntimeError('offline')
        sdk = SimpleNamespace(TqApi=MagicMock(return_value=api), TqAuth=MagicMock())
        with patch.dict(sys.modules, {'tqsdk': sdk}), patch.object(tq_worker, 'credentials', return_value=('user', 'secret')):
            with self.assertRaises(RuntimeError):
                tq_worker.collect({'action': 'bars', 'symbol': 'KQ.m@SHFE.rb', 'period': '5'})
            api.close.assert_called_once()

    def test_quote_uses_same_resolved_contract_and_closes_connection(self):
        from unittest.mock import MagicMock
        api = MagicMock()
        api.get_quote.return_value = SimpleNamespace(datetime='2025-01-03 14:59:00.000000', last_price=3500)
        sdk = SimpleNamespace(TqApi=MagicMock(return_value=api), TqAuth=MagicMock())
        with patch.dict(sys.modules, {'tqsdk': sdk}), patch.object(tq_worker, 'credentials', return_value=('user', 'secret')):
            result = tq_worker.collect({'action': 'quote', 'symbol': 'KQ.i@SHFE.rb'})
        self.assertEqual(result['price'], 3500)
        api.get_quote.assert_called_once_with('KQ.i@SHFE.rb')
        api.close.assert_called_once()

    def test_sdk_subscription_timeout_closes_connection(self):
        from unittest.mock import MagicMock
        api = MagicMock()
        api.is_serial_ready.return_value = False
        api.wait_update.return_value = False
        sdk = SimpleNamespace(TqApi=MagicMock(return_value=api), TqAuth=MagicMock())
        with patch.dict(sys.modules, {'tqsdk': sdk}), patch.object(tq_worker, 'credentials', return_value=('user', 'secret')):
            with self.assertRaises(TimeoutError):
                tq_worker.collect({'action': 'bars', 'symbol': 'KQ.m@SHFE.rb', 'period': '5'})
        api.close.assert_called_once()

    def test_engine_rejects_partial_requested_range(self):
        df = pd.DataFrame({'Close': [100]}, index=pd.to_datetime(['2025-06-01']))
        with patch.object(engine, 'fetch_data', return_value=df), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('RB0', 'daily', {}, start_date='2025-01-01', data_provider='tqsdk')
        self.assertIn('无法覆盖', result['error'])

    def test_full_engine_uses_tq_metadata_and_keeps_input_parameters(self):
        prices = 100 + np.sin(np.arange(120) / 5) * 10
        raw = bars(pd.date_range('2025-01-01', periods=120).astype(str), prices)
        params = {'fast_period': 2, 'slow_period': 5, 'fixed_size': 1}
        with patch.object(tq, 'run_worker', return_value={'bars': raw}), contextlib.redirect_stdout(io.StringIO()):
            result = engine.BacktestEngine().run('RB0', 'daily', params, data_provider='tqsdk')
        self.assertEqual(result['data_info']['provider'], 'tqsdk')
        self.assertEqual(result['data_info']['bars'], 120)
        self.assertGreater(result['metrics']['total_trades'], 0)
        self.assertNotIn('start_date', params)

    def test_optimizer_keeps_supplier_market_and_cash(self):
        opt = optimizer.StrategyOptimizer()
        result = {'metrics': {'initial_cash': 50000, 'final_value': 51000}}
        with patch.object(opt.engine, 'run', return_value=result) as run, contextlib.redirect_stdout(io.StringIO()):
            opt.optimize('RB0', 'daily', {}, max_trials=1, data_provider='tqsdk', initial_cash=50000)
        self.assertEqual(run.call_args.kwargs['data_provider'], 'tqsdk')
        self.assertEqual(run.call_args.kwargs['initial_cash'], 50000)


if __name__ == '__main__':
    unittest.main()
