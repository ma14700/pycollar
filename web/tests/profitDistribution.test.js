import assert from 'node:assert/strict';
import test from 'node:test';
import * as echarts from 'echarts';
import { getProfitDistributionOption } from '../src/utils/profitDistribution.js';

const values = (metrics) => getProfitDistributionOption(metrics).series[0].data.map(item => item.value);

test('uses closed trade counts even when total includes an open trade', () => {
    assert.deepEqual(values({ won_trades: 7, lost_trades: 12, total_trades: 20, win_rate: 35 }), [7, 12]);
});

test('supports all winning or all losing trades', () => {
    assert.deepEqual(values({ won_trades: 5, lost_trades: 0 }), [5, 0]);
    assert.deepEqual(values({ won_trades: 0, lost_trades: 5 }), [0, 5]);
});

test('flat closed trades are a separate sector, including all flat outcomes', () => {
    assert.deepEqual(values({ won_trades: 2, lost_trades: 1, flat_trades: 3 }), [2, 1, 3]);
    assert.deepEqual(values({ won_trades: 0, lost_trades: 0, flat_trades: 2 }), [0, 0, 2]);
    assert.match(getProfitDistributionOption({ won_trades: 0, lost_trades: 0, flat_trades: 2 }).series[0].data[2].name, /持平/);
});

test('legacy percentage is on a 0 to 100 scale', () => {
    assert.deepEqual(values({ total_trades: 19, win_rate: 36.84 }), [36.84, 63.16]);
    assert.deepEqual(values({ total_trades: 5, win_rate: 0 }), [0, 100]);
    assert.deepEqual(values({ total_trades: 5, win_rate: 100 }), [100, 0]);
});

test('accepts numeric strings in saved records', () => {
    assert.deepEqual(values({ won_trades: '7', lost_trades: '12' }), [7, 12]);
    assert.deepEqual(values({ total_trades: '10', win_rate: '60' }), [60, 40]);
});

test('shows empty state for no closed trades or unavailable metrics', () => {
    for (const metrics of [undefined, null, {}, { total_trades: 0, win_rate: 0 },
        { won_trades: 0, lost_trades: 0, total_trades: 1 },
        { total_trades: 5, win_rate: null }, { total_trades: 5, win_rate: NaN }]) {
        const option = getProfitDistributionOption(metrics);
        assert.deepEqual(option.series, []);
        assert.match(option.title.text, /暂无已平仓交易/);
    }
});

test('does not create negative sectors from an invalid legacy percentage', () => {
    assert.deepEqual(values({ total_trades: 10, win_rate: 120 }), [100, 0]);
});

test('ECharts renders mixed, one-sided, legacy and empty distributions', () => {
    for (const metrics of [
        { won_trades: 7, lost_trades: 12 },
        { won_trades: 5, lost_trades: 0 },
        { won_trades: 0, lost_trades: 5 },
        { total_trades: 19, win_rate: 36.84 },
        { total_trades: 0, win_rate: 0 },
    ]) {
        const chart = echarts.init(null, null, { renderer: 'svg', ssr: true, width: 900, height: 600 });
        try {
            chart.setOption(getProfitDistributionOption(metrics));
            const svg = chart.renderToSVGString();
            assert.doesNotMatch(svg, /NaN|Infinity/);
            assert.match(svg, metrics.total_trades === 0 ? /暂无已平仓交易/ : /盈利交易/);
            if (metrics.total_trades !== 0) assert.match(svg, /亏损交易/);
        } finally {
            chart.dispose();
        }
    }
});
