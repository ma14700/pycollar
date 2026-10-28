"""On-demand SQLite storage for completed contract candles and catalog responses."""
from dataclasses import dataclass
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import threading
import time

import numpy as np
import pandas as pd


CACHE_DB_PATH = Path(__file__).resolve().parents[1] / 'market_cache.sqlite3'
COLUMNS = ['Open', 'High', 'Low', 'Close', 'Volume', 'OpenInterest']
LOWER_BOUND, UPPER_BOUND = -(2 ** 62), 2 ** 62
_locks, _locks_guard = {}, threading.Lock()


def _lock(key):
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


def is_contract(symbol, market_type='futures', data_source='main'):
    return market_type == 'futures' and data_source == 'main' and bool(
        re.fullmatch(r'[A-Za-z]+\d{2}(0[1-9]|1[0-2])', symbol))


def _timestamp(value):
    stamp = pd.Timestamp(value)
    return stamp.tz_convert('Asia/Shanghai').tz_localize(None) if stamp.tzinfo else stamp


def _seconds(value):
    return int(_timestamp(value).value // 10 ** 9)


def _now():
    return pd.Timestamp.now(tz='Asia/Shanghai').tz_localize(None)


def _cutoff(now, period):
    if period == 'daily':
        return now.normalize() + pd.Timedelta(days=int(now >= now.normalize() + pd.Timedelta(hours=15, minutes=15)))
    if period == 'weekly':
        friday = now.normalize() + pd.Timedelta(days=4 - now.weekday())
        if now < friday + pd.Timedelta(hours=15, minutes=15):
            friday -= pd.Timedelta(days=7)
        return friday + pd.Timedelta(days=1)
    # Minute bars may start at session offsets (e.g. a 60m bar at 10:30).
    # Advance the coverage frontier as those bars finish, not at wall-clock hours.
    return now.floor('min') - pd.Timedelta(minutes=int(period)) + pd.Timedelta(minutes=1)


def _terminal(symbol, now):
    month = symbol[-4:]
    year, number = 2000 + int(month[:2]), int(month[2:])
    next_month = pd.Timestamp(year=year + (number == 12), month=number % 12 + 1, day=1)
    return now >= next_month


def _completed(frame, period, now):
    if frame is None or frame.empty:
        raise ValueError('第三方未返回有效合约行情，未写入本地缓存')
    result = frame.copy()
    result.index = pd.DatetimeIndex([_timestamp(value) for value in result.index])
    complete = (result.index < _cutoff(now, period) if period in ('daily', 'weekly')
                else result.index + pd.Timedelta(minutes=int(period)) <= now)
    result = result.loc[complete].copy()
    if 'OpenInterest' not in result:
        result['OpenInterest'] = 0
    result = result[COLUMNS].apply(pd.to_numeric, errors='coerce')
    if result.empty or not np.isfinite(result.to_numpy()).all():
        raise ValueError('合约行情为空或包含无效数值，未写入本地缓存')
    if ((result[['Open', 'High', 'Low', 'Close']] <= 0).any().any()
            or (result.High < result[['Open', 'Close', 'Low']].max(axis=1)).any()
            or (result.Low > result[['Open', 'Close', 'High']].min(axis=1)).any()):
        raise ValueError('合约行情价格关系异常，未写入本地缓存')
    result = result[~result.index.duplicated(keep='first')].sort_index()
    result.attrs = frame.attrs.copy()
    return result


@dataclass
class ResourceValue:
    data: object
    ttl: float
    fallback: bool = False


class MarketCache:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else CACHE_DB_PATH

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute('PRAGMA journal_mode=WAL')
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS contract_candles (
                provider TEXT NOT NULL, symbol TEXT NOT NULL, period TEXT NOT NULL,
                timestamp INTEGER NOT NULL, open REAL NOT NULL, high REAL NOT NULL,
                low REAL NOT NULL, close REAL NOT NULL, volume REAL NOT NULL, open_interest REAL NOT NULL,
                PRIMARY KEY(provider, symbol, period, timestamp));
            CREATE TABLE IF NOT EXISTS candle_coverage (
                id INTEGER PRIMARY KEY, provider TEXT NOT NULL, symbol TEXT NOT NULL, period TEXT NOT NULL,
                lower_bound INTEGER NOT NULL, upper_bound INTEGER NOT NULL,
                first_bar INTEGER NOT NULL, last_bar INTEGER NOT NULL, bar_count INTEGER NOT NULL,
                metadata TEXT NOT NULL, checked_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS candle_coverage_lookup ON candle_coverage(provider, symbol, period);
            CREATE TABLE IF NOT EXISTS resource_cache (
                key TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at REAL NOT NULL);
        ''')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _state(self, connection, key):
        rows = connection.execute('''SELECT lower_bound, upper_bound, first_bar, last_bar, bar_count, metadata
            FROM candle_coverage WHERE provider=? AND symbol=? AND period=? ORDER BY id''', key).fetchall()
        intervals, metadata = [], {}
        for lower, upper, first, last, count, payload in rows:
            actual = connection.execute('''SELECT COUNT(*) FROM contract_candles
                WHERE provider=? AND symbol=? AND period=? AND timestamp BETWEEN ? AND ?''', (*key, first, last)).fetchone()[0]
            if actual == count:
                intervals.append((lower, upper))
                metadata.update(json.loads(payload))
        merged = []
        for lower, upper in sorted(intervals):
            if merged and lower <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(upper, merged[-1][1]))
            else:
                merged.append((lower, upper))
        return merged, metadata

    def _covered_interval(self, intervals, start, end):
        lower = min(_seconds(start), end) if start is not None else None
        return next(((left, right) for left, right in reversed(intervals)
                     if right >= end and (left <= lower if lower is not None else left < end)), None)

    def candles(self, provider, symbol, period, loader, start_date=None, end_date=None, required_start_date=None,
                full_series=False):
        if not is_contract(symbol):
            raise ValueError('本地行情缓存只接受具体期货合约')
        key = (provider, symbol.upper(), str(period))
        with _lock((str(self.path.resolve()), *key)):
            now = _now()
            cutoff = _seconds(_cutoff(now, period))
            end = min(_seconds(_timestamp(end_date) + pd.Timedelta(days=1)), cutoff) if end_date else cutoff
            required_start = required_start_date if required_start_date is not None else start_date
            with self._connect() as connection:
                intervals, metadata = self._state(connection, key)
                covered = self._covered_interval(intervals, required_start, end)
                hit = covered is not None
                status = 'hit'
                downloaded = 0
                if not hit:
                    status = 'partial' if intervals else 'miss'
                    fresh = _completed(loader(), period, now)
                    downloaded = len(fresh)
                    info = fresh.attrs.get('data_info', {}).copy()
                    # Each loader returns its complete available rolling series, before date slicing.
                    first, last = _seconds(fresh.index.min()), _seconds(fresh.index.max())
                    lower = LOWER_BOUND if info.get('history_complete') else first
                    upper = UPPER_BOUND if _terminal(symbol, now) else cutoff
                    records = [(*key, _seconds(date), *map(float, row))
                               for date, row in zip(fresh.index, fresh[COLUMNS].itertuples(index=False, name=None))]
                    # Closed historical bars are immutable; repeated responses cannot overwrite them.
                    connection.executemany('INSERT OR IGNORE INTO contract_candles VALUES (?,?,?,?,?,?,?,?,?,?)', records)
                    count = connection.execute('''SELECT COUNT(*) FROM contract_candles
                        WHERE provider=? AND symbol=? AND period=? AND timestamp BETWEEN ? AND ?''', (*key, first, last)).fetchone()[0]
                    connection.execute('''INSERT INTO candle_coverage
                        (provider,symbol,period,lower_bound,upper_bound,first_bar,last_bar,bar_count,metadata,checked_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?)''', (*key, lower, upper, first, last, count,
                                                          json.dumps(info, ensure_ascii=False), time.time()))
                    connection.commit()
                    intervals, metadata = self._state(connection, key)
                    covered = self._covered_interval(intervals, required_start, end)
                    if covered is None:
                        raise ValueError('本地及第三方合约行情仍未完整覆盖所选区间，请缩短时间范围或更换周期；不会使用其他合约补齐')
                # Never concatenate disconnected rolling windows into indicator warmup.
                where = 'provider=? AND symbol=? AND period=? AND timestamp>=? AND timestamp<?'
                parameters = [*key, *covered]
                first, last = connection.execute(f'''SELECT MIN(timestamp), MAX(timestamp) FROM contract_candles
                    WHERE {where}''', parameters).fetchone()
                if start_date and not full_series:
                    where += ' AND timestamp>=?'
                    parameters.append(_seconds(start_date))
                if end_date and not full_series:
                    where += ' AND timestamp<?'
                    parameters.append(_seconds(_timestamp(end_date) + pd.Timedelta(days=1)))
                rows = connection.execute(f'''SELECT timestamp,open,high,low,close,volume,open_interest
                    FROM contract_candles WHERE {where} ORDER BY timestamp''', parameters).fetchall()
            frame = pd.DataFrame([row[1:] for row in rows], columns=COLUMNS,
                                 index=pd.DatetimeIndex(pd.to_datetime([row[0] for row in rows], unit='s')))
            metadata.update(cache_status=status, cache_downloaded_bars=downloaded,
                            history_complete=covered[0] == LOWER_BOUND,
                            available_start=str(pd.Timestamp(first, unit='s')), available_end=str(pd.Timestamp(last, unit='s')))
            frame.attrs['data_info'] = metadata
            return frame

    def resource(self, key, loader, ttl=21600):
        with _lock((str(self.path.resolve()), 'resource', key)):
            with self._connect() as connection:
                row = connection.execute('SELECT payload, expires_at FROM resource_cache WHERE key=?', (key,)).fetchone()
                if row and row[1] > time.time():
                    return json.loads(row[0])
                try:
                    value = loader()
                except Exception:
                    if row:
                        connection.execute('UPDATE resource_cache SET expires_at=? WHERE key=?', (time.time() + 60, key))
                        return json.loads(row[0])
                    raise
                if isinstance(value, ResourceValue):
                    data, ttl = value.data, value.ttl
                    if value.fallback and row:
                        data = json.loads(row[0])
                else:
                    data = value
                payload = json.dumps(data, ensure_ascii=False)
                connection.execute('INSERT OR REPLACE INTO resource_cache VALUES (?,?,?)', (key, payload, time.time() + ttl))
                return json.loads(payload)
