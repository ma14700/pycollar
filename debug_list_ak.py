
import akshare as ak

def list_ak_functions():
    funcs = [x for x in dir(ak) if 'futures' in x]
    print("Futures functions:")
    for f in funcs:
        print(f)

if __name__ == "__main__":
    list_ak_functions()
