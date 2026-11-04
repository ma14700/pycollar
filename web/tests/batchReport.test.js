import test from 'node:test';
import assert from 'node:assert/strict';
import { batchReportRows, equitySparkline } from '../src/utils/batchReport.js';

test('report cards retain source identity and account-return units across duplicate contracts',()=>{
    const data={backtest_request:{symbol:'JM2605',strategy_name:'A',period:'daily'},metrics:{initial_cash:1000,net_profit:100,total_trades:3,one_hand_profit_pct:15,one_hand_net_profit:50}};
    const rows=batchReportRows([{symbol:'JM2605',success:true,data},{symbol:'JM2605',strategy_name:'B',success:false,error:'offline'}]);
    assert.equal(rows[0].returnPct,10);
    assert.equal(rows[0].perHandReturn,15);
    assert.equal(rows[0].data,data);
    assert.equal(rows[1].error,'offline');
    assert.equal(rows[1].returnPct,null);
    assert.deepEqual(rows.map(row=>row.key),['0','1']);
    assert.deepEqual(rows.map(row=>row.strategy),['A','B']);
    assert.equal(batchReportRows([{success:true}])[0].profit,null);
});
test('sparkline shows actual variation, keeps gaps separate and handles flat or absent values',()=>{
    assert.deepEqual(equitySparkline(null),[]);
    assert.deepEqual(equitySparkline([]),[]);
    assert.deepEqual(equitySparkline([{value:100}]),[]);
    const flat=equitySparkline([{value:100},{value:100}]);
    assert.equal(flat[0],'M2.00,29.00 L238.00,29.00');
    const gaps=equitySparkline([{value:100},{value:110},{value:null},{value:90},{value:95}]);
    assert.equal(gaps.length,2);
    assert.ok(gaps.every(path=>!path.includes('NaN')));
    assert.ok(gaps[0].includes('L61.00,5.00'));
});
