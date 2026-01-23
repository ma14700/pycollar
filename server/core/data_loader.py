import akshare as ak
import pandas as pd
import datetime

def fetch_stock_data(symbol='sh600000', period='daily', start_date=None, end_date=None, adjust='qfq'):
    """
    获取股票数据
    :param symbol: 股票代码，如 'sh600000'
    :param period: 周期，'daily' (日线), '1', '5', '15', '30', '60' 分钟
    :param adjust: 复权方式，'qfq' (前复权), 'hfq' (后复权), '' (不复权)
    """
    print(f"正在从 AkShare 获取股票({symbol}) {period} 数据...")
    
    df = None
    try:
        # 处理日线数据
        if period == 'daily':
            # 优先尝试 AkShare 股票日线接口: stock_zh_a_hist (东方财富)
            # symbol 需要是 6 位代码，去掉前缀
            code = symbol[-6:]
            try:
                df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="19900101", end_date="20500101", adjust=adjust)
                
                # 清洗 (东方财富返回中文列名)
                df.rename(columns={
                    '日期': 'date',
                    '开盘': 'Open',
                    '最高': 'High',
                    '最低': 'Low',
                    '收盘': 'Close',
                    '成交量': 'Volume'
                }, inplace=True)
            except Exception as e_hist:
                print(f"东方财富接口(stock_zh_a_hist)调用失败，尝试新浪接口: {e_hist}")
                # Fallback: AkShare 股票日线接口: stock_zh_a_daily (新浪)
                # symbol 需要带前缀
                df = ak.stock_zh_a_daily(symbol=symbol, start_date="19900101", end_date="20500101", adjust=adjust)
                
                # 清洗 (新浪返回英文小写列名)
                df.rename(columns={
                    'date': 'date',
                    'open': 'Open',
                    'high': 'High',
                    'low': 'Low',
                    'close': 'Close',
                    'volume': 'Volume'
                }, inplace=True)
            
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df['OpenInterest'] = 0 # 股票无持仓量
            
        else:
            # 处理分钟数据
            # AkShare 股票分钟接口: stock_zh_a_minute
            # symbol 需要带前缀
            df = ak.stock_zh_a_minute(symbol=symbol, period=period, adjust=adjust)
            
            # 清洗
            # 返回列: day, open, high, low, close, volume
            df.rename(columns={
                'day': 'datetime',
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            }, inplace=True)
            
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
            df['OpenInterest'] = 0

        # 确保数值类型
        cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'OpenInterest']
        df[cols] = df[cols].apply(pd.to_numeric)
        
        print(f"成功获取 {len(df)} 条股票数据")

        # 日期过滤
        if df is not None and not df.empty:
            data_start = df.index.min()
            data_end = df.index.max()
            print(f"原始数据范围: {data_start} 到 {data_end}")

            if start_date:
                df = df[df.index >= pd.to_datetime(start_date)]
            if end_date:
                end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1)
                df = df[df.index < end_dt]
                
            if df.empty:
                error_msg = f"日期过滤后无数据。可用范围: {data_start} 至 {data_end}"
                print(f"错误: {error_msg}")
                raise ValueError(error_msg)

        return df

    except Exception as e:
        print(f"获取股票数据失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def fetch_data(symbol, period='5', market_type='futures', start_date=None, end_date=None, data_source='main'):
    if market_type == 'stock':
        return fetch_stock_data(symbol, period, start_date, end_date)
    else:
        return fetch_futures_data(symbol, period, start_date, end_date, data_source)

def fetch_futures_data(symbol='LH0', period='5', start_date=None, end_date=None, data_source='main'):
    """
    获取期货数据
    :param symbol: 合约代码
    :param period: 周期
    :param start_date: 开始日期
    :param end_date: 结束日期
    :param data_source: 数据来源 'main' (主力连续), 'weighted' (加权/指数)
    :return: DataFrame
    """
    # 处理加权/指数数据源
    fetch_symbol = symbol
    if data_source == 'weighted':
        # 尝试将主力合约代码转换为加权代码
        # 用户反馈：加权一般是888 (如 SH888)
        # 之前的逻辑是 13，现在优先尝试 888
        if symbol.endswith('0'):
            fetch_symbol = symbol.replace('0', '888')
        elif symbol.endswith('888'):
            fetch_symbol = symbol
        else:
            fetch_symbol = symbol + '888'
        print(f"请求加权数据，转换代码: {symbol} -> {fetch_symbol}")

    print(f"正在从 AkShare 获取期货({fetch_symbol}) {period} 数据 (Source: {data_source})...")
    
    df = None
    try:
        # 处理日线数据请求
        if period == 'daily':
            # AkShare 获取期货日线数据接口: futures_zh_daily_sina
            try:
                df = ak.futures_zh_daily_sina(symbol=fetch_symbol)
            except Exception as e_weighted:
                if data_source == 'weighted':
                    print(f"加权数据({fetch_symbol})获取失败: {e_weighted}")
                    print(f"尝试其他加权代码格式 (如 13, Index)...")
                    alternatives = []
                    base_symbol = symbol.rstrip('0') if symbol.endswith('0') else symbol.replace('888', '')
                    
                    # 尝试列表
                    alternatives.append(f"{base_symbol}13")      # 旧版加权/指数
                    alternatives.append(f"{base_symbol}Index")   # 指数
                    alternatives.append(f"{base_symbol}88")      # 其他可能
                    alternatives.append(f"{base_symbol}99")      # 其他可能
                    alternatives.append(f"{base_symbol}0")       # 主力 (作为最后尝试，但通常走fallback逻辑)
                    
                    found = False
                    for alt in alternatives:
                        try:
                            if alt == fetch_symbol: continue
                            print(f"尝试: {alt}")
                            df = ak.futures_zh_daily_sina(symbol=alt)
                            if df is not None and not df.empty:
                                print(f"成功获取替代代码: {alt}")
                                found = True
                                break
                        except:
                            continue
                    
                    if not found:
                        print(f"未找到 {symbol} 的有效加权/指数数据，自动回退到主力连续数据源。")
                        return fetch_futures_data(symbol=symbol, period=period, start_date=start_date, end_date=end_date, data_source='main')
                else:
                    raise e_weighted
            
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
            try:
                df = ak.futures_zh_minute_sina(symbol=fetch_symbol, period=period)
            except Exception as e_weighted:
                if data_source == 'weighted':
                    print(f"加权分钟数据({fetch_symbol})获取失败: {e_weighted}")
                    alternatives = []
                    base_symbol = symbol.rstrip('0') if symbol.endswith('0') else symbol.replace('888', '')
                    
                    alternatives.append(f"{base_symbol}13")
                    alternatives.append(f"{base_symbol}Index")
                    alternatives.append(f"{base_symbol}88")
                    alternatives.append(f"{base_symbol}99")
                    
                    found = False
                    for alt in alternatives:
                        try:
                            if alt == fetch_symbol: continue
                            print(f"尝试分钟数据: {alt}")
                            df = ak.futures_zh_minute_sina(symbol=alt, period=period)
                            if df is not None and not df.empty:
                                print(f"成功获取替代代码: {alt}")
                                found = True
                                break
                        except:
                            continue
                    
                    if not found:
                        print(f"未找到 {symbol} 的有效加权/指数分钟数据，自动回退到主力连续数据源。")
                        return fetch_futures_data(symbol=symbol, period=period, start_date=start_date, end_date=end_date, data_source='main')
                else:
                    raise e_weighted
            
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
            df = ak.futures_zh_daily_sina(symbol=fetch_symbol)
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
