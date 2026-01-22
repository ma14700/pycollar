import akshare as ak
import pandas as pd

def check_main_sina():
    print("Checking futures_display_main_sina()...")
    try:
        df = ak.futures_display_main_sina()
        print(f"Got {len(df)} rows.")
        print(df.head(20))
        # Check if 'symbol' column has anything unusual
        print(df['symbol'].unique()[:20])
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_main_sina()
