import React, { useState, useEffect } from 'react';
import { api } from '../services/api';

function Settings() {
  const [systemSettings, setSystemSettings] = useState({
    system_name: '全智能量化交易系统',
    language: 'zh-CN',
    timezone: 'Asia/Shanghai',
    theme: 'light',
    auto_backup: true,
    backup_interval: 'daily',
    log_level: 'info'
  });
  
  const [apiSettings, setApiSettings] = useState({
    api_url: 'http://localhost:8000',
    api_key: '********',
    api_secret: '********',
    rate_limit: 60,
    timeout: 30
  });
  
  const [riskSettings, setRiskSettings] = useState({
    max_drawdown: 10,
    max_position_size: 10,
    max_leverage: 3,
    stop_loss_enabled: true,
    take_profit_enabled: true,
    risk_per_trade: 2
  });
  
  const [userSettings, setUserSettings] = useState({
    username: 'admin',
    email: 'admin@example.com',
    change_password: false,
    current_password: '',
    new_password: '',
    confirm_password: ''
  });

  const [models, setModels] = useState([]);
  const [modelSettings, setModelSettings] = useState({
    model_type: 'lstm',
    symbol: 'BTC/USDT',
    hidden_size: 64,
    num_layers: 2,
    lookback: 60,
    learning_rate: 0.001,
    epochs: 100,
    batch_size: 32
  });

  const [aiModels, setAiModels] = useState([]);
  const [aiModelSettings, setAiModelSettings] = useState({
    name: '',
    provider: 'local',
    model: 'llama3',
    api_key: '',
    base_url: 'http://localhost:11434/api/generate',
    enabled: true
  });
  const [defaultAiModel, setDefaultAiModel] = useState({
    default_provider: 'local',
    default_model: 'llama3'
  });
  const [editingAiModel, setEditingAiModel] = useState(null);
  
  const [loading, setLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [activeTab, setActiveTab] = useState('system');

  useEffect(() => {
    loadSettings();
    if (activeTab === 'models') {
      loadModels();
    } else if (activeTab === 'ai-models') {
      loadAiModels();
      loadDefaultAiModel();
    }
  }, [activeTab]);

  const loadSettings = async () => {
    try {
      setLoading(true);
      // 从API加载设置
      const response = await api.settings.get();
      console.log('加载设置:', response);
      
      // 更新设置状态
      if (response.system) {
        setSystemSettings(response.system);
      }
      if (response.api) {
        setApiSettings(response.api);
      }
      if (response.risk) {
        setRiskSettings(response.risk);
      }
      if (response.user) {
        setUserSettings(prev => ({
          ...prev,
          username: response.user.username || prev.username,
          email: response.user.email || prev.email
        }));
      }
    } catch (error) {
      console.error('加载设置失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadModels = async () => {
    try {
      setLoading(true);
      // 从API加载模型列表
      const response = await api.models.getList();
      console.log('加载模型列表:', response);
      setModels(response);
    } catch (error) {
      console.error('加载模型列表失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleModelSettingChange = (e) => {
    const { name, value, type, checked } = e.target;
    setModelSettings(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : parseFloat(value) || value
    }));
  };

  const handleTrainModel = async () => {
    try {
      setLoading(true);
      // 调用API训练模型
      const response = await api.models.train(modelSettings);
      console.log('训练模型结果:', response);
      
      setSuccessMessage('模型训练成功！');
      setTimeout(() => setSuccessMessage(''), 3000);
      
      // 重新加载模型列表
      await loadModels();
    } catch (error) {
      console.error('训练模型失败:', error);
      setSuccessMessage('训练模型失败，请重试！');
      setTimeout(() => setSuccessMessage(''), 3000);
    } finally {
      setLoading(false);
    }
  };

  const handleViewModel = async (modelId) => {
    try {
      setLoading(true);
      // 调用API获取模型性能
      const response = await api.models.getPerformance(modelId);
      console.log('模型性能:', response);
      
      // 显示模型性能信息
      alert(`模型性能:\nR²: ${response.performance.r2.toFixed(4)}\nMSE: ${response.performance.mse.toFixed(4)}\nMAE: ${response.performance.mae.toFixed(4)}\nRMSE: ${response.performance.rmse.toFixed(4)}\nMAPE: ${response.performance.mape.toFixed(4)}`);
    } catch (error) {
      console.error('获取模型性能失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteModel = async (modelId) => {
    if (!confirm('确定要删除这个模型吗？')) return;
    
    try {
      setLoading(true);
      // 调用API删除模型
      const response = await api.models.delete(modelId);
      console.log('删除模型结果:', response);
      
      setSuccessMessage('模型删除成功！');
      setTimeout(() => setSuccessMessage(''), 3000);
      
      // 重新加载模型列表
      await loadModels();
    } catch (error) {
      console.error('删除模型失败:', error);
      setSuccessMessage('删除模型失败，请重试！');
      setTimeout(() => setSuccessMessage(''), 3000);
    } finally {
      setLoading(false);
    }
  };

  const loadAiModels = async () => {
    try {
      setLoading(true);
      // 从API加载AI模型列表
      const response = await api.aiModels.getList();
      console.log('加载AI模型列表:', response);
      setAiModels(response);
    } catch (error) {
      console.error('加载AI模型列表失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadDefaultAiModel = async () => {
    try {
      // 从API加载默认AI模型
      const response = await api.aiModels.getDefault();
      console.log('加载默认AI模型:', response);
      setDefaultAiModel(response);
    } catch (error) {
      console.error('加载默认AI模型失败:', error);
    }
  };

  const handleAiModelSettingChange = (e) => {
    const { name, value, type, checked } = e.target;
    setAiModelSettings(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleDefaultAiModelChange = (e) => {
    const { name, value } = e.target;
    setDefaultAiModel(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleAddAiModel = async () => {
    try {
      setLoading(true);
      // 调用API添加AI模型
      const response = await api.aiModels.add(aiModelSettings);
      console.log('添加AI模型结果:', response);
      
      setSuccessMessage('AI模型添加成功！');
      setTimeout(() => setSuccessMessage(''), 3000);
      
      // 重置表单
      setAiModelSettings({
        name: '',
        provider: 'local',
        model: 'llama3',
        api_key: '',
        base_url: 'http://localhost:11434/api/generate',
        enabled: true
      });
      setEditingAiModel(null);
      
      // 重新加载AI模型列表
      await loadAiModels();
    } catch (error) {
      console.error('添加AI模型失败:', error);
      setSuccessMessage('添加AI模型失败，请重试！');
      setTimeout(() => setSuccessMessage(''), 3000);
    } finally {
      setLoading(false);
    }
  };

  const handleEditAiModel = (model) => {
    setEditingAiModel(model.id);
    setAiModelSettings({
      name: model.name,
      provider: model.provider,
      model: model.model,
      api_key: model.api_key === '********' ? '' : model.api_key,
      base_url: model.base_url,
      enabled: model.enabled
    });
  };

  const handleUpdateAiModel = async () => {
    if (!editingAiModel) return;
    
    try {
      setLoading(true);
      // 调用API更新AI模型
      const response = await api.aiModels.update(editingAiModel, aiModelSettings);
      console.log('更新AI模型结果:', response);
      
      setSuccessMessage('AI模型更新成功！');
      setTimeout(() => setSuccessMessage(''), 3000);
      
      // 重置表单
      setAiModelSettings({
        name: '',
        provider: 'local',
        model: 'llama3',
        api_key: '',
        base_url: 'http://localhost:11434/api/generate',
        enabled: true
      });
      setEditingAiModel(null);
      
      // 重新加载AI模型列表
      await loadAiModels();
    } catch (error) {
      console.error('更新AI模型失败:', error);
      setSuccessMessage('更新AI模型失败，请重试！');
      setTimeout(() => setSuccessMessage(''), 3000);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAiModel = async (modelId) => {
    if (!confirm('确定要删除这个AI模型吗？')) return;
    
    try {
      setLoading(true);
      // 调用API删除AI模型
      const response = await api.aiModels.delete(modelId);
      console.log('删除AI模型结果:', response);
      
      setSuccessMessage('AI模型删除成功！');
      setTimeout(() => setSuccessMessage(''), 3000);
      
      // 重新加载AI模型列表
      await loadAiModels();
    } catch (error) {
      console.error('删除AI模型失败:', error);
      setSuccessMessage('删除AI模型失败，请重试！');
      setTimeout(() => setSuccessMessage(''), 3000);
    } finally {
      setLoading(false);
    }
  };

  const handleSetDefaultAiModel = async () => {
    try {
      setLoading(true);
      // 调用API设置默认AI模型
      const response = await api.aiModels.setDefault(defaultAiModel);
      console.log('设置默认AI模型结果:', response);
      
      setSuccessMessage('默认AI模型设置成功！');
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (error) {
      console.error('设置默认AI模型失败:', error);
      setSuccessMessage('设置默认AI模型失败，请重试！');
      setTimeout(() => setSuccessMessage(''), 3000);
    } finally {
      setLoading(false);
    }
  };

  const handleSystemSettingChange = (e) => {
    const { name, value, type, checked } = e.target;
    setSystemSettings(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleApiSettingChange = (e) => {
    const { name, value, type, checked } = e.target;
    setApiSettings(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleRiskSettingChange = (e) => {
    const { name, value, type, checked } = e.target;
    setRiskSettings(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : parseFloat(value) || 0
    }));
  };

  const handleUserSettingChange = (e) => {
    const { name, value, type, checked } = e.target;
    setUserSettings(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const saveSettings = async (settingsType) => {
    try {
      setLoading(true);
      
      // 根据设置类型保存不同的设置
      let settingsToSave = {};
      switch (activeTab) {
        case 'system':
          settingsToSave = { system: systemSettings };
          break;
        case 'api':
          settingsToSave = { api: apiSettings };
          break;
        case 'risk':
          settingsToSave = { risk: riskSettings };
          break;
        case 'user':
          settingsToSave = { user: {
            username: userSettings.username,
            email: userSettings.email
          }};
          break;
        default:
          return;
      }
      
      // 调用API保存设置
      const response = await api.settings.update(settingsToSave);
      console.log('保存设置:', settingsToSave);
      console.log('保存结果:', response);
      
      setSuccessMessage(`${settingsType}设置保存成功！`);
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (error) {
      console.error('保存设置失败:', error);
      setSuccessMessage('保存设置失败，请重试！');
      setTimeout(() => setSuccessMessage(''), 3000);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '20px' }}>
      <h2>系统设置</h2>
      
      {successMessage && (
        <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#e8f5e8', color: '#2e7d32', borderRadius: '4px' }}>
          {successMessage}
        </div>
      )}
      
      <div style={{ marginBottom: '30px' }}>
        <div style={{ display: 'flex', borderBottom: '1px solid #e0e0e0', marginBottom: '20px' }}>
          <button
            onClick={() => setActiveTab('system')}
            style={{
              padding: '10px 20px',
              border: 'none',
              backgroundColor: activeTab === 'system' ? '#3498db' : 'transparent',
              color: activeTab === 'system' ? 'white' : '#333',
              cursor: 'pointer',
              borderTopLeftRadius: '4px',
              borderTopRightRadius: '4px'
            }}
          >
            基本设置
          </button>
          <button
            onClick={() => setActiveTab('api')}
            style={{
              padding: '10px 20px',
              border: 'none',
              backgroundColor: activeTab === 'api' ? '#3498db' : 'transparent',
              color: activeTab === 'api' ? 'white' : '#333',
              cursor: 'pointer',
              borderTopLeftRadius: '4px',
              borderTopRightRadius: '4px'
            }}
          >
            API设置
          </button>
          <button
            onClick={() => setActiveTab('risk')}
            style={{
              padding: '10px 20px',
              border: 'none',
              backgroundColor: activeTab === 'risk' ? '#3498db' : 'transparent',
              color: activeTab === 'risk' ? 'white' : '#333',
              cursor: 'pointer',
              borderTopLeftRadius: '4px',
              borderTopRightRadius: '4px'
            }}
          >
            风险管理设置
          </button>
          <button
            onClick={() => setActiveTab('user')}
            style={{
              padding: '10px 20px',
              border: 'none',
              backgroundColor: activeTab === 'user' ? '#3498db' : 'transparent',
              color: activeTab === 'user' ? 'white' : '#333',
              cursor: 'pointer',
              borderTopLeftRadius: '4px',
              borderTopRightRadius: '4px'
            }}
          >
            用户设置
          </button>
          <button
            onClick={() => setActiveTab('models')}
            style={{
              padding: '10px 20px',
              border: 'none',
              backgroundColor: activeTab === 'models' ? '#3498db' : 'transparent',
              color: activeTab === 'models' ? 'white' : '#333',
              cursor: 'pointer',
              borderTopLeftRadius: '4px',
              borderTopRightRadius: '4px'
            }}
          >
            模型管理
          </button>
          <button
            onClick={() => setActiveTab('ai-models')}
            style={{
              padding: '10px 20px',
              border: 'none',
              backgroundColor: activeTab === 'ai-models' ? '#3498db' : 'transparent',
              color: activeTab === 'ai-models' ? 'white' : '#333',
              cursor: 'pointer',
              borderTopLeftRadius: '4px',
              borderTopRightRadius: '4px'
            }}
          >
            AI模型管理
          </button>
        </div>
        
        {activeTab === 'system' && (
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
            <h3>基本设置</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '20px', marginBottom: '20px' }}>
              <div>
                <label htmlFor="system_name">系统名称：</label>
                <input
                  type="text"
                  id="system_name"
                  name="system_name"
                  value={systemSettings.system_name}
                  onChange={handleSystemSettingChange}
                  style={{ marginLeft: '10px', padding: '5px', width: '200px' }}
                />
              </div>
              <div>
                <label htmlFor="language">语言：</label>
                <select
                  id="language"
                  name="language"
                  value={systemSettings.language}
                  onChange={handleSystemSettingChange}
                  style={{ marginLeft: '10px', padding: '5px' }}
                >
                  <option value="zh-CN">简体中文</option>
                  <option value="en-US">English</option>
                </select>
              </div>
              <div>
                <label htmlFor="timezone">时区：</label>
                <select
                  id="timezone"
                  name="timezone"
                  value={systemSettings.timezone}
                  onChange={handleSystemSettingChange}
                  style={{ marginLeft: '10px', padding: '5px' }}
                >
                  <option value="Asia/Shanghai">Asia/Shanghai</option>
                  <option value="UTC">UTC</option>
                  <option value="America/New_York">America/New_York</option>
                  <option value="Europe/London">Europe/London</option>
                </select>
              </div>
              <div>
                <label htmlFor="theme">主题：</label>
                <select
                  id="theme"
                  name="theme"
                  value={systemSettings.theme}
                  onChange={handleSystemSettingChange}
                  style={{ marginLeft: '10px', padding: '5px' }}
                >
                  <option value="light">浅色</option>
                  <option value="dark">深色</option>
                </select>
              </div>
              <div>
                <label>
                  <input
                    type="checkbox"
                    name="auto_backup"
                    checked={systemSettings.auto_backup}
                    onChange={handleSystemSettingChange}
                  />
                  自动备份
                </label>
              </div>
              <div>
                <label htmlFor="backup_interval">备份频率：</label>
                <select
                  id="backup_interval"
                  name="backup_interval"
                  value={systemSettings.backup_interval}
                  onChange={handleSystemSettingChange}
                  style={{ marginLeft: '10px', padding: '5px' }}
                >
                  <option value="daily">每天</option>
                  <option value="weekly">每周</option>
                  <option value="monthly">每月</option>
                </select>
              </div>
              <div>
                <label htmlFor="log_level">日志级别：</label>
                <select
                  id="log_level"
                  name="log_level"
                  value={systemSettings.log_level}
                  onChange={handleSystemSettingChange}
                  style={{ marginLeft: '10px', padding: '5px' }}
                >
                  <option value="debug">Debug</option>
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="error">Error</option>
                </select>
              </div>
            </div>
            <button
              onClick={() => saveSettings('基本')}
              disabled={loading}
              style={{
                backgroundColor: '#3498db',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '4px',
                cursor: loading ? 'not-allowed' : 'pointer'
              }}
            >
              {loading ? '保存中...' : '保存设置'}
            </button>
          </div>
        )}
        
        {activeTab === 'api' && (
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
            <h3>API设置</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '20px', marginBottom: '20px' }}>
              <div>
                <label htmlFor="api_url">API URL：</label>
                <input
                  type="text"
                  id="api_url"
                  name="api_url"
                  value={apiSettings.api_url}
                  onChange={handleApiSettingChange}
                  style={{ marginLeft: '10px', padding: '5px', width: '300px' }}
                />
              </div>
              <div>
                <label htmlFor="api_key">API Key：</label>
                <input
                  type="text"
                  id="api_key"
                  name="api_key"
                  value={apiSettings.api_key}
                  onChange={handleApiSettingChange}
                  style={{ marginLeft: '10px', padding: '5px', width: '300px' }}
                />
              </div>
              <div>
                <label htmlFor="api_secret">API Secret：</label>
                <input
                  type="password"
                  id="api_secret"
                  name="api_secret"
                  value={apiSettings.api_secret}
                  onChange={handleApiSettingChange}
                  style={{ marginLeft: '10px', padding: '5px', width: '300px' }}
                />
              </div>
              <div>
                <label htmlFor="rate_limit">速率限制（次/分钟）：</label>
                <input
                  type="number"
                  id="rate_limit"
                  name="rate_limit"
                  value={apiSettings.rate_limit}
                  onChange={handleApiSettingChange}
                  min="1"
                  style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
                />
              </div>
              <div>
                <label htmlFor="timeout">超时时间（秒）：</label>
                <input
                  type="number"
                  id="timeout"
                  name="timeout"
                  value={apiSettings.timeout}
                  onChange={handleApiSettingChange}
                  min="1"
                  style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
                />
              </div>
            </div>
            <button
              onClick={() => saveSettings('API')}
              disabled={loading}
              style={{
                backgroundColor: '#3498db',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '4px',
                cursor: loading ? 'not-allowed' : 'pointer'
              }}
            >
              {loading ? '保存中...' : '保存设置'}
            </button>
          </div>
        )}
        
        {activeTab === 'risk' && (
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
            <h3>风险管理设置</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '20px', marginBottom: '20px' }}>
              <div>
                <label htmlFor="max_drawdown">最大回撤限制（%）：</label>
                <input
                  type="number"
                  id="max_drawdown"
                  name="max_drawdown"
                  value={riskSettings.max_drawdown}
                  onChange={handleRiskSettingChange}
                  min="1"
                  max="50"
                  step="0.1"
                  style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
                />
              </div>
              <div>
                <label htmlFor="max_position_size">单笔最大仓位（%）：</label>
                <input
                  type="number"
                  id="max_position_size"
                  name="max_position_size"
                  value={riskSettings.max_position_size}
                  onChange={handleRiskSettingChange}
                  min="1"
                  max="50"
                  step="0.1"
                  style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
                />
              </div>
              <div>
                <label htmlFor="max_leverage">最大杠杆：</label>
                <input
                  type="number"
                  id="max_leverage"
                  name="max_leverage"
                  value={riskSettings.max_leverage}
                  onChange={handleRiskSettingChange}
                  min="1"
                  max="100"
                  step="0.1"
                  style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
                />
              </div>
              <div>
                <label htmlFor="risk_per_trade">每笔交易风险（%）：</label>
                <input
                  type="number"
                  id="risk_per_trade"
                  name="risk_per_trade"
                  value={riskSettings.risk_per_trade}
                  onChange={handleRiskSettingChange}
                  min="0.1"
                  max="10"
                  step="0.1"
                  style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
                />
              </div>
              <div>
                <label>
                  <input
                    type="checkbox"
                    name="stop_loss_enabled"
                    checked={riskSettings.stop_loss_enabled}
                    onChange={handleRiskSettingChange}
                  />
                  启用止损
                </label>
              </div>
              <div>
                <label>
                  <input
                    type="checkbox"
                    name="take_profit_enabled"
                    checked={riskSettings.take_profit_enabled}
                    onChange={handleRiskSettingChange}
                  />
                  启用止盈
                </label>
              </div>
            </div>
            <button
              onClick={() => saveSettings('风险管理')}
              disabled={loading}
              style={{
                backgroundColor: '#3498db',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '4px',
                cursor: loading ? 'not-allowed' : 'pointer'
              }}
            >
              {loading ? '保存中...' : '保存设置'}
            </button>
          </div>
        )}
        
        {activeTab === 'user' && (
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
            <h3>用户设置</h3>
            <div style={{ marginBottom: '20px' }}>
              <div style={{ marginBottom: '15px' }}>
                <label htmlFor="username">用户名：</label>
                <input
                  type="text"
                  id="username"
                  name="username"
                  value={userSettings.username}
                  onChange={handleUserSettingChange}
                  style={{ marginLeft: '10px', padding: '5px', width: '200px' }}
                />
              </div>
              <div style={{ marginBottom: '15px' }}>
                <label htmlFor="email">邮箱：</label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  value={userSettings.email}
                  onChange={handleUserSettingChange}
                  style={{ marginLeft: '10px', padding: '5px', width: '200px' }}
                />
              </div>
              <div style={{ marginBottom: '15px' }}>
                <label>
                  <input
                    type="checkbox"
                    name="change_password"
                    checked={userSettings.change_password}
                    onChange={handleUserSettingChange}
                  />
                  修改密码
                </label>
              </div>
              {userSettings.change_password && (
                <div style={{ marginLeft: '20px', marginTop: '15px' }}>
                  <div style={{ marginBottom: '10px' }}>
                    <label htmlFor="current_password">当前密码：</label>
                    <input
                      type="password"
                      id="current_password"
                      name="current_password"
                      value={userSettings.current_password}
                      onChange={handleUserSettingChange}
                      style={{ marginLeft: '10px', padding: '5px', width: '200px' }}
                    />
                  </div>
                  <div style={{ marginBottom: '10px' }}>
                    <label htmlFor="new_password">新密码：</label>
                    <input
                      type="password"
                      id="new_password"
                      name="new_password"
                      value={userSettings.new_password}
                      onChange={handleUserSettingChange}
                      style={{ marginLeft: '10px', padding: '5px', width: '200px' }}
                    />
                  </div>
                  <div style={{ marginBottom: '10px' }}>
                    <label htmlFor="confirm_password">确认密码：</label>
                    <input
                      type="password"
                      id="confirm_password"
                      name="confirm_password"
                      value={userSettings.confirm_password}
                      onChange={handleUserSettingChange}
                      style={{ marginLeft: '10px', padding: '5px', width: '200px' }}
                    />
                  </div>
                </div>
              )}
            </div>
            <button
              onClick={() => saveSettings('用户')}
              disabled={loading}
              style={{
                backgroundColor: '#3498db',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '4px',
                cursor: loading ? 'not-allowed' : 'pointer'
              }}
            >
              {loading ? '保存中...' : '保存设置'}
            </button>
          </div>
        )}

        {activeTab === 'models' && (
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
            <h3>模型管理</h3>
            
            <div style={{ marginBottom: '30px' }}>
              <h4>模型列表</h4>
              <div style={{ overflowX: 'auto', marginBottom: '20px' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f2f2f2' }}>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>ID</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>名称</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>类型</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>交易对</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>状态</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>性能</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>最后训练</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {models.length > 0 ? (
                      models.map(model => (
                        <tr key={model.id}>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>{model.id}</td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>{model.name}</td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>{model.type}</td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>{model.symbol}</td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                            <span style={{
                              padding: '2px 8px',
                              borderRadius: '12px',
                              backgroundColor: model.status === 'active' ? '#d4edda' : '#f8d7da',
                              color: model.status === 'active' ? '#155724' : '#721c24'
                            }}>
                              {model.status === 'active' ? '活跃' : '禁用'}
                            </span>
                          </td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                            R²: {model.performance?.r2?.toFixed(2) || 'N/A'}
                          </td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                            {new Date(model.last_trained).toLocaleString()}
                          </td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                            <button
                              onClick={() => handleViewModel(model.id)}
                              style={{
                                marginRight: '5px',
                                padding: '4px 8px',
                                backgroundColor: '#3498db',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer'
                              }}
                            >
                              查看
                            </button>
                            <button
                              onClick={() => handleDeleteModel(model.id)}
                              style={{
                                padding: '4px 8px',
                                backgroundColor: '#e74c3c',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer'
                              }}
                            >
                              删除
                            </button>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan="8" style={{ border: '1px solid #ddd', padding: '20px', textAlign: 'center' }}>
                          暂无模型
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <h4>训练新模型</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '20px', marginBottom: '20px' }}>
                <div>
                  <label htmlFor="model_type">模型类型：</label>
                  <select
                    id="model_type"
                    name="model_type"
                    value={modelSettings.model_type}
                    onChange={handleModelSettingChange}
                    style={{ marginLeft: '10px', padding: '5px' }}
                  >
                    <option value="lstm">LSTM</option>
                    <option value="gru">GRU</option>
                    <option value="transformer">Transformer</option>
                    <option value="simple_ma">简单移动平均</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="symbol">交易对：</label>
                  <select
                    id="symbol"
                    name="symbol"
                    value={modelSettings.symbol}
                    onChange={handleModelSettingChange}
                    style={{ marginLeft: '10px', padding: '5px' }}
                  >
                    <option value="BTC/USDT">BTC/USDT</option>
                    <option value="ETH/USDT">ETH/USDT</option>
                    <option value="BNB/USDT">BNB/USDT</option>
                    <option value="SOL/USDT">SOL/USDT</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="hidden_size">隐藏层大小：</label>
                  <input
                    type="number"
                    id="hidden_size"
                    name="hidden_size"
                    value={modelSettings.hidden_size}
                    onChange={handleModelSettingChange}
                    min="16"
                    max="256"
                    style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
                  />
                </div>
                <div>
                  <label htmlFor="num_layers">层数：</label>
                  <input
                    type="number"
                    id="num_layers"
                    name="num_layers"
                    value={modelSettings.num_layers}
                    onChange={handleModelSettingChange}
                    min="1"
                    max="5"
                    style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
                  />
                </div>
                <div>
                  <label htmlFor="lookback">回溯窗口：</label>
                  <input
                    type="number"
                    id="lookback"
                    name="lookback"
                    value={modelSettings.lookback}
                    onChange={handleModelSettingChange}
                    min="10"
                    max="200"
                    style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
                  />
                </div>
                <div>
                  <label htmlFor="learning_rate">学习率：</label>
                  <input
                    type="number"
                    id="learning_rate"
                    name="learning_rate"
                    value={modelSettings.learning_rate}
                    onChange={handleModelSettingChange}
                    min="0.0001"
                    max="0.1"
                    step="0.0001"
                    style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
                  />
                </div>
                <div>
                  <label htmlFor="epochs">训练轮数：</label>
                  <input
                    type="number"
                    id="epochs"
                    name="epochs"
                    value={modelSettings.epochs}
                    onChange={handleModelSettingChange}
                    min="10"
                    max="1000"
                    style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
                  />
                </div>
                <div>
                  <label htmlFor="batch_size">批次大小：</label>
                  <input
                    type="number"
                    id="batch_size"
                    name="batch_size"
                    value={modelSettings.batch_size}
                    onChange={handleModelSettingChange}
                    min="8"
                    max="128"
                    style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
                  />
                </div>
              </div>
              <button
                onClick={handleTrainModel}
                disabled={loading}
                style={{
                  backgroundColor: '#27ae60',
                  color: 'white',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: '4px',
                  cursor: loading ? 'not-allowed' : 'pointer'
                }}
              >
                {loading ? '训练中...' : '训练模型'}
              </button>
            </div>
          </div>
        )}

        {activeTab === 'ai-models' && (
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
            <h3>AI模型管理</h3>
            
            <div style={{ marginBottom: '30px' }}>
              <h4>AI模型列表</h4>
              <div style={{ overflowX: 'auto', marginBottom: '20px' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f2f2f2' }}>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>ID</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>名称</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>提供者</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>模型</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>状态</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>API Key</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>Base URL</th>
                      <th style={{ border: '1px solid #ddd', padding: '8px' }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {aiModels.length > 0 ? (
                      aiModels.map(model => (
                        <tr key={model.id}>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>{model.id}</td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>{model.name}</td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>{model.provider}</td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>{model.model}</td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                            <span style={{
                              padding: '2px 8px',
                              borderRadius: '12px',
                              backgroundColor: model.status === 'active' ? '#d4edda' : '#f8d7da',
                              color: model.status === 'active' ? '#155724' : '#721c24'
                            }}>
                              {model.status === 'active' ? '活跃' : '禁用'}
                            </span>
                          </td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>{model.api_key}</td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>{model.base_url}</td>
                          <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                            <button
                              onClick={() => handleEditAiModel(model)}
                              style={{
                                marginRight: '5px',
                                padding: '4px 8px',
                                backgroundColor: '#3498db',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer'
                              }}
                            >
                              编辑
                            </button>
                            <button
                              onClick={() => handleDeleteAiModel(model.id)}
                              style={{
                                padding: '4px 8px',
                                backgroundColor: '#e74c3c',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer'
                              }}
                            >
                              删除
                            </button>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan="8" style={{ border: '1px solid #ddd', padding: '20px', textAlign: 'center' }}>
                          暂无AI模型
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div style={{ marginBottom: '30px' }}>
              <h4>{editingAiModel ? '编辑AI模型' : '添加AI模型'}</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '20px', marginBottom: '20px' }}>
                <div>
                  <label htmlFor="name">名称：</label>
                  <input
                    type="text"
                    id="name"
                    name="name"
                    value={aiModelSettings.name}
                    onChange={handleAiModelSettingChange}
                    style={{ marginLeft: '10px', padding: '5px', width: '200px' }}
                  />
                </div>
                <div>
                  <label htmlFor="provider">提供者：</label>
                  <select
                    id="provider"
                    name="provider"
                    value={aiModelSettings.provider}
                    onChange={handleAiModelSettingChange}
                    style={{ marginLeft: '10px', padding: '5px' }}
                  >
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="local">本地LLM</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="model">模型：</label>
                  <input
                    type="text"
                    id="model"
                    name="model"
                    value={aiModelSettings.model}
                    onChange={handleAiModelSettingChange}
                    style={{ marginLeft: '10px', padding: '5px', width: '200px' }}
                  />
                </div>
                <div>
                  <label htmlFor="api_key">API Key：</label>
                  <input
                    type="password"
                    id="api_key"
                    name="api_key"
                    value={aiModelSettings.api_key}
                    onChange={handleAiModelSettingChange}
                    style={{ marginLeft: '10px', padding: '5px', width: '200px' }}
                  />
                </div>
                <div style={{ gridColumn: '1 / span 2' }}>
                  <label htmlFor="base_url">Base URL：</label>
                  <input
                    type="text"
                    id="base_url"
                    name="base_url"
                    value={aiModelSettings.base_url}
                    onChange={handleAiModelSettingChange}
                    style={{ marginLeft: '10px', padding: '5px', width: '400px' }}
                  />
                </div>
                <div>
                  <label>
                    <input
                      type="checkbox"
                      name="enabled"
                      checked={aiModelSettings.enabled}
                      onChange={handleAiModelSettingChange}
                    />
                    启用
                  </label>
                </div>
              </div>
              <button
                onClick={editingAiModel ? handleUpdateAiModel : handleAddAiModel}
                disabled={loading}
                style={{
                  backgroundColor: '#27ae60',
                  color: 'white',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: '4px',
                  cursor: loading ? 'not-allowed' : 'pointer'
                }}
              >
                {loading ? '保存中...' : (editingAiModel ? '更新模型' : '添加模型')}
              </button>
              {editingAiModel && (
                <button
                  onClick={() => {
                    setEditingAiModel(null);
                    setAiModelSettings({
                      name: '',
                      provider: 'local',
                      model: 'llama3',
                      api_key: '',
                      base_url: 'http://localhost:11434/api/generate',
                      enabled: true
                    });
                  }}
                  style={{
                    marginLeft: '10px',
                    backgroundColor: '#95a5a6',
                    color: 'white',
                    border: 'none',
                    padding: '10px 20px',
                    borderRadius: '4px',
                    cursor: 'pointer'
                  }}
                >
                  取消
                </button>
              )}
            </div>

            <div style={{ marginBottom: '20px' }}>
              <h4>默认AI模型设置</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '20px', marginBottom: '20px' }}>
                <div>
                  <label htmlFor="default_provider">默认提供者：</label>
                  <select
                    id="default_provider"
                    name="default_provider"
                    value={defaultAiModel.default_provider}
                    onChange={handleDefaultAiModelChange}
                    style={{ marginLeft: '10px', padding: '5px' }}
                  >
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="local">本地LLM</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="default_model">默认模型：</label>
                  <input
                    type="text"
                    id="default_model"
                    name="default_model"
                    value={defaultAiModel.default_model}
                    onChange={handleDefaultAiModelChange}
                    style={{ marginLeft: '10px', padding: '5px', width: '200px' }}
                  />
                </div>
              </div>
              <button
                onClick={handleSetDefaultAiModel}
                disabled={loading}
                style={{
                  backgroundColor: '#3498db',
                  color: 'white',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: '4px',
                  cursor: loading ? 'not-allowed' : 'pointer'
                }}
              >
                {loading ? '保存中...' : '设置默认AI模型'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default Settings;