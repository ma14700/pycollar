import React, { useState, useEffect, useRef } from 'react';
import { Card, Form, Input, InputNumber, Select, Button, Row, Col, message, Radio, Alert, Switch, Tag, DatePicker, Tooltip } from 'antd';
import { 
  SafetyCertificateOutlined, 
  PlayCircleOutlined,
  SaveOutlined,
  ReloadOutlined,
  DashboardOutlined,
  LineChartOutlined
} from '@ant-design/icons';
import axios from 'axios';
import dayjs from 'dayjs';
import ContractInfo from '../../components/ContractInfo';
import MetricsPanel from '../../components/MetricsPanel';
import ChartPanel from '../../components/ChartPanel';
import { useBacktest } from '../../context/BacktestContext';
import DataProviderSelect from '../../components/DataProviderSelect';
import DataSourceInfo from '../../components/DataSourceInfo';
import { buildBacktestSaveRequests } from '../../utils/backtestSave';
import { contractWindow, applyContractBacktest, normalizeContractMonths, buildBacktestTargets } from '../../utils/contractBacktest';
import BacktestLoading from '../../components/BacktestLoading';

import SingleBacktestResult from './SingleBacktestResult';
import BatchBacktestResult from './BatchBacktestResult';

const { Option } = Select;

const BacktestPage = () => {
  const { results, setResults, symbols, setSymbols, savedFormValues, setSavedFormValues, savedStrategyType, setSavedStrategyType } = useBacktest();
  const [loading, setLoading] = useState(false);
  const [activeRun, setActiveRun] = useState(null);
  const [form] = Form.useForm();
  const [defaultDateRange] = useState(() => [
    dayjs('2025-01-01'),
    dayjs(new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' })),
  ]);
  const [strategyType, setStrategyType] = useState(savedStrategyType || 'MA55BreakoutStrategy');
  const isMA144SignalStrategy = ['MA20MA144LongOnlyStrategy', 'MA20MA144ShortOnlyStrategy', 'MA20MA144LongShortStrategy'].includes(strategyType);
  const isShortMA144Strategy = strategyType === 'MA20MA144ShortOnlyStrategy';
  const isLongShortMA144Strategy = strategyType === 'MA20MA144LongShortStrategy';
  const isDirectionalMA55Strategy = ['MA20MA55LongOnlyStrategy', 'MA20MA55ShortOnlyStrategy'].includes(strategyType);
  const [quoteInfo, setQuoteInfo] = useState(null);
  const quoteRequestId = useRef(0);
  const [autoOptimize, setAutoOptimize] = useState(false);
  const [currentParams, setCurrentParams] = useState(null);
  const [isFullScreen, setIsFullScreen] = useState(false);
  
  // Local cache for lists to avoid repeated API calls if we were to move this to context fully
  // For now, we fetch on mount if symbols is empty or just fetch every time to be safe
  const [futuresList, setFuturesList] = useState([]);
  const [stockList, setStockList] = useState([]);
  const selectedProducts = Form.useWatch('symbol', form);
  const selectedMarket = Form.useWatch('market_type', form) || 'futures';
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
    axios.get('http://localhost:8000/api/futures/contracts', { params: { symbol: singleProduct } })
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
        
        if (savedFormValues) {
            const marketType = savedFormValues.market_type || 'futures';
            const list = marketType === 'stock' ? sList : fList;
            setSymbols(list || []);

            // 确保 symbol 是数组，兼容旧的单选配置
            const initialValues = { ...savedFormValues,
                date_range: savedFormValues.date_range === undefined ? defaultDateRange : savedFormValues.date_range,
                entry_delay_bars: savedFormValues.entry_delay_bars ?? 1,
                exit_delay_bars: savedFormValues.exit_delay_bars ?? 1,
                data_provider: savedFormValues.data_provider || (marketType === 'stock' ? 'akshare' : 'tqsdk') };
            if (initialValues.symbol && !Array.isArray(initialValues.symbol)) {
                initialValues.symbol = [initialValues.symbol];
            }
            initialValues.contract_month = marketType === 'futures' ? normalizeContractMonths(initialValues.contract_month) : [];
            if (initialValues.contract_month.length) {
                const window = contractWindow(initialValues.contract_month[0]);
                initialValues.date_range = initialValues.contract_month.length === 1 ? [dayjs(window.start_date), dayjs(window.end_date)] : null;
                initialValues.data_provider = 'tqsdk';
                initialValues.data_source = 'main';
            }

            form.setFieldsValue(initialValues);
            
            // 强制刷新 multiplier (防止保存的旧值有误)
            if (initialValues.symbol && initialValues.symbol.length === 1) {
                const targetSymbolCode = Array.isArray(initialValues.symbol) ? initialValues.symbol[0] : initialValues.symbol;
                const targetSymbol = list.find(s => s.code === targetSymbolCode);
                if (targetSymbol) {
                    form.setFieldsValue({ contract_multiplier: targetSymbol.multiplier });
                }
            }
            fetchQuote(initialValues.symbol);
        } else {
            // Initialize with futures
            switchSymbols('futures', fList, sList);
        }
      } catch (err) {
        console.error(err);
        message.error('无法连接到后端服务获取品种数据');
      }
    };
    fetchData();
    
    // Set initial form values
    if (!savedFormValues) {
        form.setFieldsValue({
            market_type: 'futures',
            period: 'daily',
            initial_cash: 1000000
        });
    }
  }, []);

  const switchSymbols = (marketType, fList = futuresList, sList = stockList) => {
    const list = marketType === 'stock' ? sList : fList;
    setSymbols(list || []);
    
    if (list && list.length > 0) {
      let defaultSymbol = list[0];
      if (marketType === 'futures') {
        defaultSymbol = list.find(s => s.code === 'SH0') || list[0];
      }
      
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
    axios.get('http://localhost:8000/api/quote/latest', { params: { symbol: targetSymbol, market_type: marketType, data_source: dataSource, data_provider: dataProvider } })
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

    setActiveRun({ total: targets.length, completed: 0, failed: 0, startedAt: Date.now(),
        strategy: strategyType, period: values.period, provider: values.data_provider || (values.market_type === 'stock' ? 'akshare' : 'tqsdk'),
        symbol: targets[0].symbol, unit: normalizeContractMonths(values.contract_month).length ? '合约' : '品种' });
    setLoading(true);
    setResults(null); // Clear previous results

    // 如果是单个品种，保持原有逻辑（但为了统一，可以视为长度为1的批量）
    // 为了更好的用户体验，如果只选了一个，直接展示结果，不显示折叠面板
    // 如果选了多个，则使用新逻辑

    const batchResults = [];
    let completedCount = 0;

    try {
      let params = {};
      const riskPerTrade = values.risk_per_trade !== undefined ? parseFloat(values.risk_per_trade) : 0.02;
      const equityPercent = values.equity_percent !== undefined ? parseFloat(values.equity_percent) : 0.1;
      const contractMultiplier = values.contract_multiplier ? parseInt(values.contract_multiplier) : 1;
      const marginRate = values.margin_rate !== undefined ? parseFloat(values.margin_rate) : 0.1;

      // Strategy params construction logic
      if (strategyType === 'TrendFollowingStrategy') {
        params = {
          fast_period: parseInt(values.fast_period),
          slow_period: parseInt(values.slow_period),
          atr_period: 14,
          atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 2.0,
          risk_per_trade: riskPerTrade,
          equity_percent: equityPercent,
          margin_rate: marginRate,
          contract_multiplier: contractMultiplier,
          use_expma: false,
          size_mode: values.size_mode || 'fixed',
          fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20
        };
      } else if (isMA144SignalStrategy) {
        params = {
          fast_period: 20,
          slow_period: 144,
          exit_period: 55,
          size_mode: 'fixed',
          fixed_size: Number(values.fixed_size || 20),
          margin_rate: marginRate,
          contract_multiplier: contractMultiplier,
        };
      } else if (strategyType === 'MA55BreakoutStrategy') {
        params = {
          ma_period: 55,
          macd_fast: 12,
          macd_slow: 26,
          macd_signal: values.macd_signal ? parseInt(values.macd_signal) : 9,
          atr_period: 14,
          atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
          risk_per_trade: riskPerTrade,
          equity_percent: equityPercent,
          margin_rate: marginRate,
          size_mode: values.size_mode || 'fixed',
          fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
          contract_multiplier: contractMultiplier,
          use_trailing_stop: false
        };
      } else if (strategyType === 'MA55TouchExitStrategy') {
        params = {
            ma_period: 55,
            atr_period: 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier,
            weak_threshold: 7.0
        };
      } else if (strategyType === 'MA20MA55CrossoverStrategy' || isDirectionalMA55Strategy || strategyType === 'StockMA20MA55LongOnlyStrategy' || strategyType === 'MA20MA60CrossoverStrategy') {
        params = {
            fast_period: values.fast_period ? parseInt(values.fast_period) : 20,
            slow_period: values.slow_period ? parseInt(values.slow_period) : strategyType === 'MA20MA60CrossoverStrategy' ? 60 : 55,
            atr_period: 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      } else if (strategyType === 'MA20MA55PartialTakeProfitStrategy') {
        params = {
            fast_period: values.fast_period ? parseInt(values.fast_period) : 20,
            slow_period: values.slow_period ? parseInt(values.slow_period) : 55,
            atr_period: 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier,
            take_profit_points: values.take_profit_points ? parseFloat(values.take_profit_points) : 0
        };
      } else if (strategyType === 'DKXStrategy') {
        params = {
            dkx_period: values.dkx_period ? parseInt(values.dkx_period) : 20,
            dkx_ma_period: values.dkx_ma_period ? parseInt(values.dkx_ma_period) : 10,
            atr_period: 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      } else if (strategyType === 'DKXPartialTakeProfitStrategy') {
        params = {
            dkx_period: values.dkx_period ? parseInt(values.dkx_period) : 20,
            dkx_ma_period: values.dkx_ma_period ? parseInt(values.dkx_ma_period) : 10,
            atr_period: 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier,
            take_profit_points: values.take_profit_points ? parseFloat(values.take_profit_points) : 0
        };
      } else if (strategyType === 'DKXFixedTPSLStrategy') {
        params = {
            dkx_period: values.dkx_period ? parseInt(values.dkx_period) : 20,
            dkx_ma_period: values.dkx_ma_period ? parseInt(values.dkx_ma_period) : 10,
            take_profit_points: values.take_profit_points ? parseFloat(values.take_profit_points) : 100,
            stop_loss_points: values.stop_loss_points ? parseFloat(values.stop_loss_points) : 50,
            atr_period: 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 3.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      } else if (strategyType === 'DualMAFixedTPSLStrategy') {
        params = {
            fast_period: values.fast_period ? parseInt(values.fast_period) : 20,
            slow_period: values.slow_period ? parseInt(values.slow_period) : 55,
            ma_type: values.ma_type || 'SMA',
            sl_mode: values.sl_mode || 'points',
            sl_value: values.sl_value ? parseFloat(values.sl_value) : 50.0,
            tp_mode: values.tp_mode || 'points',
            tp_value: values.tp_value ? parseFloat(values.tp_value) : 100.0,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      } else if (strategyType === 'MA20MA55RiskRewardStrategy') {
        params = {
            fast_period: values.fast_period ? parseInt(values.fast_period) : 20,
            slow_period: values.slow_period ? parseInt(values.slow_period) : 55,
            risk_reward_ratio: values.risk_reward_ratio ? parseFloat(values.risk_reward_ratio) : 2.0,
            atr_period: values.atr_period ? parseInt(values.atr_period) : 14,
            atr_multiplier: values.atr_multiplier ? parseFloat(values.atr_multiplier) : 2.0,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      } else if (strategyType === 'MA5MA20CrossoverStrategy') {
        params = {
            fast_period: values.fast_period ? parseInt(values.fast_period) : 5,
            slow_period: values.slow_period ? parseInt(values.slow_period) : 20,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      } else if (strategyType === 'MA5MA55CrossoverStrategy') {
        params = {
            fast_period: values.fast_period ? parseInt(values.fast_period) : 5,
            slow_period: values.slow_period ? parseInt(values.slow_period) : 55,
            allow_reverse: values.allow_reverse !== undefined ? values.allow_reverse : true,
            risk_per_trade: riskPerTrade,
            equity_percent: equityPercent,
            margin_rate: marginRate,
            size_mode: values.size_mode || 'fixed',
            fixed_size: values.fixed_size ? parseInt(values.fixed_size) : 20,
            contract_multiplier: contractMultiplier
        };
      }

      if (isDirectionalMA55Strategy) params.size_mode = 'fixed';
      params.entry_delay_bars = Number(values.entry_delay_bars);
      params.exit_delay_bars = Number(values.exit_delay_bars);
      setCurrentParams(params);

      // 批量执行逻辑
      // 为每个品种构建 payload
      for (const target of targets) {
          const symbolCode = target.base_symbol;
          // 获取品种特定的 multiplier
          const symbolObj = symbols.find(s => s.code === symbolCode);
          const specificMultiplier = symbolObj ? symbolObj.multiplier : contractMultiplier;

          // 复制并覆盖 multiplier
          const specificParams = { ...params, contract_multiplier: specificMultiplier };

          let payload = {
            symbol: symbolCode,
            period: values.period,
            market_type: values.market_type || 'futures',
            data_source: values.data_source || 'main',
            data_provider: values.data_provider || (values.market_type === 'stock' ? 'akshare' : 'tqsdk'),
            strategy_params: specificParams,
            initial_cash: parseFloat(values.initial_cash || 1000000),
            auto_optimize: isMA144SignalStrategy ? false : autoOptimize,
            strategy_name: strategyType
          };

          if (values.date_range && values.date_range.length === 2) {
            payload.start_date = values.date_range[0].format('YYYY-MM-DD');
            payload.end_date = values.date_range[1].format('YYYY-MM-DD');
          }
          payload = applyContractBacktest(payload, target.contract_month);
          setActiveRun(previous => ({ ...previous, symbol: payload.symbol,
              symbolName: symbolObj?.name?.match(/\(([^)]+)\)/)?.[1] || symbolObj?.name,
              provider: payload.data_provider }));

          try {
              // 串行执行以避免并发问题 (如果后端支持，可以改为 Promise.all)
              const response = await axios.post('http://localhost:8000/api/backtest', payload);
              batchResults.push({
                  symbol: payload.symbol,
                  success: true,
                  data: { ...response.data, backtest_request: payload }
              });
          } catch (err) {
              console.error(`Backtest failed for ${payload.symbol}:`, err);
              batchResults.push({
                  symbol: payload.symbol,
                  success: false,
                  error: err.response?.data?.detail || err.message
              });
          }

          completedCount++;
          setActiveRun(previous => ({ ...previous, completed: completedCount,
              failed: batchResults.filter(item => !item.success).length }));
      }
      
      // 处理结果
      if (batchResults.length === 1) {
          if (batchResults[0].success) {
              setResults(batchResults[0].data);
              message.success('回测完成');
          } else {
              message.error(`回测失败: ${batchResults[0].error}`);
          }
      } else {
          // 多品种结果
          setResults({
              isBatch: true,
              items: batchResults,
              summary: {
                  total: batchResults.length,
                  success: batchResults.filter(r => r.success).length,
                  failed: batchResults.filter(r => !r.success).length
              }
          });
          message.success(`批量回测完成: 成功 ${batchResults.filter(r => r.success).length}/${batchResults.length}`);
      }

    } catch (error) {
      console.error(error);
      message.error('执行出错: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveBacktest = async () => {
    if (!results) return;
    
    try {
      const payloads = buildBacktestSaveRequests(results, {
        symbol: form.getFieldValue('symbol'),
        period: form.getFieldValue('period'),
        strategy_name: strategyType,
        strategy_params: currentParams || {},
      });
      if (!payloads.length) {
        message.warning('暂无成功的回测结果可保存');
        return;
      }
      for (const payload of payloads) {
        await axios.post('http://localhost:8000/api/backtest/save', payload);
      }
      message.success(payloads.length > 1 ? `已保存 ${payloads.length} 个品种的回测结果` : '回测结果已保存');
    } catch (error) {
      message.error('保存失败: ' + error.message);
    }
  };

  return (
    <div style={{ height: '100%', padding: '24px' }}>
        <Row gutter={24} style={{ height: '100%' }}>
            <Col span={isFullScreen ? 0 : 6} style={{ display: isFullScreen ? 'none' : 'block' }}>
            <Card title={<span><SafetyCertificateOutlined /> 策略配置</span>} variant="borderless" style={{ height: '100%', borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)', overflowY: 'auto' }}>
                <Form form={form} layout="vertical" onFinish={onFinish} 
                    onValuesChange={(changedValues, allValues) => {
                        setSavedFormValues(allValues);
                    }}
                    initialValues={{
                    market_type: 'futures',
                    initial_cash: 1000000,
                    period: 'daily',
                    date_range: defaultDateRange,
                    entry_delay_bars: 1,
                    exit_delay_bars: 1,
                    fast_period: 10,
                    slow_period: 20,
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
                    <Option value="weighted">加权指数</Option>
                    </Select>
                </Form.Item>


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

                {selectedMarket === 'futures' && <Form.Item name="contract_month" label="具体合约（可多选）"
                    extra={!singleProduct ? '先选择一个交易品种，再选择具体合约。' : contractsError ? <span style={{ color: '#ff4d4f' }}>{contractsError} <Button type="link" size="small" onClick={() => { contractCache.current.delete(singleProduct); setContractReload(value => value + 1); }}>重试</Button></span> : '具体合约使用天勤行情；清空后恢复原有品种回测。'}>
                    <Select mode="multiple" maxTagCount="responsive" allowClear showSearch optionFilterProp="label" placeholder="可选择多个合约，如 2605、2701"
                        disabled={!singleProduct || loading} loading={contractsLoading} options={contractOptions}
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

                <Form.Item label="选择策略">
                    <Select value={strategyType} onChange={(val) => {
                        setStrategyType(val);
                        setSavedStrategyType(val);
                        // 切换策略时重置默认值
                        if (['MA20MA55LongOnlyStrategy', 'MA20MA55ShortOnlyStrategy'].includes(val)) {
                            form.setFieldsValue({ fast_period: 20, slow_period: 55, size_mode: 'fixed', fixed_size: 20 });
                        } else if (['MA20MA144LongOnlyStrategy', 'MA20MA144ShortOnlyStrategy', 'MA20MA144LongShortStrategy'].includes(val)) {
                            setAutoOptimize(false);
                            form.setFieldsValue({ fast_period: 20, slow_period: 144, exit_period: 55, size_mode: 'fixed', fixed_size: 20 });
                        } else if (val === 'MA55BreakoutStrategy' || val === 'MA55TouchExitStrategy' || val === 'MA20MA55CrossoverStrategy' || val === 'MA20MA55PartialTakeProfitStrategy' || val === 'MA20MA55RiskRewardStrategy' || val === 'MA5MA20CrossoverStrategy' || val === 'MA5MA55CrossoverStrategy' || val === 'MA20MA60CrossoverStrategy') {
                            let initialValues = {
                                atr_period: 14,
                                atr_multiplier: 3.0,
                                size_mode: 'fixed',
                                fixed_size: 20,
                                risk_per_trade: 0.02
                            };
                            
                            if (val === 'MA55BreakoutStrategy' || val === 'MA55TouchExitStrategy') {
                                initialValues.ma_period = 55;
                                initialValues.macd_fast = 12;
                                initialValues.macd_slow = 26;
                                initialValues.macd_signal = 9;
                        } else if (val === 'MA20MA55CrossoverStrategy' || val === 'MA20MA55PartialTakeProfitStrategy' || val === 'StockMA20MA55LongOnlyStrategy' || val === 'DualMAFixedTPSLStrategy' || val === 'MA20MA55RiskRewardStrategy' || val === 'MA5MA20CrossoverStrategy' || val === 'MA5MA55CrossoverStrategy' || val === 'MA20MA60CrossoverStrategy') {
                                initialValues.fast_period = 20;
                                initialValues.slow_period = 55;
                                
                                if (val === 'MA5MA20CrossoverStrategy') {
                                    initialValues.fast_period = 5;
                                    initialValues.slow_period = 20;
                                } else if (val === 'MA5MA55CrossoverStrategy') {
                                    initialValues.fast_period = 5;
                                    initialValues.slow_period = 55;
                                    initialValues.allow_reverse = true;
                                } else if (val === 'MA20MA60CrossoverStrategy') {
                                    initialValues.fast_period = 20;
                                    initialValues.slow_period = 60;
                                } else if (val === 'MA20MA55PartialTakeProfitStrategy') {
                                    initialValues.take_profit_points = 50;
                                } else if (val === 'DualMAFixedTPSLStrategy') {
                                    initialValues.ma_type = 'SMA';
                                    initialValues.sl_mode = 'points';
                                    initialValues.sl_value = 50;
                                    initialValues.tp_mode = 'points';
                                    initialValues.tp_value = 100;
                                } else if (val === 'MA20MA55RiskRewardStrategy') {
                                    initialValues.risk_reward_ratio = 2.0;
                                    initialValues.atr_multiplier = 2.0;
                                }
                            }
                            
                            form.setFieldsValue(initialValues);
                        } else if (val === 'TrendFollowingStrategy') {
                            form.setFieldsValue({
                                fast_period: 10,
                                slow_period: 30,
                                atr_period: 14,
                                atr_multiplier: 2.0,
                                risk_per_trade: 0.02
                            });
                        } else if (val === 'DKXStrategy') {
                            form.setFieldsValue({
                                dkx_period: 20,
                                dkx_ma_period: 10,
                                atr_period: 14,
                                atr_multiplier: 3.0,
                                size_mode: 'fixed',
                                fixed_size: 20,
                                risk_per_trade: 0.02
                            });
                        } else if (val === 'DKXPartialTakeProfitStrategy') {
                            form.setFieldsValue({
                                dkx_period: 20,
                                dkx_ma_period: 10,
                                atr_period: 14,
                                atr_multiplier: 3.0,
                                size_mode: 'fixed',
                                fixed_size: 20,
                                risk_per_trade: 0.02,
                                take_profit_points: 50
                            });
                        } else if (val === 'DKXFixedTPSLStrategy') {
                            form.setFieldsValue({
                                dkx_period: 20,
                                dkx_ma_period: 10,
                                atr_period: 14,
                                atr_multiplier: 3.0,
                                size_mode: 'fixed',
                                fixed_size: 20,
                                risk_per_trade: 0.02,
                                take_profit_points: 100,
                                stop_loss_points: 50
                            });
                        }
                    }}>
                        <Option value="MA55BreakoutStrategy">MA55突破+背离离场</Option>
                        <Option value="MA55TouchExitStrategy">MA55突破+触碰平仓</Option>
                        <Option value="MA20MA55CrossoverStrategy">20/55双均线交叉(多空)</Option>
                        <Option value="MA20MA55LongOnlyStrategy">20/55双均线交叉多（只做多）</Option>
                        <Option value="MA20MA55ShortOnlyStrategy">20/55双均线交叉空（只做空）</Option>
                        <Option value="MA20MA60CrossoverStrategy">20/60双均线交叉(多空)</Option>
                        <Option value="MA20MA144LongOnlyStrategy">20/144金叉做多·20/55死叉离场</Option>
                        <Option value="MA20MA144ShortOnlyStrategy">20/144死叉做空·20/55金叉离场</Option>
                        <Option value="MA20MA144LongShortStrategy">20/144多空入场·20/55交叉离场</Option>
                        <Option value="MA5MA20CrossoverStrategy">5/20双均线交叉(多空)</Option>
                        <Option value="MA5MA55CrossoverStrategy">5/55日均线多空交叉</Option>
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

                {isDirectionalMA55Strategy && <Alert type="info" showIcon style={{ marginBottom: 16 }}
                    message={strategyType === 'MA20MA55LongOnlyStrategy' ? '金叉开多，死叉平多；不做空' : '死叉开空，金叉平空；不做多'}
                    description="使用固定手数，不加仓、不反手；离场后等待同方向的新交叉信号。默认 MA20 / MA55，按开仓和平仓 K 线设置执行。" />}
                {isMA144SignalStrategy && (
                    <Alert
                        type="info" showIcon style={{ marginBottom: 16 }}
                        message={isLongShortMA144Strategy ? 'MA20 / MA144 金叉做多、死叉做空；MA20 / MA55 反向交叉离场' : isShortMA144Strategy ? 'MA20 / MA144 死叉开空，MA20 / MA55 金叉离场' : 'MA20 / MA144 金叉开多，MA20 / MA55 死叉离场'}
                        description={`${isLongShortMA144Strategy ? '空仓时金叉开多、死叉开空；多单在 MA20 下穿 MA55 时离场，空单在 MA20 上穿 MA55 时离场。不加仓，持仓期间只按离场规则处理，不直接反手；平仓成交后等待新的 MA20/144 交叉。' : isShortMA144Strategy ? '仅做空，不加仓；离场后等待下一次 MA20 下穿 MA144。' : '仅做多，不加仓；离场后等待下一次 MA20 上穿 MA144。'}均线按所选 K 线周期计算，日线下为 20 / 55 / 144 日均线。信号收盘确认，按开仓 / 平仓 K 线设置等待成交，回测末尾沿用平台平仓规则。`}
                    />
                )}

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
                            <Form.Item name={name} label={label} tooltip="信号确认后，第几根 K 线的开盘价成交。1 为下一根，2 为第二根。" rules={[
                                { required: true, message: '请输入 K 线根数' },
                                { validator: (_, value) => value == null || (Number.isInteger(value) && value >= 1) ? Promise.resolve() : Promise.reject(new Error('须为大于等于 1 的整数')) },
                            ]}>
                                <InputNumber min={1} precision={0} style={{ width: '100%' }} />
                            </Form.Item>
                        </Col>
                    ))}
                </Row>
                <div style={{ color: '#8b96a8', fontSize: 12, lineHeight: 1.7, marginTop: -8, marginBottom: 20 }}>
                    1 = 下一根开盘，2 = 第二根开盘，按实际 K 线计数。适用于信号市价单；反手取两者较大值，止盈止损挂单保持触价成交。
                </div>

                {isMA144SignalStrategy ? null : isDirectionalMA55Strategy || strategyType === 'TrendFollowingStrategy' || strategyType === 'MA20MA55CrossoverStrategy' || strategyType === 'MA20MA55PartialTakeProfitStrategy' || strategyType === 'StockMA20MA55LongOnlyStrategy' || strategyType === 'DualMAFixedTPSLStrategy' || strategyType === 'MA20MA55RiskRewardStrategy' || strategyType === 'MA5MA20CrossoverStrategy' || strategyType === 'MA5MA55CrossoverStrategy' || strategyType === 'MA20MA60CrossoverStrategy' ? (
                    <>
                        <Row gutter={16}>
                            <Col span={12}>
                                <Form.Item name="fast_period" label="快线周期">
                                    <Input type="number" />
                                </Form.Item>
                            </Col>
                            <Col span={12}>
                                <Form.Item name="slow_period" label="慢线周期">
                                    <Input type="number" />
                                </Form.Item>
                            </Col>
                        </Row>
                        {strategyType === 'MA5MA55CrossoverStrategy' && (
                            <Row gutter={16}>
                                <Col span={12}>
                                    <Form.Item name="allow_reverse" label="允许反手" valuePropName="checked" tooltip="开启后：金叉平空开多，死叉平多开空；关闭后：仅平仓不反手">
                                        <Switch />
                                    </Form.Item>
                                </Col>
                            </Row>
                        )}
                        {strategyType === 'MA20MA55PartialTakeProfitStrategy' && (
                            <Form.Item name="take_profit_points" label="盈利平半仓点数" tooltip="当浮动盈利达到此点数时，平掉一半仓位">
                                <Input type="number" />
                            </Form.Item>
                        )}
                        {strategyType === 'MA20MA55RiskRewardStrategy' && (
                            <>
                                <Row gutter={16}>
                                    <Col span={12}>
                                        <Form.Item name="risk_reward_ratio" label="盈亏比(R:R)" tooltip="止盈距离 / 止损距离">
                                            <Input type="number" step="0.1" />
                                        </Form.Item>
                                    </Col>
                                    <Col span={12}>
                                        <Form.Item name="atr_multiplier" label="止损ATR倍数" tooltip="止损距离 = ATR * 倍数">
                                            <Input type="number" step="0.1" />
                                        </Form.Item>
                                    </Col>
                                </Row>
                                <Row gutter={16}>
                                    <Col span={12}>
                                        <Form.Item name="atr_period" label="ATR周期">
                                            <Input type="number" />
                                        </Form.Item>
                                    </Col>
                                </Row>
                            </>
                        )}
                        {strategyType === 'DualMAFixedTPSLStrategy' && (
                            <>
                                <Row gutter={16}>
                                    <Col span={12}>
                                        <Form.Item name="ma_type" label="均线类型">
                                            <Select>
                                                <Option value="SMA">简单均线 (SMA)</Option>
                                                <Option value="EMA">指数均线 (EMA)</Option>
                                            </Select>
                                        </Form.Item>
                                    </Col>
                                </Row>
                                <Row gutter={16}>
                                    <Col span={12}>
                                        <Form.Item name="tp_mode" label="止盈模式">
                                            <Select>
                                                <Option value="points">固定点数</Option>
                                                <Option value="percent">百分比 (%)</Option>
                                            </Select>
                                        </Form.Item>
                                    </Col>
                                    <Col span={12}>
                                        <Form.Item name="tp_value" label="止盈数值">
                                            <Input type="number" step="0.1" />
                                        </Form.Item>
                                    </Col>
                                </Row>
                                <Row gutter={16}>
                                    <Col span={12}>
                                        <Form.Item name="sl_mode" label="止损模式">
                                            <Select>
                                                <Option value="points">固定点数</Option>
                                                <Option value="percent">百分比 (%)</Option>
                                            </Select>
                                        </Form.Item>
                                    </Col>
                                    <Col span={12}>
                                        <Form.Item name="sl_value" label="止损数值">
                                            <Input type="number" step="0.1" />
                                        </Form.Item>
                                    </Col>
                                </Row>
                            </>
                        )}
                    </>
                ) : (strategyType === 'DKXStrategy' || strategyType === 'DKXPartialTakeProfitStrategy') ? (
                        <>
                            <Row gutter={16}>
                                <Col span={12}>
                                    <Form.Item name="dkx_period" label="DKX周期" tooltip="通常为20">
                                    <Input type="number" />
                                    </Form.Item>
                                </Col>
                                <Col span={12}>
                                    <Form.Item name="dkx_ma_period" label="MADKX周期" tooltip="通常为10">
                                    <Input type="number" />
                                    </Form.Item>
                                </Col>
                            </Row>
                            {strategyType === 'DKXPartialTakeProfitStrategy' && (
                                <Form.Item name="take_profit_points" label="盈利平半仓点数" tooltip="当浮动盈利达到此点数时，平掉一半仓位">
                                    <Input type="number" />
                                </Form.Item>
                            )}
                        </>
                ) : (
                    <>
                        <Form.Item name="ma_period" label="突破均线周期">
                            <Input type="number" />
                        </Form.Item>
                        
                        {strategyType === 'MA55BreakoutStrategy' && (
                            <Row gutter={16}>
                                <Col span={8}>
                                    <Form.Item name="macd_fast" label="MACD快">
                                        <Input type="number" />
                                    </Form.Item>
                                </Col>
                                <Col span={8}>
                                    <Form.Item name="macd_slow" label="MACD慢">
                                        <Input type="number" />
                                    </Form.Item>
                                </Col>
                                <Col span={8}>
                                    <Form.Item name="macd_signal" label="MACD信">
                                        <Input type="number" />
                                    </Form.Item>
                                </Col>
                            </Row>
                        )}
                    </>
                )}

                {strategyType === 'DKXStrategy' || strategyType === 'DKXPartialTakeProfitStrategy' || strategyType === 'DKXFixedTPSLStrategy' ? (
                    <>
                        <Row gutter={16}>
                            <Col span={12}>
                                <Form.Item name="dkx_period" label="DKX周期">
                                    <Input type="number" />
                                </Form.Item>
                            </Col>
                            <Col span={12}>
                                <Form.Item name="dkx_ma_period" label="DKX均线周期">
                                    <Input type="number" />
                                </Form.Item>
                            </Col>
                        </Row>
                        {strategyType === 'DKXPartialTakeProfitStrategy' && (
                            <Form.Item name="take_profit_points" label="止盈点数">
                                <Input type="number" />
                            </Form.Item>
                        )}
                        {strategyType === 'DKXFixedTPSLStrategy' && (
                            <Row gutter={16}>
                                <Col span={12}>
                                    <Form.Item name="take_profit_points" label="止盈点数">
                                        <Input type="number" />
                                    </Form.Item>
                                </Col>
                                <Col span={12}>
                                    <Form.Item name="stop_loss_points" label="止损点数">
                                        <Input type="number" />
                                    </Form.Item>
                                </Col>
                            </Row>
                        )}
                    </>
                ) : null}

                <Form.Item
                    noStyle
                    shouldUpdate={(prevValues, currentValues) => prevValues.size_mode !== currentValues.size_mode}
                >
                    {({ getFieldValue }) => {
                        const sizeMode = getFieldValue('size_mode');
                        if ((strategyType === 'TrendFollowingStrategy' || !sizeMode || sizeMode === 'atr_risk') && strategyType !== 'MA20MA55RiskRewardStrategy' && !isMA144SignalStrategy && !isDirectionalMA55Strategy) {
                            return (
                                <Form.Item name="atr_multiplier" label="ATR止损倍数">
                                    <Input type="number" step="0.1" />
                                </Form.Item>
                            );
                        }
                        return null;
                    }}
                </Form.Item>

                {isMA144SignalStrategy || isDirectionalMA55Strategy ? (
                    <Form.Item name="fixed_size" label="固定手数 (手)" initialValue={20} rules={[
                        { required: true, message: '请输入固定手数' },
                        { validator: (_, value) => Number.isInteger(Number(value)) && Number(value) > 0
                            ? Promise.resolve() : Promise.reject(new Error('固定手数须为正整数')) },
                    ]}>
                        <Input type="number" min={1} step={1} />
                    </Form.Item>
                ) : strategyType === 'MA55BreakoutStrategy' || strategyType === 'MA55TouchExitStrategy' || strategyType === 'MA20MA55CrossoverStrategy' || strategyType === 'MA20MA55PartialTakeProfitStrategy' || strategyType === 'DKXStrategy' || strategyType === 'DKXPartialTakeProfitStrategy' || strategyType === 'DKXFixedTPSLStrategy' || strategyType === 'StockMA20MA55LongOnlyStrategy' || strategyType === 'DualMAFixedTPSLStrategy' || strategyType === 'MA20MA55RiskRewardStrategy' || strategyType === 'MA5MA20CrossoverStrategy' || strategyType === 'MA5MA55CrossoverStrategy' || strategyType === 'MA20MA60CrossoverStrategy' ? (
                    <>
                        <Form.Item name="size_mode" label="开仓模式" initialValue="fixed">
                            <Radio.Group>
                                <Radio value="fixed">固定手数</Radio>
                                <Radio value="equity_percent">固定资金比例</Radio>
                                <Radio value="atr_risk">ATR风险</Radio>
                            </Radio.Group>
                        </Form.Item>
                        <Form.Item
                            noStyle
                            shouldUpdate={(prevValues, currentValues) => prevValues.size_mode !== currentValues.size_mode}
                        >
                            {({ getFieldValue }) => {
                                const mode = getFieldValue('size_mode');
                                if (mode === 'fixed') {
                                    return (
                                        <Form.Item name="fixed_size" label="固定手数 (手)" initialValue={20}>
                                            <Input type="number" />
                                        </Form.Item>
                                    );
                                } else if (mode === 'equity_percent') {
                                    return (
                                        <Form.Item name="equity_percent" label="资金比例 (0.1=10%)" initialValue={0.1}>
                                            <Input type="number" step="0.1" max="1.0" min="0.01" />
                                        </Form.Item>
                                    );
                                } else {
                                    return (
                                        <Form.Item name="risk_per_trade" label="单笔风险系数 (0.02=2%)" initialValue={0.02}>
                                            <Input type="number" step="0.01" />
                                        </Form.Item>
                                    );
                                }
                            }}
                        </Form.Item>
                    </>
                ) : (
                        <Form.Item name="risk_per_trade" label="单笔风险系数 (0.02=2%)">
                        <Input type="number" step="0.01" />
                        </Form.Item>
                )}

                <Form.Item name="margin_rate" label="保证金率 (0.1=10%)" initialValue={0.12}>
                    <Input type="number" step="0.01" max={1} min={0.01} />
                </Form.Item>

                <Form.Item name="optimal_entry" label="开仓最优模式" valuePropName="checked" initialValue={false}>
                        <div style={{ display: 'flex', alignItems: 'center' }}>
                            <Switch />
                            <Tooltip title="开启后，所有开仓、平仓、反手操作均以当前策略所选K线的中间点位 [(High+Low)/2] 作为执行价格（开启CheatOnOpen模式以确保成交）。">
                                <span style={{ marginLeft: 8, fontSize: '12px', color: '#888', cursor: 'pointer' }}>
                                    <SafetyCertificateOutlined style={{ marginRight: 4 }} />
                                    说明
                                </span>
                            </Tooltip>
                        </div>
                </Form.Item>
                
                <Form.Item name="contract_multiplier" label="合约乘数" hidden>
                    <Input type="number" />
                </Form.Item>
                {strategyType !== 'MA20MA55RiskRewardStrategy' && <Form.Item name="atr_period" hidden><Input /></Form.Item>}

                <Form.Item label="自动优化 (若收益<20%)" tooltip="当回测年化收益率低于20%时，系统会自动尝试优化参数以寻找更好的结果。">
                    <Switch checked={autoOptimize} onChange={setAutoOptimize} disabled={isMA144SignalStrategy} />
                </Form.Item>

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
                        <Button icon={<SaveOutlined />} onClick={handleSaveBacktest} block size="large" disabled={!results}>
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
            
            <Col span={isFullScreen ? 24 : 18} style={{ height: '100%', overflowY: 'auto' }}>
            {loading && activeRun ? <BacktestLoading run={activeRun} /> : results ? (
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
