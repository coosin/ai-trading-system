import React, { Suspense, useEffect, useMemo, useState } from 'react';
import { api } from '../../services/api';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from 'recharts';

const WATCH_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'ADA/USDT', 'XRP/USDT'];
const DOC_LOADERS = import.meta.glob('../../../../docs/**/*.md', { query: '?raw', import: 'default' });
const CHART_ANIMATION = false;
const MarkdownRenderer = React.lazy(() => import('react-markdown'));

class ControlHubErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    // eslint-disable-next-line no-console
    console.error('ControlHub render error:', error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header"><div className="panel-title">⚠️ 总控页面异常</div></div>
          <div className="panel-body">渲染异常已被拦截。请刷新页面，若持续出现请查看浏览器控制台日志。</div>
        </div>
      );
    }
    return this.props.children;
  }
}

function ControlHubModule() {
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem('control_hub_active_tab') || 'overview');
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState(null);

  const [modules, setModules] = useState([]);
  const [health, setHealth] = useState(null);
  const [s1, setS1] = useState(null);
  const [risk, setRisk] = useState({});
  const [memoryStats, setMemoryStats] = useState({});
  const [guards, setGuards] = useState(null);
  const [sltpStats, setSltpStats] = useState(null);
  const [strategyOpt, setStrategyOpt] = useState(null);
  const [strategies, setStrategies] = useState([]);
  const [tickerMap, setTickerMap] = useState({});
  const [selectedSymbol, setSelectedSymbol] = useState(() => localStorage.getItem('control_hub_selected_symbol') || 'BTC/USDT');
  const [klineData, setKlineData] = useState([]);
  const [orderBook, setOrderBook] = useState({ bids: [], asks: [] });
  const [guardTrend, setGuardTrend] = useState([]);
  const [sltpTrend, setSltpTrend] = useState([]);
  const [lastGuardBackup, setLastGuardBackup] = useState(null);
  const [tradeHistory, setTradeHistory] = useState([]);
  const [monitorLogs, setMonitorLogs] = useState([]);
  const [apiLatencyMs, setApiLatencyMs] = useState(0);
  const [healthPingStatus, setHealthPingStatus] = useState('unknown');
  const [executionTypeFilter, setExecutionTypeFilter] = useState(() => localStorage.getItem('control_hub_exec_type') || 'all');
  const [executionQuery, setExecutionQuery] = useState(() => localStorage.getItem('control_hub_exec_query') || '');
  const [acknowledgedAlerts, setAcknowledgedAlerts] = useState({});
  const [alertSilenceUntil, setAlertSilenceUntil] = useState(0);
  const [paramAuditTrail, setParamAuditTrail] = useState(() => {
    try {
      const raw = localStorage.getItem('control_hub_param_audit');
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });
  const [replayExpandedKey, setReplayExpandedKey] = useState('');
  const [severityRules, setSeverityRules] = useState(() => {
    try {
      const raw = localStorage.getItem('control_hub_alert_severity_rules');
      if (raw) return JSON.parse(raw);
    } catch {}
    return {
      p1Keywords: 's1未通过,error,exception',
      p2Keywords: 'timeout,连续亏损,系统健康状态',
    };
  });
  const [replaySymbolFilter, setReplaySymbolFilter] = useState(() => localStorage.getItem('control_hub_replay_symbol') || 'all');
  const [replayHours, setReplayHours] = useState(() => Number(localStorage.getItem('control_hub_replay_hours') || 24));
  const [replayPage, setReplayPage] = useState(1);
  const replayPageSize = 6;
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(() => localStorage.getItem('control_hub_auto_refresh') !== '0');
  const [refreshIntervalSec, setRefreshIntervalSec] = useState(() => Number(localStorage.getItem('control_hub_refresh_sec') || 10));
  const [lastRefreshAt, setLastRefreshAt] = useState('');
  const [alertViewFilter, setAlertViewFilter] = useState(() => localStorage.getItem('control_hub_alert_filter') || 'active');
  const [busyActions, setBusyActions] = useState({});
  const [docQuery, setDocQuery] = useState('');
  const [selectedDocId, setSelectedDocId] = useState('control-hub-user-manual');
  const [docContents, setDocContents] = useState({});
  const [docLoading, setDocLoading] = useState(false);
  const [domainSettings, setDomainSettings] = useState(() => {
    try {
      const raw = localStorage.getItem('control_hub_domain_settings');
      return raw
        ? JSON.parse(raw)
        : {
          public_domain: 'okx.qlsm.net',
          api_upstream_port: 18790,
          notes: '预留：后续在服务器域名管理服务中配置 Nginx/隧道。',
        };
    } catch {
      return {
        public_domain: 'okx.qlsm.net',
        api_upstream_port: 18790,
        notes: '预留：后续在服务器域名管理服务中配置 Nginx/隧道。',
      };
    }
  });

  const [optForm, setOptForm] = useState({
    pool_limit: 30,
    daily_batch_size: 4,
    daily_batch_time_budget_sec: 1.0,
    daily_opt_cycle_seconds: 180,
  });

  const showNotice = (message, type = 'success') => {
    setNotice({ message, type });
    window.setTimeout(() => setNotice(null), 2500);
  };

  const withActionLock = async (key, fn) => {
    if (busyActions[key]) return;
    setBusyActions((prev) => ({ ...prev, [key]: true }));
    try {
      await fn();
    } finally {
      setBusyActions((prev) => ({ ...prev, [key]: false }));
    }
  };

  const renderStateHint = (text, type = 'empty') => {
    const icon = type === 'error' ? '⚠️' : 'ℹ️';
    const color = type === 'error' ? 'var(--error-color)' : 'var(--text-tertiary)';
    return <div style={{ color, padding: '8px 0' }}>{icon} {text}</div>;
  };

  const saveSeverityRules = () => {
    localStorage.setItem('control_hub_alert_severity_rules', JSON.stringify(severityRules));
    showNotice('告警分级规则已保存');
  };

  const recordParamAudit = (source, before, after, action = 'update') => {
    const item = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
      timestamp: new Date().toISOString(),
      source,
      action,
      before,
      after,
    };
    setParamAuditTrail((prev) => {
      const next = [item, ...prev].slice(0, 120);
      localStorage.setItem('control_hub_param_audit', JSON.stringify(next));
      return next;
    });
  };

  const metricColor = (value, warn, danger, reverse = false) => {
    const v = Number(value || 0);
    if (!reverse) {
      if (v >= danger) return 'var(--error-color)';
      if (v >= warn) return 'var(--warning-color)';
      return 'var(--success-color)';
    }
    if (v <= danger) return 'var(--error-color)';
    if (v <= warn) return 'var(--warning-color)';
    return 'var(--success-color)';
  };

  const guardTemplates = {
    conservative: { min_rr_to_trade: 1.4, max_spread_bps_to_trade: 28 },
    normal: { min_rr_to_trade: 1.2, max_spread_bps_to_trade: 35 },
    aggressive: { min_rr_to_trade: 1.1, max_spread_bps_to_trade: 42 },
  };

  const refreshAll = async () => {
    setLoading(true);
    try {
      const pingStart = Date.now();
      const [
        modulesRes,
        healthRes,
        s1Res,
        riskRes,
        memoryRes,
        guardsRes,
        sltpRes,
        strategyRes,
        strategiesRes,
        historyRes,
        logsRes,
      ] = await Promise.all([
        api.request('/modules/list').catch(() => ({ modules: [] })),
        api.request('/modules/system/health').catch(() => null),
        api.request('/s1/verify').catch(() => null),
        api.request('/modules/risk/status').catch(() => ({})),
        api.request('/modules/memory/stats').catch(() => ({})),
        api.request('/modules/ai/guards').catch(() => null),
        api.request('/modules/stop-loss/stats').catch(() => null),
        api.modules.getStrategyOptimizationStatus().catch(() => null),
        api.strategies.getAll().catch(() => []),
        api.trading.getHistory({ limit: 20 }).catch(() => []),
        api.monitoring.getLogs({ limit: 50 }).catch(() => []),
      ]);
      const latency = Date.now() - pingStart;
      setApiLatencyMs(latency);
      setHealthPingStatus(latency < 1200 ? 'good' : latency < 3000 ? 'degraded' : 'bad');

      setModules(modulesRes?.modules || []);
      setHealth(healthRes);
      setS1(s1Res);
      setRisk(riskRes || {});
      setMemoryStats(memoryRes || {});
      setGuards(guardsRes || null);
      setSltpStats(sltpRes || null);
      setStrategyOpt(strategyRes?.data || null);
      setTradeHistory(Array.isArray(historyRes) ? historyRes : []);
      setMonitorLogs(Array.isArray(logsRes) ? logsRes : []);
      const ts = new Date().toLocaleTimeString('zh-CN', { hour12: false });
      const gStats = guardsRes?.stats || {};
      setGuardTrend((prev) => [
        ...prev.slice(-19),
        {
          time: ts,
          rr: Number(gStats.rr_rejected || 0),
          spread: Number(gStats.spread_rejected || 0),
          dq: Number(gStats.data_quality_guard_hold || 0),
        },
      ]);
      setSltpTrend((prev) => [
        ...prev.slice(-19),
        {
          time: ts,
          dynamic: Number(sltpRes?.stats?.dynamic_adjustments || 0),
          active: Number(sltpRes?.stats?.active_orders || 0),
        },
      ]);
      setStrategies(Array.isArray(strategiesRes) ? strategiesRes : []);

      const runtime = strategyRes?.data?.runtime_config;
      if (runtime) {
        setOptForm((prev) => ({
          ...prev,
          pool_limit: Number(runtime.pool_limit ?? prev.pool_limit),
          daily_batch_size: Number(runtime.daily_batch_size ?? prev.daily_batch_size),
          daily_batch_time_budget_sec: Number(runtime.daily_batch_time_budget_sec ?? prev.daily_batch_time_budget_sec),
          daily_opt_cycle_seconds: Number(runtime.daily_opt_cycle_seconds ?? prev.daily_opt_cycle_seconds),
        }));
      }

      const tickers = await Promise.all(
        WATCH_SYMBOLS.map(async (symbol) => {
          try {
            const t = await api.market.getTicker(symbol);
            return [symbol, t];
          } catch {
            return [symbol, null];
          }
        })
      );
      setTickerMap(Object.fromEntries(tickers));
      await loadSymbolBoardData(selectedSymbol);
      setLastRefreshAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }));
    } finally {
      setLoading(false);
    }
  };

  const loadSymbolBoardData = async (symbol) => {
    try {
      const [kl, ob] = await Promise.all([
        api.market.getKlines(symbol, '1h', 48).catch(() => []),
        api.market.getOrderBook(symbol).catch(() => ({ bids: [], asks: [] })),
      ]);
      const formatted = (kl || []).map((k) => ({
        time: new Date(k.timestamp || k[0]).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
        close: Number(k.close || k[4] || 0),
      }));
      setKlineData(formatted);
      setOrderBook({
        bids: (ob?.bids || []).slice(0, 8),
        asks: (ob?.asks || []).slice(0, 8),
      });
    } catch {
      setKlineData([]);
      setOrderBook({ bids: [], asks: [] });
    }
  };

  useEffect(() => {
    refreshAll();
    if (!autoRefreshEnabled) return undefined;
    const sec = Math.max(5, Number(refreshIntervalSec || 10));
    const timer = setInterval(refreshAll, sec * 1000);
    return () => clearInterval(timer);
  }, [autoRefreshEnabled, refreshIntervalSec]);

  useEffect(() => {
    localStorage.setItem('control_hub_active_tab', activeTab);
    localStorage.setItem('control_hub_selected_symbol', selectedSymbol);
    localStorage.setItem('control_hub_auto_refresh', autoRefreshEnabled ? '1' : '0');
    localStorage.setItem('control_hub_refresh_sec', String(refreshIntervalSec));
    localStorage.setItem('control_hub_alert_filter', alertViewFilter);
    localStorage.setItem('control_hub_exec_type', executionTypeFilter);
    localStorage.setItem('control_hub_exec_query', executionQuery);
    localStorage.setItem('control_hub_replay_symbol', replaySymbolFilter);
    localStorage.setItem('control_hub_replay_hours', String(replayHours));
  }, [
    activeTab,
    selectedSymbol,
    autoRefreshEnabled,
    refreshIntervalSec,
    alertViewFilter,
    executionTypeFilter,
    executionQuery,
    replaySymbolFilter,
    replayHours,
  ]);

  useEffect(() => {
    try {
      localStorage.setItem('control_hub_domain_settings', JSON.stringify(domainSettings));
    } catch {
      // ignore
    }
  }, [domainSettings]);

  useEffect(() => {
    let cancelled = false;
    const loadDoc = async () => {
      if (!selectedDoc?.id || !selectedDoc?.path) return;
      if (docContents[selectedDoc.id]) return;
      const loader = DOC_LOADERS[selectedDoc.path];
      if (!loader) {
        if (!cancelled) {
          setDocContents((prev) => ({ ...prev, [selectedDoc.id]: '文档加载失败：未找到文件映射。' }));
        }
        return;
      }
      setDocLoading(true);
      try {
        const raw = await loader();
        if (!cancelled) {
          setDocContents((prev) => ({ ...prev, [selectedDoc.id]: String(raw || '') }));
        }
      } catch {
        if (!cancelled) {
          setDocContents((prev) => ({ ...prev, [selectedDoc.id]: '文档加载失败：读取异常。' }));
        }
      } finally {
        if (!cancelled) setDocLoading(false);
      }
    };
    loadDoc();
    return () => {
      cancelled = true;
    };
  }, [selectedDoc, docContents]);

  const moduleControl = async (moduleId, action) => {
    if (!window.confirm(`确认执行 ${moduleId} -> ${action} 吗？`)) return;
    await withActionLock(`module:${moduleId}:${action}`, async () => {
      try {
        const res = await api.request(`/modules/${moduleId}/control?action=${action}`, { method: 'POST', body: '{}' });
        if (res?.success) {
          showNotice(res.message || `${moduleId}:${action} 已执行`);
          await refreshAll();
        } else {
          showNotice(res?.message || '操作失败', 'error');
        }
      } catch (e) {
        showNotice(`操作失败: ${e.message}`, 'error');
      }
    });
  };

  const updateOptimizationConfig = async () => {
    const before = strategyOpt?.runtime_config || {};
    const after = {
      pool_limit: Number(optForm.pool_limit),
      daily_batch_size: Number(optForm.daily_batch_size),
      daily_batch_time_budget_sec: Number(optForm.daily_batch_time_budget_sec),
      daily_opt_cycle_seconds: Number(optForm.daily_opt_cycle_seconds),
    };
    await withActionLock('opt:update', async () => {
      try {
        const res = await api.modules.updateStrategyOptimizationConfig(after);
        if (res?.success) {
          recordParamAudit('strategy_optimization', before, after, 'runtime_hot_update');
          showNotice('策略优化参数已热更新');
          await refreshAll();
        } else {
          showNotice(res?.message || '更新失败', 'error');
        }
      } catch (e) {
        showNotice(`更新失败: ${e.message}`, 'error');
      }
    });
  };

  const setGuardPreset = async (mode) => {
    const payload = guardTemplates[mode] || guardTemplates.normal;
    const before = {
      min_rr_to_trade: Number(guards?.config?.min_rr_to_trade || 1.2),
      max_spread_bps_to_trade: Number(guards?.config?.max_spread_bps_to_trade || 35),
    };
    await withActionLock(`guard:${mode}`, async () => {
      try {
        const res = await api.request('/modules/ai/guards', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        if (res?.success) {
          recordParamAudit('guard_preset', before, payload, `preset_${mode}`);
          showNotice(`执行门控已切换: ${mode}`);
          await refreshAll();
        } else {
          showNotice(res?.message || '切换失败', 'error');
        }
      } catch (e) {
        showNotice(`切换失败: ${e.message}`, 'error');
      }
    });
  };

  const saveConfigSnapshot = () => {
    const snapshot = {
      optForm,
      guardConfig: {
        min_rr_to_trade: guards?.config?.min_rr_to_trade,
        max_spread_bps_to_trade: guards?.config?.max_spread_bps_to_trade,
      },
      savedAt: new Date().toISOString(),
    };
    localStorage.setItem('control_hub_snapshot', JSON.stringify(snapshot));
    showNotice('已保存当前配置快照');
  };

  const restoreConfigSnapshot = async () => {
    const raw = localStorage.getItem('control_hub_snapshot');
    if (!raw) {
      showNotice('没有可恢复的快照', 'error');
      return;
    }
    try {
      const snap = JSON.parse(raw);
      const before = {
        guard: {
          min_rr_to_trade: Number(guards?.config?.min_rr_to_trade || 1.2),
          max_spread_bps_to_trade: Number(guards?.config?.max_spread_bps_to_trade || 35),
        },
        optimization: strategyOpt?.runtime_config || {},
      };
      if (snap?.optForm) {
        setOptForm({
          pool_limit: Number(snap.optForm.pool_limit || optForm.pool_limit),
          daily_batch_size: Number(snap.optForm.daily_batch_size || optForm.daily_batch_size),
          daily_batch_time_budget_sec: Number(
            snap.optForm.daily_batch_time_budget_sec || optForm.daily_batch_time_budget_sec
          ),
          daily_opt_cycle_seconds: Number(snap.optForm.daily_opt_cycle_seconds || optForm.daily_opt_cycle_seconds),
        });
      }
      if (snap?.guardConfig?.min_rr_to_trade && snap?.guardConfig?.max_spread_bps_to_trade) {
        await api.request('/modules/ai/guards', {
          method: 'POST',
          body: JSON.stringify({
            min_rr_to_trade: Number(snap.guardConfig.min_rr_to_trade),
            max_spread_bps_to_trade: Number(snap.guardConfig.max_spread_bps_to_trade),
          }),
        });
      }
      await updateOptimizationConfig();
      recordParamAudit('snapshot_restore', before, {
        guard: snap?.guardConfig || {},
        optimization: snap?.optForm || {},
      }, 'restore');
      showNotice('已恢复配置快照');
      await refreshAll();
    } catch (e) {
      showNotice(`恢复失败: ${e.message}`, 'error');
    }
  };

  const runningModules = useMemo(() => modules.filter((m) => m.status === 'running').length, [modules]);
  const s1Passed = useMemo(() => (s1?.checks || []).filter((c) => c.passed).length, [s1]);
  const s1Total = (s1?.checks || []).length;
  const tradingSession = useMemo(() => {
    const h = new Date().getUTCHours();
    if (h < 8) return '亚洲时段';
    if (h < 16) return '欧洲时段';
    return '美洲时段';
  }, [loading]);

  const marketRegime = useMemo(() => {
    const vols = WATCH_SYMBOLS
      .map((s) => Math.abs(Number((tickerMap[s] || {}).change || (tickerMap[s] || {}).changePercent || 0)))
      .filter((v) => Number.isFinite(v));
    if (!vols.length) return '未知';
    const avgVol = vols.reduce((a, b) => a + b, 0) / vols.length;
    const rr = Number(guards?.config?.min_rr_to_trade || 1.2);
    const spread = Number(guards?.config?.max_spread_bps_to_trade || 35);
    if (avgVol >= 3.0) return '高波动';
    if (avgVol <= 1.0 && rr >= 1.2 && spread <= 35) return '震荡';
    return '趋势';
  }, [tickerMap, guards]);

  const actionAdvice = useMemo(() => {
    const losses = Number(risk?.consecutive_losses || 0);
    const dq = Number(guards?.stats?.data_quality_guard_hold || 0);
    const rr = Number(guards?.config?.min_rr_to_trade || 1.2);
    const spread = Number(guards?.config?.max_spread_bps_to_trade || 35);
    if (losses >= 3 || dq >= 12) {
      return {
        level: '保守',
        text: '建议短时收紧风险参数，优先等待高质量信号，减少新开仓频率。',
      };
    }
    if (marketRegime === '高波动' && rr <= 1.15 && spread >= 40) {
      return {
        level: '偏进取',
        text: '当前参数偏进取且市场高波动，建议关注滑点与仓位暴露，适度回收杠杆。',
      };
    }
    if (marketRegime === '趋势' && rr >= 1.2 && spread <= 35) {
      return {
        level: '标准',
        text: '当前参数与趋势环境匹配，建议维持标准门控并持续观察回撤变化。',
      };
    }
    return {
      level: '观察',
      text: `当前 RR=${rr.toFixed(2)} / Spread=${spread.toFixed(0)}bps，建议按盘面微调后再放量。`,
    };
  }, [risk, guards, marketRegime]);

  const applyAdvicePreset = async () => {
    let mode = 'normal';
    if (actionAdvice.level === '保守') mode = 'conservative';
    if (actionAdvice.level === '偏进取') mode = 'aggressive';
    await withActionLock('advice:apply', async () => {
      try {
        // 先备份当前关键门控参数，便于一键回滚
        setLastGuardBackup({
          min_rr_to_trade: Number(guards?.config?.min_rr_to_trade || 1.2),
          max_spread_bps_to_trade: Number(guards?.config?.max_spread_bps_to_trade || 35),
        });
        await setGuardPreset(mode);
        showNotice(`已按建议应用参数：${actionAdvice.level}（${mode}）`);
      } catch (e) {
        showNotice(`应用建议失败: ${e.message}`, 'error');
      }
    });
  };

  const rollbackAdvicePreset = async () => {
    if (!lastGuardBackup) {
      showNotice('没有可回滚的参数快照', 'error');
      return;
    }
    await withActionLock('advice:rollback', async () => {
      try {
        const before = {
          min_rr_to_trade: Number(guards?.config?.min_rr_to_trade || 1.2),
          max_spread_bps_to_trade: Number(guards?.config?.max_spread_bps_to_trade || 35),
        };
        const res = await api.request('/modules/ai/guards', {
          method: 'POST',
          body: JSON.stringify({
            min_rr_to_trade: Number(lastGuardBackup.min_rr_to_trade),
            max_spread_bps_to_trade: Number(lastGuardBackup.max_spread_bps_to_trade),
          }),
        });
        if (res?.success) {
          recordParamAudit('guard_preset', before, lastGuardBackup, 'rollback');
          showNotice('已回滚到应用前参数');
          await refreshAll();
        } else {
          showNotice(res?.message || '回滚失败', 'error');
        }
      } catch (e) {
        showNotice(`回滚失败: ${e.message}`, 'error');
      }
    });
  };
  const alertLines = useMemo(() => {
    const lines = [];
    if (health?.overall && health.overall !== 'healthy') lines.push(`系统健康状态: ${health.overall}`);
    (s1?.checks || []).filter((c) => !c.passed).forEach((c) => lines.push(`S1未通过: ${c.name} - ${c.detail || 'no detail'}`));
    if ((risk.consecutive_losses || 0) >= 3) lines.push(`连续亏损偏高: ${risk.consecutive_losses}`);
    if ((guards?.stats?.data_quality_guard_hold || 0) > 10) lines.push(`数据质量拦截偏高: ${guards.stats.data_quality_guard_hold}`);
    (monitorLogs || [])
      .filter((x) => {
        const msg = String(x?.message || '').toLowerCase();
        return msg.includes('error') || msg.includes('exception') || msg.includes('timeout') || msg.includes('warning');
      })
      .slice(0, 4)
      .forEach((x) => lines.push(`日志告警: ${String(x.message).slice(0, 100)}`));
    return lines.slice(0, 12);
  }, [health, s1, risk, guards, monitorLogs]);

  const executionTimeline = useMemo(() => {
    const evts = [];
    (tradeHistory || []).slice(0, 10).forEach((t) => {
      const ts = t.timestamp || t.time || new Date().toISOString();
      evts.push({
        time: new Date(ts).toLocaleTimeString('zh-CN', { hour12: false }),
        type: 'trade',
        text: `${t.symbol || 'N/A'} ${t.side || '-'} ${t.type || '-'} @ ${t.price || '-'}`,
      });
    });
    if (guards?.stats) {
      evts.push({
        time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        type: 'guard',
        text: `门控统计 RR=${guards.stats.rr_rejected || 0} Spread=${guards.stats.spread_rejected || 0} DQ=${guards.stats.data_quality_guard_hold || 0}`,
      });
    }
    if (sltpStats?.stats) {
      evts.push({
        time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        type: 'sltp',
        text: `SLTP动态=${sltpStats.stats.dynamic_adjustments || 0} 活跃跟踪=${sltpStats.stats.active_orders || 0}`,
      });
    }
    return evts.slice(0, 16);
  }, [tradeHistory, guards, sltpStats]);

  const filteredExecutionTimeline = useMemo(() => {
    const q = executionQuery.trim().toLowerCase();
    return (executionTimeline || []).filter((e) => {
      const typeOk = executionTypeFilter === 'all' || e.type === executionTypeFilter;
      const text = `${e.time} ${e.type} ${e.text}`.toLowerCase();
      const queryOk = !q || text.includes(q);
      return typeOk && queryOk;
    });
  }, [executionTimeline, executionTypeFilter, executionQuery]);

  const alertItems = useMemo(() => {
    const p1 = String(severityRules?.p1Keywords || '')
      .split(',')
      .map((x) => x.trim().toLowerCase())
      .filter(Boolean);
    const p2 = String(severityRules?.p2Keywords || '')
      .split(',')
      .map((x) => x.trim().toLowerCase())
      .filter(Boolean);
    return (alertLines || []).map((line) => {
      const id = `alert-${line}`;
      const lower = String(line).toLowerCase();
      let severity = 'P3';
      if (p1.some((k) => lower.includes(k))) severity = 'P1';
      else if (p2.some((k) => lower.includes(k))) severity = 'P2';
      return {
        id,
        line,
        severity,
        acknowledged: Boolean(acknowledgedAlerts[id]),
      };
    });
  }, [alertLines, acknowledgedAlerts, severityRules]);

  const activeAlerts = useMemo(() => alertItems.filter((a) => !a.acknowledged), [alertItems]);
  const visibleAlerts = useMemo(() => {
    if (alertViewFilter === 'all') return alertItems;
    if (alertViewFilter === 'ack') return alertItems.filter((a) => a.acknowledged);
    if (alertViewFilter === 'p1') return alertItems.filter((a) => a.severity === 'P1');
    if (alertViewFilter === 'p2') return alertItems.filter((a) => a.severity === 'P2');
    if (alertViewFilter === 'p3') return alertItems.filter((a) => a.severity === 'P3');
    return alertItems.filter((a) => !a.acknowledged);
  }, [alertItems, alertViewFilter]);
  const alertSeverityCount = useMemo(() => {
    const c = { P1: 0, P2: 0, P3: 0 };
    alertItems.forEach((a) => { c[a.severity] = (c[a.severity] || 0) + 1; });
    return c;
  }, [alertItems]);

  const isAlertSilenced = useMemo(() => Date.now() < Number(alertSilenceUntil || 0), [alertSilenceUntil, loading]);
  const globalHealthScore = useMemo(() => {
    let score = 100;
    if (!s1?.all_passed) score -= 25;
    if ((health?.overall || '').toLowerCase() !== 'healthy') score -= 20;
    if (apiLatencyMs >= 3000) score -= 20;
    else if (apiLatencyMs >= 1200) score -= 10;
    score -= Math.min(20, activeAlerts.length * 3);
    return Math.max(0, score);
  }, [s1, health, apiLatencyMs, activeAlerts.length]);

  const auditSourceBars = useMemo(() => {
    const map = {};
    (paramAuditTrail || []).slice(0, 80).forEach((x) => {
      map[x.source] = (map[x.source] || 0) + 1;
    });
    return Object.entries(map).map(([name, count]) => ({ name, count }));
  }, [paramAuditTrail]);

  const acknowledgeAlert = (id) => {
    setAcknowledgedAlerts((prev) => ({ ...prev, [id]: Date.now() }));
  };

  const clearAcknowledgedAlerts = () => {
    setAcknowledgedAlerts({});
    showNotice('已清空告警确认状态');
  };

  const silenceAlertsForMinutes = (minutes) => {
    const until = Date.now() + minutes * 60 * 1000;
    setAlertSilenceUntil(until);
    showNotice(`已静默告警 ${minutes} 分钟`);
  };

  const replayEvents = useMemo(() => {
    return (tradeHistory || []).slice(0, 30).map((t, idx) => {
      const ts = t.timestamp || t.time || new Date().toISOString();
      const key = `${t.order_id || t.id || idx}-${ts}`;
      const side = t.side || '-';
      const symbol = t.symbol || 'N/A';
      const price = t.price || '-';
      const qty = t.amount || t.size || '-';
      const steps = [
        { name: '信号生成', detail: `symbol=${symbol}, side=${side}` },
        { name: '门控判定', detail: `RR>=${guards?.config?.min_rr_to_trade ?? '-'}, spread<=${guards?.config?.max_spread_bps_to_trade ?? '-'}bps` },
        { name: '执行网关', detail: `type=${t.type || '-'}, price=${price}, qty=${qty}` },
        { name: '风控挂载', detail: `SLTP active=${sltpStats?.stats?.active_orders ?? 0}` },
      ];
      return {
        key,
        symbol,
        time: new Date(ts).toLocaleString('zh-CN', { hour12: false }),
        ts: new Date(ts).getTime(),
        title: `${symbol} ${side} ${t.type || ''}`.trim(),
        status: t.status || 'completed',
        steps,
      };
    });
  }, [tradeHistory, guards, sltpStats]);

  const filteredReplayEvents = useMemo(() => {
    const minTs = Date.now() - Number(replayHours || 24) * 3600 * 1000;
    return (replayEvents || []).filter((r) => {
      const symbolOk = replaySymbolFilter === 'all' || r.symbol === replaySymbolFilter;
      const timeOk = Number(r.ts || 0) >= minTs;
      return symbolOk && timeOk;
    });
  }, [replayEvents, replaySymbolFilter, replayHours]);

  const replayTotalPages = Math.max(1, Math.ceil(filteredReplayEvents.length / replayPageSize));
  const replayPageItems = useMemo(() => {
    const p = Math.min(Math.max(1, replayPage), replayTotalPages);
    const start = (p - 1) * replayPageSize;
    return filteredReplayEvents.slice(start, start + replayPageSize);
  }, [filteredReplayEvents, replayPage, replayTotalPages]);

  const executionAnomalies = useMemo(() => {
    const fromTrades = (tradeHistory || [])
      .filter((t) => {
        const s = String(t?.status || '').toLowerCase();
        const m = String(t?.message || t?.reason || '').toLowerCase();
        return s.includes('fail') || s.includes('reject') || m.includes('error') || m.includes('timeout');
      })
      .slice(0, 20)
      .map((t) => ({
        time: new Date(t.timestamp || t.time || Date.now()).toLocaleTimeString('zh-CN', { hour12: false }),
        source: 'trade',
        text: `${t.symbol || 'N/A'} ${t.side || '-'} ${t.type || '-'} ${t.status || ''} ${t.message || t.reason || ''}`.trim(),
      }));
    const fromLogs = (monitorLogs || [])
      .filter((l) => {
        const msg = String(l?.message || '').toLowerCase();
        return msg.includes('error') || msg.includes('exception') || msg.includes('timeout');
      })
      .slice(0, 20)
      .map((l) => ({
        time: new Date(l.timestamp || Date.now()).toLocaleTimeString('zh-CN', { hour12: false }),
        source: 'log',
        text: String(l.message || '').slice(0, 160),
      }));
    return [...fromTrades, ...fromLogs].slice(0, 24);
  }, [tradeHistory, monitorLogs]);

  const calcDiffKeys = (before, after) => {
    const b = before && typeof before === 'object' ? before : {};
    const a = after && typeof after === 'object' ? after : {};
    const keys = Array.from(new Set([...Object.keys(b), ...Object.keys(a)]));
    return keys.filter((k) => JSON.stringify(b[k]) !== JSON.stringify(a[k]));
  };

  const docsCatalog = useMemo(() => ([
    { id: 'control-hub-user-manual', title: '总控中心操作手册', group: '总控', path: '../../../../docs/control-hub-user-manual.md' },
    { id: 'control-hub-module-checklist', title: '总控功能清单', group: '总控', path: '../../../../docs/control-hub-module-checklist.md' },
    { id: 'dynamic-open-close', title: '动态开平仓与SLTP手册', group: '交易', path: '../../../../docs/dynamic-open-close-and-sltp-playbook.md' },
    { id: 'memory-arch', title: '记忆架构对齐', group: '架构', path: '../../../../docs/MEMORY_ARCHITECTURE_ALIGNMENT.md' },
    { id: 'changelog', title: '变更日志', group: '运维', path: '../../../../docs/CHANGELOG.md' },
    { id: 'final-verification', title: '最终验证报告', group: '运维', path: '../../../../docs/final_verification_report.md' },
    { id: 'test-report', title: '测试报告', group: '运维', path: '../../../../docs/测试报告.md' },
    { id: 'feature-guide', title: '功能缩影指南', group: '产品', path: '../../../../docs/功能缩影指南.md' },
    { id: 'integration-summary', title: '整合总结', group: '产品', path: '../../../../docs/整合总结.md' },
    { id: 'optimization-report', title: '功能优化分析报告', group: '产品', path: '../../../../docs/功能优化分析报告.md' },
    { id: 'intelligent-flow', title: '智能流程说明', group: '架构', path: '../../../../docs/INTELLIGENT_FLOW.md' },
    { id: 'maintenance-guide', title: '维护指南', group: '运维', path: '../../../../docs/MAINTENANCE_GUIDE.md' },
    { id: 'api-doc', title: 'API 文档', group: '接口', path: '../../../../docs/api.md' },
    { id: 'module-nl', title: '自然语言模块文档', group: '模块', path: '../../../../docs/modules/natural_language_interface.md' },
    { id: 'module-strategy-eval', title: '策略评估模块文档', group: '模块', path: '../../../../docs/modules/strategy_evaluator.md' },
    { id: 'work-plan', title: '工作计划', group: '规划', path: '../../../../docs/WORK_PLAN.md' },
    { id: 'nl-trading', title: '自然语言交易说明', group: '交易', path: '../../../../docs/NATURAL_LANGUAGE_TRADING.md' },
    { id: 'system-opt', title: '系统优化方案', group: '规划', path: '../../../../docs/SYSTEM_OPTIMIZATION_2026-04-01.md' },
    { id: 'code-review', title: '代码审查报告', group: '质量', path: '../../../../docs/CODE_REVIEW_REPORT.md' },
  ]), []);

  const filteredDocs = useMemo(() => {
    const q = docQuery.trim().toLowerCase();
    if (!q) return docsCatalog;
    return docsCatalog.filter((d) => `${d.title} ${d.group} ${d.id}`.toLowerCase().includes(q));
  }, [docsCatalog, docQuery]);

  const selectedDoc = useMemo(() => {
    return docsCatalog.find((d) => d.id === selectedDocId) || filteredDocs[0] || docsCatalog[0];
  }, [docsCatalog, filteredDocs, selectedDocId]);

  const selectedDocContent = useMemo(() => {
    if (!selectedDoc?.id) return '';
    return docContents[selectedDoc.id] || '';
  }, [selectedDoc, docContents]);

  const exportOpsDailyReport = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      overview: {
        health: health?.overall || '-',
        s1_all_passed: Boolean(s1?.all_passed),
        api_latency_ms: apiLatencyMs,
        alert_silenced: isAlertSilenced,
      },
      alerts: {
        total: alertItems.length,
        active: activeAlerts.length,
        severity_count: alertSeverityCount,
        severity_rules: severityRules,
        acknowledged_ids: Object.keys(acknowledgedAlerts || {}),
        items: alertItems,
      },
      execution: {
        timeline_filtered_count: filteredExecutionTimeline.length,
        timeline_filtered: filteredExecutionTimeline,
        replay: replayEvents.slice(0, 20),
      },
      parameter_audit: {
        total: paramAuditTrail.length,
        latest: (paramAuditTrail || []).slice(0, 30),
      },
    };
    const md = [
      `# 运维日报 ${new Date().toLocaleDateString('zh-CN')}`,
      '',
      '## 1) 系统总览',
      `- 健康状态: ${payload.overview.health}`,
      `- S1链路: ${payload.overview.s1_all_passed ? '通过' : '未通过'}`,
      `- API延迟: ${payload.overview.api_latency_ms} ms`,
      `- 告警静默: ${payload.overview.alert_silenced ? '是' : '否'}`,
      '',
      '## 2) 告警摘要',
      `- 总告警: ${payload.alerts.total}`,
      `- 未确认: ${payload.alerts.active}`,
      `- 分级: P1=${payload.alerts.severity_count.P1}, P2=${payload.alerts.severity_count.P2}, P3=${payload.alerts.severity_count.P3}`,
      '',
      '## 3) 参数审计',
      `- 变更总数: ${payload.parameter_audit.total}`,
      ...payload.parameter_audit.latest.slice(0, 8).map((x) => `- [${new Date(x.timestamp).toLocaleTimeString('zh-CN', { hour12: false })}] ${x.source}/${x.action}`),
      '',
      '## 4) 执行回放(最近)',
      ...payload.execution.replay.slice(0, 6).map((x) => `- ${x.time} ${x.title} (${x.status})`),
      '',
      '```json',
      JSON.stringify(payload, null, 2),
      '```',
    ].join('\n');
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `ops-daily-report-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
    showNotice('已导出运维日报');
  };

  const strategyTypePie = useMemo(() => {
    const map = {};
    (strategies || []).forEach((s) => {
      const t = s.type || s.strategy_type || 'unknown';
      map[t] = (map[t] || 0) + 1;
    });
    return Object.entries(map).map(([name, value]) => ({ name, value }));
  }, [strategies]);

  const topStrategyBars = useMemo(() => {
    return (strategies || [])
      .map((s) => ({
        name: (s.name || s.strategy_id || 'unknown').slice(0, 12),
        score: Number(s.sharpe_ratio || s.score || 0),
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 8);
  }, [strategies]);

  const massModuleAction = async (action) => {
    if (!window.confirm(`确认批量执行 ${action} 吗？`)) return;
    await withActionLock(`module:mass:${action}`, async () => {
      const targets = modules.filter((m) => (m.controls || []).includes(action)).slice(0, 8);
      for (const m of targets) {
        // eslint-disable-next-line no-await-in-loop
        await moduleControl(m.id, action);
      }
      showNotice(`批量操作完成: ${action}`);
    });
  };

  const strategyPrunePreview = useMemo(() => {
    const poolLimit = Number(optForm.pool_limit || strategyOpt?.pool_limit || 30);
    const list = (strategies || []).map((s) => {
      const score =
        Number(s.sharpe_ratio || 0) * 0.6 +
        Number(s.return_rate || s.pnl || 0) * 0.003 -
        Number(s.max_drawdown || 0) * 0.1;
      return {
        id: s.strategy_id || s.id || s.name || 'unknown',
        name: s.name || s.strategy_id || 'unknown',
        score: Number.isFinite(score) ? score : 0,
      };
    });
    const sorted = list.sort((a, b) => a.score - b.score);
    const over = Math.max(0, sorted.length - poolLimit);
    return {
      over,
      candidates: sorted.slice(0, Math.min(over || 5, 10)),
      total: sorted.length,
      poolLimit,
    };
  }, [strategies, optForm.pool_limit, strategyOpt?.pool_limit]);

  const exportSnapshot = (format = 'json') => {
    const payload = {
      exported_at: new Date().toISOString(),
      health,
      s1,
      risk,
      memoryStats,
      guards,
      sltpStats,
      strategyOpt,
      strategyPrunePreview,
      tickers: tickerMap,
    };
    if (format === 'json') {
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `control-hub-snapshot-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      showNotice('已导出 JSON 快照');
      return;
    }
    const rows = [];
    rows.push(['section', 'key', 'value'].join(','));
    rows.push(['health', 'overall', `"${health?.overall || ''}"`].join(','));
    rows.push(['s1', 'all_passed', `${Boolean(s1?.all_passed)}`].join(','));
    rows.push(['risk', 'consecutive_losses', `${risk?.consecutive_losses || 0}`].join(','));
    rows.push(['risk', 'daily_trades', `${risk?.daily_trades || 0}`].join(','));
    rows.push(['guard', 'min_rr_to_trade', `${guards?.config?.min_rr_to_trade || ''}`].join(','));
    rows.push(['guard', 'max_spread_bps_to_trade', `${guards?.config?.max_spread_bps_to_trade || ''}`].join(','));
    rows.push(['sltp', 'dynamic_adjustments', `${sltpStats?.stats?.dynamic_adjustments || 0}`].join(','));
    Object.entries(tickerMap || {}).forEach(([sym, t]) => {
      rows.push(['ticker', sym, `${Number(t?.last || t?.price || 0)}`].join(','));
    });
    const csv = rows.join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `control-hub-snapshot-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
    showNotice('已导出 CSV 快照');
  };

  return (
    <ControlHubErrorBoundary>
    <div>
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title"><span className="panel-title-icon">🎛️</span>智能总控中心模块</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-sm btn-outline" onClick={() => exportSnapshot('json')}>导出 JSON</button>
            <button className="btn btn-sm btn-outline" onClick={() => exportSnapshot('csv')}>导出 CSV</button>
            <button className="btn btn-sm btn-outline" onClick={exportOpsDailyReport}>导出运维日报</button>
            <button className="btn btn-sm btn-outline" onClick={refreshAll}>{loading ? '刷新中...' : '刷新全局状态'}</button>
          </div>
        </div>
        <div className="panel-body">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto auto', gap: 8, marginBottom: 12 }}>
            <div style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>
              健康评分 <strong style={{ color: metricColor(globalHealthScore, 70, 45, true) }}>{globalHealthScore}</strong> / 100
              {' '}· 最新刷新 {lastRefreshAt || '--:--:--'}
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
              <input type="checkbox" checked={autoRefreshEnabled} onChange={(e) => setAutoRefreshEnabled(e.target.checked)} />
              自动刷新
            </label>
            <input
              className="form-input"
              type="number"
              min="5"
              max="120"
              value={refreshIntervalSec}
              onChange={(e) => setRefreshIntervalSec(Number(e.target.value || 10))}
              style={{ width: 90 }}
              title="自动刷新间隔(秒)"
            />
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)', alignSelf: 'center' }}>秒/次</div>
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
            <button className="btn btn-sm btn-outline" onClick={() => setGuardPreset('conservative')}>应急一键保守</button>
            <button className="btn btn-sm btn-outline" onClick={() => setGuardPreset('normal')}>一键恢复标准</button>
            <button className="btn btn-sm btn-outline" onClick={exportOpsDailyReport}>一键导出运维日报</button>
          </div>
          <div className="tabs">
            {[
              { id: 'overview', label: '总览驾驶舱' },
              { id: 'market', label: '专业行情看板' },
              { id: 'execution', label: '执行中心' },
              { id: 'alerts', label: '告警中心' },
              { id: 'infra', label: '系统健康中心' },
              { id: 'modules', label: '模块总控' },
              { id: 'strategy', label: '策略与优化' },
              { id: 'risk', label: '执行与风控' },
              { id: 'docs', label: '文档中心' },
            ].map((t) => (
              <div key={t.id} className={`tab ${activeTab === t.id ? 'active' : ''}`} onClick={() => setActiveTab(t.id)}>
                {t.label}
              </div>
            ))}
          </div>
        </div>
      </div>

      {activeTab === 'overview' && (
        <div>
          <div className="dashboard-grid" style={{ marginTop: '16px' }}>
            <div className="stat-card"><div className="stat-card-title">系统健康</div><div className="stat-card-value">{health?.overall || '-'}</div><div className="stat-card-change">{health?.healthy_count || 0}/{health?.total_count || 0}</div></div>
            <div className="stat-card"><div className="stat-card-title">S1执行链路</div><div className="stat-card-value">{s1?.all_passed ? '通过' : '待检查'}</div><div className="stat-card-change">{s1Passed}/{s1Total}</div></div>
            <div className="stat-card"><div className="stat-card-title">模块在线</div><div className="stat-card-value">{runningModules}/{modules.length}</div><div className="stat-card-change">核心模块运行中</div></div>
            <div className="stat-card"><div className="stat-card-title">策略池规模</div><div className="stat-card-value">{strategyOpt?.total_strategies ?? '-'}</div><div className="stat-card-change">上限 {strategyOpt?.pool_limit ?? '-'}</div></div>
            <div className="stat-card"><div className="stat-card-title">全局健康评分</div><div className="stat-card-value" style={{ color: metricColor(globalHealthScore, 70, 45, true) }}>{globalHealthScore}</div><div className="stat-card-change">综合延迟/告警/S1</div></div>
            <div className="stat-card"><div className="stat-card-title">未确认告警</div><div className="stat-card-value">{activeAlerts.length}</div><div className="stat-card-change">P1 {alertSeverityCount.P1} / P2 {alertSeverityCount.P2}</div></div>
          </div>
          <div className="panel" style={{ marginTop: '16px' }}>
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">🧭</span>盘中环境与今日建议</div></div>
            <div className="panel-body">
              <div className="market-stats">
                <div className="market-stat-item"><div className="market-stat-label">交易时段</div><div className="market-stat-value">{tradingSession}</div></div>
                <div className="market-stat-item"><div className="market-stat-label">市场制度</div><div className="market-stat-value">{marketRegime}</div></div>
                <div className="market-stat-item"><div className="market-stat-label">建议风格</div><div className="market-stat-value">{actionAdvice.level}</div></div>
                <div className="market-stat-item"><div className="market-stat-label">连续亏损</div><div className="market-stat-value">{risk?.consecutive_losses ?? 0}</div></div>
              </div>
              <div style={{ marginTop: 10, padding: 12, borderRadius: 8, background: 'var(--bg-secondary)' }}>
                <strong>今日操作建议：</strong> {actionAdvice.text}
                <div style={{ marginTop: 10 }}>
                  <button className="btn btn-sm btn-primary" onClick={applyAdvicePreset}>一键应用建议参数</button>
                  <button
                    className="btn btn-sm btn-outline"
                    style={{ marginLeft: 8 }}
                    onClick={rollbackAdvicePreset}
                    disabled={!lastGuardBackup}
                  >
                    回滚到应用前
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div className="panel" style={{ marginTop: '16px' }}>
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">🌐</span>域名与访问入口（预留配置）</div></div>
            <div className="panel-body">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 160px', gap: 10 }}>
                <input
                  className="form-input"
                  value={domainSettings.public_domain || ''}
                  onChange={(e) => setDomainSettings((p) => ({ ...p, public_domain: e.target.value.trim() }))}
                  placeholder="对外域名，例如：okx.qlsm.net"
                />
                <input
                  className="form-input"
                  type="number"
                  value={Number(domainSettings.api_upstream_port || 18790)}
                  onChange={(e) => setDomainSettings((p) => ({ ...p, api_upstream_port: Number(e.target.value || 18790) }))}
                  placeholder="上游端口"
                  title="反代上游端口（例如 18790）"
                />
              </div>
              <textarea
                className="form-input"
                style={{ marginTop: 10, minHeight: 72 }}
                value={domainSettings.notes || ''}
                onChange={(e) => setDomainSettings((p) => ({ ...p, notes: e.target.value }))}
                placeholder="备注（例如：18789 是小龙虾端口不要动）"
              />
              <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-tertiary)' }}>
                快捷链接：
                {' '}
                <a className="domain-url" href={`https://${domainSettings.public_domain || ''}`} target="_blank" rel="noreferrer">
                  https://{domainSettings.public_domain || '(未填写)'}
                </a>
                {' '}·{' '}
                <span>API 健康：<code>https://{domainSettings.public_domain || '(未填写)'}/health</code></span>
                {' '}·{' '}
                <span>建议反代上游：<code>127.0.0.1:{Number(domainSettings.api_upstream_port || 18790)}</code></span>
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)' }}>
                当前配置仅用于前端留档与生成链接模板；实际生效需你在服务器域名管理服务/Nginx 中完成绑定。
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'market' && (
        <div className="panel-row" style={{ marginTop: '16px' }}>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">📈</span>专业量化行情看板</div></div>
            <div className="panel-body" style={{ padding: 0 }}>
              <table className="positions-table">
                <thead><tr><th>交易对</th><th>最新价</th><th>24h变化</th><th>24h高</th><th>24h低</th><th>24h量</th></tr></thead>
                <tbody>
                  {WATCH_SYMBOLS.map((s) => {
                    const t = tickerMap[s] || {};
                    const p = Number(t.last || t.price || 0);
                    const ch = Number(t.change || t.changePercent || 0);
                    return (
                      <tr key={s} onClick={() => { setSelectedSymbol(s); loadSymbolBoardData(s); }} style={{ cursor: 'pointer' }}>
                        <td className="symbol">{s}</td>
                        <td>{p ? `$${p.toLocaleString()}` : '--'}</td>
                        <td className={ch >= 0 ? 'positive' : 'negative'}>{ch >= 0 ? '+' : ''}{ch.toFixed(2)}%</td>
                        <td>{t.high ? `$${Number(t.high).toLocaleString()}` : '--'}</td>
                        <td>{t.low ? `$${Number(t.low).toLocaleString()}` : '--'}</td>
                        <td>{t.volume ? `${(Number(t.volume) / 1000000).toFixed(2)}M` : '--'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">🧮</span>{selectedSymbol} 专业图表</div></div>
            <div className="panel-body">
              <div style={{ height: 220 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={klineData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" />
                    <YAxis domain={['auto', 'auto']} />
                    <Tooltip />
                    <Area type="monotone" dataKey="close" stroke="#1890ff" fill="#1890ff33" isAnimationActive={CHART_ANIMATION} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: 8 }}>
                <div>
                  <div className="market-stat-label">买盘深度</div>
                  {(orderBook.bids || []).slice(0, 5).map((x, i) => (
                    <div key={i} style={{ fontSize: 12 }}>{Array.isArray(x) ? x[0] : x.price} / {Array.isArray(x) ? x[1] : x.amount}</div>
                  ))}
                </div>
                <div>
                  <div className="market-stat-label">卖盘深度</div>
                  {(orderBook.asks || []).slice(0, 5).map((x, i) => (
                    <div key={i} style={{ fontSize: 12 }}>{Array.isArray(x) ? x[0] : x.price} / {Array.isArray(x) ? x[1] : x.amount}</div>
                  ))}
                </div>
              </div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">🔥</span>持仓风险热力</div></div>
            <div className="panel-body">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
                {WATCH_SYMBOLS.map((s) => {
                  const t = tickerMap[s] || {};
                  const v = Math.abs(Number(t.change || t.changePercent || 0));
                  const c = v > 4 ? '#ff4d4f' : v > 2 ? '#faad14' : '#52c41a';
                  return (
                    <div key={s} style={{ padding: '10px', borderRadius: '8px', background: `${c}22`, border: `1px solid ${c}` }}>
                      <div style={{ fontWeight: 600 }}>{s}</div>
                      <div style={{ color: c }}>波动风险 {v.toFixed(2)}%</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'execution' && (
        <div className="panel-row" style={{ marginTop: '16px' }}>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">🧭</span>执行时间线</div></div>
            <div className="panel-body">
              <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                <select className="form-input" value={executionTypeFilter} onChange={(e) => setExecutionTypeFilter(e.target.value)} style={{ maxWidth: 140 }}>
                  <option value="all">全部类型</option>
                  <option value="trade">成交</option>
                  <option value="guard">门控</option>
                  <option value="sltp">SLTP</option>
                </select>
                <input
                  className="form-input"
                  placeholder="搜索交易对/动作/价格"
                  value={executionQuery}
                  onChange={(e) => setExecutionQuery(e.target.value)}
                />
              </div>
              {filteredExecutionTimeline.length ? filteredExecutionTimeline.map((e, i) => (
                <div key={`${e.time}-${i}`} style={{ padding: '8px 0', borderBottom: '1px solid var(--border-light)' }}>
                  <span style={{ color: 'var(--text-tertiary)', marginRight: 8 }}>[{e.time}]</span>
                  <span style={{ fontWeight: 600, marginRight: 8 }}>{String(e.type || '').toUpperCase()}</span>
                  <span>{e.text}</span>
                </div>
              )) : <div style={{ color: 'var(--text-tertiary)' }}>暂无执行事件</div>}
            </div>
          </div>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">📌</span>执行闭环状态</div></div>
            <div className="panel-body">
              <div className="market-stats">
                <div className="market-stat-item"><div className="market-stat-label">S1链路</div><div className="market-stat-value">{s1?.all_passed ? '正常' : '需检查'}</div></div>
                <div className="market-stat-item"><div className="market-stat-label">近期成交</div><div className="market-stat-value">{tradeHistory.length}</div></div>
                <div className="market-stat-item"><div className="market-stat-label">SLTP活跃</div><div className="market-stat-value">{sltpStats?.stats?.active_orders ?? 0}</div></div>
                <div className="market-stat-item"><div className="market-stat-label">API延迟</div><div className="market-stat-value">{apiLatencyMs} ms</div></div>
              </div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">🎬</span>执行链路回放</div></div>
            <div className="panel-body">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px', gap: 8, marginBottom: 10 }}>
                <select className="form-input" value={replaySymbolFilter} onChange={(e) => { setReplaySymbolFilter(e.target.value); setReplayPage(1); }}>
                  <option value="all">全部交易对</option>
                  {WATCH_SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                <input
                  className="form-input"
                  type="number"
                  min="1"
                  max="168"
                  value={replayHours}
                  onChange={(e) => { setReplayHours(Number(e.target.value || 24)); setReplayPage(1); }}
                  title="回放时间窗口（小时）"
                />
              </div>
              {replayPageItems.map((r) => (
                <div key={r.key} style={{ padding: '8px 0', borderBottom: '1px solid var(--border-light)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <strong>{r.title}</strong>
                      <span style={{ marginLeft: 8, color: 'var(--text-tertiary)', fontSize: 12 }}>{r.time}</span>
                    </div>
                    <button className="btn btn-sm btn-outline" onClick={() => setReplayExpandedKey(replayExpandedKey === r.key ? '' : r.key)}>
                      {replayExpandedKey === r.key ? '收起' : '展开'}
                    </button>
                  </div>
                  {replayExpandedKey === r.key && (
                    <div style={{ marginTop: 8, paddingLeft: 8 }}>
                      {r.steps.map((s, i) => (
                        <div key={i} style={{ fontSize: 12, marginBottom: 6 }}>
                          {i + 1}. {s.name}：{s.detail}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {!filteredReplayEvents.length && <div style={{ color: 'var(--text-tertiary)' }}>当前筛选下暂无可回放执行链路</div>}
              {filteredReplayEvents.length > 0 && (
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10 }}>
                  <button className="btn btn-sm btn-outline" disabled={replayPage <= 1} onClick={() => setReplayPage((p) => Math.max(1, p - 1))}>上一页</button>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>第 {Math.min(replayPage, replayTotalPages)} / {replayTotalPages} 页</div>
                  <button className="btn btn-sm btn-outline" disabled={replayPage >= replayTotalPages} onClick={() => setReplayPage((p) => Math.min(replayTotalPages, p + 1))}>下一页</button>
                </div>
              )}
            </div>
          </div>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">⛑️</span>执行异常聚合</div></div>
            <div className="panel-body">
              {executionAnomalies.length ? executionAnomalies.map((e, i) => (
                <div key={`${e.source}-${i}`} style={{ padding: '8px 0', borderBottom: '1px solid var(--border-light)' }}>
                  <span style={{ color: 'var(--text-tertiary)', marginRight: 8 }}>[{e.time}]</span>
                  <span style={{ color: '#ff4d4f', fontWeight: 600, marginRight: 8 }}>{e.source.toUpperCase()}</span>
                  <span>{e.text}</span>
                </div>
              )) : <div style={{ color: 'var(--text-tertiary)' }}>暂无异常执行事件</div>}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'alerts' && (
        <div className="panel" style={{ marginTop: '16px' }}>
          <div className="panel-header">
            <div className="panel-title"><span className="panel-title-icon">🚨</span>告警中心（归因 + 建议）</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-sm btn-outline" onClick={() => silenceAlertsForMinutes(30)}>静默30分钟</button>
              <button className="btn btn-sm btn-outline" onClick={clearAcknowledgedAlerts}>清空确认</button>
            </div>
          </div>
          <div className="panel-body">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 8, marginBottom: 10 }}>
              <input
                className="form-input"
                value={severityRules.p1Keywords}
                onChange={(e) => setSeverityRules((prev) => ({ ...prev, p1Keywords: e.target.value }))}
                placeholder="P1关键词，逗号分隔"
              />
              <input
                className="form-input"
                value={severityRules.p2Keywords}
                onChange={(e) => setSeverityRules((prev) => ({ ...prev, p2Keywords: e.target.value }))}
                placeholder="P2关键词，逗号分隔"
              />
              <button className="btn btn-sm btn-outline" onClick={saveSeverityRules}>保存分级规则</button>
            </div>
            <div style={{ marginBottom: 10, fontSize: 12, color: 'var(--text-tertiary)' }}>
              状态：{isAlertSilenced ? `已静默至 ${new Date(alertSilenceUntil).toLocaleTimeString('zh-CN', { hour12: false })}` : '告警通知开启'}，当前未确认告警 {activeAlerts.length} 条。
            </div>
            <div style={{ marginBottom: 10, fontSize: 12 }}>
              分级统计：<span style={{ color: '#ff4d4f' }}>P1 {alertSeverityCount.P1}</span> / <span style={{ color: '#faad14' }}>P2 {alertSeverityCount.P2}</span> / <span style={{ color: '#1890ff' }}>P3 {alertSeverityCount.P3}</span>
            </div>
            <div style={{ marginBottom: 10 }}>
              <select className="form-input" value={alertViewFilter} onChange={(e) => setAlertViewFilter(e.target.value)} style={{ maxWidth: 220 }}>
                <option value="active">仅未确认</option>
                <option value="all">全部告警</option>
                <option value="ack">仅已确认</option>
                <option value="p1">仅P1</option>
                <option value="p2">仅P2</option>
                <option value="p3">仅P3</option>
              </select>
            </div>
            {visibleAlerts.length ? visibleAlerts.map((a) => (
              <div key={a.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--border-light)', opacity: a.acknowledged ? 0.6 : 1 }}>
                <div style={{ marginBottom: 4 }}>
                  {a.acknowledged ? '✅' : '⚠️'} [{a.severity}] {a.line}
                </div>
                <div style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>
                  建议动作：检查对应模块日志与参数，必要时先切保守门控，确认后再恢复标准参数。
                </div>
                {!a.acknowledged && (
                  <button className="btn btn-sm btn-outline" style={{ marginTop: 8 }} onClick={() => acknowledgeAlert(a.id)}>
                    标记已确认
                  </button>
                )}
              </div>
            )) : renderStateHint('当前筛选下暂无告警，系统运行稳定。')}
          </div>
        </div>
      )}

      {activeTab === 'infra' && (
        <div className="panel-row" style={{ marginTop: '16px' }}>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">🖥️</span>系统健康中心</div></div>
            <div className="panel-body">
              <div className="market-stats">
                <div className="market-stat-item"><div className="market-stat-label">总体健康</div><div className="market-stat-value">{health?.overall || '-'}</div></div>
                <div className="market-stat-item"><div className="market-stat-label">API延迟</div><div className="market-stat-value" style={{ color: metricColor(apiLatencyMs, 1200, 3000) }}>{apiLatencyMs} ms</div></div>
                <div className="market-stat-item"><div className="market-stat-label">网络状态</div><div className="market-stat-value">{healthPingStatus === 'good' ? '良好' : healthPingStatus === 'degraded' ? '一般' : '较差'}</div></div>
                <div className="market-stat-item"><div className="market-stat-label">模块健康率</div><div className="market-stat-value">{health?.healthy_count || 0}/{health?.total_count || 0}</div></div>
              </div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">📜</span>最近监控日志</div></div>
            <div className="panel-body">
              {(monitorLogs || []).slice(0, 12).map((l, i) => (
                <div key={i} style={{ padding: '6px 0', borderBottom: '1px solid var(--border-light)', fontSize: 12 }}>
                  [{new Date(l.timestamp || Date.now()).toLocaleTimeString('zh-CN', { hour12: false })}] {String(l.message || '').slice(0, 120)}
                </div>
              ))}
              {!monitorLogs.length && renderStateHint('暂无监控日志')}
            </div>
          </div>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">🧾</span>参数变更审计</div></div>
            <div className="panel-body">
              <div style={{ height: 150 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={auditSourceBars}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#13c2c2" isAnimationActive={CHART_ANIMATION} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div style={{ marginTop: 10, maxHeight: 230, overflow: 'auto' }}>
                {(paramAuditTrail || []).slice(0, 20).map((x) => (
                  <div key={x.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--border-light)', fontSize: 12 }}>
                    <div>
                      [{new Date(x.timestamp).toLocaleTimeString('zh-CN', { hour12: false })}] {x.source} / {x.action}
                    </div>
                    <div style={{ color: 'var(--text-tertiary)' }}>
                      {calcDiffKeys(x.before, x.after).length ? (
                        <span>
                          变更字段：
                          {calcDiffKeys(x.before, x.after).map((k) => (
                            <span key={k} style={{ marginLeft: 6, color: '#13c2c2' }}>
                              {k}: {JSON.stringify((x.before || {})[k])} → {JSON.stringify((x.after || {})[k])}
                            </span>
                          ))}
                        </span>
                      ) : (
                        <span>无字段变化</span>
                      )}
                    </div>
                  </div>
                ))}
                {!paramAuditTrail.length && renderStateHint('暂无参数变更记录')}
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'modules' && (
        <div className="panel" style={{ marginTop: '16px' }}>
          <div className="panel-header">
            <div className="panel-title"><span className="panel-title-icon">🧩</span>系统模块总控</div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button className="btn btn-sm btn-outline" onClick={() => massModuleAction('start')}>批量启动</button>
              <button className="btn btn-sm btn-outline" onClick={() => massModuleAction('stop')}>批量停止</button>
              <button className="btn btn-sm btn-outline" onClick={() => massModuleAction('test')}>批量测试</button>
            </div>
          </div>
          <div className="panel-body" style={{ padding: 0 }}>
            <table className="positions-table">
              <thead><tr><th>模块</th><th>分类</th><th>状态</th><th>健康</th><th>操作</th></tr></thead>
              <tbody>
                {modules.map((m) => (
                  <tr key={m.id}>
                    <td className="symbol">{m.name}</td>
                    <td>{m.category}</td>
                    <td>{m.status}</td>
                    <td>{m.health}</td>
                    <td style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      {(m.controls || []).slice(0, 3).map((c) => (
                        <button key={c} className="btn btn-sm btn-outline" onClick={() => moduleControl(m.id, c)}>{c}</button>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'strategy' && (
        <div className="panel-row" style={{ marginTop: '16px' }}>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">⚙️</span>策略池与智能优化</div></div>
            <div className="panel-body">
            <div className="market-stats">
              <div className="market-stat-item"><div className="market-stat-label">今日优化进度</div><div className="market-stat-value">{strategyOpt?.daily_optimization?.processed ?? 0}/{strategyOpt?.daily_optimization?.total ?? 0}</div></div>
              <div className="market-stat-item"><div className="market-stat-label">回撤优化数</div><div className="market-stat-value">{strategyOpt?.daily_optimization?.drawdown_optimized ?? 0}</div></div>
              <div className="market-stat-item"><div className="market-stat-label">批处理耗时</div><div className="market-stat-value">{strategyOpt?.daily_optimization?.last_batch_ms ?? 0} ms</div></div>
              <div className="market-stat-item"><div className="market-stat-label">最近清理</div><div className="market-stat-value">{strategyOpt?.last_pool_prune_at ? '已执行' : '未执行'}</div></div>
            </div>
            <div style={{ marginTop: '12px', display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: '10px' }}>
              <input className="form-input" type="number" value={optForm.pool_limit} onChange={(e) => setOptForm({ ...optForm, pool_limit: e.target.value })} />
              <input className="form-input" type="number" value={optForm.daily_batch_size} onChange={(e) => setOptForm({ ...optForm, daily_batch_size: e.target.value })} />
              <input className="form-input" type="number" step="0.1" value={optForm.daily_batch_time_budget_sec} onChange={(e) => setOptForm({ ...optForm, daily_batch_time_budget_sec: e.target.value })} />
              <input className="form-input" type="number" value={optForm.daily_opt_cycle_seconds} onChange={(e) => setOptForm({ ...optForm, daily_opt_cycle_seconds: e.target.value })} />
            </div>
            <div style={{ marginTop: '10px' }}>
              <button className="btn btn-primary" onClick={updateOptimizationConfig}>保存并热更新</button>
              <button className="btn btn-sm btn-outline" style={{ marginLeft: 8 }} onClick={saveConfigSnapshot}>保存快照</button>
              <button className="btn btn-sm btn-outline" style={{ marginLeft: 8 }} onClick={restoreConfigSnapshot}>恢复快照</button>
            </div>
            <div style={{ marginTop: '14px', padding: '12px', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
              <div style={{ fontWeight: 600, marginBottom: '6px' }}>低分清理预览</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: '6px' }}>
                当前总数 {strategyPrunePreview.total}，池上限 {strategyPrunePreview.poolLimit}
                {strategyPrunePreview.over > 0 ? `，预计清理 ${strategyPrunePreview.over} 个低分策略` : '，当前无需清理'}
              </div>
              {strategyPrunePreview.candidates.map((c) => (
                <div key={c.id} style={{ fontSize: 12, padding: '2px 0' }}>
                  · {c.name}（score: {c.score.toFixed(3)}）
                </div>
              ))}
            </div>
          </div>
        </div>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">📊</span>策略分布与评分</div></div>
            <div className="panel-body">
              <div style={{ height: 180 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={strategyTypePie} dataKey="value" nameKey="name" outerRadius={70} label isAnimationActive={CHART_ANIMATION}>
                      {strategyTypePie.map((_, i) => <Cell key={i} fill={['#1890ff', '#52c41a', '#faad14', '#722ed1', '#eb2f96'][i % 5]} />)}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div style={{ height: 170 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={topStrategyBars}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="score" fill="#1890ff" isAnimationActive={CHART_ANIMATION} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'risk' && (
        <div>
        <div className="panel-row" style={{ marginTop: '16px' }}>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">🛡️</span>执行门控</div></div>
            <div className="panel-body">
              <div className="market-stats">
                <div className="market-stat-item" title="建议 >= 1.2，过低会放宽风险">
                  <div className="market-stat-label">Min RR</div>
                  <div className="market-stat-value" style={{ color: metricColor(guards?.config?.min_rr_to_trade, 1.2, 1.0, true) }}>{guards?.config?.min_rr_to_trade ?? '-'}</div>
                </div>
                <div className="market-stat-item" title="建议 <= 35bps，过高会放宽滑点风险">
                  <div className="market-stat-label">Max Spread</div>
                  <div className="market-stat-value" style={{ color: metricColor(guards?.config?.max_spread_bps_to_trade, 35, 45) }}>{guards?.config?.max_spread_bps_to_trade ?? '-'} bps</div>
                </div>
                <div className="market-stat-item" title="数据质量拦截次数，持续升高需检查数据源">
                  <div className="market-stat-label">数据质量拒绝</div>
                  <div className="market-stat-value" style={{ color: metricColor(guards?.stats?.data_quality_guard_hold, 5, 15) }}>{guards?.stats?.data_quality_guard_hold ?? 0}</div>
                </div>
                <div className="market-stat-item" title="SLTP动态微调次数，过高可能市场噪声偏大">
                  <div className="market-stat-label">动态SLTP</div>
                  <div className="market-stat-value" style={{ color: metricColor(sltpStats?.stats?.dynamic_adjustments, 20, 50) }}>{sltpStats?.stats?.dynamic_adjustments ?? 0}</div>
                </div>
              </div>
              <div style={{ marginTop: '10px', display: 'flex', gap: '8px' }}>
                <button className="btn btn-sm btn-outline" onClick={() => setGuardPreset('conservative')}>保守</button>
                <button className="btn btn-sm btn-outline" onClick={() => setGuardPreset('normal')}>标准</button>
                <button className="btn btn-sm btn-outline" onClick={() => setGuardPreset('aggressive')}>进取</button>
              </div>
              <div style={{ height: 180, marginTop: 8 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={guardTrend}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" />
                    <YAxis />
                    <Tooltip />
                    <Area type="monotone" dataKey="rr" stroke="#722ed1" fill="#722ed133" isAnimationActive={CHART_ANIMATION} />
                    <Area type="monotone" dataKey="spread" stroke="#faad14" fill="#faad1433" isAnimationActive={CHART_ANIMATION} />
                    <Area type="monotone" dataKey="dq" stroke="#ff4d4f" fill="#ff4d4f22" isAnimationActive={CHART_ANIMATION} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">🚨</span>风控与记忆</div></div>
            <div className="panel-body">
              <div className="market-stats">
                <div className="market-stat-item"><div className="market-stat-label">日内交易</div><div className="market-stat-value">{risk.daily_trades ?? 0}</div></div>
                <div className="market-stat-item"><div className="market-stat-label">连续亏损</div><div className="market-stat-value">{risk.consecutive_losses ?? 0}</div></div>
                <div className="market-stat-item"><div className="market-stat-label">短期记忆</div><div className="market-stat-value">{memoryStats.short_term_count ?? 0}</div></div>
                <div className="market-stat-item"><div className="market-stat-label">长期记忆</div><div className="market-stat-value">{memoryStats.long_term_count ?? 0}</div></div>
              </div>
              <div style={{ height: 180, marginTop: 8 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={sltpTrend}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="dynamic" fill="#1890ff" isAnimationActive={CHART_ANIMATION} />
                    <Bar dataKey="active" fill="#52c41a" isAnimationActive={CHART_ANIMATION} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
        <div className="panel" style={{ marginTop: '16px' }}>
          <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">⏱️</span>异常告警时间线</div></div>
          <div className="panel-body">
            {alertLines.length ? alertLines.map((l, i) => (
              <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid var(--border-light)' }}>⚠️ {l}</div>
            )) : <div style={{ color: 'var(--text-tertiary)' }}>暂无异常告警，系统运行稳定。</div>}
          </div>
        </div>
        </div>
      )}

      {activeTab === 'docs' && (
        <div className="panel-row" style={{ marginTop: '16px' }}>
          <div className="panel">
            <div className="panel-header"><div className="panel-title"><span className="panel-title-icon">📚</span>文档导航</div></div>
            <div className="panel-body">
              <input
                className="form-input"
                placeholder="搜索文档（标题/分组）"
                value={docQuery}
                onChange={(e) => setDocQuery(e.target.value)}
                style={{ marginBottom: 10 }}
              />
              <div style={{ maxHeight: 520, overflow: 'auto' }}>
                {filteredDocs.map((d) => (
                  <div
                    key={d.id}
                    onClick={() => setSelectedDocId(d.id)}
                    style={{
                      cursor: 'pointer',
                      padding: '8px 10px',
                      borderRadius: 8,
                      marginBottom: 6,
                      background: selectedDoc?.id === d.id ? 'var(--bg-secondary)' : 'transparent',
                      border: '1px solid var(--border-light)',
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>{d.title}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{d.group}</div>
                  </div>
                ))}
                {!filteredDocs.length && renderStateHint('没有匹配的文档')}
              </div>
            </div>
          </div>
          <div className="panel" style={{ gridColumn: 'span 2' }}>
            <div className="panel-header">
              <div className="panel-title"><span className="panel-title-icon">🧾</span>{selectedDoc?.title || '文档内容'}</div>
            </div>
            <div className="panel-body">
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 8 }}>
                分类：{selectedDoc?.group || '-'} · 文档数：{docsCatalog.length}
              </div>
              <div style={{ lineHeight: 1.6, fontSize: 13, maxHeight: 620, overflow: 'auto' }}>
                {docLoading && !selectedDocContent ? (
                  '文档加载中...'
                ) : (
                  <Suspense fallback={<div>渲染器加载中...</div>}>
                    <MarkdownRenderer>{selectedDocContent || '暂无文档内容'}</MarkdownRenderer>
                  </Suspense>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {notice && (
        <div style={{ position: 'fixed', top: '84px', right: '24px', padding: '10px 14px', borderRadius: '8px', color: '#fff', zIndex: 9999, background: notice.type === 'error' ? 'var(--error-color)' : 'var(--success-color)' }}>
          {notice.message}
        </div>
      )}
    </div>
    </ControlHubErrorBoundary>
  );
}

export default ControlHubModule;
