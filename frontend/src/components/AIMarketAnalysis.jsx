import React, { useState, useEffect } from 'react';
import { api } from '../services/api';

function AIMarketAnalysis() {
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT');
  const [selectedModel, setSelectedModel] = useState('astron-code-latest');
  const [aiModels, setAiModels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [strategyResult, setStrategyResult] = useState(null);
  const [signalResult, setSignalResult] = useState(null);
  const [marketData, setMarketData] = useState({
    symbol: 'BTC/USDT',
    price: 67750.0,
    volume_24h: 35000000000,
    change_24h: 2.5,
    high_24h: 68500.0,
    low_24h: 65800.0,
    indicators: {
      rsi: 65,
      macd: 'bullish',
      ema_20: 67200.0,
      ema_50: 66500.0,
      sma_20: 67100.0,
      sma_50: 66400.0,
      bollinger_upper: 69500.0,
      bollinger_lower: 65500.0
    },
    market_sentiment: 'neutral',
    funding_rate: 0.0001,
    open_interest: 15000000000
  });

  const symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT'];

  useEffect(() => {
    loadAIModels();
  }, []);

  const loadAIModels = async () => {
    try {
      const response = await api.aiModels.getAll();
      if (response.data && response.data.data) {
        const activeModels = response.data.data.filter(m => m.enabled);
        setAiModels(activeModels);
        if (activeModels.length > 0) {
          setSelectedModel(activeModels[0].model);
        }
      }
    } catch (error) {
      console.error('加载AI模型失败:', error);
      // 使用默认模型
      setAiModels([
        { id: 8, name: '讯飞', model: 'astron-code-latest', enabled: true },
        { id: 3, name: 'DeepSeek Chat', model: 'deepseek-chat', enabled: true }
      ]);
    }
  };

  const handleAnalyzeMarket = async () => {
    setLoading(true);
    setAnalysisResult(null);
    try {
      const data = { ...marketData, symbol: selectedSymbol };
      const response = await api.ai.analyzeMarket(data, selectedModel);
      if (response.data && response.data.status === 'success') {
        setAnalysisResult(response.data.data);
      } else {
        setAnalysisResult({ error: response.data?.message || '分析失败' });
      }
    } catch (error) {
      console.error('AI市场分析失败:', error);
      setAnalysisResult({ error: error.message || '分析请求失败' });
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateStrategy = async () => {
    setLoading(true);
    setStrategyResult(null);
    try {
      const analysis = analysisResult || { trend: 'neutral', confidence: 0.5 };
      const response = await api.ai.generateStrategy(analysis, selectedModel);
      if (response.data && response.data.status === 'success') {
        setStrategyResult(response.data.data);
      } else {
        setStrategyResult({ error: response.data?.message || '策略生成失败' });
      }
    } catch (error) {
      console.error('AI策略生成失败:', error);
      setStrategyResult({ error: error.message || '策略请求失败' });
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateSignal = async () => {
    setLoading(true);
    setSignalResult(null);
    try {
      const data = { ...marketData, symbol: selectedSymbol };
      const response = await api.ai.generateSignal(data, selectedModel);
      if (response.data && response.data.status === 'success') {
        setSignalResult(response.data.data);
      } else {
        setSignalResult({ error: response.data?.message || '信号生成失败' });
      }
    } catch (error) {
      console.error('AI信号生成失败:', error);
      setSignalResult({ error: error.message || '信号请求失败' });
    } finally {
      setLoading(false);
    }
  };

  const handleMarketDataChange = (field, value) => {
    setMarketData(prev => ({
      ...prev,
      [field]: parseFloat(value) || 0
    }));
  };

  const handleIndicatorChange = (indicator, value) => {
    setMarketData(prev => ({
      ...prev,
      indicators: {
        ...prev.indicators,
        [indicator]: value
      }
    }));
  };

  return (
    <div style={{ padding: '20px' }}>
      <h2>🤖 AI 智能市场分析</h2>
      <p>使用 AI 模型分析市场行情，生成交易策略和交易信号</p>

      {/* 配置区域 */}
      <div style={{ 
        backgroundColor: '#f8f9fa', 
        padding: '20px', 
        borderRadius: '8px',
        marginBottom: '20px'
      }}>
        <h3>⚙️ 分析配置</h3>
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
          gap: '20px',
          marginTop: '15px'
        }}>
          <div>
            <label style={{ display: 'block', marginBottom: '5px', fontSize: '14px', fontWeight: 'bold' }}>
              交易对
            </label>
            <select
              value={selectedSymbol}
              onChange={(e) => setSelectedSymbol(e.target.value)}
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #ced4da',
                borderRadius: '4px',
                fontSize: '14px'
              }}
            >
              {symbols.map(symbol => (
                <option key={symbol} value={symbol}>{symbol}</option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '5px', fontSize: '14px', fontWeight: 'bold' }}>
              AI 模型
            </label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #ced4da',
                borderRadius: '4px',
                fontSize: '14px'
              }}
            >
              {aiModels.map(model => (
                <option key={model.model} value={model.model}>
                  {model.name} ({model.model})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* 市场数据输入 */}
        <div style={{ marginTop: '20px' }}>
          <h4>📊 市场数据</h4>
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: '10px',
            marginTop: '10px'
          }}>
            <div>
              <label style={{ display: 'block', marginBottom: '5px', fontSize: '12px' }}>当前价格</label>
              <input
                type="number"
                value={marketData.price}
                onChange={(e) => handleMarketDataChange('price', e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1px solid #ced4da',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '5px', fontSize: '12px' }}>24h 变化 (%)</label>
              <input
                type="number"
                step="0.01"
                value={marketData.change_24h}
                onChange={(e) => handleMarketDataChange('change_24h', e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1px solid #ced4da',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '5px', fontSize: '12px' }}>RSI</label>
              <input
                type="number"
                value={marketData.indicators.rsi}
                onChange={(e) => handleIndicatorChange('rsi', e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1px solid #ced4da',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '5px', fontSize: '12px' }}>MACD</label>
              <select
                value={marketData.indicators.macd}
                onChange={(e) => handleIndicatorChange('macd', e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1px solid #ced4da',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              >
                <option value="bullish">看涨 (Bullish)</option>
                <option value="bearish">看跌 (Bearish)</option>
                <option value="neutral">中性 (Neutral)</option>
              </select>
            </div>
          </div>
        </div>

        {/* 操作按钮 */}
        <div style={{ 
          display: 'flex', 
          gap: '10px', 
          marginTop: '20px',
          flexWrap: 'wrap'
        }}>
          <button
            onClick={handleAnalyzeMarket}
            disabled={loading}
            style={{
              padding: '12px 24px',
              backgroundColor: loading ? '#95a5a6' : '#3498db',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontSize: '14px',
              fontWeight: 'bold'
            }}
          >
            {loading ? '分析中...' : '📈 AI 市场分析'}
          </button>

          <button
            onClick={handleGenerateStrategy}
            disabled={loading}
            style={{
              padding: '12px 24px',
              backgroundColor: loading ? '#95a5a6' : '#27ae60',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontSize: '14px',
              fontWeight: 'bold'
            }}
          >
            {loading ? '生成中...' : '🎯 生成交易策略'}
          </button>

          <button
            onClick={handleGenerateSignal}
            disabled={loading}
            style={{
              padding: '12px 24px',
              backgroundColor: loading ? '#95a5a6' : '#f39c12',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontSize: '14px',
              fontWeight: 'bold'
            }}
          >
            {loading ? '生成中...' : '⚡ 生成交易信号'}
          </button>
        </div>
      </div>

      {/* 结果展示区域 */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))',
        gap: '20px'
      }}>
        {/* 市场分析结果 */}
        {analysisResult && (
          <div style={{ 
            backgroundColor: '#e3f2fd', 
            padding: '20px', 
            borderRadius: '8px',
            borderLeft: '4px solid #1976d2'
          }}>
            <h3>📈 市场分析结果</h3>
            {analysisResult.error ? (
              <p style={{ color: '#c62828' }}>❌ {analysisResult.error}</p>
            ) : (
              <div style={{ marginTop: '15px' }}>
                {typeof analysisResult === 'string' ? (
                  <pre style={{ 
                    whiteSpace: 'pre-wrap', 
                    fontSize: '14px',
                    lineHeight: '1.6'
                  }}>{analysisResult}</pre>
                ) : (
                  <div>
                    {Object.entries(analysisResult).map(([key, value]) => (
                      <div key={key} style={{ marginBottom: '10px' }}>
                        <strong style={{ color: '#1976d2' }}>{key}:</strong>
                        <span style={{ marginLeft: '10px' }}>
                          {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {analysisResult.model_id && (
                  <p style={{ marginTop: '15px', fontSize: '12px', color: '#666' }}>
                    模型: {analysisResult.model_id} | 
                    Token: {analysisResult.tokens_used || 'N/A'} | 
                    延迟: {analysisResult.latency_ms ? `${analysisResult.latency_ms.toFixed(2)}ms` : 'N/A'}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* 策略结果 */}
        {strategyResult && (
          <div style={{ 
            backgroundColor: '#e8f5e8', 
            padding: '20px', 
            borderRadius: '8px',
            borderLeft: '4px solid #27ae60'
          }}>
            <h3>🎯 交易策略</h3>
            {strategyResult.error ? (
              <p style={{ color: '#c62828' }}>❌ {strategyResult.error}</p>
            ) : (
              <div style={{ marginTop: '15px' }}>
                {typeof strategyResult === 'string' ? (
                  <pre style={{ 
                    whiteSpace: 'pre-wrap', 
                    fontSize: '14px',
                    lineHeight: '1.6'
                  }}>{strategyResult}</pre>
                ) : (
                  <div>
                    {Object.entries(strategyResult).map(([key, value]) => (
                      <div key={key} style={{ marginBottom: '10px' }}>
                        <strong style={{ color: '#27ae60' }}>{key}:</strong>
                        <span style={{ marginLeft: '10px' }}>
                          {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* 交易信号结果 */}
        {signalResult && (
          <div style={{ 
            backgroundColor: '#fff3e0', 
            padding: '20px', 
            borderRadius: '8px',
            borderLeft: '4px solid #f39c12'
          }}>
            <h3>⚡ 交易信号</h3>
            {signalResult.error ? (
              <p style={{ color: '#c62828' }}>❌ {signalResult.error}</p>
            ) : (
              <div style={{ marginTop: '15px' }}>
                {typeof signalResult === 'string' ? (
                  <pre style={{ 
                    whiteSpace: 'pre-wrap', 
                    fontSize: '14px',
                    lineHeight: '1.6'
                  }}>{signalResult}</pre>
                ) : (
                  <div>
                    {signalResult.signal && (
                      <div style={{ 
                        padding: '15px',
                        backgroundColor: signalResult.signal === 'buy' ? '#e8f5e8' : 
                                        signalResult.signal === 'sell' ? '#ffebee' : '#f5f5f5',
                        borderRadius: '4px',
                        marginBottom: '15px',
                        textAlign: 'center'
                      }}>
                        <span style={{ 
                          fontSize: '24px', 
                          fontWeight: 'bold',
                          color: signalResult.signal === 'buy' ? '#27ae60' : 
                                 signalResult.signal === 'sell' ? '#e74c3c' : '#f39c12'
                        }}>
                          {signalResult.signal === 'buy' ? '🟢 买入 (BUY)' : 
                           signalResult.signal === 'sell' ? '🔴 卖出 (SELL)' : 
                           '⚪ 观望 (HOLD)'}
                        </span>
                      </div>
                    )}
                    {Object.entries(signalResult).filter(([key]) => key !== 'signal').map(([key, value]) => (
                      <div key={key} style={{ marginBottom: '10px' }}>
                        <strong style={{ color: '#f39c12' }}>{key}:</strong>
                        <span style={{ marginLeft: '10px' }}>
                          {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 使用说明 */}
      <div style={{ 
        marginTop: '30px',
        backgroundColor: '#f8f9fa', 
        padding: '20px', 
        borderRadius: '8px'
      }}>
        <h3>📖 使用说明</h3>
        <ul style={{ lineHeight: '1.8', color: '#666' }}>
          <li><strong>AI 市场分析</strong>：使用 AI 模型分析当前市场数据，提供趋势判断和技术分析</li>
          <li><strong>生成交易策略</strong>：基于市场分析结果，生成具体的交易策略建议</li>
          <li><strong>生成交易信号</strong>：生成买入/卖出/观望的交易信号，包含置信度和建议</li>
          <li>支持多个 AI 模型：讯飞、DeepSeek、GPT-4、Claude 等</li>
          <li>可以手动调整市场数据来测试不同场景下的 AI 分析结果</li>
        </ul>
      </div>
    </div>
  );
}

export default AIMarketAnalysis;
