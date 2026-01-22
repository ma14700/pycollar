import backtrader as bt
import pandas as pd
import datetime
import importlib
from .data_loader import fetch_data
from . import strategy

class StrategyData(bt.feeds.PandasData):
    lines = ('ma_fast', 'ma_slow',)
    params = (
        ('ma_fast', 'ma_fast'),
        ('ma_slow', 'ma_slow'),
    )

class BacktestEngine:
    def run(self, symbol, period, strategy_params, initial_cash=1000000.0, start_date=None, end_date=None, strategy_name='TrendFollowingStrategy', market_type='futures', data_source='main'):
        print("DEBUG: Engine.run called with Modified Code")
        # 强制重载策略模块，确保使用最新代码
        importlib.reload(strategy)
        
        # 获取策略类
        if not hasattr(strategy, strategy_name):
             # 尝试使用默认策略
             if hasattr(strategy, 'TrendFollowingStrategy'):
                 print(f"警告: 未找到策略 '{strategy_name}'。将使用默认策略 'TrendFollowingStrategy'。")
                 strategy_name = 'TrendFollowingStrategy'
             else:
                 return {"error": f"未在代码中找到策略类 '{strategy_name}'。"}
        
        StrategyClass = getattr(strategy, strategy_name)

        # 继承策略以捕获日志 (动态继承)
        class LoggingStrategy(StrategyClass):

            def __init__(self):
                super(LoggingStrategy, self).__init__()
                self.logs = []
                self.trades_history = []
                self.exec_start_dt = None  # 执行窗口起始日期 (仅记录窗口内的日志与交易)

            def start(self):
                # 确保列表已初始化（防止某些情况下 __init__ 属性丢失）
                if not hasattr(self, 'logs'):
                    self.logs = []
                if not hasattr(self, 'trades_history'):
                    self.trades_history = []
                # 设置执行起始窗口 (以便过滤预热期事件)
                try:
                    if start_date:
                        self.exec_start_dt = pd.to_datetime(start_date).date()
                except Exception:
                    self.exec_start_dt = None
                # 调用父类的 start (如果有)
                if hasattr(super(), 'start'):
                    super().start()

            def log(self, txt, dt=None):
                if not hasattr(self, 'logs'):
                    self.logs = []
                # 计算当前日志日期
                dt_cur = dt or self.datas[0].datetime.date(0)
                # 如果是策略启动类日志，将日期对齐到用户选择的窗口开始日
                if isinstance(txt, str) and self.exec_start_dt:
                    if ('策略启动' in txt or '回测开始' in txt):
                        dt_cur = self.exec_start_dt
                    # 过滤预热期的日志（窗口外不记录）
                # if dt_cur < self.exec_start_dt:
                #    return
                dt = dt_cur
                log_entry = f'{dt.isoformat()}, {txt}'
                self.logs.append(log_entry)
                # 同时打印到控制台以便调试
                print(log_entry)

            def notify_order(self, order):
                if not hasattr(self, 'trades_history'):
                    self.trades_history = []
                    
                if order.status in [order.Completed]:
                    dt_dt = self.datas[0].datetime.datetime(0)
                    
                    dt = dt_dt.strftime('%Y-%m-%d %H:%M:%S')
                    
                    size = order.executed.size
                    price = order.executed.price
                    # 计算交易前的持仓
                    current_pos = self.position.size
                    prev_pos = current_pos - size
                    
                    action_type = "未知"
                    if size > 0: # 买入
                        if prev_pos >= 0:
                            action_type = "买多" # 开多 or 加多
                        elif prev_pos < 0 and current_pos > 0:
                            action_type = "反手做多" # 之前是空仓，现在是多仓
                        else: # prev_pos < 0 and current_pos <= 0
                            action_type = "平空" # 买入平空
                    else: # 卖出 (size < 0)
                        if prev_pos <= 0:
                            action_type = "卖空" # 开空 or 加空
                        elif prev_pos > 0 and current_pos < 0:
                            action_type = "反手做空" # 之前是多仓，现在是空仓
                        else: # prev_pos > 0 and current_pos >= 0
                            action_type = "平多" # 卖出平多
                            
                    self.trades_history.append({
                        "date": dt,
                        "type": "buy" if order.isbuy() else "sell",
                        "action": action_type,
                        "price": price,
                        "size": size,
                        "position": current_pos  # 添加当前持仓量
                    })
                
                super().notify_order(order)

        cerebro = bt.Cerebro()
        
        # 1. 加载数据
        data_warning = None
        try:
            # 自动调整开始日期以包含预热期 (日线与分钟线均尝试预热)
            # 这样可以防止因数据过短导致指标无法计算
            fetch_start_date = start_date
            if start_date:
                warmup_days = 150
                if 'slow_period' in strategy_params:
                    try:
                        slow_p = int(strategy_params['slow_period'])
                        warmup_days = max(warmup_days, slow_p * 3)
                    except:
                        pass
                req_dt = pd.to_datetime(start_date)
                fetch_start_dt = req_dt - pd.Timedelta(days=warmup_days)
                fetch_start_date = fetch_start_dt.strftime('%Y-%m-%d')
                print(f"为了指标预热，自动调整请求开始日期: {start_date} -> {fetch_start_date}")

            # 将 start_date 注入到策略参数中，用于严格控制交易开始时间
            # 这样策略在 fetch_start_date 开始运行计算指标，但在 start_date 之前不进行交易
            strategy_params['start_date'] = start_date

            df_raw = fetch_data(symbol=symbol, period=period, market_type=market_type, start_date=fetch_start_date, end_date=end_date, data_source=data_source)
            
            # 检查数据是否被截断 (数据源起始时间晚于请求时间 2 天以上)
            if start_date and df_raw is not None and not df_raw.empty:
                req_start = pd.to_datetime(start_date)
                data_start = df_raw.index.min()
                if data_start > req_start + pd.Timedelta(days=5): # 放宽到5天
                    data_warning = f"【数据警告】数据源限制: 只能获取到 {data_start.strftime('%Y-%m-%d')} 之后的数据 (请求开始: {start_date})。免费接口通常仅提供最近约1000根K线(分钟级)。"
                    print(data_warning)
                    
        except ValueError as ve:
            # 捕获数据加载中抛出的已知错误（如日期范围不匹配）
            return {"error": str(ve)}
        except Exception as e:
            return {"error": f"数据获取失败: {str(e)}"}
            
        if df_raw is None or df_raw.empty:
            return {"error": "未找到该品种的数据，请检查代码或日期范围"}
            
        # 转换 timeframe
        timeframe = bt.TimeFrame.Days if period == 'daily' else bt.TimeFrame.Minutes
        compression = 1 if period == 'daily' else int(period)
        
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
        data = StrategyData(dataname=df_raw, timeframe=timeframe, compression=compression)
        cerebro.adddata(data)
        
        # 2. 添加策略
        # 确保 contract_multiplier 是 int
        if 'contract_multiplier' in strategy_params:
            strategy_params['contract_multiplier'] = int(strategy_params['contract_multiplier'])
            
        cerebro.addstrategy(LoggingStrategy, **strategy_params)
        
        # 3. 资金设置
        cerebro.broker.setcash(initial_cash)
        
        # 手续费设置 (根据品种可以做个简单映射，这里暂时通用)
        # 假设是期货，按手收费或按比例
        # 为了演示，设置一个通用费率
        # 将 margin 设置为 0，禁用 Broker 端的保证金检查，完全由策略端的仓位管理控制风险
        cerebro.broker.setcommission(commission=0.0001, margin=0.0, mult=strategy_params.get('contract_multiplier', 1))
        
        # 4. 添加分析器
        cerebro.addanalyzer(
            bt.analyzers.TimeReturn,
            _name='timereturn',
            timeframe=timeframe,
            compression=compression
        )
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days, compression=1, riskfreerate=0.0)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        # 5. 运行
        results = cerebro.run(tradehistory=True)
        if not results:
            return {"error": "回测未产生结果"}
            
        strat = results[0]
        
        # 如果有数据警告，插入到日志头部
        if data_warning:
            strat.logs.insert(0, data_warning)
        
        # 6. 提取结果
        
        # 权益曲线
        timereturns = strat.analyzers.timereturn.get_analysis()
        
        equity_curve = []
        cumulative = 1.0
        current_equity = initial_cash
        
        # TimeReturn 返回的是收益率，我们需要计算净值
        # Backtrader 的 TimeReturn key 是 datetime 对象
        for date, ret in timereturns.items():
            if ret is None:
                ret = 0.0
            cumulative *= (1.0 + ret)
            current_equity = initial_cash * cumulative
            equity_curve.append({
                "date": date.strftime("%Y-%m-%d %H:%M:%S"),
                "value": current_equity,
                "return": ret
            })
            
        # 绩效指标
        sharpe_analysis = strat.analyzers.sharpe.get_analysis()
        sharpe = sharpe_analysis.get('sharperatio')
        if sharpe is None:
            sharpe = 0.0
        
        drawdown_analysis = strat.analyzers.drawdown.get_analysis()
        max_drawdown = drawdown_analysis.get('max', {}).get('drawdown', 0)
        
        trade_analysis = strat.analyzers.trades.get_analysis()
        total_trades = trade_analysis.get('total', {}).get('total', 0)
        won_trades = trade_analysis.get('won', {}).get('total', 0)
        lost_trades = trade_analysis.get('lost', {}).get('total', 0)
        
        pnl_net = trade_analysis.get('pnl', {}).get('net', {}).get('total', 0)

        # 准备 K 线数据
        # 确保索引是 datetime
        # 构建前端可视窗口数据（切片到用户请求的范围）
        df_kline = df_raw.copy()
        
        # 重新构建 mask
        range_mask = pd.Series(True, index=df_kline.index)
        
        start_dt_ts = pd.to_datetime(start_date) if start_date else None
        end_dt_ts = (pd.to_datetime(end_date) + pd.Timedelta(days=1)) if end_date else None
        
        if start_dt_ts:
            range_mask = range_mask & (df_kline.index >= start_dt_ts)
        if end_dt_ts:
            range_mask = range_mask & (df_kline.index < end_dt_ts)
            
        final_mask = range_mask
        df_kline = df_kline[final_mask]

        if not isinstance(df_kline.index, pd.DatetimeIndex):
             # 尝试将索引转换为 datetime，或者使用 date 列
             if 'date' in df_kline.columns:
                 df_kline['date'] = pd.to_datetime(df_kline['date'])
                 df_kline.set_index('date', inplace=True)
        
        # --- 结果过滤 (确保返回给前端的数据严格在 start_date ~ end_date 范围内) ---
        # 虽然 LoggingStrategy 已做了部分 start_date 过滤，但为了保险及处理 equity_curve，再次统一过滤
        
        # 1. 过滤 Logs
        final_logs = []
        start_dt_ts = pd.to_datetime(start_date) if start_date else None
        end_dt_ts = (pd.to_datetime(end_date) + pd.Timedelta(days=1)) if end_date else None
        
        # 记录过滤前的累计盈亏 (用于解释初始负收益)
        pre_window_pnl = 0.0
        has_pre_window_pnl = False
        
        # 尝试从 equity_curve 获取 start_date 之前的最后一条记录的盈亏
        if start_dt_ts and equity_curve:
            # equity_curve 是按时间排序的
            last_pnl = 0.0
            for eq in equity_curve:
                try:
                    eq_dt = pd.to_datetime(eq['date'])
                    if eq_dt < start_dt_ts:
                        last_pnl = eq['value'] - initial_cash
                        has_pre_window_pnl = True
                    else:
                        break # 已进入窗口，停止搜索
                except:
                    continue
            
            if has_pre_window_pnl:
                pre_window_pnl = last_pnl
                # 插入一条提示日志
                final_logs.append(f"{start_date}, --- 日志过滤窗口开始 (此前累计盈亏: {pre_window_pnl:.2f}) ---")

        for log in strat.logs:
            # 尝试提取日期
            try:
                # log 格式: "2025-10-01 09:30:00, ..."
                parts = log.split(',', 1)
                log_dt = pd.to_datetime(parts[0])
                if start_dt_ts and log_dt < start_dt_ts:
                    continue
                if end_dt_ts and log_dt >= end_dt_ts:
                    continue
                final_logs.append(log)
            except:
                # 无法解析日期的（如警告信息），保留
                final_logs.append(log)
        
        # 2. 过滤 Trades
        final_trades = []
        
        # strat.trades 遍历逻辑已移至上方，此处只需过滤 history
        
        for trade in strat.trades_history:
            try:
                trade_dt_str = trade['date']
                trade_dt = pd.to_datetime(trade_dt_str)
                
                if start_dt_ts and trade_dt < start_dt_ts:
                    continue
                if end_dt_ts and trade_dt >= end_dt_ts:
                    continue
                final_trades.append(trade)
            except:
                final_trades.append(trade)
                
        # 3. 过滤 Equity Curve
        final_equity_curve = []
        for eq in equity_curve:
            try:
                eq_dt = pd.to_datetime(eq['date'])
                # equity curve 通常是日频或按 bar，如果是日频，end_date 当天应包含
                # 注意 eq['date'] 是 "YYYY-MM-DD" 字符串
                if start_dt_ts and eq_dt < start_dt_ts:
                    continue
                if end_dt_ts and eq_dt >= end_dt_ts:
                    continue
                final_equity_curve.append(eq)
            except:
                final_equity_curve.append(eq)

        kline_data = {
            "dates": df_kline.index.strftime('%Y-%m-%d %H:%M:%S').tolist(),
            "values": df_kline[['Open', 'Close', 'Low', 'High']].values.tolist(),
            "volumes": df_kline['Volume'].tolist() if 'Volume' in df_kline.columns else []
        }
        
        close_series = df_kline['Close'].astype(float)
        ma5 = close_series.rolling(window=5, min_periods=1).mean()
        ma10 = close_series.rolling(window=10, min_periods=1).mean()
        ma20 = close_series.rolling(window=20, min_periods=1).mean()
        ma55 = close_series.rolling(window=55, min_periods=1).mean()
        kline_data['ma'] = {
            "ma5": ma5.round(2).tolist(),
            "ma10": ma10.round(2).tolist(),
            "ma20": ma20.round(2).tolist(),
            "ma55": ma55.round(2).tolist()
        }

        # 计算 MACD (无论策略是否使用，都计算以便前端展示)
        try:
            fast_period = int(strategy_params.get('macd_fast', 12))
            slow_period = int(strategy_params.get('macd_slow', 26))
            signal_period = int(strategy_params.get('macd_signal', 9))
            
            close_price = df_kline['Close'].astype(float)
            exp1 = close_price.ewm(span=fast_period, adjust=False).mean()
            exp2 = close_price.ewm(span=slow_period, adjust=False).mean()
            dif = exp1 - exp2
            dea = dif.ewm(span=signal_period, adjust=False).mean()
            macd_hist = (dif - dea) * 2
            
            kline_data['macd'] = {
                "dif": dif.fillna(0).tolist(),
                "dea": dea.fillna(0).tolist(),
                "hist": macd_hist.fillna(0).tolist()
            }
        except Exception as e:
            print(f"MACD Calculation Error: {e}")
            kline_data['macd'] = None

        if strategy_name == 'DKXStrategy':
            try:
                dkx_period = int(strategy_params.get('dkx_period', 20))
                dkx_ma_period = int(strategy_params.get('dkx_ma_period', 10))
                
                mid = (3 * df_kline['Close'] + df_kline['Low'] + df_kline['Open'] + df_kline['High']) / 6.0
                dkx_values = []
                madkx_values = []
                dkx_prev = None
                madkx_prev = None
                for v in mid.values:
                    if dkx_prev is None:
                        dkx_cur = v
                    else:
                        dkx_cur = (v + (dkx_period - 1) * dkx_prev) / dkx_period
                    dkx_prev = dkx_cur
                    if madkx_prev is None:
                        madkx_cur = dkx_cur
                    else:
                        madkx_cur = (dkx_cur + (dkx_ma_period - 1) * madkx_prev) / dkx_ma_period
                    madkx_prev = madkx_cur
                    dkx_values.append(dkx_cur)
                    madkx_values.append(madkx_cur)
                dkx_line = pd.Series(dkx_values, index=mid.index)
                madkx_line = pd.Series(madkx_values, index=mid.index)
                kline_data['dkx'] = {
                    "dkx": dkx_line.tolist(),
                    "madkx": madkx_line.tolist()
                }
            except Exception as e:
                print(f"DKX Calculation Error: {e}")
                kline_data['dkx'] = None

        return {
            "status": "success",
            "equity_curve": final_equity_curve,
            "kline_data": kline_data,
            "trades": final_trades,
            "metrics": {
                "initial_cash": initial_cash,
                "final_value": cerebro.broker.getvalue(),
                "net_profit": cerebro.broker.getvalue() - initial_cash,
                "sharpe_ratio": sharpe,
                "max_drawdown": max_drawdown,
                "total_trades": total_trades,
                "win_rate": (won_trades / total_trades * 100) if total_trades > 0 else 0,
                "won_trades": won_trades,
                "lost_trades": lost_trades
            },
            "logs": final_logs
        }
