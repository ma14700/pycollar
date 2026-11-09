"""Lightweight saved-backtest summaries, separate from full result payloads."""
from .database import BacktestRecord

SUMMARY_FIELDS = ('id', 'timestamp', 'symbol', 'period', 'strategy_name', 'final_value',
                  'return_rate', 'net_profit', 'max_drawdown', 'win_rate', 'total_trades')


def summary_query(db):
    return db.query(*(getattr(BacktestRecord, field) for field in SUMMARY_FIELDS)).filter(
        BacktestRecord.detail_data.isnot(None))


def summary(row):
    return {field: getattr(row, field) for field in SUMMARY_FIELDS}


def history_page(db, cursor=None, limit=200):
    query = summary_query(db)
    if cursor is not None:
        query = query.filter(BacktestRecord.id < cursor)
    rows = query.order_by(BacktestRecord.id.desc()).limit(limit + 1).all()
    more = len(rows) > limit
    items = [summary(row) for row in rows[:limit]]
    return {'items': items, 'has_more': more,
            'next_cursor': items[-1]['id'] if more else None}
