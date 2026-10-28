import test from 'node:test';
import assert from 'node:assert/strict';
import { contractWindow, applyContractBacktest, normalizeContractMonths, buildBacktestTargets } from '../src/utils/contractBacktest.js';
import { buildBacktestSaveRequests } from '../src/utils/backtestSave.js';

test('2605 and 2701 use the five pre-delivery months through the 23rd', () => {
    assert.deepEqual(contractWindow('2605'), { contract_month: '2605', start_date: '2025-12-01', end_date: '2026-04-23' });
    assert.deepEqual(contractWindow('2701'), { contract_month: '2701', start_date: '2026-08-01', end_date: '2026-12-23' });
    assert.deepEqual(contractWindow('2403'), { contract_month: '2403', start_date: '2023-10-01', end_date: '2024-02-23' });
});

test('contract mode overrides manual dates and requests the actual contract', () => {
    const original = { symbol: 'JM0', market_type: 'futures', period: '60', data_source: 'weighted', data_provider: 'akshare',
        start_date: '2020-01-01', end_date: '2030-01-01', strategy_params: { fixed_size: 2 } };
    const payload = applyContractBacktest(original, '2605');
    assert.equal(payload.symbol, 'JM2605');
    assert.equal(payload.data_provider, 'tqsdk');
    assert.equal(payload.data_source, 'main');
    assert.equal(payload.start_date, '2025-12-01');
    assert.equal(payload.end_date, '2026-04-23');
    assert.equal(payload.period, '60');
    assert.equal(payload.strategy_params.fixed_size, 2);
    assert.equal(original.symbol, 'JM0');
});

test('cleared contract leaves ordinary stock and futures requests unchanged', () => {
    for (const request of [{ symbol: 'JM0', market_type: 'futures' }, { symbol: 'sh600000', market_type: 'stock' }]) {
        assert.deepEqual(applyContractBacktest(request, undefined), request);
    }
    assert.throws(() => applyContractBacktest({ symbol: 'sh600000', market_type: 'stock' }, '2605'));
    assert.throws(() => applyContractBacktest({ symbol: 'JM2701', market_type: 'futures' }, '2605'));
    for (const month of ['605', '2600', '2613', '202605', '', null]) assert.throws(() => contractWindow(month));
});

test('saved results keep the selected contract and its locked dates after form changes', () => {
    const request = applyContractBacktest({ symbol: 'JM0', market_type: 'futures', period: 'daily', strategy_name: 'TrendFollowingStrategy' }, '2605');
    const result = { data_info: { symbol: 'JM2605', period: 'daily' }, metrics: { initial_cash: 10000 }, backtest_request: request };
    const [saved] = buildBacktestSaveRequests(result, { symbol: ['RB0'], period: '60' });
    assert.equal(saved.symbol, 'JM2605');
    assert.equal(saved.detail_data.backtest_request.contract_month, '2605');
    assert.equal(saved.detail_data.backtest_request.start_date, '2025-12-01');
});

test('multiple contracts become separate targets with independent locked windows', () => {
    const targets = buildBacktestTargets(['JM0'], ['2605', '2701']);
    assert.equal(targets.length, 2);
    assert.deepEqual(targets.map(item => item.symbol), ['JM2605', 'JM2701']);
    assert.deepEqual(targets.map(item => [item.start_date, item.end_date]), [
        ['2025-12-01', '2026-04-23'], ['2026-08-01', '2026-12-23'],
    ]);
    assert(targets.every(item => item.base_symbol === 'JM0' && item.data_provider === 'tqsdk'));
});

test('single saved selection migrates to multi-select, duplicates are not rerun, clearing restores ordinary mode', () => {
    assert.deepEqual(normalizeContractMonths('2605'), ['2605']);
    assert.deepEqual(normalizeContractMonths(undefined), []);
    assert.deepEqual(buildBacktestTargets(['JM0'], ['2605', '2605']).map(item => item.symbol), ['JM2605']);
    assert.deepEqual(buildBacktestTargets(['JM0', 'RB0'], []).map(item => item.symbol), ['JM0', 'RB0']);
    assert.throws(() => buildBacktestTargets(['JM0', 'RB0'], ['2605']), /一个交易品种/);
    assert.throws(() => buildBacktestTargets(['JM0'], ['2613']));
});

test('saving a contract batch keeps actual contract IDs, dates and metrics independently', () => {
    const targets = buildBacktestTargets(['JM0'], ['2605', '2701']);
    const items = targets.map((target, index) => {
        const request = applyContractBacktest({ symbol: target.base_symbol, market_type: 'futures',
            period: 'daily', strategy_name: 'MA20MA55ShortOnlyStrategy' }, target.contract_month);
        return { symbol: request.symbol, success: true, data: { metrics: { net_profit: 100 + index }, backtest_request: request } };
    });
    items.push({ symbol: 'JM2609', success: false, error: 'offline' });
    const requests = buildBacktestSaveRequests({ isBatch: true, items }, { symbol: ['RB0'] });
    assert.deepEqual(requests.map(item => item.symbol), ['JM2605', 'JM2701']);
    assert.deepEqual(requests.map(item => item.net_profit), [100, 101]);
    assert.deepEqual(requests.map(item => item.detail_data.backtest_request.start_date), ['2025-12-01', '2026-08-01']);
    assert(requests.every(item => item.strategy_name === 'MA20MA55ShortOnlyStrategy'));
});
