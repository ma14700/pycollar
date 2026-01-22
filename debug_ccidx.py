
import akshare as ak

def test_ccidx():
    print("Testing CCIDX...")
    try:
        df = ak.futures_index_ccidx(symbol="100001") # Example symbol
        print(df.head())
    except Exception as e:
        print(e)

if __name__ == "__main__":
    test_ccidx()
