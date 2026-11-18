"""DKX multi-bull/bear line indicator and DKX-based strategies."""
import backtrader as bt
from .strategy_base import BaseStrategy


class DKX(bt.Indicator):
    """
    DKX多空线指标
    算法:
    MID = (3*CLOSE + LOW + OPEN + HIGH) / 6
    DKX = (20*MID + 19*REF(MID,1) + ... + 1*REF(MID,19)) / 210
    MADKX = MA(DKX, 10)
    """
    lines = ('dkx', 'madkx',)
    params = (('period', 20), ('ma_period', 10),)

    def __init__(self):
        mid = (3 * self.data.close + self.data.low + self.data.open + self.data.high) / 6.0
        self.l.dkx = bt.ind.WeightedMovingAverage(mid, period=self.params.period)
        self.l.madkx = bt.ind.SMA(self.l.dkx, period=self.params.ma_period)


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

        if self.order:
            return

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
        BaseStrategy.notify_order(self, order)

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
            self.tp_order = self.sell(size=abs(size), price=entry_price + tp_val, exectype=bt.Order.Limit, oco=self.sl_order)
        elif size < 0:
            self.sl_order = self.buy(size=abs(size), price=entry_price + sl_val, exectype=bt.Order.Stop)
            self.tp_order = self.buy(size=abs(size), price=entry_price - tp_val, exectype=bt.Order.Limit, oco=self.sl_order)

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


class DKXPartialTakeProfitStrategy(DKXStrategy):
    """
    DKX + 盈利平半仓 (简化版，仅平仓一次)
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
        if order.status == order.Completed and order.executed.size != 0:
            if abs(self.position.size) >= self.params.fixed_size:
                self.tp_executed = False
                self.entry_price = order.executed.price

    def next(self):
        super().next()

        if not self.params.disable_auto_close and len(self.datas[0]) >= self.datas[0].buflen() - 1:
            return

        if self.position.size != 0 and not self.tp_executed:
            if self.position.size > 0:
                profit_points = self.data.close[0] - self.entry_price
            else:
                profit_points = self.entry_price - self.data.close[0]

            if profit_points >= self.params.take_profit_points:
                self.log(f'Partial TP Triggered: Profit {profit_points:.2f}')
                target = int(self.position.size / 2)
                if target == 0 and self.position.size != 0:
                    target = 0
                self.close(size=self.position.size - target)
                self.tp_executed = True
