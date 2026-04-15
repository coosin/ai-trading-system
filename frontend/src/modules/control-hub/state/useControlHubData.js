import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../../services/api';

const FAST_INTERVAL = 3000;
const MEDIUM_INTERVAL = 10000;
const SLOW_INTERVAL = 20000;

const EMPTY_LOADERS = { fast: false, medium: false, slow: false, full: false };
const EMPTY_ERRORS = { fast: null, medium: null, slow: null, full: null };
const EMPTY_UPDATED = { fast: null, medium: null, slow: null, full: null };

function unwrap(payload) {
  if (!payload || typeof payload !== 'object') return payload;
  if (Object.prototype.hasOwnProperty.call(payload, 'data')) return payload.data;
  return payload;
}

export function useControlHubData() {
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [watchSymbols, setWatchSymbols] = useState(['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT']);
  const [tab, setTab] = useState('overview');
  const [notice, setNotice] = useState(null);
  const [loading, setLoading] = useState({ ...EMPTY_LOADERS });
  const [errors, setErrors] = useState({ ...EMPTY_ERRORS });
  const [updatedAt, setUpdatedAt] = useState({ ...EMPTY_UPDATED });
  const [commandInput, setCommandInput] = useState('执行系统巡检');
  const [commandReply, setCommandReply] = useState('');
  const [simulatePayload, setSimulatePayload] = useState({
    symbol: 'BTC-USDT-SWAP',
    side: 'buy',
    amount: 0.01,
    order_type: 'market',
  });
  const [autoHostingGuardEnabled, setAutoHostingGuardEnabled] = useState(() => {
    try {
      const raw = window.localStorage.getItem('auto_hosting_guard_enabled');
      return raw == null ? true : raw === '1';
    } catch {
      return true;
    }
  });
  const [autoHostingLastAction, setAutoHostingLastAction] = useState(null);

  const [state, setState] = useState({
    health: null,
    systemStatus: null,
    acceptance: null,
    exchanges: [],
    monitoringSummary: null,
    monitoringAlerts: [],
    monitoringAlertHistory: [],
    marketMonitor: null,
    riskMonitor: null,
    marketSymbols: [],
    ticker: null,
    watchTickers: [],
    orderbook: null,
    klines: null,
    dataHubStatus: null,
    dataHubSnapshot: null,
    qualityAdvice: null,
    aiAnalysis: null,
    fusion: null,
    fusionSources: null,
    fusionHistory: null,
    riskStatus: null,
    riskMetrics: null,
    accountDiagnostics: null,
    executionSpine: null,
    tradeHistory: [],
    strategies: [],
    strategyOpt: null,
    researchJobs: [],
    productionAudit: null,
    memorySummary: [],
    commanderSnapshot: null,
    commanderAudit: null,
    commanderCapabilities: null,
    hostingMode: null,
    hostingGuard: null,
    automationProfile: null,
    riskRedlines: null,
    toolContract: null,
    governanceAudit: [],
    aiGuards: null,
    stopLossStats: null,
    marketState: null,
    marketSymbolView: null,
    tradeEvents: [],
    apiSmoke: [],
    surfaceRegistry: null,
    dataIntegrationHealth: null,
    pluginsStatus: null,
    opportunities: [],
  });

  const showNotice = useCallback((message, type = 'success') => {
    setNotice({ message, type });
    window.setTimeout(() => setNotice(null), 3500);
  }, []);

  const updateSlice = useCallback((patch) => {
    setState((prev) => ({ ...prev, ...patch }));
  }, []);

  const markLoading = useCallback((key, value) => {
    setLoading((prev) => ({ ...prev, [key]: value }));
  }, []);
  const markError = useCallback((key, value) => {
    setErrors((prev) => ({ ...prev, [key]: value }));
  }, []);
  const markUpdated = useCallback((key) => {
    setUpdatedAt((prev) => ({ ...prev, [key]: new Date().toISOString() }));
  }, []);

  const loadFast = useCallback(async () => {
    markLoading('fast', true);
    markError('fast', null);
    try {
      const [health, systemStatus, exchanges, monitoringSummary, marketSymbols, ticker, orderbook, klines, dataHubStatus, marketState, marketSymbolView] =
        await Promise.all([
          api.system.getHealth().catch(() => null),
          api.system.getStatus().catch(() => null),
          api.exchanges.getAll().catch(() => null),
          api.monitoring.getSummary().catch(() => null),
          api.market.getSymbols().catch(() => null),
          api.market.getTicker(symbol).catch(() => null),
          api.market.getOrderBook(symbol).catch(() => null),
          api.market.getKlines(symbol, '1m', 30).catch(() => null),
          api.dataHub.getStatus().catch(() => null),
          api.market.getState().catch(() => null),
          api.market.getSymbolView(symbol).catch(() => null),
        ]);

      const watchList = Array.from(new Set([symbol, ...(watchSymbols || [])])).slice(0, 10);
      const watchTickersSettled = await Promise.allSettled(
        watchList.map(async (sym) => {
          const res = await api.market.getTicker(sym);
          const t = unwrap(res);
          return { symbol: sym, ticker: t };
        }),
      );
      const watchTickers = watchTickersSettled
        .filter((x) => x.status === 'fulfilled')
        .map((x) => x.value);

      updateSlice({
        health: unwrap(health),
        systemStatus: unwrap(systemStatus),
        exchanges: Array.isArray(exchanges?.exchanges) ? exchanges.exchanges : Array.isArray(unwrap(exchanges)) ? unwrap(exchanges) : [],
        monitoringSummary: unwrap(monitoringSummary),
        marketSymbols: Array.isArray(marketSymbols?.data)
          ? marketSymbols.data
          : Array.isArray(marketSymbols)
            ? marketSymbols
            : [],
        ticker: unwrap(ticker),
        watchTickers,
        orderbook: unwrap(orderbook),
        klines: unwrap(klines),
        dataHubStatus: unwrap(dataHubStatus),
        marketState: unwrap(marketState),
        marketSymbolView: unwrap(marketSymbolView)?.view || unwrap(marketSymbolView),
      });
      markUpdated('fast');
    } catch (error) {
      markError('fast', error.message || String(error));
    } finally {
      markLoading('fast', false);
    }
  }, [markError, markLoading, markUpdated, symbol, updateSlice, watchSymbols]);

  const loadMedium = useCallback(async () => {
    markLoading('medium', true);
    markError('medium', null);
    try {
      const [snapshot, quality, aiAnalysis, fusion, fusionSources, fusionHistory, riskStatus, riskMetrics, alerts, alertsHistory, marketMonitor, riskMonitor] =
        await Promise.all([
          api.dataHub.getUnifiedSnapshot(symbol).catch(() => null),
          api.dataHub.getQualityAdvice(symbol).catch(() => null),
          api.dataHub.getAiAnalysis(symbol).catch(() => null),
          api.dataFusion.analyzeMarket(symbol).catch(() => null),
          api.dataFusion.getSources().catch(() => null),
          api.dataFusion.getAnalysisHistory().catch(() => null),
          api.modules.getRiskStatus().catch(() => null),
          api.risk.getMetrics().catch(() => null),
          api.monitoring.getAlerts().catch(() => null),
          api.monitoring.getAlertsHistory().catch(() => null),
          api.monitoring.getMarketData().catch(() => null),
          api.monitoring.getRisk().catch(() => null),
        ]);
      updateSlice({
        dataHubSnapshot: unwrap(snapshot),
        qualityAdvice: unwrap(quality),
        aiAnalysis: unwrap(aiAnalysis),
        fusion: unwrap(fusion),
        fusionSources: unwrap(fusionSources),
        fusionHistory: unwrap(fusionHistory),
        riskStatus: unwrap(riskStatus),
        riskMetrics: unwrap(riskMetrics),
        monitoringAlerts: Array.isArray(alerts) ? alerts : Array.isArray(unwrap(alerts)?.alerts) ? unwrap(alerts).alerts : [],
        monitoringAlertHistory: Array.isArray(alertsHistory?.alerts)
          ? alertsHistory.alerts
          : Array.isArray(alertsHistory)
            ? alertsHistory
            : [],
        marketMonitor: unwrap(marketMonitor),
        riskMonitor: unwrap(riskMonitor),
      });
      markUpdated('medium');
    } catch (error) {
      markError('medium', error.message || String(error));
    } finally {
      markLoading('medium', false);
    }
  }, [markError, markLoading, markUpdated, symbol, updateSlice]);

  const loadSlow = useCallback(async () => {
    markLoading('slow', true);
    markError('slow', null);
    try {
      const [acceptance, accountDiagnostics, executionSpine, tradeHistory, strategies, strategyOpt, researchJobs, productionAudit, memorySummary, commanderSnapshot, commanderAudit, commanderCapabilities, hostingMode, hostingGuard, automationProfile, riskRedlines, toolContract, governanceAudit, aiGuards, stopLossStats, tradeEvents, surfaceRegistry, dataIntegrationHealth, pluginsStatus, opportunities] =
        await Promise.all([
          api.system.getAcceptance().catch(() => null),
          api.modules.getAccountDiagnostics().catch(() => null),
          api.trading.getExecutionSpine().catch(() => null),
          api.trading.getHistory({ limit: 20 }).catch(() => []),
          api.strategies.getAll().catch(() => []),
          api.modules.getStrategyOptimizationStatus().catch(() => null),
          api.modules.getStrategyResearchJobs(20).catch(() => null),
          api.modules.getExecutionProductionAudit().catch(() => null),
          api.modules.getMemoryDailySummary(8).catch(() => null),
          api.modules.getCommanderSnapshot(symbol, 'fast').catch(() => null),
          api.modules.getCommanderAudit(true).catch(() => null),
          api.modules.getCommanderCapabilities().catch(() => null),
          api.modules.getCommanderHostingMode().catch(() => null),
          api.modules.getCommanderHostingGuard().catch(() => null),
          api.modules.getCommanderAutomationProfile().catch(() => null),
          api.modules.getCommanderRiskRedlines().catch(() => null),
          api.modules.getCommanderToolContract().catch(() => null),
          api.modules.getCommanderGovernanceAudit(50).catch(() => null),
          api.modules.getAiGuards().catch(() => null),
          api.modules.getStopLossStats().catch(() => null),
          api.trading.getEvents({ limit: 50 }).catch(() => null),
          api.modules.getSurfaceRegistry().catch(() => null),
          api.modules.getDataIntegrationHealth().catch(() => null),
          api.modules.getPluginsStatus().catch(() => null),
          api.request('/monitoring/proactive-ai/opportunities').catch(() => null),
        ]);
      updateSlice({
        acceptance: unwrap(acceptance),
        accountDiagnostics: unwrap(accountDiagnostics),
        executionSpine: unwrap(executionSpine?.snapshot || executionSpine),
        tradeHistory: Array.isArray(tradeHistory?.data) ? tradeHistory.data : Array.isArray(tradeHistory) ? tradeHistory : [],
        strategies: Array.isArray(strategies) ? strategies : [],
        strategyOpt: unwrap(strategyOpt),
        researchJobs: Array.isArray(researchJobs?.jobs) ? researchJobs.jobs : [],
        productionAudit: unwrap(productionAudit),
        memorySummary: Array.isArray(memorySummary?.data) ? memorySummary.data : [],
        commanderSnapshot: unwrap(commanderSnapshot),
        commanderAudit: unwrap(commanderAudit),
        commanderCapabilities: unwrap(commanderCapabilities),
        hostingMode: unwrap(hostingMode),
        hostingGuard: unwrap(hostingGuard),
        automationProfile: unwrap(automationProfile),
        riskRedlines: unwrap(riskRedlines),
        toolContract: unwrap(toolContract),
        governanceAudit: Array.isArray(unwrap(governanceAudit)?.items) ? unwrap(governanceAudit).items : [],
        aiGuards: unwrap(aiGuards),
        stopLossStats: unwrap(stopLossStats)?.stats || unwrap(stopLossStats),
        tradeEvents: Array.isArray(unwrap(tradeEvents)?.events) ? unwrap(tradeEvents).events : [],
        surfaceRegistry: unwrap(surfaceRegistry),
        dataIntegrationHealth: unwrap(dataIntegrationHealth),
        pluginsStatus: unwrap(pluginsStatus),
        opportunities: Array.isArray(opportunities?.opportunities)
          ? opportunities.opportunities
          : Array.isArray(opportunities?.data)
            ? opportunities.data
            : [],
      });
      markUpdated('slow');
    } catch (error) {
      markError('slow', error.message || String(error));
    } finally {
      markLoading('slow', false);
    }
  }, [markError, markLoading, markUpdated, symbol, updateSlice]);

  const refreshAll = useCallback(async () => {
    markLoading('full', true);
    markError('full', null);
    try {
      await Promise.all([loadFast(), loadMedium(), loadSlow()]);
      markUpdated('full');
    } catch (error) {
      markError('full', error.message || String(error));
    } finally {
      markLoading('full', false);
    }
  }, [loadFast, loadMedium, loadSlow, markError, markLoading, markUpdated]);

  const runAccountSync = useCallback(async () => {
    try {
      const res = await api.modules.runAccountSync('ui_manual_sync');
      showNotice('账户同步已执行');
      await loadSlow();
      return res;
    } catch (error) {
      showNotice(`账户同步失败: ${error.message || error}`, 'error');
      return null;
    }
  }, [loadSlow, showNotice]);

  const runSimulateOrder = useCallback(async () => {
    try {
      const payload = {
        ...simulatePayload,
        amount: Number(simulatePayload.amount),
      };
      const res = await api.trading.simulateOrder(payload);
      showNotice('模拟下单已执行');
      await loadSlow();
      return res;
    } catch (error) {
      showNotice(`模拟下单失败: ${error.message || error}`, 'error');
      return null;
    }
  }, [loadSlow, showNotice, simulatePayload]);

  const sendCommanderMessage = useCallback(async () => {
    try {
      const message = String(commandInput || '').trim();
      if (!message) return;
      const res = await api.modules.dispatchCommanderMessage(message, 'unified_console');
      setCommandReply(res?.data?.response || res?.data?.message || JSON.stringify(res?.data || res || {}, null, 2));
      showNotice('司令部指令已发送');
      await loadSlow();
    } catch (error) {
      showNotice(`司令部指令失败: ${error.message || error}`, 'error');
    }
  }, [commandInput, loadSlow, showNotice]);

  const confirmSuggestedOpen = useCallback(async (suggestion) => {
    try {
      const symbol = String(suggestion?.symbol || '').trim();
      const side = String(suggestion?.side || 'long').trim().toLowerCase();
      const size = Number(suggestion?.size || suggestion?.quantity || 0.01);
      if (!symbol) {
        showNotice('确认开仓失败: 缺少交易对', 'error');
        return null;
      }
      const sideText = side === 'sell' || side === 'short' ? 'short' : 'long';
      const qty = Number.isFinite(size) && size > 0 ? size : 0.01;
      const message = `强制开仓 ${symbol} ${sideText} 数量 ${qty}`;
      const res = await api.modules.dispatchCommanderMessage(message, 'semi_auto_confirm');
      showNotice('已确认开仓，指令已发送到司令部');
      await loadSlow();
      return res;
    } catch (error) {
      showNotice(`确认开仓失败: ${error.message || error}`, 'error');
      return null;
    }
  }, [loadSlow, showNotice]);

  const switchHostingMode = useCallback(async (mode) => {
    try {
      const res = await api.modules.setCommanderHostingMode(mode);
      const msg = res?.message || '托管模式切换成功';
      showNotice(msg);
      await loadSlow();
      return res;
    } catch (error) {
      showNotice(`托管模式切换失败: ${error.message || error}`, 'error');
      return null;
    }
  }, [loadSlow, showNotice]);

  const setAutomationProfile = useCallback(async (profile, runValidation = true) => {
    try {
      const res = await api.modules.setCommanderAutomationProfile(profile);
      showNotice(`自动化级别已切换为 ${res?.data?.profile || profile}`);
      if (runValidation) {
        try {
          const check = await api.modules.runCommanderUpgradePipeline({
            symbol,
            trigger_optimize: false,
            force_account_sync: true,
            auto_fallback_to_semi: true,
          });
          if (!check?.success) {
            showNotice('切档后最小回归未通过，已保守处理', 'error');
          }
        } catch {
          showNotice('切档后回归检查失败，请关注告警', 'error');
        }
      }
      await loadSlow();
      return res;
    } catch (error) {
      showNotice(`自动化级别切换失败: ${error.message || error}`, 'error');
      return null;
    }
  }, [loadSlow, showNotice, symbol]);

  const updateRiskRedlines = useCallback(async (patch) => {
    try {
      const res = await api.modules.updateCommanderRiskRedlines(patch || {});
      showNotice('风控红线已更新');
      await loadSlow();
      return res;
    } catch (error) {
      showNotice(`风控红线更新失败: ${error.message || error}`, 'error');
      return null;
    }
  }, [loadSlow, showNotice]);

  const runUpgradePipeline = useCallback(async (payload = {}) => {
    try {
      const body = {
        symbol,
        trigger_optimize: false,
        force_account_sync: true,
        auto_fallback_to_semi: true,
        ...(payload || {}),
      };
      const res = await api.modules.runCommanderUpgradePipeline(body);
      showNotice(res?.success ? '一键升级回归通过' : '一键升级回归未通过', res?.success ? 'success' : 'error');
      await loadSlow();
      return res;
    } catch (error) {
      showNotice(`一键升级回归失败: ${error.message || error}`, 'error');
      return null;
    }
  }, [loadSlow, showNotice, symbol]);

  const toggleAutoHostingGuard = useCallback((enabled) => {
    setAutoHostingGuardEnabled(Boolean(enabled));
  }, []);

  const runApiSmokeTest = useCallback(async () => {
    const checks = [
      { module: 'system', name: '/system/health', call: () => api.system.getHealth() },
      { module: 'market', name: '/market/ticker', call: () => api.market.getTicker(symbol) },
      { module: 'market', name: '/market/orderbook', call: () => api.market.getOrderBook(symbol) },
      { module: 'trade', name: '/trade/execution_spine', call: () => api.trading.getExecutionSpine() },
      { module: 'trade', name: '/trade/events', call: () => api.trading.getEvents({ limit: 10 }) },
      { module: 'risk', name: '/modules/risk/status', call: () => api.modules.getRiskStatus() },
      { module: 'risk', name: '/modules/stop-loss/stats', call: () => api.modules.getStopLossStats() },
      { module: 'commander', name: '/modules/commander/snapshot', call: () => api.modules.getCommanderSnapshot(symbol, 'fast') },
      { module: 'commander', name: '/modules/commander/audit', call: () => api.modules.getCommanderAudit(true) },
      { module: 'data', name: '/data-hub/unified-snapshot', call: () => api.dataHub.getUnifiedSnapshot(symbol) },
    ];
    const startedAt = Date.now();
    markLoading('full', true);
    try {
      const rows = await Promise.all(
        checks.map(async (item) => {
          const t0 = Date.now();
          try {
            const res = await item.call();
            return {
              id: item.name,
              module: item.module,
              endpoint: item.name,
              status: 'PASS',
              latency_ms: Date.now() - t0,
              hint: res && typeof res === 'object' ? Object.keys(res).slice(0, 4).join(', ') : 'ok',
            };
          } catch (error) {
            return {
              id: item.name,
              module: item.module,
              endpoint: item.name,
              status: 'FAIL',
              latency_ms: Date.now() - t0,
              hint: error?.message || String(error),
            };
          }
        }),
      );
      updateSlice({ apiSmoke: rows });
      showNotice(`API 联调完成（${rows.filter((r) => r.status === 'PASS').length}/${rows.length} 通过）`);
      markUpdated('full');
    } finally {
      markLoading('full', false);
      if (Date.now() - startedAt > 25000) {
        showNotice('部分接口响应较慢，建议检查网络与交易所链路', 'error');
      }
    }
  }, [markLoading, markUpdated, showNotice, symbol, updateSlice]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    const fastTimer = window.setInterval(loadFast, FAST_INTERVAL);
    const mediumTimer = window.setInterval(loadMedium, MEDIUM_INTERVAL);
    const slowTimer = window.setInterval(loadSlow, SLOW_INTERVAL);
    return () => {
      window.clearInterval(fastTimer);
      window.clearInterval(mediumTimer);
      window.clearInterval(slowTimer);
    };
  }, [loadFast, loadMedium, loadSlow]);

  useEffect(() => {
    refreshAll();
  }, [symbol, refreshAll]);

  useEffect(() => {
    try {
      window.localStorage.setItem('auto_hosting_guard_enabled', autoHostingGuardEnabled ? '1' : '0');
    } catch {
      // noop
    }
  }, [autoHostingGuardEnabled]);

  const autoGuardSnapshot = useMemo(() => {
    const hostingRaw = state.hostingMode?.data?.mode || state.commanderSnapshot?.system?.hosting_mode || 'full_auto';
    const hostingMode = String(hostingRaw || 'full_auto').toLowerCase();
    const alerts = Number(state.monitoringSummary?.active_alerts || 0);
    const degraded = Boolean(state.accountDiagnostics?.degraded);
    const riskText = String(state.riskStatus?.status || state.riskMonitor?.risk_level || '').toLowerCase();
    const hasRiskPressure = ['critical', 'high', 'warning', 'danger', '严重', '高'].some((x) => riskText.includes(x));
    const reasons = [];
    if (degraded) reasons.push('账户同步降级');
    if (alerts > 0) reasons.push(`活跃告警=${alerts}`);
    if (hasRiskPressure) reasons.push(`风险状态=${state.riskStatus?.status || state.riskMonitor?.risk_level || '-'}`);
    return {
      enabled: autoHostingGuardEnabled,
      hostingMode,
      shouldDowngrade: reasons.length > 0,
      reasons,
      lastAction: autoHostingLastAction,
    };
  }, [autoHostingGuardEnabled, autoHostingLastAction, state]);

  useEffect(() => {
    if (!autoGuardSnapshot.enabled) return;
    if (autoGuardSnapshot.hostingMode !== 'full_auto') return;
    if (!autoGuardSnapshot.shouldDowngrade) return;
    const now = Date.now();
    if (autoHostingLastAction?.at && now - Number(autoHostingLastAction.at) < 60000) return;
    (async () => {
      const res = await switchHostingMode('半自动');
      if (res?.success) {
        setAutoHostingLastAction({
          at: now,
          action: 'auto_downgrade_to_semi_auto',
          reason: autoGuardSnapshot.reasons.join('；'),
        });
        showNotice(`自动安全降级：已切到半自动（${autoGuardSnapshot.reasons.join('；')}）`, 'error');
      }
    })();
  }, [autoGuardSnapshot, autoHostingLastAction, showNotice, switchHostingMode]);

  useEffect(() => {
    const items = Array.isArray(state.governanceAudit) ? state.governanceAudit : [];
    if (!items.length) return;
    const latest = items[0];
    const key = String(latest?.ts || '');
    if (!key) return;
    try {
      const prev = window.localStorage.getItem('governance_audit_last_ts') || '';
      if (prev && prev !== key) {
        const ev = String(latest?.event || 'governance_update');
        showNotice(`治理变更已更新：${ev}`, 'success');
      }
      window.localStorage.setItem('governance_audit_last_ts', key);
    } catch {
      // noop
    }
  }, [state.governanceAudit, showNotice]);

  const flowRows = useMemo(() => {
    const accountOk = !state.accountDiagnostics?.degraded;
    const marketOk = !!state.ticker && !!state.orderbook;
    const analysisOk = !!state.fusion && !!state.dataHubSnapshot;
    const executionOk = !!state.executionSpine;
    const riskOk = !!state.riskStatus;
    return [
      { id: 'ingestion', label: '数据采集', ok: marketOk, detail: marketOk ? '实时行情正常' : '行情数据不完整' },
      { id: 'analysis', label: '融合分析', ok: analysisOk, detail: analysisOk ? '分析链路可用' : '分析数据缺失' },
      { id: 'execution', label: '开平仓执行', ok: executionOk, detail: executionOk ? '执行脊柱在线' : '执行状态未知' },
      { id: 'risk', label: '风控与SLTP', ok: riskOk, detail: riskOk ? '风控在线' : '风控状态未知' },
      { id: 'account', label: '仓位与钱包同步', ok: accountOk, detail: accountOk ? '同步链路可用' : '同步降级/超时' },
    ];
  }, [state]);

  const view = useMemo(() => {
    const diag = state.accountDiagnostics || {};
    const diagData = diag.data || diag;
    const balance = diagData.balance || {};
    const balanceDetails = Array.isArray(diagData.balance_details) ? diagData.balance_details : [];
    const positions = Array.isArray(diagData.positions) ? diagData.positions : [];
    const usdt = diagData.usdt_balance || { free: diagData.usdt_free, total: diagData.usdt_total };
    const alerts = Array.isArray(state.monitoringAlerts) ? state.monitoringAlerts : [];
    const ticker = state.ticker || {};
    const bids = Array.isArray(state.orderbook?.bids) ? state.orderbook.bids : [];
    const asks = Array.isArray(state.orderbook?.asks) ? state.orderbook.asks : [];
    return {
      healthText: state.health?.overall || state.health?.status || '-',
      exchangeText: state.exchanges?.[0]?.status || state.exchanges?.[0]?.api_status || '-',
      tickerPrice: ticker.last || ticker.price || '-',
      tickerBid: ticker.bid || '-',
      tickerAsk: ticker.ask || '-',
      spread: ticker.bid && ticker.ask ? Number(ticker.ask) - Number(ticker.bid) : null,
      orderbookLevels: { bids: bids.slice(0, 10), asks: asks.slice(0, 10) },
      alertsCount: alerts.length,
      riskLevel: state.riskStatus?.status || state.riskMonitor?.risk_level || '-',
      balances: balance,
      balanceDetails,
      positions,
      usdt,
      tradeHistory: Array.isArray(state.tradeHistory) ? state.tradeHistory : [],
      strategyCount: Array.isArray(state.strategies) ? state.strategies.length : 0,
      opportunitiesCount: Array.isArray(state.opportunities) ? state.opportunities.length : 0,
      loopPolicy: state.executionSpine?.policy_metrics || {},
      stopLossStats: state.stopLossStats || {},
      tradeEvents: Array.isArray(state.tradeEvents) ? state.tradeEvents : [],
      aiGuards: state.aiGuards || {},
      marketSymbolView: state.marketSymbolView || {},
      analysisProcess: {
        trend: state.marketSymbolView?.trend || state.marketSymbolView?.action_bias || '-',
        confidence: state.marketSymbolView?.confidence ?? state.aiAnalysis?.confidence ?? '-',
        qualityScore: state.qualityAdvice?.score ?? state.dataHubSnapshot?.数据质量评估?.score ?? '-',
        signal: state.aiAnalysis?.signal || state.aiAnalysis?.action || state.fusion?.signal || '-',
      },
      tradingProcess: {
        policy: state.executionSpine?.policy_metrics || {},
        decision: state.aiAnalysis?.decision || state.aiAnalysis?.action || state.marketSymbolView?.action_bias || '-',
        latestEvent: (Array.isArray(state.tradeEvents) && state.tradeEvents[0]) || null,
        synced: !state.accountDiagnostics?.degraded,
      },
      autoHostingGuard: autoGuardSnapshot,
    };
  }, [autoGuardSnapshot, state]);

  return {
    tab,
    setTab,
    symbol,
    setSymbol,
    watchSymbols,
    setWatchSymbols,
    notice,
    loading,
    errors,
    updatedAt,
    state,
    flowRows,
    view,
    commandInput,
    setCommandInput,
    commandReply,
    simulatePayload,
    setSimulatePayload,
    actions: {
      refreshAll,
      loadFast,
      loadMedium,
      loadSlow,
      runAccountSync,
      runSimulateOrder,
      sendCommanderMessage,
      confirmSuggestedOpen,
      switchHostingMode,
      toggleAutoHostingGuard,
      setAutomationProfile,
      updateRiskRedlines,
      runUpgradePipeline,
      runApiSmokeTest,
    },
  };
}
