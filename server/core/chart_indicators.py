"""Compute chart display indicators (MA, MACD, DKX) aligned to the visible bar window."""
import logging

import backtrader as bt
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def build_kline_payload(df_raw, df_kline, strat, strategy_name, strategy_params, final_logs):
    """Build OHLCV payload with moving averages, MACD, and DKX aligned to df_kline."""
    kline_data = {
        "dates": df_kline.index.strftime('%Y-%m-%d %H:%M:%S').tolist(),
        "values": df_kline[['Open', 'Close', 'Low', 'High']].values.tolist(),
        "volumes": df_kline['Volume'].tolist() if 'Volume' in df_kline.columns else [],
    }

    close_series = df_raw['Close'].astype(float)
    ma5 = close_series.rolling(window=5, min_periods=1).mean().reindex(df_kline.index)
    ma10 = close_series.rolling(window=10, min_periods=1).mean().reindex(df_kline.index)
    ma20 = close_series.rolling(window=20, min_periods=1).mean().reindex(df_kline.index)
    ma55 = close_series.rolling(window=55, min_periods=1).mean().reindex(df_kline.index)
    ma144 = close_series.rolling(window=144, min_periods=144).mean().reindex(df_kline.index)
    kline_data['ma'] = {
        "ma5": ma5.round(2).tolist(),
        "ma10": ma10.round(2).tolist(),
        "ma20": ma20.round(2).tolist(),
        "ma55": ma55.round(2).tolist(),
        "ma144": [round(float(value), 2) if pd.notna(value) else None for value in ma144],
    }

    for key, attribute, period_key in [('fast', 'ma_fast', 'fast_period'),
                                        ('slow', 'ma_slow', 'slow_period'),
                                        ('exit', 'ma_exit', 'exit_period')]:
        indicator = getattr(strat, attribute, None)
        if indicator is None and key == 'slow':
            indicator = getattr(strat, 'ma_entry', None)
        if indicator is not None:
            values = pd.Series(list(indicator.array), index=df_raw.index).reindex(df_kline.index)
            label = 'EMA' if isinstance(indicator, bt.ind.EMA) else 'MA'
            p = getattr(strat.p, period_key)
            kline_data['ma'][f'strategy_{key}'] = [round(float(v), 2) if pd.notna(v) else None for v in values]
            kline_data['ma'][f'strategy_{key}_period'] = p
            kline_data['ma'][f'strategy_{key}_label'] = f'{label}{p}'
    if getattr(strat, 'ma', None) is not None and hasattr(strat.p, 'ma_period'):
        values = pd.Series(list(strat.ma.array), index=df_raw.index).reindex(df_kline.index)
        kline_data['ma']['strategy_fast'] = [round(float(v), 2) if pd.notna(v) else None for v in values]
        kline_data['ma']['strategy_fast_period'] = strat.p.ma_period
        kline_data['ma']['strategy_fast_label'] = f'MA{strat.p.ma_period}'

    try:
        fast_period = int(strategy_params.get('macd_fast', 12))
        slow_period = int(strategy_params.get('macd_slow', 26))
        signal_period = int(strategy_params.get('macd_signal', 9))
        exp1 = close_series.ewm(span=fast_period, adjust=False).mean()
        exp2 = close_series.ewm(span=slow_period, adjust=False).mean()
        dif = exp1 - exp2
        dea = dif.ewm(span=signal_period, adjust=False).mean()
        kline_data['macd'] = {
            "dif": dif.reindex(df_kline.index).tolist(),
            "dea": dea.reindex(df_kline.index).tolist(),
            "hist": ((dif - dea) * 2).reindex(df_kline.index).tolist(),
            "periods": [fast_period, slow_period, signal_period],
        }
    except Exception:
        logger.exception("MACD display calculation failed")
        final_logs.append("指标显示提示：MACD 计算失败，详情请查看后端日志。")
        kline_data['macd'] = None

    if strategy_name == 'MA20MA60DailyMACDStrategy':
        actual_dif = pd.Series(list(strat.daily_dif.array), index=df_raw.index).reindex(df_kline.index)
        actual_dea = pd.Series(list(strat.daily_dea.array), index=df_raw.index).reindex(df_kline.index)
        kline_data['macd'] = {
            key: [float(value) if pd.notna(value) else None for value in series]
            for key, series in [('dif', actual_dif), ('dea', actual_dea), ('hist', 2 * (actual_dif - actual_dea))]
        }

    if strategy_name in ['DKXStrategy', 'DKXPartialTakeProfitStrategy', 'DKXFixedTPSLStrategy']:
        try:
            dkx_period = int(strategy_params.get('dkx_period', 20))
            dkx_ma_period = int(strategy_params.get('dkx_ma_period', 10))
            mid = (3 * df_raw['Close'] + df_raw['Low'] + df_raw['Open'] + df_raw['High']) / 6.0
            dkx_values = mid.rolling(window=dkx_period).apply(
                lambda x: np.dot(x, np.arange(1, dkx_period + 1)) / (dkx_period * (dkx_period + 1) / 2),
                raw=True,
            )
            madkx_values = dkx_values.rolling(window=dkx_ma_period).mean()
            kline_data['dkx'] = {
                "dkx": dkx_values.reindex(df_kline.index).tolist(),
                "madkx": madkx_values.reindex(df_kline.index).tolist(),
            }
        except Exception:
            logger.exception("DKX display calculation failed")
            final_logs.append("指标显示提示：DKX 计算失败，详情请查看后端日志。")
            kline_data['dkx'] = None

    return kline_data
