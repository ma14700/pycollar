import React, { useState, useEffect } from 'react';
import { Card, Form, Input, Select, Button, Row, Col, message, Table, Modal, Tag, Radio, Switch, Tooltip, DatePicker } from 'antd';
import { PlayCircleOutlined, LineChartOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import axios from 'axios';
import ChartPanel from '../../components/ChartPanel';

const { Option } = Select;

const SymbolScan = () => {
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
                    scan_window: 5,
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
    };

    const onFinish = async (values) => {
        setLoading(true);
        try {
            // Merge form values into params
            let params = { ...values };
            delete params.symbols;
            delete params.market_type;
            delete params.period;
            delete params.strategy_name;
            delete params.scan_window;

            const payload = {
                symbols: values.symbols,
                period: values.period,
                market_type: values.market_type,
                strategy_name: values.strategy_name,
                scan_window: parseInt(values.scan_window),
                strategy_params: params
            };

            const res = await axios.post('http://localhost:8000/api/strategy/scan', payload);
            setResults(res.data.results || []);
            message.success('扫描完成');
        } catch (err) {
            console.error(err);
            message.error('扫描失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            setLoading(false);
        }
    };

    const showDetail = async (record) => {
        setDetailVisible(true);
        setDetailLoading(true);
        setCurrentDetailSymbol(record.symbol);
        setDetailResult(null);
        
        try {
            const values = form.getFieldsValue();
            let params = { ...values };
            delete params.symbols;
            delete params.market_type;
            delete params.period;
            delete params.strategy_name;
            delete params.scan_window;

            const payload = {
                symbol: record.symbol,
                period: values.period,
                market_type: values.market_type,
                strategy_name: values.strategy_name,
                strategy_params: {
                    ...params,
                    disable_auto_close: true // 告诉后端不要在最后自动平仓
                },
                initial_cash: 10000000, 
                auto_optimize: false,
                data_source: 'main',
                start_date: new Date(Date.now() - 365 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
            };
            
            // 修正参数类型，确保数值类型正确传递
            if (payload.strategy_params.fixed_size) payload.strategy_params.fixed_size = parseInt(payload.strategy_params.fixed_size);
            if (payload.strategy_params.margin_rate) payload.strategy_params.margin_rate = parseFloat(payload.strategy_params.margin_rate);
            
            // 确保日期范围合法，如果 start_date 是未来时间或不合理，可能会导致后端报错
            // 这里使用最近 365 天是安全的

            const res = await axios.post('http://localhost:8000/api/backtest', payload);
            setDetailResult(res.data);
        } catch (err) {
            console.error(err);
            message.error('加载详情失败');
        } finally {
            setDetailLoading(false);
        }
    };

    const columns = [
        { title: '品种代码', dataIndex: 'symbol', key: 'symbol', width: 100 },
        { 
            title: '交易品种', 
            dataIndex: 'symbol', 
            key: 'variety_name',
            width: 120,
            render: (text) => {
                const item = futuresList.find(f => f.code === text) || stockList.find(s => s.code === text);
                return item ? item.name : text;
            }
        },
        { 
            title: 'K线信号', 
            dataIndex: 'raw_signals', 
            key: 'signal_info',
            width: 200,
            render: (signals) => {
                if (!signals || signals.length === 0) return <Tag color="default">暂无机会</Tag>;
                return (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {signals.map((sig, idx) => (
                            <div key={idx} style={{ display: 'flex', alignItems: 'center', height: '24px' }}>
                                <Tag color={sig.action.includes('买') || sig.action.includes('多') ? 'red' : 'green'} style={{ marginRight: 8 }}>
                                    {sig.action}
                                </Tag>
                                <span>
                                    {sig.offset === 1 ? '当前K线' : `前${sig.offset-1}根`}
                                </span>
                            </div>
                        ))}
                    </div>
                );
            }
        },
        {
            title: '信号价格',
            dataIndex: 'raw_signals',
            key: 'signal_price',
            width: 100,
            render: (signals) => {
                if (!signals || signals.length === 0) return '-';
                return (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {signals.map((sig, idx) => (
                            <div key={idx} style={{ height: '24px', display: 'flex', alignItems: 'center' }}>
                                <span style={{ 
                                    fontWeight: 'bold',
                                    color: sig.action.includes('买') || sig.action.includes('多') ? '#f5222d' : '#52c41a'
                                }}>
                                    {sig.price.toFixed(2)}
                                </span>
                            </div>
                        ))}
                    </div>
                );
            }
        },
        {
            title: '当前价格',
            dataIndex: 'current_price',
            key: 'current_price',
            width: 100,
            render: (price) => price ? <span style={{ color: '#1890ff', fontWeight: 'bold' }}>{price.toFixed(2)}</span> : '-'
        },
        {
            title: '操作',
            key: 'action',
            width: 80,
            render: (_, record) => (
                <Button type="link" size="small" icon={<LineChartOutlined />} onClick={() => showDetail(record)}>
                    详情
                </Button>
            ),
        },
    ];

    return (
        <div style={{ padding: 24, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Row gutter={24} style={{ flex: 1, overflow: 'hidden' }}>
                <Col span={6} style={{ height: '100%', overflowY: 'auto' }}>
                    <Card title="扫描配置" bordered={false} style={{ height: '100%' }}>
                        <Form form={form} layout="vertical" onFinish={onFinish}>
                            <Form.Item name="market_type" label="市场类型">
                                <Select onChange={handleMarketChange}>
                                    <Option value="futures">期货</Option>
                                    <Option value="stock">股票</Option>
                                </Select>
                            </Form.Item>
                            
                            <Form.Item 
                                name="symbols" 
                                label="交易品种 (多选)" 
                                rules={[{ required: true, message: '请选择品种' }]}
                            >
                                <Select 
                                    mode="multiple" 
                                    placeholder="选择品种" 
                                    allowClear 
                                    maxTagCount="responsive" 
                                    style={{ width: '100%' }}
                                    showSearch
                                    filterOption={(input, option) => {
                                        const children = option.children ? option.children.toString().toLowerCase() : '';
                                        const value = option.value ? option.value.toString().toLowerCase() : '';
                                        const inputLower = input.toLowerCase();
                                        return children.includes(inputLower) || value.includes(inputLower);
                                    }}
                                >
                                    {symbols.map(s => (
                                        <Option key={s.code} value={s.code}>{s.name}</Option>
                                    ))}
                                </Select>
                            </Form.Item>

                            <Form.Item name="strategy_name" label="策略选择">
                                <Select onChange={(val) => {
                                    setStrategyType(val);
                                    if (val.includes('MA55')) {
                                        form.setFieldsValue({ ma_period: 55 });
                                    }
                                    if (val === 'MA20MA55RiskRewardStrategy') {
                                        form.setFieldsValue({
                                            fast_period: 20,
                                            slow_period: 55,
                                            risk_reward_ratio: 2.0,
                                            atr_period: 14,
                                            atr_multiplier: 2.0
                                        });
                                    }
                                }}>
                                    <Option value="MA55BreakoutStrategy">MA55突破+背离离场</Option>
                                    <Option value="MA55TouchExitStrategy">MA55突破+触碰平仓</Option>
                                    <Option value="MA20MA55CrossoverStrategy">20/55双均线交叉(多空)</Option>
                                    <Option value="MA20MA55RiskRewardStrategy">20/55双均线+盈亏比优化</Option>
                                    <Option value="StockMA20MA55LongOnlyStrategy">20/55双均线多头(股票)</Option>
                                    <Option value="MA20MA55PartialTakeProfitStrategy">20/55双均线+盈利平半仓</Option>
                                    <Option value="DualMAFixedTPSLStrategy">20/55双均线+固定止盈止损</Option>
                                    <Option value="DKXStrategy">DKX多空线策略</Option>
                                    <Option value="DKXPartialTakeProfitStrategy">DKX多空线+盈利平半仓</Option>
                                    <Option value="DKXFixedTPSLStrategy">DKX多空线+固定止盈止损</Option>
                                    <Option value="TrendFollowingStrategy">双均线趋势跟踪</Option>
                                </Select>
                            </Form.Item>

                            <Form.Item name="period" label="K线周期">
                                <Select>
                                    <Option value="daily">日线</Option>
                                    <Option value="60">60分钟</Option>
                                    <Option value="30">30分钟</Option>
                                    <Option value="15">15分钟</Option>
                                    <Option value="5">5分钟</Option>
                                </Select>
                            </Form.Item>

                            <Form.Item 
                                name="scan_window" 
                                label="扫描K线数 (N)" 
                                tooltip="检测最近 N 根 K 线内是否存在开仓信号"
                                rules={[
                                    { required: true, message: '请输入扫描根数' },
                                    { pattern: /^[1-9]\d*$/, message: '请输入正整数' }
                                ]}
                            >
                                <Input type="number" suffix="根" />
                            </Form.Item>

                            {/* Dynamic Strategy Params */}
                            {strategyType === 'TrendFollowingStrategy' || strategyType === 'DualMAFixedTPSLStrategy' ? (
                                <>
                                    <Row gutter={16}>
                                        <Col span={12}>
                                            <Form.Item name="fast_period" label="快线" initialValue={10}>
                                                <Input type="number" />
                                            </Form.Item>
                                        </Col>
                                        <Col span={12}>
                                            <Form.Item name="slow_period" label="慢线" initialValue={30}>
                                                <Input type="number" />
                                            </Form.Item>
                                        </Col>
                                    </Row>
                                </>
                            ) : (strategyType === 'DKXStrategy' || strategyType === 'DKXPartialTakeProfitStrategy' || strategyType === 'DKXFixedTPSLStrategy') ? (
                                <Row gutter={16}>
                                    <Col span={12}>
                                        <Form.Item name="dkx_period" label="DKX周期" initialValue={20}>
                                            <Input type="number" />
                                        </Form.Item>
                                    </Col>
                                    <Col span={12}>
                                        <Form.Item name="dkx_ma_period" label="均线周期" initialValue={10}>
                                            <Input type="number" />
                                        </Form.Item>
                                    </Col>
                                </Row>
                            ) : (
                                <Form.Item name="ma_period" label="MA周期" initialValue={55}>
                                    <Input type="number" />
                                </Form.Item>
                            )}

                            <Form.Item>
                                <Button type="primary" htmlType="submit" loading={loading} block icon={<PlayCircleOutlined />}>
                                    开始扫描
                                </Button>
                            </Form.Item>
                        </Form>
                    </Card>
                </Col>
                
                <Col span={18} style={{ height: '100%', overflowY: 'auto' }}>
                    <Card title="扫描结果" bordered={false} style={{ minHeight: '100%' }}>
                        <Table 
                            columns={columns} 
                            dataSource={results} 
                            rowKey="symbol"
                            loading={loading}
                            pagination={false}
                        />
                    </Card>
                </Col>
            </Row>

            <Modal
                title={`策略详情 - ${currentDetailSymbol}`}
                open={detailVisible}
                onCancel={() => setDetailVisible(false)}
                width={1000}
                footer={null}
                style={{ top: 20 }}
            >
                {detailLoading ? (
                    <div style={{ textAlign: 'center', padding: '50px' }}>加载中...</div>
                ) : (
                    <ChartPanel results={detailResult} chartType="kline" height={600} />
                )}
            </Modal>
        </div>
    );
};

export default SymbolScan;
