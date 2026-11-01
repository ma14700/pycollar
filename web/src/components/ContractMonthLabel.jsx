import React from 'react';
import { Switch, Tooltip } from 'antd';
import { useBacktest } from '../context/BacktestContext';

export default function ContractMonthLabel() {
    const { only159Contracts, setOnly159Contracts } = useBacktest();
    return <span style={{ display: 'inline-flex', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        具体合约（可多选）
        <Tooltip title="开启时下拉框只展示01、05、09月合约；关闭展示全部合约，已选合约保持不变。">
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                <Switch size="small" aria-label="仅展示01、05、09月合约" checked={only159Contracts} onChange={setOnly159Contracts} />
                01/05/09
            </span>
        </Tooltip>
    </span>;
}
