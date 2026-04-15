import React from 'react';
import OverviewSection from './sections/OverviewSection';
import DataAnalysisSection from './sections/DataAnalysisSection';
import TradingSection from './sections/TradingSection';
import RiskOpsSection from './sections/RiskOpsSection';
import AiStrategySection from './sections/AiStrategySection';
import CommandDocsSection from './sections/CommandDocsSection';
import { useControlHubData } from './state/useControlHubData';

const TABS = [
  { id: 'overview', label: '总览' },
  { id: 'analysis', label: '数据分析' },
  { id: 'trading', label: '交易执行' },
  { id: 'risk', label: '风控告警' },
  { id: 'ai', label: 'AI与策略' },
  { id: 'ops', label: '指挥与文档' },
];

export default function UnifiedControlHubModule() {
  const {
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
    view,
    flowRows,
    commandInput,
    setCommandInput,
    commandReply,
    simulatePayload,
    setSimulatePayload,
    actions,
  } = useControlHubData();
  const flowOk = flowRows.filter((x) => x.ok).length;
  const flowTotal = flowRows.length;
  const flowPercent = flowTotal ? Math.round((flowOk / flowTotal) * 100) : 0;
  const hasErrors = Boolean(errors.fast || errors.medium || errors.slow);
  const apiConnected = state.apiSmoke?.length
    ? `${state.apiSmoke.filter((x) => x.status === 'PASS').length}/${state.apiSmoke.length}`
    : '-';

  return (
    <div className="workspace-shell">
      <aside className="workspace-side panel">
        <div className="panel-header">
          <div className="panel-title">
            <span className="panel-title-icon">🧭</span>总控导航
          </div>
        </div>
        <div className="panel-body">
          <div className="side-health">
            <div className="side-health-title">链路完整度</div>
            <div className="side-health-value">{flowPercent}%</div>
            <div className="side-health-hint">
              通过 {flowOk}/{flowTotal} · API联调 {apiConnected}
            </div>
          </div>
          <div className="tabs">
            {TABS.map((t) => (
              <div key={t.id} className={`tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)} role="presentation">
                {t.label}
              </div>
            ))}
          </div>
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 800, marginBottom: 6 }}>市场观察列表（多交易对）</div>
            <input
              className="form-input"
              value={(watchSymbols || []).join(',')}
              onChange={(e) =>
                setWatchSymbols(
                  String(e.target.value || '')
                    .split(',')
                    .map((x) => x.trim())
                    .filter(Boolean)
                    .slice(0, 10),
                )
              }
              placeholder="用逗号分隔，例如 BTC/USDT,ETH/USDT,SOL/USDT"
            />
            <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-tertiary)' }}>
              说明：观察列表用于多交易对监控；深度分析/交易执行仍以顶部当前 symbol 为准。
            </div>
          </div>
          <div className={`side-alert ${hasErrors ? 'bad' : 'ok'}`}>
            {hasErrors ? '当前存在链路异常，请优先查看指挥与文档页诊断。' : '当前链路状态良好，可进行正常操作。'}
          </div>
        </div>
      </aside>

      <main className="workspace-main">
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">🎛️</span>统一运营控制台（实时）
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input className="form-input" value={symbol} onChange={(e) => setSymbol(e.target.value)} style={{ width: 180 }} />
              <button type="button" className="btn btn-sm btn-outline" onClick={actions.refreshAll} disabled={loading.full}>
                {loading.full ? '刷新中...' : '全量刷新'}
              </button>
            </div>
          </div>
          <div className="panel-body">
            <div className="top-status-grid">
              <div className="top-status-card">
                <div className="top-status-label">系统健康</div>
                <div className="top-status-value">{state.health?.overall || state.health?.status || '-'}</div>
              </div>
              <div className="top-status-card">
                <div className="top-status-label">数据连通</div>
                <div className="top-status-value">{flowOk}/{flowTotal}</div>
              </div>
              <div className="top-status-card">
                <div className="top-status-label">错误状态</div>
                <div className="top-status-value">{hasErrors ? '存在异常' : '正常'}</div>
              </div>
              <div className="top-status-card">
                <div className="top-status-label">最近刷新</div>
                <div className="top-status-value">{updatedAt.full || updatedAt.fast || '-'}</div>
              </div>
            </div>
          </div>
        </div>

        {tab === 'overview' && <OverviewSection state={state} view={view} flowRows={flowRows} updatedAt={updatedAt} actions={actions} loading={loading} />}
      {tab === 'analysis' && <DataAnalysisSection state={state} view={view} updatedAt={updatedAt} actions={actions} loading={loading} />}
        {tab === 'trading' && (
          <TradingSection
            state={state}
            view={view}
          updatedAt={updatedAt}
            simulatePayload={simulatePayload}
            setSimulatePayload={setSimulatePayload}
            actions={actions}
            loading={loading}
          />
        )}
        {tab === 'risk' && <RiskOpsSection state={state} />}
        {tab === 'ai' && <AiStrategySection state={state} />}
        {tab === 'ops' && (
          <CommandDocsSection
            commandInput={commandInput}
            setCommandInput={setCommandInput}
            commandReply={commandReply}
            actions={actions}
            state={state}
            errors={errors}
          />
        )}
      </main>

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
