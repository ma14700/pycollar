
import akshare as ak

def test_nh():
    print("Testing Nanhua Futures Index...")
    try:
        # Get symbol table
        df_symbols = ak.futures_index_symbol_table_nh()
        print("NH Symbols:")
        print(df_symbols.head())
        
        # Check if 'RB' or 'V' is in it
        print("\nChecking for RB and V:")
        print(df_symbols[df_symbols['symbol'].str.contains('RB|V', case=False)])
        
        # Try to fetch data for RB
        print("\nFetching RB Index from NH...")
        df = ak.futures_price_index_nh(symbol="RB")
        if df is not None:
            print(f"Success RB: {len(df)} rows")
            print(df.tail(2))
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_nh()
