from datetime import timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import news_jin10_mcp as adapter, jin10_mcp, news_jin10
from test_recent_news import NOW


def item(title='美国原油消息', ago=1, identifier='1'):
    return {'title': title, 'content': title, 'time': (NOW - timedelta(hours=ago)).isoformat(),
            'url': 'https://flash.jin10.com/detail/' + identifier}


def page(items, next_cursor=None, has_more=False):
    return {'status': 200, 'data': {'items': items, 'next_cursor': next_cursor, 'has_more': has_more}}


class MCPNewsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        store_patch = patch.object(adapter, 'STORE_PATH', Path(self.directory.name) / 'news.json')
        store_patch.start()
        self.addCleanup(store_patch.stop)
        identity_patch = patch.object(adapter, 'credential_identity', return_value='test-identity')
        identity_patch.start()
        self.addCleanup(identity_patch.stop)

    def client(self, responses):
        client = MagicMock()
        client.tools = {'list_flash': {}}
        client.initialize.return_value = client
        client.call_tool.side_effect = responses
        return client

    def test_cursor_pagination_and_exact_72_hours(self):
        client = self.client([page([item()], 'cursor-2', True),
                              page([item('美国较早原油消息', 72, '2'), item('过期', 73, '3')])])
        with patch.object(adapter, 'Jin10MCPClient', return_value=client):
            result = adapter.fetch_mcp_news(NOW)
        self.assertTrue(result['history_complete'])
        self.assertIsNone(result['warning'])
        self.assertEqual(len(result['groups']['usa']), 2)
        self.assertEqual(client.call_tool.call_args_list[1].args, ('list_flash', {'cursor': 'cursor-2'}))
        self.assertNotIn('_searchable', result['groups']['usa'][0])

    def test_next_refresh_resumes_history_then_switches_to_incremental(self):
        client = self.client([page([item()], 'older', True)])
        with patch.object(adapter, 'Jin10MCPClient', return_value=client), patch.object(adapter, 'MAX_PAGES', 1):
            partial = adapter.fetch_mcp_news(NOW)
        self.assertFalse(partial['history_complete'])
        resumed = self.client([page([item()], 'recent-page-2', True), page([item('较早原油消息', 72, '2')])])
        with patch.object(adapter, 'Jin10MCPClient', return_value=resumed):
            complete = adapter.fetch_mcp_news(NOW)
        self.assertEqual(resumed.call_tool.call_args_list[1].args, ('list_flash', {'cursor': 'older'}))
        self.assertTrue(complete['history_complete'])
        head = self.client([page([item()], 'recent-page-2', True)])
        with patch.object(adapter, 'Jin10MCPClient', return_value=head):
            adapter.fetch_mcp_news(NOW)
        self.assertEqual(head.call_tool.call_count, 1)

    def test_missing_or_repeated_cursor_is_a_partial_warning(self):
        client = self.client([page([item()], None, True)])
        with patch.object(adapter, 'Jin10MCPClient', return_value=client):
            result = adapter.fetch_mcp_news(NOW)
        self.assertIn('next_cursor', result['warning'])
        self.assertFalse(result['history_complete'])

    def test_quota_error_is_not_retried_or_falsely_successful(self):
        client = self.client([jin10_mcp.MCPBusinessError('今日该工具调用次数已达上限，请明日再试')])
        with patch.object(adapter, 'Jin10MCPClient', return_value=client):
            with self.assertRaisesRegex(jin10_mcp.MCPBusinessError, '今日该工具'):
                adapter.fetch_mcp_news(NOW)
        self.assertEqual(client.call_tool.call_count, 1)

    def test_failed_refresh_keeps_persistent_data_and_original_fetch_time(self):
        client = self.client([page([item(), item('原油旧消息', 72, '2')])])
        with patch.object(adapter, 'Jin10MCPClient', return_value=client):
            first = adapter.fetch_mcp_news(NOW)
        failed = self.client([jin10_mcp.MCPProtocolError('network unavailable')])
        with patch.object(adapter, 'Jin10MCPClient', return_value=failed):
            second = adapter.fetch_mcp_news(NOW + timedelta(minutes=5))
        self.assertTrue(second['stale'])
        self.assertEqual(second['fetched_at'], first['fetched_at'])
        self.assertEqual(len(second['groups']['oil']), 1)

    def test_parses_iso_and_beijing_local_dates_and_rejects_bad_links(self):
        raw = item()
        raw['time'] = '2026-10-27 14:00:00'
        self.assertEqual(adapter.parse_item(raw)['published_at'], (NOW - timedelta(hours=1)).isoformat())
        raw['url'] = 'javascript:alert(1)'
        self.assertIsNone(adapter.parse_item(raw))

    def test_configured_token_routes_only_through_mcp(self):
        with patch.object(jin10_mcp, 'token', return_value='test-credential'), \
             patch.object(adapter, 'fetch_mcp_news', return_value={'transport': 'mcp'}) as fetch, \
             patch.object(news_jin10, 'fetch_public_jin10_news') as public:
            self.assertEqual(news_jin10.fetch_jin10_news(NOW)['transport'], 'mcp')
        fetch.assert_called_once()
        public.assert_not_called()

    def test_long_offline_gap_does_not_falsely_preserve_full_history(self):
        initial = self.client([page([item(), item('原油旧消息', 72, '2')])])
        with patch.object(adapter, 'Jin10MCPClient', return_value=initial):
            self.assertTrue(adapter.fetch_mcp_news(NOW)['history_complete'])
        shifted = item('美国最新消息', identifier='new')
        shifted['time'] = (NOW + timedelta(hours=49)).isoformat()
        current = self.client([page([shifted])])
        with patch.object(adapter, 'Jin10MCPClient', return_value=current):
            result = adapter.fetch_mcp_news(NOW + timedelta(hours=50))
        self.assertFalse(result['history_complete'])
        self.assertIsNotNone(result['warning'])

    def test_business_error_reaches_news_page_without_secret(self):
        from core import recent_news, news_jin10
        recent_news._cache.clear()
        try:
            with patch.object(news_jin10, 'fetch_jin10_news', side_effect=jin10_mcp.MCPBusinessError('今日该工具调用次数已达上限，请明日再试')):
                result = recent_news.get_recent_news(provider='jin10', refresh=True)
            self.assertEqual(result['categories'][0]['status'], 'error')
            self.assertIn('今日该工具', result['categories'][0]['error'])
        finally:
            recent_news._cache.clear()
