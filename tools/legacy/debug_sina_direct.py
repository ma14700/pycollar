import requests
import json

def test_sina_direct():
    symbols = ["V0", "V13", "V88", "V99", "VIndex", "V"]
    for s in symbols:
        url = f"https://stock2.finance.sina.com.cn/futures/api/json.php/IndexService.getInnerFuturesDailyKLine?symbol={s}"
        print(f"Fetching {s}...", end="")
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                try:
                    data = r.json()
                    if data:
                        print(f" Success! {len(data)} records. Sample: {data[-1]['d']}")
                    else:
                        print(f" Empty list.")
                except:
                    print(f" Invalid JSON. Content: {r.text[:50]}...")
            else:
                print(f" HTTP {r.status_code}")
        except Exception as e:
            print(f" Error: {e}")

if __name__ == "__main__":
    test_sina_direct()
