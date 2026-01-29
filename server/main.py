from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from functools import lru_cache
import uvicorn
import sys
import os
import json

# 确保 core 模块可以被导入
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import akshare as ak
import datetime
from core.engine import BacktestEngine
from core.database import init_db, SessionLocal, BacktestRecord
from core.optimizer import StrategyOptimizer
from core.constants import get_multiplier, FUTURES_MULTIPLIERS, FUTURES_NAMES
from sqlalchemy.orm import Session
from sqlalchemy import desc

# 初始化数据库
init_db()

app = FastAPI()

# 数据库依赖
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class BacktestRequest(BaseModel):
    symbol: str
    period: str
    market_type: str = "futures" # 市场类型：futures/stock
    strategy_params: Dict[str, Any]
    initial_cash: float = 1000000.0 # 初始资金
    auto_optimize: bool = True # 是否开启自动优化
    start_date: Optional[str] = None # 开始时间 (YYYY-MM-DD)
    end_date: Optional[str] = None   # 结束时间 (YYYY-MM-DD)
    strategy_name: str = "TrendFollowingStrategy"
    data_source: str = "main" # 数据来源: main (主力), weighted (加权/指数)

@lru_cache(maxsize=1)
def get_all_stock_info():
    try:
        # 获取A股股票列表 (代码, 名称)
        # 结果包含: code, name
        df = ak.stock_info_a_code_name()
        return df
    except Exception as e:
        print(f"Error fetching stock list from AkShare: {e}")
        return None

@app.get("/api/symbols")
async def get_symbols(market_type: str = 'futures'):
    if market_type == 'futures':
        # FUTURES_NAMES is imported from core.constants
        
        # Generate list from FUTURES_MULTIPLIERS
        futures_list = []
        for code, multiplier in FUTURES_MULTIPLIERS.items():
            # Basic name mapping (can be expanded)
            name = FUTURES_NAMES.get(code, code)
            futures_list.append({
                "code": f"{code}0", # Main contract convention
                "name": f"{code} ({name})", 
                "multiplier": multiplier
            })
        return {"futures": futures_list}
    elif market_type == 'stock':
        stocks_list = []
        
        # 1. Add Indices (Hardcoded as they are not in stock_info_a_code_name usually)
        indices = [
            {"code": "sh000001", "name": "上证指数", "multiplier": 1},
            {"code": "sz399001", "name": "深证成指", "multiplier": 1},
            {"code": "sh000300", "name": "沪深300", "multiplier": 1},
            {"code": "sh000905", "name": "中证500", "multiplier": 1},
            {"code": "sh000852", "name": "中证1000", "multiplier": 1},
            {"code": "sz399006", "name": "创业板指", "multiplier": 1},
        ]
        stocks_list.extend(indices)

        # 2. Fetch Stocks
        df = get_all_stock_info()
        
        if df is not None and not df.empty:
            # Optimize iteration
            records = df.to_dict('records')
            for row in records:
                code = str(row['code'])
                name = row['name']
                
                # Determine prefix
                full_code = code
                if len(code) == 6:
                    if code.startswith('6'):
                        full_code = f"sh{code}"
                    elif code.startswith('0') or code.startswith('3'):
                        full_code = f"sz{code}"
                    elif code.startswith('4') or code.startswith('8') or code.startswith('9'):
                        full_code = f"bj{code}"
                
                stocks_list.append({
                    "code": full_code,
                    "name": name,
                    "multiplier": 100 # Default stock multiplier
                })
        else:
             # Fallback to hardcoded list if network fails
             stocks_list.extend([
                {"code": "sh600519", "name": "贵州茅台", "multiplier": 100},
                {"code": "sz000858", "name": "五粮液", "multiplier": 100},
                {"code": "sh600036", "name": "招商银行", "multiplier": 100},
                {"code": "sz002594", "name": "比亚迪", "multiplier": 100},
                {"code": "sh601318", "name": "中国平安", "multiplier": 100},
                {"code": "sz300750", "name": "宁德时代", "multiplier": 100},
                {"code": "sh600030", "name": "中信证券", "multiplier": 100}
             ])
             
        return {"stocks": stocks_list}
    else:
        return {"error": "Invalid market_type"}

@app.get("/api/quote/latest")
async def get_latest_quote(symbol: str, market_type: str = 'futures', data_source: str = 'main'):
    try:
        if market_type == 'stock':
             # 股票日线 (使用最近一年的数据以加快速度)
             start_dt = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime("%Y%m%d")
             end_dt = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%Y%m%d")
             code = symbol[-6:]
             try:
                 df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_dt, end_date=end_dt, adjust="qfq")
                 
                 if df is None or df.empty:
                     raise ValueError("Empty dataframe from EastMoney")
                 
                 latest = df.iloc[-1]
                 price = float(latest['收盘'])
                 date = str(latest['日期'])
             except Exception as e:
                 print(f"Quote EastMoney failed, trying Sina: {e}")
                 # Fallback to Sina
                 df = ak.stock_zh_a_daily(symbol=symbol, start_date=start_dt, end_date=end_dt, adjust="qfq")
                 
                 if df is None or df.empty:
                     raise HTTPException(status_code=404, detail="Symbol not found in both sources")
                 
                 latest = df.iloc[-1]
                 price = float(latest['close'])
                 date = str(latest['date'])
        else:
            fetch_symbol = symbol
            if data_source == 'weighted':
                # 尝试将主力合约代码转换为加权代码
                # 用户反馈：加权一般是888 (如 SH888)
                if symbol.endswith('0'):
                    fetch_symbol = symbol.replace('0', '888')
                elif symbol.endswith('888'):
                    fetch_symbol = symbol
                else:
                    fetch_symbol = symbol + '888'
            
            # 尝试获取数据
            try:
                df = ak.futures_zh_daily_sina(symbol=fetch_symbol)
            except Exception:
                df = None
            
            # 如果首选代码失败，尝试 fallback (仅在 weighted 模式下)
            if (df is None or df.empty) and data_source == 'weighted':
                print(f"Quote: {fetch_symbol} failed, trying alternatives...")
                alternatives = []
                base_symbol = symbol.rstrip('0') if symbol.endswith('0') else symbol.replace('888', '')
                alternatives.append(f"{base_symbol}13")
                alternatives.append(f"{base_symbol}Index")
                alternatives.append(f"{base_symbol}88")
                
                for alt in alternatives:
                    try:
                         df = ak.futures_zh_daily_sina(symbol=alt)
                         if df is not None and not df.empty:
                             print(f"Quote: Found alternative {alt}")
                             fetch_symbol = alt
                             break
                    except:
                        pass
                
                # 如果还是没找到，回退到主力
                if df is None or df.empty:
                     print(f"Quote: Fallback to main contract {symbol}")
                     fetch_symbol = symbol if not symbol.endswith('888') else symbol.replace('888', '0')
                     df = ak.futures_zh_daily_sina(symbol=fetch_symbol)

            if df is None or df.empty:
                raise HTTPException(status_code=404, detail="Symbol not found")
            latest = df.iloc[-1]
            price = float(latest['close'])
            date = str(latest['date'])
        
        return {
            "symbol": symbol,
            "price": price,
            "date": date
        }
    except Exception as e:
        print(f"Error fetching quote: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/backtest")
async def run_backtest(request: BacktestRequest, db: Session = Depends(get_db)):
    print(f"收到回测请求: {request.symbol}, {request.period}, {request.market_type}, {request.strategy_params}, 策略: {request.strategy_name}, 自动优化: {request.auto_optimize}, 时间段: {request.start_date} - {request.end_date}")
    engine = BacktestEngine()
    
    # 1. 运行初始回测
    result = engine.run(
        symbol=request.symbol, 
        period=request.period,
        market_type=request.market_type, 
        strategy_params=request.strategy_params,
        initial_cash=request.initial_cash,
        start_date=request.start_date,
        end_date=request.end_date,
        strategy_name=request.strategy_name,
        data_source=request.data_source
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    # 计算初始收益率
    initial_cash = result['metrics']['initial_cash']
    final_value = result['metrics']['final_value']
    net_profit = result['metrics']['net_profit']
    return_rate = (net_profit / initial_cash) * 100
    
    # 保存初始结果
    record = BacktestRecord(
        symbol=request.symbol,
        period=request.period,
        strategy_params=request.strategy_params,
        initial_cash=initial_cash,
        final_value=final_value,
        net_profit=net_profit,
        return_rate=return_rate,
        sharpe_ratio=result['metrics']['sharpe_ratio'],
        max_drawdown=result['metrics']['max_drawdown'],
        total_trades=result['metrics']['total_trades'],
        win_rate=result['metrics']['win_rate'],
        is_optimized=0
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    
    # 2. 检查是否需要自动优化
    optimized_result = None
    optimized_params = None
    
    if request.auto_optimize and return_rate < 20.0:
        optimizer = StrategyOptimizer()
        best_params, best_res = optimizer.optimize(
            symbol=request.symbol, 
            period=request.period, 
            initial_params=request.strategy_params,
            target_return=20.0,
            start_date=request.start_date,
            end_date=request.end_date,
            strategy_name=request.strategy_name,
            data_source=request.data_source
        )
        if best_res:
             optimized_result = best_res
             optimized_params = best_params
             
             # 保存优化后的结果
             opt_cash = best_res['metrics']['initial_cash']
             opt_profit = best_res['metrics']['net_profit']
             opt_return = (opt_profit / opt_cash) * 100
             
             opt_record = BacktestRecord(
                symbol=request.symbol,
                period=request.period,
                strategy_params=best_params,
                initial_cash=opt_cash,
                final_value=best_res['metrics']['final_value'],
                net_profit=opt_profit,
                return_rate=opt_return,
                sharpe_ratio=best_res['metrics']['sharpe_ratio'],
                max_drawdown=best_res['metrics']['max_drawdown'],
                total_trades=best_res['metrics']['total_trades'],
                win_rate=best_res['metrics']['win_rate'],
                is_optimized=1
            )
             db.add(opt_record)
             db.commit()

    message_str = "回测完成"
    if optimized_result:
        message_str += " (已自动优化)"
        
    # Construct response compatible with frontend
    response = result.copy()
    if optimized_result:
        response['optimization_info'] = {
            'triggered': True,
            'message': message_str,
            'original_return': return_rate,
            'optimized_return': (optimized_result['metrics']['net_profit'] / optimized_result['metrics']['initial_cash']) * 100,
            'optimized_result': optimized_result # Include full optimized result if needed
        }
    else:
        response['optimization_info'] = {'triggered': False}
        
    return response

@app.get("/api/strategy/code")
async def get_strategy_code():
    try:
        strategy_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core", "strategy.py")
        with open(strategy_path, "r", encoding="utf-8") as f:
            code = f.read()
        return {"code": code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SaveBacktestRequest(BaseModel):
    symbol: str
    period: str
    strategy_name: str
    strategy_params: Dict[str, Any]
    initial_cash: Optional[float] = None
    final_value: Optional[float] = None
    net_profit: Optional[float] = None
    return_rate: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    total_trades: Optional[int] = None
    win_rate: Optional[float] = None
    detail_data: Dict[str, Any]

@app.post("/api/backtest/save")
async def save_backtest_result(request: SaveBacktestRequest, db: Session = Depends(get_db)):
    try:
        record = BacktestRecord(
            symbol=request.symbol,
            period=request.period,
            strategy_name=request.strategy_name,
            strategy_params=request.strategy_params,
            initial_cash=request.initial_cash,
            final_value=request.final_value,
            net_profit=request.net_profit,
            return_rate=request.return_rate,
            sharpe_ratio=request.sharpe_ratio,
            max_drawdown=request.max_drawdown,
            total_trades=request.total_trades,
            win_rate=request.win_rate,
            detail_data=request.detail_data,
            is_optimized=0
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return {"status": "success", "id": record.id}
    except Exception as e:
        print(f"Save error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/backtest/list")
async def list_backtests(db: Session = Depends(get_db)):
    try:
        records = db.query(BacktestRecord).filter(BacktestRecord.detail_data.isnot(None)).order_by(desc(BacktestRecord.timestamp)).all()
        result = []
        for r in records:
            result.append({
                "id": r.id,
                "timestamp": r.timestamp,
                "symbol": r.symbol,
                "period": r.period,
                "strategy_name": r.strategy_name,
                "final_value": r.final_value,
                "return_rate": r.return_rate,
                "net_profit": r.net_profit,
                "max_drawdown": r.max_drawdown,
                "win_rate": r.win_rate,
                "total_trades": r.total_trades
            })
        return result
    except Exception as e:
        print(f"List error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/backtest/{record_id}")
async def get_backtest_detail(record_id: int, db: Session = Depends(get_db)):
    try:
        record = db.query(BacktestRecord).filter(BacktestRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")
        
        # 基础 metrics 从数据库列获取
        metrics = {
            "initial_cash": record.initial_cash,
            "final_value": record.final_value,
            "net_profit": record.net_profit,
            "return_rate": record.return_rate,
            "sharpe_ratio": record.sharpe_ratio,
            "max_drawdown": record.max_drawdown,
            "total_trades": record.total_trades,
            "win_rate": record.win_rate
        }

        # 从 detail_data 中合并更多 metrics (如 max_capital_usage 等)
        # 优先使用 detail_data 中的数据，因为它包含更完整的指标字段
        if record.detail_data and isinstance(record.detail_data, dict):
            saved_metrics = record.detail_data.get("metrics", {})
            if saved_metrics:
                metrics.update(saved_metrics)

        return {
            "id": record.id,
            "timestamp": record.timestamp,
            "symbol": record.symbol,
            "period": record.period,
            "strategy_name": record.strategy_name,
            "strategy_params": record.strategy_params,
            "metrics": metrics,
            "detail_data": record.detail_data
        }
    except Exception as e:
        print(f"Detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/backtest/{record_id}")
async def delete_backtest(record_id: int, db: Session = Depends(get_db)):
    try:
        record = db.query(BacktestRecord).filter(BacktestRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")
        db.delete(record)
        db.commit()
        return {"status": "success", "message": "Record deleted"}
    except Exception as e:
        print(f"Delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class BatchAnalyzeRequest(BaseModel):
    symbols: List[str]
    period: str
    market_type: str = "futures"
    strategy_params: Dict[str, Any]
    strategy_name: str = "TrendFollowingStrategy"

@app.post("/api/strategy/batch-analyze")
async def batch_analyze(request: BatchAnalyzeRequest):
    engine = BacktestEngine()
    results = engine.analyze_batch(
        symbols=request.symbols,
        period=request.period,
        strategy_params=request.strategy_params,
        strategy_name=request.strategy_name,
        market_type=request.market_type
    )
    return {"results": results}

class ScanRequest(BaseModel):
    symbols: List[str]
    period: str
    scan_window: int
    market_type: str = "futures"
    strategy_params: Dict[str, Any]
    strategy_name: str = "TrendFollowingStrategy"

@app.post("/api/strategy/scan")
async def scan_strategy(request: ScanRequest):
    engine = BacktestEngine()
    results = engine.scan_signals(
        symbols=request.symbols,
        period=request.period,
        scan_window=request.scan_window,
        strategy_params=request.strategy_params,
        strategy_name=request.strategy_name,
        market_type=request.market_type
    )
    return {"results": results}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
