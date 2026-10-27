"""Public Jin10 timeline only; dated/member-only history is never requested."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .news_domestic import CHINA_TZ, KEYWORDS
from .recent_news import WINDOW_HOURS, clean_text, filter_items

MAX_PAGES = 30
FETCH_SECONDS = 20
MAX_BYTES = 2 * 1024 * 1024


def fetch_page(cursor='', timeout=8):
    params = {'channel': '-8200', 'vip': '0'}
    if cursor:
        params['max_time'] = cursor
    # This is the public website's client identifier, not a user credential.
    request = Request('https://flash-api.jin10.com/get_flash_list?' + urlencode(params), headers={
        'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.jin10.com/',
        'x-app-id': 'bVBF4FyRTn5NJF5n', 'x-version': '1.0.0',
    })
    with urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError('金十快讯响应过大')
    payload = json.loads(body)
    if payload.get('status') != 200 or not isinstance(payload.get('data'), list):
        raise ValueError('金十公开快讯暂不可用或历史范围受限')
    return payload['data']


def parse_time(row):
    try:
        return datetime.strptime(row['time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=CHINA_TZ).astimezone(timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None


def parse_row(row):
    if not isinstance(row, dict):
        return None
    published = parse_time(row)
    identifier = str(row.get('id', ''))
    data, extras = row.get('data'), row.get('extras') or {}
    if published is None or not re.fullmatch(r'\d{14,25}', identifier) or not isinstance(data, dict):
        return None
    if data.get('vip_level') not in (None, 0, '0', False) or (isinstance(extras, dict) and extras.get('ad')):
        return None
    content = clean_text(str(data.get('content') or ''), 10000)
    title = clean_text(str(data.get('title') or '')) or clean_text(content, 120)
    if not title:
        return None
    return ({'id': hashlib.sha256(f'jin10|{identifier}'.encode()).hexdigest()[:20],
             'title': title, 'source': '金十快讯', 'url': f'https://flash.jin10.com/detail/{identifier}',
             'published_at': published.isoformat()}, published, f'{title} {content}'.casefold())


def fetch_public_jin10_news(now):
    cutoff, deadline = now - timedelta(hours=WINDOW_HOURS), time.monotonic() + FETCH_SECONDS
    groups = {key: [] for key in KEYWORDS}
    cursor, oldest, warning, pages = '', None, None, 0
    for _ in range(MAX_PAGES):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            warning = '金十公开快讯抓取已达时间上限，尚未覆盖全部72小时历史。'
            break
        try:
            rows = fetch_page(cursor, timeout=min(8, remaining))
        except Exception:
            if not pages:
                raise
            warning = '金十公开快讯分页暂时中断或历史受限，尚未覆盖全部72小时历史。'
            break
        pages += 1
        if not rows:
            warning = '金十公开快讯已到可获取范围，尚未覆盖全部72小时历史。'
            break
        times = [published for row in rows if isinstance(row, dict) and (published := parse_time(row)) is not None]
        for row in rows:
            parsed = parse_row(row)
            if not parsed:
                continue
            item, published, searchable = parsed
            if cutoff <= published <= now:
                for key, words in KEYWORDS.items():
                    if any(word.casefold() in searchable for word in words):
                        groups[key].append(item)
        if not times:
            warning = '金十公开快讯未返回有效时间，尚未覆盖全部72小时历史。'
            break
        earliest = min(times)
        oldest = min(oldest, earliest) if oldest else earliest
        if earliest <= cutoff:
            break
        next_cursor = earliest.astimezone(CHINA_TZ).strftime('%Y-%m-%d %H:%M:%S')
        if next_cursor == cursor:
            warning = '金十公开快讯未返回更早的分页，尚未覆盖全部72小时历史。'
            break
        cursor = next_cursor
    else:
        warning = '金十公开快讯抓取已达分页上限，尚未覆盖全部72小时历史。'
    return {'groups': {key: filter_items(items, now) for key, items in groups.items()},
            'warning': warning, 'coverage_start': oldest.isoformat() if oldest else None, 'pages': pages,
            'transport': 'public'}


def fetch_jin10_news(now):
    from .jin10_mcp import token
    if token():
        from .news_jin10_mcp import fetch_mcp_news
        return fetch_mcp_news(now)
    return fetch_public_jin10_news(now)
