import React, { useState, useEffect } from 'react';
import { Layout, Card, Form, Input, Select, Button, Row, Col, Statistic, message, Radio, Tabs, Alert, Switch, Tag, DatePicker } from 'antd';
import ReactECharts from 'echarts-for-react';
import axios from 'axios';
import Editor from '@monaco-editor/react';
import dayjs from 'dayjs';

const { Header, Content } = Layout;
const { Option } = Select;
const { TabPane } = Tabs;

function calculateMA(dayCount, data) {
  var result = [];
  for (var i = 0, len = data.length; i < len; i++) {
    if (i < dayCount - 1) {
      result.push('-');
      continue;
    }
    var sum = 0;
    for (var j = 0; j < dayCount; j++) {
      sum += data[i - j][1]; // close price
    }
    result.push((sum / dayCount).toFixed(2));
  }
  return result;
}

const App = () => {
  const [loading, setLoading] = useState(false);
  const [symbols, setSymbols] = useState([]);
  const [results, setResults] = useState(null);
  const [chartType, setChartType] = useState('line'); // 'line' or 'pie'
  const [form] = Form.useForm();
  const [strategyCode, setStrategyCode] = useState('');
  const [savingCode, setSavingCode] = useState(false);
  const [autoOptimize, setAutoOptimize] = useState(true);

  const [strategyType, setStrategyType] = useState('TrendFollowingStrategy');

  useEffect(() => {
    // 获取品种列表
    axios.get('http://localhost:8000/api/symbols')
      .then(res => {
        setSymbols(res.data.futures);
        if (res.data.futures.length > 0) {
            // 默认选中第二个（烧碱），因为之前测试过
            const defaultSymbol = res.data.futures.find(s => s.code === 'SH0') || res.data.futures[0];
            form.setFieldsValue({ 
                symbol: defaultSymbol.code, 
                contract_multiplier: defaultSymbol.multiplier,
                date_range: [dayjs('2025-01-01'), dayjs('2026-01-01')]
            });
        }
      })
      .catch(err => {
          console.error(err);
          message.error('无法连接到后端服务');
      });

    // 获取策略代码
    fetchStrategyCode();
  }, []);

  const fetchStrategyCode = () => {
      axios.get('http://localhost:8000/api/strategy/code')
        .then(res => {
            setStrategyCode(res.data.code);
        })
        .catch(err => {
            message.error('获取策略代码失败');
        });
  };

  const saveStrategyCode = () => {
      setSavingCode(true);
      axios.post('http://localhost:8000/api/strategy/code', { code: strategyCode })
        .then(res => {
            message.success('策略代码保存成功');
        })
        .catch(err => {
            message.error('保存失败: ' + (err.response?.data?.detail || err.message));
        })
        .finally(() => {
            setSavingCode(false);
        });
  };

  const onSymbolChange = (value) => {
      const selected = symbols.find(s => s.code === value);
      if (selected) {
          form.setFieldsValue({ contract_multiplier: selected.multiplier });
      }
  };

  const onFinish = async (values) => {
    setLoading(true);
    setResults(null);
    try {
      // 转换数值类型
      let params = {};
      if (strategyType === 'TrendFollowingStrategy') {
          params = {
              fast_period: parseInt(values.fast_period),
              slow_period: parseInt(values.slow_period),
              atr_period: parseInt(values.atr_period),
              atr_multiplier: parseFloat(values.atr_multiplier),
              risk_per_trade: parseFloat(values.risk_per_trade),
              contract_multiplier: parseInt(values.contract_multiplier)
          };
      } else {
          // MA55BreakoutStrategy
          const sizeMode = values.size_mode || 'atr_risk';
          const fixedSize = values.fixed_size !== undefined ? parseInt(values.fixed_size) : 1;
          const riskPerTrade = values.risk_per_trade !== undefined ? parseFloat(values.risk_per_trade) : 0.02;

          console.log('Form Values:', values);
          console.log('Parsed Params:', { sizeMode, fixedSize, riskPerTrade });

          if (sizeMode === 'fixed') {
              message.info(`正在使用固定手数模式: ${fixedSize} 手`);
          } else {
              message.info(`正在使用ATR风险模式: ${(riskPerTrade * 100).toFixed(1)}%`);
          }

          params = {
              ma_period: parseInt(values.ma_period || 55),
              macd_fast: parseInt(values.macd_fast || 12),
              macd_slow: parseInt(values.macd_slow || 26),
              macd_signal: parseInt(values.macd_signal || 9),
              atr_period: parseInt(values.atr_period),
              atr_multiplier: parseFloat(values.atr_multiplier),
              size_mode: sizeMode,
              fixed_size: fixedSize,
              risk_per_trade: riskPerTrade,
              contract_multiplier: parseInt(values.contract_multiplier)
          };
      }

      const payload = {
        symbol: values.symbol,
        period: values.period,
        strategy_params: params,
        auto_optimize: autoOptimize,
        start_date: values.date_range ? values.date_range[0].format('YYYY-MM-DD') : null,
        end_date: values.date_range ? values.date_range[1].format('YYYY-MM-DD') : null,
        strategy_name: strategyType
      };
      
      const response = await axios.post('http://localhost:8000/api/backtest', payload);
      setResults(response.data);
      message.success('回测完成');
    } catch (error) {
      console.error(error);
      message.error('回测失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  // 图表配置
  const getOption = () => {
    if (!results) return {};

    if (chartType === 'pie') {
        // 盈亏分布饼图
        const won = results.metrics.won_trades || 0;
        const lost = results.metrics.lost_trades || 0;
        
        return {
            title: { text: '交易盈亏分布', left: 'center', top: 20 },
            tooltip: { trigger: 'item' },
            legend: { bottom: '5%', left: 'center' },
            series: [
                {
                    name: '交易次数',
                    type: 'pie',
                    radius: ['35%', '60%'],
                    center: ['50%', '50%'],
                    avoidLabelOverlap: true,
                    itemStyle: {
                        borderRadius: 10,
                        borderColor: '#fff',
                        borderWidth: 2
                    },
                    label: {
                        show: true,
                        position: 'outside',
                        formatter: '{b}: {c}次 ({d}%)'
                    },
                    emphasis: {
                        label: {
                            show: true,
                            fontSize: '14',
                            fontWeight: 'bold'
                        }
                    },
                    labelLine: { show: true },
                    data: [
                        { value: won, name: '盈利交易', itemStyle: { color: '#3f8600' } },
                        { value: lost, name: '亏损交易', itemStyle: { color: '#cf1322' } }
                    ]
                }
            ]
        };
    }

    if (chartType === 'kline') {
        const dates = results.kline_data?.dates || [];
        const data = results.kline_data?.values || [];
        const volumes = results.kline_data?.volumes || [];

        return {
            title: { text: 'K线图 & 交易信号' },
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'cross'
                }
            },
            legend: {
                data: ['K线', 'MA5', 'MA10', 'MA20', 'MA55']
            },
            grid: [
                {
                    left: '3%',
                    right: '4%',
                    height: '60%'
                },
                {
                    left: '3%',
                    right: '4%',
                    top: '75%',
                    height: '15%'
                }
            ],
            xAxis: [
                {
                    type: 'category',
                    data: dates,
                    scale: true,
                    boundaryGap: false,
                    axisLine: { onZero: false },
                    splitLine: { show: false },
                    min: 'dataMin',
                    max: 'dataMax'
                },
                {
                    type: 'category',
                    gridIndex: 1,
                    data: dates,
                    axisLabel: { show: false }
                }
            ],
            yAxis: [
                {
                    scale: true,
                    splitArea: {
                        show: true
                    }
                },
                {
                    scale: true,
                    gridIndex: 1,
                    splitNumber: 2,
                    axisLabel: { show: false },
                    axisLine: { show: false },
                    axisTick: { show: false },
                    splitLine: { show: false }
                }
            ],
            dataZoom: [
                {
                    type: 'inside',
                    xAxisIndex: [0, 1],
                    start: 50,
                    end: 100
                },
                {
                    show: true,
                    xAxisIndex: [0, 1],
                    type: 'slider',
                    top: '92%',
                    start: 50,
                    end: 100
                }
            ],
            series: [
                {
                    name: 'K线',
                    type: 'candlestick',
                    data: data,
                    itemStyle: {
                        color: '#ef232a',
                        color0: '#14b143',
                        borderColor: '#ef232a',
                        borderColor0: '#14b143'
                    },
                    markPoint: {
                        label: {
                            normal: {
                                formatter: function (param) {
                                    return param.name != null ? param.name : '';
                                }
                            }
                        },
                        data: results.trades ? results.trades.map(t => ({
                            name: t.type === 'buy' ? '买' : '卖',
                            coord: [t.date, t.price],
                            value: t.price,
                            itemStyle: {
                                color: t.type === 'buy' ? '#ef232a' : '#14b143'
                            }
                        })) : [],
                        tooltip: {
                            formatter: function (param) {
                                return param.name + '<br>' + (param.data.coord || '');
                            }
                        }
                    }
                },
                {
                    name: 'MA5',
                    type: 'line',
                    data: calculateMA(5, data),
                    smooth: true,
                    lineStyle: { opacity: 0.5 }
                },
                {
                    name: 'MA10',
                    type: 'line',
                    data: calculateMA(10, data),
                    smooth: true,
                    lineStyle: { opacity: 0.5 }
                },
                {
                    name: 'MA20',
                    type: 'line',
                    data: calculateMA(20, data),
                    smooth: true,
                    lineStyle: { opacity: 0.5 }
                },
                {
                    name: 'MA55',
                    type: 'line',
                    data: calculateMA(55, data),
                    smooth: true,
                    lineStyle: { opacity: 0.8, width: 2 }
                },
                {
                    name: 'Volume',
                    type: 'bar',
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    data: volumes
                }
            ]
        };
    }

    // 默认：权益曲线线形图
    return {
      title: { text: '账户权益曲线' },
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { 
        type: 'category', 
        data: results.equity_curve.map(item => item.date) 
      },
      yAxis: { 
        type: 'value', 
        scale: true 
      },
      series: [{
        name: '权益',
        data: results.equity_curve.map(item => item.value),
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.3 },
        itemStyle: { color: '#1890ff' }
      }]
    };
  };

  const getMetricsData = () => {
    if (!results) return [];
    const m = results.metrics;
    return [
      { key: '1', metric: '最终权益', value: m.final_value.toFixed(2) },
      { key: '2', metric: '净利润', value: m.net_profit.toFixed(2) },
      { key: '3', metric: '夏普比率', value: m.sharpe_ratio.toFixed(4) },
      { key: '4', metric: '最大回撤', value: `${m.max_drawdown.toFixed(2)}%` },
      { key: '5', metric: '总交易次数', value: m.total_trades },
      { key: '6', metric: '胜率', value: `${m.win_rate.toFixed(2)}%` },
    ];
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ color: 'white', fontSize: '20px', display: 'flex', alignItems: 'center' }}>
        AI量化策略回测平台
      </Header>
      <Content style={{ padding: '24px', backgroundColor: '#f0f2f5' }}>
        <Tabs defaultActiveKey="1" type="card">
            <TabPane tab="策略回测" key="1">
                <Row gutter={24}>
                  <Col span={6}>
                    <Card title="策略配置" bordered={false} style={{ height: '100%' }}>
                      <Form form={form} layout="vertical" onFinish={onFinish} initialValues={{
                        period: 'daily',
                        fast_period: 10,
                        slow_period: 20,
                        atr_period: 14,
                        atr_multiplier: 2.0,
                        risk_per_trade: 0.02,
                        contract_multiplier: 30
                      }}>
                        <Form.Item name="symbol" label="交易品种" rules={[{ required: true }]}>
                          <Select 
                            onChange={onSymbolChange}
                            showSearch
                            placeholder="选择或搜索品种"
                            optionFilterProp="children"
                            filterOption={(input, option) =>
                              option.children.toLowerCase().indexOf(input.toLowerCase()) >= 0
                            }
                          >
                            {symbols.map(s => (
                              <Option key={s.code} value={s.code}>{s.name}</Option>
                            ))}
                          </Select>
                        </Form.Item>

                        <Form.Item label="选择策略">
                            <Select value={strategyType} onChange={setStrategyType}>
                                <Option value="TrendFollowingStrategy">趋势跟踪策略 (双均线)</Option>
                                <Option value="MA55BreakoutStrategy">MA55突破 + MACD背离</Option>
                            </Select>
                        </Form.Item>
                        
                        <Form.Item label="回测周期" name="period" initialValue="daily">
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

                        {strategyType === 'TrendFollowingStrategy' ? (
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
                        ) : (
                            <>
                                <Form.Item name="ma_period" label="突破均线周期" initialValue={55}>
                                  <Input type="number" />
                                </Form.Item>
                                <Row gutter={16}>
                                    <Col span={8}>
                                        <Form.Item name="macd_fast" label="MACD快" initialValue={12}>
                                          <Input type="number" />
                                        </Form.Item>
                                    </Col>
                                    <Col span={8}>
                                        <Form.Item name="macd_slow" label="MACD慢" initialValue={26}>
                                          <Input type="number" />
                                        </Form.Item>
                                    </Col>
                                    <Col span={8}>
                                        <Form.Item name="macd_signal" label="MACD信" initialValue={9}>
                                          <Input type="number" />
                                        </Form.Item>
                                    </Col>
                                </Row>
                            </>
                        )}

                        <Form.Item name="atr_multiplier" label="ATR止损倍数">
                          <Input type="number" step="0.1" />
                        </Form.Item>

                        {strategyType === 'MA55BreakoutStrategy' ? (
                            <>
                                <Form.Item name="size_mode" label="开仓模式" initialValue="atr_risk">
                                    <Radio.Group>
                                        <Radio value="fixed">固定手数</Radio>
                                        <Radio value="atr_risk">ATR风险</Radio>
                                    </Radio.Group>
                                </Form.Item>
                                <Form.Item
                                    noStyle
                                    shouldUpdate={(prevValues, currentValues) => prevValues.size_mode !== currentValues.size_mode}
                                >
                                    {({ getFieldValue }) =>
                                        getFieldValue('size_mode') === 'fixed' ? (
                                            <Form.Item name="fixed_size" label="固定手数 (手)" initialValue={1}>
                                                <Input type="number" />
                                            </Form.Item>
                                        ) : (
                                            <Form.Item name="risk_per_trade" label="单笔风险系数 (0.02=2%)" initialValue={0.02}>
                                                <Input type="number" step="0.01" />
                                            </Form.Item>
                                        )
                                    }
                                </Form.Item>
                            </>
                        ) : (
                             <Form.Item name="risk_per_trade" label="单笔风险系数 (0.02=2%)">
                               <Input type="number" step="0.01" />
                             </Form.Item>
                        )}
                        
                        {/* 隐藏字段，自动设置 */}
                        <Form.Item name="contract_multiplier" label="合约乘数" hidden>
                            <Input type="number" />
                        </Form.Item>
                        <Form.Item name="atr_period" hidden><Input /></Form.Item>

                        <Button type="primary" htmlType="submit" loading={loading} block size="large">
                          开始回测
                        </Button>
                      </Form>
                    </Card>
                  </Col>
                  
                  <Col span={18}>
                    {results ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                        {results.optimization_info?.triggered && (
                            <Alert
                                message="策略已自动优化"
                                description={
                                    <div>
                                        <p>{results.optimization_info.message}</p>
                                        <div>
                                            <Tag color="orange">原始收益: {results.optimization_info.original_return.toFixed(2)}%</Tag>
                                            <Tag color="green">优化后收益: {results.optimization_info.optimized_return.toFixed(2)}%</Tag>
                                        </div>
                                    </div>
                                }
                                type="success"
                                showIcon
                            />
                        )}
                        
                        <Card title="回测概览" bordered={false}>
                            <Row gutter={[16, 16]}>
                                {getMetricsData().map(item => (
                                    <Col span={4} key={item.key}>
                                        <Statistic 
                                            title={item.metric} 
                                            value={item.value} 
                                            valueStyle={{ 
                                                color: item.metric === '净利润' 
                                                    ? (parseFloat(item.value) > 0 ? '#3f8600' : '#cf1322') 
                                                    : undefined 
                                            }}
                                        />
                                    </Col>
                                ))}
                            </Row>
                        </Card>
                        
                        <Card 
                            title={
                                chartType === 'line' ? "账户权益曲线" : 
                                chartType === 'kline' ? "K线图 & 交易信号" :
                                "盈亏分布分析"
                            } 
                            bordered={false}
                            extra={
                                <Radio.Group value={chartType} onChange={e => setChartType(e.target.value)}>
                                    <Radio.Button value="line">趋势图</Radio.Button>
                                    <Radio.Button value="kline">K线图</Radio.Button>
                                    <Radio.Button value="pie">饼状图</Radio.Button>
                                </Radio.Group>
                            }
                        >
                          <ReactECharts option={getOption()} style={{ height: 400 }} />
                        </Card>
                        
                        <Card title="交易日志" bordered={false}>
                            <div style={{ 
                                maxHeight: 300, 
                                overflowY: 'auto', 
                                fontFamily: 'monospace',
                                backgroundColor: '#f5f5f5',
                                padding: '12px',
                                borderRadius: '4px'
                            }}>
                                {results.logs.map((log, index) => (
                                    <div key={index} style={{ borderBottom: '1px solid #eee', padding: '2px 0' }}>{log}</div>
                                ))}
                            </div>
                        </Card>
                      </div>
                    ) : (
                      <Card style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <div style={{ textAlign: 'center', color: '#999' }}>
                          <h2>准备就绪</h2>
                          <p>请在左侧配置策略参数，点击“开始回测”查看结果</p>
                        </div>
                      </Card>
                    )}
                  </Col>
                </Row>
            </TabPane>
            
            <TabPane tab="策略代码编辑器" key="2">
                <Card 
                    title="编辑策略逻辑 (server/core/strategy.py)" 
                    extra={
                        <Button type="primary" onClick={saveStrategyCode} loading={savingCode}>
                            保存并生效
                        </Button>
                    }
                    style={{ height: 'calc(100vh - 120px)' }}
                    bodyStyle={{ height: 'calc(100% - 60px)', padding: 0 }}
                >
                    <Editor
                        height="100%"
                        defaultLanguage="python"
                        value={strategyCode}
                        onChange={(value) => setStrategyCode(value)}
                        theme="vs-dark"
                        options={{
                            minimap: { enabled: false },
                            fontSize: 14,
                            scrollBeyondLastLine: false,
                        }}
                    />
                </Card>
            </TabPane>
        </Tabs>
      </Content>
    </Layout>
  );
};

export default App;
