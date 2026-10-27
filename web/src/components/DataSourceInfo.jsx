import React from 'react';
import { Alert } from 'antd';

const DataSourceInfo = ({ info }) => info ? <Alert
    type="info" showIcon
    message={`行情来源：${info.provider_name || info.provider}${info.resolved_symbol ? ` · ${info.resolved_symbol}` : ''}`}
    description={<>
        <div>{info.start} ～ {info.end} · {info.bars} 根 K 线 · {info.data_source === 'weighted' ? '加权指数' : '主力连续 / 合约行情'}</div>
        {info.note && <div>{info.note}</div>}
    </>}
/> : null;

export default DataSourceInfo;
