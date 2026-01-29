import backtrader as bt
import pandas as pd
import numpy as np
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
    def _filter_params(self, StrategyClass, params):
        """
        根据策略类定义过滤参数，防止传入多余参数导致报错
        """
        if not hasattr(StrategyClass, 'params'):
            return params
            
        valid_params = {}
        # StrategyClass.params 是 AutoInfoClass 实例，包含所有继承链上的参数默认值
        for k, v in params.items():
            if hasattr(StrategyClass.params, k):
                valid_params[k] = v
        
        return valid_params

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

            def __init__(self, *args, **kwargs):
                super(LoggingStrategy, self).__init__(*args, **kwargs)
                self.logs = []
                self.trades_history = []
                self.exec_start_dt = None  # 执行窗口起始日期 (仅记录窗口内的日志与交易)
                # 最大回撤点位记录 (Price, Date)
                self.current_mdd_price = None
                self.current_mdd_date = None
                self.entry_price = None # 当前持仓的平均开仓价 (用于计算回撤幅度)
                
                # 新增统计指标
                self.max_capital_usage = 0.0
                self.max_profit_points = 0.0
                self.max_loss_points = 0.0
                self.max_pos_size = 0.0 # 记录最大持仓手数
                self.accum_profit_per_hand = 0.0 # 累计每手净利润
                self.accum_profit_pct = 0.0 # 累计每手盈利百分比
                
                # 辅助记录最大最小PNL
                self.max_trade_pnl = -float('inf')
                self.min_trade_pnl = float('inf')
            
            def pre_next(self):
                # 覆盖 BaseStrategy.pre_next 以防止回测结束时强制平仓
                # 这里只保留 start_date 检查
                if self.params.start_date:
                    current_date = self.datas[0].datetime.date(0)
                    start_date = self.params.start_date
                    # 如果是字符串，尝试解析
                    if isinstance(start_date, str):
                        try:
                            start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                        except:
                            pass
                    if isinstance(start_date, datetime.datetime):
                        start_date = start_date.date()
                        
                    if current_date < start_date:
                        return False
                
                # 如果传入了 disable_auto_close=True (来自 scan_signals 的详情调用)
                # 则跳过基类的平仓逻辑
                if getattr(self.params, 'disable_auto_close', False):
                    return True
                
                # 否则调用基类的逻辑 (普通回测需要强制平仓)
                return super().pre_next()

            def start(self):
                # 确保列表已初始化（防止某些情况下 __init__ 属性丢失）
                if not hasattr(self, 'logs'):
                    self.logs = []
                if not hasattr(self, 'trades_history'):
                    self.trades_history = []
                # 重置回撤记录
                self.current_mdd_price = None
                self.current_mdd_date = None
                self.entry_price = None
                
                self.max_capital_usage = 0.0
                self.max_profit_points = 0.0
                self.max_loss_points = 0.0
                self.max_pos_size = 0.0
                self.accum_profit_per_hand = 0.0
                self.accum_profit_pct = 0.0
                self.sum_entry_price = 0.0
                self.closed_trade_count = 0
                
                self.max_trade_pnl = -float('inf')
                self.min_trade_pnl = float('inf')
                
                # 设置执行起始窗口 (以便过滤预热期事件)
                try:
                    if start_date:
                        self.exec_start_dt = pd.to_datetime(start_date).date()
                except Exception:
                    self.exec_start_dt = None
                # 调用父类的 start (如果有)
                if hasattr(super(), 'start'):
                    super().start()

            def notify_trade(self, trade):
                if trade.isclosed:
                    # 计算点数
                    multiplier = getattr(self.p, 'contract_multiplier', 1)
                    # margin_rate = getattr(self.p, 'margin_rate', 0.1) # Unused
                    
                    size = abs(trade.size)
                    if size == 0:
                        # Try to recover size from history
                        if hasattr(trade, 'history') and len(trade.history) > 0:
                            max_size = 0
                            curr_size = 0
                            for ev in trade.history:
                                # trade.history contains TradeHistory objects (dict-like)
                                # Structure: {'status': {...}, 'event': {'size': ..., ...}}
                                if 'event' in ev and 'size' in ev['event']:
                                    ev_size = ev['event']['size']
                                    curr_size += ev_size
                                    if abs(curr_size) > max_size:
                                        max_size = abs(curr_size)
                            size = max_size
                        
                        # Fallback to fixed_size if history recovery failed
                        if size == 0:
                            size_mode = getattr(self.params, 'size_mode', 'fixed')
                            if size_mode == 'fixed' or not size_mode:
                                size = int(getattr(self.params, 'fixed_size', 1))
                    
                    pnl = trade.pnlcomm

                    if size > 0 and multiplier > 0:
                        points = pnl / (size * multiplier)
                        
                        # 累计每手净利润
                        self.accum_profit_per_hand += pnl / size
                        
                        # 累计盈利百分比 (基于开仓价)
                        # 用户定义逻辑：(总每手净利润 / 平均开仓价格)
                        # 这里只更新 sum_entry_price，最终百分比在 stop() 或 run() 结束时计算
                        # 但为了实时更新 metrics，我们在这里计算当前状态
                        if trade.price > 0:
                            self.sum_entry_price += trade.price
                            self.closed_trade_count += 1
                            
                            # Calculate Aggregate Percentage
                            avg_entry_price = self.sum_entry_price / self.closed_trade_count
                            if avg_entry_price > 0:
                                self.accum_profit_pct = (self.accum_profit_per_hand / avg_entry_price)
                        
                        # 记录最大盈利交易的点数
                        if pnl > self.max_trade_pnl:
                            self.max_trade_pnl = pnl
                            self.max_profit_points = points
                        
                        # 记录最亏交易的点数
                        if pnl < self.min_trade_pnl:
                            self.min_trade_pnl = pnl
                            self.max_loss_points = points
                
                super().notify_trade(trade)

            def next(self):
                # 记录最大资金使用率
                # 由于 broker.setcommission 设置了 margin=0，getcash() 不会扣除保证金
                # 因此需要手动计算理论保证金占用
                val = self.broker.getvalue()
                if val > 0:
                    margin_rate = getattr(self.p, 'margin_rate', 0.1)
                    multiplier = getattr(self.p, 'contract_multiplier', 1)
                    # 使用收盘价估算市值
                    price = self.datas[0].close[0]
                    size = abs(self.position.size)
                    
                    margin_used = size * price * multiplier * margin_rate
                    usage = margin_used / val
                    self.max_capital_usage = max(self.max_capital_usage, usage)

                # 记录最大持仓
                self.max_pos_size = max(self.max_pos_size, abs(self.position.size))

                # 记录最大回撤点位 (在 super().next() 之前或之后均可，这里选择之前以捕获当前bar)
                # 注意：Backtrader 的 next 在 bar 关闭时调用，所以 datas[0] 是当前结束的 bar
                if self.position.size > 0:
                    # 多头持仓：关注最低价
                    low = self.datas[0].low[0]
                    dt = self.datas[0].datetime.datetime(0)
                    if self.current_mdd_price is None or low < self.current_mdd_price:
                        self.current_mdd_price = low
                        self.current_mdd_date = dt.strftime('%Y-%m-%d %H:%M:%S')
                elif self.position.size < 0:
                    # 空头持仓：关注最高价
                    high = self.datas[0].high[0]
                    dt = self.datas[0].datetime.datetime(0)
                    if self.current_mdd_price is None or high > self.current_mdd_price:
                        self.current_mdd_price = high
                        self.current_mdd_date = dt.strftime('%Y-%m-%d %H:%M:%S')
                
                # 调用父类策略逻辑
                super().next()

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
                if order.status in [order.Submitted, order.Accepted]:
                    return

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
                    
                    # 确保数值比较的稳定性
                    if abs(prev_pos) < 1e-9: prev_pos = 0
                    if abs(current_pos) < 1e-9: current_pos = 0
                    
                    # 维护 entry_price 逻辑
                    recorded_entry_price = self.entry_price # 默认使用当前记录的成本价
                    
                    # 调试日志
                    # print(f"DEBUG: Order Executed. Date={dt}, Size={size}, Price={price}, PrevPos={prev_pos}, CurrPos={current_pos}, OldEntry={self.entry_price}")

                    # 1. 开仓 (0 -> 非0)
                    if prev_pos == 0 and current_pos != 0:
                        self.entry_price = price
                        recorded_entry_price = None # 开仓本身没有历史持仓
                    
                    # 2. 反手 (正 -> 负 或 负 -> 正)
                    elif (prev_pos > 0 and current_pos < 0) or (prev_pos < 0 and current_pos > 0):
                        # recorded_entry_price 保持为反手前的持仓成本，用于记录
                        self.entry_price = price # 更新为新方向的成本
                        
                    # 3. 平仓 (非0 -> 0)
                    elif prev_pos != 0 and current_pos == 0:
                        # recorded_entry_price 保持为平仓前的持仓成本，用于记录
                        self.entry_price = None
                        
                    # 4. 加仓 (绝对值增加)
                    elif abs(current_pos) > abs(prev_pos):
                        # 计算加权平均成本
                        if self.entry_price is not None:
                            old_value = prev_pos * self.entry_price
                            new_part_value = size * price
                            # 注意: prev_pos 和 size 同号，current_pos = prev_pos + size
                            self.entry_price = (old_value + new_part_value) / current_pos
                        else:
                            self.entry_price = price # 理论上不应发生，作为防御
                        recorded_entry_price = None # 加仓不产生平仓记录的回撤点
                        
                    # 5. 减仓 (绝对值减少，但未归零)
                    elif abs(current_pos) < abs(prev_pos):
                        # 成本价不变
                        pass

                    action_type = "未知"
                    holding_direction = "无" # 该笔交易对应的前一段持仓方向 (用于前端显示回撤方向)
                    
                    if size > 0: # 买入
                        if prev_pos >= 0:
                            action_type = "买多" # 开多 or 加多
                            if prev_pos > 0: holding_direction = "做多" # 加仓
                        elif prev_pos < 0 and current_pos > 0:
                            action_type = "反手做多" # 之前是空仓，现在是多仓
                            holding_direction = "做空" # 之前是做空
                        else: # prev_pos < 0 and current_pos <= 0
                            action_type = "平空" # 买入平空
                            holding_direction = "做空" # 之前是做空
                    else: # 卖出 (size < 0)
                        if prev_pos <= 0:
                            action_type = "卖空" # 开空 or 加空
                            if prev_pos < 0: holding_direction = "做空" # 加仓
                        elif prev_pos > 0 and current_pos < 0:
                            action_type = "反手做空" # 之前是多仓，现在是空仓
                            holding_direction = "做多" # 之前是做多
                        else: # prev_pos > 0 and current_pos >= 0
                            action_type = "平多" # 卖出平多
                            holding_direction = "做多" # 之前是做多
                            
                    # 确保 float 类型，防止 numpy 类型导致 json 序列化问题
                    def safe_float(val):
                        if val is None: return None
                        try:
                            f = float(val)
                            import math
                            if math.isnan(f) or math.isinf(f): return None
                            return f
                        except:
                            return None

                    final_mdd_price = safe_float(self.current_mdd_price)
                    final_entry_price = safe_float(recorded_entry_price)
                    
                    # 只有平仓或反手时，才记录 MDD
                    # 开仓和加仓不记录 MDD (因为还没有"持仓过程"结束)
                    if recorded_entry_price is None:
                        final_mdd_price = None
                        
                    self.trades_history.append({
                        "date": dt,
                        "type": "buy" if order.isbuy() else "sell",
                        "action": action_type,
                        "price": float(price),
                        "size": float(size),
                        "position": float(current_pos),  # 添加当前持仓量
                        "mdd_price": final_mdd_price, # 当前持仓期间的最大回撤价格
                        "mdd_date": self.current_mdd_date if final_mdd_price is not None else None,    # 最大回撤发生的日期
                        "entry_price": final_entry_price, # 对应的开仓均价
                        "holding_direction": holding_direction # 对应的持仓方向
                    })

                    # --- Sync Log with History ---
                    comm = order.executed.comm
                    final_entry_price_val = final_entry_price if final_entry_price is not None else 0.0
                    mdd_str = f", 期间最大回撤: {final_mdd_price:.2f}" if final_mdd_price is not None else ""
                    
                    # PnL (Net Profit with commission)
                    # pnl is gross, comm is commission. Only show for closing trades (pnl != 0)
                    raw_pnl = order.executed.pnl
                    pnl_val = raw_pnl - order.executed.comm
                    pnl_str = ""
                    if raw_pnl != 0:
                        pnl_str = f", 净利润: {pnl_val:.2f}"
                        # Calculate Profit Percentage
                        # User Logic: (NetProfitPerHand / EntryPrice)
                        try:
                            exec_size = abs(order.executed.size)
                            multiplier = getattr(self.p, 'contract_multiplier', 1)
                            
                            # 1. Infer Entry Price using Gross PnL (raw_pnl)
                            # Long (Sell to Close): Entry = Exit - (GrossPnL / (Size * Mult))
                            # Short (Buy to Close): Entry = Exit + (GrossPnL / (Size * Mult))
                            
                            profit_per_hand_gross = raw_pnl / exec_size
                            price_diff = profit_per_hand_gross / multiplier
                            
                            implied_entry = 0.0
                            if order.executed.size < 0: # Sell to Close (Long)
                                implied_entry = order.executed.price - price_diff
                            else: # Buy to Close (Short)
                                implied_entry = order.executed.price + price_diff
                                
                            if implied_entry > 0:
                                # 2. Calculate Pct using Net PnL (pnl_val)
                                profit_per_hand_net = pnl_val / exec_size
                                pct = (profit_per_hand_net / implied_entry)
                                pnl_str += f", 收益率: {pct:.2f}%"
                        except Exception:
                            pass

                    log_msg = (f"交易执行: 【{action_type}】 "
                               f"价格: {price:.2f}, 数量: {float(size)}, 费用: {comm:.2f}, "
                               f"当前持仓: {float(current_pos)}, 持仓成本: {final_entry_price_val:.2f}, "
                               f"方向: {holding_direction}{mdd_str}{pnl_str}")
                    self.log(log_msg)
                    
                    if order.isbuy():
                        self.buyprice = order.executed.price
                        self.buycomm = order.executed.comm
                    self.bar_executed = len(self)
                    
                    # 状态重置逻辑
                    if current_pos == 0:
                        # 平仓后，重置回撤记录
                        self.current_mdd_price = None
                        self.current_mdd_date = None
                    elif (prev_pos > 0 and current_pos < 0) or (prev_pos < 0 and current_pos > 0):
                        # 反手操作：之前的记录归属于上一笔交易，现在开始新交易，重置
                        self.current_mdd_price = None
                        self.current_mdd_date = None
                    # 注意：如果 prev_pos == 0 (新开仓)，self.current_mdd_price 应该在 next() 中被初始化/更新。
                    # 由于 notify_order 在 next 之前或之中触发，如果这是开仓单，
                    # 此时 recorded mdd 可能是 None (正确) 或者上一笔残留 (如果不幸没清除)。
                    # 上面的逻辑保证了平仓或反手时清除。
                    # 如果是单纯开仓 (0 -> size)，mdd 为 None，这是合理的，因为刚开仓还没有"过程"。
                
                elif order.status in [order.Canceled, order.Margin, order.Rejected]:
                    self.log('订单已取消/保证金不足/被拒绝')

                self.order = None

        cerebro = bt.Cerebro()
        
        # 检查是否开启“开仓最优模式” (Optimal Entry)
        # 如果开启，启用 cheat_on_open 以便能在当前 K 线上以 Limit 价格成交
        # NOTE: Remove from params to avoid passing to strategy __init__
        if strategy_params.pop('optimal_entry', False):
            cerebro.broker.set_coo(True)
            print("DEBUG: Optimal Entry Mode Enabled (Cheat On Open = True)")
        
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
            strategy_params['end_date'] = end_date # 注入结束日期，用于强制平仓

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
            
        # 过滤掉不属于策略的参数
        filtered_params = self._filter_params(StrategyClass, strategy_params)

        # 动态创建混合策略类，使其同时继承 LoggingStrategy 和 StrategyClass
        # 这样 LoggingStrategy 就能捕获 StrategyClass 的行为，同时记录日志
        class MixedStrategy(LoggingStrategy, StrategyClass):
             pass

        # MixedStrategy 会继承 StrategyClass 的 params，以及 LoggingStrategy 的逻辑
        # 我们传递过滤后的参数给 MixedStrategy
        cerebro.addstrategy(MixedStrategy, **filtered_params)
        
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

        # 新增指标提取
        max_capital_usage = getattr(strat, 'max_capital_usage', 0.0)
        max_profit_points = getattr(strat, 'max_profit_points', 0.0)
        max_loss_points = getattr(strat, 'max_loss_points', 0.0)
        
        # 使用手数
        actual_max_size = getattr(strat, 'max_pos_size', 0)
        used_size = actual_max_size if actual_max_size > 0 else '动态'
        
        # 如果没有实际交易或 size 为 0，回退到参数
        if used_size == '动态' or used_size == 0:
            size_mode = strategy_params.get('size_mode')
            if size_mode == 'fixed' or not size_mode: # Default to fixed if not present
                try:
                    fixed_size = int(strategy_params.get('fixed_size', 20)) # Default 20
                    used_size = fixed_size
                except:
                    used_size = '未知'
        
        # 一手最终赚钱数 (每手净利润)
        # 使用累计的 (PnL/Size) 之和，这样即使 size 变化也能正确反映"单位手"的盈利能力
        one_hand_net_profit = getattr(strat, 'accum_profit_per_hand', 0.0)
            
        # 一手盈利百分数 (每手盈利金额 / 开仓价)
        # 使用累计的 (PnL / (Size * Price)) 之和
        one_hand_profit_pct = getattr(strat, 'accum_profit_pct', 0.0) * 100.0

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

        # 策略自定义均线计算 (用于前端展示策略实际使用的均线)
        if 'fast_period' in strategy_params:
            try:
                p = int(strategy_params['fast_period'])
                # 根据 ma_type 选择 SMA 或 EMA (默认 SMA)
                is_ema = strategy_params.get('ma_type', 'SMA').upper() == 'EMA'
                
                if is_ema:
                    kline_data['ma']['strategy_fast'] = close_series.ewm(span=p, adjust=False).mean().round(2).tolist()
                else:
                    kline_data['ma']['strategy_fast'] = close_series.rolling(window=p, min_periods=1).mean().round(2).tolist()
                
                kline_data['ma']['strategy_fast_period'] = p
                kline_data['ma']['strategy_fast_label'] = f"{'EMA' if is_ema else 'MA'}{p}"
            except:
                pass

        if 'slow_period' in strategy_params:
            try:
                p = int(strategy_params['slow_period'])
                is_ema = strategy_params.get('ma_type', 'SMA').upper() == 'EMA'
                
                if is_ema:
                    kline_data['ma']['strategy_slow'] = close_series.ewm(span=p, adjust=False).mean().round(2).tolist()
                else:
                    kline_data['ma']['strategy_slow'] = close_series.rolling(window=p, min_periods=1).mean().round(2).tolist()
                
                kline_data['ma']['strategy_slow_period'] = p
                kline_data['ma']['strategy_slow_label'] = f"{'EMA' if is_ema else 'MA'}{p}"
            except:
                pass

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

        if strategy_name in ['DKXStrategy', 'DKXPartialTakeProfitStrategy', 'DKXFixedTPSLStrategy']:
            try:
                dkx_period = int(strategy_params.get('dkx_period', 20))
                dkx_ma_period = int(strategy_params.get('dkx_ma_period', 10))
                
                mid = (3 * df_kline['Close'] + df_kline['Low'] + df_kline['Open'] + df_kline['High']) / 6.0
                
                # 计算 DKX (WMA)
                # DKX = (20*MID + 19*REF(MID,1) + ... + 1*REF(MID,19)) / 210
                dkx_values = mid.rolling(window=dkx_period).apply(
                    lambda x: np.dot(x, np.arange(1, dkx_period + 1)) / (dkx_period * (dkx_period + 1) / 2),
                    raw=True
                )
                
                # 计算 MADKX (SMA)
                madkx_values = dkx_values.rolling(window=dkx_ma_period).mean()
                
                kline_data['dkx'] = {
                    "dkx": dkx_values.fillna(0).tolist(),
                    "madkx": madkx_values.fillna(0).tolist()
                }
            except Exception as e:
                print(f"DKX Calculation Error: {e}")
                kline_data['dkx'] = None

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

        raw_result = {
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
                "lost_trades": lost_trades,
                "used_size": used_size,
                "max_capital_usage": max_capital_usage * 100,
                "one_hand_net_profit": one_hand_net_profit,
                "max_profit_points": max_profit_points,
                "max_loss_points": max_loss_points,
                "one_hand_profit_pct": one_hand_profit_pct
            },
            "logs": final_logs
        }
        
        return clean_data(raw_result)

    def analyze_batch(self, symbols, period, strategy_params, strategy_name='TrendFollowingStrategy', market_type='futures'):
        """
        批量分析策略状态
        """
        importlib.reload(strategy)
        
        if not hasattr(strategy, strategy_name):
             if hasattr(strategy, 'TrendFollowingStrategy'):
                 strategy_name = 'TrendFollowingStrategy'
             else:
                 return {"error": f"Strategy '{strategy_name}' not found."}
        
        StrategyClass = getattr(strategy, strategy_name)
        
        # 简单包装策略以获取最终状态
        class BatchStrategy(StrategyClass):
            def __init__(self):
                self.last_entry_price = "-"
                super().__init__()

            def notify_order(self, order):
                if order.status == order.Completed:
                    # 如果有持仓，记录开仓均价
                    if self.position.size != 0:
                        self.last_entry_price = self.position.price
                super().notify_order(order)
            
            def pre_next(self):
                # 覆盖 BaseStrategy.pre_next 以防止回测结束时强制平仓
                # 仅保留 start_date 检查
                if self.params.start_date:
                    current_date = self.datas[0].datetime.date(0)
                    start_date = self.params.start_date
                    if isinstance(start_date, str):
                        try:
                            start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                        except:
                            pass
                    if isinstance(start_date, datetime.datetime):
                        start_date = start_date.date()
                        
                    if current_date < start_date:
                        return False
                return True

            def stop(self):
                # 记录最终状态
                self.final_size = self.position.size
                if self.position.size != 0:
                    self.final_entry_price = self.position.price
                else:
                    self.final_entry_price = self.last_entry_price
                
                if hasattr(super(), 'stop'):
                    super().stop()

        results = []
        
        # Handle optimal_entry
        use_optimal_entry = strategy_params.pop('optimal_entry', False)
        
        # 预先过滤策略参数
        filtered_strategy_params = self._filter_params(StrategyClass, strategy_params)
        
        # 默认回测最近1年数据，确保指标计算充分
        start_date = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime('%Y-%m-%d')

        for symbol in symbols:
            try:
                # 获取数据
                df = fetch_data(symbol, period, start_date=start_date, end_date=None, market_type=market_type)
                
                if df is not None:
                    # Ensure lowercase columns for backtrader
                    df.columns = [c.lower() for c in df.columns]
                
                if df is None or df.empty:
                    results.append({
                        "symbol": symbol,
                        "name": symbol, # Placeholder, caller should map name
                        "price": 0,
                        "direction": "数据缺失",
                        "entry_price": "-"
                    })
                    continue

                cerebro = bt.Cerebro()
                # 禁用标准输出
                cerebro.check = False
                
                if use_optimal_entry:
                    cerebro.broker.set_coo(True)
                
                # 设置初始资金 (足够大以避免margin问题)
                cerebro.broker.setcash(10000000.0)
                # 设置手续费
                cerebro.broker.setcommission(commission=0.0001, margin=0.0, mult=int(strategy_params.get('contract_multiplier', 10)))

                data = bt.feeds.PandasData(dataname=df)
                cerebro.adddata(data)
                
                # 添加策略
                cerebro.addstrategy(BatchStrategy, **filtered_strategy_params)
                
                # 运行 (不生成图表数据，速度较快)
                strats = cerebro.run()
                if not strats:
                    continue
                    
                strat = strats[0]
                
                # 获取当前价格
                current_price = df['close'].iloc[-1]
                
                # 判断方向
                size = getattr(strat, 'final_size', 0)
                entry_price = getattr(strat, 'final_entry_price', "-")
                
                direction = "空仓"
                color = "default" # default/green/red
                
                if size > 0:
                    direction = "多"
                elif size < 0:
                    direction = "空"
                
                # 计算盈利点数
                profit_points = 0
                if entry_price != "-" and isinstance(entry_price, (int, float)):
                    if size > 0:
                        profit_points = current_price - entry_price
                    elif size < 0:
                        profit_points = entry_price - current_price
                
                results.append({
                    "symbol": symbol,
                    "price": float(current_price),
                    "direction": direction,
                    "entry_price": entry_price,
                    "size": size,
                    "profit_points": profit_points if size != 0 else "-"
                })
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Error analyzing {symbol}: {e}")
                results.append({
                    "symbol": symbol,
                    "error": str(e)
                })
        
        return results

    def scan_signals(self, symbols, period, scan_window, strategy_params, strategy_name='TrendFollowingStrategy', market_type='futures'):
        """
        扫描最近 N 根 K 线的开仓信号
        """
        importlib.reload(strategy)
        
        if not hasattr(strategy, strategy_name):
             if hasattr(strategy, 'TrendFollowingStrategy'):
                 strategy_name = 'TrendFollowingStrategy'
             else:
                 return {"error": f"Strategy '{strategy_name}' not found."}
        
        StrategyClass = getattr(strategy, strategy_name)
        
        class ScanStrategy(StrategyClass):
            def __init__(self):
                self.signals = []
                self.last_pos_size = 0
                self.order_creation = {} # 记录订单创建时的 bar index
                self.order_creation_size = {} # 记录订单创建时的持仓状态
                super().__init__()

            def notify_order(self, order):
                if order.status == order.Submitted:
                    # 记录订单创建时间 (当前已处理的 Bar 数量)
                    self.order_creation[order.ref] = len(self)
                    # 记录订单创建时的持仓状态
                    self.order_creation_size[order.ref] = self.position.size

                if order.status == order.Completed:
                    # 判断开平仓逻辑
                    # 注意：notify_order 调用时，self.position 可能已经更新
                    # 但为了准确判断，我们记录上一次的持仓大小
                    
                    current_size = self.position.size
                    executed_size = order.executed.size # 带符号? backtrader order.executed.size 通常是正数，通过 isbuy/issell 判断方向? 
                    # 不，order.executed.size 是绝对值。order.size 是带符号的。
                    
                    # 简单判定：
                    # 如果成交后持仓绝对值增加，或者持仓方向改变，则视为"开仓"性质
                    # 如果成交后持仓绝对值减小且同向，视为"平仓"
                    
                    is_entry = False
                    action = ""
                    
                    # 以前的 size
                    prev_size = self.last_pos_size
                    
                    if order.isbuy():
                        # 买入
                        if prev_size >= 0:
                            is_entry = True # 加仓或开仓
                            action = "买入开仓" if prev_size == 0 else "买入加仓"
                        else:
                            # 原持有空单
                            if current_size >= 0:
                                # 反手或平空后翻多
                                is_entry = True # 翻多视为开仓
                                action = "反手做多"
                            else:
                                is_entry = False # 平空
                                action = "买入平空"
                    else:
                        # 卖出
                        if prev_size <= 0:
                            is_entry = True # 加空或开空
                            action = "卖出开仓" if prev_size == 0 else "卖出加空"
                        else:
                            # 原持有多单
                            if current_size <= 0:
                                is_entry = True
                                action = "反手做空"
                            else:
                                is_entry = False
                                action = "卖出平多"
                    
                    # 更新记录的持仓
                    self.last_pos_size = current_size
                    
                    if is_entry:
                        dt = self.datas[0].datetime.datetime(0)
                        # 记录 Bar 索引 (负数表示倒数第几根)
                        # len(self) 是当前处理的 K 线总数
                        # 我们在 run 之后会知道总长度 TotalLen
                        # 这里先记录 index = len(self)
                        self.signals.append({
                            "date": dt.strftime('%Y-%m-%d'),
                            "action": action,
                            "price": order.executed.price,
                            "bar_index": len(self) 
                        })
                        
                super().notify_order(order)

            def stop(self):
                # 检查未成交订单 (Pending Orders)，捕获最新K线产生的信号
                # 仅保留最近一根K线产生的订单
                last_bar_idx = len(self)
                
                for order in self.broker.orders:
                    if order.status in [order.Submitted, order.Accepted]:
                        # 检查订单创建时间
                        # 只有在最后一根 K 线（或非常接近末尾）生成的订单才被视为"新信号"
                        creation_idx = self.order_creation.get(order.ref, 0)
                        
                        # 如果订单是很久以前创建的（比如 limit 单），忽略它
                        # last_bar_idx 是当前 total_bars
                        # 我们不再强制要求 creation_idx == last_bar_idx，而是交给外部的 scan_window 过滤
                        # 但是，如果 creation_idx 确实太早了（比如 100 根之前），那确实应该忽略，避免数据量过大
                        # 不过 scan_window 最大可能也就几百？
                        # 安全起见，我们还是记录下来，让 scan_signals 函数去过滤
                        
                        # 计算 ago (倒数第几根)
                        ago = last_bar_idx - creation_idx
                        
                        # 获取订单创建时的日期
                        # 注意：self.datas[0].datetime 是当前(结束时)的时间轴
                        # 我们可以通过 ago 来回溯
                        # date(-ago)
                        try:
                            # ago = 0 means current bar (last_bar_idx)
                            # date(0) is the date of last_bar_idx
                            dt_date = self.datas[0].datetime.date(-ago)
                            dt_str = dt_date.strftime('%Y-%m-%d')
                        except:
                            # Fallback to current date if out of bounds (should not happen if data is loaded)
                            dt_str = self.datas[0].datetime.datetime(0).strftime('%Y-%m-%d')

                        is_entry = False
                        action = ""
                        # 使用订单创建时的持仓状态来判断，而不是当前持仓状态
                        # 这样可以避免历史持仓对当前信号判断的干扰
                        creation_size = self.order_creation_size.get(order.ref, self.position.size)
                        
                        if order.isbuy():
                             if creation_size >= 0:
                                 action = "买入开仓" if creation_size == 0 else "买入加仓"
                                 is_entry = True
                             elif creation_size < 0:
                                 action = "反手做多"
                                 is_entry = True
                        else:
                             if creation_size <= 0:
                                 action = "卖出开仓" if creation_size == 0 else "卖出加空"
                                 is_entry = True
                             elif creation_size > 0:
                                 action = "反手做空"
                                 is_entry = True

                        if is_entry:
                             # 价格处理
                             price = order.created.price
                             if order.exectype == bt.Order.Market or price is None or price == 0:
                                 price = self.datas[0].close[0]
                             
                             self.signals.append({
                                 "date": dt_str,
                                 "action": action + "(信号)",
                                 "price": price,
                                 "bar_index": creation_idx # 使用创建时的 index
                             })
                
                if hasattr(super(), 'stop'):
                    super().stop()

        results = []
        
        # Handle optimal_entry
        use_optimal_entry = strategy_params.pop('optimal_entry', False)
        
        # 强制禁用自动平仓，避免产生虚假信号
        strategy_params['disable_auto_close'] = True
        
        filtered_strategy_params = self._filter_params(StrategyClass, strategy_params)
        
        # 足够的数据以覆盖扫描窗口和指标预热
        # 假设 N=100, 预热=100 -> 200天
        # 默认取 365 天比较稳妥
        start_date = (datetime.datetime.now() - datetime.timedelta(days=max(365, scan_window * 2))).strftime('%Y-%m-%d')

        for symbol in symbols:
            try:
                df = fetch_data(symbol, period, start_date=start_date, end_date=None, market_type=market_type)
                if df is not None:
                    df.columns = [c.lower() for c in df.columns]
                
                if df is None or df.empty:
                    continue

                total_bars = len(df)
                
                cerebro = bt.Cerebro()
                cerebro.check = False
                if use_optimal_entry:
                    cerebro.broker.set_coo(True)
                cerebro.broker.setcash(10000000.0)
                cerebro.broker.setcommission(commission=0.0001, margin=0.0, mult=int(strategy_params.get('contract_multiplier', 10)))
                
                data = bt.feeds.PandasData(dataname=df)
                cerebro.adddata(data)
                
                cerebro.addstrategy(ScanStrategy, **filtered_strategy_params)
                strats = cerebro.run()
                if not strats:
                    continue
                
                strat = strats[0]
                
                # 筛选最近 scan_window 内的信号
                # 这里的 bar_index 是基于 1-based (len(self))
                
                valid_signals = []
                seen_dates = set()
                
                # 倒序遍历，优先处理最新的信号
                for sig in sorted(strat.signals, key=lambda x: x['bar_index'], reverse=True):
                    offset = total_bars - sig['bar_index'] + 1
                    
                    if offset <= scan_window:
                        # 同一日期只保留一个信号（通常是成交信号或最新的挂单信号）
                        if sig['date'] in seen_dates:
                            continue
                            
                        valid_signals.append({
                            "date": sig['date'],
                            "action": sig['action'],
                            "offset": offset, 
                            "price": sig['price']
                        })
                        seen_dates.add(sig['date'])
                
                # 重新排序回正序（前端展示需要）
                valid_signals.sort(key=lambda x: x['offset'], reverse=True)
                
                # 获取当前价格
                current_price = df['close'].iloc[-1] if not df.empty else 0.0

                results.append({
                    "symbol": symbol,
                    "name": symbol, 
                    "signal_text": "有" if valid_signals else "无",
                    "raw_signals": valid_signals,
                    "current_price": current_price
                })
                
            except Exception as e:
                print(f"Error scanning {symbol}: {e}")
                results.append({
                    "symbol": symbol,
                    "error": str(e)
                })
        
        return results

