
import akshare as ak
import pandas as pd
import traceback

def test_symbol_lists():
    print("=" * 50)
    print("TESTING SYMBOL LISTS")
    
    print("-" * 30)
    print("1. Testing Futures List (Sina - futures_display_main_sina)...")
    try:
        df = ak.futures_display_main_sina()
        print(f"Success! Got {len(df) if df is not None else 0} records.")
        if df is not None and not df.empty:
            print(df.head(2))
    except Exception as e:
        print("FAILED Futures List:")
        print(e)

    print("-" * 30)
    print("2. Testing Stock List (stock_info_a_code_name)...")
    try:
        df = ak.stock_info_a_code_name()
        print(f"Success! Got {len(df) if df is not None else 0} records.")
        if df is not None and not df.empty:
            print(df.head(2))
    except Exception as e:
        print("FAILED Stock List:")
        print(e)

if __name__ == "__main__":
    test_symbol_lists()
