import React from 'react';
import { Col, Form, InputNumber, Row } from 'antd';

export default function PointExitInputs() {
    return <Row gutter={12}>
        {[['take_profit_points', '盈利多少点平仓'], ['stop_loss_points', '亏损多少点平仓']].map(([name, label]) =>
            <Col span={12} key={name}><Form.Item name={name} label={label} preserve={false}
                tooltip="相对实际开仓价的价格点数，触及后平掉全部持仓。"
                rules={[{ required: true, message: `请输入${label}` }, { type: 'number', min: 0.00000001, message: '点数须大于0' }]}>
                <InputNumber min={0.01} style={{ width: '100%' }} />
            </Form.Item></Col>)}
    </Row>;
}
