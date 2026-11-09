"""Order/trade recording and accounting instrumentation for strategies."""
import datetime
import pandas as pd
from .accounting import closed_trade_stats


def make_logging_strategy(strategy_class, start_date, market_type):
    class LoggingStrategy(strategy_class):

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
                    start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
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


            # Dates have already been validated by the engine.
            self.exec_start_dt = pd.to_datetime(start_date).date() if start_date else None
            # 调用父类的 start (如果有)
            if hasattr(super(), 'start'):
                super().start()

        def notify_trade(self, trade):
            if trade.isclosed:
                margin_rate = getattr(self.p, 'margin_rate', 0.1) if market_type == 'futures' else 1.0
                stats = closed_trade_stats(trade, getattr(self.p, 'contract_multiplier', 1), margin_rate)
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
                # Notifications can contain both entry and protective exit
                # from the same bar; use each fill's position snapshot.
                current_pos = order.executed.psize
                self.max_pos_size = max(self.max_pos_size, abs(current_pos))
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
                    except (ValueError, TypeError):
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

    return LoggingStrategy
