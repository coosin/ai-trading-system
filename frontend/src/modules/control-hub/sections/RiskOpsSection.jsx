import React from 'react';
import { ActionList, DataTable, InsightCard, JsonDetails, MetricGrid } from '../components/UiBlocks';

export default function RiskOpsSection({ state }) {
  const monitoringHumanized = state.monitoringSummary?.humanized || {};
  const alertRows = (state.monitoringAlerts || []).slice(0, 20).map((row, idx) => ({
    id: idx,
    level: row.severity || row.level || '-',
    type: row.alert_type || row.type || '-',
    message: row.message || '-',
    source: row.source || '-',
  }));
  const historyRows = (state.monitoringAlertHistory || []).slice(0, 20).map((row, idx) => ({
    id: idx,
    level: row.severity || '-',
    message: row.message || '-',
    time: row.timestamp || row.created_at || '-',
  }));

  return (
    <div className="panel section-panel" style={{ marginTop: 16 }}>
      <div className="panel-header">
        <div className="panel-title">风控、告警、运维监控</div>
      </div>
      <div className="panel-body">
        <MetricGrid
          items={[
            { label: '活跃告警', value: state.monitoringSummary?.active_alerts ?? 0 },
            { label: '风控状态', value: state.riskStatus?.status || '-' },
            { label: '风险等级', value: state.riskMonitor?.risk_level || '-' },
            { label: '杠杆', value: state.riskMetrics?.leverage_used ?? '-' },
          ]}
        />
        <InsightCard
          title="风控结论"
          content={monitoringHumanized.headline || `当前风险等级：${state.riskMonitor?.risk_level || '-'}，活跃告警 ${state.monitoringSummary?.active_alerts ?? 0} 条。`}
          tone={(state.monitoringSummary?.active_alerts ?? 0) > 0 ? 'warn' : 'info'}
        />
        <ActionList
          items={Array.isArray(monitoringHumanized.next_actions) && monitoringHumanized.next_actions.length ? monitoringHumanized.next_actions : [
            '若出现高风险告警，请先暂停新增仓位',
            '优先处理“当前告警”中的最高级别问题',
            '告警清零后再恢复正常开仓节奏',
          ]}
        />
        <div className="sub-title" style={{ marginTop: 12 }}>当前告警</div>
        <DataTable
          columns={[
            { key: 'level', title: '级别' },
            { key: 'type', title: '类型' },
            { key: 'message', title: '内容' },
            { key: 'source', title: '来源' },
          ]}
          rows={alertRows}
          emptyText="暂无活跃告警"
        />
        <div className="sub-title" style={{ marginTop: 12 }}>历史告警</div>
        <DataTable
          columns={[
            { key: 'level', title: '级别' },
            { key: 'message', title: '内容' },
            { key: 'time', title: '时间' },
          ]}
          rows={historyRows}
          emptyText="暂无历史告警"
        />
        <JsonDetails title="高级原始数据：风控详情" value={{ riskStatus: state.riskStatus, riskMetrics: state.riskMetrics, riskMonitor: state.riskMonitor }} />
      </div>
    </div>
  );
}
