import test from 'node:test';
import assert from 'node:assert/strict';
import { buildBatchAnalysis, drawdownCurve, strategyHighlights } from '../src/utils/batchAnalysis.js';

function item(symbol='JM2701', name='A', patch={}) {
    return {symbol,success:true,strategy_name:name,data:{backtest_request:{symbol,strategy_name:name,period:'daily',data_provider:'tqsdk',data_source:'main',strategy_params:{fixed_size:2,margin_rate:.12}},
        data_info:{symbol,period:'daily',start:'2026-01-01',end:'2026-01-03'},
        metrics:{initial_cash:1000,net_profit:100,max_drawdown:5,win_rate:50,total_trades:10,used_size:2,
            one_hand_profit_pct:20,one_hand_net_profit:50,one_hand_return_basis:'entry_margin',one_hand_margin_rate:.12,calculation_version:2,commission_rate:.0001,...patch},
        equity_curve:[{date:'2026-01-01',value:1000},{date:'2026-01-02',value:1200},{date:'2026-01-03',value:1100}]}};
}

test('groups exact contract and compatible conditions without blending account returns',()=>{
    const a=item(),b=item('JM2701','B',{net_profit:50}),c=item('JM2605','A');
    const model=buildBatchAnalysis([a,b,c]);
    assert.equal(model.groups.length,2);assert.equal(model.groups[0].rows.length,2);
    assert.deepEqual(model.groups[0].rows.map(row=>row.returnPct),[10,5]);
    assert.equal(model.groups[0].rows[0].perHandReturn,20);
    for(const patch of [{initial_cash:2000},{one_hand_margin_rate:.2},{calculation_version:1},{one_hand_return_basis:'legacy'}]){
        assert.equal(buildBatchAnalysis([a,item('JM2701','B',patch)]).groups.length,2);
    }
    for(const property of ['period','start','end','provider','data_source']){
        const changed=item('JM2701','B');changed.data.data_info[property]='different';
        assert.equal(buildBatchAnalysis([a,changed]).groups.length,2,property);
    }
});

test('failed and missing result rows remain visible but cannot participate in comparisons',()=>{
    const result=buildBatchAnalysis([item(),{symbol:'JM2701',strategy_name:'failed',success:false,error:'timeout'}, {symbol:'JM2701',success:true,data:{}}]);
    assert.equal(result.groups[0].rows.length,1);assert.equal(result.failures.length,2);
    assert.equal(result.failures[0].strategy,'failed');
    assert.equal(buildBatchAnalysis(result.failures).groups.length,0);
});

test('curves use initial account value, exact equity peaks and preserve absent values',()=>{
    const data=item().data;
    const curve=drawdownCurve(data);
    assert.deepEqual(curve.map(p=>p[1]),[0,0,100/1200*100]);
    data.equity_curve=[{date:'bad',value:0},{date:'2026-01-02',value:null},{date:'2026-01-03',value:900}];
    assert.deepEqual(drawdownCurve(data).map(p=>p[1]),[10]);
    data.metrics.initial_cash=null;assert.deepEqual(drawdownCurve(data),[]);
    const row=buildBatchAnalysis([item('JM2701','A',{sharpe_ratio:null,one_hand_profit_pct:null})]).groups[0].rows[0];
    assert.equal(row.sharpe,null);assert.equal(row.perHandReturn,null);
});

test('strengths distinguish returns from risk and exclude untraded zero-drawdown rows',()=>{
    const rows=buildBatchAnalysis([item('JM2701','profit',{net_profit:200,max_drawdown:20,total_trades:3}),
        item('JM2701','risk',{net_profit:100,max_drawdown:5,one_hand_net_profit:60}),
        item('JM2701','flat',{net_profit:0,max_drawdown:0,total_trades:0,used_size:0})]).groups[0].rows;
    const tags=strategyHighlights(rows);
    assert(tags[rows[0].key].some(tag=>tag.text==='收益领先'));
    assert(tags[rows[0].key].some(tag=>tag.text==='回撤较高'));
    assert(tags[rows[0].key].some(tag=>tag.text==='交易样本少于5笔'));
    assert(tags[rows[1].key].some(tag=>tag.text==='回撤较低'));
    assert(!tags[rows[2].key].some(tag=>tag.text==='回撤较低'));
    assert(tags[rows[2].key].some(tag=>tag.text==='未成交'));
    assert(!strategyHighlights([rows[0]])[rows[0].key].some(tag=>tag.text==='收益领先'));
});
