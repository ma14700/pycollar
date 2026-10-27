from datetime import timedelta
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import recent_news as news, news_jin10 as jin10
from test_recent_news import NOW, entry, feed


def row(content='美国原油库存下降', ago=1, identifier='20261027120000123456', **overrides):
    result = {'id': identifier, 'time': (NOW - timedelta(hours=ago)).astimezone(jin10.CHINA_TZ).strftime('%Y-%m-%d %H:%M:%S'),
              'data': {'content': content}, 'extras': {'ad': False}, 'type': 0}
    result.update(overrides)
    return result


def snapshot(items=None, warning=None, coverage=None):
    groups = {key: [] for key, _, _ in news.CATEGORIES}
    for raw in items or []:
        item, _, _ = jin10.parse_row(raw)
        groups['usa'].append(item)
    return {'groups': groups, 'warning': warning, 'coverage_start': (coverage or NOW - timedelta(hours=72)).isoformat(), 'pages': 1}


class Jin10NewsTests(unittest.TestCase):
    def setUp(self):
        news._cache.clear()
        token_patch = patch('core.jin10_mcp.token', return_value='')
        token_patch.start()
        self.addCleanup(token_patch.stop)

    def tearDown(self):
        news._cache.clear()

    def test_parse_public_content_and_keep_attribution_and_beijing_time(self):
        item, published, searchable = jin10.parse_row(row('<b>美国原油</b> 库存下降'))
        self.assertEqual(item['title'], '美国原油 库存下降')
        self.assertEqual(item['source'], '金十快讯')
        self.assertEqual(published, NOW - timedelta(hours=1))
        self.assertTrue(item['url'].startswith('https://flash.jin10.com/detail/'))
        self.assertIn('库存下降', searchable)

    def test_ads_locked_content_and_malformed_rows_are_skipped(self):
        for raw in [None, {}, row(identifier='javascript:alert(1)'), row(data={'vip_level': 1, 'title': '会员专享'}),
                    row(extras={'ad': True}), row(data=None), row(data={'actual': '3.0'})]:
            self.assertIsNone(jin10.parse_row(raw))

    def test_public_pagination_uses_last_returned_time_and_exact_cutoff(self):
        pages = [[row(ago=1), row('伊朗消息', ago=2)],
                 [row('伊朗消息', ago=2), row('美国较早原油消息', ago=72, identifier='20261024150000123456'), row(ago=73)]]
        with patch.object(jin10, 'fetch_page', side_effect=pages) as fetch:
            result = jin10.fetch_jin10_news(NOW)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args_list[1].args[0], '2026-10-27 13:00:00')
        self.assertEqual(len(result['groups']['usa']), 2)
        self.assertEqual(len(result['groups']['middle_east']), 1)
        self.assertIsNone(result['warning'])

    def test_history_error_returns_partial_data_with_notice(self):
        with patch.object(jin10, 'fetch_page', side_effect=[[row()], ValueError('member history unavailable')]):
            result = jin10.fetch_jin10_news(NOW)
        self.assertEqual(len(result['groups']['usa']), 1)
        self.assertIn('历史', result['warning'])

    def test_repeated_cursor_is_bounded_and_deduplicated(self):
        with patch.object(jin10, 'fetch_page', return_value=[row()]) as fetch:
            result = jin10.fetch_jin10_news(NOW)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(len(result['groups']['oil']), 1)
        self.assertIsNotNone(result['warning'])

    def test_empty_initial_timeline_is_marked_incomplete(self):
        with patch.object(jin10, 'fetch_page', return_value=[]):
            result = jin10.fetch_jin10_news(NOW)
        self.assertIsNotNone(result['warning'])

    def test_public_endpoint_never_requests_member_history(self):
        response = io.BytesIO(json.dumps({'status': 200, 'data': []}).encode())
        with patch.object(jin10, 'urlopen', return_value=response) as fetch:
            self.assertEqual(jin10.fetch_page('2026-10-27 13:00:00'), [])
        request = fetch.call_args.args[0]
        self.assertEqual(urlsplit(request.full_url).path, '/get_flash_list')
        params = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(params['vip'], ['0'])
        self.assertNotIn('date', params)

    def test_jin10_only_does_not_request_eastmoney(self):
        with patch.object(jin10, 'fetch_jin10_news', return_value=snapshot([row()])), \
             patch('core.news_domestic.fetch_domestic_news') as em, patch.object(news, 'utc_now', return_value=NOW):
            result = news.get_recent_news(provider='jin10')
        em.assert_not_called()
        self.assertEqual(result['provider'], 'jin10')

    def test_domestic_prefers_jin10_and_supplements_only_older_history(self):
        primary = snapshot([row()], warning='公开历史未取全', coverage=NOW - timedelta(hours=2))
        older = dict(jin10.parse_row(row('美国较早消息', ago=4, identifier='20261027100000123456'))[0], source='东方财富快讯', url='https://finance.eastmoney.com/a/202610271234567890.html')
        newer = {**older, 'title': '国内较新消息', 'url': older['url'] + '?new', 'published_at': (NOW - timedelta(minutes=10)).isoformat()}
        backup = snapshot()
        backup['groups']['usa'] = [newer, older]
        with patch.object(jin10, 'fetch_jin10_news', return_value=primary), \
             patch('core.news_domestic.fetch_domestic_news', return_value=backup), patch.object(news, 'utc_now', return_value=NOW):
            result = news.get_recent_news(provider='domestic')
        group = result['categories'][1]
        self.assertEqual([item['source'] for item in group['items']], ['金十快讯', '东方财富快讯'])
        self.assertEqual(group['provider_id'], 'domestic_mixed')
        self.assertIsNone(group['warning'])
        self.assertIsNotNone(group['supplement_fetched_at'])

    def test_domestic_falls_back_to_eastmoney_when_jin10_fails(self):
        backup = snapshot([row()])
        backup['groups']['usa'][0]['source'] = '东方财富快讯'
        with patch.object(jin10, 'fetch_jin10_news', side_effect=TimeoutError), \
             patch('core.news_domestic.fetch_domestic_news', return_value=backup), patch.object(news, 'utc_now', return_value=NOW):
            result = news.get_recent_news(provider='domestic')
        self.assertEqual(result['provider'], 'eastmoney')

    def test_auto_keeps_google_first_then_uses_jin10(self):
        with patch.object(news, 'fetch_feed', return_value=feed(entry())), \
             patch.object(jin10, 'fetch_jin10_news') as cn, patch.object(news, 'utc_now', return_value=NOW):
            first = news.get_recent_news()
        cn.assert_not_called()
        self.assertEqual(first['provider'], 'google')
        with patch.object(news, 'fetch_feed', side_effect=TimeoutError), \
             patch.object(jin10, 'fetch_jin10_news', return_value=snapshot([row()])), \
             patch('core.news_domestic.fetch_domestic_news') as em, patch.object(news, 'utc_now', return_value=NOW):
            second = news.get_recent_news(refresh=True)
        em.assert_not_called()
        self.assertEqual(second['provider'], 'jin10')

    def test_jin10_cache_is_independent_from_eastmoney(self):
        with patch.object(jin10, 'fetch_jin10_news', return_value=snapshot([row()])) as fetch, \
             patch.object(news, 'utc_now', return_value=NOW):
            news.get_recent_news(provider='jin10')
            cached = news.get_recent_news(provider='jin10')
        fetch.assert_called_once()
        self.assertTrue(all(group['cached'] for group in cached['categories']))
        self.assertNotIn('eastmoney', news._cache)
