import akshare as ak
import pandas as pd

def test_sina_suffixes():
    print("Testing Sina suffixes for 'V' (PVC)...")
    suffixes = ["0", "13", "88", "99", "Index", "I", "L", "S"]
    for s in suffixes:
        symbol = f"V{s}"
        print(f"  Trying {symbol}...", end="")
        try:
            df = ak.futures_zh_daily_sina(symbol=symbol)
            print(f" Success! ({len(df)} rows)")
            print(df.tail(1))
        except Exception as e:
            print(f" Failed.")

def test_em_suffixes():
    print("\nTesting EastMoney suffixes for 'V' (PVC)...")
    # EM usually uses specific codes or suffixes
    # V0 is often VMain
    candidates = ["V0", "V13", "V88", "V99", "V", "V.DCE", "VIndex"]
    for s in candidates:
        print(f"  Trying {s} with futures_hist_em...", end="")
        try:
            df = ak.futures_hist_em(symbol=s, start_date="20240101", end_date="20240201")
            if df is not None and not df.empty:
                print(f" Success! ({len(df)} rows)")
                print(df.tail(1))
            else:
                print(" Empty.")
        except Exception as e:
            print(f" Failed.")

if __name__ == "__main__":
    test_sina_suffixes()
    test_em_suffixes()
