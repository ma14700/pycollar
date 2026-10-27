import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Col, Row, Space, Statistic, Tag, Typography } from 'antd';
import { DollarCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import axios from 'axios';

const instruments = [{ code: 'UKOIL', name: '布伦特原油', unit: '美元/桶' }, { code: 'USOIL', name: 'WTI 原油', unit: '美元/桶' }, { code: 'XAGUSD', name: '现货白银', unit: '美元/盎司' }];
const AUTO_REFRESH_SECONDS = 240;
const formatTime = value => value ? new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
}).format(new Date(value)) : '尚未获取';
const formatNumber = (value, precision) => typeof value === 'number' && Number.isFinite(value)
    ? new Intl.NumberFormat('zh-CN', { minimumFractionDigits: precision ?? 0, maximumFractionDigits: precision ?? 6 }).format(value) : '—';
const signed = (value, precision) => `${value > 0 ? '+' : ''}${formatNumber(value, precision)}`;
const color = value => value > 0 ? '#cf1322' : value < 0 ? '#389e0d' : '#595959';

const MarketQuoteBar = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const request = useRef(null);

    const load = async (refresh = false) => {
        request.current?.abort();
        const controller = new AbortController();
        request.current = controller;
        setLoading(true);
        setError('');
        // Never leave an earlier successful price labeled current while a
        // refresh is pending or has failed.
        setData(null);
        try {
            const response = await axios.get('http://localhost:8000/api/market/quotes', {
                params: { refresh }, signal: controller.signal, timeout: 75000,
            });
            if (request.current === controller) setData(response.data);
        } catch (err) {
            if (!axios.isCancel(err) && request.current === controller) setError('行情暂时获取失败，请稍后刷新。');
        } finally {
            if (request.current === controller) setLoading(false);
        }
    };

    useEffect(() => {
        load();
        const refreshVisible = () => { if (document.visibilityState === 'visible') load(); };
        const timer = setInterval(refreshVisible, AUTO_REFRESH_SECONDS * 1000);
        document.addEventListener('visibilitychange', refreshVisible);
        return () => {
            request.current?.abort();
            clearInterval(timer);
            document.removeEventListener('visibilitychange', refreshVisible);
        };
    }, []);

    return <Card className="market-quote-panel" title={<Space><DollarCircleOutlined />原油与白银行情</Space>}
        extra={<Space wrap><Typography.Text type="secondary">每{AUTO_REFRESH_SECONDS / 60}分钟更新</Typography.Text><Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={() => load(true)}>刷新行情</Button></Space>}>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>来源：金十 MCP · 原油：美元/桶 · 白银：美元/盎司 · 时间均为北京时间，具体行情口径以金十品种代码为准。</Typography.Paragraph>
        {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
        <Row gutter={[16, 16]}>
            {instruments.map(instrument => {
                const quote = data?.quotes.find(item => item.code === instrument.code);
                const precision = quote?.precision ?? 3;
                const status = loading ? '获取中' : quote?.status === 'stale' ? '上次报价' : quote?.status === 'error' ? '连接异常' : quote?.delayed ? '报价较早' : quote?.cached ? '缓存' : quote ? '已更新' : '待获取';
                return <Col xs={24} md={12} xl={8} key={instrument.code}>
                    <Card size="small" className="market-quote-card" title={<Space><span>{instrument.name}</span><Typography.Text type="secondary">{instrument.code}</Typography.Text></Space>}
                        extra={<Tag color={quote?.status === 'stale' || quote?.delayed ? 'orange' : quote?.status === 'error' ? 'red' : undefined}>{status}</Tag>}>
                        <div className="market-quote-price">
                            <Statistic title={quote?.status === 'stale' ? '上次获取的价格' : '最新报价'} value={quote?.close ?? '—'} precision={precision} valueStyle={{ color: color(quote?.ups_price), fontSize: 32 }} suffix={quote?.close != null ? <span style={{ fontSize: 14 }}>{quote.unit || instrument.unit}</span> : null} />
                            <div className="market-quote-change" style={{ color: color(quote?.ups_price) }}>
                                <div>涨跌 {signed(quote?.ups_price, precision)}</div>
                                <div>涨跌幅 {signed(quote?.ups_percent)}{quote?.ups_percent != null ? '%' : ''}</div>
                            </div>
                        </div>
                        <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
                            {[['今开', quote?.open], ['最高', quote?.high], ['最低', quote?.low], ['成交量', quote?.volume]].map(([label, value]) => <Col span={6} key={label}><Typography.Text type="secondary">{label}</Typography.Text><div>{formatNumber(value, label === '成交量' ? undefined : precision)}</div></Col>)}
                        </Row>
                        <Typography.Paragraph type="secondary" className="market-quote-time">报价时间：{formatTime(quote?.time)}<br />获取时间：{formatTime(quote?.fetched_at)}</Typography.Paragraph>
                        {quote?.delayed && <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>报价时间较早，可能处于休市或数据延迟，请以时间戳为准。</Typography.Paragraph>}
                        {quote?.error && <Alert type={quote.status === 'stale' ? 'warning' : 'error'} showIcon message={quote.error} style={{ marginTop: 12 }} />}
                    </Card>
                </Col>;
            })}
        </Row>
    </Card>;
};

export default MarketQuoteBar;
