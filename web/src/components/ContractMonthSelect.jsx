import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, Form, Select } from 'antd';
import axios from 'axios';

// Shared contract catalog and stale-request protection for analysis pages.
export default function ContractMonthSelect({ form, symbolsField = 'symbol', disabled = false }) {
    const market = Form.useWatch('market_type', form) || 'futures';
    const selection = Form.useWatch(symbolsField, form);
    const products = Array.isArray(selection) ? selection : selection ? [selection] : [];
    const product = market === 'futures' && products.length === 1 ? products[0] : null;
    const months = Form.useWatch('contract_month', form) || [];
    const [options, setOptions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [reload, setReload] = useState(0);
    const previous = useRef(product);
    const cache = useRef(new Map());

    useEffect(() => {
        if (previous.current !== product) form.setFieldValue('contract_month', []);
        previous.current = product;
        setOptions([]); setError(''); setLoading(false);
        if (!product) return;
        if (cache.current.has(product)) { setOptions(cache.current.get(product)); return; }
        const controller = new AbortController();
        setLoading(true);
        axios.get('http://localhost:8000/api/futures/contracts', { params: { symbol: product }, signal: controller.signal })
            .then(({ data }) => {
                if (controller.signal.aborted) return;
                cache.current.set(product, data.contracts || []);
                setOptions(data.contracts || []);
            })
            .catch(failure => { if (!controller.signal.aborted) setError(failure.response?.data?.detail || '合约加载失败，请重试'); })
            .finally(() => { if (!controller.signal.aborted) setLoading(false); });
        return () => controller.abort();
    }, [product, reload, form]);

    if (market !== 'futures') return null;
    return <>
        <Form.Item name="contract_month" label="具体合约（可多选）" initialValue={[]}
            extra={!product ? '先选择一个交易品种，再选择具体合约。' : error ? <span style={{ color: '#ff4d4f' }}>{error}<Button type="link" size="small" onClick={() => { cache.current.delete(product); setReload(value => value + 1); }}>重试</Button></span> : '清空后恢复品种行情；选中后使用天勤具体合约数据。'}>
            <Select mode="multiple" showSearch optionFilterProp="label" allowClear maxTagCount="responsive"
                disabled={!product || disabled} loading={loading} options={options} placeholder="选择具体合约"
                notFoundContent={loading ? '加载合约中…' : error ? '合约加载失败' : '暂无可用合约'}
                onChange={value => { if (value.length) form.setFieldsValue({ data_provider: 'tqsdk', data_source: 'main' }); }} />
        </Form.Item>
        {months.length > 0 && product && <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message={`已选择 ${months.length} 个具体合约，按合约分别分析`} />}
    </>;
}
