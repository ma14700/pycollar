import requests
try:
    res = requests.get('http://localhost:8000/api/symbols?market_type=futures')
    data = res.json()
    futures = data.get('futures', [])
    jm = next((f for f in futures if 'JM' in f['code']), None)
    print(f"JM Info: {jm}")
except Exception as e:
    print(e)
