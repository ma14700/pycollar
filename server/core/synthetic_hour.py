"""Build trading-time hourly candles from completed 5-minute source bars."""
import re
import numpy as np
import pandas as pd

# All times are Beijing local. Commodity day trading pauses at 10:15 and 11:30.
COMMODITY_DAY = [("09:00", "10:00", [("09:00", "10:00")]),
                 ("10:00", "11:15", [("10:00", "10:15"), ("10:30", "11:15")]),
                 ("11:15", "14:15", [("11:15", "11:30"), ("13:30", "14:15")]),
                 ("14:15", "15:00", [("14:15", "15:00")])]
STOCK_DAY = [("09:30", "10:30", [("09:30", "10:30")]), ("10:30", "11:30", [("10:30", "11:30")]),
             ("13:00", "14:00", [("13:00", "14:00")]), ("14:00", "15:00", [("14:00", "15:00")])]
FINANCIAL = {"IF", "IH", "IC", "IM"}
BONDS = {"T", "TF", "TS", "TL"}
NIGHT_1AM = {"CU", "AL", "ZN", "PB", "NI", "SN", "SS", "AO", "BC"}
NIGHT_230AM = {"AU", "AG", "SC"}


def synthesize_hour(frame, symbol, market_type='futures', provider='tqsdk', now=None):
    if frame is None or frame.empty:
        raise ValueError('合成60分钟线缺少5分钟行情')
    df = frame.copy()
    df.index = pd.DatetimeIndex(pd.to_datetime(df.index))
    if df.index.tz is not None:
        df.index = df.index.tz_convert('Asia/Shanghai').tz_localize(None)
    # TqSdk timestamps mark bar starts; Sina / AkShare minute data mark bar ends.
    if provider == 'akshare':
        df.index = df.index - pd.Timedelta(minutes=5)
    df = df.sort_index()
    if df.index.has_duplicates:
        raise ValueError('5分钟行情存在重复时间，无法安全合成')
    columns = ['Open', 'High', 'Low', 'Close', 'Volume', 'OpenInterest']
    for col in columns:
        if col not in df:
            if col in ('Volume', 'OpenInterest'):
                df[col] = 0
            else:
                raise ValueError('5分钟行情缺少开高低收，无法合成')
        df[col] = pd.to_numeric(df[col], errors='coerce')
    if not np.isfinite(df[columns].to_numpy()).all():
        raise ValueError('5分钟行情含无效数值，无法合成')
    if market_type not in ('stock', 'futures'):
        raise ValueError('当前市场不支持合成60分钟线')
    product_match = re.match(r'^([A-Za-z]+)', symbol)
    product = product_match.group(1).upper() if product_match else ''
    financial = market_type == 'stock' or product in FINANCIAL or product in BONDS
    schedule = list(STOCK_DAY if financial else COMMODITY_DAY)
    if product in BONDS and market_type == 'futures':
        schedule.append(('15:00','15:15',[('15:00','15:15')]))
    now = pd.Timestamp.now(tz='Asia/Shanghai').tz_localize(None) if now is None else pd.Timestamp(now)
    if now.tzinfo is not None:
        now = now.tz_convert('Asia/Shanghai').tz_localize(None)
    def at(day, value):
        hour, minute = map(int, value.split(':'))
        return day + pd.Timedelta(hours=hour, minutes=minute)
    records, skipped = [], 0
    def emit(start, end, sections):
        nonlocal skipped
        if end > now: return
        wanted = pd.DatetimeIndex(np.concatenate([pd.date_range(a, b, freq='5min', inclusive='left').to_numpy() for a,b in sections]))
        # Ignore entirely absent sessions; never manufacture bars across missing intervals.
        if not len(df.index.intersection(wanted)): return
        if not wanted.isin(df.index).all():
            if wanted.min() >= df.index.min() and wanted.max() <= df.index.max():
                raise ValueError(f'5分钟行情在 {start} 附近存在缺失，无法可靠合成60分钟K线')
            skipped += 1
            return
        part = df.loc[wanted]
        records.append((start, float(part.Open.iloc[0]), float(part.High.max()), float(part.Low.min()),
                        float(part.Close.iloc[-1]), float(part.Volume.sum()), float(part.OpenInterest.iloc[-1])))
    days = pd.date_range(df.index.min().normalize() - pd.Timedelta(days=1), df.index.max().normalize(), freq='D')
    for day in days:
        for start, end, sections in schedule:
            emit(at(day,start), at(day,end), [(at(day,a),at(day,b)) for a,b in sections])
        if market_type == 'futures' and not financial:
            end_hour = 26.5 if product in NIGHT_230AM else 25 if product in NIGHT_1AM else 23
            cursor = day + pd.Timedelta(hours=21)
            night_end = day + pd.Timedelta(hours=end_hour)
            while cursor < night_end:
                end = min(cursor + pd.Timedelta(hours=1), night_end)
                emit(cursor,end,[(cursor,end)])
                cursor = end
    if not records:
        raise ValueError('5分钟行情不足以合成完整的60分钟K线')
    result = pd.DataFrame(records,columns=['datetime',*columns]).set_index('datetime').sort_index()
    result.attrs = frame.attrs.copy()
    info = result.attrs.get('data_info', {}).copy()
    info.update(hourly_mode='trading_time', source_period='5', synthetic_skipped_bars=skipped,
                note=f'由5分钟行情按交易时段合成60分钟K线；跳过缺失或不完整的K线 {skipped} 根。')
    result.attrs['data_info'] = info
    return result
