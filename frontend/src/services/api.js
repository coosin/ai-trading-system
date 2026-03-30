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
      
      // 401 Unauthorized - 清除token并跳转到登录页
      if (status === 401) {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
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
    getTicker: (symbol) => apiClient.get(`/market/ticker/${symbol}`),
    getKlines: (symbol, interval, limit = 100) => 
      apiClient.get(`/market/klines/${symbol}`, { params: { interval, limit } }),
    getOrderBook: (symbol) => apiClient.get(`/market/orderbook/${symbol}`),
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
};

export default apiClient;
