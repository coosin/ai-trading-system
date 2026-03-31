import React, { useState, useEffect } from 'react';
import axios from 'axios';

function AccountManagement() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeAccount, setActiveAccount] = useState(null);
  const [newAccount, setNewAccount] = useState({
    name: '',
    exchange: '',
    api_key: '',
    api_secret: '',
    passphrase: '',
    is_enabled: true
  });
  const [showAddForm, setShowAddForm] = useState(false);

  useEffect(() => {
    fetchAccounts();
  }, []);

  const fetchAccounts = async () => {
    try {
      setLoading(true);
      // 模拟获取账户列表
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      const mockAccounts = [
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
        },
        {
          id: '3',
          name: 'Bybit 交易账户',
          exchange: 'bybit',
          balance: 8750.25,
          is_enabled: true,
          api_key: '********',
          api_secret: '********',
          passphrase: '********',
          created_at: '2023-03-01T00:00:00Z',
          last_sync: '2024-01-01T11:00:00Z'
        }
      ];
      
      setAccounts(mockAccounts);
      if (mockAccounts.length > 0) {
        setActiveAccount(mockAccounts[0]);
      }
    } catch (err) {
      setError('获取账户列表失败');
      console.error('Error fetching accounts:', err);
    } finally {
      setLoading(false);
    }
  };

  const toggleAccountStatus = async (accountId) => {
    try {
      setLoading(true);
      // 模拟切换账户状态
      await new Promise(resolve => setTimeout(resolve, 500));
      
      setAccounts(prev => prev.map(account => 
        account.id === accountId 
          ? { ...account, is_enabled: !account.is_enabled }
          : account
      ));
    } catch (err) {
      setError('切换账户状态失败');
      console.error('Error toggling account status:', err);
    } finally {
      setLoading(false);
    }
  };

  const addAccount = async (e) => {
    e.preventDefault();
    try {
      setLoading(true);
      // 模拟添加账户
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      const account = {
        id: Date.now().toString(),
        ...newAccount,
        balance: 0,
        created_at: new Date().toISOString(),
        last_sync: new Date().toISOString()
      };
      
      setAccounts(prev => [...prev, account]);
      setActiveAccount(account);
      setNewAccount({
        name: '',
        exchange: '',
        api_key: '',
        api_secret: '',
        passphrase: '',
        is_enabled: true
      });
      setShowAddForm(false);
    } catch (err) {
      setError('添加账户失败');
      console.error('Error adding account:', err);
    } finally {
      setLoading(false);
    }
  };

  const deleteAccount = async (accountId) => {
    if (!window.confirm('确定要删除这个账户吗？')) return;
    
    try {
      setLoading(true);
      // 模拟删除账户
      await new Promise(resolve => setTimeout(resolve, 500));
      
      setAccounts(prev => prev.filter(account => account.id !== accountId));
      if (activeAccount && activeAccount.id === accountId) {
        setActiveAccount(accounts.length > 1 ? accounts.find(a => a.id !== accountId) : null);
      }
    } catch (err) {
      setError('删除账户失败');
      console.error('Error deleting account:', err);
    } finally {
      setLoading(false);
    }
  };

  const syncAccount = async (accountId) => {
    try {
      setLoading(true);
      // 模拟同步账户
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      setAccounts(prev => prev.map(account => 
        account.id === accountId 
          ? { ...account, last_sync: new Date().toISOString(), balance: account.balance * (1 + (Math.random() - 0.5) * 0.1) }
          : account
      ));
    } catch (err) {
      setError('同步账户失败');
      console.error('Error syncing account:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div style={{ padding: '20px' }}>加载账户列表中...</div>;
  }

  if (error) {
    return <div style={{ padding: '20px', color: 'red' }}>{error}</div>;
  }

  return (
    <div style={{ padding: '20px' }}>
      <h2>多账户管理</h2>
      
      <div style={{ marginBottom: '30px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3>账户列表</h3>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            style={{
              backgroundColor: '#3498db',
              color: 'white',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            {showAddForm ? '取消' : '添加账户'}
          </button>
        </div>
        
        {showAddForm && (
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
            <h4>添加新账户</h4>
            <form onSubmit={addAccount}>
              <div style={{ marginBottom: '15px' }}>
                <label htmlFor="account-name">账户名称：</label>
                <input
                  type="text"
                  id="account-name"
                  value={newAccount.name}
                  onChange={(e) => setNewAccount({ ...newAccount, name: e.target.value })}
                  required
                  style={{ marginLeft: '10px', padding: '5px', width: '200px' }}
                />
              </div>
              
              <div style={{ marginBottom: '15px' }}>
                <label htmlFor="exchange">交易所：</label>
                <select
                  id="exchange"
                  value={newAccount.exchange}
                  onChange={(e) => setNewAccount({ ...newAccount, exchange: e.target.value })}
                  required
                  style={{ marginLeft: '10px', padding: '5px' }}
                >
                  <option value="">选择交易所</option>
                  <option value="binance">Binance</option>
                  <option value="okx">OKX</option>
                  <option value="bybit">Bybit</option>
                  <option value="ftx">FTX</option>
                  <option value="huobi">Huobi</option>
                </select>
              </div>
              
              <div style={{ marginBottom: '15px' }}>
                <label htmlFor="api-key">API Key：</label>
                <input
                  type="text"
                  id="api-key"
                  value={newAccount.api_key}
                  onChange={(e) => setNewAccount({ ...newAccount, api_key: e.target.value })}
                  required
                  style={{ marginLeft: '10px', padding: '5px', width: '300px' }}
                />
              </div>
              
              <div style={{ marginBottom: '15px' }}>
                <label htmlFor="api-secret">API Secret：</label>
                <input
                  type="password"
                  id="api-secret"
                  value={newAccount.api_secret}
                  onChange={(e) => setNewAccount({ ...newAccount, api_secret: e.target.value })}
                  required
                  style={{ marginLeft: '10px', padding: '5px', width: '300px' }}
                />
              </div>
              
              <div style={{ marginBottom: '15px' }}>
                <label htmlFor="passphrase">Passphrase（如果需要）：</label>
                <input
                  type="password"
                  id="passphrase"
                  value={newAccount.passphrase}
                  onChange={(e) => setNewAccount({ ...newAccount, passphrase: e.target.value })}
                  style={{ marginLeft: '10px', padding: '5px', width: '300px' }}
                />
              </div>
              
              <div style={{ marginBottom: '15px' }}>
                <label>
                  <input
                    type="checkbox"
                    checked={newAccount.is_enabled}
                    onChange={(e) => setNewAccount({ ...newAccount, is_enabled: e.target.checked })}
                  />
                  启用账户
                </label>
              </div>
              
              <button
                type="submit"
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
                {loading ? '添加中...' : '添加账户'}
              </button>
            </form>
          </div>
        )}
        
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: '#f5f5f5' }}>
                <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>账户名称</th>
                <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>交易所</th>
                <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>余额 (USDT)</th>
                <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>状态</th>
                <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>最后同步</th>
                <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map(account => (
                <tr key={account.id}>
                  <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{account.name}</td>
                  <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{account.exchange.toUpperCase()}</td>
                  <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{account.balance.toFixed(2)}</td>
                  <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>
                    <span style={{ 
                      padding: '5px 10px', 
                      borderRadius: '12px', 
                      backgroundColor: account.is_enabled ? '#e8f5e8' : '#ffebee',
                      color: account.is_enabled ? '#2e7d32' : '#c62828',
                      fontSize: '12px'
                    }}>
                      {account.is_enabled ? '启用' : '禁用'}
                    </span>
                  </td>
                  <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>
                    {new Date(account.last_sync).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>
                    <button
                      onClick={() => toggleAccountStatus(account.id)}
                      style={{
                        marginRight: '5px',
                        padding: '5px 10px',
                        backgroundColor: account.is_enabled ? '#e74c3c' : '#27ae60',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer'
                      }}
                    >
                      {account.is_enabled ? '禁用' : '启用'}
                    </button>
                    <button
                      onClick={() => syncAccount(account.id)}
                      style={{
                        marginRight: '5px',
                        padding: '5px 10px',
                        backgroundColor: '#3498db',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer'
                      }}
                    >
                      同步
                    </button>
                    <button
                      onClick={() => setActiveAccount(account)}
                      style={{
                        marginRight: '5px',
                        padding: '5px 10px',
                        backgroundColor: '#f39c12',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer'
                      }}
                    >
                      详情
                    </button>
                    <button
                      onClick={() => deleteAccount(account.id)}
                      style={{
                        padding: '5px 10px',
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
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {activeAccount && (
        <div style={{ marginBottom: '30px' }}>
          <h3>账户详情 - {activeAccount.name}</h3>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '15px', marginBottom: '20px' }}>
              <div>
                <strong>交易所：</strong>{activeAccount.exchange.toUpperCase()}
              </div>
              <div>
                <strong>账户余额：</strong>{activeAccount.balance.toFixed(2)} USDT
              </div>
              <div>
                <strong>状态：</strong>{activeAccount.is_enabled ? '启用' : '禁用'}
              </div>
              <div>
                <strong>创建时间：</strong>{new Date(activeAccount.created_at).toLocaleString()}
              </div>
              <div>
                <strong>最后同步：</strong>{new Date(activeAccount.last_sync).toLocaleString()}
              </div>
              <div>
                <strong>API Key：</strong>{activeAccount.api_key}
              </div>
            </div>
            
            <div style={{ marginBottom: '20px' }}>
              <h4>账户资产分布</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '15px' }}>
                <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '8px', textAlign: 'center' }}>
                  <h5>BTC</h5>
                  <div style={{ fontSize: '18px', fontWeight: 'bold' }}>0.1234</div>
                  <div style={{ color: '#666' }}>价值: 6,170 USDT</div>
                </div>
                <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '8px', textAlign: 'center' }}>
                  <h5>ETH</h5>
                  <div style={{ fontSize: '18px', fontWeight: 'bold' }}>2.3456</div>
                  <div style={{ color: '#666' }}>价值: 4,691 USDT</div>
                </div>
                <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '8px', textAlign: 'center' }}>
                  <h5>USDT</h5>
                  <div style={{ fontSize: '18px', fontWeight: 'bold' }}>1,639.50</div>
                  <div style={{ color: '#666' }}>价值: 1,639.50 USDT</div>
                </div>
              </div>
            </div>
            
            <div>
              <h4>近期交易</h4>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#e9ecef' }}>
                      <th style={{ padding: '8px', border: '1px solid #dee2e6' }}>时间</th>
                      <th style={{ padding: '8px', border: '1px solid #dee2e6' }}>交易对</th>
                      <th style={{ padding: '8px', border: '1px solid #dee2e6' }}>方向</th>
                      <th style={{ padding: '8px', border: '1px solid #dee2e6' }}>价格</th>
                      <th style={{ padding: '8px', border: '1px solid #dee2e6' }}>数量</th>
                      <th style={{ padding: '8px', border: '1px solid #dee2e6' }}>金额</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>2024-01-01 12:00:00</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>BTC/USDT</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6', color: '#27ae60' }}>买入</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>50,000</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>0.01</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>500</td>
                    </tr>
                    <tr>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>2024-01-01 11:30:00</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>ETH/USDT</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6', color: '#e74c3c' }}>卖出</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>2,000</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>0.5</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>1,000</td>
                    </tr>
                    <tr>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>2024-01-01 10:15:00</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>BTC/USDT</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6', color: '#27ae60' }}>买入</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>49,500</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>0.02</td>
                      <td style={{ padding: '8px', border: '1px solid #dee2e6' }}>990</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AccountManagement;