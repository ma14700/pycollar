import akshare as ak
import pandas as pd

def test_index_data():
    print("Testing futures_zh_index_daily_em (EastMoney)...")
    try:
        # Try generic symbol 'rb' or 'V'
        df = ak.futures_zh_index_daily_em(symbol="V")
        print(f"V index data: {len(df)} rows")
        print(df.tail())
    except Exception as e:
        print(f"V index failed: {e}")

    try:
        df = ak.futures_zh_index_daily_em(symbol="RB")
        print(f"RB index data: {len(df)} rows")
        print(df.tail())
    except Exception as e:
        print(f"RB index failed: {e}")

    print("\nTesting futures_main_sina (Main Contract)...")
    try:
        # Just to compare
        df = ak.futures_main_sina(symbol="V0") 
        print(f"V0 main data: {len(df)} rows")
    except Exception as e:
        print(f"V0 main failed: {e}")

if __name__ == "__main__":
    test_index_data()
