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
        ('atr_multiplier', 2.0), # ATR 止损倍数
        ('risk_per_trade', 0.02),# 每笔风险
        ('size_mode', 'atr_risk'), # 开仓模式: 'fixed' 或 'atr_risk'
        ('fixed_size', 1),       # 固定手数
        ('contract_multiplier', 1), # 合约乘数
        ('print_log', True),     # 打印日志
    )

    def log(self, txt, dt=None):
        if self.params.print_log:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
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
        if self.order:
            return
            
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
                    # 如果持有多单，离场
                    if self.position.size > 0:
                        self.log(f'顶背离触发离场: 价格新高 {self.current_wave_high_price:.2f} > {self.last_dead_cross_high_price:.2f}, MACD {self.current_wave_macd_max:.2f} < {self.last_dead_cross_macd_max:.2f}')
                        self.order = self.close()
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
                    # 如果持有空单，离场
                    if self.position.size < 0:
                        self.log(f'底背离触发离场: 价格新低 {self.current_wave_low_price:.2f} < {self.last_gold_cross_low_price:.2f}, MACD {self.current_wave_macd_min:.2f} > {self.last_gold_cross_macd_min:.2f}')
                        self.order = self.close()
                        divergence_exit = True

            # 更新历史记录
            self.last_gold_cross_low_price = self.current_wave_low_price
            self.last_gold_cross_macd_min = self.current_wave_macd_min

        if divergence_exit:
            return

        if divergence_exit:
            return

        # 2. 突破信号处理 (开仓 & 反手)
        # 只要有突破信号，无论是否有仓位，都进行开仓/反手操作
        
        # 上穿 MA55 -> 做多
        if self.crossover_ma > 0:
            self.log(f'MA55 向上突破: {close:.2f} > {self.ma55[0]:.2f}')
            
            # 计算止损和仓位
            atr_val = self.atr[0]
            stop_dist = atr_val * self.params.atr_multiplier
            new_stop_price = close - stop_dist
            
            size = 0
            if self.params.size_mode == 'fixed':
                size = self.params.fixed_size or 1
            else:
                risk_amt = value * self.params.risk_per_trade
                risk_unit = stop_dist * self.params.contract_multiplier
                size = int(risk_amt / risk_unit) if risk_unit > 0 else 0
            
            if size is not None and size > 0:
                # 使用 order_target_size 自动处理平仓+开仓 (反手)
                self.log(f'做多/反手做多: 目标持仓 {size}')
                self.order = self.order_target_size(target=size)
                self.stop_price = new_stop_price # 更新止损价
        
        # 下穿 MA55 -> 做空
        elif self.crossover_ma < 0:
            self.log(f'MA55 向下突破: {close:.2f} < {self.ma55[0]:.2f}')
            
            # 计算止损和仓位
            atr_val = self.atr[0]
            stop_dist = atr_val * self.params.atr_multiplier
            new_stop_price = close + stop_dist # 空单止损在上方
            
            size = 0
            if self.params.size_mode == 'fixed':
                size = self.params.fixed_size or 1
            else:
                risk_amt = value * self.params.risk_per_trade
                risk_unit = stop_dist * self.params.contract_multiplier
                size = int(risk_amt / risk_unit) if risk_unit > 0 else 0
            
            if size is not None and size > 0:
                # 做空到目标仓位 (负数)
                self.log(f'做空/反手做空: 目标持仓 {-size}')
                self.order = self.order_target_size(target=-size)
                self.stop_price = new_stop_price
        
        # 3. 持仓管理 (仅在无新信号时执行移动止损)
        elif self.position:
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
