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

const SEVERITY_LABEL = { block: '阻断', reduce: '降风险', warn: '告警' };

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
  const commanderSnapshot = state.commanderSnapshot?.data || state.commanderSnapshot || {};
  const executionAttribution =
    commanderSnapshot.execution_attribution ||
    commanderSnapshot.data?.execution_attribution ||
    {};
  const executionSummary = String(executionAttribution.summary || '').trim();
  const executionTop = (Array.isArray(executionAttribution.top_reasons) ? executionAttribution.top_reasons : [])
    .slice(0, 3)
    .map((x) => {
      const sev = String(x?.severity || 'warn').toLowerCase();
      return `${SEVERITY_LABEL[sev] || '告警'} · ${String(x?.key || '-')}（${Number(x?.count || 0)}）`;
    });
  const automationProfile = state.automationProfile?.data?.profile || state.systemStatus?.automation_profile || 'semi_auto';
  const tradingWorkflow = state.tradingWorkflow?.data || state.tradingWorkflow || {};
  const humanizedWorkflow = tradingWorkflow.humanized || {};
  const systemMastery = state.systemMastery?.data || state.systemMastery || {};
  const humanizedMastery = systemMastery.humanized || {};
  const closedLoopSummary = state.closedLoopSummary?.data || state.closedLoopSummary || {};
  const humanizedClosedLoop = closedLoopSummary.humanized || {};
  const profit = state.profitAnalytics?.data || state.profitAnalytics || {};
  const overall = profit?.overall || {};
  const byStrategy = Array.isArray(profit?.by_strategy_top) ? profit.by_strategy_top : [];
  const byRegime = Array.isArray(profit?.by_regime_top) ? profit.by_regime_top : [];
  const byHour = Array.isArray(profit?.by_hour_top) ? profit.by_hour_top : [];
  const profitRecommendations = Array.isArray(profit?.recommendations) ? profit.recommendations : [];
  const pnlText =
    overall && typeof overall === 'object' && Object.keys(overall).length
      ? `30天真实PnL：${overall.total_pnl ?? '-'}；手续费：${overall.total_fees ?? '-'}；胜率：${overall.win_rate != null ? `${(Number(overall.win_rate) * 100).toFixed(2)}%` : '-'}；PF：${overall.profit_factor ?? '-'}；最大回撤(PnL)：${overall.max_drawdown_pnl ?? '-'}。`
      : '暂无盈利分析数据（可能还没有真实PnL样本，或被 accurate_only 过滤）。';
  const topStr = byStrategy.slice(0, 3).map((x) => `${x.key || 'unknown'}:${x.total_pnl}`).join('；');
  const topReg = byRegime.slice(0, 3).map((x) => `${x.key || 'unknown'}:${x.total_pnl}`).join('；');
  const strategyRows = byStrategy.slice(0, 8).map((x, idx) => ({
    id: `s-${idx}`,
    key: x?.key || 'unknown',
    trades: Number(x?.trades || 0),
    win_rate: x?.win_rate != null ? `${(Number(x.win_rate) * 100).toFixed(2)}%` : '-',
    total_pnl: x?.total_pnl ?? '-',
    expectancy: x?.expectancy ?? '-',
  }));
  const regimeRows = byRegime.slice(0, 8).map((x, idx) => ({
    id: `r-${idx}`,
    key: x?.key || 'unknown',
    trades: Number(x?.trades || 0),
    win_rate: x?.win_rate != null ? `${(Number(x.win_rate) * 100).toFixed(2)}%` : '-',
    total_pnl: x?.total_pnl ?? '-',
    expectancy: x?.expectancy ?? '-',
  }));
  const hourRows = byHour.slice(0, 8).map((x, idx) => ({
    id: `h-${idx}`,
    key: x?.key || 'unknown',
    trades: Number(x?.trades || 0),
    win_rate: x?.win_rate != null ? `${(Number(x.win_rate) * 100).toFixed(2)}%` : '-',
    total_pnl: x?.total_pnl ?? '-',
    expectancy: x?.expectancy ?? '-',
  }));
  const runtimePatch = { regime_policy_matrix: {} };
  const adaptiveTips = [];
  byRegime.slice(0, 8).forEach((x) => {
    const key = String(x?.key || 'unknown');
    const trades = Number(x?.trades || 0);
    const pnl = Number(x?.total_pnl || 0);
    const exp = Number(x?.expectancy || 0);
    if (!key || key === 'unknown' || trades < 5) return;
    if (pnl < 0 || exp < 0) {
      runtimePatch.regime_policy_matrix[key] = { qty_mult: 0.9, leverage_mult: 0.9 };
      adaptiveTips.push(`Regime=${key} 样本${trades}且收益偏弱，建议先降仓降杠杆（qty/leverage ×0.9）观察 1-3 天。`);
    }
  });
  byStrategy.slice(0, 8).forEach((x) => {
    const key = String(x?.key || 'unknown');
    const trades = Number(x?.trades || 0);
    const exp = Number(x?.expectancy || 0);
    if (key !== 'unknown' && trades >= 8 && exp < 0) {
      adaptiveTips.push(`策略=${key} 期望为负，建议提高开仓阈值（min_rr 或 min_conf）并降低该策略在弱势 regime 的参与度。`);
    }
  });
  const weakHours = byHour
    .filter((x) => Number(x?.trades || 0) >= 5 && Number(x?.total_pnl || 0) < 0)
    .slice(0, 3)
    .map((x) => String(x?.key || 'unknown'))
    .filter((x) => x !== 'unknown');
  if (weakHours.length) {
    adaptiveTips.push(`时段 ${weakHours.join(', ')} 表现偏弱，建议降低这些时段开仓频率或提升点差门槛。`);
  }
  if (!adaptiveTips.length) {
    adaptiveTips.push('当前分组表现未见明显劣势段，建议保持参数并继续滚动观察。');
  }
  const runtimePatchText =
    Object.keys(runtimePatch.regime_policy_matrix).length > 0
      ? JSON.stringify(runtimePatch, null, 2)
      : JSON.stringify(
          {
            regime_policy_matrix: {
              low_vol_grind: { qty_mult: 0.9, leverage_mult: 0.9 },
            },
          },
          null,
          2
        );
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
        {humanizedWorkflow.headline ? (
          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 16, marginBottom: 16 }}>
            <InsightCard
              title="中文运行摘要"
              tone="normal"
              content={`${humanizedWorkflow.headline} ${humanizedWorkflow.verdict || ''} ${humanizedWorkflow.risk_hint || ''}`.trim()}
            />
            <div className="insight-card warn">
              <div className="insight-title">当前处理建议</div>
              <ActionList items={Array.isArray(humanizedWorkflow.next_actions) ? humanizedWorkflow.next_actions.slice(0, 4) : []} />
            </div>
          </div>
        ) : null}
        {!humanizedWorkflow.headline && humanizedMastery.headline ? (
          <div style={{ marginBottom: 16 }}>
            <InsightCard
              title="全局中文总览"
              tone="normal"
              content={`${humanizedMastery.headline} ${humanizedMastery.verdict || ''}`.trim()}
            />
          </div>
        ) : null}
        {!humanizedWorkflow.headline && !humanizedMastery.headline && humanizedClosedLoop.headline ? (
          <div style={{ marginBottom: 16 }}>
            <InsightCard
              title="闭环中文摘要"
              tone="normal"
              content={`${humanizedClosedLoop.headline} ${humanizedClosedLoop.verdict || ''}`.trim()}
            />
          </div>
        ) : null}
        {Array.isArray(humanizedWorkflow.focus_cards) && humanizedWorkflow.focus_cards.length ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12, marginBottom: 16 }}>
            {humanizedWorkflow.focus_cards.slice(0, 3).map((card, idx) => (
              <InsightCard
                key={`${card.title || 'focus'}-${idx}`}
                title={card.title || '摘要'}
                tone={card.tone || 'normal'}
                content={card.summary || '-'}
              />
            ))}
          </div>
        ) : null}
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
        <InsightCard
          title="执行归因主结论"
          content={
            executionSummary ||
            (executionTop.length
              ? `当前主要执行归因为：${executionTop.join('；')}`
              : '暂无执行归因数据，建议检查 commander snapshot 与 trading-diagnosis 数据链路。')
          }
          tone={executionTop.some((x) => x.startsWith('阻断')) ? 'warn' : 'info'}
        />
        <InsightCard
          title="盈利概览（真实PnL）"
          content={`${pnlText}${topStr ? ` 策略Top: ${topStr}。` : ''}${topReg ? ` RegimeTop: ${topReg}。` : ''}`}
          tone={Number(overall?.total_pnl || 0) < 0 ? 'warn' : 'info'}
        />
        <ActionList
          items={
            profitRecommendations.length
              ? profitRecommendations.slice(0, 5)
              : ['暂无后端盈利优化建议，建议继续观察 30 天真实PnL后再调参。']
          }
        />
        <div className="sub-title" style={{ marginTop: 12 }}>盈利归因下钻（真实PnL）</div>
        <div className="table-grid-two">
          <div>
            <div className="sub-title">策略 Top</div>
            <DataTable
              columns={[
                { key: 'key', title: '策略' },
                { key: 'trades', title: '样本' },
                { key: 'win_rate', title: '胜率' },
                { key: 'total_pnl', title: '总PnL' },
                { key: 'expectancy', title: '期望' },
              ]}
              rows={strategyRows}
              emptyText="暂无策略归因数据"
            />
          </div>
          <div>
            <div className="sub-title">Regime Top</div>
            <DataTable
              columns={[
                { key: 'key', title: 'Regime' },
                { key: 'trades', title: '样本' },
                { key: 'win_rate', title: '胜率' },
                { key: 'total_pnl', title: '总PnL' },
                { key: 'expectancy', title: '期望' },
              ]}
              rows={regimeRows}
              emptyText="暂无 regime 归因数据"
            />
          </div>
        </div>
        <div style={{ marginTop: 10 }}>
          <div className="sub-title">时段 Top（00-23）</div>
          <DataTable
            columns={[
              { key: 'key', title: '小时' },
              { key: 'trades', title: '样本' },
              { key: 'win_rate', title: '胜率' },
              { key: 'total_pnl', title: '总PnL' },
              { key: 'expectancy', title: '期望' },
            ]}
            rows={hourRows}
            emptyText="暂无时段归因数据"
          />
        </div>
        <InsightCard
          title="自动调参建议（草案）"
          content={adaptiveTips.join('；')}
          tone="info"
        />
        <div style={{ marginTop: 8, fontWeight: 700 }}>运行时覆盖建议（可回滚）</div>
        <pre style={{ marginTop: 6, padding: 10, background: 'var(--bg-tertiary)', borderRadius: 8, overflow: 'auto', fontSize: 12 }}>
          {runtimePatchText}
        </pre>
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
