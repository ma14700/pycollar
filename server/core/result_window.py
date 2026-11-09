"""Filter executed results by date without silently keeping malformed events."""
import pandas as pd


def timestamp(value, label):
    try:
        result = pd.Timestamp(value)
        if pd.isna(result):
            raise ValueError()
        return result
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f'{label}包含无效日期') from error


def result_window(logs, trades, equity, start_date, end_date, initial_cash):
    start = timestamp(start_date, '开始日期') if start_date else None
    end = timestamp(end_date, '结束日期') + pd.Timedelta(days=1) if end_date else None
    def within(value):
        return (start is None or value >= start) and (end is None or value < end)
    def records(rows, label):
        selected = []
        for row in rows:
            if within(timestamp(row.get('date'), label)):
                selected.append(row)
        return selected
    final_logs = []
    before = [row for row in equity if start is not None and timestamp(row.get('date'), '权益曲线') < start]
    if before:
        pnl = before[-1]['value'] - initial_cash
        final_logs.append(f'{start_date}, --- 日志过滤窗口开始 (此前累计盈亏: {pnl:.2f}) ---')
    for log in logs:
        try:
            value = timestamp(log.split(',', 1)[0], '日志')
        except ValueError:
            # A plain warning has no date and is useful to the reader.
            final_logs.append(log)
            continue
        if within(value):
            final_logs.append(log)
    return final_logs, records(trades, '成交记录'), records(equity, '权益曲线')
