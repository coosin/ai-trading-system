import React, { useState } from 'react';

function DataExportImport() {
  const [activeTab, setActiveTab] = useState('export');
  const [exportData, setExportData] = useState({
    dataType: 'strategies',
    format: 'json',
    dateRange: '7d'
  });
  const [importData, setImportData] = useState({
    dataType: 'strategies',
    file: null
  });
  const [loading, setLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  const handleExportChange = (e) => {
    const { name, value } = e.target;
    setExportData(prev => ({ ...prev, [name]: value }));
  };

  const handleImportChange = (e) => {
    const { name, value, files } = e.target;
    if (name === 'file' && files.length > 0) {
      setImportData(prev => ({ ...prev, [name]: files[0] }));
    } else {
      setImportData(prev => ({ ...prev, [name]: value }));
    }
  };

  const handleExport = async () => {
    try {
      setLoading(true);
      setSuccessMessage('');
      setErrorMessage('');
      
      // 模拟导出数据
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // 创建模拟数据
      let data;
      if (exportData.dataType === 'strategies') {
        data = [
          {
            id: '1',
            name: '移动平均趋势跟踪',
            status: 'active',
            returns: '15.2',
            max_drawdown: '8.3',
            sharpe_ratio: '1.2',
            parameters: {
              fast_ma_period: 10,
              slow_ma_period: 30,
              stop_loss_pct: 0.05,
              take_profit_pct: 0.1
            },
            symbols: ['BTC/USDT', 'ETH/USDT'],
            timeframe: '1h'
          },
          {
            id: '2',
            name: '布林带均值回归',
            status: 'inactive',
            returns: '10.5',
            max_drawdown: '6.7',
            sharpe_ratio: '0.9',
            parameters: {
              bb_period: 20,
              bb_std: 2,
              stop_loss_pct: 0.04,
              take_profit_pct: 0.08
            },
            symbols: ['BTC/USDT'],
            timeframe: '4h'
          }
        ];
      } else if (exportData.dataType === 'trades') {
        data = [
          {
            id: '1',
            timestamp: '2024-01-01T12:30:00Z',
            symbol: 'BTC/USDT',
            side: 'buy',
            price: '49500',
            amount: '0.01',
            status: 'filled'
          },
          {
            id: '2',
            timestamp: '2024-01-01T11:45:00Z',
            symbol: 'ETH/USDT',
            side: 'sell',
            price: '2000',
            amount: '0.5',
            status: 'filled'
          }
        ];
      } else if (exportData.dataType === 'accounts') {
        data = [
          {
            id: '1',
            name: 'Binance 主账户',
            exchange: 'binance',
            balance: 12500.50,
            is_enabled: true,
            api_key: '********',
            api_secret: '********',
            passphrase: '********',
            created_at: '2023-01-01T00:00:00Z',
            last_sync: '2024-01-01T12:00:00Z'
          },
          {
            id: '2',
            name: 'OKX 测试账户',
            exchange: 'okx',
            balance: 5000.75,
            is_enabled: false,
            api_key: '********',
            api_secret: '********',
            passphrase: '********',
            created_at: '2023-02-01T00:00:00Z',
            last_sync: '2024-01-01T10:00:00Z'
          }
        ];
      } else if (exportData.dataType === 'settings') {
        data = {
          system: {
            system_name: '全智能量化交易系统',
            language: 'zh-CN',
            timezone: 'Asia/Shanghai',
            theme: 'light',
            auto_backup: true,
            backup_interval: 'daily',
            log_level: 'info'
          },
          risk: {
            max_drawdown: 10,
            max_position_size: 10,
            max_leverage: 3,
            stop_loss_enabled: true,
            take_profit_enabled: true,
            risk_per_trade: 2
          }
        };
      }
      
      // 生成文件
      const fileName = `openclaw-${exportData.dataType}-${new Date().toISOString().slice(0, 10)}.${exportData.format}`;
      let content, mimeType;
      
      if (exportData.format === 'json') {
        content = JSON.stringify(data, null, 2);
        mimeType = 'application/json';
      } else if (exportData.format === 'csv') {
        if (exportData.dataType === 'trades') {
          content = 'id,timestamp,symbol,side,price,amount,status\n';
          data.forEach(trade => {
            content += `${trade.id},${trade.timestamp},${trade.symbol},${trade.side},${trade.price},${trade.amount},${trade.status}\n`;
          });
        } else {
          content = 'id,name,status,returns\n';
          data.forEach(item => {
            content += `${item.id},${item.name},${item.status},${item.returns || 0}\n`;
          });
        }
        mimeType = 'text/csv';
      }
      
      // 下载文件
      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      setSuccessMessage('数据导出成功！');
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (error) {
      setErrorMessage('数据导出失败');
      console.error('Error exporting data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleImport = async () => {
    try {
      setLoading(true);
      setSuccessMessage('');
      setErrorMessage('');
      
      if (!importData.file) {
        setErrorMessage('请选择文件');
        return;
      }
      
      // 模拟导入数据
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      setSuccessMessage('数据导入成功！');
      setTimeout(() => setSuccessMessage(''), 3000);
      
      // 重置文件输入
      setImportData(prev => ({ ...prev, file: null }));
      document.getElementById('file-input').value = '';
    } catch (error) {
      setErrorMessage('数据导入失败');
      console.error('Error importing data:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '20px' }}>
      <h2>数据导出/导入</h2>
      
      {successMessage && (
        <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#e8f5e8', color: '#2e7d32', borderRadius: '4px' }}>
          {successMessage}
        </div>
      )}
      
      {errorMessage && (
        <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#ffebee', color: '#c62828', borderRadius: '4px' }}>
          {errorMessage}
        </div>
      )}
      
      <div style={{ marginBottom: '30px' }}>
        <div style={{ display: 'flex', borderBottom: '1px solid #e0e0e0', marginBottom: '20px' }}>
          <button
            onClick={() => setActiveTab('export')}
            style={{
              padding: '10px 20px',
              border: 'none',
              backgroundColor: activeTab === 'export' ? '#3498db' : 'transparent',
              color: activeTab === 'export' ? 'white' : '#333',
              cursor: 'pointer',
              borderTopLeftRadius: '4px',
              borderTopRightRadius: '4px'
            }}
          >
            数据导出
          </button>
          <button
            onClick={() => setActiveTab('import')}
            style={{
              padding: '10px 20px',
              border: 'none',
              backgroundColor: activeTab === 'import' ? '#3498db' : 'transparent',
              color: activeTab === 'import' ? 'white' : '#333',
              cursor: 'pointer',
              borderTopLeftRadius: '4px',
              borderTopRightRadius: '4px'
            }}
          >
            数据导入
          </button>
        </div>
        
        {activeTab === 'export' && (
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
            <h3>数据导出</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '20px', marginBottom: '20px' }}>
              <div>
                <label htmlFor="dataType">数据类型：</label>
                <select
                  id="dataType"
                  name="dataType"
                  value={exportData.dataType}
                  onChange={handleExportChange}
                  style={{ marginLeft: '10px', padding: '5px' }}
                >
                  <option value="strategies">交易策略</option>
                  <option value="trades">交易历史</option>
                  <option value="accounts">账户信息</option>
                  <option value="settings">系统设置</option>
                </select>
              </div>
              <div>
                <label htmlFor="format">导出格式：</label>
                <select
                  id="format"
                  name="format"
                  value={exportData.format}
                  onChange={handleExportChange}
                  style={{ marginLeft: '10px', padding: '5px' }}
                >
                  <option value="json">JSON</option>
                  <option value="csv">CSV</option>
                </select>
              </div>
              <div>
                <label htmlFor="dateRange">时间范围：</label>
                <select
                  id="dateRange"
                  name="dateRange"
                  value={exportData.dateRange}
                  onChange={handleExportChange}
                  style={{ marginLeft: '10px', padding: '5px' }}
                >
                  <option value="24h">24小时</option>
                  <option value="7d">7天</option>
                  <option value="30d">30天</option>
                  <option value="90d">90天</option>
                  <option value="all">全部</option>
                </select>
              </div>
            </div>
            <button
              onClick={handleExport}
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
              {loading ? '导出中...' : '导出数据'}
            </button>
          </div>
        )}
        
        {activeTab === 'import' && (
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
            <h3>数据导入</h3>
            <div style={{ marginBottom: '20px' }}>
              <div style={{ marginBottom: '15px' }}>
                <label htmlFor="importDataType">数据类型：</label>
                <select
                  id="importDataType"
                  name="dataType"
                  value={importData.dataType}
                  onChange={handleImportChange}
                  style={{ marginLeft: '10px', padding: '5px' }}
                >
                  <option value="strategies">交易策略</option>
                  <option value="trades">交易历史</option>
                  <option value="accounts">账户信息</option>
                  <option value="settings">系统设置</option>
                </select>
              </div>
              <div style={{ marginBottom: '15px' }}>
                <label htmlFor="file-input">选择文件：</label>
                <input
                  type="file"
                  id="file-input"
                  name="file"
                  accept=".json,.csv"
                  onChange={handleImportChange}
                  style={{ marginLeft: '10px' }}
                />
                {importData.file && (
                  <div style={{ marginTop: '10px', fontSize: '14px', color: '#666' }}>
                    已选择文件：{importData.file.name}
                  </div>
                )}
              </div>
              <div style={{ marginBottom: '15px', padding: '15px', backgroundColor: '#e3f2fd', borderRadius: '4px' }}>
                <h4>导入说明：</h4>
                <ul style={{ margin: '10px 0 0 0', paddingLeft: '20px' }}>
                  <li>支持导入 JSON 和 CSV 格式的文件</li>
                  <li>导入策略时，会覆盖同名策略</li>
                  <li>导入账户时，会添加新账户，不会覆盖已有账户</li>
                  <li>导入设置时，会合并设置，不会覆盖所有设置</li>
                </ul>
              </div>
            </div>
            <button
              onClick={handleImport}
              disabled={loading || !importData.file}
              style={{
                backgroundColor: '#3498db',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '4px',
                cursor: (loading || !importData.file) ? 'not-allowed' : 'pointer'
              }}
            >
              {loading ? '导入中...' : '导入数据'}
            </button>
          </div>
        )}
      </div>
      
      <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
        <h3>数据备份与恢复</h3>
        <div style={{ marginBottom: '20px' }}>
          <div style={{ marginBottom: '15px' }}>
            <button
              style={{
                backgroundColor: '#27ae60',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '4px',
                cursor: 'pointer',
                marginRight: '10px'
              }}
            >
              创建系统备份
            </button>
            <button
              style={{
                backgroundColor: '#f39c12',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              恢复系统备份
            </button>
          </div>
          <div style={{ padding: '15px', backgroundColor: '#e3f2fd', borderRadius: '4px' }}>
            <h4>备份说明：</h4>
            <ul style={{ margin: '10px 0 0 0', paddingLeft: '20px' }}>
              <li>系统备份包含所有策略、账户、设置和交易历史</li>
              <li>备份文件会保存在系统指定目录</li>
              <li>建议定期创建备份以防止数据丢失</li>
              <li>恢复备份会覆盖当前系统数据，请谨慎操作</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

export default DataExportImport;