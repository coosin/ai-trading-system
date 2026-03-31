import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import { useMarketData, useTechnicalIndicators, useOrderBook, useTrades, useAIMarketAnalysis, useAITradingSignal } from '../hooks/useRealTimeData';

function RealTimeMarket() {
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT');
  const [selectedModel, setSelectedModel] = useState('astron-code-latest');
  const [aiModels, setAiModels] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [multiSymbolData, setMultiSymbolData] = useState({});
  
  const symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'ADA/USDT'];

  // 使用自定义Hooks获取真实数据
  const { data: marketData, loading: marketLoading } = useMarketData(selectedSymbol, '1m', 60);
  const { indicators: technicalIndicators, loading: indicatorsLoading } = useTechnicalIndicators(selectedSymbol);
  const { orderBook, loading: orderBookLoading } = useOrderBook(selectedSymbol);
  const { trades, loading: tradesLoading } = useTrades(selectedSymbol, 20);
  
  // AI分析
  const { analysis: aiAnalysis, loading: analysisLoading, analyze: analyzeMarket } = useAIMarketAnalysis(selectedSymbol);
  const { signal: aiSignal, loading: signalLoading, generateSignal } = useAITradingSignal(selectedSymbol);

  // 加载AI模型列表
  useEffect(() => {
    loadAIModels();
  }, []);

  // 加载多交易对数据
  useEffect(() => {
    loadMultiSymbolData();
    const timer = setInterval(loadMultiSymbolData, 5000);
    return () => clearInterval(timer);
  }, []);

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

  const loadMultiSymbolData = async () => {
    try {
      const data = {};
      for (const symbol of symbols) {
        try {
          const response = await api.market.getTicker(symbol);
          data[symbol] = response.data;
        } catch (e) {
          console.error(`获取${symbol}数据失败:`, e);
        }
      }
      setMultiSymbolData(data);
    } catch (error) {
      console.error('加载多交易对数据失败:', error);
    }
  };

  const handleAnalyze = async () => {
    await analyzeMarket(selectedModel);
  };

  const handleGenerateSignal = async () => {
    await generateSignal(selectedModel);
  };

  const startStreaming = () => {
    setIsStreaming(true);
  };

  const stopStreaming = () => {
    setIsStreaming(false);
  };

  const renderPriceChart = () => {
    if (marketData.length === 0) return null;

    const canvasWidth = 800;
    const canvasHeight = 300;
    const padding = 40;
    const innerWidth = canvasWidth - 2 * padding;
    const innerHeight = canvasHeight - 2 * padding;

    const prices = marketData.map(d => d.close);
    const maxPrice = Math.max(...prices);
    const minPrice = Math.min(...prices);
    const priceRange = maxPrice - minPrice || 1;

    const pathData = marketData.map((data, index) => {
      const x = padding + (index / (marketData.length - 1)) * innerWidth;
      const y = padding + innerHeight - ((data.close - minPrice) / priceRange) * innerHeight;
      return `${index === 0 ? 'M' : 'L'} ${x} ${y}`;
    }).join(' ');

    return (
      <svg width={canvasWidth} height={canvasHeight} style={{ backgroundColor: 'white', borderRadius: '4px' }}>
        <path
          d={pathData}
          fill="none"
          stroke="#3498db"
          strokeWidth="2"
        />
        <text x={canvasWidth / 2} y={20} textAnchor="middle" fontSize="14" fontWeight="bold">
          {selectedSymbol} 价格走势 (实时)
        </text>
        <text x={20} y={padding / 2} textAnchor="start" fontSize="12" fill="#666">
          ${maxPrice.toFixed(2)}
        </text>
        <text x={20} y={canvasHeight - padding / 2} textAnchor="start" fontSize="12" fill="#666">
          ${minPrice.toFixed(2)}
        </text>
      </svg>
    );
  };

  const loading = marketLoading || indicatorsLoading || orderBookLoading || tradesLoading;

  return (
    <div style={{ padding: '20px' }}>
      <h2>📈 实时行情跟踪与AI智能分析系统</h2>
      <p>实时监控市场数据，AI智能分析技术指标，生成交易信号</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '30px' }}>
        {/* 交易对选择和控制 */}
        <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px' }}>
          <h3>交易对选择</h3>
          <div style={{ marginBottom: '20px' }}>
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
          
          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontSize: '14px', fontWeight: 'bold' }}>
              AI 分析模型
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

          <div style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
            <button
              onClick={handleAnalyze}
              disabled={analysisLoading}
              style={{
                flex: 1,
                padding: '10px',
                backgroundColor: analysisLoading ? '#95a5a6' : '#3498db',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: analysisLoading ? 'not-allowed' : 'pointer',
                fontSize: '14px'
              }}
            >
              {analysisLoading ? '分析中...' : '🤖 AI市场分析'}
            </button>
            <button
              onClick={handleGenerateSignal}
              disabled={signalLoading}
              style={{
                flex: 1,
                padding: '10px',
                backgroundColor: signalLoading ? '#95a5a6' : '#f39c12',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: signalLoading ? 'not-allowed' : 'pointer',
                fontSize: '14px'
              }}
            >
              {signalLoading ? '生成中...' : '⚡ AI交易信号'}
            </button>
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              onClick={startStreaming}
              disabled={isStreaming}
              style={{
                flex: 1,
                padding: '10px',
                backgroundColor: '#27ae60',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: isStreaming ? 'not-allowed' : 'pointer',
                fontSize: '14px'
              }}
            >
              {isStreaming ? '实时流已开启' : '开始实时流'}
            </button>
            <button
              onClick={stopStreaming}
              disabled={!isStreaming}
              style={{
                flex: 1,
                padding: '10px',
                backgroundColor: '#e74c3c',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: !isStreaming ? 'not-allowed' : 'pointer',
                fontSize: '14px'
              }}
            >
              停止实时流
            </button>
          </div>
        </div>

        {/* AI分析结果 */}
        <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px' }}>
          <h3>🤖 AI智能分析结果</h3>
          
          {aiAnalysis ? (
            <div style={{
              backgroundColor: '#e3f2fd',
              padding: '15px',
              borderRadius: '6px',
              borderLeft: '4px solid #1976d2',
              marginBottom: '15px'
            }}>
              <h4 style={{ margin: '0 0 10px 0' }}>市场分析</h4>
              <div style={{ fontSize: '13px', lineHeight: '1.6' }}>
                {typeof aiAnalysis === 'string' ? (
                  <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{aiAnalysis}</pre>
                ) : (
                  <div>
                    {Object.entries(aiAnalysis).map(([key, value]) => (
                      <div key={key} style={{ marginBottom: '8px' }}>
                        <strong>{key}:</strong> {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
              点击"AI市场分析"按钮获取AI智能分析
            </div>
          )}

          {aiSignal ? (
            <div style={{
              backgroundColor: aiSignal.signal === 'buy' ? '#e8f5e8' : 
                             aiSignal.signal === 'sell' ? '#ffebee' : '#fff3e0',
              padding: '15px',
              borderRadius: '6px',
              borderLeft: `4px solid ${aiSignal.signal === 'buy' ? '#27ae60' : 
                                        aiSignal.signal === 'sell' ? '#e74c3c' : '#f39c12'}`
            }}>
              <h4 style={{ margin: '0 0 10px 0' }}>
                {aiSignal.signal === 'buy' ? '🟢 买入信号' : 
                 aiSignal.signal === 'sell' ? '🔴 卖出信号' : 
                 '⚪ 观望信号'}
              </h4>
              {aiSignal.confidence && (
                <p style={{ margin: '5px 0' }}>
                  <strong>置信度:</strong> {aiSignal.confidence}%
                </p>
              )}
              {aiSignal.reasoning && (
                <p style={{ margin: '5px 0', fontSize: '13px' }}>
                  <strong>分析依据:</strong> {aiSignal.reasoning}
                </p>
              )}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
              点击"AI交易信号"按钮获取AI交易建议
            </div>
          )}
        </div>
      </div>

      {/* 价格图表 */}
      <div style={{ marginBottom: '30px' }}>
        <h3>📊 价格走势 (真实数据)</h3>
        <div style={{ 
          backgroundColor: '#f8f9fa', 
          padding: '20px', 
          borderRadius: '8px',
          display: 'flex',
          justifyContent: 'center'
        }}>
          {marketLoading ? (
            <div style={{ padding: '40px' }}>加载图表中...</div>
          ) : (
            renderPriceChart()
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        {/* 技术指标 (真实数据) */}
        <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px' }}>
          <h3>📈 技术指标 (实时计算)</h3>
          {indicatorsLoading ? (
            <div style={{ textAlign: 'center', padding: '20px' }}>加载指标中...</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
              <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '4px', border: '1px solid #e9ecef' }}>
                <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>RSI (14)</h4>
                <p style={{ fontSize: '24px', fontWeight: 'bold' }}>{technicalIndicators.rsi?.toFixed(2) || 'N/A'}</p>
                <p style={{ 
                  fontSize: '12px', 
                  color: technicalIndicators.rsi > 70 ? '#e74c3c' : 
                         technicalIndicators.rsi < 30 ? '#27ae60' : '#666'
                }}>
                  {technicalIndicators.rsi > 70 ? '超买' : 
                   technicalIndicators.rsi < 30 ? '超卖' : '中性'}
                </p>
              </div>
              <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '4px', border: '1px solid #e9ecef' }}>
                <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>MACD</h4>
                <p style={{ fontSize: '24px', fontWeight: 'bold', color: technicalIndicators.macd > 0 ? '#27ae60' : '#e74c3c' }}>
                  {technicalIndicators.macd?.toFixed(4) || 'N/A'}
                </p>
                <p style={{ 
                  fontSize: '12px', 
                  color: technicalIndicators.macd > 0 ? '#27ae60' : '#e74c3c'
                }}>
                  {technicalIndicators.macd > 0 ? '看涨' : '看跌'}
                </p>
              </div>
              <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '4px', border: '1px solid #e9ecef' }}>
                <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>MA5</h4>
                <p style={{ fontSize: '20px', fontWeight: 'bold' }}>${technicalIndicators.sma5?.toFixed(2) || 'N/A'}</p>
              </div>
              <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '4px', border: '1px solid #e9ecef' }}>
                <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>MA20</h4>
                <p style={{ fontSize: '20px', fontWeight: 'bold' }}>${technicalIndicators.sma20?.toFixed(2) || 'N/A'}</p>
              </div>
            </div>
          )}
          {technicalIndicators.bollinger && (
            <div style={{ marginTop: '15px', backgroundColor: 'white', padding: '15px', borderRadius: '4px', border: '1px solid #e9ecef' }}>
              <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>布林带</h4>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <div>
                  <span style={{ fontSize: '12px', color: '#666' }}>上轨:</span>
                  <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>${technicalIndicators.bollinger.upper?.toFixed(2) || 'N/A'}</p>
                </div>
                <div>
                  <span style={{ fontSize: '12px', color: '#666' }}>中轨:</span>
                  <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>${technicalIndicators.bollinger.middle?.toFixed(2) || 'N/A'}</p>
                </div>
                <div>
                  <span style={{ fontSize: '12px', color: '#666' }}>下轨:</span>
                  <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>${technicalIndicators.bollinger.lower?.toFixed(2) || 'N/A'}</p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 订单簿和交易历史 (真实数据) */}
        <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px' }}>
          <h3>📋 订单簿 (实时)</h3>
          {orderBookLoading ? (
            <div style={{ textAlign: 'center', padding: '20px' }}>加载订单簿中...</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
              <div>
                <h4 style={{ margin: '0 0 10px 0', fontSize: '14px', color: '#27ae60' }}>买单</h4>
                <div style={{ backgroundColor: 'white', borderRadius: '4px', border: '1px solid #e9ecef', maxHeight: '200px', overflowY: 'auto' }}>
                  {orderBook.bids?.slice(0, 10).map((bid, index) => (
                    <div key={index} style={{ 
                      padding: '8px', 
                      borderBottom: '1px solid #f1f1f1',
                      display: 'flex',
                      justifyContent: 'space-between'
                    }}>
                      <span style={{ fontWeight: 'bold' }}>${bid.price?.toFixed(2) || bid[0]}</span>
                      <span>{bid.quantity?.toFixed(4) || bid[1]}</span>
                    </div>
                  )) || <div style={{ padding: '10px', textAlign: 'center', color: '#666' }}>暂无数据</div>}
                </div>
              </div>
              <div>
                <h4 style={{ margin: '0 0 10px 0', fontSize: '14px', color: '#e74c3c' }}>卖单</h4>
                <div style={{ backgroundColor: 'white', borderRadius: '4px', border: '1px solid #e9ecef', maxHeight: '200px', overflowY: 'auto' }}>
                  {orderBook.asks?.slice(0, 10).map((ask, index) => (
                    <div key={index} style={{ 
                      padding: '8px', 
                      borderBottom: '1px solid #f1f1f1',
                      display: 'flex',
                      justifyContent: 'space-between'
                    }}>
                      <span style={{ fontWeight: 'bold' }}>${ask.price?.toFixed(2) || ask[0]}</span>
                      <span>{ask.quantity?.toFixed(4) || ask[1]}</span>
                    </div>
                  )) || <div style={{ padding: '10px', textAlign: 'center', color: '#666' }}>暂无数据</div>}
                </div>
              </div>
            </div>
          )}

          <h3 style={{ marginTop: '20px' }}>📝 最新交易 (实时)</h3>
          {tradesLoading ? (
            <div style={{ textAlign: 'center', padding: '20px' }}>加载交易历史中...</div>
          ) : (
            <div style={{ backgroundColor: 'white', borderRadius: '4px', border: '1px solid #e9ecef', maxHeight: '150px', overflowY: 'auto' }}>
              {trades?.slice(0, 20).map((trade, index) => (
                <div key={trade.id || index} style={{ 
                  padding: '8px', 
                  borderBottom: '1px solid #f1f1f1',
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '12px'
                }}>
                  <span style={{ 
                    color: trade.side === 'buy' ? '#27ae60' : '#e74c3c',
                    fontWeight: 'bold'
                  }}>
                    {trade.side === 'buy' ? '买入' : '卖出'}
                  </span>
                  <span style={{ fontWeight: 'bold' }}>${trade.price?.toFixed(2)}</span>
                  <span>{trade.quantity?.toFixed(4)}</span>
                  <span style={{ color: '#666' }}>
                    {trade.timestamp ? new Date(trade.timestamp).toLocaleTimeString() : 'N/A'}
                  </span>
                </div>
              )) || <div style={{ padding: '10px', textAlign: 'center', color: '#666' }}>暂无交易数据</div>}
            </div>
          )}
        </div>
      </div>

      {/* 多交易对监控 (真实数据) */}
      <div style={{ marginTop: '30px' }}>
        <h3>📊 多交易对监控 (实时行情)</h3>
        <div style={{ 
          backgroundColor: '#f8f9fa', 
          padding: '20px', 
          borderRadius: '8px',
          overflowX: 'auto'
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: '#e9ecef' }}>
                <th style={{ padding: '10px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>交易对</th>
                <th style={{ padding: '10px', textAlign: 'right', borderBottom: '1px solid #dee2e6' }}>最新价格</th>
                <th style={{ padding: '10px', textAlign: 'right', borderBottom: '1px solid #dee2e6' }}>24h变化</th>
                <th style={{ padding: '10px', textAlign: 'right', borderBottom: '1px solid #dee2e6' }}>24h交易量</th>
                <th style={{ padding: '10px', textAlign: 'center', borderBottom: '1px solid #dee2e6' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {symbols.map(symbol => {
                const data = multiSymbolData[symbol];
                const price = data?.price || 0;
                const change = data?.change || 0;
                const volume = data?.volume || 0;
                
                return (
                  <tr key={symbol} style={{ 
                    backgroundColor: symbol === selectedSymbol ? '#e3f2fd' : 'white',
                    cursor: 'pointer'
                  }} onClick={() => setSelectedSymbol(symbol)}>
                    <td style={{ padding: '10px', borderBottom: '1px solid #dee2e6' }}>{symbol}</td>
                    <td style={{ padding: '10px', textAlign: 'right', borderBottom: '1px solid #dee2e6', fontWeight: 'bold' }}>
                      ${price.toFixed(2)}
                    </td>
                    <td style={{ 
                      padding: '10px', 
                      textAlign: 'right', 
                      borderBottom: '1px solid #dee2e6',
                      color: change > 0 ? '#27ae60' : change < 0 ? '#e74c3c' : '#666'
                    }}>
                      {change > 0 ? '+' : ''}{change.toFixed(2)}%
                    </td>
                    <td style={{ padding: '10px', textAlign: 'right', borderBottom: '1px solid #dee2e6' }}>
                      ${volume.toLocaleString()}
                    </td>
                    <td style={{ padding: '10px', textAlign: 'center', borderBottom: '1px solid #dee2e6' }}>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedSymbol(symbol);
                        }}
                        style={{
                          padding: '6px 12px',
                          backgroundColor: symbol === selectedSymbol ? '#3498db' : '#95a5a6',
                          color: 'white',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: 'pointer',
                          fontSize: '12px'
                        }}
                      >
                        {symbol === selectedSymbol ? '当前选中' : '查看'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default RealTimeMarket;
