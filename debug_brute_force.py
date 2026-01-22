
import akshare as ak
import pandas as pd
import time

def brute_force_sina():
    base = "RB"
    suffixes = ["0", "13", "88", "99", "Index", "I", "L", "S", "main", "zs"]
    print("Testing Sina suffixes for RB...")
    for s in suffixes:
        symbol = f"{base}{s}"
        try:
            # Sina usually takes symbol like RB0
            df = ak.futures_zh_daily_sina(symbol=symbol)
            if df is not None and not df.empty:
                print(f"SUCCESS Sina: {symbol} - {len(df)}")
            else:
                print(f"Empty Sina: {symbol}")
        except Exception as e:
            print(f"Error Sina {symbol}: {e}")

def brute_force_em():
    # futures_hist_em might need specific codes.
    # Try generic codes
    codes = ["RB", "RB0", "RB13", "RB88", "RB99", "RBMAIN", "RBZL", "RBZ"]
    print("\nTesting EM codes for RB...")
    for c in codes:
        try:
            # futures_hist_em parameters: symbol, period, start_date, end_date
            df = ak.futures_hist_em(symbol=c, period="daily", start_date="20240101", end_date="20240120")
            if df is not None and not df.empty:
                print(f"SUCCESS EM: {c} - {len(df)}")
            else:
                print(f"Empty EM: {c}")
        except Exception as e:
            print(f"Error EM {c}: {e}")

if __name__ == "__main__":
    brute_force_sina()
    brute_force_em()
