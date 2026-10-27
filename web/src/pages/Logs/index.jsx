import React from 'react';
import { Card, Empty, Table, Tag } from 'antd';
import { useBacktest } from '../../context/BacktestContext';
import { getValueColor, parseLogItem } from '../../utils';

const logTypes = {
  buy: { text: '买入', color: 'volcano' },
  sell: { text: '卖出', color: 'green' },
  profit: { text: '结算', color: 'gold' },
  signal: { text: '信号', color: 'blue' },
  system: { text: '系统', color: 'default' },
  info: { text: '信息', color: 'default' },
};

const LogsPage = () => {
  const { results } = useBacktest();
  const logs = Array.isArray(results?.logs) ? results.logs.map(parseLogItem) : [];

  return (
    <div style={{ padding: '24px' }}>
      <Card title="交易日志">
        {logs.length ? (
          <Table
            rowKey="key"
            dataSource={logs}
            columns={[
              { title: '时间', dataIndex: 'date', width: 180 },
              {
                title: '类型', dataIndex: 'type', width: 100,
                filters: Object.entries(logTypes).map(([value, { text }]) => ({ text, value })),
                onFilter: (value, record) => record.type === value,
                render: (type, record) => (
                  <Tag color={logTypes[type].color}>{record.action || logTypes[type].text}</Tag>
                ),
              },
              { title: '内容', dataIndex: 'content' },
              {
                title: '净利', dataIndex: 'pnl', width: 120, align: 'right',
                render: (value) => value === null ? '-' : (
                  <span style={{ color: getValueColor(value) }}>{value.toFixed(2)}</span>
                ),
              },
            ]}
            pagination={{ defaultPageSize: 50, showSizeChanger: true }}
            scroll={{ x: 900 }}
            size="small"
          />
        ) : <Empty description="暂无交易日志，请先运行一次回测" />}
      </Card>
    </div>
  );
};

export default LogsPage;
