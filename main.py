import datetime
import pandas as pd
import numpy as np
import backtrader as bt
from strategy import TrendFollowingStrategy
from data_loader import fetch_futures_data

# 自定义期货佣金模式
class FuturesCommission(bt.CommInfoBase):
    params = (
        ('stocklike', False),  # 期货模式
        ('commtype', bt.CommInfoBase.COMM_PERC), # 按百分比收取
        ('percabs', True),     # 0.0002 表示 0.02%
        ('mult', 16.0),        # 合约乘数：生猪 16吨/手
        ('margin', None),      # 保证金 (如果需要更精细控制可设置，这里主要用乘数)
    )

def run_backtest():
    # 1. 初始化 Cerebro 引擎
    cerebro = bt.Cerebro()
    
    # 2. 设置策略参数
    # 禁用 EXPMA (使用 SMA)，并配置烧碱期货参数
    # 烧碱(SH) 合约乘数: 30吨/手
    cerebro.addstrategy(TrendFollowingStrategy, 
                        fast_period=10, 
                        slow_period=30,       
                        atr_period=14,
                        atr_multiplier=2.0,   
                        risk_per_trade=0.01,  
                        contract_multiplier=30, # 烧碱合约乘数 30
                        use_expma=False)
    
    # 3. 使用真实数据
    print("正在获取烧碱期货(SH)真实 日线 数据...")
    # 获取烧碱主力连续数据 (SH0)
    df = fetch_futures_data(symbol='SH0', period='daily')
    
    if df is not None:
        # 加载数据到 Cerebro
        # 将 Pandas DataFrame 转换为 Backtrader 数据馈送
        data = bt.feeds.PandasData(dataname=df, timeframe=bt.TimeFrame.Days, compression=1)
        cerebro.adddata(data)

    # 4. 设置初始资金
    start_cash = 1000000.0
    cerebro.broker.setcash(start_cash)
    
    # 设置期货佣金和乘数
    # 佣金：万分之2 (0.0002)
    # 乘数：16
    comminfo = FuturesCommission(
        commission=0.0002, 
        mult=16.0,
        margin=None # 简单起见，暂不强制检查保证金，由策略risk控制仓位
    )
    cerebro.broker.addcommissioninfo(comminfo)
    
    # 5. 运行回测
    print(f'初始资金: {start_cash:.2f}')
    cerebro.run()
    
    # 6. 输出结果
    end_cash = cerebro.broker.getvalue()
    profit = end_cash - start_cash
    return_rate = (profit / start_cash) * 100
    
    print(f'最终资金: {end_cash:.2f}')
    print(f'净利润: {profit:.2f}')
    print(f'收益率: {return_rate:.2f}%')
    
    # 7. 绘图
    try:
        # volume=False 避免成交量遮挡价格
        cerebro.plot(style='candlestick', volume=True) 
    except Exception as e:
        print(f"绘图失败: {e}")

if __name__ == '__main__':
    run_backtest()
