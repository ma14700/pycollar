import assert from 'node:assert/strict';
import test from 'node:test';
import { parseLogItem } from '../src/utils/logParser.js';
import { finiteNumber, normalizeHistoryRecord, filterHistoryRecords, summarizeHistory, flattenResultLogs, filterLogRows, summarizeLogs, normalizedEquity, logsCsv } from '../src/utils/backtestAnalytics.js';

test('history derives percentage from capital without multiplying existing percentage values', () => {
    const record = normalizeHistoryRecord({ net_profit: 5, final_value: 1005, return_rate: 90, win_rate: 0.5, max_drawdown: 0.75 });
    assert.equal(record.returnPct, 0.5);
    assert.equal(record.winRatePct, 0.5);
    assert.equal(record.drawdownPct, 0.75);
    assert.equal(normalizeHistoryRecord({ return_rate: '0.5%' }).returnPct, 0.5);
});

test('zero results remain zero and missing data is not fabricated into profitable or flat results', () => {
    const zero = normalizeHistoryRecord({ net_profit: 0, final_value: 1000, win_rate: 0, max_drawdown: 0 });
    const missing = normalizeHistoryRecord({});
    assert.equal(zero.outcome, 'flat'); assert.equal(zero.returnPct, 0);
    assert.equal(missing.outcome, 'unknown'); assert.equal(missing.returnPct, null);
    for (const value of [null, undefined, '', ' ', 'NaN', '12oops', Infinity]) assert.equal(finiteNumber(value), null);
});

test('history filters compose strategy, symbol, query, outcome, and Beijing save date', () => {
    const rows = [normalizeHistoryRecord({ id: 1, symbol: 'RB0', strategy_name: 'demo', net_profit: 5, final_value: 1005, timestamp: '2026-10-27T17:00:00', strategyLabel: '均线策略' }),
        normalizeHistoryRecord({ id: 2, symbol: 'AG0', strategy_name: 'demo', net_profit: -5, final_value: 995, timestamp: '2026-10-26T17:00:00' })];
    assert.deepEqual(filterHistoryRecords(rows, { query: '均线', symbol: 'RB0', strategy: 'demo', outcome: 'profit', start: '2026-10-28', end: '2026-10-28' }).map(row => row.id), [1]);
    assert.equal(filterHistoryRecords(rows, { symbol: 'RB0', outcome: 'loss' }).length, 0);
});

test('history summary excludes unknown returns and does not treat duplicate runs as a portfolio', () => {
    const rows = [{ returnPct: 10, outcome: 'profit' }, { returnPct: -5, outcome: 'loss' }, { returnPct: null, outcome: 'unknown' }];
    const result = summarizeHistory(rows);
    assert.equal(result.averageReturn, 2.5); assert.equal(result.profitablePct, 50); assert.equal(result.best.returnPct, 10);
    assert.equal(summarizeHistory([]).averageReturn, null);
});

test('closing a long remains a sell despite the holding direction saying long', () => {
    const row = parseLogItem('2026-01-03, 交易执行: 【平多】 价格: 100, 数量: -2, 费用: 0, 当前持仓: 0, 方向: 做多, 净利润: 50');
    assert.equal(row.type, 'sell'); assert.equal(row.kind, 'execution'); assert.equal(row.pnl, 50);
    assert.equal(row.comm, 0); assert.equal(row.pos, 0);
});

test('signals and canceled orders are not counted as executions', () => {
    for (const text of ['金叉信号: 做多', '平多信号: MA20 下穿 MA55']) {
        const row = parseLogItem(`2026-01-01, ${text}`);
        assert.equal(row.kind, 'signal'); assert.equal(row.isExecution, false);
    }
    assert.equal(parseLogItem('2026-01-01, 订单已取消/保证金不足/被拒绝').kind, 'warning');
});

test('legacy and structured settlement logs parse signed decimals and preserve original content', () => {
    assert.equal(parseLogItem('2026-01-03, 交易利润, 毛利 50.00, 净利 -12.34').pnl, -12.34);
    assert.equal(parseLogItem({ date: '2026-01-03', content: '交易结算', pnl: 0, kind: 'settlement' }).pnl, 0);
    assert.equal(parseLogItem('没有日期, 但有逗号').content, '没有日期, 但有逗号');
    assert.equal(parseLogItem('2026-01-03, 交易利润, 净利: +1.2e3').pnl, 1200);
});

test('profit chart counts only final settlements, not the duplicate execution estimate', () => {
    const rows = flattenResultLogs({ logs: [
        '2026-01-03, 交易执行: 【平多】 价格: 100, 数量: -2, 费用: 2, 净利润: 100',
        '2026-01-03, 交易利润, 毛利 104, 净利 98',
        '2026-01-04, 交易利润, 毛利 -10, 净利 -12',
        '2026-01-05, 交易利润, 毛利 0, 净利 0',
    ] });
    const summary = summarizeLogs(rows);
    assert.equal(summary.netProfit, 86); assert.equal(summary.settled, 3);
    assert.deepEqual(summary.points.map(point => point.cumulative), [98, 86, 86]);
    assert.equal(summary.executions, 1); assert.equal(summary.fees, 2);
    assert.ok(Math.abs(summary.winRate - 100 / 3) < 1e-10);
});

test('missing settlements are unknown rather than estimated from closing executions', () => {
    const summary = summarizeLogs(flattenResultLogs({ logs: ['2026-01-03, 交易执行: 【平多】 价格: 100, 净利润: 100'] }));
    assert.equal(summary.netProfit, null); assert.equal(summary.settled, 0);
    assert.equal(summary.winRate, null); assert.deepEqual(summary.points, []);
});

test('batch logs are sorted by trading time and keep symbols and unique row keys', () => {
    const rows = flattenResultLogs({ isBatch: true, items: [
        { success: true, symbol: 'RB0', data: { logs: ['2026-01-03, 交易利润, 净利 2'] } },
        { success: false, symbol: 'AG0', data: { logs: ['2026-01-01, 交易利润, 净利 999'] } },
        { success: true, symbol: 'SC0', data: { logs: ['2026-01-02, 交易利润, 净利 -1'] } },
    ] });
    assert.deepEqual(rows.map(row => row.symbol), ['SC0', 'RB0']);
    assert.equal(new Set(rows.map(row => row.key)).size, 2);
    assert.deepEqual(summarizeLogs(rows).points.map(point => point.cumulative), [-1, 1]);
    assert.equal(summarizeLogs(filterLogRows(rows, { symbol: 'RB0', kind: 'settlement', query: '利润', start: '2026-01-03', end: '2026-01-03' })).netProfit, 2);
});

test('comparison normalizes each run to its own initial cash and skips invalid points', () => {
    const record = { metrics: { initial_cash: 1000 }, equity_curve: [
        { date: '2026-01-01', value: 1000 }, { date: '2026-01-02', value: 1100 },
        { date: '2026-01-03', value: null }, { date: 'invalid', value: 1500 },
    ] };
    assert.deepEqual(normalizedEquity(record).map(point => point[1]), [0, 10]);
    assert.deepEqual(normalizedEquity({ ...record, metrics: { initial_cash: 0 } }), []);
});

test('CSV quotes multiline text and prevents formula execution while preserving numeric losses', () => {
    const csv = logsCsv([{ date: '2026-01-01', symbol: '=1+1', kind: 'settlement', isSettlement: true, pnl: -12, content: 'hello,"quoted"\nline' }]);
    assert.ok(csv.startsWith('\uFEFF')); assert.ok(csv.includes('"\'=1+1"'));
    assert.ok(csv.includes('"-12"')); assert.ok(csv.includes('hello,""quoted""\nline'));
});

test('batch logs carry actual contract and strategy through filtering and CSV', () => {
    const log='2026-10-29, 交易利润, 毛利 100, 净利 90';
    const results={isBatch:true,items:[
        {success:true,symbol:'JM0',strategy_name:'fallback',data:{data_info:{symbol:'JM2701'},backtest_request:{symbol:'JM2701',strategy_name:'MA20MA144LongOnlyStrategy'},logs:[log]}},
        {success:true,symbol:'JM2605',strategy_name:'MA20MA144ShortOnlyStrategy',data:{logs:[log]}},
        {success:true,symbol:'JM2701',data:{backtest_request:{symbol:'JM2701',strategy_name:'MA5MA55CrossoverStrategy'},logs:[log]}},
        {success:false,symbol:'JM0',data:{logs:[log]}},
    ]};
    const rows=flattenResultLogs(results);
    assert.deepEqual(rows.map(row=>row.symbol),['JM2701','JM2605','JM2701']);
    assert.equal(rows[0].strategy,'MA20MA144LongOnlyStrategy');
    assert.match(rows[0].strategyLabel,/金叉做多/);
    assert.equal(new Set(rows.map(row=>row.key)).size,3);
    assert.equal(filterLogRows(rows,{symbol:'JM2701'}).length,2);
    const filtered=filterLogRows(rows,{symbol:'JM2701',strategy:'MA5MA55CrossoverStrategy'});
    assert.equal(filtered.length,1);assert.equal(filterLogRows(rows,{query:'死叉做空'}).length,1);
    const csv=logsCsv(filtered);
    assert.match(csv,/合约\/品种/);assert.match(csv,/策略代码/);assert.match(csv,/JM2701/);assert.match(csv,/MA5MA55CrossoverStrategy/);
    assert.doesNotMatch(csv,/JM2605/);
});

test('single saved detail can recover contract from submitted request when metadata is absent',()=>{
    const rows=flattenResultLogs({backtest_request:{symbol:'SA2701',strategy_name:'MA20MA144ShortOnlyStrategy'},logs:['2026-10-29, 测试']});
    assert.equal(rows[0].symbol,'SA2701');assert.equal(rows[0].strategy,'MA20MA144ShortOnlyStrategy');
});
