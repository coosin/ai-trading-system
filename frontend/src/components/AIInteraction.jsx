import React, { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';

function AIInteraction() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      content: '您好！我是您的智能交易助手。我可以帮您分析市场、生成策略、回答交易相关问题。请问有什么可以帮助您的？',
      role: 'ai',
      timestamp: new Date().toLocaleTimeString()
    }
  ]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [analysisType, setAnalysisType] = useState('market');
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT');
  const [analysisResult, setAnalysisResult] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async () => {
    if (!inputText.trim()) return;

    const userMessage = {
      id: Date.now(),
      content: inputText,
      role: 'user',
      timestamp: new Date().toLocaleTimeString()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputText('');
    setLoading(true);

    try {
      // 调用AI API获取响应
      const response = await api.ai.chat(inputText);
      
      if (response.status === 'success') {
        const aiResponse = {
          id: Date.now() + 1,
          content: response.data?.response || '抱歉，我没有理解您的问题。',
          role: 'ai',
          timestamp: new Date().toLocaleTimeString(),
          model: response.data?.model_id,
          tokens: response.data?.tokens_used
        };
        setMessages(prev => [...prev, aiResponse]);
      } else {
        // API返回错误
        const aiResponse = {
          id: Date.now() + 1,
          content: `AI服务暂时不可用: ${response.message}`,
          role: 'ai',
          timestamp: new Date().toLocaleTimeString()
        };
        setMessages(prev => [...prev, aiResponse]);
      }
    } catch (error) {
      console.error('AI响应失败:', error);
      // 失败时使用模拟响应作为后备
      const aiResponse = {
        id: Date.now() + 1,
        content: generateAIResponse(inputText),
        role: 'ai',
        timestamp: new Date().toLocaleTimeString()
      };
      setMessages(prev => [...prev, aiResponse]);
    } finally {
      setLoading(false);
    }
  };

  const generateAIResponse = (message) => {
    const lowerMessage = message.toLowerCase();
    
    if (lowerMessage.includes('市场') || lowerMessage.includes('分析')) {
      return '根据当前市场数据分析，比特币价格呈现上升趋势，主要受机构资金流入和宏观经济因素影响。建议关注交易量变化和关键技术指标，如MACD和RSI。';
    } else if (lowerMessage.includes('策略') || lowerMessage.includes('建议')) {
      return '基于当前市场状况，我建议采用趋势跟随策略，结合移动平均线和波动率指标。同时设置合理的止损和止盈点位，控制风险敞口。';
    } else if (lowerMessage.includes('风险') || lowerMessage.includes('管理')) {
      return '风险管理建议：1. 控制单笔交易资金不超过总资金的5%；2. 设置2-3%的止损；3. 多元化投资组合；4. 定期评估策略表现并调整。';
    } else if (lowerMessage.includes('回测')) {
      return '回测建议：使用至少1年的历史数据，考虑不同市场环境，评估关键指标如夏普比率、最大回撤和胜率。同时注意过度拟合的风险。';
    } else {
      return '我理解您的问题。作为智能交易助手，我可以帮助您分析市场趋势、制定交易策略、评估风险等。请问您具体需要哪方面的帮助？';
    }
  };

  const handleAnalysis = async () => {
    setIsAnalyzing(true);
    setAnalysisResult(null);

    try {
      // 模拟分析过程
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // 生成模拟分析结果
      const result = {
        symbol: selectedSymbol,
        analysisType: analysisType === 'market' ? '市场分析' : analysisType === 'strategy' ? '策略分析' : '风险分析',
        timestamp: new Date().toLocaleString(),
        prediction: Math.random() > 0.5 ? '看涨' : '看跌',
        confidence: (Math.random() * 30 + 70).toFixed(1),
        keyMetrics: {
          volatility: (Math.random() * 5 + 1).toFixed(2),
          volumeChange: (Math.random() * 50 - 25).toFixed(1),
          sentiment: (Math.random() * 40 + 30).toFixed(1),
          momentum: Math.random() > 0.5 ? '正向' : '负向'
        },
        recommendations: [
          '关注价格突破关键阻力位',
          '设置合理的止损点位',
          '结合其他指标进行综合判断',
          '密切关注市场消息面'
        ],
        technicalIndicators: {
          macd: Math.random() > 0.5 ? '金叉' : '死叉',
          rsi: (Math.random() * 40 + 30).toFixed(1),
          ma: Math.random() > 0.5 ? '多头排列' : '空头排列',
          bollinger: Math.random() > 0.5 ? '突破上轨' : '在区间内'
        }
      };

      setAnalysisResult(result);
    } catch (error) {
      console.error('分析失败:', error);
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div style={{ padding: '20px' }}>
      <h2>🤖 AI智能交互中心</h2>
      <p>与AI助手对话，获取市场分析和交易建议</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginTop: '30px' }}>
        {/* AI对话区域 */}
        <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px' }}>
          <h3>💬 AI对话</h3>
          <div style={{ 
            height: '400px', 
            overflowY: 'auto', 
            border: '1px solid #e9ecef', 
            borderRadius: '4px', 
            padding: '15px',
            marginBottom: '15px',
            backgroundColor: 'white'
          }}>
            {messages.map(message => (
              <div 
                key={message.id} 
                style={{
                  marginBottom: '15px',
                  display: 'flex',
                  flexDirection: message.role === 'user' ? 'row-reverse' : 'row'
                }}
              >
                <div style={{
                  maxWidth: '70%',
                  padding: '10px 15px',
                  borderRadius: '18px',
                  backgroundColor: message.role === 'user' ? '#3498db' : '#e9ecef',
                  color: message.role === 'user' ? 'white' : 'black'
                }}>
                  <p style={{ margin: 0 }}>{message.content}</p>
                  <p style={{ 
                    margin: '5px 0 0 0', 
                    fontSize: '10px', 
                    opacity: 0.7,
                    textAlign: message.role === 'user' ? 'right' : 'left'
                  }}>
                    {message.timestamp}
                    {message.model && (
                      <span style={{ marginLeft: '10px', fontSize: '9px' }}>
                        ({message.model}{message.tokens ? ` · ${message.tokens} tokens` : ''})
                      </span>
                    )}
                  </p>
                </div>
              </div>
            ))}
            {loading && (
              <div style={{
                display: 'flex',
                marginBottom: '15px'
              }}>
                <div style={{
                  maxWidth: '70%',
                  padding: '10px 15px',
                  borderRadius: '18px',
                  backgroundColor: '#e9ecef',
                  color: 'black'
                }}>
                  <p style={{ margin: 0 }}>AI正在思考...</p>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
              placeholder="输入您的问题..."
              style={{
                flex: 1,
                padding: '10px',
                border: '1px solid #ced4da',
                borderRadius: '4px',
                fontSize: '14px'
              }}
            />
            <button
              onClick={handleSendMessage}
              disabled={loading}
              style={{
                padding: '10px 20px',
                backgroundColor: '#3498db',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: loading ? 'not-allowed' : 'pointer',
                fontSize: '14px'
              }}
            >
              {loading ? '发送中...' : '发送'}
            </button>
          </div>
        </div>

        {/* 智能分析区域 */}
        <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px' }}>
          <h3>📊 智能分析</h3>
          <div style={{ marginBottom: '20px' }}>
            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontSize: '14px', fontWeight: 'bold' }}>
                分析类型
              </label>
              <select
                value={analysisType}
                onChange={(e) => setAnalysisType(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1px solid #ced4da',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              >
                <option value="market">市场分析</option>
                <option value="strategy">策略分析</option>
                <option value="risk">风险分析</option>
              </select>
            </div>
            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontSize: '14px', fontWeight: 'bold' }}>
                交易对
              </label>
              <select
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1px solid #ced4da',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              >
                <option value="BTC/USDT">BTC/USDT</option>
                <option value="ETH/USDT">ETH/USDT</option>
                <option value="SOL/USDT">SOL/USDT</option>
                <option value="BNB/USDT">BNB/USDT</option>
                <option value="ADA/USDT">ADA/USDT</option>
              </select>
            </div>
            <button
              onClick={handleAnalysis}
              disabled={isAnalyzing}
              style={{
                width: '100%',
                padding: '10px',
                backgroundColor: '#27ae60',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: isAnalyzing ? 'not-allowed' : 'pointer',
                fontSize: '14px',
                fontWeight: 'bold'
              }}
            >
              {isAnalyzing ? '分析中...' : '开始分析'}
            </button>
          </div>

          {analysisResult && (
            <div style={{ backgroundColor: 'white', padding: '15px', borderRadius: '4px', border: '1px solid #e9ecef' }}>
              <h4 style={{ marginTop: 0, marginBottom: '15px' }}>
                {analysisResult.analysisType} - {analysisResult.symbol}
              </h4>
              <p style={{ fontSize: '12px', color: '#666', marginBottom: '15px' }}>
                分析时间: {analysisResult.timestamp}
              </p>
              <div style={{ marginBottom: '15px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
                  <span style={{ fontWeight: 'bold' }}>市场预测:</span>
                  <span style={{
                    color: analysisResult.prediction === '看涨' ? '#27ae60' : '#e74c3c',
                    fontWeight: 'bold'
                  }}>
                    {analysisResult.prediction}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
                  <span style={{ fontWeight: 'bold' }}>置信度:</span>
                  <span style={{ fontWeight: 'bold' }}>{analysisResult.confidence}%</span>
                </div>
              </div>
              <div style={{ marginBottom: '15px' }}>
                <h5 style={{ marginBottom: '10px', fontSize: '14px' }}>关键指标</h5>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div style={{ backgroundColor: '#f8f9fa', padding: '8px', borderRadius: '4px' }}>
                    <span style={{ fontSize: '12px', color: '#666' }}>波动率:</span>
                    <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>{analysisResult.keyMetrics.volatility}%</p>
                  </div>
                  <div style={{ backgroundColor: '#f8f9fa', padding: '8px', borderRadius: '4px' }}>
                    <span style={{ fontSize: '12px', color: '#666' }}>量能变化:</span>
                    <p style={{ margin: '5px 0 0 0', fontWeight: 'bold', color: analysisResult.keyMetrics.volumeChange > 0 ? '#27ae60' : '#e74c3c' }}>
                      {analysisResult.keyMetrics.volumeChange > 0 ? '+' : ''}{analysisResult.keyMetrics.volumeChange}%
                    </p>
                  </div>
                  <div style={{ backgroundColor: '#f8f9fa', padding: '8px', borderRadius: '4px' }}>
                    <span style={{ fontSize: '12px', color: '#666' }}>市场情绪:</span>
                    <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>{analysisResult.keyMetrics.sentiment}%</p>
                  </div>
                  <div style={{ backgroundColor: '#f8f9fa', padding: '8px', borderRadius: '4px' }}>
                    <span style={{ fontSize: '12px', color: '#666' }}>动量:</span>
                    <p style={{ margin: '5px 0 0 0', fontWeight: 'bold', color: analysisResult.keyMetrics.momentum === '正向' ? '#27ae60' : '#e74c3c' }}>
                      {analysisResult.keyMetrics.momentum}
                    </p>
                  </div>
                </div>
              </div>
              <div style={{ marginBottom: '15px' }}>
                <h5 style={{ marginBottom: '10px', fontSize: '14px' }}>技术指标</h5>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div style={{ backgroundColor: '#f8f9fa', padding: '8px', borderRadius: '4px' }}>
                    <span style={{ fontSize: '12px', color: '#666' }}>MACD:</span>
                    <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>{analysisResult.technicalIndicators.macd}</p>
                  </div>
                  <div style={{ backgroundColor: '#f8f9fa', padding: '8px', borderRadius: '4px' }}>
                    <span style={{ fontSize: '12px', color: '#666' }}>RSI:</span>
                    <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>{analysisResult.technicalIndicators.rsi}</p>
                  </div>
                  <div style={{ backgroundColor: '#f8f9fa', padding: '8px', borderRadius: '4px' }}>
                    <span style={{ fontSize: '12px', color: '#666' }}>均线:</span>
                    <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>{analysisResult.technicalIndicators.ma}</p>
                  </div>
                  <div style={{ backgroundColor: '#f8f9fa', padding: '8px', borderRadius: '4px' }}>
                    <span style={{ fontSize: '12px', color: '#666' }}>布林带:</span>
                    <p style={{ margin: '5px 0 0 0', fontWeight: 'bold' }}>{analysisResult.technicalIndicators.bollinger}</p>
                  </div>
                </div>
              </div>
              <div>
                <h5 style={{ marginBottom: '10px', fontSize: '14px' }}>AI建议</h5>
                <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                  {analysisResult.recommendations.map((rec, index) => (
                    <li key={index} style={{ 
                      marginBottom: '5px', 
                      padding: '5px 10px',
                      backgroundColor: '#e8f5e8',
                      borderRadius: '4px',
                      fontSize: '13px'
                    }}>
                      {rec}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 预设问题 */}
      <div style={{ marginTop: '30px' }}>
        <h3>💡 快速提问</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginTop: '15px' }}>
          <button 
            onClick={() => {
              setInputText('分析当前比特币市场趋势');
              handleSendMessage();
            }}
            style={{
              padding: '8px 16px',
              backgroundColor: '#e9ecef',
              border: '1px solid #ced4da',
              borderRadius: '20px',
              cursor: 'pointer',
              fontSize: '13px'
            }}
          >
            分析比特币趋势
          </button>
          <button 
            onClick={() => {
              setInputText('推荐一个适合当前市场的交易策略');
              handleSendMessage();
            }}
            style={{
              padding: '8px 16px',
              backgroundColor: '#e9ecef',
              border: '1px solid #ced4da',
              borderRadius: '20px',
              cursor: 'pointer',
              fontSize: '13px'
            }}
          >
            推荐交易策略
          </button>
          <button 
            onClick={() => {
              setInputText('如何管理交易风险');
              handleSendMessage();
            }}
            style={{
              padding: '8px 16px',
              backgroundColor: '#e9ecef',
              border: '1px solid #ced4da',
              borderRadius: '20px',
              cursor: 'pointer',
              fontSize: '13px'
            }}
          >
            风险管理建议
          </button>
          <button 
            onClick={() => {
              setInputText('如何优化回测参数');
              handleSendMessage();
            }}
            style={{
              padding: '8px 16px',
              backgroundColor: '#e9ecef',
              border: '1px solid #ced4da',
              borderRadius: '20px',
              cursor: 'pointer',
              fontSize: '13px'
            }}
          >
            回测优化
          </button>
          <button 
            onClick={() => {
              setInputText('解释什么是MACD指标');
              handleSendMessage();
            }}
            style={{
              padding: '8px 16px',
              backgroundColor: '#e9ecef',
              border: '1px solid #ced4da',
              borderRadius: '20px',
              cursor: 'pointer',
              fontSize: '13px'
            }}
          >
            解释技术指标
          </button>
        </div>
      </div>
    </div>
  );
}

export default AIInteraction;