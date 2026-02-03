import React, { useState } from 'react';
import { Collapse, Tabs, Badge, Tag, Typography, Progress, Button, Tooltip } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined, FullscreenOutlined, FullscreenExitOutlined } from '@ant-design/icons';
import SingleBacktestResult from './SingleBacktestResult';

const { Panel } = Collapse;
const { Text } = Typography;

const BatchBacktestResult = ({ results, symbols = [], isFullScreen, onToggleFullScreen }) => {
  const [activeKey, setActiveKey] = useState([]);

  if (!results || !results.isBatch) return null;

  const { items, summary } = results;

  // 渲染摘要头
  const renderHeader = () => (
    <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <Text strong style={{ fontSize: 16 }}>批量回测报告</Text>
        <Tag color="blue">总计: {summary.total}</Tag>
        <Tag color="success">成功: {summary.success}</Tag>
        {summary.failed > 0 && <Tag color="error">失败: {summary.failed}</Tag>}
      </div>
      {onToggleFullScreen && (
          <Tooltip title={isFullScreen ? "退出全屏" : "全屏显示"}>
            <Button 
                type="text"
                icon={isFullScreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />} 
                onClick={onToggleFullScreen}
            >
                {isFullScreen ? "退出全屏" : "全屏查看"}
            </Button>
          </Tooltip>
      )}
    </div>
  );

  return (
    <div>
      {renderHeader()}
      
      <Collapse 
        defaultActiveKey={['0']} 
        onChange={setActiveKey}
        expandIconPosition="end"
      >
        {items.map((item, index) => {
          const isSuccess = item.success;
          const data = item.data;
          const symbol = item.symbol;
          const metrics = data?.metrics;
          
          // 获取品种名称
          const symbolObj = symbols.find(s => s.code === symbol);
          // 如果找不到完全匹配，尝试匹配前缀 (e.g. SH0 -> SH) 或者从名称中提取
          // 这里假设 symbols 列表里有准确的 code
          const symbolName = symbolObj ? symbolObj.name : '';
          
          // 构建面板标题
          const header = (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {isSuccess ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
                <Text strong>{symbol}</Text>
                {symbolName && <Text type="secondary" style={{ fontSize: '13px' }}>{symbolName}</Text>}
                
                {isSuccess && metrics && (
                  <>
                    <Tag color="gold" style={{ marginLeft: 8, fontWeight: 'bold' }}>
                      净利: {metrics.net_profit?.toLocaleString()}
                    </Tag>
                    <Tag color={metrics.net_profit > 0 ? 'red' : 'green'}>
                      收益: {(metrics.one_hand_profit_pct !== undefined && metrics.one_hand_profit_pct !== null) ? metrics.one_hand_profit_pct.toFixed(2) : metrics.return_rate?.toFixed(2)}%
                    </Tag>
                    <Tag>回撤: {metrics.max_drawdown?.toFixed(2)}%</Tag>
                  </>
                )}
              </div>
              {!isSuccess && <Text type="danger" style={{ fontSize: 12 }}>{item.error}</Text>}
            </div>
          );

          return (
            <Panel header={header} key={index}>
              {isSuccess ? (
                // 只有展开时才渲染内容以优化性能 (Ant Design Collapse 默认销毁折叠内容吗? 不一定，加个判断)
                activeKey.includes(index.toString()) && (
                  <SingleBacktestResult results={data} />
                )
              ) : (
                <div style={{ padding: 16, color: '#ff4d4f' }}>
                  错误信息: {item.error}
                </div>
              )}
            </Panel>
          );
        })}
      </Collapse>
    </div>
  );
};

export default BatchBacktestResult;
