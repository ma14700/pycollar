from datetime import timedelta
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import recent_news as news, news_domestic as domestic
from test_recent_news import NOW, entry, feed


def row(title='美国原油库存下降', ago=1, code='202610271234567890', summary=''):
    return {'title': title, 'summary': summary, 'code': code,
            'showTime': (NOW - timedelta(hours=ago)).astimezone(domestic.CHINA_TZ).strftime('%Y-%m-%d %H:%M:%S')}


def page(*rows, cursor='next'):
    return {'fastNewsList': list(rows), 'sortEnd': cursor}


class DomesticNewsTests(unittest.TestCase):
    def setUp(self):
        news._cache.clear()
        jin10_patch = patch('core.news_jin10.fetch_jin10_news', side_effect=TimeoutError)
        self.jin10 = jin10_patch.start()
        self.addCleanup(jin10_patch.stop)

    def tearDown(self):
        news._cache.clear()

    def test_classifies_title_and_summary_with_beijing_timezone(self):
        rows = [row('地区局势', summary='伊朗与以色列就霍尔木兹问题对话'),
                row('美联储政策', code='202610271234567891'),
                row('布伦特价格走高', code='202610271234567892'), row(ago=73)]
        with patch.object(domestic, 'fetch_page', return_value=page(*rows)) as fetch:
            result = domestic.fetch_domestic_news(NOW)
        self.assertIsNone(result['warning'])
        self.assertEqual(len(result['groups']['middle_east']), 1)
        self.assertEqual(len(result['groups']['usa']), 1)
        self.assertEqual(len(result['groups']['oil']), 2)
        item = result['groups']['usa'][0]
        self.assertEqual(item['published_at'], (NOW - timedelta(hours=1)).isoformat())
        self.assertTrue(item['url'].startswith('https://finance.eastmoney.com/a/'))
        fetch.assert_called_once()

    def test_paginates_until_cutoff_and_filters_future(self):
        pages = [page(row(ago=-1), row(ago=2)), page(row('伊朗消息', ago=72), row(ago=73), cursor='older')]
        with patch.object(domestic, 'fetch_page', side_effect=pages) as fetch:
            result = domestic.fetch_domestic_news(NOW)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args_list[1].args[0], 'next')
        self.assertEqual(len(result['groups']['usa']), 1)
        self.assertEqual(len(result['groups']['middle_east']), 1)

    def test_repeated_cursor_stops_and_warns(self):
        with patch.object(domestic, 'fetch_page', return_value=page(row())) as fetch:
            result = domestic.fetch_domestic_news(NOW)
        self.assertEqual(fetch.call_count, 2)
        self.assertIsNotNone(result['warning'])
        self.assertEqual(len(result['groups']['oil']), 1)

    def test_mid_pagination_failure_keeps_partial_data_with_warning(self):
        with patch.object(domestic, 'fetch_page', side_effect=[page(row()), TimeoutError]):
            result = domestic.fetch_domestic_news(NOW)
        self.assertEqual(len(result['groups']['oil']), 1)
        self.assertIn('中断', result['warning'])

    def test_initial_failure_is_not_reported_as_empty_success(self):
        with patch.object(domestic, 'fetch_page', side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                domestic.fetch_domestic_news(NOW)

    def test_page_limit_returns_warning(self):
        with patch.object(domestic, 'fetch_page', return_value=page(row())), patch.object(domestic, 'MAX_PAGES', 1):
            result = domestic.fetch_domestic_news(NOW)
        self.assertIn('分页上限', result['warning'])

    def test_invalid_rows_do_not_produce_links(self):
        self.assertIsNone(domestic.parse_row(row(code='https://evil.example')))
        self.assertIsNone(domestic.parse_row({'showTime': 'bad date', 'code': '202610271234567890'}))
        self.assertIsNone(domestic.parse_row(None))
        self.assertEqual(domestic.parse_row(row(title='', summary='【伊朗消息】最新公开快讯'))[0]['title'], '【伊朗消息】最新公开快讯')

    def test_domestic_cache_is_separate_and_fetches_once_for_three_categories(self):
        with patch.object(domestic, 'fetch_page', return_value=page(row(), row(ago=73))) as fetch, \
             patch.object(news, 'fetch_feed', side_effect=AssertionError('Domestic mode must not call Google')), \
             patch.object(news, 'utc_now', return_value=NOW):
            first = news.get_recent_news(provider='eastmoney')
            second = news.get_recent_news(provider='eastmoney')
            news.get_recent_news(provider='eastmoney', refresh=True)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(first['provider'], 'eastmoney')
        self.assertTrue(all(item['cached'] for item in second['categories']))
        self.assertTrue(all(item['provider_id'] == 'eastmoney' for item in first['categories']))

    def test_switching_provider_does_not_reuse_other_source_items(self):
        with patch.object(domestic, 'fetch_page', return_value=page(row(), row(ago=73))), \
             patch.object(news, 'fetch_feed', return_value=feed(entry())), patch.object(news, 'utc_now', return_value=NOW):
            cn = news.get_recent_news(provider='eastmoney')
            google = news.get_recent_news(provider='google')
            cn_again = news.get_recent_news(provider='eastmoney')
        self.assertEqual(cn['categories'][1]['items'][0]['source'], '东方财富快讯')
        self.assertEqual(google['categories'][1]['items'][0]['source'], '测试媒体')
        self.assertEqual(cn_again['categories'][1]['items'], cn['categories'][1]['items'])

    def test_auto_uses_google_without_contacting_domestic(self):
        with patch.object(domestic, 'fetch_page') as cn, \
             patch.object(news, 'fetch_feed', return_value=feed(entry())) as google, patch.object(news, 'utc_now', return_value=NOW):
            result = news.get_recent_news()
        cn.assert_not_called()
        self.assertEqual(google.call_count, 3)
        self.assertEqual(result['requested_provider'], 'auto')
        self.assertEqual(result['provider'], 'google')

    def test_auto_falls_back_when_google_fails(self):
        with patch.object(domestic, 'fetch_page', return_value=page(row(), row(ago=73))), \
             patch.object(news, 'fetch_feed', side_effect=TimeoutError), patch.object(news, 'utc_now', return_value=NOW):
            result = news.get_recent_news()
        self.assertEqual(result['provider'], 'eastmoney')
        self.assertIsNotNone(result['fallback_reason'])
        self.assertTrue(all(category['status'] in ('success', 'empty') for category in result['categories']))

    def test_auto_only_replaces_failed_google_category(self):
        def fetch(query):
            if query == news.CATEGORIES[1][2]:
                raise TimeoutError
            return feed(entry())
        with patch.object(domestic, 'fetch_page', return_value=page(row(), row(ago=73))), \
             patch.object(news, 'fetch_feed', side_effect=fetch), patch.object(news, 'utc_now', return_value=NOW):
            result = news.get_recent_news()
        self.assertEqual(result['provider'], 'mixed')
        self.assertEqual([item['provider_id'] for item in result['categories']], ['google', 'eastmoney', 'google'])

    def test_auto_retains_valid_google_cache_when_both_sources_fail(self):
        old_time = NOW - timedelta(minutes=10)
        news._cache[('google', 'usa')] = {'items': news.parse_feed(feed(entry()), NOW), 'fetched_at': old_time}
        with patch.object(domestic, 'fetch_page', side_effect=TimeoutError), \
             patch.object(news, 'fetch_feed', side_effect=TimeoutError), patch.object(news, 'utc_now', return_value=NOW):
            result = news.get_recent_news(refresh=True)
        self.assertEqual(result['categories'][1]['status'], 'stale')
        self.assertEqual(result['categories'][1]['fetched_at'], old_time.isoformat())

    def test_domestic_failure_preserves_old_timestamp_and_filters_expired_cache(self):
        with patch.object(domestic, 'fetch_page', return_value=page(row(ago=71), row(ago=73))), \
             patch.object(news, 'utc_now', return_value=NOW):
            news.get_recent_news(provider='eastmoney')
        with patch.object(domestic, 'fetch_page', side_effect=TimeoutError), \
             patch.object(news, 'utc_now', return_value=NOW + timedelta(minutes=10)):
            stale = news.get_recent_news(provider='eastmoney', refresh=True)
        category = stale['categories'][1]
        self.assertEqual(category['status'], 'stale')
        self.assertEqual(category['fetched_at'], NOW.isoformat())
        with patch.object(domestic, 'fetch_page', side_effect=TimeoutError), \
             patch.object(news, 'utc_now', return_value=NOW + timedelta(hours=2)):
            expired = news.get_recent_news(provider='eastmoney', refresh=True)
        self.assertEqual(expired['categories'][1]['status'], 'error')
        self.assertEqual(expired['categories'][1]['items'], [])
