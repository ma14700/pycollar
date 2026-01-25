import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Space, Button, Popconfirm, message, Progress, Descriptions, Row, Col, Radio } from 'antd';
import { 
    ReloadOutlined, HistoryOutlined, DeleteOutlined, RiseOutlined, 
    FallOutlined, ArrowLeftOutlined, LineChartOutlined, ThunderboltOutlined,
    PercentageOutlined, FileTextOutlined, SaveOutlined
} from '@ant-design/icons';
import axios from 'axios';
import { strategyNameMap, periodMap } from '../../constants';
import { getSymbolName, parseLogItem } from '../../utils';
import MetricsPanel from '../../components/MetricsPanel';
import ChartPanel from '../../components/ChartPanel';

const HistoryPage = () => {
  const [savedBacktests, setSavedBacktests] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [viewingHistory, setViewingHistory] = useState(null);
  const [chartType, setChartType] = useState('line');

  useEffect(() => {
      fetchSavedBacktests();
  }, []);

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

  const downloadLogs = () => {
    if (!viewingHistory || !viewingHistory.detail_data || !viewingHistory.detail_data.logs) {
      message.warning('暂无日志可下载');
      return;
    }
    
    const logsToExport = viewingHistory.detail_data.logs.map((log, index) => parseLogItem(log, index));
    
    const header = "时间,类型,内容,净利\n";
    const rows = logsToExport.map(item => {
        const typeMap = {
            'buy': '买入', 'sell': '卖出', 'profit': '结算',
            'signal': '信号', 'system': '系统', 'info': '信息'
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

  if (viewingHistory) {
      return (
        <div style={{ padding: '24px', height: '100%', overflowY: 'auto' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <Button onClick={() => setViewingHistory(null)} icon={<ArrowLeftOutlined />}>返回列表</Button>
                    <h2 style={{ color: '#333', margin: 0 }}>
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
                
                <MetricsPanel metrics={viewingHistory.metrics || (viewingHistory.detail_data && viewingHistory.detail_data.metrics)} />

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
                         <ChartPanel 
                            chartType={chartType}
                            results={{ ...viewingHistory.detail_data, metrics: viewingHistory.metrics || (viewingHistory.detail_data && viewingHistory.detail_data.metrics) }}
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
                                { title: '时间', dataIndex: 'date', width: 180, sorter: (a, b) => new Date(a.date) - new Date(b.date), defaultSortOrder: 'ascend' },
                                { 
                                    title: '类型', dataIndex: 'type', width: 100,
                                    filters: [
                                        { text: '买入', value: 'buy' }, { text: '卖出', value: 'sell' },
                                        { text: '结算', value: 'profit' }, { text: '信号', value: 'signal' },
                                        { text: '系统', value: 'system' }, { text: '信息', value: 'info' }
                                    ],
                                    onFilter: (value, record) => record.type === value,
                                    render: (type) => {
                                        const config = { 'buy': { color: '#f50', text: '买入' }, 'sell': { color: '#87d068', text: '卖出' }, 'profit': { color: 'gold', text: '结算' }, 'signal': { color: 'blue', text: '信号' }, 'system': { color: 'default', text: '系统' }, 'info': { color: 'default', text: '信息' } };
                                        const c = config[type] || config['info'];
                                        return <Tag color={c.color}>{c.text}</Tag>;
                                    }
                                },
                                { title: '内容', dataIndex: 'content', render: (text) => <span style={{ fontFamily: 'monospace' }}>{text}</span> },
                                { title: '净利', dataIndex: 'pnl', width: 120, sorter: (a, b) => (a.pnl || 0) - (b.pnl || 0), render: (pnl) => pnl !== null ? <span style={{ color: pnl > 0 ? '#cf1322' : '#3f8600', fontWeight: 'bold' }}>{pnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span> : '-' }
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
        </div>
      );
  }

  return (
    <div style={{ padding: '24px', height: '100%' }}>
        <Card 
            title={<div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><HistoryOutlined style={{ color: '#1890ff', fontSize: '20px' }} /> <span style={{ fontSize: '18px', fontWeight: 'bold', color: '#333' }}>回测历史记录</span></div>} 
            variant="borderless"
            style={{ background: '#fff', height: '100%', borderRadius: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }} 
            styles={{ 
                header: { borderBottom: '1px solid #f0f0f0', padding: '0 24px' },
                body: { padding: '0', height: 'calc(100% - 57px)', position: 'relative' } 
            }}
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
                        title: '策略名称', dataIndex: 'strategy_name', key: 'strategy_name', width: 180,
                        render: (text) => <span style={{ fontWeight: 500, color: '#1890ff' }}>{strategyNameMap[text] || text}</span>
                    },
                    { 
                        title: '交易品种', dataIndex: 'symbol', key: 'symbol', width: 140, align: 'center',
                        render: (text) => <Tag color="geekblue" style={{ margin: 0, minWidth: '60px', textAlign: 'center' }}>{getSymbolName(text)}</Tag>
                    },
                    { 
                        title: '周期', dataIndex: 'period', key: 'period', width: 80, align: 'center',
                        render: (text) => <Tag color={text === 'daily' ? 'purple' : 'cyan'}>{periodMap[text] || text}</Tag>
                    },
                    { 
                        title: '最终权益', dataIndex: 'final_value', key: 'final_value', align: 'right', sorter: (a, b) => a.final_value - b.final_value,
                        render: (val) => val ? <span style={{ fontWeight: 'bold', fontFamily: 'Consolas, Monaco, monospace' }}>{val.toFixed(2)}</span> : '-' 
                    },
                    { 
                        title: '净利润', dataIndex: 'net_profit', key: 'net_profit', align: 'right', sorter: (a, b) => a.net_profit - b.net_profit,
                        render: (val) => {
                            if (val === null || val === undefined) return '-';
                            const color = val >= 0 ? '#f5222d' : '#52c41a'; 
                            const icon = val >= 0 ? <RiseOutlined /> : <FallOutlined />;
                            return <span style={{ color, fontWeight: 'bold', fontFamily: 'Consolas, Monaco, monospace' }}>{icon} {val.toFixed(2)}</span>;
                        } 
                    },
                    { 
                        title: '收益率', dataIndex: 'return_rate', key: 'return_rate', align: 'right', sorter: (a, b) => a.return_rate - b.return_rate,
                        render: (val, record) => {
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
                        title: '胜率', dataIndex: 'win_rate', key: 'win_rate', width: 120, sorter: (a, b) => a.win_rate - b.win_rate,
                        render: (val) => {
                            if (val === null || val === undefined) return '-';
                            const percent = val > 1 ? val : val * 100;
                            return <Progress percent={percent.toFixed(1)} size="small" status={percent > 50 ? 'exception' : 'success'} strokeColor={percent > 50 ? '#f5222d' : '#52c41a'} format={percent => <span style={{ color: '#666' }}>{percent}%</span>} />;
                        }
                    },
                    { 
                        title: '最大回撤', dataIndex: 'max_drawdown', key: 'max_drawdown', align: 'right', sorter: (a, b) => a.max_drawdown - b.max_drawdown,
                        render: (val) => {
                            if (!val) return '-';
                            const percent = val > 1 ? val : val * 100;
                            return <span style={{ color: '#faad14' }}>{percent.toFixed(2)}%</span>;
                        }
                    },
                    { title: '交易次数', dataIndex: 'total_trades', key: 'total_trades', align: 'center', sorter: (a, b) => a.total_trades - b.total_trades },
                    { 
                        title: '保存时间', dataIndex: 'timestamp', key: 'timestamp', width: 160, align: 'center', sorter: (a, b) => new Date(a.timestamp) - new Date(b.timestamp),
                        render: (val) => <span style={{ fontSize: '12px', color: '#999' }}>{new Date(val).toLocaleString()}</span> 
                    },
                    {
                        title: '操作', key: 'action', align: 'center', fixed: 'right', width: 140,
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
    </div>
  );
};

export default HistoryPage;
