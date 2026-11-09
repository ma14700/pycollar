
import akshare as ak
import pandas as pd
import datetime

def test_weighted_sina():
    symbols = ['V13', 'RB13', 'V0', 'RB0', 'VIndex', 'RBIndex', 'V88', 'RB88']
    print("Testing futures_zh_daily_sina with weighted symbols...")
    for s in symbols:
        try:
            print(f"Fetching {s}...")
            df = ak.futures_zh_daily_sina(symbol=s)
            if df is not None and not df.empty:
                print(f"  SUCCESS: {s} - {len(df)} rows. Last: {df.iloc[-1]['date']}")
            else:
                print(f"  FAILED: {s} - Empty")
        except Exception as e:
            print(f"  ERROR: {s} - {e}")

def test_other_interfaces():
    print("\nTesting other interfaces...")
    try:
        # Some potential interfaces for index/weighted
        # futures_zh_index_daily is a candidate if it exists in this version
        if hasattr(ak, 'futures_zh_index_daily'):
            print("Testing futures_zh_index_daily...")
            df = ak.futures_zh_index_daily(symbol="V") # Try generic symbol
            print(f"  Result: {len(df) if df is not None else 'None'}")
    except Exception as e:
        print(f"  Error in other interfaces: {e}")

if __name__ == "__main__":
    test_weighted_sina()
    test_other_interfaces()
