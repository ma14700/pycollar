import { buildBacktestTargets, normalizeContractMonths } from './contractBacktest.js';

// Analysis uses the actual contract symbol, without the backtest's delivery window.
export function analysisSymbols(symbols, months, market = 'futures') {
    if (market !== 'futures') {
        if (normalizeContractMonths(months).length) throw new Error('具体合约仅适用于期货');
        return [...symbols];
    }
    return buildBacktestTargets(symbols, months).map(target => target.symbol);
}

export function buildContractComparisons(payload, months) {
    const selected = normalizeContractMonths(months);
    return analysisSymbols([payload.symbol], selected).map(symbol => ({ ...payload, symbol,
        ...(selected.length ? { data_provider: 'tqsdk', data_source: 'main' } : {}) }));
}
