import akshare as ak
import pandas as pd

def check_spot_symbols():
    print("Fetching futures_zh_spot()...")
    try:
        # futures_zh_spot returns current snapshot of all domestic futures
        df = ak.futures_zh_spot()
        print(f"Got {len(df)} rows.")
        print(df.columns)
        
        # Filter for 'V' (PVC) related
        # Usually symbol column is 'symbol'
        if 'symbol' in df.columns:
            v_df = df[df['symbol'].astype(str).str.contains('V', case=False, na=False)]
            print("\nV related symbols:")
            print(v_df[['symbol', 'name']].head(20))
            
            # Check for 'Index' or 'Weighted' in name
            idx_df = df[df['name'].astype(str).str.contains('指数|加权', case=False, na=False)]
            print("\nIndex/Weighted related symbols (first 20):")
            print(idx_df[['symbol', 'name']].head(20))
        else:
            print("No 'symbol' column found.")
            print(df.head())
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_spot_symbols()
