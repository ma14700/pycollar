import test from 'node:test';
import assert from 'node:assert/strict';
import { buildTomorrowAnalysisRequest, getTomorrowDetailRequest, buildTomorrowDetailChart } from '../src/utils/tomorrowStrategy.js';
import { buildMovingAverageSeries } from '../src/utils/chartMovingAverages.js';

test('analysis strips blank parameters and retains explicit false and zero', () => {
    const request = buildTomorrowAnalysisRequest({ symbols: ['JM0'], market_type: 'futures', period: '60', strategy_name: 'TrendFollowingStrategy', fast_period: '', slow_period: undefined, use_expma: false, commission: 0 });
    assert.deepEqual(request.strategy_params, { use_expma: false, commission: 0 });
    assert.equal(request.data_provider, 'tqsdk');
});

test('detail uses the analyzed snapshot after form parameters change', () => {
    const values = { symbols: ['JM0'], market_type: 'futures', period: '60', strategy_name: 'DualMAFixedTPSLStrategy', sl_value: 15 };
    const payload = buildTomorrowAnalysisRequest(values);
    const record = { analysis_request: { ...payload, symbol: 'JM0', as_of: '2026-10-27 14:00:00' } };
    values.strategy_name = 'DKXStrategy';
    values.sl_value = 50;
    const detail = getTomorrowDetailRequest(record);
    assert.equal(detail.strategy_name, 'DualMAFixedTPSLStrategy');
    assert.equal(detail.strategy_params.sl_value, 15);
    assert.equal(detail.period, '60');
    assert.equal(detail.as_of, '2026-10-27 14:00:00');
    detail.strategy_params.sl_value = 200;
    assert.equal(record.analysis_request.strategy_params.sl_value, 15);
});

test('chart keeps executions and labels actual position without mistaking additions for entries', () => {
    const data = { position_state: { size: 4 }, kline_data: { dates: ['first', 'last'], values: [[100, 110, 95, 115], [110, 120, 105, 125]] }, trades: [
        { date: 'first', action: '买多', opens_position: true, position: 2 },
        { date: 'last', action: '买多', opens_position: false, position: 4 },
    ] };
    const chart = buildTomorrowDetailChart(data);
    assert.equal(chart.signals[0], data.trades[0]);
    assert.equal(chart.signals[1].custom_label, '多 4手');
    assert.equal(chart.signals[1].price, 120);
    assert.equal(chart.trades.length, 2);
    assert.equal(data.signals, undefined);
});

test('flat position has a neutral marker and old rows require new analysis', () => {
    const chart = buildTomorrowDetailChart({ position_state: { size: 0 }, kline_data: { dates: ['last'], values: [[1, 2, 0, 3]] }, trades: [] });
    assert.equal(chart.signals[0].custom_label, '空仓');
    assert.equal(chart.signals[0].itemStyle.color, '#999');
    assert.throws(() => getTomorrowDetailRequest({}), /重新分析/);
});

test('single MA55 strategy does not create duplicate MA55 reference lines', () => {
    const series = buildMovingAverageSeries({ ma: { strategy_fast: [null, 100], strategy_fast_label: 'MA55', ma55: [99, 100] } });
    assert.equal(series.filter(line => line.name === 'MA55').length, 1);
    assert.deepEqual(series.find(line => line.name === 'MA55').data, [null, 100]);
});
