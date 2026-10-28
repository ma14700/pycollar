import backtrader as bt
import pandas as pd
import numpy as np
import datetime
import importlib
from .data_loader import fetch_data
from . import strategy
from .constants import get_multiplier
from .execution_delay import SignalDelayBroker, execution_delay_params
from .accounting import (configure_accounting, closed_trade_stats, equity_statistics,
                         AccountEquity, COMMISSION_RATE, METRICS_VERSION)

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
                if v is None or v == '':
                    continue
                default = getattr(StrategyClass.params, k)
                if isinstance(default, bool) and isinstance(v, str):
                    if v.lower() not in ('true', 'false'):
                        raise ValueError(f'策略参数 {k} 必须为布尔值')
                    v = v.lower() == 'true'
                elif isinstance(default, (int, float)) and not isinstance(default, bool):
                    number = float(v)
                    if not np.isfinite(number) or (isinstance(default, int) and not number.is_integer()):
                        raise ValueError(f'策略参数 {k} 数值无效')
                    v = int(number) if isinstance(default, int) else number
                valid_params[k] = v
        
        return valid_params

    def run(self, symbol, period, strategy_params, initial_cash=1000000.0, start_date=None, end_date=None, strategy_name='TrendFollowingStrategy', market_type='futures', data_source='main', data_provider='akshare', as_of=None, history_start=None):
        strategy_params = strategy_params.copy()
        try:
            initial_cash = float(initial_cash)
            if not np.isfinite(initial_cash) or initial_cash <= 0:
                raise ValueError('初始资金必须为大于 0 的有限数字')
            delay_params = execution_delay_params(strategy_params)
        except (ValueError, TypeError) as error:
            return {"error": str(error)}
        print("DEBUG: Engine.run called with Modified Code")
        # 强制重载策略模块，确保使用最新代码
        importlib.reload(strategy)
        
        # 获取策略类
        if not hasattr(strategy, strategy_name):
            return {"error": f"未在代码中找到策略类 '{strategy_name}'。"}
        
        StrategyClass = getattr(strategy, strategy_name)
        try:
            optimal_entry = strategy_params.get('optimal_entry', False)
            strategy_params = {**dict(StrategyClass.params._getitems()),
                               **self._filter_params(StrategyClass, strategy_params)}
            strategy_params['optimal_entry'] = optimal_entry
        except (ValueError, TypeError) as error:
            return {"error": f"策略参数无效: {error}"}

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
                self.position_entry_bar = None
                
                # 新增统计指标
                self.max_capital_usage = 0.0
                self.max_profit_points = 0.0
                self.max_loss_points = 0.0
                self.max_pos_size = 0.0 # 记录最大持仓手数
                self.accum_profit_per_hand = 0.0 # 累计每手净利润
                self.accum_profit_pct = 0.0 # 累计每手盈利百分比
                

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
                self.closed_trade_stats = []
                self.total_commission = 0.0
                
                
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
                    stats = closed_trade_stats(trade, getattr(self.p, 'contract_multiplier', 1))
                    self.closed_trade_stats.append(stats)
                    self.accum_profit_per_hand += stats['net_per_hand']
                    self.accum_profit_pct += stats['return_pct'] / 100
                    self.max_profit_points = max(self.max_profit_points, stats['net_points'])
                    self.max_loss_points = min(self.max_loss_points, stats['net_points'])

                super().notify_trade(trade)

            def next(self):
                # 记录最大资金使用率
                # Futures reserve collateral at the average entry price; stocks
                # use full market value. This is sampled at bar close only.
                val = self.broker.getvalue()
                if val > 0:
                    margin_rate = getattr(self.p, 'margin_rate', 0.1) if market_type == 'futures' else 1.0
                    multiplier = getattr(self.p, 'contract_multiplier', 1)
                    price = self.position.price if market_type == 'futures' else self.datas[0].close[0]
                    size = abs(self.position.size)
                    
                    margin_used = size * price * multiplier * margin_rate
                    usage = margin_used / val
                    self.max_capital_usage = max(self.max_capital_usage, usage)

                # 记录最大持仓
                curr_size = abs(self.position.size)
                self.max_pos_size = max(self.max_pos_size, curr_size)
                

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
                if getattr(self, '_forwarding_order_notification', False) and txt.startswith((
                        '买入成交', '卖出成交', '订单已取消/保证金不足/被拒绝', '回测结束：待执行信号未成交')):
                    return
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
                if self.params.print_log:
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
                    opens_position = current_pos != 0 and (prev_pos == 0 or prev_pos * current_pos < 0)
                    if opens_position:
                        self.position_entry_bar = len(self)
                    elif current_pos == 0:
                        self.position_entry_bar = None
                    
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
                        "signal_date": order.info.get('signal_time'),
                        "execution_delay_bars": order.info.get('execution_delay_bars', 1),
                        "date": dt,
                        "type": "buy" if order.isbuy() else "sell",
                        "action": action_type,
                        "price": float(price),
                        "size": float(size),
                        "commission": float(order.executed.comm),
                        "position": float(current_pos),  # 添加当前持仓量
                        "opens_position": opens_position,
                        "mdd_price": final_mdd_price, # 当前持仓期间的最大回撤价格
                        "mdd_date": self.current_mdd_date if final_mdd_price is not None else None,    # 最大回撤发生的日期
                        "entry_price": final_entry_price, # 对应的开仓均价
                        "holding_direction": holding_direction # 对应的持仓方向
                    })

                    # --- Sync Log with History ---
                    comm = order.executed.comm
                    final_entry_price_val = final_entry_price if final_entry_price is not None else 0.0
                    mdd_str = f", 期间最大回撤: {final_mdd_price:.2f}" if final_mdd_price is not None else ""
                    
                    # A closing order alone excludes entry commissions and can
                    # contain an opening leg on reversal. Settle net PnL once,
                    # in notify_trade, rather than estimating/accumulating twice.
                    self.total_commission += float(comm)

                    log_msg = (f"交易执行: 【{action_type}】 "
                               f"价格: {price:.2f}, 数量: {float(size)}, 费用: {comm:.2f}, "
                               f"当前持仓: {float(current_pos)}, 持仓成本: {final_entry_price_val:.2f}, "
                               f"方向: {holding_direction}{mdd_str}")
                    if order.info.get('execution_delay_bars', 1) > 1:
                        log_msg += f", 信号时间: {order.info.get('signal_time')}, 执行 K 线: 信号后第 {order.info.get('execution_delay_bars')} 根开盘"
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
                    self.log('回测结束：待执行信号未成交' if order.info.get('end_of_backtest') else '订单已取消/保证金不足/被拒绝')

                self._forwarding_order_notification = True
                try:
                    super().notify_order(order)
                finally:
                    self._forwarding_order_notification = False

                self.order = None

        cerebro = bt.Cerebro()
        cerebro.setbroker(SignalDelayBroker(**delay_params))
        try:
            configure_accounting(cerebro.broker, strategy_params, market_type)
        except (ValueError, TypeError) as error:
            return {"error": str(error)}
        
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
                warmup_days = 432 if period == 'daily' else 150
                if 'slow_period' in strategy_params:
                    try:
                        slow_p = int(strategy_params['slow_period'])
                        warmup_days = max(warmup_days, slow_p * 3)
                    except:
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

            df_raw = fetch_data(symbol=symbol, period=period, market_type=market_type, start_date=fetch_start_date, end_date=end_date, data_source=data_source, data_provider=data_provider)
            if df_raw is not None:
                df_raw = df_raw.copy()
                if as_of:
                    df_raw = df_raw.loc[df_raw.index <= pd.to_datetime(as_of)].copy()
                if history_start and not df_raw.empty:
                    first_bar = pd.to_datetime(history_start)
                    if df_raw.index.min() > first_bar:
                        raise ValueError('分析时的历史起点已超出当前行情窗口，请重新分析后查看详情')
                    df_raw = df_raw.loc[df_raw.index >= first_bar].copy()
            
            # 检查数据是否被截断 (数据源起始时间晚于请求时间 2 天以上)
            if start_date and df_raw is not None and not df_raw.empty:
                req_start = pd.to_datetime(start_date)
                data_start = df_raw.index.min()
                if data_start > req_start + pd.Timedelta(days=5): # 放宽到5天
                    if data_provider == 'tqsdk':
                        raise ValueError(f'天勤免费滚动窗口无法覆盖所选开始日期 {start_date}，当前最早数据为 {data_start}。请缩短范围或清空日期使用近期窗口。')
                    data_warning = f"【数据警告】数据源限制: 只能获取到 {data_start.strftime('%Y-%m-%d')} 之后的数据 (请求开始: {start_date})。免费接口通常仅提供最近约1000根K线(分钟级)。"
                    print(data_warning)
                    
        except ValueError as ve:
            # 捕获数据加载中抛出的已知错误（如日期范围不匹配）
            return {"error": str(ve)}
        except Exception as e:
            return {"error": f"数据获取失败: {str(e)}"}
            
        if df_raw is None or df_raw.empty:
            return {"error": "未找到该品种的数据，请检查代码或日期范围"}

        history_requirement = getattr(StrategyClass, 'required_bars', None)
        if callable(history_requirement):
            required_bars = history_requirement(strategy_params)
            if len(df_raw) < required_bars:
                return {"error": f"该策略至少需要 {required_bars} 根已完成 K 线用于均线与交叉确认，当前仅有 {len(df_raw)} 根，请扩大数据范围或更换周期"}
            
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
        data = StrategyData(dataname=df_raw, timeframe=timeframe, compression=compression)
        cerebro.adddata(data)
        
        # 2. 添加策略
        # Retain the same multiplier used by broker accounting and statistics.
        if 'contract_multiplier' in strategy_params:
            strategy_params['contract_multiplier'] = float(strategy_params['contract_multiplier'])
            
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
        
        # 4. 添加分析器
        cerebro.addanalyzer(AccountEquity, _name='account_equity')
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
            
        # Sum of each closed trade's net return on entry notional (not margin,
        # account return, or compounded return); contract multiplier included.
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
        
        # Calculate on all available history, then align to the visible range.
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
            "ma144": [round(float(value), 2) if pd.notna(value) else None for value in ma144]
        }

        # Read the executed indicators, including strategy defaults and EMA seeds.
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
                
                mid = (3 * df_raw['Close'] + df_raw['Low'] + df_raw['Open'] + df_raw['High']) / 6.0

                # 计算 DKX (WMA)
                # DKX = (20*MID + 19*REF(MID,1) + ... + 1*REF(MID,19)) / 210
                dkx_values = mid.rolling(window=dkx_period).apply(
                    lambda x: np.dot(x, np.arange(1, dkx_period + 1)) / (dkx_period * (dkx_period + 1) / 2),
                    raw=True
                )

                # 计算 MADKX (SMA)
                madkx_values = dkx_values.rolling(window=dkx_ma_period).mean()
                
                kline_data['dkx'] = {
                    "dkx": dkx_values.reindex(df_kline.index).tolist(),
                    "madkx": madkx_values.reindex(df_kline.index).tolist()
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

        equity_stats = equity_statistics(final_equity_curve, initial_cash, period)
        raw_result = {
            "status": "success",
            "strategy_info": {"name": strategy_name, "params": filtered_params},
            "execution_info": {"history_start": str(df_raw.index.min())},
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
            "data_info": {**df_raw.attrs.get('data_info', {}), "provider": data_provider,
                          "provider_name": '天勤 TqSdk 免费版' if data_provider == 'tqsdk' else '原有行情',
                          "symbol": symbol, "data_source": data_source, "period": period,
                          "bars": len(df_kline), "start": str(df_kline.index.min()), "end": str(df_kline.index.max())},
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
                "one_hand_profit_pct": one_hand_profit_pct
            },
            "logs": final_logs
        }
        
        return clean_data(raw_result)

    def analyze_detail(self, symbol, period, strategy_params, strategy_name='TrendFollowingStrategy',
                       market_type='futures', data_provider='akshare', data_source='main',
                       start_date=None, as_of=None, history_start=None):
        """Use the backtest executor without liquidating a live strategy at the data boundary."""
        params = strategy_params.copy()
        params['disable_auto_close'] = True
        params.setdefault('print_log', False)
        params.setdefault('contract_multiplier', get_multiplier(symbol) if market_type == 'futures' else 1)
        if start_date is None and data_provider != 'tqsdk':
            days = 1095 if period == 'weekly' else 365
            start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
        result = self.run(symbol=symbol, period=period, strategy_params=params,
                          initial_cash=10000000.0, start_date=start_date,
                          strategy_name=strategy_name, market_type=market_type,
                          data_provider=data_provider, data_source=data_source, as_of=as_of, history_start=history_start)
        if 'error' not in result:
            result['analysis_request'] = {
                'symbol': symbol, 'period': period, 'market_type': market_type,
                'strategy_name': strategy_name, 'strategy_params': {
                    **result['strategy_info']['params'], **execution_delay_params(params)},
                'data_provider': data_provider, 'data_source': data_source,
                'start_date': start_date, 'as_of': result['data_info']['end'],
                'history_start': result['execution_info']['history_start'],
            }
        return result

    def analyze_batch(self, symbols, period, strategy_params, strategy_name='TrendFollowingStrategy',
                      market_type='futures', data_provider='akshare', data_source='main'):
        results = []
        for symbol in symbols:
            try:
                detail = self.analyze_detail(symbol, period, strategy_params,
                                             strategy_name, market_type, data_provider, data_source)
                if 'error' in detail:
                    raise ValueError(detail['error'])
                results.append({
                    'symbol': symbol, **detail['position_state'],
                    'data_info': detail['data_info'], 'analysis_request': detail['analysis_request'],
                })
            except Exception as error:
                results.append({'symbol': symbol, 'error': str(error), 'price': 0,
                                'direction': 'Error', 'entry_price': '-', 'profit_points': '-'})
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
                cerebro.setbroker(SignalDelayBroker(**execution_delay_params(strategy_params)))
                cerebro.check = False
                if use_optimal_entry:
                    cerebro.broker.set_coo(True)
                cerebro.broker.setcash(10000000.0)
                configure_accounting(cerebro.broker, strategy_params, market_type)

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

