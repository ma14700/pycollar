
class DualMAFixedTPSLStrategy(bt.Strategy):
    """
    20/55双均线交叉(多空) + 固定止盈止损策略
    1. 信号：
       - 多头：快线(20) 上穿 慢线(55)
       - 空头：快线(20) 下穿 慢线(55)
    2. 风控：
       - 支持固定点数或百分比的止盈止损
    3. 交易：
       - 信号出现时反手 (平仓+开新仓)
       - 开仓后挂 OCO 止盈止损单
    """
    params = (
        ('fast_period', 20),
        ('slow_period', 55),
        ('ma_type', 'SMA'), # 'SMA' or 'EMA'
        ('sl_mode', 'points'), # 'points' or 'percent'
        ('sl_value', 50.0),
        ('tp_mode', 'points'), # 'points' or 'percent'
        ('tp_value', 100.0),
        ('fixed_size', 1),
        ('contract_multiplier', 1),
        ('print_log', True),
        ('size_mode', 'fixed'), # 为了兼容性保留
        ('equity_percent', 0.1), # 为了兼容性保留
        ('margin_rate', 0.1),    # 为了兼容性保留
        ('start_date', None),    # 策略启动日期
    )

    def log(self, txt, dt=None):
        if self.params.print_log:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        # 初始化均线
        if self.params.ma_type.upper() == 'EMA':
            self.ma_fast = bt.ind.EMA(period=self.params.fast_period)
            self.ma_slow = bt.ind.EMA(period=self.params.slow_period)
        else:
            self.ma_fast = bt.ind.SMA(period=self.params.fast_period)
            self.ma_slow = bt.ind.SMA(period=self.params.slow_period)
        
        self.crossover = bt.ind.CrossOver(self.ma_fast, self.ma_slow)
        
        # 订单引用
        self.order = None      # 开仓/平仓单
        self.sl_order = None   # 止损单
        self.tp_order = None   # 止盈单
        
        # 记录上次平仓数量用于计算点数 (兼容 notify_trade)
        self.last_closed_trade_size = 0
        self.max_profit_points = 0.0
        self.max_loss_points = 0.0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            # 辅助判断函数
            def is_same_order(o1, o2):
                if o1 is None or o2 is None:
                    return False
                return o1.ref == o2.ref

            is_sl = is_same_order(order, self.sl_order)
            is_tp = is_same_order(order, self.tp_order)
            
            # 如果是开仓单/反手单完成 (非止盈止损单)
            if not is_sl and not is_tp:
                action = "买入" if order.isbuy() else "卖出"
                self.log(f'{action}成交: 价格 {order.executed.price:.2f}, 数量 {order.executed.size}')
                
                # 只有当持有仓位时才挂止盈止损
                if self.position.size != 0:
                    self.log(f'持仓确认 (Size: {self.position.size}), 立即挂出止盈止损单')
                    self.place_sl_tp_orders(order.executed.price, self.position.size)
            
            # 如果是止盈或止损单完成
            elif is_sl:
                self.log(f'止损触发: 价格 {order.executed.price:.2f}')
                self.cancel_sl_tp() # 取消剩下的止盈单
            elif is_tp:
                self.log(f'止盈触发: 价格 {order.executed.price:.2f}')
                self.cancel_sl_tp() # 取消剩下的止损单
            
            # 记录平仓手数用于 notify_trade
            if order.executed.size != 0:
                # 简单逻辑：如果当前仓位变小了，或者是反手，都涉及平仓
                # 这里为了配合 notify_trade 的点数计算，尽量记录
                self.last_closed_trade_size = abs(order.executed.size)

            self.order = None

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'订单状态异常: {order.getstatusname()}')
            self.order = None

    def place_sl_tp_orders(self, entry_price, size):
        # 先取消已有的
        self.cancel_sl_tp()
        
        sl_price = 0
        tp_price = 0
        
        # 计算价差
        sl_diff = 0
        tp_diff = 0
        
        if self.params.sl_mode == 'percent':
            sl_diff = entry_price * (self.params.sl_value / 100.0)
        else:
            sl_diff = self.params.sl_value
            
        if self.params.tp_mode == 'percent':
            tp_diff = entry_price * (self.params.tp_value / 100.0)
        else:
            tp_diff = self.params.tp_value

        if size > 0: # 多头
            sl_price = entry_price - sl_diff
            tp_price = entry_price + tp_diff
            # 挂单: 卖出平仓
            self.sl_order = self.sell(size=abs(size), price=sl_price, exectype=bt.Order.Stop)
            self.tp_order = self.sell(size=abs(size), price=tp_price, exectype=bt.Order.Limit)
            self.log(f'挂单(多头): 止损@{sl_price:.2f}, 止盈@{tp_price:.2f}')
            
        elif size < 0: # 空头
            sl_price = entry_price + sl_diff
            tp_price = entry_price - tp_diff
            # 挂单: 买入平仓
            self.sl_order = self.buy(size=abs(size), price=sl_price, exectype=bt.Order.Stop)
            self.tp_order = self.buy(size=abs(size), price=tp_price, exectype=bt.Order.Limit)
            self.log(f'挂单(空头): 止损@{sl_price:.2f}, 止盈@{tp_price:.2f}')

    def cancel_sl_tp(self):
        if self.sl_order:
            self.cancel(self.sl_order)
            self.sl_order = None
        if self.tp_order:
            self.cancel(self.tp_order)
            self.tp_order = None

    def notify_trade(self, trade):
        # 复用 TrendFollowingStrategy 的 notify_trade 逻辑 (如果需要)
        # 这里简单打印
        if not trade.isclosed:
            return
        self.log(f'交易利润: 毛利 {trade.pnl:.2f}, 净利 {trade.pnlcomm:.2f}')

    def next(self):
        # 强制在回测结束前平仓
        if len(self) >= self.datas[0].buflen() - 2:
            if self.position:
                self.log(f'回测即将结束，强制平仓')
                self.cancel_sl_tp()
                self.order = self.close()
            return

        # 如果有正在进行的主订单(开仓/平仓)，等待
        if self.order and self.order != self.sl_order and self.order != self.tp_order:
            return

        # 获取当前持仓
        pos_size = self.position.size
        
        # 信号逻辑
        # 金叉 (20 上穿 55)
        if self.crossover > 0:
            # 如果当前为空头，或者无持仓 -> 做多
            if pos_size <= 0:
                self.log(f'金叉信号 (Fast > Slow): {self.ma_fast[0]:.2f} > {self.ma_slow[0]:.2f}')
                self.cancel_sl_tp() # 取消之前的挂单
                
                target_size = self.params.fixed_size
                if target_size is None:
                    target_size = 1
                
                self.log(f'执行做多/反手做多: 目标持仓 {target_size}')
                self.order = self.order_target_size(target=target_size)
        
        # 死叉 (20 下穿 55)
        elif self.crossover < 0:
            # 如果当前为多头，或者无持仓 -> 做空
            if pos_size >= 0:
                self.log(f'死叉信号 (Fast < Slow): {self.ma_fast[0]:.2f} < {self.ma_slow[0]:.2f}')
                self.cancel_sl_tp() # 取消之前的挂单
                
                target_size = self.params.fixed_size
                if target_size is None:
                    target_size = 1
                    
                self.log(f'执行做空/反手做空: 目标持仓 {-target_size}')
                self.order = self.order_target_size(target=-target_size)
