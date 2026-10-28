import React, { useState, useEffect, useRef } from 'react';
import { Card, Form, InputNumber, Select, Button, Row, Col, message, Table, Modal, Tag, Switch, Tooltip, Alert, Collapse } from 'antd';
import { PlayCircleOutlined, LineChartOutlined } from '@ant-design/icons';
import axios from 'axios';
import ChartPanel from '../../components/ChartPanel';
import DataProviderSelect from '../../components/DataProviderSelect';
import DataSourceInfo from '../../components/DataSourceInfo';
import { tomorrowStrategyOptions, strategyParameterKeys, buildTomorrowAnalysisRequest, getTomorrowDetailRequest, buildTomorrowDetailChart } from '../../utils/tomorrowStrategy';

const { Option } = Select;

const TomorrowStrategy = () => {
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState([]);
    const [futuresList, setFuturesList] = useState([]);
    const [stockList, setStockList] = useState([]);
    const [symbols, setSymbols] = useState([]);
    const [form] = Form.useForm();
    const [strategyType, setStrategyType] = useState('TrendFollowingStrategy');
    const [detailVisible, setDetailVisible] = useState(false);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailResult, setDetailResult] = useState(null);
    const [currentDetailSymbol, setCurrentDetailSymbol] = useState(null);
    const detailRequestId = useRef(0);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [futuresRes, stockRes] = await Promise.all([
                    axios.get('http://localhost:8000/api/symbols?market_type=futures'),
                    axios.get('http://localhost:8000/api/symbols?market_type=stock')
                ]);
                const fList = futuresRes.data.futures || [];
                const sList = stockRes.data.stocks || [];
                setFuturesList(fList);
                setStockList(sList);
                
                // Initialize
                setSymbols(fList);
                form.setFieldsValue({ 
                    market_type: 'futures',
                    period: 'daily',
                    strategy_name: 'TrendFollowingStrategy',
                    symbols: fList.slice(0, 5).map(s => s.code),
                    fast_period: 10,
                    slow_period: 30,
                    use_expma: false,
                    fixed_size: 20,
                    margin_rate: 0.12
                });
            } catch (err) {
                console.error(err);
                message.error('无法连接到后端服务');
            }
        };
        fetchData();
    }, []);

    const handleMarketChange = (val) => {
        const list = val === 'stock' ? stockList : futuresList;
        setSymbols(list || []);
        form.setFieldsValue({ symbols: [] });
        if (val === 'stock') form.setFieldsValue({ data_provider: 'akshare', data_source: 'main' });
        else form.setFieldsValue({ data_provider: 'tqsdk' });
        setResults([]);
    };

    const onFinish = async (values) => {
        setLoading(true);
        try {
            const payload = buildTomorrowAnalysisRequest(values);

            const res = await axios.post('http://localhost:8000/api/strategy/batch-analyze', payload);
            const rows = res.data.results || [];
            setResults(rows);
            const errors = rows.filter(row => row.error);
            if (errors.length === rows.length && errors.length) message.error(errors[0].error);
            else if (errors.length) message.warning(`分析完成，${errors.length} 个品种取数失败，请查看行情状态`);
            else message.success('分析完成');
        } catch (err) {
            console.error(err);
            message.error('分析失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            setLoading(false);
        }
    };

    const showDetail = async (record) => {
        const requestId = ++detailRequestId.current;
        setDetailVisible(true);
        setDetailLoading(true);
        setCurrentDetailSymbol(record.symbol);
        setDetailResult(null);
        try {
            const payload = getTomorrowDetailRequest(record);
            const res = await axios.post('http://localhost:8000/api/strategy/detail', payload);
            if (requestId === detailRequestId.current) setDetailResult(buildTomorrowDetailChart(res.data));
        } catch (err) {
            if (requestId === detailRequestId.current) message.error('加载详情失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            if (requestId === detailRequestId.current) setDetailLoading(false);
        }
    };

    const columns = [
        { title: '品种代码', dataIndex: 'symbol', key: 'symbol' },
        { 
            title: '交易品种', 
            dataIndex: 'symbol', 
            key: 'variety_name',
            render: (text) => {
                const item = futuresList.find(f => f.code === text) || stockList.find(s => s.code === text);
                return item ? item.name : text;
            }
        },
        {
            title: '最新价格',
            dataIndex: 'price',
            key: 'price',
            render: (text, record) => {
                if (record.error) {
                    return <Tooltip title={record.error}><span style={{color: 'red'}}>Error</span></Tooltip>;
                }
                return text;
            }
        },
        { 
            title: '持仓方向', 
            dataIndex: 'direction', 
            key: 'direction',
            render: (text) => {
                let color = 'default';
                let style = {};
                if (text === '多') {
                    color = '#f5222d'; // 红色
                    style = { fontWeight: 'bold', fontSize: '14px' };
                }
                if (text === '空') {
                    color = '#52c41a'; // 绿色
                    style = { fontWeight: 'bold', fontSize: '14px' };
                }
                return <Tag color={color} style={style}>{text}</Tag>;
            }
        },
        { title: '上次开仓价', dataIndex: 'entry_price', key: 'entry_price' },
        {
            title: '行情状态', key: 'data_status',
            render: (_, record) => record.error
                ? <Tooltip title={record.error}><Tag color="error">取数失败</Tag></Tooltip>
                : <Tooltip title={record.data_info?.end}><Tag>{record.data_info?.provider_name || '原有行情'}</Tag></Tooltip>,
        },
        {
            title: '持有K线数',
            dataIndex: 'hold_bars',
            key: 'hold_bars',
            render: (text, record) => {
                if (!record.size || record.size === 0) return '-';

                // 多单红色，空单绿色
                const color = record.size > 0 ? '#f5222d' : '#52c41a';
                return <span style={{ color, fontWeight: 'bold' }}>{text}</span>;
            }
        },
        {
            title: '盈利点数',
            dataIndex: 'profit_points',
            key: 'profit_points',
            render: (text, record) => {
                if (text === '-' || text === 0) return <span style={{color: '#ccc'}}>-</span>;
                const val = parseFloat(text);
                if (isNaN(val)) return <span style={{color: '#ccc'}}>-</span>;

                // 盈利显示红色，亏损显示绿色
                const color = val > 0 ? '#ff4d4f' : (val < 0 ? '#52c41a' : '#ccc');
                // 保留两位小数
                return <span style={{ color, fontWeight: 'bold' }}>{val.toFixed(2)}</span>;
            }
        },
        {
            title: '操作',
            key: 'action',
            render: (_, record) => (
                <Button type="link" icon={<LineChartOutlined />} disabled={loading || !!record.error} onClick={() => showDetail(record)}>
                    详情
                </Button>
            ),
        },
    ];

    return (
        <div style={{ padding: 24, height: '100vh', display: 'flex', flexDirection: 'column' }}>
            <Row gutter={24} style={{ flex: 1, overflow: 'hidden' }}>
                <Col span={6} style={{ height: '100%', overflowY: 'auto' }}>
                    <Card title="策略配置" bordered={false}>
                        <Form form={form} layout="vertical" onFinish={onFinish}>
                            <Form.Item name="market_type" label="市场类型">
                                <Select onChange={handleMarketChange}>
                                    <Option value="futures">期货</Option>
                                    <Option value="stock">股票</Option>
                                </Select>
                            </Form.Item>
                            <DataProviderSelect form={form} />
                            <Form.Item name="data_source" label="合约口径" initialValue="main">
                                <Select options={[{ value: 'main', label: '主力连续' }, { value: 'weighted', label: '加权指数' }]} />
                            </Form.Item>

                            <Form.Item 
                                name="symbols" 
                                label="交易品种 (多选)" 
                                rules={[{ required: true, message: '请选择品种' }]}
                            >
                                <Select mode="multiple" placeholder="选择品种" allowClear maxTagCount="responsive" style={{ width: '100%' }}>
                                    {symbols.map(s => (
                                        <Option key={s.code} value={s.code}>{s.name}</Option>
                                    ))}
                                </Select>
                            </Form.Item>

                            <Form.Item name="strategy_name" label="策略选择">
                                <Select options={tomorrowStrategyOptions} onChange={(val) => {
                                    setStrategyType(val);
                                    const defaults = tomorrowStrategyOptions.find(option => option.value === val).defaults;
                                    form.setFieldsValue({ ...Object.fromEntries(strategyParameterKeys.map(key => [key, undefined])), ...defaults });
                                }} />
                            </Form.Item>

                            <Form.Item name="period" label="K线周期">
                                <Select>
                                    <Option value="daily">日线</Option>
                                    <Option value="weekly">周线</Option>
                                    <Option value="60">60分钟</Option>
                                    <Option value="30">30分钟</Option>
                                    <Option value="15">15分钟</Option>
                                    <Option value="5">5分钟</Option>
                                </Select>
                            </Form.Item>
                            
                            {['fast_period', 'slow_period', 'ma_period', 'dkx_period', 'dkx_ma_period'].filter(key =>
                                Object.hasOwn(tomorrowStrategyOptions.find(option => option.value === strategyType).defaults, key)
                            ).map(key => (
                                <Form.Item key={key} name={key} preserve={false} label={{ fast_period: '快线周期', slow_period: '慢线周期', ma_period: '均线周期', dkx_period: 'DKX周期', dkx_ma_period: 'DKX均线周期' }[key]} rules={[{ required: true }]}>
                                    <InputNumber min={1} precision={0} style={{ width: '100%' }} />
                                </Form.Item>
                            ))}
                            {strategyType === 'TrendFollowingStrategy' && <Form.Item name="use_expma" label="使用EMA" valuePropName="checked" preserve={false}><Switch /></Form.Item>}
                            {strategyType === 'MA5MA55CrossoverStrategy' && <Form.Item name="allow_reverse" label="允许反手" valuePropName="checked" preserve={false}><Switch /></Form.Item>}
                            {strategyType === 'DualMAFixedTPSLStrategy' && <>
                                <Form.Item name="ma_type" label="均线类型" preserve={false}><Select options={[{ value: 'SMA', label: 'SMA' }, { value: 'EMA', label: 'EMA' }]} /></Form.Item>
                                <Form.Item name="sl_mode" label="止损方式" preserve={false}><Select options={[{ value: 'points', label: '点数' }, { value: 'percent', label: '百分比' }]} /></Form.Item>
                                <Form.Item name="sl_value" label="止损值" preserve={false} rules={[{ required: true }]}><InputNumber min={0.01} style={{ width: '100%' }} /></Form.Item>
                                <Form.Item name="tp_mode" label="止盈方式" preserve={false}><Select options={[{ value: 'points', label: '点数' }, { value: 'percent', label: '百分比' }]} /></Form.Item>
                                <Form.Item name="tp_value" label="止盈值" preserve={false} rules={[{ required: true }]}><InputNumber min={0.01} style={{ width: '100%' }} /></Form.Item>
                            </>}
                            {['MA20MA55PartialTakeProfitStrategy', 'DKXPartialTakeProfitStrategy', 'DKXFixedTPSLStrategy'].includes(strategyType) && <Form.Item name="take_profit_points" label="止盈点数" preserve={false} rules={[{ required: true }]}><InputNumber min={0.01} style={{ width: '100%' }} /></Form.Item>}
                            {strategyType === 'DKXFixedTPSLStrategy' && <Form.Item name="stop_loss_points" label="止损点数" preserve={false} rules={[{ required: true }]}><InputNumber min={0.01} style={{ width: '100%' }} /></Form.Item>}
                            {strategyType === 'MA20MA55RiskRewardStrategy' && <>
                                <Form.Item name="risk_reward_ratio" label="盈亏比" preserve={false} rules={[{ required: true }]}><InputNumber min={0.1} style={{ width: '100%' }} /></Form.Item>
                                <Form.Item name="atr_period" label="ATR周期" preserve={false} rules={[{ required: true }]}><InputNumber min={1} precision={0} style={{ width: '100%' }} /></Form.Item>
                                <Form.Item name="atr_multiplier" label="止损ATR倍数" preserve={false} rules={[{ required: true }]}><InputNumber min={0.1} style={{ width: '100%' }} /></Form.Item>
                            </>}
                            <Form.Item name="fixed_size" label="固定手数" initialValue={20} rules={[{ required: true }]}><InputNumber min={1} precision={0} style={{ width: '100%' }} /></Form.Item>
                            <Form.Item name="margin_rate" label="保证金率" initialValue={0.12} rules={[{ required: true }]}><InputNumber min={0.01} max={1} step={0.01} style={{ width: '100%' }} /></Form.Item>
                            <p style={{ color: '#888' }}>按已完成K线计算信号，市价单在下一根K线开盘成交。详情沿用生成结果时的策略配置。</p>

                            <Form.Item>
                                <Button type="primary" htmlType="submit" loading={loading} block icon={<PlayCircleOutlined />}>
                                    开始分析
                                </Button>
                            </Form.Item>
                        </Form>
                    </Card>
                </Col>
                <Col span={18} style={{ height: '100%', overflowY: 'auto' }}>
                    <Card title="品种信号列表" bordered={false}>
                        <Table 
                            dataSource={results} 
                            columns={columns} 
                            rowKey="symbol" 
                            loading={loading}
                            pagination={{ pageSize: 20 }} 
                        />
                    </Card>
                </Col>
            </Row>

            <Modal
                title={`K线详情 - ${currentDetailSymbol}`}
                open={detailVisible}
                onCancel={() => { ++detailRequestId.current; setDetailVisible(false); }}
                width={1200}
                footer={null}
                style={{ top: 20 }}
            >
                {detailLoading ? <p>加载中...</p> : (
                    <>
                        <DataSourceInfo info={detailResult?.data_info} />
                        {detailResult && <Alert type="info" showIcon style={{ marginBottom: 16 }} message={`${tomorrowStrategyOptions.find(option => option.value === detailResult.strategy_info?.name)?.label || detailResult.strategy_info?.name} · ${detailResult.position_state.direction} ${Math.abs(detailResult.position_state.size)}手 · 持有 ${detailResult.position_state.hold_bars} 根K线`} description={detailResult.pending_orders?.length ? '最新K线已有待执行市价单，将在下一根K线成交；图中标记显示已成交的开仓和当前持仓。' : '图中标记显示最近一次实际开仓和当前持仓，不在数据末尾强制平仓。'} />}
                        <ChartPanel chartType="kline" results={detailResult} visibleBars={Math.max(200, (detailResult?.position_state?.hold_bars || 0) + 80)} />
                        {detailResult && <Collapse items={[{ key: 'trades', label: '最近交易记录', children: <Table size="small" rowKey={(_, index) => index} dataSource={[...detailResult.trades].reverse()} pagination={{ pageSize: 10 }} columns={[
                            { title: '时间', dataIndex: 'date' }, { title: '操作', dataIndex: 'action' },
                            { title: '成交价格', dataIndex: 'price' }, { title: '成交数量', dataIndex: 'size' }, { title: '成交后持仓', dataIndex: 'position' },
                        ]} /> }]} />}
                    </>
                )}
            </Modal>
        </div>
    );
};

export default TomorrowStrategy;
