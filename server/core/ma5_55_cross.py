import backtrader as bt
from .strategy import BaseStrategy

class MA5MA55CrossoverStrategy(BaseStrategy):
    """
    5/55日均线多空交叉策略
    逻辑：
    1. MA5上穿MA55 (金叉) -> 平空开多
    2. MA5下穿MA55 (死叉) -> 平多开空
    3. 支持反手配置
    """
    params = (
        ('fast_period', 5),
        ('slow_period', 55),
        ('allow_reverse', True), # 是否允许反手
    )

    def __init__(self):
        super().__init__()
        self.ma_fast = bt.ind.SMA(period=self.params.fast_period)
        self.ma_slow = bt.ind.SMA(period=self.params.slow_period)
        self.crossover = bt.ind.CrossOver(self.ma_fast, self.ma_slow)

    def next(self):
        # 调用基类 pre_next (处理自动平仓等)
        if not self.pre_next():
            return

        if self.order:
            return

        # 金叉
        if self.crossover > 0:
            self.log(f'金叉信号: MA{self.params.fast_period}={self.ma_fast[0]:.2f} > MA{self.params.slow_period}={self.ma_slow[0]:.2f}')
            
            if self.position.size < 0: # 当前持有空单
                if self.params.allow_reverse:
                    self.log('反手做多')
                    self.order = self.order_target_size(target=self.params.fixed_size)
                else:
                    self.log('平空仓 (不反手)')
                    self.order = self.close()
            else: # 当前空仓或已有多单(通常不会)
                 self.log('开多仓')
                 self.order = self.order_target_size(target=self.params.fixed_size)

        # 死叉
        elif self.crossover < 0:
            self.log(f'死叉信号: MA{self.params.fast_period}={self.ma_fast[0]:.2f} < MA{self.params.slow_period}={self.ma_slow[0]:.2f}')
            
            if self.position.size > 0: # 当前持有多单
                if self.params.allow_reverse:
                    self.log('反手做空')
                    self.order = self.order_target_size(target=-self.params.fixed_size)
                else:
                    self.log('平多仓 (不反手)')
                    self.order = self.close()
            else: # 当前空仓
                 self.log('开空仓')
                 self.order = self.order_target_size(target=-self.params.fixed_size)
