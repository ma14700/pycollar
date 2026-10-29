import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Empty, Select, Skeleton, Tag } from 'antd';
import { FileTextOutlined, ReloadOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useBacktest } from '../../context/BacktestContext';
import { AnalysisHero } from '../../components/AnalyticsUi';
import TradeLogDashboard from '../../components/TradeLogDashboard';
import { getSymbolLabel } from '../../utils';
import { periodMap, strategyNameMap } from '../../constants';

export default function LogsPage() {
    const { results } = useBacktest();
    const navigate = useNavigate();
    const [selection, setSelection] = useState(results ? 'current' : undefined);
    const [records, setRecords] = useState([]);
    const [detail, setDetail] = useState(null);
    const [listLoading, setListLoading] = useState(true);
    const [loading, setLoading] = useState(false);
    const [listError, setListError] = useState('');
    const [detailError, setDetailError] = useState('');
    const [refresh, setRefresh] = useState(0);

    useEffect(() => {
        const controller = new AbortController();
        setListLoading(true);
        axios.get('http://localhost:8000/api/backtest/list', { signal: controller.signal })
            .then(({ data }) => {
                const items = Array.isArray(data) ? data : [];
                setRecords(items);
                setSelection(previous => previous ?? (results ? 'current' : items.length ? `history:${items[0].id}` : undefined));
                setListError('');
            })
            .catch(failure => { if (!axios.isCancel(failure)) setListError('历史回测记录读取失败，请检查后端连接后刷新。'); })
            .finally(() => { if (!controller.signal.aborted) setListLoading(false); });
        return () => controller.abort();
    }, [refresh, results]);

    useEffect(() => {
        if (!selection || selection === 'current') { setDetail(null); setLoading(false); setDetailError(''); return; }
        const controller = new AbortController();
        setLoading(true); setDetail(null); setDetailError('');
        axios.get(`http://localhost:8000/api/backtest/${selection.split(':')[1]}`, { signal: controller.signal })
            .then(({ data }) => setDetail(data))
            .catch(failure => { if (!axios.isCancel(failure)) setDetailError('这条回测的日志读取失败，请刷新或选择其他记录。'); })
            .finally(() => { if (!controller.signal.aborted) setLoading(false); });
        return () => controller.abort();
    }, [selection, refresh]);

    const activeResults = useMemo(() => selection === 'current' ? results : detail?.detail_data ? {
        ...detail.detail_data, data_info: { ...detail.detail_data.data_info, symbol: detail.detail_data.data_info?.symbol || detail.symbol },
        backtest_request: { strategy_name:detail.strategy_name, ...detail.detail_data.backtest_request },
    } : null, [selection, results, detail]);
    const currentSymbols = results?.isBatch ? [...new Set((results.items || []).map(item => item.data?.data_info?.symbol || item.data?.backtest_request?.symbol || item.symbol).filter(Boolean))]
        : [results?.data_info?.symbol || results?.backtest_request?.symbol].filter(Boolean);
    const currentLabel = currentSymbols.map(getSymbolLabel).join(' / ');
    const options = [
        ...(results ? [{ value: 'current', label: results.isBatch ? `当前批量回测 · ${currentLabel} · ${results.items?.length || 0} 项结果` : `当前回测${currentLabel ? ` · ${currentLabel}` : ''}` }] : []),
        ...records.map(record => ({ value: `history:${record.id}`, label: `#${record.id} · ${getSymbolLabel(record.symbol)} · ${strategyNameMap[record.strategy_name] || record.strategy_name} · ${periodMap[record.period] || record.period}` })),
    ];
    const error = detailError || listError;

    return <div className="analysis-page">
        <AnalysisHero icon={<FileTextOutlined />} eyebrow="策略研究 / 交易复盘" title="交易日志"
            description="从信号到成交，再到结算，回看每一个交易决策。"
            extra={<><Select aria-label="选择日志来源" showSearch optionFilterProp="label" placeholder="搜索合约代码、策略或回测编号" value={selection} options={options} onChange={setSelection} loading={listLoading} style={{ width: 440, maxWidth: '100%' }} /><Button icon={<ReloadOutlined />} loading={listLoading || loading} onClick={() => setRefresh(value => value + 1)}>刷新</Button></>} />
        {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 20 }} />}
        {activeResults && <div className="analysis-toolbar">
            <div><Tag color={selection === 'current' ? 'blue' : 'purple'}>{selection === 'current' ? '当前回测' : `历史记录 #${detail.id}`}</Tag>
                {detail && <><Tag>{getSymbolLabel(detail.symbol)}</Tag><span className="analysis-muted">{strategyNameMap[detail.strategy_name] || detail.strategy_name} · {periodMap[detail.period] || detail.period}</span></>}
            </div><span className="analysis-muted">统计随合约、策略、事件与日期筛选同步更新</span>
        </div>}
        {loading || (!activeResults && listLoading) ? <Card className="analysis-card"><Skeleton active paragraph={{ rows: 8 }} /></Card>
            : activeResults ? <TradeLogDashboard key={selection} results={activeResults} filename={`logs-${detail?.id || 'current'}.csv`} />
                : !error && <Card variant="borderless" className="analysis-card"><Empty description="暂无可查看的回测日志"><Button type="primary" icon={<ArrowRightOutlined />} onClick={() => navigate('/backtest')}>开始一次回测</Button></Empty></Card>}
    </div>;
}
