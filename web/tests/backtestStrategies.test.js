import test from 'node:test';
import assert from 'node:assert/strict';
import { defaultStrategyParameters, buildStrategyParameters, pickStrategyParameters, strategyOptions } from '../src/utils/backtestStrategies.js';
import { createBacktestTask } from '../src/utils/backtestTask.js';
import { buildBacktestSaveRequests } from '../src/utils/backtestSave.js';

test('strategy defaults keep distinct MA periods, direction parameters and exits', () => {
    const common = { fixed_size: 3, margin_rate: .12, entry_delay_bars: 2, exit_delay_bars: 3 };
    for (const [name,fast,slow,exit] of [
        ['MA5MA55CrossoverStrategy',5,55], ['MA20MA60CrossoverStrategy',20,60],
        ['MA20MA144LongOnlyStrategy',20,144,55], ['MA20MA144CrossExitLongShortStrategy',20,144,144],
    ]) {
        const params = buildStrategyParameters(name,{...common,...defaultStrategyParameters(name)});
        assert.equal(params.fast_period,fast);assert.equal(params.slow_period,slow);
        if (exit) assert.equal(params.exit_period,exit);
        assert.equal(params.fixed_size,3);assert.equal(params.margin_rate,.12);
        assert.equal(params.entry_delay_bars,2);assert.equal(params.exit_delay_bars,3);
    }
    for (const option of strategyOptions) assert(Object.keys(buildStrategyParameters(option.value, {...common,...defaultStrategyParameters(option.value)})).length > 3, option.value);
});

test('per-strategy drafts preserve explicit booleans and ignore common dates and lot size', () => {
    assert.deepEqual(pickStrategyParameters({ fast_period:5,allow_reverse:false,fixed_size:3,margin_rate:.12,symbol:['JM0'],period:'daily' }), {fast_period:5,allow_reverse:false});
    const draft={...defaultStrategyParameters('MA5MA55CrossoverStrategy'),fast_period:7,slow_period:80,allow_reverse:false};
    const params=buildStrategyParameters('MA5MA55CrossoverStrategy',{...draft,fixed_size:2,entry_delay_bars:1,exit_delay_bars:1});
    assert.equal(params.fast_period,7);assert.equal(params.slow_period,80);assert.equal(params.allow_reverse,false);
    assert.equal(defaultStrategyParameters('MA20MA144LongOnlyStrategy').fast_period,20);
});

test('same-symbol different-strategy queue preserves identities, failures and save payloads', async () => {
    const names=['MA20MA144LongOnlyStrategy','MA20MA144ShortOnlyStrategy'];
    const tasks=['JM2701','JM2605'].flatMap(symbol=>names.map(strategy_name=>({payload:{symbol,strategy_name,
        strategy_params:{fixed_size:2,entry_delay_bars:1},period:'daily'}})));
    const calls=[];
    const queue=createBacktestTask(async payload=>{
        calls.push(payload);
        if (payload.symbol==='JM2701' && payload.strategy_name===names[1]) throw Error('failed');
        return {metrics:{net_profit:10,initial_cash:1000,final_value:1010}};
    });
    await queue.start({tasks});
    const {results}=queue.getSnapshot();
    assert.equal(calls.length,4);assert.equal(results.summary.success,3);
    assert.equal(results.items[1].strategy_name,names[1]);
    const saves=buildBacktestSaveRequests(results);
    assert.deepEqual(saves.map(p=>[p.symbol,p.strategy_name]),[['JM2701',names[0]],['JM2605',names[0]],['JM2605',names[1]]]);
});
