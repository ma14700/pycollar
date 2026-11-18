"""Collect scan events from the same broker that executes strategy analysis."""
import backtrader as bt
import pandas as pd

from .execution_delay import SignalDelayBroker


def position_action(before, after):
    before = 0 if abs(before) < 1e-9 else before
    after = 0 if abs(after) < 1e-9 else after
    if before == 0:
        return '开多' if after > 0 else '开空'
    if before * after < 0:
        return '反手做多' if after > 0 else '反手做空'
    if abs(after) > abs(before):
        return '加多' if before > 0 else '加空'
    if after:
        return '减多' if before > 0 else '减空'
    return '平多' if before > 0 else '平空'


class ScanBroker(SignalDelayBroker):
    def start(self):
        super().start()
        self.scan_orders = {}

    def transmit(self, order, check=True):
        self.scan_orders[order.ref] = (
            order, len(order.data), self.getposition(order.data).size, float(order.data.close[0]),
        )
        return super().transmit(order, check=check)

    def scan_events(self, index, first_bar, window):
        events = []
        for order, submitted_bar, before, signal_price in self.scan_orders.values():
            if order.info.get('force_execution') or order.info.get('end_of_backtest'):
                continue
            filled = bool(order.executed.size)
            fill_time = pd.Timestamp(bt.num2date(order.executed.dt)).round('s') if filled else None
            after = before + order.created.size
            protective = order.exectype != bt.Order.Market and before * order.created.size < 0 and abs(after) < abs(before)
            if protective:
                if not filled:
                    continue
                trigger_bar = int(index.get_indexer([fill_time])[0]) + 1
                signal_price = float(order.created.price)
            else:
                trigger_bar = submitted_bar
            offset = len(index) - trigger_bar + 1
            if trigger_bar < first_bar or not 1 <= offset <= window:
                continue
            if filled:
                after = order.executed.psize
                before = after - order.executed.size
            status = {
                order.Completed: 'filled', order.Partial: 'partial_fill', order.Margin: 'margin',
                order.Rejected: 'rejected', order.Canceled: 'canceled', order.Expired: 'expired',
            }.get(order.status, 'pending')
            events.append({
                'ref': order.ref, 'action': position_action(before, after), 'offset': offset,
                'signal_time': str(index[trigger_bar - 1]), 'signal_price': signal_price,
                'fill_time': str(fill_time) if filled else None,
                'fill_price': float(order.executed.price) if filled else None,
                'status': status, 'trigger_basis': '保护价' if protective else '收盘价',
            })
        return sorted(events, key=lambda event: (event['offset'], -event['ref']))
