import React from 'react';
import { Alert, Card, Statistic, Row, Col, Tooltip } from 'antd';
import { 
  WalletOutlined, AccountBookOutlined, SafetyCertificateOutlined, 
  FallOutlined, CodeOutlined, RiseOutlined, FileTextOutlined, 
  ThunderboltOutlined, TransactionOutlined, PercentageOutlined 
} from '@ant-design/icons';
import { getValueColor } from '../utils';
import { accountReturn } from '../utils/contractEstimate';

const MetricsPanel = ({ metrics }) => {
    if (!metrics) return null;

    const verified = metrics.calculation_version >= 2;
    const marginReturn = metrics.one_hand_return_basis === 'entry_margin';
    const stockReturn = metrics.one_hand_return_basis === 'entry_notional';

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
      { key: '3', metric: verified ? '夏普比率（年化）' : '夏普比率（旧口径）', value: toNumber(metrics.sharpe_ratio) === null ? '—' : toNumber(metrics.sharpe_ratio).toFixed(4), tip: '按账户日收益计算，日线及分钟线年化因子 252，周线为 52；无风险收益率为 0，收益波动不足时不计算', icon: <SafetyCertificateOutlined />, color: '#faad14', bg: '#fffbe6' },
      { key: '4', metric: '最大回撤', tip: '账户权益相对历史峰值的最大跌幅，包含初始资金基准；按 K 线收盘采样，不是盘中最大回撤', value: fmtPct(metrics.max_drawdown), icon: <FallOutlined />, color: '#52c41a', bg: '#f6ffed' },
      { key: '5', metric: verified ? '已平仓交易次数' : '总交易次数（旧口径）', tip: '完整持仓从开仓到最终平仓计一笔；部分平仓不是独立的一笔', value: metrics.total_trades ?? '—', icon: <CodeOutlined />, color: '#1890ff', bg: '#e6f7ff' },
      { key: '6', metric: '胜率', tip: '净利润大于 0 的已平仓笔数 ÷ 全部已平仓笔数；持平交易进入分母，未平仓不进入', value: fmtPct(metrics.win_rate), icon: <RiseOutlined />, color: '#cf1322', bg: '#fff1f0' },
      { key: '7', metric: '最大实际持仓', tip: '回测实际持仓手数的最大绝对值；没有成交时为 0', value: metrics.used_size ?? '—', icon: <FileTextOutlined />, color: '#595959', bg: '#fafafa' },
      { key: '8', metric: '最大资金占用率', tip: '期货按开仓均价冻结的保证金 ÷ 当时账户权益；股票按持仓市值 ÷ 权益。按 K 线收盘采样', value: fmtPct(metrics.max_capital_usage), icon: <ThunderboltOutlined />, color: '#fa8c16', bg: '#fff7e6' },
      { key: '9', metric: '单手累计净利润', tip: '每笔已平仓交易净利润 ÷ 该笔累计开仓手数，再求和；扣除开平仓手续费。动态手数时不等于账户净利除以最大持仓', value: fmt(metrics.one_hand_net_profit), icon: <TransactionOutlined />, color: getValueColor(metrics.one_hand_net_profit), bg: '#e6fffb', isPnl: true },
      { key: '10', metric: '最大净盈利点', tip: '每笔净利润 ÷（累计开仓手数 × 合约乘数）的最大正值；没有盈利交易时为 0', value: fmt(metrics.max_profit_points), icon: <RiseOutlined />, color: '#f5222d', bg: '#fff1f0' },
      { key: '11', metric: '最大净亏损点', tip: '每笔净利润 ÷（累计开仓手数 × 合约乘数）的最小负值；没有亏损交易时为 0', value: fmt(metrics.max_loss_points), icon: <FallOutlined />, color: '#2f54eb', bg: '#f0f5ff' },
      { key: '12', metric: marginReturn ? '单手累计收益率（保证金）' : stockReturn ? '单手累计收益率（全额本金）' : verified ? '单手累计收益率（旧名义口径）' : '单手收益率（旧口径）', tip: marginReturn ? '每笔单手净利润 ÷ 对应单手开仓保证金 × 100%，再累计。开仓保证金 = 实际开仓价 × 合约乘数 × 配置保证金率；净利润扣除开平仓手续费。加仓按各次实际开仓金额加权，不是复利收益率。' : '股票以全额开仓本金为分母；旧记录可能使用名义金额口径，请重新回测。', value: fmtPct(metrics.one_hand_profit_pct), icon: <PercentageOutlined />, color: getValueColor(metrics.one_hand_profit_pct), bg: '#fff0f6', isPnl: true },
      { key: '13', metric: '账户收益率', value: fmtPct(accountReturn(metrics)), tip: '账户净利润 ÷ 初始资金 × 100%；账户权益包含未平仓浮动盈亏', icon: <PercentageOutlined />, color: getValueColor(metrics.net_profit), bg: '#fff0f6' },
      { key: '14', metric: '累计手续费', value: fmt(metrics.total_commission), tip: '所有实际成交的开平仓手续费之和，暂按成交名义金额的 0.01% / 边估算', icon: <AccountBookOutlined />, color: '#595959', bg: '#fafafa' },
    ];

    return (
        <>
        {!verified && <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="此结果使用旧计算口径，请重新运行回测以获得修正后的权益、回撤和单手统计。" />}
        {verified && !marginReturn && !stockReturn && <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="此记录的单手收益率按旧名义金额计算，重新回测后将按开仓保证金计算。" />}
        {verified && <div style={{ color: '#64748b', fontSize: 12, marginBottom: 16 }}>手续费统一按成交额 0.01% / 边估算，未计滑点；期货按开仓均价冻结保证金并按 K 线盯市，未模拟保证金率调整及强平。旧记录需重新回测。</div>}
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
                            title={<Tooltip title={item.tip}><span style={{ fontSize: '12px', color: '#666', display: 'flex', alignItems: 'center', gap: '6px' }}>{item.icon} {item.metric}</span></Tooltip>}
                            value={item.value}
                            valueStyle={{ color: item.color, fontSize: '18px', fontWeight: 'bold' }}
                        />
                    </Card>
                </Col>
            ))}
        </Row>
        </>
    );
};

export default MetricsPanel;
