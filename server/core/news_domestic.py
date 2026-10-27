"""Eastmoney's public 7x24 feed, paginated until the rolling cutoff."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import uuid

from .recent_news import WINDOW_HOURS, clean_text, filter_items

CHINA_TZ = timezone(timedelta(hours=8))
MAX_PAGES = 30
FETCH_SECONDS = 35
MAX_BYTES = 2 * 1024 * 1024
KEYWORDS = {
    'middle_east': ('中东', '伊朗', '以色列', '加沙', '黎巴嫩', '叙利亚', '沙特', '阿联酋', '卡塔尔',
                    '伊拉克', '霍尔木兹', '内塔尼亚胡', '哈马斯', '真主党', '胡塞', '也门', '德黑兰',
                    '巴勒斯坦', '科威特', '巴林', '波斯湾'),
    'usa': ('美国', '美联储', '白宫', '特朗普', '纳斯达克', '纳指', '标普', '道琼斯', '美股', '美债',
            '美元指数', '鲍威尔', 'FOMC'),
    'oil': ('原油', '油价', '石油', '布伦特', 'WTI', 'OPEC', '库欣', 'EIA', '霍尔木兹'),
}


def fetch_page(cursor='', timeout=8):
    params = {'client': 'web', 'biz': 'web_724', 'fastColumn': '102', 'sortEnd': cursor,
              'pageSize': '200', 'req_trace': uuid.uuid4().hex}
    request = Request('https://np-weblist.eastmoney.com/comm/web/getFastNewsList?' + urlencode(params),
                      headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://kuaixun.eastmoney.com/'})
    with urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError('国内新闻响应过大')
    payload = json.loads(body)
    data = payload.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('fastNewsList'), list):
        raise ValueError('国内新闻源未返回有效数据')
    return data


def parse_row(row):
    if not isinstance(row, dict):
        return None
    try:
        published = datetime.strptime(row['showTime'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=CHINA_TZ).astimezone(timezone.utc)
    except (KeyError, ValueError, TypeError):
        return None
    code = str(row.get('code', ''))
    if not re.fullmatch(r'\d{12,25}', code):
        return None
    summary = clean_text(row.get('summary'), 10000)
    title = clean_text(row.get('title')) or clean_text(summary, 120)
    if not title:
        return None
    source = '东方财富快讯'
    return ({'id': hashlib.sha256(f'{source}|{title}'.encode()).hexdigest()[:20],
             'title': title, 'source': source, 'url': f'https://finance.eastmoney.com/a/{code}.html',
             'published_at': published.isoformat()}, published, f'{title} {summary}'.casefold())


def fetch_domestic_news(now):
    cutoff = now - timedelta(hours=WINDOW_HOURS)
    deadline = time.monotonic() + FETCH_SECONDS
    cursor, seen_cursors = '', set()
    groups = {key: [] for key in KEYWORDS}
    oldest = None
    warning = None
    pages = 0
    for _ in range(MAX_PAGES):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            warning = '国内新闻抓取已达时间上限，当前仅展示已获取的近72小时消息，可稍后刷新。'
            break
        try:
            data = fetch_page(cursor, timeout=min(8, remaining))
        except Exception:
            if not pages:
                raise
            warning = '国内新闻分页暂时中断，当前仅展示已获取的近72小时消息，可稍后刷新。'
            break
        pages += 1
        rows = data['fastNewsList']
        if not rows:
            break
        page_times = []
        for row in rows:
            parsed = parse_row(row)
            if parsed is None:
                continue
            item, published, searchable = parsed
            page_times.append(published)
            oldest = min(oldest, published) if oldest else published
            if not cutoff <= published <= now:
                continue
            for key, words in KEYWORDS.items():
                if any(word.casefold() in searchable for word in words):
                    groups[key].append(item)
        if page_times and min(page_times) <= cutoff:
            break
        next_cursor = str(data.get('sortEnd') or '')
        if not next_cursor or next_cursor == cursor or next_cursor in seen_cursors or not page_times:
            warning = '国内新闻源未提供更早的有效分页，当前仅展示已获取的近72小时消息。'
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    else:
        warning = '国内新闻抓取已达分页上限，当前仅展示已获取的近72小时消息。'
    return {'groups': {key: filter_items(items, now) for key, items in groups.items()},
            'warning': warning, 'pages': pages, 'coverage_start': oldest.isoformat() if oldest else None}
