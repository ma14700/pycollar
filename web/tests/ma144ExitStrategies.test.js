import test from 'node:test';
import assert from 'node:assert/strict';
import { ma144ExitStrategyOptions, getMA144ExitStrategy } from '../src/utils/ma144ExitStrategies.js';
import { tomorrowStrategyOptions, buildTomorrowAnalysisRequest } from '../src/utils/tomorrowStrategy.js';
import { buildMovingAverageSeries } from '../src/utils/chartMovingAverages.js';
import { strategyNameMap } from '../src/constants/index.js';

test('three distinct 20/144 exit choices keep the same defaults in analysis and history labels', () => {
    assert.equal(ma144ExitStrategyOptions.length, 3);
    assert.equal(new Set(ma144ExitStrategyOptions.map(option => option.value)).size, 3);
    for (const option of ma144ExitStrategyOptions) {
        assert.deepEqual(option.defaults, { fast_period: 20, slow_period: 144, exit_period: 144 });
        assert.equal(getMA144ExitStrategy(option.value), option);
        assert.equal(strategyNameMap[option.value], option.label);
        assert.equal(tomorrowStrategyOptions.find(item => item.value === option.value), option);
        const request = buildTomorrowAnalysisRequest({ symbols: ['JM0'], market_type: 'futures', period: 'daily',
            strategy_name: option.value, ...option.defaults });
        assert.equal(request.strategy_name, option.value);
        assert.equal(request.strategy_params.exit_period, 144);
    }
    assert.equal(getMA144ExitStrategy('MA20MA144LongShortStrategy'), undefined);
    assert.ok(strategyNameMap.MA20MA144LongShortStrategy.includes('20/55'));
    assert.equal(getMA144ExitStrategy('MA20MA144CrossExitLongShortStrategy').reverses, true);
    assert.ok(strategyNameMap.MA20MA144CrossExitLongShortStrategy.includes('反手'));
    assert.ok(ma144ExitStrategyOptions.filter(option => option.value !== 'MA20MA144CrossExitLongShortStrategy').every(option => !option.reverses));
});

test('shared entry and exit MA144 appear once on the executed strategy chart', () => {
    const ma = { strategy_fast_label: 'MA20', strategy_fast: [100],
        strategy_slow_label: 'MA144', strategy_slow: [99],
        strategy_exit_label: 'MA144', strategy_exit: [99], ma144: [99], ma55: [101] };
    const lines = buildMovingAverageSeries({ ma });
    assert.deepEqual(lines.map(line => line.name), ['MA20', 'MA144']);
    assert.deepEqual(lines[1].data, [99]);
});
