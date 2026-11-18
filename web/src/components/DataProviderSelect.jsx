import React, { useEffect, useState } from 'react';
import { Alert, Form, Select, Switch } from 'antd';
import axios from '../utils/api.js';

const DataProviderSelect = ({ form, onChange, disabled = false }) => {
    const market = Form.useWatch('market_type', form) || 'futures';
    const provider = Form.useWatch('data_provider', form) || (market === 'stock' ? 'akshare' : 'tqsdk');
    const [status, setStatus] = useState(null);
    useEffect(() => {
        let active = true;
        axios.get('/api/data/providers')
            .then(({ data }) => { if (active) setStatus(data[provider] || null); })
            .catch(() => { if (active) setStatus(null); });
        return () => { active = false; };
    }, [provider]);

    return <>
        <Form.Item name="data_provider" label="行情供应商" initialValue="tqsdk">
            <Select disabled={disabled} onChange={onChange} options={[
                { value: 'akshare', label: market === 'stock' ? '原有来源（东方财富 / 新浪）' : '新浪财经（原有来源）' },
                { value: 'tqsdk', label: '天勤 TqSdk 免费版', disabled: market !== 'futures' },
                { value: 'gm', label: '掘金量化', disabled: market !== 'futures' },
            ]} />
        </Form.Item>
        <Form.Item name="synthesize_60" label="60分钟线按交易时段合成" valuePropName="checked" initialValue={false} extra="使用5分钟行情合成；仅在选择60分钟周期时生效，历史范围受底层数据限制。">
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
        </Form.Item>
        {provider === 'tqsdk' && <Alert
            type={status && (!status.configured || !status.installed) ? 'warning' : 'info'}
            showIcon style={{ marginBottom: 16 }}
            message={status && !status.installed ? '天勤依赖尚未安装' : status && !status.configured ? '天勤账号尚未配置' : '天勤免费滚动行情'}
            description={<>
                {status && !status.configured && <div>请先在本地 .env 中配置快期账号和密码。</div>}
                <div>仅支持期货近期行情，最多 10000 根 K 线；周线由日线合成。结果标明实际日期范围。</div>
            </>}
        />}
        {provider === 'gm' && <Alert type={status && (!status.configured || !status.installed) ? 'warning' : 'info'}
            showIcon style={{ marginBottom: 16 }}
            message={status && !status.installed ? '掘金 SDK 尚未安装' : status && !status.configured ? '掘金 Token 尚未配置' : '掘金量化行情'}
            description="需启动并登录掘金终端；支持期货主力连续和加权指数，行情范围由账号权限决定。具体合约多选当前使用天勤。" />}
    </>;
};

export default DataProviderSelect;
