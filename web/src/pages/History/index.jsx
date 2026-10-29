import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Alert, Button, Card, DatePicker, Descriptions, Empty, Input, Modal, Popconfirm, Radio, Select, Space, Table, Tabs, Tag, Tooltip, message } from 'antd';
import { ReloadOutlined, HistoryOutlined, DeleteOutlined, ArrowLeftOutlined, LineChartOutlined, SearchOutlined, TrophyOutlined, RiseOutlined, FundOutlined, EyeOutlined, SwapOutlined } from '@ant-design/icons';
import axios from 'axios';
import { strategyNameMap, periodMap } from '../../constants';
import { getSymbolLabel } from '../../utils';
import MetricsPanel from '../../components/MetricsPanel';
import ChartPanel from '../../components/ChartPanel';
import DataSourceInfo from '../../components/DataSourceInfo';
import TradeLogDashboard from '../../components/TradeLogDashboard';
import { AnalysisHero, AnalysisStat, AnalysisChart } from '../../components/AnalyticsUi';
import { normalizeHistoryRecord, filterHistoryRecords, summarizeHistory, formatNumber, formatPercent, valueColor, finiteNumber, normalizedEquity } from '../../utils/backtestAnalytics';

const savedTime = value => value === null ? '—' : new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false });
const tooltip = { trigger: 'item', renderMode: 'richText', backgroundColor: '#fff', borderColor: '#e5eaf2', textStyle: { color: '#475569', fontSize: 12 } };
const parameterLabels = { entry_delay_bars: '开仓 K 线', exit_delay_bars: '平仓 K 线', fast_period: '快线周期', slow_period: '入场慢线周期', exit_period: '离场均线周期', fixed_size: '固定手数', size_mode: '开仓模式', margin_rate: '保证金率', contract_multiplier: '合约乘数', atr_period: 'ATR 周期', atr_multiplier: 'ATR 倍数', risk_per_trade: '单笔风险比例', equity_percent: '资金比例', start_date: '开始日期', end_date: '结束日期', optimal_entry: '开仓最优模式' };

export default function HistoryPage() {
    const [records, setRecords] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [filters, setFilters] = useState({});
    const [selectedIds, setSelectedIds] = useState([]);
    const [viewing, setViewing] = useState(null);
    const [loadingId, setLoadingId] = useState(null);
    const [detailTab, setDetailTab] = useState('overview');
    const [chartType, setChartType] = useState('line');
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(10);
    const [compareOpen, setCompareOpen] = useState(false);
    const [compareLoading, setCompareLoading] = useState(false);
    const [comparisons, setComparisons] = useState([]);
    const [compareError, setCompareError] = useState('');
    const detailRequest = useRef(null);
    const detailResults = useMemo(() => viewing?.detail_data ? {
        ...viewing.detail_data, data_info: { ...viewing.detail_data.data_info, symbol: viewing.detail_data.data_info?.symbol || viewing.symbol },
        backtest_request: { strategy_name:viewing.strategy_name, ...viewing.detail_data.backtest_request },
    } : null, [viewing]);

    const loadRecords = async () => {
        setLoading(true); setError('');
        try {
            const { data } = await axios.get('http://localhost:8000/api/backtest/list');
            setRecords((Array.isArray(data) ? data : []).map(record => normalizeHistoryRecord({ ...record,
                strategyLabel: strategyNameMap[record.strategy_name] || record.strategy_name,
                symbolLabel: getSymbolLabel(record.symbol),
            })));
        } catch { setError('获取回测记录失败，请检查后端连接后重试。'); }
        finally { setLoading(false); }
    };
    useEffect(() => { loadRecords(); return () => detailRequest.current?.abort(); }, []);
    const filtered = useMemo(() => filterHistoryRecords(records, filters), [records, filters]);
    const summary = useMemo(() => summarizeHistory(filtered), [filtered]);
    const ranked = useMemo(() => filtered.filter(record => record.returnPct !== null).sort((a, b) => b.returnPct - a.returnPct).slice(0, 12).reverse(), [filtered]);
    const risks = useMemo(() => filtered.filter(record => record.returnPct !== null && record.drawdownPct !== null), [filtered]);
    useEffect(() => {
        setSelectedIds(previous => {
            const next = previous.filter(id => filtered.some(record => record.id === id));
            return next.length === previous.length ? previous : next;
        });
    }, [filtered]);
    const update = next => { setFilters(previous => ({ ...previous, ...next })); setPage(1); };

    const openDetail = async (id, tab = 'overview') => {
        detailRequest.current?.abort();
        const controller = new AbortController(); detailRequest.current = controller;
        setLoadingId(id);
        try {
            const { data } = await axios.get(`http://localhost:8000/api/backtest/${id}`, { signal: controller.signal });
            setViewing(data); setDetailTab(tab); setChartType('line');
        } catch (failure) { if (!axios.isCancel(failure)) message.error('获取详情失败，请重试。'); }
        finally { if (!controller.signal.aborted) setLoadingId(null); }
    };
    const deleteRecord = async id => {
        try { await axios.delete(`http://localhost:8000/api/backtest/${id}`); message.success('记录已删除'); await loadRecords(); }
        catch { message.error('删除失败，请重试。'); }
    };
    const compareRecords = async () => {
        setCompareOpen(true); setCompareLoading(true); setComparisons([]); setCompareError('');
        const responses = await Promise.allSettled(selectedIds.map(id => axios.get(`http://localhost:8000/api/backtest/${id}`)));
        const successful = responses.flatMap((response, index) => response.status === 'fulfilled' ? [{ ...records.find(record => record.id === selectedIds[index]), detail: response.value.data }] : []);
        setComparisons(successful);
        if (successful.length !== selectedIds.length) setCompareError('部分回测详情读取失败，当前仅展示成功读取的记录。');
        setCompareLoading(false);
    };
    const rankOption = {
        tooltip: { ...tooltip, formatter: params => `${params.data.recordLabel}\n收益率  ${formatPercent(params.value)}\n点击查看回测详情` },
        grid: { left: 110, right: 64, top: 8, bottom: 28 },
        xAxis: { type: 'value', axisLabel: { color: '#8b96a8', formatter: '{value}%' }, splitLine: { lineStyle: { color: '#edf1f7', type: 'dashed' } } },
        yAxis: { type: 'category', data: ranked.map(record => `#${record.id} ${record.symbolLabel}`), axisLabel: { color: '#64748b', fontSize: 11, width: 100, overflow: 'truncate' }, axisLine: { show: false }, axisTick: { show: false } },
        series: [{ type: 'bar', barMaxWidth: 13, data: ranked.map(record => ({ value: Number(record.returnPct.toFixed(2)), recordId: record.id,
            recordLabel: `#${record.id} ${record.symbolLabel} · ${record.strategyLabel}`, itemStyle: { color: record.returnPct > 0 ? '#e5767f' : record.returnPct < 0 ? '#53b79a' : '#94a3b8', borderRadius: 3 } })),
            label: { show: true, position: 'right', color: '#64748b', fontSize: 11, formatter: '{c}%' } }],
    };
    const riskOption = {
        tooltip: { ...tooltip, formatter: params => `${params.data.recordLabel}\n收益率  ${formatPercent(params.value[1])}\n最大回撤  ${formatPercent(params.value[0])}\n点击查看回测详情` },
        grid: { left: 55, right: 30, top: 28, bottom: 45 },
        xAxis: { type: 'value', name: '回撤 %', min: 0, nameTextStyle: { color: '#8b96a8', padding: [0, 0, 0, -20] }, axisLabel: { color: '#8b96a8' }, splitLine: { lineStyle: { color: '#edf1f7', type: 'dashed' } } },
        yAxis: { type: 'value', name: '收益 %', nameTextStyle: { color: '#8b96a8' }, axisLabel: { color: '#8b96a8' }, splitLine: { lineStyle: { color: '#edf1f7', type: 'dashed' } } },
        series: [{ type: 'scatter', symbolSize: 14, data: risks.map(record => ({ value: [record.drawdownPct, record.returnPct], recordId: record.id,
            recordLabel: `#${record.id} ${record.symbolLabel} · ${record.strategyLabel}`, itemStyle: { color: valueColor(record.returnPct), opacity: .75, borderColor: '#fff', borderWidth: 2 } })) }],
    };
    const chartEvents = { click: params => { if (params.data?.recordId) openDetail(params.data.recordId); } };
    const comparisonSeries = comparisons.map((record, index) => ({ name: `#${record.id} ${record.symbolLabel}`, type: 'line', showSymbol: false,
        data: normalizedEquity(record.detail), lineStyle: { width: 2 }, itemStyle: { color: ['#4f7ff1', '#a075cf', '#d99b39', '#21a390'][index] } }));
    const compareOption = {
        tooltip: { trigger: 'axis', renderMode: 'richText', valueFormatter: value => formatPercent(Array.isArray(value) ? value[1] : value) },
        legend: { top: 4, icon: 'circle', textStyle: { color: '#64748b' } },
        grid: { left: 60, right: 25, top: 55, bottom: 55 },
        xAxis: { type: 'time', axisLabel: { color: '#8b96a8' }, splitLine: { show: false } },
        yAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: '#8b96a8' }, splitLine: { lineStyle: { color: '#edf1f7', type: 'dashed' } } },
        dataZoom: [{ type: 'inside' }, { type: 'slider', height: 15, bottom: 4 }], series: comparisonSeries,
    };
    const columns = [
        { title: '回测记录', key: 'record', width: 260, render: (_, record) => <><button className="analysis-record-title" onClick={() => openDetail(record.id)}>{record.strategyLabel}</button><div className="analysis-muted" style={{ marginTop: 5 }}>#{record.id} · {record.symbolLabel} <Tag style={{ marginLeft: 6 }}>{periodMap[record.period] || record.period}</Tag></div></> },
        { title: '收益率', dataIndex: 'returnPct', width: 125, align: 'right', sorter: (a, b) => (a.returnPct ?? -Infinity) - (b.returnPct ?? -Infinity), render: value => <span className="analysis-num" style={{ color: valueColor(value) }}>{formatPercent(value)}</span> },
        { title: '净利润', dataIndex: 'netProfit', width: 140, align: 'right', sorter: (a, b) => (a.netProfit ?? -Infinity) - (b.netProfit ?? -Infinity), render: value => <span className="analysis-num" style={{ color: valueColor(value) }}>{formatNumber(value)}</span> },
        { title: '最大回撤', dataIndex: 'drawdownPct', width: 110, align: 'right', sorter: (a, b) => (a.drawdownPct ?? Infinity) - (b.drawdownPct ?? Infinity), render: value => <span style={{ color: '#b68b3e' }}>{formatPercent(value)}</span> },
        { title: '胜率', dataIndex: 'winRatePct', width: 140, render: value => value === null ? '—' : <div className="analysis-win-rate"><span className="analysis-win-track"><span style={{ width: `${Math.min(100, Math.max(0, value))}%` }} /></span><span>{formatNumber(value, 1)}%</span></div> },
        { title: '交易次数', dataIndex: 'total_trades', width: 90, align: 'right', render: value => formatNumber(value, 0) },
        { title: '保存时间 · 北京', dataIndex: 'savedAt', width: 165, sorter: (a, b) => (a.savedAt ?? 0) - (b.savedAt ?? 0), render: value => <span className="analysis-muted">{savedTime(value)}</span> },
        { title: '操作', key: 'action', fixed: 'right', width: 155, render: (_, record) => <Space size={4}>
            <Button type="text" size="small" icon={<EyeOutlined />} loading={loadingId === record.id} onClick={() => openDetail(record.id)}>详情</Button>
            <Tooltip title="交易复盘"><Button type="text" size="small" aria-label={`查看记录 ${record.id} 的日志`} icon={<HistoryOutlined />} onClick={() => openDetail(record.id, 'logs')} /></Tooltip>
            <Popconfirm title="删除这条回测记录？" description="删除后无法在历史记录中恢复。" onConfirm={() => deleteRecord(record.id)} okText="删除" cancelText="取消"><Button type="text" size="small" danger aria-label={`删除记录 ${record.id}`} icon={<DeleteOutlined />} /></Popconfirm>
        </Space> },
    ];

    if (viewing) {
        const rawMetrics = { ...viewing.metrics, ...viewing.detail_data?.metrics };
        const metrics = Object.fromEntries(Object.entries(rawMetrics).map(([key, value]) => [key, finiteNumber(value)]));
        return <div className="analysis-page">
            <AnalysisHero icon={<FundOutlined />} eyebrow={`回测档案 / #${viewing.id}`} title={strategyNameMap[viewing.strategy_name] || viewing.strategy_name}
                description={`${getSymbolLabel(viewing.symbol)} · ${periodMap[viewing.period] || viewing.period} · ${savedTime(normalizeHistoryRecord(viewing).savedAt)}`}
                extra={<Button icon={<ArrowLeftOutlined />} onClick={() => setViewing(null)}>返回历史记录</Button>} />
            <DataSourceInfo info={viewing.detail_data?.data_info} />
            <Tabs className="analysis-detail-tabs" activeKey={detailTab} onChange={setDetailTab} items={[
                { key: 'overview', label: '回测概览', children: <div className="analysis-stack"><MetricsPanel metrics={metrics} />
                    <Card variant="borderless" className="analysis-card" title={<div className="analysis-card-title">{chartType === 'line' ? '账户权益曲线' : chartType === 'kline' ? 'K 线与交易信号' : '盈亏分布'}</div>}
                        extra={<Radio.Group size="small" value={chartType} onChange={event => setChartType(event.target.value)} optionType="button" buttonStyle="solid" options={[{ label: '权益', value: 'line' }, { label: 'K 线', value: 'kline' }, { label: '盈亏', value: 'pie' }]} />}>
                        <ChartPanel chartType={chartType} results={{ ...viewing.detail_data, metrics }} />
                    </Card></div> },
                { key: 'logs', label: '交易复盘', children: <TradeLogDashboard results={detailResults} filename={`history-${viewing.id}-logs.csv`} /> },
                { key: 'params', label: '策略参数', children: <Card variant="borderless" className="analysis-card"><Descriptions column={{ xs: 1, sm: 2, lg: 3 }} bordered size="small" items={Object.entries(viewing.strategy_params || {}).map(([key, value]) => ({ key, label: parameterLabels[key] || key, children: value === null ? '—' : typeof value === 'boolean' ? value ? '是' : '否' : String(value) }))} /></Card> },
            ]} />
        </div>;
    }

    return <div className="analysis-page">
        <AnalysisHero icon={<HistoryOutlined />} eyebrow="策略研究 / 回测档案" title="回测历史记录" description="比较收益与风险，筛选值得进一步复盘的策略。"
            extra={<><Tag color="blue">{records.length} 条已保存记录</Tag><Button icon={<ReloadOutlined />} loading={loading} onClick={loadRecords}>刷新记录</Button></>} />
        {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 20 }} />}
        <div className="analysis-stats">
            <AnalysisStat title="当前回测记录" value={formatNumber(summary.count, 0)} detail={`覆盖 ${new Set(filtered.map(record => record.symbol)).size} 个品种`} icon={<HistoryOutlined />} loading={loading} />
            <AnalysisStat title="盈利记录占比" value={formatPercent(summary.profitablePct)} detail={`${summary.profitable} 条盈利 / ${summary.known} 条可统计记录`} icon={<RiseOutlined />} color="#8b70d4" loading={loading} />
            <AnalysisStat title="平均单次收益率" value={formatPercent(summary.averageReturn)} detail="当前筛选记录的等权平均" icon={<LineChartOutlined />} color={valueColor(summary.averageReturn)} loading={loading} />
            <AnalysisStat title="最佳单次收益率" value={formatPercent(summary.best?.returnPct)} detail={summary.best ? `#${summary.best.id} · ${summary.best.symbolLabel}` : '暂无可统计的收益数据'} icon={<TrophyOutlined />} color={valueColor(summary.best?.returnPct)} loading={loading} />
        </div>
        <div className="analysis-filter-card"><div className="analysis-filters">
            <Input className="analysis-filter-query" prefix={<SearchOutlined style={{ color: '#94a3b8' }} />} placeholder="搜索策略、合约代码或记录编号" allowClear value={filters.query || ''} onChange={event => update({ query: event.target.value })} />
            <Select aria-label="历史策略" placeholder="全部策略" style={{ width: 210 }} allowClear value={filters.strategy} onChange={strategy => update({ strategy })} options={[...new Set(records.map(record => record.strategy_name))].map(value => ({ value, label: strategyNameMap[value] || value }))} />
            <Select aria-label="历史品种" placeholder="全部合约 / 品种" style={{ width: 190 }} showSearch optionFilterProp="label" allowClear value={filters.symbol} onChange={symbol => update({ symbol })} options={[...new Set(records.map(record => record.symbol))].map(value => ({ value, label: getSymbolLabel(value) }))} />
            <Select aria-label="盈亏结果" placeholder="全部盈亏" style={{ width: 120 }} allowClear value={filters.outcome} onChange={outcome => update({ outcome })} options={[{ value: 'profit', label: '盈利' }, { value: 'loss', label: '亏损' }, { value: 'flat', label: '持平' }]} />
            <DatePicker.RangePicker aria-label="记录保存日期" value={filters.range || null} onChange={range => update({ range, start: range?.[0]?.format('YYYY-MM-DD'), end: range?.[1]?.format('YYYY-MM-DD') })} />
            <Button type="text" onClick={() => { setFilters({}); setPage(1); }}>重置</Button>
        </div></div>
        <div className="analysis-charts">
            <AnalysisChart title="收益率排名" subtitle="当前筛选中收益率最高的 12 条记录 · 点击条形查看详情" option={rankOption} hasData={ranked.length > 0} height={300} onEvents={chartEvents} loading={loading} />
            <AnalysisChart title="收益与回撤" subtitle="同等收益下，越靠左代表历史最大回撤越小" option={riskOption} hasData={risks.length > 0} height={300} onEvents={chartEvents} loading={loading} />
        </div>
        <div className="analysis-note">统计与图表基于当前筛选。每条回测独立计算，平均收益率不代表组合收益；保存日期以北京时间显示。</div>
        <Card variant="borderless" className="analysis-card" title={<div className="analysis-card-title">回测档案<small>勾选 2～4 条记录，对比以各自初始资金为基准的权益收益率</small></div>}
            extra={<Button type="primary" icon={<SwapOutlined />} disabled={selectedIds.length < 2} onClick={compareRecords}>对比所选{selectedIds.length ? ` (${selectedIds.length}/4)` : ''}</Button>}>
            <Table className="analysis-table" rowKey="id" loading={loading} dataSource={filtered} columns={columns} scroll={{ x: 1340 }}
                rowSelection={{ selectedRowKeys: selectedIds, onChange: keys => setSelectedIds(keys.slice(0, 4)), getCheckboxProps: record => ({ disabled: selectedIds.length >= 4 && !selectedIds.includes(record.id) }) }}
                pagination={{ current: page, pageSize, showSizeChanger: true, pageSizeOptions: [10, 20, 50], showTotal: total => `共 ${total} 条记录`, onChange: (nextPage, size) => { setPage(nextPage); setPageSize(size); } }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={records.length ? '没有符合筛选条件的回测记录' : '暂无保存的回测，请先运行并保存一次回测'} /> }} />
        </Card>
        <Modal title="回测对比" open={compareOpen} onCancel={() => setCompareOpen(false)} footer={<Button onClick={() => setCompareOpen(false)}>关闭</Button>} width={1100} destroyOnClose>
            {compareError && <Alert type="warning" showIcon message={compareError} style={{ marginBottom: 16 }} />}
            <p className="analysis-note">各曲线按“权益 ÷ 各自初始资金 − 1”归一化。回测日期或周期不同，请结合图例和参数判断。</p>
            <AnalysisChart title="归一化权益收益率" subtitle="拖动底部滑块查看区间，点击图例显示或隐藏曲线" height={350} option={compareOption} hasData={comparisonSeries.some(series => series.data.length)} loading={compareLoading} />
            {!compareLoading && comparisons.some(record => !normalizedEquity(record.detail).length) && <Alert type="info" message="部分旧记录缺少权益曲线或有效初始资金，无法绘制对比曲线。" style={{ marginTop: 16 }} />}
            <Table size="small" style={{ marginTop: 18 }} rowKey="id" pagination={false} dataSource={comparisons} scroll={{ x: 700 }} columns={[
                { title: '记录', render: (_, record) => <><b>#{record.id} {record.symbolLabel}</b><div className="analysis-muted">{record.strategyLabel} · {periodMap[record.period] || record.period}</div></> },
                { title: '收益率', dataIndex: 'returnPct', align: 'right', render: value => <span style={{ color: valueColor(value) }}>{formatPercent(value)}</span> },
                { title: '最大回撤', dataIndex: 'drawdownPct', align: 'right', render: formatPercent },
                { title: '胜率', dataIndex: 'winRatePct', align: 'right', render: formatPercent },
                { title: '净利润', dataIndex: 'netProfit', align: 'right', render: value => formatNumber(value) },
            ]} />
        </Modal>
    </div>;
}
