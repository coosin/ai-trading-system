import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

function MarketAnalysis() {
  const [marketData, setMarketData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT');

  useEffect(() => {
    fetchMarketData();
  }, [selectedSymbol]);

  const fetchMarketData = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`/api/v1/market/data?symbol=${selectedSymbol}`);
      setMarketData(response.data);
      setError(null);
    } catch (err) {
      setError('获取市场数据失败');
      console.error('Error fetching market data:', err);
    } finally {
      setLoading(false);
    }
  };

  const symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'ADA/USDT'];

  if (loading) {
    return <div style={{ padding: '20px' }}>加载市场数据中...</div>;
  }

  if (error) {
    return <div style={{ padding: '20px', color: 'red' }}>{error}</div>;
  }

  return (
    <div style={{ padding: '20px' }}>
      <h2>市场分析</h2>
      
      <div style={{ marginBottom: '20px' }}>
        <label htmlFor="symbol-select">选择交易对：</label>
        <select
          id="symbol-select"
          value={selectedSymbol}
          onChange={(e) => setSelectedSymbol(e.target.value)}
          style={{ marginLeft: '10px', padding: '5px' }}
        >
          {symbols.map(symbol => (
            <option key={symbol} value={symbol}>{symbol}</option>
          ))}
        </select>
      </div>

      <div style={{ marginBottom: '30px' }}>
        <h3>价格趋势</h3>
        <div style={{ height: '400px', width: '100%' }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={marketData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="close" stroke="#3498db" name="收盘价" />
              <Line type="monotone" dataKey="high" stroke="#2ecc71" name="最高价" />
              <Line type="monotone" dataKey="low" stroke="#e74c3c" name="最低价" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div style={{ marginBottom: '30px' }}>
        <h3>市场情绪分析</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px' }}>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>恐惧与贪婪指数</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#3498db' }}>52</div>
            <p>中性</p>
          </div>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>交易量变化</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#2ecc71' }}>+12.5%</div>
            <p>较昨日</p>
          </div>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>波动率</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#e67e22' }}>18.3%</div>
            <p>24小时</p>
          </div>
        </div>
      </div>

      <div>
        <h3>AI市场预测</h3>
        <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
          <p><strong>短期预测（24小时）：</strong> 看涨</p>
          <p><strong>中期预测（7天）：</strong> 震荡</p>
          <p><strong>长期预测（30天）：</strong> 看涨</p>
          <p><strong>预测置信度：</strong> 85%</p>
        </div>
      </div>
    </div>
  );
}

export default MarketAnalysis;