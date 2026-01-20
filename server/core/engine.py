import backtrader as bt
import pandas as pd
import datetime
import importlib
from .data_loader import fetch_futures_data
from . import strategy

class BacktestEngine:
    def run(self, symbol, period, strategy_params, initial_cash=1000000.0, start_date=None, end_date=None, strategy_name='TrendFollowingStrategy'):
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
                # 务必调用父类 init
                super().__init__()
                self.logs = []
                self.trades_history = []

            def start(self):
                # 确保列表已初始化（防止某些情况下 __init__ 属性丢失）
                if not hasattr(self, 'logs'):
                    self.logs = []
                if not hasattr(self, 'trades_history'):
                    self.trades_history = []
                
                # 调用父类的 start (如果有)
                if hasattr(super(), 'start'):
                    super().start()

            def log(self, txt, dt=None):
                if not hasattr(self, 'logs'):
                    self.logs = []
                dt = dt or self.datas[0].datetime.date(0)
                log_entry = f'{dt.isoformat()}, {txt}'
                self.logs.append(log_entry)
                # 同时打印到控制台以便调试
                print(log_entry)

            def notify_order(self, order):
                if not hasattr(self, 'trades_history'):
                    self.trades_history = []
                    
                if order.status in [order.Completed]:
                    dt = self.datas[0].datetime.datetime(0).strftime('%Y-%m-%d %H:%M:%S')
                    
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
        try:
            df = fetch_futures_data(symbol=symbol, period=period, start_date=start_date, end_date=end_date)
        except ValueError as ve:
            # 捕获数据加载中抛出的已知错误（如日期范围不匹配）
            return {"error": str(ve)}
        except Exception as e:
            return {"error": f"数据获取失败: {str(e)}"}
            
        if df is None or df.empty:
            return {"error": "未找到该品种的数据，请检查代码或日期范围"}
            
        # 转换 timeframe
        timeframe = bt.TimeFrame.Days if period == 'daily' else bt.TimeFrame.Minutes
        compression = 1 if period == 'daily' else int(period)
        
        # 检查数据列
        if 'OpenInterest' not in df.columns and 'hold' in df.columns:
             df.rename(columns={'hold': 'OpenInterest'}, inplace=True)

        data = bt.feeds.PandasData(dataname=df, timeframe=timeframe, compression=compression)
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
        cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='timereturn')
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days, compression=1, riskfreerate=0.0)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        # 5. 运行
        results = cerebro.run()
        if not results:
            return {"error": "回测未产生结果"}
            
        strat = results[0]
        
        # 6. 提取结果
        
        # 权益曲线
        timereturns = strat.analyzers.timereturn.get_analysis()
        equity_curve = []
        cumulative = 1.0
        current_equity = initial_cash
        
        # TimeReturn 返回的是收益率，我们需要计算净值
        # Backtrader 的 TimeReturn key 是 datetime 对象
        for date, ret in timereturns.items():
            if ret is None: ret = 0.0
            cumulative *= (1.0 + ret)
            current_equity = initial_cash * cumulative
            equity_curve.append({
                "date": date.strftime("%Y-%m-%d"),
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
        df_kline = df.copy()
        if not isinstance(df_kline.index, pd.DatetimeIndex):
             # 尝试将索引转换为 datetime，或者使用 date 列
             if 'date' in df_kline.columns:
                 df_kline['date'] = pd.to_datetime(df_kline['date'])
                 df_kline.set_index('date', inplace=True)
        
        kline_data = {
            "dates": df_kline.index.strftime('%Y-%m-%d %H:%M:%S').tolist(),
            "values": df_kline[['Open', 'Close', 'Low', 'High']].values.tolist(),
            "volumes": df_kline['Volume'].tolist() if 'Volume' in df_kline.columns else []
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

        return {
            "status": "success",
            "equity_curve": equity_curve,
            "kline_data": kline_data,
            "trades": strat.trades_history,
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
            "logs": strat.logs
        }
