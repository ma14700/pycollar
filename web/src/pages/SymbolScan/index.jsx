import React, { useState, useEffect, useRef } from 'react';
import { Alert, Card, Form, InputNumber, Select, Button, Row, Col, message, Table, Modal, Tag, Switch, Space } from 'antd';
import { PlayCircleOutlined, LineChartOutlined } from '@ant-design/icons';
import axios from '../../utils/api.js';
import ChartPanel from '../../components/ChartPanel';
import DataProviderSelect from '../../components/DataProviderSelect';
import DataSourceInfo from '../../components/DataSourceInfo';
import PointExitInputs from '../../components/PointExitInputs';
import { defaultAnalysisSymbols } from '../../utils/tradingDefaults';
import { getMA144ExitStrategy, ma144ExitStrategyOptions } from '../../utils/ma144ExitStrategies';
import { tomorrowStrategyOptions, getTomorrowDetailRequest } from '../../utils/tomorrowStrategy';

const { Option } = Select;
const price = value => Number.isFinite(value) ? value.toFixed(2) : '—';
const periods = { daily: '日线', weekly: '周线', 60: '60分钟', 30: '30分钟', 15: '15分钟', 5: '5分钟' };
const providers = { tqsdk: '天勤', gm: '掘金量化', akshare: '原有行情' };
const statusLabels = {
    filled: ['success', '已模拟成交'], partial_fill: ['processing', '部分成交'],
    pending: ['processing', '待成交'], margin: ['error', '保证金不足'],
    rejected: ['error', '已拒绝'], canceled: ['default', '已取消'], expired: ['default', '已过期'],
};
const signalColumns = [
    { title: '动作 / 状态', width: 192, render: (_, signal) => {
        const [color, label] = statusLabels[signal.status];
        return <Space size={4} wrap><strong>{signal.action}</strong><Tag color={color}>{label}</Tag></Space>;
    } },
    { title: '触发时间（K线）', width: 180, render: (_, signal) => <>
        {signal.signal_time}<br /><small>{signal.offset === 1 ? '最新一根' : `前 ${signal.offset - 1} 根`}</small>
    </> },
    { title: '触发价', width: 105, render: (_, signal) => <>{price(signal.signal_price)} <small>{signal.trigger_basis}</small></> },
    { title: '模拟成交', width: 174, render: (_, signal) => signal.fill_time ? <>{price(signal.fill_price)}<br /><small>{signal.fill_time}</small></> : '—' },
];

const SymbolScan = () => {
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState([]);
    const [scanConfig, setScanConfig] = useState(null);
    const [signalsOnly, setSignalsOnly] = useState(false);
    const [futuresList, setFuturesList] = useState([]);
    const [stockList, setStockList] = useState([]);
    const [form] = Form.useForm();
    const [strategyType, setStrategyType] = useState('TrendFollowingStrategy');
    const [detailVisible, setDetailVisible] = useState(false);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailResult, setDetailResult] = useState(null);
    const [currentDetailSymbol, setCurrentDetailSymbol] = useState(null);
    const [detailError, setDetailError] = useState(null);
    const detailRequestId = useRef(0);
    const market = Form.useWatch('market_type', form) || 'futures';
    const symbols = market === 'stock' ? stockList : futuresList;
    const currentProvider = Form.useWatch('data_provider', form);
    const defaults = tomorrowStrategyOptions.find(option => option.value === strategyType)?.defaults;

    useEffect(() => {
        const controller = new AbortController();
        const options = { signal: controller.signal };
        axios.get('/api/symbols?market_type=futures', options).then(({ data }) => {
            const entries = data.futures || [];
            setFuturesList(entries);
            if (form.getFieldValue('market_type') === 'futures' && !form.isFieldTouched('symbols')) {
                form.setFieldsValue({ symbols: defaultAnalysisSymbols(entries) });
            }
        }).catch(error => { if (!axios.isCancel(error)) message.error('加载期货品种失败'); });
        axios.get('/api/symbols?market_type=stock', options)
            .then(({ data }) => setStockList(data.stocks || []))
            .catch(error => { if (!axios.isCancel(error)) message.warning('加载股票品种失败'); });
        return () => controller.abort();
    }, [form]);

    const handleMarketChange = val => {
        form.setFieldsValue({
            symbols: val === 'futures' ? defaultAnalysisSymbols(futuresList, 0) : [],
            data_provider: val === 'stock' ? 'akshare' : 'tqsdk', data_source: 'main',
        });
    };

    const onFinish = async values => {
        setLoading(true);
        try {
            const { symbols, period, market_type, strategy_name, scan_window, data_provider, data_source, synthesize_60, ...params } = values;
            const strategy = tomorrowStrategyOptions.find(option => option.value === strategy_name);
            const strategyParams = { fixed_size: 20, margin_rate: 0.12, ...strategy?.defaults };
            for (const key of [...Object.keys(strategy?.defaults || {}), 'entry_delay_bars', 'exit_delay_bars']) {
                if (params[key] != null) strategyParams[key] = params[key];
            }
            Object.assign(strategyParams, getMA144ExitStrategy(strategy_name)?.defaults);
            const payload = {
                symbols, period, market_type, strategy_name, scan_window, data_provider,
                data_source: market_type === 'futures' && data_provider !== 'akshare' ? data_source : 'main',
                synthesize_60: period === '60' && synthesize_60, strategy_params: strategyParams,
            };
            const { data } = await axios.post('/api/strategy/scan', payload);
            const rows = data.results || [];
            setResults(rows);
            setScanConfig(payload);
            setSignalsOnly(false);
            const incomplete = rows.filter(row => row.status !== 'ok').length;
            if (incomplete) message.warning(`扫描完成，${incomplete} 个品种失败或历史不足`);
            else message.success('扫描完成');
        } catch (err) {
            const detail = err.response?.data?.detail;
            message.error('扫描失败：' + (typeof detail === 'string' ? detail : err.message));
        } finally {
            setLoading(false);
        }
    };

    const showDetail = async record => {
        const requestId = ++detailRequestId.current;
        setDetailVisible(true);
        setDetailLoading(true);
        setCurrentDetailSymbol(record.symbol);
        setDetailResult(null);
        setDetailError(null);
        try {
            const { data } = await axios.post('/api/strategy/detail', getTomorrowDetailRequest(record));
            if (requestId === detailRequestId.current) setDetailResult(data);
        } catch (err) {
            if (requestId === detailRequestId.current) setDetailError(err.response?.data?.detail || err.message);
        } finally {
            if (requestId === detailRequestId.current) setDetailLoading(false);
        }
    };

    const signalCount = results.filter(row => row.raw_signals?.length).length;
    const failedCount = results.filter(row => row.status === 'error').length;
    const insufficientCount = results.filter(row => row.status === 'insufficient_history').length;
    const latestTime = row => row.raw_signals?.[0]?.signal_time || '';
    const visibleRows = results
        .filter(row => !signalsOnly || row.raw_signals?.length)
        .sort((first, second) => latestTime(second).localeCompare(latestTime(first)));
    const latestColumns = signalColumns.map(column => ({
        ...column, render: (_, row) => row.raw_signals?.length ? column.render(null, row.raw_signals[0]) : '—',
    }));
    const columns = [
        { title: '品种', dataIndex: 'symbol', width: 130, render: symbol => {
            const item = futuresList.find(entry => entry.code === symbol) || stockList.find(entry => entry.code === symbol);
            return <><strong>{item?.name || symbol}</strong>{item && <><br /><small>{symbol}</small></>}</>;
        } },
        { title: '扫描状态', width: 150, render: (_, row) => {
            if (row.status === 'error') return <><Tag color="error">扫描失败</Tag><div>{row.error}</div></>;
            if (row.status === 'insufficient_history') return <><Tag color="warning">历史不足</Tag>
                <div>{row.error || `可判断 ${row.available_bars} 根 / 请求 ${scanConfig.scan_window} 根`}</div></>;
            return row.raw_signals?.length ? <Tag color="blue">{row.raw_signals.length} 条信号</Tag> : <Tag>无信号</Tag>;
        } },
        ...latestColumns,
        { title: '最新K线收盘价', width: 165, render: (_, row) => <>{price(row.current_price)}
            {row.data_info?.end && <><br /><small>{row.data_info.end}</small></>}</> },
        { title: '操作', width: 80, fixed: 'right', render: (_, row) => <Button type="link" size="small"
            disabled={!row.analysis_request} icon={<LineChartOutlined />} onClick={() => showDetail(row)}>详情</Button> },
    ];

    return (
        <div style={{ padding: 20 }}>
            <Row gutter={[16, 16]} align="top">
                <Col xs={24} xl={6} style={{ minWidth: 0 }}>
                    <Card title="扫描配置" bordered={false}>
                        <Form form={form} layout="vertical" onFinish={onFinish} disabled={loading} initialValues={{
                            market_type: 'futures', period: 'daily', strategy_name: 'TrendFollowingStrategy',
                            data_provider: 'tqsdk', data_source: 'main', scan_window: 5,
                            fast_period: 10, slow_period: 30, entry_delay_bars: 0, exit_delay_bars: 0,
                        }}>
                            <Form.Item name="market_type" label="市场类型">
                                <Select onChange={handleMarketChange}>
                                    <Option value="futures">期货</Option>
                                    <Option value="stock">股票</Option>
                                </Select>
                            </Form.Item>

                            <DataProviderSelect form={form} />
                            {market === 'futures' && currentProvider !== 'akshare' && (
                                <Form.Item name="data_source" label="合约口径">
                                    <Select options={[{ value: 'main', label: '主力连续' }, { value: 'weighted', label: '加权指数' }]} />
                                </Form.Item>
                            )}

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
                                    form.setFieldsValue(tomorrowStrategyOptions.find(option => option.value === val)?.defaults || {});
                                }}>
                                    <Option value="MA55BreakoutStrategy">MA55突破+背离离场</Option>
                                    <Option value="MA55TouchExitStrategy">MA55突破+触碰平仓</Option>
                                    <Option value="MA20MA55CrossoverStrategy">20/55双均线交叉(多空)</Option>
                                    <Option value="MA20MA55PointExitStrategy">20/55双均线交叉(多空平仓点数)</Option>
                                    <Option value="MA20MA55LongOnlyStrategy">20/55双均线交叉多（只做多）</Option>
                                    <Option value="MA20MA55ShortOnlyStrategy">20/55双均线交叉空（只做空）</Option>
                                    {ma144ExitStrategyOptions.map(option => <Option key={option.value} value={option.value}>{option.label}</Option>)}
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

                            <Form.Item
                                name="scan_window"
                                label="扫描K线数 (N)"
                                tooltip="按触发时所在 K 线筛选开仓、反手、加减仓和平仓；成交可能在后续 K 线。"
                                rules={[
                                    { required: true, message: '请输入扫描根数' },
                                    { type: 'integer', min: 1, max: 10000, message: '请输入 1 到 10000 的整数' }
                                ]}
                            >
                                <InputNumber min={1} max={10000} precision={0} style={{ width: '100%' }} />
                            </Form.Item>

                            {strategyType === 'MA20MA55PointExitStrategy' && <PointExitInputs />}
                            {getMA144ExitStrategy(strategyType) ? (
                                <p>{getMA144ExitStrategy(strategyType).reverses ? '固定 MA20 / MA144，金叉平空开多、死叉平多开空，按固定手数反手。' : '固定 MA20 / MA144，反向交叉离场，不加仓、不直接反手。'}</p>
                            ) : defaults?.fast_period ? (
                                <>
                                    <Row gutter={16}>
                                        <Col span={12}>
                                            <Form.Item name="fast_period" label="快线">
                                                <InputNumber min={1} precision={0} style={{ width: '100%' }} />
                                            </Form.Item>
                                        </Col>
                                        <Col span={12}>
                                            <Form.Item name="slow_period" label="慢线">
                                                <InputNumber min={1} precision={0} style={{ width: '100%' }} />
                                            </Form.Item>
                                        </Col>
                                    </Row>
                                </>
                            ) : defaults?.dkx_period ? (
                                <Row gutter={16}>
                                    <Col span={12}>
                                        <Form.Item name="dkx_period" label="DKX周期" initialValue={20}>
                                            <InputNumber min={1} precision={0} style={{ width: '100%' }} />
                                        </Form.Item>
                                    </Col>
                                    <Col span={12}>
                                        <Form.Item name="dkx_ma_period" label="均线周期" initialValue={10}>
                                            <InputNumber min={1} precision={0} style={{ width: '100%' }} />
                                        </Form.Item>
                                    </Col>
                                </Row>
                            ) : (
                                <Form.Item name="ma_period" label="MA周期" initialValue={55}>
                                    <InputNumber min={1} precision={0} style={{ width: '100%' }} />
                                </Form.Item>
                            )}
                            <Row gutter={12}>
                                {[['entry_delay_bars', '开仓 K 线'], ['exit_delay_bars', '平仓 K 线']].map(([name, label]) => (
                                    <Col span={12} key={name}>
                                        <Form.Item name={name} label={label} tooltip="0 表示下一根开盘；正整数表示触发后第 N 根开盘">
                                            <InputNumber min={0} precision={0} style={{ width: '100%' }} />
                                        </Form.Item>
                                    </Col>
                                ))}
                            </Row>

                            <Form.Item>
                                <Button type="primary" htmlType="submit" loading={loading} block icon={<PlayCircleOutlined />}>
                                    开始扫描
                                </Button>
                            </Form.Item>
                        </Form>
                    </Card>
                </Col>

                <Col xs={24} xl={18} style={{ minWidth: 0 }}>
                    <Card title="扫描结果" bordered={false}>
                        {scanConfig && <Space direction="vertical" size={8} style={{ display: 'flex', marginBottom: 16 }}>
                            <div>
                                {tomorrowStrategyOptions.find(option => option.value === scanConfig.strategy_name)?.label}
                                {' · '}{periods[scanConfig.period]}{' · '}{providers[scanConfig.data_provider]}
                                {scanConfig.market_type === 'futures' && (scanConfig.data_source === 'weighted' ? ' / 加权指数' : ' / 主力连续')}
                                {scanConfig.synthesize_60 && ' · 交易时段合成'}{' · '}最近 {scanConfig.scan_window} 根
                            </div>
                            <Space wrap>
                                <Tag>扫描 {results.length} 个</Tag><Tag color="blue">有信号 {signalCount} 个</Tag>
                                <Tag color="gold">历史不足 {insufficientCount} 个</Tag><Tag color="red">失败 {failedCount} 个</Tag>
                                <Switch checked={signalsOnly} onChange={setSignalsOnly} size="small" aria-label="只看有信号" />只看有信号
                            </Space>
                        </Space>}
                        <Table
                            columns={columns}
                            dataSource={visibleRows}
                            rowKey="symbol"
                            loading={loading}
                            size="small"
                            scroll={{ x: 1240 }}
                            pagination={{ defaultPageSize: 15, showSizeChanger: true, pageSizeOptions: [15, 30, 60] }}
                            locale={{ emptyText: !scanConfig ? '选择品种和策略后开始扫描' : '没有符合筛选条件的结果' }}
                            expandable={{
                                rowExpandable: row => row.raw_signals?.length > 1,
                                expandedRowRender: row => <Table size="small" columns={signalColumns} rowKey="ref"
                                    dataSource={row.raw_signals} pagination={false} />,
                            }}
                        />
                    </Card>
                </Col>
            </Row>

            <Modal
                title={`策略详情 - ${currentDetailSymbol}`}
                open={detailVisible}
                onCancel={() => { detailRequestId.current += 1; setDetailVisible(false); }}
                width="min(1100px, 96vw)"
                footer={null}
                style={{ top: 20 }}
            >
                {detailLoading ? (
                    <div style={{ textAlign: 'center', padding: '50px' }}>加载中...</div>
                ) : detailError ? <Alert type="error" showIcon message="加载详情失败" description={detailError} />
                    : detailResult && <>
                        <DataSourceInfo info={detailResult.data_info} />
                        <ChartPanel results={detailResult} chartType="kline" height={600} />
                    </>}
            </Modal>
        </div>
    );
};

export default SymbolScan;
