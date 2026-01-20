import requests
import json

url = "http://localhost:8000/api/backtest"
payload = {
    "symbol": "SH0",
    "period": "daily",
    "strategy_params": {
        "fast_period": 10,
        "slow_period": 20,
        "atr_period": 14,
        "atr_multiplier": 2.0,
        "risk_per_trade": 0.02,
        "contract_multiplier": 30
    }
}

try:
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        data = response.json()
        print("Success!")
        print(f"Final Value: {data['metrics']['final_value']}")
        print(f"Sharpe Ratio: {data['metrics']['sharpe_ratio']}")
        print(f"Total Trades: {data['metrics']['total_trades']}")
    else:
        print(f"Failed: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"Error: {e}")
