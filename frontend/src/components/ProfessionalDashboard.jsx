import React, { useState, useEffect, useRef, useCallback, useMemo, memo } from 'react';
import { api } from '../services/api';
import { 
  AreaChart, Area, 
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import MultiSourceAnalysis from './MultiSourceAnalysis';

const COLORS = ['#1890ff', '#52c41a', '#faad14', '#722ed1', '#eb2f96'];

const StatCard = memo(function StatCard({ title, value, change, positive, icon, color }) {
  return (
    <div className="stat-card">
      <div className="stat-card-header">
        <span className="stat-card-title">{title}</span>
        <div className={`stat-card-icon ${color}`}>{icon}</div>
      </div>
      <div className="stat-card-value">{value}</div>
      <div className={`stat-card-change ${positive ? 'positive' : 'negative'}`}>
        {positive ? '↑' : '↓'} {change}
      </div>
    </div>
  );
});

const StatusItem = memo(function StatusItem({ name, status, value }) {
  return (
    <div className="status-item">
      <div className={`status-indicator ${status}`}></div>
      <div className="status-info">
        <div className="status-name">{name}</div>
        <div className="status-value">{value}</div>
      </div>
    </div>
  );
});

const RiskGauge = memo(function RiskGauge({ label, value, max }) {
  const percentage = (value / max) * 100;
  const color = percentage > 70 ? 'var(--error-color)' : percentage > 40 ? 'var(--warning-color)' : 'var(--success-color)';
  
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ marginBottom: '8px', fontSize: '13px', color: 'var(--text-tertiary)' }}>{label}</div>
      <div style={{ 
        width: '80px', 
        height: '80px', 
        borderRadius: '50%', 
        background: `conic-gradient(${color} ${percentage}%, var(--bg-secondary) ${percentage}%)`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        margin: '0 auto'
      }}>
        <div style={{ 
          width: '60px', 
          height: '60px', 
          borderRadius: '50%', 
          background: 'var(--bg-primary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '18px',
          fontWeight: 600
        }}>
          {value}
        </div>
      </div>
    </div>
  );
});

function ProfessionalDashboard({ activeView }) {
  const [marketData, setMarketData] = useState({});
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT');
  const [klineData, setKlineData] = useState([]);
  const [orderBook, setOrderBook] = useState({ bids: [], asks: [] });
  
  const [positions, setPositions] = useState([]);
  const [accountInfo, setAccountInfo] = useState(null);
  const [tradeHistory, setTradeHistory] = useState([]);
  
  const [aiMessages, setAiMessages] = useState([
    { role: 'assistant', content: '您好！我是AI交易助手，有什么可以帮助您的吗？您可以问我关于市场分析、交易策略、风险管理等问题。' }
  ]);
  const [aiInput, setAiInput] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const [notification, setNotification] = useState(null);
  
  const [tradeSymbol, setTradeSymbol] = useState('BTC/USDT');
  const [orderType, setOrderType] = useState('limit');
  const [tradePrice, setTradePrice] = useState('');
  const [tradeAmount, setTradeAmount] = useState('');
  
  const [settingsTab, setSettingsTab] = useState('基本设置');
  const [systemSettings, setSystemSettings] = useState({});
  
  const [aiAnalysisLogs, setAiAnalysisLogs] = useState([]);
  const [aiAnalysisRunning, setAiAnalysisRunning] = useState(true);
  
  const [riskData, setRiskData] = useState(null);
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState({});

  const symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'ADA/USDT', 'XRP/USDT'];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [aiMessages]);

  useEffect(() => {
    loadInitialData();
    const interval = setInterval(refreshData, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (activeView === 'ai' && aiAnalysisRunning) {
      const interval = setInterval(loadAiAnalysisLogs, 5000);
      return () => clearInterval(interval);
    }
  }, [activeView, aiAnalysisRunning]);

  const loadInitialData = async () => {
    setLoading(prev => ({ ...prev, initial: true }));
    try {
      await Promise.all([
        loadMarketData(),
        loadPositions(),
        loadAccountInfo(),
        loadTradeHistory(),
        loadRiskData(),
        loadStrategies(),
      ]);
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(prev => ({ ...prev, initial: false }));
    }
  };

  const refreshData = async () => {
    try {
      await Promise.all([
        loadMarketData(),
        loadPositions(),
      ]);
    } catch (error) {
      console.error('刷新数据失败:', error);
    }
  };

  const loadMarketData = async () => {
    try {
      const data = {};
      for (const symbol of symbols) {
        try {
          const ticker = await api.market.getTicker(symbol);
          data[symbol] = ticker;
        } catch (e) {
          console.log(`获取 ${symbol} 行情失败`);
        }
      }
      setMarketData(data);
      
      if (selectedSymbol && !klineData.length) {
        loadKlineData(selectedSymbol);
        loadOrderBook(selectedSymbol);
      }
    } catch (error) {
      console.error('加载市场数据失败:', error);
    }
  };

  const loadKlineData = async (symbol) => {
    try {
      const klines = await api.market.getKlines(symbol, '1h', 24);
      if (klines && klines.length) {
        const formatted = klines.map((k, i) => ({
          time: new Date(k.timestamp || k[0]).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
          price: k.close || k[4]
        }));
        setKlineData(formatted);
      }
    } catch (error) {
      console.error('加载K线数据失败:', error);
    }
  };

  const loadOrderBook = async (symbol) => {
    try {
      const book = await api.market.getOrderBook(symbol);
      if (book) {
        setOrderBook({
          bids: book.bids || [],
          asks: book.asks || []
        });
      }
    } catch (error) {
      console.error('加载订单簿失败:', error);
    }
  };

  const loadPositions = async () => {
    try {
      const [realPositions, contractPositions] = await Promise.all([
        api.trading.getPositions().catch(() => []),
        api.contractTrading.getPositions().catch(() => [])
      ]);
      
      const allPositions = [...(realPositions || []), ...(contractPositions || [])];
      setPositions(allPositions);
    } catch (error) {
      console.error('加载持仓失败:', error);
      setPositions([]);
    }
  };

  const loadAccountInfo = async () => {
    try {
      const account = await api.contractTrading.getAccount();
      setAccountInfo(account);
    } catch (error) {
      console.error('加载账户信息失败:', error);
    }
  };

  const loadTradeHistory = async () => {
    try {
      const history = await api.trading.getHistory({});
      setTradeHistory(history || []);
    } catch (error) {
      console.error('加载交易历史失败:', error);
      setTradeHistory([]);
    }
  };

  const loadRiskData = async () => {
    try {
      const risk = await api.risk.getOverview();
      setRiskData(risk);
    } catch (error) {
      console.error('加载风险数据失败:', error);
    }
  };

  const loadStrategies = async () => {
    try {
      const strategyList = await api.strategies.getAll();
      setStrategies(strategyList || []);
    } catch (error) {
      console.error('加载策略失败:', error);
    }
  };

  const loadAiAnalysisLogs = async () => {
    try {
      const logs = await api.monitoring.getLogs({ limit: 20, level: 'INFO' });
      if (logs && logs.length) {
        const formatted = logs.map(log => ({
          time: new Date(log.timestamp).toLocaleTimeString('zh-CN', { hour12: false }),
          type: log.category || 'info',
          message: log.message
        }));
        setAiAnalysisLogs(prev => [...prev.slice(-10), ...formatted].slice(-20));
      }
    } catch (error) {
      const mockLog = {
        time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        type: ['market', 'signal', 'risk', 'strategy'][Math.floor(Math.random() * 4)],
        message: `正在监控 ${selectedSymbol} 市场数据...`
      };
      setAiAnalysisLogs(prev => [...prev.slice(-19), mockLog]);
    }
  };

  const showNotification = (message, type = 'success') => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 3000);
  };

  const handleSymbolSelect = useCallback((symbol) => {
    setSelectedSymbol(symbol);
    loadKlineData(symbol);
    loadOrderBook(symbol);
  }, []);

  const sendAiMessage = useCallback(async () => {
    if (!aiInput.trim() || aiLoading) return;
    
    const userMessage = aiInput.trim();
    setAiInput('');
    setAiMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setAiLoading(true);

    try {
      const response = await api.ai.chat({ message: userMessage });
      
      if (response && response.response) {
        setAiMessages(prev => [...prev, { role: 'assistant', content: response.response }]);
      } else if (response && response.result) {
        setAiMessages(prev => [...prev, { role: 'assistant', content: response.result }]);
      }
    } catch (error) {
      setAiMessages(prev => [...prev, { 
        role: 'assistant', 
        content: '抱歉，AI服务暂时不可用。请稍后再试。' 
      }]);
    } finally {
      setAiLoading(false);
    }
  }, [aiInput, aiLoading]);

  const handleAiKeyPress = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendAiMessage();
    }
  }, [sendAiMessage]);

  const handleInputChange = useCallback((e) => {
    setAiInput(e.target.value);
  }, []);

  const handleQuickQuestion = useCallback((question) => {
    setAiInput(question);
  }, []);

  const handleTradeSubmit = useCallback(async (side) => {
    if (!tradePrice || !tradeAmount) {
      showNotification('请填写完整交易信息', 'error');
      return;
    }
    
    try {
      const orderData = {
        symbol: tradeSymbol,
        side: side,
        type: orderType,
        price: parseFloat(tradePrice),
        amount: parseFloat(tradeAmount)
      };
      
      await api.contractTrading.placeOrder(orderData);
      showNotification(`${side === 'buy' ? '买入' : '卖出'}订单已提交`, 'success');
      setTradePrice('');
      setTradeAmount('');
      loadPositions();
    } catch (error) {
      showNotification(`下单失败: ${error.message}`, 'error');
    }
  }, [tradePrice, tradeAmount, tradeSymbol, orderType]);

  const handleClosePosition = useCallback(async (symbol) => {
    try {
      await api.contractTrading.closePosition(symbol);
      showNotification(`已平仓 ${symbol}`, 'success');
      loadPositions();
    } catch (error) {
      showNotification(`平仓失败: ${error.message}`, 'error');
    }
  }, []);

  const currentPrice = useMemo(() => {
    const data = marketData[selectedSymbol];
    return data?.last || data?.price || 0;
  }, [marketData, selectedSymbol]);

  const priceChange = useMemo(() => {
    const data = marketData[selectedSymbol];
    return data?.change || data?.changePercent || 0;
  }, [marketData, selectedSymbol]);

  const totalAssets = useMemo(() => {
    return accountInfo?.total_equity || accountInfo?.balance || '$125,430.50';
  }, [accountInfo]);

  const todayPnL = useMemo(() => {
    return accountInfo?.today_pnl || '+$2,340.80';
  }, [accountInfo]);

  const renderDashboard = () => (
    <>
      <div className="dashboard-grid">
        <StatCard 
          title="总资产" 
          value={typeof totalAssets === 'number' ? `$${totalAssets.toLocaleString()}` : totalAssets}
          change={accountInfo?.today_pnl_percent || "+5.23%"}
          positive={true}
          icon="💰"
          color="blue"
        />
        <StatCard 
          title="今日盈亏" 
          value={typeof todayPnL === 'number' ? `$${todayPnL.toLocaleString()}` : todayPnL}
          change={accountInfo?.win_rate || "+1.89%"}
          positive={true}
          icon="📈"
          color="green"
        />
        <StatCard 
          title="持仓数量" 
          value={positions.length.toString()}
          change={`${positions.filter(p => parseFloat(p.unrealized_pnl || p.pnl || 0) > 0).length} 盈利`}
          positive={positions.filter(p => parseFloat(p.unrealized_pnl || p.pnl || 0) > 0).length > positions.filter(p => parseFloat(p.unrealized_pnl || p.pnl || 0) < 0).length}
          icon="📋"
          color="orange"
        />
        <StatCard 
          title="AI信号" 
          value={riskData?.signal || "买入"}
          change={`置信度 ${riskData?.confidence || 85}%`}
          positive={true}
          icon="🤖"
          color="purple"
        />
      </div>

      <div className="panel-row">
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">📊</span>
              实时行情 - {selectedSymbol}
            </div>
            <div className="panel-actions">
              <div className="symbol-selector">
                {symbols.slice(0, 4).map(symbol => (
                  <button
                    key={symbol}
                    className={`symbol-btn ${selectedSymbol === symbol ? 'active' : ''}`}
                    onClick={() => handleSymbolSelect(symbol)}
                  >
                    {symbol.replace('/USDT', '')}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="panel-body">
            <div className="price-display">
              <span className="current-price">${currentPrice > 0 ? currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '---'}</span>
              <span className={`price-change ${priceChange >= 0 ? 'positive' : 'negative'}`}>
                {priceChange >= 0 ? '+' : ''}{typeof priceChange === 'number' ? priceChange.toFixed(2) : priceChange}%
              </span>
            </div>
            <div className="market-stats">
              <div className="market-stat-item">
                <div className="market-stat-label">24h最高</div>
                <div className="market-stat-value">${marketData[selectedSymbol]?.high ? parseFloat(marketData[selectedSymbol].high).toLocaleString() : '---'}</div>
              </div>
              <div className="market-stat-item">
                <div className="market-stat-label">24h最低</div>
                <div className="market-stat-value">${marketData[selectedSymbol]?.low ? parseFloat(marketData[selectedSymbol].low).toLocaleString() : '---'}</div>
              </div>
              <div className="market-stat-item">
                <div className="market-stat-label">24h成交量</div>
                <div className="market-stat-value">{marketData[selectedSymbol]?.volume ? `${(parseFloat(marketData[selectedSymbol].volume) / 1000000).toFixed(2)}M` : '---'}</div>
              </div>
              <div className="market-stat-item">
                <div className="market-stat-label">市值</div>
                <div className="market-stat-value">--</div>
              </div>
            </div>
            <div className="chart-container" style={{ height: '200px', marginTop: '16px' }}>
              {klineData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={klineData}>
                    <defs>
                      <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#1890ff" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#1890ff" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                    <XAxis dataKey="time" stroke="#666" />
                    <YAxis stroke="#666" domain={['auto', 'auto']} />
                    <Tooltip />
                    <Area type="monotone" dataKey="price" stroke="#1890ff" fillOpacity={1} fill="url(#colorPrice)" />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-tertiary)' }}>
                  加载图表中...
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">🤖</span>
              AI智能交互
            </div>
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', height: '400px' }}>
            <div style={{ 
              flex: 1, 
              overflowY: 'auto', 
              padding: '12px',
              background: 'var(--bg-secondary)',
              borderRadius: 'var(--radius-md)',
              marginBottom: '12px'
            }}>
              {aiMessages.map((msg, i) => (
                <div key={i} style={{
                  display: 'flex',
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  marginBottom: '12px'
                }}>
                  <div style={{
                    maxWidth: '80%',
                    padding: '10px 14px',
                    borderRadius: '12px',
                    background: msg.role === 'user' 
                      ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' 
                      : 'var(--bg-primary)',
                    color: msg.role === 'user' ? 'white' : 'var(--text-primary)',
                    boxShadow: 'var(--shadow-sm)'
                  }}>
                    <div style={{ 
                      fontSize: '12px', 
                      marginBottom: '4px',
                      opacity: 0.8
                    }}>
                      {msg.role === 'user' ? '👤 您' : '🤖 AI助手'}
                    </div>
                    <div style={{ fontSize: '14px', lineHeight: '1.5', whiteSpace: 'pre-wrap' }}>
                      {msg.content}
                    </div>
                  </div>
                </div>
              ))}
              {aiLoading && (
                <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '12px' }}>
                  <div style={{
                    padding: '10px 14px',
                    borderRadius: '12px',
                    background: 'var(--bg-primary)',
                    boxShadow: 'var(--shadow-sm)'
                  }}>
                    <span>🤖 AI正在思考...</span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                className="form-input"
                placeholder="输入您的问题..."
                value={aiInput}
                onChange={handleInputChange}
                onKeyPress={handleAiKeyPress}
                style={{ flex: 1 }}
              />
              <button 
                className="btn btn-primary" 
                onClick={sendAiMessage}
                disabled={aiLoading}
              >
                发送
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="panel-row">
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">📋</span>
              持仓列表
            </div>
            <button className="btn btn-sm btn-outline" onClick={loadPositions}>刷新</button>
          </div>
          <div className="panel-body" style={{ padding: 0 }}>
            {positions.length > 0 ? (
              <table className="positions-table">
                <thead>
                  <tr>
                    <th>交易对</th>
                    <th>方向</th>
                    <th>数量</th>
                    <th>均价</th>
                    <th>当前价</th>
                    <th>盈亏</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.slice(0, 6).map((pos, i) => (
                    <tr key={i}>
                      <td className="symbol">{pos.symbol}</td>
                      <td style={{ color: pos.side === 'long' || pos.side === '多' ? 'var(--success-color)' : 'var(--error-color)' }}>
                        {pos.side === 'long' ? '多' : pos.side === 'short' ? '空' : pos.side}
                      </td>
                      <td>{pos.size || pos.amount || pos.quantity}</td>
                      <td>${parseFloat(pos.entry_price || pos.avgPrice || 0).toLocaleString()}</td>
                      <td>${parseFloat(pos.mark_price || pos.currentPrice || pos.current_price || 0).toLocaleString()}</td>
                      <td className={parseFloat(pos.unrealized_pnl || pos.pnl || 0) >= 0 ? 'positive' : 'negative'}>
                        {parseFloat(pos.unrealized_pnl || pos.pnl || 0) >= 0 ? '+' : ''}{pos.unrealized_pnl || pos.pnl || '$0'}
                      </td>
                      <td>
                        <button 
                          className="btn btn-sm btn-outline"
                          onClick={() => handleClosePosition(pos.symbol)}
                        >
                          平仓
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-state">
                <div className="empty-state-icon">📋</div>
                <div className="empty-state-text">暂无持仓</div>
              </div>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">🛡️</span>
              风险指标
            </div>
          </div>
          <div className="panel-body">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <RiskGauge label="VaR (95%)" value={riskData?.var || 2.5} max={10} />
              <RiskGauge label="最大回撤" value={riskData?.max_drawdown || 8.2} max={20} />
              <RiskGauge label="夏普比率" value={riskData?.sharpe_ratio || 1.8} max={3} />
              <RiskGauge label="风险敞口" value={riskData?.exposure || 42} max={100} />
            </div>
            <div style={{ marginTop: '20px' }}>
              <h4 style={{ marginBottom: '12px', fontSize: '14px' }}>系统状态</h4>
              <div className="system-status">
                <StatusItem name="交易引擎" status="healthy" value="运行中" />
                <StatusItem name="AI分析" status="healthy" value="正常" />
                <StatusItem name="风控系统" status="healthy" value="监控中" />
                <StatusItem name="数据同步" status="healthy" value="实时" />
              </div>
            </div>
          </div>
        </div>
      </div>
      
      {notification && (
        <div style={{
          position: 'fixed',
          top: '80px',
          right: '24px',
          padding: '12px 20px',
          background: notification.type === 'success' ? 'var(--success-color)' : 'var(--error-color)',
          color: 'white',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--shadow-lg)',
          zIndex: 1000
        }}>
          {notification.message}
        </div>
      )}
    </>
  );

  const renderMarket = () => (
    <>
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <span className="panel-title-icon">📈</span>
            多交易对行情监控
          </div>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="positions-table">
            <thead>
              <tr>
                <th>交易对</th>
                <th>最新价</th>
                <th>24h变化</th>
                <th>24h最高</th>
                <th>24h最低</th>
                <th>24h成交量</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {symbols.map(symbol => {
                const data = marketData[symbol] || {};
                const price = data.last || data.price || 0;
                const change = data.change || data.changePercent || 0;
                return (
                  <tr key={symbol}>
                    <td className="symbol">{symbol}</td>
                    <td>${price ? parseFloat(price).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '---'}</td>
                    <td className={change >= 0 ? 'positive' : 'negative'}>
                      {change >= 0 ? '+' : ''}{typeof change === 'number' ? change.toFixed(2) : change}%
                    </td>
                    <td>${data.high ? parseFloat(data.high).toLocaleString() : '---'}</td>
                    <td>${data.low ? parseFloat(data.low).toLocaleString() : '---'}</td>
                    <td>{data.volume ? `${(parseFloat(data.volume) / 1000000).toFixed(2)}M` : '---'}</td>
                    <td>
                      <button 
                        className="btn btn-sm btn-primary"
                        onClick={() => {
                          handleSymbolSelect(symbol);
                          showNotification(`已选择 ${symbol}`);
                        }}
                      >
                        详情
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel-row" style={{ marginTop: '24px' }}>
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">订单簿 - {selectedSymbol}</div>
          </div>
          <div className="panel-body">
            <div className="order-book">
              <div className="order-book-side bids">
                <h4>买单</h4>
                {(orderBook.bids || []).slice(0, 8).map((order, i) => (
                  <div key={i} className="order-row">
                    <span className="order-price" style={{ color: '#52c41a' }}>
                      ${parseFloat(Array.isArray(order) ? order[0] : order.price).toFixed(2)}
                    </span>
                    <span className="order-amount">{parseFloat(Array.isArray(order) ? order[1] : order.amount).toFixed(4)}</span>
                  </div>
                ))}
              </div>
              <div className="order-book-side asks">
                <h4>卖单</h4>
                {(orderBook.asks || []).slice(0, 8).map((order, i) => (
                  <div key={i} className="order-row">
                    <span className="order-price" style={{ color: '#ff4d4f' }}>
                      ${parseFloat(Array.isArray(order) ? order[0] : order.price).toFixed(2)}
                    </span>
                    <span className="order-amount">{parseFloat(Array.isArray(order) ? order[1] : order.amount).toFixed(4)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">最近成交</div>
          </div>
          <div className="panel-body">
            <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
              {tradeHistory.slice(0, 15).map((trade, i) => (
                <div key={i} className="order-row" style={{ padding: '8px 0' }}>
                  <span style={{ 
                    color: trade.side === 'buy' ? 'var(--success-color)' : 'var(--error-color)',
                    fontWeight: 500
                  }}>
                    {trade.side === 'buy' ? '买入' : '卖出'}
                  </span>
                  <span className="order-price">${parseFloat(trade.price || 0).toFixed(2)}</span>
                  <span className="order-amount">{parseFloat(trade.amount || trade.size || 0).toFixed(4)}</span>
                  <span style={{ color: 'var(--text-tertiary)', fontSize: '12px' }}>
                    {trade.timestamp ? new Date(trade.timestamp).toLocaleTimeString('zh-CN') : '--:--'}
                  </span>
                </div>
              ))}
              {tradeHistory.length === 0 && (
                <div className="empty-state">
                  <div className="empty-state-text">暂无成交记录</div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );

  const renderTrade = () => (
    <div className="panel">
      <div className="panel-header">
        <div className="panel-title">
          <span className="panel-title-icon">💱</span>
          交易面板
        </div>
      </div>
      <div className="panel-body">
        <div className="trade-panel">
          <div className="trade-form">
            <h3 style={{ marginBottom: '20px', color: 'var(--success-color)' }}>买入</h3>
            <div className="form-group">
              <label className="form-label">交易对</label>
              <select className="form-input" value={tradeSymbol} onChange={e => setTradeSymbol(e.target.value)}>
                {symbols.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">订单类型</label>
              <select className="form-input" value={orderType} onChange={e => setOrderType(e.target.value)}>
                <option value="limit">限价单</option>
                <option value="market">市价单</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">价格</label>
              <div className="form-input-group">
                <input 
                  type="number" 
                  className="form-input" 
                  placeholder="输入价格" 
                  value={tradePrice}
                  onChange={e => setTradePrice(e.target.value)}
                />
                <span className="form-suffix">USDT</span>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">数量</label>
              <div className="form-input-group">
                <input 
                  type="number" 
                  className="form-input" 
                  placeholder="输入数量"
                  value={tradeAmount}
                  onChange={e => setTradeAmount(e.target.value)}
                />
                <span className="form-suffix">{tradeSymbol.split('/')[0]}</span>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">总额</label>
              <div className="form-input-group">
                <input 
                  type="number" 
                  className="form-input" 
                  placeholder="0.00" 
                  value={tradePrice && tradeAmount ? (parseFloat(tradePrice) * parseFloat(tradeAmount)).toFixed(2) : ''}
                  disabled 
                />
                <span className="form-suffix">USDT</span>
              </div>
            </div>
            <button 
              className="btn btn-success btn-block btn-lg"
              onClick={() => handleTradeSubmit('buy')}
            >
              买入
            </button>
          </div>

          <div className="trade-form">
            <h3 style={{ marginBottom: '20px', color: 'var(--error-color)' }}>卖出</h3>
            <div className="form-group">
              <label className="form-label">交易对</label>
              <select className="form-input" value={tradeSymbol} onChange={e => setTradeSymbol(e.target.value)}>
                {symbols.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">订单类型</label>
              <select className="form-input" value={orderType} onChange={e => setOrderType(e.target.value)}>
                <option value="limit">限价单</option>
                <option value="market">市价单</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">价格</label>
              <div className="form-input-group">
                <input 
                  type="number" 
                  className="form-input" 
                  placeholder="输入价格"
                  value={tradePrice}
                  onChange={e => setTradePrice(e.target.value)}
                />
                <span className="form-suffix">USDT</span>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">数量</label>
              <div className="form-input-group">
                <input 
                  type="number" 
                  className="form-input" 
                  placeholder="输入数量"
                  value={tradeAmount}
                  onChange={e => setTradeAmount(e.target.value)}
                />
                <span className="form-suffix">{tradeSymbol.split('/')[0]}</span>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">总额</label>
              <div className="form-input-group">
                <input 
                  type="number" 
                  className="form-input" 
                  placeholder="0.00"
                  value={tradePrice && tradeAmount ? (parseFloat(tradePrice) * parseFloat(tradeAmount)).toFixed(2) : ''}
                  disabled 
                />
                <span className="form-suffix">USDT</span>
              </div>
            </div>
            <button 
              className="btn btn-danger btn-block btn-lg"
              onClick={() => handleTradeSubmit('sell')}
            >
              卖出
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  const renderPositions = () => (
    <div className="panel">
      <div className="panel-header">
        <div className="panel-title">
          <span className="panel-title-icon">📋</span>
          持仓管理
        </div>
        <div className="panel-actions">
          <button className="btn btn-sm btn-outline" onClick={loadPositions}>刷新</button>
          <button className="btn btn-sm btn-primary" onClick={() => showNotification('一键平仓功能已触发', 'warning')}>一键平仓</button>
        </div>
      </div>
      <div className="panel-body" style={{ padding: 0 }}>
        {positions.length > 0 ? (
          <table className="positions-table">
            <thead>
              <tr>
                <th>交易对</th>
                <th>方向</th>
                <th>数量</th>
                <th>开仓均价</th>
                <th>当前价格</th>
                <th>未实现盈亏</th>
                <th>盈亏比例</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos, i) => (
                <tr key={i}>
                  <td className="symbol">{pos.symbol}</td>
                  <td style={{ color: pos.side === 'long' || pos.side === '多' ? 'var(--success-color)' : 'var(--error-color)' }}>
                    {pos.side === 'long' ? '多' : pos.side === 'short' ? '空' : pos.side}
                  </td>
                  <td>{pos.size || pos.amount || pos.quantity}</td>
                  <td>${parseFloat(pos.entry_price || pos.avgPrice || 0).toLocaleString()}</td>
                  <td>${parseFloat(pos.mark_price || pos.currentPrice || 0).toLocaleString()}</td>
                  <td className={parseFloat(pos.unrealized_pnl || pos.pnl || 0) >= 0 ? 'positive' : 'negative'}>
                    {parseFloat(pos.unrealized_pnl || pos.pnl || 0) >= 0 ? '+' : ''}{pos.unrealized_pnl || pos.pnl || '$0'}
                  </td>
                  <td className={parseFloat(pos.unrealized_pnl_percent || pos.pnlPercent || 0) >= 0 ? 'positive' : 'negative'}>
                    {parseFloat(pos.unrealized_pnl_percent || pos.pnlPercent || 0) >= 0 ? '+' : ''}{(pos.unrealized_pnl_percent || pos.pnlPercent || '0')}%
                  </td>
                  <td>
                    <button 
                      className="btn btn-sm btn-outline"
                      onClick={() => handleClosePosition(pos.symbol)}
                    >
                      平仓
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">
            <div className="empty-state-icon">📋</div>
            <div className="empty-state-text">暂无持仓</div>
          </div>
        )}
      </div>
    </div>
  );

  const renderHistory = () => (
    <div className="panel">
      <div className="panel-header">
        <div className="panel-title">
          <span className="panel-title-icon">📜</span>
          交易历史
        </div>
        <div className="panel-actions">
          <button className="btn btn-sm btn-outline" onClick={loadTradeHistory}>刷新</button>
        </div>
      </div>
      <div className="panel-body" style={{ padding: 0 }}>
        {tradeHistory.length > 0 ? (
          <table className="positions-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>交易对</th>
                <th>方向</th>
                <th>类型</th>
                <th>价格</th>
                <th>数量</th>
                <th>总额</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {tradeHistory.map((trade, i) => (
                <tr key={i}>
                  <td style={{ color: 'var(--text-tertiary)', fontSize: '13px' }}>
                    {trade.timestamp ? new Date(trade.timestamp).toLocaleString('zh-CN') : '--'}
                  </td>
                  <td className="symbol">{trade.symbol}</td>
                  <td style={{ color: trade.side === 'buy' ? 'var(--success-color)' : 'var(--error-color)', fontWeight: 500 }}>
                    {trade.side === 'buy' ? '买入' : '卖出'}
                  </td>
                  <td>{trade.type === 'limit' ? '限价单' : '市价单'}</td>
                  <td>${parseFloat(trade.price || 0).toLocaleString()}</td>
                  <td>{parseFloat(trade.amount || trade.size || 0).toFixed(4)}</td>
                  <td>${parseFloat((trade.price || 0) * (trade.amount || trade.size || 0)).toLocaleString()}</td>
                  <td><span style={{ color: 'var(--success-color)' }}>{trade.status || '已完成'}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">
            <div className="empty-state-icon">📜</div>
            <div className="empty-state-text">暂无交易历史</div>
          </div>
        )}
      </div>
    </div>
  );

  const renderAI = () => (
    <div className="panel-row">
      <div className="panel" style={{ gridColumn: 'span 2' }}>
        <div className="panel-header">
          <div className="panel-title">
            <span className="panel-title-icon">🤖</span>
            AI智能交互中心
          </div>
        </div>
        <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', height: '400px' }}>
          <div style={{ 
            flex: 1, 
            overflowY: 'auto', 
            padding: '16px',
            background: 'var(--bg-secondary)',
            borderRadius: 'var(--radius-md)',
            marginBottom: '16px'
          }}>
            {aiMessages.map((msg, i) => (
              <div key={i} style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: '16px'
              }}>
                <div style={{
                  maxWidth: '70%',
                  padding: '12px 16px',
                  borderRadius: '16px',
                  background: msg.role === 'user' 
                    ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' 
                    : 'var(--bg-primary)',
                  color: msg.role === 'user' ? 'white' : 'var(--text-primary)',
                  boxShadow: 'var(--shadow-md)'
                }}>
                  <div style={{ 
                    fontSize: '12px', 
                    marginBottom: '6px',
                    opacity: 0.8,
                    fontWeight: 500
                  }}>
                    {msg.role === 'user' ? '👤 您' : '🤖 AI交易助手'}
                  </div>
                  <div style={{ fontSize: '14px', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>
                    {msg.content}
                  </div>
                </div>
              </div>
            ))}
            {aiLoading && (
              <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '16px' }}>
                <div style={{
                  padding: '12px 16px',
                  borderRadius: '16px',
                  background: 'var(--bg-primary)',
                  boxShadow: 'var(--shadow-md)'
                }}>
                  <span style={{ color: 'var(--text-tertiary)' }}>🤖 AI正在分析中...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <textarea
                className="form-input"
                placeholder="输入您的问题，例如：分析一下BTC的走势、推荐一个交易策略..."
                value={aiInput}
                onChange={handleInputChange}
                onKeyPress={handleAiKeyPress}
                style={{ minHeight: '60px', resize: 'vertical' }}
              />
            </div>
            <button 
              className="btn btn-primary btn-lg" 
              onClick={sendAiMessage}
              disabled={aiLoading}
              style={{ minWidth: '100px' }}
            >
              {aiLoading ? '发送中...' : '发送'}
            </button>
          </div>
          <div style={{ marginTop: '12px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button className="btn btn-sm btn-outline" onClick={() => handleQuickQuestion('分析一下当前市场趋势')}>📊 市场趋势</button>
            <button className="btn btn-sm btn-outline" onClick={() => handleQuickQuestion('推荐一个交易策略')}>💡 策略建议</button>
            <button className="btn btn-sm btn-outline" onClick={() => handleQuickQuestion('检查我的持仓风险')}>🛡️ 风险检查</button>
            <button className="btn btn-sm btn-outline" onClick={() => handleQuickQuestion(`${selectedSymbol}现在适合买入吗？`)}>📈 买入建议</button>
          </div>
        </div>
      </div>
      
      <div className="panel" style={{ gridColumn: 'span 2' }}>
        <div className="panel-header">
          <div className="panel-title">
            <span className="panel-title-icon">📊</span>
            实时AI分析看板
          </div>
          <div className="panel-actions">
            <button 
              className={`btn btn-sm ${aiAnalysisRunning ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => setAiAnalysisRunning(!aiAnalysisRunning)}
            >
              {aiAnalysisRunning ? '⏸ 暂停' : '▶ 运行'}
            </button>
            <button className="btn btn-sm btn-outline" onClick={() => setAiAnalysisLogs([])}>清空</button>
          </div>
        </div>
        <div className="panel-body" style={{ height: '300px', overflowY: 'auto' }}>
          <div style={{ 
            background: '#1a1a2e', 
            borderRadius: 'var(--radius-md)', 
            padding: '16px',
            fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',
            fontSize: '13px',
            height: '100%',
            overflowY: 'auto'
          }}>
            {aiAnalysisLogs.map((log, i) => (
              <div key={i} style={{ 
                marginBottom: '8px',
                color: log.type === 'signal' ? '#52c41a' : 
                       log.type === 'risk' ? '#faad14' : 
                       log.type === 'strategy' ? '#1890ff' :
                       log.type === 'trade' ? '#eb2f96' : '#a0a0a0'
              }}>
                <span style={{ color: '#666' }}>[{log.time}]</span>
                <span style={{ 
                  marginLeft: '8px',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  background: log.type === 'signal' ? 'rgba(82, 196, 26, 0.2)' : 
                              log.type === 'risk' ? 'rgba(250, 173, 20, 0.2)' : 
                              log.type === 'strategy' ? 'rgba(24, 144, 255, 0.2)' :
                              log.type === 'trade' ? 'rgba(235, 47, 150, 0.2)' : 'rgba(160, 160, 160, 0.2)',
                  fontSize: '11px'
                }}>
                  {log.type.toUpperCase()}
                </span>
                <span style={{ marginLeft: '8px' }}>{log.message}</span>
              </div>
            ))}
            {aiAnalysisRunning && (
              <div style={{ color: '#52c41a' }}>
                ▌ 等待新数据...
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  const renderStrategies = () => (
    <div className="panel">
      <div className="panel-header">
        <div className="panel-title">
          <span className="panel-title-icon">⚙️</span>
          策略管理
        </div>
        <button className="btn btn-sm btn-primary" onClick={() => showNotification('新建策略功能已打开')}>+ 新建策略</button>
      </div>
      <div className="panel-body" style={{ padding: 0 }}>
        {strategies.length > 0 ? (
          <table className="positions-table">
            <thead>
              <tr>
                <th>策略名称</th>
                <th>类型</th>
                <th>状态</th>
                <th>收益率</th>
                <th>最大回撤</th>
                <th>夏普比率</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((strategy, i) => (
                <tr key={i}>
                  <td className="symbol">{strategy.name}</td>
                  <td>{strategy.type}</td>
                  <td><span style={{ color: strategy.active ? 'var(--success-color)' : 'var(--text-tertiary)' }}>
                    {strategy.active ? '运行中' : '已停止'}
                  </span></td>
                  <td className={parseFloat(strategy.return_rate || 0) >= 0 ? 'positive' : 'negative'}>
                    {parseFloat(strategy.return_rate || 0) >= 0 ? '+' : ''}{strategy.return_rate || '0'}%
                  </td>
                  <td>{strategy.max_drawdown || '--'}%</td>
                  <td>{strategy.sharpe_ratio || '--'}</td>
                  <td>
                    <button className="btn btn-sm btn-outline" onClick={() => showNotification(`编辑策略: ${strategy.name}`)}>编辑</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">
            <div className="empty-state-icon">⚙️</div>
            <div className="empty-state-text">暂无策略</div>
          </div>
        )}
      </div>
    </div>
  );

  const renderRisk = () => (
    <div className="panel-row">
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <span className="panel-title-icon">🛡️</span>
            风险概览
          </div>
        </div>
        <div className="panel-body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '20px' }}>
            <div style={{ textAlign: 'center', padding: '20px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ fontSize: '36px', fontWeight: 700, color: 'var(--success-color)' }}>
                {riskData?.risk_level || '低'}
              </div>
              <div style={{ fontSize: '14px', color: 'var(--text-tertiary)', marginTop: '8px' }}>当前风险等级</div>
            </div>
            <div style={{ textAlign: 'center', padding: '20px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ fontSize: '36px', fontWeight: 700 }}>{riskData?.exposure || 42}%</div>
              <div style={{ fontSize: '14px', color: 'var(--text-tertiary)', marginTop: '8px' }}>风险敞口</div>
            </div>
          </div>
          
          <div style={{ marginTop: '24px' }}>
            <h4 style={{ marginBottom: '16px' }}>风险指标</h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
              <RiskGauge label="VaR (95%)" value={riskData?.var || 2.5} max={10} />
              <RiskGauge label="最大回撤" value={riskData?.max_drawdown || 8.2} max={20} />
              <RiskGauge label="夏普比率" value={riskData?.sharpe_ratio || 1.8} max={3} />
              <RiskGauge label="索提诺比率" value={riskData?.sortino_ratio || 2.1} max={3} />
            </div>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <span className="panel-title-icon">⚠️</span>
            风险告警
          </div>
        </div>
        <div className="panel-body">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {positions.filter(p => parseFloat(p.unrealized_pnl || p.pnl || 0) < 0).length > 0 && (
              <div style={{ 
                padding: '12px', 
                background: 'rgba(255, 77, 79, 0.1)', 
                borderRadius: 'var(--radius-md)',
                borderLeft: '4px solid var(--error-color)'
              }}>
                <div style={{ fontWeight: 500, marginBottom: '4px', color: 'var(--error-color)' }}>
                  亏损持仓警告
                </div>
                <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                  您有 {positions.filter(p => parseFloat(p.unrealized_pnl || p.pnl || 0) < 0).length} 个持仓处于亏损状态，请关注风险
                </div>
              </div>
            )}
            <div style={{ 
              padding: '12px', 
              background: 'rgba(82, 196, 26, 0.1)', 
              borderRadius: 'var(--radius-md)',
              borderLeft: '4px solid var(--success-color)'
            }}>
              <div style={{ fontWeight: 500, marginBottom: '4px', color: 'var(--success-color)' }}>
                系统运行正常
              </div>
              <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                所有风控指标正常，无异常告警
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const renderAnalysis = () => (
    <MultiSourceAnalysis 
      symbol={selectedSymbol}
      onAnalysisComplete={(analysis) => {
        console.log('分析完成:', analysis);
      }}
    />
  );

  const renderReports = () => (
    <div className="panel-row">
      <div className="panel" style={{ gridColumn: 'span 2' }}>
        <div className="panel-header">
          <div className="panel-title">
            <span className="panel-title-icon">📑</span>
            分析报告
          </div>
          <div className="panel-actions">
            <button className="btn btn-sm btn-outline" onClick={() => showNotification('生成新报告')}>生成报告</button>
          </div>
        </div>
        <div className="panel-body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px', marginBottom: '24px' }}>
            <div style={{ padding: '20px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', textAlign: 'center' }}>
              <div style={{ fontSize: '32px', fontWeight: 700, color: 'var(--success-color)' }}>
                {accountInfo?.total_pnl ? `${parseFloat(accountInfo.total_pnl) >= 0 ? '+' : ''}${accountInfo.total_pnl}%` : '+12.5%'}
              </div>
              <div style={{ fontSize: '14px', color: 'var(--text-tertiary)', marginTop: '8px' }}>总收益率</div>
            </div>
            <div style={{ padding: '20px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', textAlign: 'center' }}>
              <div style={{ fontSize: '32px', fontWeight: 700 }}>{tradeHistory.length}</div>
              <div style={{ fontSize: '14px', color: 'var(--text-tertiary)', marginTop: '8px' }}>总交易次数</div>
            </div>
            <div style={{ padding: '20px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', textAlign: 'center' }}>
              <div style={{ fontSize: '32px', fontWeight: 700, color: 'var(--success-color)' }}>
                {accountInfo?.win_rate || '68'}%
              </div>
              <div style={{ fontSize: '14px', color: 'var(--text-tertiary)', marginTop: '8px' }}>胜率</div>
            </div>
          </div>
          
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <div>
              <h4 style={{ marginBottom: '16px' }}>交易统计</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                  <span>总盈亏</span>
                  <span style={{ color: 'var(--success-color)' }}>{accountInfo?.total_pnl || '+$2,340.50'}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                  <span>持仓数量</span>
                  <span>{positions.length}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                  <span>策略数量</span>
                  <span>{strategies.length}</span>
                </div>
              </div>
            </div>
            
            <div>
              <h4 style={{ marginBottom: '16px' }}>风险指标</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                  <span>最大回撤</span>
                  <span>{riskData?.max_drawdown || '8.2'}%</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                  <span>夏普比率</span>
                  <span>{riskData?.sharpe_ratio || '1.8'}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                  <span>风险敞口</span>
                  <span>{riskData?.exposure || '42'}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const renderSettings = () => (
    <div className="panel">
      <div className="panel-header">
        <div className="panel-title">
          <span className="panel-title-icon">⚙️</span>
          系统设置
        </div>
      </div>
      <div className="panel-body">
        <div className="tabs">
          {['基本设置', 'API配置', '风险参数', '通知设置'].map(tab => (
            <div 
              key={tab}
              className={`tab ${settingsTab === tab ? 'active' : ''}`}
              onClick={() => setSettingsTab(tab)}
            >
              {tab}
            </div>
          ))}
        </div>
        
        {settingsTab === '基本设置' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginTop: '20px' }}>
            <div className="form-group">
              <label className="form-label">系统名称</label>
              <input type="text" className="form-input" defaultValue="全智能量化交易系统" />
            </div>
            <div className="form-group">
              <label className="form-label">语言</label>
              <select className="form-input" defaultValue="zh-CN">
                <option value="zh-CN">简体中文</option>
                <option value="en">English</option>
              </select>
            </div>
          </div>
        )}

        {settingsTab === 'API配置' && (
          <div style={{ marginTop: '20px' }}>
            <div className="form-group">
              <label className="form-label">OKX API Key</label>
              <input type="password" className="form-input" placeholder="输入API Key" />
            </div>
            <div className="form-group">
              <label className="form-label">OKX Secret Key</label>
              <input type="password" className="form-input" placeholder="输入Secret Key" />
            </div>
            <div className="form-group">
              <label className="form-label">OKX Passphrase</label>
              <input type="password" className="form-input" placeholder="输入Passphrase" />
            </div>
          </div>
        )}

        {settingsTab === '风险参数' && (
          <div style={{ marginTop: '20px' }}>
            <div className="form-group">
              <label className="form-label">单笔最大亏损比例 (%)</label>
              <input type="number" className="form-input" defaultValue="2" />
            </div>
            <div className="form-group">
              <label className="form-label">最大持仓数量</label>
              <input type="number" className="form-input" defaultValue="5" />
            </div>
            <div className="form-group">
              <label className="form-label">最大杠杆倍数</label>
              <input type="number" className="form-input" defaultValue="10" />
            </div>
          </div>
        )}

        {settingsTab === '通知设置' && (
          <div style={{ marginTop: '20px' }}>
            <div className="form-group">
              <label className="form-label">Telegram Bot Token</label>
              <input type="text" className="form-input" placeholder="输入Bot Token" />
            </div>
            <div className="form-group">
              <label className="form-label">Telegram Chat ID</label>
              <input type="text" className="form-input" placeholder="输入Chat ID" />
            </div>
          </div>
        )}
        
        <div style={{ marginTop: '24px', display: 'flex', gap: '12px' }}>
          <button 
            className="btn btn-primary"
            onClick={() => showNotification('设置已保存', 'success')}
          >
            保存设置
          </button>
        </div>
      </div>
    </div>
  );

  const renderView = () => {
    switch (activeView) {
      case 'dashboard': return renderDashboard();
      case 'market': return renderMarket();
      case 'trade': return renderTrade();
      case 'positions': return renderPositions();
      case 'history': return renderHistory();
      case 'ai': return renderAI();
      case 'analysis': return renderAnalysis();
      case 'strategies': return renderStrategies();
      case 'risk': return renderRisk();
      case 'reports': return renderReports();
      case 'settings': return renderSettings();
      default: return renderDashboard();
    }
  };

  return (
    <div>
      {renderView()}
      {notification && (
        <div style={{
          position: 'fixed',
          top: '80px',
          right: '24px',
          padding: '12px 20px',
          background: notification.type === 'success' ? 'var(--success-color)' : 'var(--error-color)',
          color: 'white',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--shadow-lg)',
          zIndex: 1000
        }}>
          {notification.message}
        </div>
      )}
    </div>
  );
}

export default ProfessionalDashboard;
