import React from 'react';
import { Alert, Col, Form, Input, Row, Switch } from 'antd';

export default function RiskRewardInputs({ isRR3Strategy }) {
    return (
                            <>
                                {isRR3Strategy && <>
                                    <Alert type="info" showIcon style={{ marginBottom: 16 }} message="20/55 交叉入场 · ATR 风险止盈止损"
                                        description="使用所选周期；信号时冻结 ATR，按实际开仓价设置止损与止盈。默认止损 2×ATR、止盈 3R，全仓退出后等下一次交叉。同根触及两端按止损优先；跳空按可成交价处理，实际收益包含费用。" />
                                    <Form.Item name="exit_on_opposite_cross" label="反向交叉提前离场" valuePropName="checked"
                                        tooltip="关闭：只按止盈止损退出；开启：反向交叉按平仓 K 线配置提前平仓，不反手。等待期间止盈止损继续生效。回测结束会强平。">
                                        <Switch checkedChildren="开启" unCheckedChildren="关闭" />
                                    </Form.Item>
                                </>}
                                <Row gutter={16}>
                                    <Col span={12}>
                                        <Form.Item name="risk_reward_ratio" label="止盈倍数（赚 / 亏）" tooltip="止盈距离 / 止损距离">
                                            <Input type="number" step="0.1" />
                                        </Form.Item>
                                    </Col>
                                    <Col span={12}>
                                        <Form.Item name="atr_multiplier" label="止损ATR倍数" tooltip="止损距离 = ATR * 倍数">
                                            <Input type="number" step="0.1" />
                                        </Form.Item>
                                    </Col>
                                </Row>
                                <Row gutter={16}>
                                    <Col span={12}>
                                        <Form.Item name="atr_period" label="ATR周期">
                                            <Input type="number" />
                                        </Form.Item>
                                    </Col>
                                </Row>
                            </>
    );
}
