const maColors = { 20: '#fa8c16', 55: '#1677ff', 60: '#13a8a8', 144: '#722ed1' };

export const buildCandleOption = (segment, following = null, maPeriods = [20, 55, 144]) => {
    const dates = [...segment.dates, ...(following?.dates || [])];
    const averages = [...new Set(maPeriods)].map(period => ({ period, color: maColors[period] }));
    return {
        animation: false,
        legend: { top: 0, data: ['K线', ...averages.map(({ period }) => `MA${period}`)] },
        tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
        grid: { left: 70, right: 25, top: 45, bottom: 75 },
        xAxis: {
            type: 'category', data: dates, scale: true, boundaryGap: true,
            axisLabel: {
                hideOverlap: true,
                formatter: value => dates.every(date => date.endsWith('00:00:00'))
                    ? value.slice(0, 10) : `${value.slice(5, 10)}\n${value.slice(11, 16)}`,
            },
        },
        yAxis: { type: 'value', scale: true },
        dataZoom: [{ type: 'inside' }, { type: 'slider', bottom: 10, height: 20 }],
        series: [{
            name: 'K线', type: 'candlestick',
            data: [...segment.ohlc, ...(following?.ohlc || [])],
            itemStyle: { color: '#cf1322', color0: '#3f8600', borderColor: '#cf1322', borderColor0: '#3f8600' },
            ...(following?.bars ? {
                markLine: { symbol: 'none', label: { formatter: '匹配结束' }, data: [{ xAxis: segment.bars - 1 }] },
                markArea: { silent: true, itemStyle: { color: 'rgba(250, 140, 22, 0.08)' }, data: [[{ xAxis: segment.bars - 1 }, { xAxis: dates.length - 1 }]] },
            } : {}),
        }, ...averages.map(({ period, color }) => ({
            name: `MA${period}`, type: 'line', showSymbol: false, connectNulls: false,
            data: [
                ...(segment.ma?.[`ma${period}`] || Array(segment.bars).fill(null)),
                ...(following?.ma?.[`ma${period}`] || Array(following?.bars || 0).fill(null)),
            ],
            lineStyle: { width: 1.7 }, itemStyle: { color },
        }))],
    };
};

export const buildOverlayOption = (target, match, maPeriods = []) => {
    const count = target.bars;
    const future = match.following?.normalized_close || [];
    const maLines = [...new Set(maPeriods)].flatMap(period => {
        const key = `ma${period}`;
        const targetValues = target.normalized_ma?.[key] || Array(count).fill(null);
        const matchValues = match.normalized_ma?.[key] || Array(count).fill(null);
        const followingValues = match.following?.normalized_ma?.[key] || Array(future.length).fill(null);
        return [
            { name: `基准 MA${period}`, type: 'line', showSymbol: false, connectNulls: false,
                data: [...targetValues, ...Array(future.length).fill(null)],
                lineStyle: { width: 1.7, type: 'solid' }, itemStyle: { color: maColors[period] } },
            { name: `历史 MA${period}`, type: 'line', showSymbol: false, connectNulls: false,
                data: [...matchValues, ...followingValues],
                lineStyle: { width: 1.7, type: 'dashed' }, itemStyle: { color: maColors[period] } },
        ];
    });
    return {
        animation: false,
        legend: { type: 'scroll', left: 10, right: 10, data: ['基准走势', '历史匹配', ...(future.length ? ['历史后续'] : []), ...maLines.map(line => line.name)] },
        tooltip: { trigger: 'axis', valueFormatter: value => typeof value === 'number' ? value.toFixed(3) : '-' },
        grid: { left: 65, right: 30, top: maLines.length ? 85 : 55, bottom: 45 },
        xAxis: { type: 'category', name: '第几根', nameLocation: 'middle', nameGap: 30, data: Array.from({ length: count + future.length }, (_, index) => index + 1) },
        yAxis: { type: 'value', name: '标准化价格', scale: true },
        series: [
            { name: '基准走势', type: 'line', showSymbol: false, data: [...target.normalized_close, ...Array(future.length).fill(null)], lineStyle: { width: 2.5 }, itemStyle: { color: '#1677ff' } },
            { name: '历史匹配', type: 'line', showSymbol: false, data: [...match.normalized_close, ...Array(future.length).fill(null)], lineStyle: { width: 2.5 }, itemStyle: { color: '#722ed1' } },
            ...(future.length ? [{
                name: '历史后续', type: 'line', showSymbol: false,
                data: [...Array(count - 1).fill(null), match.normalized_close[count - 1], ...future],
                lineStyle: { type: 'dashed', width: 2 }, itemStyle: { color: '#fa8c16' },
                markLine: { symbol: 'none', label: { formatter: '匹配结束' }, data: [{ xAxis: count - 1 }] },
            }] : []),
            ...maLines,
        ],
    };
};
