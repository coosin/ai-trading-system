import React, { useState, useEffect } from 'react';
import axios from 'axios';
import SystemStatus from './components/SystemStatus';
import TradingStrategies from './components/TradingStrategies';
import PerformanceMetrics from './components/PerformanceMetrics';
import MarketAnalysis from './components/MarketAnalysis';
import RiskManagement from './components/RiskManagement';

function App() {
  const [activeView, setActiveView] = useState('status');
  const [systemStatus, setSystemStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSystemStatus();
    const interval = setInterval(fetchSystemStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchSystemStatus = async () => {
    try {
      const response = await axios.get('/api/v1/status');
      setSystemStatus(response.data);
    } catch (error) {
      console.error('Error fetching system status:', error);
    } finally {
      setLoading(false);
    }
  };

  const renderView = () => {
    switch (activeView) {
      case 'status':
        return <SystemStatus status={systemStatus} loading={loading} />;
      case 'strategies':
        return <TradingStrategies />;
      case 'performance':
        return <PerformanceMetrics />;
      case 'market':
        return <MarketAnalysis />;
      case 'risk':
        return <RiskManagement />;
      default:
        return <SystemStatus status={systemStatus} loading={loading} />;
    }
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Sidebar */}
      <div style={{
        width: '250px',
        backgroundColor: '#2c3e50',
        color: 'white',
        padding: '20px',
        flexShrink: 0
      }}>
        <h1 style={{ fontSize: '18px', marginBottom: '30px' }}>智能交易系统</h1>
        <nav>
          <ul style={{ listStyle: 'none', padding: 0 }}>
            <li style={{ marginBottom: '15px' }}>
              <button
                onClick={() => setActiveView('status')}
                style={{
                  width: '100%',
                  padding: '10px',
                  backgroundColor: activeView === 'status' ? '#3498db' : 'transparent',
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
                  backgroundColor: activeView === 'strategies' ? '#3498db' : 'transparent',
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
                  backgroundColor: activeView === 'performance' ? '#3498db' : 'transparent',
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
                  backgroundColor: activeView === 'market' ? '#3498db' : 'transparent',
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
                onClick={() => setActiveView('risk')}
                style={{
                  width: '100%',
                  padding: '10px',
                  backgroundColor: activeView === 'risk' ? '#3498db' : 'transparent',
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
          </ul>
        </nav>
      </div>

      {/* Main Content */}
      <div style={{
        flex: 1,
        padding: '20px',
        overflowY: 'auto'
      }}>
        <header style={{ marginBottom: '30px' }}>
          <h1>全智能量化交易系统</h1>
          <p>实时监控和管理您的交易策略</p>
        </header>
        {renderView()}
      </div>
    </div>
  );
}

export default App;