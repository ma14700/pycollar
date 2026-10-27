import React, { useMemo } from 'react';
import { Card, Empty, Table, Tag, Typography } from 'antd';
import { useBacktest } from '../../context/BacktestContext';
import { parseLogItem } from '../../utils';

const { Text } = Typography;

const LogsPage = () => {
  const { results } = useBacktest();

  const logsData = useMemo(() => {
    const items = results?.isBatch
      ? results.items.filter(item => item.success).flatMap(item =>
          (item.data?.logs || []).map(entry => ({ entry, symbol: item.symbol })))
      : (results?.logs || []).map(entry => ({ entry, symbol: '' }));
    return items.map(({ entry, symbol }, index) => {
      const parsed = parseLogItem(entry, index);
      const legacyProfit = parsed.content.match(/净利\s+([-\d.]+)/);
      return { ...parsed, symbol, netProfit: parsed.pnl ?? (legacyProfit ? Number(legacyProfit[1]) : null) };
    }).reverse();
  }, [results]);

  const columns = [
    ...(results?.isBatch ? [{ title: '品种', dataIndex: 'symbol', width: 100 }] : []),
    {
      title: '时间',
      dataIndex: 'date',
      width: 180,
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 100,
      render: (type, record) => {
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
          profit: '结算',
          loss: '止损',
          signal: '信号',
          warning: '警告',
          system: '系统',
          info: '信息'
        };
        return <Tag color={colors[type] || 'default'}>{record.action || labels[type] || '信息'}</Tag>;
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
