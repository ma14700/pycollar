import backtrader as bt
import datetime

# --- 基础策略类 ---
class BaseStrategy(bt.Strategy):
    """
    包含通用的日志记录、订单管理和交易通知逻辑
    """
    params = (
        ('print_log', True),
        ('start_date', None),
        ('end_date', None), # 新增结束日期参数
        ('contract_multiplier', 1),
        ('atr_period', 14),
        ('atr_multiplier', 2.0),
        ('risk_per_trade', 0.02),
        ('equity_percent', 0.1),
        ('margin_rate', 0.1),
        ('size_mode', 'fixed'),
        ('fixed_size', 1),
        ('use_trailing_stop', False),
    )

    def log(self, txt, dt=None):
        if self.params.print_log:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        self.order = None
        self.buyprice = None
        self.buycomm = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'买入成交, 价格: {order.executed.price:.2f}, 成本: {order.executed.value:.2f}, 手续费: {order.executed.comm:.2f}')
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            else:
                self.log(f'卖出成交, 价格: {order.executed.price:.2f}, 成本: {order.executed.value:.2f}, 手续费: {order.executed.comm:.2f}')
            
            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('订单已取消/保证金不足/被拒绝')

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        self.log(f'交易利润, 毛利 {trade.pnl:.2f}, 净利 {trade.pnlcomm:.2f}')

    def pre_next(self):
        """
        预处理检查：
        1. 检查是否到达策略启动日期
        2. 检查是否是最后一根K线（如果是则强制平仓）
        """
        # 1. 检查启动日期
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
        
        # 2. 检查数据结束 (强制平仓)
        # 优先使用 buflen 判断 (回测模式)
        is_near_end = False
        if self.datas[0].buflen() > 0:
            # 在倒数第二根K线时发出平仓指令，以便在最后一根K线执行
            if len(self.datas[0]) == self.datas[0].buflen() - 1:
                is_near_end = True
        
        # 辅助使用 end_date 判断 (实盘或 buflen 无效时)
        if not is_near_end and self.params.end_date:
             current_date = self.datas[0].datetime.date(0)
             end_date = self.params.end_date
             if isinstance(end_date, str):
                 try:
                     end_date = datetime.datetime.strptime(end_date, '%Y-%m-%d').date()
                 except:
                     pass
             if isinstance(end_date, datetime.datetime):
                 end_date = end_date.date()
             
             # 如果当前日期 >= 结束日期 (通常用于实盘手动停止时间点)
             if current_date >= end_date:
                 is_near_end = True

        if is_near_end:
            if self.position:
                self.log('数据结束检查: 平掉所有持仓 (市价单)')
                # 使用 Market 单在下一根(即最后一根)K线开盘时立即成交，确保平仓成功
                self.close(exectype=bt.Order.Market) 
            return False # 停止当前K线的其他信号处理
            
        # 最后一根K线直接跳过，防止产生新信号
        if self.datas[0].buflen() > 0 and len(self.datas[0]) >= self.datas[0].buflen():
            return False

        return True

# --- 指标定义 ---
class DKX(bt.Indicator):
    """
    DKX多空线指标
    算法:
    MID = (3*CLOSE + LOW + OPEN + HIGH) / 6
    DKX = (20*MID + 19*REF(MID,1) + ... + 1*REF(MID,19)) / 210
    MADKX = MA(DKX, 10)
    
    修正：
    原代码错误地使用了 SMMA (平滑移动平均)。
    标准 DKX 实际上是 WMA (线性加权移动平均)，权重为 20, 19...1。
    MADKX 通常为 SMA (简单移动平均)。
    """
    lines = ('dkx', 'madkx',)
    params = (('period', 20), ('ma_period', 10),)
    
    def __init__(self):
        # 计算 MID
        mid = (3 * self.data.close + self.data.low + self.data.open + self.data.high) / 6.0
        
        # DKX: 使用加权移动平均 (WMA)
        self.l.dkx = bt.ind.WeightedMovingAverage(mid, period=self.params.period)
        
        # MADKX: 使用简单移动平均 (SMA)
        self.l.madkx = bt.ind.SMA(self.l.dkx, period=self.params.ma_period)

# --- 具体策略类 ---

class TrendFollowingStrategy(BaseStrategy):
    """
    双均线趋势跟踪策略 (默认策略)
    """
    params = (
        ('fast_period', 10),
        ('slow_period', 30),
        ('use_expma', False),
    )

    def __init__(self):
        super().__init__()
        if self.params.use_expma:
            self.ma_fast = bt.ind.EMA(period=self.params.fast_period)
            self.ma_slow = bt.ind.EMA(period=self.params.slow_period)
        else:
            self.ma_fast = bt.ind.SMA(period=self.params.fast_period)
            self.ma_slow = bt.ind.SMA(period=self.params.slow_period)
            
        self.crossover = bt.ind.CrossOver(self.ma_fast, self.ma_slow)

    def next(self):
        if not self.pre_next():
            return
            
        if self.order:
            return

        if self.crossover > 0:
            self.log(f'金叉 (快线 {self.ma_fast[0]:.2f} > 慢线 {self.ma_slow[0]:.2f})')
            self.order = self.order_target_size(target=self.params.fixed_size)
        elif self.crossover < 0:
            self.log(f'死叉 (快线 {self.ma_fast[0]:.2f} < 慢线 {self.ma_slow[0]:.2f})')
            self.order = self.order_target_size(target=-self.params.fixed_size)

class MA5MA20CrossoverStrategy(BaseStrategy):
    """
    5/20双均线交叉策略
    逻辑：
    1. MA5上穿MA20 (金叉) -> 做多
    2. MA5下穿MA20 (死叉) -> 做空
    3. 始终持有仓位，反手操作
    """
    params = (
        ('fast_period', 5),
        ('slow_period', 20),
    )

    def __init__(self):
        super().__init__()
        self.ma_fast = bt.ind.SMA(period=self.params.fast_period)
        self.ma_slow = bt.ind.SMA(period=self.params.slow_period)
        self.crossover = bt.ind.CrossOver(self.ma_fast, self.ma_slow)

    def next(self):
        if not self.pre_next():
            return

        if self.order:
            return

        # 金叉做多
        if self.crossover > 0:
            self.log(f'金叉信号: 做多 (MA{self.params.fast_period}={self.ma_fast[0]:.2f} > MA{self.params.slow_period}={self.ma_slow[0]:.2f})')
            self.order = self.order_target_size(target=self.params.fixed_size)
            
        # 死叉做空
        elif self.crossover < 0:
            self.log(f'死叉信号: 做空 (MA{self.params.fast_period}={self.ma_fast[0]:.2f} < MA{self.params.slow_period}={self.ma_slow[0]:.2f})')
            self.order = self.order_target_size(target=-self.params.fixed_size)

class MA20MA55CrossoverStrategy(BaseStrategy):
    """
    20/55双均线交叉策略 (多空)
    """
    params = (
        ('fast_period', 20),
        ('slow_period', 55),
    )

    def __init__(self):
        super().__init__()
        self.ma_fast = bt.ind.SMA(period=self.params.fast_period)
        self.ma_slow = bt.ind.SMA(period=self.params.slow_period)
        self.crossover = bt.ind.CrossOver(self.ma_fast, self.ma_slow)

    def next(self):
        if not self.pre_next():
            return

        if self.order:
            return

        if self.crossover > 0:
            self.log('买入信号 (金叉)')
            self.order = self.order_target_size(target=self.params.fixed_size)
        elif self.crossover < 0:
            self.log('卖出信号 (死叉)')
            self.order = self.order_target_size(target=-self.params.fixed_size)

class StockMA20MA55LongOnlyStrategy(BaseStrategy):
    """
    20/55双均线多头策略 (仅做多)
    """
    params = (
        ('fast_period', 20),
        ('slow_period', 55),
    )

    def __init__(self):
        super().__init__()
        self.ma_fast = bt.ind.SMA(period=self.params.fast_period)
        self.ma_slow = bt.ind.SMA(period=self.params.slow_period)
        self.crossover = bt.ind.CrossOver(self.ma_fast, self.ma_slow)

    def next(self):
        if not self.pre_next():
            return
            
        if self.order:
            return

        if self.crossover > 0:
            self.log('买入信号 (金叉)')
            self.order = self.order_target_size(target=self.params.fixed_size)
        elif self.crossover < 0:
            if self.position.size > 0:
                self.log('平仓信号 (死叉)')
                self.order = self.close()

class DualMAFixedTPSLStrategy(BaseStrategy):
    """
    20/55双均线交叉(多空) + 固定止盈止损策略
    """
    params = (
        ('fast_period', 20),
        ('slow_period', 55),
        ('ma_type', 'SMA'),
        ('sl_mode', 'points'),
        ('sl_value', 50.0),
        ('tp_mode', 'points'),
        ('tp_value', 100.0),
    )

    def __init__(self):
        super().__init__()
        if self.params.ma_type.upper() == 'EMA':
            self.ma_fast = bt.ind.EMA(period=self.params.fast_period)
            self.ma_slow = bt.ind.EMA(period=self.params.slow_period)
        else:
            self.ma_fast = bt.ind.SMA(period=self.params.fast_period)
            self.ma_slow = bt.ind.SMA(period=self.params.slow_period)
        
        self.crossover = bt.ind.CrossOver(self.ma_fast, self.ma_slow)
        self.sl_order = None
        self.tp_order = None

    def notify_order(self, order):
        # 调用父类基础逻辑
        super().notify_order(order)
        
        if order.status in [order.Completed]:
            # 判断是否为止盈止损单
            is_sl_tp = (self.sl_order and order.ref == self.sl_order.ref) or \
                       (self.tp_order and order.ref == self.tp_order.ref)
            
            if is_sl_tp:
                self.cancel_sl_tp() # 一方成交，取消另一方
            elif order.executed.size != 0: # 开仓或反手成交
                self.place_sl_tp_orders(order.executed.price, self.position.size)

    def place_sl_tp_orders(self, entry_price, size):
        self.cancel_sl_tp()
        
        sl_diff = self.params.sl_value if self.params.sl_mode != 'percent' else entry_price * (self.params.sl_value / 100.0)
        tp_diff = self.params.tp_value if self.params.tp_mode != 'percent' else entry_price * (self.params.tp_value / 100.0)

        if size > 0:
            sl_price = entry_price - sl_diff
            tp_price = entry_price + tp_diff
            self.sl_order = self.sell(size=abs(size), price=sl_price, exectype=bt.Order.Stop)
            self.tp_order = self.sell(size=abs(size), price=tp_price, exectype=bt.Order.Limit)
        elif size < 0:
            sl_price = entry_price + sl_diff
            tp_price = entry_price - tp_diff
            self.sl_order = self.buy(size=abs(size), price=sl_price, exectype=bt.Order.Stop)
            self.tp_order = self.buy(size=abs(size), price=tp_price, exectype=bt.Order.Limit)

    def cancel_sl_tp(self):
        if self.sl_order:
            self.cancel(self.sl_order)
            self.sl_order = None
        if self.tp_order:
            self.cancel(self.tp_order)
            self.tp_order = None

    def next(self):
        if not self.pre_next():
            return
            
        if self.order and self.order.status not in [bt.Order.Completed, bt.Order.Canceled, bt.Order.Margin]:
            return

        if self.crossover > 0:
            self.cancel_sl_tp()
            self.order = self.order_target_size(target=self.params.fixed_size)
        elif self.crossover < 0:
            self.cancel_sl_tp()
            self.order = self.order_target_size(target=-self.params.fixed_size)

class DKXStrategy(BaseStrategy):
    """
    DKX多空线策略
    DKX 金叉 MADKX 做多
    DKX 死叉 MADKX 做空
    """
    params = (
        ('dkx_period', 20),
        ('dkx_ma_period', 10),
    )

    def __init__(self):
        super().__init__()
        self.dkx_ind = DKX(period=self.params.dkx_period, ma_period=self.params.dkx_ma_period)
        self.crossover = bt.ind.CrossOver(self.dkx_ind.dkx, self.dkx_ind.madkx)

    def next(self):
        if not self.pre_next():
            return

        if self.order: return

        if self.crossover > 0:
            self.log(f'DKX金叉: DKX {self.dkx_ind.dkx[0]:.2f} > MADKX {self.dkx_ind.madkx[0]:.2f}')
            self.order = self.order_target_size(target=self.params.fixed_size)
        elif self.crossover < 0:
            self.log(f'DKX死叉: DKX {self.dkx_ind.dkx[0]:.2f} < MADKX {self.dkx_ind.madkx[0]:.2f}')
            self.order = self.order_target_size(target=-self.params.fixed_size)

class DKXFixedTPSLStrategy(DKXStrategy):
    """
    DKX多空线 + 固定止盈止损
    """
    params = (
        ('take_profit_points', 100.0),
        ('stop_loss_points', 50.0),
    )

    def __init__(self):
        super().__init__()
        self.sl_order = None
        self.tp_order = None

    def notify_order(self, order):
        BaseStrategy.notify_order(self, order) # Call BaseStrategy
        
        if order.status in [order.Completed]:
            is_sl_tp = (self.sl_order and order.ref == self.sl_order.ref) or \
                       (self.tp_order and order.ref == self.tp_order.ref)
            
            if is_sl_tp:
                self.cancel_sl_tp()
            elif order.executed.size != 0:
                self.place_sl_tp_orders(order.executed.price, self.position.size)

    def place_sl_tp_orders(self, entry_price, size):
        self.cancel_sl_tp()
        sl_val = self.params.stop_loss_points
        tp_val = self.params.take_profit_points
        
        if size > 0:
            self.sl_order = self.sell(size=abs(size), price=entry_price - sl_val, exectype=bt.Order.Stop)
            self.tp_order = self.sell(size=abs(size), price=entry_price + tp_val, exectype=bt.Order.Limit)
        elif size < 0:
            self.sl_order = self.buy(size=abs(size), price=entry_price + sl_val, exectype=bt.Order.Stop)
            self.tp_order = self.buy(size=abs(size), price=entry_price - tp_val, exectype=bt.Order.Limit)

    def cancel_sl_tp(self):
        if self.sl_order:
            self.cancel(self.sl_order)
            self.sl_order = None
        if self.tp_order:
            self.cancel(self.tp_order)
            self.tp_order = None

    def next(self):
        # Override to cancel SL/TP on reversal
        if not self.pre_next():
            return

        if self.order and self.order.status not in [bt.Order.Completed, bt.Order.Canceled, bt.Order.Margin]:
            return

        if self.crossover > 0:
            self.cancel_sl_tp()
            self.order = self.order_target_size(target=self.params.fixed_size)
        elif self.crossover < 0:
            self.cancel_sl_tp()
            self.order = self.order_target_size(target=-self.params.fixed_size)

class MA20MA55RiskRewardStrategy(BaseStrategy):
    """
    20/55双均线 + 固定盈亏比策略 (量化优化版)
    逻辑：
    1. 入场：MA20金叉MA55做多，死叉做空（维持原逻辑）
    2. 止损：基于ATR的动态止损 (Entry - Multiplier * ATR)
    3. 止盈：基于固定盈亏比 (Risk * RewardRatio)
    4. 反手：若未触发止盈止损，出现反向信号则立即反手
    """
    params = (
        ('fast_period', 20),
        ('slow_period', 55),
        ('risk_reward_ratio', 2.0),   # 盈亏比，默认 2:1
        ('atr_period', 14),           # ATR周期
        ('atr_multiplier', 2.0),      # 止损ATR倍数
    )

    def __init__(self):
        super().__init__()
        self.ma_fast = bt.ind.SMA(period=self.params.fast_period)
        self.ma_slow = bt.ind.SMA(period=self.params.slow_period)
        self.crossover = bt.ind.CrossOver(self.ma_fast, self.ma_slow)
        self.atr = bt.ind.ATR(period=self.params.atr_period)
        
        self.sl_order = None
        self.tp_order = None

    def notify_order(self, order):
        super().notify_order(order)
        
        # 订单完成时处理
        if order.status == order.Completed:
            # 检查是否是止损或止盈单成交
            is_sl_tp = (self.sl_order and order.ref == self.sl_order.ref) or \
                       (self.tp_order and order.ref == self.tp_order.ref)
            
            if is_sl_tp:
                self.log(f'止盈/止损成交: {order.executed.price:.2f}')
                self.cancel_sl_tp()
            
            # 如果是主开仓单成交 (size != 0 且仓位增加/反手)
            elif order.executed.size != 0:
                # 只有当持仓存在时才设置止损止盈
                if self.position.size != 0:
                    self.place_sl_tp_orders(order.executed.price, self.position.size)

    def place_sl_tp_orders(self, entry_price, size):
        # 先取消旧的
        self.cancel_sl_tp()
        
        # 计算动态风险距离 (Risk)
        atr_val = self.atr[0]
        risk_dist = atr_val * self.params.atr_multiplier
        
        # 计算目标盈利距离 (Reward)
        reward_dist = risk_dist * self.params.risk_reward_ratio
        
        if size > 0: # 多头
            sl_price = entry_price - risk_dist
            tp_price = entry_price + reward_dist
            self.log(f'设置多头止损: {sl_price:.2f} (ATR={atr_val:.2f}), 止盈: {tp_price:.2f} (盈亏比={self.params.risk_reward_ratio})')
            
            self.sl_order = self.sell(size=abs(size), price=sl_price, exectype=bt.Order.Stop)
            self.tp_order = self.sell(size=abs(size), price=tp_price, exectype=bt.Order.Limit)
            
        elif size < 0: # 空头
            sl_price = entry_price + risk_dist
            tp_price = entry_price - reward_dist
            self.log(f'设置空头止损: {sl_price:.2f} (ATR={atr_val:.2f}), 止盈: {tp_price:.2f} (盈亏比={self.params.risk_reward_ratio})')
            
            self.sl_order = self.buy(size=abs(size), price=sl_price, exectype=bt.Order.Stop)
            self.tp_order = self.buy(size=abs(size), price=tp_price, exectype=bt.Order.Limit)

    def cancel_sl_tp(self):
        if self.sl_order:
            self.cancel(self.sl_order)
            self.sl_order = None
        if self.tp_order:
            self.cancel(self.tp_order)
            self.tp_order = None

    def next(self):
        if not self.pre_next():
            return

        if self.order and self.order.status not in [bt.Order.Completed, bt.Order.Canceled, bt.Order.Rejected, bt.Order.Margin]:
            return

        # 信号逻辑：均线交叉
        if self.crossover > 0: # 金叉
            # 无论当前是否有空单，直接反手做多 (target=fixed_size)
            # 如果之前有止损止盈单，notify_order 会处理取消，或者这里显式取消更安全
            self.cancel_sl_tp() 
            self.log(f'金叉信号: 做多 (MA{self.params.fast_period}={self.ma_fast[0]:.2f} > MA{self.params.slow_period}={self.ma_slow[0]:.2f})')
            self.order = self.order_target_size(target=self.params.fixed_size)
            
        elif self.crossover < 0: # 死叉
            self.cancel_sl_tp()
            self.log(f'死叉信号: 做空 (MA{self.params.fast_period}={self.ma_fast[0]:.2f} < MA{self.params.slow_period}={self.ma_slow[0]:.2f})')
            self.order = self.order_target_size(target=-self.params.fixed_size)

class DKXPartialTakeProfitStrategy(DKXStrategy):
    """
    DKX + 盈利平半仓 (简化版，仅平仓一次)
    """
    params = (
        ('take_profit_points', 50.0),
    )
    
    def __init__(self):
        super().__init__()
        self.tp_executed = False # 标记当前持仓是否已执行过减仓
        self.entry_price = 0.0

    def notify_order(self, order):
        BaseStrategy.notify_order(self, order)
        if order.status == order.Completed:
            if order.executed.size != 0:
                # 如果是开新仓或反手
                if abs(self.position.size) >= self.params.fixed_size:
                    self.tp_executed = False
                    self.entry_price = order.executed.price

    def next(self):
        super().next() # 执行信号逻辑
        
        # 如果是最后两根K线（已在pre_next处理平仓或跳过），则停止后续逻辑
        if len(self.datas[0]) >= self.datas[0].buflen() - 1:
            return

        # 止盈逻辑
        if self.position.size != 0 and not self.tp_executed:
            profit_points = 0
            if self.position.size > 0:
                profit_points = self.data.close[0] - self.entry_price
            else:
                profit_points = self.entry_price - self.data.close[0]
                
            if profit_points >= self.params.take_profit_points:
                self.log(f'Partial TP Triggered: Profit {profit_points:.2f}')
                target = int(self.position.size / 2)
                # 保持方向
                if target == 0 and self.position.size != 0: 
                    target = 0 # 如果只剩1手，是否全平？这里假设不全平，或者设为0
                
                self.close(size=self.position.size - target) # 平掉一半
                self.tp_executed = True

class MA55BreakoutStrategy(BaseStrategy):
    """
    MA55 突破策略 (简化恢复版)
    逻辑: 收盘价突破 MA55 做多/做空
    """
    params = (
        ('ma_period', 55),
        ('macd_fast', 12),
        ('macd_slow', 26),
        ('macd_signal', 9),
    )

    def __init__(self):
        super().__init__()
        self.ma = bt.ind.SMA(period=self.params.ma_period)

    def next(self):
        if not self.pre_next(): return
        if self.order: return

        if self.data.close[0] > self.ma[0] and self.data.close[-1] <= self.ma[-1]:
            self.order = self.order_target_size(target=self.params.fixed_size)
        elif self.data.close[0] < self.ma[0] and self.data.close[-1] >= self.ma[-1]:
            self.order = self.order_target_size(target=-self.params.fixed_size)

class MA55TouchExitStrategy(BaseStrategy):
    """
    MA55 突破 + 触碰平仓 (简化恢复版)
    """
    params = (
        ('ma_period', 55),
        ('weak_threshold', 7.0),
    )

    def __init__(self):
        super().__init__()
        self.ma = bt.ind.SMA(period=self.params.ma_period)

    def next(self):
        if not self.pre_next(): return
        if self.order: return

        # 简单的突破开仓
        if self.position.size == 0:
            if self.data.close[0] > self.ma[0]:
                self.order = self.order_target_size(target=self.params.fixed_size)
            elif self.data.close[0] < self.ma[0]:
                self.order = self.order_target_size(target=-self.params.fixed_size)
        else:
            # 触碰均线平仓
            if self.position.size > 0 and self.data.low[0] <= self.ma[0]:
                self.close()
            elif self.position.size < 0 and self.data.high[0] >= self.ma[0]:
                self.close()

class MA20MA55PartialTakeProfitStrategy(MA20MA55CrossoverStrategy):
    """
    20/55 双均线 + 盈利平半仓
    """
    params = (
        ('take_profit_points', 50.0),
    )
    
    def __init__(self):
        super().__init__()
        self.tp_executed = False
        self.entry_price = 0.0

    def notify_order(self, order):
        BaseStrategy.notify_order(self, order)
        if order.status == order.Completed:
            if abs(self.position.size) >= self.params.fixed_size:
                self.tp_executed = False
                self.entry_price = order.executed.price

    def next(self):
        super().next()
        
        # 如果是最后两根K线（已在pre_next处理平仓或跳过），则停止后续逻辑
        if len(self.datas[0]) >= self.datas[0].buflen() - 1:
            return

        if self.position.size != 0 and not self.tp_executed:
            profit = 0
            if self.position.size > 0:
                profit = self.data.close[0] - self.entry_price
            else:
                profit = self.entry_price - self.data.close[0]
            
            if profit >= self.params.take_profit_points:
                self.log(f'Partial TP: {profit:.2f}')
                self.close(size=self.position.size / 2)
                self.tp_executed = True
