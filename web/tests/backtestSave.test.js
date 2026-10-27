import test from 'node:test';
import assert from 'node:assert/strict';
import { buildBacktestSaveRequests } from '../src/utils/backtestSave.js';

test('single selection from the multi-select form saves as a symbol string', () => {
  const [payload] = buildBacktestSaveRequests({ metrics: { net_profit: 12, win_rate: '50%' } },
    { symbol: ['RB0'], period: 'daily', strategy_name: 'MA55BreakoutStrategy' });
  assert.equal(payload.symbol, 'RB0');
  assert.equal(payload.net_profit, 12);
  assert.equal(payload.win_rate, 50);
});

test('batch saves successful symbols with their own metrics and original parameters', () => {
  const data = (profit, multiplier) => ({ metrics: { net_profit: profit }, backtest_request: {
    period: 'weekly', strategy_name: 'MA20MA60CrossoverStrategy', strategy_params: { contract_multiplier: multiplier },
  } });
  const requests = buildBacktestSaveRequests({ isBatch: true, items: [
    { symbol: 'RB0', success: true, data: data(10, 10) },
    { symbol: 'AG0', success: false, error: 'offline' },
    { symbol: 'SC0', success: true, data: data(-20, 1000) },
  ] }, { symbol: ['changed'], period: 'daily', strategy_name: 'changed' });
  assert.deepEqual(requests.map(r => r.symbol), ['RB0', 'SC0']);
  assert.deepEqual(requests.map(r => r.net_profit), [10, -20]);
  assert.deepEqual(requests.map(r => r.strategy_params.contract_multiplier), [10, 1000]);
  assert.ok(requests.every(r => r.period === 'weekly' && r.strategy_name === 'MA20MA60CrossoverStrategy'));
});

test('all failed batch produces no invalid save requests', () => {
  assert.deepEqual(buildBacktestSaveRequests({ isBatch: true, items: [{ success: false }] }), []);
});
