import React, { useState, useEffect } from 'react';
import { api } from '../services/api';

function ControlCenter() {
  const [modules, setModules] = useState([]);
  const [models, setModels] = useState([]);
  const [tradingSymbols, setTradingSymbols] = useState([]);
  const [blacklist, setBlacklist] = useState(['ETH/USDT']);
  const [riskStatus, setRiskStatus] = useState({});
  const [memoryStats, setMemoryStats] = useState({});
  const [systemHealth, setSystemHealth] = useState({});
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('modules');
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    loadAllData();
    const interval = setInterval(loadAllData, 10000);
    return () => clearInterval(interval);
  }, []);

  const loadAllData = async () => {
    setLoading(true);
    try {
      const [modulesRes, modelsRes, symbolsRes, riskRes, memoryRes, healthRes] = await Promise.all([
        api.request('/modules/list').catch(() => ({ modules: [] })),
        api.request('/modules/models').catch(() => ({ models: [] })),
        api.request('/modules/trading/symbols').catch(() => ({ symbols: [], blacklist: [] })),
        api.request('/modules/risk/status').catch(() => ({})),
        api.request('/modules/memory/stats').catch(() => ({})),
        api.request('/modules/system/health').catch(() => ({}))
      ]);

      setModules(modulesRes.modules || []);
      setModels(modelsRes.models || []);
      setTradingSymbols(symbolsRes.symbols || []);
      setBlacklist(symbolsRes.blacklist || ['ETH/USDT']);
      setRiskStatus(riskRes);
      setMemoryStats(memoryRes);
      setSystemHealth(healthRes);

      addLog('系统数据已刷新', 'info');
    } catch (error) {
      console.error('加载数据失败:', error);
      addLog('加载数据失败: ' + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const addLog = (message, type = 'info') => {
    const newLog = {
      id: Date.now(),
      message,
      type,
      timestamp: new Date().toLocaleTimeString()
    };
    setLogs(prev => [newLog, ...prev].slice(0, 100));
  };

  const handleModuleControl = async (moduleId, action, params = {}) => {
    try {
      addLog(`正在执行: ${moduleId} - ${action}`, 'info');
      const result = await api.request(`/modules/${moduleId}/control?action=${action}`, {
        method: 'POST',
        body: JSON.stringify(params)
      });

      if (result.success) {
        addLog(`✅ ${result.message}`, 'success');
        loadAllData();
      } else {
        addLog(`❌ ${result.message}`, 'error');
      }
    } catch (error) {
      addLog(`❌ 操作失败: ${error.message}`, 'error');
    }
  };

  const handleModelSelect = async (modelId) => {
    try {
      const result = await api.request(`/modules/models/${modelId}/select`, {
        method: 'POST'
      });
      addLog(result.message, result.success ? 'success' : 'error');
    } catch (error) {
      addLog('模型选择失败: ' + error.message, 'error');
    }
  };

  const handleSymbolConfig = async () => {
    try {
      const allSymbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT'];
      const result = await api.request('/modules/trading/symbols/config', {
        method: 'POST',
        body: JSON.stringify({
          symbols: allSymbols,
          blacklist: blacklist
        })
      });
      addLog(result.message, result.success ? 'success' : 'error');
      if (result.success) {
        setTradingSymbols(result.symbols);
      }
    } catch (error) {
      addLog('配置失败: ' + error.message, 'error');
    }
  };

  const toggleBlacklist = (symbol) => {
    setBlacklist(prev => {
      if (prev.includes(symbol)) {
        return prev.filter(s => s !== symbol);
      } else {
        return [...prev, symbol];
      }
    });
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'running':
      case 'healthy':
      case 'active':
        return '#27ae60';
      case 'stopped':
      case 'inactive':
        return '#e74c3c';
      case 'ready':
        return '#3498db';
      default:
        return '#95a5a6';
    }
  };

  const getCategoryIcon = (category) => {
    const icons = {
      '核心': '🧠',
      'AI': '🤖',
      '通信': '📡',
      '安全': '🛡️',
      '监控': '📊',
      '资金': '💰',
      '策略': '📈',
      '数据': '💾'
    };
    return icons[category] || '📦';
  };

  return (
    <div style={{ padding: '20px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '28px' }}>🎮 全智能量化交易控制中心</h1>
          <p style={{ margin: '5px 0 0 0', color: '#666' }}>集中控制所有系统模块和配置</p>
        </div>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <span style={{
            padding: '8px 16px',
            borderRadius: '20px',
            backgroundColor: systemHealth.overall === 'healthy' ? '#27ae60' : '#f39c12',
            color: 'white',
            fontWeight: 'bold'
          }}>
            {systemHealth.overall === 'healthy' ? '✅ 系统正常' : '⚠️ 需要关注'}
          </span>
          <button
            onClick={loadAllData}
            style={{
              padding: '10px 20px',
              backgroundColor: '#3498db',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer'
            }}
          >
            🔄 刷新
          </button>
        </div>
      </div>

      {/* 标签导航 */}
      <div style={{ display: 'flex', gap: '5px', marginBottom: '20px', borderBottom: '2px solid #eee', paddingBottom: '10px' }}>
        {[
          { id: 'modules', label: '📦 模块控制' },
          { id: 'trading', label: '💱 交易配置' },
          { id: 'ai', label: '🤖 AI模型' },
          { id: 'risk', label: '🛡️ 风险管理' },
          { id: 'logs', label: '📋 系统日志' }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '10px 20px',
              backgroundColor: activeTab === tab.id ? '#3498db' : 'transparent',
              color: activeTab === tab.id ? 'white' : '#333',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontWeight: activeTab === tab.id ? 'bold' : 'normal'
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 模块控制 */}
      {activeTab === 'modules' && (
        <div>
          <h2>📦 系统模块 ({modules.length}个)</h2>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))',
            gap: '15px',
            marginTop: '15px'
          }}>
            {modules.map(module => (
              <div key={module.id} style={{
                backgroundColor: 'white',
                borderRadius: '12px',
                padding: '20px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                borderLeft: `4px solid ${getStatusColor(module.status)}`
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <div>
                    <span style={{ fontSize: '20px', marginRight: '8px' }}>{getCategoryIcon(module.category)}</span>
                    <span style={{ fontWeight: 'bold', fontSize: '16px' }}>{module.name}</span>
                  </div>
                  <span style={{
                    padding: '4px 12px',
                    borderRadius: '12px',
                    backgroundColor: getStatusColor(module.status),
                    color: 'white',
                    fontSize: '12px',
                    fontWeight: 'bold'
                  }}>
                    {module.status}
                  </span>
                </div>
                <p style={{ color: '#666', fontSize: '13px', margin: '5px 0 15px 0' }}>
                  {module.description}
                </p>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {module.controls?.map(control => (
                    <button
                      key={control}
                      onClick={() => handleModuleControl(module.id, control)}
                      style={{
                        padding: '6px 14px',
                        backgroundColor: control === 'stop' ? '#e74c3c' : control === 'start' ? '#27ae60' : '#3498db',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '12px'
                      }}
                    >
                      {control}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 交易配置 */}
      {activeTab === 'trading' && (
        <div>
          <h2>💱 交易对配置</h2>
          <div style={{ backgroundColor: 'white', borderRadius: '12px', padding: '20px', marginTop: '15px' }}>
            <div style={{ marginBottom: '20px' }}>
              <h3>🚫 黑名单 (不交易)</h3>
              <p style={{ color: '#666', fontSize: '13px' }}>黑名单中的交易对将被AI自动排除</p>
              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginTop: '10px' }}>
                {['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT'].map(symbol => (
                  <button
                    key={symbol}
                    onClick={() => toggleBlacklist(symbol)}
                    style={{
                      padding: '8px 16px',
                      backgroundColor: blacklist.includes(symbol) ? '#e74c3c' : '#27ae60',
                      color: 'white',
                      border: 'none',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      opacity: symbol === 'ETH/USDT' ? 1 : 0.8
                    }}
                  >
                    {symbol} {blacklist.includes(symbol) ? '🚫' : '✅'}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <h3>📊 当前活跃交易对</h3>
              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginTop: '10px' }}>
                {tradingSymbols.map(symbol => (
                  <span key={symbol} style={{
                    padding: '6px 14px',
                    backgroundColor: '#3498db',
                    color: 'white',
                    borderRadius: '4px',
                    fontSize: '13px'
                  }}>
                    {symbol}
                  </span>
                ))}
              </div>
            </div>

            <button
              onClick={handleSymbolConfig}
              style={{
                padding: '12px 24px',
                backgroundColor: '#27ae60',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontWeight: 'bold'
              }}
            >
              💾 保存配置
            </button>
          </div>
        </div>
      )}

      {/* AI模型 */}
      {activeTab === 'ai' && (
        <div>
          <h2>🤖 AI模型配置</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '15px', marginTop: '15px' }}>
            {models.map(model => (
              <div key={model.id} style={{
                backgroundColor: 'white',
                borderRadius: '12px',
                padding: '20px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <h4 style={{ margin: '0 0 5px 0' }}>{model.name}</h4>
                    <p style={{ color: '#666', fontSize: '12px', margin: 0 }}>
                      Provider: {model.provider} | Priority: {model.priority}
                    </p>
                  </div>
                  <span style={{
                    padding: '4px 10px',
                    borderRadius: '4px',
                    backgroundColor: model.enabled ? '#27ae60' : '#95a5a6',
                    color: 'white',
                    fontSize: '11px'
                  }}>
                    {model.enabled ? '启用' : '禁用'}
                  </span>
                </div>
                <div style={{ marginTop: '15px' }}>
                  <button
                    onClick={() => handleModelSelect(model.id)}
                    style={{
                      width: '100%',
                      padding: '8px',
                      backgroundColor: '#3498db',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer'
                    }}
                  >
                    选择此模型
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div style={{ backgroundColor: 'white', borderRadius: '12px', padding: '20px', marginTop: '20px' }}>
            <h3>🧠 记忆系统统计</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '15px', marginTop: '10px' }}>
              <div style={{ textAlign: 'center', padding: '15px', backgroundColor: '#f8f9fa', borderRadius: '8px' }}>
                <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#3498db' }}>{memoryStats.short_term_count || 0}</div>
                <div style={{ fontSize: '12px', color: '#666' }}>短期记忆</div>
              </div>
              <div style={{ textAlign: 'center', padding: '15px', backgroundColor: '#f8f9fa', borderRadius: '8px' }}>
                <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#27ae60' }}>{memoryStats.long_term_count || 0}</div>
                <div style={{ fontSize: '12px', color: '#666' }}>长期记忆</div>
              </div>
              <div style={{ textAlign: 'center', padding: '15px', backgroundColor: '#f8f9fa', borderRadius: '8px' }}>
                <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#f39c12' }}>{memoryStats.trade_records || 0}</div>
                <div style={{ fontSize: '12px', color: '#666' }}>交易记录</div>
              </div>
              <div style={{ textAlign: 'center', padding: '15px', backgroundColor: '#f8f9fa', borderRadius: '8px' }}>
                <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#e74c3c' }}>{memoryStats.risk_events || 0}</div>
                <div style={{ fontSize: '12px', color: '#666' }}>风险事件</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 风险管理 */}
      {activeTab === 'risk' && (
        <div>
          <h2>🛡️ 风险管理</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '15px', marginTop: '15px' }}>
            <div style={{ backgroundColor: 'white', borderRadius: '12px', padding: '20px' }}>
              <h4>熔断器状态</h4>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: riskStatus.circuit_breaker?.status === 'closed' ? '#27ae60' : '#e74c3c' }}>
                {riskStatus.circuit_breaker?.status === 'closed' ? '✅ 正常' : '🚨 已触发'}
              </div>
            </div>
            <div style={{ backgroundColor: 'white', borderRadius: '12px', padding: '20px' }}>
              <h4>日内交易次数</h4>
              <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{riskStatus.daily_trades || 0}</div>
            </div>
            <div style={{ backgroundColor: 'white', borderRadius: '12px', padding: '20px' }}>
              <h4>连续亏损</h4>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: (riskStatus.consecutive_losses || 0) > 2 ? '#e74c3c' : '#333' }}>
                {riskStatus.consecutive_losses || 0}
              </div>
            </div>
            <div style={{ backgroundColor: 'white', borderRadius: '12px', padding: '20px' }}>
              <h4>当前回撤</h4>
              <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
                {((riskStatus.current_drawdown || 0) * 100).toFixed(2)}%
              </div>
            </div>
          </div>

          <div style={{ backgroundColor: 'white', borderRadius: '12px', padding: '20px', marginTop: '20px' }}>
            <h3>⚡ 快速操作</h3>
            <div style={{ display: 'flex', gap: '10px', marginTop: '15px' }}>
              <button
                onClick={() => handleModuleControl('risk', 'reset')}
                style={{
                  padding: '12px 24px',
                  backgroundColor: '#f39c12',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer'
                }}
              >
                🔄 重置计数器
              </button>
              <button
                onClick={() => handleModuleControl('emergency_stop', 'trigger')}
                style={{
                  padding: '12px 24px',
                  backgroundColor: '#e74c3c',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: 'bold'
                }}
              >
                🚨 紧急停止
              </button>
              <button
                onClick={() => handleModuleControl('emergency_stop', 'reset')}
                style={{
                  padding: '12px 24px',
                  backgroundColor: '#27ae60',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer'
                }}
              >
                ✅ 重置紧急停止
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 系统日志 */}
      {activeTab === 'logs' && (
        <div>
          <h2>📋 系统日志</h2>
          <div style={{
            backgroundColor: '#1e1e1e',
            borderRadius: '12px',
            padding: '15px',
            marginTop: '15px',
            maxHeight: '500px',
            overflowY: 'auto'
          }}>
            {logs.map(log => (
              <div key={log.id} style={{
                fontFamily: 'monospace',
                fontSize: '13px',
                padding: '5px 10px',
                borderBottom: '1px solid #333',
                color: log.type === 'error' ? '#e74c3c' : log.type === 'success' ? '#27ae60' : '#fff'
              }}>
                <span style={{ color: '#666' }}>[{log.timestamp}]</span> {log.message}
              </div>
            ))}
            {logs.length === 0 && (
              <div style={{ color: '#666', textAlign: 'center', padding: '20px' }}>
                暂无日志
              </div>
            )}
          </div>
        </div>
      )}

      {/* 底部状态栏 */}
      <div style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        backgroundColor: '#2c3e50',
        color: 'white',
        padding: '10px 20px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <span style={{ marginRight: '20px' }}>📊 模块: {modules.filter(m => m.status === 'running').length}/{modules.length}</span>
          <span style={{ marginRight: '20px' }}>🤖 模型: {models.length}</span>
          <span>💱 交易对: {tradingSymbols.length}</span>
        </div>
        <div>
          <span>最后更新: {new Date().toLocaleTimeString()}</span>
        </div>
      </div>
    </div>
  );
}

export default ControlCenter;
