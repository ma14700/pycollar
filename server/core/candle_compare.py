"""Fixed-length OHLC shape search; reference and continuation never reach target."""
import numpy as np
import pandas as pd

from .data_loader import fetch_data
from .market_cache import is_contract

PRICE_COLUMNS = ['Open', 'High', 'Low', 'Close']
WEIGHTS = np.array([0.15, 0.20, 0.20, 0.45])
MA_PERIODS = (20, 55, 60, 144)
COMPARISON_MA_PERIODS = (20, 60, 144)


def boundary(value, end=False):
    if not value:
        return None
    try:
        result = pd.Timestamp(value)
        if pd.isna(result):
            raise ValueError
        if result.tzinfo is not None:
            result = result.tz_convert('Asia/Shanghai').tz_localize(None)
        if end and len(str(value).strip()) == 10:
            result += pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
        return result
    except (ValueError, TypeError, OverflowError):
        raise ValueError('时间格式无效，请重新选择日期或时间') from None


def segment(df, mean, scale):
    close = df.Close.to_numpy(dtype=float)
    return {
        'start': str(df.index[0]) if len(df) else None,
        'end': str(df.index[-1]) if len(df) else None,
        'bars': len(df),
        'dates': df.index.strftime('%Y-%m-%d %H:%M:%S').tolist(),
        # ECharts uses open, close, low, high.
        'ohlc': df[['Open', 'Close', 'Low', 'High']].to_numpy(dtype=float).tolist(),
        'normalized_close': ((close - mean) / scale).round(6).tolist(),
        'ma': {
            f'ma{period}': [None if pd.isna(value) else round(float(value), 6)
                            for value in df[f'MA{period}'].to_numpy()]
            for period in MA_PERIODS
        },
        'normalized_ma': {
            f'ma{period}': [None if pd.isna(value) else round((float(value) - mean) / scale, 6)
                            for value in df[f'MA{period}'].to_numpy()]
            for period in MA_PERIODS
        },
        'return_pct': round(float((close[-1] / close[0] - 1) * 100), 4) if len(df) else None,
    }


def find_similar_candles(df, window_size=50, top_k=5, min_similarity=0,
                         continuation_bars=20, target_end=None,
                         search_start=None, search_end=None, ma_periods=None):
    if ma_periods is not None and (not isinstance(ma_periods, (list, tuple)) or
            any(type(period) is not int or period not in COMPARISON_MA_PERIODS for period in ma_periods)):
        raise ValueError('辅助对比均线仅支持 MA20、MA60、MA144')
    ma_periods = sorted(set(ma_periods or []))
    if not 10 <= window_size <= 500 or not 1 <= top_k <= 20:
        raise ValueError('对比根数须为 10～500，返回数量须为 1～20')
    if not 0 <= continuation_bars <= 200 or not 0 <= min_similarity <= 100:
        raise ValueError('后续观察根数须为 0～200，相似度门槛须为 0～100')
    if df is None or df.empty:
        raise ValueError('没有可用于对比的行情数据')
    if not all(column in df for column in PRICE_COLUMNS):
        raise ValueError('行情数据缺少开高低收字段')
    df = df.copy()
    df.index = pd.DatetimeIndex(pd.to_datetime(df.index)).as_unit('ns')
    if df.index.tz is not None:
        df.index = df.index.tz_convert('Asia/Shanghai').tz_localize(None)
    if df.index.hasnans or df.index.has_duplicates:
        raise ValueError('行情时间存在缺失或重复，请更换品种或数据源')
    df = df.sort_index()
    try:
        prices = df[PRICE_COLUMNS].to_numpy(dtype=float)
    except (ValueError, TypeError):
        raise ValueError('行情价格格式无效') from None
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError('行情包含缺失、无穷或非正价格，无法对比')
    if ((prices[:, 1] < prices.max(axis=1)) | (prices[:, 2] > prices.min(axis=1))).any():
        raise ValueError('行情高低价关系异常，无法对比')

    # Calculate trailing averages before slicing. A 50-bar chart can therefore
    # show MA144 using its preceding history; insufficient history stays null.
    close_series = pd.Series(prices[:, 3], index=df.index)
    for period in MA_PERIODS:
        df[f'MA{period}'] = close_series.rolling(period, min_periods=period).mean()

    cutoff = boundary(target_end, end=True)
    history_start, history_end = boundary(search_start), boundary(search_end, end=True)
    if history_start is not None and history_end is not None and history_start > history_end:
        raise ValueError('历史搜索开始时间不能晚于结束时间')
    target_stop = len(df) if cutoff is None else int(df.index.searchsorted(cutoff, side='right'))
    target_start = target_stop - window_size
    if target_start < 0:
        raise ValueError(f'基准结束时间之前不足 {window_size} 根 K 线，请缩小根数或调整时间')
    # Keep continuation wholly before the target; exclude the target itself.
    last_start = target_start - window_size - continuation_bars
    if last_start < 0:
        needed = 2 * window_size + continuation_bars
        raise ValueError(f'历史长度不足：基准结束前需至少 {needed} 根 K 线，当前只有 {target_stop} 根。请减小对比或观察根数。')

    target = df.iloc[target_start:target_stop]
    target_mean, target_scale = float(target.Close.mean()), float(target.Close.std(ddof=0))
    if target_scale <= abs(target_mean) * 1e-12:
        raise ValueError('基准区间收盘价几乎不变，无法计算有效形态相似度')
    target_shape = (prices[target_start:target_stop] - target_mean) / target_scale
    ma_values = df[[f'MA{period}' for period in ma_periods]].to_numpy(dtype=float)
    target_ma = ma_values[target_start:target_stop]
    if ma_periods and not np.isfinite(target_ma).all():
        raise ValueError(f'基准区间之前的历史不足，无法完整计算 MA{max(ma_periods)}，请推迟基准结束时间或减少均线周期')
    target_ma_shape = (target_ma - target_mean) / target_scale
    starts = np.arange(last_start + 1)
    if history_start is not None:
        starts = starts[df.index[starts] >= history_start]
    if history_end is not None:
        starts = starts[df.index[starts + window_size - 1] <= history_end]

    candidates = []
    valid_count = 0
    # Bounded chunks avoid materializing a 10000 x 500 x 4 array.
    for offset in range(0, len(starts), 256):
        positions = starts[offset:offset + 256]
        windows = prices[positions[:, None] + np.arange(window_size)]
        means = windows[:, :, 3].mean(axis=1)
        scales = windows[:, :, 3].std(axis=1)
        valid = scales > np.abs(means) * 1e-12
        ma_windows = ma_values[positions[:, None] + np.arange(window_size)]
        if ma_periods:
            valid &= np.isfinite(ma_windows).all(axis=(1, 2))
        ma_windows = ma_windows[valid]
        positions, windows, means, scales = positions[valid], windows[valid], means[valid], scales[valid]
        valid_count += len(positions)
        if not len(positions):
            continue
        shapes = (windows - means[:, None, None]) / scales[:, None, None]
        price_error = np.mean(np.sum((shapes - target_shape) ** 2 * WEIGHTS, axis=2), axis=1)
        if ma_periods:
            # Use the same price scale for candles and their MAs, preserving
            # both MA shape and price/MA location. Each selected MA has equal weight.
            ma_shapes = (ma_windows - means[:, None, None]) / scales[:, None, None]
            ma_error = np.mean((ma_shapes - target_ma_shape) ** 2, axis=(1, 2))
            distance = np.sqrt(0.5 * price_error + 0.5 * ma_error)
        else:
            distance = np.sqrt(price_error)
        scores = 100 * np.exp(-distance)
        candidates.extend((int(pos), float(score)) for pos, score in zip(positions, scores) if score >= min_similarity - 1e-9)

    candidates.sort(key=lambda item: (-item[1], item[0]))
    selected = []
    for pos, score in candidates:
        if any(abs(pos - previous[0]) < window_size for previous in selected):
            continue
        selected.append((pos, score))
        if len(selected) >= top_k:
            break

    matches = []
    for rank, (pos, score) in enumerate(selected, 1):
        history = df.iloc[pos:pos + window_size]
        mean, scale = float(history.Close.mean()), float(history.Close.std(ddof=0))
        match = segment(history, mean, scale)
        following = df.iloc[pos + window_size:pos + window_size + continuation_bars]
        match.update({
            'rank': rank, 'similarity': round(score, 2),
            'following': segment(following, mean, scale),
            'following_return_pct': round(float((following.Close.iloc[-1] / history.Close.iloc[-1] - 1) * 100), 4) if len(following) else None,
        })
        matches.append(match)

    return {
        'status': 'success', 'target': segment(target, target_mean, target_scale),
        'matches': matches, 'scanned_windows': valid_count,
        'qualifying_windows': len(candidates),
        'parameters': {'window_size': window_size, 'top_k': top_k,
                       'min_similarity': min_similarity, 'continuation_bars': continuation_bars,
                       'ma_periods': ma_periods},
        'method': ('开高低收按各窗口收盘均值和波动统一标准化，距离越小分数越高；收盘权重45%，开盘15%，最高最低各20%。' +
                   (f' 综合评分中 K 线占50%，所选均线（{"、".join(f"MA{p}" for p in ma_periods)}）合计占50%且等权；均线与价格共用标准化尺度，比较形态及相对位置，历史预热不足的窗口不参与排名。' if ma_periods else '')),
        'message': f'找到 {len(matches)} 段互不重叠的历史走势' if matches else '没有找到达到门槛的历史走势，可降低门槛或调整根数、范围。',
    }


def compare_market_candles(symbol, period='daily', data_provider='tqsdk', data_source='main', **parameters):
    explicit_contract = is_contract(symbol)
    if explicit_contract and (data_provider != 'tqsdk' or data_source != 'main'):
        raise ValueError('具体合约对比须使用天勤行情和具体合约口径')
    # The legacy loader may silently replace minute/weighted data. Do not allow
    # those ambiguous combinations in the shape-comparison feature.
    if data_provider == 'akshare' and (period != 'daily' or data_source != 'main'):
        raise ValueError('原有来源在 K 线对比中仅支持主力连续日线；分钟线或加权指数请选择天勤')
    df = fetch_data(symbol, period=period, market_type='futures',
                    data_provider=data_provider, data_source=data_source,
                    **({'cache_contract': True} if explicit_contract else {}))
    if df is None or df.empty:
        raise ValueError('未获取到行情，请检查品种、网络或天勤配置')
    df = df.sort_index().tail(10000).copy()
    if data_provider == 'akshare':
        now = pd.Timestamp.now(tz='Asia/Shanghai').tz_localize(None)
        df = df[df.index.normalize() + pd.Timedelta(hours=15, minutes=15) <= now]
    result = find_similar_candles(df, **parameters)
    result['data_info'] = {
        **df.attrs.get('data_info', {}), 'provider': data_provider,
        'provider_name': '天勤 TqSdk 免费版' if data_provider == 'tqsdk' else '新浪财经',
        'symbol': symbol, 'data_source': data_source, 'period': period,
        'bars': len(df), 'start': str(df.index.min()), 'end': str(df.index.max()),
    }
    return result
