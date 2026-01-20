import akshare as ak
import pandas as pd
import datetime

def fetch_futures_data(symbol='LH0', period='5', start_date=None, end_date=None):
    """
    获取期货主力合约数据 (通用)
    :param symbol: 合约代码，如 'LH0' (生猪), 'SH0' (烧碱)
    :param period: 周期，'daily' (日线), '1', '5', '15', '30', '60' 分钟
    :param start_date: 开始日期 (YYYY-MM-DD)
    :param end_date: 结束日期 (YYYY-MM-DD)
    :return: Pandas DataFrame 格式的 OHLC 数据
    """
    print(f"正在从 AkShare 获取期货({symbol}) {period} 数据...")
    
    df = None
    try:
        # 处理日线数据请求
        if period == 'daily':
            # AkShare 获取期货日线数据接口: futures_zh_daily_sina
            df = ak.futures_zh_daily_sina(symbol=symbol)
            
            # 数据清洗和格式化
            # 返回列：date, open, high, low, close, volume, hold, settle
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            # 转换列名为 Backtrader 标准
            df.rename(columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume',
                'hold': 'OpenInterest'
            }, inplace=True)
            
            # 确保是数值类型
            cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'OpenInterest']
            df[cols] = df[cols].apply(pd.to_numeric)
            
            print(f"成功获取 {len(df)} 条日线数据")
            
        else:
            # 处理分钟数据请求
            # AkShare 获取期货分钟数据接口: futures_zh_minute_sina
            df = ak.futures_zh_minute_sina(symbol=symbol, period=period)
            
            # 2. 数据清洗和格式化
            # 返回列：datetime, open, high, low, close, volume, hold
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
            
            # 转换列名为 Backtrader 标准
            df.rename(columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume',
                'hold': 'OpenInterest' # 持仓量
            }, inplace=True)
            
            # 确保是数值类型
            cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'OpenInterest']
            df[cols] = df[cols].apply(pd.to_numeric)
            
            print(f"成功获取 {len(df)} 条分钟数据")
            
        # 日期过滤
        if df is not None and not df.empty:
            data_start = df.index.min()
            data_end = df.index.max()
            print(f"原始数据范围: {data_start} 到 {data_end}")

            if start_date:
                df = df[df.index >= pd.to_datetime(start_date)]
            if end_date:
                # 加一天以包含结束日期当天的数据
                end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1)
                df = df[df.index < end_dt]
            
            if df.empty:
                error_msg = f"日期过滤后无数据。可用范围: {data_start} 至 {data_end}，请求范围: {start_date} 至 {end_date}。分钟数据通常仅提供近期历史。"
                print(f"错误: {error_msg}")
                raise ValueError(error_msg)
        
        return df
        
    except Exception as e:
        print(f"获取数据失败: {e}")
        # 如果获取分钟数据失败，尝试获取日线数据作为备选
        try:
            print("尝试获取日线数据作为备选...")
            df = ak.futures_zh_daily_sina(symbol=symbol)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df.rename(columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume',
                'hold': 'OpenInterest'
            }, inplace=True)
            return df
        except Exception as e2:
            print(f"获取日线数据也失败: {e2}")
            return None

def fetch_lh_data(period='5', adjust='0'):
    return fetch_futures_data(symbol='LH0', period=period)


if __name__ == "__main__":
    # 测试获取数据
    df = fetch_lh_data(period='5')
    if df is not None:
        print(df.head())
        print(df.tail())
