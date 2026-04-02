import React, { useState, useEffect, useCallback } from 'react';
import ProfessionalDashboard from './components/ProfessionalDashboard';
import Login from './components/Login';
import { api } from './services/api';
import { useAuthStore } from './store';
import './styles/main.css';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  const [activeView, setActiveView] = useState('dashboard');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [darkMode, setDarkMode] = useState(true);
  const [systemStatus, setSystemStatus] = useState({
    ai: 'online',
    trading: 'online',
    risk: 'online',
    data: 'online',
    exchange: 'online'
  });
  const [connectionStable, setConnectionStable] = useState(true);

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
      setDarkMode(savedTheme === 'dark');
    }
    document.documentElement.setAttribute('data-theme', darkMode ? 'dark' : 'light');
  }, [darkMode]);

  useEffect(() => {
    checkAuth();
    checkSystemStatus();
    const interval = setInterval(checkSystemStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const checkAuth = async () => {
    const token = localStorage.getItem('token') || localStorage.getItem('auth_token');
    if (token) {
      try {
        const user = await api.auth.getCurrentUser().catch(() => null);
        if (user) {
          setCurrentUser(user);
          setIsAuthenticated(true);
        }
      } catch (e) {
        const savedUser = localStorage.getItem('user');
        if (savedUser) {
          setCurrentUser(JSON.parse(savedUser));
          setIsAuthenticated(true);
        }
      }
    }
  };

  const checkSystemStatus = useCallback(async () => {
    try {
      const [health, exchangeStatus] = await Promise.all([
        api.system.getHealth().catch(() => null),
        api.exchange.getList().catch(() => null)
      ]);
      
      const newStatus = {
        ai: health?.ai || 'online',
        trading: health?.trading || 'online',
        risk: health?.risk || 'online',
        data: health?.data || 'online',
        exchange: exchangeStatus ? 'online' : 'offline'
      };
      
      setSystemStatus(newStatus);
      setConnectionStable(true);
    } catch (e) {
      setConnectionStable(false);
    }
  }, []);

  const toggleTheme = useCallback(() => {
    const newMode = !darkMode;
    setDarkMode(newMode);
    localStorage.setItem('theme', newMode ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', newMode ? 'dark' : 'light');
  }, [darkMode]);

  const handleLogin = (user, token) => {
    localStorage.setItem('token', token);
    localStorage.setItem('auth_token', token);
    localStorage.setItem('user', JSON.stringify(user));
    setCurrentUser(user);
    setIsAuthenticated(true);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    setCurrentUser(null);
    setIsAuthenticated(false);
    setActiveView('dashboard');
  };

  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />;
  }

  const menuItems = [
    { id: 'dashboard', icon: '📊', label: '总览面板' },
    { id: 'market', icon: '📈', label: '行情中心' },
    { id: 'trade', icon: '💱', label: '交易面板' },
    { id: 'positions', icon: '📋', label: '持仓管理' },
    { id: 'history', icon: '📜', label: '交易历史' },
    { id: 'ai', icon: '🤖', label: 'AI 分析' },
    { id: 'analysis', icon: '🧠', label: '多源数据分析' },
    { id: 'strategies', icon: '⚙️', label: '策略管理' },
    { id: 'risk', icon: '🛡️', label: '风险控制' },
    { id: 'reports', icon: '📑', label: '分析报告' },
    { id: 'settings', icon: '🔧', label: '系统设置' },
  ];

  return (
    <div className="app-container" data-theme={darkMode ? 'dark' : 'light'}>
      <aside className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-header">
          <div className="logo">
            <span className="logo-icon">🚀</span>
            {!sidebarCollapsed && <span className="logo-text">量化交易系统</span>}
          </div>
          <button 
            className="sidebar-toggle"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          >
            {sidebarCollapsed ? '→' : '←'}
          </button>
        </div>
        
        <nav className="sidebar-nav">
          {menuItems.map(item => (
            <div
              key={item.id}
              className={`nav-item ${activeView === item.id ? 'active' : ''}`}
              onClick={() => setActiveView(item.id)}
            >
              <span className="nav-icon">{item.icon}</span>
              {!sidebarCollapsed && <span className="nav-label">{item.label}</span>}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="theme-toggle">
            <button 
              className="theme-btn"
              onClick={toggleTheme}
              title={darkMode ? '切换到浅色模式' : '切换到深色模式'}
            >
              {darkMode ? '☀️' : '🌙'}
            </button>
          </div>
          <div className="system-status-mini">
            <div className={`status-dot ${connectionStable && systemStatus.exchange === 'online' ? 'online' : 'offline'}`}></div>
            {!sidebarCollapsed && (
              <span className={connectionStable ? '' : 'status-warning'}>
                交易所: {connectionStable && systemStatus.exchange === 'online' ? '已连接' : '离线'}
              </span>
            )}
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="top-header">
          <div className="header-left">
            <h1 className="page-title">
              {menuItems.find(m => m.id === activeView)?.label || '总览面板'}
            </h1>
          </div>
          <div className="header-right">
            <div className="header-status">
              <span className="status-item">
                <span className={`status-dot ${systemStatus.trading === 'online' ? 'online' : 'offline'}`}></span>
                交易引擎
              </span>
              <span className="status-item">
                <span className={`status-dot ${systemStatus.ai === 'online' ? 'online' : 'offline'}`}></span>
                AI服务
              </span>
              <span className="status-item">
                <span className={`status-dot ${connectionStable ? 'online' : 'offline'}`}></span>
                {connectionStable ? '已连接' : '重连中...'}
              </span>
            </div>
            <div className="user-menu">
              <span className="user-avatar">👤</span>
              <span className="user-name">{currentUser?.username || 'Admin'}</span>
              <button className="logout-btn" onClick={handleLogout}>
                退出
              </button>
            </div>
          </div>
        </header>

        <div className="content-area">
          <ProfessionalDashboard activeView={activeView} />
        </div>
      </main>
    </div>
  );
}

export default App;
