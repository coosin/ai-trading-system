import React, { useState } from 'react';

function APIDocs() {
  const [activeCategory, setActiveCategory] = useState('authentication');
  const [expandedEndpoints, setExpandedEndpoints] = useState({});

  const toggleEndpoint = (endpoint) => {
    setExpandedEndpoints(prev => ({
      ...prev,
      [endpoint]: !prev[endpoint]
    }));
  };

  const apiDocumentation = {
    authentication: {
      title: '认证相关',
      endpoints: [
        {
          path: '/api/v1/auth/login',
          method: 'POST',
          description: '用户登录',
          request: {
            username: 'string',
            password: 'string'
          },
          response: {
            token: 'string',
            user: {
              id: 'number',
              username: 'string',
              role: 'string',
              email: 'string'
            },
            access_token: 'string',
            token_type: 'string',
            expires_in: 'number'
          }
        },
        {
          path: '/api/v1/auth/logout',
          method: 'POST',
          description: '用户登出',
          response: {
            status: 'string',
            message: 'string'
          }
        },
        {
          path: '/api/v1/auth/refresh',
          method: 'POST',
          description: '刷新访问令牌',
          response: {
            access_token: 'string',
            token_type: 'string',
            expires_in: 'number'
          }
        },
        {
          path: '/api/v1/auth/me',
          method: 'GET',
          description: '获取当前用户信息',
          response: {
            id: 'number',
            username: 'string',
            role: 'string',
            email: 'string',
            created_at: 'string'
          }
        }
      ]
    },
    strategies: {
      title: '策略管理',
      endpoints: [
        {
          path: '/api/v1/strategies',
          method: 'GET',
          description: '获取所有策略',
          response: 'Array<Strategy>'
        },
        {
          path: '/api/v1/strategies/{id}',
          method: 'GET',
          description: '获取单个策略',
          response: 'Strategy'
        },
        {
          path: '/api/v1/strategies',
          method: 'POST',
          description: '创建策略',
          request: {
            name: 'string',
            config: 'object',
            symbols: 'Array<string>'
          },
          response: 'Strategy'
        },
        {
          path: '/api/v1/strategies/{id}',
          method: 'PUT',
          description: '更新策略',
          request: {
            name: 'string',
            config: 'object',
            symbols: 'Array<string>'
          },
          response: 'Strategy'
        },
        {
          path: '/api/v1/strategies/{id}',
          method: 'DELETE',
          description: '删除策略',
          response: {
            status: 'string',
            message: 'string'
          }
        },
        {
          path: '/api/v1/strategies/{id}/activate',
          method: 'POST',
          description: '激活策略',
          response: {
            status: 'string',
            message: 'string'
          }
        },
        {
          path: '/api/v1/strategies/{id}/deactivate',
          method: 'POST',
          description: '停用策略',
          response: {
            status: 'string',
            message: 'string'
          }
        },
        {
          path: '/api/v1/strategies/{id}/performance',
          method: 'GET',
          description: '获取策略性能',
          response: 'StrategyPerformance'
        }
      ]
    },
    market: {
      title: '市场数据',
      endpoints: [
        {
          path: '/api/v1/market/data',
          method: 'GET',
          description: '获取市场数据',
          params: {
            symbol: 'string (默认: BTC/USDT)'
          },
          response: 'Array<MarketData>'
        }
      ]
    },
    risk: {
      title: '风险管理',
      endpoints: [
        {
          path: '/api/v1/risk/metrics',
          method: 'GET',
          description: '获取风险指标',
          response: 'RiskMetrics'
        }
      ]
    },
    trades: {
      title: '交易历史',
      endpoints: [
        {
          path: '/api/v1/trades',
          method: 'GET',
          description: '获取交易历史',
          params: {
            range: 'string (默认: 7d)'
          },
          response: 'Array<Trade>'
        }
      ]
    },
    system: {
      title: '系统管理',
      endpoints: [
        {
          path: '/api/v1/status',
          method: 'GET',
          description: '获取系统状态',
          response: 'SystemStatus'
        },
        {
          path: '/api/v1/health',
          method: 'GET',
          description: '健康检查',
          response: 'HealthStatus'
        },
        {
          path: '/api/v1/metrics',
          method: 'GET',
          description: '获取系统指标',
          response: 'SystemMetrics'
        }
      ]
    }
  };

  const categories = Object.keys(apiDocumentation);

  return (
    <div style={{ padding: '20px' }}>
      <h2>API文档</h2>
      
      <div style={{ marginBottom: '30px' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginBottom: '20px' }}>
          {categories.map(category => (
            <button
              key={category}
              onClick={() => setActiveCategory(category)}
              style={{
                padding: '8px 16px',
                backgroundColor: activeCategory === category ? '#3498db' : 'transparent',
                color: activeCategory === category ? 'white' : '#333',
                border: '1px solid #e0e0e0',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              {apiDocumentation[category].title}
            </button>
          ))}
        </div>
        
        <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
          <h3>{apiDocumentation[activeCategory].title}</h3>
          
          <div style={{ marginTop: '20px' }}>
            {apiDocumentation[activeCategory].endpoints.map((endpoint, index) => (
              <div key={index} style={{ marginBottom: '15px', border: '1px solid #e0e0e0', borderRadius: '4px', overflow: 'hidden' }}>
                <div 
                  style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between', 
                    alignItems: 'center', 
                    padding: '15px', 
                    backgroundColor: '#e9ecef',
                    cursor: 'pointer'
                  }}
                  onClick={() => toggleEndpoint(`${activeCategory}-${index}`)}
                >
                  <div>
                    <span style={{ 
                      padding: '4px 8px', 
                      backgroundColor: endpoint.method === 'GET' ? '#27ae60' : 
                                     endpoint.method === 'POST' ? '#3498db' : 
                                     endpoint.method === 'PUT' ? '#f39c12' : 
                                     '#e74c3c',
                      color: 'white',
                      borderRadius: '4px',
                      fontSize: '12px',
                      marginRight: '10px'
                    }}>
                      {endpoint.method}
                    </span>
                    <span style={{ fontWeight: 'bold' }}>{endpoint.path}</span>
                  </div>
                  <span style={{ fontSize: '16px' }}>
                    {expandedEndpoints[`${activeCategory}-${index}`] ? '▼' : '▶'}
                  </span>
                </div>
                
                {expandedEndpoints[`${activeCategory}-${index}`] && (
                  <div style={{ padding: '15px' }}>
                    <div style={{ marginBottom: '10px' }}>
                      <strong>描述：</strong>{endpoint.description}
                    </div>
                    
                    {endpoint.params && (
                      <div style={{ marginBottom: '10px' }}>
                        <strong>查询参数：</strong>
                        <pre style={{ backgroundColor: '#f1f3f4', padding: '10px', borderRadius: '4px', marginTop: '5px' }}>
                          {JSON.stringify(endpoint.params, null, 2)}
                        </pre>
                      </div>
                    )}
                    
                    {endpoint.request && (
                      <div style={{ marginBottom: '10px' }}>
                        <strong>请求体：</strong>
                        <pre style={{ backgroundColor: '#f1f3f4', padding: '10px', borderRadius: '4px', marginTop: '5px' }}>
                          {JSON.stringify(endpoint.request, null, 2)}
                        </pre>
                      </div>
                    )}
                    
                    <div style={{ marginBottom: '10px' }}>
                      <strong>响应：</strong>
                      <pre style={{ backgroundColor: '#f1f3f4', padding: '10px', borderRadius: '4px', marginTop: '5px' }}>
                        {typeof endpoint.response === 'string' ? endpoint.response : JSON.stringify(endpoint.response, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
      
      <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px' }}>
        <h3>API使用示例</h3>
        
        <div style={{ marginBottom: '20px' }}>
          <h4>使用JavaScript (Fetch API)</h4>
          <pre style={{ backgroundColor: '#f1f3f4', padding: '15px', borderRadius: '4px', overflowX: 'auto' }}>
{`// 登录示例
fetch('/api/v1/auth/login', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    username: 'admin',
    password: 'admin123'
  })
})
.then(response => response.json())
.then(data => {
  console.log('登录成功:', data);
  // 保存token
  localStorage.setItem('token', data.access_token);
});

// 获取策略列表示例
fetch('/api/v1/strategies', {
  headers: {
    'Authorization': 'Bearer ' + localStorage.getItem('token')
  }
})
.then(response => response.json())
.then(data => {
  console.log('策略列表:', data);
});`}
          </pre>
        </div>
        
        <div>
          <h4>使用Python (Requests)</h4>
          <pre style={{ backgroundColor: '#f1f3f4', padding: '15px', borderRadius: '4px', overflowX: 'auto' }}>
{`import requests

# 登录
data = {
    'username': 'admin',
    'password': 'admin123'
}
response = requests.post('http://localhost:8000/api/v1/auth/login', json=data)
token = response.json()['access_token']

# 获取策略列表
headers = {
    'Authorization': f'Bearer {token}'
}
response = requests.get('http://localhost:8000/api/v1/strategies', headers=headers)
strategies = response.json()
print('策略列表:', strategies)`}
          </pre>
        </div>
      </div>
    </div>
  );
}

export default APIDocs;