import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Card, Checkbox, Col, DatePicker, Empty, Form, InputNumber, Modal, Row, Select, Space, Statistic, Switch, Table, Tabs, Tag, Typography } from 'antd';
import { LineChartOutlined, PlayCircleOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import axios from '../../utils/api.js';
import DataProviderSelect from '../../components/DataProviderSelect';
import DataSourceInfo from '../../components/DataSourceInfo';
import ContractMonthSelect from '../../components/ContractMonthSelect';
import { defaultTradingSymbol } from '../../utils/tradingDefaults';
import { buildContractComparisons } from '../../utils/contractAnalysis';
import { contractWindow } from '../../utils/contractBacktest';
import { pooledBestEvents, pooledCrossGroups, pooledCrossOptimization } from '../../utils/pooledCrossOptimization';
import { compareCrossNumber, compareCrossText, crossProfitPoints } from '../../utils/crossTableSort';
import { candleAssistAverages } from '../../utils/candleAssistAverages';
import './CandleAssist.css';

const pairs = ['20/55', '20/144', '55/144'];
const directionText = { golden: '金叉', death: '死叉' };
const outcomeText = { up: '上涨', down: '下跌', flat: '平盘' };
const fmt = value => value == null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
const fmtPoints = value => value == null ? '—' : `${value > 0 ? '+' : ''}${new Intl.NumberFormat('zh-CN',{maximumFractionDigits:8}).format(value)}`;
const renderPoints = value => <span style={{color:value>0?'#cf1322':value<0?'#3f8600':'#888',fontWeight:600}}>{fmtPoints(value)}</span>;
const ratioText = value => Number.isFinite(value) ? `${value.toFixed(2)} : 1` : '—';
const averagePoints = value => Number.isFinite(value) ? new Intl.NumberFormat('zh-CN',{maximumFractionDigits:2}).format(value) : '—';
function ProfitLossRatio({stats}) {
    return <div className="assist-profit-ratio" title="平均盈利点数 ÷ 平均亏损点数；平盘不参与两侧平均，无盈利或无亏损时不计算。">
        <div><span>盈亏比</span><strong>{ratioText(stats?.profit_loss_ratio)}</strong></div>
        <small>平均盈利 {averagePoints(stats?.avg_profit_points)} 点 · 平均亏损 {averagePoints(stats?.avg_loss_points)} 点</small>
    </div>;
}
const ALL_CONTRACTS = '__all_contracts__';

function candleOption(chart, event, observationBars) {
    const dates = chart.dates;
    const first = dates.indexOf(event.signal || event.start), last = dates.indexOf(event.end);
    const start = Math.max(0, first - 40), end = Math.min(dates.length - 1, last + 20);
    const averages = candleAssistAverages(chart,event.pair);
    return { animation:false, legend:{data:['K线', ...averages.series.map(line=>line.name)],selected:averages.selected,top:0},
        tooltip:{trigger:'axis',axisPointer:{type:'cross'}}, grid:{left:65,right:35,top:48,bottom:75},
        xAxis:{type:'category',data:dates,axisLabel:{hideOverlap:true}}, yAxis:{scale:true,splitLine:{lineStyle:{color:'#eef2f8'}}},
        dataZoom:[{type:'inside',startValue:start,endValue:end},{type:'slider',startValue:start,endValue:end,bottom:10}],
        series:[{name:'K线',type:'candlestick',data:chart.ohlc,itemStyle:{color:'#e85864',color0:'#2baa91',borderColor:'#e85864',borderColor0:'#2baa91'},
            markPoint:{symbolSize:42,data:[{name:directionText[event.direction],coord:[event.signal || event.start,event.signal_close ?? event.start_close],value:directionText[event.direction],itemStyle:{color:event.direction==='golden'?'#e85864':'#2baa91'}},
                ...(event.signal && event.signal!==event.start ? [{name:'观察起点',coord:[event.start,event.start_close],value:'起点',itemStyle:{color:'#d69e2e'}}] : []),
                {name:event.exit_reason === 'reverse' ? '反转平仓' : observationBars ? `第${observationBars}根收盘` : '反向交叉',coord:[event.end,event.end_close],value:'结束',itemStyle:{color:'#7185b5'}}]}},
            ...averages.series] };
}

export default function CandleAssistPage() {
    const [form] = Form.useForm();
    const [defaultRange] = useState(() => {
        const today = new Intl.DateTimeFormat('sv-SE', { timeZone:'Asia/Shanghai', year:'numeric', month:'2-digit', day:'2-digit' }).format(new Date());
        return [dayjs('2024-01-01'), dayjs(today).subtract(7, 'day')];
    });
    const [symbols, setSymbols] = useState([]);
    const [symbolError, setSymbolError] = useState('');
    const [loading, setLoading] = useState(false);
    const [runs, setRuns] = useState([]);
    const [active, setActive] = useState('');
    const [detail, setDetail] = useState(null);
    const [pairFilter, setPairFilter] = useState('all');
    const [directionFilter, setDirectionFilter] = useState('all');
    const [optimizationKey, setOptimizationKey] = useState('');
    const [bestDetail, setBestDetail] = useState(null);
    const [bestEventIndex, setBestEventIndex] = useState(0);
    const request = useRef(null);
    const provider = Form.useWatch('data_provider', form) || 'tqsdk';
    const synthesize60 = Form.useWatch('synthesize_60', form) || false;
    const period = Form.useWatch('period', form) || '60';
    const months = Form.useWatch('contract_month', form) || [];
    useEffect(() => {
        const controller = new AbortController();
        axios.get('/api/symbols', {params:{market_type:'futures'}, signal:controller.signal})
            .then(({data}) => { const list = data.futures || []; setSymbols(list); form.setFieldValue('symbol', defaultTradingSymbol(list)?.code); })
            .catch(() => { if (!controller.signal.aborted) setSymbolError('品种列表加载失败，请刷新重试'); });
        return () => { controller.abort(); request.current?.abort(); };
    }, [form]);
    useEffect(() => { if (provider === 'akshare') form.setFieldsValue({period:'daily',data_source:'main'}); }, [provider, form]);
    useEffect(() => { if (provider === 'akshare' && !synthesize60 && form.getFieldValue('period') === '60') form.setFieldValue('period','daily'); }, [provider, synthesize60, form]);

    const run = async (values, optimize = false) => {
        request.current?.abort();
        const controller = new AbortController(); request.current = controller;
        setLoading(true); setRuns([]); setActive(''); setDetail(null); setBestDetail(null); setPairFilter('all'); setDirectionFilter('all'); setOptimizationKey('');
        try {
            const payload = { symbol:values.symbol, period:values.period, data_provider:values.data_provider || 'tqsdk',
                data_source:values.data_source, synthesize_60:values.synthesize_60 || false, pairs:values.pairs, observation_bars:optimize ? null : values.observation_bars ?? null, observation_delay:values.observation_delay ?? 0, reverse_exit:values.reverse_exit ?? false,
                optimize, max_search_bars:values.max_search_bars ?? 200,
                start:values.range?.[0]?.format('YYYY-MM-DD'), end:values.range?.[1]?.format('YYYY-MM-DD') };
            const next = [];
            for (const item of buildContractComparisons(payload, values.contract_month)) {
                try {
                    const {data} = await axios.post('/api/candles/cross-probability', item, {signal:controller.signal});
                    next.push({symbol:item.symbol,data});
                } catch (error) {
                    if (controller.signal.aborted) return;
                    next.push({symbol:item.symbol,error:typeof error.response?.data?.detail === 'string' ? error.response.data.detail : '行情分析失败，请稍后重试'});
                }
            }
            if (!controller.signal.aborted) { setRuns(next); setActive(next.length > 1 && next.some(item=>item.data) ? ALL_CONTRACTS : (next.find(item=>item.data) || next[0])?.symbol || ''); }
        } catch (error) {
            if (!controller.signal.aborted) setRuns([{symbol:'请求',error:error.message}]);
        } finally { if (request.current === controller) setLoading(false); }
    };
    const pooled = useMemo(()=>pooledCrossOptimization(runs),[runs]);
    const pooledGroups = useMemo(()=>pooledCrossGroups(runs),[runs]);
    const successfulRuns = runs.filter(item=>Array.isArray(item.data?.groups));
    const aggregate = active === ALL_CONTRACTS && runs.length > 1 && successfulRuns.length > 0;
    const selected = aggregate ? {symbol:'整体合约',data:{...successfulRuns[0].data,optimization:pooled,groups:pooledGroups,chart:null}} : runs.find(item=>item.symbol===active) || runs[0];
    const observationBars = selected?.data?.observation_bars ?? null;
    const observationDelay = selected?.data?.observation_delay ?? 0;
    const reverseExit = selected?.data?.reverse_exit ?? false;
    const endpointLabel = observationBars ? (reverseExit ? '观察结束' : `起点后第${observationBars}根收盘`) : '反向交叉';
    const groups = selected?.data?.groups || [];
    const optimization = selected?.data?.optimization || [];
    const activeOptimization = optimization.find(item=>`${item.pair}-${item.direction}`===optimizationKey) || optimization[0];
    const optimizationOption = activeOptimization && { tooltip:{trigger:'axis',formatter:params=>{const item=params[0]?.data; return item ? `观察 ${item.value[0]} 根<br/>胜率 ${item.value[1] == null ? '暂无样本' : `${item.value[1]}%`}<br/>符合 ${item.wins} / ${item.total} 次<br/>盈亏比 ${ratioText(item.profit_loss_ratio)}` : ''; }},
        grid:{left:55,right:25,top:20,bottom:65}, xAxis:{type:'value',name:'观察根数',min:1,max:selected.data.max_search_bars}, yAxis:{type:'value',min:0,max:100,axisLabel:{formatter:'{value}%'}},
        dataZoom:[{type:'inside'},{type:'slider',bottom:12}], series:[{type:'line',showSymbol:false,connectNulls:false,lineStyle:{color:'#607eea',width:2},areaStyle:{color:'rgba(96,126,234,.13)'},
            data:activeOptimization.series.map(item=>({value:[item.bars,item.match_pct],total:item.total,wins:item.wins,profit_loss_ratio:item.profit_loss_ratio}))}] };
    const rows = groups.flatMap(group => group.events.map((event,index)=>({...event,profit_points:crossProfitPoints(event),pair:group.pair,key:`${group.pair}-${index}`})));
    const excludedRows = groups.flatMap(group => (group.excluded || []).map((event,index)=>({...event,pair:group.pair,key:`${group.pair}-excluded-${index}`})));
    const filteredRows = rows.filter(row=>(pairFilter==='all'||row.pair===pairFilter)&&(directionFilter==='all'||row.direction===directionFilter));
    const categories = groups.flatMap(group=>['golden','death'].map(direction=>({pair:group.pair,direction,...group.summary[direction]})));
    const option = { tooltip:{trigger:'axis',axisPointer:{type:'shadow'}}, legend:{bottom:0}, grid:{left:105,right:35,top:20,bottom:48},
        xAxis:{type:'value',min:0,max:100,axisLabel:{formatter:'{value}%'}},
        yAxis:{type:'category',inverse:true,data:categories.map(item=>`${item.pair} ${directionText[item.direction]}  (n=${item.total})`)},
        series:[['up','上涨','#eb626a'],['down','下跌','#39a789'],['flat','平盘','#aebbd0']].map(([key,name,color])=>({name,type:'bar',stack:'total',barMaxWidth:28,itemStyle:{color},
            label:{show:true,formatter:params=>params.value>0?`${params.value.toFixed(1)}%`:''},
            data:categories.map(item=>item.total ? +(item[key]/item.total*100).toFixed(2) : null)})) };
    const columns = [
        ...(aggregate?[{title:'合约',dataIndex:'symbol',width:110,sorter:compareCrossText('symbol')}]:[]),
        {title:'均线',dataIndex:'pair',width:110,sorter:compareCrossText('pair')}, {title:'信号',dataIndex:'direction',width:95,sorter:compareCrossText('direction'),render:v=><Tag color={v==='golden'?'red':'green'}>{directionText[v]}</Tag>},
        {title:'交叉时间',dataIndex:'signal',width:190,sorter:compareCrossText('signal'),defaultSortOrder:'descend'}, {title:'观察起点时间',dataIndex:'start',width:190,sorter:compareCrossText('start')}, {title:`${endpointLabel}时间`,dataIndex:'end',width:200,sorter:compareCrossText('end')},
        {title:'起点收盘价',dataIndex:'start_close',width:130,sorter:compareCrossNumber('start_close')}, {title:'终点收盘价',dataIndex:'end_close',width:130,sorter:compareCrossNumber('end_close')},
        {title:'结束原因',dataIndex:'exit_reason',width:120,render:v=><Tag color={v==='reverse'?'orange':'blue'}>{v==='reverse'?'反向交叉':'观察到期'}</Tag>},
        {title:'间隔K线',dataIndex:'bars',width:120,sorter:compareCrossNumber('bars')}, {title:'涨跌幅',dataIndex:'return_pct',width:125,sorter:compareCrossNumber('return_pct'),render:v=><span style={{color:v>0?'#cf1322':v<0?'#3f8600':'#888',fontWeight:600}}>{fmt(v)}</span>},
        {title:'盈亏点数',dataIndex:'profit_points',width:130,sorter:compareCrossNumber('profit_points'),render:renderPoints},
        {title:'结果',dataIndex:'outcome',width:80,render:v=>outcomeText[v]},
        {title:'查看',width:90,fixed:'right',render:(_,row)=><Button type="link" onClick={()=>setDetail(row)}>K线图</Button>},
    ];
    return <div className="candle-assist">
        <header className="candle-assist-hero"><div><div className="candle-assist-eyebrow"><LineChartOutlined /> K线辅助分析</div><h1>K线辅助</h1>
            <p>探索均线交叉后的走势，用历史样本辅助判断。</p></div><div className="candle-assist-hero-decoration" aria-hidden="true"><i/><i/><i/><i/><i/><i/><i/><i/><i/><i/><i/><i/></div></header>
        <Card className="assist-panel assist-config" title={<div><span className="assist-section-kicker">01 / 设置</span><span>分析条件</span></div>}>
            {symbolError && <Alert type="error" showIcon message={symbolError} style={{marginBottom:16}}/>}
            <Form form={form} layout="vertical" onFinish={values=>run(values)} initialValues={{market_type:'futures',period:'60',range:defaultRange,data_provider:'tqsdk',data_source:'main',max_search_bars:200,reverse_exit:false,pairs}}>
                <Row gutter={20}>
                    <Col xs={24} md={12} xl={8}><DataProviderSelect form={form} disabled={months.length>0}/></Col>
                    <Col xs={24} md={12} xl={8}><Form.Item name="symbol" label="交易品种" rules={[{required:true,message:'请选择交易品种'}]}><Select showSearch optionFilterProp="label" options={symbols.map(item=>({value:item.code,label:item.name}))}/></Form.Item>
                        <Form.Item name="data_source" label="合约口径"><Select disabled={provider==='akshare'||months.length>0} options={[{value:'main',label:months.length?'具体合约':'主力连续'},{value:'weighted',label:'加权指数'}]}/></Form.Item></Col>
                    <Col xs={24} md={12} xl={8}><Form.Item name="period" label="K线周期"><Select disabled={provider==='akshare'&&!synthesize60} options={[{value:'daily',label:'日线'},...(provider==='akshare' ? ['60'] : ['1','5','15','30','60']).map(value=>({value,label:`${value}分钟`}))]}/></Form.Item>
                        {months.length ? <Form.Item label="分析时间范围"><Typography.Text type="secondary">具体合约按策略回测的合约窗口分别分析，清空合约后可自选时间。</Typography.Text></Form.Item> : <Form.Item name="range" label="分析时间范围（可选）"><DatePicker.RangePicker style={{width:'100%'}}/></Form.Item>}</Col>
                </Row>
                <ContractMonthSelect form={form} disabled={loading}/>
                {months.length>0 && <Alert type="info" showIcon style={{marginBottom:16}} message="各合约回测时间范围" description={months.map(month=>{const window=contractWindow(month); return <div key={month}>{month}：{window.start_date} ～ {window.end_date}</div>;})}/>}
                <div className="assist-settings-grid"><Form.Item name="observation_delay" label="延时观察（可选）" extra="填写 2 表示从交叉后的第 2 根收盘价开始；留空或 0 表示交叉当根收盘。" rules={[{validator:(_,value)=>value == null || (Number.isInteger(value) && value >= 0 && value <= 10000) ? Promise.resolve() : Promise.reject(new Error('请输入 0 至 10000 的整数'))}]}>
                    <InputNumber min={0} max={10000} precision={0} placeholder="默认 0 根" style={{width:'100%'}}/>
                </Form.Item>
                <Form.Item name="observation_bars" label="观察K线根数（可选）" extra="填写后比较观察起点与其后第 N 根收盘价；留空则比较下一次反向交叉收盘价。开启反转平仓后，反向交叉可提前结束。" rules={[{validator:(_,value)=>value == null || (Number.isInteger(value) && value >= 1 && value <= 10000) ? Promise.resolve() : Promise.reject(new Error('请输入 1 至 10000 的整数'))}]}>
                    <InputNumber min={1} max={10000} precision={0} placeholder="留空使用反向交叉" style={{width:'100%'}}/>
                </Form.Item>
                <Form.Item name="max_search_bars" label="量化判断搜索上限" extra="量化判断会依次比较从 1 根到该上限的观察结果。" rules={[{required:true,message:'请输入搜索上限'},{validator:(_,value)=>Number.isInteger(value) && value >= 1 && value <= 1000 ? Promise.resolve() : Promise.reject(new Error('请输入 1 至 1000 的整数'))}]}>
                    <InputNumber min={1} max={1000} precision={0} style={{width:'100%'}}/>
                </Form.Item>
                <Form.Item name="reverse_exit" label="反转平仓" valuePropName="checked" extra="开启后，观察期间出现反向交叉时按该根收盘价提前结束；延时观察期间已反向交叉则不计入。"><Switch checkedChildren="开启" unCheckedChildren="关闭"/></Form.Item></div>
                <Form.Item name="pairs" label="均线组合（可多选）" rules={[{type:'array',required:true,min:1,message:'请至少选择一组均线'}]} extra="均线按所选K线周期计算，例如日线时使用对应的日均线。">
                    <Checkbox.Group options={pairs.map(value=>({value,label:`${value} 均线金叉 / 死叉`}))}/>
                </Form.Item>
                <div className="assist-actions"><Space wrap><Button type="primary" htmlType="submit" loading={loading} icon={<PlayCircleOutlined/>} size="large">开始分析</Button>
                    <Button type="default" disabled={loading} onClick={()=>form.validateFields().then(values=>run(values,true)).catch(()=>{})} icon={<LineChartOutlined/>} size="large">量化判断</Button></Space><span>基于已完成的历史 K 线计算</span></div>
            </Form>
        </Card>
        <Alert type="info" showIcon message="统计口径" description="金叉按做多、死叉按做空统计。盈亏比 = 平均盈利点数 ÷ 平均亏损点数；平盘不参与盈亏点数平均，无盈利或无亏损样本时显示 —，不含手续费。观察起点为交叉后的延时根数收盘价；固定观察根数从该起点继续计数，留空则以下一次反向交叉收盘价为终点。留空观察根数或开启反转平仓时，若反向交叉不晚于延时起点则不计入；开启反转平仓后，观察期间发生反向交叉则提前结束；行情不足或超出结束日期的样本不计入。"/>
        {runs.length > 1 && <Tabs activeKey={active} onChange={value=>{setActive(value);setDetail(null);setBestDetail(null);setPairFilter('all');setDirectionFilter('all');}} items={[...(successfulRuns.length ? [{key:ALL_CONTRACTS,label:'整体合约'}] : []),...runs.map(item=>({key:item.symbol,label:<span>{item.symbol} {item.error&&<Tag color="error">失败</Tag>}</span>}))]}/>}
        {selected?.error && <Alert type="error" showIcon message={`${selected.symbol} 分析失败`} description={selected.error}/>}
        {selected?.data && <>
            <div className="assist-result-heading"><div><span className="assist-section-kicker">02 / 结果</span><h2>分析结果 <span>{selected.symbol}</span></h2><p>{selected.data.data_info.period==='daily'?'日线':`${selected.data.data_info.period}分钟`} · 延时 {observationDelay} 根 · {observationBars?`起点后第 ${observationBars} 根收盘`:'下一次反向交叉收盘'} · 反转平仓{reverseExit?'开启':'关闭'}</p></div><div className="assist-result-count"><strong>{rows.length}</strong><span>{observationBars?'已完成样本':'反向交叉样本'}</span></div></div>
            {aggregate ? <Alert type={successfulRuns.length<runs.length?'warning':'info'} showIcon message={`整体纳入 ${successfulRuns.length} / ${runs.length} 个合约`} description={<><div>逐根汇总各合约的符合次数和完整样本数，再计算整体胜率；不同根数的有效样本和参与合约可能不同。</div>{successfulRuns.map(run=><div key={run.symbol}>{run.symbol}：{run.data.analysis_window?.start} ～ {run.data.analysis_window?.end}</div>)}{runs.some(item=>item.error)&&<div>失败合约未计入：{runs.filter(item=>item.error).map(item=>item.symbol).join('、')}</div>}</>}/> : <><DataSourceInfo info={selected.data.data_info}/>{selected.data.analysis_window?.contract_window && <Alert type="info" showIcon message={`策略回测合约窗口：${selected.data.analysis_window.start} ～ ${selected.data.analysis_window.end}`} description="交叉信号和观察终点均须在此范围内；此前行情仅用于均线预热。"/>}</>}
            {optimization.length > 0 && <Card className="assist-panel assist-optimization" title="量化判断 · 历史最高胜率" extra={`搜索 1～${selected.data.max_search_bars} 根 · 延时 ${observationDelay} 根`}>
                <Alert type="info" showIcon style={{marginBottom:16}} message="每组金叉与死叉分别寻找历史胜率最高的观察根数" description={`金叉按上涨、死叉按下跌统计；平盘计入分母。${reverseExit?"开启反转平仓时，反向交叉可提前结束样本。":"各根数只统计该根数后行情完整的信号。"}样本数可能不同；胜率相同时取较短根数。历史最优不保证未来有效，样本较少时请谨慎解读。`}/>
                <Row gutter={[12,12]}>{optimization.map(item=><Col xs={24} sm={12} xl={8} key={`${item.pair}-${item.direction}`}><Card className="assist-insight-card" size="small" style={{height:'100%'}}>
                    <Typography.Text strong>{item.pair} {directionText[item.direction]} · {item.direction==='golden'?'上涨':'下跌'}</Typography.Text>
                    {item.best ? <><Statistic title="历史最高胜率" value={item.best.match_pct} precision={2} suffix="%" valueStyle={{color:'#5574db',fontWeight:700}}/>
                        <Typography.Text>观察 <strong>{item.best.bars}</strong> 根 · {item.best.wins}/{item.best.total} 次</Typography.Text><ProfitLossRatio stats={item.best}/>
                        <Space wrap><Button type="link" style={{paddingLeft:0}} onClick={()=>form.setFieldValue('observation_bars',item.best.bars)}>填入观察根数</Button><Button type="link" onClick={()=>{setBestEventIndex(0);setBestDetail(aggregate?{...item,...pooledBestEvents(runs,item)}:item);}}>查看历史K线</Button></Space></> : <div style={{padding:'18px 0',color:'#999'}}>行情不足，暂无完整样本</div>}
                </Card></Col>)}</Row>
                <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginTop:22,gap:12,flexWrap:'wrap'}}><Typography.Text strong>胜率随观察根数变化</Typography.Text>
                    <Select aria-label="选择量化曲线" value={activeOptimization ? `${activeOptimization.pair}-${activeOptimization.direction}` : undefined} onChange={setOptimizationKey} style={{width:180}} options={optimization.map(item=>({value:`${item.pair}-${item.direction}`,label:`${item.pair} ${directionText[item.direction]}`}))}/></div>
                {activeOptimization?.best ? <ReactECharts option={optimizationOption} notMerge style={{height:310}}/> : <Empty description="暂无完整样本"/>}
                <Typography.Text type="secondary">鼠标悬停查看每个根数的胜率和样本数；可缩放曲线。点击“查看历史K线”可查看最高胜率对应的每个样本。</Typography.Text>
            </Card>}
            <Modal title={bestDetail?`${selected.symbol} · ${bestDetail.pair} ${directionText[bestDetail.direction]} · 观察 ${bestDetail.best.bars} 根历史K线`:''} open={!!bestDetail} onCancel={()=>setBestDetail(null)} footer={null} width="min(1250px, 95vw)" destroyOnClose>
                {bestDetail && (()=>{const events=bestDetail.events || []; const event=events[bestEventIndex]; const chart=aggregate ? runs.find(run=>run.symbol===event?.symbol)?.data?.chart : selected.data.chart; return <>
                    <Alert type="info" showIcon style={{marginBottom:12}} message={`最高胜率 ${bestDetail.best.match_pct}% · 符合 ${bestDetail.best.wins} / ${bestDetail.best.total} 次 · 延时 ${observationDelay} 根，观察 ${bestDetail.best.bars} 根`} description="选择下方历史样本查看行情；点击图例可显示或隐藏 MA20、MA55 和 MA144。"/>
                    {bestDetail.complete===false ? <Alert type="warning" showIcon message="历史样本与汇总结果不一致，请重新量化判断"/> : event && chart ? <><Typography.Text strong>{event.symbol && `${event.symbol} · `}{event.signal} · {outcomeText[event.outcome]} {fmt(event.return_pct)}</Typography.Text><ReactECharts option={candleOption(chart,{...event,pair:bestDetail.pair},bestDetail.best.bars)} notMerge style={{height:460}}/></> : <Empty description="暂无该结果的K线数据，请重新量化判断"/>}
                    <Table size="small" rowKey="index" dataSource={events.map((item,index)=>({...item,profit_points:crossProfitPoints(item),index}))} scroll={{x:1020}} pagination={{pageSize:5,showSizeChanger:false,showTotal:total=>`共 ${total} 条`}} rowClassName={row=>row.index===bestEventIndex?'ant-table-row-selected':''} columns={[
                        ...(aggregate?[{title:'合约',dataIndex:'symbol',width:100}]:[]),{title:'交叉时间',dataIndex:'signal',width:170},{title:'观察起点',dataIndex:'start',width:170},{title:'观察终点',dataIndex:'end',width:170},{title:'结束原因',dataIndex:'exit_reason',width:110,render:v=>v==='reverse'?'反向交叉':'观察到期'},
                        {title:'涨跌幅',dataIndex:'return_pct',width:100,render:fmt},{title:'盈亏点数',dataIndex:'profit_points',width:110,render:renderPoints},{title:'结果',dataIndex:'outcome',width:80,render:value=>outcomeText[value]},
                        {title:'操作',width:85,render:(_,row)=><Button type="link" onClick={()=>setBestEventIndex(row.index)}>查看</Button>}
                    ]}/></>;})()}
            </Modal>
            <Card className="assist-panel assist-distribution" title="交叉后涨跌分布" extra={<Typography.Text type="secondary">{aggregate?'合约样本汇总 · ':''}按已完成样本统计 · n 为样本数</Typography.Text>}>
                <ReactECharts option={option} notMerge style={{height:Math.max(240,categories.length*48+85)}}/>
                <Row gutter={[12,12]}>{categories.map(item=><Col xs={24} sm={12} xl={8} key={`${item.pair}-${item.direction}`}><Card size="small" style={{height:'100%',borderRadius:14,background:item.direction==='golden'?'linear-gradient(135deg,#fff5f5,#fff)':'linear-gradient(135deg,#effaf7,#fff)',borderColor:item.direction==='golden'?'#f8d9dc':'#d3efe7'}}>
                    <Statistic title={`${item.pair} ${directionText[item.direction]}后${item.direction==='golden'?'上涨':'下跌'}概率`} value={item.match_pct==null?'暂无样本':item.match_pct} suffix={item.match_pct==null?'':'%'} precision={item.match_pct==null?undefined:2} valueStyle={{color:item.direction==='golden'?'#cf4251':'#278d77',fontWeight:700}}/>
                    <Typography.Text type="secondary">共 {item.total} 次 · 涨 {item.up} / 跌 {item.down} / 平 {item.flat}</Typography.Text><ProfitLossRatio stats={item}/>
                </Card></Col>)}</Row>
                <Typography.Paragraph type="secondary" style={{margin:'16px 0 0'}}>未完成样本：{groups.map(group=>`${group.pair} ${group.pending} 次`).join(' · ')}</Typography.Paragraph>
                {groups.some(group=>group.expired>0) && <Typography.Paragraph type="secondary" style={{margin:'4px 0 0'}}>延时起点前已反向交叉：{groups.map(group=>`${group.pair} ${group.expired} 次`).join(' · ')}</Typography.Paragraph>}
            </Card>
            <Card className="assist-panel assist-history" title="历史交叉明细" extra={<Space wrap><Select aria-label="筛选均线组合" value={pairFilter} onChange={setPairFilter} style={{width:130}} options={[{value:'all',label:'全部均线'},...groups.map(group=>({value:group.pair,label:group.pair}))]}/><Select aria-label="筛选交叉信号" value={directionFilter} onChange={setDirectionFilter} style={{width:120}} options={[{value:'all',label:'全部信号'},{value:'golden',label:'金叉'},{value:'death',label:'死叉'}]}/></Space>}><div className="assist-table-caption">共 {filteredRows.length} 条结果 · 点击表头可升序或降序排列 · 盈亏点数按金叉做多、死叉做空计算，不含费用</div><Table rowKey="key" dataSource={filteredRows} columns={columns} size="middle" scroll={{x:1630}} pagination={{pageSize:10,showSizeChanger:false,showTotal:total=>`共 ${total} 条`}} locale={{emptyText:<Empty description="暂无已完成交叉样本"/>}}/></Card>
            <Card className="assist-panel assist-excluded" title="未计入概率的交叉信号" extra={`${excludedRows.length} 条`}><Typography.Paragraph type="secondary">已识别但未完成观察的交叉列在这里，不计入胜率。分析范围以信号时间为准；计算均线需要更早的历史行情。</Typography.Paragraph>
                <Table rowKey="key" size="small" dataSource={excludedRows.filter(row=>(pairFilter==='all'||row.pair===pairFilter)&&(directionFilter==='all'||row.direction===directionFilter))} columns={[
                    ...(aggregate?[{title:'合约',dataIndex:'symbol',width:100}]:[]),
                    {title:'均线',dataIndex:'pair',width:100},{title:'信号',dataIndex:'direction',width:100,render:v=>directionText[v]},
                    {title:'交叉时间',dataIndex:'signal',width:180},{title:'未计入原因',dataIndex:'reason'}
                ]} pagination={{pageSize:5,showSizeChanger:false,showTotal:total=>`共 ${total} 条`}} locale={{emptyText:<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有未计入的交叉信号"/>}}/>
            </Card>
            <Modal title={detail?`${detail.symbol || selected.symbol} · ${detail.pair} ${directionText[detail.direction]} K线详情`:''} open={!!detail} onCancel={()=>setDetail(null)} footer={null} width="min(1200px, 95vw)" destroyOnClose>
                {detail && <><Alert type="info" showIcon style={{marginBottom:12}} message={`${detail.start} 至 ${detail.end} · ${detail.bars} 根K线 · 涨跌幅 ${fmt(detail.return_pct)}`} description={`标记显示交叉、观察起点及${endpointLabel}；点击图例可显示或隐藏均线，拖动缩放条可查看前后行情。`}/>
                    {(()=>{const chart=aggregate ? runs.find(run=>run.symbol===detail.symbol)?.data?.chart : selected.data.chart; return chart && chart.dates.includes(detail.start) && chart.dates.includes(detail.end) ? <ReactECharts option={candleOption(chart,detail,observationBars)} notMerge style={{height:540}}/> : <Empty description="此结果暂无K线数据，请重新分析"/>;})()}</>}
            </Modal>
        </>}
    </div>;
}
