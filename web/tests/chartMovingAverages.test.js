import assert from 'node:assert/strict';
import test from 'node:test';
import * as echarts from 'echarts';
import { buildMovingAverageSeries } from '../src/utils/chartMovingAverages.js';

test('shared charts show 144 alongside existing 20 and 55', () => {
    const series = buildMovingAverageSeries({ ma: { ma20: [101], ma55: [100], ma144: [90] } });
    assert.deepEqual(series.map(line => line.name), ['MA20', 'MA55', 'MA144']);
    assert.deepEqual(series[2].data, [90]);
});

test('custom strategy lines retain their periods and do not duplicate MA144', () => {
    const series = buildMovingAverageSeries({ ma: { strategy_fast: [101], strategy_fast_label: 'EMA20',
        strategy_slow: [99], strategy_slow_label: 'MA144', ma144: [90] } });
    assert.deepEqual(series.map(line => line.name), ['EMA20', 'MA144']);
    assert.deepEqual(series[1].data, [90]);
});

test('old results compute 144 only when a full window is available', () => {
    const values = Array.from({ length: 145 }, (_, index) => [1, index + 1, 0, 200]);
    const series = buildMovingAverageSeries({ values });
    assert.deepEqual(series[0].data.slice(0, 143), Array(143).fill(null));
    assert.deepEqual(series[0].data.slice(143), [72.5, 73.5]);
    assert.equal(series[0].connectNulls, false);
});

test('20/144 entry strategy retains its distinct 55 exit line with one reference 144', () => {
    const series = buildMovingAverageSeries({ ma: {
        strategy_fast: [101], strategy_fast_label: 'MA20',
        strategy_slow: [90], strategy_slow_label: 'MA144',
        strategy_exit: [99], strategy_exit_label: 'MA55',
        ma55: [98], ma144: [90],
    } });
    assert.deepEqual(series.map(line => line.name), ['MA20', 'MA55', 'MA144']);
    assert.deepEqual(series.find(line => line.name === 'MA55').data, [99]);
});

test('invalid closes leave gaps instead of treating them as zero', () => {
    const values = Array.from({ length: 144 }, () => [100, 100, 99, 101]);
    values[70][1] = null;
    assert.equal(buildMovingAverageSeries({ values })[0].data[143], null);
});

test('ECharts renders a warmup gap and MA144 line', () => {
    const chart = echarts.init(null, null, { renderer: 'svg', ssr: true, width: 900, height: 360 });
    try {
        const series = buildMovingAverageSeries({ ma: { ma20: [1, 2, 3], ma55: [2, 3, 4], ma144: [null, 1, 2] } });
        chart.setOption({ xAxis: { type: 'category', data: ['a', 'b', 'c'] }, yAxis: {}, series });
        assert.doesNotMatch(chart.renderToSVGString(), /NaN|Infinity/);
    } finally { chart.dispose(); }
});
