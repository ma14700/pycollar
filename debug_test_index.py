
import akshare as ak
import pandas as pd

def test_ccidx():
    print("Testing futures_index_ccidx...")
    try:
        # It seems this function returns index data for all exchanges or specific ones?
        # Let's check help or just try to run it.
        # It usually requires no args or simple args.
        df = ak.futures_index_ccidx(symbol="100001") # Example index code?
        print(f"CCIDX Result: {len(df) if df is not None else 'None'}")
    except Exception as e:
        print(f"CCIDX Error: {e}")

def test_em_index():
    print("\nTesting futures_hist_em for index...")
    # EastMoney might use different codes for index.
    # Often index is not easily available via standard futures interface.
    # Try symbols like 'RB13', 'RB99' in EM interface?
    symbols = ['RB13', 'RB99', 'RBIndex']
    for s in symbols:
        try:
            print(f"Fetching {s} from EM...")
            # futures_hist_em(symbol="RB13", period="daily", start_date="20240101", end_date="20241231")
            # But we need to know the exact symbol format for EM.
            # Usually EM uses specific codes.
            pass
        except Exception:
            pass

def test_sina_main_display():
    print("\nTesting futures_display_main_sina...")
    try:
        df = ak.futures_display_main_sina()
        print(f"Display Main Result: {len(df)}")
        print(df.head())
    except Exception as e:
        print(f"Display Main Error: {e}")

if __name__ == "__main__":
    test_sina_main_display()
    # test_ccidx() # Requires knowing the symbol
