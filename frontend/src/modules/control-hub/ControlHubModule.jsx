import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { api } from '../../services/api';
import { toCnFieldKey, toCnRiskLevel, toCnSignal, toCnStrategy, translateReasoning } from '../../utils/cnFormatter';

const DOC_LOADERS = import.meta.glob(
  ['../../../docs/**/*.md', '../../../../docs/**/*.md'],
  { query: '?raw', import: 'default' },
);

function resolveDocLoader(docPath) {
  if (DOC_LOADERS[docPath]) return DOC_LOADERS[docPath];
  const alt = docPath.startsWith('../../../')
    ? docPath.replace('../../../', '../../../../')
    : docPath.replace('../../../../', '../../../');
  return DOC_LOADERS[alt] || null;
}

function ControlHubModule() {
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  const [health, setHealth] = useState(null);
  const [s1, setS1] = useState(null);
  const [guards, setGuards] = useState(null);
  const [sltpStats, setSltpStats] = useState(null);
  const [tradeHistory, setTradeHistory] = useState([]);
  const [monitorLogs, setMonitorLogs] = useState([]);
  const [marketData, setMarketData] = useState({});
  const [monitoringSummary, setMonitoringSummary] = useState(null);
  const [dataSymbol, setDataSymbol] = useState('BTC/USDT');
  const [dataModuleBusy, setDataModuleBusy] = useState(false);
  const [dataModuleStatus, setDataModuleStatus] = useState({
    symbols: [],
    ticker: null,
    trends: null,
    signals: null,
    fusion: null,
    lastUpdatedAt: null,
    source: 'idle',
  });
  const [dataHubSnapshot, setDataHubSnapshot] = useState(null);
  const [dataHubStatus, setDataHubStatus] = useState(null);
  const [qualityAdvice, setQualityAdvice] = useState(null);
  const [aiDataAnalysis, setAiDataAnalysis] = useState(null);
  const [proactiveStatus, setProactiveStatus] = useState(null);
  const [riskMetrics, setRiskMetrics] = useState(null);
  const [opportunities, setOpportunities] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [alertsHistory, setAlertsHistory] = useState([]);
  const [tradeStats, setTradeStats] = useState(null);
  const [tradeReview, setTradeReview] = useState(null);
  const [dailyMemorySummary, setDailyMemorySummary] = useState([]);
  const [commanderSnapshot, setCommanderSnapshot] = useState(null);
  const [commanderAudit, setCommanderAudit] = useState(null);
  const [commanderSnapshotMode, setCommanderSnapshotMode] = useState('fast');
  const [commanderInput, setCommanderInput] = useState('执行系统巡检');
  const [commanderReply, setCommanderReply] = useState('');

  const [strategies, setStrategies] = useState([]);
  const [strategyOpt, setStrategyOpt] = useState(null);
  const [researchBusy, setResearchBusy] = useState(false);
  const [researchLog, setResearchLog] = useState('');
  const [researchJobs, setResearchJobs] = useState([]);
  const [productionAudit, setProductionAudit] = useState(null);
  const [manualBusy, setManualBusy] = useState(false);
  const [feedbackForm, setFeedbackForm] = useState({
    strategy_id: 'default_trend_following_ma',
    pnl: -5,
    win_rate: 45,
    max_drawdown: 0.2,
    total_trades: 20,
    force_optimize: true,
  });

  const [docQuery, setDocQuery] = useState('');
  const [selectedDocId, setSelectedDocId] = useState('control-hub-user-manual');
  const [docContents, setDocContents] = useState({});
  const [docLoading, setDocLoading] = useState(false);

  const showNotice = (message, type = 'success') => {
    setNotice({ message, type });
    window.setTimeout(() => setNotice(null), 3200);
  };

  const docsCatalog = useMemo(
    () => [
      { id: 'control-hub-user-manual', title: '总控中心操作手册', group: '总控', path: '../../../docs/control-hub-user-manual.md' },
      { id: 'control-hub-module-checklist', title: '总控功能清单', group: '总控', path: '../../../docs/control-hub-module-checklist.md' },
      { id: 'dynamic-open-close', title: '动态开平仓与SLTP手册', group: '交易', path: '../../../docs/dynamic-open-close-and-sltp-playbook.md' },
      { id: 'maintenance-guide', title: '维护指南', group: '运维', path: '../../../docs/MAINTENANCE_GUIDE.md' },
      { id: 'api-doc', title: 'API 文档', group: '接口', path: '../../../docs/api.md' },
    ],
    []
  );

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

  const loadStrategyData = useCallback(async () => {
    try {
      const [list, optRes, jobsRes, auditRes, memSummaryRes, commanderRes, commanderAuditRes] = await Promise.all([
        api.strategies.getAll().catch(() => []),
        api.modules.getStrategyOptimizationStatus().catch(() => null),
        api.modules.getStrategyResearchJobs(20).catch(() => ({ jobs: [] })),
        api.modules.getExecutionProductionAudit().catch(() => null),
        api.modules.getMemoryDailySummary(6).catch(() => ({ data: [] })),
        api.modules.getCommanderSnapshotFast(dataSymbol || 'BTC/USDT').catch(() => null),
        api.modules.getCommanderAudit().catch(() => null),
      ]);
      setStrategies(Array.isArray(list) ? list : []);
      setStrategyOpt(optRes?.data ?? null);
      setResearchJobs(Array.isArray(jobsRes?.jobs) ? jobsRes.jobs : []);
      setProductionAudit(auditRes || null);
      setDailyMemorySummary(Array.isArray(memSummaryRes?.data) ? memSummaryRes.data : []);
      setCommanderSnapshot(commanderRes?.data || commanderRes || null);
      setCommanderSnapshotMode((commanderRes?.data || commanderRes || null)?.mode || 'fast');
      setCommanderAudit(commanderAuditRes || null);
    } catch (e) {
      showNotice(`策略数据加载失败：${e.message || e}`, 'error');
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadDoc = async () => {
      if (!selectedDoc?.id || !selectedDoc?.path) return;
      if (docContents[selectedDoc.id]) return;
      const loader = resolveDocLoader(selectedDoc.path);
      if (!loader) {
        if (!cancelled) {
          setDocContents((prev) => ({
            ...prev,
            [selectedDoc.id]: '文档加载失败：未找到文件映射（开发环境请确认 Vite 可访问上级 docs/；镜像构建需包含 docs）。',
          }));
        }
        return;
      }
      setDocLoading(true);
      try {
        const raw = await loader();
        if (!cancelled) setDocContents((prev) => ({ ...prev, [selectedDoc.id]: String(raw || '') }));
      } catch {
        if (!cancelled) setDocContents((prev) => ({ ...prev, [selectedDoc.id]: '文档加载失败：读取异常。' }));
      } finally {
        if (!cancelled) setDocLoading(false);
      }
    };
    loadDoc();
    return () => {
      cancelled = true;
    };
  }, [selectedDoc, docContents]);

  const refresh = async () => {
    setLoading(true);
    try {
      const center = await api.controlCenter.getState({ limit: 20 }).catch(() => null);
      if (center?.success) {
        setHealth(center.system?.health || null);
        setS1(center.ai?.s1 || null);
        setGuards(center.ai?.guards || null);
        setSltpStats(center.trading?.sltp_stats || null);
        setTradeHistory(Array.isArray(center.trading?.trade_history) ? center.trading.trade_history : []);
        setMonitorLogs(Array.isArray(center.observability?.logs) ? center.observability.logs : []);
        setMarketData(center.market?.market_data || {});
        setMonitoringSummary(center.market?.monitoring_summary || null);
        setProactiveStatus(center.ai?.proactive_status || null);
        setRiskMetrics(center.market?.risk || null);
        setOpportunities(Array.isArray(center.ai?.opportunities) ? center.ai.opportunities : []);
        setAnomalies(Array.isArray(center.observability?.anomalies) ? center.observability.anomalies : []);
        setAlertsHistory(Array.isArray(center.observability?.alerts_history) ? center.observability.alerts_history : []);
        setTradeStats(center.trading?.trade_statistics || null);
        setTradeReview(center.trading?.trade_review || null);
        const strategyList = Array.isArray(center.trading?.strategies) ? center.trading.strategies : [];
        setStrategies(strategyList);
        setStrategyOpt(center.trading?.strategy_optimization || null);
        return;
      }

      const [healthRes, s1Res, guardsRes, sltpRes, histRes, logsRes] = await Promise.all([
        api.request('/modules/system/health').catch(() => null),
        api.request('/s1/verify').catch(() => null),
        api.request('/modules/ai/guards').catch(() => null),
        api.request('/modules/stop-loss/stats').catch(() => null),
        api.trading.getHistory({ limit: 10 }).catch(() => []),
        api.monitoring?.getLogs ? api.monitoring.getLogs({ limit: 20 }).catch(() => []) : Promise.resolve([]),
      ]);
      setHealth(healthRes);
      setS1(s1Res);
      setGuards(guardsRes);
      setSltpStats(sltpRes);
      setTradeHistory(Array.isArray(histRes?.data) ? histRes.data : Array.isArray(histRes) ? histRes : []);
      setMonitorLogs(Array.isArray(logsRes?.data) ? logsRes.data : Array.isArray(logsRes) ? logsRes : []);
      setMarketData({});
      setMonitoringSummary(null);
      setProactiveStatus(null);
      setRiskMetrics(null);
      setOpportunities([]);
      setAnomalies([]);
      setAlertsHistory([]);
      setTradeStats(null);
      setTradeReview(null);
      await loadStrategyData();
    } finally {
      setLoading(false);
    }
  };

  const refreshDataModule = useCallback(async (symbol = dataSymbol) => {
    const targetSymbol = String(symbol || 'BTC/USDT');
    setDataModuleBusy(true);
    try {
      const [symbolsRes, tickerRes, trendsRes, signalsRes, fusionRes, hubStatusRes, hubSnapshotRes, adviceRes, aiRes] = await Promise.all([
        api.market.getSymbols().catch(() => []),
        api.market.getTicker(targetSymbol).catch(() => null),
        api.externalData.analyzeTrends(targetSymbol).catch(() => null),
        api.externalData.getSignals(targetSymbol).catch(() => null),
        api.dataFusion.analyzeMarket(targetSymbol).catch(() => null),
        api.dataHub.getStatus().catch(() => null),
        api.dataHub.getUnifiedSnapshot(targetSymbol).catch(() => null),
        api.dataHub.getQualityAdvice(targetSymbol).catch(() => null),
        api.dataHub.getAiAnalysis(targetSymbol).catch(() => null),
      ]);

      const symbols = Array.isArray(symbolsRes?.data)
        ? symbolsRes.data
        : Array.isArray(symbolsRes)
          ? symbolsRes
          : [];

      setDataModuleStatus({
        symbols,
        ticker: tickerRes?.data || tickerRes || null,
        trends: trendsRes?.data || trendsRes || null,
        signals: signalsRes?.data || signalsRes || null,
        fusion: fusionRes?.data || fusionRes || null,
        lastUpdatedAt: new Date().toISOString(),
        source: 'api-live',
      });
      setDataHubStatus(hubStatusRes?.data || hubStatusRes || null);
      setDataHubSnapshot(hubSnapshotRes?.data || hubSnapshotRes || null);
      setQualityAdvice(adviceRes?.data || adviceRes || null);
      setAiDataAnalysis(aiRes?.data || aiRes || null);
    } catch (e) {
      setDataModuleStatus((prev) => ({
        ...prev,
        lastUpdatedAt: new Date().toISOString(),
        source: 'api-fallback',
      }));
      showNotice(`数据模块刷新失败：${e.message || e}`, 'error');
    } finally {
      setDataModuleBusy(false);
    }
  }, [dataSymbol]);

  useEffect(() => {
    refresh();
    refreshDataModule('BTC/USDT');
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      refreshDataModule();
    }, 15000);
    return () => window.clearInterval(timer);
  }, [refreshDataModule]);

  const runResearch = async () => {
    setResearchBusy(true);
    setResearchLog('');
    try {
      const res = await api.modules.runStrategyResearch({
        timeout_seconds: 900,
        max_symbols: 6,
        lookback_days: 28,
        symbols: ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT'],
      });
      if (res.success) {
        showNotice(`策略研发任务已提交：${res.job_id || '-'}`);
        setResearchLog(JSON.stringify(res, null, 2));
        const jobId = res.job_id;
        if (jobId) {
          let tries = 0;
          while (tries < 30) {
            tries += 1;
            await new Promise((r) => setTimeout(r, 2000));
            const jobRes = await api.modules.getStrategyResearchJob(jobId).catch(() => null);
            const st = jobRes?.job?.status;
            if (st === 'completed' || st === 'failed') {
              setResearchLog(JSON.stringify(jobRes.job || jobRes, null, 2));
              break;
            }
          }
        }
        await loadStrategyData();
      } else {
        showNotice(res.message || '策略研发失败', 'error');
        setResearchLog(res.message || JSON.stringify(res, null, 2));
      }
    } catch (e) {
      showNotice(String(e.message || e), 'error');
      setResearchLog(String(e.message || e));
    } finally {
      setResearchBusy(false);
    }
  };

  const runOptimizeNow = async () => {
    setManualBusy(true);
    try {
      const res = await api.modules.triggerStrategyOptimizeNow();
      showNotice(res?.message || '已触发优化批次');
      await loadStrategyData();
    } catch (e) {
      showNotice(`触发优化失败：${e.message || e}`, 'error');
    } finally {
      setManualBusy(false);
    }
  };

  const submitTradeFeedback = async () => {
    setManualBusy(true);
    try {
      const payload = {
        ...feedbackForm,
        pnl: Number(feedbackForm.pnl),
        win_rate: Number(feedbackForm.win_rate),
        max_drawdown: Number(feedbackForm.max_drawdown),
        total_trades: Number(feedbackForm.total_trades),
      };
      const res = await api.modules.submitStrategyTradeFeedback(payload);
      showNotice(res?.data?.success ? '交易反馈已提交并触发优化链路' : '交易反馈已提交');
      await loadStrategyData();
    } catch (e) {
      showNotice(`提交交易反馈失败：${e.message || e}`, 'error');
    } finally {
      setManualBusy(false);
    }
  };

  const runDailySummaryNow = async () => {
    setManualBusy(true);
    try {
      const res = await api.modules.runMemoryDailySummary();
      showNotice(res?.message || '已触发每日复盘写入');
      await loadStrategyData();
    } catch (e) {
      showNotice(`触发每日复盘失败：${e.message || e}`, 'error');
    } finally {
      setManualBusy(false);
    }
  };

  const runCommanderChores = async (triggerOptimize = false) => {
    setManualBusy(true);
    try {
      const res = await api.modules.runCommanderChores({ symbol: dataSymbol || 'BTC/USDT', trigger_optimize: !!triggerOptimize });
      showNotice(res?.success ? '司令部日常任务执行完成' : (res?.message || '司令部任务失败'), res?.success ? 'success' : 'error');
      await loadStrategyData();
    } catch (e) {
      showNotice(`司令部任务失败：${e.message || e}`, 'error');
    } finally {
      setManualBusy(false);
    }
  };

  const sendCommanderMessage = async () => {
    const msg = String(commanderInput || '').trim();
    if (!msg) return;
    setManualBusy(true);
    try {
      const res = await api.modules.dispatchCommanderMessage(msg, 'control_hub');
      const out = res?.data?.response || res?.data?.message || JSON.stringify(res?.data || res || {});
      setCommanderReply(String(out || ''));
      showNotice('司令部已处理指令');
      await loadStrategyData();
    } catch (e) {
      showNotice(`司令部指令失败：${e.message || e}`, 'error');
    } finally {
      setManualBusy(false);
    }
  };

  const refreshCommanderSnapshotFull = async () => {
    setManualBusy(true);
    try {
      const res = await api.modules.getCommanderSnapshotFull(dataSymbol || 'BTC/USDT');
      setCommanderSnapshot(res?.data || res || null);
      setCommanderSnapshotMode((res?.data || res || null)?.mode || 'full');
      showNotice('已刷新司令部完整快照');
    } catch (e) {
      showNotice(`刷新完整快照失败：${e.message || e}`, 'error');
    } finally {
      setManualBusy(false);
    }
  };

  const alerts = useMemo(() => {
    const a = [];
    if (health?.overall && String(health.overall).toLowerCase() !== 'healthy') a.push(`系统健康异常: ${health.overall}`);
    if (s1 && s1.all_passed === false) a.push('S1 执行链路未通过');
    if ((guards?.stats?.data_quality_guard_hold || 0) > 10) a.push(`数据质量拦截偏高: ${guards.stats.data_quality_guard_hold}`);
    (monitorLogs || []).slice(0, 4).forEach((l) => {
      const msg = String(l?.message || '');
      if (msg) a.push(`日志: ${msg.slice(0, 120)}`);
    });
    return a.slice(0, 12);
  }, [health, s1, guards, monitorLogs]);

  const bestStrategy = useMemo(() => {
    if (!strategies || !strategies.length) return null;
    try {
      const sorted = [...strategies].sort(
        (a, b) => (b.sharpe_ratio || 0) - (a.sharpe_ratio || 0),
      );
      return sorted[0] || null;
    } catch {
      return null;
    }
  }, [strategies]);

  const marketRows = useMemo(() => {
    if (!marketData || typeof marketData !== 'object') return [];
    return Object.entries(marketData)
      .map(([symbol, data]) => ({ symbol, ...(data || {}) }))
      .sort((a, b) => Number(b.volume || 0) - Number(a.volume || 0))
      .slice(0, 12);
  }, [marketData]);

  return (
    <div style={{ padding: 16 }}>
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <span className="panel-title-icon">🎛️</span>智能总控中心
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="btn btn-sm btn-outline" onClick={refresh}>
              {loading ? '刷新中...' : '刷新'}
            </button>
          </div>
        </div>
        <div className="panel-body">
          <div className="tabs">
            {[
              { id: 'overview', label: '总览' },
              { id: 'market', label: '行情' },
              { id: 'ai', label: 'AI监督' },
              { id: 'risk', label: '风险与流程' },
              { id: 'command', label: '指挥' },
              { id: 'strategy', label: '策略研发' },
              { id: 'alerts', label: '告警' },
              { id: 'execution', label: '执行' },
              { id: 'docs', label: '文档' },
            ].map((t) => (
              <div
                key={t.id}
                className={`tab ${activeTab === t.id ? 'active' : ''}`}
                onClick={() => setActiveTab(t.id)}
                role="presentation"
              >
                {t.label}
              </div>
            ))}
          </div>
        </div>
      </div>

      {activeTab === 'overview' && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header">
            <div className="panel-title">系统状态</div>
          </div>
          <div className="panel-body">
            <div className="market-stats">
              <div className="market-stat-item">
                <div className="market-stat-label">健康</div>
                <div className="market-stat-value">{health?.overall || '-'}</div>
              </div>
              <div className="market-stat-item">
                <div className="market-stat-label">S1链路</div>
                <div className="market-stat-value">{s1?.all_passed ? '通过' : '待检查'}</div>
              </div>
              <div className="market-stat-item">
                <div className="market-stat-label">策略池</div>
                <div className="market-stat-value">
                  {strategyOpt?.total_strategies ?? strategies.length ?? '-'} / {strategyOpt?.pool_limit ?? '-'}
                </div>
              </div>
              <div className="market-stat-item">
                <div className="market-stat-label">首选策略</div>
                <div className="market-stat-value">
                  {bestStrategy ? (bestStrategy.name || bestStrategy.strategy_id || '-') : '-'}
                </div>
              </div>
              <div className="market-stat-item">
                <div className="market-stat-label">SLTP动态</div>
                <div className="market-stat-value">{sltpStats?.stats?.dynamic_adjustments ?? 0}</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'market' && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header">
            <div className="panel-title">市场行情总览</div>
          </div>
          <div className="panel-body">
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 10 }}>
              数据质量概览：{monitoringSummary?.status || 'unknown'} · 交易记录 {monitoringSummary?.total_trades ?? '-'} · 活跃告警{' '}
              {monitoringSummary?.active_alerts ?? '-'}
            </div>
            <div style={{ border: '1px solid var(--border-light)', borderRadius: 8, padding: 10, marginBottom: 10 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
                <div style={{ fontWeight: 600 }}>数据模块联动</div>
                <input
                  className="form-input"
                  value={dataSymbol}
                  onChange={(e) => setDataSymbol(e.target.value)}
                  style={{ maxWidth: 200 }}
                  placeholder="BTC/USDT"
                />
                <button type="button" className="btn btn-sm btn-outline" onClick={() => refreshDataModule(dataSymbol)} disabled={dataModuleBusy}>
                  {dataModuleBusy ? '拉取中…' : '刷新数据模块'}
                </button>
                <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                  源: {dataModuleStatus.source} · 更新时间: {dataModuleStatus.lastUpdatedAt || '-'}
                </span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                可用交易对 {dataModuleStatus.symbols?.length || 0} · 行情 {dataModuleStatus.ticker ? 'ok' : 'n/a'} · 趋势{' '}
                {dataModuleStatus.trends ? 'ok' : 'n/a'} · 信号 {dataModuleStatus.signals ? 'ok' : 'n/a'} · 融合分析{' '}
                {dataModuleStatus.fusion ? 'ok' : 'n/a'}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
                统一数据源中心：{dataHubStatus?.模块 || '统一数据源中心'} · 健康 {String(dataHubStatus?.健康 ?? '-') } · 提供者 {dataHubStatus?.提供者 || '-'}
              </div>
              <pre style={{ maxHeight: 180, overflow: 'auto', fontSize: 11, marginTop: 8, background: 'var(--bg-secondary)', padding: 8, borderRadius: 6, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(
                  {
                    symbol: dataSymbol,
                    ticker: dataModuleStatus.ticker,
                    trends: dataModuleStatus.trends,
                    signals: dataModuleStatus.signals,
                    fusion: dataModuleStatus.fusion,
                  },
                  null,
                  2
                )}
              </pre>
              {dataHubSnapshot ? (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>统一双渠道快照（中文）</div>
                  <pre style={{ maxHeight: 220, overflow: 'auto', fontSize: 11, marginTop: 6, background: 'var(--bg-secondary)', padding: 8, borderRadius: 6, whiteSpace: 'pre-wrap' }}>
                    {JSON.stringify(dataHubSnapshot, null, 2)}
                  </pre>
                </div>
              ) : null}
              {qualityAdvice ? (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>
                    数据质量与作用评分：{qualityAdvice.grade || '-'} · 置信度 {qualityAdvice.confidence ?? '-'}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
                    质量分 {qualityAdvice.quality_score ?? '-'} · 作用分 {qualityAdvice.effectiveness_score ?? '-'} · 稳定性{' '}
                    {qualityAdvice.stability_score ?? '-'}
                  </div>
                  <div style={{ marginTop: 4, fontSize: 12 }}>
                    建议：{Array.isArray(qualityAdvice.suggestions) ? qualityAdvice.suggestions.join('；') : '-'}
                  </div>
                </div>
              ) : null}
              {aiDataAnalysis ? (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>AI智能分析：{aiDataAnalysis.action_bias || '-'}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
                    趋势 {aiDataAnalysis.trend || '-'} · 情绪 {aiDataAnalysis.sentiment || '-'} · 风险 {aiDataAnalysis.risk_level || '-'} ·
                    置信度 {aiDataAnalysis.confidence ?? '-'}
                  </div>
                  <div style={{ marginTop: 4, fontSize: 12 }}>{aiDataAnalysis.summary || '-'}</div>
                </div>
              ) : null}
            </div>
            <div style={{ maxHeight: 360, overflow: 'auto', border: '1px solid var(--border-light)', borderRadius: 8 }}>
              {marketRows.map((m) => (
                <div key={m.symbol} style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-light)' }}>
                  <div style={{ fontWeight: 600 }}>{m.symbol}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                    价格 {m.last_price ?? '-'} · 24h波动 {m.volatility_24h ?? '-'} · 点差 {m.spread ?? '-'} · 流动性 {m.liquidity_score ?? '-'} ·
                    制度 {m.market_regime || '-'} · 异常分 {m.anomaly_score ?? '-'}
                  </div>
                </div>
              ))}
              {!marketRows.length && <div style={{ padding: 12, color: 'var(--text-tertiary)' }}>暂无市场数据（待采集或接口未接入）。</div>}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'ai' && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header">
            <div className="panel-title">AI工作监督</div>
          </div>
          <div className="panel-body">
            <div className="market-stats" style={{ marginBottom: 12 }}>
              <div className="market-stat-item">
                <div className="market-stat-label">执行模式</div>
                <div className="market-stat-value">{proactiveStatus?.mode || '-'}</div>
              </div>
              <div className="market-stat-item">
                <div className="market-stat-label">扫描级别</div>
                <div className="market-stat-value">{proactiveStatus?.scan_level || '-'}</div>
              </div>
              <div className="market-stat-item">
                <div className="market-stat-label">机会数</div>
                <div className="market-stat-value">{proactiveStatus?.opportunity_count ?? '-'}</div>
              </div>
              <div className="market-stat-item">
                <div className="market-stat-label">运行状态</div>
                <div className="market-stat-value">{proactiveStatus?.status || '-'}</div>
              </div>
            </div>
            <pre
              style={{
                maxHeight: 300,
                overflow: 'auto',
                fontSize: 11,
                padding: 10,
                background: 'var(--bg-secondary)',
                borderRadius: 8,
                whiteSpace: 'pre-wrap',
              }}
            >
              {JSON.stringify(proactiveStatus || {}, null, 2)}
            </pre>
            <div style={{ marginTop: 12, fontWeight: 600 }}>当前机会 ({opportunities.length})</div>
            <div style={{ maxHeight: 220, overflow: 'auto', border: '1px solid var(--border-light)', borderRadius: 8, marginTop: 8 }}>
              {opportunities.slice(0, 10).map((o, i) => (
                <div key={`${o.symbol}-${i}`} style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-light)' }}>
                  <div style={{ fontWeight: 600 }}>
                    {o.symbol || '-'} · {o.direction || '-'} · 置信度 {o.confidence ?? '-'}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{o.reasoning || '-'}</div>
                </div>
              ))}
              {!opportunities.length && <div style={{ padding: 10, color: 'var(--text-tertiary)' }}>暂无AI机会数据</div>}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'risk' && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header">
            <div className="panel-title">风险与流程监视</div>
          </div>
          <div className="panel-body">
            <div className="market-stats" style={{ marginBottom: 12 }}>
              <div className="market-stat-item">
                <div className="market-stat-label">组合净值</div>
                <div className="market-stat-value">{riskMetrics?.portfolio_value ?? '-'}</div>
              </div>
              <div className="market-stat-item">
                <div className="market-stat-label">总暴露</div>
                <div className="market-stat-value">{riskMetrics?.total_exposure ?? '-'}</div>
              </div>
              <div className="market-stat-item">
                <div className="market-stat-label">VaR95</div>
                <div className="market-stat-value">{riskMetrics?.var_95 ?? '-'}</div>
              </div>
              <div className="market-stat-item">
                <div className="market-stat-label">杠杆</div>
                <div className="market-stat-value">{riskMetrics?.leverage_used ?? '-'}</div>
              </div>
            </div>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>异常事件 ({anomalies.length})</div>
            <div style={{ maxHeight: 220, overflow: 'auto', border: '1px solid var(--border-light)', borderRadius: 8 }}>
              {anomalies.slice(0, 12).map((a, i) => (
                <div key={a.event_id || i} style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-light)' }}>
                  <div style={{ fontWeight: 600 }}>
                    {a.event_type || '-'} · 严重度 {a.severity || '-'} · 置信度 {a.confidence ?? '-'}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{a.message || '-'}</div>
                </div>
              ))}
              {!anomalies.length && <div style={{ padding: 10, color: 'var(--text-tertiary)' }}>暂无异常事件</div>}
            </div>
            <div style={{ marginTop: 12, fontWeight: 600 }}>告警历史 ({alertsHistory.length})</div>
            <div style={{ maxHeight: 180, overflow: 'auto', border: '1px solid var(--border-light)', borderRadius: 8, marginTop: 8 }}>
              {alertsHistory.slice(0, 12).map((a, i) => (
                <div key={a.alert_id || i} style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-light)' }}>
                  {a.severity || '-'} · {a.alert_type || '-'} · {a.message || '-'}
                </div>
              ))}
              {!alertsHistory.length && <div style={{ padding: 10, color: 'var(--text-tertiary)' }}>暂无告警历史</div>}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'command' && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header">
            <div className="panel-title">总调度指挥台</div>
          </div>
          <div className="panel-body">
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <button type="button" className="btn btn-sm btn-outline" onClick={refresh}>一键全量刷新</button>
              <button type="button" className="btn btn-sm btn-primary" disabled={researchBusy} onClick={runResearch}>
                {researchBusy ? '策略研发执行中…' : '一键触发策略研发'}
              </button>
              <button type="button" className="btn btn-sm btn-outline" disabled={manualBusy} onClick={() => runCommanderChores(false)}>
                执行司令部日常任务
              </button>
              <button type="button" className="btn btn-sm btn-outline" disabled={manualBusy} onClick={() => runCommanderChores(true)}>
                司令部任务并优化
              </button>
            </div>
            <div style={{ marginBottom: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                className="form-input"
                value={commanderInput}
                onChange={(e) => setCommanderInput(e.target.value)}
                style={{ minWidth: 300 }}
                placeholder="给司令部发送指令，如：执行系统巡检"
              />
              <button type="button" className="btn btn-sm btn-primary" disabled={manualBusy} onClick={sendCommanderMessage}>
                发送司令部指令
              </button>
            </div>
            {commanderReply ? (
              <pre style={{ maxHeight: 120, overflow: 'auto', fontSize: 11, padding: 10, background: 'var(--bg-secondary)', borderRadius: 8, whiteSpace: 'pre-wrap', marginTop: 6 }}>
                {commanderReply}
              </pre>
            ) : null}
            <div style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
              指挥台聚合了系统状态、AI监督、策略研发与执行观测。后续会继续扩展到模块级启动/停用、风控预案切换、任务编排等统一指令。
            </div>
            <div style={{ marginTop: 12, fontWeight: 600 }}>司令部对接审查</div>
            <pre style={{ maxHeight: 180, overflow: 'auto', fontSize: 11, padding: 10, background: 'var(--bg-secondary)', borderRadius: 8, whiteSpace: 'pre-wrap', marginTop: 8 }}>
              {JSON.stringify(commanderAudit || {}, null, 2)}
            </pre>
            <div style={{ marginTop: 12, fontWeight: 600 }}>司令部统一快照</div>
            <div style={{ marginTop: 6, marginBottom: 6, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>当前模式: {commanderSnapshotMode}</span>
              <button type="button" className="btn btn-sm btn-outline" disabled={manualBusy} onClick={refreshCommanderSnapshotFull}>
                拉取完整快照(full)
              </button>
            </div>
            <pre style={{ maxHeight: 220, overflow: 'auto', fontSize: 11, padding: 10, background: 'var(--bg-secondary)', borderRadius: 8, whiteSpace: 'pre-wrap', marginTop: 8 }}>
              {JSON.stringify(commanderSnapshot || {}, null, 2)}
            </pre>
            <div style={{ marginTop: 12, fontWeight: 600 }}>交易统计（30天）</div>
            <pre
              style={{
                maxHeight: 180,
                overflow: 'auto',
                fontSize: 11,
                padding: 10,
                background: 'var(--bg-secondary)',
                borderRadius: 8,
                whiteSpace: 'pre-wrap',
                marginTop: 8,
              }}
            >
              {JSON.stringify(tradeStats || {}, null, 2)}
            </pre>
            <div style={{ marginTop: 12, fontWeight: 600 }}>交易复盘摘要</div>
            <pre
              style={{
                maxHeight: 180,
                overflow: 'auto',
                fontSize: 11,
                padding: 10,
                background: 'var(--bg-secondary)',
                borderRadius: 8,
                whiteSpace: 'pre-wrap',
                marginTop: 8,
              }}
            >
              {JSON.stringify(tradeReview || {}, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {activeTab === 'strategy' && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header">
            <div className="panel-title">策略池与研发</div>
          </div>
          <div className="panel-body">
            <div style={{ marginBottom: 16, display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
              <button type="button" className="btn btn-sm btn-primary" disabled={researchBusy} onClick={runResearch}>
                {researchBusy ? '研发执行中（可能数分钟）…' : '手动触发策略研发'}
              </button>
              <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
                走完整 walk-forward 与门控，不受「有持仓」限制；默认最多 6 个交易对、约 15 分钟超时。
              </span>
            </div>
            {strategyOpt?.daily_optimization && (
              <div style={{ fontSize: 13, marginBottom: 12, color: 'var(--text-secondary)' }}>
                每日批量优化：{strategyOpt.daily_optimization.completed ? '已完成' : '进行中'} · 处理{' '}
                {strategyOpt.daily_optimization.processed}/{strategyOpt.daily_optimization.total}
              </div>
            )}
            {strategyOpt?.deployment_stage_counts && (
              <div style={{ fontSize: 13, marginBottom: 12, color: 'var(--text-secondary)' }}>
                分层发布：paper {strategyOpt.deployment_stage_counts.paper || 0} · shadow {strategyOpt.deployment_stage_counts.shadow || 0} ·
                small {strategyOpt.deployment_stage_counts.small || 0} · full {strategyOpt.deployment_stage_counts.full || 0}
              </div>
            )}
            <div style={{ marginBottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button type="button" className="btn btn-sm btn-outline" onClick={runOptimizeNow} disabled={manualBusy}>
                {manualBusy ? '执行中…' : '手动触发每日优化批次'}
              </button>
              <button type="button" className="btn btn-sm btn-outline" onClick={runDailySummaryNow} disabled={manualBusy}>
                {manualBusy ? '执行中…' : '立即执行每日复盘'}
              </button>
              <button type="button" className="btn btn-sm btn-outline" onClick={loadStrategyData} disabled={manualBusy}>
                刷新研究任务与生产审计
              </button>
            </div>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>每日复盘记忆（AI总结）</div>
              <div style={{ maxHeight: 160, overflow: 'auto', border: '1px solid var(--border-light)', borderRadius: 8 }}>
                {(dailyMemorySummary || []).slice(0, 6).map((m) => (
                  <div key={m.id || Math.random()} style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-light)', fontSize: 12 }}>
                    {String(m.content || '').slice(0, 220)}
                  </div>
                ))}
                {!dailyMemorySummary?.length && <div style={{ padding: 10, color: 'var(--text-tertiary)' }}>暂无每日复盘记录</div>}
              </div>
            </div>

            <div style={{ marginBottom: 12, border: '1px solid var(--border-light)', borderRadius: 8, padding: 10 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>手动交易反馈（触发自适应优化）</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(120px,1fr))', gap: 8 }}>
                <input className="form-input" value={feedbackForm.strategy_id} onChange={(e) => setFeedbackForm((p) => ({ ...p, strategy_id: e.target.value }))} placeholder="strategy_id" />
                <input className="form-input" type="number" value={feedbackForm.pnl} onChange={(e) => setFeedbackForm((p) => ({ ...p, pnl: e.target.value }))} placeholder="pnl" />
                <input className="form-input" type="number" value={feedbackForm.win_rate} onChange={(e) => setFeedbackForm((p) => ({ ...p, win_rate: e.target.value }))} placeholder="win_rate(%)" />
                <input className="form-input" type="number" step="0.01" value={feedbackForm.max_drawdown} onChange={(e) => setFeedbackForm((p) => ({ ...p, max_drawdown: e.target.value }))} placeholder="max_drawdown" />
                <input className="form-input" type="number" value={feedbackForm.total_trades} onChange={(e) => setFeedbackForm((p) => ({ ...p, total_trades: e.target.value }))} placeholder="total_trades" />
                <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <input type="checkbox" checked={!!feedbackForm.force_optimize} onChange={(e) => setFeedbackForm((p) => ({ ...p, force_optimize: e.target.checked }))} />
                  force_optimize
                </label>
              </div>
              <div style={{ marginTop: 8 }}>
                <button type="button" className="btn btn-sm btn-primary" onClick={submitTradeFeedback} disabled={manualBusy}>
                  提交交易反馈
                </button>
              </div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>研究任务队列（最近）</div>
              <div style={{ maxHeight: 180, overflow: 'auto', border: '1px solid var(--border-light)', borderRadius: 8 }}>
                {(researchJobs || []).slice(0, 10).map((j) => (
                  <div key={j.job_id} style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-light)', fontSize: 12 }}>
                    {j.job_id} · {j.status} · {j.created_at}
                  </div>
                ))}
                {!researchJobs?.length && <div style={{ padding: 10, color: 'var(--text-tertiary)' }}>暂无研究任务记录</div>}
              </div>
            </div>

            {productionAudit ? (
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>生产执行审计</div>
                <pre style={{ maxHeight: 220, overflow: 'auto', fontSize: 11, padding: 10, background: 'var(--bg-secondary)', borderRadius: 8, whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(productionAudit, null, 2)}
                </pre>
              </div>
            ) : null}
            <div style={{ fontWeight: 600, marginBottom: 8 }}>当前策略 ({strategies.length})</div>
            <div style={{ maxHeight: 280, overflow: 'auto', border: '1px solid var(--border-light)', borderRadius: 8 }}>
              {(strategies || []).map((s) => (
                <div
                  key={s.id || s.strategy_id}
                  style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-light)' }}
                >
                  <div style={{ fontWeight: 600 }}>
                    {s.name || s.strategy_id}{' '}
                    <span style={{ fontWeight: 400, fontSize: 12, color: 'var(--text-tertiary)' }}>
                      ({s.strategy_type || '-'}) · {s.status === 'active' || s.enabled ? '启用' : '停用'}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                    交易 {s.total_trades ?? '-'} · 胜率 {s.win_rate != null ? `${s.win_rate}%` : '-'} · 夏普 {s.sharpe_ratio ?? '-'}{' '}
                    · 回撤% {s.max_drawdown ?? '-'}
                  </div>
                </div>
              ))}
              {!strategies?.length && (
                <div style={{ padding: 16, color: 'var(--text-tertiary)' }}>暂无策略或接口未连通（请确认页面与 API 同源或已反向代理 /api）。</div>
              )}
            </div>
            {researchLog ? (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>上次研发输出</div>
                <pre
                  style={{
                    maxHeight: 220,
                    overflow: 'auto',
                    fontSize: 11,
                    padding: 10,
                    background: 'var(--bg-secondary)',
                    borderRadius: 8,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {researchLog}
                </pre>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {activeTab === 'alerts' && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header">
            <div className="panel-title">告警（中文化）</div>
          </div>
          <div className="panel-body">
            {alerts.length ? (
              alerts.map((x, i) => (
                <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid var(--border-light)' }}>
                  ⚠️ {x}
                </div>
              ))
            ) : (
              <div style={{ color: 'var(--text-tertiary)' }}>暂无告警</div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'execution' && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header">
            <div className="panel-title">最近执行（中文化）</div>
          </div>
          <div className="panel-body">
            {(tradeHistory || []).slice(0, 10).map((t, i) => (
              <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid var(--border-light)' }}>
                <div style={{ fontWeight: 600 }}>
                  {t.symbol || '-'} · {toCnSignal(t.side)} · {t.price ?? '-'} · {t.quantity ?? '-'}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                  {toCnFieldKey('reasoning')}: {translateReasoning(t.reasoning || t.reason || '')} · {toCnFieldKey('strategy')}:{' '}
                  {toCnStrategy(t.strategy || t.strategy_name)} · {toCnFieldKey('risk_level')}: {toCnRiskLevel(t.risk_level)}
                </div>
              </div>
            ))}
            {!tradeHistory?.length && <div style={{ color: 'var(--text-tertiary)' }}>暂无交易历史</div>}
          </div>
        </div>
      )}

      {activeTab === 'docs' && (
        <div className="panel-row" style={{ marginTop: 16 }}>
          <div className="panel">
            <div className="panel-header">
              <div className="panel-title">文档导航</div>
            </div>
            <div className="panel-body">
              <input
                className="form-input"
                placeholder="搜索文档"
                value={docQuery}
                onChange={(e) => setDocQuery(e.target.value)}
                style={{ marginBottom: 10 }}
              />
              {filteredDocs.map((d) => (
                <div
                  key={d.id}
                  onClick={() => setSelectedDocId(d.id)}
                  style={{
                    cursor: 'pointer',
                    padding: '8px 10px',
                    borderRadius: 8,
                    marginBottom: 6,
                    border: '1px solid var(--border-light)',
                    background: selectedDoc?.id === d.id ? 'var(--bg-secondary)' : 'transparent',
                  }}
                  role="presentation"
                >
                  <div style={{ fontWeight: 600 }}>{d.title}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{d.group}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="panel" style={{ gridColumn: 'span 2' }}>
            <div className="panel-header">
              <div className="panel-title">{selectedDoc?.title}</div>
            </div>
            <div className="panel-body">
              {docLoading && !selectedDocContent ? (
                <div style={{ color: 'var(--text-tertiary)' }}>文档加载中...</div>
              ) : (
                <div style={{ maxHeight: 620, overflow: 'auto' }}>
                  <ReactMarkdown>{selectedDocContent || '暂无文档内容'}</ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {notice && (
        <div
          style={{
            position: 'fixed',
            top: '84px',
            right: '24px',
            padding: '10px 14px',
            borderRadius: '8px',
            color: '#fff',
            zIndex: 9999,
            background: notice.type === 'error' ? 'var(--error-color)' : 'var(--success-color)',
          }}
        >
          {notice.message}
        </div>
      )}
    </div>
  );
}

export default ControlHubModule;
