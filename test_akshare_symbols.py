import akshare as ak
import pandas as pd

try:
    print("Fetching futures rule table...")
    # This function usually returns details like multiplier, margin, etc.
    df_rules = ak.futures_rule_cn()
    print(df_rules.head())
    print(df_rules.columns)
    
    # Save to CSV to inspect if needed, or just print key columns
    print("\nSample records:")
    print(df_rules[['symbol', 'exchange', 'name', 'contract_unit']].head(10))
    
except Exception as e:
    print(f"Error fetching rules: {e}")

try:
    print("\nFetching main contracts from Sina...")
    # This gets price data, not the list of symbols directly in a simple list format with names
    # But let's see what we can find.
    # Usually we rely on known symbols or a listing function.
    pass
except Exception as e:
    print(f"Error: {e}")
