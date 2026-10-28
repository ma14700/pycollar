export function contractWindow(month) {
    if (typeof month !== 'string' || !/^\d{2}(0[1-9]|1[0-2])$/.test(month)) {
        throw new Error('合约月份须为四位 YYMM，例如 2605、2701');
    }
    const year = 2000 + Number(month.slice(0, 2));
    const deliveryMonth = Number(month.slice(2));
    const iso = date => date.toISOString().slice(0, 10);
    return {
        contract_month: month,
        start_date: iso(new Date(Date.UTC(year, deliveryMonth - 6, 1))),
        end_date: iso(new Date(Date.UTC(year, deliveryMonth - 2, 23))),
    };
}

export function applyContractBacktest(request, month) {
    if (!month) return { ...request };
    if (request.market_type !== 'futures') throw new Error('具体合约回测仅适用于期货');
    const match = /^([A-Za-z]+)(0|\d{4})$/.exec(request.symbol);
    if (!match || !['0', month].includes(match[2])) throw new Error('交易品种与合约月份不一致');
    return {
        ...request, ...contractWindow(month), symbol: `${match[1].toUpperCase()}${month}`,
        data_provider: 'tqsdk', data_source: 'main',
    };
}

export function normalizeContractMonths(value) {
    if (value == null || value === '') return [];
    const months = [...new Set(Array.isArray(value) ? value : [value])];
    months.forEach(contractWindow);
    return months;
}

export function buildBacktestTargets(symbols, selection) {
    const products = [...new Set(Array.isArray(symbols) ? symbols : [symbols])];
    if (!products.length || products.some(symbol => !symbol)) throw new Error('请至少选择一个品种');
    const months = normalizeContractMonths(selection);
    if (!months.length) return products.map(symbol => ({ symbol, base_symbol: symbol, contract_month: undefined }));
    if (products.length !== 1) throw new Error('多合约回测请先选择一个交易品种');
    return months.map(month => ({ ...applyContractBacktest({ symbol: products[0], market_type: 'futures' }, month), base_symbol: products[0] }));
}
