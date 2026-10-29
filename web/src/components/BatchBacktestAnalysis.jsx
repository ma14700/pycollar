import React, { useMemo, useState } from 'react';
import { Alert, Card, Col, Descriptions, Empty, Modal, Radio, Row, Select, Space, Table, Tag, Typography } from 'antd';
import { AnalysisChart, AnalysisStat } from './AnalyticsUi';
import { buildBatchAnalysis, strategyHighlights } from '../utils/batchAnalysis';
import { formatNumber, formatPercent, valueColor } from '../utils/backtestAnalytics';
import { strategyOptions } from '../utils/backtestStrategies';
import { periodMap } from '../constants';
import { RiseOutlined, SafetyCertificateOutlined, TransactionOutlined } from '@ant-design/icons';

const palette = ['#4f7ff1','#ac6ad5','#18a999','#e89d35','#e05d7a','#64748b','#7cae3a','#916a57'];
const name = row => strategyOptions.find(option => option.value === row.strategy)?.label || row.strategy;
const tooltip = { renderMode: 'richText', confine: true };
const parameterLabels = { fast_period:'快线周期',slow_period:'慢线周期',exit_period:'离场均线周期',ma_period:'入场均线周期',
    fixed_size:'固定手数',size_mode:'仓位模式',margin_rate:'保证金率',contract_multiplier:'合约乘数',
    entry_delay_bars:'开仓 K 线',exit_delay_bars:'平仓 K 线',atr_period:'ATR周期',atr_multiplier:'ATR倍数',risk_per_trade:'单笔风险比例',
    equity_percent:'资金比例',allow_reverse:'允许反手',take_profit_points:'止盈点数',stop_loss_points:'止损点数',
    tp_value:'止盈值',sl_value:'止损值',tp_mode:'止盈方式',sl_mode:'止损方式',ma_type:'均线类型',risk_reward_ratio:'盈亏比',
    dkx_period:'DKX周期',dkx_ma_period:'DKX均线周期',macd_fast:'MACD快线',macd_slow:'MACD慢线',macd_signal:'MACD信号线',use_expma:'使用EMA' };
const parameterValue = value => ({fixed:'固定手数',atr_risk:'风险比例',equity_percent:'资金比例',points:'点数',percent:'百分比',true:'是',false:'否'}[String(value)] || String(value));
const numeric = (value, percent = false) => <span style={{ color: valueColor(value), whiteSpace: 'nowrap' }}>{percent ? formatPercent(value) : formatNumber(value)}</span>;

export default function BatchBacktestAnalysis({ items, onClose }) {
    const { groups, failures } = useMemo(() => buildBatchAnalysis(items), [items]);
    const [groupKey, setGroupKey] = useState(groups[0]?.key);
    const [curveMode, setCurveMode] = useState('equity');
    const [barMetric, setBarMetric] = useState('perHandReturn');
    const group = groups.find(item => item.key === groupKey) || groups[0];
    const rows = group?.rows || [];
    const conditions = group?.conditions || {};
    const highlights = strategyHighlights(rows);
    const curve = {
        animation: false,
        tooltip: { ...tooltip, trigger: 'axis', valueFormatter: value => formatPercent(Array.isArray(value) ? value[1] : value) },
        legend: { type: 'scroll', top: 0, data: rows.map(row => `${name(row)} #${Number(row.key)+1}`) },
        grid: { left: 65, right: 25, top: 60, bottom: 55 },
        xAxis: { type: 'time' }, yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
        dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 5 }],
        series: rows.map((row,index) => ({ name: `${name(row)} #${Number(row.key)+1}`, type: 'line', showSymbol: false,
            data: curveMode === 'equity' ? row.equity : row.drawdowns, connectNulls: false,
            lineStyle: { width: 2 }, itemStyle: { color: palette[index % palette.length] } })),
    };
    const riskRows = rows.filter(row => row.returnPct !== null && row.drawdown !== null && row.trades > 0);
    const scatter = {
        animation: false,
        tooltip: { ...tooltip, formatter: params => `${params.data.strategyLabel}\n账户收益率：${formatPercent(params.value[1])}\n最大回撤：${formatPercent(params.value[0])}\n已平仓：${params.data.trades} 笔` },
        grid: { left: 60, right: 45, top: 35, bottom: 45 },
        xAxis: { type: 'value', name: '回撤 %', min: 0 }, yAxis: { type: 'value', name: '收益 %' },
        series: [{ type: 'scatter', symbolSize: 18, data: riskRows.map(row => ({ value: [row.drawdown,row.returnPct],
            strategyLabel: name(row), trades: row.trades,
            itemStyle: { color: palette[rows.indexOf(row) % palette.length] } })) }],
    };
    const bars = rows.filter(row => row[barMetric] !== null);
    const bar = {
        animation: false,
        tooltip: { ...tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { left: 200, right: 65, top: 15, bottom: 30 },
        xAxis: { type: 'value', axisLabel: { formatter: barMetric === 'perHandReturn' ? '{value}%' : '{value} 元' } },
        yAxis: { type: 'category', inverse: true, data: bars.map(row => `${name(row)} #${Number(row.key)+1}`), axisLabel: { width: 185, overflow: 'truncate' } },
        series: [{ type: 'bar', barMaxWidth: 20, data: bars.map(row => ({ value: row[barMetric], itemStyle: { color: valueColor(row[barMetric]) } })) }],
    };
    const leader = (field, descending) => rows.filter(row => row.trades > 0 && Number.isFinite(row[field]))
        .sort((a,b) => descending ? b[field]-a[field] : a[field]-b[field])[0];
    const best = leader('returnPct',true), safest = leader('drawdown',false), unitBest = leader('perHandProfit',true);
    const columns = [
        { title: '策略 / 表现特点', key: 'strategy', width: 300, fixed: 'left', render: (_,row) => <><Typography.Text strong>{name(row)}</Typography.Text><div style={{ marginTop:6 }}>{highlights[row.key]?.map(tag => <Tag key={tag.text} color={tag.color}>{tag.text}</Tag>)}</div></> },
        ...[['returnPct','账户收益率',true],['netProfit','净利润（元）'],['drawdown','最大回撤',true],['perHandReturn',conditions.basis === 'entry_margin' ? '单手收益率（保证金）' : '单手收益率（本金/旧口径）',true],['perHandProfit','单手净利（元）'],['winRate','胜率',true],['trades','已平仓笔数'],['sharpe','夏普'],['size','最大持仓'],['fees','手续费（元）']].map(([key,title,percent]) => ({
            title, dataIndex:key, key, width:135, align:'right', sorter:(a,b) => (a[key] ?? -Infinity)-(b[key] ?? -Infinity),
            render:value => ['trades','size'].includes(key) ? formatNumber(value,0) : numeric(value,percent),
        })),
    ];
    return <Modal title="回测分析 · 同合约策略对比" open onCancel={onClose} footer={null} width={1440}
        style={{ top:24, maxWidth:'calc(100vw - 32px)' }} styles={{ body:{ maxHeight:'calc(100vh - 145px)',overflowY:'auto',paddingRight:4 } }}>
        <div className="analysis-stack">
            <Alert type="info" showIcon message="同合约、同周期、同数据范围及资金口径比较，各策略独立运行，不合并为组合收益。"
                description="优缺点标签只反映本组历史样本中的相对表现；低回撤也可能来自交易较少，请结合已平仓笔数、仓位和参数判断。" />
            {failures.length > 0 && <Alert type="warning" showIcon message={`${failures.length} 项失败或缺少指标，未参与统计`}
                description={<div style={{maxHeight:100,overflowY:'auto'}}>{failures.map(item => <div key={item.key}>{item.symbol} · {name(item)}：{String(item.error)}</div>)}</div>} />}
            {!group ? <Empty description="暂无成功回测结果可分析" /> : <>
                <Space wrap><Typography.Text strong>对比合约 / 条件组</Typography.Text>
                    <Select aria-label="对比合约与条件组" value={group.key} style={{ width:430,maxWidth:'100%' }} onChange={setGroupKey}
                        options={groups.map((item,index) => ({ value:item.key,label:`${item.conditions.symbol} · ${periodMap[item.conditions.period] || item.conditions.period} · ${item.rows.length} 个策略结果 · 条件组 ${index+1}` }))} />
                    <Tag color="blue">共 {groups.length} 个独立条件组</Tag>
                </Space>
                <Descriptions bordered size="small" column={{ xs:1,sm:2,lg:4 }} items={[
                    { key:'range',label:'实际行情范围',children:`${conditions.start || '未知'} ～ ${conditions.end || '未知'}`,span:2 },
                    { key:'cash',label:'初始资金',children:`${formatNumber(conditions.cash)} 元` },
                    { key:'margin',label:'保证金率',children:conditions.margin === null ? '—' : formatPercent(conditions.margin*100) },
                ]} />
                {rows.length < 2 && <Alert type="warning" showIcon message="本条件组不足两个成功策略，请为同一合约选择多个策略进行对比。" />}
                {rows.some(row => row.equity.length === 0) && <Alert type="warning" showIcon message="部分结果缺少有效权益曲线或初始资金，仅展示其已有指标，不补算虚构曲线。" />}
                <Row gutter={[16,16]}>
                    <Col xs={24} md={8}><AnalysisStat icon={<RiseOutlined />} title="账户收益率最高" value={best ? formatPercent(best.returnPct) : '—'} detail={best ? name(best) : '暂无已平仓样本'} color={valueColor(best?.returnPct)} /></Col>
                    <Col xs={24} md={8}><AnalysisStat icon={<SafetyCertificateOutlined />} title="最大回撤最低" value={safest ? formatPercent(safest.drawdown) : '—'} detail={safest ? name(safest) : '暂无已平仓样本'} /></Col>
                    <Col xs={24} md={8}><AnalysisStat icon={<TransactionOutlined />} title="单手净利润最高" value={unitBest ? `${formatNumber(unitBest.perHandProfit)} 元` : '—'} detail={unitBest ? name(unitBest) : '暂无已平仓样本'} color={valueColor(unitBest?.perHandProfit)} /></Col>
                </Row>
                <AnalysisChart title={curveMode === 'equity' ? '多策略账户收益曲线' : '多策略回撤曲线'} subtitle="按各自初始资金归一化；点击图例显隐，拖动底部时间轴缩放" option={curve}
                    hasData={rows.some(row => row.equity.length)} height={340}
                    extra={<Radio.Group value={curveMode} onChange={event=>setCurveMode(event.target.value)} optionType="button" options={[{value:'equity',label:'收益曲线'},{value:'drawdown',label:'回撤曲线'}]} />} />
                <Row gutter={[16,16]}>
                    <Col xs={24} xl={12}><AnalysisChart title="收益与风险分布" subtitle="越靠左上，历史收益相对越高、回撤越低；悬停查看策略" option={scatter} hasData={riskRows.length} height={300} /></Col>
                    <Col xs={24} xl={12}><AnalysisChart title="单手表现对比" subtitle={conditions.basis === 'entry_margin' ? '按已平仓交易累计，以开仓保证金为分母；不计复利' : '本金或旧口径；旧结果需重新回测后按保证金比较'} option={bar} hasData={bars.length} height={Math.max(300,bars.length*30)}
                        extra={<Select aria-label="单手对比指标" value={barMetric} style={{width:110}} onChange={setBarMetric} options={[{value:'perHandReturn',label:'单手收益率'},{value:'perHandProfit',label:'单手净利润'}]} />} /></Col>
                </Row>
                <Card title="策略优缺点与指标明细" size="small">
                    <Table rowKey="key" columns={columns} dataSource={rows} pagination={false} size="small" scroll={{x:1650}}
                        expandable={{expandedRowRender:row => <Typography.Paragraph style={{margin:0}}>回测配置：{Object.entries(row.params).filter(([key])=>parameterLabels[key]).map(([key,value])=>`${parameterLabels[key]}：${parameterValue(value)}`).join('；') || '未保存参数'}</Typography.Paragraph>}} />
                </Card>
            </>}
        </div>
    </Modal>;
}
