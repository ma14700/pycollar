import contextlib
from concurrent.futures import ThreadPoolExecutor
import io
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import market_cache as mc, tq_provider as tq, data_loader, engine


def frame(dates, price=100, complete=True):
    result = pd.DataFrame({'Open': price, 'High': price + 2, 'Low': price - 2, 'Close': price,
                           'Volume': 10, 'OpenInterest': 20}, index=pd.to_datetime(dates))
    result.attrs['data_info'] = {'history_complete': complete}
    return result


def serial(dates):
    return [{'datetime': pd.Timestamp(date, tz='Asia/Shanghai').value,
             'open': 100, 'high': 102, 'low': 98, 'close': 100, 'volume': 10, 'close_oi': 20}
            for date in dates]


class MarketCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'cache.sqlite3'
        self.cache = mc.MarketCache(self.path)
        self.addCleanup(patch.stopall)
        patch.object(mc, 'CACHE_DB_PATH', self.path).start()
        self.clock = patch.object(mc, '_now', return_value=pd.Timestamp('2026-10-29 16:00')).start()

    def candles(self, load, **kwargs):
        options = dict(start_date='2026-01-01', end_date='2026-04-23')
        options.update(kwargs)
        return self.cache.candles('tqsdk', 'JM2605', 'daily', load, **options)

    def test_persistent_hit_reuses_full_download_and_warmup_without_network(self):
        load = Mock(return_value=frame(pd.bdate_range('2025-06-01', '2026-05-15')))
        first = self.candles(load)
        self.assertEqual(first.attrs['data_info']['cache_status'], 'miss')
        self.cache = mc.MarketCache(self.path)
        load.side_effect = AssertionError('must stay offline')
        second = self.candles(load, start_date='2025-12-01')
        self.assertEqual(second.attrs['data_info']['cache_status'], 'hit')
        self.assertEqual(second.index.min(), pd.Timestamp('2025-12-01'))
        self.assertEqual(load.call_count, 1)
        self.assertTrue(self.path.exists())

    def test_history_before_listing_and_nontrading_dates_are_certified(self):
        load = Mock(return_value=frame(pd.bdate_range('2026-01-05', '2026-04-24')))
        self.candles(load, start_date='2025-12-01')
        self.candles(load, start_date='2026-01-03', end_date='2026-01-04')
        self.assertEqual(load.call_count, 1)

    def test_overlap_preserves_closed_prices_and_adds_missing_prefix(self):
        load = Mock(side_effect=[frame(pd.bdate_range('2026-03-01', '2026-05-01'), complete=False),
                                 frame(pd.bdate_range('2026-01-01', '2026-05-01'), price=110, complete=False)])
        self.candles(load, start_date='2026-03-02')
        updated = self.candles(load)
        self.assertEqual(updated.attrs['data_info']['cache_status'], 'partial')
        self.assertEqual(updated.loc['2026-03-02', 'Close'], 100)
        self.assertEqual(updated.loc['2026-01-02', 'Close'], 110)
        self.assertEqual(load.call_count, 2)

    def test_deleted_interior_bar_triggers_refetch_instead_of_false_hit(self):
        load = Mock(return_value=frame(pd.bdate_range('2026-01-01', '2026-05-01')))
        self.candles(load)
        with contextlib.closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('DELETE FROM contract_candles WHERE timestamp=?', (mc._seconds('2026-02-10'),))
        restored = self.candles(load)
        self.assertEqual(load.call_count, 2)
        self.assertIn(pd.Timestamp('2026-02-10'), restored.index)

    def test_missing_rolling_prefix_cannot_be_marked_complete(self):
        load = Mock(return_value=frame(pd.bdate_range('2026-03-01', '2026-05-01'), complete=False))
        with self.assertRaises(ValueError):
            self.candles(load)
        with self.assertRaises(ValueError):
            self.candles(load)
        self.assertEqual(load.call_count, 2)

    def test_provider_symbol_and_period_are_isolated(self):
        load = Mock(return_value=frame(['2026-01-05']))
        for provider, symbol, period in [('tqsdk', 'JM2605', 'daily'), ('akshare', 'JM2605', 'daily'),
                                         ('tqsdk', 'RB2605', 'daily'), ('tqsdk', 'JM2605', '5')]:
            self.cache.candles(provider, symbol, period, load, end_date='2026-04-23')
        self.assertEqual(load.call_count, 4)

    def test_current_day_is_not_saved_until_daily_close_and_future_is_not_covered(self):
        self.clock.return_value = pd.Timestamp('2026-10-29 14:00')
        load = Mock(return_value=frame(['2026-10-28', '2026-10-29', '2026-10-30']))
        def fetch():
            return self.cache.candles('tqsdk', 'JM2701', 'daily', load, end_date='2026-12-23')
        before = fetch()
        self.assertEqual(list(before.index), [pd.Timestamp('2026-10-28')])
        fetch()
        self.assertEqual(load.call_count, 1)
        self.clock.return_value = pd.Timestamp('2026-10-29 16:00')
        after = fetch()
        self.assertEqual(after.index.max(), pd.Timestamp('2026-10-29'))
        self.assertEqual(load.call_count, 2)
        self.clock.return_value = pd.Timestamp('2026-10-30 16:00')
        self.assertEqual(fetch().index.max(), pd.Timestamp('2026-10-30'))
        self.assertEqual(load.call_count, 3)

    def test_minute_bars_complete_at_session_offset_not_wall_clock_hour(self):
        load = Mock(return_value=frame(['2026-10-29 09:00', '2026-10-29 10:30']))
        self.clock.return_value = pd.Timestamp('2026-10-29 11:15')
        first = self.cache.candles('tqsdk', 'JM2701', '60', load)
        self.assertEqual(len(first), 1)
        self.clock.return_value = pd.Timestamp('2026-10-29 11:30')
        second = self.cache.candles('tqsdk', 'JM2701', '60', load)
        self.assertEqual(len(second), 2)
        self.assertEqual(load.call_count, 2)

    def test_disconnected_windows_are_not_joined_into_indicator_warmup(self):
        self.clock.return_value = pd.Timestamp('2026-01-15 16:00')
        load = Mock(side_effect=[frame(pd.bdate_range('2026-01-01', '2026-01-15'), complete=False),
                                 frame(pd.bdate_range('2026-10-01', '2026-10-29'), complete=False)])
        self.cache.candles('tqsdk', 'JM2701', 'daily', load)
        self.clock.return_value = pd.Timestamp('2026-10-29 16:00')
        recent = self.cache.candles('tqsdk', 'JM2701', 'daily', load, start_date='2025-08-01',
                                    required_start_date='2026-10-10')
        self.assertEqual(recent.index.min(), pd.Timestamp('2026-10-01'))
        self.assertFalse(recent.attrs['data_info']['history_complete'])
        latest = self.cache.candles('tqsdk', 'JM2701', 'daily', load)
        self.assertEqual(latest.index.min(), pd.Timestamp('2026-10-01'))
        self.assertEqual(load.call_count, 2)

    def test_complete_listing_history_survives_a_later_overlapping_rolling_window(self):
        self.clock.return_value = pd.Timestamp('2026-01-15 16:00')
        load = Mock(side_effect=[frame(pd.bdate_range('2026-01-01', '2026-01-15')),
                                 frame(pd.bdate_range('2026-01-12', '2026-01-20'), complete=False)])
        self.cache.candles('tqsdk', 'JM2701', 'daily', load)
        self.clock.return_value = pd.Timestamp('2026-01-20 16:00')
        result = self.cache.candles('tqsdk', 'JM2701', 'daily', load)
        self.assertTrue(result.attrs['data_info']['history_complete'])
        self.assertEqual(result.index.min(), pd.Timestamp('2026-01-01'))

    def test_bad_data_and_exceptions_do_not_poison_cache(self):
        invalid = frame(['2026-01-02'])
        invalid.loc[:, 'High'] = 1
        for load in [Mock(side_effect=ValueError('offline')), Mock(return_value=invalid), Mock(return_value=None)]:
            with self.assertRaises(ValueError):
                self.candles(load)
        with contextlib.closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM candle_coverage').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM contract_candles').fetchone()[0], 0)

    def test_concurrent_identical_backtests_share_one_download(self):
        load = Mock(return_value=frame(pd.bdate_range('2026-01-01', '2026-05-01')))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.candles(load), range(4)))
        self.assertEqual(load.call_count, 1)
        self.assertEqual(sum(result.attrs['data_info']['cache_status'] == 'hit' for result in results), 3)

    def test_only_explicit_contract_backtests_write_candles(self):
        with patch.object(tq, 'run_worker', return_value={'bars': serial(['2026-01-05']), 'history_complete': True}):
            tq.fetch_tq_data('JM2605', 'daily')
            tq.fetch_tq_data('JM0', 'daily', cache_contract=True)
            tq.fetch_tq_data('JM0', 'daily', data_source='weighted', cache_contract=True)
        with patch.object(data_loader, 'fetch_stock_data', return_value='stock'):
            self.assertEqual(data_loader.fetch_data('sh600000', market_type='stock', cache_contract=True), 'stock')
        with patch.object(tq, 'run_worker', return_value={'price': 100, 'date': '2026-01-05'}):
            tq.fetch_tq_quote('JM2605')
        self.assertFalse(self.path.exists())
        for symbol in ['JM0', 'JM888', 'JM2600', 'JM2613', 'sh600000']:
            self.assertFalse(mc.is_contract(symbol))

    def test_tq_daily_and_weekly_share_cache_and_weekly_filters_after_aggregation(self):
        raw = serial(pd.bdate_range('2026-01-05', '2026-01-16').astype(str))
        with patch.object(tq, 'run_worker', return_value={'bars': raw, 'history_complete': True}) as worker:
            daily = data_loader.fetch_data('JM2605', 'daily', data_provider='tqsdk', cache_contract=True)
            weekly = data_loader.fetch_data('JM2605', 'weekly', start_date='2026-01-07', end_date='2026-01-14',
                                             data_provider='tqsdk', cache_contract=True)
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(daily.attrs['data_info']['cache_status'], 'miss')
        self.assertEqual(weekly.attrs['data_info']['cache_status'], 'hit')
        self.assertEqual(list(weekly.index), [pd.Timestamp('2026-01-09')])
        self.assertEqual(weekly.iloc[0].Volume, 50)
        self.assertEqual(weekly.attrs['data_info']['period'], 'weekly')

    def test_akshare_contract_cache_never_changes_requested_frequency(self):
        with patch.object(data_loader.ak, 'futures_zh_minute_sina', side_effect=ValueError('unavailable')), \
                patch.object(data_loader.ak, 'futures_zh_daily_sina') as daily, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                data_loader.fetch_data('JM2605', '5', cache_contract=True)
            daily.assert_not_called()

    def test_akshare_contract_repeated_backtests_use_local_series(self):
        with patch.object(data_loader, 'fetch_futures_data', return_value=frame(['2026-01-05'])) as vendor:
            first = data_loader.fetch_data('JM2605', 'daily', cache_contract=True)
            second = data_loader.fetch_data('JM2605', 'daily', cache_contract=True)
        self.assertEqual(vendor.call_count, 1)
        self.assertEqual(first.attrs['data_info']['cache_status'], 'miss')
        self.assertEqual(second.attrs['data_info']['cache_status'], 'hit')

    def test_catalog_cache_persists_and_returns_independent_payloads(self):
        load = Mock(return_value={'items': ['JM0']})
        first = self.cache.resource('symbols', load)
        first['items'].append('bad')
        result = mc.MarketCache(self.path).resource('symbols', load)
        self.assertEqual(result, {'items': ['JM0']})
        self.assertEqual(load.call_count, 1)

    def test_catalog_expiry_refresh_and_stale_failure_retry(self):
        load = Mock(side_effect=[{'items': ['old']}, ValueError('offline'), {'items': ['new']}])
        with patch.object(mc.time, 'time', return_value=100):
            self.cache.resource('symbols', load, ttl=10)
        with patch.object(mc.time, 'time', return_value=111):
            self.assertEqual(self.cache.resource('symbols', load), {'items': ['old']})
        with patch.object(mc.time, 'time', return_value=130):
            self.cache.resource('symbols', load)
        self.assertEqual(load.call_count, 2)
        with patch.object(mc.time, 'time', return_value=172):
            self.assertEqual(self.cache.resource('symbols', load), {'items': ['new']})

    def test_failure_without_catalog_is_not_cached_and_fallback_retries(self):
        load = Mock(side_effect=[ValueError('offline'), mc.ResourceValue({'items': ['fallback']}, ttl=60, fallback=True),
                                 {'items': ['real']}])
        with patch.object(mc.time, 'time', return_value=100):
            with self.assertRaises(ValueError):
                self.cache.resource('symbols', load)
            self.cache.resource('symbols', load)
        with patch.object(mc.time, 'time', return_value=161):
            self.assertEqual(self.cache.resource('symbols', load), {'items': ['real']})

    def test_fallback_cannot_replace_last_good_catalog(self):
        self.cache.resource('symbols', lambda: {'items': ['real']}, ttl=-1)
        result = self.cache.resource('symbols', lambda: mc.ResourceValue({'items': ['fallback']}, 60, True))
        self.assertEqual(result, {'items': ['real']})


class CatalogEndpointTests(unittest.TestCase):
    setUp = MarketCacheTests.setUp

    def test_stock_endpoint_caches_complete_response_and_recovers_from_first_failure(self):
        import main
        load = Mock(side_effect=[None, pd.DataFrame([{'code': '600000', 'name': 'Example'}])])
        with patch.object(main, 'get_all_stock_info', load), patch.object(mc.time, 'time', return_value=100):
            fallback = main.get_symbols('stock')
            self.assertGreater(len(fallback['stocks']), 6)
            main.get_symbols('stock')
        self.assertEqual(load.call_count, 1)
        with patch.object(main, 'get_all_stock_info', load), patch.object(mc.time, 'time', return_value=161):
            recovered = main.get_symbols('stock')
            repeated = main.get_symbols('stock')
        self.assertEqual(len(recovered['stocks']), 7)
        self.assertEqual(repeated, recovered)
        self.assertEqual(load.call_count, 2)
        self.assertEqual(recovered['stocks'][-1]['code'], 'sh600000')

    def test_contract_catalog_is_cached_per_product_and_invalid_queries_do_not_load(self):
        import main
        with patch.object(main, 'fetch_tq_contracts', return_value=[{'value': '2605'}]) as load:
            main.get_futures_contracts('JM0')
            main.get_futures_contracts('jm0')
            self.assertEqual(load.call_count, 1)
            main.get_futures_contracts('RB0')
            self.assertEqual(load.call_count, 2)
            with self.assertRaises(main.HTTPException):
                main.get_futures_contracts('JM2605')
            self.assertEqual(load.call_count, 2)

    def test_futures_symbols_have_separate_persistent_cache(self):
        import main
        with patch.object(main, '_build_symbols', wraps=main._build_symbols) as build:
            first = main.get_symbols('futures')
            self.assertEqual(main.get_symbols('futures'), first)
            self.assertEqual(build.call_count, 1)
            self.assertGreater(len(first['futures']), 20)


if __name__ == '__main__':
    unittest.main()
