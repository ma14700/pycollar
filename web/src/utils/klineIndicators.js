const valid = value => typeof value === 'number' && Number.isFinite(value);
const period = (value, fallback) => Number.isInteger(Number(value)) && Number(value) > 0 ? Number(value) : fallback;

export function chartMacd(kline = {}, params = {}) {
    const periods = [period(params.macd_fast, 12), period(params.macd_slow, 26), period(params.macd_signal, 9)];
    const stored = kline.macd;
    const length = kline.dates?.length || 0;
    if (stored && ['dif', 'dea', 'hist'].every(key => Array.isArray(stored[key]) && stored[key].length === length)) {
        return { ...stored, periods: stored.periods || periods, fromSavedBars: false };
    }
    // Legacy records lack indicators: compute only from their saved prices.
    let fast = null, slow = null, signal = null;
    const result = { dif: [], dea: [], hist: [], periods, fromSavedBars: true };
    for (let index = 0; index < length; index++) {
        const close = kline.values?.[index]?.[1];
        if (!valid(close)) {
            fast = slow = signal = null;
            for (const key of ['dif', 'dea', 'hist']) result[key].push(null);
            continue;
        }
        fast = fast === null ? close : fast + 2 / (periods[0] + 1) * (close - fast);
        slow = slow === null ? close : slow + 2 / (periods[1] + 1) * (close - slow);
        const dif = fast - slow;
        signal = signal === null ? dif : signal + 2 / (periods[2] + 1) * (dif - signal);
        result.dif.push(dif); result.dea.push(signal); result.hist.push(2 * (dif - signal));
    }
    return result;
}

export function buildKlineIndicatorPanels(kline, equityCurve = [], params = {}) {
    const dates = kline.dates || [];
    const macd = chartMacd(kline, params);
    const equity = equityCurve.length > 0;
    const grid = [{ left: '7%', right: '5%', top: '13%', height: equity ? '40%' : '48%' },
        { left: '7%', right: '5%', top: equity ? '60%' : '70%', height: equity ? '16%' : '20%' }];
    if (equity) grid.push({ left: '7%', right: '5%', top: '83%', height: '8%' });
    const xAxis = grid.map((_, index) => ({ type: 'category', gridIndex: index, data: dates,
        boundaryGap: false, min: 'dataMin', max: 'dataMax', axisLine: { onZero: false },
        splitLine: { show: false }, axisLabel: { show: index === grid.length - 1 } }));
    const yAxis = grid.map((_, index) => ({ scale: true, gridIndex: index, splitNumber: index ? 2 : 5,
        splitArea: { show: index === 0 }, name: index === 1 ? `MACD (${macd.periods.join(',')})${macd.fromSavedBars ? ' · 保存K线计算' : ''}` : index === 2 ? '资金' : '',
        nameTextStyle: { fontSize: 11 }, axisLabel: { hideOverlap: true } }));
    const series = [
        ...[['DIF', macd.dif, '#e89d35'], ['DEA', macd.dea, '#7367d7']].map(([name, data, color]) => ({
            name, data, type: 'line', xAxisIndex: 1, yAxisIndex: 1, showSymbol: false,
            connectNulls: false, lineStyle: { width: 1.5, color }, itemStyle: { color } })),
        { name: 'MACD', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, barMaxWidth: 8,
            data: macd.hist.map(value => valid(value) ? { value, itemStyle: { color: value >= 0 ? '#ef232a' : '#14b143' } } : null) },
    ];
    if (equity) series.push({ name: '资金曲线', type: 'line', xAxisIndex: 2, yAxisIndex: 2,
        data: equityCurve.map(item => item?.value ?? null), showSymbol: false, connectNulls: false,
        lineStyle: { width: 1.5, color: '#1890ff' }, areaStyle: { opacity: .15 } });
    return { grid, xAxis, yAxis, series, axisIndices: grid.map((_, index) => index) };
}
