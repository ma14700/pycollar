
import akshare as ak
import pandas as pd
import traceback

def test_futures():
    print("=" * 50)
    print("TESTING FUTURES FETCHING")
    symbol = "SH0" # Shanghai Caustic Soda
    print(f"1. Testing Futures Daily (Sina) for {symbol}...")
    try:
        df = ak.futures_zh_daily_sina(symbol=symbol)
        print(f"Success! Got {len(df) if df is not None else 0} records.")
        if df is not None and not df.empty:
            print(df.tail(2))
    except Exception as e:
        print("FAILED Futures Daily:")
        print(e)

    print("-" * 30)
    print(f"2. Testing Futures Minute (Sina) for {symbol}...")
    try:
        df = ak.futures_zh_minute_sina(symbol=symbol, period="5")
        print(f"Success! Got {len(df) if df is not None else 0} records.")
        if df is not None and not df.empty:
            print(df.tail(2))
    except Exception as e:
        print("FAILED Futures Minute:")
        print(e)

def test_stocks():
    print("=" * 50)
    print("TESTING STOCK FETCHING")
    symbol = "sh600000"
    code = "600000"
    
    print(f"1. Testing Stock Daily (EastMoney - stock_zh_a_hist) for {code}...")
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="20250101", end_date="20250201", adjust="qfq")
        print(f"Success! Got {len(df) if df is not None else 0} records.")
    except Exception as e:
        print("FAILED Stock Daily (EastMoney):")
        print(e)

    print("-" * 30)
    print(f"2. Testing Stock Daily (Sina - stock_zh_a_daily) for {symbol}...")
    try:
        df = ak.stock_zh_a_daily(symbol=symbol, start_date="20250101", end_date="20250201", adjust="qfq")
        print(f"Success! Got {len(df) if df is not None else 0} records.")
    except Exception as e:
        print("FAILED Stock Daily (Sina):")
        print(e)

if __name__ == "__main__":
    test_futures()
    test_stocks()
