"""Integration checks against actual broker fills, not a copied metrics implementation."""
import contextlib
import io
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from core import engine, strategy
from core.accounting import equity_statistics


def audit_run(prices, signals, multiplier=10, margin=.1, cash=10000, market='futures',
              period='daily', start_date=None, end_date=None, **kwargs):
    class AccountingAuditStrategy(strategy.BaseStrategy):
        def next(self):
            if not self.pre_next() or self.order:
                return
            size = signals.get(len(self) - 1)
            if size == 'close':
                self.order = self.close()
            elif size:
                self.order = self.buy(size=size) if size > 0 else self.sell(size=-size)

    frame = pd.DataFrame({'Open': prices, 'High': prices, 'Low': prices, 'Close': prices, 'Volume': 100},
                         index=pd.date_range('2025-01-01', periods=len(prices), freq='W-FRI' if period == 'weekly' else 'D'))
    with patch.object(strategy, 'AccountingAuditStrategy', AccountingAuditStrategy, create=True), \
         patch.object(engine, 'fetch_data', return_value=frame), contextlib.redirect_stdout(io.StringIO()):
        result = engine.BacktestEngine().run('AUDIT', period,
                    {'contract_multiplier': multiplier, 'margin_rate': margin, 'fixed_size': 2, **kwargs},
                    initial_cash=cash, strategy_name='AccountingAuditStrategy', market_type=market,
                    start_date=start_date, end_date=end_date)
    if 'error' in result:
        raise AssertionError(result['error'])
    return result


class ProfitCalculationTests(unittest.TestCase):
    def assert_equity(self, result, expected):
        np.testing.assert_allclose([v['value'] for v in result['equity_curve']], expected, rtol=0, atol=1e-8)
        self.assertAlmostEqual(result['metrics']['final_value'], expected[-1])
        self.assertAlmostEqual(result['metrics']['net_profit'], expected[-1] - result['metrics']['initial_cash'])
        self.assertAlmostEqual(sum(t['commission'] for t in result['trades']), result['metrics']['total_commission'])

    def test_long_cash_curve_net_profit_and_per_hand_reconcile(self):
        # 2 hands, multiplier 10, entry 100, exit 110: gross 200;
        # fees = 100*2*10*.0001 + 110*2*10*.0001 = .42; net 199.58.
        result = audit_run([100,100,100,105,110,110,110,110], {1:2, 4:'close'})
        metrics = result['metrics']
        self.assert_equity(result, [10000,10000,9999.8,10099.8,10199.8,10199.58,10199.58,10199.58])
        self.assertAlmostEqual(metrics['realized_net_profit'], 199.58)
        self.assertAlmostEqual(metrics['one_hand_net_profit'], 99.79)
        self.assertAlmostEqual(metrics['one_hand_profit_pct'], 99.79)
        self.assertEqual(metrics['one_hand_return_basis'], 'entry_margin')
        self.assertAlmostEqual(metrics['return_rate'], 1.9958)
        self.assertAlmostEqual(metrics['max_profit_points'], 9.979)
        self.assertEqual(metrics['max_loss_points'], 0)
        self.assertEqual((metrics['total_trades'],metrics['won_trades'],metrics['lost_trades']), (1,1,0))
        self.assertAlmostEqual(metrics['max_capital_usage'], 200 / 9999.8 * 100)
        self.assertAlmostEqual(metrics['max_drawdown'], .22 / 10199.8 * 100)

    def test_short_marks_floating_profit_with_multiplier(self):
        result = audit_run([100,100,100,95,90,90,90,90], {1:-2,4:'close'})
        self.assert_equity(result, [10000,10000,9999.8,10099.8,10199.8,10199.62,10199.62,10199.62])
        self.assertAlmostEqual(result['metrics']['one_hand_net_profit'],99.81)
        self.assertAlmostEqual(result['metrics']['one_hand_profit_pct'],99.81)
        self.assertEqual(result['metrics']['max_loss_points'],0)

    def test_all_losing_has_no_positive_max_profit_and_drawdown_includes_float(self):
        result = audit_run([100,100,100,95,90,90,90,90], {1:2,4:'close'})
        self.assert_equity(result, [10000,10000,9999.8,9899.8,9799.8,9799.62,9799.62,9799.62])
        m=result['metrics']
        self.assertEqual(m['max_profit_points'],0)
        self.assertAlmostEqual(m['max_loss_points'],-10.019)
        self.assertAlmostEqual(m['one_hand_profit_pct'],-100.19)
        self.assertAlmostEqual(m['max_drawdown'],2.0038)
        self.assertEqual((m['won_trades'],m['lost_trades'],m['win_rate']), (0,1,0))

    def test_partial_close_then_add_then_close_counts_all_opened_units(self):
        # Enter 2@100, close 1@110, add 1@120, close 2@130.
        # Gross 100 + 400 = 500; fee .2+.11+.12+.26=.69.
        result = audit_run([100,100,100,110,120,130,130,130], {1:2,2:-1,3:1,4:'close'})
        m=result['metrics']
        self.assertAlmostEqual(m['net_profit'],499.31)
        self.assertAlmostEqual(m['realized_net_profit'],499.31)
        self.assertAlmostEqual(m['total_commission'],.69)
        self.assertAlmostEqual(m['one_hand_net_profit'],499.31/3)
        self.assertAlmostEqual(m['one_hand_profit_pct'],499.31/320*100)
        self.assertEqual(m['total_trades'],1)
        self.assertEqual(m['used_size'],2)
        self.assertAlmostEqual(result['equity_curve'][-1]['value'],10499.31)

    def test_reversal_splits_settlements_without_double_counting_fees(self):
        # 2 long 100->110 and 2 short 110->90: gross 200+400.
        result = audit_run([100,100,100,105,110,95,90,90,90], {1:2,3:-4,5:'close'})
        m=result['metrics']
        self.assertAlmostEqual(m['total_commission'],.2+.44+.18)
        self.assertAlmostEqual(m['net_profit'],599.18)
        self.assertAlmostEqual(m['realized_net_profit'],599.18)
        self.assertAlmostEqual(m['one_hand_net_profit'],599.18/2)
        self.assertAlmostEqual(result['equity_curve'][4]['value'],10199.36)
        self.assertEqual((m['total_trades'],m['won_trades']), (2,2))

    def test_maximum_points_are_selected_by_points_rather_than_trade_money(self):
        # First wins 1000 yuan with 10 hands, second 200 yuan with 1 hand;
        # second has more net points despite the smaller cash profit.
        result = audit_run([100,100,100,110,110,100,100,120,120,120], {1:10,2:'close',4:1,6:'close'})
        self.assertAlmostEqual(result['metrics']['max_profit_points'],19.978)
        self.assertAlmostEqual(result['metrics']['one_hand_net_profit'],99.79+199.78)
        self.assertAlmostEqual(result['metrics']['one_hand_profit_pct'],99.79+199.78)

    def test_unclosed_position_is_not_in_win_rate_or_closed_profit(self):
        result = audit_run([100,100,100,105,110,110,110,110],{1:2},disable_auto_close=True)
        m=result['metrics']
        self.assertAlmostEqual(m['net_profit'],199.8)
        self.assertEqual((m['total_trades'],m['open_trades'],m['won_trades']), (0,1,0))
        self.assertEqual(m['one_hand_net_profit'],0)
        self.assertEqual(m['realized_net_profit'],0)

    def test_no_fills_reports_zero_actual_size_and_unavailable_sharpe(self):
        m=audit_run([100]*8,{})['metrics']
        self.assertEqual(m['used_size'],0)
        self.assertEqual(m['net_profit'],0)
        self.assertIsNone(m['sharpe_ratio'])

    def test_futures_margin_checks_consume_real_collateral_not_stock_price(self):
        # Two hands @100 require 200 collateral + .20 opening fees.
        m=audit_run([100]*8,{1:2},cash=200)['metrics']
        self.assertEqual(m['used_size'],0)
        m=audit_run([100]*8,{1:2},cash=201)['metrics']
        self.assertEqual(m['used_size'],2)
        self.assertAlmostEqual(m['net_profit'],-.4)

    def test_stock_lots_use_full_funds_and_multiplier_in_fees_and_equity(self):
        result=audit_run([100,100,100,105,110,110,110,110],{1:2,4:'close'},multiplier=100,market='stock',cash=30000)
        self.assert_equity(result,[30000,30000,29998,30998,31998,31995.8,31995.8,31995.8])
        self.assertAlmostEqual(result['metrics']['net_profit'],1995.8)
        self.assertAlmostEqual(result['metrics']['one_hand_profit_pct'],9.979)
        self.assertEqual(result['metrics']['one_hand_return_basis'],'entry_notional')
        rejected=audit_run([100]*8,{1:2},multiplier=100,market='stock',cash=10000)
        self.assertEqual(rejected['metrics']['used_size'],0)

    def test_margin_rate_changes_unit_return_without_changing_profit(self):
        for rate in (.1,.12,.2,1):
            with self.subTest(rate=rate):
                result=audit_run([100,100,100,105,110,110,110,110],{1:2,4:'close'},margin=rate)
                self.assertAlmostEqual(result['metrics']['one_hand_profit_pct'],99.79/(100*10*rate)*100)
                self.assertAlmostEqual(result['metrics']['one_hand_net_profit'],99.79)
                self.assertAlmostEqual(result['metrics']['net_profit'],199.58)
                self.assertAlmostEqual(result['metrics']['return_rate'],1.9958)
                self.assertEqual(result['metrics']['one_hand_margin_rate'],rate)

    def test_extreme_short_loss_can_reduce_equity_below_zero_without_phantom_margin(self):
        result=audit_run([100,100,100,700,700,700,700,700],{1:-2,4:'close'})
        self.assertAlmostEqual(result['equity_curve'][3]['value'],-2000.2)
        self.assertAlmostEqual(result['metrics']['net_profit'],-12001.6)
        self.assertIsNone(result['metrics']['sharpe_ratio'])

    def test_invalid_accounting_inputs_fail_before_data_fetch(self):
        for params,cash in [({'contract_multiplier':0},10000),({'margin_rate':0},10000),({'margin_rate':2},10000),({},0)]:
            with self.subTest(params=params,cash=cash), patch.object(engine,'fetch_data') as fetch, contextlib.redirect_stdout(io.StringIO()):
                result=engine.BacktestEngine().run('AUDIT','daily',params,initial_cash=cash)
                self.assertIn('error',result)
                fetch.assert_not_called()

    def test_annualized_sharpe_uses_daily_returns_or_weekly_factor(self):
        curve=[{'date':f'2025-01-0{i+1} 00:00:00','value':v} for i,v in enumerate([100,110,99,108])]
        returns=np.array([0,.1,-.1,108/99-1])
        m=equity_statistics(curve,100,'daily')
        self.assertAlmostEqual(m['sharpe_ratio'],returns.mean()/returns.std()*math.sqrt(252))
        self.assertAlmostEqual(m['max_drawdown'],10)
        self.assertAlmostEqual(equity_statistics(curve,100,'weekly')['sharpe_ratio'],returns.mean()/returns.std()*math.sqrt(52))
        intraday=[{'date':'2025-01-01 09:00:00','value':95},{'date':'2025-01-01 15:00:00','value':100}]+curve[1:]
        self.assertAlmostEqual(equity_statistics(intraday,100,'5')['sharpe_ratio'],m['sharpe_ratio'])

    def test_weekly_curve_preserves_actual_last_bar_inside_end_date(self):
        result=audit_run([100,100,100,105,110,110,110,110],{1:2,4:'close'},period='weekly',
                         start_date='2025-01-03',end_date='2025-02-21')
        self.assertEqual(result['equity_curve'][-1]['date'],'2025-02-21 00:00:00')
        self.assertAlmostEqual(result['equity_curve'][-1]['value'],result['metrics']['final_value'])
        self.assertEqual(len(result['equity_curve']),8)

    def test_sharpe_excludes_flat_warmup_before_requested_window(self):
        result=audit_run([100]*7+[105,110,110,110,110],{5:2,8:'close'},start_date='2025-01-06')
        values=np.array([v['value'] for v in result['equity_curve']])
        self.assertEqual(len(values),7)
        returns=values/np.r_[10000,values[:-1]]-1
        self.assertAlmostEqual(result['metrics']['sharpe_ratio'],returns.mean()/returns.std()*math.sqrt(252))

    def test_zero_account_equity_does_not_break_curve_recording(self):
        result=audit_run([100,100,100,600,610,610,610,610],{1:-2,4:'close'},cash=10000.2)
        self.assertAlmostEqual(result['equity_curve'][3]['value'],0)
        self.assertAlmostEqual(result['equity_curve'][4]['value'],-200)
        self.assertAlmostEqual(result['equity_curve'][-1]['value'],result['metrics']['final_value'])


if __name__ == '__main__':
    unittest.main()
