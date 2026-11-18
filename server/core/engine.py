import backtrader as bt
import pandas as pd
import numpy as np
import datetime
import logging
from .data_loader import fetch_data
from . import strategy
from .parameters import execution_options, filter_strategy_params
from .strategy_logging import make_logging_strategy
from .result_window import result_window, timestamp
from .constants import get_multiplier
from .contract_backtest import contract_scope
from .execution_delay import SignalDelayBroker, execution_delay_params
from .symbol_scan import ScanBroker
from .daily_macd import align_daily_macd
from .chart_indicators import build_kline_payload
from .accounting import (configure_accounting, closed_trade_stats, equity_statistics,
                         AccountEquity, COMMISSION_RATE, METRICS_VERSION)

logger = logging.getLogger(__name__)


class StrategyData(bt.feeds.PandasData):
    lines = ('ma_fast', 'ma_slow',)
    params = (
        ('ma_fast', 'ma_fast'),
        ('ma_slow', 'ma_slow'),
    )

class DailyMACDStrategyData(StrategyData):
    lines = ('daily_dif', 'daily_dea',)
    params = (('daily_dif', 'daily_dif'), ('daily_dea', 'daily_dea'))

class BacktestEngine:
    def _filter_params(self, StrategyClass, params):
        return filter_strategy_params(StrategyClass, params)

    def run(self, symbol, period, strategy_params, initial_cash=1000000.0, start_date=None, end_date=None, strategy_name='TrendFollowingStrategy', market_type='futures', data_source='main', data_provider='akshare', as_of=None, history_start=None, contract_month=None, daily_history_start=None, synthesize_60=False, scan_window=None):
        strategy_params = strategy_params.copy()
        contract_info = None
        try:
            if contract_month:
                contract_info = contract_scope(symbol, contract_month, market_type, data_provider, data_source)
                symbol, start_date, end_date = (contract_info[key] for key in ('symbol', 'start_date', 'end_date'))
            initial_cash = float(initial_cash)
            if not np.isfinite(initial_cash) or initial_cash <= 0:
                raise ValueError('初始资金必须为大于 0 的有限数字')
            delay_params = execution_delay_params(strategy_params)
            start = timestamp(start_date, '开始日期') if start_date else None
            end = timestamp(end_date, '结束日期') if end_date else None
            if start is not None and end is not None and start > end:
                raise ValueError('开始日期不能晚于结束日期')
        except (ValueError, TypeError) as error:
            return {"error": str(error)}
        # Strategy classes stay stable across concurrent requests; reload via service restart.
        
        # 获取策略类
        if not hasattr(strategy, strategy_name):
            return {"error": f"未在代码中找到策略类 '{strategy_name}'。"}
        
        StrategyClass = getattr(strategy, strategy_name)
        try:
            options = execution_options(strategy_params)
            strategy_params = {**dict(StrategyClass.params._getitems()),
                               **self._filter_params(StrategyClass, strategy_params)}
        except (ValueError, TypeError) as error:
            return {"error": f"策略参数无效: {error}"}

        LoggingStrategy = make_logging_strategy(StrategyClass, start_date, market_type)

        cerebro = bt.Cerebro()
        broker_class = ScanBroker if scan_window is not None else SignalDelayBroker
        cerebro.setbroker(broker_class(**delay_params))
        try:
            configure_accounting(cerebro.broker, strategy_params, market_type)
        except (ValueError, TypeError) as error:
            return {"error": str(error)}
        
        # 检查是否开启“开仓最优模式” (Optimal Entry)
        # 如果开启，启用 cheat_on_open 以便能在当前 K 线上以 Limit 价格成交
        # NOTE: Remove from params to avoid passing to strategy __init__
        if options['optimal_entry']:
            cerebro.broker.set_coo(True)
            print("DEBUG: Optimal Entry Mode Enabled (Cheat On Open = True)")
        
        # 1. 加载数据
        data_warning = None
        try:
            # 自动调整开始日期以包含预热期 (日线与分钟线均尝试预热)
            # 这样可以防止因数据过短导致指标无法计算
            fetch_start_date = start_date
            if start_date:
                warmup_days = 432 if period == 'daily' else 150
                if 'slow_period' in strategy_params:
                    try:
                        slow_p = int(strategy_params['slow_period'])
                        warmup_days = max(warmup_days, slow_p * 3)
                    except (ValueError, TypeError):
                        pass

                # 如果是周线，需要大幅增加预热天数 (一周7天，放大倍数)
                if period == 'weekly':
                    warmup_days = warmup_days * 7
                    print(f"检测到周线模式，自动放大预热天数至: {warmup_days} 天")

                req_dt = pd.to_datetime(start_date)
                fetch_start_dt = req_dt - pd.Timedelta(days=warmup_days)
                fetch_start_date = fetch_start_dt.strftime('%Y-%m-%d')
                print(f"为了指标预热，自动调整请求开始日期: {start_date} -> {fetch_start_date}")

            # 将 start_date 注入到策略参数中，用于严格控制交易开始时间
            # 这样策略在 fetch_start_date 开始运行计算指标，但在 start_date 之前不进行交易
            strategy_params['start_date'] = start_date
            strategy_params['end_date'] = end_date # 注入结束日期，用于强制平仓

            df_raw = fetch_data(symbol=symbol, period=period, market_type=market_type, start_date=fetch_start_date, end_date=end_date, data_source=data_source, data_provider=data_provider,
                                cache_contract=True, required_start_date=start_date,
                                **({'synthesize_60': True} if synthesize_60 and period == '60' else {}))
            if df_raw is not None:
                df_raw = df_raw.copy()
                if contract_info:
                    df_raw = df_raw.loc[df_raw.index < pd.Timestamp(end_date) + pd.Timedelta(days=1)].copy()
                if as_of:
                    last_bar = pd.to_datetime(as_of)
                    df_raw = df_raw.loc[df_raw.index <= last_bar].copy()
                    if df_raw.empty or df_raw.index.max() != last_bar:
                        raise ValueError('分析时的最后一根 K 线已不在当前行情中，请重新分析')
                if history_start and not df_raw.empty:
                    first_bar = pd.to_datetime(history_start)
                    if first_bar not in df_raw.index:
                        raise ValueError('分析时的历史起点已超出当前行情窗口，请重新分析后查看详情')
                    df_raw = df_raw.loc[df_raw.index >= first_bar].copy()
            
            # 检查数据是否被截断 (数据源起始时间晚于请求时间 2 天以上)
            if start_date and df_raw is not None and not df_raw.empty:
                req_start = pd.to_datetime(start_date)
                data_start = df_raw.index.min()
                if data_start > req_start + pd.Timedelta(days=5): # 放宽到5天
                    if data_provider in ('tqsdk', 'gm') and not (contract_info and df_raw.attrs.get('data_info', {}).get('history_complete')):
                        label = '天勤免费滚动窗口' if data_provider == 'tqsdk' else '掘金可用行情'
                        raise ValueError(f'{label}无法覆盖所选开始日期 {start_date}，当前最早数据为 {data_start}。请缩短范围或清空日期使用近期窗口。')
                    data_warning = (f"【合约行情】{symbol} 的完整可用历史始于 {data_start.strftime('%Y-%m-%d')}，所选月份范围按实际行情回测。"
                                    if contract_info and df_raw.attrs.get('data_info', {}).get('history_complete') else
                                    f"【数据警告】数据源限制: 只能获取到 {data_start.strftime('%Y-%m-%d')} 之后的数据 (请求开始: {start_date})。免费接口通常仅提供最近约1000根K线(分钟级)。")
                    print(data_warning)
                    
        except ValueError as ve:
            # 捕获数据加载中抛出的已知错误（如日期范围不匹配）
            return {"error": str(ve)}
        except Exception as e:
            logger.exception("Market data retrieval failed")
            return {"error": "数据获取失败，请稍后重试或查看后端日志"}
            
        if df_raw is None or df_raw.empty:
            return {"error": "未找到该品种的数据，请检查代码或日期范围"}

        if contract_info and not ((df_raw.index >= pd.Timestamp(start_date)) &
                                  (df_raw.index < pd.Timestamp(end_date) + pd.Timedelta(days=1))).any():
            return {"error": f"{symbol} 在 {start_date} 至 {end_date} 内尚无可用行情，无法回测该合约"}

        history_requirement = getattr(StrategyClass, 'required_bars', None)
        if callable(history_requirement):
            required_bars = history_requirement(strategy_params)
            if len(df_raw) < required_bars:
                return {"error": f"该策略至少需要 {required_bars} 根已完成 K 线用于均线与交叉确认，当前仅有 {len(df_raw)} 根，请扩大数据范围或更换周期",
                        **({'status': 'insufficient_history'} if scan_window is not None else {})}
            
        if strategy_name == 'MA20MA60DailyMACDStrategy' and period != 'daily':
            try:
                daily = fetch_data(symbol=symbol, period='daily', market_type=market_type,
                                   data_provider=data_provider, data_source=data_source, start_date=None,
                                   end_date=end_date, cache_contract=True)
                df_raw = align_daily_macd(df_raw, daily, period, market_type, daily_history_start)
            except Exception as error:
                return {"error": f"日线MACD过滤数据获取或计算失败: {error}"}

        # 转换 timeframe
        if period == 'weekly':
            timeframe = bt.TimeFrame.Weeks
            compression = 1
        elif period == 'daily':
            timeframe = bt.TimeFrame.Days
            compression = 1
        else:
            timeframe = bt.TimeFrame.Minutes
            compression = int(period)
        
        # 检查数据列
        if 'OpenInterest' not in df_raw.columns and 'hold' in df_raw.columns:
             df_raw.rename(columns={'hold': 'OpenInterest'}, inplace=True)

        # --- 预计算策略所需的 MA 数据 (支持 min_periods=1 以消除预热期) ---
        fast_p = 20
        slow_p = 55
        
        # 根据策略类型和参数确定周期
        if 'fast_period' in strategy_params:
            fast_p = int(strategy_params['fast_period'])
        elif strategy_name == 'TrendFollowingStrategy':
            fast_p = 10
            
        if 'slow_period' in strategy_params:
            slow_p = int(strategy_params['slow_period'])
        elif strategy_name == 'TrendFollowingStrategy':
            slow_p = 30
            
        # 计算并添加到 DataFrame
        if 'Close' in df_raw.columns:
            df_raw['ma_fast'] = df_raw['Close'].rolling(window=fast_p, min_periods=1).mean()
            df_raw['ma_slow'] = df_raw['Close'].rolling(window=slow_p, min_periods=1).mean()
            # 确保没有 NaN
            df_raw['ma_fast'] = df_raw['ma_fast'].bfill()
            df_raw['ma_slow'] = df_raw['ma_slow'].bfill()

        # 使用自定义 DataFeed
        FeedClass = DailyMACDStrategyData if 'daily_dif' in df_raw else StrategyData
        data = FeedClass(dataname=df_raw, timeframe=timeframe, compression=compression)
        cerebro.adddata(data)
        
        # 2. 添加策略
        # Retain the same multiplier used by broker accounting and statistics.
        if 'contract_multiplier' in strategy_params:
            strategy_params['contract_multiplier'] = float(strategy_params['contract_multiplier'])
            
        # 过滤掉不属于策略的参数
        filtered_params = self._filter_params(StrategyClass, strategy_params)

        cerebro.addstrategy(LoggingStrategy, **filtered_params)
        
        # 3. 资金设置
        cerebro.broker.setcash(initial_cash)
        
        # 4. 添加分析器
        if scan_window is None:
            cerebro.addanalyzer(AccountEquity, _name='account_equity')
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        # 5. 运行
        results = cerebro.run(tradehistory=True, runonce=not strategy_params.get('disable_auto_close', False))
        if not results:
            return {"error": "回测未产生结果"}
            
        strat = results[0]

        execution_info = {"history_start": str(df_raw.index.min()), **options}
        visible = df_raw.index
        if start is not None:
            visible = visible[visible >= start]
        if end is not None:
            visible = visible[visible < end + pd.Timedelta(days=1)]
        data_info = {**df_raw.attrs.get('data_info', {}), "provider": data_provider,
                     "provider_name": {'tqsdk': '天勤 TqSdk 免费版', 'gm': '掘金量化'}.get(data_provider, '原有行情'),
                     "symbol": symbol, "data_source": data_source, "period": period,
                     "contract_month": contract_month, "bars": len(visible),
                     "start": str(visible.min()), "end": str(visible.max())}
        if scan_window is not None:
            first_bar = max(len(df_raw) - len(visible) + 1, strat._minperiod)
            available = max(0, len(df_raw) - first_bar + 1)
            signals = cerebro.broker.scan_events(df_raw.index, first_bar, scan_window)
            return {
                'status': 'insufficient_history' if available < scan_window else 'ok',
                'available_bars': available, 'raw_signals': signals,
                'current_price': float(df_raw['Close'].iloc[-1]),
                'strategy_info': {'name': strategy_name, 'params': filtered_params},
                'execution_info': execution_info, 'data_info': data_info,
            }
        
        # 如果有数据警告，插入到日志头部
        if data_warning:
            strat.logs.insert(0, data_warning)
        
        # 6. 提取结果
        
        # Use actual broker values and bar timestamps. Compounding TimeReturn
        # observations can drift, divide by zero after insolvency, and stamp
        # weekly observations outside the user's visible end-date window.
        equity_curve = strat.analyzers.account_equity.get_analysis()

        # 绩效指标
        trade_analysis = strat.analyzers.trades.get_analysis()
        settlements = strat.closed_trade_stats
        total_trades = len(settlements)
        won_trades = sum(item['net_profit'] > 1e-9 for item in settlements)
        lost_trades = sum(item['net_profit'] < -1e-9 for item in settlements)
        flat_trades = total_trades - won_trades - lost_trades

        # 新增指标提取
        max_capital_usage = getattr(strat, 'max_capital_usage', 0.0)
        max_profit_points = getattr(strat, 'max_profit_points', 0.0)
        max_loss_points = getattr(strat, 'max_loss_points', 0.0)
        
        used_size = getattr(strat, 'max_pos_size', 0)

        # 一手最终赚钱数 (每手净利润)
        # 使用累计的 (PnL/Size) 之和，这样即使 size 变化也能正确反映"单位手"的盈利能力
        one_hand_net_profit = getattr(strat, 'accum_profit_per_hand', 0.0)
            
        # Sum closed trades' net returns on entry margin (full funds for stocks).
        # This is a per-hand measure, not account return or compounded return.
        one_hand_profit_pct = getattr(strat, 'accum_profit_pct', 0.0) * 100.0

        # 准备 K 线数据
        # 确保索引是 datetime
        # 构建前端可视窗口数据（切片到用户请求的范围）
        df_kline = df_raw.copy()
        
        df_kline = df_kline.loc[visible]

        if not isinstance(df_kline.index, pd.DatetimeIndex):
             # 尝试将索引转换为 datetime，或者使用 date 列
             if 'date' in df_kline.columns:
                 df_kline['date'] = pd.to_datetime(df_kline['date'])
                 df_kline.set_index('date', inplace=True)
        
        # --- 结果过滤 (确保返回给前端的数据严格在 start_date ~ end_date 范围内) ---
        # 虽然 LoggingStrategy 已做了部分 start_date 过滤，但为了保险及处理 equity_curve，再次统一过滤
        
        try:
            final_logs, final_trades, final_equity_curve = result_window(
                strat.logs, strat.trades_history, equity_curve, start_date, end_date, initial_cash)
        except ValueError as error:
            logger.exception('Invalid generated backtest events')
            return {'error': str(error)}

        kline_data = build_kline_payload(df_raw, df_kline, strat, strategy_name, strategy_params, final_logs)

        # 辅助函数：清理 NaN 和 Inf
        def clean_data(obj):
            if isinstance(obj, float):
                if pd.isna(obj) or np.isinf(obj):
                    return None
                return obj
            elif isinstance(obj, dict):
                return {k: clean_data(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_data(v) for v in obj]
            elif isinstance(obj, (np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.float64, np.float32)):
                if pd.isna(obj) or np.isinf(obj):
                    return None
                return float(obj)
            return obj

        equity_stats = equity_statistics(final_equity_curve, initial_cash, period)
        raw_result = {
            "risk_reward_trades": getattr(strat, 'risk_reward_trades', []),
            "status": "success",
            "contract_info": contract_info,
            "strategy_info": {"name": strategy_name, "params": filtered_params},
            "execution_info": execution_info,
            "pending_orders": [{"date": df_raw.index[-1].strftime('%Y-%m-%d %H:%M:%S'),
                                "type": "buy" if order.isbuy() else "sell",
                                "size": float(order.created.size)}
                               for order in strat.broker.orders if order.alive() and order.exectype == bt.Order.Market],
            "position_state": {
                "size": float(strat.position.size),
                "direction": "多" if strat.position.size > 0 else "空" if strat.position.size < 0 else "空仓",
                "price": float(df_raw['Close'].iloc[-1]),
                "entry_price": float(strat.position.price) if strat.position.size else "-",
                "hold_bars": len(strat) - strat.position_entry_bar if strat.position.size and strat.position_entry_bar is not None else 0,
                "profit_points": (float(df_raw['Close'].iloc[-1]) - strat.position.price) * (1 if strat.position.size > 0 else -1) if strat.position.size else "-",
            },
            "data_info": data_info,
            "equity_curve": final_equity_curve,
            "kline_data": kline_data,
            "trades": final_trades,
            "metrics": {
                "calculation_version": METRICS_VERSION,
                "commission_rate": COMMISSION_RATE,
                "accounting_model": 'entry_margin_mark_to_market' if market_type == 'futures' else 'stock_lots',
                "initial_cash": initial_cash,
                "final_value": cerebro.broker.getvalue(),
                "net_profit": cerebro.broker.getvalue() - initial_cash,
                "return_rate": (cerebro.broker.getvalue() / initial_cash - 1) * 100,
                "sharpe_ratio": equity_stats['sharpe_ratio'],
                "max_drawdown": equity_stats['max_drawdown'],
                "total_trades": total_trades,
                "win_rate": (won_trades / total_trades * 100) if total_trades > 0 else 0,
                "won_trades": won_trades,
                "lost_trades": lost_trades,
                "flat_trades": flat_trades,
                "open_trades": trade_analysis.get('total', {}).get('open', 0),
                "total_commission": strat.total_commission,
                "realized_net_profit": sum(item['net_profit'] for item in settlements),
                "used_size": used_size,
                "max_capital_usage": max_capital_usage * 100,
                "one_hand_net_profit": one_hand_net_profit,
                "max_profit_points": max_profit_points,
                "max_loss_points": max_loss_points,
                "one_hand_profit_pct": one_hand_profit_pct,
                "one_hand_return_basis": 'entry_margin' if market_type == 'futures' else 'entry_notional',
                "one_hand_margin_rate": strategy_params.get('margin_rate', 0.1) if market_type == 'futures' else 1.0
            },
            "logs": final_logs
        }
        
        return clean_data(raw_result)

    def analyze_detail(self, symbol, period, strategy_params, strategy_name='TrendFollowingStrategy',
                       market_type='futures', data_provider='akshare', data_source='main',
                       start_date=None, as_of=None, history_start=None, daily_history_start=None, synthesize_60=False,
                       scan_window=None):
        """Use the backtest executor without liquidating a live strategy at the data boundary."""
        params = strategy_params.copy()
        params['disable_auto_close'] = True
        params.setdefault('print_log', False)
        params.setdefault('contract_multiplier', get_multiplier(symbol) if market_type == 'futures' else 1)
        if start_date is None and data_provider not in ('tqsdk', 'gm'):
            days = 1095 if period == 'weekly' else 365
            if scan_window is not None:
                days = max(days, scan_window * (7 if period == 'weekly' else 2))
            start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
        result = self.run(symbol=symbol, period=period, strategy_params=params,
                          initial_cash=10000000.0, start_date=start_date,
                          strategy_name=strategy_name, market_type=market_type,
                          data_provider=data_provider, data_source=data_source, as_of=as_of, history_start=history_start,
                          daily_history_start=daily_history_start, synthesize_60=synthesize_60,
                          **({'scan_window': scan_window} if scan_window is not None else {}))
        if 'error' not in result:
            result['analysis_request'] = {
                'symbol': symbol, 'period': period, 'market_type': market_type,
                'strategy_name': strategy_name, 'strategy_params': {
                    **result['strategy_info']['params'], **execution_delay_params(params), **execution_options(params)},
                'data_provider': data_provider, 'data_source': data_source, 'synthesize_60': synthesize_60,
                'start_date': start_date, 'as_of': result['data_info']['end'],
                'history_start': result['execution_info']['history_start'],
                **({'daily_history_start': result['data_info']['daily_macd_history_start']} if result['data_info'].get('daily_macd_history_start') else {}),
            }
        return result

    def analyze_batch(self, symbols, period, strategy_params, strategy_name='TrendFollowingStrategy',
                      market_type='futures', data_provider='akshare', data_source='main', synthesize_60=False):
        results = []
        for symbol in symbols:
            try:
                detail = self.analyze_detail(symbol, period, strategy_params,
                                             strategy_name, market_type, data_provider, data_source, synthesize_60=synthesize_60)
                if 'error' in detail:
                    raise ValueError(detail['error'])
                results.append({
                    'symbol': symbol, **detail['position_state'],
                    'data_info': detail['data_info'], 'analysis_request': detail['analysis_request'],
                })
            except ValueError as error:
                results.append({'symbol': symbol, 'error': str(error), 'price': 0,
                                'direction': 'Error', 'entry_price': '-', 'profit_points': '-'})
            except Exception:
                logger.exception('Strategy analysis failed for %s', symbol)
                results.append({'symbol': symbol, 'error': '策略分析失败，请查看后端日志', 'price': 0,
                                'direction': 'Error', 'entry_price': '-', 'profit_points': '-'})
        return results

    def scan_signals(self, symbols, period, scan_window, strategy_params, strategy_name='TrendFollowingStrategy',
                     market_type='futures', data_provider='akshare', data_source='main', synthesize_60=False):
        results = []
        for symbol in dict.fromkeys(symbols):
            try:
                result = self.analyze_detail(
                    symbol, period, strategy_params, strategy_name, market_type, data_provider, data_source,
                    synthesize_60=synthesize_60, scan_window=scan_window,
                )
                if 'error' in result:
                    results.append({'symbol': symbol, 'status': result.get('status', 'error'), 'error': result['error']})
                else:
                    results.append({'symbol': symbol, **{key: result[key] for key in (
                        'status', 'available_bars', 'raw_signals', 'current_price', 'data_info', 'analysis_request',
                    )}})
            except Exception:
                logger.exception("Signal scan failed for %s", symbol)
                results.append({'symbol': symbol, 'status': 'error', 'error': '信号扫描失败，请检查参数或查看后端日志'})
        return results

