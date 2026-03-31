import React, { useState, useEffect } from 'react';
import { api } from '../services/api';

function ExternalData() {
  const [dataSources, setDataSources] = useState([
    {
      id: 1,
      name: 'CoinGecko API',
      type: 'market',
      status: 'connected',
      url: 'https://api.coingecko.com/api/v3',
      apiKey: '********',
      lastSync: new Date().toLocaleString(),
      isActive: true
    },
    {
      id: 2,
      name: 'CryptoCompare API',
      type: 'market',
      status: 'connected',
      url: 'https://min-api.cryptocompare.com/data',
      apiKey: '********',
      lastSync: new Date().toLocaleString(),
      isActive: true
    },
    {
      id: 3,
      name: 'News API',
      type: 'news',
      status: 'connected',
      url: 'https://newsapi.org/v2',
      apiKey: '********',
      lastSync: new Date().toLocaleString(),
      isActive: true
    },
    {
      id: 4,
      name: 'Twitter API',
      type: 'social',
      status: 'disconnected',
      url: 'https://api.twitter.com/2',
      apiKey: '',
      lastSync: 'N/A',
      isActive: false
    },
    {
      id: 5,
      name: 'Reddit API',
      type: 'social',
      status: 'disconnected',
      url: 'https://api.reddit.com',
      apiKey: '',
      lastSync: 'N/A',
      isActive: false
    }
  ]);
  
  const [newsData, setNewsData] = useState([]);
  const [socialData, setSocialData] = useState([]);
  const [marketData, setMarketData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [newSource, setNewSource] = useState({
    name: '',
    type: 'market',
    url: '',
    apiKey: ''
  });
  const [editingSource, setEditingSource] = useState(null);

  useEffect(() => {
    loadExternalData();
  }, []);

  const loadExternalData = async () => {
    setLoading(true);
    try {
      // 尝试从API获取市场数据
      const symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'];
      const marketDataFromApi = [];
      
      for (const symbol of symbols) {
        try {
          const tickerData = await api.market.getTicker(symbol);
          marketDataFromApi.push({
            id: Date.now() + Math.random(),
            symbol,
            price: tickerData.price || 0,
            change24h: (Math.random() * 5 - 2.5).toFixed(2),
            volume24h: tickerData.volume || 0,
            source: 'API',
            lastUpdated: new Date().toLocaleString()
          });
        } catch (error) {
          console.error(`获取${symbol}数据失败:`, error);
        }
      }
      
      if (marketDataFromApi.length > 0) {
        setMarketData(marketDataFromApi);
      } else {
        // 失败时使用模拟数据
        const mockMarket = [
          {
            id: 1,
            symbol: 'BTC/USDT',
            price: 69500,
            change24h: 2.5,
            volume24h: 25000000000,
            source: 'CoinGecko',
            lastUpdated: new Date().toLocaleString()
          },
          {
            id: 2,
            symbol: 'ETH/USDT',
            price: 3200,
            change24h: 1.8,
            volume24h: 12000000000,
            source: 'CryptoCompare',
            lastUpdated: new Date().toLocaleString()
          },
          {
            id: 3,
            symbol: 'SOL/USDT',
            price: 110,
            change24h: -0.5,
            volume24h: 3000000000,
            source: 'CoinGecko',
            lastUpdated: new Date().toLocaleString()
          }
        ];
        setMarketData(mockMarket);
      }

      // 模拟新闻数据
      const mockNews = [
        {
          id: 1,
          title: '比特币价格突破70,000美元大关',
          source: 'CoinDesk',
          publishedAt: new Date().toLocaleString(),
          url: 'https://coindesk.com',
          sentiment: 'positive'
        },
        {
          id: 2,
          title: '以太坊2.0升级进展顺利',
          source: 'Ethereum Foundation',
          publishedAt: new Date(Date.now() - 3600000).toLocaleString(),
          url: 'https://ethereum.org',
          sentiment: 'positive'
        },
        {
          id: 3,
          title: 'SEC推迟比特币ETF决定',
          source: 'Bloomberg',
          publishedAt: new Date(Date.now() - 7200000).toLocaleString(),
          url: 'https://bloomberg.com',
          sentiment: 'neutral'
        },
        {
          id: 4,
          title: '大型机构开始增持加密资产',
          source: 'Financial Times',
          publishedAt: new Date(Date.now() - 10800000).toLocaleString(),
          url: 'https://ft.com',
          sentiment: 'positive'
        },
        {
          id: 5,
          title: '市场波动加剧，投资者保持谨慎',
          source: 'Reuters',
          publishedAt: new Date(Date.now() - 14400000).toLocaleString(),
          url: 'https://reuters.com',
          sentiment: 'negative'
        }
      ];
      setNewsData(mockNews);

      // 模拟社交数据
      const mockSocial = [
        {
          id: 1,
          platform: 'Twitter',
          mentions: 15420,
          sentiment: 72,
          trendingTopics: ['#Bitcoin', '#Ethereum', '#Crypto'],
          lastUpdated: new Date().toLocaleString()
        },
        {
          id: 2,
          platform: 'Reddit',
          mentions: 8760,
          sentiment: 65,
          trendingTopics: ['r/CryptoCurrency', 'r/Bitcoin', 'r/Ethereum'],
          lastUpdated: new Date().toLocaleString()
        },
        {
          id: 3,
          platform: 'Telegram',
          mentions: 5430,
          sentiment: 68,
          trendingTopics: ['Crypto Signals', 'Trading Groups', 'Market Analysis'],
          lastUpdated: new Date().toLocaleString()
        }
      ];
      setSocialData(mockSocial);

    } catch (error) {
      console.error('加载外部数据失败:', error);
      // 失败时使用模拟数据
      const mockMarket = [
        {
          id: 1,
          symbol: 'BTC/USDT',
          price: 69500,
          change24h: 2.5,
          volume24h: 25000000000,
          source: 'CoinGecko',
          lastUpdated: new Date().toLocaleString()
        },
        {
          id: 2,
          symbol: 'ETH/USDT',
          price: 3200,
          change24h: 1.8,
          volume24h: 12000000000,
          source: 'CryptoCompare',
          lastUpdated: new Date().toLocaleString()
        },
        {
          id: 3,
          symbol: 'SOL/USDT',
          price: 110,
          change24h: -0.5,
          volume24h: 3000000000,
          source: 'CoinGecko',
          lastUpdated: new Date().toLocaleString()
        }
      ];
      setMarketData(mockMarket);

      const mockNews = [
        {
          id: 1,
          title: '比特币价格突破70,000美元大关',
          source: 'CoinDesk',
          publishedAt: new Date().toLocaleString(),
          url: 'https://coindesk.com',
          sentiment: 'positive'
        },
        {
          id: 2,
          title: '以太坊2.0升级进展顺利',
          source: 'Ethereum Foundation',
          publishedAt: new Date(Date.now() - 3600000).toLocaleString(),
          url: 'https://ethereum.org',
          sentiment: 'positive'
        }
      ];
      setNewsData(mockNews);

      const mockSocial = [
        {
          id: 1,
          platform: 'Twitter',
          mentions: 15420,
          sentiment: 72,
          trendingTopics: ['#Bitcoin', '#Ethereum', '#Crypto'],
          lastUpdated: new Date().toLocaleString()
        }
      ];
      setSocialData(mockSocial);
    } finally {
      setLoading(false);
    }
  };

  const handleAddDataSource = () => {
    if (!newSource.name || !newSource.url) return;
    
    const source = {
      id: Date.now(),
      ...newSource,
      status: 'disconnected',
      lastSync: 'N/A',
      isActive: false
    };
    
    setDataSources(prev => [...prev, source]);
    setNewSource({ name: '', type: 'market', url: '', apiKey: '' });
  };

  const handleEditDataSource = (source) => {
    setEditingSource(source);
  };

  const handleUpdateDataSource = () => {
    if (!editingSource) return;
    
    setDataSources(prev => prev.map(source => 
      source.id === editingSource.id ? editingSource : source
    ));
    setEditingSource(null);
  };

  const handleToggleSource = (id) => {
    setDataSources(prev => prev.map(source => 
      source.id === id ? { ...source, isActive: !source.isActive } : source
    ));
  };

  const handleSyncSource = (id) => {
    setDataSources(prev => prev.map(source => 
      source.id === id ? { ...source, lastSync: new Date().toLocaleString(), status: 'connected' } : source
    ));
    loadExternalData();
  };

  return (
    <div style={{ padding: '20px' }}>
      <h2>🌐 外部数据源整合</h2>
      <p>管理和整合外部API数据源，获取市场、新闻和社交数据</p>

      {/* 数据源管理 */}
      <div style={{ marginBottom: '30px' }}>
        <h3>📡 数据源管理</h3>
        <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px' }}>
          <div style={{ marginBottom: '20px' }}>
            <h4>添加新数据源</h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '10px', marginTop: '15px' }}>
              <input
                type="text"
                placeholder="数据源名称"
                value={newSource.name}
                onChange={(e) => setNewSource({ ...newSource, name: e.target.value })}
                style={{
                  padding: '8px',
                  border: '1px solid #ced4da',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              />
              <select
                value={newSource.type}
                onChange={(e) => setNewSource({ ...newSource, type: e.target.value })}
                style={{
                  padding: '8px',
                  border: '1px solid #ced4da',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              >
                <option value="market">市场数据</option>
                <option value="news">新闻数据</option>
                <option value="social">社交数据</option>
                <option value="other">其他</option>
              </select>
              <input
                type="text"
                placeholder="API URL"
                value={newSource.url}
                onChange={(e) => setNewSource({ ...newSource, url: e.target.value })}
                style={{
                  padding: '8px',
                  border: '1px solid #ced4da',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              />
              <input
                type="text"
                placeholder="API Key"
                value={newSource.apiKey}
                onChange={(e) => setNewSource({ ...newSource, apiKey: e.target.value })}
                style={{
                  padding: '8px',
                  border: '1px solid #ced4da',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              />
            </div>
            <button
              onClick={handleAddDataSource}
              style={{
                marginTop: '15px',
                padding: '10px 20px',
                backgroundColor: '#3498db',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              添加数据源
            </button>
          </div>

          <div>
            <h4>已配置数据源</h4>
            <div style={{ overflowX: 'auto', marginTop: '15px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: '#e9ecef' }}>
                    <th style={{ padding: '10px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>数据源名称</th>
                    <th style={{ padding: '10px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>类型</th>
                    <th style={{ padding: '10px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>API URL</th>
                    <th style={{ padding: '10px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>API Key</th>
                    <th style={{ padding: '10px', textAlign: 'center', borderBottom: '1px solid #dee2e6' }}>状态</th>
                    <th style={{ padding: '10px', textAlign: 'center', borderBottom: '1px solid #dee2e6' }}>最后同步</th>
                    <th style={{ padding: '10px', textAlign: 'center', borderBottom: '1px solid #dee2e6' }}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {dataSources.map(source => (
                    <tr key={source.id} style={{ backgroundColor: source.isActive ? '#e3f2fd' : 'white' }}>
                      <td style={{ padding: '10px', borderBottom: '1px solid #dee2e6' }}>{source.name}</td>
                      <td style={{ padding: '10px', borderBottom: '1px solid #dee2e6' }}>
                        <span style={{
                          padding: '4px 12px',
                          borderRadius: '12px',
                          fontSize: '12px',
                          fontWeight: 'bold',
                          backgroundColor: source.type === 'market' ? '#e3f2fd' : 
                                           source.type === 'news' ? '#e8f5e8' : 
                                           source.type === 'social' ? '#fff3e0' : '#f3e5f5',
                          color: source.type === 'market' ? '#1976d2' : 
                                 source.type === 'news' ? '#388e3c' : 
                                 source.type === 'social' ? '#ef6c00' : '#7b1fa2'
                        }}>
                          {source.type === 'market' ? '市场' : 
                           source.type === 'news' ? '新闻' : 
                           source.type === 'social' ? '社交' : '其他'}
                        </span>
                      </td>
                      <td style={{ padding: '10px', borderBottom: '1px solid #dee2e6', fontSize: '12px' }}>{source.url}</td>
                      <td style={{ padding: '10px', borderBottom: '1px solid #dee2e6' }}>{source.apiKey || '未设置'}</td>
                      <td style={{ padding: '10px', textAlign: 'center', borderBottom: '1px solid #dee2e6' }}>
                        <span style={{
                          padding: '4px 12px',
                          borderRadius: '12px',
                          fontSize: '12px',
                          fontWeight: 'bold',
                          backgroundColor: source.status === 'connected' ? '#e8f5e8' : '#ffebee',
                          color: source.status === 'connected' ? '#388e3c' : '#c62828'
                        }}>
                          {source.status === 'connected' ? '已连接' : '未连接'}
                        </span>
                      </td>
                      <td style={{ padding: '10px', borderBottom: '1px solid #dee2e6', fontSize: '12px' }}>{source.lastSync}</td>
                      <td style={{ padding: '10px', textAlign: 'center', borderBottom: '1px solid #dee2e6' }}>
                        <div style={{ display: 'flex', gap: '5px', justifyContent: 'center' }}>
                          <button
                            onClick={() => handleToggleSource(source.id)}
                            style={{
                              padding: '4px 8px',
                              backgroundColor: source.isActive ? '#e74c3c' : '#27ae60',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '12px'
                            }}
                          >
                            {source.isActive ? '禁用' : '启用'}
                          </button>
                          <button
                            onClick={() => handleSyncSource(source.id)}
                            style={{
                              padding: '4px 8px',
                              backgroundColor: '#f39c12',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '12px'
                            }}
                          >
                            同步
                          </button>
                          <button
                            onClick={() => handleEditDataSource(source)}
                            style={{
                              padding: '4px 8px',
                              backgroundColor: '#3498db',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '12px'
                            }}
                          >
                            编辑
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {/* 编辑数据源对话框 */}
      {editingSource && (
        <div style={{ 
          position: 'fixed', 
          top: 0, 
          left: 0, 
          width: '100%', 
          height: '100%', 
          backgroundColor: 'rgba(0,0,0,0.5)', 
          display: 'flex', 
          justifyContent: 'center', 
          alignItems: 'center',
          zIndex: 1000
        }}>
          <div style={{ 
            backgroundColor: 'white', 
            padding: '30px', 
            borderRadius: '8px', 
            width: '500px',
            boxShadow: '0 4px 6px rgba(0,0,0,0.1)'
          }}>
            <h3>编辑数据源</h3>
            <div style={{ marginBottom: '20px' }}>
              <div style={{ marginBottom: '10px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontSize: '14px', fontWeight: 'bold' }}>
                  数据源名称
                </label>
                <input
                  type="text"
                  value={editingSource.name}
                  onChange={(e) => setEditingSource({ ...editingSource, name: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ced4da',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>
              <div style={{ marginBottom: '10px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontSize: '14px', fontWeight: 'bold' }}>
                  类型
                </label>
                <select
                  value={editingSource.type}
                  onChange={(e) => setEditingSource({ ...editingSource, type: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ced4da',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                >
                  <option value="market">市场数据</option>
                  <option value="news">新闻数据</option>
                  <option value="social">社交数据</option>
                  <option value="other">其他</option>
                </select>
              </div>
              <div style={{ marginBottom: '10px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontSize: '14px', fontWeight: 'bold' }}>
                  API URL
                </label>
                <input
                  type="text"
                  value={editingSource.url}
                  onChange={(e) => setEditingSource({ ...editingSource, url: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ced4da',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>
              <div style={{ marginBottom: '10px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontSize: '14px', fontWeight: 'bold' }}>
                  API Key
                </label>
                <input
                  type="text"
                  value={editingSource.apiKey}
                  onChange={(e) => setEditingSource({ ...editingSource, apiKey: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ced4da',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>
            </div>
            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setEditingSource(null)}
                style={{
                  padding: '8px 16px',
                  backgroundColor: '#e9ecef',
                  color: '#343a40',
                  border: '1px solid #ced4da',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '14px'
                }}
              >
                取消
              </button>
              <button
                onClick={handleUpdateDataSource}
                style={{
                  padding: '8px 16px',
                  backgroundColor: '#3498db',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '14px'
                }}
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 数据展示 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '20px' }}>
        {/* 新闻数据 */}
        <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px' }}>
          <h3>📰 新闻数据</h3>
          <div style={{ maxHeight: '400px', overflowY: 'auto', marginTop: '15px' }}>
            {newsData.map(news => (
              <div key={news.id} style={{ 
                backgroundColor: 'white', 
                padding: '15px', 
                borderRadius: '4px', 
                marginBottom: '10px',
                borderLeft: `4px solid ${news.sentiment === 'positive' ? '#27ae60' : 
                                         news.sentiment === 'negative' ? '#e74c3c' : '#f39c12'}`
              }}>
                <h4 style={{ margin: '0 0 5px 0', fontSize: '14px' }}>{news.title}</h4>
                <p style={{ margin: '5px 0', fontSize: '12px', color: '#666' }}>来源: {news.source}</p>
                <p style={{ margin: '5px 0', fontSize: '11px', color: '#999' }}>发布时间: {news.publishedAt}</p>
                <div style={{ marginTop: '10px' }}>
                  <a 
                    href={news.url} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    style={{
                      fontSize: '12px',
                      color: '#3498db',
                      textDecoration: 'none'
                    }}
                  >
                    阅读原文
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 社交数据 */}
        <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px' }}>
          <h3>🌍 社交数据</h3>
          <div style={{ maxHeight: '400px', overflowY: 'auto', marginTop: '15px' }}>
            {socialData.map(social => (
              <div key={social.id} style={{ 
                backgroundColor: 'white', 
                padding: '15px', 
                borderRadius: '4px', 
                marginBottom: '10px'
              }}>
                <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>{social.platform}</h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '10px' }}>
                  <div style={{ backgroundColor: '#f8f9fa', padding: '8px', borderRadius: '4px' }}>
                    <span style={{ fontSize: '12px', color: '#666' }}>提及次数:</span>
                    <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>{social.mentions.toLocaleString()}</p>
                  </div>
                  <div style={{ backgroundColor: '#f8f9fa', padding: '8px', borderRadius: '4px' }}>
                    <span style={{ fontSize: '12px', color: '#666' }}>情绪指数:</span>
                    <p style={{ 
                      margin: '5px 0 0 0', 
                      fontWeight: 'bold',
                      color: social.sentiment > 60 ? '#27ae60' : social.sentiment < 40 ? '#e74c3c' : '#f39c12'
                    }}>
                      {social.sentiment}%
                    </p>
                  </div>
                </div>
                <div style={{ marginBottom: '10px' }}>
                  <span style={{ fontSize: '12px', color: '#666' }}>热门话题:</span>
                  <div style={{ marginTop: '5px', display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                    {social.trendingTopics.map((topic, index) => (
                      <span key={index} style={{
                        padding: '4px 8px',
                        backgroundColor: '#e3f2fd',
                        color: '#1976d2',
                        borderRadius: '12px',
                        fontSize: '11px'
                      }}>
                        {topic}
                      </span>
                    ))}
                  </div>
                </div>
                <p style={{ margin: '5px 0', fontSize: '11px', color: '#999' }}>最后更新: {social.lastUpdated}</p>
              </div>
            ))}
          </div>
        </div>

        {/* 市场数据 */}
        <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px' }}>
          <h3>📊 市场数据</h3>
          <div style={{ maxHeight: '400px', overflowY: 'auto', marginTop: '15px' }}>
            {marketData.map(market => (
              <div key={market.id} style={{ 
                backgroundColor: 'white', 
                padding: '15px', 
                borderRadius: '4px', 
                marginBottom: '10px'
              }}>
                <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>{market.symbol}</h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '10px' }}>
                  <div style={{ backgroundColor: '#f8f9fa', padding: '8px', borderRadius: '4px' }}>
                    <span style={{ fontSize: '12px', color: '#666' }}>当前价格:</span>
                    <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>${market.price.toLocaleString()}</p>
                  </div>
                  <div style={{ backgroundColor: '#f8f9fa', padding: '8px', borderRadius: '4px' }}>
                    <span style={{ fontSize: '12px', color: '#666' }}>24h变化:</span>
                    <p style={{ 
                      margin: '5px 0 0 0', 
                      fontWeight: 'bold',
                      color: market.change24h > 0 ? '#27ae60' : '#e74c3c'
                    }}>
                      {market.change24h > 0 ? '+' : ''}{market.change24h}%
                    </p>
                  </div>
                </div>
                <div style={{ marginBottom: '10px' }}>
                  <span style={{ fontSize: '12px', color: '#666' }}>24h交易量:</span>
                  <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>${market.volume24h.toLocaleString()}</p>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#999' }}>
                  <span>数据源: {market.source}</span>
                  <span>最后更新: {market.lastUpdated}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 数据统计 */}
      <div style={{ marginTop: '30px' }}>
        <h3>📈 数据统计</h3>
        <div style={{ 
          backgroundColor: '#f8f9fa', 
          padding: '20px', 
          borderRadius: '8px',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '20px'
        }}>
          <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '4px', textAlign: 'center' }}>
            <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>活跃数据源</h4>
            <p style={{ fontSize: '32px', fontWeight: 'bold', color: '#3498db' }}>
              {dataSources.filter(s => s.isActive).length}
            </p>
            <p style={{ fontSize: '12px', color: '#666' }}>共 {dataSources.length} 个数据源</p>
          </div>
          <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '4px', textAlign: 'center' }}>
            <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>新闻文章</h4>
            <p style={{ fontSize: '32px', fontWeight: 'bold', color: '#27ae60' }}>
              {newsData.length}
            </p>
            <p style={{ fontSize: '12px', color: '#666' }}>最近获取</p>
          </div>
          <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '4px', textAlign: 'center' }}>
            <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>社交平台</h4>
            <p style={{ fontSize: '32px', fontWeight: 'bold', color: '#f39c12' }}>
              {socialData.length}
            </p>
            <p style={{ fontSize: '12px', color: '#666' }}>已整合</p>
          </div>
          <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '4px', textAlign: 'center' }}>
            <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>市场数据</h4>
            <p style={{ fontSize: '32px', fontWeight: 'bold', color: '#9b59b6' }}>
              {marketData.length}
            </p>
            <p style={{ fontSize: '12px', color: '#666' }}>交易对</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ExternalData;