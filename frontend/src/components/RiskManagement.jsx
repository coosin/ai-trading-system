import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

function RiskManagement() {
  const [riskMetrics, setRiskMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchRiskMetrics();
  }, []);

  const fetchRiskMetrics = async () => {
    try {
      setLoading(true);
      const response = await axios.get('/api/v1/risk/metrics');
      setRiskMetrics(response.data);
      setError(null);
    } catch (err) {
      setError('获取风险指标失败');
      console.error('Error fetching risk metrics:', err);
    } finally {
      setLoading(false);
    }
  };

  const positionData = [
    { name: 'BTC/USDT', value: 45 },
    { name: 'ETH/USDT', value: 25 },
    { name: 'BNB/USDT', value: 15 },
    { name: 'SOL/USDT', value: 10 },
    { name: 'ADA/USDT', value: 5 }
  ];

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];

  if (loading) {
    return <div style={{ padding: '20px' }}>加载风险指标中...</div>;
  }

  if (error) {
    return <div style={{ padding: '20px', color: 'red' }}>{error}</div>;
  }

  return (
    <div style={{ padding: '20px' }}>
      <h2>风险管理</h2>

      <div style={{ marginBottom: '30px' }}>
        <h3>风险指标概览</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px' }}>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>最大回撤</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#e74c3c' }}>8.2%</div>
            <p>过去30天</p>
          </div>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>夏普比率</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#2ecc71' }}>2.3</div>
            <p>年化</p>
          </div>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>VaR (95%)</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#3498db' }}>2.5%</div>
            <p>每日</p>
          </div>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>风险敞口</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#9b59b6' }}>42%</div>
            <p>总资金</p>
          </div>
        </div>
      </div>

      <div style={{ marginBottom: '30px' }}>
        <h3>资产配置</h3>
        <div style={{ height: '400px', width: '100%' }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={positionData}
                cx="50%"
                cy="50%"
                labelLine={false}
                outerRadius={150}
                fill="#8884d8"
                dataKey="value"
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              >
                {positionData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div style={{ marginBottom: '30px' }}>
        <h3>风险控制设置</h3>
        <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="max-drawdown">最大回撤限制：</label>
            <input
              type="number"
              id="max-drawdown"
              defaultValue={10}
              min={1}
              max={50}
              style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
            />
            <span style={{ marginLeft: '10px' }}>%</span>
          </div>
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="position-size">单笔最大仓位：</label>
            <input
              type="number"
              id="position-size"
              defaultValue={10}
              min={1}
              max={50}
              style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
            />
            <span style={{ marginLeft: '10px' }}>%</span>
          </div>
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="leverage">最大杠杆：</label>
            <input
              type="number"
              id="leverage"
              defaultValue={3}
              min={1}
              max={100}
              style={{ marginLeft: '10px', padding: '5px', width: '100px' }}
            />
          </div>
          <button
            style={{
              backgroundColor: '#3498db',
              color: 'white',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            保存设置
          </button>
        </div>
      </div>

      <div>
        <h3>风险警报</h3>
        <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
          <ul style={{ listStyle: 'none', padding: 0 }}>
            <li style={{ marginBottom: '10px', padding: '10px', backgroundColor: '#e7f3ff', borderRadius: '4px' }}>
              <strong>低风险：</strong> 市场波动率正常，无异常情况
            </li>
            <li style={{ marginBottom: '10px', padding: '10px', backgroundColor: '#e7f3ff', borderRadius: '4px' }}>
              <strong>低风险：</strong> 资产配置符合风险控制要求
            </li>
            <li style={{ marginBottom: '10px', padding: '10px', backgroundColor: '#fff3e0', borderRadius: '4px' }}>
              <strong>中风险：</strong> BTC价格波动较大，建议关注
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default RiskManagement;