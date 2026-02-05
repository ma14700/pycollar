import React, { useState, useEffect } from 'react';
import { Card, Form, Input, Select, Button, Row, Col, message, Table, Modal, Tag, Radio, Switch, Tooltip, DatePicker } from 'antd';
import { PlayCircleOutlined, LineChartOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import axios from 'axios';
import ChartPanel from '../../components/ChartPanel';

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

            const payload = {
                symbols: values.symbols,
                period: values.period,
                market_type: values.market_type,
                strategy_name: values.strategy_name,
                strategy_params: params
            };

            const res = await axios.post('http://localhost:8000/api/strategy/batch-analyze', payload);
            setResults(res.data.results || []);
            message.success('分析完成');
        } catch (err) {
            console.error(err);
            message.error('分析失败: ' + (err.response?.data?.detail || err.message));
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

            const payload = {
                symbol: record.symbol,
                period: values.period,
                market_type: values.market_type,
                strategy_name: values.strategy_name,
                strategy_params: params,
                initial_cash: 10000000, // 与 analyze_batch 保持一致
                auto_optimize: false,
                data_source: 'main',
                // 关键修正：确保详情回测的时间范围与批量分析完全一致（最近365天）
                // 否则数据起点不同会导致指标计算差异，进而导致信号不一致
                // 2024-05 Update: 针对周线模式，需要拉取更长的数据（3年），否则K线太少
                start_date: new Date(Date.now() - (values.period === 'weekly' ? 1095 : 365) * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
            };
            
            const res = await axios.post('http://localhost:8000/api/backtest', payload);
            
            // --- 定制化处理：仅显示最后一次开仓信号 + 当前持仓状态 ---
            const data = res.data;
            if (data && data.trades && data.kline_data && data.kline_data.dates.length > 0) {
                // 1. 找到最后一次"入场"性质的交易 (买多, 卖空, 反手...)
                const entryActions = ['买多', '卖空', '反手做多', '反手做空'];
                const lastEntry = [...data.trades].reverse().find(t => 
                    entryActions.some(action => t.action.includes(action))
                );

                // 2. 构造当前持仓状态的虚拟信号
                const dates = data.kline_data.dates;
                const values = data.kline_data.values;
                const lastDate = dates[dates.length - 1];
                // K线数据结构通常是 [date, open, close, low, high, vol] 或类似，close通常在索引2 (如果带date) 或 1 (如果不带)
                // ChartPanel中逻辑：if length>=5 close=value[2]
                const lastValueArr = values[values.length - 1];
                let lastClose = 0;
                if (Array.isArray(lastValueArr)) {
                    if (lastValueArr.length >= 5) lastClose = lastValueArr[2];
                    else if (lastValueArr.length === 4) lastClose = lastValueArr[1];
                }

                const lastTrade = data.trades[data.trades.length - 1];
                const currentPos = lastTrade ? lastTrade.position : 0;
                
                let statusLabel = `空仓`;
                let color = '#999';
                let type = 'buy'; // default

                if (currentPos > 0) {
                    statusLabel = `多 ${currentPos}手`;
                    color = '#ef232a';
                    type = 'buy';
                } else if (currentPos < 0) {
                    statusLabel = `空 ${Math.abs(currentPos)}手`;
                    color = '#14b143';
                    type = 'sell';
                }

                const statusSignal = {
                    date: lastDate,
                    price: lastClose,
                    custom_label: statusLabel,
                    type: type,
                    itemStyle: { color: color },
                    action: '当前状态' // 避免 ChartPanel 报错或显示 undefined
                };

                // 3. 重组 trades 列表
                const newTrades = [];
                // 如果最后一次开仓存在，且当前有持仓(或者用户想看最近一次操作)，加入列表
                // 用户要求：只显示最后一次根据策略开仓的位置
                if (lastEntry) {
                    newTrades.push(lastEntry);
                }
                // 加入状态标签
                newTrades.push(statusSignal);

                data.trades = newTrades;
                // 为了兼容 ChartPanel 可能使用 signals 字段
                data.signals = newTrades; 
            }
            // -----------------------------------------------------

            setDetailResult(data);
        } catch (err) {
            console.error(err);
            message.error('加载详情失败');
        } finally {
            setDetailLoading(false);
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
                <Button type="link" icon={<LineChartOutlined />} onClick={() => showDetail(record)}>
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
                                <Select onChange={(val) => {
                                    setStrategyType(val);
                                    // Set some defaults
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
                                    <Option value="weekly">周线</Option>
                                    <Option value="60">60分钟</Option>
                                    <Option value="30">30分钟</Option>
                                    <Option value="15">15分钟</Option>
                                    <Option value="5">5分钟</Option>
                                </Select>
                            </Form.Item>
                            
                            {/* Common Params */}
                            <Form.Item name="fast_period" label="快线周期" tooltip="适用于MA/MACD等"><Input type="number" /></Form.Item>
                            <Form.Item name="slow_period" label="慢线周期" tooltip="适用于MA/MACD等"><Input type="number" /></Form.Item>
                            <Form.Item name="ma_period" label="均线周期" tooltip="适用于单均线策略"><Input type="number" /></Form.Item>
                            <Form.Item name="dkx_period" label="DKX周期"><Input type="number" /></Form.Item>
                            <Form.Item name="dkx_ma_period" label="DKX均线周期"><Input type="number" /></Form.Item>

                            {strategyType === 'MA20MA55RiskRewardStrategy' && (
                                <>
                                    <Form.Item name="risk_reward_ratio" label="盈亏比(R:R)" initialValue={2.0} tooltip="止盈距离 / 止损距离"><Input type="number" step="0.1" /></Form.Item>
                                    <Form.Item name="atr_period" label="ATR周期" initialValue={14}><Input type="number" /></Form.Item>
                                    <Form.Item name="atr_multiplier" label="止损ATR倍数" initialValue={2.0} tooltip="止损距离 = ATR * 倍数"><Input type="number" step="0.1" /></Form.Item>
                                </>
                            )}
                            
                            <Form.Item name="size_mode" label="开仓模式" initialValue="fixed">
                                <Radio.Group>
                                    <Radio value="fixed">固定手数</Radio>
                                    <Radio value="equity_percent">资金比例</Radio>
                                    <Radio value="atr_risk">ATR风险</Radio>
                                </Radio.Group>
                            </Form.Item>
                            <Form.Item name="fixed_size" label="固定手数" initialValue={20}><Input type="number" /></Form.Item>
                            <Form.Item name="margin_rate" label="保证金率" initialValue={0.12}><Input type="number" step="0.01" /></Form.Item>

                             <Form.Item name="optimal_entry" label="开仓最优模式" valuePropName="checked" initialValue={false}>
                                <div style={{ display: 'flex', alignItems: 'center' }}>
                                    <Switch />
                                    <Tooltip title="开启后，操作均以中间点位 [(High+Low)/2] 执行。">
                                        <SafetyCertificateOutlined style={{ marginLeft: 8 }} />
                                    </Tooltip>
                                </div>
                            </Form.Item>

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
                onCancel={() => setDetailVisible(false)}
                width={1200}
                footer={null}
                style={{ top: 20 }}
            >
                {detailLoading ? <p>加载中...</p> : (
                    <ChartPanel chartType="kline" results={detailResult} />
                )}
            </Modal>
        </div>
    );
};

export default TomorrowStrategy;
