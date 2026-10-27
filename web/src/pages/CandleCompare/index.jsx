import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Checkbox, Col, DatePicker, Empty, Form, InputNumber, Modal, Row, Select, Space, Statistic, Table, Tag, Typography } from 'antd';
import { FundViewOutlined, SearchOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import axios from 'axios';
import DataProviderSelect from '../../components/DataProviderSelect';
import DataSourceInfo from '../../components/DataSourceInfo';
import { buildCandleOption, buildOverlayOption } from '../../utils/candleCompareCharts';
import { buildFollowingDetails } from '../../utils/candleFollowingDetails';

const { RangePicker } = DatePicker;
const percent = value => value === null ? '-' : <span style={{ color: value >= 0 ? '#cf1322' : '#3f8600' }}>{value > 0 ? '+' : ''}{value.toFixed(2)}%</span>;
const priceFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 6 });
const percentFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 6 });
const priceText = value => Number.isFinite(value) ? priceFormatter.format(value) : '—';
const detailChange = (value, isPercent = false) => !Number.isFinite(value) ? '—' : <span style={{ color: value > 0 ? '#cf1322' : value < 0 ? '#3f8600' : '#8c8c8c', whiteSpace: 'nowrap' }}>{value > 0 ? '+' : ''}{(isPercent ? percentFormatter : priceFormatter).format(value)}{isPercent ? '%' : ''}</span>;

const CandleComparePage = () => {
    const [form] = Form.useForm();
    const [symbols, setSymbols] = useState([]);
    const [symbolError, setSymbolError] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [result, setResult] = useState(null);
    const [selectedRank, setSelectedRank] = useState(1);
    const [detailMatch, setDetailMatch] = useState(null);
    const request = useRef(null);
    const provider = Form.useWatch('data_provider', form) || 'tqsdk';
    const period = Form.useWatch('period', form) || 'daily';
    const selected = result?.matches.find(item => item.rank === selectedRank);
    const comparedMAs = result?.parameters.ma_periods || [];
    const displayedMAs = comparedMAs.length ? comparedMAs : [20, 55, 144];
    const detailRows = buildFollowingDetails(detailMatch);
    const detailColumns = [
        { title: '后第几根', dataIndex: 'sequence', width: 75 },
        { title: '时间', dataIndex: 'date', width: 170, render: value => value || '—' },
        { title: '开盘', dataIndex: 'open', width: 85, align: 'right', render: priceText },
        { title: '收盘', dataIndex: 'close', width: 85, align: 'right', render: priceText },
        { title: '前收', dataIndex: 'previous_close', width: 85, align: 'right', render: priceText },
        { title: '本根收－开', dataIndex: 'body_change', width: 100, align: 'right', render: value => detailChange(value) },
        { title: '较前收涨跌', dataIndex: 'change', width: 100, align: 'right', render: value => detailChange(value) },
        { title: '较前收涨跌幅', dataIndex: 'change_pct', width: 110, align: 'right', render: value => detailChange(value, true) },
        { title: '累计涨跌', dataIndex: 'cumulative_change', width: 100, align: 'right', render: value => detailChange(value) },
        { title: '累计涨跌幅', dataIndex: 'cumulative_pct', width: 110, align: 'right', render: value => detailChange(value, true) },
    ];

    useEffect(() => {
        const controller = new AbortController();
        axios.get('http://localhost:8000/api/symbols', { params: { market_type: 'futures' }, signal: controller.signal })
            .then(({ data }) => {
                const list = data.futures || [];
                setSymbols(list);
                form.setFieldValue('symbol', list.find(item => item.code === 'SH0')?.code || list[0]?.code);
            })
            .catch(err => { if (!axios.isCancel(err)) setSymbolError('品种列表加载失败，请刷新页面重试。'); });
        return () => { controller.abort(); request.current?.abort(); };
    }, [form]);

    useEffect(() => {
        if (provider === 'akshare') form.setFieldsValue({ period: 'daily', data_source: 'main' });
    }, [provider, form]);

    const runComparison = async values => {
        request.current?.abort();
        const controller = new AbortController();
        request.current = controller;
        setLoading(true);
        setError('');
        setResult(null);
        setDetailMatch(null);
        const format = values.period === 'daily' ? 'YYYY-MM-DD' : 'YYYY-MM-DD HH:mm:ss';
        const payload = {
            symbol: values.symbol, period: values.period,
            data_provider: values.data_provider || 'tqsdk', data_source: values.data_source,
            window_size: values.window_size, top_k: values.top_k,
            min_similarity: values.min_similarity, continuation_bars: values.continuation_bars,
            ma_periods: values.ma_periods || [],
            target_end: values.target_end?.format(format),
            search_start: values.search_range?.[0]?.format(format),
            search_end: values.search_range?.[1]?.format(format),
        };
        try {
            const { data } = await axios.post('http://localhost:8000/api/candles/compare', payload, { signal: controller.signal });
            setResult(data);
            setSelectedRank(data.matches[0]?.rank || 1);
        } catch (err) {
            if (!axios.isCancel(err)) {
                const detail = err.response?.data?.detail;
                setError(typeof detail === 'string' ? detail : '对比失败，请检查参数或后端连接。');
            }
        } finally {
            if (request.current === controller) setLoading(false);
        }
    };

    const columns = [
        { title: '排名', dataIndex: 'rank', width: 65 },
        { title: '形态相似度', dataIndex: 'similarity', width: 125, render: value => <Tag color={value >= 80 ? 'green' : 'blue'}>{value.toFixed(2)} 分</Tag> },
        { title: '历史片段起止', render: (_, item) => <div>{item.start}<br />{item.end}</div> },
        { title: '片段涨跌幅', dataIndex: 'return_pct', align: 'right', render: percent },
        { title: `后 ${result?.parameters.continuation_bars || 0} 根实际涨跌`, dataIndex: 'following_return_pct', align: 'right', render: percent },
        { title: '操作', width: 150, fixed: 'right', render: (_, item) => <Space size={4}>
            <Button type={selectedRank === item.rank ? 'primary' : 'link'} size="small" onClick={() => setSelectedRank(item.rank)}>对比</Button>
            <Button type="link" size="small" onClick={event => { event.stopPropagation(); setDetailMatch(item); }}>详情</Button>
        </Space> },
    ];

    return <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div>
            <Typography.Title level={3} style={{ margin: '0 0 8px' }}><FundViewOutlined /> K线对比</Typography.Title>
            <Typography.Text type="secondary">固定根数，寻找同品种、同周期中更早出现过的相似走势。</Typography.Text>
        </div>
        <Card title="对比条件">
            {symbolError && <Alert type="error" showIcon message={symbolError} style={{ marginBottom: 16 }} />}
            <Form form={form} layout="vertical" onFinish={runComparison} initialValues={{ market_type: 'futures', period: 'daily', data_source: 'main', window_size: 50, top_k: 5, min_similarity: 0, continuation_bars: 20, ma_periods: [] }}>
                <Row gutter={20}>
                    <Col xs={24} md={12} xl={6}><DataProviderSelect form={form} /></Col>
                    <Col xs={24} md={12} xl={6}>
                        <Form.Item name="symbol" label="交易品种" rules={[{ required: true, message: '请选择交易品种' }]}>
                            <Select showSearch optionFilterProp="label" placeholder="选择或搜索期货品种" options={symbols.map(item => ({ value: item.code, label: item.name }))} />
                        </Form.Item>
                        <Form.Item name="data_source" label="合约口径"><Select disabled={provider === 'akshare'} options={[{ value: 'main', label: '主力连续' }, { value: 'weighted', label: '加权指数' }]} /></Form.Item>
                    </Col>
                    <Col xs={24} md={12} xl={6}>
                        <Form.Item name="period" label="K线周期"><Select disabled={provider === 'akshare'} options={[{ value: 'daily', label: '日线' }, ...['1', '5', '15', '30', '60'].map(value => ({ value, label: `${value}分钟` }))]} /></Form.Item>
                        <Form.Item name="target_end" label="基准结束时间（可选）" tooltip="留空使用最近已完成的 K 线；指定时间则截取截至该时间的固定根数。">
                            <DatePicker showTime={period !== 'daily'} format={period === 'daily' ? 'YYYY-MM-DD' : 'YYYY-MM-DD HH:mm:ss'} placeholder="最近已完成 K 线" style={{ width: '100%' }} />
                        </Form.Item>
                    </Col>
                    <Col xs={24} md={12} xl={6}>
                        <Form.Item name="window_size" label="固定对比根数" rules={[{ required: true }]}><InputNumber min={10} max={500} precision={0} style={{ width: '100%' }} /></Form.Item>
                        <Form.Item name="continuation_bars" label="后续观察根数" tooltip="展示每段历史匹配之后的实际行情，该部分不参与相似度评分。" rules={[{ required: true }]}><InputNumber min={0} max={200} precision={0} style={{ width: '100%' }} /></Form.Item>
                    </Col>
                </Row>
                <Form.Item name="ma_periods" label="均线辅助对比（可多选）" extra="可单选或全选；不选时仅比较 K 线形态。选中后，K 线占评分的 50%，所选均线合计占 50%，并显示在叠加图与两组 K 线图中。">
                    <Checkbox.Group options={[20, 60, 144].map(value => ({ value, label: `配合 ${value}${period === 'daily' ? '日线' : '周期均线'}对比` }))} />
                </Form.Item>
                <Row gutter={20} align="bottom">
                    <Col xs={24} md={12}><Form.Item name="search_range" label="历史搜索范围（可选）"><RangePicker showTime={period !== 'daily'} format={period === 'daily' ? 'YYYY-MM-DD' : 'YYYY-MM-DD HH:mm:ss'} style={{ width: '100%' }} /></Form.Item></Col>
                    <Col xs={12} md={4}><Form.Item name="min_similarity" label="最低相似度（分）" rules={[{ required: true }]}><InputNumber min={0} max={100} style={{ width: '100%' }} /></Form.Item></Col>
                    <Col xs={12} md={4}><Form.Item name="top_k" label="返回数量" rules={[{ required: true }]}><InputNumber min={1} max={20} precision={0} style={{ width: '100%' }} /></Form.Item></Col>
                    <Col xs={24} md={4}><Form.Item><Button type="primary" htmlType="submit" loading={loading} icon={<SearchOutlined />} block>查找相似走势</Button></Form.Item></Col>
                </Row>
            </Form>
            <Typography.Text type="secondary">统一价格与波动幅度后比较开高低收形态；历史片段及其后续观察区间均早于基准，匹配片段之间互不重叠。相似分数不代表上涨概率。</Typography.Text>
        </Card>
        {error && <Alert type="error" showIcon message="无法完成对比" description={error} />}
        {result ? <>
            <DataSourceInfo info={result.data_info} />
            <Card title="历史相似走势排名" extra={<Typography.Text type="secondary">基准：{result.target.start} ～ {result.target.end}</Typography.Text>}>
                <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
                    <Col xs={12} md={6}><Statistic title="基准 K 线数" value={result.target.bars} /></Col>
                    <Col xs={12} md={6}><Statistic title="有效历史窗口" value={result.scanned_windows} /></Col>
                    <Col xs={12} md={6}><Statistic title="返回独立片段" value={result.matches.length} /></Col>
                    <Col xs={12} md={6}><Statistic title="最高相似度" value={result.matches[0]?.similarity ?? '-'} precision={2} suffix="分" /></Col>
                </Row>
                <Table rowKey="rank" dataSource={result.matches} columns={columns} pagination={false} scroll={{ x: 1000 }} size="middle"
                    rowSelection={{ type: 'radio', selectedRowKeys: selected ? [selected.rank] : [], onChange: keys => setSelectedRank(keys[0]) }}
                    onRow={item => ({ onClick: () => setSelectedRank(item.rank), style: { cursor: 'pointer' } })}
                    locale={{ emptyText: result.message }} />
                <Typography.Paragraph type="secondary" style={{ margin: '16px 0 0' }}>{result.method} 涨跌幅另列展示，成交量不参与本次形态评分。</Typography.Paragraph>
            </Card>
            {selected ? <>
                <Card title="形态叠加（消除价格和波动幅度差异）" extra={<Space><Tag color="blue">基准</Tag><Tag color="purple">历史第 {selected.rank} 名</Tag><Tag color="orange">后续走势见图例</Tag></Space>}>
                    <ReactECharts option={buildOverlayOption(result.target, selected, comparedMAs)} notMerge style={{ height: 360 }} />
                </Card>
                <Row gutter={[20, 20]}>
                    <Col xs={24} xl={12}><Card title={`基准 K 线 · ${result.target.bars} 根`}><ReactECharts option={buildCandleOption(result.target, null, displayedMAs)} notMerge style={{ height: 360 }} /></Card></Col>
                    <Col xs={24} xl={12}><Card title={`历史匹配 · ${selected.bars} 根 + 后续 ${selected.following.bars} 根`}><ReactECharts option={buildCandleOption(selected, selected.following, displayedMAs)} notMerge style={{ height: 360 }} /></Card></Col>
                </Row>
                <Typography.Text type="secondary">{displayedMAs.map(value => `MA${value}`).join('、')} 按当前 K 线周期计算，可点击图例显示或隐藏。叠加图中的均线实线为基准、虚线为历史。均线使用片段之前的历史数据；所选辅助均线历史不足的窗口不参与排名。修改配置后请重新查找，图表和排名以本次查询配置为准。</Typography.Text>
            </> : <Empty description={result.message} />}
        </> : !loading && !error && <Card><Empty description="选择品种、周期和固定根数，查找前期相似行情" /></Card>}
        <Modal open={Boolean(detailMatch)} onCancel={() => setDetailMatch(null)} footer={null} width={1100}
            style={{ maxWidth: 'calc(100vw - 32px)', top: 40 }} title={`历史第 ${detailMatch?.rank ?? ''} 名 · 后续逐根涨跌详情`}>
            {detailMatch && <>
                <Typography.Paragraph>匹配区间：{detailMatch.start} ～ {detailMatch.end}<br />匹配末根收盘：<strong>{priceText(detailMatch.ohlc?.at(-1)?.[1])}</strong>；后续实际 {detailRows.length} 根 K 线。</Typography.Paragraph>
                <Typography.Paragraph type="secondary">较前收涨跌＝本根收盘－前一根收盘，第1根以前述匹配末根收盘为前收。累计涨跌始终以匹配末根收盘为基准。“本根收－开”单独显示该根 K 线实体的涨跌。以下为历史实际数据，不参与相似度评分。</Typography.Paragraph>
                <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
                    <Col span={6}><Statistic title="后续 K 线数" value={detailRows.length} /></Col>
                    <Col span={6}><Statistic title="上涨（较前收）" value={detailRows.filter(row => row.change > 0).length} valueStyle={{ color: '#cf1322' }} /></Col>
                    <Col span={6}><Statistic title="下跌（较前收）" value={detailRows.filter(row => row.change < 0).length} valueStyle={{ color: '#3f8600' }} /></Col>
                    <Col span={6}><Statistic title="平盘（较前收）" value={detailRows.filter(row => row.change === 0).length} /></Col>
                </Row>
                <Table key={detailMatch.rank} rowKey="key" dataSource={detailRows} columns={detailColumns} size="small"
                    pagination={detailRows.length > 20 ? { pageSize: 20, showSizeChanger: false, showTotal: total => `共 ${total} 根` } : false}
                    scroll={{ x: 1025, y: 'min(420px, 50vh)' }}
                    locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本次后续观察根数为0，暂无逐根明细。可设置后续观察根数后重新查找。" /> }} />
            </>}
        </Modal>
    </div>;
};

export default CandleComparePage;
