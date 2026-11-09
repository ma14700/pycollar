import akshare as ak

# Print ALL futures related functions
funcs = [x for x in dir(ak) if 'futures' in x]
for f in funcs:
    print(f)
