
import akshare as ak
import pandas as pd
import os

def test_stock_fetch():
    symbol_full = "sh600000"
    symbol_code = "600000"
    
    # Try to unset proxy env vars for this process if they exist, just to test
    # os.environ.pop('HTTP_PROXY', None)
    # os.environ.pop('HTTPS_PROXY', None)

    print("-" * 30)
    print(f"Testing stock_zh_a_hist (EastMoney) with code: {symbol_code}")
    try:
        df_daily = ak.stock_zh_a_hist(symbol=symbol_code, period="daily", start_date="20240101", end_date="20240201", adjust="qfq")
        print("EastMoney Daily Result:")
        print(df_daily.head() if df_daily is not None else "None")
    except Exception as e:
        print(f"EastMoney Daily Error: {e}")

    print("-" * 30)
    print(f"Testing stock_zh_a_daily (Sina) with symbol: {symbol_full}")
    try:
        # Sina usually takes 'sh600000'
        df_daily_sina = ak.stock_zh_a_daily(symbol=symbol_full, start_date="20240101", end_date="20240201", adjust="qfq")
        print("Sina Daily Result:")
        print(df_daily_sina.head() if df_daily_sina is not None else "None")
    except Exception as e:
        print(f"Sina Daily Error: {e}")

if __name__ == "__main__":
    test_stock_fetch()
