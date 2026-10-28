import React from 'react';
import { Alert } from 'antd';

const DataSourceInfo = ({ info }) => info ? <Alert
    type="info" showIcon
    message={`行情来源：${info.provider_name || info.provider}${info.resolved_symbol ? ` · ${info.resolved_symbol}` : ''}`}
    description={<>
        <div>{info.start} ～ {info.end} · {info.bars} 根 K 线 · {info.contract_month ? `具体合约 ${info.contract_month}` : info.data_source === 'weighted' ? '加权指数' : '主力连续 / 合约行情'}</div>
        {info.cache_status && <div>{info.cache_status === 'hit' ? '本地缓存命中，本次未请求第三方行情' : `${info.cache_status === 'partial' ? '本地覆盖不足' : '首次获取'}，已拉取并缓存 ${info.cache_downloaded_bars || 0} 根已完成 K 线`}</div>}
        {info.note && <div>{info.note}</div>}
    </>}
/> : null;

export default DataSourceInfo;
