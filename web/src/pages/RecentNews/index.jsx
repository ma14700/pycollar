import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Col, Empty, List, Row, Select, Space, Spin, Tag, Typography } from 'antd';
import { ClockCircleOutlined, GlobalOutlined, ReadOutlined, ReloadOutlined } from '@ant-design/icons';
import axios from 'axios';
import MarketQuoteBar from './MarketQuoteBar';
import './style.css';

const categories = [
    { id: 'middle_east', name: '中东', color: 'orange', subtitle: '中东局势 · 伊朗 · 以色列 · 霍尔木兹' },
    { id: 'usa', name: '美国', color: 'blue', subtitle: '美国动态 · 美联储 · 白宫' },
    { id: 'oil', name: '原油', color: 'purple', subtitle: '原油市场 · 油价 · OPEC · 布伦特' },
];
const providerOptions = [
    { value: 'auto', label: '自动（优先外网）' },
    { value: 'domestic', label: '国内（优先金十）' },
    { value: 'jin10', label: '金十快讯（仅金十）' },
    { value: 'eastmoney', label: '东方财富快讯（国内）' },
    { value: 'google', label: 'Google 新闻（外网）' },
];
const savedProvider = () => {
    try {
        const value = localStorage.getItem('recent-news-provider');
        return providerOptions.some(option => option.value === value) ? value : 'auto';
    } catch { return 'auto'; }
};
const formatTime = value => value ? new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
}).format(new Date(value)) : '尚未获取';

const RecentNewsPage = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [pages, setPages] = useState({});
    const request = useRef(null);
    const [provider, setProvider] = useState(savedProvider);

    const loadNews = async (refresh = false) => {
        request.current?.abort();
        const controller = new AbortController();
        request.current = controller;
        setLoading(true);
        setError('');
        // Hide the previous response while fetching so it cannot display an
        // expired headline after crossing the rolling 72-hour boundary.
        setData(null);
        try {
            const response = await axios.get('http://localhost:8000/api/news/recent', {
                params: { refresh, provider }, signal: controller.signal, timeout: 80000,
            });
            if (request.current !== controller) return;
            setData(response.data);
            setPages({});
        } catch (err) {
            if (!axios.isCancel(err) && request.current === controller) {
                setError('消息加载失败，请检查后端服务和网络连接后重试。');
            }
        } finally {
            if (request.current === controller) setLoading(false);
        }
    };

    useEffect(() => {
        try { localStorage.setItem('recent-news-provider', provider); } catch { /* Storage may be disabled. */ }
        loadNews();
        const refreshVisible = () => { if (document.visibilityState === 'visible') loadNews(); };
        const timer = setInterval(refreshVisible, 5 * 60 * 1000);
        document.addEventListener('visibilitychange', refreshVisible);
        return () => {
            request.current?.abort();
            clearInterval(timer);
            document.removeEventListener('visibilitychange', refreshVisible);
        };
    }, [provider]);

    return <div className="recent-news-page">
        <div className="recent-news-header">
            <div>
                <Typography.Title level={3} style={{ margin: '0 0 8px' }}><ReadOutlined /> 近期消息</Typography.Title>
                <Typography.Text type="secondary">最近三天（滚动72小时）的公开新闻，按发布时间从新到旧排列。</Typography.Text>
            </div>
            <Space wrap>
                <Typography.Text>新闻数据源</Typography.Text>
                <Select aria-label="新闻数据源" value={provider} options={providerOptions} onChange={setProvider} style={{ width: 220 }} />
                <Button type="primary" icon={<ReloadOutlined />} loading={loading} onClick={() => loadNews(true)}>刷新消息</Button>
            </Space>
        </div>
        <MarketQuoteBar />
        <Alert type="info" showIcon icon={<ClockCircleOutlined />} message="中东 · 美国 · 原油"
            description={<Space direction="vertical" size={2}>
                <span>时间均为北京时间。每个板块最多展示100条，支持分页；同一报道可能关联多个主题。</span>
                <span>当前数据源：{data?.provider_name || providerOptions.find(option => option.value === provider)?.label}。自动模式优先外网，失败时回退国内；国内模式先取金十，未覆盖的历史由东方财富补充。</span>
                <span>页面每5分钟更新，5分钟内复用缓存，点击刷新可立即重新抓取。国内消息按关键词分类，同一报道可能出现在多个板块。</span>
                {data?.jin10_mcp && <span>金十 MCP：{data.jin10_mcp.configured ? '已配置授权 Token' : '未配置 Token，使用公开快讯'}{data.jin10_mcp.connected ? ` · 协议 ${data.jin10_mcp.negotiated_version} · 已发现 ${data.jin10_mcp.available_tools.length} 个工具` : ''}。{data.jin10_mcp.configured && '国内金十数据使用后端 Bearer 授权连接。'}</span>}
                {provider === 'jin10' && <span>仅金十模式只显示接口实际返回的快讯；历史受限或未取全时会提示。</span>}
                {data && <span>本次筛选范围：{formatTime(data.window_start)} ～ {formatTime(data.window_end)}</span>}
            </Space>} />
        {data?.fallback_reason && <Alert type="warning" showIcon message={data.fallback_reason} />}
        {error && <Alert type="error" showIcon message={error} action={<Button size="small" onClick={() => loadNews(true)}>重试</Button>} />}
        {loading && <div className="recent-news-loading"><Spin size="large" /><Typography.Text type="secondary">正在获取最近三天的消息…</Typography.Text></div>}
        <Row gutter={[20, 20]} align="top">
            {categories.map(category => {
                const result = data?.categories.find(item => item.id === category.id);
                const items = result?.items || [];
                return <Col xs={24} xl={8} key={category.id}>
                    <Card className="recent-news-card" title={<Space><GlobalOutlined /><span>{category.name}</span><Tag color={category.color}>{items.length} 条</Tag></Space>}
                        extra={<Tag>{result?.status === 'error' ? '连接异常' : result?.status === 'stale' ? '上次抓取' : result?.cached ? '缓存' : result?.fetched_at ? '已更新' : '待获取'}</Tag>}>
                        <Typography.Paragraph type="secondary" className="recent-news-subtitle">{category.subtitle}</Typography.Paragraph>
                        {result && <Typography.Paragraph type="secondary" className="recent-news-updated">来源：{result.provider}</Typography.Paragraph>}
                        <Typography.Paragraph type="secondary" className="recent-news-updated">抓取时间：{formatTime(result?.fetched_at)}</Typography.Paragraph>
                        {result?.error && <Alert style={{ marginBottom: 12 }} type={result.status === 'stale' ? 'warning' : 'error'} showIcon message={result.error} />}
                        {result?.warning && <Alert style={{ marginBottom: 12 }} type="warning" showIcon message={result.warning} />}
                        {result?.notice && <Typography.Paragraph type="secondary" className="recent-news-updated">{result.notice}</Typography.Paragraph>}
                        {result?.supplement_fetched_at && <Typography.Paragraph type="secondary" className="recent-news-updated">历史补充抓取时间：{formatTime(result.supplement_fetched_at)}</Typography.Paragraph>}
                        <List dataSource={items} size="small"
                            pagination={items.length > 10 ? { current: pages[category.id] || 1, pageSize: 10, showSizeChanger: false, size: 'small', simple: true,
                                onChange: page => setPages(previous => ({ ...previous, [category.id]: page })) } : false}
                            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={loading ? '正在获取消息' : result?.status === 'error' ? '暂时无法获取消息' : data ? '最近三天暂无相关消息' : '暂无消息，请刷新重试'} /> }}
                            renderItem={item => <List.Item key={item.id} className="recent-news-item">
                                <a className="recent-news-link" href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
                                <div className="recent-news-meta"><span>{item.source}</span><time dateTime={item.published_at}>{formatTime(item.published_at)}</time></div>
                            </List.Item>} />
                    </Card>
                </Col>;
            })}
        </Row>
    </div>;
};

export default RecentNewsPage;
