import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import { 
  AreaChart, Area, 
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';

const MultiSourceAnalysis = ({ symbol, onAnalysisComplete }) => {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [analysisHistory, setAnalysisHistory] = useState([]);

  const loadAnalysis = useCallback(async () => {
    if (!symbol) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const result = await api.dataFusion.analyzeMarket(symbol);
      setAnalysis(result.data);
      
      if (onAnalysisComplete) {
        onAnalysisComplete(result.data);
      }
      
      // 加载分析历史
      const historyResult = await api.dataFusion.getAnalysisHistory();
      if (historyResult && historyResult.data && historyResult.data.length) {
        setAnalysisHistory(historyResult.data.slice(0, 10));
      }
      
    } catch (err) {
      setError('获取分析数据失败');
      console.error('分析失败:', err);
      
      // 使用模拟数据
      setAnalysis(getMockAnalysis(symbol));
    } finally {
      setLoading(false);
    }
  }, [symbol, onAnalysisComplete]);

  useEffect(() => {
    loadAnalysis();
  }, [loadAnalysis]);

  const getSentimentColor = (sentiment) => {
    switch (sentiment) {
      case 'extreme_greed':
        return '#52c41a';
      case 'greed':
        return '#73d13d';
      case 'neutral':
        return '#faad14';
      case 'fear':
        return '#ff7a45';
      case 'extreme_fear':
        return '#ff4d4f';
      default:
        return '#1890ff';
    }
  };

  const getSignalStrengthText = (strength) => {
    switch (strength) {
      case 5:
        return '非常强';
      case 4:
        return '强';
      case 3:
        return '中等';
      case 2:
        return '弱';
      case 1:
        return '非常弱';
      default:
        return '未知';
    }
  };

  const getRecommendationText = (recommendation) => {
    switch (recommendation) {
      case 'bullish':
        return '看多';
      case 'bearish':
        return '看空';
      case 'neutral':
        return '中性';
      default:
        return '未知';
    }
  };

  const getRecommendationColor = (recommendation) => {
    switch (recommendation) {
      case 'bullish':
        return 'var(--success-color)';
      case 'bearish':
        return 'var(--error-color)';
      case 'neutral':
        return 'var(--warning-color)';
      default:
        return 'var(--text-primary)';
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>🔍</div>
        <div style={{ color: 'var(--text-tertiary)' }}>正在分析 {symbol} 多源数据...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>❌</div>
        <div style={{ color: 'var(--error-color)' }}>{error}</div>
        <button 
          className="btn btn-primary" 
          onClick={loadAnalysis}
          style={{ marginTop: '16px' }}
        >
          重新分析
        </button>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>📊</div>
        <div style={{ color: 'var(--text-tertiary)' }}>点击分析按钮开始分析 {symbol}</div>
        <button 
          className="btn btn-primary" 
          onClick={loadAnalysis}
          style={{ marginTop: '16px' }}
        >
          开始分析
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* 主要分析结果 */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <span className="panel-title-icon">🧠</span>
            多源数据融合分析 - {symbol}
          </div>
          <button className="btn btn-sm btn-outline" onClick={loadAnalysis}>
            刷新分析
          </button>
        </div>
        <div className="panel-body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px', marginBottom: '24px' }}>
            {/* 综合情绪 */}
            <div style={{ 
              textAlign: 'center', 
              padding: '20px', 
              background: 'var(--bg-secondary)', 
              borderRadius: 'var(--radius-md)'
            }}>
              <div style={{ fontSize: '14px', color: 'var(--text-tertiary)', marginBottom: '8px' }}>综合情绪</div>
              <div 
                style={{ 
                  fontSize: '28px', 
                  fontWeight: 700, 
                  color: getSentimentColor(analysis.overall_sentiment)
                }}
              >
                {analysis.overall_sentiment === 'extreme_greed' ? '极度贪婪' :
                 analysis.overall_sentiment === 'greed' ? '贪婪' :
                 analysis.overall_sentiment === 'neutral' ? '中性' :
                 analysis.overall_sentiment === 'fear' ? '恐惧' :
                 analysis.overall_sentiment === 'extreme_fear' ? '极度恐惧' :
                 analysis.overall_sentiment}
              </div>
              <div style={{ 
                marginTop: '8px', 
                fontSize: '14px', 
                color: 'var(--text-tertiary)'
              }}>
                情绪得分: {analysis.overall_sentiment_score.toFixed(2)}
              </div>
            </div>

            {/* 信号强度 */}
            <div style={{ 
              textAlign: 'center', 
              padding: '20px', 
              background: 'var(--bg-secondary)', 
              borderRadius: 'var(--radius-md)'
            }}>
              <div style={{ fontSize: '14px', color: 'var(--text-tertiary)', marginBottom: '8px' }}>信号强度</div>
              <div style={{ 
                fontSize: '28px', 
                fontWeight: 700, 
                color: analysis.signal_strength >= 4 ? 'var(--success-color)' : 
                       analysis.signal_strength >= 3 ? 'var(--warning-color)' : 'var(--error-color)'
              }}>
                {getSignalStrengthText(analysis.signal_strength)}
              </div>
              <div style={{ 
                marginTop: '8px', 
                fontSize: '14px', 
                color: 'var(--text-tertiary)'
              }}>
                强度: {analysis.signal_strength}/5
              </div>
            </div>

            {/* 交易建议 */}
            <div style={{ 
              textAlign: 'center', 
              padding: '20px', 
              background: 'var(--bg-secondary)', 
              borderRadius: 'var(--radius-md)'
            }}>
              <div style={{ fontSize: '14px', color: 'var(--text-tertiary)', marginBottom: '8px' }}>交易建议</div>
              <div style={{ 
                fontSize: '28px', 
                fontWeight: 700, 
                color: getRecommendationColor(analysis.recommendation)
              }}>
                {getRecommendationText(analysis.recommendation)}
              </div>
              <div style={{ 
                marginTop: '8px', 
                fontSize: '14px', 
                color: 'var(--text-tertiary)'
              }}>
                置信度: {Math.round(analysis.confidence * 100)}%
              </div>
            </div>
          </div>

          {/* 关键洞察 */}
          <div style={{ marginBottom: '24px' }}>
            <h4 style={{ marginBottom: '12px', fontSize: '14px', fontWeight: 600 }}>关键洞察</h4>
            <div style={{ 
              background: 'var(--bg-secondary)', 
              borderRadius: 'var(--radius-md)', 
              padding: '16px'
            }}>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {analysis.key_insights.map((insight, index) => (
                  <li key={index} style={{ 
                    marginBottom: '8px', 
                    display: 'flex', 
                    alignItems: 'flex-start'
                  }}>
                    <span style={{ 
                      marginRight: '8px', 
                      color: 'var(--primary-color)',
                      marginTop: '4px'
                    }}>•</span>
                    <span>{insight}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* 风险因素 */}
          {analysis.risk_factors && analysis.risk_factors.length > 0 && (
            <div style={{ marginBottom: '24px' }}>
              <h4 style={{ marginBottom: '12px', fontSize: '14px', fontWeight: 600, color: 'var(--error-color)' }}>风险因素</h4>
              <div style={{ 
                background: 'rgba(255, 77, 79, 0.1)', 
                borderRadius: 'var(--radius-md)', 
                padding: '16px'
              }}>
                <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                  {analysis.risk_factors.map((risk, index) => (
                    <li key={index} style={{ 
                      marginBottom: '8px', 
                      display: 'flex', 
                      alignItems: 'flex-start'
                    }}>
                      <span style={{ 
                        marginRight: '8px', 
                        color: 'var(--error-color)',
                        marginTop: '4px'
                      }}>⚠️</span>
                      <span>{risk}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* 机会信号 */}
          {analysis.opportunity_signals && analysis.opportunity_signals.length > 0 && (
            <div style={{ marginBottom: '24px' }}>
              <h4 style={{ marginBottom: '12px', fontSize: '14px', fontWeight: 600, color: 'var(--success-color)' }}>机会信号</h4>
              <div style={{ 
                background: 'rgba(82, 196, 26, 0.1)', 
                borderRadius: 'var(--radius-md)', 
                padding: '16px'
              }}>
                <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                  {analysis.opportunity_signals.map((opportunity, index) => (
                    <li key={index} style={{ 
                      marginBottom: '8px', 
                      display: 'flex', 
                      alignItems: 'flex-start'
                    }}>
                      <span style={{ 
                        marginRight: '8px', 
                        color: 'var(--success-color)',
                        marginTop: '4px'
                      }}>💡</span>
                      <span>{opportunity}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* 数据源信息 */}
          <div style={{ marginBottom: '24px' }}>
            <h4 style={{ marginBottom: '12px', fontSize: '14px', fontWeight: 600 }}>数据源信息</h4>
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              {analysis.data_sources_used.map((source, index) => (
                <span key={index} style={{
                  padding: '6px 12px',
                  background: 'var(--primary-color)',
                  color: 'white',
                  borderRadius: '16px',
                  fontSize: '12px'
                }}>
                  ✅ {source}
                </span>
              ))}
              {analysis.data_sources_missing.map((source, index) => (
                <span key={index} style={{
                  padding: '6px 12px',
                  background: 'var(--bg-secondary)',
                  color: 'var(--text-tertiary)',
                  borderRadius: '16px',
                  fontSize: '12px'
                }}>
                  ❌ {source}
                </span>
              ))}
            </div>
          </div>

          {/* 分析时间 */}
          <div style={{ 
            textAlign: 'right', 
            fontSize: '12px', 
            color: 'var(--text-tertiary)'
          }}>
            分析时间: {new Date(analysis.timestamp).toLocaleString('zh-CN')}
          </div>
        </div>
      </div>

      {/* 历史分析 */}
      {analysisHistory.length > 0 && (
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">📜</span>
              历史分析记录
            </div>
          </div>
          <div className="panel-body" style={{ maxHeight: '300px', overflowY: 'auto' }}>
            <table className="positions-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>情绪</th>
                  <th>信号强度</th>
                  <th>建议</th>
                  <th>置信度</th>
                </tr>
              </thead>
              <tbody>
                {analysisHistory.map((item, index) => (
                  <tr key={index}>
                    <td style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>
                      {new Date(item.timestamp).toLocaleTimeString('zh-CN')}
                    </td>
                    <td style={{ 
                      color: getSentimentColor(item.overall_sentiment)
                    }}>
                      {item.overall_sentiment === 'extreme_greed' ? '极度贪婪' :
                       item.overall_sentiment === 'greed' ? '贪婪' :
                       item.overall_sentiment === 'neutral' ? '中性' :
                       item.overall_sentiment === 'fear' ? '恐惧' :
                       item.overall_sentiment === 'extreme_fear' ? '极度恐惧' :
                       item.overall_sentiment}
                    </td>
                    <td>{getSignalStrengthText(item.signal_strength)}</td>
                    <td style={{ color: getRecommendationColor(item.recommendation) }}>
                      {getRecommendationText(item.recommendation)}
                    </td>
                    <td>{Math.round(item.confidence * 100)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

// 模拟数据
function getMockAnalysis(symbol) {
  const sentiments = ['extreme_greed', 'greed', 'neutral', 'fear', 'extreme_fear'];
  const recommendations = ['bullish', 'bearish', 'neutral'];
  
  return {
    overall_sentiment: sentiments[Math.floor(Math.random() * sentiments.length)],
    overall_sentiment_score: (Math.random() * 2 - 1).toFixed(2),
    signal_strength: Math.floor(Math.random() * 5) + 1,
    technical_analysis: {
      trend: (Math.random() * 2 - 1).toFixed(2),
      rsi: (Math.random() * 40 + 30).toFixed(2),
      volatility: (Math.random() * 0.1).toFixed(3)
    },
    sentiment_analysis: {
      price_change_7d: (Math.random() * 20 - 10).toFixed(2),
      positive_days: Math.floor(Math.random() * 7) + 1,
      negative_days: 7 - Math.floor(Math.random() * 7)
    },
    on_chain_analysis: {
      tx_count: Math.floor(Math.random() * 500) + 100,
      large_tx_count: Math.floor(Math.random() * 50) + 5
    },
    news_analysis: {
      article_count: Math.floor(Math.random() * 50) + 10,
      positive_mentions: Math.floor(Math.random() * 20) + 5,
      negative_mentions: Math.floor(Math.random() * 10)
    },
    social_media_analysis: {
      tweet_count: Math.floor(Math.random() * 500) + 100,
      engagement: Math.floor(Math.random() * 5000) + 1000
    },
    key_insights: [
      '技术面显示上升趋势明显',
      '市场情绪偏多，投资者信心增强',
      '链上活跃度较高，大额交易频繁',
      '新闻报道正面，社交媒体讨论积极'
    ],
    risk_factors: [
      '短期超买，可能出现回调',
      '市场波动较大，风险增加'
    ],
    opportunity_signals: [
      '突破阻力位，可能继续上涨',
      '成交量放大，动能增强'
    ],
    recommendation: recommendations[Math.floor(Math.random() * recommendations.length)],
    confidence: (Math.random() * 0.3 + 0.7).toFixed(2),
    data_sources_used: ['technical', 'market_sentiment', 'news', 'social_media'],
    data_sources_missing: ['on_chain'],
    timestamp: new Date().toISOString()
  };
}

export default MultiSourceAnalysis;