import backtrader as bt
import datetime

class TrendFollowingStrategy(bt.Strategy):
    """
    趋势跟踪策略：
    1. 信号：双均线交叉 (Fast SMA vs Slow SMA)
    2. 风控：ATR 移动止损
    3. 仓位管理：基于账户权益百分比的风险敞口计算
    """
    params = (
        ('fast_period', 10),      # 快速均线周期
        ('slow_period', 30),      # 慢速均线周期
        ('atr_period', 14),       # ATR周期
        ('atr_multiplier', 2.0),  # ATR止损倍数
        ('risk_per_trade', 0.02), # 每笔交易风险 (2% of equity)
        ('contract_multiplier', 1), # 合约乘数 (期货使用)
        ('use_expma', False),     # 是否使用指数移动平均 (EXPMA)
        ('print_log', True),      # 是否打印日志
    )

    def log(self, txt, dt=None):
        """ 日志记录函数 """
        if self.params.print_log:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        # 初始化指标
        if self.params.use_expma:
            # 使用指数移动平均 (EXPMA/EMA)
            self.sma_fast = bt.indicators.ExponentialMovingAverage(
                self.datas[0], period=self.params.fast_period)
            self.sma_slow = bt.indicators.ExponentialMovingAverage(
                self.datas[0], period=self.params.slow_period)
        else:
            # 使用简单移动平均 (SMA)
            self.sma_fast = bt.indicators.SimpleMovingAverage(
                self.datas[0], period=self.params.fast_period)
            self.sma_slow = bt.indicators.SimpleMovingAverage(
                self.datas[0], period=self.params.slow_period)
        
        self.atr = bt.indicators.ATR(
            self.datas[0], period=self.params.atr_period)
        
        # 交叉信号
        self.crossover = bt.indicators.CrossOver(self.sma_fast, self.sma_slow)
        
        # 交易状态变量
        self.stop_price = None  # 止损价格
        self.order = None       # 当前挂单

    def notify_order(self, order):
        """ 订单状态更新通知 """
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'买入执行: 价格: {order.executed.price:.2f}, 成本: {order.executed.value:.2f}, 手续费: {order.executed.comm:.2f}')
            elif order.issell():
                self.log(f'卖出执行: 价格: {order.executed.price:.2f}, 成本: {order.executed.value:.2f}, 手续费: {order.executed.comm:.2f}')
            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('订单取消/保证金不足/拒绝')

        self.order = None

    def notify_trade(self, trade):
        """ 交易结束通知 """
        if not trade.isclosed:
            return
        self.log(f'交易利润: 毛利 {trade.pnl:.2f}, 净利 {trade.pnlcomm:.2f}')

    def next(self):
        """ 主策略逻辑 """
        # 如果有订单正在处理，不进行新操作
        if self.order:
            return

        # 获取当前账户价值
        value = self.broker.get_value()
        
        # 调试信号 (每100天打一次，或者有信号时打)
        # if len(self) % 100 == 0:
        #    self.log(f'Close: {self.datas[0].close[0]:.2f}, SMA10: {self.sma_fast[0]:.2f}, SMA30: {self.sma_slow[0]:.2f}, Cross: {self.crossover[0]}')

        # 1. 没有持仓
        if not self.position:
            # 金叉买入
            if self.crossover > 0:
                # 计算止损距离
                atr_value = self.atr[0]
                stop_dist = atr_value * self.params.atr_multiplier
                self.stop_price = self.datas[0].close[0] - stop_dist
                
                # 计算仓位大小 (基于风险)
                # Risk Amount = Size * (Entry - Stop) * Multiplier
                # Size = Risk Amount / ((Entry - Stop) * Multiplier)
                risk_amount = value * self.params.risk_per_trade
                risk_per_unit = stop_dist * self.params.contract_multiplier
                
                size = 0
                if risk_per_unit > 0:
                    size = int(risk_amount / risk_per_unit)
                    # 调试日志
                    # self.log(f'计算仓位: 权益{value:.0f}, 风险金{risk_amount:.0f}, ATR{atr_value:.1f}, 止损距{stop_dist:.1f}, 单手风险{risk_per_unit:.1f}, 数量{size}')
                
                if size > 0:
                    self.log(f'买入信号: 收盘价 {self.datas[0].close[0]:.2f}, ATR {atr_value:.2f}, 目标仓位 {size}')
                    self.order = self.buy(size=size)
                    
        # 2. 持有仓位
        else:
            # 死叉卖出平仓
            if self.crossover < 0:
                self.log(f'卖出信号 (死叉): 收盘价 {self.datas[0].close[0]:.2f}')
                self.order = self.close()
            
            # 移动止损逻辑
            else:
                # 如果价格上涨，提高止损线 (只升不降)
                atr_value = self.atr[0]
                new_stop_price = self.datas[0].close[0] - (atr_value * self.params.atr_multiplier)
                
                if self.stop_price and new_stop_price > self.stop_price:
                    self.stop_price = new_stop_price
                
                # 检查是否触发止损
                if self.datas[0].close[0] < self.stop_price:
                    self.log(f'止损触发: 当前价 {self.datas[0].close[0]:.2f} < 止损价 {self.stop_price:.2f}')
                    self.order = self.close()

class MA55BreakoutStrategy(bt.Strategy):
    """
    MA55 突破与 MACD 背离策略
    1. 开仓：突破 55 周期均线
    2. 离场：多头顶背离 / 空头底背离 / ATR 移动止损
    """
    params = (
        ('ma_period', 55),       # 均线周期
        ('macd_fast', 12),       # MACD 快线
        ('macd_slow', 26),       # MACD 慢线
        ('macd_signal', 9),      # MACD 信号线
        ('atr_period', 14),      # ATR 周期
        ('atr_multiplier', 3.0), # ATR 止损倍数 (默认放宽，以便背离离场)
        ('risk_per_trade', 0.02),# 每笔风险
        ('size_mode', 'atr_risk'), # 开仓模式: 'fixed' 或 'atr_risk'
        ('fixed_size', 1),       # 固定手数
        ('contract_multiplier', 1), # 合约乘数
        ('use_trailing_stop', False), # 是否使用移动止损 (默认为False，主要依靠背离)
        ('print_log', True),     # 打印日志
    )

    def log(self, txt, dt=None):
        if self.params.print_log:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        super(MA55BreakoutStrategy, self).__init__()
        # 均线
        self.ma55 = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.ma_period)
        
        # MACD
        self.macd = bt.indicators.MACD(
            self.datas[0], 
            period_me1=self.params.macd_fast, 
            period_me2=self.params.macd_slow, 
            period_signal=self.params.macd_signal
        )
        
        self.atr = bt.indicators.ATR(self.datas[0], period=self.params.atr_period)
        
        # 突破信号: 收盘价上穿/下穿 MA55
        self.crossover_ma = bt.indicators.CrossOver(self.datas[0].close, self.ma55)
        
        # MACD 交叉信号 (用于背离判断的锚点)
        self.crossover_macd = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)
        
        # 交易状态
        self.stop_price = None
        self.order = None
        
        # 背离检测状态变量
        # 记录上一次 MACD 死叉/金叉时的价格极值和 MACD 极值
        self.last_dead_cross_high_price = 0
        self.last_dead_cross_macd_max = -9999
        self.last_gold_cross_low_price = 999999
        self.last_gold_cross_macd_min = 9999
        
        # 当前波段的极值记录
        self.current_wave_high_price = 0
        self.current_wave_macd_max = -9999
        self.current_wave_low_price = 999999
        self.current_wave_macd_min = 9999

    def start(self):
        if self.params.print_log:
             mode_desc = f"固定手数({self.params.fixed_size})" if self.params.size_mode == 'fixed' else f"ATR风险({self.params.risk_per_trade})"
             self.log(f"策略启动: MA55突破, 开仓模式: {mode_desc}, ATR倍数: {self.params.atr_multiplier}, 移动止损: {self.params.use_trailing_stop}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'买入执行: {order.executed.price:.2f}')
            elif order.issell():
                self.log(f'卖出执行: {order.executed.price:.2f}')
        self.order = None

    def next(self):
        # if self.order:
        #    return
            
        value = self.broker.get_value()
        close = self.datas[0].close[0]
        macd_val = self.macd.macd[0]
        hist_val = self.macd.macd[0] - self.macd.signal[0] # 手动计算hist以便确认
        
        # --- 维护波段极值 (简化背离所需数据) ---
        # 如果 MACD 柱状图 > 0 (红柱区域)，记录最高价和最高MACD
        if hist_val > 0:
            self.current_wave_high_price = max(self.current_wave_high_price, self.datas[0].high[0])
            self.current_wave_macd_max = max(self.current_wave_macd_max, macd_val)
            # 重置绿柱极值
            self.current_wave_low_price = 999999
            self.current_wave_macd_min = 9999
            
        # 如果 MACD 柱状图 < 0 (绿柱区域)，记录最低价和最低MACD
        else:
            self.current_wave_low_price = min(self.current_wave_low_price, self.datas[0].low[0])
            self.current_wave_macd_min = min(self.current_wave_macd_min, macd_val)
            # 重置红柱极值
            self.current_wave_high_price = 0
            self.current_wave_macd_max = -9999

        # --- 信号检测 ---
        
        # 1. 背离离场逻辑 (在死叉/金叉发生时刻判断)
        
        divergence_exit = False
        
        # 检测 MACD 死叉 (红变绿) -> 检查顶背离
        if self.crossover_macd < 0:
            # 发生了死叉，比较本次红柱波峰与上次红柱波峰
            if self.last_dead_cross_high_price > 0: # 确保不是第一次
                # 顶背离：价格创新高，MACD未创新高
                if self.current_wave_high_price > self.last_dead_cross_high_price and \
                   self.current_wave_macd_max < self.last_dead_cross_macd_max:
                    
                    self.log(f'[背离检测] 顶背离: 价格 {self.current_wave_high_price:.2f} > {self.last_dead_cross_high_price:.2f}, MACD {self.current_wave_macd_max:.2f} < {self.last_dead_cross_macd_max:.2f}')
                    
                    # 如果持有多单，标记离场信号
                    if self.position.size > 0:
                        self.log(f'>>> 顶背离信号触发')
                        divergence_exit = True
            
            # 更新历史记录
            self.last_dead_cross_high_price = self.current_wave_high_price
            self.last_dead_cross_macd_max = self.current_wave_macd_max

        # 检测 MACD 金叉 (绿变红) -> 检查底背离
        elif self.crossover_macd > 0:
            # 发生了金叉
            if self.last_gold_cross_low_price < 999999:
                # 底背离：价格创新低，MACD未创新低
                if self.current_wave_low_price < self.last_gold_cross_low_price and \
                   self.current_wave_macd_min > self.last_gold_cross_macd_min:
                    
                    self.log(f'[背离检测] 底背离: 价格 {self.current_wave_low_price:.2f} < {self.last_gold_cross_low_price:.2f}, MACD {self.current_wave_macd_min:.2f} > {self.last_gold_cross_macd_min:.2f}')
                    
                    # 如果持有空单，标记离场信号
                    if self.position.size < 0:
                        self.log(f'>>> 底背离信号触发')
                        divergence_exit = True

            # 更新历史记录
            self.last_gold_cross_low_price = self.current_wave_low_price
            self.last_gold_cross_macd_min = self.current_wave_macd_min

        # 2. 突破信号处理 (开仓 & 反手)
        # 只要有突破信号，无论是否有仓位，都进行开仓/反手操作
        
        has_breakout = False
        
        # 上穿 MA55 -> 做多
        if self.crossover_ma[0] > 0:
            self.log(f'MA55 向上突破信号检测: Close {close:.2f} > MA55 {self.ma55[0]:.2f}')
            has_breakout = True
            
            # 计算止损和仓位
            atr_val = self.atr[0]
            stop_dist = atr_val * self.params.atr_multiplier
            new_stop_price = close - stop_dist
            
            size = 0
            if self.params.size_mode == 'fixed':
                try:
                    size = int(self.params.fixed_size) if self.params.fixed_size is not None else 1
                except (ValueError, TypeError):
                    size = 1
            else:
                risk_amt = value * self.params.risk_per_trade
                risk_unit = stop_dist * self.params.contract_multiplier
                size = int(risk_amt / risk_unit) if risk_unit > 0 else 0
            
            if size is not None and size > 0:
                # 使用 order_target_size 自动处理平仓+开仓 (反手)
                self.log(f'做多/反手做多: 目标持仓 {size}')
                self.order = self.order_target_size(target=size)
                self.stop_price = new_stop_price # 更新止损价
            else:
                self.log(f'做多信号触发但仓位计算为0! 权益: {value:.2f}, 风险: {self.params.risk_per_trade}, StopDist: {stop_dist:.2f}')
        
        # 下穿 MA55 -> 做空
        elif self.crossover_ma[0] < 0:
            self.log(f'MA55 向下突破信号检测: Close {close:.2f} < MA55 {self.ma55[0]:.2f}')
            has_breakout = True
            
            # 计算止损和仓位
            atr_val = self.atr[0]
            stop_dist = atr_val * self.params.atr_multiplier
            new_stop_price = close + stop_dist # 空单止损在上方
            
            size = 0
            if self.params.size_mode == 'fixed':
                try:
                    size = int(self.params.fixed_size) if self.params.fixed_size is not None else 1
                except (ValueError, TypeError):
                    size = 1
            else:
                risk_amt = value * self.params.risk_per_trade
                risk_unit = stop_dist * self.params.contract_multiplier
                size = int(risk_amt / risk_unit) if risk_unit > 0 else 0
            
            if size is not None and size > 0:
                # 做空到目标仓位 (负数)
                self.log(f'做空/反手做空: 目标持仓 {-size}')
                self.order = self.order_target_size(target=-size)
                self.stop_price = new_stop_price
            else:
                 self.log(f'做空信号触发但仓位计算为0! 权益: {value:.2f}, 风险: {self.params.risk_per_trade}, StopDist: {stop_dist:.2f}')
        
        # 3. 如果没有突破，处理离场或持仓管理
        if not has_breakout:
            if divergence_exit:
                self.log(f'执行背离离场')
                self.order = self.close()
                
            elif self.position:
                # 如果启用了移动止损
                if self.params.use_trailing_stop:
                    # 如果是多单
                    if self.position.size > 0:
                        # 移动止损
                        atr_val = self.atr[0]
                        new_stop = close - (atr_val * self.params.atr_multiplier)
                        if new_stop > self.stop_price:
                            self.stop_price = new_stop
                        
                        if close < self.stop_price:
                            self.log(f'多单止损触发: {close:.2f} < {self.stop_price:.2f}')
                            self.order = self.close()
                    
                    # 如果是空单
                    elif self.position.size < 0:
                        atr_val = self.atr[0]
                        new_stop = close + (atr_val * self.params.atr_multiplier)
                        if new_stop < self.stop_price:
                            self.stop_price = new_stop
                        
                        if close > self.stop_price:
                            self.log(f'空单止损触发: {close:.2f} > {self.stop_price:.2f}')
                            self.order = self.close()
                
                # 如果未启用移动止损，则仅使用开仓时的固定止损 (Hard Stop)
                else:
                    if self.stop_price:
                         if self.position.size > 0 and close < self.stop_price:
                             self.log(f'多单固定止损触发: {close:.2f} < {self.stop_price:.2f}')
                             self.order = self.close()
                         elif self.position.size < 0 and close > self.stop_price:
                             self.log(f'空单固定止损触发: {close:.2f} > {self.stop_price:.2f}')
                             self.order = self.close()

class MA55TouchExitStrategy(bt.Strategy):
    """
    MA55 触碰平仓策略
    1. 开仓：突破 55 周期均线
    2. 平仓：价格回落/反弹触碰 55 周期均线
    """
    params = (
        ('ma_period', 55),       # 均线周期
        ('risk_per_trade', 0.02),# 每笔风险
        ('size_mode', 'atr_risk'), # 开仓模式: 'fixed' 或 'atr_risk'
        ('fixed_size', 1),       # 固定手数
        ('contract_multiplier', 1), # 合约乘数
        ('atr_period', 14),      # ATR 周期 (仅用于计算仓位)
        ('atr_multiplier', 3.0), # ATR 止损倍数 (仅用于计算仓位止损距离)
        ('weak_threshold', 7.0), # 弱势突破阈值 (点数)
        ('print_log', True),     # 打印日志
    )

    def log(self, txt, dt=None):
        if self.params.print_log:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        super(MA55TouchExitStrategy, self).__init__()
        # 均线
        self.ma55 = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.ma_period)
        
        self.atr = bt.indicators.ATR(self.datas[0], period=self.params.atr_period)
        
        # 突破信号: 收盘价上穿/下穿 MA55
        self.crossover_ma = bt.indicators.CrossOver(self.datas[0].close, self.ma55)
        
        self.order = None
        
        # 策略状态变量
        self.entry_bar_index = -1       # 开仓时的 Bar 索引
        self.entry_bar_close = 0        # 开仓时 K 线的收盘价
        
        self.bar1_checked = False       # 是否已检查第二根 K 线
        self.is_weak_breakout = False   # 是否为弱势突破
        self.bar1_high = 0              # 第二根 K 线最高价
        self.bar1_low = 0               # 第二根 K 线最低价
        
        self.pending_exit_check = False # 是否处于等待平仓确认状态

    def start(self):
        if self.params.print_log:
             mode_desc = f"固定手数({self.params.fixed_size})" if self.params.size_mode == 'fixed' else f"ATR风险({self.params.risk_per_trade})"
             self.log(f"策略启动: MA55触碰平仓, 开仓模式: {mode_desc}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'买入执行: {order.executed.price:.2f}')
            elif order.issell():
                self.log(f'卖出执行: {order.executed.price:.2f}')
        self.order = None

    def next(self):
        # 移除了订单等待检查，以便反手
        
        value = self.broker.get_value()
        close = self.datas[0].close[0]
        low = self.datas[0].low[0]
        high = self.datas[0].high[0]
        ma_val = self.ma55[0]
        
        current_idx = len(self)

        has_signal = False

        # 1. 突破信号 (优先于平仓)
        if self.crossover_ma[0] > 0:
            self.log(f'MA55 向上突破: {close:.2f} > {ma_val:.2f}')
            has_signal = True
            
            # 初始化状态
            self.entry_bar_index = current_idx
            self.entry_bar_close = close
            self.bar1_checked = False
            self.is_weak_breakout = False
            self.pending_exit_check = False
            
            # 计算仓位
            atr_val = self.atr[0]
            stop_dist = atr_val * self.params.atr_multiplier # 用于风险计算的止损距离
            
            size = 0
            if self.params.size_mode == 'fixed':
                try:
                    size = int(self.params.fixed_size) if self.params.fixed_size is not None else 1
                except (ValueError, TypeError):
                    size = 1
            else:
                risk_amt = value * self.params.risk_per_trade
                risk_unit = stop_dist * self.params.contract_multiplier
                size = int(risk_amt / risk_unit) if risk_unit > 0 else 0
            
            if size > 0:
                self.log(f'做多/反手做多: 目标持仓 {size}')
                self.order = self.order_target_size(target=size)
            else:
                self.log(f'警告: 做多信号触发但仓位计算为0! 权益: {value:.2f}, 风险: {self.params.risk_per_trade}')
                # 如果持有空单且触发了做多信号，即使新仓位为0，也应该平掉空单
                if self.position.size < 0:
                     self.log('强制平空 (反手仓位为0)')
                     self.order = self.close()

        elif self.crossover_ma[0] < 0:
            self.log(f'MA55 向下突破: {close:.2f} < {ma_val:.2f}')
            has_signal = True
            
            # 初始化状态
            self.entry_bar_index = current_idx
            self.entry_bar_close = close
            self.bar1_checked = False
            self.is_weak_breakout = False
            self.pending_exit_check = False
            
            # 计算仓位
            atr_val = self.atr[0]
            stop_dist = atr_val * self.params.atr_multiplier
            
            size = 0
            if self.params.size_mode == 'fixed':
                try:
                    size = int(self.params.fixed_size) if self.params.fixed_size is not None else 1
                except (ValueError, TypeError):
                    size = 1
            else:
                risk_amt = value * self.params.risk_per_trade
                risk_unit = stop_dist * self.params.contract_multiplier
                size = int(risk_amt / risk_unit) if risk_unit > 0 else 0
            
            if size > 0:
                self.log(f'做空/反手做空: 目标持仓 {-size}')
                self.order = self.order_target_size(target=-size)
            else:
                self.log(f'警告: 做空信号触发但仓位计算为0! 权益: {value:.2f}, 风险: {self.params.risk_per_trade}')
                # 如果持有多单且触发了做空信号，即使新仓位为0，也应该平掉多单
                if self.position.size > 0:
                     self.log('强制平多 (反手仓位为0)')
                     self.order = self.close()

        # 2. 状态更新 (检查第二根K线)
        if self.position and not has_signal:
             # 如果当前是开仓后的第二根K线 (Entry + 1)
             if current_idx == self.entry_bar_index + 1:
                 diff = close - self.entry_bar_close
                 
                 # 多单检查
                 if self.position.size > 0:
                     self.bar1_high = high # 记录第二根的最高价
                     if diff <= self.params.weak_threshold:
                         self.is_weak_breakout = True
                         self.log(f'弱势突破确认: 涨幅 {diff:.2f} <= {self.params.weak_threshold}, 启用延迟平仓逻辑')
                     else:
                         self.log(f'强势突破确认: 涨幅 {diff:.2f} > {self.params.weak_threshold}')
                 
                 # 空单检查
                 elif self.position.size < 0:
                     self.bar1_low = low # 记录第二根的最低价
                     # 空单跌幅应为负数，比较绝对跌幅是否足够大，或者看是否跌了7个点以上 (Close < Entry - 7)
                     # 也就是说 Entry - Close > 7 => Close - Entry < -7
                     # 用户说"不高于第一根7个点"，对于空单应该是"不低于第一根7个点"?
                     # 意图是：如果没有显著下跌（跌幅不够）。
                     # 所以如果是下跌： Entry - Close <= 7  => Close >= Entry - 7
                     if (self.entry_bar_close - close) <= self.params.weak_threshold:
                         self.is_weak_breakout = True
                         self.log(f'弱势突破确认: 跌幅 {(self.entry_bar_close - close):.2f} <= {self.params.weak_threshold}, 启用延迟平仓逻辑')
                     else:
                         self.log(f'强势突破确认: 跌幅 {(self.entry_bar_close - close):.2f} > {self.params.weak_threshold}')

        # 3. 平仓逻辑
        if not has_signal and self.position:
            # 优先处理待定平仓状态 (Pending Exit)
            if self.pending_exit_check:
                # 多单：等待下一根不高于第二根 (Close <= Bar1_High)
                if self.position.size > 0:
                    if close <= self.bar1_high:
                         self.log(f'延迟平仓触发: 收盘价 {close:.2f} <= 第二根高点 {self.bar1_high:.2f}')
                         self.order = self.close()
                    else:
                         self.log(f'延迟平仓取消: 价格反弹 {close:.2f} > {self.bar1_high:.2f}, 继续持仓')
                
                # 空单：等待下一根不低于第二根 (Close >= Bar1_Low)
                elif self.position.size < 0:
                    if close >= self.bar1_low:
                        self.log(f'延迟平仓触发: 收盘价 {close:.2f} >= 第二根低点 {self.bar1_low:.2f}')
                        self.order = self.close()
                    else:
                        self.log(f'延迟平仓取消: 价格回落 {close:.2f} < {self.bar1_low:.2f}, 继续持仓')
                
                # 无论是否平仓，Pending状态解除 (只检查一根)
                # 或者用户意思是一直等？"也要等下一个线不高于第二根才能平仓"
                # 如果这根不行，下根继续等？通常"等下一个线"暗示只看下一根。
                # 但为了安全，如果反弹了就不平了，回归正常碰线检查比较合理。
                self.pending_exit_check = False
                return # 本次循环结束

            # 常规碰线检查
            # 多单持仓
            if self.position.size > 0:
                # 价格回落触碰/跌破 MA55 (使用 Low 判断盘中触碰)
                if low <= ma_val:
                     if self.is_weak_breakout:
                         # 弱势突破，进入延迟检查
                         self.log(f'多单触碰均线 (Low {low:.2f} <= MA {ma_val:.2f}), 但由于弱势突破，等待下一根确认')
                         self.pending_exit_check = True
                     else:
                         self.log(f'多单盘中触碰均线平仓: Low {low:.2f} <= MA {ma_val:.2f}')
                         self.order = self.close()
            
            # 空单持仓
            elif self.position.size < 0:
                # 价格反弹触碰/升破 MA55 (使用 High 判断盘中触碰)
                if high >= ma_val:
                    if self.is_weak_breakout:
                        # 弱势突破，进入延迟检查
                        self.log(f'空单触碰均线 (High {high:.2f} >= MA {ma_val:.2f}), 但由于弱势突破，等待下一根确认')
                        self.pending_exit_check = True
                    else:
                        self.log(f'空单盘中触碰均线平仓: High {high:.2f} >= MA {ma_val:.2f}')
                        self.order = self.close()
