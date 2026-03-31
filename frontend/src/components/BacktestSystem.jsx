import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area } from 'recharts';

function BacktestSystem() {
  const [strategies, setStrategies] = useState([]);
  const [selectedStrategy, setSelectedStrategy] = useState('');
  const [timeRange, setTimeRange] = useState('1y');
  const [initialCapital, setInitialCapital] = useState(10000);
  const [backtestResult, setBacktestResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchStrategies();
  }, []);

  const fetchStrategies = async () => {
    try {
      const response = await axios.get('/api/v1/strategies');
      setStrategies(response.data);
      if (response.data.length > 0) {
        setSelectedStrategy(response.data[0].id);
      }
    } catch (error) {
      console.error('Error fetching strategies:', error);
    }
  };

  const runBacktest = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // 模拟回测请求
      // 实际项目中应该调用真实的回测API
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // 模拟回测结果
      const result = {
        strategy: selectedStrategy,
        time_range: timeRange,
        initial_capital: initialCapital,
        final_capital: initialCapital * 1.25,
        total_return: 25.0,
        max_drawdown: 12.5,
        sharpe_ratio: 1.8,
        win_rate: 65.0,
        total_trades: 124,
        average_trade: 0.2,
        equity_curve: generateEquityCurve(initialCapital, 25.0),
        drawdown_curve: generateDrawdownCurve(),
        trades: generateTradeData()
      };
      
      setBacktestResult(result);
    } catch (err) {
      setError('回测执行失败');
      console.error('Error running backtest:', err);
    } finally {
      setLoading(false);
    }
  };

  const generateEquityCurve = (initial, totalReturn) => {
    const curve = [];
    let value = initial;
    const steps = 100;
    const dailyReturn = Math.pow(1 + totalReturn / 100, 1 / steps) - 1;
    
    for (let i = 0; i <= steps; i++) {
      curve.push({
        date: new Date(Date.now() - (steps - i) * (365 / steps) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        equity: value
      });
      value *= (1 + dailyReturn);
    }
    
    return curve;
  };

  const generateDrawdownCurve = () => {
    const curve = [];
    let drawdown = 0;
    
    for (let i = 0; i <= 100; i++) {
      drawdown = Math.max(0, drawdown + (Math.random() - 0.5) * 2);
      curve.push({
        date: new Date(Date.now() - (100 - i) * (365 / 100) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        drawdown: drawdown
      });
    }
    
    return curve;
  };

  const generateTradeData = () => {
    const trades = [];
    const symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'ADA/USDT'];
    
    for (let i = 0; i < 20; i++) {
      const side = Math.random() > 0.5 ? 'buy' : 'sell';
      const symbol = symbols[Math.floor(Math.random() * symbols.length)];
      const price = Math.random() * 50000;
      const amount = Math.random() * 1;
      
      trades.push({
        id: i + 1,
        timestamp: new Date(Date.now() - Math.random() * 365 * 24 * 60 * 60 * 1000).toISOString(),
        symbol: symbol,
        side: side,
        price: price.toFixed(2),
        amount: amount.toFixed(4),
        pnl: (Math.random() * 100 - 50).toFixed(2)
      });
    }
    
    return trades;
  };

  return (
    <div style={{ padding: '20px' }}>
      <h2>回测系统</h2>
      
      <div style={{ marginBottom: '30px' }}>
        <h3>回测参数设置</h3>
        <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="strategy-select">选择策略：</label>
            <select
              id="strategy-select"
              value={selectedStrategy}
              onChange={(e) => setSelectedStrategy(e.target.value)}
              style={{ marginLeft: '10px', padding: '5px' }}
            >
              {strategies.map(strategy => (
                <option key={strategy.id} value={strategy.id}>{strategy.name}</option>
              ))}
            </select>
          </div>
          
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="time-range">时间范围：</label>
            <select
              id="time-range"
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              style={{ marginLeft: '10px', padding: '5px' }}
            >
              <option value="1m">1个月</option>
              <option value="3m">3个月</option>
              <option value="6m">6个月</option>
              <option value="1y">1年</option>
              <option value="2y">2年</option>
              <option value="5y">5年</option>
            </select>
          </div>
          
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="initial-capital">初始资金：</label>
            <input
              type="number"
              id="initial-capital"
              value={initialCapital}
              onChange={(e) => setInitialCapital(parseFloat(e.target.value) || 0)}
              min="1000"
              step="1000"
              style={{ marginLeft: '10px', padding: '5px', width: '150px' }}
            />
            <span style={{ marginLeft: '10px' }}>USDT</span>
          </div>
          
          <button
            onClick={runBacktest}
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
            {loading ? '执行中...' : '执行回测'}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#ffebee', color: '#c62828', borderRadius: '4px' }}>
          {error}
        </div>
      )}

      {backtestResult && (
        <div>
          <h3>回测结果</h3>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px', marginBottom: '30px' }}>
            <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
              <h4>总收益率</h4>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#27ae60' }}>
                +{backtestResult.total_return}%
              </div>
            </div>
            <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
              <h4>最大回撤</h4>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#e74c3c' }}>
                {backtestResult.max_drawdown}%
              </div>
            </div>
            <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
              <h4>夏普比率</h4>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#3498db' }}>
                {backtestResult.sharpe_ratio}
              </div>
            </div>
            <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
              <h4>胜率</h4>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#27ae60' }}>
                {backtestResult.win_rate}%
              </div>
            </div>
          </div>

          <div style={{ marginBottom: '30px' }}>
            <h4>资金曲线</h4>
            <div style={{ height: '400px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={backtestResult.equity_curve}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="equity" stroke="#3498db" name="资金" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div style={{ marginBottom: '30px' }}>
            <h4>回撤曲线</h4>
            <div style={{ height: '300px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={backtestResult.drawdown_curve}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Area type="monotone" dataKey="drawdown" stroke="#e74c3c" fill="#ffebee" name="回撤" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div>
            <h4>交易记录</h4>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f5f5f5' }}>
                    <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>时间</th>
                    <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>交易对</th>
                    <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>方向</th>
                    <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>价格</th>
                    <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>数量</th>
                    <th style={{ padding: '10px', border: '1px solid #e0e0e0' }}>盈亏</th>
                  </tr>
                </thead>
                <tbody>
                  {backtestResult.trades.map(trade => (
                    <tr key={trade.id}>
                      <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{trade.timestamp}</td>
                      <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{trade.symbol}</td>
                      <td style={{ padding: '10px', border: '1px solid #e0e0e0', color: trade.side === 'buy' ? '#27ae60' : '#e74c3c' }}>
                        {trade.side === 'buy' ? '买入' : '卖出'}
                      </td>
                      <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{trade.price}</td>
                      <td style={{ padding: '10px', border: '1px solid #e0e0e0' }}>{trade.amount}</td>
                      <td style={{ padding: '10px', border: '1px solid #e0e0e0', color: parseFloat(trade.pnl) >= 0 ? '#27ae60' : '#e74c3c' }}>
                        {parseFloat(trade.pnl) >= 0 ? '+' : ''}{trade.pnl}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default BacktestSystem;