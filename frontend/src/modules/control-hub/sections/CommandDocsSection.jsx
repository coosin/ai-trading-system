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
          <MetricGrid
            items={[
              { label: '司令部能力检查', value: state.commanderAudit?.all_passed ? '通过' : '部分缺失' },
              { label: '能力项数量', value: Array.isArray(state.commanderCapabilities?.specialists) ? state.commanderCapabilities.specialists.length : '-' },
              { label: '审计检查项', value: auditChecks.length },
              { label: 'API覆盖率', value: `${connected}/${coverageRows.length}` },
            ]}
          />
          <InsightCard
            title="傻瓜式使用建议"
            content="先看覆盖率与联调结果；如果有“缺数据”，按诊断提示处理即可。不会代码也能排查问题。"
            tone="info"
          />
          <ActionList
            items={[
              '点击“一键联调关键API”自动检测',
              '出现“链路超时”先检查网络/代理',
              '出现“鉴权失败”先检查交易所密钥',
            ]}
          />
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
