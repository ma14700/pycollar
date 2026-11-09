import React from 'react';
import { Card, Table, Tag, Space, Typography } from 'antd';

const reasons = { take_profit: '止盈', stop_loss: '止损', opposite_cross: '反向交叉', end_of_backtest: '结束强平' };
const number = value => Number(value).toFixed(2);

export default function RiskRewardDetails({ results }) {
    if (results.strategy_info?.name !== 'MA20MA55RR3Strategy') return null;
    const trades = results.risk_reward_trades || [];
    const params = results.strategy_info.params;
    const averageR = trades.length ? trades.reduce((sum, row) => sum + row.net_r, 0) / trades.length : null;
    const columns = [
        { title: '开仓时间', dataIndex: 'entry_date', width: 170 },
        { title: '方向', dataIndex: 'direction', width: 75, render: value => value > 0 ? '做多' : '做空' },
        { title: '开仓价', dataIndex: 'entry_price', width: 100, render: number },
        { title: '1R（点）', dataIndex: 'risk_points', width: 100, render: number },
        { title: '止损价', dataIndex: 'stop_price', width: 100, render: number },
        { title: '止盈价', dataIndex: 'target_price', width: 100, render: number },
        { title: '平仓时间', dataIndex: 'exit_date', width: 170 },
        { title: '平仓价', dataIndex: 'exit_price', width: 100, render: number },
        { title: '离场原因', dataIndex: 'exit_reason', width: 110, render: value => reasons[value] || value },
        { title: '净收益（元）', dataIndex: 'net_profit', width: 120, render: number },
        { title: '净收益 R', dataIndex: 'net_r', width: 110,
            render: value => <Tag color={value >= 0 ? 'green' : 'red'}>{number(value)}R</Tag> },
    ];
    return <Card title="收益风险明细" variant="borderless" style={{ minWidth: 0 }}>
        <Space wrap style={{ marginBottom: 12 }}>
            <Tag color="blue">目标 {params.risk_reward_ratio ?? 3}R</Tag>
            <Tag>平均净收益 {averageR === null ? '—' : `${number(averageR)}R`}</Tag>
            {Object.entries(reasons).map(([key, label]) => <Tag key={key}>{label} {trades.filter(row => row.exit_reason === key).length} 笔</Tag>)}
        </Space>
        <Typography.Paragraph type="secondary">
            1R = 入场时固定的止损点数 × 手数 × 合约乘数；净收益 R 已扣手续费。
            跳空、提前离场和结束强平会使实际收益偏离目标比例。仅统计已平仓交易。
        </Typography.Paragraph>
        <Table size="small" columns={columns} dataSource={trades} rowKey={(_, index) => index}
            scroll={{ x: 1255 }} pagination={{ pageSize: 10, showSizeChanger: false }} />
    </Card>;
}
