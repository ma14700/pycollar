"""Read-only GM historical data adapter; no trading functions are used."""
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import numpy as np
import pandas as pd
from dotenv import dotenv_values
from .tq_provider import EXCHANGES, completed_weekly_bars

ROOT = Path(__file__).resolve().parents[2]
GM_PYTHON = ROOT / '.venv' / 'gm-runtime' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
PERIODS = {'1': '60s', '5': '300s', '15': '900s', '30': '1800s', '60': '3600s', 'daily': '1d', 'weekly': '1d'}


def credential():
    return (os.environ.get('GM_TOKEN') or dotenv_values(ROOT / '.env').get('GM_TOKEN') or '').strip()


def provider_status():
    root = GM_PYTHON.parent.parent
    modules = [root / 'Lib' / 'site-packages' / 'gm' / 'api' / '__init__.py']
    modules.extend(root.glob('lib/python*/site-packages/gm/api/__init__.py'))
    return {'configured': bool(credential()), 'installed': GM_PYTHON.exists() and any(path.exists() for path in modules)}


def gm_symbol(symbol, data_source='main'):
    match = re.fullmatch(r'([A-Za-z]+)(\d+)', symbol)
    if not match or data_source not in ('main', 'weighted'):
        raise ValueError('掘金合约或口径无效')
    product, suffix = match[1].upper(), match[2]
    exchange = next((exchange for exchange, products in EXCHANGES.items() if product in products.split()), None)
    if not exchange:
        raise ValueError(f'掘金暂未配置品种 {product} 的交易所')
    if suffix == '0':
        return f'{exchange}.{product}{"99" if data_source == "weighted" else ""}'
    if data_source != 'main':
        raise ValueError('加权指数请选择期货品种')
    if len(suffix) != 4:
        raise ValueError('具体合约月份须为四位')
    if exchange == 'CZCE': suffix = suffix[1:]
    code = product if exchange in ('CZCE', 'CFFEX') else product.lower()
    return f'{exchange}.{code}{suffix}'


def run_worker(request):
    token = credential()
    if not token:
        raise ValueError('尚未配置掘金 Token，请在项目根目录 .env 设置 GM_TOKEN')
    if not GM_PYTHON.exists():
        raise ValueError('掘金 SDK 尚未安装，请运行 scripts/setup-gm.ps1')
    try:
        completed = subprocess.run([str(GM_PYTHON), str(ROOT / 'server/core/gm_worker.py')],
            input=json.dumps({**request, 'token': token}), text=True, encoding='utf-8',
            capture_output=True, timeout=120, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    except subprocess.TimeoutExpired:
        raise ValueError('掘金取数超过 120 秒，请检查终端连接或缩短时间范围') from None
    try:
        result = json.loads(completed.stdout)
    except (ValueError, TypeError):
        raise ValueError('掘金 SDK 启动失败，请检查终端及 SDK 安装') from None
    if completed.returncode or 'error' in result:
        raise ValueError(result.get('error', '掘金取数失败'))
    return result['rows']


def normalize(rows, period, now=None):
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError('掘金没有返回所选范围的 K 线')
    now = pd.Timestamp.now(tz='Asia/Shanghai') if now is None else pd.Timestamp(now)
    if now.tzinfo is None: now = now.tz_localize('Asia/Shanghai')
    ends = pd.to_datetime(df['eob'], utc=True).dt.tz_convert('Asia/Shanghai')
    starts = pd.to_datetime(df['bob'], utc=True).dt.tz_convert('Asia/Shanghai')
    if period in ('daily', 'weekly'):
        # Daily eob may be midnight; conservatively wait until the trading day closes.
        ends = ends.dt.normalize() + pd.Timedelta(hours=15, minutes=15)
        starts = ends.dt.normalize()
    df = df.loc[ends <= now].copy()
    starts = starts.loc[ends <= now]
    df.index = pd.DatetimeIndex(starts.dt.tz_localize(None))
    df = df.rename(columns={'open':'Open', 'high':'High', 'low':'Low', 'close':'Close', 'volume':'Volume', 'position':'OpenInterest'})
    columns = ['Open','High','Low','Close','Volume','OpenInterest']
    df = df[columns].apply(pd.to_numeric, errors='coerce').dropna()
    if not np.isfinite(df.to_numpy()).all() or (df[['Open','High','Low','Close']] <= 0).any().any():
        raise ValueError('掘金返回了无效价格，已停止回测')
    if ((df.High < df[['Open','Close','Low']].max(axis=1)) | (df.Low > df[['Open','Close','High']].min(axis=1))).any():
        raise ValueError('掘金返回的高低价关系异常，已停止回测')
    return df[~df.index.duplicated(keep='last')].sort_index()


def fetch_gm_data(symbol, period='daily', start_date=None, end_date=None, data_source='main', required_start_date=None):
    if period not in PERIODS:
        raise ValueError('掘金支持周线、日线及 1/5/15/30/60 分钟线')
    resolved = gm_symbol(symbol, data_source)
    now = pd.Timestamp.now(tz='Asia/Shanghai').tz_localize(None)
    start = pd.Timestamp(start_date) if start_date else now.normalize() - pd.Timedelta(days=150)
    end = min(pd.Timestamp(end_date) + pd.Timedelta(days=1), now) if end_date else now
    if start >= end: raise ValueError('所选时间范围没有已完成行情')
    request = {'action':'bars', 'symbol':resolved, 'frequency':PERIODS[period], 'start':start.isoformat(), 'end':end.isoformat()}
    clipped = False
    try:
        rows = run_worker(request)
    except ValueError as error:
        boundary = re.search(r'查询起始日期不早于\s*(\d{4}-\d{2}-\d{2})', str(error))
        if not boundary or not required_start_date or pd.Timestamp(required_start_date) < pd.Timestamp(boundary[1]):
            raise
        request['start'] = pd.Timestamp(boundary[1]).isoformat()
        rows = run_worker(request)
        clipped = True
    df = normalize(rows, period, now)
    if period == 'weekly': df = completed_weekly_bars(df, now)
    if df.empty: raise ValueError('掘金没有返回所选范围的已完成 K 线')
    if required_start_date and df.index.min() > pd.Timestamp(required_start_date) + pd.Timedelta(days=5):
        raise ValueError(f'掘金可用数据无法覆盖所选开始日期，最早为 {df.index.min()}')
    df.attrs['data_info'] = {'provider':'gm','provider_name':'掘金量化','symbol':symbol,
        'resolved_symbol':resolved,'data_source':data_source,'period':period,'timezone':'Asia/Shanghai',
        'bars':len(df),'start':str(df.index.min()),'end':str(df.index.max()),
        'note':'掘金终端历史行情；' + ('预热数据受账号权限限制，已从允许的最早日期开始。' if clipped else '日期范围及权限以实际返回为准。')}
    return df


def fetch_gm_quote(symbol, data_source='main'):
    resolved = gm_symbol(symbol, data_source)
    df = normalize(run_worker({'action':'quote','symbol':resolved}), 'daily')
    if df.empty: raise ValueError('掘金没有返回已完成的日线参考价格')
    return {'symbol':symbol,'price':float(df.Close.iloc[-1]),'date':str(df.index[-1]),
            'data_provider':'gm','resolved_symbol':resolved,'price_basis':'最近一根已完成日线收盘价'}
