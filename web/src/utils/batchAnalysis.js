import { finiteNumber, normalizedEquity, tradingTimestamp } from './backtestAnalytics.js';
import { accountReturn } from './contractEstimate.js';

export function drawdownCurve(data) {
    let peak = finiteNumber(data.metrics?.initial_cash);
    if (!(peak > 0)) return [];
    const points = (data.equity_curve || []).map(point => [tradingTimestamp(point.date), finiteNumber(point.value)])
        .filter(([time,value]) => time !== null && value !== null).sort((a,b)=>a[0]-b[0]);
    return points.map(([time, value]) => {
        peak = Math.max(peak, value);
        return [time, (peak - value) / peak * 100];
    });
}

export function buildBatchAnalysis(items = []) {
    const groups = new Map();
    const failures = [];
    for (const [index, item] of items.entries()) {
        const request = item.data?.backtest_request || {};
        const data = item.data || {};
        const metrics = data.metrics;
        const symbol = item.symbol || data.data_info?.symbol || request.symbol || '未知合约';
        const strategy = item.strategy_name || request.strategy_name || data.strategy_info?.name || '未知策略';
        if (!item.success || !metrics) {
            failures.push({ key: String(index), symbol, strategy, error: item.error || '结果缺少指标' });
            continue;
        }
        const info = data.data_info || {};
        // Only compare identical instruments and compatible account/data windows.
        const conditions = {
            symbol, period: info.period || request.period || '未知周期',
            start: info.start || data.kline_data?.dates?.[0] || null,
            end: info.end || data.kline_data?.dates?.at(-1) || null,
            requestedStart: request.start_date || null, requestedEnd: request.end_date || null,
            provider: info.provider || request.data_provider || null,
            source: info.data_source || request.data_source || null,
            cash: finiteNumber(metrics.initial_cash), margin: finiteNumber(metrics.one_hand_margin_rate ?? request.strategy_params?.margin_rate),
            commission: finiteNumber(metrics.commission_rate), version: metrics.calculation_version ?? null,
            basis: metrics.one_hand_return_basis || 'legacy',
        };
        const key = JSON.stringify(conditions);
        if (!groups.has(key)) groups.set(key, { key, conditions, rows: [] });
        const closed = finiteNumber(metrics.total_trades);
        groups.get(key).rows.push({
            key: String(index), symbol, strategy, data, params: request.strategy_params || {},
            returnPct: accountReturn(metrics), netProfit: finiteNumber(metrics.net_profit),
            drawdown: finiteNumber(metrics.max_drawdown), winRate: finiteNumber(metrics.win_rate),
            perHandProfit: finiteNumber(metrics.one_hand_net_profit), perHandReturn: finiteNumber(metrics.one_hand_profit_pct),
            sharpe: finiteNumber(metrics.sharpe_ratio), fees: finiteNumber(metrics.total_commission),
            trades: closed, size: finiteNumber(metrics.used_size),
            equity: normalizedEquity(data), drawdowns: drawdownCurve(data),
        });
    }
    return { groups: [...groups.values()], failures };
}

export function strategyHighlights(rows) {
    const compared = rows.filter(row => row.trades > 0);
    const extremes = (field, high) => {
        const values = compared.map(row => row[field]).filter(Number.isFinite);
        if (values.length < 2 || Math.max(...values) - Math.min(...values) < 1e-8) return null;
        return (high ? Math.max : Math.min)(...values);
    };
    const bestReturn = extremes('returnPct', true), lowRisk = extremes('drawdown', false);
    const highRisk = extremes('drawdown', true), bestUnit = extremes('perHandProfit', true);
    const highWin = extremes('winRate', true);
    return Object.fromEntries(rows.map(row => {
        const tags = [];
        if (row.netProfit < 0) tags.push({ text: '净亏损', color: 'green' });
        if (row.trades === 0) tags.push({ text: row.size > 0 ? '暂无已平仓交易' : '未成交', color: 'default' });
        if (row.trades > 0) {
            if (bestReturn !== null && row.returnPct === bestReturn) tags.push({ text: '收益领先', color: 'red' });
            if (lowRisk !== null && row.drawdown === lowRisk) tags.push({ text: '回撤较低', color: 'blue' });
            if (highRisk !== null && row.drawdown === highRisk) tags.push({ text: '回撤较高', color: 'orange' });
            if (bestUnit !== null && row.perHandProfit === bestUnit) tags.push({ text: '单手净利领先', color: 'purple' });
            if (highWin !== null && row.winRate === highWin) tags.push({ text: '胜率领先', color: 'cyan' });
            if (row.trades < 5) tags.push({ text: '交易样本少于5笔', color: 'default' });
        }
        return [row.key, tags];
    }));
}
