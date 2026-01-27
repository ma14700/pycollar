import React from 'react';
import { Card, Statistic, Row, Col } from 'antd';
import { 
  WalletOutlined, AccountBookOutlined, SafetyCertificateOutlined, 
  FallOutlined, CodeOutlined, RiseOutlined, FileTextOutlined, 
  ThunderboltOutlined, TransactionOutlined, PercentageOutlined 
} from '@ant-design/icons';
import { getValueColor } from '../utils';

const MetricsPanel = ({ metrics }) => {
    if (!metrics) return null;

    // Debug log to check what metrics are received
    console.log('MetricsPanel received:', metrics);

    const toNumber = (val) => {
        if (val === undefined || val === null || val === '') return null;
        const num = typeof val === 'string' ? parseFloat(val.replace('%', '')) : Number(val);
        return Number.isFinite(num) ? num : null;
    };

    const fmt = (val) => {
        const num = toNumber(val);
        return num === null ? '-' : num.toFixed(2);
    };

    const fmtPct = (val) => {
        const num = toNumber(val);
        return num === null ? '-' : `${num.toFixed(2)}%`;
    };

    const data = [
      { key: '1', metric: '最终权益', value: fmt(metrics.final_value), icon: <WalletOutlined />, color: '#722ed1', bg: '#f9f0ff' },
      { key: '2', metric: '净利润', value: fmt(metrics.net_profit), icon: <AccountBookOutlined />, color: getValueColor(metrics.net_profit), bg: '#fff1f0', isPnl: true },
      { key: '3', metric: '夏普比率', value: (metrics.sharpe_ratio || 0).toFixed(4), icon: <SafetyCertificateOutlined />, color: '#faad14', bg: '#fffbe6' },
      { key: '4', metric: '最大回撤', value: fmtPct(metrics.max_drawdown), icon: <FallOutlined />, color: '#52c41a', bg: '#f6ffed' },
      { key: '5', metric: '总交易次数', value: metrics.total_trades || 0, icon: <CodeOutlined />, color: '#1890ff', bg: '#e6f7ff' },
      { key: '6', metric: '胜率', value: fmtPct(metrics.win_rate), icon: <RiseOutlined />, color: '#cf1322', bg: '#fff1f0' },
      { key: '7', metric: '使用手数', value: metrics.used_size, icon: <FileTextOutlined />, color: '#595959', bg: '#fafafa' },
      { key: '8', metric: '最大资金使用率', value: fmtPct(metrics.max_capital_usage), icon: <ThunderboltOutlined />, color: '#fa8c16', bg: '#fff7e6' },
      { key: '9', metric: '一手最终赚钱数', value: fmt(metrics.one_hand_net_profit), icon: <TransactionOutlined />, color: getValueColor(metrics.one_hand_net_profit), bg: '#e6fffb', isPnl: true },
      { key: '10', metric: '最大盈利点', value: fmt(metrics.max_profit_points), icon: <RiseOutlined />, color: '#f5222d', bg: '#fff1f0' },
      { key: '11', metric: '最大亏损点', value: fmt(metrics.max_loss_points), icon: <FallOutlined />, color: '#2f54eb', bg: '#f0f5ff' },
      { key: '12', metric: '一手盈利百分数', value: fmtPct(metrics.one_hand_profit_pct), icon: <PercentageOutlined />, color: getValueColor(metrics.one_hand_profit_pct), bg: '#fff0f6', isPnl: true },
    ];

    return (
        <Row gutter={[16, 16]}>
            {data.map(item => (
                <Col xs={12} sm={8} md={6} lg={4} key={item.key}>
                    <Card 
                        variant="borderless" 
                        styles={{ body: { padding: '16px', background: item.bg, borderRadius: '8px', transition: 'all 0.3s' } }}
                        hoverable
                        style={{ height: '100%' }}
                    >
                        <Statistic 
                            title={<span style={{ fontSize: '12px', color: '#666', display: 'flex', alignItems: 'center', gap: '6px' }}>{item.icon} {item.metric}</span>}
                            value={item.value}
                            valueStyle={{ color: item.color, fontSize: '18px', fontWeight: 'bold' }}
                        />
                    </Card>
                </Col>
            ))}
        </Row>
    );
};

export default MetricsPanel;
