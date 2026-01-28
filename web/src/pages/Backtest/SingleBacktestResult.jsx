import React, { useState } from 'react';
import { Card, Radio, Alert, Tag } from 'antd';
import { 
  DashboardOutlined, 
  LineChartOutlined 
} from '@ant-design/icons';
import MetricsPanel from '../../components/MetricsPanel';
import ChartPanel from '../../components/ChartPanel';

const SingleBacktestResult = ({ results }) => {
  const [chartType, setChartType] = useState('line');

  if (!results) return null;

  return (
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
        <MetricsPanel metrics={results.metrics} />
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
            <Radio.Button value="kline"><LineChartOutlined /> K线图</Radio.Button>
            <Radio.Button value="pie"><LineChartOutlined /> 盈亏分布</Radio.Button>
          </Radio.Group>
        }
      >
        <ChartPanel chartType={chartType} results={results} onChartClick={(params) => console.log('Chart clicked:', params)} />
      </Card>
    </div>
  );
};

export default SingleBacktestResult;
