import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import jin10_mcp as mcp


class Response(io.BytesIO):
    def __init__(self, payload=None, sse=False, session=None, raw=None):
        body = raw if raw is not None else json.dumps(payload).encode()
        if sse and raw is None:
            body = b': heartbeat\n\nevent: message\ndata: ' + body + b'\n\n'
        super().__init__(body)
        self.headers = {'Content-Type': 'text/event-stream' if sse else 'application/json'}
        if session:
            self.headers['Mcp-Session-Id'] = session


def rpc(identifier, result):
    return {'jsonrpc': '2.0', 'id': identifier, 'result': result}


TOOLS = [{'name': 'list_flash', 'inputSchema': {'type': 'object', 'properties': {'cursor': {'type': 'string'}}}},
         {'name': 'get_quote', 'inputSchema': {'properties': {'code': {'type': 'string'}}, 'required': ['code']}}]


class MCPClientTests(unittest.TestCase):
    def client(self):
        client = mcp.Jin10MCPClient(credential='test-credential')
        client.tools = {tool['name']: tool for tool in TOOLS}
        return client

    def test_handshake_notification_discovery_and_bearer_session_headers(self):
        client = self.client()
        replies = [Response(rpc(1, {'protocolVersion': '2025-11-25', 'capabilities': {'tools': {}, 'resources': {}}}), sse=True, session='session-1'),
                   Response(raw=b''), Response(rpc(2, {'tools': TOOLS})),
                   Response(rpc(3, {'resources': [{'uri': 'quote://codes'}]}), sse=True)]
        with patch.object(client.opener, 'open', side_effect=replies) as send:
            client.initialize()
        requests = [json.loads(call.args[0].data) for call in send.call_args_list]
        self.assertEqual([request['method'] for request in requests],
                         ['initialize', 'notifications/initialized', 'tools/list', 'resources/list'])
        self.assertNotIn('id', requests[1])
        self.assertEqual(requests[0]['params']['protocolVersion'], '2025-11-25')
        headers = {key.lower(): value for key, value in send.call_args_list[2].args[0].header_items()}
        self.assertEqual(headers['authorization'], 'Bearer test-credential')
        self.assertEqual(headers['mcp-session-id'], 'session-1')
        self.assertEqual(headers['mcp-protocol-version'], '2025-11-25')
        self.assertEqual(client.resources[0]['uri'], 'quote://codes')

    def test_tool_prefers_structured_content_over_conflicting_text(self):
        client = self.client()
        structured = {'status': 200, 'data': {'items': [], 'has_more': False, 'next_cursor': None}}
        result = {'structuredContent': structured, 'content': [{'type': 'text', 'text': '{invalid machine data'}]}
        with patch.object(client.opener, 'open', return_value=Response(rpc(1, result), sse=True)), \
             patch.object(mcp, 'reserve_tool_call'):
            self.assertEqual(client.call_tool('list_flash', {'cursor': 'next'}), structured)

    def test_text_only_is_never_silently_used_as_machine_json(self):
        client = self.client()
        with patch.object(client, '_request', return_value={'content': [{'type': 'text', 'text': '{"data":{}}'}]}), \
             patch.object(mcp, 'reserve_tool_call'):
            with self.assertRaises(mcp.MCPProtocolError):
                client.call_tool('list_flash')

    def test_business_quota_error_and_rpc_error_remain_distinct(self):
        client = self.client()
        result = {'isError': True, 'structuredContent': {'message': '今日该工具调用次数已达上限，请明日再试'}}
        with patch.object(client, '_request', return_value=result), patch.object(mcp, 'reserve_tool_call'):
            with self.assertRaisesRegex(mcp.MCPBusinessError, '今日该工具'):
                client.call_tool('list_flash')
        with patch.object(client.opener, 'open', return_value=Response({'jsonrpc': '2.0', 'id': 1, 'error': {'code': -32602, 'message': 'bad parameter'}})):
            with self.assertRaisesRegex(mcp.MCPProtocolError, 'bad parameter'):
                client._request('tools/list', {})

    def test_error_messages_redact_bearer_credential(self):
        client = self.client()
        with patch.object(client, '_request', return_value={'isError': True, 'structuredContent': {'message': 'error test-credential'}}), \
             patch.object(mcp, 'reserve_tool_call'):
            with self.assertRaises(mcp.MCPBusinessError) as raised:
                client.call_tool('list_flash')
        self.assertNotIn('test-credential', str(raised.exception))

    def test_no_undeclared_parameters_or_missing_required_code(self):
        client = self.client()
        with patch.object(client, '_request') as send, patch.object(mcp, 'reserve_tool_call') as reserve:
            for name, arguments in [('list_flash', {'offset': 'bad'}), ('get_quote', {}), ('unknown', {})]:
                with self.assertRaises(mcp.MCPProtocolError):
                    client.call_tool(name, arguments)
        send.assert_not_called()
        reserve.assert_not_called()

    def test_sse_skips_notifications_and_checks_rpc_id(self):
        client = self.client()
        raw = b'data: {"jsonrpc":"2.0","method":"notifications/message"}\n\ndata: ' + json.dumps(rpc(1, {})).encode() + b'\n\n'
        with patch.object(client.opener, 'open', return_value=Response(sse=True, raw=raw)):
            self.assertEqual(client._request('tools/list', {}), {})
        with patch.object(client.opener, 'open', return_value=Response(rpc(999, {}))):
            with self.assertRaises(mcp.MCPProtocolError):
                client._request('tools/list', {})

    def test_discovery_uses_standard_cursor_pagination(self):
        client = self.client()
        with patch.object(client, '_request', side_effect=[{'tools': TOOLS[:1], 'nextCursor': 'page-2'}, {'tools': TOOLS[1:]}]) as send:
            self.assertEqual(len(client._discover('tools/list', 'tools')), 2)
        self.assertEqual(send.call_args_list[1].args, ('tools/list', {'cursor': 'page-2'}))

    def test_declared_resource_can_be_read(self):
        client = self.client()
        client.resources = [{'uri': 'quote://codes'}]
        with patch.object(client, '_request', return_value={'contents': []}) as send:
            client.read_resource('quote://codes')
        self.assertEqual(send.call_args.args, ('resources/read', {'uri': 'quote://codes'}))

    def test_budget_persists_per_tool_without_storing_token(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(mcp, 'STATE_PATH', Path(directory) / 'usage.json'):
            mcp.reserve_tool_call('list_flash', 'test-credential')
            state = json.loads(mcp.STATE_PATH.read_text())
            self.assertEqual(state['calls']['list_flash'], 1)
            self.assertNotIn('test-credential', mcp.STATE_PATH.read_text())
            state['calls']['list_flash'] = 1440
            mcp.STATE_PATH.write_text(json.dumps(state))
            with self.assertRaises(mcp.MCPBusinessError):
                mcp.reserve_tool_call('list_flash', 'test-credential')
            mcp.reserve_tool_call('get_quote', 'test-credential')

    def test_redirects_are_not_followed_with_bearer(self):
        self.assertIsNone(mcp.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example/'))

    def test_status_never_returns_credential_or_internal_identity(self):
        import hashlib
        with patch.object(mcp, 'token', return_value='test-credential'), \
             patch.dict(mcp._last_discovery, {'_identity': hashlib.sha256(b'test-credential').hexdigest(), 'connected': True}, clear=True):
            status = mcp.status()
        self.assertTrue(status['configured'])
        self.assertTrue(status['connected'])
        self.assertNotIn('_identity', status)
        self.assertNotIn('test-credential', json.dumps(status))
