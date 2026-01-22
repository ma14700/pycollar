import akshare as ak
print("Futures functions:")
funcs = [x for x in dir(ak) if 'futures' in x]
print(funcs[:20]) # Print first 20
print(f"Total: {len(funcs)}")

print("\nSearching for 'index':")
print([x for x in funcs if 'index' in x])

print("\nSearching for 'weighted':")
print([x for x in funcs if 'weight' in x])
