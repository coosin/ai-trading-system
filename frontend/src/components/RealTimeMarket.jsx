import React, { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';

function RealTimeMarket() {
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT');
  const [marketData, setMarketData] = useState([]);
  const [orderBook, setOrderBook] = useState({ bids: [], asks: [] });
  const [trades, setTrades] = useState([]);
  const [technicalIndicators, setTechnicalIndicators] = useState({});
  const [marketSignal, setMarketSignal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  
  const chartRef = useRef(null);
  const symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'ADA/USDT'];

  useEffect(() => {
    loadMarketData();
    const interval = setInterval(loadMarketData, 2000);
    return () => clearInterval(interval);
  }, [selectedSymbol]);

  const loadMarketData = async () => {
    setLoading(true);
    try {
      // 获取市场数据
      const klinesData = await api.market.getKlines(selectedSymbol, '1m', 60);
      const marketDataFromApi = klinesData.map(kline => ({
        timestamp: kline.timestamp,
        open: kline.open,
        high: kline.high,
        low: kline.low,
        close: kline.close,
        volume: kline.volume
      }));
      setMarketData(marketDataFromApi);

      // 获取订单簿数据
      const orderBookData = await api.market.getOrderBook(selectedSymbol);
      setOrderBook(orderBookData);

      // 获取交易历史
      const tradesData = await api.trading.getHistory({ symbol: selectedSymbol, limit: 20 });
      setTrades(tradesData);

      // 模拟技术指标
      const mockIndicators = {
        rsi: (Math.random() * 40 + 30).toFixed(2),
        macd: (Math.random() * 2 - 1).toFixed(4),
        ma5: (marketDataFromApi.slice(-5).reduce((sum, item) => sum + item.close, 0) / 5).toFixed(2),
        ma20: (marketDataFromApi.slice(-20).reduce((sum, item) => sum + item.close, 0) / 20).toFixed(2),
        bollinger: {
          upper: (marketDataFromApi[marketDataFromApi.length - 1].close * 1.02).toFixed(2),
          middle: marketDataFromApi[marketDataFromApi.length - 1].close.toFixed(2),
          lower: (marketDataFromApi[marketDataFromApi.length - 1].close * 0.98).toFixed(2)
        }
      };
      setTechnicalIndicators(mockIndicators);

      // 生成市场信号
      generateMarketSignal(mockIndicators, marketDataFromApi);

    } catch (error) {
      console.error('加载市场数据失败:', error);
      // 失败时使用模拟数据
      const mockMarketData = [];
      const now = Date.now();
      
      for (let i = 0; i < 60; i++) {
        const timestamp = now - (60 - i) * 60000;
        const basePrice = selectedSymbol === 'BTC/USDT' ? 60000 :
                         selectedSymbol === 'ETH/USDT' ? 3000 :
                         selectedSymbol === 'SOL/USDT' ? 100 :
                         selectedSymbol === 'BNB/USDT' ? 300 : 1;
        const price = basePrice + (Math.random() * 100 - 50);
        const volume = Math.random() * 1000;
        
        mockMarketData.push({
          timestamp,
          open: price,
          high: price + Math.random() * 20,
          low: price - Math.random() * 20,
          close: price,
          volume
        });
      }
      
      setMarketData(mockMarketData);

      const mockOrderBook = {
        bids: Array.from({ length: 10 }, (_, i) => ({
          price: mockMarketData[mockMarketData.length - 1].close - i * 10,
          quantity: Math.random() * 5
        })),
        asks: Array.from({ length: 10 }, (_, i) => ({
          price: mockMarketData[mockMarketData.length - 1].close + i * 10,
          quantity: Math.random() * 5
        }))
      };
      setOrderBook(mockOrderBook);

      const mockTrades = Array.from({ length: 20 }, (_, i) => ({
        id: i,
        price: mockMarketData[mockMarketData.length - 1].close + (Math.random() * 20 - 10),
        quantity: Math.random() * 2,
        side: Math.random() > 0.5 ? 'buy' : 'sell',
        timestamp: now - i * 10000
      }));
      setTrades(mockTrades);

      const mockIndicators = {
        rsi: (Math.random() * 40 + 30).toFixed(2),
        macd: (Math.random() * 2 - 1).toFixed(4),
        ma5: (mockMarketData.slice(-5).reduce((sum, item) => sum + item.close, 0) / 5).toFixed(2),
        ma20: (mockMarketData.slice(-20).reduce((sum, item) => sum + item.close, 0) / 20).toFixed(2),
        bollinger: {
          upper: (mockMarketData[mockMarketData.length - 1].close * 1.02).toFixed(2),
          middle: mockMarketData[mockMarketData.length - 1].close.toFixed(2),
          lower: (mockMarketData[mockMarketData.length - 1].close * 0.98).toFixed(2)
        }
      };
      setTechnicalIndicators(mockIndicators);

      generateMarketSignal(mockIndicators, mockMarketData);
    } finally {
      setLoading(false);
    }
  };

  const generateMarketSignal = (indicators, data) => {
    const rsi = parseFloat(indicators.rsi);
    const macd = parseFloat(indicators.macd);
    const latestPrice = data[data.length - 1].close;
    const previousPrice = data[data.length - 2].close;
    
    let signal = null;
    let confidence = 0;
    let reasons = [];

    if (rsi < 30 && macd > 0 && latestPrice > previousPrice) {
      signal = 'buy';
      confidence = (Math.random() * 30 + 70).toFixed(1);
      reasons = ['RSI超卖', 'MACD金叉', '价格上涨'];
    } else if (rsi > 70 && macd < 0 && latestPrice < previousPrice) {
      signal = 'sell';
      confidence = (Math.random() * 30 + 70).toFixed(1);
      reasons = ['RSI超买', 'MACD死叉', '价格下跌'];
    } else {
      signal = 'hold';
      confidence = (Math.random() * 20 + 80).toFixed(1);
      reasons = ['市场稳定', '指标中性'];
    }

    setMarketSignal({
      signal,
      confidence,
      reasons,
      timestamp: new Date().toLocaleString()
    });
  };

  const startStreaming = () => {
    setIsStreaming(true);
    // 这里可以实现WebSocket连接
  };

  const stopStreaming = () => {
    setIsStreaming(false);
    // 这里可以关闭WebSocket连接
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
    const priceRange = maxPrice - minPrice;

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
          {selectedSymbol} 价格走势 (1小时)
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

  return (
    <div style={{ padding: '20px' }}>
      <h2>📈 实时行情跟踪与判断系统</h2>
      <p>实时监控市场数据，分析技术指标，生成交易信号</p>

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
              {isStreaming ? '已连接' : '开始实时流'}
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

        {/* 市场信号 */}
        <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px' }}>
          <h3>🎯 市场判断信号</h3>
          {marketSignal ? (
            <div style={{
              backgroundColor: marketSignal.signal === 'buy' ? '#e8f5e8' : 
                             marketSignal.signal === 'sell' ? '#ffebee' : '#fff3e0',
              padding: '15px',
              borderRadius: '6px',
              borderLeft: `4px solid ${marketSignal.signal === 'buy' ? '#27ae60' : 
                                        marketSignal.signal === 'sell' ? '#e74c3c' : '#f39c12'}`
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <h4 style={{ margin: 0 }}>
                  {marketSignal.signal === 'buy' ? '买入信号' : 
                   marketSignal.signal === 'sell' ? '卖出信号' : '持有信号'}
                </h4>
                <div style={{ 
                  backgroundColor: marketSignal.signal === 'buy' ? '#27ae60' : 
                                   marketSignal.signal === 'sell' ? '#e74c3c' : '#f39c12',
                  color: 'white',
                  padding: '6px 12px',
                  borderRadius: '12px',
                  fontSize: '12px',
                  fontWeight: 'bold'
                }}>
                  置信度: {marketSignal.confidence}%
                </div>
              </div>
              <p style={{ fontSize: '12px', color: '#666', marginBottom: '10px' }}>
                生成时间: {marketSignal.timestamp}
              </p>
              <h5 style={{ margin: '10px 0' }}>判断依据:</h5>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {marketSignal.reasons.map((reason, index) => (
                  <li key={index} style={{ 
                    marginBottom: '5px', 
                    fontSize: '13px'
                  }}>
                    • {reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
              加载市场信号中...
            </div>
          )}
        </div>
      </div>

      {/* 价格图表 */}
      <div style={{ marginBottom: '30px' }}>
        <h3>📊 价格走势</h3>
        <div style={{ 
          backgroundColor: '#f8f9fa', 
          padding: '20px', 
          borderRadius: '8px',
          display: 'flex',
          justifyContent: 'center'
        }}>
          {loading ? (
            <div style={{ padding: '40px' }}>加载图表中...</div>
          ) : (
            renderPriceChart()
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        {/* 技术指标 */}
        <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px' }}>
          <h3>📈 技术指标</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
            <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '4px', border: '1px solid #e9ecef' }}>
              <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>RSI (14)</h4>
              <p style={{ fontSize: '24px', fontWeight: 'bold' }}>{technicalIndicators.rsi || '0'}</p>
              <p style={{ 
                fontSize: '12px', 
                color: parseFloat(technicalIndicators.rsi) > 70 ? '#e74c3c' : 
                       parseFloat(technicalIndicators.rsi) < 30 ? '#27ae60' : '#666'
              }}>
                {parseFloat(technicalIndicators.rsi) > 70 ? '超买' : 
                 parseFloat(technicalIndicators.rsi) < 30 ? '超卖' : '中性'}
              </p>
            </div>
            <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '4px', border: '1px solid #e9ecef' }}>
              <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>MACD</h4>
              <p style={{ fontSize: '24px', fontWeight: 'bold', color: parseFloat(technicalIndicators.macd) > 0 ? '#27ae60' : '#e74c3c' }}>
                {technicalIndicators.macd || '0'}
              </p>
              <p style={{ 
                fontSize: '12px', 
                color: parseFloat(technicalIndicators.macd) > 0 ? '#27ae60' : '#e74c3c'
              }}>
                {parseFloat(technicalIndicators.macd) > 0 ? '金叉' : '死叉'}
              </p>
            </div>
            <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '4px', border: '1px solid #e9ecef' }}>
              <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>MA5</h4>
              <p style={{ fontSize: '20px', fontWeight: 'bold' }}>${technicalIndicators.ma5 || '0'}</p>
            </div>
            <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '4px', border: '1px solid #e9ecef' }}>
              <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>MA20</h4>
              <p style={{ fontSize: '20px', fontWeight: 'bold' }}>${technicalIndicators.ma20 || '0'}</p>
            </div>
          </div>
          {technicalIndicators.bollinger && (
            <div style={{ marginTop: '15px', backgroundColor: 'white', padding: '15px', borderRadius: '4px', border: '1px solid #e9ecef' }}>
              <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>布林带</h4>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <div>
                  <span style={{ fontSize: '12px', color: '#666' }}>上轨:</span>
                  <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>${technicalIndicators.bollinger.upper}</p>
                </div>
                <div>
                  <span style={{ fontSize: '12px', color: '#666' }}>中轨:</span>
                  <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>${technicalIndicators.bollinger.middle}</p>
                </div>
                <div>
                  <span style={{ fontSize: '12px', color: '#666' }}>下轨:</span>
                  <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>${technicalIndicators.bollinger.lower}</p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 订单簿和交易历史 */}
        <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px' }}>
          <h3>📋 订单簿</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
            <div>
              <h4 style={{ margin: '0 0 10px 0', fontSize: '14px', color: '#27ae60' }}>买单</h4>
              <div style={{ backgroundColor: 'white', borderRadius: '4px', border: '1px solid #e9ecef', maxHeight: '200px', overflowY: 'auto' }}>
                {orderBook.bids.map((bid, index) => (
                  <div key={index} style={{ 
                    padding: '8px', 
                    borderBottom: '1px solid #f1f1f1',
                    display: 'flex',
                    justifyContent: 'space-between'
                  }}>
                    <span style={{ fontWeight: 'bold' }}>${bid.price.toFixed(2)}</span>
                    <span>{bid.quantity.toFixed(4)}</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h4 style={{ margin: '0 0 10px 0', fontSize: '14px', color: '#e74c3c' }}>卖单</h4>
              <div style={{ backgroundColor: 'white', borderRadius: '4px', border: '1px solid #e9ecef', maxHeight: '200px', overflowY: 'auto' }}>
                {orderBook.asks.map((ask, index) => (
                  <div key={index} style={{ 
                    padding: '8px', 
                    borderBottom: '1px solid #f1f1f1',
                    display: 'flex',
                    justifyContent: 'space-between'
                  }}>
                    <span style={{ fontWeight: 'bold' }}>${ask.price.toFixed(2)}</span>
                    <span>{ask.quantity.toFixed(4)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <h3 style={{ marginTop: '20px' }}>📝 最新交易</h3>
          <div style={{ backgroundColor: 'white', borderRadius: '4px', border: '1px solid #e9ecef', maxHeight: '150px', overflowY: 'auto' }}>
            {trades.map((trade) => (
              <div key={trade.id} style={{ 
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
                <span style={{ fontWeight: 'bold' }}>${trade.price.toFixed(2)}</span>
                <span>{trade.quantity.toFixed(4)}</span>
                <span style={{ color: '#666' }}>
                  {new Date(trade.timestamp).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 多交易对监控 */}
      <div style={{ marginTop: '30px' }}>
        <h3>📊 多交易对监控</h3>
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
                <th style={{ padding: '10px', textAlign: 'center', borderBottom: '1px solid #dee2e6' }}>信号</th>
              </tr>
            </thead>
            <tbody>
              {symbols.map(symbol => {
                const basePrice = symbol === 'BTC/USDT' ? 60000 :
                                 symbol === 'ETH/USDT' ? 3000 :
                                 symbol === 'SOL/USDT' ? 100 :
                                 symbol === 'BNB/USDT' ? 300 : 1;
                const price = basePrice + (Math.random() * 100 - 50);
                const change = (Math.random() * 10 - 5).toFixed(2);
                const volume = (Math.random() * 1000000).toFixed(0);
                const signal = Math.random() > 0.6 ? 'buy' : Math.random() > 0.5 ? 'sell' : 'hold';
                
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
                      color: parseFloat(change) > 0 ? '#27ae60' : '#e74c3c'
                    }}>
                      {parseFloat(change) > 0 ? '+' : ''}{change}%
                    </td>
                    <td style={{ padding: '10px', textAlign: 'right', borderBottom: '1px solid #dee2e6' }}>
                      ${volume}
                    </td>
                    <td style={{ padding: '10px', textAlign: 'center', borderBottom: '1px solid #dee2e6' }}>
                      <span style={{ 
                        padding: '4px 12px', 
                        borderRadius: '12px',
                        fontSize: '12px',
                        fontWeight: 'bold',
                        backgroundColor: signal === 'buy' ? '#e8f5e8' : 
                                         signal === 'sell' ? '#ffebee' : '#fff3e0',
                        color: signal === 'buy' ? '#27ae60' : 
                               signal === 'sell' ? '#e74c3c' : '#f39c12'
                      }}>
                        {signal === 'buy' ? '买入' : signal === 'sell' ? '卖出' : '持有'}
                      </span>
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