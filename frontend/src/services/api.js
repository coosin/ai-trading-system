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
    getAcceptance: () => request('/system/acceptance'),
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
    activate: (id) => request(`/strategies/${id}/activate`, { method: 'POST' }),
  },
  trading: {
    getPositions: () => request('/trading/positions'),
    getOrders: () => request('/trading/orders'),
    createOrder: (data) => request('/trading/orders', { method: 'POST', body: JSON.stringify(data) }),
    cancelOrder: (id) => request(`/trading/orders/${id}`, { method: 'DELETE' }),
    getHistory: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/trading/history${q ? `?${q}` : ''}`).catch(() =>
        request(`/trades${q ? `?${q}` : ''}`)
      );
    },
    getExecutionSpine: () => request('/trade/execution_spine'),
    getAnalyticsSummary: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/trades/analytics/summary${q ? `?${q}` : ''}`);
    },
    simulateOrder: (data) =>
      request('/modules/execution/simulate-order', { method: 'POST', body: JSON.stringify(data || {}) }),
    getEvents: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/trade/events${q ? `?${q}` : ''}`);
    },
  },
  market: {
    getSymbols: () => request('/market/symbols'),
    getTicker: (symbol) => request(`/market/ticker?symbol=${encodeURIComponent(symbol)}`),
    getKlines: (symbol, interval = '1m', limit = 60) =>
      request(`/market/klines?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&limit=${limit}`),
    getOrderBook: (symbol) => request(`/market/orderbook?symbol=${encodeURIComponent(symbol)}`),
    getSymbolView: (symbol, params = {}) => {
      const query = new URLSearchParams({ ...params }).toString();
      return request(`/market/symbol/${encodeURIComponent(symbol)}${query ? `?${query}` : ''}`);
    },
    getState: () => request('/market/state'),
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
    getSources: () => request('/data-fusion/sources'),
  },
  performance: {
    getMetrics: () => request('/performance/metrics'),
  },
  risk: {
    getMetrics: () => request('/risk/metrics'),
  },
  modules: {
    getStrategyOptimizationStatus: () => request('/modules/strategy/optimization-status'),
    getStrategyOptimizationConfig: () => request('/modules/strategy/optimization-config'),
    updateStrategyOptimizationConfig: (data) =>
      request('/modules/strategy/optimization-config', { method: 'POST', body: JSON.stringify(data) }),
    triggerStrategyOptimizeNow: () =>
      request('/modules/strategy/optimize-now', { method: 'POST' }),
    submitStrategyTradeFeedback: (data) =>
      request('/modules/strategy/trade-feedback', { method: 'POST', body: JSON.stringify(data || {}) }),
    runStrategyResearch: (body) =>
      request('/modules/strategy/research-run', { method: 'POST', body: JSON.stringify(body || {}) }),
    getStrategyResearchJobs: (limit = 20) =>
      request(`/modules/strategy/research-jobs?limit=${Number(limit) || 20}`),
    getStrategyResearchJob: (jobId) =>
      request(`/modules/strategy/research-jobs/${encodeURIComponent(jobId)}`),
    getStrategyResearchProfile: (strategyId) =>
      request(`/modules/strategy/research-profile/${encodeURIComponent(strategyId)}`),
    saveStrategyExperimentCard: (strategyId, data = {}) =>
      request(`/modules/strategy/research-profile/${encodeURIComponent(strategyId)}/experiment-card`, { method: 'POST', body: JSON.stringify(data || {}) }),
    saveStrategyPeerReview: (strategyId, data = {}) =>
      request(`/modules/strategy/research-profile/${encodeURIComponent(strategyId)}/peer-review`, { method: 'POST', body: JSON.stringify(data || {}) }),
    saveStrategyFailureCase: (strategyId, data = {}) =>
      request(`/modules/strategy/research-profile/${encodeURIComponent(strategyId)}/failure-case`, { method: 'POST', body: JSON.stringify(data || {}) }),
    saveStrategyParameterSensitivity: (strategyId, data = {}) =>
      request(`/modules/strategy/research-profile/${encodeURIComponent(strategyId)}/parameter-sensitivity`, { method: 'POST', body: JSON.stringify(data || {}) }),
    getExecutionProductionAudit: () =>
      request('/modules/execution/production-audit'),
    getMemoryDailySummary: (limit = 6) =>
      request(`/modules/memory/daily-summary?limit=${Number(limit) || 6}`),
    runMemoryDailySummary: () =>
      request('/modules/memory/daily-summary/run', { method: 'POST' }),
    getCommanderSnapshot: (symbol = 'BTC/USDT', mode = 'fast') =>
      request(`/modules/commander/snapshot?symbol=${encodeURIComponent(symbol)}&mode=${encodeURIComponent(mode)}`),
    getCommanderSnapshotFast: (symbol = 'BTC/USDT') =>
      request(`/modules/commander/snapshot?symbol=${encodeURIComponent(symbol)}&mode=fast`),
    getCommanderSnapshotFull: (symbol = 'BTC/USDT') =>
      request(`/modules/commander/snapshot?symbol=${encodeURIComponent(symbol)}&mode=full`),
    getCommanderTradingWorkflow: (symbol = 'BTC/USDT', params = {}) => {
      const query = new URLSearchParams({ symbol, ...params }).toString();
      return request(`/modules/commander/trading-workflow?${query}`);
    },
    getCommanderSystemMastery: (symbol = 'BTC/USDT', params = {}) => {
      const query = new URLSearchParams({ symbol, ...params }).toString();
      return request(`/modules/commander/system-mastery?${query}`);
    },
    getCommanderPlatformOversight: (symbol = 'BTC/USDT', params = {}) => {
      const query = new URLSearchParams({ symbol, ...params }).toString();
      return request(`/modules/commander/platform-oversight?${query}`);
    },
    getCommanderClosedLoopSummary: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/modules/commander/closed-loop-summary${query ? `?${query}` : ''}`);
    },
    getCommanderAgentEffectiveness: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/modules/commander/agent-effectiveness${query ? `?${query}` : ''}`);
    },
    getMemoryStats: () => request('/modules/memory/stats'),
    getProfitOpsOverview: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/modules/profit/ops-overview${query ? `?${query}` : ''}`);
    },
    runCommanderChores: (body = {}) =>
      request('/modules/commander/chores', { method: 'POST', body: JSON.stringify(body || {}) }),
    dispatchCommanderMessage: (message, source = 'control_hub') =>
      request('/modules/commander/dispatch', { method: 'POST', body: JSON.stringify({ message, source }) }),
    getAiFrequencyProfile: () =>
      request('/modules/ai/frequency-profile'),
    setAiFrequencyProfile: (profile) =>
      request('/modules/ai/frequency-profile', { method: 'POST', body: JSON.stringify({ profile }) }),
    updateAiGuards: (data) =>
      request('/modules/ai/guards', { method: 'POST', body: JSON.stringify(data || {}) }),
    getRiskStatus: () =>
      request('/modules/risk/status'),
    getRiskConfig: () =>
      request('/modules/risk/config'),
    updateRiskConfig: (data) =>
      request('/modules/risk/config', { method: 'POST', body: JSON.stringify(data || {}) }),
    getAccountDiagnostics: () => request('/modules/commander/account-diagnostics'),
    runAccountSync: (reason = 'ui') =>
      request('/modules/commander/account-sync/run', { method: 'POST', body: JSON.stringify({ reason }) }),
    getCommanderCapabilities: () => request('/modules/commander/capabilities'),
    getCommanderResearchCockpit: (symbol = 'BTC/USDT') =>
      request(`/modules/commander/research-cockpit?symbol=${encodeURIComponent(symbol)}`),
    getCommanderAudit: (enrich = false) => request(`/modules/commander/audit?enrich=${enrich ? 'true' : 'false'}`),
    getCommanderHostingMode: () => request('/modules/commander/hosting-mode'),
    setCommanderHostingMode: (mode) =>
      request('/modules/commander/hosting-mode', { method: 'POST', body: JSON.stringify({ mode }) }),
    getCommanderHostingGuard: () => request('/modules/commander/hosting-guard'),
    updateCommanderHostingGuard: (data) =>
      request('/modules/commander/hosting-guard', { method: 'POST', body: JSON.stringify(data || {}) }),
    getCommanderAutomationProfile: () => request('/modules/commander/automation-profile'),
    setCommanderAutomationProfile: (profile) =>
      request('/modules/commander/automation-profile', { method: 'POST', body: JSON.stringify({ profile }) }),
    getCommanderRiskRedlines: () => request('/modules/commander/risk-redlines'),
    updateCommanderRiskRedlines: (data) =>
      request('/modules/commander/risk-redlines', { method: 'POST', body: JSON.stringify(data || {}) }),
    getCommanderArchitectureLayers: () => request('/modules/commander/architecture/layers'),
    getCommanderUpgradeBenchmark: () => request('/modules/commander/upgrade/benchmark'),
    getCommanderToolContract: () => request('/modules/commander/tool-contract'),
    getCommanderGovernanceAudit: (limit = 50) =>
      request(`/modules/commander/governance-audit?limit=${Number(limit) || 50}`),
    runCommanderUpgradePipeline: (data = {}) =>
      request('/modules/commander/upgrade/run', { method: 'POST', body: JSON.stringify(data || {}) }),
    getAiGuards: () => request('/modules/ai/guards'),
    getStopLossStats: () => request('/modules/stop-loss/stats'),
    getSurfaceRegistry: () => request('/modules/surface/registry'),
    getDataIntegrationHealth: () => request('/modules/data/integration/health'),
    getPluginsStatus: () => request('/modules/plugins/status'),
    getMarketStructureMultiSourceSnapshot: (symbol = 'BTC/USDT') =>
      request(`/modules/market-structure/multi-source-snapshot?symbol=${encodeURIComponent(symbol)}`),
    getLearningWeeklyReview: (body = {}) =>
      request('/modules/commander/learning/weekly-review', { method: 'POST', body: JSON.stringify(body || {}) }),
    getLearningRetrievalDeck: (body = {}) =>
      request('/modules/commander/learning/retrieval-deck', { method: 'POST', body: JSON.stringify(body || {}) }),
  },
  monitoring: {
    /** 若后端未实现则返回 404，总控会降级为空列表 */
    getLogs: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/monitoring/logs${q ? `?${q}` : ''}`);
    },
    getSummary: () => request('/monitoring/summary'),
    getAlerts: () => request('/monitoring/alerts'),
    getAlertsHistory: () => request('/monitoring/alerts/history'),
    getMarketData: () => request('/monitoring/market-data'),
    getRisk: () => request('/monitoring/risk'),
  },
  controlCenter: {
    getState: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/control-center/state${q ? `?${q}` : ''}`);
    },
  },
  dataHub: {
    getStatus: () => request('/data-hub/status'),
    getUnifiedSnapshot: (symbol = 'BTC/USDT') =>
      request(`/data-hub/unified-snapshot?symbol=${encodeURIComponent(symbol)}`),
    getQualityAdvice: (symbol = 'BTC/USDT') =>
      request(`/data-hub/quality-advice?symbol=${encodeURIComponent(symbol)}`),
    getAiAnalysis: (symbol = 'BTC/USDT') =>
      request(`/data-hub/ai-analysis?symbol=${encodeURIComponent(symbol)}`),
  },
  exchanges: {
    getAll: () => request('/exchanges'),
  },
};
