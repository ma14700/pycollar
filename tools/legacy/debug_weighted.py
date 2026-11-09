
import akshare as ak
import pandas as pd

def test_weighted():
    print("Testing Weighted Futures Data...")
    
    # 1. Get Main List to see a sample
    try:
        df_list = ak.futures_display_main_sina()
        print("Main List Sample:")
        print(df_list.head(2))
    except Exception as e:
        print(f"List error: {e}")

    # Try V (PVC) and M (Meal)
    for base in ["V", "M", "RB", "IF"]:
        s0 = f"{base}0"
        s13 = f"{base}13"
        print(f"\nTesting {base}...")
        
        # Main
        try:
            df = ak.futures_zh_daily_sina(symbol=s0)
            print(f"  {s0}: {len(df) if df is not None else 0} rows")
        except:
            print(f"  {s0}: Failed")
            
        # Index
        try:
            df = ak.futures_zh_daily_sina(symbol=s13)
            print(f"  {s13}: {len(df) if df is not None else 0} rows")
        except Exception as e:
            print(f"  {s13}: Failed ({str(e)[:50]}...)")

if __name__ == "__main__":
    test_weighted()
