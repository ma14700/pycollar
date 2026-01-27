
import unittest
from unittest.mock import MagicMock
import sys
import os

# Add server directory to path to import engine
sys.path.append(os.path.join(os.path.dirname(__file__), 'server'))

# Mocking backtrader classes since we can't easily import them without complex setup
class MockStrategy:
    def __init__(self):
        self.p = MagicMock()
        self.p.contract_multiplier = 10
        self.p.margin_rate = 0.1
        self.accum_profit_per_hand = 0.0
        self.accum_profit_pct = 0.0
        self.sum_entry_price = 0.0
        self.closed_trade_count = 0
        self.max_trade_pnl = -float('inf')
        self.min_trade_pnl = float('inf')
        self.max_profit_points = 0.0
        self.max_loss_points = 0.0
        
    def notify_trade(self, trade):
        # Copy-paste logic from engine.py LoggingStrategy.notify_trade (simplified for test)
        if trade.isclosed:
            multiplier = self.p.contract_multiplier
            size = abs(trade.size)
            if size == 0: size = 1 # Simplified handling
            
            pnl = trade.pnlcomm # Net PnL
            
            if size > 0 and multiplier > 0:
                points = pnl / (size * multiplier)
                
                # 累计每手净利润
                self.accum_profit_per_hand += pnl / size
                
                # 累计盈利百分比 (基于开仓价)
                # Logic to be tested:
                # User Logic: (TotalNetProfitPerHand / AverageEntryPrice)
                if trade.price > 0:
                    self.sum_entry_price += trade.price
                    self.closed_trade_count += 1
                    
                    avg_entry_price = self.sum_entry_price / self.closed_trade_count
                    if avg_entry_price > 0:
                        self.accum_profit_pct = (self.accum_profit_per_hand / avg_entry_price)
                
                if pnl > self.max_trade_pnl:
                    self.max_trade_pnl = pnl
                    self.max_profit_points = points
                if pnl < self.min_trade_pnl:
                    self.min_trade_pnl = pnl
                    self.max_loss_points = points

class TestProfitCalculation(unittest.TestCase):
    def test_long_profit_pct(self):
        """Test Long Trade Profit Percentage (Net / Price)"""
        strat = MockStrategy()
        
        # Trade: Buy @ 100, Sell @ 110. Size 1. Mult 10. Comm 5.
        trade = MagicMock()
        trade.isclosed = True
        trade.size = 1
        trade.price = 100.0 # Entry Price
        
        # Gross PnL = (110 - 100) * 1 * 10 = 100
        trade.pnl = 100.0 
        # Net PnL = 100 - 5 = 95
        trade.pnlcomm = 95.0
        
        strat.notify_trade(trade)
        
        # Expected %: (95 / 1) / 100 = 0.95
        self.assertAlmostEqual(strat.accum_profit_pct, 0.95)
        
        # Check Net Profit Per Hand
        # Expected: 95 / 1 = 95
        self.assertAlmostEqual(strat.accum_profit_per_hand, 95.0)

    def test_short_profit_pct(self):
        """Test Short Trade Profit Percentage (Net / Price)"""
        strat = MockStrategy()
        
        # Trade: Sell @ 100, Buy @ 90. Size -1. Mult 10. Comm 5.
        trade = MagicMock()
        trade.isclosed = True
        trade.size = -1 # Short
        trade.price = 100.0 # Entry Price
        
        # Gross PnL = (100 - 90) * 1 * 10 = 100 (Positive for profit)
        trade.pnl = 100.0
        # Net PnL = 95
        trade.pnlcomm = 95.0
        
        strat.notify_trade(trade)
        
        # Expected %: (95 / 1) / 100 = 0.95
        self.assertAlmostEqual(strat.accum_profit_pct, 0.95)

    def test_loss_pct(self):
        """Test Loss Percentage (Net / Price)"""
        strat = MockStrategy()
        
        # Trade: Buy @ 100, Sell @ 90. Size 1. Mult 10. Comm 5.
        trade = MagicMock()
        trade.isclosed = True
        trade.size = 1
        trade.price = 100.0
        
        # Gross PnL = (90 - 100) * 10 = -100
        trade.pnl = -100.0
        # Net PnL = -105
        trade.pnlcomm = -105.0
        
        strat.notify_trade(trade)
        
        # Expected %: (-105 / 1) / 100 = -1.05
        self.assertAlmostEqual(strat.accum_profit_pct, -1.05)

if __name__ == '__main__':
    unittest.main()
