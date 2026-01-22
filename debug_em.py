
import akshare as ak

def test_em():
    print("Testing EM Futures...")
    # Try generic symbols
    symbols = ["RB00", "RB13", "RBM", "RBMAIN", "RB"]
    
    for s in symbols:
        print(f"\nFetching {s} from EM...")
        try:
            # Note: params might differ, checking docs or guessing
            # Usually needs start_date, end_date
            df = ak.futures_hist_em(symbol=s, start_date="20240101", end_date="20240201")
            if df is not None:
                print(f"Success {s}: {len(df)} rows")
                print(df.head(1))
        except Exception as e:
            print(f"Failed {s}: {e}")

if __name__ == "__main__":
    test_em()
