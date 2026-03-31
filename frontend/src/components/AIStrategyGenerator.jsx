import React, { useState } from 'react';
import axios from 'axios';

function AIStrategyGenerator() {
  const [marketCondition, setMarketCondition] = useState('trending');
  const [timeframe, setTimeframe] = useState('1h');
  const [riskLevel, setRiskLevel] = useState('medium');
  const [symbols, setSymbols] = useState('BTC/USDT, ETH/USDT');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [generatedStrategy, setGeneratedStrategy] = useState(null);

  const generateStrategy = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // 模拟AI策略生成请求
      // 实际项目中应该调用真实的AI策略生成API
      await new Promise(resolve => setTimeout(resolve, 3000));
      
      // 模拟生成的策略
      const strategy = {
        name: `AI生成策略_${Date.now()}`,
        market_condition: marketCondition,
        timeframe: timeframe,
        risk_level: riskLevel,
        symbols: symbols.split(',').map(s => s.trim()),
        parameters: {
          fast_ma_period: 10,
          slow_ma_period: 30,
          rsi_period: 14,
          rsi_overbought: 70,
          rsi_oversold: 30,
          macd_fast: 12,
          macd_slow: 26,
          macd_signal: 9,
          stop_loss_pct: riskLevel === 'high' ? 0.08 : riskLevel === 'medium' ? 0.05 : 0.03,
          take_profit_pct: riskLevel === 'high' ? 0.15 : riskLevel === 'medium' ? 0.1 : 0.06,
          position_size_pct: riskLevel === 'high' ? 0.2 : riskLevel === 'medium' ? 0.1 : 0.05
        },
        logic: `
// 策略逻辑
if (market_condition === 'trending') {
  // 趋势跟踪策略
  if (fast_ma > slow_ma && rsi < 70) {
    enter_long();
  } else if (fast_ma < slow_ma && rsi > 30) {
    enter_short();
  }
} else if (market_condition === 'range') {
  // 区间交易策略
  if (price < support && rsi < 30) {
    enter_long();
  } else if (price > resistance && rsi > 70) {
    enter_short();
  }
} else if (market_condition === 'volatile') {
  // 波动策略
  if (macd_histogram > 0 && rsi < 60) {
    enter_long();
  } else if (macd_histogram < 0 && rsi > 40) {
    enter_short();
  }
}

// 风险管理
if (current_drawdown > max_drawdown) {
  close_all_positions();
  pause_trading();
}
        `,
        expected_performance: {
          expected_return: riskLevel === 'high' ? '25-35%' : riskLevel === 'medium' ? '15-25%' : '8-15%',
          expected_max_drawdown: riskLevel === 'high' ? '15-20%' : riskLevel === 'medium' ? '10-15%' : '5-10%',
          expected_sharpe_ratio: riskLevel === 'high' ? '1.2-1.5' : riskLevel === 'medium' ? '1.5-1.8' : '1.8-2.2',
          recommended_timeframe: timeframe
        }
      };
      
      setGeneratedStrategy(strategy);
    } catch (err) {
      setError('策略生成失败');
      console.error('Error generating strategy:', err);
    } finally {
      setLoading(false);
    }
  };

  const saveStrategy = async () => {
    if (!generatedStrategy) return;
    
    try {
      setLoading(true);
      
      // 模拟保存策略请求
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      alert('策略保存成功！');
    } catch (err) {
      setError('策略保存失败');
      console.error('Error saving strategy:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '20px' }}>
      <h2>智能策略生成</h2>
      
      <div style={{ marginBottom: '30px' }}>
        <h3>策略参数设置</h3>
        <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="market-condition">市场条件：</label>
            <select
              id="market-condition"
              value={marketCondition}
              onChange={(e) => setMarketCondition(e.target.value)}
              style={{ marginLeft: '10px', padding: '5px' }}
            >
              <option value="trending">趋势市场</option>
              <option value="range">区间市场</option>
              <option value="volatile">高波动市场</option>
            </select>
          </div>
          
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="timeframe">时间周期：</label>
            <select
              id="timeframe"
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              style={{ marginLeft: '10px', padding: '5px' }}
            >
              <option value="1m">1分钟</option>
              <option value="5m">5分钟</option>
              <option value="15m">15分钟</option>
              <option value="1h">1小时</option>
              <option value="4h">4小时</option>
              <option value="1d">1天</option>
            </select>
          </div>
          
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="risk-level">风险等级：</label>
            <select
              id="risk-level"
              value={riskLevel}
              onChange={(e) => setRiskLevel(e.target.value)}
              style={{ marginLeft: '10px', padding: '5px' }}
            >
              <option value="low">低风险</option>
              <option value="medium">中风险</option>
              <option value="high">高风险</option>
            </select>
          </div>
          
          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="symbols">交易对：</label>
            <input
              type="text"
              id="symbols"
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
              placeholder="例如：BTC/USDT, ETH/USDT"
              style={{ marginLeft: '10px', padding: '5px', width: '300px' }}
            />
          </div>
          
          <button
            onClick={generateStrategy}
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
            {loading && !generatedStrategy ? '生成中...' : '生成策略'}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#ffebee', color: '#c62828', borderRadius: '4px' }}>
          {error}
        </div>
      )}

      {generatedStrategy && (
        <div style={{ marginBottom: '30px' }}>
          <h3>生成的策略</h3>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
            <div style={{ marginBottom: '20px' }}>
              <h4>策略信息</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '15px' }}>
                <div>
                  <strong>策略名称：</strong>{generatedStrategy.name}
                </div>
                <div>
                  <strong>市场条件：</strong>{marketCondition === 'trending' ? '趋势市场' : marketCondition === 'range' ? '区间市场' : '高波动市场'}
                </div>
                <div>
                  <strong>时间周期：</strong>{timeframe}
                </div>
                <div>
                  <strong>风险等级：</strong>{riskLevel === 'low' ? '低风险' : riskLevel === 'medium' ? '中风险' : '高风险'}
                </div>
                <div colSpan="2">
                  <strong>交易对：</strong>{generatedStrategy.symbols.join(', ')}
                </div>
              </div>
            </div>
            
            <div style={{ marginBottom: '20px' }}>
              <h4>策略参数</h4>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#e9ecef' }}>
                      <th style={{ padding: '10px', border: '1px solid #dee2e6' }}>参数</th>
                      <th style={{ padding: '10px', border: '1px solid #dee2e6' }}>值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(generatedStrategy.parameters).map(([key, value]) => (
                      <tr key={key}>
                        <td style={{ padding: '10px', border: '1px solid #dee2e6' }}>
                          {key.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </td>
                        <td style={{ padding: '10px', border: '1px solid #dee2e6' }}>{value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            
            <div style={{ marginBottom: '20px' }}>
              <h4>策略逻辑</h4>
              <pre style={{ backgroundColor: '#f1f3f4', padding: '15px', borderRadius: '4px', overflowX: 'auto' }}>
                {generatedStrategy.logic}
              </pre>
            </div>
            
            <div style={{ marginBottom: '20px' }}>
              <h4>预期表现</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '15px' }}>
                <div>
                  <strong>预期收益率：</strong>{generatedStrategy.expected_performance.expected_return}
                </div>
                <div>
                  <strong>预期最大回撤：</strong>{generatedStrategy.expected_performance.expected_max_drawdown}
                </div>
                <div>
                  <strong>预期夏普比率：</strong>{generatedStrategy.expected_performance.expected_sharpe_ratio}
                </div>
                <div>
                  <strong>推荐时间周期：</strong>{generatedStrategy.expected_performance.recommended_timeframe}
                </div>
              </div>
            </div>
            
            <div style={{ marginTop: '20px' }}>
              <button
                onClick={saveStrategy}
                disabled={loading}
                style={{
                  backgroundColor: '#27ae60',
                  color: 'white',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: '4px',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  marginRight: '10px'
                }}
              >
                保存策略
              </button>
              <button
                onClick={() => setGeneratedStrategy(null)}
                style={{
                  backgroundColor: '#95a5a6',
                  color: 'white',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: '4px',
                  cursor: 'pointer'
                }}
              >
                重新生成
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AIStrategyGenerator;