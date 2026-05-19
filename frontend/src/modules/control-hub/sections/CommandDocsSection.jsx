import React, { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { ActionList, DataTable, InsightCard, JsonDetails, MetricGrid } from '../components/UiBlocks';

const DOC_LOADERS = import.meta.glob(
  ['../../../../docs/**/*.md', '../../../../../docs/**/*.md'],
  { query: '?raw', import: 'default' },
);

const DOCS = [
  { id: 'readme', title: '文档索引', path: '../../../../docs/README.md' },
  { id: 'engineering', title: '工程文档', path: '../../../../docs/ENGINEERING.md' },
  { id: 'operations', title: '运维文档', path: '../../../../docs/OPERATIONS.md' },
  { id: 'api', title: 'API文档', path: '../../../../docs/API_REFERENCE.md' },
  { id: 'changelog', title: '变更记录', path: '../../../../docs/CHANGELOG.md' },
];

const API_MATRIX = [
  { module: '系统', endpoint: '系统健康状态', key: 'health' },
  { module: '系统', endpoint: '系统运行总览', key: 'systemStatus' },
  { module: '交易所', endpoint: '交易所连接列表', key: 'exchanges' },
  { module: '行情', endpoint: '实时价格', key: 'ticker' },
  { module: '行情', endpoint: '盘口深度', key: 'orderbook' },
  { module: '行情', endpoint: 'K线数据', key: 'klines' },
  { module: '行情', endpoint: '市场状态', key: 'marketState' },
  { module: '行情', endpoint: '智能行情判断', key: 'marketSymbolView' },
  { module: '数据', endpoint: '统一数据快照', key: 'dataHubSnapshot' },
  { module: '数据', endpoint: '融合分析结果', key: 'fusion' },
  { module: '交易', endpoint: '账户诊断', key: 'accountDiagnostics' },
  { module: '交易', endpoint: '执行状态', key: 'executionSpine' },
  { module: '交易', endpoint: '开平仓事件流', key: 'tradeEvents' },
  { module: '风控', endpoint: '风险状态', key: 'riskStatus' },
  { module: '风控', endpoint: '止盈止损统计', key: 'stopLossStats' },
  { module: '司令部', endpoint: '司令部快照', key: 'commanderSnapshot' },
  { module: '司令部', endpoint: '平台总巡检', key: 'platformOversight' },
  { module: '司令部', endpoint: '司令部能力', key: 'commanderCapabilities' },
  { module: '司令部', endpoint: '司令部审计', key: 'commanderAudit' },
  { module: 'AI', endpoint: 'AI门控规则', key: 'aiGuards' },
];

function resolve(path) {
  if (DOC_LOADERS[path]) return DOC_LOADERS[path];
  const alt = path.replace('../../../../', '../../../../../');
  return DOC_LOADERS[alt] || null;
}

function diagnoseMissing(row, errors, value) {
  if (Array.isArray(value)) return value.length > 0 ? '-' : '接口返回空数组';
  if (value) return '-';
  const key = row.key;
  const fastKeys = new Set(['health', 'systemStatus', 'exchanges', 'ticker', 'orderbook', 'klines', 'marketState', 'marketSymbolView']);
  const mediumKeys = new Set(['dataHubSnapshot', 'fusion']);
  const slowKeys = new Set([
    'accountDiagnostics',
    'executionSpine',
    'tradeEvents',
    'riskStatus',
    'stopLossStats',
    'commanderSnapshot',
    'platformOversight',
    'commanderCapabilities',
    'commanderAudit',
    'aiGuards',
  ]);
  const err = fastKeys.has(key) ? errors?.fast : mediumKeys.has(key) ? errors?.medium : slowKeys.has(key) ? errors?.slow : null;
  if (!err) return '接口未返回数据';
  const msg = String(err).toLowerCase();
  if (msg.includes('timeout')) return '链路超时';
  if (msg.includes('401') || msg.includes('403')) return '鉴权失败';
  if (msg.includes('404')) return '接口未实现/未注册';
  if (msg.includes('502') || msg.includes('503') || msg.includes('504')) return '后端服务异常';
  return err;
}

const SEVERITY_RANK = { block: 0, reduce: 1, warn: 2 };
const SEVERITY_LABEL = { block: '阻断', reduce: '降风险', warn: '告警' };
const SEVERITY_COLOR = { block: '#dc2626', reduce: '#d97706', warn: '#64748b' };
const OVERSIGHT_SEVERITY_LABEL = { critical: '关键', high: '高', medium: '中', low: '低' };
const OVERSIGHT_SEVERITY_COLOR = { critical: '#b91c1c', high: '#dc2626', medium: '#d97706', low: '#64748b' };

export default function CommandDocsSection({ commandInput, setCommandInput, commandReply, actions, state, errors }) {
  const [docId, setDocId] = useState('readme');
  const [content, setContent] = useState('');

  const selected = useMemo(() => DOCS.find((d) => d.id === docId) || DOCS[0], [docId]);
  const auditChecks = Array.isArray(state.commanderAudit?.checks) ? state.commanderAudit.checks : [];
  const auditRows = auditChecks.slice(0, 30).map((row, idx) => ({
    id: idx,
    name: row.name || '-',
    passed: row.passed ? 'PASS' : 'FAIL',
    detail: row.detail || '-',
  }));
  const coverageRows = API_MATRIX.map((row, idx) => {
    const value = state?.[row.key];
    const hasData = Array.isArray(value) ? value.length > 0 : Boolean(value);
    return {
      id: `${row.endpoint}-${idx}`,
      module: row.module,
      item: row.endpoint,
      status: hasData ? '已对接' : '缺数据',
      source: row.key,
      diagnose: diagnoseMissing(row, errors, value),
    };
  });
  const connected = coverageRows.filter((r) => r.status === '已对接').length;
  const smokeRows = Array.isArray(state.apiSmoke) ? state.apiSmoke : [];
  const contract = state.toolContract?.data || {};
  const toolRows = [
    ...(Array.isArray(contract.read_tools) ? contract.read_tools.map((x, i) => ({ id: `r-${i}`, kind: '只读', path: x })) : []),
    ...(Array.isArray(contract.write_tools) ? contract.write_tools.map((x, i) => ({ id: `w-${i}`, kind: '写入', path: x })) : []),
  ];
  const govAuditRows = (Array.isArray(state.governanceAudit) ? state.governanceAudit : []).slice(0, 30).map((x, i) => ({
    id: i,
    ts: x.ts || '-',
    event: x.event || '-',
    detail: JSON.stringify(x.detail || {}, null, 0),
  }));
  const commanderSnapshot = state.commanderSnapshot?.data || state.commanderSnapshot || {};
  const snapshotHumanized = commanderSnapshot.humanized || {};
  const systemMasteryHumanized = state.systemMastery?.data?.humanized || state.systemMastery?.humanized || {};
  const platformOversight = state.platformOversight?.data || state.platformOversight || {};
  const platformHumanized = platformOversight.humanized || {};
  const componentRows = Array.isArray(platformOversight.component_inventory)
    ? platformOversight.component_inventory.slice(0, 30).map((row, idx) => ({
        id: idx,
        component: row.component || '-',
        status: row.available ? 'READY' : 'MISSING',
        responsibility: row.responsibility || '-',
        source_file: row.source_file || '-',
      }))
    : [];
  const routeSummary = platformOversight.route_inventory?.summary || {};
  const routeRows = Array.isArray(platformOversight.route_inventory?.routes)
    ? platformOversight.route_inventory.routes.slice(0, 40).map((row, idx) => ({
        id: idx,
        path: row.path || '-',
        methods: Array.isArray(row.methods) ? row.methods.join(', ') : '-',
        domain: row.domain || '-',
        file: row.endpoint_file || '-',
      }))
    : [];
  const oversightFocusRows = Array.isArray(platformHumanized.focus_cards)
    ? platformHumanized.focus_cards.map((row, idx) => ({
        id: idx,
        title: row.title || '-',
        tone: row.tone || '-',
        summary: row.summary || '-',
      }))
    : [];
  const priorityAlertRows = Array.isArray(platformOversight.priority_alerts)
    ? platformOversight.priority_alerts.slice(0, 12).map((row, idx) => {
        const sev = String(row.severity || 'low').toLowerCase();
        return {
          id: row.id ?? idx,
          severity: (
            <span
              style={{
                display: 'inline-block',
                padding: '2px 8px',
                borderRadius: 999,
                color: '#fff',
                background: OVERSIGHT_SEVERITY_COLOR[sev] || OVERSIGHT_SEVERITY_COLOR.low,
                fontSize: 12,
                fontWeight: 700,
              }}
            >
              {OVERSIGHT_SEVERITY_LABEL[sev] || OVERSIGHT_SEVERITY_LABEL.low}
            </span>
          ),
          area: row.area || '-',
          title: row.title || '-',
          summary: row.summary || '-',
          recommendation: row.recommendation || '-',
        };
      })
    : [];
  const executionAttribution =
    commanderSnapshot.execution_attribution ||
    commanderSnapshot.data?.execution_attribution ||
    {};
  const attributionSummary = String(executionAttribution.summary || '').trim();
  const attributionTop = Array.isArray(executionAttribution.top_reasons)
    ? executionAttribution.top_reasons
    : [];
  const attributionRows = attributionTop
    .map((x, i) => {
      const sev = String(x?.severity || 'warn').toLowerCase();
      return {
        id: `${x?.key || 'unknown'}-${i}`,
        reason: String(x?.key || '-'),
        severity: (
          <span
            style={{
              display: 'inline-block',
              padding: '2px 8px',
              borderRadius: 999,
              color: '#fff',
              background: SEVERITY_COLOR[sev] || SEVERITY_COLOR.warn,
              fontSize: 12,
              fontWeight: 700,
            }}
          >
            {SEVERITY_LABEL[sev] || SEVERITY_LABEL.warn}
          </span>
        ),
        category: String(x?.category || '-'),
        count: Number(x?.count || 0),
        hint: String(x?.action_hint || '-'),
        severity_raw: sev,
      };
    })
    .sort((a, b) => {
      const sa = SEVERITY_RANK[a.severity_raw] ?? 9;
      const sb = SEVERITY_RANK[b.severity_raw] ?? 9;
      if (sa !== sb) return sa - sb;
      return Number(b.count || 0) - Number(a.count || 0);
    })
    .slice(0, 10);

  const loadDoc = async () => {
    const loader = resolve(selected.path);
    if (!loader) {
      setContent('文档加载失败：未找到文件。');
      return;
    }
    const raw = await loader();
    setContent(String(raw || ''));
  };

  return (
    <div className="panel-row" style={{ marginTop: 16 }}>
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">指挥与运维</div>
        </div>
        <div className="panel-body">
          {(snapshotHumanized.headline || systemMasteryHumanized.headline || platformHumanized.headline) ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
              {snapshotHumanized.headline ? (
                <InsightCard title="司令部快照摘要" tone="normal" content={`${snapshotHumanized.headline} ${snapshotHumanized.verdict || ''}`.trim()} />
              ) : null}
              {systemMasteryHumanized.headline ? (
                <InsightCard title="系统掌控摘要" tone="normal" content={`${systemMasteryHumanized.headline} ${systemMasteryHumanized.verdict || ''}`.trim()} />
              ) : null}
              {platformHumanized.headline ? (
                <InsightCard title="平台总巡检摘要" tone="normal" content={`${platformHumanized.headline} ${platformHumanized.verdict || ''}`.trim()} />
              ) : null}
            </div>
          ) : null}
          <MetricGrid
            items={[
              { label: '司令部能力检查', value: state.commanderAudit?.all_passed ? '通过' : '部分缺失' },
              { label: '能力项数量', value: Array.isArray(state.commanderCapabilities?.specialists) ? state.commanderCapabilities.specialists.length : '-' },
              { label: '审计检查项', value: auditChecks.length },
              { label: 'API覆盖率', value: `${connected}/${coverageRows.length}` },
              { label: '运行时路由', value: routeSummary.total_routes ?? '-' },
              { label: '核心组件', value: componentRows.length ? `${componentRows.filter((x) => x.status === 'READY').length}/${componentRows.length}` : '-' },
              { label: '高优先级告警', value: priorityAlertRows.length },
            ]}
          />
          <InsightCard
            title="傻瓜式使用建议"
            content="先看覆盖率与联调结果；如果有“缺数据”，按诊断提示处理即可。不会代码也能排查问题。"
            tone="info"
          />
          <InsightCard
            title="执行归因一句话结论"
            content={attributionSummary || '暂无执行归因总结，先点击“刷新覆盖状态”或检查司令部快照是否可用。'}
            tone="normal"
          />
          <ActionList
            items={platformHumanized.next_actions?.length ? platformHumanized.next_actions.slice(0, 4) : [
              '点击“一键联调关键API”自动检测',
              '出现“链路超时”先检查网络/代理',
              '出现“鉴权失败”先检查交易所密钥',
            ]}
          />
          {oversightFocusRows.length ? (
            <>
              <div className="sub-title">平台总巡检焦点</div>
              <DataTable
                columns={[
                  { key: 'title', title: '焦点' },
                  { key: 'tone', title: '语气' },
                  { key: 'summary', title: '摘要' },
                ]}
                rows={oversightFocusRows}
                emptyText="暂无巡检焦点"
              />
            </>
          ) : null}
          {priorityAlertRows.length ? (
            <>
              <div className="sub-title">优先处理告警</div>
              <DataTable
                columns={[
                  { key: 'severity', title: '级别' },
                  { key: 'area', title: '区域' },
                  { key: 'title', title: '问题' },
                  { key: 'summary', title: '现象' },
                  { key: 'recommendation', title: '建议' },
                ]}
                rows={priorityAlertRows}
                emptyText="暂无高优先级告警"
              />
            </>
          ) : null}
          <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
            <button type="button" className="btn btn-sm btn-outline" onClick={actions.runApiSmokeTest}>
              一键联调关键API
            </button>
            <button type="button" className="btn btn-sm btn-outline" onClick={actions.refreshAll}>
              刷新覆盖状态
            </button>
          </div>
          <div className="sub-title">全链路 API 覆盖清单</div>
          <DataTable
            columns={[
              { key: 'module', title: '模块' },
              { key: 'item', title: '功能项' },
              { key: 'status', title: '状态' },
              { key: 'diagnose', title: '诊断' },
            ]}
            rows={coverageRows}
            emptyText="暂无覆盖清单"
          />
          {componentRows.length ? (
            <>
              <div className="sub-title" style={{ marginTop: 12 }}>核心组件与代码模块</div>
              <DataTable
                columns={[
                  { key: 'component', title: '组件' },
                  { key: 'status', title: '状态' },
                  { key: 'responsibility', title: '职责' },
                  { key: 'source_file', title: '代码位置' },
                ]}
                rows={componentRows}
                emptyText="暂无组件清单"
              />
            </>
          ) : null}
          {routeRows.length ? (
            <>
              <div className="sub-title" style={{ marginTop: 12 }}>运行时路由抽样</div>
              <DataTable
                columns={[
                  { key: 'path', title: '路径' },
                  { key: 'methods', title: '方法' },
                  { key: 'domain', title: '域' },
                  { key: 'file', title: '代码文件' },
                ]}
                rows={routeRows}
                emptyText="暂无路由清单"
              />
            </>
          ) : null}
          <div className="sub-title" style={{ marginTop: 12 }}>API 联调结果</div>
          <DataTable
            columns={[{ key: 'module', title: '模块' }, { key: 'endpoint', title: '接口路径' }, { key: 'status', title: '联调' }, { key: 'latency_ms', title: '耗时(ms)' }, { key: 'hint', title: '结果' }]}
            rows={smokeRows}
            emptyText="点击“一键联调关键API”开始验收"
          />
          <div className="sub-title" style={{ marginTop: 12 }}>标准工具契约清单（OpenClaw/MCP）</div>
          <DataTable
            columns={[
              { key: 'kind', title: '类型' },
              { key: 'path', title: '接口路径' },
            ]}
            rows={toolRows}
            emptyText="暂无工具契约数据"
          />
          <div className="sub-title" style={{ marginTop: 12 }}>治理审计流（最近变更）</div>
          <DataTable
            columns={[
              { key: 'ts', title: '时间' },
              { key: 'event', title: '变更事件' },
              { key: 'detail', title: '详情' },
            ]}
            rows={govAuditRows}
            emptyText="暂无治理审计记录"
          />
          <div className="sub-title" style={{ marginTop: 12 }}>执行归因（按严重级别排序）</div>
          <DataTable
            columns={[
              { key: 'severity', title: '级别' },
              { key: 'reason', title: '主因' },
              { key: 'category', title: '分类' },
              { key: 'count', title: '次数' },
              { key: 'hint', title: '处理建议' },
            ]}
            rows={attributionRows}
            emptyText="暂无执行归因数据"
          />
          <input className="form-input" value={commandInput} onChange={(e) => setCommandInput(e.target.value)} placeholder="发送司令部指令" />
          <button type="button" className="btn btn-sm btn-primary" style={{ marginTop: 8 }} onClick={actions.sendCommanderMessage}>
            发送指令
          </button>
          <pre style={{ maxHeight: 180, overflow: 'auto', fontSize: 11, background: 'var(--bg-secondary)', padding: 8, borderRadius: 8, marginTop: 8 }}>
{commandReply || '暂无回复'}
          </pre>
          <div className="sub-title" style={{ marginTop: 10 }}>司令部能力审计</div>
          <DataTable
            columns={[
              { key: 'name', title: '检查项' },
              { key: 'passed', title: '状态' },
              { key: 'detail', title: '说明' },
            ]}
            rows={auditRows}
            emptyText="暂无审计数据"
          />
          <JsonDetails title="高级原始数据：路由注册清单" value={state.surfaceRegistry} />
          <JsonDetails title="高级原始数据：数据集成健康" value={state.dataIntegrationHealth} />
          <JsonDetails title="高级原始数据：插件状态" value={state.pluginsStatus} />
          <JsonDetails title="高级原始数据：司令部快照" value={state.commanderSnapshot} />
          <JsonDetails title="高级原始数据：平台总巡检" value={state.platformOversight} />
          <JsonDetails title="高级原始数据：司令部能力" value={state.commanderCapabilities} />
        </div>
      </div>
      <div className="panel" style={{ gridColumn: 'span 2' }}>
        <div className="panel-header">
          <div className="panel-title">文档中心</div>
        </div>
        <div className="panel-body">
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
            {DOCS.map((doc) => (
              <button key={doc.id} type="button" className={`btn btn-sm ${doc.id === docId ? 'btn-primary' : 'btn-outline'}`} onClick={() => setDocId(doc.id)}>
                {doc.title}
              </button>
            ))}
            <button type="button" className="btn btn-sm btn-outline" onClick={loadDoc}>
              读取文档
            </button>
          </div>
          <div style={{ maxHeight: 620, overflow: 'auto' }}>
            <ReactMarkdown>{content || '点击“读取文档”加载内容。'}</ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  );
}
