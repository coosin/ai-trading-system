import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuthStore, useSystemStore, useThemeStyles } from './store';
import Login from './components/Login';
import SystemStatus from './components/SystemStatus';
import TradingStrategies from './components/TradingStrategies';
import PerformanceMetrics from './components/PerformanceMetrics';
import MarketAnalysis from './components/MarketAnalysis';
import RiskManagement from './components/RiskManagement';
import TradeHistory from './components/TradeHistory';
import BacktestSystem from './components/BacktestSystem';
import AIStrategyGenerator from './components/AIStrategyGenerator';
import AccountManagement from './components/AccountManagement';
import Notifications from './components/Notifications';
import Settings from './components/Settings';
import APIDocs from './components/APIDocs';
import DataExportImport from './components/DataExportImport';
import ControlCenter from './components/ControlCenter';
import AIInteraction from './components/AIInteraction';
import RealTimeMarket from './components/RealTimeMarket';
import ExternalData from './components/ExternalData';
import AIMarketAnalysis from './components/AIMarketAnalysis';
import ThemeToggle from './components/ThemeToggle';

function App() {
  const [activeView, setActiveView] = useState('control');
  const { isAuthenticated, initialize: initializeAuth, logout } = useAuthStore();
  const { status, fetchStatus, isLoading: loading, theme } = useSystemStore();
  const styles = useThemeStyles();

  // 初始化认证状态
  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  // 获取系统状态
  useEffect(() => {
    if (isAuthenticated) {
      fetchStatus();
      const interval = setInterval(fetchStatus, 5000);
      return () => clearInterval(interval);
    }
  }, [isAuthenticated, fetchStatus]);

  // 如果未认证，显示登录页面
  if (!isAuthenticated) {
    return <Login />;
  }

  const renderView = () => {
    switch (activeView) {
      case 'control':
        return <ControlCenter />;
      case 'ai-interaction':
        return <AIInteraction />;
      case 'real-time-market':
        return <RealTimeMarket />;
      case 'external-data':
        return <ExternalData />;
      case 'ai-market-analysis':
        return <AIMarketAnalysis />;
      case 'status':
        return <SystemStatus status={status} loading={loading} />;
      case 'strategies':
        return <TradingStrategies />;
      case 'performance':
        return <PerformanceMetrics />;
      case 'market':
        return <MarketAnalysis />;
      case 'risk':
        return <RiskManagement />;
      case 'history':
        return <TradeHistory />;
      case 'backtest':
        return <BacktestSystem />;
      case 'ai-strategy':
        return <AIStrategyGenerator />;
      case 'accounts':
        return <AccountManagement />;
      case 'notifications':
        return <Notifications />;
      case 'settings':
        return <Settings />;
      case 'api-docs':
        return <APIDocs />;
      case 'data':
        return <DataExportImport />;
      default:
        return <ControlCenter />;
    }
  };

  const handleLogout = () => {
    logout();
  };

  return (
    <div style={styles.container}>
      <div style={{ display: 'flex', minHeight: '100vh' }}>
        {/* Sidebar */}
        <div style={{
          width: '250px',
          ...styles.sidebar,
          padding: '20px',
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column'
        }}>
          <h1 style={{ fontSize: '18px', marginBottom: '30px' }}>智能交易系统</h1>
          <nav style={{ flex: 1 }}>
            <ul style={{ listStyle: 'none', padding: 0 }}>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('control')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'control' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  总控中心
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('status')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'status' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  系统状态
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('strategies')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'strategies' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  交易策略
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('performance')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'performance' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  性能指标
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('market')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'market' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  市场分析
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('real-time-market')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'real-time-market' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  实时行情跟踪
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('risk')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'risk' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  风险管理
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('history')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'history' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  交易历史
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('backtest')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'backtest' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  回测系统
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('ai-strategy')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'ai-strategy' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  智能策略生成
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('ai-interaction')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'ai-interaction' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  AI交互中心
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('accounts')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'accounts' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  多账户管理
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('notifications')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'notifications' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  通知系统
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('settings')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'settings' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  系统设置
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('api-docs')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'api-docs' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  API文档
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('data')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'data' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  数据导出/导入
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('external-data')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'external-data' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  外部数据源
                </button>
              </li>
              <li style={{ marginBottom: '15px' }}>
                <button
                  onClick={() => setActiveView('ai-market-analysis')}
                  style={{
                    width: '100%',
                    padding: '10px',
                    backgroundColor: activeView === 'ai-market-analysis' ? (styles.sidebar.backgroundColor === '#2d2d2d' ? '#3a3a3a' : '#3498db') : 'transparent',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  AI市场分析
                </button>
              </li>
            </ul>
          </nav>
          
          {/* 登出按钮 */}
          <div style={{ borderTop: `1px solid ${styles.sidebar.backgroundColor === '#2d2d2d' ? '#444' : '#2980b9'}`, paddingTop: '20px' }}>
            <button
              onClick={handleLogout}
              style={{
                width: '100%',
                padding: '10px',
                backgroundColor: '#e74c3c',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                textAlign: 'center'
              }}
            >
              退出登录
            </button>
          </div>
        </div>

        {/* Main Content */}
        <div style={{
          flex: 1,
          padding: '20px',
          overflowY: 'auto',
          ...styles.content
        }}>
          <header style={{ 
            marginBottom: '30px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <div>
              <h1>全智能量化交易系统</h1>
              <p>实时监控和管理您的交易策略</p>
            </div>
            <ThemeToggle />
          </header>
          {renderView()}
        </div>
      </div>
    </div>
  );
}

export default App;