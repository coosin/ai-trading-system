import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { useMarketData, useTechnicalIndicators, useAIMarketAnalysis, useExternalData } from '../hooks/useRealTimeData';

function MarketAnalysis() {
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT');
  const [selectedModel, setSelectedModel] = useState('astron-code-latest');
  const [aiModels, setAiModels] = useState([]);
  const [marketSentiment, setMarketSentiment] = useState(null);
  const [trendAnalysis, setTrendAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'ADA/USDT'];

  // 使用自定义Hooks获取真实数据
  const { data: marketData, loading: marketLoading } = useMarketData(selectedSymbol, '1h', 100);
  const { indicators: technicalIndicators, loading: indicatorsLoading } = useTechnicalIndicators(selectedSymbol);
  const { analysis: aiAnalysis, loading: analysisLoading, analyze: analyzeMarket } = useAIMarketAnalysis(selectedSymbol);

  // 加载AI模型列表
  useEffect(() => {
    loadAIModels();
  }, []);

  // 加载市场情绪数据
  useEffect(() => {
    loadMarketSentiment();
  }, [selectedSymbol]);

  // 加载趋势分析
  useEffect(() => {
    loadTrendAnalysis();
  }, [selectedSymbol]);

  const loadAIModels = async () => {
    try {
      const response = await api.aiModels.getAll();
      if (response.data && response.data.data) {
        const activeModels = response.data.data.filter(m => m.enabled);
        setAiModels(activeModels);
      }
    } catch (error) {
      console.error('加载AI模型失败:', error);
    }
  };

  const loadMarketSentiment = async () => {
    try {
      setLoading(true);
      // 从外部数据源获取市场情绪
      const response = await api.externalData.analyzeTrends(selectedSymbol);
      setMarketSentiment(response.data);
      setError(null);
    } catch (err) {
      console.error('获取市场情绪失败:', err);
      setError('获取市场情绪数据失败');
    } finally {
      setLoading(false);
    }
  };

  const loadTrendAnalysis = async () => {
    try {
      const response = await api.externalData.getSignals(selectedSymbol);
      setTrendAnalysis(response.data);
    } catch (err) {
      console.error('获取趋势分析失败:', err);
    }
  };

  const handleAIAnalyze = async () => {
    await analyzeMarket(selectedModel);
  };

  // 计算恐惧贪婪指数 (基于RSI和波动率)
  const calculateFearGreedIndex = () => {
    if (!technicalIndicators.rsi) return { value: 50, label: '中性', color: '#3498db' };
    
    const rsi = technicalIndicators.rsi;
    let value = 50;
    let label = '中性';
    let color = '#3498db';

    if (rsi > 70) {
      value = 80 + (rsi - 70) * 2;
      label = '贪婪';
      color = '#e74c3c';
    } else if (rsi < 30) {
      value = 20 - (30 - rsi) * 2;
      label = '恐惧';
      color = '#27ae60';
    } else if (rsi > 50) {
      value = 50 + (rsi - 50);
      label = '偏向贪婪';
      color = '#f39c12';
    } else {
      value = 50 - (50 - rsi);
      label = '偏向恐惧';
      color = '#9b59b6';
    }

    return { value: Math.min(100, Math.max(0, value)), label, color };
  };

  // 计算24h变化
  const calculate24hChange = () => {
    if (marketData.length < 2) return { value: 0, percent: 0 };
    const current = marketData[marketData.length - 1].close;
    const previous = marketData[0].close;
    const change = current - previous;
    const percent = (change / previous) * 100;
    return { value: change, percent };
  };

  // 计算波动率
  const calculateVolatility = () => {
    if (marketData.length < 2) return 0;
    const prices = marketData.map(d => d.close);
    const mean = prices.reduce((a, b) => a + b, 0) / prices.length;
    const variance = prices.reduce((sum, price) => sum + Math.pow(price - mean, 2), 0) / prices.length;
    const stdDev = Math.sqrt(variance);
    const volatility = (stdDev / mean) * 100;
    return volatility;
  };

  const fearGreed = calculateFearGreedIndex();
  const change24h = calculate24hChange();
  const volatility = calculateVolatility();

  if (loading || marketLoading) {
    return <div style={{ padding: '20px' }}>加载市场数据中...</div>;
  }

  if (error) {
    return <div style={{ padding: '20px', color: 'red' }}>{error}</div>;
  }

  return (
    <div style={{ padding: '20px' }}>
      <h2>📊 AI智能市场分析</h2>
      <p>基于真实市场数据和AI智能分析的行情预测</p>

      <div style={{ marginBottom: '20px', display: 'flex', gap: '15px', alignItems: 'center' }}>
        <div>
          <label htmlFor="symbol-select" style={{ marginRight: '10px' }}>选择交易对：</label>
          <select
            id="symbol-select"
            value={selectedSymbol}
            onChange={(e) => setSelectedSymbol(e.target.value)}
            style={{ padding: '8px', borderRadius: '4px', border: '1px solid #ced4da' }}
          >
            {symbols.map(symbol => (
              <option key={symbol} value={symbol}>{symbol}</option>
            ))}
          </select>
        </div>

        <div>
          <label style={{ marginRight: '10px' }}>AI模型：</label>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            style={{ padding: '8px', borderRadius: '4px', border: '1px solid #ced4da' }}
          >
            {aiModels.map(model => (
              <option key={model.model} value={model.model}>
                {model.name}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={handleAIAnalyze}
          disabled={analysisLoading}
          style={{
            padding: '8px 16px',
            backgroundColor: analysisLoading ? '#95a5a6' : '#3498db',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: analysisLoading ? 'not-allowed' : 'pointer'
          }}
        >
          {analysisLoading ? '分析中...' : '🤖 AI深度分析'}
        </button>
      </div>

      {/* 市场情绪指标 */}
      <div style={{ marginBottom: '30px' }}>
        <h3>市场情绪指标 (实时计算)</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px' }}>
          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>恐惧与贪婪指数</h4>
            <div style={{ 
              fontSize: '36px', 
              fontWeight: 'bold', 
              color: fearGreed.color 
            }}>
              {fearGreed.value.toFixed(0)}
            </div>
            <p style={{ color: fearGreed.color, fontWeight: 'bold' }}>{fearGreed.label}</p>
            <p style={{ fontSize: '12px', color: '#666' }}>基于RSI计算</p>
          </div>

          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>24h价格变化</h4>
            <div style={{ 
              fontSize: '36px', 
              fontWeight: 'bold', 
              color: change24h.percent > 0 ? '#27ae60' : change24h.percent < 0 ? '#e74c3c' : '#666'
            }}>
              {change24h.percent > 0 ? '+' : ''}{change24h.percent.toFixed(2)}%
            </div>
            <p style={{ fontSize: '14px', color: '#666' }}>
              ${change24h.value > 0 ? '+' : ''}{change24h.value.toFixed(2)}
            </p>
          </div>

          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>波动率</h4>
            <div style={{ 
              fontSize: '36px', 
              fontWeight: 'bold', 
              color: volatility > 20 ? '#e74c3c' : volatility > 10 ? '#f39c12' : '#27ae60'
            }}>
              {volatility.toFixed(2)}%
            </div>
            <p style={{ fontSize: '14px', color: '#666' }}>
              {volatility > 20 ? '高波动' : volatility > 10 ? '中等波动' : '低波动'}
            </p>
          </div>

          <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
            <h4>趋势信号</h4>
            <div style={{ 
              fontSize: '24px', 
              fontWeight: 'bold',
              color: trendAnalysis?.signal === 'buy' ? '#27ae60' : 
                     trendAnalysis?.signal === 'sell' ? '#e74c3c' : '#f39c12'
            }}>
              {trendAnalysis?.signal === 'buy' ? '🟢 买入' : 
               trendAnalysis?.signal === 'sell' ? '🔴 卖出' : 
               '⚪ 观望'}
            </div>
            <p style={{ fontSize: '12px', color: '#666' }}>
              置信度: {trendAnalysis?.confidence?.toFixed(1) || 0}%
            </p>
          </div>
        </div>
      </div>

      {/* 价格趋势图表 */}
      <div style={{ marginBottom: '30px' }}>
        <h3>价格趋势 (真实数据)</h3>
        <div style={{ height: '400px', width: '100%', backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={marketData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" tickFormatter={(time) => new Date(time).toLocaleTimeString()} />
              <YAxis domain={['auto', 'auto']} />
              <Tooltip 
                labelFormatter={(label) => new Date(label).toLocaleString()}
                formatter={(value) => [`$${value.toFixed(2)}`, '']}
              />
              <Legend />
              <Line type="monotone" dataKey="close" stroke="#3498db" name="收盘价" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="high" stroke="#2ecc71" name="最高价" strokeWidth={1} dot={false} />
              <Line type="monotone" dataKey="low" stroke="#e74c3c" name="最低价" strokeWidth={1} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 技术指标图表 */}
      {technicalIndicators && (
        <div style={{ marginBottom: '30px' }}>
          <h3>技术指标 (实时计算)</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '20px' }}>
            <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
              <h4>RSI 指标</h4>
              <div style={{ fontSize: '48px', fontWeight: 'bold', textAlign: 'center', color: 
                technicalIndicators.rsi > 70 ? '#e74c3c' : 
                technicalIndicators.rsi < 30 ? '#27ae60' : '#3498db'
              }}>
                {technicalIndicators.rsi?.toFixed(2) || 'N/A'}
              </div>
              <p style={{ textAlign: 'center', color: '#666' }}>
                {technicalIndicators.rsi > 70 ? '超买区域 - 可能回调' : 
                 technicalIndicators.rsi < 30 ? '超卖区域 - 可能反弹' : 
                 '中性区域'}
              </p>
            </div>

            <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
              <h4>MACD 指标</h4>
              <div style={{ fontSize: '48px', fontWeight: 'bold', textAlign: 'center', color:
                technicalIndicators.macd > 0 ? '#27ae60' : '#e74c3c'
              }}>
                {technicalIndicators.macd?.toFixed(4) || 'N/A'}
              </div>
              <p style={{ textAlign: 'center', color: '#666' }}>
                {technicalIndicators.macd > 0 ? '看涨信号 - MACD为正' : '看跌信号 - MACD为负'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* AI深度分析结果 */}
      {aiAnalysis && (
        <div style={{ marginBottom: '30px' }}>
          <h3>🤖 AI深度分析结果</h3>
          <div style={{ 
            backgroundColor: '#e3f2fd', 
            padding: '20px', 
            borderRadius: '8px',
            borderLeft: '4px solid #1976d2'
          }}>
            {typeof aiAnalysis === 'string' ? (
              <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: '14px', lineHeight: '1.6' }}>
                {aiAnalysis}
              </pre>
            ) : (
              <div>
                {Object.entries(aiAnalysis).map(([key, value]) => (
                  <div key={key} style={{ marginBottom: '10px' }}>
                    <strong style={{ color: '#1976d2' }}>{key}:</strong>
                    <span style={{ marginLeft: '10px' }}>
                      {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* AI市场预测 */}
      <div>
        <h3>AI市场预测</h3>
        <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px' }}>
            <div style={{ textAlign: 'center' }}>
              <h4>短期预测（24小时）</h4>
              <div style={{ 
                fontSize: '24px', 
                fontWeight: 'bold',
                color: trendAnalysis?.short_term === 'bullish' ? '#27ae60' : 
                       trendAnalysis?.short_term === 'bearish' ? '#e74c3c' : '#f39c12'
              }}>
                {trendAnalysis?.short_term === 'bullish' ? '看涨 📈' : 
                 trendAnalysis?.short_term === 'bearish' ? '看跌 📉' : 
                 '震荡 ➡️'}
              </div>
            </div>

            <div style={{ textAlign: 'center' }}>
              <h4>中期预测（7天）</h4>
              <div style={{ 
                fontSize: '24px', 
                fontWeight: 'bold',
                color: trendAnalysis?.medium_term === 'bullish' ? '#27ae60' : 
                       trendAnalysis?.medium_term === 'bearish' ? '#e74c3c' : '#f39c12'
              }}>
                {trendAnalysis?.medium_term === 'bullish' ? '看涨 📈' : 
                 trendAnalysis?.medium_term === 'bearish' ? '看跌 📉' : 
                 '震荡 ➡️'}
              </div>
            </div>

            <div style={{ textAlign: 'center' }}>
              <h4>预测置信度</h4>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#3498db' }}>
                {trendAnalysis?.confidence?.toFixed(1) || 0}%
              </div>
            </div>
          </div>

          {trendAnalysis?.reasoning && (
            <div style={{ marginTop: '20px', padding: '15px', backgroundColor: 'white', borderRadius: '4px' }}>
              <h4>分析依据</h4>
              <p style={{ lineHeight: '1.6' }}>{trendAnalysis.reasoning}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default MarketAnalysis;
