"""TqSdk free rolling-series adapter. Credentials never leave the backend."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pandas as pd
import numpy as np
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERIES_LENGTH = 10000
PERIODS = {"daily": 86400, "1": 60, "5": 300, "15": 900, "30": 1800, "60": 3600}
EXCHANGES = {
    "SHFE": "CU AL ZN PB NI SN AU AG RB WR HC FU BU RU SP SS AO BR AD OP",
    "DCE": "M Y A B P C CS JD BB FB L V PP J JM I EG RR EB PG LH LG",
    "CZCE": "SR CF CY PM WH RI LR JR RS OI RM SF SM TA MA FG SA UR AP CJ PK PF SH PX PR",
    "CFFEX": "IF IC IH IM T TF TS TL",
    "INE": "SC NR LU BC EC",
    "GFEX": "SI LC PS",
}


def credentials():
    config = dotenv_values(PROJECT_ROOT / ".env")
    user = os.environ.get("TQ_USERNAME", config.get("TQ_USERNAME") or "").strip()
    password = os.environ.get("TQ_PASSWORD", config.get("TQ_PASSWORD") or "")
    return user, password


def provider_status():
    user, password = credentials()
    return {"configured": bool(user and password),
            "installed": importlib.util.find_spec("tqsdk") is not None,
            "series_length": SERIES_LENGTH}


def tq_symbol(symbol, data_source="main"):
    if data_source not in ("main", "weighted"):
        raise ValueError("不支持的天勤合约口径")
    # Accept only the project's main-contract convention or explicit futures.
    match = re.fullmatch(r"([A-Za-z]+)(\d+)", symbol)
    if not match:
        raise ValueError("天勤合约格式无效，请选择期货品种")
    product, suffix = match.group(1).upper(), match.group(2)
    exchange = next((ex for ex, products in EXCHANGES.items() if product in products.split()), None)
    if exchange is None:
        raise ValueError(f"天勤暂未配置品种 {product} 的交易所")
    product_code = product if exchange in ("CZCE", "CFFEX") else product.lower()
    if suffix == "0":
        kind = "i" if data_source == "weighted" else "m"
        return f"KQ.{kind}@{exchange}.{product_code}"
    if data_source == "weighted":
        raise ValueError("加权指数请使用品种主连代码，如 RB0")
    if exchange == "CZCE" and len(suffix) == 4:
        suffix = suffix[1:]
    if len(suffix) != (3 if exchange == "CZCE" else 4):
        raise ValueError("天勤具体合约月份格式无效")
    return f"{exchange}.{product_code}{suffix}"


def normalize_serial(serial, period, now=None):
    """Convert UTC nanoseconds to Beijing timestamps and exclude unfinished bars."""
    duration = PERIODS[period]
    df = pd.DataFrame(serial).copy()
    df = df[pd.to_numeric(df["datetime"], errors="coerce") > 0]
    timestamps = pd.to_datetime(df["datetime"].astype("int64"), unit="ns", utc=True).dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)
    df.index = pd.DatetimeIndex(timestamps)
    now = pd.Timestamp.now(tz="Asia/Shanghai").tz_localize(None) if now is None else pd.Timestamp(now)
    if now.tzinfo is not None:
        now = now.tz_convert("Asia/Shanghai").tz_localize(None)
    # Conservative completion boundary includes the latest domestic bond close.
    ends = df.index.normalize() + pd.Timedelta(hours=15, minutes=15) if period == "daily" else df.index + pd.Timedelta(seconds=duration)
    df = df[ends <= now]
    if period == "daily":
        df.index = df.index.normalize()
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume", "close_oi": "OpenInterest"})
    columns = ["Open", "High", "Low", "Close", "Volume", "OpenInterest"]
    df = df[columns].apply(pd.to_numeric, errors="coerce").dropna()
    if not np.isfinite(df.to_numpy()).all():
        raise ValueError("天勤返回了无效数值，已停止回测")
    if (df[["Open", "High", "Low", "Close"]] <= 0).any().any():
        raise ValueError("天勤返回了无效价格，已停止回测")
    if ((df.High < df[["Open", "Close", "Low"]].max(axis=1)) |
            (df.Low > df[["Open", "Close", "High"]].min(axis=1))).any():
        raise ValueError("天勤返回的高低价关系异常，已停止回测")
    return df[~df.index.duplicated(keep="last")].sort_index()


def run_worker(request):
    user, password = credentials()
    if not user or not password:
        raise ValueError("尚未配置天勤账号，请在项目根目录 .env 中填写 TQ_USERNAME 和 TQ_PASSWORD")
    if importlib.util.find_spec("tqsdk") is None:
        raise ValueError("尚未安装 TqSdk，请安装 server/requirements.txt 中的依赖")
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "core.tq_worker"], input=json.dumps(request),
            cwd=PROJECT_ROOT / "server", capture_output=True, text=True,
            encoding="utf-8", timeout=60,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        raise ValueError("天勤连接或取数超过 60 秒，请检查网络和账号权限") from None
    try:
        result = json.loads(completed.stdout)
    except (ValueError, TypeError):
        raise ValueError("天勤连接失败，请检查本机 SDK 和账号配置") from None
    if completed.returncode or "error" in result:
        raise ValueError(result.get("error", "天勤数据获取失败"))
    return result


def completed_weekly_bars(daily, now=None):
    weekly = daily.resample("W-FRI").agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last",
        "Volume": "sum", "OpenInterest": "last",
    }).dropna()
    now = pd.Timestamp.now(tz="Asia/Shanghai") if now is None else pd.Timestamp(now)
    if now.tzinfo is not None:
        now = now.tz_convert("Asia/Shanghai").tz_localize(None)
    return weekly[weekly.index + pd.Timedelta(hours=15, minutes=15) <= now]


def fetch_tq_data(symbol, period="daily", start_date=None, end_date=None, data_source="main"):
    if period not in PERIODS and period != "weekly":
        raise ValueError("天勤支持周线、日线及 1/5/15/30/60 分钟线")
    resolved = tq_symbol(symbol, data_source)
    source_period = "daily" if period == "weekly" else period
    result = run_worker({"action": "bars", "symbol": resolved, "period": source_period})
    df = normalize_serial(result["bars"], source_period)
    if period == "weekly":
        # Aggregate before date filtering so a midweek start cannot truncate OHLC.
        df = completed_weekly_bars(df)
    if df.empty:
        raise ValueError("天勤未返回有效的已完成 K 线")
    available_start, available_end = df.index.min(), df.index.max()
    if start_date:
        df = df[df.index >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df.index < pd.Timestamp(end_date) + pd.Timedelta(days=1)]
    if df.empty:
        raise ValueError(f"所选日期没有天勤数据。免费滚动窗口为 {available_start} 至 {available_end}；不会切换其他来源或周期")
    df.attrs["data_info"] = {
        "provider": "tqsdk", "provider_name": "天勤 TqSdk 免费版",
        "symbol": symbol, "resolved_symbol": resolved, "data_source": data_source,
        "period": period, "timezone": "Asia/Shanghai", "bars": len(df),
        "start": str(df.index.min()), "end": str(df.index.max()),
        "available_start": str(available_start), "available_end": str(available_end),
        "note": ("周线由最多 10000 根天勤日线按周五合成，排除未结束的交易周。"
                 if period == "weekly" else "近期滚动窗口，最多 10000 根；仅使用已完成 K 线，日期筛选按北京时间。"),
    }
    return df


def fetch_tq_quote(symbol, data_source="main"):
    resolved = tq_symbol(symbol, data_source)
    result = run_worker({"action": "quote", "symbol": resolved})
    return {"symbol": symbol, "price": result["price"], "date": result["date"],
            "data_provider": "tqsdk", "resolved_symbol": resolved}
