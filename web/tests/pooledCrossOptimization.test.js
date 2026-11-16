import test from 'node:test';
import assert from 'node:assert/strict';
import {pooledCrossGroups, pooledCrossOptimization, pooledBestEvents} from '../src/utils/pooledCrossOptimization.js';

test('pooled profit/loss ratio weights individual point totals and counts for both views',()=>{
    const stats=(gross_profit_points,profit_count,gross_loss_points,loss_count)=>({gross_profit_points,profit_count,gross_loss_points,loss_count});
    const make=(symbol,pnl)=>({symbol,data:{groups:[{pair:'20/55',events:[],excluded:[],pending:0,expired:0,
        summary:{golden:{total:pnl.profit_count+pnl.loss_count,up:pnl.profit_count,down:pnl.loss_count,flat:0,...pnl},death:{total:0,up:0,down:0,flat:0,...stats(0,0,0,0)}}}],
        optimization:[{pair:'20/55',direction:'golden',series:[{bars:1,wins:pnl.profit_count,total:pnl.profit_count+pnl.loss_count,...pnl}]}]}});
    const runs=[make('JM2605',stats(20,2,10,1)),make('JM2609',stats(90,1,40,2))];
    const summary=pooledCrossGroups(runs)[0].summary.golden;
    const best=pooledCrossOptimization(runs)[0].best;
    assert.ok(Math.abs(summary.profit_loss_ratio-2.2)<1e-12);
    assert.ok(Math.abs(best.profit_loss_ratio-2.2)<1e-12);
    assert.equal(summary.avg_profit_points,110/3);
    assert.equal(summary.avg_loss_points,50/3);
    assert.equal(pooledCrossGroups([make('X',stats(20,2,0,0))])[0].summary.golden.profit_loss_ratio,null);
    assert.equal(pooledCrossOptimization([make('X',stats(0,0,20,2))])[0].best.profit_loss_ratio,null);
});

test('distribution pools completed counts and preserves contract identity and excluded signals',()=>{
    const summary=(total,up,down,flat)=>({total,up,down,flat,match_pct:100});
    const make=(symbol,golden,death,events,excluded)=>({symbol,data:{groups:[{pair:'20/60',summary:{golden,death},pending:excluded.length,expired:0,events,excluded}]}});
    const runs=[make('JM2605',summary(10,9,1,0),summary(2,0,1,1),[{direction:'golden',signal:'a'}],[{direction:'death',signal:'c'}]),
        make('JM2609',summary(1,0,1,0),summary(2,1,1,0),[{direction:'golden',signal:'b'}],[]),{symbol:'JM2701',error:'offline'}];
    const [group]=pooledCrossGroups(runs);
    assert.deepEqual(group.summary.golden,{total:11,up:9,down:2,flat:0,up_pct:81.82,match_pct:81.82});
    assert.deepEqual(group.summary.death,{total:4,up:1,down:2,flat:1,up_pct:25,match_pct:50});
    assert.deepEqual(group.events.map(item=>item.symbol),['JM2605','JM2609']);
    assert.equal(group.excluded[0].symbol,'JM2605');
    assert.equal(group.pending,1);
    assert.deepEqual(pooledCrossGroups([{error:'failed'}]),[]);
});

test('pool wins and samples per horizon instead of averaging contract percentages',()=>{
    const make = (symbol,points)=>({symbol,data:{optimization:[{pair:'20/60',direction:'golden',series:points}]}});
    const runs=[make('JM2605',[{bars:1,wins:9,total:10},{bars:2,wins:3,total:4},{bars:3,wins:0,total:0}]),
        make('JM2609',[{bars:1,wins:0,total:1},{bars:2,wins:0,total:0},{bars:3,wins:0,total:0}]),{symbol:'JM2701',error:'offline'}];
    const [result]=pooledCrossOptimization(runs);
    assert.deepEqual(result.series.map(point=>point.match_pct),[81.82,75,null]);
    assert.deepEqual(result.best,{bars:1,wins:9,total:11,match_pct:81.82});
});

test('ties use shorter horizon and empty samples never produce a best',()=>{
    const make = series=>[{symbol:'JM',data:{optimization:[{pair:'60/144',direction:'death',series}]}}];
    assert.equal(pooledCrossOptimization(make([{bars:2,wins:2,total:4},{bars:1,wins:1,total:2}]))[0].best.bars,1);
    assert.equal(pooledCrossOptimization(make([{bars:1,wins:0,total:0}]))[0].best,null);
});

test('overall best reconstructs each contract sample from its own candles and delay',()=>{
    const make=(symbol,prices,signals,delay=1)=>({symbol,data:{observation_delay:delay,
        chart:{dates:prices.map((_,i)=>`d${i}`),ohlc:prices.map(value=>[value,value,value,value])},
        optimization:[{pair:'20/60',direction:'golden',series:[]}],
        groups:[{pair:'20/60',events:signals.map(signal=>({signal,direction:'golden'})),excluded:[]}]}});
    const runs=[make('JM2605',[100,102,105,90],['d0']),make('JM2609',[100,100,90,120],['d0'])];
    const item={pair:'20/60',direction:'golden',best:{bars:1,total:2,wins:1}};
    const {events,complete}=pooledBestEvents(runs,item);
    assert.equal(complete,true);
    assert.deepEqual(events.map(e=>[e.symbol,e.start,e.end,e.outcome]),[['JM2605','d1','d2','up'],['JM2609','d1','d2','down']]);
    assert.equal(pooledBestEvents(runs,{...item,best:{...item.best,wins:2}}).complete,false);
    assert.equal(pooledBestEvents([make('JM',[100,100],['d0'])],{...item,best:{bars:2,total:0,wins:0}}).events.length,0);
});


test('pooled best honors early reverse exits and ignores signals reversed during delay',()=>{
    const make=(symbol,delay)=>({symbol,data:{reverse_exit:true,observation_delay:delay,
        chart:{dates:['d0','d1','d2'],ohlc:[100,102,105].map(v=>[v,v,v,v])},
        optimization:[{pair:'20/55',direction:'golden',series:[]}],
        groups:[{pair:'20/55',events:[],excluded:[{direction:'golden',signal:'d0',next_opposite:'d2'}]}]}});
    const item={pair:'20/55',direction:'golden',best:{bars:5,total:1,wins:1}};
    const result=pooledBestEvents([make('JM2605',0),make('JM2609',2)],item);
    assert.equal(result.complete,true);
    assert.deepEqual(result.events.map(e=>[e.symbol,e.end,e.bars,e.exit_reason]),[['JM2605','d2',2,'reverse']]);
});
