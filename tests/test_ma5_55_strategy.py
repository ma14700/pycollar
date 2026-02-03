
import unittest
import datetime
import pandas as pd
import backtrader as bt
import sys
import os

# Add server path to allow importing core modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'server'))

try:
    from core.ma5_55_cross import MA5MA55CrossoverStrategy
except ImportError:
    # If running from tests directory directly
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from server.core.ma5_55_cross import MA5MA55CrossoverStrategy

class TestMA5MA55(unittest.TestCase):
    def create_cerebro(self, data, allow_reverse=True):
        cerebro = bt.Cerebro()
        feed = bt.feeds.PandasData(dataname=data)
        cerebro.adddata(feed)
        
        cerebro.addstrategy(MA5MA55CrossoverStrategy, 
                            fast_period=5, 
                            slow_period=20, # Use shorter period for test speed/data size
                            fixed_size=1,
                            allow_reverse=allow_reverse)
                            
        cerebro.broker.setcash(100000.0)
        cerebro.broker.setcommission(commission=0.0)
        
        cerebro.addanalyzer(bt.analyzers.Transactions, _name='trans')
        return cerebro

    def test_crossover_logic_reverse(self):
        """Test Golden Cross -> Death Cross with Reverse=True"""
        # Data Construction for MA5 vs MA20 (shorter for test)
        # 0-25: Price 100. MA5=100, MA20=100.
        # 26-30: Price 110. MA5 rises. MA20 rises slower. Cross UP.
        # 31-35: Price 90. MA5 drops. MA20 drops slower. Cross DOWN.
        
        dates = pd.date_range(start='2023-01-01', periods=50)
        prices = [100] * 25 + [110] * 5 + [90] * 10 + [100] * 10
        
        df = pd.DataFrame({
            'open': prices, 'high': prices, 'low': prices, 'close': prices, 'volume': [1000]*50
        }, index=dates)
        
        cerebro = self.create_cerebro(df, allow_reverse=True)
        strats = cerebro.run()
        strat = strats[0]
        trans = strat.analyzers.trans.get_analysis()
        
        # Verify Transactions
        # We expect:
        # 1. Buy (Open) when MA5 > MA20
        # 2. Sell (Close) + Sell (Open) when MA5 < MA20 -> Reverse
        
        # Print transactions for debug
        print("\nTransactions (Reverse=True):")
        for date, t_list in trans.items():
            for t in t_list:
                print(f"{date}: Size {t[0]}, Price {t[1]}, Value {t[2]}")
        
        # Count total transactions
        total_tx = sum(len(t_list) for t_list in trans.values())
        
        # We expect at least:
        # 1. Open Short (Size -1) (First signal was Death Cross in this data)
        # 2. Reverse to Long (Size 2) (Next signal Golden Cross)
        # 3. Auto Close (Size -1)
        
        has_reversal = False
        for date, t_list in trans.items():
            for t in t_list:
                if abs(t[0]) == 2:
                    has_reversal = True
                    break
        
        self.assertTrue(has_reversal, "Should have executed a reversal (Size 2)")

    def test_crossover_logic_no_reverse(self):
        """Test Golden Cross -> Death Cross with Reverse=False"""
        # Same data
        dates = pd.date_range(start='2023-01-01', periods=50)
        prices = [100] * 25 + [110] * 5 + [90] * 10 + [100] * 10
        
        df = pd.DataFrame({
            'open': prices, 'high': prices, 'low': prices, 'close': prices, 'volume': [1000]*50
        }, index=dates)
        
        cerebro = self.create_cerebro(df, allow_reverse=False)
        strats = cerebro.run()
        strat = strats[0]
        trans = strat.analyzers.trans.get_analysis()
        
        print("\nTransactions (Reverse=False):")
        for date, t_list in trans.items():
            for t in t_list:
                print(f"{date}: Size {t[0]}, Price {t[1]}, Value {t[2]}")
                
        # With Reverse=False:
        # 1. Open Short (Size -1).
        # 2. Signal Long -> Close Short (Size 1). Position 0.
        # 3. No new signal immediately (CrossOver is transient).
        # So we should NOT see Size 2.
        
        has_reversal = False
        for date, t_list in trans.items():
            for t in t_list:
                if abs(t[0]) == 2:
                    has_reversal = True
                    break
                    
        self.assertFalse(has_reversal, "Should NOT have executed a reversal (Size 2) when allow_reverse=False")


if __name__ == '__main__':
    unittest.main()
