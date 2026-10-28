// Old saved results may have prices but no MA144 field.
function legacyMA144(values) {
    const closes = values.map(bar => typeof bar?.[1] === 'number' && Number.isFinite(bar[1]) ? bar[1] : null);
    return closes.map((_, index) => {
        if (index < 143) return null;
        const window = closes.slice(index - 143, index + 1);
        if (window.includes(null)) return null;
        return Number((window.reduce((sum, value) => sum + value, 0) / 144).toFixed(2));
    });
}

export function buildMovingAverageSeries(kline = {}) {
    const ma = kline.ma || {};
    const lines = [
        [ma.strategy_fast_label || 'Fast MA', ma.strategy_fast, '#ff7f50', 1.5],
        [ma.strategy_slow_label || 'Slow MA', ma.strategy_slow, '#87cefa', 1.5],
    ].filter(([, values]) => Array.isArray(values));
    if (!ma.strategy_fast && ma.ma20) lines.push(['MA20', ma.ma20, '#ff7f50', 1]);
    if (!ma.strategy_slow && ma.ma55) lines.push(['MA55', ma.ma55, '#87cefa', 1]);
    // Keep the reference SMA144 independent of custom strategy periods.
    const reference = ['MA144', ma.ma144 || legacyMA144(kline.values || []), '#eb2f96', 1.5];
    const names = new Set();
    return [...lines.filter(([name]) => name !== 'MA144'), reference].filter(([name]) => {
        if (names.has(name)) return false;
        names.add(name);
        return true;
    }).map(([name, values, color, width]) => ({
        name,
        type: 'line',
        data: values,
        smooth: true,
        showSymbol: false,
        connectNulls: false,
        itemStyle: { color },
        lineStyle: { width, color },
    }));
}
