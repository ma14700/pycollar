export function defaultTradingSymbol(list, market = 'futures') {
    return (market === 'futures' && (list.find(item => item.code === 'JM0')
        || list.find(item => item.code === 'SH0'))) || list[0];
}

// Analysis pages previously selected the first five products on entry and
// cleared the selection when switching markets. Preserve both fallbacks.
export function defaultAnalysisSymbols(list, fallbackCount = 5) {
    const preferred = list.find(item => item.code === 'JM0');
    return preferred ? [preferred.code] : list.slice(0, fallbackCount).map(item => item.code);
}
