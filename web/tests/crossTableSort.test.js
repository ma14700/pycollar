import test from 'node:test';
import assert from 'node:assert/strict';
import {compareCrossNumber,compareCrossText,crossProfitPoints} from '../src/utils/crossTableSort.js';

test('points reflect long and short signal directions from observation start to end',()=>{
    assert.equal(crossProfitPoints({start_close:100,end_close:105,direction:'golden'}),5);
    assert.equal(crossProfitPoints({start_close:100,end_close:95,direction:'golden'}),-5);
    assert.equal(crossProfitPoints({start_close:100,end_close:95,direction:'death'}),5);
    assert.equal(crossProfitPoints({start_close:100,end_close:105,direction:'death'}),-5);
    assert.equal(crossProfitPoints({start_close:0.1,end_close:0.3,direction:'golden'}),0.2);
    assert.equal(crossProfitPoints({start_close:100,end_close:100,direction:'death'}),0);
    assert.equal(crossProfitPoints({start_close:null,end_close:100,direction:'golden'}),null);
});

test('history sorting uses numerical values for positive and negative returns and bar counts',()=>{
    const rows=[{return_pct:3,bars:10},{return_pct:-12,bars:2},{return_pct:0.5,bars:100}];
    assert.deepEqual([...rows].sort(compareCrossNumber('return_pct')).map(row=>row.return_pct),[-12,0.5,3]);
    assert.deepEqual([...rows].sort(compareCrossNumber('bars')).map(row=>row.bars),[2,10,100]);
});
test('history sorting respects complete timestamps and contract identifiers',()=>{
    const rows=[{signal:'2026-01-09 21:00:00',symbol:'JM2701'},{signal:'2025-12-23 09:00:00',symbol:'JM2605'},{signal:'2026-01-09 09:00:00',symbol:'JM2609'}];
    assert.deepEqual([...rows].sort(compareCrossText('signal')).map(row=>row.signal),['2025-12-23 09:00:00','2026-01-09 09:00:00','2026-01-09 21:00:00']);
    assert.deepEqual([...rows].sort(compareCrossText('symbol')).map(row=>row.symbol),['JM2605','JM2609','JM2701']);
});
