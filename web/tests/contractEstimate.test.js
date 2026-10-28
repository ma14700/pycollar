import assert from 'node:assert/strict';
import test from 'node:test';
import { contractEstimate, accountReturn } from '../src/utils/contractEstimate.js';

test('reference price and notional do not rise with margin rate', () => {
    const input = { price: 3500, multiplier: 10, initialCash: 1000000, marginRate: .12 };
    const estimate = contractEstimate(input);
    assert.equal(estimate.price, 3500);
    assert.equal(estimate.notional, 35000);
    assert.equal(estimate.collateral, 4200);
    assert.equal(estimate.maxHands, 237);
    const higherMargin = contractEstimate({ ...input, marginRate: .2 });
    assert.equal(higherMargin.price, 3500);
    assert.equal(higherMargin.notional, 35000);
    assert.equal(higherMargin.collateral, 7000);
});

test('reference capacity allows for opening fees and stock purchases require full funds', () => {
    assert.equal(contractEstimate({ price: 100, multiplier: 10, initialCash: 200, marginRate: .1 }).maxHands, 1);
    const stock = contractEstimate({ price: 100, multiplier: 100, initialCash: 20000, marginRate: .12, marketType: 'stock' });
    assert.equal(stock.marginRate, 1);
    assert.equal(stock.collateral, 10000);
    assert.equal(stock.maxHands, 1);
});

test('unknown or invalid quote, collateral and capital values do not fabricate a usable estimate', () => {
    const valid = { price: 100, multiplier: 10, initialCash: 10000, marginRate: .12 };
    for (const update of [{ price: null }, { price: 0 }, { price: Infinity }, { multiplier: 0 }, { marginRate: 0 }, { marginRate: 2 }, { initialCash: '' }]) {
        assert.equal(contractEstimate({ ...valid, ...update }), null);
    }
    assert.equal(contractEstimate({ ...valid, initialCash: 0 }).maxHands, 0);
});

test('account return uses net profit and initial funds, never a single-hand return', () => {
    assert.equal(accountReturn({ net_profit: 200, initial_cash: 10000, one_hand_profit_pct: 99 }), 2);
    assert.equal(accountReturn({ net_profit: -200, initial_cash: 10000 }), -2);
    assert.equal(accountReturn({ net_profit: 0, initial_cash: 10000 }), 0);
    assert.equal(accountReturn({ return_rate: '2.5' }), 2.5);
    assert.equal(accountReturn({ initial_cash: 0 }), null);
});
