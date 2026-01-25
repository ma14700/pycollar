from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import os

# 数据库文件路径
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quant.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class BacktestRecord(Base):
    __tablename__ = "backtest_records"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.now)
    symbol = Column(String, index=True)
    period = Column(String)
    strategy_name = Column(String, default="TrendFollowingStrategy")
    
    # 策略参数 (JSON 存储)
    strategy_params = Column(JSON)
    
    # 回测结果指标
    initial_cash = Column(Float)
    final_value = Column(Float)
    net_profit = Column(Float)
    return_rate = Column(Float)  # 收益率 %
    sharpe_ratio = Column(Float)
    max_drawdown = Column(Float)
    total_trades = Column(Integer)
    win_rate = Column(Float)
    
    # 标记是否为自动优化的结果
    is_optimized = Column(Integer, default=0) # 0: 原始, 1: 优化后

    # 完整的回测结果数据
    detail_data = Column(JSON) 

def init_db():
    Base.metadata.create_all(bind=engine)
