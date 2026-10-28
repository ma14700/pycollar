"""Delay signal market orders by observed bars, preserving normal broker fills."""
import re

import backtrader as bt


def execution_delay_params(params):
    result = {}
    for key, label in [('entry_delay_bars', '开仓 K 线'), ('exit_delay_bars', '平仓 K 线')]:
        value = params.get(key, 1)
        if isinstance(value, bool) or not re.fullmatch(r'[1-9]\d*', str(value)):
            raise ValueError(f'{label}必须为大于等于 1 的整数，1 表示下一根开盘成交')
        result[key] = int(value)
    return result


class SignalDelayBroker(bt.brokers.BackBroker):
    params = (('entry_delay_bars', 1), ('exit_delay_bars', 1))

    def submit(self, order, check=True):
        position = self.getposition(order.data).size
        size = order.created.size
        # Even with negative free cash, closing a position must remain possible.
        # BackBroker's actual execution still checks cash for any opening leg.
        if position * size < 0 and abs(size) <= abs(position):
            check = False
        if order.exectype == bt.Order.Market:
            if order.info.get('force_execution', False):
                kind, delay = 'forced_exit', 1
            elif position * size < 0:
                reversing = abs(size) > abs(position)
                kind = 'reversal' if reversing else 'exit'
                delay = max(self.p.entry_delay_bars, self.p.exit_delay_bars) if reversing else self.p.exit_delay_bars
            else:
                kind, delay = 'entry', self.p.entry_delay_bars
            order.addinfo(signal_bar=len(order.data), execution_bar=len(order.data) + delay,
                          execution_delay_bars=delay, execution_kind=kind,
                          signal_time=order.data.datetime.datetime(0).isoformat(sep=' '))
            if delay > 1:
                label = {'entry': '开仓', 'exit': '平仓', 'reversal': '反手'}[kind]
                order.owner.log(f'待执行信号: {label}将在信号后第 {delay} 根 K 线开盘尝试成交')
        return super().submit(order, check=check)

    def _try_exec_market(self, order, popen, phigh, plow):
        if len(order.data) < order.info.get('execution_bar', 0):
            return
        return super()._try_exec_market(order, popen, phigh, plow)
