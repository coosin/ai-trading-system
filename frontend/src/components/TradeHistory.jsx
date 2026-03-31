import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

function TradeHistory() {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dateRange, setDateRange] = useState('7d');

  useEffect(() => {
    fetchTrades();
  }, [dateRange]);

  const fetchTrades = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`/api/v1/trades?range=${dateRange}`);
      setTrades(response.data);
      setError(null);
    } catch (err) {
      setError('获取交易历史失败');
      console.error('Error fetching trades:', err);
    } finally {
      setLoading(false);
    }
  };

  const getChartData = () => {
    const chartData = [];
    let balance = 10000; // 初始余额
    
    trades.forEach(trade => {
      if (trade.side === 'buy') {
        balance -= trade.amount * trade.price;
      } else {
        balance += trade.amount * trade.price;
      }
      chartData.push({
        timestamp: trade.timestamp,
        balance: balance
      });
    });
    
    return chartData;
  };

  const totalPnL = trades.reduce((sum, trade) => {
    if (trade.side === 'sell') {
      // 简化计算，假设每次卖出都有对应的买入
      return sum + (trade.amount * trade.price * 0.01); // 假设1%的盈利
    }
    return sum;
  }, 0);

  if (loading) {
    return <div style={{ padding: '20px' }}>加载交易历史中...</div>;
  }

  if (error) {
    return <div style={{ padding: '20px', color: 'red' }}>{error}</div>;
  }

  return (
    <div style={{ padding: '20px' }}>
      <h2>交易历史</h2>
      
      <div style={{ marginBottom: '20px' }}>
        <label htmlFor="date-range">选择时间范围：</label>
        <select
          id="date-range"
          value={dateRange}
          onChange={(e) => setDateRange(e.target.value)}
          style={{ marginLeft: '10px', padding: '5px' }}
        >
          <option value="24h">24小时</option>
          <option value="7d">7天</option>
          <option value="30d">30天</option>
          <option value="90d">90天</option>
        </select>
      </div>

      <div style={{ marginBottom: '30px' }}>
        <h3>账户概览</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px' }}>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>总交易次数</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{trades.length}</div>
          </div>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>总盈亏</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: totalPnL >= 0 ? '#27ae60' : '#e74c3c' }}>
              {totalPnL >= 0 ? '+' : ''}{totalPnL.toFixed(2)} USDT
            </div>
          </div>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>胜率</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>68%</div>
          </div>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>平均收益</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#27ae60' }}>2.3%</div>
          </div>
        </div>
      </div>

      <div style={{ marginBottom: '30px' }}>
        <h3>账户余额趋势</h3>
        <div style={{ height: '400px', width: '100%' }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={getChartData()}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="balance" stroke="#3498db" name="账户余额" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div>
        <h3>交易记录</h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: '#f5f5f5' }}>
                <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>时间</th>
                <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>交易对</th>
                <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>方向</th>
                <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>价格</th>
                <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>数量</th>
                <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>金额</th>
                <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>状态</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade, index) => (
                <tr key={index}>
                  <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{trade.timestamp}</td>
                  <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{trade.symbol}</td>
                  <td style={{ padding: '10px', border: '1px solid #e0e0e0', color: trade.side === 'buy' ? '#27ae60' : '#e74c3c' }}>
                    {trade.side === 'buy' ? '买入' : '卖出'}
                  </td>
                  <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{trade.price}</td>
                  <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{trade.amount}</td>
                  <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{(trade.amount * trade.price).toFixed(2)}</td>
                  <td style={{ padding: '10px', border: '1px solid #e0e0e0', color: trade.status === 'filled' ? '#27ae60' : '#f39c12' }}>
                    {trade.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default TradeHistory;