
import akshare as ak
import pandas as pd
import datetime

def test_em_weighted():
    # EastMoney symbols often don't have suffixes like '0' or '13' in the same way.
    # But sometimes they do.
    # Let's try to list symbols from EM first if possible, or guess.
    
    # Common EM futures codes might be 'RB2405', 'RB2410', etc.
    # Does it support 'RB13'?
    
    candidates = ['RB13', 'RB99', 'RBM', 'RBMAIN', 'RB']
    print("Testing futures_hist_em with candidates...")
    
    for s in candidates:
        try:
            print(f"Fetching {s}...")
            df = ak.futures_hist_em(symbol=s, period="daily", start_date="20240101", end_date="20240120")
            if df is not None and not df.empty:
                print(f"  SUCCESS: {s} - {len(df)} rows.")
            else:
                print(f"  FAILED: {s} - Empty")
        except Exception as e:
            print(f"  ERROR: {s} - {e}")

def test_zh_index_daily():
    # If futures_zh_index_daily exists (it wasn't in the list, but let's double check via try-except import/call)
    print("\nTesting futures_zh_index_daily (if exists)...")
    try:
        # It might be named differently or I missed it.
        # Let's try `get_futures_index` or similar?
        pass
    except:
        pass

if __name__ == "__main__":
    test_em_weighted()
