from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import recent_news as news


NOW = datetime(2026, 10, 27, 7, 0, tzinfo=timezone.utc)


def entry(title='新闻标题 - 测试媒体', published=None, url='https://example.com/news/1', source='测试媒体'):
    date = format_datetime(published or NOW - timedelta(hours=1))
    return f'<item><title>{escape(title)}</title><link>{escape(url)}</link><pubDate>{date}</pubDate><source>{escape(source)}</source></item>'


def feed(*items):
    return ('<rss version="2.0"><channel>' + ''.join(items) + '</channel></rss>').encode('utf-8')


class RecentNewsTests(unittest.TestCase):
    def setUp(self):
        news._cache.clear()

    def tearDown(self):
        news._cache.clear()

    def test_exact_72_hour_window_excludes_future_and_expired(self):
        body = feed(entry(url='https://example.com/boundary', published=NOW - timedelta(hours=72)),
                    entry(url='https://example.com/expired', published=NOW - timedelta(hours=72, seconds=1)),
                    entry(url='https://example.com/future', published=NOW + timedelta(seconds=1)))
        items = news.parse_feed(body, NOW)
        self.assertEqual([item['url'] for item in items], ['https://example.com/boundary'])

    def test_sort_deduplicate_and_preserve_media_attribution(self):
        body = feed(entry(title='较早新闻 - 测试媒体', url='https://example.com/old', published=NOW - timedelta(hours=2)),
                    entry(), entry(url='https://example.com/duplicate-title'),
                    entry(title='不同标题', url='https://example.com/news/1#fragment'))
        items = news.parse_feed(body, NOW)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['title'], '新闻标题')
        self.assertEqual(items[0]['source'], '测试媒体')
        self.assertEqual(items[1]['title'], '较早新闻')
        json.dumps(items, ensure_ascii=False, allow_nan=False)

    def test_timezone_offsets_represent_the_same_instant(self):
        offset_date = NOW.astimezone(timezone(timedelta(hours=8))) - timedelta(hours=1)
        item = news.parse_feed(feed(entry(published=offset_date)), NOW)[0]
        self.assertEqual(datetime.fromisoformat(item['published_at']), NOW - timedelta(hours=1))

    def test_unusable_dates_links_and_titles_are_skipped(self):
        invalid_date = entry().replace('<pubDate>', '<pubDate>invalid ')
        body = feed(invalid_date, entry(url='javascript:alert(1)'), entry(url='https://user:secret@example.com'),
                    entry(title=''), entry(title='&lt;b&gt;正常标题&lt;/b&gt;'))
        items = news.parse_feed(body, NOW)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], '正常标题')

    def test_html_error_and_entity_declarations_are_rejected(self):
        for body in (b'<html>Blocked</html>', b'<!DOCTYPE rss><rss><channel /></rss>', b'<rss>broken'):
            with self.assertRaises(Exception):
                news.parse_feed(body, NOW)

    def test_item_count_is_bounded(self):
        body = feed(*(entry(title=f'消息{i}', url=f'https://example.com/{i}') for i in range(130)))
        self.assertEqual(len(news.parse_feed(body, NOW)), 100)

    def test_fresh_cache_is_reused_and_force_refresh_fetches(self):
        with patch.object(news, 'fetch_feed', return_value=feed(entry())) as fetch, patch.object(news, 'utc_now', return_value=NOW):
            first = news.category_news(news.CATEGORIES[0], NOW)
            second = news.category_news(news.CATEGORIES[0], NOW + timedelta(seconds=10))
            third = news.category_news(news.CATEGORIES[0], NOW + timedelta(seconds=20), refresh=True)
        self.assertFalse(first['cached'])
        self.assertTrue(second['cached'])
        self.assertFalse(third['cached'])
        self.assertEqual(fetch.call_count, 2)

    def test_expired_cache_is_fetched_again(self):
        news._cache[('google', 'oil')] = {'items': [], 'fetched_at': NOW - timedelta(seconds=300)}
        with patch.object(news, 'fetch_feed', return_value=feed(entry())) as fetch:
            result = news.category_news(news.CATEGORIES[2], NOW)
        fetch.assert_called_once()
        self.assertEqual(result['status'], 'success')

    def test_failed_refresh_preserves_fetch_time_and_only_unexpired_items(self):
        old_time = NOW - timedelta(hours=2)
        cached = news.parse_feed(feed(entry(published=NOW - timedelta(hours=73)),
                                      entry(title='仍有效', url='https://example.com/current', published=NOW - timedelta(hours=3))), old_time)
        news._cache[('google', 'oil')] = {'items': cached, 'fetched_at': old_time}
        with patch.object(news, 'fetch_feed', side_effect=TimeoutError):
            result = news.category_news(news.CATEGORIES[2], NOW, refresh=True)
        self.assertEqual(result['status'], 'stale')
        self.assertEqual(result['fetched_at'], old_time.isoformat())
        self.assertEqual([item['title'] for item in result['items']], ['仍有效'])

    def test_category_failure_does_not_discard_other_categories(self):
        def fetch(query):
            if query == news.CATEGORIES[1][2]:
                raise TimeoutError('private diagnostic')
            return feed(entry())
        with patch.object(news, 'fetch_feed', side_effect=fetch), patch.object(news, 'utc_now', return_value=NOW):
            result = news.get_recent_news(provider='google')
        self.assertEqual([item['status'] for item in result['categories']], ['success', 'error', 'success'])
        self.assertEqual([item['name'] for item in result['categories']], ['中东', '美国', '原油'])
        self.assertNotIn('private diagnostic', json.dumps(result))

    def test_cache_hit_refilters_rolling_window(self):
        cached_time = NOW - timedelta(seconds=100)
        items = news.parse_feed(feed(entry(published=NOW - timedelta(hours=72, seconds=50))), cached_time)
        news._cache[('google', 'oil')] = {'items': items, 'fetched_at': cached_time}
        with patch.object(news, 'fetch_feed') as fetch:
            result = news.category_news(news.CATEGORIES[2], NOW)
        fetch.assert_not_called()
        self.assertEqual(result['items'], [])
        self.assertEqual(result['status'], 'empty')
