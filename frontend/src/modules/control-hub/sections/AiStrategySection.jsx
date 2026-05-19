import React from 'react';
import { ActionList, DataTable, InsightCard, JsonDetails, MetricGrid } from '../components/UiBlocks';

export default function AiStrategySection({ state }) {
  const memoryHumanized = state.memoryDailySummaryRaw?.humanized || {};
  const systemMasteryHumanized = state.systemMastery?.data?.humanized || state.systemMastery?.humanized || {};
  const memoryStatsHumanized = state.memoryStats?.humanized || {};
  const agentEffectivenessHumanized = state.agentEffectiveness?.data?.humanized || state.agentEffectiveness?.humanized || {};
  const strategyRows = (state.strategies || []).slice(0, 20).map((row, idx) => ({
    id: idx,
    name: row.name || row.strategy_name || `strategy-${idx + 1}`,
    status: row.status || '-',
    type: row.type || row.category || '-',
  }));
  const jobRows = (state.researchJobs || []).slice(0, 20).map((row, idx) => ({
    id: idx,
    topic: row.topic || row.symbol || '-',
    status: row.status || '-',
    progress: row.progress ?? '-',
  }));
  const oppRows = (state.opportunities || []).slice(0, 20).map((row, idx) => ({
    id: idx,
    symbol: row.symbol || '-',
    score: row.score ?? '-',
    action: row.action || row.suggestion || '-',
  }));

  return (
    <div className="panel section-panel" style={{ marginTop: 16 }}>
      <div className="panel-header">
        <div className="panel-title">AI与策略研发</div>
      </div>
      <div className="panel-body">
        <MetricGrid
          items={[
            { label: '策略总数', value: state.strategies?.length || 0 },
            { label: '研究任务', value: state.researchJobs?.length || 0 },
            { label: 'AI机会', value: state.opportunities?.length || 0 },
            { label: '记忆摘要数', value: state.memorySummary?.length || 0 },
          ]}
        />
        <InsightCard
          title="策略智能建议"
          content={
            memoryHumanized.headline
              || memoryStatsHumanized.headline
              || agentEffectivenessHumanized.headline
              || systemMasteryHumanized.verdict
              || `当前可用策略 ${state.strategies?.length || 0} 个，AI机会 ${state.opportunities?.length || 0} 条。建议优先处理高评分机会。`
          }
          tone="info"
        />
        <ActionList
          items={Array.isArray(memoryHumanized.next_actions) && memoryHumanized.next_actions.length ? memoryHumanized.next_actions.slice(0, 3) : Array.isArray(agentEffectivenessHumanized.next_actions) && agentEffectivenessHumanized.next_actions.length ? agentEffectivenessHumanized.next_actions.slice(0, 3) : [
            '先看“AI机会建议”评分高的标的',
            '研究任务状态长期不变时，建议重新触发研究任务',
            '策略状态异常时，先停用再恢复，避免误触发',
          ]}
        />
        <div className="sub-title" style={{ marginTop: 12 }}>策略列表</div>
        <DataTable columns={[{ key: 'name', title: '策略' }, { key: 'status', title: '状态' }, { key: 'type', title: '类型' }]} rows={strategyRows} />
        <div className="table-grid-two" style={{ marginTop: 12 }}>
          <div>
            <div className="sub-title">研究任务</div>
            <DataTable columns={[{ key: 'topic', title: '主题' }, { key: 'status', title: '状态' }, { key: 'progress', title: '进度' }]} rows={jobRows} />
          </div>
          <div>
            <div className="sub-title">AI机会建议</div>
            <DataTable columns={[{ key: 'symbol', title: '标的' }, { key: 'score', title: '评分' }, { key: 'action', title: '建议' }]} rows={oppRows} />
          </div>
        </div>
        <JsonDetails title="高级原始数据：策略优化详情" value={state.strategyOpt} />
        <JsonDetails title="高级原始数据：生产审计详情" value={state.productionAudit} />
      </div>
    </div>
  );
}
