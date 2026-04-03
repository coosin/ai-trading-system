import axios from 'axios';

// 创建API客户端实例
const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    // 从localStorage获取token
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    return response.data;
  },
  (error) => {
    if (error.response) {
      const { status, data } = error.response;
      
      // 401 Unauthorized - 清除token
      if (status === 401) {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user');
        // 触发页面重新渲染，显示登录页面
        window.location.reload();
      }
      
      console.error('API Error:', { status, message: data?.message || error.message });
      return Promise.reject(new Error(data?.message || error.message));
    } else if (error.request) {
      console.error('Network Error:', error.request);
      return Promise.reject(new Error('网络连接失败，请检查网络'));
    } else {
      console.error('Request Error:', error.message);
      return Promise.reject(error);
    }
  }
);

// API方法
export const api = {
  // 认证相关
  auth: {
    login: (credentials) => apiClient.post('/auth/login', credentials),
    logout: () => apiClient.post('/auth/logout'),
    refreshToken: () => apiClient.post('/auth/refresh'),
    getCurrentUser: () => apiClient.get('/auth/me'),
  },

  // 系统状态
  system: {
    getStatus: () => apiClient.get('/status'),
    getHealth: () => apiClient.get('/health'),
    getMetrics: () => apiClient.get('/metrics'),
  },

  // 策略管理
  strategies: {
    getAll: () => apiClient.get('/strategies'),
    getById: (id) => apiClient.get(`/strategies/${id}`),
    create: (data) => apiClient.post('/strategies', data),
    update: (id, data) => apiClient.put(`/strategies/${id}`, data),
    delete: (id) => apiClient.delete(`/strategies/${id}`),
    activate: (id) => apiClient.post(`/strategies/${id}/activate`),
    deactivate: (id) => apiClient.post(`/strategies/${id}/deactivate`),
    getPerformance: (id) => apiClient.get(`/strategies/${id}/performance`),
  },

  // 交易相关
  trading: {
    getPositions: () => apiClient.get('/trading/positions'),
    getOrders: () => apiClient.get('/trading/orders'),
    createOrder: (data) => apiClient.post('/trading/orders', data),
    cancelOrder: (id) => apiClient.delete(`/trading/orders/${id}`),
    getHistory: (params) => apiClient.get('/trading/history', { params }),
  },

  // 市场数据
  market: {
    getSymbols: () => apiClient.get('/market/symbols'),
    getTicker: (symbol) => {
      const formattedSymbol = symbol.replace('/', '-');
      return apiClient.get(`/market/ticker/${formattedSymbol}`);
    },
    getKlines: (symbol, interval, limit = 100) => {
      const formattedSymbol = symbol.replace('/', '-');
      return apiClient.get(`/market/klines/${formattedSymbol}`, { params: { interval, limit } });
    },
    getOrderBook: (symbol) => {
      const formattedSymbol = symbol.replace('/', '-');
      return apiClient.get(`/market/orderbook/${formattedSymbol}`);
    },
  },

  // 风险管理
  risk: {
    getOverview: () => apiClient.get('/risk/overview'),
    getVaR: () => apiClient.get('/risk/var'),
    getDrawdown: () => apiClient.get('/risk/drawdown'),
    getPositionLimits: () => apiClient.get('/risk/limits'),
  },

  // 回测
  backtest: {
    run: (data) => apiClient.post('/backtest/run', data),
    getResults: (id) => apiClient.get(`/backtest/results/${id}`),
    getHistory: () => apiClient.get('/backtest/history'),
  },

  // 监控
  monitoring: {
    getAlerts: () => apiClient.get('/monitoring/alerts'),
    getLogs: (params) => apiClient.get('/monitoring/logs', { params }),
    getPerformance: () => apiClient.get('/monitoring/performance'),
  },

  // 自然语言接口
  nlp: {
    query: (question) => apiClient.post('/nlp/query', { question }),
  },

  // 设置管理
  settings: {
    get: () => apiClient.get('/settings'),
    update: (settings) => apiClient.put('/settings', settings),
  },

  // 模型管理
  models: {
    getList: () => apiClient.get('/models'),
    train: (modelData) => apiClient.post('/models/train', modelData),
    update: (id, modelData) => apiClient.put(`/models/${id}`, modelData),
    delete: (id) => apiClient.delete(`/models/${id}`),
    getPerformance: (id) => apiClient.get(`/models/${id}/performance`),
  },

  // AI模型管理
  aiModels: {
    getList: () => apiClient.get('/ai-models'),
    add: (modelData) => apiClient.post('/ai-models', modelData),
    update: (id, modelData) => apiClient.put(`/ai-models/${id}`, modelData),
    delete: (id) => apiClient.delete(`/ai-models/${id}`),
    getDefault: () => apiClient.get('/ai-models/default'),
    setDefault: (defaultData) => apiClient.put('/ai-models/default', defaultData),
  },

  // AI对话
  ai: {
    chat: (message, modelId = null) => apiClient.post('/ai/chat', { message, model_id: modelId }),
    query: (query, context = {}) => apiClient.post('/ai/query', { query, context }),
    analyzeMarket: (marketData, modelId = null) => apiClient.post('/ai/analyze-market', { market_data: marketData, model_id: modelId }),
    generateStrategy: (analysis, modelId = null) => apiClient.post('/ai/generate-strategy', { analysis, model_id: modelId }),
    generateSignal: (marketData, modelId = null) => apiClient.post('/ai/generate-signal', { market_data: marketData, model_id: modelId }),
  },

  // 外部数据获取
  externalData: {
    getSources: () => apiClient.get('/external-data/sources'),
    fetchData: (source, params) => apiClient.post(`/external-data/fetch/${source}`, params),
    getIndicators: (symbol, indicators) => apiClient.post('/external-data/indicators', { symbol, indicators }),
    analyzeTrends: (symbol) => apiClient.get(`/external-data/analyze-trends/${symbol}`),
    getSignals: (symbol) => apiClient.get(`/external-data/signals/${symbol}`),
  },

  // 多源数据融合分析
  dataFusion: {
    analyzeMarket: (symbol) => apiClient.get(`/data-fusion/analyze/${symbol.replace('/', '-')}`),
    getSources: () => apiClient.get('/data-fusion/sources'),
    getAnalysisHistory: () => apiClient.get('/data-fusion/history'),
  },

  // 链上数据
  onchain: {
    getTransactions: (address, params) => apiClient.post('/onchain/transactions', { address, ...params }),
    getBalance: (address) => apiClient.get(`/onchain/balance/${address}`),
  },

  // 社交媒体数据
  social: {
    getTweets: (query, maxResults = 100) => apiClient.get('/social/tweets', { params: { query, max_results: maxResults } }),
    getNews: (query, pageSize = 100) => apiClient.get('/social/news', { params: { query, page_size: pageSize } }),
  },

  // 模拟合约交易
  contractTrading: {
    getAccount: () => apiClient.get('/contract-trading/account'),
    getPositions: () => apiClient.get('/contract-trading/positions'),
    placeOrder: (orderData) => apiClient.post('/contract-trading/order', orderData),
    closePosition: (symbol, size = null) => apiClient.post('/contract-trading/close', { symbol, size }),
    getStats: () => apiClient.get('/contract-trading/stats'),
  },

  // 交易所管理
  exchange: {
    getList: () => apiClient.get('/exchanges'),
    getBalance: (exchangeId) => apiClient.get(`/exchanges/${exchangeId}/balance`),
    getTicker: (exchangeId, symbol) => apiClient.get(`/exchanges/${exchangeId}/ticker/${symbol}`),
  },

  // 模块控制
  request: (endpoint, options = {}) => {
    const url = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    if (options.method === 'POST' || options.method === 'PUT') {
      return apiClient.post(url, options.body ? JSON.parse(options.body) : {});
    }
    return apiClient.get(url);
  },
};

export default apiClient;
