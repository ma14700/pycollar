import contextlib
import io
from pathlib import Path
import sys
import unittest
import types
from unittest.mock import patch
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import gm_provider as gm, data_loader, engine
from core import gm_worker


def rows(dates, price=100):
    return [{'bob':f'{date}T00:00:00+08:00','eob':f'{date}T00:00:00+08:00',
             'open':price,'high':price+2,'low':price-2,'close':price,'volume':100,'position':200}
            for date in dates]


class GMProviderTests(unittest.TestCase):
    def test_main_weighted_and_specific_contract_codes(self):
        for symbol, source, expected in [('JM0','main','DCE.JM'),('JM0','weighted','DCE.JM99'),
                                          ('JM2701','main','DCE.jm2701'),('SH2701','main','CZCE.SH701'),
                                          ('IF2701','main','CFFEX.IF2701')]:
            self.assertEqual(gm.gm_symbol(symbol,source),expected)
        with self.assertRaises(ValueError): gm.gm_symbol('JM2701','weighted')
        with self.assertRaises(ValueError): gm.gm_symbol('FAKE0')

    def test_timezone_and_completed_candles(self):
        daily = gm.normalize(rows(['2025-01-02','2025-01-03']), 'daily', now='2025-01-03 15:14:00+08:00')
        self.assertEqual(list(daily.index),[pd.Timestamp('2025-01-02')])
        minute = rows(['2025-01-03'])
        minute[0].update(bob='2025-01-03T09:00:00+08:00', eob='2025-01-03T10:00:00+08:00')
        self.assertTrue(gm.normalize(minute, '60', now='2025-01-03 09:59:00+08:00').empty)
        self.assertEqual(gm.normalize(minute,'60',now='2025-01-03 10:00:00+08:00').index[0],pd.Timestamp('2025-01-03 09:00:00'))

    def test_warmup_clips_only_when_the_requested_start_is_permitted(self):
        warning='掘金数据权限不足：查询起始日期不早于 2025-02-01'
        raw=rows(pd.bdate_range('2025-02-03',periods=10).strftime('%Y-%m-%d'))
        with patch.object(gm,'run_worker',side_effect=[ValueError(warning),raw]) as worker:
            frame=gm.fetch_gm_data('JM0','daily','2024-01-01','2025-03-01','weighted','2025-02-03')
        self.assertEqual(worker.call_count,2)
        self.assertEqual(worker.call_args.args[0]['symbol'],'DCE.JM99')
        self.assertIn('预热数据受账号权限限制',frame.attrs['data_info']['note'])
        with patch.object(gm,'run_worker',side_effect=ValueError(warning)) as worker:
            with self.assertRaisesRegex(ValueError,'权限不足'):
                gm.fetch_gm_data('JM0','daily','2024-01-01','2025-03-01','main','2024-01-01')
            self.assertEqual(worker.call_count,1)

    def test_backtest_uses_gm_index_and_retains_metadata(self):
        dates=pd.bdate_range(end=pd.Timestamp.now().normalize()-pd.Timedelta(days=1),periods=90).strftime('%Y-%m-%d')
        with patch.object(gm,'run_worker',return_value=rows(dates)) as worker, contextlib.redirect_stdout(io.StringIO()):
            result=engine.BacktestEngine().run('JM0','daily',{'fixed_size':1,'print_log':False},
                strategy_name='MA20MA55CrossoverStrategy',data_provider='gm',data_source='weighted')
        self.assertNotIn('error',result)
        self.assertEqual(worker.call_args.args[0]['symbol'],'DCE.JM99')
        self.assertEqual(result['data_info']['provider_name'],'掘金量化')
        self.assertEqual(result['data_info']['data_source'],'weighted')
        self.assertEqual(result['kline_data']['values'][-1][1],100)

    def test_no_fallback_on_gm_errors_or_stock(self):
        with patch.object(gm,'run_worker',side_effect=ValueError('权限不足')), \
             patch.object(data_loader,'fetch_futures_data') as fallback:
            with self.assertRaisesRegex(ValueError,'权限不足'):
                data_loader.fetch_data('JM0','daily',data_provider='gm')
            fallback.assert_not_called()
        with self.assertRaisesRegex(ValueError,'仅支持期货'):
            data_loader.fetch_data('sh600000','daily',market_type='stock',data_provider='gm')

    def test_history_requests_are_bounded_to_avoid_provider_truncation(self):
        calls=[]
        api=types.ModuleType('gm.api')
        api.set_token=lambda token: None
        api.history_n=lambda **kwargs: None
        def history(**kwargs):
            calls.append(kwargs)
            return pd.DataFrame(rows(['2025-01-02']))
        api.history=history
        with patch.dict(sys.modules,{'gm':types.ModuleType('gm'),'gm.api':api}):
            result=gm_worker.collect({'token':'test','action':'bars','symbol':'DCE.JM99',
                'frequency':'60s','start':'2025-01-01T00:00:00','end':'2025-02-10T00:00:00'})
        self.assertEqual(len(calls),3)
        self.assertEqual(len(result['rows']),3)
        self.assertTrue(all((pd.Timestamp(call['end_time'])-pd.Timestamp(call['start_time'])).days<=15 for call in calls))

    def test_analysis_without_dates_uses_gm_recent_window(self):
        backtest = engine.BacktestEngine()
        with patch.object(backtest, 'run', return_value={'error':'test'}) as run:
            backtest.analyze_detail('JM0','60',{},data_provider='gm')
        self.assertIsNone(run.call_args.kwargs['start_date'])


if __name__=='__main__': unittest.main()
