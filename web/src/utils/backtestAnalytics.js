import { parseLogItem } from './logParser.js';
import { strategyNameMap } from '../constants/index.js';

export const finiteNumber = value => {
    if (value === null || value === undefined || String(value).trim() === '') return null;
    const number = Number(typeof value === 'string' ? value.trim().replace(/%$/, '') : value);
    return Number.isFinite(number) ? number : null;
};

export const formatNumber = (value, digits = 2) => {
    const number = finiteNumber(value);
    return number === null ? '—' : number.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
};
export const formatPercent = value => finiteNumber(value) === null ? '—' : `${formatNumber(value)}%`;
export const valueColor = value => finiteNumber(value) === null || Number(value) === 0 ? '#64748b' : Number(value) > 0 ? '#dc4b57' : '#17a078';

function savedTimestamp(value) {
    if (!value) return null;
    const raw = String(value).replace(' ', 'T');
    const timestamp = Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw}Z`);
    return Number.isFinite(timestamp) ? timestamp : null;
}

export function tradingTimestamp(value) {
    if (!value) return null;
    let raw = String(value).replace(' ', 'T');
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) raw += 'T00:00:00';
    const timestamp = Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw}+08:00`);
    return Number.isFinite(timestamp) ? timestamp : null;
}

export function normalizeHistoryRecord(record) {
    const netProfit = finiteNumber(record.net_profit);
    const finalValue = finiteNumber(record.final_value);
    const initialCash = finiteNumber(record.initial_cash) ?? (finalValue !== null && netProfit !== null ? finalValue - netProfit : null);
    const returnPct = netProfit !== null && initialCash > 0 ? netProfit / initialCash * 100 : finiteNumber(record.return_rate);
    const savedAt = savedTimestamp(record.timestamp);
    return {
        ...record, netProfit, finalValue, initialCash, returnPct,
        winRatePct: finiteNumber(record.win_rate), drawdownPct: finiteNumber(record.max_drawdown),
        savedAt, dateKey: savedAt === null ? '' : new Date(savedAt).toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' }),
        outcome: (netProfit ?? returnPct) === null ? 'unknown' : (netProfit ?? returnPct) > 0 ? 'profit' : (netProfit ?? returnPct) < 0 ? 'loss' : 'flat',
    };
}

export function filterHistoryRecords(records, filters = {}) {
    const query = (filters.query || '').trim().toLowerCase();
    return records.filter(record => (!query || [record.id, record.symbol, record.symbolLabel, record.strategy_name, record.strategyLabel].join(' ').toLowerCase().includes(query))
        && (!filters.symbol || record.symbol === filters.symbol)
        && (!filters.strategy || record.strategy_name === filters.strategy)
        && (!filters.outcome || record.outcome === filters.outcome)
        && (!filters.start || (record.dateKey && record.dateKey >= filters.start))
        && (!filters.end || (record.dateKey && record.dateKey <= filters.end)));
}

export function summarizeHistory(records) {
    const returns = records.filter(record => record.returnPct !== null);
    const known = records.filter(record => record.outcome !== 'unknown');
    const profitable = known.filter(record => record.outcome === 'profit').length;
    return {
        count: records.length, profitable, known: known.length,
        profitablePct: known.length ? profitable / known.length * 100 : null,
        averageReturn: returns.length ? returns.reduce((sum, item) => sum + item.returnPct, 0) / returns.length : null,
        best: returns.reduce((best, item) => !best || item.returnPct > best.returnPct ? item : best, null),
    };
}

export function flattenResultLogs(results) {
    const runs = results?.isBatch ? (results.items || []).filter(item => item.success)
        : [{ data: results }];
    return runs.flatMap(({ data, symbol: fallbackSymbol, strategy_name }, runIndex) => (Array.isArray(data?.logs) ? data.logs : []).map((entry, index) => {
        const row = parseLogItem(entry, `${runIndex}:${index}`);
        const symbol = data.data_info?.symbol || data.backtest_request?.symbol || fallbackSymbol || '';
        const strategy = data.backtest_request?.strategy_name || strategy_name || data.strategy_info?.name || '';
        const strategyLabel = strategyNameMap[strategy] || strategy || '未记录策略';
        return { ...row, symbol, strategy, strategyLabel, timestamp: tradingTimestamp(row.date), sequence: index, runIndex };
    })).sort((a, b) => (a.timestamp ?? Infinity) - (b.timestamp ?? Infinity) || a.runIndex - b.runIndex || a.sequence - b.sequence);
}

export function filterLogRows(rows, filters = {}) {
    const query = (filters.query || '').trim().toLowerCase();
    return rows.filter(row => (!filters.symbol || row.symbol === filters.symbol)
        && (!filters.strategy || row.strategy === filters.strategy)
        && (!filters.kind || row.kind === filters.kind)
        && (!query || `${row.content} ${row.symbol} ${row.strategy || ''} ${row.strategyLabel || ''} ${row.action}`.toLowerCase().includes(query))
        && (!filters.start || row.date.slice(0, 10) >= filters.start)
        && (!filters.end || (row.date && row.date.slice(0, 10) <= filters.end)));
}

export function summarizeLogs(rows) {
    // Closing execution logs contain estimates too; only trade settlements count.
    const settlements = rows.filter(row => row.isSettlement && row.pnl !== null);
    const executions = rows.filter(row => row.isExecution);
    const winners = settlements.filter(row => row.pnl > 0).length;
    let cumulative = 0;
    const points = settlements.map(row => ({ ...row, cumulative: cumulative += row.pnl }));
    const distribution = Object.entries(rows.reduce((counts, row) => ({ ...counts, [row.kind]: (counts[row.kind] || 0) + 1 }), {}))
        .map(([kind, value]) => ({ kind, value }));
    return {
        count: rows.length, executions: executions.length, settled: settlements.length,
        netProfit: settlements.length ? cumulative : null, winners,
        winRate: settlements.length ? winners / settlements.length * 100 : null,
        fees: executions.some(row => row.comm !== null) ? executions.reduce((sum, row) => sum + (row.comm ?? 0), 0) : null,
        points, distribution,
    };
}

export function normalizedEquity(record) {
    const data = record.detail_data || record;
    const cash = finiteNumber(data.metrics?.initial_cash ?? record.metrics?.initial_cash);
    if (cash === null || cash <= 0) return [];
    return (data.equity_curve || []).flatMap(point => {
        const value = finiteNumber(point.value);
        const time = tradingTimestamp(point.date);
        return value === null || time === null ? [] : [[time, Number(((value - cash) / cash * 100).toFixed(4))]];
    }).sort((a, b) => a[0] - b[0]);
}

export function logsCsv(rows) {
    const kindNames = { execution: '成交', settlement: '结算', signal: '信号', system: '系统', warning: '异常', info: '信息' };
    const cell = value => {
        const text = String(value ?? '');
        const safe = typeof value === 'string' && /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;
        return `"${safe.replace(/"/g, '""')}"`;
    };
    const header = ['时间', '合约/品种', '策略', '策略代码', '类型', '动作', '价格', '数量', '费用', '结算净利', '内容'];
    return '\uFEFF' + [header, ...rows.map(row => [row.date, row.symbol, row.strategyLabel, row.strategy, kindNames[row.kind] || '信息', row.action, row.price, row.size, row.comm, row.isSettlement ? row.pnl : null, row.content])]
        .map(row => row.map(cell).join(',')).join('\r\n');
}

export function downloadLogCsv(rows, filename = 'trading-logs.csv') {
    const url = URL.createObjectURL(new Blob([logsCsv(rows)], { type: 'text/csv;charset=utf-8;' }));
    const link = document.createElement('a');
    link.href = url; link.download = filename;
    document.body.appendChild(link); link.click(); link.remove();
    URL.revokeObjectURL(url);
}
