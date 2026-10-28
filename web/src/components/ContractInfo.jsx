import React from 'react';
import { Form, Input, Row, Col, Tooltip } from 'antd';
import { contractEstimate } from '../utils/contractEstimate';

const ContractInfo = ({ form, quoteInfo }) => {
    const initialCash = Form.useWatch('initial_cash', form);
    const contractMultiplier = Form.useWatch('contract_multiplier', form);
    const marginRate = Form.useWatch('margin_rate', form);
    const marketType = Form.useWatch('market_type', form);
    
    if (!quoteInfo) return null;

    const estimate = contractEstimate({ price: quoteInfo.price, multiplier: contractMultiplier,
        initialCash, marginRate, marketType });
    const display = (value, digits = 2) => value === undefined ? '—' : value.toFixed(digits);
    
    return (
        <div style={{ background: '#fafafa', padding: '12px', borderRadius: '6px', marginBottom: '24px', border: '1px solid #f0f0f0' }}>
            <div style={{ fontSize: '12px', color: '#888', marginBottom: '8px' }}>合约详情参考 ({quoteInfo.date})</div>
            <Row gutter={[8, 8]}>
                <Col span={12}>
                    <div style={{ fontSize: '12px', color: '#666' }}>行情价格（开仓参考）</div>
                    <Tooltip title="数据源返回的最近行情价，保证金率不改变价格。实际回测按历史信号及开平仓 K 线设置成交，与这里的当前行情参考价无关。">
                        <Input 
                            size="small" 
                            value={display(estimate?.price)}
                            disabled
                            style={{ width: '100px', fontWeight: 'bold', color: '#595959', cursor: 'not-allowed', backgroundColor: '#f5f5f5' }} 
                        />
                    </Tooltip>
                </Col>
                <Col span={12}>
                    <div style={{ fontSize: '12px', color: '#666' }}>1点价值</div>
                    <div>{display(estimate?.multiplier, 0)} 元 / 手</div>
                </Col>
                <Col span={12}>
                    <div style={{ fontSize: '12px', color: '#666' }}>一手合约价值</div>
                    <div>{estimate ? `${(estimate.notional / 10000).toFixed(2)} 万` : '—'}</div>
                </Col>
                <Col span={12}>
                    <div style={{ fontSize: '12px', color: '#666' }}>{marketType === 'stock' ? '理论可买（全额资金）' : `理论可开（${estimate ? (estimate.marginRate * 100).toFixed(0) : '—'}%保证金）`}</div>
                    <Tooltip title="初始资金 ÷（参考价 × 合约乘数 × 保证金率＋估算开仓手续费），向下取整；股票全额资金。手续费暂按成交额的 0.01% / 边估算，实际历史价格和可用资金会影响成交。">
                        <div style={{ color: '#1890ff', fontWeight: 'bold' }}>{estimate?.maxHands ?? '—'} 手</div>
                    </Tooltip>
                </Col>
            </Row>
        </div>
    );
};

export default ContractInfo;
