import React, { useEffect, useState } from 'react';
import { Alert, Form, Select } from 'antd';
import axios from 'axios';

const DataProviderSelect = ({ form, onChange }) => {
    const market = Form.useWatch('market_type', form) || 'futures';
    const provider = Form.useWatch('data_provider', form) || (market === 'stock' ? 'akshare' : 'tqsdk');
    const [status, setStatus] = useState(null);
    useEffect(() => {
        let active = true;
        axios.get('http://localhost:8000/api/data/providers')
            .then(({ data }) => { if (active) setStatus(data.tqsdk); })
            .catch(() => { if (active) setStatus(null); });
        return () => { active = false; };
    }, [provider]);

    return <>
        <Form.Item name="data_provider" label="行情供应商" initialValue="tqsdk">
            <Select onChange={onChange} options={[
                { value: 'akshare', label: market === 'stock' ? '原有来源（东方财富 / 新浪）' : '新浪财经（原有来源）' },
                { value: 'tqsdk', label: '天勤 TqSdk 免费版', disabled: market !== 'futures' },
            ]} />
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
    </>;
};

export default DataProviderSelect;
