
import requests
import json
import datetime

def test_api():
    url = "http://127.0.0.1:8000/api/backtest"
    
    end_date = datetime.date.today().strftime('%Y-%m-%d')
    start_date = (datetime.date.today() - datetime.timedelta(days=365)).strftime('%Y-%m-%d')

    payload = {
        "symbol": "rb0",
        "period": "daily",
        "strategy_params": {
            "fast_period": 5,
            "slow_period": 20,
            "fixed_size": 1,
            "size_mode": "fixed"
        },
        "initial_cash": 50000,
        "start_date": start_date,
        "end_date": end_date,
        "strategy_name": "TrendFollowingStrategy",
        "market_type": "futures",
        "data_source": "main",
        "auto_optimize": False
    }

    print(f"Sending POST request to {url}...")
    try:
        response = requests.post(url, json=payload)
        
        if response.status_code != 200:
            print(f"Request failed with status {response.status_code}")
            print(response.text)
            return

        data = response.json()
        metrics = data.get("metrics", {})
        
        print("\n--- API Metrics Verification ---")
        keys_to_verify = [
            'one_hand_net_profit',
            'max_profit_points',
            'max_loss_points',
            'one_hand_profit_pct',
            'total_trades',
            'net_profit'
        ]
        
        all_present = True
        for key in keys_to_verify:
            if key not in metrics:
                print(f"MISSING: {key}")
                all_present = False
            else:
                val = metrics[key]
                print(f"FOUND: {key} = {val} (Type: {type(val)})")
                
        if all_present:
            print("\nSUCCESS: API returned all required metrics.")
        else:
            print("\nFAILURE: API missing metrics.")

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_api()
