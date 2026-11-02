"""Causal alignment of a separate daily MACD onto the selected trading bars."""
import numpy as np
import pandas as pd


def seeded_ema(series, period):
    result = pd.Series(np.nan, index=series.index)
    values = series.dropna()
    if len(values) < period:
        return result
    start = values.index[period - 1]
    tail = series.loc[start:].copy()
    tail.iloc[0] = values.iloc[:period].mean()
    result.loc[start:] = tail.ewm(span=period, adjust=False).mean()
    return result


def align_daily_macd(bars, daily, period, market_type='futures', history_start=None):
    if daily is None or daily.empty or 'Close' not in daily:
        raise ValueError('日线MACD过滤需要独立日线行情，日线取数失败，已停止本项回测')
    daily = daily.copy().sort_index()
    daily.index = pd.DatetimeIndex(daily.index)
    if daily.index.tz is not None:
        daily.index = daily.index.tz_convert('Asia/Shanghai').tz_localize(None)
    if daily.index.has_duplicates:
        raise ValueError('日线MACD行情日期重复，无法确认过滤状态')
    if history_start:
        first = pd.Timestamp(history_start)
        if daily.index.min() > first or first not in daily.index:
            raise ValueError('分析时的日线历史起点已超出行情窗口，请重新分析')
        daily = daily.loc[daily.index >= first]
    close_time = pd.Timedelta(hours=15, minutes=15 if market_type == 'futures' else 0)
    # Futures use a conservative completion boundary that also covers bond futures.
    decisions = bars.index.normalize() + close_time if period == 'weekly' else bars.index + pd.Timedelta(minutes=int(period))
    available_at = daily.index.normalize() + close_time
    daily = daily.loc[available_at <= decisions.max()]
    available_at = daily.index.normalize() + close_time
    close = pd.to_numeric(daily.Close, errors='coerce')
    if not np.isfinite(close.to_numpy()).all() or (close <= 0).any():
        raise ValueError('日线MACD行情包含无效收盘价，无法计算过滤状态')
    if len(daily) < 34:
        raise ValueError('日线MACD预热不足：至少需要34根已完成日线，请扩大日线历史范围')
    dif = seeded_ema(close, 12) - seeded_ema(close, 26)
    dea = seeded_ema(dif, 9)
    source = pd.DataFrame({'available_at': available_at, 'daily_dif': dif.to_numpy(), 'daily_dea': dea.to_numpy(),
                           'daily_macd_date': daily.index.strftime('%Y-%m-%d')})
    matched = pd.merge_asof(pd.DataFrame({'decision': decisions}), source,
                           left_on='decision', right_on='available_at', direction='backward')
    if not matched.daily_dea.notna().any():
        raise ValueError('所选行情范围内无已完成且预热充分的日线MACD数据')
    result = bars.copy()
    result['daily_dif'] = matched.daily_dif.to_numpy()
    result['daily_dea'] = matched.daily_dea.to_numpy()
    result['daily_macd_date'] = matched.daily_macd_date.to_numpy()
    info = dict(result.attrs.get('data_info', {}))
    info.update(daily_macd_history_start=str(daily.index.min()), macd_period='daily')
    info['note'] = (info.get('note', '') + ' MACD过滤使用同合约独立日线，只关联信号时已完成的日线；日线预热不足的信号不开仓。').strip()
    result.attrs['data_info'] = info
    return result
