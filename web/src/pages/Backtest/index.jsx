import React, { useState, useEffect } from 'react';
import { Card, Form, Input, Select, Button, Row, Col, message, Radio, Alert, Switch, Tag, DatePicker, Tooltip } from 'antd';
import { 
  SafetyCertificateOutlined, 
  PlayCircleOutlined,
  SaveOutlined,
  ReloadOutlined,
  DashboardOutlined,
  LineChartOutlined
} from '@ant-design/icons';
import axios from 'axios';
import ContractInfo from '../../components/ContractInfo';
import MetricsPanel from '../../components/MetricsPanel';
import ChartPanel from '../../components/ChartPanel';
import { useBacktest } from '../../context/BacktestContext';

import SingleBacktestResult from './SingleBacktestResult';
import BatchBacktestResult from './BatchBacktestResult';

const { Option } = Select;

const BacktestPage = () => {
  const { results, setResults, symbols, setSymbols, savedFormValues, setSavedFormValues, savedStrategyType, setSavedStrategyType } = useBacktest();
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();
  const [strategyType, setStrategyType] = useState(savedStrategyType || 'MA55BreakoutStrategy');
  const [quoteInfo, setQuoteInfo] = useState(null);
  const [autoOptimize, setAutoOptimize] = useState(false);
  const [currentParams, setCurrentParams] = useState(null);
  const [isFullScreen, setIsFullScreen] = useState(false);
  
  // Local cache for lists to avoid repeated API calls if we were to move this to context fully
  // For now, we fetch on mount if symbols is empty or just fetch every time to be safe
  const [futuresList, setFuturesList] = useState([]);
  const [stockList, setStockList] = useState([]);

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
            const initialValues = { ...savedFormValues };
            if (initialValues.symbol && !Array.isArray(initialValues.symbol)) {
                initialValues.symbol = [initialValues.symbol];
            }
            
            form.setFieldsValue(initialValues);
            if (initialValues.symbol && initialValues.symbol.length > 0) {
                fetchQuote(initialValues.symbol);
            }
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

  const fetchQuote = (symbol) => {
    if (!symbol) return;
    // 如果是数组（多选），只获取第一个的行情，或者不获取
    const targetSymbol = Array.isArray(symbol) ? symbol[0] : symbol;
    if (!targetSymbol) return;

    const marketType = form.getFieldValue('market_type') || 'futures';
    const dataSource = form.getFieldValue('data_source') || 'main';
    axios.get(`http://localhost:8000/api/quote/latest?symbol=${targetSymbol}&market_type=${marketType}&data_source=${dataSource}`)
      .then(res => {
        setQuoteInfo(res.data);
      })
      .catch(err => {
        console.error("Failed to fetch quote", err);
        setQuoteInfo(null);
      });
  };

  const onSymbolChange = (value) => {
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
            setQuoteInfo(null);
        }
    } else {
        setQuoteInfo(null);
    }
  };

  const onFinish = async (values) => {
    let selectedSymbols = values.symbol;
    // 类型安全检查：确保是数组
    if (selectedSymbols && !Array.isArray(selectedSymbols)) {
        selectedSymbols = [selectedSymbols];
    }

    if (!selectedSymbols || selectedSymbols.length === 0) {
        message.error('请至少选择一个品种');
        return;
    }

    setLoading(true);
    setResults(null); // Clear previous results
    
    // 如果是单个品种，保持原有逻辑（但为了统一，可以视为长度为1的批量）
    // 为了更好的用户体验，如果只选了一个，直接展示结果，不显示折叠面板
    // 如果选了多个，则使用新逻辑
    
    const isBatch = selectedSymbols.length > 1;
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
      } else if (strategyType === 'MA20MA55CrossoverStrategy' || strategyType === 'StockMA20MA55LongOnlyStrategy') {
        params = {
            fast_period: 20,
            slow_period: 55,
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

      setCurrentParams(params);
      
      // 批量执行逻辑
      // 为每个品种构建 payload
      for (const symbolCode of selectedSymbols) {
          // 获取品种特定的 multiplier
          const symbolObj = symbols.find(s => s.code === symbolCode);
          const specificMultiplier = symbolObj ? symbolObj.multiplier : contractMultiplier;
          
          // 复制并覆盖 multiplier
          const specificParams = { ...params, contract_multiplier: specificMultiplier };

          const payload = {
            symbol: symbolCode,
            period: values.period,
            market_type: values.market_type || 'futures',
            data_source: values.data_source || 'main',
            strategy_params: specificParams,
            initial_cash: parseFloat(values.initial_cash || 1000000),
            auto_optimize: autoOptimize,
            strategy_name: strategyType
          };

          if (values.date_range && values.date_range.length === 2) {
            payload.start_date = values.date_range[0].format('YYYY-MM-DD');
            payload.end_date = values.date_range[1].format('YYYY-MM-DD');
          }
          
          try {
              // 串行执行以避免并发问题 (如果后端支持，可以改为 Promise.all)
              const response = await axios.post('http://localhost:8000/api/backtest', payload);
              batchResults.push({
                  symbol: symbolCode,
                  success: true,
                  data: response.data
              });
          } catch (err) {
              console.error(`Backtest failed for ${symbolCode}:`, err);
              batchResults.push({
                  symbol: symbolCode,
                  success: false,
                  error: err.response?.data?.detail || err.message
              });
          }
          
          completedCount++;
          // 可以添加 setProgress(completedCount / total)
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
    
    const safeNum = (val) => {
        if (val === null || val === undefined || val === '') return null;
        if (typeof val === 'string' && val.includes('%')) {
            val = val.replace('%', '');
        }
        const num = Number(val);
        return isNaN(num) ? null : num;
    };

    try {
      const payload = {
        symbol: form.getFieldValue('symbol'),
        period: form.getFieldValue('period'),
        strategy_name: strategyType,
        strategy_params: currentParams || {},
        initial_cash: safeNum(results.metrics.initial_cash),
        final_value: safeNum(results.metrics.final_value),
        net_profit: safeNum(results.metrics.net_profit),
        return_rate: safeNum(results.metrics.return_rate),
        sharpe_ratio: safeNum(results.metrics.sharpe_ratio),
        max_drawdown: safeNum(results.metrics.max_drawdown),
        total_trades: safeNum(results.metrics.total_trades),
        win_rate: safeNum(results.metrics.win_rate),
        detail_data: results
      };
      
      await axios.post('http://localhost:8000/api/backtest/save', payload);
      message.success('回测结果已保存');
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
                        form.setFieldsValue({ symbol: undefined });
                        if (val === 'stock') {
                            form.setFieldsValue({ data_source: 'main' });
                        }
                        switchSymbols(val);
                    }}>
                    <Option value="futures">期货</Option>
                    <Option value="stock">股票</Option>
                    </Select>
                </Form.Item>

                <Form.Item 
                    name="data_source" 
                    label="数据源" 
                    initialValue="main"
                    tooltip="选择'主力连续'将使用主力合约拼接数据；选择'加权指数'将使用加权指数数据(如可用)"
                    shouldUpdate={(prev, curr) => prev.market_type !== curr.market_type}
                >
                    <Select disabled={form.getFieldValue('market_type') === 'stock'}>
                    <Option value="main">主力连续</Option>
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

                <ContractInfo 
                    form={form} 
                    quoteInfo={quoteInfo} 
                />

                <Form.Item label="选择策略">
                    <Select value={strategyType} onChange={(val) => {
                        setStrategyType(val);
                        setSavedStrategyType(val);
                        // 切换策略时重置默认值
                        if (val === 'MA55BreakoutStrategy' || val === 'MA55TouchExitStrategy' || val === 'MA20MA55CrossoverStrategy' || val === 'MA20MA55PartialTakeProfitStrategy' || val === 'MA20MA55RiskRewardStrategy' || val === 'MA5MA20CrossoverStrategy' || val === 'MA5MA55CrossoverStrategy') {
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
                        } else if (val === 'MA20MA55CrossoverStrategy' || val === 'MA20MA55PartialTakeProfitStrategy' || val === 'StockMA20MA55LongOnlyStrategy' || val === 'DualMAFixedTPSLStrategy' || val === 'MA20MA55RiskRewardStrategy' || val === 'MA5MA20CrossoverStrategy' || val === 'MA5MA55CrossoverStrategy') {
                                initialValues.fast_period = 20;
                                initialValues.slow_period = 55;
                                
                                if (val === 'MA5MA20CrossoverStrategy') {
                                    initialValues.fast_period = 5;
                                    initialValues.slow_period = 20;
                                } else if (val === 'MA5MA55CrossoverStrategy') {
                                    initialValues.fast_period = 5;
                                    initialValues.slow_period = 55;
                                    initialValues.allow_reverse = true;
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
                
                <Form.Item label="回测周期" name="period">
                    <Select>
                    <Option value="daily">日线</Option>
                    <Option value="60">60分钟</Option>
                    <Option value="30">30分钟</Option>
                    <Option value="15">15分钟</Option>
                    <Option value="5">5分钟</Option>
                    </Select>
                </Form.Item>

                <Form.Item label="时间范围" name="date_range">
                    <DatePicker.RangePicker style={{ width: '100%' }} />
                </Form.Item>

                {strategyType === 'TrendFollowingStrategy' || strategyType === 'MA20MA55CrossoverStrategy' || strategyType === 'MA20MA55PartialTakeProfitStrategy' || strategyType === 'StockMA20MA55LongOnlyStrategy' || strategyType === 'DualMAFixedTPSLStrategy' || strategyType === 'MA20MA55RiskRewardStrategy' || strategyType === 'MA5MA20CrossoverStrategy' || strategyType === 'MA5MA55CrossoverStrategy' ? (
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
                        if ((strategyType === 'TrendFollowingStrategy' || !sizeMode || sizeMode === 'atr_risk') && strategyType !== 'MA20MA55RiskRewardStrategy') {
                            return (
                                <Form.Item name="atr_multiplier" label="ATR止损倍数">
                                    <Input type="number" step="0.1" />
                                </Form.Item>
                            );
                        }
                        return null;
                    }}
                </Form.Item>

                {strategyType === 'MA55BreakoutStrategy' || strategyType === 'MA55TouchExitStrategy' || strategyType === 'MA20MA55CrossoverStrategy' || strategyType === 'MA20MA55PartialTakeProfitStrategy' || strategyType === 'DKXStrategy' || strategyType === 'DKXPartialTakeProfitStrategy' || strategyType === 'DKXFixedTPSLStrategy' || strategyType === 'StockMA20MA55LongOnlyStrategy' || strategyType === 'DualMAFixedTPSLStrategy' || strategyType === 'MA20MA55RiskRewardStrategy' || strategyType === 'MA5MA20CrossoverStrategy' || strategyType === 'MA5MA55CrossoverStrategy' ? (
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
                    <Switch checked={autoOptimize} onChange={setAutoOptimize} />
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
                        <Button icon={<ReloadOutlined />} onClick={form.submit} block size="large">
                            刷新图表
                        </Button>
                        </Tooltip>
                </Form.Item>
                </Form>
            </Card>
            </Col>
            
            <Col span={isFullScreen ? 24 : 18} style={{ height: '100%', overflowY: 'auto' }}>
            {results ? (
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
