const API_BASE = '/api/v1';

async function request(path, options = {}) {
  const url = path.startsWith('http') ? path : `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    throw new Error(data?.message || `HTTP ${res.status}`);
  }
  return data;
}

export const api = {
  request,
  auth: {
    login: (credentials) => request('/auth/login', { method: 'POST', body: JSON.stringify(credentials) }),
    logout: () => request('/auth/logout', { method: 'POST' }),
    getCurrentUser: () => request('/auth/me'),
  },
  system: {
    getStatus: () => request('/system/status'),
    getHealth: () => request('/system/health'),
    getMetrics: () => request('/system/metrics'),
  },
  settings: {
    get: () => request('/settings'),
    update: (data) => request('/settings', { method: 'PUT', body: JSON.stringify(data) }),
  },
  models: {
    getList: () => request('/models'),
    train: (data) => request('/models/train', { method: 'POST', body: JSON.stringify(data) }),
    getPerformance: (id) => request(`/models/${id}/performance`),
    delete: (id) => request(`/models/${id}`, { method: 'DELETE' }),
  },
  aiModels: {
    getAll: () => request('/models/ai'),
    getList: () => request('/models/ai'),
    getDefault: () => request('/models/ai/default'),
    add: (data) => request('/models/ai', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/models/ai/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    delete: (id) => request(`/models/ai/${id}`, { method: 'DELETE' }),
    setDefault: (id) => request('/models/ai/default', { method: 'POST', body: JSON.stringify({ id }) }),
  },
  ai: {
    chat: (message) => request('/ai/chat', { method: 'POST', body: JSON.stringify({ message }) }),
    analyzeMarket: (marketData, modelId) => request('/ai/analyze', { method: 'POST', body: JSON.stringify({ marketData, modelId }) }),
    generateStrategy: (analysis, modelId) => request('/ai/strategy/generate', { method: 'POST', body: JSON.stringify({ analysis, modelId }) }),
    generateSignal: (marketData, modelId) => request('/ai/signal', { method: 'POST', body: JSON.stringify({ marketData, modelId }) }),
  },
  strategies: {
    getAll: () => request('/strategies'),
    create: (data) => request('/strategies', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/strategies/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    delete: (id) => request(`/strategies/${id}`, { method: 'DELETE' }),
    activate: (id) => request(`/strategies/activate/${id}`, { method: 'POST' }),
  },
  trading: {
    getPositions: () => request('/trading/positions'),
    getOrders: () => request('/trading/orders'),
    createOrder: (data) => request('/trading/orders', { method: 'POST', body: JSON.stringify(data) }),
    cancelOrder: (id) => request(`/trading/orders/${id}`, { method: 'DELETE' }),
    getHistory: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/trading/history${q ? `?${q}` : ''}`);
    },
  },
  market: {
    getSymbols: () => request('/market/symbols'),
    getTicker: (symbol) => request(`/market/ticker?symbol=${encodeURIComponent(symbol)}`),
    getKlines: (symbol, interval = '1m', limit = 60) =>
      request(`/market/klines?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&limit=${limit}`),
    getOrderBook: (symbol) => request(`/market/orderbook?symbol=${encodeURIComponent(symbol)}`),
  },
  externalData: {
    getIndicators: (symbol, indicators = []) =>
      request('/external/indicators', { method: 'POST', body: JSON.stringify({ symbol, indicators }) }),
    analyzeTrends: (symbol) => request(`/external/analyze-trends?symbol=${encodeURIComponent(symbol)}`),
    getSignals: (symbol) => request(`/external/signals?symbol=${encodeURIComponent(symbol)}`),
  },
  dataFusion: {
    analyzeMarket: (symbol) => request(`/data-fusion/analyze?symbol=${encodeURIComponent(symbol)}`),
    getAnalysisHistory: () => request('/data-fusion/history'),
  },
  performance: {
    getMetrics: () => request('/performance/metrics'),
  },
  risk: {
    getMetrics: () => request('/risk/metrics'),
  },
};

