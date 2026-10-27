"""Jin10 Streamable HTTP MCP client. Credentials never leave this backend."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_URL = 'https://mcp.jin10.com/mcp'
PROTOCOL_VERSION = '2025-11-25'
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
STATE_PATH = PROJECT_ROOT / '.venv' / 'jin10_mcp_usage.json'
_usage_lock = Lock()
_status_lock = Lock()
_last_discovery = {}


class MCPError(RuntimeError):
    pass


class MCPProtocolError(MCPError):
    pass


class MCPBusinessError(MCPError):
    pass


def token():
    config = dotenv_values(PROJECT_ROOT / '.env')
    return (os.getenv('JIN10_MCP_TOKEN') or config.get('JIN10_MCP_TOKEN') or '').strip()


def credential_identity():
    value = token()
    return hashlib.sha256(value.encode()).hexdigest() if value else 'public'


def status():
    credential = token()
    identity = hashlib.sha256(credential.encode()).hexdigest() if credential else None
    with _status_lock:
        discovery = {key: value for key, value in _last_discovery.items() if not key.startswith('_')} if _last_discovery.get('_identity') == identity else {}
        return {'configured': bool(credential), 'protocol_version': PROTOCOL_VERSION,
                'connected': False, **discovery}


def _safe_message(value, credential):
    return str(value or '金十 MCP 调用失败').replace(credential, '[redacted]')[:300]


def reserve_tool_call(name, credential):
    """Local per-token, per-tool Beijing-day budget, persisted across restarts."""
    day = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    identity = hashlib.sha256(credential.encode()).hexdigest()
    with _usage_lock:
        try:
            state = json.loads(STATE_PATH.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            state = {}
        if state.get('day') != day or state.get('identity') != identity:
            state = {'day': day, 'identity': identity, 'calls': {}}
        calls = state.setdefault('calls', {})
        if calls.get(name, 0) >= 1440:
            raise MCPBusinessError('本地已接近金十该工具每日调用上限，请明日再试。')
        calls[name] = calls.get(name, 0) + 1
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = STATE_PATH.with_suffix('.tmp')
        temporary.write_text(json.dumps(state), encoding='utf-8')
        temporary.replace(STATE_PATH)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward a Bearer credential to a redirected destination.
        return None


class Jin10MCPClient:
    def __init__(self, credential=None, timeout=12):
        self.credential = credential if credential is not None else token()
        if not self.credential:
            raise MCPError('尚未配置 JIN10_MCP_TOKEN')
        self.timeout = timeout
        self.protocol_version = None
        self.session_id = None
        self.sequence = 0
        self.tools = {}
        self.resources = []
        self.opener = build_opener(NoRedirect())

    def _read_rpc(self, response, request_id):
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/event-stream' not in content_type:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise MCPProtocolError('金十 MCP 响应过大')
            return json.loads(body)
        # Stop after the matching JSON-RPC response, without waiting for the
        # server to close a potentially persistent SSE stream.
        data, consumed = [], 0
        while True:
            line = response.readline(min(MAX_RESPONSE_BYTES - consumed + 1, 1024 * 1024))
            consumed += len(line)
            if consumed > MAX_RESPONSE_BYTES:
                raise MCPProtocolError('金十 MCP SSE 响应过大')
            if not line or line in (b'\n', b'\r\n'):
                if data:
                    payload = json.loads('\n'.join(data))
                    data = []
                    if isinstance(payload, dict) and payload.get('id') == request_id:
                        return payload
                if not line:
                    raise MCPProtocolError('金十 MCP SSE 缺少匹配的响应')
            elif line.startswith(b'data:'):
                data.append(line[5:].decode('utf-8').strip())

    def _request(self, method, params=None, notification=False):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                   'Authorization': 'Bearer ' + self.credential}
        if self.protocol_version:
            headers['MCP-Protocol-Version'] = self.protocol_version
        if self.session_id:
            headers['Mcp-Session-Id'] = self.session_id
        payload = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            payload['params'] = params
        if not notification:
            self.sequence += 1
            payload['id'] = self.sequence
        request = Request(SERVER_URL, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                session = response.headers.get('Mcp-Session-Id')
                if session:
                    self.session_id = session
                if notification:
                    return None
                message = self._read_rpc(response, self.sequence)
        except HTTPError as error:
            raise MCPProtocolError(f'金十 MCP HTTP {error.code}，请检查 Token 权限或服务状态') from None
        except (URLError, TimeoutError, OSError):
            raise MCPProtocolError('金十 MCP 网络连接失败，请稍后重试') from None
        except (ValueError, UnicodeError):
            raise MCPProtocolError('金十 MCP 返回了无效的协议响应') from None
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or message.get('id') != self.sequence:
            raise MCPProtocolError('金十 MCP JSON-RPC 响应不匹配')
        if 'error' in message:
            error = message['error']
            detail = error.get('message') if isinstance(error, dict) else error
            raise MCPProtocolError(_safe_message(detail, self.credential))
        if 'result' not in message:
            raise MCPProtocolError('金十 MCP 响应缺少 result')
        return message['result']

    def _discover(self, method, field):
        items, cursor, seen = [], None, set()
        for _ in range(20):
            result = self._request(method, {'cursor': cursor} if cursor else {})
            if not isinstance(result, dict) or not isinstance(result.get(field), list):
                raise MCPProtocolError(f'金十 MCP {method} 返回格式无效')
            items.extend(result[field])
            cursor = result.get('nextCursor')  # Standard MCP discovery pagination.
            if not cursor:
                return items
            if cursor in seen:
                raise MCPProtocolError('金十 MCP 服务发现分页游标重复')
            seen.add(cursor)
        raise MCPProtocolError('金十 MCP 服务发现分页超出上限')

    def initialize(self):
        result = self._request('initialize', {'protocolVersion': PROTOCOL_VERSION, 'capabilities': {},
            'clientInfo': {'name': 'pycollar', 'version': '1.0.0'}})
        version = result.get('protocolVersion') if isinstance(result, dict) else None
        if version not in (PROTOCOL_VERSION, '2025-06-18', '2025-03-26'):
            raise MCPProtocolError('金十 MCP 协商的协议版本不受支持')
        self.protocol_version = version
        self._request('notifications/initialized', notification=True)
        self.tools = {tool['name']: tool for tool in self._discover('tools/list', 'tools') if isinstance(tool, dict) and 'name' in tool}
        capabilities = result.get('capabilities') or {}
        if 'resources' in capabilities:
            self.resources = self._discover('resources/list', 'resources')
        with _status_lock:
            _last_discovery.update({'connected': True, 'negotiated_version': version,
                '_identity': hashlib.sha256(self.credential.encode()).hexdigest(),
                'available_tools': sorted(self.tools),
                'available_resources': [resource.get('uri') for resource in self.resources if isinstance(resource, dict)],
                'last_connected_at': datetime.now(timezone.utc).isoformat()})
        return self

    def call_tool(self, name, arguments=None):
        if name not in self.tools:
            raise MCPProtocolError(f'金十 MCP 未声明工具 {name}')
        arguments = arguments or {}
        schema = self.tools[name].get('inputSchema') or {}
        declared = schema.get('properties') or {}
        if set(arguments) - set(declared) or set(schema.get('required') or []) - set(arguments):
            raise MCPProtocolError('金十 MCP 工具参数与服务声明不一致')
        reserve_tool_call(name, self.credential)
        result = self._request('tools/call', {'name': name, 'arguments': arguments})
        if not isinstance(result, dict):
            raise MCPProtocolError('金十 MCP 工具结果格式无效')
        structured = result.get('structuredContent')
        if result.get('isError'):
            detail = structured.get('message') if isinstance(structured, dict) else None
            if not detail:
                detail = ' '.join(str(part.get('text', '')) for part in result.get('content', []) if isinstance(part, dict))
            raise MCPBusinessError(_safe_message(detail, self.credential))
        # Text content is supplementary only; never parse it as machine data.
        if not isinstance(structured, dict):
            raise MCPProtocolError('金十 MCP 工具缺少 structuredContent')
        if structured.get('status', 200) != 200:
            raise MCPBusinessError(_safe_message(structured.get('message'), self.credential))
        return structured

    def read_resource(self, uri):
        if uri not in {resource.get('uri') for resource in self.resources}:
            raise MCPProtocolError('金十 MCP 未声明该资源')
        return self._request('resources/read', {'uri': uri})
