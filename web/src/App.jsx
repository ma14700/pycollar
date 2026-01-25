import React, { useState, useEffect } from 'react';
import { Layout, Card, Form, Input, Select, Button, Row, Col, Statistic, message, Radio, Tabs, Alert, Switch, Tag, DatePicker, Tooltip, Table, Space, Typography, Divider, Menu, Progress, Popconfirm, Descriptions } from 'antd';
import { 
  ReloadOutlined, 
  LineChartOutlined, 
  CodeOutlined, 
  FileTextOutlined, 
  DashboardOutlined,
  PlayCircleOutlined,
  RiseOutlined,
  FallOutlined,
  TransactionOutlined,
  AccountBookOutlined,
  SafetyCertificateOutlined,
  PercentageOutlined,
  WalletOutlined,
  ThunderboltOutlined,
  SaveOutlined,
  HistoryOutlined,
  ArrowLeftOutlined,
  DeleteOutlined
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import axios from 'axios';
import Editor from '@monaco-editor/react';
import dayjs from 'dayjs';

const { Header, Content, Sider } = Layout;
const { Option } = Select;
const { TabPane } = Tabs;

// Helper function for parsing log items
const parseLogItem = (log, index) => {
    const logStr = String(log || '');
    const firstComma = logStr.indexOf(',');
    const date = firstComma !== -1 ? logStr.substring(0, firstComma).trim() : '';
    const content = firstComma !== -1 ? logStr.substring(firstComma + 1).trim() : logStr;
    
    let type = 'info';
    if (content.includes('买入') || content.includes('开多') || content.includes('做多')) type = 'buy';
    else if (content.includes('卖出') || content.includes('开空') || content.includes('做空') || content.includes('平仓')) type = 'sell';
    else if (content.includes('交易利润')) type = 'profit';
    else if (content.includes('策略启动') || content.includes('回测结束')) type = 'system';
    else if (content.includes('金叉') || content.includes('死叉')) type = 'signal';

    let pnl = null;
    if (type === 'profit') {
        const match = content.match(/净利\s*([-\d.]+)/);
        if (match) pnl = parseFloat(match[1]);
    }

    return { key: index, date, content, type, pnl };
};

function calculateMA(dayCount, data) {
  if (!Array.isArray(data)) return [];
  var result = [];
  var sum = 0;
  for (var i = 0, len = data.length; i < len; i++) {
    if (!data[i] || data[i].length < 2) {
        result.push('-');
        continue;
    }
    sum += data[i][1];
    if (i >= dayCount) {
      if (data[i - dayCount] && data[i - dayCount].length >= 2) {
          sum -= data[i - dayCount][1];
      }
      result.push((sum / dayCount).toFixed(2));
    } else {
      result.push((sum / (i + 1)).toFixed(2));
    }
  }
  return result;
}

const ContractInfo = ({ form, quoteInfo }) => {
    const initialCash = Form.useWatch('initial_cash', form);
    const contractMultiplier = Form.useWatch('contract_multiplier', form);
    const marginRate = Form.useWatch('margin_rate', form);
    
    if (!quoteInfo) return null;

    const currentMultiplier = contractMultiplier || 1;
    const currentInitialCash = parseFloat(initialCash || 0);
    const currentMarginRate = parseFloat(marginRate || 0.12);
    
    // Auto-calculate entry price: Market Price * (1 + Margin Rate)
    const basePrice = quoteInfo.price ? parseFloat(quoteInfo.price) : 0;
    const calcPrice = basePrice * (1 + currentMarginRate);
    
    const oneHandValue = calcPrice * currentMultiplier;
    // Note: Margin calculation typically uses the entry price. 
    // If calcPrice is the simulated entry price, we use it for margin requirement estimation.
    const maxHands = oneHandValue > 0 ? Math.floor(currentInitialCash / (oneHandValue * currentMarginRate)) : 0;
    
    return (
        <div style={{ background: '#fafafa', padding: '12px', borderRadius: '6px', marginBottom: '24px', border: '1px solid #f0f0f0' }}>
            <div style={{ fontSize: '12px', color: '#888', marginBottom: '8px' }}>合约详情参考 ({quoteInfo.date})</div>
            <Row gutter={[8, 8]}>
                <Col span={12}>
                    <div style={{ fontSize: '12px', color: '#666' }}>开仓价格 (参考)</div>
                    <Tooltip title={`计算公式: 当前价格 × (1 + 保证金率 ${currentMarginRate})`}>
                        <Input 
                            size="small" 
                            value={calcPrice.toFixed(2)} 
                            disabled
                            style={{ width: '100px', fontWeight: 'bold', color: '#595959', cursor: 'not-allowed', backgroundColor: '#f5f5f5' }} 
                        />
                    </Tooltip>
                </Col>
                <Col span={12}>
                    <div style={{ fontSize: '12px', color: '#666' }}>1点价值</div>
                    <div>{currentMultiplier} 元</div>
                </Col>
                <Col span={12}>
                    <div style={{ fontSize: '12px', color: '#666' }}>一手合约价值</div>
                    <div>{(oneHandValue / 10000).toFixed(2)} 万</div>
                </Col>
                <Col span={12}>
                    <div style={{ fontSize: '12px', color: '#666' }}>最大可开({(currentMarginRate * 100).toFixed(0)}%保证金)</div>
                    <div style={{ color: '#1890ff', fontWeight: 'bold' }}>{maxHands} 手</div>
                </Col>
            </Row>
        </div>
    );
};

// 策略名称映射
const strategyNameMap = {
  'MA55BreakoutStrategy': 'MA55突破+背离离场',
  'MA55TouchExitStrategy': 'MA55突破+触碰平仓',
  'MA20MA55CrossoverStrategy': '20/55双均线交叉(多空)',
  'StockMA20MA55LongOnlyStrategy': '20/55双均线多头(股票)',
  'MA20MA55PartialTakeProfitStrategy': '20/55双均线+盈利平半仓',
  'DKXStrategy': 'DKX多空线策略',
  'DKXPartialTakeProfitStrategy': 'DKX多空线+盈利平半仓',
  'TrendFollowingStrategy': '双均线趋势跟踪'
};

const symbolMap = {
  'BTC/USDT': '比特币',
  'ETH/USDT': '以太坊',
  'BNB/USDT': '币安币',
  'SOL/USDT': '索拉纳',
  'XRP/USDT': '瑞波币',
  'DOGE/USDT': '狗狗币',
  'ADA/USDT': '艾达币',
  'AVAX/USDT': '雪崩协议',
  'SHIB/USDT': '柴犬币',
  'DOT/USDT': '波卡',
  'TRX/USDT': '波场',
  'MATIC/USDT': '马蹄币',
  'LTC/USDT': '莱特币',
  'LINK/USDT': '预言机',
  'UNI/USDT': '独角兽',
  'BCH/USDT': '比特币现金',
  'ATOM/USDT': '阿童木',
  'XLM/USDT': '恒星币',
  'ETC/USDT': '以太经典',
  'FIL/USDT': '文件币',
  'APT/USDT': '阿普托斯',
  'NEAR/USDT': 'NEAR协议',
  'LDO/USDT': 'LDO',
  'QNT/USDT': 'QNT',
  'VET/USDT': '唯链',
  'ICP/USDT': '互联网计算机',
  'ARB/USDT': 'Arbitrum',
  'OP/USDT': 'Optimism',
  'GRT/USDT': 'Graph',
  'ALGO/USDT': 'Algorand',
  'STX/USDT': 'Stacks',
  'EOS/USDT': '柚子币',
  'XTZ/USDT': 'Tezos',
  'IMX/USDT': 'Immutable',
  'SAND/USDT': '沙盒',
  'MANA/USDT': 'Decentraland',
  'THETA/USDT': 'Theta',
  'AAVE/USDT': 'Aave',
  'AXS/USDT': 'Axie'
};

const futuresMap = {
  "CU": "铜", "AL": "铝", "ZN": "锌", "PB": "铅", "NI": "镍", "SN": "锡", 
  "AU": "黄金", "AG": "白银", "RB": "螺纹钢", "WR": "线材", "HC": "热轧卷板", 
  "FU": "燃油", "BU": "沥青", "RU": "天然橡胶", "SP": "纸浆", "SS": "不锈钢", 
  "AO": "氧化铝", "BR": "丁二烯橡胶",
  "M": "豆粕", "Y": "豆油", "A": "豆一", "B": "豆二", "P": "棕榈油", 
  "C": "玉米", "CS": "玉米淀粉", "JD": "鸡蛋", "BB": "胶合板", "FB": "纤维板", 
  "L": "塑料", "V": "PVC", "PP": "聚丙烯", "J": "焦炭", "JM": "焦煤", 
  "I": "铁矿石", "EG": "乙二醇", "RR": "粳米", "EB": "苯乙烯", "PG": "液化石油气", 
  "LH": "生猪",
  "SR": "白糖", "CF": "棉花", "CY": "棉纱", "PM": "普麦", "WH": "强麦", 
  "RI": "早缼稻", "LR": "晚缼稻", "JR": "粳稻", "RS": "油菜籽", "OI": "菜籽油", 
  "RM": "菜籽粕", "SF": "硅铁", "SM": "锰硅", "TA": "PTA", "MA": "甲醇", 
  "FG": "玻璃", "SA": "纯碱", "UR": "尿素", "AP": "苹果", "CJ": "红枣", 
  "PK": "花生", "PF": "短纤", "SH": "烧碱", "PX": "对二甲苯",
  "IF": "沪深300", "IC": "中证500", "IH": "上证50", "IM": "中证1000", 
  "T": "10年期国债", "TF": "5年期国债", "TS": "2年期国债", "TL": "30年期国债",
  "SC": "原油", "NR": "20号胶", "LU": "低硫燃料油", "BC": "国际铜", "EC": "欧线集运"
};

const getSymbolName = (symbol) => {
  if (!symbol) return '';
  if (symbolMap[symbol]) return symbolMap[symbol];
  
  // 匹配期货代码 (大写字母开头)
  const match = symbol.match(/^([A-Z]+)/);
  if (match) {
      const code = match[1];
      if (futuresMap[code]) return futuresMap[code];
  }
  
  return symbol;
};

const periodMap = {
  'daily': '日线',
  '60': '60分钟',
  '30': '30分钟',
  '15': '15分钟',
  '5': '5分钟'
};

const App = () => {


  const [loading, setLoading] = useState(false);
  const [symbols, setSymbols] = useState([]);
  const [results, setResults] = useState(null);
  const [chartType, setChartType] = useState('line'); // 'line' or 'pie'
  const [form] = Form.useForm();
  const [strategyCode, setStrategyCode] = useState('');
  const [savingCode, setSavingCode] = useState(false);
  const [savedBacktests, setSavedBacktests] = useState([]);
  const [viewingHistory, setViewingHistory] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [currentParams, setCurrentParams] = useState(null);
  const [autoOptimize, setAutoOptimize] = useState(false);

  const [strategyType, setStrategyType] = useState('MA55BreakoutStrategy');
  const [quoteInfo, setQuoteInfo] = useState(null);
  const [selectedMddInfo, setSelectedMddInfo] = useState(null);
  const [activeTab, setActiveTab] = useState('1');
  const [filteredLogs, setFilteredLogs] = useState(null);
  
  // 缓存全量数据
  const [futuresList, setFuturesList] = useState([]);
  const [stockList, setStockList] = useState([]);

  // 统一处理列表切换逻辑
  const switchSymbols = (marketType, fList = futuresList, sList = stockList) => {
      const list = marketType === 'stock' ? sList : fList;
      setSymbols(list || []);
      
      // 如果列表不为空，默认选中第一个
      if (list && list.length > 0) {
          // 如果是期货，尝试找 SH0，否则取第一个
          let defaultSymbol = list[0];
          if (marketType === 'futures') {
              defaultSymbol = list.find(s => s.code === 'SH0') || list[0];
          }
          
          form.setFieldsValue({ 
              symbol: defaultSymbol.code, 
              contract_multiplier: defaultSymbol.multiplier
          });
          fetchQuote(defaultSymbol.code);
      } else {
          form.setFieldsValue({ symbol: undefined });
          setQuoteInfo(null);
      }
  };

  const fetchQuote = (symbol) => {
      if (!symbol) return;
      const marketType = form.getFieldValue('market_type') || 'futures';
      const dataSource = form.getFieldValue('data_source') || 'main';
      axios.get(`http://localhost:8000/api/quote/latest?symbol=${symbol}&market_type=${marketType}&data_source=${dataSource}`)
        .then(res => {
            setQuoteInfo(res.data);
        })
        .catch(err => {
            console.error("Failed to fetch quote", err);
            setQuoteInfo(null);
        });
  };

  useEffect(() => {
    // 初始加载：并发获取期货和股票列表
    Promise.all([
        axios.get('http://localhost:8000/api/symbols?market_type=futures'),
        axios.get('http://localhost:8000/api/symbols?market_type=stock')
    ]).then(([futuresRes, stockRes]) => {
        const fList = futuresRes.data.futures || [];
        const sList = stockRes.data.stocks || [];
        
        setFuturesList(fList);
        setStockList(sList);
        
        // 默认显示期货列表并选中
        switchSymbols('futures', fList, sList);
    }).catch(err => {
        console.error(err);
        message.error('无法连接到后端服务获取品种数据');
    });
    
    // 初始化表单默认值
    form.setFieldsValue({
        market_type: 'futures',
        period: 'daily',
        initial_cash: 1000000
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
      fetchQuote(value);
  };

  const onChartClick = (params) => {
      console.log('Chart click params:', params);
      if (!params) return;
      
      if (params.componentType === 'markPoint' && params.name === '最大回撤') {
          setSelectedMddInfo(params.data);
      }
  };

  const fetchSavedBacktests = async () => {
    setHistoryLoading(true);
    try {
      const response = await axios.get('http://localhost:8000/api/backtest/list');
      setSavedBacktests(response.data);
    } catch (error) {
      message.error('获取回测记录失败: ' + error.message);
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleSaveBacktest = async () => {
    if (!results) return;
    
    // 辅助函数：安全转换数值，无效值返回 null
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
      fetchSavedBacktests();
    } catch (error) {
      message.error('保存失败: ' + error.message);
    }
  };

  const handleViewHistory = async (id) => {
    setHistoryLoading(true);
    try {
      const response = await axios.get(`http://localhost:8000/api/backtest/${id}`);
      setViewingHistory(response.data);
    } catch (error) {
      message.error('获取详情失败: ' + error.message);
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleDeleteBacktest = async (id) => {
    try {
      await axios.delete(`http://localhost:8000/api/backtest/${id}`);
      message.success('删除成功');
      fetchSavedBacktests();
    } catch (error) {
      message.error('删除失败: ' + error.message);
    }
  };

  const parsedLogs = React.useMemo(() => {
    if (!results || !results.logs) return [];
    return results.logs.map((log, index) => parseLogItem(log, index));
  }, [results]);

  const downloadLogs = () => {
    if (!viewingHistory || !viewingHistory.detail_data || !viewingHistory.detail_data.logs) {
      message.warning('暂无日志可下载');
      return;
    }
    
    // Parse logs using shared helper
    const logsToExport = viewingHistory.detail_data.logs.map((log, index) => parseLogItem(log, index));
    
    // Generate CSV content
    const header = "时间,类型,内容,净利\n";
    const rows = logsToExport.map(item => {
        const typeMap = {
            'buy': '买入',
            'sell': '卖出',
            'profit': '结算',
            'signal': '信号',
            'system': '系统',
            'info': '信息'
        };
        const typeStr = typeMap[item.type] || '信息';
        
        return `${item.date},${typeStr},"${item.content.replace(/"/g, '""')}",${item.pnl !== null ? item.pnl : ''}`;
    }).join('\n');
    
    const blobWithBOM = new Blob(['\uFEFF' + header + rows], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blobWithBOM);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${getSymbolName(viewingHistory.symbol)}_${viewingHistory.strategy_name}_${viewingHistory.timestamp}_logs.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const downloadCurrentLogs = () => {
    // Determine data source (filtered or full)
    const dataToExport = (filteredLogs && filteredLogs.length > 0) ? filteredLogs : parsedLogs;
    
    if (!dataToExport || dataToExport.length === 0) {
      message.warning('暂无日志可下载');
      return;
    }
    
    // Generate CSV content
    const header = "时间,类型,内容,净利\n";
    const rows = dataToExport.map(item => {
        const typeMap = {
            'buy': '买入',
            'sell': '卖出',
            'profit': '结算',
            'signal': '信号',
            'system': '系统',
            'info': '信息'
        };
        const typeStr = typeMap[item.type] || '信息';
        
        return `${item.date},${typeStr},"${item.content.replace(/"/g, '""')}",${item.pnl !== null ? item.pnl : ''}`;
    }).join('\n');
    
    const blobWithBOM = new Blob(['\uFEFF' + header + rows], { type: 'text/csv;charset=utf-8;' });
    
    const url = URL.createObjectURL(blobWithBOM);
    const link = document.createElement('a');
    link.href = url;
    
    const timestamp = dayjs().format('YYYYMMDD_HHmmss');
    const strategy = strategyType || 'UnknownStrategy';
    const symbol = form.getFieldValue('symbol') || 'UnknownSymbol';
    link.download = `${strategy}_${getSymbolName(symbol)}_${timestamp}_logs.csv`;
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const onFinish = async (values) => {
    setLoading(true);
    setResults(null);
    setFilteredLogs(null);
    try {
      // 转换数值类型
      let params = {};
      
      // 通用风险参数处理 (适用于支持 size_mode 的策略)
      const getSizeParams = () => {
          const sizeMode = values.size_mode || 'fixed';
          const fixedSize = values.fixed_size !== undefined ? parseInt(values.fixed_size) : 20;
          const riskPerTrade = values.risk_per_trade !== undefined ? parseFloat(values.risk_per_trade) : 0.02;
          
          if (sizeMode === 'fixed') {
              message.info(`正在使用固定手数模式: ${fixedSize} 手`);
          } else {
              message.info(`正在使用ATR风险模式: ${(riskPerTrade * 100).toFixed(1)}%`);
          }
          
          return {
              size_mode: sizeMode,
              fixed_size: fixedSize,
              risk_per_trade: riskPerTrade
          };
      };

      const riskPerTrade = values.risk_per_trade !== undefined ? parseFloat(values.risk_per_trade) : 0.02;
      const equityPercent = values.equity_percent !== undefined ? parseFloat(values.equity_percent) : 0.1;

      const contractMultiplier = values.contract_multiplier ? parseInt(values.contract_multiplier) : 1;

      const marginRate = values.margin_rate !== undefined ? parseFloat(values.margin_rate) : 0.1;

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
            fast_period: 20,
            slow_period: 55,
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
      }

      const payload = {
        symbol: values.symbol,
        period: values.period,
        market_type: values.market_type || 'futures',
        data_source: values.data_source || 'main',
        strategy_params: params,
        initial_cash: parseFloat(values.initial_cash || 1000000),
        auto_optimize: autoOptimize,
        strategy_name: strategyType
      };

      setCurrentParams(params);

      if (values.date_range && values.date_range.length === 2) {
        payload.start_date = values.date_range[0].format('YYYY-MM-DD');
        payload.end_date = values.date_range[1].format('YYYY-MM-DD');
      }
      
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
  const getOption = (data = results, currentStrategyType = strategyType) => {
    if (!data) return {};

    if (chartType === 'pie') {
        // 盈亏分布饼图
        const won = data.metrics.won_trades || 0;
        const lost = data.metrics.lost_trades || 0;
        
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
        const dates = data.kline_data?.dates || [];
        const rawData = data.kline_data?.values || [];
        const volumes = data.kline_data?.volumes || [];
        const macdData = data.kline_data?.macd || { dif: [], dea: [], hist: [] };
        const dkxData = data.kline_data?.dkx || { dkx: [], madkx: [] };
        const maData = data.kline_data?.ma || {};
        const ma5Series = (maData.ma5 && maData.ma5.length === rawData.length) ? maData.ma5 : calculateMA(5, rawData);
        const ma10Series = (maData.ma10 && maData.ma10.length === rawData.length) ? maData.ma10 : calculateMA(10, rawData);
        const ma20Series = (maData.ma20 && maData.ma20.length === rawData.length) ? maData.ma20 : calculateMA(20, rawData);
        const ma55Series = (maData.ma55 && maData.ma55.length === rawData.length) ? maData.ma55 : calculateMA(55, rawData);
        const showDKX = currentStrategyType === 'DKXStrategy' || currentStrategyType === 'DKXPartialTakeProfitStrategy';

        const equityCurve = data.equity_curve || [];
        let equitySeries = [];
        if (equityCurve.length > 0) {
            const equityMap = {};
            equityCurve.forEach(item => {
                const fullKey = item.date;
                const shortKey = typeof item.date === 'string' ? item.date.slice(0, 10) : item.date;
                equityMap[fullKey] = item.value;
                if (!Object.prototype.hasOwnProperty.call(equityMap, shortKey)) {
                    equityMap[shortKey] = item.value;
                }
            });
            let lastValue = equityCurve[0].value;
            equitySeries = dates.map(d => {
                const fullKey = d;
                const shortKey = typeof d === 'string' ? d.slice(0, 10) : d;
                if (Object.prototype.hasOwnProperty.call(equityMap, fullKey)) {
                    lastValue = equityMap[fullKey];
                } else if (Object.prototype.hasOwnProperty.call(equityMap, shortKey)) {
                    lastValue = equityMap[shortKey];
                }
                return lastValue;
            });
        }

        const legendData = ['K线', 'MA5', 'MA10', 'MA20', 'MA55', 'DIF', 'DEA', 'MACD'];
        if (showDKX && dkxData.dkx.length > 0) {
            legendData.push('DKX', 'MADKX');
        }
        if (equitySeries.length > 0) {
            legendData.push('资金曲线');
        }

        const seriesList = [
            {
                name: 'K线',
                type: 'candlestick',
                data: rawData,
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
                                const data = param.data;
                                let displaySize = Math.abs(data.tradeSize);
                                // 如果是反手操作，显示持仓量而不是交易量（避免用户混淆 20 vs 40）
                                if (data.name && data.name.includes('反手') && data.position) {
                                    displaySize = Math.abs(data.position);
                                }
                                return (param.name || '') + '\n' + displaySize + '手';
                            },
                            fontSize: 11,
                            fontWeight: 'bold'
                        }
                    },
                    data: Array.isArray(data.trades) ? (() => {
                        const tradeMarkers = data.trades.map(t => {
                            // 根据 action 决定颜色和图标方向
                            const action = t.action || '';
                            let color = '#5470c6'; // 默认卖出颜色 (平多/卖空)
                            let symbolRotate = 180;
                            
                            // 修正判断逻辑：包含“买”或者是“反手做多” -> 红色
                            if (action.includes('买') || action === '平空' || action === '反手做多') {
                                color = '#ef232a';
                                symbolRotate = 0;
                            }
                            
                            // 反手做空 -> 绿色
                            if (action === '反手做空') {
                                color = '#5470c6';
                                symbolRotate = 180;
                            }

                            return {
                                name: action || (t.type === 'buy' ? '买入' : '卖出'),
                                coord: [t.date, t.price],
                                value: t.price,
                                tradeSize: t.size,
                                position: t.position,
                                symbol: 'arrow',
                                symbolSize: 12,
                                symbolRotate: symbolRotate,
                                symbolOffset: [0, (action.includes('买') || action === '平空' || action === '反手做多') ? 10 : -10],
                                itemStyle: {
                                    color: color
                                },
                                tooltip: {
                                    formatter: function (param) {
                                        let sizeDisplay = t.size;
                                        if (action.includes('反手') && t.position) {
                                            sizeDisplay = `${t.size} (目标持仓: ${t.position})`;
                                        }
                                        return (action || (t.type === 'buy' ? '买入' : '卖出')) + 
                                               '<br>时间: ' + t.date +
                                               '<br>价格: ' + t.price + 
                                               '<br>数量: ' + sizeDisplay;
                                    }
                                }
                            };
                        });

                        const mddMarkers = [];
                        data.trades.forEach(t => {
                            if (t.mdd_price !== null && t.mdd_price !== undefined && t.mdd_date) {
                                mddMarkers.push({
                                    name: '最大回撤',
                                    coord: [t.mdd_date, t.mdd_price],
                                    value: t.mdd_price,
                                    symbol: 'pin',
                                    symbolSize: 20,
                                    itemStyle: {
                                        color: '#faad14'
                                    },
                                    // 显式传递数据到 data item 中，避免闭包问题
                                    entry_price: t.entry_price,
                                    mdd_price: t.mdd_price,
                                    holding_direction: t.holding_direction,
                                    mdd_date: t.mdd_date,
                                    tooltip: {
                                        formatter: function (param) {
                                            const data = param.data;
                                            
                                            const parseVal = (val) => {
                                                if (val === null || val === undefined || val === '') return null;
                                                const num = parseFloat(val);
                                                return isNaN(num) ? null : num;
                                            };

                                            const entryVal = parseVal(data.entry_price);
                                            const mddVal = parseVal(data.mdd_price);
                                            
                                            const entryPriceStr = entryVal !== null ? entryVal.toFixed(2) : 'N/A';
                                            const mddPriceStr = mddVal !== null ? mddVal.toFixed(2) : 'N/A';
                                            
                                            let lossPoints = 'N/A';
                                            if (entryVal !== null && mddVal !== null) {
                                                lossPoints = Math.abs(mddVal - entryVal).toFixed(2);
                                            }
                                            
                                            const direction = data.holding_direction || '未知';
                                            
                                            return '最大回撤点<br>' +
                                                   '方向: ' + direction + '<br>' +
                                                   '开仓均价: ' + entryPriceStr + '<br>' +
                                                   '回撤价格: ' + mddPriceStr + '<br>' +
                                                   '亏损点数: ' + lossPoints + '<br>' +
                                                   '日期: ' + (data.mdd_date || 'N/A');
                                        }
                                    },
                                    label: {
                                        show: false
                                    }
                                });
                            }
                        });

                        return tradeMarkers.concat(mddMarkers);
                    })() : []
                }
            },
            {
                name: 'MA5',
                type: 'line',
                data: ma5Series,
                smooth: true,
                showSymbol: false,
                lineStyle: { opacity: 0.5, width: 1 }
            },
            {
                name: 'MA10',
                type: 'line',
                data: ma10Series,
                smooth: true,
                showSymbol: false,
                lineStyle: { opacity: 0.5, width: 1 }
            },
            {
                name: 'MA20',
                type: 'line',
                data: ma20Series,
                smooth: true,
                showSymbol: false,
                lineStyle: { opacity: 0.8, width: 2, color: 'red' }
            },
            {
                name: 'MA55',
                type: 'line',
                data: ma55Series,
                smooth: true,
                showSymbol: false,
                lineStyle: { opacity: 0.8, width: 2, color: '#999' }
            },
            {
                name: '成交量',
                type: 'bar',
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: volumes
            },
            {
                name: 'DIF',
                type: 'line',
                xAxisIndex: 2,
                yAxisIndex: 2,
                data: macdData.dif,
                showSymbol: false,
                lineStyle: { width: 1, color: '#1890ff' }
            },
            {
                name: 'DEA',
                type: 'line',
                xAxisIndex: 2,
                yAxisIndex: 2,
                data: macdData.dea,
                showSymbol: false,
                lineStyle: { width: 1, color: '#faad14' }
            },
            {
                name: 'MACD',
                type: 'bar',
                xAxisIndex: 2,
                yAxisIndex: 2,
                data: macdData.hist,
                itemStyle: {
                    color: function(params) {
                        return params.value > 0 ? '#ef232a' : '#14b143';
                    }
                }
            }
        ];

        if (showDKX && dkxData.dkx.length > 0) {
            seriesList.push({
                name: 'DKX',
                type: 'line',
                data: dkxData.dkx,
                smooth: true,
                showSymbol: false,
                lineStyle: { width: 2, color: '#722ed1', type: 'solid' },
                z: 5
            });
            seriesList.push({
                name: 'MADKX',
                type: 'line',
                data: dkxData.madkx,
                smooth: true,
                showSymbol: false,
                lineStyle: { width: 2, color: '#fa8c16', type: 'dashed' },
                z: 5
            });
        }

        if (equitySeries.length > 0) {
            seriesList.push({
                name: '资金曲线',
                type: 'line',
                xAxisIndex: 3,
                yAxisIndex: 3,
                data: equitySeries,
                smooth: true,
                showSymbol: false,
                lineStyle: { width: 1.5, color: '#1890ff' },
                areaStyle: { opacity: 0.15 }
            });
        }

        return {
            title: { text: 'K线图 & 交易信号' },
            legend: {
                data: legendData,
                selected: {
                    'MA5': false,
                    'MA10': false,
                    'MA20': true,
                    'MA55': true,
                    'DKX': true,
                    'MADKX': true
                }
            },
            grid: [
                {
                    left: '5%',
                    right: '5%',
                    top: '5%',
                    height: '40%'
                },
                {
                    left: '5%',
                    right: '5%',
                    top: '50%',
                    height: '10%'
                },
                {
                    left: '5%',
                    right: '5%',
                    top: '65%',
                    height: '10%'
                },
                {
                    left: '5%',
                    right: '5%',
                    top: '80%',
                    height: '10%'
                }
            ],
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'cross'
                },
                formatter: function (params) {
                    if (!params || !params.length) return '';
                    const date = params[0].axisValue;
                    let result = date + '<br/>';
                    
                    params.forEach(param => {
                        const seriesName = param.seriesName;
                        const marker = param.marker;
                        const value = param.value;
                        
                        if (param.seriesType === 'candlestick') {
                            if (Array.isArray(value) && value.length > 4) {
                                const open = value[1];
                                const close = value[2];
                                const low = value[3];
                                const high = value[4];
                                
                                result += `${marker} ${seriesName}<br/>
                                           开盘: ${open}<br/>
                                           收盘: ${close}<br/>
                                           最低: ${low}<br/>
                                           最高: ${high}<br/>`;
                            }
                        } else {
                             let val = value;
                             if (Array.isArray(value) && value.length > 1) val = value[1];
                             if (val === undefined || val === null) val = param.data;
                             
                             if (typeof val === 'number') {
                                 val = val.toFixed(2);
                             } else if (val === null || val === undefined) {
                                 val = '-';
                             }
                             
                             result += `${marker} ${seriesName}: ${val}<br/>`;
                        }
                    });
                    return result;
                }
            },
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
                },
                {
                    type: 'category',
                    gridIndex: 2,
                    data: dates,
                    axisLabel: { show: false }
                },
                {
                    type: 'category',
                    gridIndex: 3,
                    data: dates,
                    axisLabel: { show: false }
                }
            ],
            yAxis: [
                {
                    scale: true,
                    splitArea: { show: true }
                },
                {
                    scale: true,
                    gridIndex: 1,
                    splitNumber: 2,
                    axisLabel: { show: false },
                    axisLine: { show: false },
                    axisTick: { show: false },
                    splitLine: { show: false }
                },
                {
                    scale: true,
                    gridIndex: 2,
                    splitNumber: 2,
                    axisLabel: { show: false },
                    axisLine: { show: false },
                    axisTick: { show: false },
                    splitLine: { show: false }
                },
                {
                    scale: true,
                    gridIndex: 3,
                    splitNumber: 2,
                    axisLabel: { show: true },
                    axisLine: { show: false },
                    axisTick: { show: false },
                    splitLine: { show: false }
                }
            ],
            dataZoom: [
                {
                    type: 'inside',
                    xAxisIndex: [0, 1, 2, 3],
                    start: 50,
                    end: 100
                },
                {
                    show: true,
                    xAxisIndex: [0, 1, 2, 3],
                    type: 'slider',
                    top: '94%',
                    start: 50,
                    end: 100
                }
            ],
            series: seriesList
        };
    }

    // 默认：权益曲线线形图
    const equityCurve = Array.isArray(data.equity_curve) ? data.equity_curve : [];
    return {
      title: { text: '账户权益曲线' },
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { 
        type: 'category', 
        data: equityCurve.map(item => item ? item.date : '') 
      },
      yAxis: { 
        type: 'value', 
        scale: true 
      },
      series: [{
        name: '权益',
        data: equityCurve.map(item => item ? item.value : 0),
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.3 },
        itemStyle: { color: '#1890ff' }
      }]
    };
  };

  const getValueColor = (val, isPercentage = false) => {
    if (val === null || val === undefined || val === '') return 'inherit';
    
    // 移除百分号等非数字字符进行判断
    let numVal = val;
    if (typeof val === 'string') {
        numVal = parseFloat(val.replace(/%/g, ''));
    }
    
    if (isNaN(numVal)) return 'inherit';
    
    // 大于0红色，小于0绿色，等于0默认
    if (numVal > 0) return '#cf1322'; // Red
    if (numVal < 0) return '#3f8600'; // Green
    return 'inherit';
  };

  const getMetricsData = (data = results) => {
    if (!data || !data.metrics) return [];
    const m = data.metrics;
    const fmt = (val) => val ? parseFloat(val).toFixed(2) : '0.00';
    const fmtPct = (val) => val ? `${parseFloat(val).toFixed(2)}%` : '0.00%';

    return [
      { key: '1', metric: '最终权益', value: fmt(m.final_value), icon: <WalletOutlined />, color: '#722ed1', bg: '#f9f0ff' },
      { key: '2', metric: '净利润', value: fmt(m.net_profit), icon: <AccountBookOutlined />, color: m.net_profit > 0 ? '#cf1322' : '#3f8600', bg: '#fff1f0', isPnl: true },
      { key: '3', metric: '夏普比率', value: (m.sharpe_ratio || 0).toFixed(4), icon: <SafetyCertificateOutlined />, color: '#faad14', bg: '#fffbe6' },
      { key: '4', metric: '最大回撤', value: fmtPct(m.max_drawdown), icon: <FallOutlined />, color: '#52c41a', bg: '#f6ffed' },
      { key: '5', metric: '总交易次数', value: m.total_trades || 0, icon: <CodeOutlined />, color: '#1890ff', bg: '#e6f7ff' },
      { key: '6', metric: '胜率', value: fmtPct(m.win_rate), icon: <RiseOutlined />, color: '#cf1322', bg: '#fff1f0' },
      { key: '7', metric: '使用手数', value: m.used_size, icon: <FileTextOutlined />, color: '#595959', bg: '#fafafa' },
      { key: '8', metric: '最大资金使用率', value: fmtPct(m.max_capital_usage), icon: <ThunderboltOutlined />, color: '#fa8c16', bg: '#fff7e6' },
      { key: '9', metric: '一手最终赚钱数', value: fmt(m.one_hand_net_profit), icon: <TransactionOutlined />, color: '#13c2c2', bg: '#e6fffb', isPnl: true },
      { key: '10', metric: '最大盈利点', value: fmt(m.max_profit_points), icon: <RiseOutlined />, color: '#f5222d', bg: '#fff1f0' },
      { key: '11', metric: '最大亏损点', value: fmt(m.max_loss_points), icon: <FallOutlined />, color: '#2f54eb', bg: '#f0f5ff' },
      { key: '12', metric: '一手盈利百分数', value: fmtPct(m.one_hand_profit_pct), icon: <PercentageOutlined />, color: '#eb2f96', bg: '#fff0f6', isPnl: true },
    ];
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ 
        background: 'linear-gradient(90deg, #001529 0%, #003a8c 100%)', 
        padding: '0 24px', 
        color: 'white', 
        display: 'flex', 
        alignItems: 'center', 
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        zIndex: 10,
        height: '64px'
      }}>
        <DashboardOutlined style={{ fontSize: '24px', marginRight: '12px', color: '#1890ff' }} />
        <div style={{ fontSize: '20px', fontWeight: 'bold', letterSpacing: '1px' }}>
          AI 量化策略回测平台
        </div>
      </Header>
      <Content style={{ padding: '0', backgroundColor: '#f0f2f5', overflow: 'hidden' }}>
        <Layout style={{ height: 'calc(100vh - 64px)', background: '#f0f2f5' }}>
            <Sider width={220} style={{ background: '#001529', height: '100%', overflowY: 'auto' }}>
                <Menu
                    mode="inline"
                    defaultSelectedKeys={['1']}
                    style={{ height: '100%', borderRight: 0 }}
                    theme="dark"
                    onSelect={({ key }) => {
                        setActiveTab(key);
                        if (key === '4') {
                            fetchSavedBacktests();
                        }
                    }}
                    items={[
                        { key: '1', icon: <LineChartOutlined />, label: '策略回测' },
                        { key: '2', icon: <CodeOutlined />, label: '代码编辑' },
                        { key: '3', icon: <FileTextOutlined />, label: '交易日志' },
                        { key: '4', icon: <HistoryOutlined />, label: '回测记录' }
                    ]}
                />
            </Sider>
            <Content style={{ height: '100%', overflowY: 'auto', backgroundColor: '#f0f2f5' }}>
                <div style={{ display: activeTab === '1' ? 'block' : 'none', height: '100%' }}>
                    <div style={{ padding: '24px', minHeight: '100%' }}>
                        <Row gutter={24} style={{ height: '100%' }}>
                          <Col span={6}>
                            <Card title={<span><SafetyCertificateOutlined /> 策略配置</span>} variant="borderless" style={{ height: '100%', borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                              <Form form={form} layout="vertical" onFinish={onFinish} initialValues={{
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
                              // 切换市场类型时，清空交易品种并切换列表
                              form.setFieldsValue({ symbol: undefined });
                              // 如果切换到股票，重置数据源为main
                              if (val === 'stock') {
                                  form.setFieldsValue({ data_source: 'main' });
                              }
                              // 直接使用缓存切换，不再重新请求
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
                                const marketType = getFieldValue('market_type') || 'futures';
                                return (
                                    <Form.Item name="symbol" label={`交易品种 (共${symbols.length}个)`} rules={[{ required: true }]}>
                                          <Select 
                                            onChange={onSymbolChange}
                                            showSearch
                                            placeholder="选择或搜索品种"
                                            optionFilterProp="children"
                                            filterOption={(input, option) =>
                                              option.children.toLowerCase().indexOf(input.toLowerCase()) >= 0
                                            }
                                            // 针对股票大量数据，优化渲染（如果数据量很大，可能需要虚拟滚动，这里暂且直接展示）
                                            // Antd 4+ 的 Select 已经内置了虚拟滚动，通常可以处理几千条数据
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
                                // 切换策略时重置默认值
                                if (val === 'MA55BreakoutStrategy' || val === 'MA55TouchExitStrategy' || val === 'MA20MA55CrossoverStrategy' || val === 'MA20MA55PartialTakeProfitStrategy') {
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
                                } else if (val === 'MA20MA55CrossoverStrategy' || val === 'MA20MA55PartialTakeProfitStrategy' || val === 'StockMA20MA55LongOnlyStrategy') {
                                        initialValues.fast_period = 20;
                                        initialValues.slow_period = 55;
                                        if (val === 'MA20MA55PartialTakeProfitStrategy') {
                                            initialValues.take_profit_points = 50; // 默认值
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
                                }
                            }}>
                                <Option value="MA55BreakoutStrategy">MA55突破+背离离场</Option>
                                <Option value="MA55TouchExitStrategy">MA55突破+触碰平仓</Option>
                                <Option value="MA20MA55CrossoverStrategy">20/55双均线交叉(多空)</Option>
                                <Option value="StockMA20MA55LongOnlyStrategy">20/55双均线多头(股票)</Option>
                                <Option value="MA20MA55PartialTakeProfitStrategy">20/55双均线+盈利平半仓</Option>
                                <Option value="DKXStrategy">DKX多空线策略</Option>
                                <Option value="DKXPartialTakeProfitStrategy">DKX多空线+盈利平半仓</Option>
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

                        {strategyType === 'TrendFollowingStrategy' || strategyType === 'MA20MA55CrossoverStrategy' || strategyType === 'MA20MA55PartialTakeProfitStrategy' || strategyType === 'StockMA20MA55LongOnlyStrategy' ? (
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
                                {strategyType === 'MA20MA55PartialTakeProfitStrategy' && (
                                    <Form.Item name="take_profit_points" label="盈利平半仓点数" tooltip="当浮动盈利达到此点数时，平掉一半仓位">
                                        <Input type="number" />
                                    </Form.Item>
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

                        {strategyType === 'DKXStrategy' || strategyType === 'DKXPartialTakeProfitStrategy' ? (
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
                            </>
                        ) : null}

                        <Form.Item
                            noStyle
                            shouldUpdate={(prevValues, currentValues) => prevValues.size_mode !== currentValues.size_mode}
                        >
                            {({ getFieldValue }) => {
                                const sizeMode = getFieldValue('size_mode');
                                // TrendFollowingStrategy 始终显示 (没有 size_mode 字段)
                                // 其他策略: 仅当 size_mode 为 'atr_risk' (或默认未选时) 显示
                                if (strategyType === 'TrendFollowingStrategy' || !sizeMode || sizeMode === 'atr_risk') {
                                    return (
                                        <Form.Item name="atr_multiplier" label="ATR止损倍数">
                                          <Input type="number" step="0.1" />
                                        </Form.Item>
                                    );
                                }
                                return null;
                            }}
                        </Form.Item>

                        {strategyType === 'MA55BreakoutStrategy' || strategyType === 'MA55TouchExitStrategy' || strategyType === 'MA20MA55CrossoverStrategy' || strategyType === 'MA20MA55PartialTakeProfitStrategy' || strategyType === 'DKXStrategy' || strategyType === 'DKXPartialTakeProfitStrategy' || strategyType === 'StockMA20MA55LongOnlyStrategy' ? (
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
                        
                        {/* 隐藏字段，自动设置 */}
                        <Form.Item name="contract_multiplier" label="合约乘数" hidden>
                            <Input type="number" />
                        </Form.Item>
                        <Form.Item name="atr_period" hidden><Input /></Form.Item>

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
                        
                        <Card 
                            title={<span><DashboardOutlined /> 回测概览</span>} 
                            variant="borderless"
                            style={{ borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}
                        >
                            <Row gutter={[16, 16]}>
                                {getMetricsData().map(item => (
                                    <Col span={4} key={item.key}>
                                        <Card 
                                            variant="borderless" 
                                            styles={{ body: { padding: '16px', background: item.bg, borderRadius: '8px', transition: 'all 0.3s' } }}
                                            hoverable
                                            style={{ height: '100%' }}
                                        >
                                            <Statistic 
                                                title={<span style={{ color: '#666', fontSize: '13px', display: 'flex', alignItems: 'center' }}>{item.metric}</span>}
                                                value={item.value} 
                                                valueStyle={{ 
                                                    color: item.isPnl 
                                                        ? (parseFloat(item.value) > 0 ? '#cf1322' : (parseFloat(item.value) < 0 ? '#3f8600' : '#333'))
                                                        : '#333',
                                                    fontSize: '20px',
                                                    fontWeight: 'bold',
                                                    marginTop: '4px'
                                                }}
                                                prefix={<span style={{ color: item.color, marginRight: '8px', fontSize: '20px', verticalAlign: 'middle' }}>{item.icon}</span>}
                                            />
                                        </Card>
                                    </Col>
                                ))}
                            </Row>
                        </Card>
                        
                        <Card 
                            title={
                                <div style={{ display: 'flex', alignItems: 'center' }}>
                                    <LineChartOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
                                    {chartType === 'line' ? "账户权益曲线" : 
                                     chartType === 'kline' ? "K线图 & 交易信号" :
                                     "盈亏分布分析"}
                                </div>
                            } 
                            variant="borderless"
                            style={{ borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}
                            extra={
                                <Radio.Group value={chartType} onChange={e => setChartType(e.target.value)} buttonStyle="solid">
                                    <Radio.Button value="line"><LineChartOutlined /> 趋势图</Radio.Button>
                                    <Radio.Button value="kline"><ThunderboltOutlined /> K线图</Radio.Button>
                                    <Radio.Button value="pie"><PercentageOutlined /> 饼状图</Radio.Button>
                                </Radio.Group>
                            }
                        >
                          <ReactECharts 
                            option={getOption()} 
                            style={{ height: '800px', width: '100%' }} 
                            notMerge={true} 
                            onEvents={{
                                'click': onChartClick
                            }}
                          />
                        </Card>
                        
                        {selectedMddInfo && (
                            <Card title="最大回撤详情" variant="borderless" style={{ marginTop: '24px', backgroundColor: '#fffbe6', border: '1px solid #ffe58f' }}>
                                <div style={{ display: 'flex', gap: '40px', flexWrap: 'wrap' }}>
                                    <div>
                                       <div style={{ fontSize: '12px', color: '#888' }}>日期</div>
                                        <div style={{ fontSize: '16px', fontWeight: 'bold' }}>{selectedMddInfo.mdd_date}</div>
                                    </div>
                                    <div>
                                        <div style={{ fontSize: '12px', color: '#888' }}>持仓方向</div>
                                        <div style={{ fontSize: '16px', fontWeight: 'bold' }}>{selectedMddInfo.holding_direction}</div>
                                    </div>
                                    <div>
                                        <div style={{ fontSize: '12px', color: '#888' }}>开仓均价</div>
                                        <div style={{ fontSize: '16px', fontWeight: 'bold' }}>
                                            {(() => {
                                                const val = parseFloat(selectedMddInfo.entry_price);
                                                return !isNaN(val) ? val.toFixed(2) : 'N/A';
                                            })()}
                                        </div>
                                    </div>
                                    <div>
                                        <div style={{ fontSize: '12px', color: '#888' }}>最大回撤价格</div>
                                        <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#cf1322' }}>
                                            {(() => {
                                                const val = parseFloat(selectedMddInfo.mdd_price);
                                                return !isNaN(val) ? val.toFixed(2) : 'N/A';
                                            })()}
                                        </div>
                                    </div>
                                    <div>
                                        <div style={{ fontSize: '12px', color: '#888' }}>亏损点数</div>
                                        <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#cf1322' }}>
                                            {(() => {
                                                const entry = parseFloat(selectedMddInfo.entry_price);
                                                const mdd = parseFloat(selectedMddInfo.mdd_price);
                                                if (!isNaN(entry) && !isNaN(mdd)) {
                                                    return Math.abs(mdd - entry).toFixed(2);
                                                }
                                                return 'N/A';
                                            })()}
                                        </div>
                                    </div>
                                </div>
                            </Card>
                        )}
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
                </div>
              </div>

                <div style={{ display: activeTab === '2' ? 'block' : 'none', height: '100%' }}>
                    <Card 
                        title={<span><CodeOutlined /> 编辑策略逻辑 (server/core/strategy.py)</span>}
                        extra={
                            <Button type="primary" onClick={saveStrategyCode} loading={savingCode} icon={<CodeOutlined />}>
                                保存并生效
                            </Button>
                        }
                        variant="borderless"
                        style={{ height: '100%' }}
                        styles={{ body: { height: 'calc(100% - 60px)', padding: 0 } }}
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
                </div>

                <div style={{ display: activeTab === '3' ? 'block' : 'none', height: '100%' }}>
                    <div style={{ padding: '24px', height: '100%' }}>
                        <Card 
                            title={<span><FileTextOutlined /> 详细交易日志</span>} 
                            extra={
                                <Button type="primary" size="small" icon={<SaveOutlined />} onClick={downloadCurrentLogs}>
                                    下载日志
                                </Button>
                            }
                            variant="borderless"
                            style={{ height: '100%', borderRadius: '8px' }}
                            styles={{ body: { height: 'calc(100% - 60px)', padding: '0' } }}
                        >
                            {parsedLogs && parsedLogs.length > 0 ? (
                                <Table 
                                    dataSource={parsedLogs}
                                    onChange={(pagination, filters, sorter, extra) => setFilteredLogs(extra.currentDataSource)}
                                    columns={[
                                        { 
                                            title: '时间', 
                                            dataIndex: 'date', 
                                            width: 180,
                                            sorter: (a, b) => new Date(a.date) - new Date(b.date),
                                            defaultSortOrder: 'ascend'
                                        },
                                        { 
                                            title: '类型', 
                                            dataIndex: 'type', 
                                            width: 100,
                                            filters: [
                                                { text: '买入', value: 'buy' },
                                                { text: '卖出', value: 'sell' },
                                                { text: '结算', value: 'profit' },
                                                { text: '信号', value: 'signal' },
                                                { text: '系统', value: 'system' },
                                                { text: '信息', value: 'info' }
                                            ],
                                            onFilter: (value, record) => record.type === value,
                                            render: (type) => {
                                                const config = {
                                                    'buy': { color: '#f50', text: '买入' },
                                                    'sell': { color: '#87d068', text: '卖出' },
                                                    'profit': { color: 'gold', text: '结算' },
                                                    'signal': { color: 'blue', text: '信号' },
                                                    'system': { color: 'default', text: '系统' },
                                                    'info': { color: 'default', text: '信息' }
                                                };
                                                const c = config[type] || config['info'];
                                                return <Tag color={c.color}>{c.text}</Tag>;
                                            }
                                        },
                                        { 
                                            title: '内容', 
                                            dataIndex: 'content',
                                            render: (text) => <span style={{ fontFamily: 'monospace' }}>{text}</span>
                                        },
                                        { 
                                            title: '净利', 
                                            dataIndex: 'pnl', 
                                            width: 120,
                                            sorter: (a, b) => (a.pnl || 0) - (b.pnl || 0),
                                            render: (pnl) => pnl !== null ? <span style={{ color: pnl > 0 ? '#cf1322' : '#3f8600', fontWeight: 'bold' }}>{pnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span> : '-' 
                                        }
                                    ]}
                                    pagination={{ pageSize: 50, showSizeChanger: true }}
                                    scroll={{ y: 'calc(100vh - 250px)' }}
                                    size="small"
                                    rowKey="key"
                                    bordered
                                />
                            ) : <div style={{ textAlign: 'center', color: '#999', marginTop: '50px' }}>暂无日志数据，请先运行回测</div>}
                        </Card>
                    </div>
                </div>

                <div style={{ display: activeTab === '4' ? 'block' : 'none', height: '100%', overflowY: 'auto' }}>
                    <div style={{ padding: '24px', height: '100%' }}>
                        {viewingHistory ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                                    <Button onClick={() => setViewingHistory(null)} icon={<ArrowLeftOutlined />}>返回列表</Button>
                                    <h2 style={{ color: '#fff', margin: 0 }}>
                                        {strategyNameMap[viewingHistory.strategy_name] || viewingHistory.strategy_name} - {getSymbolName(viewingHistory.symbol)} ({viewingHistory.period})
                                    </h2>
                                </div>
                                
                                {viewingHistory.strategy_params && (
                                    <Card variant="borderless" style={{ borderRadius: '8px' }} styles={{ body: { padding: '12px 24px' } }}>
                                        <Descriptions title="策略参数" size="small" column={4}>
                                            {Object.entries(viewingHistory.strategy_params).map(([key, value]) => (
                                                <Descriptions.Item key={key} label={key}>{String(value)}</Descriptions.Item>
                                            ))}
                                        </Descriptions>
                                    </Card>
                                )}
                                
                                <Row gutter={[16, 16]}>
                                    {getMetricsData({ ...viewingHistory.detail_data, metrics: viewingHistory.metrics || (viewingHistory.detail_data && viewingHistory.detail_data.metrics) }).map(item => (
                                        <Col span={4} key={item.key}>
                                            <Card variant="borderless" style={{ background: item.bg, borderRadius: '8px' }}>
                                                <Statistic
                                                    title={
                                                        <span style={{ fontSize: '14px', color: '#666', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                            {item.icon} {item.metric}
                                                        </span>
                                                    }
                                                    value={item.value}
                                                    valueStyle={{ color: item.color, fontSize: '20px', fontWeight: 'bold' }}
                                                />
                                            </Card>
                                        </Col>
                                    ))}
                                </Row>

                                <Card 
                                    title={
                                        <div style={{ display: 'flex', alignItems: 'center' }}>
                                            <LineChartOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
                                            {chartType === 'line' ? "账户权益曲线" : 
                                             chartType === 'kline' ? "K线图 & 交易信号" :
                                             "盈亏分布分析"}
                                        </div>
                                    }
                                    variant="borderless" 
                                    style={{ marginTop: '24px', borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}
                                    extra={
                                        <Radio.Group value={chartType} onChange={e => setChartType(e.target.value)} buttonStyle="solid">
                                            <Radio.Button value="line"><LineChartOutlined /> 趋势图</Radio.Button>
                                            <Radio.Button value="kline"><ThunderboltOutlined /> K线图</Radio.Button>
                                            <Radio.Button value="pie"><PercentageOutlined /> 饼状图</Radio.Button>
                                        </Radio.Group>
                                    }
                                >
                                    <div style={{ height: '600px' }}>
                                         <ReactECharts 
                                            option={getOption({ ...viewingHistory.detail_data, metrics: viewingHistory.metrics || (viewingHistory.detail_data && viewingHistory.detail_data.metrics) }, viewingHistory.strategy_name)} 
                                            style={{ height: '100%', width: '100%' }} 
                                            notMerge={true}
                                            onEvents={{ click: onChartClick }}
                                         />
                                    </div>
                                </Card>

                                <Card 
                                    title={<span><FileTextOutlined /> 详细交易日志</span>} 
                                    variant="borderless"
                                    style={{ borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}
                                    extra={<Button type="primary" size="small" icon={<SaveOutlined />} onClick={downloadLogs}>下载日志</Button>}
                                >
                                    {viewingHistory.detail_data && Array.isArray(viewingHistory.detail_data.logs) ? (
                                        <Table 
                                            dataSource={viewingHistory.detail_data.logs.map((logItem, index) => parseLogItem(logItem, index))}
                                            columns={[
                                                { 
                                                    title: '时间', 
                                                    dataIndex: 'date', 
                                                    width: 180,
                                                    sorter: (a, b) => new Date(a.date) - new Date(b.date),
                                                    defaultSortOrder: 'ascend'
                                                },
                                                { 
                                                    title: '类型', 
                                                    dataIndex: 'type', 
                                                    width: 100,
                                                    filters: [
                                                        { text: '买入', value: 'buy' },
                                                        { text: '卖出', value: 'sell' },
                                                        { text: '结算', value: 'profit' },
                                                        { text: '信号', value: 'signal' },
                                                        { text: '系统', value: 'system' },
                                                        { text: '信息', value: 'info' }
                                                    ],
                                                    onFilter: (value, record) => record.type === value,
                                                    render: (type) => {
                                                        const config = {
                                                            'buy': { color: '#f50', text: '买入' },
                                                            'sell': { color: '#87d068', text: '卖出' },
                                                            'profit': { color: 'gold', text: '结算' },
                                                            'signal': { color: 'blue', text: '信号' },
                                                            'system': { color: 'default', text: '系统' },
                                                            'info': { color: 'default', text: '信息' }
                                                        };
                                                        const c = config[type] || config['info'];
                                                        return <Tag color={c.color}>{c.text}</Tag>;
                                                    }
                                                },
                                                { 
                                                    title: '内容', 
                                                    dataIndex: 'content',
                                                    render: (text) => <span style={{ fontFamily: 'monospace' }}>{text}</span>
                                                },
                                                { 
                                                    title: '净利', 
                                                    dataIndex: 'pnl', 
                                                    width: 120,
                                                    sorter: (a, b) => (a.pnl || 0) - (b.pnl || 0),
                                                    render: (pnl) => pnl !== null ? <span style={{ color: pnl > 0 ? '#cf1322' : '#3f8600', fontWeight: 'bold' }}>{pnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span> : '-' 
                                                }
                                            ]}
                                            pagination={{ pageSize: 50, showSizeChanger: true }}
                                            scroll={{ y: 500 }}
                                            size="small"
                                            rowKey="key"
                                            bordered
                                        />
                                    ) : <div style={{ textAlign: 'center', color: '#999', marginTop: '50px' }}>暂无日志数据</div>}
                                </Card>
                            </div>
                        ) : (
                            <Card 
                                title={<div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><HistoryOutlined style={{ color: '#1890ff', fontSize: '20px' }} /> <span style={{ fontSize: '18px', fontWeight: 'bold', color: '#333' }}>回测历史记录</span></div>} 
                                bordered={false}
                                style={{ background: '#fff', height: '100%', borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }} 
                                headStyle={{ borderBottom: '1px solid #f0f0f0', padding: '0 24px' }}
                                styles={{ body: { padding: '0', height: 'calc(100% - 57px)', position: 'relative' } }}
                                extra={<Button type="primary" ghost icon={<ReloadOutlined />} onClick={fetchSavedBacktests}>刷新列表</Button>}
                            >
                                <Table 
                                    dataSource={savedBacktests} 
                                    rowKey="id"
                                    loading={historyLoading} 
                                    size="middle"
                                    columns={[
                                        { title: 'ID', dataIndex: 'id', key: 'id', width: 60, align: 'center', sorter: (a, b) => a.id - b.id, defaultSortOrder: 'descend' },
                                        { 
                                            title: '策略名称', 
                                            dataIndex: 'strategy_name', 
                                            key: 'strategy_name',
                                            width: 180,
                                            render: (text) => <span style={{ fontWeight: 500, color: '#1890ff' }}>{strategyNameMap[text] || text}</span>
                                        },
                                        { 
                                            title: '交易品种', 
                                            dataIndex: 'symbol', 
                                            key: 'symbol', 
                                            width: 140,
                                            align: 'center',
                                            render: (text) => <Tag color="geekblue" style={{ margin: 0, minWidth: '60px', textAlign: 'center' }}>{getSymbolName(text)}</Tag>
                                        },
                                        { 
                                            title: '周期', 
                                            dataIndex: 'period', 
                                            key: 'period', 
                                            width: 80,
                                            align: 'center',
                                            render: (text) => <Tag color={text === 'daily' ? 'purple' : 'cyan'}>{periodMap[text] || text}</Tag>
                                        },
                                        { 
                                            title: '最终权益', 
                                            dataIndex: 'final_value', 
                                            key: 'final_value',
                                            align: 'right',
                                            sorter: (a, b) => a.final_value - b.final_value,
                                            render: (val) => val ? <span style={{ fontWeight: 'bold', fontFamily: 'Consolas, Monaco, monospace' }}>{val.toFixed(2)}</span> : '-' 
                                        },
                                        { 
                                            title: '净利润', 
                                            dataIndex: 'net_profit', 
                                            key: 'net_profit',
                                            align: 'right',
                                            sorter: (a, b) => a.net_profit - b.net_profit,
                                            render: (val) => {
                                                if (val === null || val === undefined) return '-';
                                                const color = val >= 0 ? '#f5222d' : '#52c41a'; 
                                                const icon = val >= 0 ? <RiseOutlined /> : <FallOutlined />;
                                                return <span style={{ color, fontWeight: 'bold', fontFamily: 'Consolas, Monaco, monospace' }}>{icon} {val.toFixed(2)}</span>;
                                            } 
                                        },
                                        { 
                                            title: '收益率', 
                                            dataIndex: 'return_rate', 
                                            key: 'return_rate',
                                            align: 'right',
                                            sorter: (a, b) => a.return_rate - b.return_rate,
                                            render: (val, record) => {
                                                // 兼容逻辑：如果return_rate为空，尝试通过net_profit计算
                                                let displayVal = val;
                                                if (displayVal === null || displayVal === undefined) {
                                                    if (record.net_profit !== null && record.final_value !== null) {
                                                        const initial = record.final_value - record.net_profit;
                                                        if (initial !== 0) {
                                                            displayVal = record.net_profit / initial;
                                                        }
                                                    }
                                                }
                                                
                                                if (displayVal === null || displayVal === undefined) return '-';
                                                
                                                const color = displayVal >= 0 ? '#f5222d' : '#52c41a';
                                                return <span style={{ color, fontWeight: 'bold' }}>{(displayVal * 100).toFixed(2)}%</span>;
                                            }
                                        },
                                        { 
                                            title: '胜率', 
                                            dataIndex: 'win_rate', 
                                            key: 'win_rate',
                                            width: 120,
                                            sorter: (a, b) => a.win_rate - b.win_rate,
                                            render: (val) => {
                                                if (val === null || val === undefined) return '-';
                                                // 兼容逻辑：如果大于1，认为是百分比值，否则认为是比例
                                                const percent = val > 1 ? val : val * 100;
                                                return <Progress percent={percent.toFixed(1)} size="small" status={percent > 50 ? 'exception' : 'success'} strokeColor={percent > 50 ? '#f5222d' : '#52c41a'} format={percent => <span style={{ color: '#666' }}>{percent}%</span>} />;
                                            }
                                        },
                                        { 
                                            title: '最大回撤', 
                                            dataIndex: 'max_drawdown', 
                                            key: 'max_drawdown',
                                            align: 'right',
                                            sorter: (a, b) => a.max_drawdown - b.max_drawdown,
                                            render: (val) => {
                                                if (!val) return '-';
                                                // 兼容逻辑：如果大于1，认为是百分比值，否则认为是比例
                                                const percent = val > 1 ? val : val * 100;
                                                return <span style={{ color: '#faad14' }}>{percent.toFixed(2)}%</span>;
                                            }
                                        },
                                        { title: '交易次数', dataIndex: 'total_trades', key: 'total_trades', align: 'center', sorter: (a, b) => a.total_trades - b.total_trades },
                                        { 
                                            title: '保存时间', 
                                            dataIndex: 'timestamp', 
                                            key: 'timestamp', 
                                            width: 160,
                                            align: 'center',
                                            sorter: (a, b) => new Date(a.timestamp) - new Date(b.timestamp),
                                            render: (val) => <span style={{ fontSize: '12px', color: '#999' }}>{new Date(val).toLocaleString()}</span> 
                                        },
                                        {
                                            title: '操作',
                                            key: 'action',
                                            align: 'center',
                                            fixed: 'right',
                                            width: 140,
                                            render: (_, record) => (
                                                <Space size="small">
                                                    <Button type="primary" size="small" ghost onClick={() => handleViewHistory(record.id)}>查看详情</Button>
                                                    <Popconfirm
                                                        title="删除记录"
                                                        description="确定要删除这条回测记录吗？"
                                                        onConfirm={() => handleDeleteBacktest(record.id)}
                                                        okText="确定"
                                                        cancelText="取消"
                                                    >
                                                        <Button type="primary" size="small" danger icon={<DeleteOutlined />} />
                                                    </Popconfirm>
                                                </Space>
                                            )
                                        }
                                    ]}
                                    pagination={{ 
                                        pageSize: 20, 
                                        showTotal: (total) => `共 ${total} 条记录`,
                                        showQuickJumper: true,
                                        showSizeChanger: true,
                                        position: ['bottomRight'],
                                        style: {
                                            position: 'absolute',
                                            bottom: 0,
                                            right: 0,
                                            width: '100%',
                                            padding: '12px 24px',
                                            margin: 0,
                                            borderTop: '1px solid #f0f0f0',
                                            background: '#fff',
                                            display: 'flex',
                                            justifyContent: 'flex-end',
                                            zIndex: 10
                                        }
                                    }}
                                    scroll={{ x: 1300, y: 'calc(100vh - 240px)' }}
                                />
                            </Card>
                        )}
                    </div>
                </div>
            </Content>
        </Layout>
      </Content>
    </Layout>
  );
};

export default App;
