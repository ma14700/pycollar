import backtrader as bt
import datetime

class BaseStrategy(bt.Strategy):
    """
    包含通用的日志记录、订单管理和交易通知逻辑
    """
    params = (
        ('print_log', True),
        ('start_date', None),
        ('end_date', None), # 新增结束日期参数
        ('disable_auto_close', False), # 是否禁用自动平仓
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
            self.log('回测结束：待执行信号未成交' if order.info.get('end_of_backtest') else '订单已取消/保证金不足/被拒绝')

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
                start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
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
                 end_date = datetime.datetime.strptime(end_date, '%Y-%m-%d').date()
             if isinstance(end_date, datetime.datetime):
                 end_date = end_date.date()

             # 如果当前日期 >= 结束日期 (通常用于实盘手动停止时间点)
             if current_date >= end_date:
                 is_near_end = True

        if is_near_end:
            # 如果未禁用自动平仓，则执行平仓逻辑
            if not self.params.disable_auto_close:
                # Do not let a delayed signal open a new position on the last bar.
                for pending in list(self.broker.get_orders_open()):
                    if pending.owner is self and pending.info.get('execution_delay_bars', 1) > 1:
                        pending.addinfo(end_of_backtest=True)
                        self.cancel(pending)
                        if self.order is not None and self.order.ref == pending.ref:
                            self.order = None
                if self.position:
                    self.log('数据结束检查: 平掉所有持仓 (市价单)')
                    # 使用 Market 单在下一根(即最后一根)K线开盘时立即成交，确保平仓成功
                    self.close(exectype=bt.Order.Market, force_execution=True)

            # 无论是否平仓，如果接近结束，都停止处理新信号，除非禁用了自动平仓(意味着我们希望在扫描模式下看到最新的信号)
            # 对于扫描模式，我们希望看到最新K线的信号，所以如果禁用了自动平仓，就不应该返回 False
            if not self.params.disable_auto_close:
                return False # 停止当前K线的其他信号处理

        # 最后一根K线直接跳过，防止产生新信号
        if self.datas[0].buflen() > 0 and len(self.datas[0]) >= self.datas[0].buflen():
            if not self.params.disable_auto_close:
                return False

        return True
