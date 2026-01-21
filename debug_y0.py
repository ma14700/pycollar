 
import sys
import os
import backtrader as bt
import pandas as pd
import akshare as ak
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from server.core.strategy import TrendFollowingStrategy

def debug_soybean_oil():
    symbol = "Y0" # 豆油主力
    print(f"Fetching daily data for {symbol}...")
    
    try:
        df = ak.futures_zh_daily_sina(symbol=symbol)
        if df is None or df.empty:
            print("No data found for Y0")
            return
            
        print(f"Got {len(df)} rows of data.")
        print(df.tail())
        
        # Prepare data for Backtrader
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume',
            'hold': 'OpenInterest'
        }, inplace=True)
        cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'OpenInterest']
        df[cols] = df[cols].apply(pd.to_numeric)
        
        # Filter date range (recent year)
        start_date = "2025-10-01"
        end_date = "2025-12-01"
        df = df[df.index >= pd.to_datetime(start_date)]
        # df = df[df.index <= pd.to_datetime(end_date)] # Optional
        
        print(f"Data after filtering: {len(df)} rows")
        
        if df.empty:
            print("No data after date filtering.")
            return

        cerebro = bt.Cerebro()
        
        # Add strategy
        cerebro.addstrategy(TrendFollowingStrategy, 
                           fast_period=10, 
                           slow_period=30, 
                           print_log=True)
        
        # Add data
        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)
        
        cerebro.broker.setcash(1000000.0)
        cerebro.broker.setcommission(commission=0.0001)
        
        print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())
        cerebro.run()
        print("Final Portfolio Value: %.2f" % cerebro.broker.getvalue())
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_soybean_oil()
