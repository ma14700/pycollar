from datetime import timedelta
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import market_quotes as oil
from core.jin10_mcp import MCPBusinessError
from test_recent_news import NOW


def quote(code, close='101.427'):
    return {'status': 200, 'data': {'code': code, 'name': code, 'time': (NOW - timedelta(seconds=10)).isoformat(),
        'close': close, 'open': '100.552', 'high': '101.621', 'low': '99.833', 'volume': 40665,
        'ups_price': '0.870', 'ups_percent': '0.865'}}


class OilQuoteTests(unittest.TestCase):
    def setUp(self):
        oil._cache.clear()
        identity = patch.object(oil, 'credential_identity', return_value='test-identity')
        identity.start()
        self.addCleanup(identity.stop)
        clock = patch.object(oil, 'utc_now', return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def tearDown(self):
        oil._cache.clear()

    def client(self, codes=('UKOIL', 'USOIL', 'XAGUSD')):
        client = MagicMock()
        client.initialize.return_value = client
        client.read_resource.return_value = {'contents': [{'mimeType': 'application/json',
            'text': json.dumps({'data': [{'code': code} for code in codes]})}]}
        client.call_tool.side_effect = lambda name, arguments: quote(arguments['code'], {'UKOIL': '111.22', 'USOIL': '101.427', 'XAGUSD': '52.813'}[arguments['code']])
        return client

    def test_codes_are_confirmed_before_quotes_and_use_only_declared_arguments(self):
        client = self.client()
        with patch.object(oil, 'Jin10MCPClient', return_value=client):
            result = oil.get_market_quotes()
        methods = [call[0] for call in client.method_calls]
        self.assertLess(methods.index('read_resource'), methods.index('call_tool'))
        self.assertEqual(client.read_resource.call_args.args, ('quote://codes',))
        self.assertEqual([call.args for call in client.call_tool.call_args_list],
                         [('get_quote', {'code': 'UKOIL'}), ('get_quote', {'code': 'USOIL'}), ('get_quote', {'code': 'XAGUSD'})])
        self.assertEqual([item['code'] for item in result['quotes']], ['UKOIL', 'USOIL', 'XAGUSD'])

    def test_precision_and_provider_percentage_are_preserved(self):
        client = self.client()
        with patch.object(oil, 'Jin10MCPClient', return_value=client):
            brent, wti, silver = oil.get_market_quotes()['quotes']
        self.assertEqual(brent['close'], 111.22)
        self.assertEqual(brent['precision'], 2)
        self.assertEqual(wti['close'], 101.427)
        self.assertEqual(wti['precision'], 3)
        self.assertEqual(wti['ups_percent'], 0.865)
        self.assertEqual(wti['ups_price'], 0.870)
        self.assertEqual(silver['close'], 52.813)
        self.assertEqual(silver['precision'], 3)
        self.assertEqual(silver['unit'], '美元/盎司')
        self.assertEqual(brent['unit'], '美元/桶')

    def test_fresh_pair_cache_avoids_tool_calls_and_manual_refresh_bypasses(self):
        client = self.client()
        with patch.object(oil, 'Jin10MCPClient', return_value=client) as create:
            oil.get_market_quotes()
            second = oil.get_market_quotes()
            self.assertTrue(all(item['cached'] for item in second['quotes']))
            self.assertEqual(create.call_count, 1)
            oil.get_market_quotes(refresh=True)
        self.assertEqual(client.call_tool.call_count, 6)

    def test_missing_resource_code_is_not_requested(self):
        client = self.client(codes=('UKOIL',))
        with patch.object(oil, 'Jin10MCPClient', return_value=client):
            brent, wti, silver = oil.get_market_quotes()['quotes']
        self.assertEqual(brent['status'], 'success')
        self.assertEqual(wti['status'], 'error')
        self.assertEqual(silver['status'], 'error')
        self.assertEqual(client.call_tool.call_count, 1)

    def test_one_instrument_error_does_not_discard_other_quote(self):
        client = self.client()
        client.call_tool.side_effect = [MCPBusinessError('布伦特暂不可用'), quote('USOIL'), quote('XAGUSD', '52.813')]
        with patch.object(oil, 'Jin10MCPClient', return_value=client):
            brent, wti, silver = oil.get_market_quotes()['quotes']
        self.assertEqual(brent['status'], 'error')
        self.assertEqual(wti['status'], 'success')
        self.assertEqual(silver['status'], 'success')

    def test_failed_refresh_is_stale_and_retains_original_quote_and_fetch_times(self):
        client = self.client()
        with patch.object(oil, 'Jin10MCPClient', return_value=client):
            first = oil.get_market_quotes()
            client.call_tool.side_effect = MCPBusinessError('今日该工具调用次数已达上限，请明日再试')
            with patch.object(oil, 'utc_now', return_value=NOW + timedelta(minutes=20)):
                later = oil.get_market_quotes(refresh=True)
        for before, after in zip(first['quotes'], later['quotes']):
            self.assertEqual(after['status'], 'stale')
            self.assertEqual(after['fetched_at'], before['fetched_at'])
            self.assertEqual(after['time'], before['time'])
            self.assertTrue(after['delayed'])
            self.assertIn('今日该工具', after['error'])

    def test_token_change_does_not_show_previous_tokens_quotes(self):
        client = self.client()
        with patch.object(oil, 'Jin10MCPClient', return_value=client):
            oil.get_market_quotes()
            client.initialize.side_effect = MCPBusinessError('Token 无效')
            with patch.object(oil, 'credential_identity', return_value='other-token'):
                result = oil.get_market_quotes()
        self.assertTrue(all(item['status'] == 'error' and item['close'] is None for item in result['quotes']))

    def test_wrong_code_nonfinite_and_missing_price_are_rejected(self):
        for data in [quote('WRONG')['data'], {**quote('UKOIL')['data'], 'close': None},
                     {**quote('UKOIL')['data'], 'close': 'NaN'}, {**quote('UKOIL')['data'], 'close': '0'}]:
            with self.assertRaises(ValueError):
                oil.normalize_quote(data, 'UKOIL', '布伦特原油')

    def test_optional_fields_stay_missing_instead_of_turning_into_zero(self):
        data = {'code': 'UKOIL', 'close': '111.22', 'time': NOW.isoformat()}
        normalized = oil.normalize_quote(data, 'UKOIL', '布伦特原油')
        self.assertIsNone(normalized['open'])
        self.assertIsNone(normalized['ups_percent'])

    def test_silver_negative_changes_keep_sign_and_percent_scale(self):
        data = {**quote('XAGUSD', '52.813')['data'], 'ups_price': '-1.152', 'ups_percent': '-2.135'}
        result = oil.normalize_quote(data, 'XAGUSD', '现货白银')
        self.assertEqual(result['unit'], '美元/盎司')
        self.assertEqual(result['ups_price'], -1.152)
        self.assertEqual(result['ups_percent'], -2.135)
