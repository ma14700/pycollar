from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
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
from core.constants import get_multiplier
from sqlalchemy.orm import Session

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
    strategy_params: Dict[str, Any]
    auto_optimize: bool = True # 是否开启自动优化
    start_date: Optional[str] = "2025-01-01" # 开始时间 (YYYY-MM-DD)
    end_date: Optional[str] = "2026-01-01"   # 结束时间 (YYYY-MM-DD)
    strategy_name: str = "TrendFollowingStrategy"

@app.post("/api/backtest")
async def run_backtest(request: BacktestRequest, db: Session = Depends(get_db)):
    print(f"收到回测请求: {request.symbol}, {request.period}, {request.strategy_params}, 策略: {request.strategy_name}, 自动优化: {request.auto_optimize}, 时间段: {request.start_date} - {request.end_date}")
    engine = BacktestEngine()
    
    # 1. 运行初始回测
    result = engine.run(
        symbol=request.symbol, 
        period=request.period, 
        strategy_params=request.strategy_params,
        start_date=request.start_date,
        end_date=request.end_date,
        strategy_name=request.strategy_name
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
            strategy_name=request.strategy_name
        )
        
        if best_res:
             # 计算优化后的收益率
            opt_final_value = best_res['metrics']['final_value']
            opt_net_profit = best_res['metrics']['net_profit']
            opt_return_rate = (opt_net_profit / initial_cash) * 100
            
            if opt_return_rate > return_rate:
                print(f"优化成功! 新收益率: {opt_return_rate:.2f}%")
                optimized_result = best_res
                optimized_params = best_params
                optimization_msg = f"原始收益率 {return_rate:.2f}% 未达标 (<20%)。已自动优化参数，新收益率 {opt_return_rate:.2f}%。"
                
                # 保存优化后的结果
                # ... existing code ...
            else:
                optimization_msg = "自动优化尝试未找到更好的参数组合。"
        else:
             optimization_msg = "自动优化失败，未产生有效结果。"
             
    # 构建最终响应
    response_data = result
    if optimized_result:
        response_data = optimized_result
        response_data['optimization_info'] = {
            'triggered': True,
            'message': optimization_msg,
            'original_return': return_rate,
            'optimized_return': (optimized_result['metrics']['net_profit'] / initial_cash) * 100,
            'optimized_params': optimized_params
        }
    else:
        response_data['optimization_info'] = {
            'triggered': False,
            'message': "收益率已达标或未开启自动优化" if return_rate >= 20 else "自动优化未找到更好结果"
        }

    return response_data

class StrategyCodeRequest(BaseModel):
    code: str

@app.get("/api/strategy/code")
async def get_strategy_code():
    try:
        strategy_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core", "strategy.py")
        with open(strategy_path, "r", encoding="utf-8") as f:
            code = f.read()
        return {"code": code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/strategy/code")
async def save_strategy_code(request: StrategyCodeRequest):
    try:
        # 简单校验语法
        compile(request.code, "<string>", "exec")
        
        strategy_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core", "strategy.py")
        with open(strategy_path, "w", encoding="utf-8") as f:
            f.write(request.code)
        return {"status": "success", "message": "Strategy code updated successfully"}
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Syntax Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 缓存品种列表
CACHED_SYMBOLS = []
LAST_CACHE_TIME = None

@app.get("/api/symbols")
async def get_symbols():
    global CACHED_SYMBOLS, LAST_CACHE_TIME
    
    # 简单的缓存机制 (1小时失效)
    if CACHED_SYMBOLS and LAST_CACHE_TIME:
        if (datetime.datetime.now() - LAST_CACHE_TIME).total_seconds() < 3600:
            return {"futures": CACHED_SYMBOLS}
            
    try:
        print("正在从 AkShare 获取最新期货品种列表...")
        df = ak.futures_display_main_sina()
        
        futures_list = []
        for _, row in df.iterrows():
            symbol = row['symbol']
            name = row['name']
            
            # 过滤掉非主力连续合约 (通常我们只关注主连)
            # Sina 返回的通常都是主连 (如 V0, M0)
            
            multiplier = get_multiplier(symbol)
            
            futures_list.append({
                "code": symbol,
                "name": f"{name} ({symbol})",
                "multiplier": multiplier
            })
            
        CACHED_SYMBOLS = futures_list
        LAST_CACHE_TIME = datetime.datetime.now()
        
        return {"futures": futures_list}
        
    except Exception as e:
        print(f"获取品种列表失败: {e}")
        # 如果失败，返回硬编码的列表作为降级方案
        return {
            "futures": [
                {"code": "LH0", "name": "生猪主力 (LH0)", "multiplier": 16},
                {"code": "SH0", "name": "烧碱主力 (SH0)", "multiplier": 30},
                {"code": "RB0", "name": "螺纹钢主力 (RB0)", "multiplier": 10},
                {"code": "M0", "name": "豆粕主力 (M0)", "multiplier": 10},
                {"code": "IF0", "name": "沪深300 (IF0)", "multiplier": 300}
            ]
        }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
