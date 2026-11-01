import test from 'node:test';
import assert from 'node:assert/strict';
import { defaultTradingSymbol, defaultAnalysisSymbols } from '../src/utils/tradingDefaults.js';

const list = codes => codes.map(code => ({ code }));
test('single-product pages prefer coking coal and preserve SH0/first-product fallbacks', () => {
    assert.equal(defaultTradingSymbol(list(['A0','SH0','JM0'])).code,'JM0');
    assert.equal(defaultTradingSymbol(list(['A0','SH0'])).code,'SH0');
    assert.equal(defaultTradingSymbol(list(['A0','B0'])).code,'A0');
    assert.equal(defaultTradingSymbol([]),undefined);
    assert.equal(defaultTradingSymbol(list(['sh600000','JM0']),'stock').code,'sh600000');
});
test('analysis pages prefer coking coal alone so specific contracts are immediately selectable', () => {
    assert.deepEqual(defaultAnalysisSymbols(list(['A0','SH0','JM0'])),['JM0']);
    assert.deepEqual(defaultAnalysisSymbols(list(['A0','SH0','JM0']),0),['JM0']);
    const products=list(['A0','B0','C0','D0','E0','F0']);
    assert.deepEqual(defaultAnalysisSymbols(products),['A0','B0','C0','D0','E0']);
    assert.deepEqual(defaultAnalysisSymbols(products,0),[]);
    assert.deepEqual(defaultAnalysisSymbols([]),[]);
});
