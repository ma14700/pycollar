
import sys
import os
from sqlalchemy import create_engine, text

# Add server directory to path
sys.path.append(os.path.join(os.getcwd(), 'server'))

from server.core.database import SQLALCHEMY_DATABASE_URL

def migrate():
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    with engine.connect() as conn:
        # Check if columns exist (sqlite specific pragma)
        result = conn.execute(text("PRAGMA table_info(backtest_records)")).fetchall()
        columns = [row[1] for row in result]
        
        if 'strategy_name' not in columns:
            print("Adding strategy_name column...")
            try:
                conn.execute(text("ALTER TABLE backtest_records ADD COLUMN strategy_name VARCHAR DEFAULT 'TrendFollowingStrategy'"))
            except Exception as e:
                print(f"Error adding strategy_name: {e}")

        if 'detail_data' not in columns:
            print("Adding detail_data column...")
            try:
                conn.execute(text("ALTER TABLE backtest_records ADD COLUMN detail_data JSON"))
            except Exception as e:
                print(f"Error adding detail_data: {e}")
                
    print("Migration completed.")

if __name__ == "__main__":
    migrate()
