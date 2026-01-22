
import akshare as ak

def list_methods():
    methods = [m for m in dir(ak) if 'futures' in m]
    print(f"Found {len(methods)} futures methods.")
    for m in methods:
        if 'index' in m or 'weighted' in m:
            print(m)
            
    print("-" * 20)
    print("Checking for NH (Nanhua):")
    for m in dir(ak):
        if 'nh' in m:
            print(m)

if __name__ == "__main__":
    list_methods()
