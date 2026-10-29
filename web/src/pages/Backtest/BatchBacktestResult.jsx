import React, { useState } from 'react';
import { Collapse, Tabs, Badge, Tag, Typography, Progress, Button, Tooltip } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined, FullscreenOutlined, FullscreenExitOutlined } from '@ant-design/icons';
import SingleBacktestResult from './SingleBacktestResult';
import { accountReturn } from '../../utils/contractEstimate';
import { formatNumber, formatPercent, valueColor } from '../../utils/backtestAnalytics';
import { strategyOptions } from '../../utils/backtestStrategies';
import BatchBacktestAnalysis from '../../components/BatchBacktestAnalysis';

const { Panel } = Collapse;
const { Text } = Typography;

const BatchBacktestResult = ({ results, symbols = [], isFullScreen, onToggleFullScreen }) => {
  const [activeKey, setActiveKey] = useState(['0']);
  const [analysisOpen, setAnalysisOpen] = useState(false);

  if (!results || !results.isBatch) return null;

  const { items, summary } = results;

  // 渲染摘要头
  const renderHeader = () => (
    <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
        <Text strong style={{ fontSize: 16 }}>批量回测报告</Text>
        <Button type="primary" onClick={() => setAnalysisOpen(true)}>回测分析</Button>
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
      {analysisOpen && <BatchBacktestAnalysis items={items} onClose={() => setAnalysisOpen(false)} />}

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
          const symbolObj = symbols.find(s => s.code === symbol)
            || symbols.find(s => s.code === `${symbol?.match(/^[A-Za-z]+/)?.[0]}0`);
          // 如果找不到完全匹配，尝试匹配前缀 (e.g. SH0 -> SH) 或者从名称中提取
          // 这里假设 symbols 列表里有准确的 code
          const symbolName = symbolObj ? symbolObj.name : '';

          // 构建面板标题
          const header = (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, width: '100%' }}>
              <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8, minWidth: 0 }}>
                {isSuccess ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
                <Text strong>{symbol}</Text>
                {symbolName && <Text type="secondary" style={{ fontSize: '13px' }}>{symbolName}</Text>}
                <Tag color="blue">{strategyOptions.find(option => option.value === (item.strategy_name || data?.backtest_request?.strategy_name))?.label || item.strategy_name || data?.backtest_request?.strategy_name || '策略未知'}</Tag>

                {isSuccess && metrics && (
                  <>
                    <Tag color="gold" style={{ marginLeft: 8, fontWeight: 'bold' }}>
                      净利: {metrics.net_profit?.toLocaleString()}
                    </Tag>
                    <Tag color={metrics.net_profit > 0 ? 'red' : 'green'}>
                      账户收益: {accountReturn(metrics)?.toFixed(2) ?? '—'}%
                    </Tag>
                    <Tag>回撤: {metrics.max_drawdown?.toFixed(2)}%</Tag>
                    <Tooltip title={metrics.one_hand_return_basis === 'entry_margin'
                      ? '各笔单手净利润 ÷ 对应单手开仓保证金 × 100%，再累计；扣除开平仓手续费，不计复利。'
                      : metrics.one_hand_return_basis === 'entry_notional'
                        ? '股票按全额开仓本金计算，累计各笔已平仓收益率。'
                        : '旧记录的单手收益率采用旧口径，请重新回测以获取保证金口径。'}>
                      <Tag style={{ color: valueColor(metrics.one_hand_profit_pct) }}>
                        单手收益率{metrics.one_hand_return_basis === 'entry_margin' ? '（保证金）' : metrics.one_hand_return_basis === 'entry_notional' ? '（全额本金）' : '（旧口径）'}: {formatPercent(metrics.one_hand_profit_pct)}
                      </Tag>
                    </Tooltip>
                    <Tooltip title="各笔已平仓交易净利润按该笔累计开仓手数折算后相加，扣除开平仓手续费。">
                      <Tag style={{ color: valueColor(metrics.one_hand_net_profit) }}>
                        单手盈利金额: {formatNumber(metrics.one_hand_net_profit)} 元
                      </Tag>
                    </Tooltip>
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
