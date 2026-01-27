import React from 'react';
import { Layout, Menu } from 'antd';
import { 
  DashboardOutlined, 
  LineChartOutlined, 
  CodeOutlined, 
  FileTextOutlined, 
  HistoryOutlined,
  BulbOutlined
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';

const { Header, Content, Sider } = Layout;

const MainLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();

  // 映射路径到 Menu Key
  const getSelectedKey = () => {
    const path = location.pathname;
    if (path === '/' || path === '/backtest') return '1';
    if (path === '/tomorrow-strategy') return '5';
    if (path === '/editor') return '2';
    if (path === '/logs') return '3';
    if (path === '/history') return '4';
    return '1';
  };

  const handleMenuSelect = ({ key }) => {
    switch (key) {
      case '1':
        navigate('/backtest');
        break;
      case '2':
        navigate('/editor');
        break;
      case '3':
        navigate('/logs');
        break;
      case '4':
        navigate('/history');
        break;
      case '5':
        navigate('/tomorrow-strategy');
        break;
      default:
        navigate('/backtest');
    }
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ 
        background: 'linear-gradient(90deg, #001529 0%, #003a8c 100%)', 
        padding: '0 24px', 
        color: 'white', 
        display: 'flex', 
        alignItems: 'center', 
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        zIndex: 10,
        height: '64px'
      }}>
        <DashboardOutlined style={{ fontSize: '24px', marginRight: '12px', color: '#1890ff' }} />
        <div style={{ fontSize: '20px', fontWeight: 'bold', letterSpacing: '1px' }}>
          AI 量化策略回测平台
        </div>
      </Header>
      <Content style={{ padding: '0', backgroundColor: '#f0f2f5', overflow: 'hidden' }}>
        <Layout style={{ height: 'calc(100vh - 64px)', background: '#f0f2f5' }}>
            <Sider width={220} style={{ background: '#001529', height: '100%', overflowY: 'auto' }}>
                <Menu
                    mode="inline"
                    selectedKeys={[getSelectedKey()]}
                    style={{ height: '100%', borderRight: 0 }}
                    theme="dark"
                    onSelect={handleMenuSelect}
                    items={[
                        { key: '1', icon: <LineChartOutlined />, label: '策略回测' },
                        { key: '5', icon: <BulbOutlined />, label: '明日策略' },
                        { key: '2', icon: <CodeOutlined />, label: '代码编辑' },
                        { key: '3', icon: <FileTextOutlined />, label: '交易日志' },
                        { key: '4', icon: <HistoryOutlined />, label: '回测记录' }
                    ]}
                />
            </Sider>
            <Content style={{ height: '100%', overflowY: 'auto', backgroundColor: '#f0f2f5' }}>
                <Outlet />
            </Content>
        </Layout>
      </Content>
    </Layout>
  );
};

export default MainLayout;
