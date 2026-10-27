"""Incremental, bounded 72-hour headline sync through the official MCP API."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import time

from .jin10_mcp import Jin10MCPClient, MCPError, MCPProtocolError, PROJECT_ROOT, credential_identity
from .news_domestic import CHINA_TZ, KEYWORDS
from .recent_news import WINDOW_HOURS, clean_text, filter_items, safe_link

STORE_PATH = PROJECT_ROOT / '.venv' / 'jin10_mcp_news.json'
FETCH_SECONDS = 30
MAX_PAGES = 250


def parse_item(row):
    if not isinstance(row, dict):
        return None
    try:
        published = datetime.fromisoformat(str(row.get('time', '')).replace('Z', '+00:00'))
        if published.tzinfo is None:
            published = published.replace(tzinfo=CHINA_TZ)
        published = published.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None
    url = safe_link(row.get('url'))
    if not url:
        return None
    content = clean_text(str(row.get('content') or ''), 20000)
    title = clean_text(str(row.get('title') or '')) or clean_text(content, 120)
    if not title:
        return None
    return {'id': hashlib.sha256(('jin10-mcp|' + url).encode()).hexdigest()[:20],
            'title': title, 'source': '金十 MCP', 'url': url, 'published_at': published.isoformat(),
            '_searchable': f'{title} {content}'.casefold()}


def read_state(identity):
    try:
        state = json.loads(STORE_PATH.read_text(encoding='utf-8'))
        if state.get('identity') == identity and isinstance(state.get('items'), list):
            return state
    except (OSError, ValueError, AttributeError):
        pass
    return {'identity': identity, 'items': [], 'history_cursor': None, 'history_complete': False,
            'history_exhausted': False, 'coverage_start': None}


def write_state(state):
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STORE_PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    temporary.replace(STORE_PATH)


def fetch_mcp_news(now):
    cutoff, deadline = now - timedelta(hours=WINDOW_HOURS), time.monotonic() + FETCH_SECONDS
    identity = credential_identity()
    state = read_state(identity)
    # Keep all retained headlines for incremental overlap detection; category
    # display caps are applied only after matching, never to the sync cursor.
    retained = [item for item in state['items'] if cutoff <= datetime.fromisoformat(item['published_at']) <= now]
    if not retained:
        state.update(history_complete=False, history_exhausted=False, history_cursor=None, coverage_start=None)
    known = {item['url'] for item in retained}
    items = {item['url']: item for item in retained}
    coverage = datetime.fromisoformat(state['coverage_start']) if state.get('coverage_start') else None
    if coverage and coverage <= cutoff:
        state['history_complete'] = True
    warning, pages, cursor, reading_head, failed = None, 0, None, True, False
    head_earliest = None
    try:
        client = Jin10MCPClient(timeout=10).initialize()
        if 'list_flash' not in client.tools:
            raise MCPProtocolError('金十 MCP 没有声明 list_flash 工具')
        seen_cursors = set()
        while pages < MAX_PAGES and time.monotonic() < deadline:
            client.timeout = max(0.1, min(10, deadline - time.monotonic()))
            response = client.call_tool('list_flash', {'cursor': cursor} if cursor else {})
            data = response.get('data')
            if not isinstance(data, dict) or not isinstance(data.get('items'), list) or not isinstance(data.get('has_more'), bool):
                raise MCPProtocolError('金十 MCP 快讯列表缺少 data.items / data.has_more')
            pages += 1
            parsed = [item for raw in data['items'] if (item := parse_item(raw)) is not None]
            overlap = any(item['url'] in known for item in parsed)
            times = [datetime.fromisoformat(item['published_at']) for item in parsed]
            for item in parsed:
                if cutoff <= datetime.fromisoformat(item['published_at']) <= now:
                    items[item['url']] = item
            if times:
                earliest = min(times)
                if reading_head:
                    head_earliest = min(head_earliest, earliest) if head_earliest else earliest
                coverage = min(coverage, earliest) if coverage else earliest
                if earliest <= cutoff:
                    state.update(history_complete=True, history_cursor=None)
                    break
            next_cursor = data.get('next_cursor')
            if data['has_more'] and (not isinstance(next_cursor, str) or not next_cursor or next_cursor == cursor or next_cursor in seen_cursors):
                raise MCPProtocolError('金十 MCP 快讯分页缺少有效 next_cursor，或游标重复')
            if not data['has_more']:
                if reading_head and not overlap:
                    # A long offline gap can separate retained older stories
                    # from the server's current window. Do not claim a full
                    # 72 hours just because a previous sync once covered it.
                    coverage = head_earliest
                    state['history_complete'] = bool(coverage and coverage <= cutoff)
                state.update(history_exhausted=True, history_cursor=None)
                break
            if not parsed:
                raise MCPProtocolError('金十 MCP 当前分页未返回有效快讯时间或链接')
            seen_cursors.add(next_cursor)
            if reading_head and overlap:
                if state['history_complete'] or state['history_exhausted']:
                    break
                cursor = state.get('history_cursor') or next_cursor
                reading_head = False
            else:
                cursor = next_cursor
                # If the newest gap itself exceeds this refresh budget, save
                # this position and continue it on the next refresh.
                state['history_cursor'] = cursor
        if not state['history_complete']:
            warning = ('金十 MCP 已到接口可提供的历史范围，尚未覆盖全部72小时。' if state['history_exhausted']
                       else '金十 MCP 正在分批同步历史，尚未覆盖全部72小时；下次刷新会继续，国内模式可由东方财富补充。')
    except MCPError as error:
        if not pages:
            if not retained:
                raise
            failed = True
        warning = str(error)
    fetched_at = (datetime.fromisoformat(state['fetched_at']) if failed and state.get('fetched_at')
                  else datetime.now(timezone.utc))
    state.update(items=sorted(items.values(), key=lambda item: item['published_at'], reverse=True),
                 coverage_start=coverage.isoformat() if coverage else None, fetched_at=fetched_at.isoformat())
    write_state(state)
    groups = {}
    for key, words in KEYWORDS.items():
        matched = []
        for item in state['items']:
            if any(word.casefold() in item.get('_searchable', item['title'].casefold()) for word in words):
                matched.append({name: value for name, value in item.items() if not name.startswith('_')})
        groups[key] = filter_items(matched, now)
    return {'groups': groups, 'warning': warning, 'coverage_start': state['coverage_start'], 'pages': pages,
            'transport': 'mcp', 'fetched_at': fetched_at, 'stale': failed,
            'history_complete': state['history_complete'], 'retained_items': len(state['items'])}
