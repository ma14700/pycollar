import backtrader as bt
import pandas as pd
import datetime
import pandas as pd

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
        ('size_mode', 'fixed'), # 开仓模式: 'fixed', 'equity_percent', 'atr_risk'
        ('fixed_size', 20),       # 固定手数
        ('equity_percent', 0.1), # 资金比例 (0.1 = 10%)
        ('margin_rate', 0.1),    # 保证金率 (0.1 = 10%)
        ('start_date', None),    # 策略启动日期 (YYYY-MM-DD)，在此之前不交易
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
        
        # 记录最大盈利/亏损点数
        self.max_profit_points = 0.0
        self.max_loss_points = 0.0

    def _calculate_size(self, value):
        atr_val = self.atr[0]
        close = self.datas[0].close[0]
        mode = self.params.size_mode
        size = 0
        if mode == 'fixed':
            try:
                size = int(self.params.fixed_size) if self.params.fixed_size is not None else 0
            except (ValueError, TypeError):
                size = 0
        elif mode == 'equity_percent':
            target_value = value * self.params.equity_percent
            one_hand_margin = close * self.params.contract_multiplier * self.params.margin_rate
            size = int(target_value / one_hand_margin) if one_hand_margin > 0 else 0
        else:
            stop_dist = atr_val * self.params.atr_multiplier
            risk_amt = value * self.params.risk_per_trade
            risk_unit = stop_dist * self.params.contract_multiplier
            size = int(risk_amt / risk_unit) if risk_unit > 0 else 0
        if size <= 0:
            fallback = 0
            try:
                fallback = int(self.params.fixed_size) if self.params.fixed_size is not None else 0
            except (ValueError, TypeError):
                fallback = 0
            size = fallback if fallback > 0 else 1
        return size

    def start(self):
        if self.params.print_log:
            self.log(f"策略启动: TrendFollowingStrategy (趋势跟踪), 参数: Fast={self.params.fast_period}, Slow={self.params.slow_period}, ATR={self.params.atr_period}x{self.params.atr_multiplier}")


    def notify_order(self, order):
        """ 订单状态更新通知 """
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            action = "买入" if order.isbuy() else "卖出"
            current_pos = self.position.size
            exec_size = order.executed.size
            msg = f'{action}执行: 价格: {order.executed.price:.2f}, 成交数量: {exec_size} (当前持仓: {current_pos}), 成本: {order.executed.value:.2f}, 手续费: {order.executed.comm:.2f}'
            self.log(msg)
            
            # 记录平仓/反手导致的手数变化，用于 notify_trade 计算点数
            prev_pos = current_pos - exec_size
            if (prev_pos > 0 and exec_size < 0) or (prev_pos < 0 and exec_size > 0):
                self.last_closed_trade_size = min(abs(prev_pos), abs(exec_size))
                
            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('订单取消/保证金不足/拒绝')

        self.order = None

    def stop(self):
        """ 策略结束时调用 """
        value = self.broker.get_value()
        initial_cash = self.broker.startingcash
        total_pnl = value - initial_cash
        self.log(f'=========================================')
        self.log(f'回测结束统计:')
        self.log(f'初始资金: {initial_cash:.2f}')
        self.log(f'最终权益: {value:.2f}')
        self.log(f'总盈亏: {total_pnl:.2f}')
        self.log(f'=========================================')

    def notify_trade(self, trade):
        """ 交易结束通知 """
        if not trade.isclosed:
            return
        
        points_msg = ""
        closed_size = getattr(self, 'last_closed_trade_size', 0)
        if closed_size > 0 and self.params.contract_multiplier > 0:
            try:
                points = trade.pnl / (closed_size * self.params.contract_multiplier)
                points_msg = f", 盈亏点数: {points:.2f}"
                
                # 更新最大盈利/亏损点数
                if points > self.max_profit_points:
                    self.max_profit_points = points
                if points < self.max_loss_points:
                    self.max_loss_points = points
            except ZeroDivisionError:
                pass
        
        # 计算持仓天数
        dtopen = bt.num2date(trade.dtopen)
        dtclose = bt.num2date(trade.dtclose)
        duration = (dtclose - dtopen).days

        # 计算累计收益
        total_pnl = self.broker.get_value() - self.broker.startingcash
        
        # 计算本次交易前的累计盈亏，以便展示变化
        prev_total_pnl = total_pnl - trade.pnlcomm
        
        self.log(f'交易结束: 毛利 {trade.pnl:.2f}, 净利 {trade.pnlcomm:.2f}{points_msg} (持仓周期: {trade.barlen}bars/{duration}天, 开仓均价: {trade.price:.2f})')
        self.log(f'账户资金变动: {prev_total_pnl:.2f} (前值) + {trade.pnlcomm:.2f} (本次) = {total_pnl:.2f} (当前总盈亏)')

    def next(self):
        # 0. 严格的时间窗口控制
        if self.params.start_date:
            current_date = self.datas[0].datetime.date(0)
            # 处理字符串类型的 start_date
            if isinstance(self.params.start_date, str):
                try:
                    start_dt = pd.to_datetime(self.params.start_date).date()
                    if current_date < start_dt:
                        return
                except:
                    pass
            elif isinstance(self.params.start_date, datetime.date):
                 if current_date < self.params.start_date:
                     return

        # 强制在回测结束前平仓
        if len(self) >= self.datas[0].buflen() - 2:
            if self.position:
                self.log(f'回测即将结束，强制平仓: {self.datas[0].close[0]:.2f}')
                self.order = self.close()
            return

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
            # 金叉买入 (做多)
            if self.crossover > 0:
                # 计算止损距离
                atr_value = self.atr[0]
                stop_dist = atr_value * self.params.atr_multiplier
                self.stop_price = self.datas[0].close[0] - stop_dist
                
                size = self._calculate_size(value)
                
                if size > 0:
                    self.log(f'买入信号 (金叉): 收盘价 {self.datas[0].close[0]:.2f}, ATR {atr_value:.2f}, 目标仓位 {size}')
                    self.order = self.buy(size=size)
            
            # 死叉卖出 (做空)
            elif self.crossover < 0:
                # 计算止损距离 (空单止损在上方)
                atr_value = self.atr[0]
                stop_dist = atr_value * self.params.atr_multiplier
                self.stop_price = self.datas[0].close[0] + stop_dist
                
                size = self._calculate_size(value)
                
                if size > 0:
                    self.log(f'卖空信号 (死叉): 收盘价 {self.datas[0].close[0]:.2f}, ATR {atr_value:.2f}, 目标仓位 {-size}')
                    self.order = self.sell(size=size)
                    
        # 2. 持有仓位
        else:
            # 持有多单
            if self.position.size > 0:
                # 死叉: 平多单 + 开空单 (反手)
                if self.crossover < 0:
                    self.log(f'反手信号 (死叉): 收盘价 {self.datas[0].close[0]:.2f}, 平多开空')
                    
                    # 1. 计算新空单仓位
                    atr_value = self.atr[0]
                    stop_dist = atr_value * self.params.atr_multiplier
                    self.stop_price = self.datas[0].close[0] + stop_dist
                    size = self._calculate_size(value)
                    
                    if size > 0:
                        # order_target_size 会自动处理平仓+开新仓
                        self.order = self.order_target_size(target=-size)
                    else:
                        self.order = self.close() # 无法开新仓则仅平仓
                
                # 移动止损逻辑
                else:
                    # 如果价格上涨，提高止损线 (只升不降)
                    atr_value = self.atr[0]
                    new_stop_price = self.datas[0].close[0] - (atr_value * self.params.atr_multiplier)
                    
                    if self.stop_price and new_stop_price > self.stop_price:
                        self.stop_price = new_stop_price
                    
                    # 检查是否触发止损
                    if self.datas[0].close[0] < self.stop_price:
                        self.log(f'多单止损触发: 当前价 {self.datas[0].close[0]:.2f} < 止损价 {self.stop_price:.2f}')
                        self.order = self.close()

            # 持有空单
            elif self.position.size < 0:
                # 金叉: 平空单 + 开多单 (反手)
                if self.crossover > 0:
                    self.log(f'反手信号 (金叉): 收盘价 {self.datas[0].close[0]:.2f}, 平空开多')
                    
                    # 1. 计算新多单仓位
                    atr_value = self.atr[0]
                    stop_dist = atr_value * self.params.atr_multiplier
                    self.stop_price = self.datas[0].close[0] - stop_dist
                    size = self._calculate_size(value)
                    
                    if size > 0:
                        self.order = self.order_target_size(target=size)
                    else:
                        self.order = self.close()
                
                # 移动止损逻辑
                else:
                    # 如果价格下跌，降低止损线 (只降不升)
                    atr_value = self.atr[0]
                    new_stop_price = self.datas[0].close[0] + (atr_value * self.params.atr_multiplier)
                    
                    # 空单止损价是下降才更新 (越低越好，类似于多单越高越好)
                    # Wait, trailing stop for short: Stop price should move DOWN as price moves DOWN.
                    # Stop price is above current price.
                    # If Price = 100, Stop = 110.
                    # Price moves to 90, New Stop = 100. (Move down)
                    # So if new_stop_price < self.stop_price, update.
                    
                    if self.stop_price is None or new_stop_price < self.stop_price:
                        self.stop_price = new_stop_price
                    
                    # 检查是否触发止损 (价格上涨超过止损价)
                    if self.datas[0].close[0] > self.stop_price:
                        self.log(f'空单止损触发: 当前价 {self.datas[0].close[0]:.2f} > 止损价 {self.stop_price:.2f}')
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
        ('equity_percent', 0.1), # 资金比例 (0.1 = 10%)
        ('margin_rate', 0.1),    # 保证金率 (0.1 = 10%)
        ('size_mode', 'atr_risk'), # 开仓模式: 'fixed', 'equity_percent', 'atr_risk'
        ('fixed_size', 1),       # 固定手数
        ('contract_multiplier', 1), # 合约乘数
        ('use_trailing_stop', False), # 是否使用移动止损 (默认为False，主要依靠背离)
        ('print_log', True),     # 打印日志
        ('start_date', None),    # 策略启动日期
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
        
        # 记录最大盈利/亏损点数
        self.max_profit_points = 0.0
        self.max_loss_points = 0.0

    def start(self):
        if self.params.print_log:
             mode_desc = f"固定手数({self.params.fixed_size})" if self.params.size_mode == 'fixed' else f"ATR风险({self.params.risk_per_trade})"
             self.log(f"策略启动: MA55BreakoutStrategy (MA55突破), 参数: MA={self.params.ma_period}, 开仓模式: {mode_desc}, ATR倍数: {self.params.atr_multiplier}, 移动止损: {self.params.use_trailing_stop}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            action = "买入" if order.isbuy() else "卖出"
            current_pos = self.position.size
            exec_size = order.executed.size
            
            # 优化显示逻辑：如果是反手（例如 +20 -> -20，成交 -40），提示用户
            msg = f'{action}执行: 价格: {order.executed.price:.2f}, 成交数量: {exec_size}'
            if abs(exec_size) > abs(current_pos) and current_pos != 0 and (exec_size * current_pos > 0): 
                 # 简单的反手判断：成交量绝对值 > 持仓绝对值，且同向（例如成交-40，持仓-20，说明之前是+20）
                 # 注意：order.executed.size 和 self.position.size 在 Completed 时通常已经是同符号（除非是平仓）
                 pass
            
            msg += f' (当前持仓: {current_pos})'
            self.log(msg)
            
            # 记录平仓/反手导致的手数变化，用于 notify_trade 计算点数
            prev_pos = current_pos - exec_size
            if (prev_pos > 0 and exec_size < 0) or (prev_pos < 0 and exec_size > 0):
                self.last_closed_trade_size = min(abs(prev_pos), abs(exec_size))
            
        self.order = None

    def stop(self):
        """ 策略结束时调用 """
        value = self.broker.get_value()
        initial_cash = self.broker.startingcash
        total_pnl = value - initial_cash
        self.log(f'=========================================')
        self.log(f'回测结束统计:')
        self.log(f'初始资金: {initial_cash:.2f}')
        self.log(f'最终权益: {value:.2f}')
        self.log(f'总盈亏: {total_pnl:.2f}')
        self.log(f'=========================================')

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        
        points_msg = ""
        closed_size = getattr(self, 'last_closed_trade_size', 0)
        if closed_size > 0 and self.params.contract_multiplier > 0:
            try:
                points = trade.pnl / (closed_size * self.params.contract_multiplier)
                points_msg = f", 盈亏点数: {points:.2f}"
                
                # 更新最大盈利/亏损点数
                if points > self.max_profit_points:
                    self.max_profit_points = points
                if points < self.max_loss_points:
                    self.max_loss_points = points
            except ZeroDivisionError:
                pass
        
        # 计算持仓天数
        dtopen = bt.num2date(trade.dtopen)
        dtclose = bt.num2date(trade.dtclose)
        duration = (dtclose - dtopen).days

        # 计算累计收益
        total_pnl = self.broker.get_value() - self.broker.startingcash
        
        # 计算本次交易前的累计盈亏，以便展示变化
        prev_total_pnl = total_pnl - trade.pnlcomm

        self.log(f'交易结束: 毛利 {trade.pnl:.2f}, 净利 {trade.pnlcomm:.2f}{points_msg} (持仓周期: {trade.barlen}bars/{duration}天, 开仓均价: {trade.price:.2f})')
        self.log(f'账户资金变动: {prev_total_pnl:.2f} (前值) + {trade.pnlcomm:.2f} (本次) = {total_pnl:.2f} (当前总盈亏)')

    def next(self):
        # 0. 严格的时间窗口控制
        if self.params.start_date:
            current_date = self.datas[0].datetime.date(0)
            # 处理字符串类型的 start_date
            if isinstance(self.params.start_date, str):
                try:
                    start_dt = pd.to_datetime(self.params.start_date).date()
                    if current_date < start_dt:
                        return
                except:
                    pass
            elif isinstance(self.params.start_date, datetime.date):
                 if current_date < self.params.start_date:
                     return

        # 强制在回测结束前平仓
        if len(self) >= self.datas[0].buflen() - 2:
            if self.position:
                self.log(f'回测即将结束，强制平仓: {self.datas[0].close[0]:.2f}')
                self.order = self.close()
            return

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
            elif self.params.size_mode == 'equity_percent':
                target_value = value * self.params.equity_percent
                one_hand_margin = close * self.params.contract_multiplier * self.params.margin_rate
                if one_hand_margin > 0:
                    size = int(target_value / one_hand_margin)
                else:
                    size = 0
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
            elif self.params.size_mode == 'equity_percent':
                target_value = value * self.params.equity_percent
                one_hand_margin = close * self.params.contract_multiplier * self.params.margin_rate
                if one_hand_margin > 0:
                    size = int(target_value / one_hand_margin)
                else:
                    size = 0
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
        ('equity_percent', 0.1), # 资金比例 (0.1 = 10%)
        ('margin_rate', 0.1),    # 保证金率 (0.1 = 10%)
        ('size_mode', 'atr_risk'), # 开仓模式: 'fixed', 'equity_percent', 'atr_risk'
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
        
        # 记录最大盈利/亏损点数
        self.max_profit_points = 0.0
        self.max_loss_points = 0.0

    def start(self):
        if self.params.print_log:
             mode_desc = f"固定手数({self.params.fixed_size})" if self.params.size_mode == 'fixed' else f"ATR风险({self.params.risk_per_trade})"
             self.log(f"策略启动: MA55TouchExitStrategy (MA55触碰平仓), 参数: MA={self.params.ma_period}, 开仓模式: {mode_desc}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            action = "买入" if order.isbuy() else "卖出"
            current_pos = self.position.size
            exec_size = order.executed.size
            msg = f'{action}执行: 价格: {order.executed.price:.2f}, 成交数量: {exec_size} (当前持仓: {current_pos})'
            self.log(msg)
            
            # 记录平仓/反手导致的手数变化，用于 notify_trade 计算点数
            prev_pos = current_pos - exec_size
            if (prev_pos > 0 and exec_size < 0) or (prev_pos < 0 and exec_size > 0):
                self.last_closed_trade_size = min(abs(prev_pos), abs(exec_size))
                
        self.order = None

    def stop(self):
        """ 策略结束时调用 """
        value = self.broker.get_value()
        initial_cash = self.broker.startingcash
        total_pnl = value - initial_cash
        self.log(f'=========================================')
        self.log(f'回测结束统计:')
        self.log(f'初始资金: {initial_cash:.2f}')
        self.log(f'最终权益: {value:.2f}')
        self.log(f'总盈亏: {total_pnl:.2f}')
        self.log(f'=========================================')

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        
        points_msg = ""
        closed_size = getattr(self, 'last_closed_trade_size', 0)
        if closed_size > 0 and self.params.contract_multiplier > 0:
            try:
                points = trade.pnl / (closed_size * self.params.contract_multiplier)
                points_msg = f", 盈亏点数: {points:.2f}"
                
                # 更新最大盈利/亏损点数
                if points > self.max_profit_points:
                    self.max_profit_points = points
                if points < self.max_loss_points:
                    self.max_loss_points = points
            except ZeroDivisionError:
                pass
        
        # 计算持仓天数
        dtopen = bt.num2date(trade.dtopen)
        dtclose = bt.num2date(trade.dtclose)
        duration = (dtclose - dtopen).days

        # 计算累计收益
        total_pnl = self.broker.get_value() - self.broker.startingcash
        
        self.log(f'交易利润: 毛利 {trade.pnl:.2f}, 净利 {trade.pnlcomm:.2f}{points_msg} (持仓周期: {trade.barlen}bars/{duration}天, 开仓均价: {trade.price:.2f}), 累计收益: {total_pnl:.2f}')

    def next(self):
        # 0. 严格的时间窗口控制
        if self.start_date:
            current_date = self.datas[0].datetime.date(0)
            if current_date < self.start_date:
                # print(f"DEBUG: Skipping date {current_date} < {self.start_date}")
                return

        # 强制在回测结束前平仓
        if len(self) >= self.datas[0].buflen() - 2:
            if self.position:
                self.log(f'回测即将结束，强制平仓: {self.datas[0].close[0]:.2f}')
                self.order = self.close()
            return

        value = self.broker.get_value()
        close = self.datas[0].close[0]
        low = self.datas[0].low[0]
        high = self.datas[0].high[0]
        ma_val = self.ma55[0]
        
        # 上一根数据
        last_close = self.datas[0].close[-1]
        last_ma = self.ma55[-1]
        
        current_idx = len(self)
        dt_str = self.datas[0].datetime.datetime(0).strftime('%Y-%m-%d %H:%M')

        # 手动计算交叉
        # 金叉: 上一根 <= MA, 当前 > MA
        cross_up = last_close <= last_ma and close > ma_val
        # 死叉: 上一根 >= MA, 当前 < MA
        cross_down = last_close >= last_ma and close < ma_val

        # 调试日志：关键时刻打印
        if cross_up or cross_down or (self.position.size > 0 and low <= ma_val) or (self.position.size < 0 and high >= ma_val):
            self.log(f'[DEBUG] Close: {close:.2f}, MA: {ma_val:.2f}, LastClose: {last_close:.2f}, LastMA: {last_ma:.2f}, CrossUp: {cross_up}, CrossDown: {cross_down}')

        has_signal = False

        # 1. 突破信号 (优先于平仓)
        if cross_up:
            self.log(f'MA55 向上突破: {close:.2f} > {ma_val:.2f} (上根: {last_close:.2f} <= {last_ma:.2f})')
            has_signal = True
            
            # 计算仓位
            atr_val = self.atr[0]
            stop_dist = atr_val * self.params.atr_multiplier 
            
            size = 0
            if self.params.size_mode == 'fixed':
                try:
                    size = int(self.params.fixed_size) if self.params.fixed_size is not None else 1
                except (ValueError, TypeError):
                    size = 1
            elif self.params.size_mode == 'equity_percent':
                target_value = value * self.params.equity_percent
                one_hand_margin = close * self.params.contract_multiplier * self.params.margin_rate
                if one_hand_margin > 0:
                    size = int(target_value / one_hand_margin)
                else:
                    size = 0
            else:
                risk_amt = value * self.params.risk_per_trade
                risk_unit = stop_dist * self.params.contract_multiplier
                size = int(risk_amt / risk_unit) if risk_unit > 0 else 0
            
            if size > 0:
                self.log(f'做多/反手做多: 目标持仓 {size}')
                self.order = self.order_target_size(target=size)
            else:
                self.log(f'警告: 做多信号触发但仓位计算为0! 权益: {value:.2f}')
                if self.position.size < 0:
                     self.log('强制平空 (反手仓位为0)')
                     self.order = self.close()

        elif cross_down:
            self.log(f'MA55 向下突破: {close:.2f} < {ma_val:.2f} (上根: {last_close:.2f} >= {last_ma:.2f})')
            has_signal = True
            
            # 计算仓位
            atr_val = self.atr[0]
            stop_dist = atr_val * self.params.atr_multiplier
            
            size = 0
            if self.params.size_mode == 'fixed':
                try:
                    size = int(self.params.fixed_size) if self.params.fixed_size is not None else 1
                except (ValueError, TypeError):
                    size = 1
            elif self.params.size_mode == 'equity_percent':
                target_value = value * self.params.equity_percent
                one_hand_margin = close * self.params.contract_multiplier * self.params.margin_rate
                if one_hand_margin > 0:
                    size = int(target_value / one_hand_margin)
                else:
                    size = 0
            else:
                risk_amt = value * self.params.risk_per_trade
                risk_unit = stop_dist * self.params.contract_multiplier
                size = int(risk_amt / risk_unit) if risk_unit > 0 else 0
            
            if size > 0:
                self.log(f'做空/反手做空: 目标持仓 {-size}')
                self.order = self.order_target_size(target=-size)
            else:
                self.log(f'警告: 做空信号触发但仓位计算为0! 权益: {value:.2f}')
                if self.position.size > 0:
                     self.log('强制平多 (反手仓位为0)')
                     self.order = self.close()

        # 2. 如果没有突破信号，检查是否需要平仓
        if not has_signal and self.position:
            # 多单持仓
            if self.position.size > 0:
                # 改为: 收盘价跌破 MA55 平仓 (不再使用盘中触碰)
                if close < ma_val:
                     self.log(f'多单收盘跌破均线平仓: Close {close:.2f} < MA {ma_val:.2f}')
                     self.order = self.close()
            
            # 空单持仓
            elif self.position.size < 0:
                # 改为: 收盘价升破 MA55 平仓 (不再使用盘中触碰)
                if close > ma_val:
                    self.log(f'空单收盘升破均线平仓: Close {close:.2f} > MA {ma_val:.2f}')
                    self.order = self.close()

class MA20MA55CrossoverStrategy(bt.Strategy):
    """
    20/55 双均线交叉策略
    1. 核心逻辑：MA20 与 MA55 交叉
    2. 交易信号：
       - MA20 上穿 MA55 (金叉)：做多 (若持有空单则反手)
       - MA20 下穿 MA55 (死叉)：做空 (若持有多单则反手)
    3. 离场：依赖反向信号进行反手，无固定止盈止损 (Always In 模式)
    """
    params = (
        ('fast_period', 20),     # 快线周期
        ('slow_period', 55),     # 慢线周期
        ('risk_per_trade', 0.02),# 每笔风险
        ('equity_percent', 0.1), # 资金比例 (0.1 = 10%)
        ('margin_rate', 0.1),    # 保证金率 (0.1 = 10%)
        ('size_mode', 'atr_risk'), # 开仓模式: 'fixed', 'equity_percent', 'atr_risk'
        ('fixed_size', 1),       # 固定手数
        ('contract_multiplier', 1), # 合约乘数
        ('atr_period', 14),      # ATR 周期 (仅用于计算仓位)
        ('atr_multiplier', 3.0), # ATR 止损倍数 (仅用于计算仓位)
        ('print_log', True),     # 打印日志
        ('start_date', None),    # 强制回测开始日期 (在此之前只计算指标不交易)
    )

    def log(self, txt, dt=None):
        if self.params.print_log:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        super(MA20MA55CrossoverStrategy, self).__init__()
        
        # 解析 start_date
        self.start_date = None
        if self.params.start_date:
            try:
                if isinstance(self.params.start_date, str):
                    self.start_date = pd.to_datetime(self.params.start_date).date()
                else:
                    self.start_date = self.params.start_date
            except:
                pass
        
        # 尝试使用 DataFeed 中预计算的 MA (消除预热期)
        has_precalc_ma = hasattr(self.datas[0], 'ma_fast') and hasattr(self.datas[0], 'ma_slow')
        
        if has_precalc_ma:
            self.ma_fast = self.datas[0].ma_fast
            self.ma_slow = self.datas[0].ma_slow
        else:
            # 均线 (标准计算，有预热期)
            self.ma_fast = bt.indicators.SimpleMovingAverage(
                self.datas[0], period=self.params.fast_period)
            self.ma_slow = bt.indicators.SimpleMovingAverage(
                self.datas[0], period=self.params.slow_period)
        
        self.atr = bt.indicators.ATR(self.datas[0], period=self.params.atr_period)
        
        # 交叉信号: Fast 上穿/下穿 Slow
        self.crossover = bt.indicators.CrossOver(self.ma_fast, self.ma_slow)
        
        self.order = None
        
        # 记录最大盈利/亏损点数
        self.max_profit_points = 0.0
        self.max_loss_points = 0.0

    def start(self):
        if self.params.print_log:
             mode_desc = f"固定手数({self.params.fixed_size})" if self.params.size_mode == 'fixed' else f"ATR风险({self.params.risk_per_trade})"
             self.log(f"策略启动: MA20MA55CrossoverStrategy (双均线交叉), 参数: Fast={self.params.fast_period}, Slow={self.params.slow_period}, 开仓模式: {mode_desc}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            action = "买入" if order.isbuy() else "卖出"
            current_pos = self.position.size
            exec_size = order.executed.size
            msg = f'{action}执行: 价格: {order.executed.price:.2f}, 成交数量: {exec_size} (当前持仓: {current_pos})'
            self.log(msg)
            
            # 记录平仓/反手导致的手数变化，用于 notify_trade 计算点数
            prev_pos = current_pos - exec_size
            if (prev_pos > 0 and exec_size < 0) or (prev_pos < 0 and exec_size > 0):
                self.last_closed_trade_size = min(abs(prev_pos), abs(exec_size))
                
            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'订单失败: {order.getstatusname()}')

        self.order = None

    def stop(self):
        """ 策略结束时调用 """
        value = self.broker.get_value()
        initial_cash = self.broker.startingcash
        total_pnl = value - initial_cash
        self.log(f'=========================================')
        self.log(f'回测结束统计:')
        self.log(f'初始资金: {initial_cash:.2f}')
        self.log(f'最终权益: {value:.2f}')
        self.log(f'总盈亏: {total_pnl:.2f}')
        self.log(f'=========================================')

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        
        points_msg = ""
        closed_size = getattr(self, 'last_closed_trade_size', 0)
        if closed_size > 0 and self.params.contract_multiplier > 0:
            try:
                points = trade.pnl / (closed_size * self.params.contract_multiplier)
                points_msg = f", 盈亏点数: {points:.2f}"
                
                # 更新最大盈利/亏损点数
                if points > self.max_profit_points:
                    self.max_profit_points = points
                if points < self.max_loss_points:
                    self.max_loss_points = points
            except ZeroDivisionError:
                pass
        
        # 计算持仓天数
        dtopen = bt.num2date(trade.dtopen)
        dtclose = bt.num2date(trade.dtclose)
        duration = (dtclose - dtopen).days

        # 计算累计收益
        total_pnl = self.broker.get_value() - self.broker.startingcash
        
        self.log(f'交易利润: 毛利 {trade.pnl:.2f}, 净利 {trade.pnlcomm:.2f}{points_msg} (持仓周期: {trade.barlen}bars/{duration}天, 开仓均价: {trade.price:.2f}), 累计收益: {total_pnl:.2f}')

    def next(self):
        # 0. 严格的时间窗口控制
        if self.start_date:
            current_date = self.datas[0].datetime.date(0)
            if current_date < self.start_date:
                # print(f"DEBUG: Skipping date {current_date} < {self.start_date}")
                return

        # 强制在回测结束前平仓
        if len(self) >= self.datas[0].buflen() - 2:
            if self.position:
                self.log(f'回测即将结束，强制平仓: {self.datas[0].close[0]:.2f}')
                self.order = self.close()
            return

        # 如果有订单正在处理，不进行新操作 (除了反手可能需要快速处理，但在 Backtrader 中通常等待完成)
        # 为了保证反手顺畅，如果只是 Close 订单可能很快，但如果是 Target 订单，Backtrader 会处理
        # 这里为了简单，如果有挂单先不操作，防止重复下单
        if self.order:
            return

        value = self.broker.get_value()
        
        # 1. 金叉: 20 > 55
        if self.crossover > 0:
            self.log(f'金叉信号 (MA20 > MA55): {self.ma_fast[0]:.2f} > {self.ma_slow[0]:.2f}')
            
            # 计算目标仓位
            size = self._calculate_size(value)
            
            if size > 0:
                # order_target_size 会自动计算差额：
                # - 如果当前空仓 0，买入 size
                # - 如果当前持有空单 -size，买入 2*size 变为 +size
                # - 如果当前持有多单 size，不操作
                self.log(f'执行做多/反手做多: 目标持仓 {size}')
                self.order = self.order_target_size(target=size)
            else:
                # 详细诊断日志
                close = self.datas[0].close[0]
                mode = self.params.size_mode
                if mode == 'fixed':
                    self.log(f'金叉触发但计算仓位为0 [fixed]。请检查 fixed_size={self.params.fixed_size}')
                elif mode == 'equity_percent':
                    target_value = value * self.params.equity_percent
                    one_hand_margin = close * self.params.contract_multiplier * self.params.margin_rate
                    self.log(f'金叉触发但计算仓位为0 [equity_percent]。target_value={target_value:.2f}, one_hand_margin={one_hand_margin:.2f}, multiplier={self.params.contract_multiplier}, margin_rate={self.params.margin_rate}')
                else:
                    atr_val = self.atr[0]
                    multiplier = self.params.atr_multiplier if self.params.atr_multiplier is not None else 3.0
                    stop_dist = atr_val * multiplier
                    risk_amt = value * self.params.risk_per_trade
                    risk_unit = stop_dist * self.params.contract_multiplier
                    self.log(f'金叉触发但计算仓位为0 [atr_risk]。risk_amt={risk_amt:.2f}, stop_dist={stop_dist:.4f}, contract_mult={self.params.contract_multiplier}, risk_unit={risk_unit:.2f}, close={close:.2f}')

        # 2. 死叉: 20 < 55
        elif self.crossover < 0:
            self.log(f'死叉信号 (MA20 < MA55): {self.ma_fast[0]:.2f} < {self.ma_slow[0]:.2f}')
            
            # 计算目标仓位
            size = self._calculate_size(value)
            
            if size > 0:
                self.log(f'执行做空/反手做空: 目标持仓 {-size}')
                self.order = self.order_target_size(target=-size)
            else:
                # 详细诊断日志
                close = self.datas[0].close[0]
                mode = self.params.size_mode
                if mode == 'fixed':
                    self.log(f'死叉触发但计算仓位为0 [fixed]。请检查 fixed_size={self.params.fixed_size}')
                elif mode == 'equity_percent':
                    target_value = value * self.params.equity_percent
                    one_hand_margin = close * self.params.contract_multiplier * self.params.margin_rate
                    self.log(f'死叉触发但计算仓位为0 [equity_percent]。target_value={target_value:.2f}, one_hand_margin={one_hand_margin:.2f}, multiplier={self.params.contract_multiplier}, margin_rate={self.params.margin_rate}')
                else:
                    atr_val = self.atr[0]
                    multiplier = self.params.atr_multiplier if self.params.atr_multiplier is not None else 3.0
                    stop_dist = atr_val * multiplier
                    risk_amt = value * self.params.risk_per_trade
                    risk_unit = stop_dist * self.params.contract_multiplier
                    self.log(f'死叉触发但计算仓位为0 [atr_risk]。risk_amt={risk_amt:.2f}, stop_dist={stop_dist:.4f}, contract_mult={self.params.contract_multiplier}, risk_unit={risk_unit:.2f}, close={close:.2f}')
        
        # 调试日志：每100根K线打印一次状态，确认策略在运行
        # if len(self) % 100 == 0:
        #      self.log(f'[Debug] Bar: {len(self)}, Close: {self.datas[0].close[0]:.2f}, MA20: {self.ma_fast[0]:.2f}, MA55: {self.ma_slow[0]:.2f}')

    def _calculate_size(self, value):
        atr_val = self.atr[0]
        close = self.datas[0].close[0]
        
        size = 0
        if self.params.size_mode == 'fixed':
            try:
                size = int(self.params.fixed_size) if self.params.fixed_size is not None else 1
            except (ValueError, TypeError):
                size = 1
        elif self.params.size_mode == 'equity_percent':
             target_value = value * self.params.equity_percent
             if close > 0:
                 size = int(target_value / (close * self.params.contract_multiplier))
             else:
                 size = 0
        else:
            # 默认 ATR 风险模式
            multiplier = self.params.atr_multiplier if self.params.atr_multiplier is not None else 3.0
            stop_dist = atr_val * multiplier
            
            risk_amt = value * self.params.risk_per_trade
            risk_unit = stop_dist * self.params.contract_multiplier
            size = int(risk_amt / risk_unit) if risk_unit > 0 else 0
        
        return size


class StockMA20MA55LongOnlyStrategy(MA20MA55CrossoverStrategy):
    def next(self):
        if self.start_date:
            current_date = self.datas[0].datetime.date(0)
            if current_date < self.start_date:
                return
        if len(self) >= self.datas[0].buflen() - 2:
            if self.position:
                self.log(f'回测即将结束，强制平仓: {self.datas[0].close[0]:.2f}')
                self.order = self.close()
            return
        if self.order:
            return
        value = self.broker.get_value()
        if self.crossover > 0:
            self.log(f'金叉信号 (MA20 > MA55): {self.ma_fast[0]:.2f} > {self.ma_slow[0]:.2f}')
            size = self._calculate_size(value)
            if size > 0:
                self.log(f'执行做多/加仓: 目标持仓 {size}')
                self.order = self.order_target_size(target=size)
        elif self.crossover < 0:
            if self.position.size > 0:
                self.log(f'死叉信号(仅平多不做空): {self.ma_fast[0]:.2f} < {self.ma_slow[0]:.2f}，平掉多单')
                self.order = self.close()

class MA20MA55PartialTakeProfitStrategy(MA20MA55CrossoverStrategy):
    """
    20/55 双均线交叉策略 + 盈利平半仓
    继承自 MA20MA55CrossoverStrategy，增加以下逻辑：
    - 当浮动盈利点数达到 take_profit_points 时，平掉一半仓位。
    """
    params = (
        ('take_profit_points', 0), # 盈利平半仓的点数，0表示禁用
    )

    def __init__(self):
        super(MA20MA55PartialTakeProfitStrategy, self).__init__()
        # 记录是否已经执行过平半仓
        self.partial_exit_executed = False

    def start(self):
        super().start()
        if self.params.take_profit_points > 0:
            self.log(f"启用盈利平半仓逻辑: 目标盈利点数={self.params.take_profit_points}")
        else:
            self.log("未启用盈利平半仓逻辑 (点数为0)")

    def next(self):
        # 强制在回测结束前平仓
        if len(self) >= self.datas[0].buflen() - 2:
            if self.position:
                self.log(f'回测即将结束，强制平仓: {self.datas[0].close[0]:.2f}')
                self.order = self.close()
            return

        if self.order:
            return

        # 如果当前没有持仓，重置标志位
        if self.position.size == 0:
            self.partial_exit_executed = False

        value = self.broker.get_value()
        
        # 1. 检查是否有交叉信号 (反手/开仓)
        signal_triggered = False
        
        # 金叉
        if self.crossover > 0:
            self.log(f'金叉信号 (MA20 > MA55): {self.ma_fast[0]:.2f} > {self.ma_slow[0]:.2f}')
            size = self._calculate_size(value)
            if size > 0:
                self.log(f'执行做多/反手做多: 目标持仓 {size}')
                self.order = self.order_target_size(target=size)
                self.partial_exit_executed = False
                signal_triggered = True
            else:
                self.log(f'金叉触发但计算仓位为0')

        # 死叉
        elif self.crossover < 0:
            self.log(f'死叉信号 (MA20 < MA55): {self.ma_fast[0]:.2f} < {self.ma_slow[0]:.2f}')
            size = self._calculate_size(value)
            if size > 0:
                self.log(f'执行做空/反手做空: 目标持仓 {-size}')
                self.order = self.order_target_size(target=-size)
                self.partial_exit_executed = False
                signal_triggered = True
            else:
                self.log(f'死叉触发但计算仓位为0')
        
        if signal_triggered:
            return

        # 2. 检查盈利平半仓逻辑
        if self.position.size != 0 and self.params.take_profit_points > 0 and not self.partial_exit_executed:
            current_price = self.datas[0].close[0]
            entry_price = self.position.price
            
            profit_points = 0
            if self.position.size > 0: # 多头
                profit_points = current_price - entry_price
            else: # 空头
                profit_points = entry_price - current_price
            
            if profit_points >= self.params.take_profit_points:
                current_size = abs(self.position.size)
                exit_size = current_size // 2
                
                if exit_size > 0:
                    self.log(f'达到盈利点数 {profit_points:.2f} >= {self.params.take_profit_points}, 执行平半仓: {exit_size}手')
                    if self.position.size > 0:
                        self.order = self.sell(size=exit_size)
                    else:
                        self.order = self.buy(size=exit_size)
                    self.partial_exit_executed = True

class DKX(bt.Indicator):
    """
    DKX (多空线) 指标 - 递归实现
    MID = (3*CLOSE + LOW + OPEN + HIGH) / 6
    DKX = SMA(MID, 20, 1)  (注意: 这里 SMA 是加权移动平均的一种，类似于 EMA)
    """
    lines = ('dkx',)
    params = (('period', 20),)

    def __init__(self):
        # 计算 MID
        self.mid = (3 * self.data.close + self.data.low + self.data.open + self.data.high) / 6.0

    def next(self):
        if len(self) == 1:
            self.lines.dkx[0] = self.mid[0]
        else:
            # SMA(X, N, 1) = (1*X + (N-1)*Y') / N
            n = self.params.period
            self.lines.dkx[0] = (self.mid[0] + (n - 1) * self.lines.dkx[-1]) / n

class DKX_Indicator(bt.Indicator):
    lines = ('dkx', 'madkx',)
    params = (('period', 20), ('ma_period', 10),)
    
    def __init__(self):
        self.dkx_base = DKX(self.data, period=self.params.period)

    def next(self):
        self.lines.dkx[0] = self.dkx_base.dkx[0]
        if len(self) == 1:
            self.lines.madkx[0] = self.lines.dkx[0]
        else:
            n = self.params.ma_period
            self.lines.madkx[0] = (self.lines.dkx[0] + (n - 1) * self.lines.madkx[-1]) / n


class DKXStrategy(MA20MA55CrossoverStrategy):
    """
    DKX 多空线策略
    1. 计算 DKX 和 MADKX
    2. 交易信号：
       - 金叉 (DKX > MADKX): 做多 (若持有空单则反手)
       - 死叉 (DKX < MADKX): 做空 (若持有多单则反手)
    """
    params = (
        ('dkx_period', 20),      # DKX 计算周期 (用于 SMA(MID, N, 1))
        ('dkx_ma_period', 10),   # MADKX 均线周期
        # 继承其他参数: risk_per_trade, equity_percent, etc.
    )

    def __init__(self):
        # 注意: 这里不调用 super().__init__()，因为父类会初始化 MA20/MA55，我们不需要
        # 但是我们需要父类的 log 方法等。
        # 最好直接继承 bt.Strategy 然后把通用逻辑抽出来，或者为了省事，
        # 我们还是调用 super 但忽略它的 MA 信号，改用自己的。
        # 不过 MA20MA55CrossoverStrategy 的 __init__ 里写死了 MA20/55。
        # 所以最好重新写一个 __init__。
        
        # 调用更上层的父类 TrendFollowingStrategy (如果有) 或者 bt.Strategy
        # 这里 MA20MA55CrossoverStrategy 继承自 bt.Strategy (根据之前的代码 Read)
        # 等等，之前的 Read 显示: class MA20MA55CrossoverStrategy(bt.Strategy):
        
        bt.Strategy.__init__(self) # 显式调用基类
        
        # DKX 指标
        self.dkx_ind = DKX_Indicator(
            self.datas[0], 
            period=self.params.dkx_period, 
            ma_period=self.params.dkx_ma_period
        )
        
        self.atr = bt.indicators.ATR(self.datas[0], period=self.params.atr_period)
        
        # 交叉信号: DKX 上穿/下穿 MADKX
        self.crossover = bt.indicators.CrossOver(self.dkx_ind.dkx, self.dkx_ind.madkx)
        
        self.order = None

    def next(self):
        # 强制在回测结束前平仓
        if len(self) >= self.datas[0].buflen() - 2:
            if self.position:
                self.log(f'回测即将结束，强制平仓: {self.datas[0].close[0]:.2f}')
                self.order = self.close()
            return

        if self.order:
            return

        value = self.broker.get_value()
        
        # 1. 金叉: DKX > MADKX
        if self.crossover > 0:
            self.log(f'DKX金叉信号 (DKX > MADKX): {self.dkx_ind.dkx[0]:.2f} > {self.dkx_ind.madkx[0]:.2f}')
            
            size = self._calculate_size(value)
            if size > 0:
                self.log(f'执行做多/反手做多: 目标持仓 {size}')
                self.order = self.order_target_size(target=size)
            else:
                self.log(f'DKX金叉触发但计算仓位为0')

        # 2. 死叉: DKX < MADKX
        elif self.crossover < 0:
            self.log(f'DKX死叉信号 (DKX < MADKX): {self.dkx_ind.dkx[0]:.2f} < {self.dkx_ind.madkx[0]:.2f}')
            
            size = self._calculate_size(value)
            if size > 0:
                self.log(f'执行做空/反手做空: 目标持仓 {-size}')
                self.order = self.order_target_size(target=-size)
            else:
                self.log(f'DKX死叉触发但计算仓位为0')


class DKXPartialTakeProfitStrategy(DKXStrategy):
    params = (
        ('dkx_period', 20),
        ('dkx_ma_period', 10),
        ('take_profit_points', 0),
    )

    def __init__(self):
        super().__init__()
        self.partial_exit_executed = False

    def next(self):
        if len(self) >= self.datas[0].buflen() - 2:
            if self.position:
                self.log(f'回测即将结束，强制平仓: {self.datas[0].close[0]:.2f}')
                self.order = self.close()
            return

        if self.order:
            return

        if self.position.size == 0:
            self.partial_exit_executed = False

        value = self.broker.get_value()
        signal_triggered = False

        if self.crossover > 0:
            self.log(f'DKX金叉信号 (DKX > MADKX): {self.dkx_ind.dkx[0]:.2f} > {self.dkx_ind.madkx[0]:.2f}')
            size = self._calculate_size(value)
            if size > 0:
                self.log(f'执行做多/反手做多: 目标持仓 {size}')
                self.order = self.order_target_size(target=size)
                self.partial_exit_executed = False
                signal_triggered = True
            else:
                self.log(f'DKX金叉触发但计算仓位为0')

        elif self.crossover < 0:
            self.log(f'DKX死叉信号 (DKX < MADKX): {self.dkx_ind.dkx[0]:.2f} < {self.dkx_ind.madkx[0]:.2f}')
            size = self._calculate_size(value)
            if size > 0:
                self.log(f'执行做空/反手做空: 目标持仓 {-size}')
                self.order = self.order_target_size(target=-size)
                self.partial_exit_executed = False
                signal_triggered = True
            else:
                self.log(f'DKX死叉触发但计算仓位为0')

        if signal_triggered:
            return

        if self.position.size != 0 and self.params.take_profit_points > 0 and not self.partial_exit_executed:
            current_price = self.datas[0].close[0]
            entry_price = self.position.price

            if self.position.size > 0:
                profit_points = current_price - entry_price
            else:
                profit_points = entry_price - current_price

            if profit_points >= self.params.take_profit_points:
                current_size = abs(self.position.size)
                exit_size = current_size // 2

                if exit_size > 0:
                    self.log(f'达到盈利点数 {profit_points:.2f} >= {self.params.take_profit_points}, 执行平半仓: {exit_size}手')
                    if self.position.size > 0:
                        self.order = self.sell(size=exit_size)
                    else:
                        self.order = self.buy(size=exit_size)
                    self.partial_exit_executed = True

