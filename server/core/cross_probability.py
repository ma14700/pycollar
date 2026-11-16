"""Historical close-to-close outcomes between opposite moving-average crosses."""
import numpy as np
import pandas as pd

from .candle_compare import boundary
from .data_loader import fetch_data
from .market_cache import is_contract
from .contract_backtest import contract_window

PAIRS = {'20/55': (20, 55), '20/144': (20, 144), '55/144': (55, 144),
         '20/60': (20, 60), '60/144': (60, 144)}  # historical internal callers


def cross_signals(diff):
    """Recognize a real side change, including an equal-MA plateau, just once."""
    previous = diff.where(diff != 0).ffill().shift(1)
    # An initial fully warmed-up equality can establish the first departure.
    previous = previous.mask(previous.isna() & diff.shift(1).notna(), 0)
    golden = (previous <= 0) & (diff > 0)
    death = (previous >= 0) & (diff < 0)
    return golden.fillna(False).to_numpy(), death.fillna(False).to_numpy()


def point_profit_stats(changes):
    """Average profit / average absolute loss; flat samples do not enter either average."""
    changes = np.asarray(changes, dtype=float)
    profits, losses = changes[changes > 0], -changes[changes < 0]
    profit_count, loss_count = len(profits), len(losses)
    profit_sum, loss_sum = float(profits.sum()), float(losses.sum())
    avg_profit = profit_sum / profit_count if profit_count else None
    avg_loss = loss_sum / loss_count if loss_count else None
    ratio = avg_profit / avg_loss if avg_profit is not None and avg_loss is not None and avg_loss > 0 else None
    return {'gross_profit_points': profit_sum, 'gross_loss_points': loss_sum,
            'profit_count': profit_count, 'loss_count': loss_count,
            'avg_profit_points': avg_profit, 'avg_loss_points': avg_loss, 'profit_loss_ratio': ratio}


def _normalized_frame(df):
    """Normalize market timestamps before sorting and keep source metadata intact."""
    frame = df.copy()
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index, format='mixed')).as_unit('ns')
    if frame.index.tz is not None:
        frame.index = frame.index.tz_convert('Asia/Shanghai').tz_localize(None)
    return frame.sort_index()


def analyze_crosses(df, pairs, start=None, end=None, observation_bars=None, observation_delay=0, reverse_exit=False):
    if observation_bars is not None and (type(observation_bars) is not int or not 1 <= observation_bars <= 10000):
        raise ValueError('观察K线根数必须是1至10000的整数')
    if type(observation_delay) is not int or not 0 <= observation_delay <= 10000:
        raise ValueError('延时观察必须是0至10000的整数')
    if not pairs or any(pair not in PAIRS for pair in pairs):
        raise ValueError('请选择至少一个有效的均线组合')
    if df is None or df.empty or 'Close' not in df:
        raise ValueError('没有可用的收盘价行情')
    df = _normalized_frame(df)
    if df.index.hasnans or df.index.has_duplicates:
        raise ValueError('行情时间存在缺失或重复')
    close = pd.to_numeric(df.Close, errors='coerce')
    if not np.isfinite(close).all() or (close <= 0).any():
        raise ValueError('行情包含无效收盘价')
    start, end = boundary(start), boundary(end, end=True)
    if start is not None and end is not None and start > end:
        raise ValueError('开始时间不能晚于结束时间')
    averages = {period: close.rolling(period, min_periods=period).mean() for period in {n for pair in pairs for n in PAIRS[pair]}}
    output = []
    for pair in dict.fromkeys(pairs):
        fast, slow = PAIRS[pair]
        diff = averages[fast] - averages[slow]
        golden, death = cross_signals(diff)
        crosses = [(int(i), 'golden' if golden[i] else 'death') for i in np.flatnonzero(golden | death)]
        events, excluded, pending, expired = [], [], 0, 0
        for index, (i, direction) in enumerate(crosses):
            if (start is not None and df.index[i] < start) or (end is not None and df.index[i] > end):
                continue
            begin = i + observation_delay
            opposite = next((position for position, kind in crosses[index + 1:] if kind != direction), None)
            opposite = opposite if opposite is not None and (end is None or df.index[opposite] <= end) else None
            signal_info = {'direction': direction, 'signal': str(df.index[i]),
                           'next_opposite': str(df.index[opposite]) if opposite is not None else None}
            if (observation_bars is None or reverse_exit) and opposite is not None and opposite <= begin:
                expired += 1
                excluded.append({**signal_info, 'reason': '反向交叉不晚于观察起点'})
                continue
            target = begin + observation_bars if observation_bars is not None else None
            early_exit = opposite is not None and (target is None or (reverse_exit and opposite <= target))
            following = opposite if early_exit else target
            if following is None or following >= len(df) or (end is not None and df.index[following] > end):
                pending += 1
                excluded.append({**signal_info, 'reason': '观察尚未完成或超出分析结束时间'})
                continue
            j = following
            pct = (float(close.iloc[j]) / float(close.iloc[begin]) - 1) * 100
            events.append({**signal_info, 'signal_close': float(close.iloc[i]),
                           'start': str(df.index[begin]), 'end': str(df.index[j]),
                           'start_close': float(close.iloc[begin]), 'end_close': float(close.iloc[j]),
                           'bars': j-begin, 'exit_reason': 'reverse' if early_exit else 'horizon',
                           'return_pct': round(pct, 6), 'outcome': 'up' if pct > 0 else 'down' if pct < 0 else 'flat'})
        summary = {}
        for direction in ('golden', 'death'):
            rows = [event for event in events if event['direction'] == direction]
            counts = {outcome: sum(event['outcome'] == outcome for event in rows) for outcome in ('up', 'down', 'flat')}
            matching = counts['up' if direction == 'golden' else 'down']
            changes = [(event['end_close'] - event['start_close']) * (1 if direction == 'golden' else -1) for event in rows]
            summary[direction] = {'total': len(rows), **counts,
                                  'up_pct': round(counts['up'] / len(rows) * 100, 2) if rows else None,
                                  'match_pct': round(matching / len(rows) * 100, 2) if rows else None,
                                  **point_profit_stats(changes)}
        output.append({'pair': pair, 'summary': summary, 'pending': pending, 'expired': expired, 'events': events, 'excluded': excluded})
    return output


def optimize_cross_horizons(df, pairs, start=None, end=None, observation_delay=0, max_bars=200, reverse_exit=False):
    """Compare each horizon on its available completed signals; ties prefer fewer bars."""
    if type(max_bars) is not int or not 1 <= max_bars <= 1000:
        raise ValueError('量化搜索上限必须是1至1000的整数')
    if type(observation_delay) is not int or not 0 <= observation_delay <= 10000:
        raise ValueError('延时观察必须是0至10000的整数')
    if not pairs or any(pair not in PAIRS for pair in pairs):
        raise ValueError('请选择至少一个有效的均线组合')
    df = _normalized_frame(df)
    close = pd.to_numeric(df.Close, errors='coerce')
    if df.index.hasnans or df.index.has_duplicates or not np.isfinite(close).all() or (close <= 0).any():
        raise ValueError('行情时间或收盘价无效')
    start, end = boundary(start), boundary(end, end=True)
    if start is not None and end is not None and start > end:
        raise ValueError('开始时间不能晚于结束时间')
    values = close.to_numpy(dtype=float)
    end_index = len(df) - 1 if end is None else int(df.index.searchsorted(end, side='right')) - 1
    averages = {n: close.rolling(n, min_periods=n).mean().to_numpy() for n in {n for pair in pairs for n in PAIRS[pair]}}
    output = []
    for pair in dict.fromkeys(pairs):
        fast, slow = PAIRS[pair]
        delta = pd.Series(averages[fast] - averages[slow])
        golden, death = cross_signals(delta)
        for direction in ('golden', 'death'):
            signals = np.flatnonzero(golden if direction == 'golden' else death)
            if start is not None:
                signals = signals[df.index[signals] >= start]
            if end is not None:
                signals = signals[df.index[signals] <= end]
            starts = signals + observation_delay
            if reverse_exit:
                opposite = np.flatnonzero(death if direction == 'golden' else golden)
                indexes = np.searchsorted(opposite, signals, side='right')
                next_opposite = np.full(len(signals), len(df) + 10001, dtype=int)
                found = indexes < len(opposite)
                next_opposite[found] = opposite[indexes[found]]
            else:
                next_opposite = np.full(len(signals), len(df) + 10001, dtype=int)
            series, best = [], None
            for horizon in range(1, max_bars + 1):
                ends = np.minimum(starts + horizon, next_opposite)
                valid_mask = (ends <= end_index) & (next_opposite > starts)
                valid, valid_ends = starts[valid_mask], ends[valid_mask]
                total = len(valid)
                if total:
                    changes = values[valid_ends] - values[valid]
                    pnl = changes if direction == 'golden' else -changes
                    stats = point_profit_stats(pnl)
                    wins = stats['profit_count']
                    pct = round(100 * wins / total, 2)
                    row = {'bars': horizon, 'total': total, 'wins': wins, 'match_pct': pct, **stats}
                    if best is None or wins * best['total'] > best['wins'] * total:
                        best = row
                else:
                    row = {'bars': horizon, 'total': 0, 'wins': 0, 'match_pct': None, **point_profit_stats([])}
                series.append(row)
            output.append({'pair': pair, 'direction': direction, 'best': best, 'series': series})
    return output


def market_cross_probability(symbol, period, data_provider, data_source, pairs, start=None, end=None, observation_bars=None, observation_delay=0, optimize=False, max_search_bars=200, reverse_exit=False):
    contract = is_contract(symbol)
    if contract and (data_provider != 'tqsdk' or data_source != 'main'):
        raise ValueError('具体合约须使用天勤行情和具体合约口径')
    window = contract_window(symbol[-4:]) if contract else None
    if window:
        start, end = window['start_date'], window['end_date']
    if data_provider == 'akshare' and (period != 'daily' or data_source != 'main'):
        raise ValueError('原有来源仅支持主力连续日线')
    df = fetch_data(symbol, period=period, market_type='futures', data_provider=data_provider,
                    data_source=data_source, **({'cache_contract': True} if contract else {}))
    if df is None or df.empty:
        raise ValueError('未获取到行情，请检查品种、网络或天勤配置')
    df = _normalized_frame(df).tail(10000).copy()
    if data_provider == 'akshare':
        now = pd.Timestamp.now(tz='Asia/Shanghai').tz_localize(None)
        df = df[df.index.normalize() + pd.Timedelta(hours=15, minutes=15) <= now]
    groups = analyze_crosses(df, pairs, start, end, observation_bars, observation_delay, reverse_exit)
    chart_df = df.loc[df.index <= boundary(end, end=True)] if end else df
    chart = None
    if all(column in chart_df for column in ('Open', 'High', 'Low', 'Close')):
        ohlc = chart_df[['Open', 'Close', 'Low', 'High']].apply(pd.to_numeric, errors='coerce')
        ma = {str(n): ohlc['Close'].rolling(n, min_periods=n).mean() for n in (20, 55, 144)}
        number = lambda value: float(value) if pd.notna(value) and np.isfinite(value) else None
        chart = {'dates': chart_df.index.strftime('%Y-%m-%d %H:%M:%S').tolist(),
                 'ohlc': [[number(value) for value in row] for row in ohlc.to_numpy()],
                 'ma': {key: [number(value) for value in values] for key, values in ma.items()}}
    optimization = optimize_cross_horizons(df, pairs, start, end, observation_delay, max_search_bars, reverse_exit) if optimize else None
    if optimization is not None:
        best_groups = {}
        for item in optimization:
            if item['best'] is None:
                item['events'] = []
                continue
            key = (item['pair'], item['best']['bars'])
            if key not in best_groups:
                best_groups[key] = analyze_crosses(df, [item['pair']], start, end, key[1], observation_delay, reverse_exit)[0]
            item['events'] = [event for event in best_groups[key]['events'] if event['direction'] == item['direction']]
    return {'symbol': symbol, 'groups': groups, 'chart': chart, 'analysis_window': {'start': start, 'end': end, 'contract_window': bool(window)}, 'observation_bars': observation_bars, 'observation_delay': observation_delay, 'reverse_exit': reverse_exit, 'optimization': optimization, 'max_search_bars': max_search_bars if optimize else None, 'data_info': {**df.attrs.get('data_info', {}),
            'symbol': symbol, 'period': period, 'provider': data_provider, 'provider_name': df.attrs.get('data_info', {}).get('provider_name') or ('天勤 TqSdk 免费版' if data_provider == 'tqsdk' else '新浪财经'), 'data_source': data_source,
            'bars': len(df), 'start': str(df.index.min()), 'end': str(df.index.max())}}
