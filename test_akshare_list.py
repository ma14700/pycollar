import akshare as ak
import pandas as pd

try:
    print("Fetching main contracts from Sina...")
    df = ak.futures_display_main_sina()
    print(df.head())
    print(df.columns)
    print(f"Total rows: {len(df)}")
    
    # Check if we can find 'symbol' and 'name'
    if 'symbol' in df.columns and 'name' in df.columns:
        print("\nSample symbols:")
        print(df[['symbol', 'name']].head(10))
except Exception as e:
    print(f"Error fetching main contracts: {e}")
