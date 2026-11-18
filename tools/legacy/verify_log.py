
import backtrader as bt
import pandas as pd
import numpy as np
import datetime
from core.strategy import TrendFollowingStrategy

# Mock Data with forced crossover
def get_dummy_data():
    dates = pd.date_range(start='2024-01-01', periods=100)
    # Create a V-shape: Drop then Rise
    # Days 0-40: Drop from 100 to 60
    # Days 40-100: Rise from 60 to 120
    prices = []
    for i in range(100):
        if i < 40:
            p = 100 - i
        else:
            p = 60 + (i - 40) * 1.5
        prices.append(p)
        
    data = {
        'open': prices,
        'high': [p + 2 for p in prices],
        'low': [p - 2 for p in prices],
        'close': prices,
        'volume': [1000] * 100,
        'openinterest': [0] * 100
    }
    df = pd.DataFrame(data, index=dates)
    return bt.feeds.PandasData(dataname=df)

def run_verification(optimal_entry):
    cerebro = bt.Cerebro()
    
    # Configure strategy
    # Fast=5, Slow=10
    # Initial drop: Fast < Slow
    # Rise starts at day 40.
    # Around day 50, Fast should cross Slow -> Buy Signal
    cerebro.addstrategy(TrendFollowingStrategy, 
                        optimal_entry=optimal_entry,
                        print_log=True,
                        fast_period=5,
                        slow_period=10,
                        atr_period=5) # Short ATR
    
    data = get_dummy_data()
    cerebro.adddata(data)
    
    cerebro.broker.setcash(100000)
    
    if optimal_entry:
        cerebro.broker.set_coo(True)
        print("\n--- Testing Optimal Entry Mode: ON ---")
    else:
        print("\n--- Testing Optimal Entry Mode: OFF ---")
        
    cerebro.run()

if __name__ == '__main__':
    run_verification(False)
    run_verification(True)
