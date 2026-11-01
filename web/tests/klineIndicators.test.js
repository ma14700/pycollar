import test from 'node:test';
import assert from 'node:assert/strict';
import * as echarts from 'echarts';
import { chartMacd, buildKlineIndicatorPanels } from '../src/utils/klineIndicators.js';

const kline = (closes = [100,102,101,105]) => ({ dates: closes.map((_,index)=>`2026-01-${String(index+1).padStart(2,'0')}`),
    values: closes.map(close=>[close,close,close,close]) });

test('MACD legacy fallback uses recursive EMA and the doubled histogram, preserving saved indicator data',()=>{
    const data=kline([10,12,11]);
    const result=chartMacd(data,{macd_fast:2,macd_slow:3,macd_signal:2});
    assert.deepEqual(result.periods,[2,3,2]);
    assert.equal(result.fromSavedBars,true);
    assert.equal(result.dif[0],0);
    assert.ok(Math.abs(result.dif[1]-1/3)<1e-12);
    assert.ok(Math.abs(result.dea[1]-2/9)<1e-12);
    assert.ok(Math.abs(result.hist[1]-2/9)<1e-12);
    data.macd={ dif:[1,2,3],dea:[4,5,6],hist:[-6,-6,-6],periods:[5,10,3] };
    const saved=chartMacd(data);
    assert.equal(saved.dif,data.macd.dif);
    assert.equal(saved.fromSavedBars,false);
    assert.deepEqual(saved.periods,[5,10,3]);
});

test('missing prices stay gaps, invalid periods use defaults, and future candles cannot change past MACD',()=>{
    const result=chartMacd(kline([100,null,105]),{macd_fast:0,macd_slow:'bad'});
    assert.deepEqual(result.periods,[12,26,9]);
    assert.deepEqual(result.dif,[0,null,0]);
    assert.deepEqual(result.hist,[0,null,0]);
    const before=chartMacd(kline()),after=chartMacd(kline([100,102,101,105,80,90]));
    for(const key of ['dif','dea','hist']) assert.deepEqual(before[key],after[key].slice(0,4));
    assert.deepEqual(chartMacd({}).dif,[]);
});

test('candles, MACD and optional equity have distinct aligned grids and linked zoom indices',()=>{
    const data=kline();
    data.macd={dif:[1,2,-1,0],dea:[0,1,0,0],hist:[2,2,-2,0]};
    for(const equity of [[],data.dates.map(date=>({date,value:1000}))]) {
        const panels=buildKlineIndicatorPanels(data,equity);
        assert.equal(panels.grid.length,equity.length?3:2);
        assert.deepEqual(panels.axisIndices,equity.length?[0,1,2]:[0,1]);
        assert.ok(panels.xAxis.every(axis=>axis.data===data.dates));
        const hist=panels.series.find(series=>series.name==='MACD');
        assert.equal(hist.yAxisIndex,1);
        assert.equal(hist.data[0].itemStyle.color,'#ef232a');
        assert.equal(hist.data[2].itemStyle.color,'#14b143');
        if(equity.length) assert.equal(panels.series.find(series=>series.name==='资金曲线').yAxisIndex,2);
        const chart=echarts.init(null,null,{renderer:'svg',ssr:true,width:1100,height:740});
        try {
            chart.setOption({...panels,series:[{name:'K线',type:'candlestick',data:data.values},...panels.series],
                dataZoom:[{type:'inside',xAxisIndex:panels.axisIndices},{type:'slider',xAxisIndex:panels.axisIndices}]});
            assert.ok(chart.renderToSVGString().includes('<svg'));
        } finally { chart.dispose(); }
    }
});
