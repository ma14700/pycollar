import assert from 'node:assert/strict';
import test from 'node:test';
import * as echarts from 'echarts';
import { buildCandleOption, buildOverlayOption } from '../src/utils/candleCompareCharts.js';

const target = { bars: 3, dates: ['a', 'b', 'c'], ohlc: [[10, 11, 9, 12], [11, 12, 10, 13], [12, 13, 11, 14]], normalized_close: [-1, 0, 1] };
const following = { bars: 2, dates: ['d', 'e'], ohlc: [[13, 14, 12, 15], [14, 15, 13, 16]], normalized_close: [2, 3] };

test('overlay keeps future out of target and historical matching lines', () => {
    const option = buildOverlayOption(target, { ...target, following });
    assert.deepEqual(option.series[0].data, [-1, 0, 1, null, null]);
    assert.deepEqual(option.series[1].data, [-1, 0, 1, null, null]);
    assert.deepEqual(option.series[2].data, [null, null, 1, 2, 3]);
    assert.equal(option.xAxis.data.length, 5);
});

test('candles keep OHLC order and separate continuation boundary', () => {
    const option = buildCandleOption(target, following);
    assert.deepEqual(option.series[0].data[0], [10, 11, 9, 12]);
    assert.equal(option.series[0].data.length, 5);
    assert.equal(option.series[0].markLine.data[0].xAxis, 2);
});

test('zero-continuation overlay has no future line', () => {
    const option = buildOverlayOption(target, { ...target, following: { bars: 0, normalized_close: [] } });
    assert.equal(option.series.length, 2);
    assert.equal(option.xAxis.data.length, 3);
});

test('MA20, MA55 and MA144 continue across the matching boundary', () => {
    const pattern = { ...target, ma: { ma20: [101, 102, 103], ma55: [null, 90, 91], ma144: [null, null, null] } };
    const next = { ...following, ma: { ma20: [104, 105], ma55: [92, 93], ma144: [null, 80] } };
    const option = buildCandleOption(pattern, next);
    assert.deepEqual(option.legend.data, ['K线', 'MA20', 'MA55', 'MA144']);
    assert.deepEqual(option.series[1].data, [101, 102, 103, 104, 105]);
    assert.deepEqual(option.series[2].data, [null, 90, 91, 92, 93]);
    assert.deepEqual(option.series[3].data, [null, null, null, null, 80]);
    assert.equal(option.series[3].connectNulls, false);
});

test('missing historical averages stay blank instead of being recomputed on the fragment', () => {
    const option = buildCandleOption(target, following);
    for (const line of option.series.slice(1)) assert.deepEqual(line.data, [null, null, null, null, null]);
});

test('ECharts renders overlay and candlestick options', () => {
    for (const option of [buildOverlayOption(target, { ...target, following }), buildCandleOption(target, following)]) {
        const chart = echarts.init(null, null, { renderer: 'svg', ssr: true, width: 900, height: 360 });
        try {
            chart.setOption(option);
            assert.doesNotMatch(chart.renderToSVGString(), /NaN|Infinity/);
        } finally { chart.dispose(); }
    }
});

test('single and multiple selected averages appear on both comparison charts', () => {
    for (const periods of [[20], [60], [144], [20, 60, 144]]) {
        const pattern = { ...target, normalized_ma: { ma20: [1, 2, 3], ma60: [4, 5, 6], ma144: [7, 8, 9] },
            ma: { ma20: [11, 12, 13], ma60: [14, 15, 16], ma144: [17, 18, 19] } };
        const next = { ...following, normalized_ma: { ma60: [10, 11] } };
        const candles = buildCandleOption(pattern, next, periods);
        assert.deepEqual(candles.legend.data, ['K线', ...periods.map(period => `MA${period}`)]);
        const overlay = buildOverlayOption(pattern, { ...pattern, following: next }, periods);
        for (const period of periods) {
            const reference = overlay.series.find(line => line.name === `基准 MA${period}`);
            const history = overlay.series.find(line => line.name === `历史 MA${period}`);
            assert.deepEqual(reference.data, [...pattern.normalized_ma[`ma${period}`], null, null]);
            assert.deepEqual(history.data.slice(0, 3), pattern.normalized_ma[`ma${period}`]);
            assert.equal(history.lineStyle.type, 'dashed');
        }
        if (periods.includes(60)) assert.deepEqual(overlay.series.find(line => line.name === '历史 MA60').data, [4, 5, 6, 10, 11]);
        const chart = echarts.init(null, null, { renderer: 'svg', ssr: true, width: 900, height: 360 });
        try {
            chart.setOption(overlay);
            assert.doesNotMatch(chart.renderToSVGString(), /NaN|Infinity/);
        } finally { chart.dispose(); }
    }
});
