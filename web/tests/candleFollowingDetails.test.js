import assert from 'node:assert/strict';
import test from 'node:test';
import { buildFollowingDetails } from '../src/utils/candleFollowingDetails.js';

const sample = () => ({
    ohlc: [[98, 100, 97, 101]],
    following: { dates: ['2026-01-02', '2026-01-03', '2026-01-04'],
        ohlc: [[107, 103, 102, 108], [104, 99, 98, 105], [99, 99, 98, 100]] },
});

test('first following change uses match closing price, independently of candle body', () => {
    const [first] = buildFollowingDetails(sample());
    assert.equal(first.previous_close, 100);
    assert.equal(first.close, 103);
    assert.equal(first.body_change, -4);
    assert.equal(first.change, 3);
    assert.equal(first.change_pct, 3);
    assert.equal(first.cumulative_change, 3);
    assert.equal(first.sequence, 1);
});

test('each later bar compares with previous close, cumulative change stays anchored', () => {
    const rows = buildFollowingDetails(sample());
    assert.equal(rows[1].previous_close, 103);
    assert.equal(rows[1].change, -4);
    assert.equal(rows[1].change_pct, -3.8834951456);
    assert.equal(rows[1].cumulative_change, -1);
    assert.equal(rows[1].cumulative_pct, -1);
    assert.equal(rows[2].change, 0);
    assert.equal(rows[2].change_pct, 0);
    assert.equal(rows[2].cumulative_pct, -1);
});

test('no follow-up bars returns an empty list', () => {
    assert.deepEqual(buildFollowingDetails(null), []);
    assert.deepEqual(buildFollowingDetails({ ohlc: [[1, 2, 1, 2]], following: { dates: [], ohlc: [] } }), []);
});

test('missing close stays missing and does not silently compare across a gap', () => {
    const match = sample();
    match.following.ohlc[0][1] = null;
    const rows = buildFollowingDetails(match);
    assert.equal(rows[0].change, null);
    assert.equal(rows[1].previous_close, null);
    assert.equal(rows[1].change, null);
    assert.equal(rows[1].cumulative_pct, -1);
    assert.equal(rows[2].change, 0);
});

test('missing anchor disables cumulative change instead of inventing zero', () => {
    const match = sample();
    match.ohlc[0][1] = NaN;
    const rows = buildFollowingDetails(match);
    assert.equal(rows[0].change_pct, null);
    assert.equal(rows[0].cumulative_pct, null);
    assert.equal(rows[1].change, -4);
    assert.equal(rows[1].cumulative_pct, null);
});

test('decimal prices do not produce floating-point tails or negative zero', () => {
    const match = { ohlc: [[0.1, 0.2, 0.1, 0.2]], following: { dates: ['a'], ohlc: [[0.2, 0.3, 0.2, 0.3]] } };
    const [row] = buildFollowingDetails(match);
    assert.equal(row.change, 0.1);
    assert.equal(row.change_pct, 50);
    assert.equal(row.cumulative_change, 0.1);
    const nearFlat = { ohlc: [[1000, 1000.00000000001, 1000, 1001]], following: { dates: ['a'], ohlc: [[1000, 1000, 999, 1001]] } };
    const [flat] = buildFollowingDetails(nearFlat);
    assert.equal(Object.is(flat.change, -0), false);
    assert.equal(flat.change, 0);
});
