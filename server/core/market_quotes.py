"""Brent, WTI and spot silver quotes from authorized Jin10 MCP."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import json
import math
from threading import Lock

from .jin10_mcp import Jin10MCPClient, MCPError, MCPProtocolError, credential_identity

INSTRUMENTS = (('UKOIL', '布伦特原油'), ('USOIL', 'WTI 原油'), ('XAGUSD', '现货白银'))
UNITS = {'UKOIL': '美元/桶', 'USOIL': '美元/桶', 'XAGUSD': '美元/盎司'}
CACHE_SECONDS = 60
REFRESH_SECONDS = 240
_lock = Lock()
_cache = {}


def utc_now():
    return datetime.now(timezone.utc)


def resource_codes(result):
    if not isinstance(result, dict) or not isinstance(result.get('contents'), list):
        raise MCPProtocolError('金十报价代码资源格式无效')
    codes = set()

    def collect(value):
        if isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            code = value.get('code')
            if isinstance(code, str):
                codes.add(code)
            for item in value.values():
                if isinstance(item, (list, dict)):
                    collect(item)

    for content in result.get('contents', []):
        if not isinstance(content, dict) or content.get('mimeType') != 'application/json':
            continue
        try:
            collect(json.loads(content.get('text', '')))
        except (ValueError, TypeError):
            raise MCPProtocolError('金十报价代码资源不是有效 JSON') from None
    return codes


def number(value, required=False):
    if value is None or value == '':
        if required:
            raise ValueError('金十报价缺少最新价格')
        return None
    try:
        parsed = float(value)
    except (ValueError, TypeError):
        raise ValueError('金十报价包含无效数值') from None
    if not math.isfinite(parsed):
        raise ValueError('金十报价包含无效数值')
    return parsed


def normalize_quote(data, code, name):
    if not isinstance(data, dict) or data.get('code') != code:
        raise ValueError('金十返回的报价品种与请求不一致')
    close = number(data.get('close'), required=True)
    if close <= 0:
        raise ValueError('金十最新报价不是有效正价格')
    try:
        published = datetime.fromisoformat(str(data.get('time', '')).replace('Z', '+00:00'))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone(timedelta(hours=8)))
        published = published.astimezone(timezone.utc)
        precision = max(2, min(6, -Decimal(str(data['close'])).as_tuple().exponent))
    except (ValueError, TypeError, OverflowError, InvalidOperation):
        raise ValueError('金十报价时间或价格格式无效') from None
    return {'code': code, 'name': name, 'source': '金十 MCP', 'currency': 'USD', 'unit': UNITS[code],
            'close': close, 'precision': precision, 'time': published.isoformat(),
            **{field: number(data.get(field)) for field in ('open', 'high', 'low', 'volume', 'ups_price', 'ups_percent')}}


def view(snapshot, now, cached=False, error=None):
    result = {**snapshot, 'cached': cached, 'status': 'stale' if error else 'success', 'error': error}
    published = datetime.fromisoformat(snapshot['time'])
    result['quote_age_seconds'] = max(0, round((now - published).total_seconds()))
    result['delayed'] = result['quote_age_seconds'] > 15 * 60
    return result


def get_market_quotes(refresh=False):
    identity = credential_identity()
    with _lock:
        now = utc_now()
        quotes = {}
        needed = []
        for code, name in INSTRUMENTS:
            cached = _cache.get((identity, code))
            if cached and not refresh and (now - datetime.fromisoformat(cached['fetched_at'])).total_seconds() < CACHE_SECONDS:
                quotes[code] = view(cached, now, cached=True)
            else:
                needed.append((code, name))
        if needed:
            try:
                client = Jin10MCPClient(timeout=8).initialize()
                supported = resource_codes(client.read_resource('quote://codes'))
                initialization_error = None
            except MCPError as error:
                initialization_error = str(error)
            for code, name in needed:
                try:
                    if initialization_error:
                        raise MCPProtocolError(initialization_error)
                    if code not in supported:
                        raise MCPProtocolError(f'金十代码资源未声明 {code}，暂不请求该品种')
                    response = client.call_tool('get_quote', {'code': code})
                    snapshot = {**normalize_quote(response.get('data'), code, name), 'fetched_at': utc_now().isoformat()}
                    _cache[(identity, code)] = snapshot
                    quotes[code] = view(snapshot, utc_now())
                except (MCPError, ValueError) as error:
                    cached = _cache.get((identity, code))
                    if cached:
                        quotes[code] = view(cached, utc_now(), cached=True, error=str(error))
                    else:
                        quotes[code] = {'code': code, 'name': name, 'source': '金十 MCP', 'status': 'error',
                                        'error': str(error), 'cached': False, 'close': None, 'time': None, 'fetched_at': None}
        return {'source': '金十 MCP', 'timezone': 'Asia/Shanghai', 'cache_seconds': CACHE_SECONDS,
                'refresh_seconds': REFRESH_SECONDS, 'quotes': [quotes[code] for code, _ in INSTRUMENTS]}
