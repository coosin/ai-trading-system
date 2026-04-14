import React from 'react';
import { ActionList, DataTable, InsightCard, MetricGrid, StatusBadge } from '../components/UiBlocks';

function statusText(ok) {
  return ok ? '正常' : '异常';
}

export default function OverviewSection({ state, flowRows, updatedAt }) {
  const missingRows = flowRows.filter((r) => !r.ok);
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
