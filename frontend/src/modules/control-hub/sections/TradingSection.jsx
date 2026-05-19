import React from 'react';
import { ActionList, DataTable, InsightCard, JsonDetails, MetricGrid, ProcessSteps, StatusBadge } from '../components/UiBlocks';

export default function TradingSection({
  state,
  view,
  simulatePayload,
  setSimulatePayload,
  actions,
  loading,
  updatedAt,
}) {
  const closedLoopHumanized = state.closedLoopSummary?.data?.humanized || state.closedLoopSummary?.humanized || {};
  const profitOpsHumanized = state.profitOpsOverview?.data?.humanized || state.profitOpsOverview?.humanized || {};
  const [ignoredSuggestionIds, setIgnoredSuggestionIds] = React.useState([]);
  const [nowTs, setNowTs] = React.useState(Date.now());
  const [secondConfirmEnabled, setSecondConfirmEnabled] = React.useState(() => {
    try {
      const raw = window.localStorage.getItem('semi_auto_second_confirm');
      return raw == null ? true : raw === '1';
    } catch {
      return true;
    }
  });
  const [highRiskOnly, setHighRiskOnly] = React.useState(false);
  const balanceRows = Object.entries(view.balances || {}).map(([asset, total]) => ({ id: asset, asset, total }));
  const detailRows = (view.balanceDetails || []).map((row, idx) => ({
    id: idx,
    asset: row.asset || row.ccy,
    free: row.free ?? row.availEq ?? '-',
    total: row.total ?? row.eq ?? '-',
  }));
  const posRows = (view.positions || []).map((row, idx) => ({
    id: idx,
    instId: row.instId || row.symbol || '-',
    side: row.posSide || row.side || '-',
    size: row.pos || row.size || '-',
    markPx: row.markPx || '-',
    upl: row.upl || '-',
  }));
  const tradeRows = (view.tradeHistory || []).slice(0, 12).map((row, idx) => ({
    id: idx,
    symbol: row.symbol || '-',
    side: row.side || '-',
    price: row.price || '-',
    qty: row.quantity || row.size || '-',
    pnl: row.pnl || '-',
  }));
  const syncOk = !state.accountDiagnostics?.degraded;
  const loopPolicyRows = Object.entries(view.loopPolicy || {}).map(([k, v]) => ({ id: k, key: k, value: typeof v === 'object' ? JSON.stringify(v) : String(v) }));
  const eventRows = (view.tradeEvents || []).slice(0, 20).map((row, idx) => ({
    id: idx,
    type: row.type || row.event_type || '-',
    symbol: row.symbol || '-',
    side: row.side || '-',
    status: row.status || '-',
    time: row.timestamp || row.ts || '-',
  }));
  const hostingMode = state.hostingMode?.data?.mode || state.commanderSnapshot?.system?.hosting_mode || 'full_auto';
  const pendingSuggestions = (view.tradeEvents || [])
    .map((row, idx) => {
      const rawText = String(row.detail || row.message || row.reason || row.status || '').toLowerCase();
      const rawErr = String(row?.raw?.error || '').toLowerCase();
      const blocked =
        rawText.includes('半自动') ||
        rawText.includes('hosting_mode_denied') ||
        rawText.includes('requires_manual_approval') ||
        rawErr.includes('hosting_mode_denied');
      if (!blocked) return null;
      const id = `${row.ts || row.timestamp || idx}-${row.symbol || '-'}-${row.side || '-'}`;
      const rawTs = row.ts || row.timestamp || null;
      const parsedTs = rawTs ? Date.parse(String(rawTs)) : NaN;
      const createdAt = Number.isFinite(parsedTs) ? parsedTs : Date.now();
      const expiresAt = createdAt + 120000;
      const ttlSec = Math.max(0, Math.floor((expiresAt - nowTs) / 1000));
      const sizeNum = Number(row.size || row.quantity || 0.01);
      const reasonText = String(row.detail || row.message || '').toLowerCase();
      let riskLevel = '中';
      if (reasonText.includes('critical') || reasonText.includes('严重') || sizeNum >= 0.03) {
        riskLevel = '高';
      } else if (sizeNum <= 0.01) {
        riskLevel = '低';
      }
      return {
        id,
        symbol: row.symbol || '-',
        side: row.side || 'long',
        size: row.size || row.quantity || 0.01,
        reason: row.detail || row.message || '半自动模式拦截，需人工确认',
        time: row.ts || row.timestamp || '-',
        createdAt,
        ttlSec,
        riskLevel,
      };
    })
    .filter((x) => x && !ignoredSuggestionIds.includes(x.id) && x.ttlSec > 0)
    .sort((a, b) => b.createdAt - a.createdAt)
    .slice(0, 5);
  const visibleSuggestions = highRiskOnly
    ? pendingSuggestions.filter((x) => x.riskLevel === '高')
    : pendingSuggestions;

  React.useEffect(() => {
    const timer = window.setInterval(() => setNowTs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  React.useEffect(() => {
    try {
      window.localStorage.setItem('semi_auto_second_confirm', secondConfirmEnabled ? '1' : '0');
    } catch {
      // noop
    }
  }, [secondConfirmEnabled]);
  const applyPreset = (mode) => {
    const base = { ...simulatePayload };
    if (mode === 'conservative') {
      setSimulatePayload({ ...base, side: 'buy', amount: 0.005, order_type: 'limit' });
      return;
    }
    if (mode === 'balanced') {
      setSimulatePayload({ ...base, side: 'buy', amount: 0.01, order_type: 'market' });
      return;
    }
    setSimulatePayload({ ...base, side: 'buy', amount: 0.02, order_type: 'market' });
  };
  const latest = view.tradingProcess?.latestEvent || {};
  const tradingSteps = [
    {
      id: 't1',
      title: '风险门控',
      desc: `账户同步 ${view.tradingProcess?.synced ? '正常' : '降级'}，门控项 ${Object.keys(view.tradingProcess?.policy || {}).length} 个`,
      ok: view.tradingProcess?.synced,
    },
    {
      id: 't2',
      title: '交易判断',
      desc: `当前决策 ${view.tradingProcess?.decision}`,
      ok: view.tradingProcess?.decision !== '-',
    },
    {
      id: 't3',
      title: '执行发送',
      desc: `最近事件 ${latest.type || latest.event_type || '-'} / ${latest.status || '-'}`,
      ok: Boolean(latest.type || latest.event_type),
    },
    {
      id: 't4',
      title: '结果回执',
      desc: `回执时间 ${latest.timestamp || latest.ts || '-'}，标的 ${latest.symbol || '-'}`,
      ok: Boolean(latest.timestamp || latest.ts),
    },
  ];
  const policyRows = Object.entries(view.tradingProcess?.policy || {}).map(([k, v]) => ({
    id: k,
    item: k,
    value: typeof v === 'object' ? JSON.stringify(v) : String(v),
    judge:
      typeof v === 'number'
        ? v > 0
          ? '通过'
          : '待确认'
        : String(v).toLowerCase().includes('false')
          ? '待确认'
          : '通过',
  }));
  const sltpRows = Object.entries(view.stopLossStats || {}).slice(0, 20).map(([k, v]) => ({
    id: k,
    item: k,
    value: typeof v === 'object' ? JSON.stringify(v) : String(v),
  }));

  return (
    <div className="panel section-panel" style={{ marginTop: 16 }}>
      <div className="panel-header">
        <div className="panel-title">交易执行、开平仓、仓位钱包同步</div>
      </div>
      <div className="panel-body">
        <MetricGrid
          items={[
            { label: '账户同步', value: <StatusBadge ok={syncOk} text={syncOk ? '正常' : '降级'} /> },
            { label: 'USDT 可用/总额', value: `${view.usdt?.free ?? '-'} / ${view.usdt?.total ?? '-'}` },
            { label: '持仓数量', value: view.positions?.length || 0 },
            { label: '执行脊柱', value: state.executionSpine ? '在线' : '未知' },
          ]}
        />
        <InsightCard
          title="交易执行建议"
          content={
            closedLoopHumanized.headline
              || profitOpsHumanized.headline
              || (syncOk
              ? `当前可执行交易。持仓 ${view.positions?.length || 0} 笔，建议优先小仓位开单并观察事件流回报。`
              : '账户同步处于降级状态，建议先点“手动账户同步”，确认仓位和钱包正常后再开单。')
          }
          tone={syncOk ? 'info' : 'warn'}
        />
        {(closedLoopHumanized.next_actions?.length || profitOpsHumanized.next_actions?.length) ? (
          <ActionList items={(closedLoopHumanized.next_actions || profitOpsHumanized.next_actions || []).slice(0, 4)} />
        ) : null}
        {hostingMode === 'semi_auto' && (
          <div className="confirm-card">
            <div className="confirm-title">半自动待确认开仓（傻瓜化确认区）</div>
            <div className="confirm-desc">
              AI 给出开仓建议后会先拦截到这里，你只需要点“确认开仓”或“忽略”。
            </div>
            <div className="confirm-tools">
              <label className="confirm-toggle">
                <input
                  type="checkbox"
                  checked={secondConfirmEnabled}
                  onChange={(e) => setSecondConfirmEnabled(e.target.checked)}
                />
                二次确认
              </label>
              <label className="confirm-toggle">
                <input
                  type="checkbox"
                  checked={highRiskOnly}
                  onChange={(e) => setHighRiskOnly(e.target.checked)}
                />
                只看高风险
              </label>
              <button
                type="button"
                className="btn btn-sm btn-outline"
                onClick={() => setIgnoredSuggestionIds((prev) => [...prev, ...pendingSuggestions.map((x) => x.id)])}
                disabled={!pendingSuggestions.length}
              >
                一键清空待确认
              </button>
            </div>
            {!visibleSuggestions.length ? (
              <div className="confirm-empty">当前没有待确认建议</div>
            ) : (
              <div className="confirm-list">
                {visibleSuggestions.map((s) => (
                  <div key={s.id} className="confirm-item">
                    <div>
                      <div className="confirm-item-title">
                        {s.symbol} · {String(s.side || '').toUpperCase()} · 数量 {s.size}
                      </div>
                      <div className="confirm-item-sub">拦截原因: {s.reason}</div>
                      <div className="confirm-item-sub">
                        时间: {s.time} · 倒计时: {s.ttlSec}s · 风险:
                        <span className={`confirm-risk ${s.riskLevel === '高' ? 'high' : s.riskLevel === '低' ? 'low' : 'mid'}`}>
                          {s.riskLevel}
                        </span>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className="btn btn-sm btn-primary"
                        onClick={() => {
                          if (secondConfirmEnabled) {
                            const ok = window.confirm(
                              `确认开仓？\n标的: ${s.symbol}\n方向: ${String(s.side || '').toUpperCase()}\n数量: ${s.size}\n风险: ${s.riskLevel}`,
                            );
                            if (!ok) return;
                          }
                          actions?.confirmSuggestedOpen?.(s);
                        }}
                      >
                        确认开仓
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline"
                        onClick={() => setIgnoredSuggestionIds((prev) => [...prev, s.id])}
                      >
                        忽略
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
          <button type="button" className="btn btn-sm btn-outline" onClick={actions.loadSlow} disabled={loading.slow}>
            {loading.slow ? '刷新中' : '刷新交易状态'}
          </button>
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
            交易状态更新时间: {updatedAt?.slow || '-'}
          </span>
        </div>
        <ActionList
          items={[
            '先同步账户，再执行开平仓',
            '开仓后优先观察“实时开平仓事件流”是否回执成功',
            '若止盈止损统计无更新，请暂停新增仓位并排查链路',
          ]}
        />
        <div className="sub-title">交易判断过程（可视化）</div>
        <ProcessSteps rows={tradingSteps} />
        <div className="sub-title" style={{ marginTop: 12 }}>开平仓判断逻辑详情</div>
        <DataTable
          columns={[
            { key: 'item', title: '判断项' },
            { key: 'value', title: '当前值' },
            { key: 'judge', title: '判定' },
          ]}
          rows={policyRows}
          emptyText="暂无门控判断细节"
        />
        <div className="sub-title" style={{ marginTop: 12 }}>止盈止损逻辑状态</div>
        <DataTable
          columns={[
            { key: 'item', title: 'SLTP项' },
            { key: 'value', title: '当前值' },
          ]}
          rows={sltpRows}
          emptyText="暂无止盈止损统计"
        />
        <div className="sub-title">一键开单模式（傻瓜化）</div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-sm btn-outline" onClick={() => applyPreset('conservative')}>
            保守开单
          </button>
          <button type="button" className="btn btn-sm btn-outline" onClick={() => applyPreset('balanced')}>
            平衡开单
          </button>
          <button type="button" className="btn btn-sm btn-primary" onClick={() => applyPreset('aggressive')}>
            激进开单
          </button>
          <button type="button" className="btn btn-sm btn-primary" onClick={actions.runSimulateOrder} disabled={loading.slow || !syncOk}>
            一键执行当前模式
          </button>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 8 }}>
          模式说明：保守=小仓位+限价，平衡=中仓位+市价，激进=较大仓位+市价。执行前请确认账户同步正常。
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
          <button type="button" className="btn btn-sm btn-outline" onClick={actions.runAccountSync}>
            手动账户同步
          </button>
          <button type="button" className="btn btn-sm btn-primary" onClick={actions.runSimulateOrder} disabled={loading.slow}>
            模拟开平仓
          </button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(120px,1fr))', gap: 8, marginBottom: 10 }}>
          <input className="form-input" value={simulatePayload.symbol} onChange={(e) => setSimulatePayload((p) => ({ ...p, symbol: e.target.value }))} />
          <select className="form-input" value={simulatePayload.side} onChange={(e) => setSimulatePayload((p) => ({ ...p, side: e.target.value }))}>
            <option value="buy">买入开仓</option>
            <option value="sell">卖出开仓</option>
          </select>
          <input className="form-input" type="number" step="0.001" value={simulatePayload.amount} onChange={(e) => setSimulatePayload((p) => ({ ...p, amount: e.target.value }))} />
          <select className="form-input" value={simulatePayload.order_type} onChange={(e) => setSimulatePayload((p) => ({ ...p, order_type: e.target.value }))}>
            <option value="market">市价单</option>
            <option value="limit">限价单</option>
          </select>
        </div>

        <div className="table-grid-two">
          <div>
            <div className="sub-title">钱包余额（聚合）</div>
            <DataTable columns={[{ key: 'asset', title: '资产' }, { key: 'total', title: '总额' }]} rows={balanceRows} />
          </div>
          <div>
            <div className="sub-title">钱包明细</div>
            <DataTable columns={[{ key: 'asset', title: '资产' }, { key: 'free', title: '可用' }, { key: 'total', title: '总额' }]} rows={detailRows} />
          </div>
        </div>
        <div className="sub-title" style={{ marginTop: 12 }}>实时持仓</div>
        <DataTable
          columns={[
            { key: 'instId', title: '合约' },
            { key: 'side', title: '方向' },
            { key: 'size', title: '数量' },
            { key: 'markPx', title: '标记价' },
            { key: 'upl', title: '未实现盈亏' },
          ]}
          rows={posRows}
          emptyText="当前无持仓"
        />
        <div className="sub-title" style={{ marginTop: 12 }}>最近交易事件</div>
        <DataTable
          columns={[
            { key: 'symbol', title: '标的' },
            { key: 'side', title: '方向' },
            { key: 'price', title: '价格' },
            { key: 'qty', title: '数量' },
            { key: 'pnl', title: '盈亏' },
          ]}
          rows={tradeRows}
          emptyText="暂无交易记录"
        />
        <div className="table-grid-two" style={{ marginTop: 12 }}>
          <div>
            <div className="sub-title">循环开单策略门控（Loop Policy）</div>
            <DataTable columns={[{ key: 'key', title: '门控项' }, { key: 'value', title: '当前值' }]} rows={loopPolicyRows} emptyText="执行策略门控数据未返回" />
          </div>
          <div>
            <div className="sub-title">实时开平仓事件流</div>
            <DataTable
              columns={[
                { key: 'type', title: '事件类型' },
                { key: 'symbol', title: '标的' },
                { key: 'side', title: '方向' },
                { key: 'status', title: '状态' },
                { key: 'time', title: '时间' },
              ]}
              rows={eventRows}
              emptyText="事件流暂无数据"
            />
          </div>
        </div>
        <div style={{ marginTop: 10, fontWeight: 700 }}>高级原始数据（可选查看）</div>
        <JsonDetails title="AI 执行门控原始详情" value={view.aiGuards} />
        <JsonDetails title="止盈止损循环原始统计" value={view.stopLossStats} />
        <JsonDetails title="账户同步原始诊断" value={state.accountDiagnostics} />
        <JsonDetails title="执行脊柱原始详情" value={state.executionSpine} />
      </div>
    </div>
  );
}
