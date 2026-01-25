import React, { useState, useEffect } from 'react';
import { Card, Button, message } from 'antd';
import { CodeOutlined } from '@ant-design/icons';
import Editor from '@monaco-editor/react';
import axios from 'axios';

const EditorPage = () => {
  const [strategyCode, setStrategyCode] = useState('');
  const [savingCode, setSavingCode] = useState(false);

  useEffect(() => {
    fetchStrategyCode();
  }, []);

  const fetchStrategyCode = () => {
      axios.get('http://localhost:8000/api/strategy/code')
        .then(res => {
            setStrategyCode(res.data.code);
        })
        .catch(err => {
            message.error('获取策略代码失败');
        });
  };

  const saveStrategyCode = () => {
      setSavingCode(true);
      axios.post('http://localhost:8000/api/strategy/code', { code: strategyCode })
        .then(res => {
            message.success('策略代码保存成功');
        })
        .catch(err => {
            message.error('保存失败: ' + (err.response?.data?.detail || err.message));
        })
        .finally(() => {
            setSavingCode(false);
        });
  };

  return (
    <div style={{ height: '100%', padding: '24px' }}>
        <Card 
            title={<span><CodeOutlined /> 编辑策略逻辑 (server/core/strategy.py)</span>}
            extra={
                <Button type="primary" onClick={saveStrategyCode} loading={savingCode} icon={<CodeOutlined />}>
                    保存并生效
                </Button>
            }
            variant="borderless"
            style={{ height: '100%' }}
            styles={{ body: { height: 'calc(100% - 60px)', padding: 0 } }}
        >
            <Editor
                height="100%"
                defaultLanguage="python"
                value={strategyCode}
                onChange={(value) => setStrategyCode(value)}
                theme="vs-dark"
                options={{
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
