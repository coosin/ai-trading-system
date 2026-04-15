import React from 'react';
import { ActionList, DataTable, InsightCard, MetricGrid, StatusBadge } from '../components/UiBlocks';

function statusText(ok) {
  return ok ? '正常' : '异常';
}

function viewAutoGuard(view) {
  const g = view?.autoHostingGuard || {};
  return {
    enabled: Boolean(g.enabled),
    shouldDowngrade: Boolean(g.shouldDowngrade),
    reasons: Array.isArray(g.reasons) ? g.reasons : [],
    lastAction: g.lastAction || null,
  };
}

export default function OverviewSection({ state, view, flowRows, updatedAt, actions, loading }) {
  const missingRows = flowRows.filter((r) => !r.ok);
  const hosting = state.hostingMode?.data || {};
  const currentMode = hosting.mode || state.commanderSnapshot?.system?.hosting_mode || 'full_auto';
  const currentModeZh = hosting.mode_zh || (currentMode === 'semi_auto' ? '半自动' : '全自动');
  const hostingDesc =
    hosting.description ||
    (currentMode === 'semi_auto'
      ? '半自动托管：策略开仓需人工确认，平仓风控仍自动执行'
      : '全自动托管：AI自主开平仓并自动执行风控');
  const autoGuard = viewAutoGuard(view);
  const automationProfile = state.automationProfile?.data?.profile || state.systemStatus?.automation_profile || 'semi_auto';
  const red = state.riskRedlines?.data || state.systemStatus?.risk_redlines || {};
  const [redlineDraft, setRedlineDraft] = React.useState({
    max_positions: Number(red.max_positions || 5),
    single_order_max_ratio: Number(red.single_order_max_ratio || 0.05),
    max_total_exposure_ratio: Number(red.max_total_exposure_ratio || 0.8),
    min_open_cooldown_sec: Number(red.min_open_cooldown_sec || 5),
    max_drawdown_ratio: Number(red.max_drawdown_ratio || 0.15),
  });
  React.useEffect(() => {
    setRedlineDraft({
      max_positions: Number(red.max_positions || 5),
      single_order_max_ratio: Number(red.single_order_max_ratio || 0.05),
      max_total_exposure_ratio: Number(red.max_total_exposure_ratio || 0.8),
      min_open_cooldown_sec: Number(red.min_open_cooldown_sec || 5),
      max_drawdown_ratio: Number(red.max_drawdown_ratio || 0.15),
    });
  }, [red.max_drawdown_ratio, red.max_positions, red.max_total_exposure_ratio, red.min_open_cooldown_sec, red.single_order_max_ratio]);
  const controlRows = [
    {
      id: 'c1',
      label: '数据输入层',
      value: state.ticker && state.orderbook ? '正常' : '缺失',
      note: state.ticker ? `最新价 ${state.ticker.last || state.ticker.price || '-'}` : '无实时行情',
    },
    {
      id: 'c2',
      label: '分析决策层',
      value: state.aiAnalysis || state.fusion ? '正常' : '缺失',
      note: state.aiAnalysis?.signal || state.marketSymbolView?.trend || '无明确信号',
    },
    {
      id: 'c3',
      label: '执行控制层',
      value: state.executionSpine ? '正常' : '缺失',
      note: state.executionSpine?.status || state.executionSpine?.state || '执行状态未知',
    },
    {
      id: 'c4',
      label: '风险与SLTP层',
      value: state.stopLossStats || state.riskStatus ? '正常' : '缺失',
      note: state.riskStatus?.status || state.riskMonitor?.risk_level || '无风险状态',
    },
    {
      id: 'c5',
      label: '账户回执层',
      value: !state.accountDiagnostics?.degraded ? '正常' : '降级',
      note: !state.accountDiagnostics?.degraded ? '持仓钱包同步可用' : '账户同步链路降级',
    },
  ];
  const metrics = [
    { label: '系统健康', value: state.health?.overall || state.health?.status || '-' },
    { label: '交易所连接', value: state.exchanges?.[0]?.status || '-' },
    { label: '实时价格', value: state.ticker?.last || state.ticker?.price || '-' },
    { label: '账户同步', value: statusText(!state.accountDiagnostics?.degraded) },
    { label: '活跃告警', value: state.monitoringSummary?.active_alerts ?? 0 },
    { label: '模块数', value: state.systemStatus?.module_count ?? '-' },
    { label: '托管模式', value: currentModeZh },
  ];
  const watchRows = (state.watchTickers || []).map((row, idx) => {
    const t = row.ticker || {};
    return {
      id: idx,
      symbol: row.symbol,
      last: t.last || t.price || '-',
      bid: t.bid || '-',
      ask: t.ask || '-',
    };
  });

  return (
    <div className="panel section-panel" style={{ marginTop: 16 }}>
      <div className="panel-header">
        <div className="panel-title">系统全链路总览</div>
      </div>
      <div className="panel-body">
        <MetricGrid items={metrics} />
        <div className={`hosting-card ${currentMode === 'semi_auto' ? 'semi' : 'full'}`}>
          <div className="hosting-title">托管模式（傻瓜化一键切换）</div>
          <div className="hosting-current">
            当前模式：<strong>{currentModeZh}</strong>
          </div>
          <div className="hosting-desc">{hostingDesc}</div>
          <div className="hosting-actions">
            <button
              type="button"
              className={`btn btn-sm ${currentMode === 'full_auto' ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => actions?.switchHostingMode?.('全自动')}
              disabled={loading?.slow}
            >
              切到全自动（推荐）
            </button>
            <button
              type="button"
              className={`btn btn-sm ${currentMode === 'semi_auto' ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => actions?.switchHostingMode?.('半自动')}
              disabled={loading?.slow}
            >
              切到半自动（更稳）
            </button>
          </div>
          <div className="hosting-guard-row">
            <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>自动化级别：</span>
            <button type="button" className={`btn btn-sm ${automationProfile === 'conservative' ? 'btn-primary' : 'btn-outline'}`} onClick={() => actions?.setAutomationProfile?.('conservative')}>
              保守
            </button>
            <button type="button" className={`btn btn-sm ${automationProfile === 'semi_auto' ? 'btn-primary' : 'btn-outline'}`} onClick={() => actions?.setAutomationProfile?.('semi_auto')}>
              半自动
            </button>
            <button type="button" className={`btn btn-sm ${automationProfile === 'full_auto' ? 'btn-primary' : 'btn-outline'}`} onClick={() => actions?.setAutomationProfile?.('full_auto')}>
              全自动
            </button>
            <button type="button" className="btn btn-sm btn-outline" onClick={() => actions?.runUpgradePipeline?.()}>
              一键回归校验
            </button>
          </div>
          <div className="hosting-guard-row">
            <label className="confirm-toggle">
              <input
                type="checkbox"
                checked={Boolean(autoGuard.enabled)}
                onChange={(e) => actions?.toggleAutoHostingGuard?.(e.target.checked)}
              />
              自动安全降级（异常时自动切半自动）
            </label>
          </div>
          <div className="hosting-guard-row" style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(120px, 1fr))', gap: 8 }}>
            <input className="form-input" type="number" value={redlineDraft.max_positions} onChange={(e) => setRedlineDraft((p) => ({ ...p, max_positions: Number(e.target.value) }))} placeholder="最大持仓数" />
            <input className="form-input" type="number" step="0.01" value={redlineDraft.single_order_max_ratio} onChange={(e) => setRedlineDraft((p) => ({ ...p, single_order_max_ratio: Number(e.target.value) }))} placeholder="单笔上限比例" />
            <input className="form-input" type="number" step="0.01" value={redlineDraft.max_total_exposure_ratio} onChange={(e) => setRedlineDraft((p) => ({ ...p, max_total_exposure_ratio: Number(e.target.value) }))} placeholder="总暴露上限" />
            <input className="form-input" type="number" value={redlineDraft.min_open_cooldown_sec} onChange={(e) => setRedlineDraft((p) => ({ ...p, min_open_cooldown_sec: Number(e.target.value) }))} placeholder="开仓冷却秒" />
            <input className="form-input" type="number" step="0.01" value={redlineDraft.max_drawdown_ratio} onChange={(e) => setRedlineDraft((p) => ({ ...p, max_drawdown_ratio: Number(e.target.value) }))} placeholder="最大回撤比例" />
          </div>
          <div className="hosting-guard-row">
            <button
              type="button"
              className="btn btn-sm btn-primary"
              onClick={() => actions?.updateRiskRedlines?.(redlineDraft)}
              disabled={loading?.slow}
            >
              应用统一风控红线
            </button>
          </div>
          {autoGuard.enabled && autoGuard.shouldDowngrade && currentMode === 'full_auto' && (
            <div className="hosting-tips">检测到异常：{autoGuard.reasons.join('；')}。系统将自动切到半自动。</div>
          )}
          {autoGuard.lastAction?.reason && (
            <div className="hosting-tips">最近自动动作：{autoGuard.lastAction.reason}</div>
          )}
          <div className="hosting-tips">
            提示：行情剧烈波动时建议先切“半自动”；链路稳定后再切回“全自动”。
          </div>
        </div>
        <InsightCard
          title="当前系统结论"
          content={`系统健康：${state.health?.overall || state.health?.status || '-'}；账户同步：${statusText(!state.accountDiagnostics?.degraded)}；活跃告警：${state.monitoringSummary?.active_alerts ?? 0}。`}
          tone="info"
        />
        <ActionList
          items={[
            '先看“端到端链路状态”，有异常项先处理异常',
            '账户同步异常时，先去交易页执行“手动账户同步”',
            '风险告警不为 0 时，先降低交易频率',
          ]}
        />
        <div className="sub-title">总控中心五层态势</div>
        <div className="table-wrap">
          <table className="pro-table">
            <thead>
              <tr>
                <th>层级</th>
                <th>状态</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              {controlRows.map((r) => (
                <tr key={r.id}>
                  <td>{r.label}</td>
                  <td>{r.value}</td>
                  <td>{r.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {missingRows.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <InsightCard
              title="当前阻塞项"
              content={missingRows.map((r) => `${r.label}: ${r.detail}`).join('；')}
              tone="warn"
            />
          </div>
        )}

        <div className="sub-title" style={{ marginTop: 12 }}>全市场多交易对监控（观察列表）</div>
        <DataTable
          columns={[
            { key: 'symbol', title: '交易对' },
            { key: 'last', title: '最新价' },
            { key: 'bid', title: '买一' },
            { key: 'ask', title: '卖一' },
          ]}
          rows={watchRows}
          emptyText="暂无观察列表行情数据"
        />

        <div style={{ marginTop: 14, fontWeight: 700 }}>端到端链路状态</div>
        <div className="flow-list" style={{ marginTop: 8 }}>
          {flowRows.map((row) => (
            <div key={row.id} className="flow-item">
              <div style={{ fontWeight: 700, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>{row.label}</span>
                <StatusBadge ok={row.ok} text={row.ok ? '在线' : '异常'} />
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{row.detail}</div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-tertiary)' }}>
          刷新时间: 快速 {updatedAt.fast || '-'} · 中速 {updatedAt.medium || '-'} · 慢速 {updatedAt.slow || '-'}
        </div>
      </div>
    </div>
  );
}
