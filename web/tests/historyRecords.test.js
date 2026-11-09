import test from 'node:test';
import assert from 'node:assert/strict';
import { loadHistoryRecords } from '../src/utils/historyRecords.js';

test('history collects every summary page for global filtering and rankings', async () => {
  const cursors = [];
  const rows = await loadHistoryRecords(async (path, {params}) => {
    assert.equal(path, '/api/backtest/history');
    cursors.push(params.cursor);
    return {data: params.cursor === undefined ? {items: [{id: 3},{id: 2}], has_more: true, next_cursor: 2}
      : {items: [{id: 1}], has_more: false, next_cursor: null}};
  });
  assert.deepEqual(rows.map(row => row.id), [3,2,1]);
  assert.deepEqual(cursors, [undefined,2]);
});

test('history rejects broken cursors and stops on cancellation', async () => {
  await assert.rejects(loadHistoryRecords(async () => ({data: {items: [], has_more: true, next_cursor: null}})));
  const controller = new AbortController(); let calls = 0;
  await assert.rejects(loadHistoryRecords(async () => {
    calls++; controller.abort();
    return {data: {items: [{id: 2}], has_more: true, next_cursor: 2}};
  }, controller.signal));
  assert.equal(calls, 1);
});
