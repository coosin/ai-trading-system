import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { useSystemStore, useAuthStore } from '../store';

function ControlCenter() {
  const [marketData, setMarketData] = useState({});
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [systemStatus, setSystemStatus] = useState({});
  const [activeModules, setActiveModules] = useState([]);
  const [externalData, setExternalData] = useState({});
  const [loading, setLoading] = useState(true);
  
  const { status, fetchStatus } = useSystemStore();
  const { isAuthenticated } = useAuthStore();

  useEffect(() => {
    if (isAuthenticated) {
      loadControlCenterData();
      const interval = setInterval(loadControlCenterData, 5000);
      return () => clearInterval(interval);
    }
  }, [isAuthenticated]);

  const loadControlCenterData = async () => {
    setLoading(true);
    try {
      // 获取市场数据
      const tickerData = await api.market.getTicker('BTC/USDT');
      setMarketData({
        symbol: 'BTC/USDT',
        price: tickerData.price || 0,
        change: (Math.random() * 2 - 1).toFixed(2),
        volume: tickerData.volume || 0
      });

      // 获取系统状态
      const statusResponse = await api.system.getStatus();
      setSystemStatus(statusResponse);

      // 模拟AI分析数据
      setAiAnalysis({
        marketTrend: Math.random() > 0.5 ? '看涨' : '看跌',
        confidence: (Math.random() * 30 + 70).toFixed(1),
        keyFactors: ['交易量增加', '技术指标金叉', '市场情绪积极'],
        recommendation: Math.random() > 0.3 ? '持有' : Math.random() > 0.5 ? '买入' : '卖出'
      });

      // 模拟外部数据
      setExternalData({
        news: [
          '美联储暗示将保持利率稳定',
          '大型机构开始增持加密资产',
          '比特币ETF申请进展顺利'
        ],
        socialSentiment: (Math.random() * 40 + 30).toFixed(1),
        marketFearGreed: Math.floor(Math.random() * 100)
      });

      // 获取活跃模块
      setActiveModules([
        { name: '策略管理器', status: '运行中', health: 'healthy' },
        { name: '风险管理', status: '运行中', health: 'healthy' },
        { name: '市场分析', status: '运行中', health: 'healthy' },
        { name: 'AI分析', status: '运行中', health: 'healthy' },
        { name: '回测系统', status: '就绪', health: 'healthy' }
      ]);

    } catch (error) {
      console.error('加载总控中心数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleModuleAction = async (moduleName, action) => {
    console.log(`对模块 ${moduleName} 执行 ${action} 操作`);
    // 这里可以添加实际的模块控制逻辑
  };

  return (
    <div style={{ padding: '20px' }}>
      <h2>全智能量化交易总控中心</h2>
      <p>实时监控和控制所有系统功能</p>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}>
          <div>加载中...</div>
        </div>
      ) : (
        <div>
          {/* 市场概览 */}
          <div style={{ marginBottom: '30px' }}>
            <h3>📊 市场概览</h3>
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
              gap: '20px',
              marginTop: '15px'
            }}>
              <div style={{ 
                backgroundColor: '#f8f9fa', 
                padding: '20px', 
                borderRadius: '8px',
                borderLeft: '4px solid #3498db'
              }}>
                <h4>比特币价格</h4>
                <p style={{ fontSize: '24px', fontWeight: 'bold' }}>
                  ${marketData.price?.toLocaleString() || '0'}
                </p>
                <p style={{ 
                  color: marketData.change > 0 ? '#27ae60' : '#e74c3c',
                  fontSize: '14px'
                }}>
                  {marketData.change > 0 ? '+' : ''}{marketData.change}%
                </p>
              </div>
              <div style={{ 
                backgroundColor: '#f8f9fa', 
                padding: '20px', 
                borderRadius: '8px',
                borderLeft: '4px solid #27ae60'
              }}>
                <h4>24h交易量</h4>
                <p style={{ fontSize: '24px', fontWeight: 'bold' }}>
                  ${(marketData.volume / 1000000).toFixed(2)}M
                </p>
                <p style={{ fontSize: '14px', color: '#666' }}>
                  BTC/USDT
                </p>
              </div>
              <div style={{ 
                backgroundColor: '#f8f9fa', 
                padding: '20px', 
                borderRadius: '8px',
                borderLeft: '4px solid #e67e22'
              }}>
                <h4>市场情绪</h4>
                <p style={{ fontSize: '24px', fontWeight: 'bold' }}>
                  {externalData.marketFearGreed}%
                </p>
                <p style={{ fontSize: '14px', color: '#666' }}>
                  {externalData.marketFearGreed > 70 ? '贪婪' : externalData.marketFearGreed < 30 ? '恐惧' : '中性'}
                </p>
              </div>
              <div style={{ 
                backgroundColor: '#f8f9fa', 
                padding: '20px', 
                borderRadius: '8px',
                borderLeft: '4px solid #9b59b6'
              }}>
                <h4>社交情绪</h4>
                <p style={{ fontSize: '24px', fontWeight: 'bold' }}>
                  {externalData.socialSentiment}%
                </p>
                <p style={{ fontSize: '14px', color: '#666' }}>
                  积极情绪占比
                </p>
              </div>
            </div>
          </div>

          {/* AI分析 */}
          <div style={{ marginBottom: '30px' }}>
            <h3>🤖 AI智能分析</h3>
            <div style={{ 
              backgroundColor: '#f8f9fa', 
              padding: '20px', 
              borderRadius: '8px',
              marginTop: '15px'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                <div>
                  <h4>市场趋势预测</h4>
                  <p style={{ fontSize: '18px', fontWeight: 'bold' }}>
                    {aiAnalysis?.marketTrend || '分析中'}
                  </p>
                </div>
                <div style={{ 
                  backgroundColor: aiAnalysis?.confidence > 85 ? '#27ae60' : aiAnalysis?.confidence > 70 ? '#f39c12' : '#e74c3c',
                  color: 'white',
                  padding: '10px 20px',
                  borderRadius: '20px',
                  fontSize: '14px',
                  fontWeight: 'bold'
                }}>
                  置信度: {aiAnalysis?.confidence || '0'}%
                </div>
              </div>
              <div style={{ marginBottom: '15px' }}>
                <h5>关键因素</h5>
                <ul style={{ listStyle: 'none', padding: 0, marginTop: '10px' }}>
                  {aiAnalysis?.keyFactors?.map((factor, index) => (
                    <li key={index} style={{ 
                      backgroundColor: 'white', 
                      padding: '8px 12px', 
                      borderRadius: '4px',
                      marginBottom: '5px',
                      borderLeft: '3px solid #3498db'
                    }}>
                      {factor}
                    </li>
                  )) || <li>分析中...</li>}
                </ul>
              </div>
              <div style={{ 
                backgroundColor: aiAnalysis?.recommendation === '买入' ? '#e8f5e8' : 
                                aiAnalysis?.recommendation === '卖出' ? '#ffebee' : '#fff3e0',
                padding: '15px',
                borderRadius: '6px',
                borderLeft: `4px solid ${aiAnalysis?.recommendation === '买入' ? '#27ae60' : 
                                        aiAnalysis?.recommendation === '卖出' ? '#e74c3c' : '#f39c12'}`
              }}>
                <h5>AI推荐</h5>
                <p style={{ fontSize: '16px', fontWeight: 'bold' }}>
                  {aiAnalysis?.recommendation || '分析中'}
                </p>
              </div>
            </div>
          </div>

          {/* 系统状态 */}
          <div style={{ marginBottom: '30px' }}>
            <h3>⚙️ 系统状态</h3>
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
              gap: '20px',
              marginTop: '15px'
            }}>
              {activeModules.map((module, index) => (
                <div key={index} style={{ 
                  backgroundColor: '#f8f9fa', 
                  padding: '20px', 
                  borderRadius: '8px',
                  borderLeft: `4px solid ${module.health === 'healthy' ? '#27ae60' : '#e74c3c'}`
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h4>{module.name}</h4>
                    <span style={{ 
                      backgroundColor: module.status === '运行中' ? '#27ae60' : '#f39c12',
                      color: 'white',
                      padding: '4px 12px',
                      borderRadius: '12px',
                      fontSize: '12px'
                    }}>
                      {module.status}
                    </span>
                  </div>
                  <div style={{ marginTop: '15px', display: 'flex', gap: '10px' }}>
                    <button 
                      onClick={() => handleModuleAction(module.name, 'start')}
                      style={{
                        padding: '6px 12px',
                        backgroundColor: '#3498db',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '12px'
                      }}
                    >
                      启动
                    </button>
                    <button 
                      onClick={() => handleModuleAction(module.name, 'stop')}
                      style={{
                        padding: '6px 12px',
                        backgroundColor: '#e74c3c',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '12px'
                      }}
                    >
                      停止
                    </button>
                    <button 
                      onClick={() => handleModuleAction(module.name, 'restart')}
                      style={{
                        padding: '6px 12px',
                        backgroundColor: '#f39c12',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '12px'
                      }}
                    >
                      重启
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 外部数据 */}
          <div style={{ marginBottom: '30px' }}>
            <h3>🌐 外部数据</h3>
            <div style={{ 
              backgroundColor: '#f8f9fa', 
              padding: '20px', 
              borderRadius: '8px',
              marginTop: '15px'
            }}>
              <h4>市场新闻</h4>
              <ul style={{ listStyle: 'none', padding: 0, marginTop: '10px' }}>
                {externalData.news?.map((news, index) => (
                  <li key={index} style={{ 
                    backgroundColor: 'white', 
                    padding: '12px', 
                    borderRadius: '4px',
                    marginBottom: '10px',
                    borderLeft: '3px solid #3498db'
                  }}>
                    {news}
                  </li>
                )) || <li>加载中...</li>}
              </ul>
            </div>
          </div>

          {/* 快速操作 */}
          <div>
            <h3>🚀 快速操作</h3>
            <div style={{ 
              display: 'flex', 
              flexWrap: 'wrap',
              gap: '15px',
              marginTop: '15px'
            }}>
              <button style={{
                padding: '12px 24px',
                backgroundColor: '#3498db',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: 'bold'
              }}>
                启动所有模块
              </button>
              <button style={{
                padding: '12px 24px',
                backgroundColor: '#e74c3c',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: 'bold'
              }}>
                停止所有模块
              </button>
              <button style={{
                padding: '12px 24px',
                backgroundColor: '#27ae60',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: 'bold'
              }}>
                运行回测
              </button>
              <button style={{
                padding: '12px 24px',
                backgroundColor: '#f39c12',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: 'bold'
              }}>
                生成AI策略
              </button>
              <button style={{
                padding: '12px 24px',
                backgroundColor: '#9b59b6',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: 'bold'
              }}>
                导出系统报告
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ControlCenter;