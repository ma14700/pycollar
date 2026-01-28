import React, { useMemo } from 'react';
import { Card, Empty, Table, Tag, Typography } from 'antd';
import { useBacktest } from '../../context/BacktestContext';

const { Text } = Typography;

const LogsPage = () => {
  const { results } = useBacktest();

  const logsData = useMemo(() => {
    if (!results || !results.logs || results.logs.length === 0) {
      return [];
    }
    
    // 解析日志字符串
    return results.logs.map((log, index) => {
      // 格式通常为: "YYYY-MM-DD HH:MM:SS, message"
      const parts = log.split(',', 1);
      if (parts.length > 0) {
        const date = parts[0];
        const content = log.substring(date.length + 1).trim();
        
        let type = 'info';
        let netProfit = null;
        
        if (content.includes('买入') || content.includes('做多')) type = 'buy';
        if (content.includes('卖出') || content.includes('做空') || content.includes('平仓')) type = 'sell';
        if (content.includes('止盈')) type = 'profit';
        if (content.includes('止损')) type = 'loss';
        if (content.includes('金叉') || content.includes('死叉')) type = 'signal';
        if (content.includes('警告') || content.includes('Error')) type = 'warning';
        
        // 提取净利润
        if (content.includes('净利')) {
             const match = content.match(/净利\s*([-\d.]+)/);
             if (match && match[1]) {
                 netProfit = parseFloat(match[1]);
             }
        }
        
        return {
          key: index,
          date,
          content,
          type,
          netProfit
        };
      }
      return { key: index, date: '', content: log, type: 'info', netProfit: null };
    }).reverse(); // 最新的在前面
  }, [results]);

  const columns = [
    {
      title: '时间',
      dataIndex: 'date',
      width: 180,
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 100,
      render: (type) => {
        const colors = {
          buy: 'red',
          sell: 'green',
          profit: 'orange',
          loss: 'blue',
          signal: 'purple',
          warning: 'volcano',
          info: 'default'
        };
        const labels = {
          buy: '买入',
          sell: '卖出',
          profit: '止盈',
          loss: '止损',
          signal: '信号',
          warning: '警告',
          info: '信息'
        };
        return <Tag color={colors[type] || 'default'}>{labels[type] || '信息'}</Tag>;
      }
    },
    {
      title: '内容',
      dataIndex: 'content',
      render: (text, record) => {
         let color = 'inherit';
         let fontWeight = 'normal';
         
         if (record.type === 'buy') {
             color = '#cf1322';
             fontWeight = 'bold';
         }
         if (record.type === 'sell') {
             color = '#389e0d';
             fontWeight = 'bold';
         }
         
         // 高亮价格和成本
         const highlightNumber = (str) => {
             return str.split(/(价格: [\d.]+|成本: [\d.]+|毛利 [-\d.]+|净利 [-\d.]+)/g).map((part, i) => {
                 if (part.match(/价格: [\d.]+|成本: [\d.]+|毛利 [-\d.]+|净利 [-\d.]+/)) {
                     return <span key={i} style={{ fontWeight: 'bold', margin: '0 4px' }}>{part}</span>;
                 }
                 return part;
             });
         };
         
         return <Text style={{ color, fontWeight }}>{highlightNumber(text)}</Text>;
      }
    },
    {
        title: '净利润',
        dataIndex: 'netProfit',
        width: 120,
        render: (text) => {
            if (text === null || text === undefined) return '-';
            const color = text > 0 ? '#cf1322' : (text < 0 ? '#389e0d' : 'inherit');
            return <Text style={{ color, fontWeight: 'bold' }}>{text.toFixed(2)}</Text>;
        }
    }
  ];

  if (!results) {
      return (
        <Card title="交易日志" style={{ margin: 16 }}>
          <Empty description="请先进行回测以查看日志" />
        </Card>
      );
  }

  return (
    <Card title={`交易日志 (共 ${logsData.length} 条)`} style={{ margin: 16 }} bodyStyle={{ padding: 0 }}>
      {logsData.length > 0 ? (
        <Table 
            dataSource={logsData} 
            columns={columns} 
            pagination={{ pageSize: 20, showSizeChanger: true }}
            size="small"
        />
      ) : (
        <Empty description="暂无日志数据" style={{ margin: '32px 0' }} />
      )}
    </Card>
  );
};

export default LogsPage;

