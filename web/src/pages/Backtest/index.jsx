import React, { useState, useEffect, useRef } from 'react';
import { Card, Form, Input, InputNumber, Select, Button, Row, Col, message, Alert, DatePicker, Tooltip } from 'antd';
import { 
  SafetyCertificateOutlined, 
  PlayCircleOutlined,
  SaveOutlined,
  ReloadOutlined,
  DashboardOutlined
} from '@ant-design/icons';
import axios from '../../utils/api.js';
import dayjs from 'dayjs';
import ContractInfo from '../../components/ContractInfo';
import { useBacktest } from '../../context/BacktestContext';
import DataProviderSelect from '../../components/DataProviderSelect';
import { contractWindow, applyContractBacktest, normalizeContractMonths, buildBacktestTargets, filterContractMonthOptions } from '../../utils/contractBacktest';
import BacktestLoading from '../../components/BacktestLoading';
import ContractMonthLabel from '../../components/ContractMonthLabel';
import { defaultTradingSymbol } from '../../utils/tradingDefaults';
import { strategyParameterKeys, pickStrategyParameters, defaultStrategyParameters, buildStrategyParameters, isFixedMA144Strategy, isMA55144Strategy } from '../../utils/backtestStrategies';

import SingleBacktestResult from './SingleBacktestResult';
import BatchBacktestResult from './BatchBacktestResult';
import StrategyConfigFields from './StrategyConfigFields';

const { Option } = Select;

const BacktestPage = () => {
  const { results, symbols, setSymbols, savedFormValues, setSavedFormValues, savedStrategyType, setSavedStrategyType, selectedStrategies, setSelectedStrategies, strategyConfigs, setStrategyConfigs,
    loading, activeRun, runError, startBacktest, saveBacktestResults, autoOptimize, setAutoOptimize, currentParams, setCurrentParams,
    only159Contracts } = useBacktest();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const pageRef = useRef(null);
  const configRef = useRef(null);
  const resultsRef = useRef(null);
  useEffect(() => {
    if (!loading) return;
    pageRef.current?.parentElement?.scrollTo({ top: 0, behavior: 'instant' });
    configRef.current?.scrollTo({ top: 0, behavior: 'instant' });
    resultsRef.current?.scrollTo({ top: 0, behavior: 'instant' });
  }, [loading]);
  const [defaultDateRange] = useState(() => [
    dayjs('2025-01-01'),
    dayjs(new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' })),
  ]);
  const [strategyType, setStrategyType] = useState(savedStrategyType || 'MA20MA55CrossoverStrategy');
  const [quoteInfo, setQuoteInfo] = useState(null);
  const quoteRequestId = useRef(0);
  const [isFullScreen, setIsFullScreen] = useState(false);
  
  // Local cache for lists to avoid repeated API calls if we were to move this to context fully
  // For now, we fetch on mount if symbols is empty or just fetch every time to be safe
  const [futuresList, setFuturesList] = useState([]);
  const [stockList, setStockList] = useState([]);
  const selectedProducts = Form.useWatch('symbol', form);
  const selectedMarket = Form.useWatch('market_type', form) || 'futures';
  const selectedProvider = Form.useWatch('data_provider', form) || (selectedMarket === 'stock' ? 'akshare' : 'tqsdk');
  const selectedSource = Form.useWatch('data_source', form) || 'main';
  const contractMonths = normalizeContractMonths(Form.useWatch('contract_month', form));
  const contractMode = selectedMarket === 'futures' && contractMonths.length > 0;
  const singleProduct = Array.isArray(selectedProducts) && selectedProducts.length === 1 ? selectedProducts[0] : null;
  const [contractOptions, setContractOptions] = useState([]);
  const [contractsLoading, setContractsLoading] = useState(false);
  const [contractsError, setContractsError] = useState('');
  const [contractReload, setContractReload] = useState(0);
  const contractCache = useRef(new Map());
  const previousDateRange = useRef(defaultDateRange);

  useEffect(() => {
    let active = true;
    setContractOptions([]);
    setContractsError('');
    if (selectedMarket !== 'futures' || !singleProduct) {
        setContractsLoading(false);
        return;
    }
    const cached = contractCache.current.get(singleProduct);
    if (cached) {
        setContractOptions(cached);
        setContractsLoading(false);
        return;
    }
    setContractsLoading(true);
    axios.get('/api/futures/contracts', { params: { symbol: singleProduct } })
      .then(({ data }) => {
        if (!active) return;
        const options = data.contracts || [];
        contractCache.current.set(singleProduct, options);
        setContractOptions(options);
      })
      .catch(error => { if (active) setContractsError(error.response?.data?.detail || '加载合约失败，请重试'); })
      .finally(() => { if (active) setContractsLoading(false); });
    return () => { active = false; };
  }, [singleProduct, selectedMarket, contractReload]);

  // Fetch symbols on mount
  useEffect(() => {
    let active = true;
    // Restore the submitted form immediately, even while catalog requests are pending.
    if (savedFormValues) {
        const marketType = savedFormValues.market_type || 'futures';
        const initialValues = { ...savedFormValues,
            date_range: savedFormValues.date_range === undefined ? defaultDateRange : savedFormValues.date_range,
            entry_delay_bars: savedFormValues.entry_delay_bars ?? 0,
            exit_delay_bars: savedFormValues.exit_delay_bars ?? 0,
            data_provider: savedFormValues.data_provider || (marketType === 'stock' ? 'akshare' : 'tqsdk') };
        if (initialValues.symbol && !Array.isArray(initialValues.symbol)) initialValues.symbol = [initialValues.symbol];
        initialValues.contract_month = marketType === 'futures' ? normalizeContractMonths(initialValues.contract_month) : [];
        if (initialValues.contract_month.length) {
            const window = contractWindow(initialValues.contract_month[0]);
            initialValues.date_range = initialValues.contract_month.length === 1 ? [dayjs(window.start_date), dayjs(window.end_date)] : null;
            initialValues.data_provider = 'tqsdk';
            initialValues.data_source = 'main';
        }
        form.setFieldsValue(initialValues);
    } else {
        form.setFieldsValue({ market_type: 'futures', period: '60', initial_cash: 1000000 });
    }
    const fetchData = async () => {
      try {
        const [futuresRes, stockRes] = await Promise.all([
          axios.get('/api/symbols?market_type=futures'),
          axios.get('/api/symbols?market_type=stock')
        ]);
        
        const fList = futuresRes.data.futures || [];
        const sList = stockRes.data.stocks || [];
        if (!active) return;
        
        setFuturesList(fList);
        setStockList(sList);
        
        const currentValues = form.getFieldsValue(true);
        const marketType = currentValues.market_type || 'futures';
        if (savedFormValues || currentValues.symbol?.length) {
            const list = marketType === 'stock' ? sList : fList;
            setSymbols(list || []);
            // 强制刷新 multiplier (防止保存的旧值有误)
            if (currentValues.symbol && currentValues.symbol.length === 1) {
                const targetSymbol = list.find(s => s.code === currentValues.symbol[0]);
                if (targetSymbol) {
                    form.setFieldsValue({ contract_multiplier: targetSymbol.multiplier });
                }
            }
            fetchQuote(currentValues.symbol);
        } else {
            // Initialize with futures
            switchSymbols(marketType, fList, sList);
        }
      } catch (err) {
        if (!active) return;
        console.error(err);
        message.error('无法连接到后端服务获取品种数据');
      }
    };
    fetchData();
    
    return () => { active = false; ++quoteRequestId.current; };
  }, []);

  const switchSymbols = (marketType, fList = futuresList, sList = stockList) => {
    const list = marketType === 'stock' ? sList : fList;
    setSymbols(list || []);
    
    if (list && list.length > 0) {
      const defaultSymbol = defaultTradingSymbol(list, marketType);
      
      // 默认选中一个，作为数组
      form.setFieldsValue({ 
        symbol: [defaultSymbol.code],
        contract_multiplier: defaultSymbol.multiplier
      });
      fetchQuote(defaultSymbol.code);
    } else {
      form.setFieldsValue({ symbol: [] });
      setQuoteInfo(null);
    }
  };

  const fetchQuote = (symbol, overrides = {}) => {
    const requestId = ++quoteRequestId.current;
    setQuoteInfo(null);
    let targetSymbol = Array.isArray(symbol) ? (symbol.length === 1 ? symbol[0] : null) : symbol;
    if (!targetSymbol) return;
    const marketType = form.getFieldValue('market_type') || 'futures';
    let dataSource = overrides.data_source || form.getFieldValue('data_source') || 'main';
    let dataProvider = overrides.data_provider || form.getFieldValue('data_provider') || (marketType === 'stock' ? 'akshare' : 'tqsdk');
    const months = normalizeContractMonths(Object.hasOwn(overrides, 'contract_month') ? overrides.contract_month : form.getFieldValue('contract_month'));
    if (months.length > 1) return;
    if (months.length === 1 && marketType === 'futures') {
        const specific = applyContractBacktest({ symbol: targetSymbol, market_type: marketType }, months[0]);
        targetSymbol = specific.symbol;
        dataSource = specific.data_source;
        dataProvider = specific.data_provider;
    }
    axios.get('/api/quote/latest', { params: { symbol: targetSymbol, market_type: marketType, data_source: dataSource, data_provider: dataProvider } })
      .then(res => {
        if (requestId === quoteRequestId.current) setQuoteInfo(res.data);
      })
      .catch(err => {
        console.error("Failed to fetch quote", err);
        if (requestId === quoteRequestId.current) setQuoteInfo(null);
      });
  };

  const clearContract = () => {
    if (normalizeContractMonths(form.getFieldValue('contract_month')).length) {
        form.setFieldsValue({ contract_month: [], date_range: previousDateRange.current });
    }
  };

  const onContractChange = (selection) => {
    const months = normalizeContractMonths(selection);
    if (months.length) {
        if (!contractMonths.length) previousDateRange.current = form.getFieldValue('date_range');
        const window = contractWindow(months[0]);
        form.setFieldsValue({ contract_month: months, data_provider: 'tqsdk', data_source: 'main',
            date_range: months.length === 1 ? [dayjs(window.start_date), dayjs(window.end_date)] : null });
    } else {
        form.setFieldsValue({ contract_month: [], date_range: previousDateRange.current });
    }
    setSavedFormValues(form.getFieldsValue());
    fetchQuote(form.getFieldValue('symbol'), { contract_month: months });
  };

  const onSymbolChange = (value) => {
    clearContract();
    // value 是数组
    if (Array.isArray(value) && value.length > 0) {
        // 取最后一个选中的作为参考来设置乘数
        const lastSelected = value[value.length - 1];
        const selected = symbols.find(s => s.code === lastSelected);
        if (selected) {
            form.setFieldsValue({ contract_multiplier: selected.multiplier });
        }
        // 如果只选了一个，获取行情；否则清空行情面板以免混淆
        if (value.length === 1) {
            fetchQuote(lastSelected);
        } else {
            fetchQuote(null);
        }
    } else {
        fetchQuote(null);
    }
    setSavedFormValues(form.getFieldsValue());
  };

  const activateStrategy = name => {
    const currentValues = form.getFieldsValue(true);
    const configs = { ...strategyConfigs, [strategyType]: pickStrategyParameters(currentValues) };
    setStrategyConfigs(configs);
    setStrategyType(name); setSavedStrategyType(name);
    form.setFieldsValue({ ...Object.fromEntries(strategyParameterKeys.map(key => [key, undefined])),
      ...defaultStrategyParameters(name), ...configs[name] });
    setSavedFormValues(form.getFieldsValue(true));
  };

  const onFinish = async (values) => {
    if (loading) return;
    let selectedSymbols = values.symbol;
    // 类型安全检查：确保是数组
    if (selectedSymbols && !Array.isArray(selectedSymbols)) {
        selectedSymbols = [selectedSymbols];
    }

    if (!selectedSymbols || selectedSymbols.length === 0) {
        message.error('请至少选择一个品种');
        return;
    }
    let targets;
    try {
        targets = buildBacktestTargets(selectedSymbols, values.contract_month);
    } catch (error) {
        message.error(error.message);
        return;
    }

    try {
      if (!selectedStrategies.length) throw new Error('请至少选择一个策略');
      const configs = { ...strategyConfigs, [strategyType]: pickStrategyParameters(values) };
      setStrategyConfigs(configs);
      const tasks = selectedStrategies.flatMap(name => {
          const strategyValues = { ...values, ...defaultStrategyParameters(name), ...configs[name] };
          const params = buildStrategyParameters(name, strategyValues);
          return targets.map(target => {
              const symbolObj = symbols.find(item => item.code === target.base_symbol);
              let payload = {
                  symbol: target.base_symbol, period: values.period, market_type: values.market_type || 'futures',
                  data_source: values.data_source || 'main', synthesize_60: values.synthesize_60 || false,
                  data_provider: values.data_provider || (values.market_type === 'stock' ? 'akshare' : 'tqsdk'),
                  strategy_name: name, strategy_params: { ...params, contract_multiplier: symbolObj?.multiplier || values.contract_multiplier || 1 },
                  initial_cash: Number(values.initial_cash || 1000000), auto_optimize: isFixedMA144Strategy(name) || isMA55144Strategy(name) || ['MA20MA60DailyMACDStrategy','MA20MA55RR3Strategy'].includes(name) ? false : autoOptimize,
              };
              if (values.date_range?.length === 2) {
                  payload.start_date = values.date_range[0].format('YYYY-MM-DD');
                  payload.end_date = values.date_range[1].format('YYYY-MM-DD');
              }
              payload = applyContractBacktest(payload, target.contract_month);
              return { payload, symbolName: symbolObj?.name };
          });
      });
      setCurrentParams(tasks[0].payload.strategy_params);
      setSavedFormValues({ ...values });
      await startBacktest({ tasks, strategy: selectedStrategies.length > 1 ? '多策略回测' : strategyType, period: values.period,
        provider: tasks[0].payload.data_provider,
        unit: selectedStrategies.length > 1 ? '组合' : normalizeContractMonths(values.contract_month).length ? '合约' : '品种' });

    } catch (error) {
      console.error(error);
      message.error('执行出错: ' + error.message);
    }
  };

  const handleSaveBacktest = async () => {
    if (!results) return;
    setSaving(true);
    try {
      const count = await saveBacktestResults(results, {
        symbol: form.getFieldValue('symbol'), period: form.getFieldValue('period'),
        strategy_name: strategyType, strategy_params: currentParams || {},
      });
      if (!count) message.warning('暂无成功的回测结果可保存');
      else message.success(count > 1 ? `已保存 ${count} 项回测结果` : '回测结果已保存');
    } catch (error) {
      message.error('保存未全部完成，重试会跳过已保存项目：' + error.message);
    } finally { setSaving(false); }
  };

  return (
    <div ref={pageRef} className="backtest-page" style={{ height: '100%', minHeight: 0, boxSizing: 'border-box', padding: '24px', overflow: 'hidden' }}>
        <Row gutter={24} style={{ height: '100%', minHeight: 0 }}>
            <Col span={isFullScreen ? 0 : 6} style={{ height: '100%', minHeight: 0, minWidth: 0, display: isFullScreen ? 'none' : 'block' }}>
            <Card ref={configRef} title={<span><SafetyCertificateOutlined /> 策略配置</span>} variant="borderless" style={{ height: '100%', borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)', overflowY: 'auto' }}>
                <Form form={form} layout="vertical" onFinish={onFinish} 
                    onValuesChange={(changedValues, allValues) => {
                        setSavedFormValues(allValues);
                        setStrategyConfigs(previous => ({...previous,[strategyType]:pickStrategyParameters(allValues)}));
                    }}
                    initialValues={{
                    market_type: 'futures',
                    initial_cash: 1000000,
                    period: '60',
                    date_range: defaultDateRange,
                    entry_delay_bars: 0,
                    exit_delay_bars: 0,
                    fast_period: 20,
                    slow_period: 55,
                    atr_period: 14,
                    atr_multiplier: 2.0,
                    risk_per_trade: 0.02,
                    contract_multiplier: 30,
                    ma_period: 55,
                    macd_fast: 12,
                    macd_slow: 26,
                    macd_signal: 9
                }}>
                <Form.Item name="market_type" label="市场类型">
                    <Select onChange={(val) => {
                        clearContract();
                        form.setFieldsValue({ symbol: undefined });
                        if (val === 'stock') {
                            form.setFieldsValue({ data_source: 'main', data_provider: 'akshare' });
                        } else {
                            form.setFieldsValue({ data_provider: 'tqsdk' });
                        }
                        switchSymbols(val);
                        setSavedFormValues(form.getFieldsValue());
                    }}>
                    <Option value="futures">期货</Option>
                    <Option value="stock">股票</Option>
                    </Select>
                </Form.Item>

                <DataProviderSelect form={form} disabled={contractMode} onChange={(value) => fetchQuote(form.getFieldValue('symbol'), { data_provider: value })} />

                <Form.Item 
                    name="data_source" 
                    label="合约口径"
                    initialValue="main"
                    tooltip="选择'主力连续'将使用主力合约拼接数据；选择'加权指数'将使用加权指数数据(如可用)"
                    shouldUpdate={(prev, curr) => prev.market_type !== curr.market_type}
                >
                    <Select disabled={selectedMarket === 'stock' || contractMode} onChange={(value) => fetchQuote(form.getFieldValue('symbol'), { data_source: value })}>
                    <Option value="main">{contractMode ? '具体合约' : '主力连续'}</Option>
                    <Option value="weighted">{selectedProvider === 'tqsdk' ? '加权指数（天勤）' : '加权指数'}</Option>
                    </Select>
                </Form.Item>

                {selectedMarket === 'futures' && selectedProvider === 'tqsdk' && selectedSource === 'weighted' && !contractMode &&
                    <Alert type="info" showIcon style={{ marginBottom: 16 }}
                        message="天勤加权指数回测"
                        description="采用各在市合约昨持仓量加权的品种指数。该指数不可直接交易，收益为按指数价格模拟的结果；选择具体合约会切换为该合约行情。" />}


                <Form.Item name="initial_cash" label="初始资金">
                    <Input type="number" step="10000" />
                </Form.Item>

                <Form.Item noStyle shouldUpdate={(prev, curr) => prev.market_type !== curr.market_type}>
                    {({ getFieldValue }) => {
                        return (
                            <Form.Item name="symbol" label={`交易品种 (共${symbols.length}个)`} rules={[{ required: true }]}>
                                    <Select 
                                    onChange={onSymbolChange}
                                    showSearch
                                    mode="multiple"
                                    maxTagCount="responsive"
                                    placeholder="选择或搜索品种 (支持多选)"
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
                        );
                    }}
                </Form.Item>

                {selectedMarket === 'futures' && <Form.Item name="contract_month" htmlFor={null}
                    label={<ContractMonthLabel />}
                    extra={!singleProduct ? '先选择一个交易品种，再选择具体合约。' : contractsError ? <span style={{ color: '#ff4d4f' }}>{contractsError} <Button type="link" size="small" onClick={() => { contractCache.current.delete(singleProduct); setContractReload(value => value + 1); }}>重试</Button></span> : '具体合约使用天勤行情；清空后恢复原有品种回测。'}>
                    <Select mode="multiple" maxTagCount="responsive" allowClear showSearch optionFilterProp="label" placeholder="可选择多个合约，如 2605、2701"
                        disabled={!singleProduct || loading} loading={contractsLoading} options={filterContractMonthOptions(contractOptions, only159Contracts)}
                        notFoundContent={contractsLoading ? '加载合约中…' : contractsError ? '合约加载失败' : '暂无可用合约'}
                        onChange={onContractChange} />
                </Form.Item>}
                {contractMode && <Alert type="info" showIcon style={{ marginBottom: 16 }}
                    message={`已选择 ${contractMonths.length} 个具体合约，将分别生成回测结果`}
                    description={<><div>各合约时间范围独立锁定，仅回测已有行情。</div>
                        <div style={{ maxHeight: 160, overflowY: 'auto', marginTop: 8 }}>
                            {contractMonths.map(month => { const window = contractWindow(month); return <div key={month} style={{ marginTop: 4 }}>
                                <strong>{singleProduct?.replace(/0$/, '')}{month}</strong>：{window.start_date} ～ {window.end_date}
                            </div>; })}
                        </div></>} />}

                <ContractInfo 
                    form={form} 
                    quoteInfo={quoteInfo} 
                />

                <StrategyConfigFields
                    strategyType={strategyType}
                    selectedStrategies={selectedStrategies}
                    setSelectedStrategies={setSelectedStrategies}
                    activateStrategy={activateStrategy}
                    loading={loading}
                    autoOptimize={autoOptimize}
                    setAutoOptimize={setAutoOptimize}
                >
                    <Form.Item label="回测周期" name="period">
                        <Select>
                        <Option value="daily">日线</Option>
                        <Option value="weekly">周线</Option>
                        <Option value="60">60分钟</Option>
                        <Option value="30">30分钟</Option>
                        <Option value="15">15分钟</Option>
                        <Option value="5">5分钟</Option>
                        </Select>
                    </Form.Item>

                    <Form.Item label="时间范围" name="date_range">
                        <DatePicker.RangePicker disabled={contractMode} placeholder={contractMonths.length > 1 ? ['各合约独立开始日期', '各合约独立结束日期'] : undefined} style={{ width: '100%' }} />
                    </Form.Item>

                    <Row gutter={12}>
                        {[['entry_delay_bars', '开仓 K 线'], ['exit_delay_bars', '平仓 K 线']].map(([name, label]) => (
                            <Col span={12} key={name}>
                                <Form.Item name={name} label={label} tooltip="0 为不额外延迟，在下一根开盘成交；1 也沿用下一根开盘，2 = 第二根。" rules={[
                                    { required: true, message: '请输入 K 线根数' },
                                    { validator: (_, value) => value == null || (Number.isInteger(value) && value >= 0) ? Promise.resolve() : Promise.reject(new Error('须为大于等于 0 的整数')) },
                                ]}>
                                    <InputNumber min={0} precision={0} style={{ width: '100%' }} />
                                </Form.Item>
                            </Col>
                        ))}
                    </Row>
                    <div style={{ color: '#8b96a8', fontSize: 12, lineHeight: 1.7, marginTop: -8, marginBottom: 20 }}>
                        默认 0 = 不额外延迟，下一根开盘成交；1 沿用下一根开盘，2 = 第二根开盘。适用于信号市价单；反手取两者较大值，止盈止损挂单保持触价成交。
                    </div>
                </StrategyConfigFields>

                <Form.Item>
                    <Button 
                    type="primary" 
                    htmlType="submit" 
                    loading={loading} 
                    block 
                    size="large"
                    icon={<PlayCircleOutlined />}
                    style={{ 
                        height: '48px', 
                        fontSize: '18px', 
                        fontWeight: 'bold', 
                        borderRadius: '6px', 
                        background: 'linear-gradient(90deg, #1890ff 0%, #096dd9 100%)', 
                        border: 'none',
                        boxShadow: '0 4px 14px 0 rgba(24, 144, 255, 0.39)'
                    }}
                    >
                    开始回测
                    </Button>
                </Form.Item>
                <Form.Item>
                        <Tooltip title="保存当前回测配置和结果">
                        <Button icon={<SaveOutlined />} onClick={handleSaveBacktest} loading={saving} block size="large" disabled={!results}>
                            保存回测结果
                        </Button>
                        </Tooltip>
                </Form.Item>
                <Form.Item>
                        <Tooltip title="重新运行回测以刷新图表">
                        <Button icon={<ReloadOutlined />} onClick={form.submit} disabled={loading} block size="large">
                            刷新图表
                        </Button>
                        </Tooltip>
                </Form.Item>
                </Form>
            </Card>
            </Col>
            
            <Col ref={resultsRef} role="region" aria-label="策略回测结果" tabIndex={0} span={isFullScreen ? 24 : 18} style={{ height: '100%', minHeight: 0, minWidth: 0, overflow: 'auto' }}>
            {loading && activeRun ? <BacktestLoading run={activeRun} /> : runError ? (
                <Alert type="error" showIcon message="回测失败" description={runError} />
            ) : results ? (
                results.isBatch ? (
                    <BatchBacktestResult
                        results={results}
                        symbols={symbols}
                        isFullScreen={isFullScreen}
                        onToggleFullScreen={() => setIsFullScreen(!isFullScreen)}
                    />
                ) : (
                    <SingleBacktestResult results={results} />
                )
            ) : (
                <div style={{ 
                    height: '100%', 
                    display: 'flex', 
                    justifyContent: 'center', 
                    alignItems: 'center',
                    flexDirection: 'column',
                    color: '#999'
                }}>
                    <DashboardOutlined style={{ fontSize: '64px', marginBottom: '16px', color: '#e6f7ff' }} />
                    <div style={{ fontSize: '16px' }}>请在左侧配置策略参数并点击"开始回测"</div>
                </div>
            )}
            </Col>
        </Row>
    </div>
  );
};

export default BacktestPage;
