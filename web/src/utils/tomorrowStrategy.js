import { ma144ExitStrategyOptions } from './ma144ExitStrategies.js';

export const tomorrowStrategyOptions = [
    ...ma144ExitStrategyOptions,
    { value: 'MA55BreakoutStrategy', label: 'MA55突破（多空反手）', defaults: { ma_period: 55 } },
    { value: 'MA55TouchExitStrategy', label: 'MA55突破+触碰平仓', defaults: { ma_period: 55 } },
    { value: 'MA20MA55CrossoverStrategy', label: '20/55双均线交叉(多空)', defaults: { fast_period: 20, slow_period: 55 } },
    { value: 'MA20MA55LongOnlyStrategy', label: '20/55双均线交叉多（只做多）', defaults: { fast_period: 20, slow_period: 55 } },
    { value: 'MA20MA55ShortOnlyStrategy', label: '20/55双均线交叉空（只做空）', defaults: { fast_period: 20, slow_period: 55 } },
    { value: 'MA20MA60CrossoverStrategy', label: '20/60双均线交叉(多空)', defaults: { fast_period: 20, slow_period: 60 } },
    { value: 'MA5MA20CrossoverStrategy', label: '5/20双均线交叉(多空)', defaults: { fast_period: 5, slow_period: 20 } },
    { value: 'MA5MA55CrossoverStrategy', label: '5/55均线交叉(多空)', defaults: { fast_period: 5, slow_period: 55, allow_reverse: true } },
    { value: 'MA20MA55RiskRewardStrategy', label: '20/55双均线+盈亏比', defaults: { fast_period: 20, slow_period: 55, risk_reward_ratio: 2, atr_period: 14, atr_multiplier: 2 } },
    { value: 'StockMA20MA55LongOnlyStrategy', label: '20/55双均线多头(股票)', defaults: { fast_period: 20, slow_period: 55 } },
    { value: 'MA20MA55PartialTakeProfitStrategy', label: '20/55双均线+盈利平半仓', defaults: { fast_period: 20, slow_period: 55, take_profit_points: 50 } },
    { value: 'DualMAFixedTPSLStrategy', label: '20/55双均线+固定止盈止损', defaults: { fast_period: 20, slow_period: 55, ma_type: 'SMA', sl_mode: 'points', sl_value: 50, tp_mode: 'points', tp_value: 100 } },
    { value: 'DKXStrategy', label: 'DKX多空线策略', defaults: { dkx_period: 20, dkx_ma_period: 10 } },
    { value: 'DKXPartialTakeProfitStrategy', label: 'DKX多空线+盈利平半仓', defaults: { dkx_period: 20, dkx_ma_period: 10, take_profit_points: 50 } },
    { value: 'DKXFixedTPSLStrategy', label: 'DKX多空线+固定止盈止损', defaults: { dkx_period: 20, dkx_ma_period: 10, take_profit_points: 100, stop_loss_points: 50 } },
    { value: 'TrendFollowingStrategy', label: '双均线趋势跟踪', defaults: { fast_period: 10, slow_period: 30, use_expma: false } },
];

export const strategyParameterKeys = [...new Set(tomorrowStrategyOptions.flatMap(option => Object.keys(option.defaults)))];

export function buildTomorrowAnalysisRequest(values) {
    const { symbols, market_type, period, strategy_name, data_provider, data_source, ...parameters } = values;
    return {
        symbols: [...symbols], market_type, period, strategy_name,
        data_provider: data_provider || (market_type === 'stock' ? 'akshare' : 'tqsdk'),
        data_source: data_source || 'main',
        strategy_params: Object.fromEntries(Object.entries(parameters).filter(([, value]) => value !== '' && value !== null && value !== undefined)),
    };
}

export function getTomorrowDetailRequest(record) {
    if (!record.analysis_request) throw new Error('请重新分析后查看详情');
    return structuredClone(record.analysis_request);
}

export function buildTomorrowDetailChart(data) {
    const dates = data.kline_data?.dates || [];
    const bars = data.kline_data?.values || [];
    if (!dates.length || !bars.length) return data;
    const size = data.position_state?.size || 0;
    const label = size > 0 ? `多 ${size}手` : size < 0 ? `空 ${Math.abs(size)}手` : '空仓';
    const entry = [...(data.trades || [])].reverse().find(trade => trade.opens_position);
    const status = {
        date: dates.at(-1), price: bars.at(-1)[1], action: '当前状态',
        custom_label: label, type: size < 0 ? 'sell' : 'buy',
        itemStyle: { color: size > 0 ? '#ef232a' : size < 0 ? '#14b143' : '#999' },
    };
    // Keep actual executions intact for the transaction table.
    return { ...data, signals: [...(entry ? [entry] : []), status] };
}
