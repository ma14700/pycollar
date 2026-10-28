import React, { useMemo, useState, useEffect } from 'react';
import { Button, Card, DatePicker, Empty, Input, Segmented, Select, Space, Table, Tag, Timeline, Tooltip } from 'antd';
import { DownloadOutlined, FileTextOutlined, SwapOutlined, TrophyOutlined, WalletOutlined, SearchOutlined } from '@ant-design/icons';
import { AnalysisChart, AnalysisStat } from './AnalyticsUi';
import { flattenResultLogs, filterLogRows, summarizeLogs, formatNumber, formatPercent, valueColor, downloadLogCsv } from '../utils/backtestAnalytics';

const kinds = {
    execution: { label: '成交', color: '#5286e8' }, settlement: { label: '结算', color: '#8b70d4' },
    signal: { label: '信号', color: '#e4a746' }, system: { label: '系统', color: '#91a0b5' },
    warning: { label: '异常', color: '#dc4b57' }, info: { label: '信息', color: '#55b8b2' },
};
const tooltip = { trigger: 'axis', renderMode: 'richText', backgroundColor: '#fff', borderColor: '#e5eaf2', textStyle: { color: '#475569' } };

export default function TradeLogDashboard({ results, filename = 'trading-logs.csv' }) {
    const [filters, setFilters] = useState({});
    const [view, setView] = useState('table');
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(20);
    const rows = useMemo(() => flattenResultLogs(results), [results]);
    const filtered = useMemo(() => filterLogRows(rows, filters), [rows, filters]);
    const summary = useMemo(() => summarizeLogs(filtered), [filtered]);
    const symbols = useMemo(() => [...new Set(rows.map(row => row.symbol).filter(Boolean))], [rows]);
    const latest = useMemo(() => [...filtered].reverse(), [filtered]);
    useEffect(() => { setFilters({}); setPage(1); }, [results]);
    const update = next => { setFilters(previous => ({ ...previous, ...next })); setPage(1); };
    const profitOption = {
        tooltip: { ...tooltip, valueFormatter: value => formatNumber(value) },
        grid: { left: 65, right: 24, top: 22, bottom: 56 },
        xAxis: { type: 'category', data: summary.points.map(row => row.date || '未标时间'), boundaryGap: false, axisLine: { lineStyle: { color: '#dbe3ee' } }, axisLabel: { color: '#8b96a8', formatter: value => value.slice(0, 10) }, axisTick: { show: false } },
        yAxis: { type: 'value', axisLabel: { color: '#8b96a8', formatter: value => Math.abs(value) >= 10000 ? `${(value / 10000).toFixed(1)}万` : value }, splitLine: { lineStyle: { color: '#eef2f7', type: 'dashed' } } },
        series: [{ name: '累计结算净利', type: 'line', data: summary.points.map(row => Number(row.cumulative.toFixed(2))), showSymbol: summary.points.length < 20,
            lineStyle: { width: 2.5, color: '#4f7ff1' }, itemStyle: { color: '#4f7ff1' }, areaStyle: { color: '#edf2ff' },
            markLine: { symbol: 'none', silent: true, lineStyle: { color: '#b8c5d9', type: 'dashed' }, label: { show: false }, data: [{ yAxis: 0 }] } }],
        dataZoom: summary.points.length > 40 ? [{ type: 'inside' }] : [],
    };
    const distributionOption = {
        tooltip: { trigger: 'item', renderMode: 'richText', formatter: '{b}  {c} 条（{d}%）' },
        legend: { bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { color: '#718098', fontSize: 12 } },
        series: [{ type: 'pie', radius: ['50%', '72%'], center: ['50%', '43%'], avoidLabelOverlap: true,
            label: { show: false }, emphasis: { label: { show: true, fontSize: 15, fontWeight: 600, formatter: '{b}\n{c} 条' } },
            itemStyle: { borderColor: '#fff', borderWidth: 4, borderRadius: 5 },
            data: summary.distribution.map(item => ({ name: kinds[item.kind].label, value: item.value, itemStyle: { color: kinds[item.kind].color } })) }],
        graphic: [{ type: 'text', left: 'center', top: '34%', silent: true, style: { text: `${summary.count}\n日志总数`, textAlign: 'center', fill: '#34445e', font: '600 18px sans-serif', lineHeight: 25 } }],
    };
    const columns = [
        { title: '时间 / 品种', key: 'time', width: 164, render: (_, row) => <><div className="analysis-primary">{row.date || '未标时间'}</div>{row.symbol && <span className="analysis-muted">{row.symbol}</span>}</> },
        { title: '事件', key: 'kind', width: 110, render: (_, row) => <Tag color={kinds[row.kind].color}>{row.action || kinds[row.kind].label}</Tag> },
        { title: '价格', dataIndex: 'price', align: 'right', width: 95, render: value => <span className="analysis-num">{formatNumber(value)}</span> },
        { title: '数量', dataIndex: 'size', align: 'right', width: 75, render: value => formatNumber(value, 0) },
        { title: '手续费', dataIndex: 'comm', align: 'right', width: 88, render: value => formatNumber(value) },
        { title: '结算净利', key: 'settled', align: 'right', width: 120, render: (_, row) => row.isSettlement ? <span className="analysis-num" style={{ color: valueColor(row.pnl) }}>{formatNumber(row.pnl)}</span> : '—' },
        { title: '日志内容', dataIndex: 'content', render: value => <span className="analysis-log-text">{value}</span> },
    ];

    return <div>
        <div className="analysis-stats">
            <AnalysisStat title="成交记录" value={formatNumber(summary.executions, 0)} detail={`当前 ${summary.count} 条日志 / 共 ${rows.length} 条`} icon={<SwapOutlined />} />
            <AnalysisStat title="已结算净利" value={formatNumber(summary.netProfit)} detail={`仅统计 ${summary.settled} 笔结算，不含浮动盈亏`} color={valueColor(summary.netProfit)} icon={<WalletOutlined />} />
            <AnalysisStat title="结算胜率" value={formatPercent(summary.winRate)} detail={`${summary.winners} 笔盈利 / ${summary.settled} 笔结算`} icon={<TrophyOutlined />} color="#8b70d4" />
            <AnalysisStat title="成交手续费" value={formatNumber(summary.fees)} detail="当前筛选范围内的成交费用" icon={<FileTextOutlined />} color="#c58a30" />
        </div>
        <div className="analysis-filter-card"><div className="analysis-filters">
            <Input className="analysis-filter-query" prefix={<SearchOutlined style={{ color: '#94a3b8' }} />} placeholder="搜索信号、交易动作或日志内容" value={filters.query || ''} allowClear onChange={event => update({ query: event.target.value })} />
            {symbols.length > 1 && <Select aria-label="日志品种" placeholder="全部品种" allowClear value={filters.symbol} onChange={symbol => update({ symbol })} options={symbols.map(symbol => ({ value: symbol, label: symbol }))} style={{ width: 135 }} />}
            <Select aria-label="日志事件类型" placeholder="全部事件" allowClear value={filters.kind} onChange={kind => update({ kind })} options={Object.entries(kinds).map(([value, item]) => ({ value, label: item.label }))} style={{ width: 125 }} />
            <DatePicker.RangePicker aria-label="日志日期范围" value={filters.range || null} onChange={range => update({ range, start: range?.[0]?.format('YYYY-MM-DD'), end: range?.[1]?.format('YYYY-MM-DD') })} />
            <Button type="text" onClick={() => { setFilters({}); setPage(1); }}>重置</Button>
        </div></div>
        <div className="analysis-charts">
            <AnalysisChart title="累计结算净利" subtitle="按当前筛选的结算日志累加，不等同于账户权益" option={profitOption} hasData={summary.points.length > 0} />
            <AnalysisChart title="日志事件分布" subtitle="区分成交、结算与策略信号" option={distributionOption} hasData={summary.count > 0} />
        </div>
        <Card variant="borderless" className="analysis-card" title={<div className="analysis-card-title">交易事件明细<small>原始日志完整保留，成交估算与最终结算分开展示</small></div>} extra={<Tooltip title="导出当前筛选范围"><Button icon={<DownloadOutlined />} disabled={!filtered.length} onClick={() => downloadLogCsv(filtered, filename)}>导出日志</Button></Tooltip>}>
            <div className="analysis-toolbar"><Space><Tag color="blue">{filtered.length} 条记录</Tag><span className="analysis-muted">最新事件优先</span></Space><Segmented aria-label="日志展示方式" value={view} onChange={setView} options={[{ label: '明细表', value: 'table' }, { label: '时间线', value: 'timeline' }]} /></div>
            {view === 'table' ? <Table className="analysis-table" rowKey="key" dataSource={latest} columns={columns} size="middle" scroll={{ x: 1000 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={rows.length ? '没有符合筛选条件的日志' : '这次回测尚无交易日志'} /> }}
                pagination={{ current: page, pageSize, showSizeChanger: true, pageSizeOptions: [20, 50, 100], showTotal: total => `共 ${total} 条`, onChange: (nextPage, size) => { setPage(nextPage); setPageSize(size); } }} />
                : latest.length ? <><Timeline items={latest.slice(0, 40).map(row => ({ color: kinds[row.kind].color, children: <div className="analysis-event">
                    <div className="analysis-event-header"><Tag color={kinds[row.kind].color}>{row.action || kinds[row.kind].label}</Tag><strong>{row.symbol}</strong><span className="analysis-muted">{row.date || '未标时间'}</span>{row.isSettlement && <span className="analysis-num" style={{ color: valueColor(row.pnl) }}>{formatNumber(row.pnl)}</span>}</div>
                    <div className="analysis-event-content">{row.content}</div>{row.isExecution && <div className="analysis-event-metrics"><span>成交价 <b>{formatNumber(row.price)}</b></span><span>数量 <b>{formatNumber(row.size, 0)}</b></span><span>手续费 <b>{formatNumber(row.comm)}</b></span></div>}
                </div> }))} />{latest.length > 40 && <div className="analysis-note">时间线显示最新 40 条事件，完整日志请切换明细表或导出。</div>}</>
                : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有符合条件的事件" />}
        </Card>
    </div>;
}
