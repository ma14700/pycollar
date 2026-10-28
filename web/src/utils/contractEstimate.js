import { finiteNumber } from './backtestAnalytics.js';

export function contractEstimate({ price, multiplier = 1, initialCash, marginRate = 0.12, marketType = 'futures' }) {
    const quote = finiteNumber(price);
    const lot = finiteNumber(multiplier);
    const cash = finiteNumber(initialCash);
    const margin = marketType === 'stock' ? 1 : finiteNumber(marginRate);
    if (!(quote > 0 && lot > 0 && cash !== null && cash >= 0 && margin > 0 && margin <= 1)) return null;
    const notional = quote * lot;
    const collateral = notional * margin;
    const openingFee = notional * 0.0001;
    return { price: quote, multiplier: lot, marginRate: margin, notional, collateral,
        maxHands: Math.floor(cash / (collateral + openingFee)) };
}

export function accountReturn(metrics = {}) {
    const cash = finiteNumber(metrics.initial_cash);
    const profit = finiteNumber(metrics.net_profit);
    return cash > 0 && profit !== null ? profit / cash * 100 : finiteNumber(metrics.return_rate);
}
