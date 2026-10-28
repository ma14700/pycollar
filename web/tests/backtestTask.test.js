import test from 'node:test';
import assert from 'node:assert/strict';
import { createBacktestTask } from '../src/utils/backtestTask.js';
import { buildBacktestSaveRequests } from '../src/utils/backtestSave.js';

const deferred = () => {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
};
const task = symbol => ({ payload: { symbol, period: 'daily', data_provider: 'tqsdk',
    strategy_name: 'MA20MA144CrossExitLongShortStrategy', strategy_params: { fixed_size: 2 },
    start_date: '2025-12-01', end_date: '2026-04-23' }, symbolName: 'Example' });
const tick = () => new Promise(resolve => setImmediate(resolve));

test('single request survives route unsubscribe and is available when the route subscribes again', async () => {
    const response = deferred();
    let calls = 0, updates = 0;
    const store = createBacktestTask(() => { calls++; return response.promise; }, () => 1000);
    const leavePage = store.subscribe(() => updates++);
    const running = store.start({ tasks: [task('JM2605')], strategy: 'test', period: 'daily' });
    await tick();
    leavePage();
    const beforeLeaving = updates;
    response.resolve({ metrics: { net_profit: 12 }, trades: [{ action: 'reverse' }] });
    await running;
    assert.equal(updates, beforeLeaving);
    const returned = store.getSnapshot();
    const stop = store.subscribe(() => {});
    assert.equal(returned.loading, false);
    assert.equal(returned.activeRun.completed, 1);
    assert.equal(returned.activeRun.status, 'completed');
    assert.equal(returned.results.metrics.net_profit, 12);
    assert.deepEqual(returned.results.trades, [{ action: 'reverse' }]);
    assert.equal(returned.results.backtest_request.symbol, 'JM2605');
    assert.equal(calls, 1);
    stop();
});

test('returning during the request preserves start time and cannot start a duplicate run', async () => {
    const response = deferred();
    let calls = 0, clock = 1000;
    const store = createBacktestTask(() => { calls++; return response.promise; }, () => clock);
    const first = store.start({ tasks: [task('JM2605')] });
    await tick();
    clock = 4000;
    const backOnPage = store.subscribe(() => {});
    const duplicate = store.start({ tasks: [task('RB2605')] });
    assert.equal(first, duplicate);
    assert.equal(store.getSnapshot().loading, true);
    assert.equal(store.getSnapshot().activeRun.startedAt, 1000);
    assert.equal(store.getSnapshot().activeRun.symbol, 'JM2605');
    response.resolve({});
    await duplicate;
    assert.equal(calls, 1);
    assert.equal(store.getSnapshot().activeRun.finishedAt, 4000);
    backOnPage();
});

test('batch queue advances while away, continues failures and preserves every target request', async () => {
    const responses = [deferred(), deferred(), deferred()];
    const calls = [];
    const store = createBacktestTask(payload => {
        calls.push(payload.symbol);
        return responses[calls.length - 1].promise;
    });
    const leavePage = store.subscribe(() => {});
    const tasks = [task('JM2605'), task('JM2701'), task('JM2705')];
    const pending = store.start({ tasks, unit: '合约' });
    await tick();
    leavePage();
    responses[0].resolve({ metrics: { net_profit: 10 } });
    await tick();
    assert.deepEqual(calls, ['JM2605', 'JM2701']);
    assert.equal(store.getSnapshot().activeRun.completed, 1);
    assert.equal(store.getSnapshot().activeRun.symbol, 'JM2701');
    responses[1].reject({ response: { data: { detail: 'no history' } } });
    await tick();
    assert.deepEqual(calls, ['JM2605', 'JM2701', 'JM2705']);
    assert.equal(store.getSnapshot().activeRun.failed, 1);
    responses[2].resolve({ metrics: { net_profit: 20 } });
    await pending;
    const state = store.getSnapshot();
    assert.equal(state.loading, false);
    assert.equal(state.activeRun.completed, 3);
    assert.equal(state.activeRun.unit, '合约');
    assert.deepEqual(state.results.summary, { total: 3, success: 2, failed: 1 });
    assert.equal(state.results.items[1].error, 'no history');
    assert.deepEqual(state.results.items[2].data.backtest_request, tasks[2].payload);
    const saves = buildBacktestSaveRequests(state.results);
    assert.deepEqual(saves.map(item => item.symbol), ['JM2605', 'JM2705']);
    assert.equal(saves[0].strategy_params.fixed_size, 2);
});

test('later draft changes do not change queued requests or saved parameters', async () => {
    const responses = [deferred(), deferred()];
    const seen = [];
    const store = createBacktestTask(payload => { seen.push(payload); return responses[seen.length - 1].promise; });
    const tasks = [task('JM2605'), task('JM2701')];
    const pending = store.start({ tasks });
    tasks[0].payload.strategy_params.fixed_size = 99;
    tasks[1].payload.symbol = 'WRONG';
    tasks[1].payload.end_date = '2099-01-01';
    await tick();
    responses[0].resolve({});
    await tick();
    responses[1].resolve({});
    await pending;
    assert.equal(seen[0].strategy_params.fixed_size, 2);
    assert.equal(seen[1].symbol, 'JM2701');
    assert.equal(seen[1].end_date, '2026-04-23');
});

test('single failure remains visible on return and a later successful run clears it', async () => {
    let calls = 0;
    const store = createBacktestTask(async () => { if (++calls === 1) throw new Error('offline'); return { metrics: { net_profit: 3 } }; });
    await store.start({ tasks: [task('JM2605')] });
    const failed = store.getSnapshot();
    assert.equal(failed.loading, false);
    assert.equal(failed.activeRun.status, 'failed');
    assert.equal(failed.activeRun.failed, 1);
    assert.equal(failed.runError, 'offline');
    assert.equal(failed.results, null);
    await store.start({ tasks: [task('JM2701')] });
    const success = store.getSnapshot();
    assert.equal(success.runError, null);
    assert.equal(success.results.backtest_request.symbol, 'JM2701');
    assert.equal(success.activeRun.status, 'completed');
    assert.equal(failed.activeRun.status, 'failed'); // Prior snapshots remain stable.
});

test('all failed batch finishes with the failure details instead of getting stuck loading', async () => {
    const store = createBacktestTask(async () => { throw new Error('no data'); });
    await store.start({ tasks: [task('JM2605'), task('JM2701')] });
    const state = store.getSnapshot();
    assert.equal(state.loading, false);
    assert.equal(state.activeRun.status, 'failed');
    assert.deepEqual(state.results.summary, { total: 2, success: 0, failed: 2 });
    assert.ok(state.results.items.every(item => item.error === 'no data'));
    assert.equal(state.runError, null);
});

test('empty queue is rejected without erasing the previous result or becoming busy', async () => {
    const store = createBacktestTask(async () => ({ metrics: { net_profit: 5 } }));
    await store.start({ tasks: [task('JM2605')] });
    const before = store.getSnapshot();
    assert.throws(() => store.start({ tasks: [] }));
    assert.equal(store.getSnapshot(), before);
    assert.equal(store.getSnapshot().loading, false);
});
