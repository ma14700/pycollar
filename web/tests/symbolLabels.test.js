import test from 'node:test';
import assert from 'node:assert/strict';
import { getSymbolLabel } from '../src/utils/index.js';

test('same product archives and search labels keep distinct delivery codes', () => {
    assert.equal(getSymbolLabel('JM2701'),'焦煤（JM2701）');
    assert.equal(getSymbolLabel('JM2605'),'焦煤（JM2605）');
    assert.notEqual(getSymbolLabel('JM2701'),getSymbolLabel('JM2605'));
    assert.equal(getSymbolLabel('JM0'),'焦煤（JM0）');
});
test('unknown instruments and absent labels are not duplicated or fabricated', () => {
    assert.equal(getSymbolLabel('sh600000'),'sh600000');
    assert.equal(getSymbolLabel('XYZ2701'),'XYZ2701');
    assert.equal(getSymbolLabel(undefined),'');
});
