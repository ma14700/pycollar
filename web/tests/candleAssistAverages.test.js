import test from 'node:test';
import assert from 'node:assert/strict';
import {candleAssistAverages} from '../src/utils/candleAssistAverages.js';

test('every average is available while only the tested pair is visible initially',()=>{
    const chart={ohlc:Array.from({length:160},(_,i)=>[i+1,i+1,i+1,i+1]),ma:{'20':[11], '55':[22], '60':[33], '144':[44]}};
    for(const pair of ['20/55','20/144','55/144']) {
        const {series,selected}=candleAssistAverages(chart,pair);
        assert.deepEqual(series.map(line=>line.name),['MA20','MA55','MA144']);
        assert.deepEqual(Object.keys(selected).filter(name=>selected[name]),pair.split('/').map(n=>`MA${n}`));
        assert.deepEqual(series[1].data,[22]);
    }
});

test('legacy snapshots calculate missing averages only from complete valid windows',()=>{
    const chart={ohlc:Array.from({length:160},(_,i)=>[i+1,i+1,i+1,i+1]),ma:{}};
    const ma55=candleAssistAverages(chart,'20/55').series[1].data;
    assert.equal(ma55[53],null);
    assert.equal(ma55[54],28);
    chart.ohlc[60][1]=null;
    const gapped=candleAssistAverages(chart,'20/55').series[1].data;
    assert.equal(gapped[60],null);
    assert.equal(gapped[115],89);
});
