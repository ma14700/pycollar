"""Broker accounting and statistics used by real backtests (amounts in yuan)."""
import math

import backtrader as bt
import numpy as np
import pandas as pd


COMMISSION_RATE = 0.0001  # Unified model: 0.01% of traded notional per side.
METRICS_VERSION = 2


class AccountEquity(bt.Analyzer):
    """Record broker equity on actual bar timestamps, including warmup bars."""
    def start(self):
        self.rets = []
        self.previous = self.strategy.broker.getvalue()

    def next(self):
        value = self.strategy.broker.getvalue()
        self.rets.append({'date': self.strategy.data.datetime.datetime(0).strftime('%Y-%m-%d %H:%M:%S'),
                          'value': value, 'return': value / self.previous - 1 if self.previous > 0 else None})
        self.previous = value


class FuturesCommissionInfo(bt.CommInfoBase):
    params = (('stocklike', False), ('commtype', bt.CommInfoBase.COMM_PERC),
              ('percabs', True), ('margin_rate', 0.1))

    def get_margin(self, price):
        return price * self.p.mult * self.p.margin_rate

    def getvalue(self, position, price):
        # Cash is marked to market by Backtrader's cashadjust. Add back only
        # the collateral frozen at entry, not a changing market-value margin:
        # otherwise changing prices would create artificial account equity.
        return abs(position.size) * self.get_margin(position.price)

    def _getcommission(self, size, price, pseudoexec):
        return abs(size) * price * self.p.mult * self.p.commission


class StockLotCommissionInfo(bt.CommInfoBase):
    """A strategy size of 1 represents one configured lot (usually 100 shares)."""
    params = (('stocklike', True), ('commtype', bt.CommInfoBase.COMM_PERC), ('percabs', True))

    def getoperationcost(self, size, price):
        return super().getoperationcost(size, price) * self.p.mult

    def getvaluesize(self, size, price):
        return super().getvaluesize(size, price) * self.p.mult

    def getvalue(self, position, price):
        return super().getvalue(position, price) * self.p.mult

    def _getcommission(self, size, price, pseudoexec):
        return abs(size) * price * self.p.mult * self.p.commission


def configure_accounting(broker, params, market_type):
    multiplier = float(params.get('contract_multiplier', 1))
    margin_rate = float(params.get('margin_rate', 0.1)) if market_type == 'futures' else 1.0
    if not math.isfinite(multiplier) or multiplier <= 0:
        raise ValueError('合约乘数必须为大于 0 的有限数字')
    if not math.isfinite(margin_rate) or not 0 < margin_rate <= 1:
        raise ValueError('保证金率必须大于 0 且不超过 1')
    if market_type == 'futures':
        broker.set_shortcash(False)
        info = FuturesCommissionInfo(mult=multiplier, margin_rate=margin_rate, commission=COMMISSION_RATE)
    else:
        info = StockLotCommissionInfo(mult=multiplier, commission=COMMISSION_RATE)
    broker.addcommissioninfo(info)
    return info


def closed_trade_stats(trade, multiplier, margin_rate=1.0):
    # Count units actually opened, including adds after partial closes, rather
    # than the final size (zero) or peak position. Reversals are split into
    # separate Backtrader trades and their own history events.
    opened_units, entry_notional = 0.0, 0.0
    for event in trade.history:
        size = event.event.size
        if (size > 0) == trade.long:
            opened_units += abs(size)
            entry_notional += abs(size) * event.event.price * multiplier
    pnl = float(trade.pnlcomm)
    return {
        'net_profit': pnl,
        'net_per_hand': pnl / opened_units if opened_units else 0.0,
        'net_points': pnl / (opened_units * multiplier) if opened_units else 0.0,
        # Dividing both profit and collateral by opened_units gives the same
        # per-hand return. Added entries use their own actual execution prices.
        'return_pct': pnl / (entry_notional * margin_rate) * 100 if entry_notional else 0.0,
    }


def equity_statistics(equity_curve, initial_cash, period):
    """Close-to-close drawdown and annualized Sharpe within the requested window."""
    if not equity_curve:
        return {'sharpe_ratio': None, 'max_drawdown': 0.0}
    values = np.asarray([item['value'] for item in equity_curve], dtype=float)
    peaks = np.maximum.accumulate(np.r_[initial_cash, values])[1:]
    drawdown = (peaks - values) / peaks * 100
    series = pd.Series(values, index=pd.to_datetime([item['date'] for item in equity_curve]))
    # Intraday bars must not each be treated as a daily observation.
    observations = series.groupby(series.index.date).last().to_numpy() if period != 'weekly' else values
    bases = np.r_[initial_cash, observations[:-1]]
    sharpe = None
    if len(observations) >= 2 and np.all(bases > 0):
        returns = observations / bases - 1
        deviation = float(np.std(returns, ddof=0))
        if deviation > 1e-12:
            sharpe = float(np.mean(returns) / deviation * math.sqrt(52 if period == 'weekly' else 252))
    return {'sharpe_ratio': sharpe, 'max_drawdown': float(np.max(drawdown))}
