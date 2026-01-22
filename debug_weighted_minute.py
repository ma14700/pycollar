
import akshare as ak

def test_weighted_minute():
    print("Testing Weighted Futures Minute Data...")
    
    symbol = "V13" # PVC Index
    period = "5"
    
    try:
        print(f"Fetching {symbol} {period}min...")
        df = ak.futures_zh_minute_sina(symbol=symbol, period=period)
        if df is not None:
            print(f"Success {symbol}: {len(df)} rows")
            print(df.tail(2))
    except Exception as e:
        print(f"Failed {symbol}: {e}")

    symbol_main = "V0"
    try:
        print(f"Fetching {symbol_main} {period}min...")
        df = ak.futures_zh_minute_sina(symbol=symbol_main, period=period)
        if df is not None:
            print(f"Success {symbol_main}: {len(df)} rows")
    except Exception as e:
        print(f"Failed {symbol_main}: {e}")

if __name__ == "__main__":
    test_weighted_minute()
