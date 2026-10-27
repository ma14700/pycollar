"""Public RSS headlines, with bounded fetching and a rolling 72-hour window."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import re
from threading import Lock
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from .jin10_mcp import MCPError, status as jin10_mcp_status


WINDOW_HOURS = 72
CACHE_SECONDS = 300
MAX_ITEMS = 100
MAX_FEED_BYTES = 2 * 1024 * 1024
CATEGORIES = (
    ('middle_east', '中东', '中东 OR 伊朗 OR 以色列 OR 霍尔木兹'),
    ('usa', '美国', '美国 OR 美联储 OR 白宫'),
    ('oil', '原油', '原油 OR 油价 OR OPEC OR 布伦特'),
)
PROVIDER = 'Google 新闻 RSS'
PROVIDERS = {'google': PROVIDER, 'eastmoney': '东方财富快讯（国内）', 'jin10': '金十快讯（国内）',
             'domestic_mixed': '金十快讯 + 东方财富（历史补充）'}
_cache = {}
_locks = {key: Lock() for key, _, _ in CATEGORIES}
_domestic_locks = {'eastmoney': Lock(), 'jin10': Lock()}


def utc_now():
    return datetime.now(timezone.utc)


def clean_text(value, limit=500):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', '', html.unescape(value or ''))).strip()[:limit]


def safe_link(value):
    try:
        parts = urlsplit((value or '').strip())
        if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password:
            return None
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))
    except ValueError:
        return None


def parse_feed(body, now):
    if len(body) > MAX_FEED_BYTES or b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
        raise ValueError('新闻源响应格式无效')
    root = ET.fromstring(body)
    channel = root.find('channel') if root.tag == 'rss' else None
    if channel is None:
        raise ValueError('新闻源没有返回 RSS 内容')
    cutoff = now - timedelta(hours=WINDOW_HOURS)
    items = []
    for entry in channel.findall('item'):
        try:
            published = parsedate_to_datetime(entry.findtext('pubDate', ''))
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            published = published.astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            continue
        if not cutoff <= published <= now:
            continue
        source = clean_text(entry.findtext('source'), 120)
        title = clean_text(entry.findtext('title'))
        if source and title.endswith(f' - {source}'):
            title = title[:-len(source) - 3].strip()
        link = safe_link(entry.findtext('link'))
        if not title or not link:
            continue
        source = source or urlsplit(link).hostname
        items.append({
            'id': hashlib.sha256(f'{source}|{title}'.encode('utf-8')).hexdigest()[:20],
            'title': title, 'source': source, 'url': link,
            'published_at': published.isoformat(),
        })
    return filter_items(items, now)


def filter_items(items, now):
    """Re-filter cached items too, so expired stories never leave the API."""
    cutoff = now - timedelta(hours=WINDOW_HOURS)
    result, seen_links, seen_titles = [], set(), set()
    for item in sorted(items, key=lambda row: row['published_at'], reverse=True):
        published = datetime.fromisoformat(item['published_at'])
        title_key = (item['title'].casefold(), item['source'].casefold())
        if not cutoff <= published <= now or item['url'] in seen_links or title_key in seen_titles:
            continue
        seen_links.add(item['url'])
        seen_titles.add(title_key)
        result.append(dict(item))
    return result[:MAX_ITEMS]


def fetch_feed(query):
    url = 'https://news.google.com/rss/search?' + urlencode({
        'q': f'({query}) when:3d', 'hl': 'zh-CN', 'gl': 'CN', 'ceid': 'CN:zh-Hans',
    })
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/rss+xml, application/xml'})
    with urlopen(request, timeout=12) as response:
        body = response.read(MAX_FEED_BYTES + 1)
    if len(body) > MAX_FEED_BYTES:
        raise ValueError('新闻源响应过大')
    return body


def category_news(category, now, refresh=False):
    key, name, query = category
    base = {'id': key, 'name': name, 'provider': PROVIDER, 'provider_id': 'google'}
    with _locks[key]:
        cached = _cache.get(('google', key))
        if cached and not refresh and 0 <= (now - cached['fetched_at']).total_seconds() < CACHE_SECONDS:
            items = filter_items(cached['items'], now)
            return {**base, 'items': items, 'status': 'success' if items else 'empty',
                    'fetched_at': cached['fetched_at'].isoformat(), 'cached': True, 'error': None}
        try:
            items = parse_feed(fetch_feed(query), now)
            fetched_at = utc_now()
            _cache[('google', key)] = {'items': items, 'fetched_at': fetched_at}
            return {**base, 'items': items, 'status': 'success' if items else 'empty',
                    'fetched_at': fetched_at.isoformat(), 'cached': False, 'error': None}
        except Exception:
            items = filter_items(cached['items'], now) if cached else []
            return {**base, 'items': items, 'status': 'stale' if items else 'error',
                    'fetched_at': cached['fetched_at'].isoformat() if cached else None,
                    'cached': bool(items),
                    'error': ('新闻源暂不可用，显示上次抓取且仍在最近72小时内的消息。' if items
                              else '新闻源暂不可用，请稍后刷新或检查网络连接。')}


def domestic_news(now, refresh=False, provider='eastmoney'):
    from .news_domestic import fetch_domestic_news
    from .news_jin10 import fetch_jin10_news
    fetch = fetch_jin10_news if provider == 'jin10' else fetch_domestic_news
    if provider == 'jin10':
        from .jin10_mcp import credential_identity
        source_key = credential_identity()
    else:
        source_key = 'eastmoney'
    with _domestic_locks[provider]:
        cached = _cache.get(provider)
        if cached and cached.get('source_key') != source_key:
            cached = None
        cache_hit = bool(cached and cached.get('source_key') == source_key and not refresh and
                         (now - cached['fetched_at']).total_seconds() < CACHE_SECONDS)
        failed = bool(cached and cached.get('stale'))
        failure_reason = None
        if not cache_hit:
            try:
                snapshot = fetch(now)
                cached = {**snapshot, 'fetched_at': snapshot.get('fetched_at') or utc_now(), 'source_key': source_key}
                failed = bool(snapshot.get('stale'))
                _cache[provider] = cached
            except Exception as exception:
                failed = True
                if isinstance(exception, MCPError):
                    failure_reason = str(exception)
        categories = []
        for key, name, _ in CATEGORIES:
            items = filter_items(cached['groups'][key], now) if cached else []
            error = None
            if failed:
                error = failure_reason or (f'{PROVIDERS[provider]}暂不可用，显示上次抓取且仍在最近72小时内的消息。' if items
                         else f'{PROVIDERS[provider]}暂不可用，请稍后刷新或检查网络连接。')
            categories.append({
                'id': key, 'name': name, 'provider': ('金十 MCP（授权）' if provider == 'jin10' and cached and cached.get('transport') == 'mcp' else PROVIDERS[provider]), 'provider_id': provider,
                'items': items, 'fetched_at': cached['fetched_at'].isoformat() if cached else None,
                'status': ('stale' if items else 'error') if failed else ('success' if items else 'empty'),
                'cached': cache_hit or (failed and bool(items)), 'error': error,
                'warning': cached.get('warning') if cached else None,
                'coverage_start': cached.get('coverage_start') if cached else None,
                'transport': cached.get('transport') if cached else None,
                'history_complete': cached.get('history_complete') if cached else None,
            })
        return categories


def preferred_domestic_news(now, refresh=False):
    """Prefer Jin10; supplement only its missing history with Eastmoney."""
    primary = domestic_news(now, refresh, provider='jin10')
    if all(category['status'] in ('success', 'empty') and not category['warning'] for category in primary):
        return primary
    backup = {category['id']: category for category in domestic_news(now, refresh, provider='eastmoney')}
    result = []
    for category in primary:
        other = backup[category['id']]
        if category['status'] in ('error', 'stale'):
            result.append(other if other['status'] in ('success', 'empty') or
                          (category['status'] == 'error' and other['status'] == 'stale') else category)
            continue
        if not category['warning'] or other['status'] not in ('success', 'empty'):
            result.append(category)
            continue
        coverage = category['coverage_start']
        older = [item for item in other['items'] if coverage is None or item['published_at'] < coverage]
        merged = filter_items(category['items'] + older, now)
        item_sources = {item['source'] for item in merged}
        actual = ('domestic_mixed' if len(item_sources) > 1 else
                  'eastmoney' if item_sources == {'东方财富快讯'} else 'jin10')
        result.append({**category, 'items': merged, 'provider': category['provider'] if actual == 'jin10' else PROVIDERS[actual],
                       'provider_id': actual, 'warning': other['warning'],
                       'coverage_start': other['coverage_start'], 'cached': category['cached'] and other['cached'],
                       'fetched_at': other['fetched_at'] if actual == 'eastmoney' else category['fetched_at'],
                       'supplement_fetched_at': other['fetched_at'],
                       'notice': '近期快讯优先来自金十，未覆盖的历史由东方财富补充，逐条标明来源。'})
    return result


def get_recent_news(refresh=False, provider='auto'):
    if provider not in ('auto', 'google', 'eastmoney', 'jin10', 'domestic'):
        raise ValueError('新闻源仅支持自动、国内优先金十、金十、东方财富和 Google 新闻')
    now = utc_now()
    actual_provider = 'google' if provider == 'auto' else provider
    fallback_reason = None
    if actual_provider in ('eastmoney', 'jin10'):
        categories = domestic_news(now, refresh, provider=actual_provider)
    if actual_provider == 'domestic':
        categories = preferred_domestic_news(now, refresh)
        sources = {category['provider_id'] for category in categories}
        actual_provider = next(iter(sources)) if len(sources) == 1 else 'mixed'
    if actual_provider == 'google':
        with ThreadPoolExecutor(max_workers=3) as pool:
            categories = list(pool.map(lambda category: category_news(category, now, refresh), CATEGORIES))
        if provider == 'auto' and any(category['status'] in ('error', 'stale') for category in categories):
            domestic = {category['id']: category for category in preferred_domestic_news(now, refresh)}
            replaced = []
            for index, category in enumerate(categories):
                backup = domestic[category['id']]
                if category['status'] in ('error', 'stale') and (
                        backup['status'] in ('success', 'empty') or
                        (category['status'] == 'error' and backup['status'] == 'stale')):
                    categories[index] = backup
                    replaced.append(category['name'])
            if replaced:
                fallback_reason = f'{"、".join(replaced)}的外网新闻源暂不可用，已回退至国内源（优先金十），实际来源见各板块。'
            else:
                fallback_reason = '外网新闻源暂不可用，国内备用源也未能获取更新，请稍后刷新。'
            sources = {category['provider_id'] for category in categories}
            actual_provider = next(iter(sources)) if len(sources) == 1 else 'mixed'
    return {
        'requested_provider': provider, 'provider': actual_provider,
        'provider_name': ('金十 MCP（授权）' if actual_provider == 'jin10' and any(category.get('transport') == 'mcp' for category in categories)
                          else PROVIDERS.get(actual_provider, '多源新闻（实际来源见各板块）')), 'fallback_reason': fallback_reason,
        'window_hours': WINDOW_HOURS, 'window_start': (now - timedelta(hours=WINDOW_HOURS)).isoformat(),
        'window_end': now.isoformat(), 'timezone': 'Asia/Shanghai',
        'cache_seconds': CACHE_SECONDS, 'max_items_per_category': MAX_ITEMS,
        'categories': categories,
        'jin10_mcp': jin10_mcp_status(),
    }
