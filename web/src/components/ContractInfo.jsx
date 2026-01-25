import React from 'react';
import { Form, Input, Row, Col, Tooltip } from 'antd';

const ContractInfo = ({ form, quoteInfo }) => {
    const initialCash = Form.useWatch('initial_cash', form);
    const contractMultiplier = Form.useWatch('contract_multiplier', form);
    const marginRate = Form.useWatch('margin_rate', form);
    
    if (!quoteInfo) return null;

    const currentMultiplier = contractMultiplier || 1;
    const currentInitialCash = parseFloat(initialCash || 0);
    const currentMarginRate = parseFloat(marginRate || 0.12);
    
    // Auto-calculate entry price: Market Price * (1 + Margin Rate)
    const basePrice = quoteInfo.price ? parseFloat(quoteInfo.price) : 0;
    const calcPrice = basePrice * (1 + currentMarginRate);
    
    const oneHandValue = calcPrice * currentMultiplier;
    // Note: Margin calculation typically uses the entry price. 
    // If calcPrice is the simulated entry price, we use it for margin requirement estimation.
    const maxHands = oneHandValue > 0 ? Math.floor(currentInitialCash / (oneHandValue * currentMarginRate)) : 0;
    
    return (
        <div style={{ background: '#fafafa', padding: '12px', borderRadius: '6px', marginBottom: '24px', border: '1px solid #f0f0f0' }}>
            <div style={{ fontSize: '12px', color: '#888', marginBottom: '8px' }}>合约详情参考 ({quoteInfo.date})</div>
            <Row gutter={[8, 8]}>
                <Col span={12}>
                    <div style={{ fontSize: '12px', color: '#666' }}>开仓价格 (参考)</div>
                    <Tooltip title={`计算公式: 当前价格 × (1 + 保证金率 ${currentMarginRate})`}>
                        <Input 
                            size="small" 
                            value={calcPrice.toFixed(2)} 
                            disabled
                            style={{ width: '100px', fontWeight: 'bold', color: '#595959', cursor: 'not-allowed', backgroundColor: '#f5f5f5' }} 
                        />
                    </Tooltip>
                </Col>
                <Col span={12}>
                    <div style={{ fontSize: '12px', color: '#666' }}>1点价值</div>
                    <div>{currentMultiplier} 元</div>
                </Col>
                <Col span={12}>
                    <div style={{ fontSize: '12px', color: '#666' }}>一手合约价值</div>
                    <div>{(oneHandValue / 10000).toFixed(2)} 万</div>
                </Col>
                <Col span={12}>
                    <div style={{ fontSize: '12px', color: '#666' }}>最大可开({(currentMarginRate * 100).toFixed(0)}%保证金)</div>
                    <div style={{ color: '#1890ff', fontWeight: 'bold' }}>{maxHands} 手</div>
                </Col>
            </Row>
        </div>
    );
};

export default ContractInfo;
