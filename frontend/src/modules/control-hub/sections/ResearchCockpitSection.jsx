import React from 'react';
import { ActionList, DataTable, InsightCard, JsonDetails, MetricGrid } from '../components/UiBlocks';

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

export default function ResearchCockpitSection({ state, actions, loading, updatedAt }) {
  const cockpit = state.researchCockpit?.data || state.researchCockpit || {};
  const research = cockpit.research || {};
  const learning = cockpit.learning || {};
  const featureStore = cockpit.feature_store || {};
  const marketStructure = cockpit.market_structure?.market_structure || state.marketStructureCockpit?.data?.market_structure || {};
  const governance = research.market_structure_governance || {};
  const funnel = research.funnel || {};
  const stageCounts = funnel.by_stage || {};
  const governanceCounts = governance.status_counts || {};
  const strategyRows = safeArray(research.strategy_rows).map((row, idx) => ({
    id: row.strategy_id || idx,
    name: row.name || row.strategy_id || '-',
    stage: row.stage || '-',
    oos: row.oos_status || '-',
    drift: row.live_drift_status || '-',
    overlay: row.market_structure_overlay_status || '-',
    effective_cap: row.effective_cap_multiplier ?? '-',
    review: row.review_completion_status || '-',
    failure_cases: row.failure_case_count ?? 0,
    sensitivity: row.parameter_sensitivity_summary || '-',
  }));
  const deckRows = safeArray(learning.retrieval_deck?.cards || state.retrievalDeck?.cards).map((row, idx) => ({
    id: idx,
    question: row.question || '-',
    lesson_type: row.lesson_type || '-',
    strategy: row.strategy || '-',
  }));
  const researchLabelRows = safeArray(featureStore.research_labels).map((row, idx) => ({
    id: idx,
    strategy: row.strategy_id || '-',
    stage: row.stage || '-',
    oos: row.oos_status || '-',
    decision: row.decision || '-',
  }));
  const execRows = safeArray(featureStore.execution_outcomes).map((row, idx) => ({
    id: idx,
    symbol: row.symbol || '-',
    status: row.status || '-',
    regime: row.regime_label || '-',
    posture: row.risk_posture || '-',
  }));
  const rawRows = safeArray(featureStore.raw_market_events).map((row, idx) => ({
    id: idx,
    symbol: row.symbol || '-',
    spread: row.spread_bps ?? '-',
    funding: row.funding_rate ?? '-',
    quality: row.quality_score ?? '-',
  }));
  const derivedRows = safeArray(featureStore.derived_features).map((row, idx) => ({
    id: idx,
    symbol: row.symbol || '-',
    regime: row.regime_label || '-',
    posture: row.risk_posture || '-',
    conflict: row.signal_conflict_score ?? '-',
  }));
  const weeklyReview = learning.weekly_review || state.weeklyReview?.weekly_review || state.weeklyReview || {};
  const analytics = learning.analytics || {};
  const reviewMarkdown = weeklyReview.review_markdown || '';
  const stageSummary = Object.entries(stageCounts)
    .map(([k, v]) => `${k}:${v}`)
    .join(' · ');
  const governanceSummary = Object.entries(governanceCounts)
    .map(([k, v]) => `${k}:${v}`)
    .join(' · ');
  const topFailureRows = strategyRows
    .filter((row) => Number(row.failure_cases || 0) > 0)
    .sort((a, b) => Number(b.failure_cases || 0) - Number(a.failure_cases || 0))
    .slice(0, 8);

  return (
    <div className="panel section-panel" style={{ marginTop: 16 }}>
      <div className="panel-header">
        <div className="panel-title">研究与学习驾驶舱</div>
      </div>
      <div className="panel-body">
        <MetricGrid
          items={[
            { label: '研究策略数', value: funnel.total ?? 0 },
            { label: '评审完成率', value: `${Math.round(Number(research.review_completion_rate || 0) * 100)}%` },
            { label: '主动回忆正确率', value: analytics.retrieval_accuracy != null ? `${Math.round(Number(analytics.retrieval_accuracy) * 100)}%` : '-' },
            { label: '研究转化率', value: analytics.research_conversion_rate != null ? `${Math.round(Number(analytics.research_conversion_rate) * 100)}%` : '-' },
            { label: '失败案例总数', value: research.failure_case_total ?? 0 },
          ]}
        />
        <InsightCard
          title="驾驶舱结论"
          content={`当前研究漏斗：${stageSummary || '暂无'}。市场结构=${marketStructure.regime_label || '-'} / 风险姿态=${marketStructure.risk_posture || '-'} / 治理状态=${governanceSummary || '暂无'}。`}
          tone="info"
        />
        <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-sm btn-outline" onClick={actions.loadSlow} disabled={loading.slow}>
            {loading.slow ? '刷新中' : '刷新研究驾驶舱'}
          </button>
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
            最近更新时间: {updatedAt.slow || '-'}
          </span>
        </div>
        <ActionList
          items={[
            '优先处理 OOS 非 passed 且 review 未完成的策略',
            '若 live drift 进入 degraded，先降权再补复盘卡',
            '每周至少完成一次 retrieval deck 回答，不要只看总结',
          ]}
        />

        <div className="table-grid-two" style={{ marginTop: 12 }}>
          <div>
            <div className="sub-title">策略研究漏斗</div>
            <DataTable
              columns={[
                { key: 'name', title: '策略' },
                { key: 'stage', title: '阶段' },
                { key: 'oos', title: 'OOS' },
                { key: 'overlay', title: '治理状态' },
                { key: 'effective_cap', title: '有效倍率' },
                { key: 'review', title: '评审' },
              ]}
              rows={strategyRows}
              emptyText="暂无策略研究数据"
            />
          </div>
          <div>
            <div className="sub-title">主动回忆题卡</div>
            <DataTable
              columns={[
                { key: 'question', title: '问题' },
                { key: 'lesson_type', title: '类型' },
                { key: 'strategy', title: '策略' },
              ]}
              rows={deckRows}
              emptyText="暂无题卡"
            />
          </div>
        </div>

        <div className="table-grid-two" style={{ marginTop: 12 }}>
          <div>
            <div className="sub-title">研究标签流</div>
            <DataTable
              columns={[
                { key: 'strategy', title: '策略' },
                { key: 'stage', title: '阶段' },
                { key: 'oos', title: 'OOS' },
                { key: 'decision', title: '决策' },
              ]}
              rows={researchLabelRows}
              emptyText="暂无研究标签"
            />
          </div>
          <div>
            <div className="sub-title">执行结果流</div>
            <DataTable
              columns={[
                { key: 'symbol', title: '标的' },
                { key: 'status', title: '结果' },
                { key: 'regime', title: 'Regime' },
                { key: 'posture', title: '姿态' },
              ]}
              rows={execRows}
              emptyText="暂无执行结果"
            />
          </div>
        </div>

        <div className="table-grid-two" style={{ marginTop: 12 }}>
          <div>
            <div className="sub-title">原始市场事件</div>
            <DataTable
              columns={[
                { key: 'symbol', title: '标的' },
                { key: 'spread', title: 'Spread' },
                { key: 'funding', title: 'Funding' },
                { key: 'quality', title: '质量分' },
              ]}
              rows={rawRows}
              emptyText="暂无原始市场事件"
            />
          </div>
          <div>
            <div className="sub-title">派生结构特征</div>
            <DataTable
              columns={[
                { key: 'symbol', title: '标的' },
                { key: 'regime', title: 'Regime' },
                { key: 'posture', title: '姿态' },
                { key: 'conflict', title: '冲突分' },
              ]}
              rows={derivedRows}
              emptyText="暂无派生结构特征"
            />
          </div>
        </div>

        <div className="sub-title" style={{ marginTop: 12 }}>失败案例热点</div>
        <DataTable
          columns={[
            { key: 'name', title: '策略' },
            { key: 'failure_cases', title: '失败案例数' },
            { key: 'drift', title: '漂移' },
            { key: 'oos', title: 'OOS' },
          ]}
          rows={topFailureRows}
          emptyText="暂无失败案例热点"
        />

        <InsightCard
          title="本周研究复盘摘录"
          content={reviewMarkdown ? reviewMarkdown.slice(0, 280) : '暂无周复盘内容'}
          tone="normal"
        />
        <InsightCard
          title="结构建议"
          content={`优先 setup：${safeArray(marketStructure.preferred_setups).join(' / ') || '暂无'}。规避标的：${safeArray(marketStructure.avoid_symbols).join(' / ') || '暂无'}。`}
          tone="normal"
        />
        <JsonDetails title="高级原始数据：Research Cockpit" value={cockpit} />
      </div>
    </div>
  );
}
