
import sys
import os
import logging
import pandas as pd

# 设置日志
logging.basicConfig(level=logging.INFO)

# 添加项目路径
sys.path.append(os.getcwd())

from server.core.engine import BacktestEngine

def test_scan():
    print("Initializing BacktestEngine...")
    engine = BacktestEngine()
    
    # 模拟用户参数
    # 用户说是"铜"，选择60分钟
    # 注意：新浪分钟接口使用 '60' 表示 60分钟
    symbols = ['CU0'] 
    period = '60' 
    scan_window = 2
    
    # 20/55 双均线交叉
    strategy_params = {
        'fast_period': 20,
        'slow_period': 55,
        'fixed_size': 1,
        'print_log': True # 开启日志以便查看回测过程中的输出
    }
    
    strategy_name = 'TrendFollowingStrategy'
    
    print(f"Scanning {symbols} with period={period}, scan_window={scan_window}...")
    print(f"Strategy: {strategy_name}, Params: {strategy_params}")
    
    try:
        results = engine.scan_signals(
            symbols=symbols,
            period=period,
            scan_window=scan_window,
            strategy_params=strategy_params,
            strategy_name=strategy_name
        )
        
        print("\nScan Results:")
        for res in results:
            print(f"Symbol: {res['symbol']}")
            print(f"Signal Text: {res['signal_text']}")
            print("Raw Signals:")
            if not res['raw_signals']:
                print("  None")
            for sig in res['raw_signals']:
                print(f"  {sig}")
                
    except Exception as e:
        print(f"Error during scan: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_scan()
