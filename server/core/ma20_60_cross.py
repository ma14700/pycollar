import backtrader as bt
from .strategy import BaseStrategy

class MA20MA60CrossoverStrategy(BaseStrategy):
    """
    20/60双均线交叉策略 (多空)
    逻辑：
    1. MA20上穿MA60 (金叉) -> 做多
    2. MA20下穿MA60 (死叉) -> 做空
    """
    params = (
        ('fast_period', 20),
        ('slow_period', 60),
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
            self.log(f'金叉信号: 做多 (MA{self.params.fast_period}={self.ma_fast[0]:.2f} > MA{self.params.slow_period}={self.ma_slow[0]:.2f})')
            self.order = self.order_target_size(target=self.params.fixed_size)
        elif self.crossover < 0:
            self.log(f'死叉信号: 做空 (MA{self.params.fast_period}={self.ma_fast[0]:.2f} < MA{self.params.slow_period}={self.ma_slow[0]:.2f})')
            self.order = self.order_target_size(target=-self.params.fixed_size)
