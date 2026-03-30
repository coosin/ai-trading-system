import React, { useState, useEffect } from 'react';
import axios from 'axios';

const TradingStrategies = () => {
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStrategies();
  }, []);

  const fetchStrategies = async () => {
    try {
      const response = await axios.get('/api/v1/strategies');
      setStrategies(response.data);
    } catch (error) {
      console.error('Error fetching strategies:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div>加载中...</div>;
  }

  return (
    <div style={{ backgroundColor: 'white', padding: '20px', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
      <h2>交易策略</h2>
      <div style={{ marginBottom: '20px' }}>
        <button style={{
          padding: '10px 20px',
          backgroundColor: '#3498db',
          color: 'white',
          border: 'none',
          borderRadius: '4px',
          cursor: 'pointer'
        }}>
          创建新策略
        </button>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ backgroundColor: '#f5f5f5' }}>
              <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>策略名称</th>
              <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>状态</th>
              <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>收益率</th>
              <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>最大回撤</th>
              <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>夏普比率</th>
              <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {strategies.map((strategy) => (
              <tr key={strategy.id}>
                <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{strategy.name}</td>
                <td style={{ padding: '10px', border: '1px solid #e0e0e0', color: strategy.status === 'active' ? '#27ae60' : '#e74c3c' }}>
                  {strategy.status}
                </td>
                <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>
                  {strategy.returns}%
                </td>
                <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>
                  {strategy.max_drawdown}%
                </td>
                <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>
                  {strategy.sharpe_ratio}
                </td>
                <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>
                  <button style={{
                    marginRight: '10px',
                    padding: '5px 10px',
                    backgroundColor: '#27ae60',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer'
                  }}>
                    启动
                  </button>
                  <button style={{
                    marginRight: '10px',
                    padding: '5px 10px',
                    backgroundColor: '#e74c3c',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer'
                  }}>
                    停止
                  </button>
                  <button style={{
                    padding: '5px 10px',
                    backgroundColor: '#f39c12',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer'
                  }}>
                    编辑
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default TradingStrategies;