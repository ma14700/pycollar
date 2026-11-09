import backtrader as bt
import datetime
import math
from .strategy_base import BaseStrategy

class MA20MA55RR3Strategy(BaseStrategy):
    """Close-confirmed 20/55 entries with a frozen ATR risk and 3R target.

    SignalDelayBroker installs OCO protection on the entry bar. Opposite
    crosses optionally close only; they never reverse or re-enter late.
    """
    params = (('fast_period', 20), ('slow_period', 55),
              ('atr_period', 14), ('atr_multiplier', 2.0),
              ('risk_reward_ratio', 3.0), ('exit_on_opposite_cross', False))

    @classmethod
    def validate_params(cls, params):
        for key in ('fast_period', 'slow_period', 'atr_period', 'fixed_size'):
            value = params.get(key, getattr(cls.params, key))
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 1 or int(value) != value:
                raise ValueError(f'{key} 必须是正整数')
        if params.get('fast_period', 20) >= params.get('slow_period', 55):
            raise ValueError('快均线周期必须小于慢均线周期')
        for key in ('atr_multiplier', 'risk_reward_ratio'):
            value = params.get(key, getattr(cls.params, key))
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'{key} 必须是大于 0 的有限数字')
        if not isinstance(params.get('exit_on_opposite_cross', False), bool):
            raise ValueError('反向交叉提前离场必须为布尔值')
        if params.get('size_mode', 'fixed') != 'fixed':
            raise ValueError('20/55 ATR 1:3 策略使用固定手数')

    @classmethod
    def required_bars(cls, params):
        return max(int(params.get('slow_period', 55)) + 1,
                   int(params.get('atr_period', 14)) + 1)

    def __init__(self):
        super().__init__()
        self.validate_params(dict(self.p._getkwargs()))
        if not hasattr(self.broker, '_try_exec_market') or not hasattr(self.broker.p, 'entry_delay_bars'):
            raise ValueError('该策略需要 SignalDelayBroker，以保证开仓当根止损生效')
        self.ma_fast = bt.ind.SMA(period=int(self.p.fast_period))
        self.ma_slow = bt.ind.SMA(period=int(self.p.slow_period))
        self.crossover = bt.ind.CrossOver(self.ma_fast, self.ma_slow)
        self.atr = bt.ind.ATR(period=int(self.p.atr_period))
        self.rr_pending = None
        self.sl_order = self.tp_order = None
        self.rr_trade = None
        self.risk_reward_trades = []

    def _entry_signal(self):
        return self.crossover[0]

    def install_rr_protection(self, order):
        risk = float(order.info['rr_risk_points'])
        price, size = order.executed.price, order.executed.size
        direction = 1 if size > 0 else -1
        stop = price - direction * risk
        target = price + direction * risk * self.p.risk_reward_ratio
        self.rr_trade = dict(entry_price=price, risk_points=risk,
                             entry_date=self.data.datetime.datetime(0).isoformat(sep=' '),
                             risk_amount=risk * abs(size) * self.p.contract_multiplier,
                             stop_price=stop, target_price=target, direction=direction)
        close = self.sell if size > 0 else self.buy
        self.sl_order = close(size=abs(size), price=stop, exectype=bt.Order.Stop,
                              rr_reason='stop_loss', rr_risk_points=risk)
        self.tp_order = close(size=abs(size), price=target, exectype=bt.Order.Limit,
                              oco=self.sl_order, rr_reason='take_profit', rr_risk_points=risk)
        self.log(f'风险计划: 成交 {price:.4f}, 1R={risk:.4f}点, 止损 {stop:.4f}, 止盈 {target:.4f}, 目标 {self.p.risk_reward_ratio:g}R')
        return [self.sl_order, self.tp_order]

    def _close_risk_position(self, reason, force=False):
        # Keep the protection alive while a delayed cross exit is pending.
        self.rr_pending = self.close(oco=self.sl_order, rr_reason=reason,
                                      force_execution=force)

    def notify_order(self, order):
        super().notify_order(order)
        if order.status == order.Completed and order.info.get('rr_reason'):
            if self.rr_trade is not None:
                self.rr_trade.update(exit_reason=order.info['rr_reason'],
                                     exit_price=order.executed.price,
                                     exit_date=self.data.datetime.datetime(0).isoformat(sep=' '))
            reason = {'stop_loss': '止损', 'take_profit': '止盈', 'opposite_cross': '反向交叉',
                      'end_of_backtest': '结束强平'}.get(order.info['rr_reason'], order.info['rr_reason'])
            self.log(f'风险策略离场: {reason}, 成交 {order.executed.price:.4f}')
        if self.rr_pending is not None and order.ref == self.rr_pending.ref and not order.alive():
            self.rr_pending = None

    def notify_trade(self, trade):
        super().notify_trade(trade)
        if trade.isclosed and self.rr_trade is not None:
            self.risk_reward_trades.append({**self.rr_trade, 'net_profit': trade.pnlcomm,
                                           'net_r': trade.pnlcomm / self.rr_trade['risk_amount']})
            self.rr_trade = None

    def next(self):
        current = self.data.datetime.date(0)
        def date_value(value):
            if isinstance(value, str): return datetime.date.fromisoformat(value[:10])
            return value.date() if isinstance(value, datetime.datetime) else value
        if self.p.start_date and current < date_value(self.p.start_date):
            return
        ending = ((self.data.buflen() and len(self.data) >= self.data.buflen() - 1)
                  or (self.p.end_date and current >= date_value(self.p.end_date)))
        if ending and not self.p.disable_auto_close:
            if self.rr_pending is not None and self.rr_pending.alive():
                # Cancel a pending signal. Canceling an OCO exit cancels its
                # siblings too; the forced close below replaces that group.
                self.rr_pending.addinfo(end_of_backtest=True)
                self.cancel(self.rr_pending)
                self.rr_pending = None
            if self.position and len(self.data) < self.data.buflen():
                for child in (self.sl_order, self.tp_order):
                    if child is not None and child.alive(): self.cancel(child)
                self.sl_order = self.tp_order = None
                self._close_risk_position('end_of_backtest', force=True)
            return
        if self.rr_pending is not None and self.rr_pending.alive():
            return
        signal = self._entry_signal()
        if self.position:
            if self.p.exit_on_opposite_cross and signal * self.position.size < 0:
                self._close_risk_position('opposite_cross')
            return
        if signal == 0:
            return
        risk = float(self.atr[0]) * self.p.atr_multiplier
        if not math.isfinite(risk) or risk <= 0:
            self.log('跳过入场：ATR 风险距离无效')
            return
        side = self.buy if signal > 0 else self.sell
        self.rr_pending = side(size=int(self.p.fixed_size), rr_entry=True, rr_risk_points=risk)
