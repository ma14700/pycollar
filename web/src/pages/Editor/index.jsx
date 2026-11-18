import React, { useState, useEffect, useRef } from 'react';
import { Alert, Button, Card, Select, Space, message } from 'antd';
import { CodeOutlined, ReloadOutlined } from '@ant-design/icons';
import Editor from '@monaco-editor/react';
import axios from '../../utils/api.js';

const DEFAULT_MODULES = [
  { key: 'strategy.py', label: '主策略模块 (strategy.py)' },
  { key: 'strategy_dkx.py', label: 'DKX 多空线策略 (strategy_dkx.py)' },
  { key: 'strategy_rr3.py', label: '20/55 ATR 盈亏比策略 (strategy_rr3.py)' },
  { key: 'strategy_base.py', label: '策略基类 (strategy_base.py)' },
  { key: 'ma5_55_cross.py', label: '5/55 均线交叉策略 (ma5_55_cross.py)' },
  { key: 'ma20_60_cross.py', label: '20/60 均线交叉策略 (ma20_60_cross.py)' },
];

const EditorPage = () => {
  const [selectedModule, setSelectedModule] = useState('strategy.py');
  const [modules, setModules] = useState(DEFAULT_MODULES);
  const [strategyCode, setStrategyCode] = useState('');
  const [loadingCode, setLoadingCode] = useState(false);
  const requestController = useRef(null);

  const fetchStrategyCode = (moduleName = selectedModule) => {
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    setLoadingCode(true);
    axios.get('/api/strategy/code', { params: { module: moduleName }, signal: controller.signal })
      .then(res => {
        if (controller.signal.aborted) return;
        setStrategyCode(res.data.code || '');
        if (Array.isArray(res.data.modules) && res.data.modules.length) {
          setModules(res.data.modules);
        }
      })
      .catch(error => {
        if (!axios.isCancel(error) && !controller.signal.aborted) {
          message.error(error.response?.data?.detail || '获取策略代码失败');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoadingCode(false);
        }
      });
  };

  useEffect(() => {
    fetchStrategyCode(selectedModule);
    return () => requestController.current?.abort();
  }, [selectedModule]);

  return (
    <div style={{ height: '100%', padding: '24px', display: 'flex', flexDirection: 'column', gap: '12px', boxSizing: 'border-box' }}>
      <Alert
        type="info"
        showIcon
        message="当前页面为只读策略源码预览"
        description="为保证并发回测与扫描期间策略类稳定，平台已禁用网页端热更新。可通过右上角切换查看各策略模块源码；如需修改，请编辑本地对应文件并重启后端服务。"
      />
      <Card
        title={<span><CodeOutlined /> 策略源码 (server/core/{selectedModule})</span>}
        extra={
          <Space>
            <Select
              aria-label="选择策略模块"
              value={selectedModule}
              onChange={setSelectedModule}
              style={{ width: 280 }}
              options={modules.map(item => ({ value: item.key, label: item.label }))}
            />
            <Button onClick={() => fetchStrategyCode(selectedModule)} loading={loadingCode} icon={<ReloadOutlined />}>
              刷新
            </Button>
          </Space>
        }
        variant="borderless"
        style={{ flex: 1, minHeight: 0 }}
        styles={{ body: { height: 'calc(100% - 57px)', padding: 0 } }}
      >
        <Editor
          height="100%"
          defaultLanguage="python"
          value={strategyCode}
          theme="vs-dark"
          options={{
            readOnly: true,
            domReadOnly: true,
            minimap: { enabled: false },
            fontSize: 14,
            scrollBeyondLastLine: false,
          }}
        />
      </Card>
    </div>
  );
};

export default EditorPage;
