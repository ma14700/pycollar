import assert from 'node:assert/strict';
import test from 'node:test';
import { analysisSymbols, buildContractComparisons } from '../src/utils/contractAnalysis.js';
import { buildTomorrowAnalysisRequest, getTomorrowDetailRequest } from '../src/utils/tomorrowStrategy.js';

test('tomorrow expands each selected contract, forces actual source, and excludes delivery cutoff dates', () => {
    const request = buildTomorrowAnalysisRequest({ symbols: ['JM0'], contract_month: ['2701', '2605', '2701'],
        market_type: 'futures', period: '60', data_provider: 'akshare', data_source: 'weighted',
        strategy_name: 'MA20MA144LongShortStrategy', fixed_size: 2 });
    assert.deepEqual(request.symbols, ['JM2701', 'JM2605']);
    assert.equal(request.data_provider, 'tqsdk');
    assert.equal(request.data_source, 'main');
    assert.deepEqual(request.strategy_params, { fixed_size: 2 });
    assert.equal(request.start_date, undefined);
    assert.equal(request.end_date, undefined);
    const detail = getTomorrowDetailRequest({ analysis_request: { ...request, symbol: 'JM2605' } });
    assert.equal(detail.symbol, 'JM2605');
});

test('comparison requests isolate contracts and retain requested comparison periods and dates', () => {
    const payload = { symbol: 'SA0', period: '5', data_provider: 'akshare', data_source: 'weighted',
        target_end: '2026-10-20', search_start: '2026-01-01', ma_periods: [20,144], window_size: 50 };
    const requests = buildContractComparisons(payload, ['2701','2605']);
    assert.deepEqual(requests.map(item => item.symbol), ['SA2701','SA2605']);
    for (const request of requests) {
        assert.equal(request.data_provider, 'tqsdk'); assert.equal(request.data_source, 'main');
        assert.equal(request.target_end, payload.target_end); assert.equal(request.search_start, payload.search_start);
        assert.deepEqual(request.ma_periods, [20,144]); assert.equal(request.period, '5');
    }
    assert.equal(payload.symbol,'SA0');
    assert.deepEqual(buildContractComparisons(payload, []), [payload]);
});

test('cleared selection retains products and multiple products or stocks cannot reuse selected contract months', () => {
    assert.deepEqual(analysisSymbols(['JM0','SA0'], []), ['JM0','SA0']);
    assert.throws(() => analysisSymbols(['JM0','SA0'], ['2701']), /一个交易品种/);
    assert.throws(() => analysisSymbols(['sh600000'], ['2701'], 'stock'), /仅适用于期货/);
    assert.throws(() => analysisSymbols(['JM0'], ['2713']), /月份/);
    assert.deepEqual(analysisSymbols(['sh600000'], [], 'stock'), ['sh600000']);
});
