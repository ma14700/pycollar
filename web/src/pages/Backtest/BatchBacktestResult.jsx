import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Drawer, Empty, Input, Select, Tag, Tooltip } from 'antd';
import { BarChartOutlined, CheckCircleOutlined, CloseCircleOutlined, FullscreenOutlined, FullscreenExitOutlined, LineChartOutlined, SearchOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import SingleBacktestResult from './SingleBacktestResult';
import BatchBacktestAnalysis from '../../components/BatchBacktestAnalysis';
import { batchReportRows, equitySparkline } from '../../utils/batchReport';
import { formatNumber, formatPercent, valueColor } from '../../utils/backtestAnalytics';
import { strategyOptions } from '../../utils/backtestStrategies';
import { periodMap } from '../../constants';
import './BatchBacktestResult.css';

const strategyName = value => strategyOptions.find(option=>option.value===value)?.label || value;
const tooltip = {renderMode:'richText',confine:true,textStyle:{fontSize:11}};
function ReportChart({ height = 230, ...props }) {
    const ref=useRef(null);
    useEffect(()=>{
        const chart=ref.current.getEchartsInstance();
        const observer=new ResizeObserver(()=>{if(!chart.isDisposed()) chart.resize();});
        observer.observe(chart.getDom());
        return ()=>observer.disconnect();
    },[]);
    return <ReactECharts ref={ref} {...props} notMerge style={{height}} opts={{renderer:'svg'}}/>;
}

export default function BatchBacktestResult({ results, symbols = [], isFullScreen, onToggleFullScreen }) {
    const rows = useMemo(()=>batchReportRows(results?.items || []),[results?.items]);
    const [analysisOpen,setAnalysisOpen] = useState(false);
    const [detailKey,setDetailKey] = useState(null);
    const [query,setQuery] = useState('');
    const [filter,setFilter] = useState('all');
    const [sort,setSort] = useState('original');
    const [selectedStrategy,setSelectedStrategy] = useState('all');
    if (!results?.isBatch) return null;
    const successes = rows.filter(row=>row.success);
    const profits = successes.filter(row=>row.profit>0).length;
    const losses = successes.filter(row=>row.profit<0).length;
    const neutral = successes.length-profits-losses;
    const ranked = successes.filter(row=>row.returnPct!==null && row.trades>0).slice().sort((a,b)=>b.returnPct-a.returnPct);
    const best = ranked[0];
    const detail = rows.find(row=>row.key===detailKey);
    const shown = rows.filter(row=>(selectedStrategy==='all'||row.strategy===selectedStrategy)
        && `${row.symbol} ${strategyName(row.strategy)}`.toLowerCase().includes(query.trim().toLowerCase())
        && (filter==='all'||(filter==='failed'&&!row.success)||(filter==='profit'&&row.success&&row.profit>0)||(filter==='loss'&&row.success&&row.profit<0)));
    if(sort!=='original') shown.sort((a,b)=>sort==='return'?(b.returnPct??-Infinity)-(a.returnPct??-Infinity):(a.drawdown??Infinity)-(b.drawdown??Infinity));
    const rankOption={animation:false,grid:{left:86,right:58,top:8,bottom:26},tooltip:{...tooltip,formatter:p=>`${ranked[p.dataIndex].symbol}\n${strategyName(ranked[p.dataIndex].strategy)}\n账户收益 ${formatPercent(p.value)}`},
        xAxis:{type:'value',axisLabel:{formatter:'{value}%',fontSize:10,color:'#99a6ba'},splitLine:{lineStyle:{color:'#eef2f8',type:'dashed'}}},
        yAxis:{type:'category',inverse:true,data:ranked.map(row=>`${row.symbol} #${Number(row.key)+1}`),axisLine:{show:false},axisTick:{show:false},axisLabel:{interval:0,fontSize:10,color:'#8393aa'}},
        series:[{type:'bar',barMaxWidth:15,label:{show:true,position:'right',fontSize:10,color:'#8393aa',formatter:p=>formatPercent(p.value)},data:ranked.map(row=>({value:row.returnPct,rowKey:row.key,itemStyle:{color:row.returnPct>=0?'#6c8aeb':'#27ac97',borderRadius:4}}))}]};
    const distribution=[{name:'盈利',value:profits,itemStyle:{color:'#6485e9'}},{name:'亏损',value:losses,itemStyle:{color:'#2daf99'}},
        {name:'持平 / 指标未知',value:neutral,itemStyle:{color:'#b9c6db'}},{name:'失败',value:rows.length-successes.length,itemStyle:{color:'#e6a0a8'}}].filter(item=>item.value>0);
    const distributionOption={animation:false,tooltip:{...tooltip,trigger:'item',formatter:'{b}：{c} 条（{d}%）'},legend:{bottom:0,textStyle:{fontSize:10,color:'#8c9bb0'}},
        title:{text:String(rows.length),subtext:'回测任务',left:'center',top:'33%',textStyle:{fontSize:25,color:'#38557c'},subtextStyle:{fontSize:10,color:'#9cabc0'}},
        series:[{type:'pie',radius:['52%','72%'],center:['50%','43%'],label:{show:false},itemStyle:{borderColor:'#fff',borderWidth:4,borderRadius:6},data:distribution}]};
    const onRankClick = p => { if(p.data?.rowKey!==undefined) setDetailKey(p.data.rowKey); };
    return <section className="batch-report" aria-label="批量回测报告">
        <header className="batch-report-hero"><div><div className="batch-report-eyebrow"><BarChartOutlined/> BATCH BACKTEST</div><h2>批量回测报告</h2><p>按合约和策略查看每一次回测，点击卡片查看完整结果。</p></div>
            <div className="batch-report-actions"><Button type="primary" icon={<LineChartOutlined/>} onClick={()=>setAnalysisOpen(true)}>回测分析</Button>
                {onToggleFullScreen&&<Button icon={isFullScreen?<FullscreenExitOutlined/>:<FullscreenOutlined/>} onClick={onToggleFullScreen}>{isFullScreen?'退出全屏':'全屏查看'}</Button>}
            </div>
        </header>
        <div className="batch-report-stats">
            <div className="batch-report-stat"><span>回测任务</span><strong>{rows.length}</strong><small>{new Set(rows.map(row=>row.symbol)).size} 个合约 · {new Set(rows.map(row=>row.strategy)).size} 个策略</small></div>
            <div className="batch-report-stat"><span>成功完成</span><strong style={{color:'#577be2'}}>{successes.length}<span style={{fontSize:13,color:'#a0adbf'}}> / {rows.length}</span></strong><small>{rows.length-successes.length} 项失败 · 保留原因</small></div>
            <div className="batch-report-stat"><span>盈利结果</span><strong>{profits}</strong><small>各结果独立统计</small></div>
            <div className="batch-report-stat"><span>最高账户收益</span><strong style={{color:valueColor(best?.returnPct)}}>{best?formatPercent(best.returnPct):'—'}</strong><small title={best&&strategyName(best.strategy)}>{best?`${best.symbol} · ${strategyName(best.strategy)}`:'暂无已平仓样本'}</small></div>
        </div>
        <div className="batch-report-plots">
            <div className="batch-report-plot"><h3>账户收益排名</h3><p>有已平仓交易的结果 · 共 {ranked.length} 条 · 上下滚动查看，点击查看详情</p>{ranked.length?<div className="batch-report-ranking-scroll" role="region" aria-label="账户收益完整排名" tabIndex={0}><ReportChart height={Math.max(230,ranked.length*28+34)} option={rankOption} onEvents={{click:onRankClick}}/></div>:<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无已平仓结果"/>}</div>
            <div className="batch-report-plot"><h3>回测结果分布</h3><p>按回测任务统计，非单笔交易胜率</p>{rows.length?<ReportChart option={distributionOption}/>:<Empty image={Empty.PRESENTED_IMAGE_SIMPLE}/>}</div>
        </div>
        <div className="batch-report-toolbar"><strong>回测结果 <span style={{fontWeight:400,color:'#96a4b7',fontSize:12}}>{shown.length} / {rows.length}</span></strong><div className="batch-report-tools">
            <Input aria-label="搜索回测结果" prefix={<SearchOutlined/>} placeholder="搜索合约 / 策略" allowClear value={query} onChange={event=>setQuery(event.target.value)} style={{width:180}}/>
            <Select aria-label="筛选报告策略" value={selectedStrategy} onChange={setSelectedStrategy} style={{width:180}} options={[{value:'all',label:'全部策略'},...Array.from(new Set(rows.map(row=>row.strategy))).map(value=>({value,label:strategyName(value)}))]}/>
            <Select aria-label="筛选报告结果" value={filter} onChange={setFilter} style={{width:105}} options={[{value:'all',label:'全部结果'},{value:'profit',label:'盈利'},{value:'loss',label:'亏损'},{value:'failed',label:'失败'}]}/>
            <Select aria-label="回测结果排序" value={sort} onChange={setSort} style={{width:120}} options={[{value:'original',label:'默认顺序'},{value:'return',label:'收益从高到低'},{value:'drawdown',label:'回撤从低到高'}]}/>
        </div></div>
        {shown.length?<div className="batch-report-grid">{shown.map(row=>{
            const symbolInfo=symbols.find(item=>item.code===row.symbol)||symbols.find(item=>item.code===`${row.symbol.match(/^[A-Za-z]+/)?.[0]}0`);
            const paths=equitySparkline(row.data?.equity_curve);
            const color=valueColor(row.profit);
            return <article className="batch-result-card" key={row.key}>
                <div className="batch-result-card-head"><div><span className="batch-result-symbol">{row.symbol}</span><span className="batch-result-name">{symbolInfo?.name?.match(/\(([^)]+)\)/)?.[1]||symbolInfo?.name}</span></div>
                    <Tag icon={row.success?<CheckCircleOutlined/>:<CloseCircleOutlined/>} color={row.success?'blue':'error'} style={{margin:0,fontSize:10}}>{row.success?'已完成':'失败'}</Tag></div>
                <div className="batch-result-strategy">{strategyName(row.strategy)}</div>
                {row.success?<><div className="batch-result-main"><div><span>账户收益率</span><strong style={{color}}>{formatPercent(row.returnPct)}</strong><small>净利润 {formatNumber(row.profit)} 元</small></div>
                    {paths.length?<svg className="batch-result-spark" viewBox="0 0 240 58" role="img" aria-label={`${row.symbol}权益走势`}><line x1="0" y1="56" x2="240" y2="56" stroke="#eaf0f8"/>{paths.map((path,index)=><path key={index} d={path} fill="none" stroke={color} strokeWidth="2"/>)}</svg>:<div className="batch-result-spark-empty">暂无权益曲线</div>}</div>
                    <div className="batch-result-metrics"><div><span>最大回撤</span><b>{formatPercent(row.drawdown)}</b></div><div><span>胜率</span><b>{formatPercent(row.winRate)}</b></div><div><span>已平仓笔数</span><b>{formatNumber(row.trades,0)}</b></div></div>
                    <div className="batch-result-unit"><Tooltip title={row.basis==='entry_margin'?'以开仓保证金为分母，累计已平仓单手收益率':row.basis==='entry_notional'?'以全额开仓本金为分母':'旧口径，请重新回测确认'}><span>单手收益率<b style={{color:valueColor(row.perHandReturn)}}>{formatPercent(row.perHandReturn)}</b>（{row.basis==='entry_margin'?'保证金':row.basis==='entry_notional'?'全额本金':'旧口径'}）</span></Tooltip><span>单手净利<b style={{color:valueColor(row.perHandProfit)}}>{formatNumber(row.perHandProfit)} 元</b></span></div>
                </>:<div className="batch-result-error">{typeof row.error==='string'?row.error:JSON.stringify(row.error)}</div>}
                <footer className="batch-result-footer"><span>#{Number(row.key)+1} · {periodMap[row.period]||row.period||'周期未知'}</span><Button type="link" size="small" disabled={!row.success||!row.data} onClick={()=>setDetailKey(row.key)}>查看详情 →</Button></footer>
            </article>;
        })}</div>:<Empty description="当前筛选条件下没有结果"/>}
        <div className="batch-report-note">各合约与策略为独立回测，收益不相加；权益小图按每条结果独立缩放，具体时间与价格请查看详情。</div>
        {analysisOpen&&<BatchBacktestAnalysis items={results.items} onClose={()=>setAnalysisOpen(false)}/>}
        <Drawer title={detail?`${detail.symbol} · ${strategyName(detail.strategy)}`:'回测详情'} width="min(1080px, 100vw)" open={Boolean(detail)} onClose={()=>setDetailKey(null)} destroyOnClose>{detail?.data&&<SingleBacktestResult results={detail.data}/>}</Drawer>
    </section>;
}
