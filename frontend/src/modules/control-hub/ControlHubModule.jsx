import React, { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { api } from '../../services/api';
import { toCnFieldKey, toCnRiskLevel, toCnSignal, toCnStrategy, translateReasoning } from '../../utils/cnFormatter';

const DOC_LOADERS = import.meta.glob('../../../../docs/**/*.md', { query: '?raw', import: 'default' });

function ControlHubModule() {
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  const [health, setHealth] = useState(null);
  const [s1, setS1] = useState(null);
  const [guards, setGuards] = useState(null);
  const [sltpStats, setSltpStats] = useState(null);
  const [tradeHistory, setTradeHistory] = useState([]);
  const [monitorLogs, setMonitorLogs] = useState([]);

  const [docQuery, setDocQuery] = useState('');
  const [selectedDocId, setSelectedDocId] = useState('control-hub-user-manual');
  const [docContents, setDocContents] = useState({});
  const [docLoading, setDocLoading] = useState(false);

  const showNotice = (message, type = 'success') => {
    setNotice({ message, type });
    window.setTimeout(() => setNotice(null), 2500);
  };

  const docsCatalog = useMemo(() => ([
    { id: 'control-hub-user-manual', title: '总控中心操作手册', group: '总控', path: '../../../../docs/control-hub-user-manual.md' },
    { id: 'control-hub-module-checklist', title: '总控功能清单', group: '总控', path: '../../../../docs/control-hub-module-checklist.md' },
    { id: 'dynamic-open-close', title: '动态开平仓与SLTP手册', group: '交易', path: '../../../../docs/dynamic-open-close-and-sltp-playbook.md' },
    { id: 'maintenance-guide', title: '维护指南', group: '运维', path: '../../../../docs/MAINTENANCE_GUIDE.md' },
    { id: 'api-doc', title: 'API 文档', group: '接口', path: '../../../../docs/api.md' },
  ]), []);

  const filteredDocs = useMemo(() => {
    const q = docQuery.trim().toLowerCase();
    if (!q) return docsCatalog;
    return docsCatalog.filter((d) => `${d.title} ${d.group} ${d.id}`.toLowerCase().includes(q));
  }, [docsCatalog, docQuery]);

  const selectedDoc = useMemo(() => {
    return docsCatalog.find((d) => d.id === selectedDocId) || filteredDocs[0] || docsCatalog[0];
  }, [docsCatalog, filteredDocs, selectedDocId]);

  const selectedDocContent = useMemo(() => {
    if (!selectedDoc?.id) return '';
    return docContents[selectedDoc.id] || '';
  }, [selectedDoc, docContents]);

  useEffect(() => {
    let cancelled = false;
    const loadDoc = async () => {
      if (!selectedDoc?.id || !selectedDoc?.path) return;
      if (docContents[selectedDoc.id]) return;
      const loader = DOC_LOADERS[selectedDoc.path];
      if (!loader) {
        if (!cancelled) setDocContents((prev) => ({ ...prev, [selectedDoc.id]: '文档加载失败：未找到文件映射。' }));
        return;
      }
      setDocLoading(true);
      try {
        const raw = await loader();
        if (!cancelled) setDocContents((prev) => ({ ...prev, [selectedDoc.id]: String(raw || '') }));
      } catch {
        if (!cancelled) setDocContents((prev) => ({ ...prev, [selectedDoc.id]: '文档加载失败：读取异常。' }));
      } finally {
        if (!cancelled) setDocLoading(false);
      }
    };
    loadDoc();
    return () => { cancelled = true; };
  }, [selectedDoc, docContents]);

  const refresh = async () => {
    setLoading(true);
    try {
      const [healthRes, s1Res, guardsRes, sltpRes, histRes, logsRes] = await Promise.all([
        api.request('/modules/system/health').catch(() => null),
        api.request('/s1/verify').catch(() => null),
        api.request('/modules/ai/guards').catch(() => null),
        api.request('/modules/stop-loss/stats').catch(() => null),
        api.trading.getHistory({ limit: 10 }).catch(() => []),
        api.monitoring?.getLogs ? api.monitoring.getLogs({ limit: 20 }).catch(() => []) : Promise.resolve([]),
      ]);
      setHealth(healthRes);
      setS1(s1Res);
      setGuards(guardsRes);
      setSltpStats(sltpRes);
      setTradeHistory(Array.isArray(histRes?.data) ? histRes.data : Array.isArray(histRes) ? histRes : []);
      setMonitorLogs(Array.isArray(logsRes?.data) ? logsRes.data : Array.isArray(logsRes) ? logsRes : []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const alerts = useMemo(() => {
    const a = [];
    if (health?.overall && String(health.overall).toLowerCase() !== 'healthy') a.push(`系统健康异常: ${health.overall}`);
    if (s1 && s1.all_passed === false) a.push('S1 执行链路未通过');
    if ((guards?.stats?.data_quality_guard_hold || 0) > 10) a.push(`数据质量拦截偏高: ${guards.stats.data_quality_guard_hold}`);
    (monitorLogs || []).slice(0, 4).forEach((l) => {
      const msg = String(l?.message || '');
      if (msg) a.push(`日志: ${msg.slice(0, 120)}`);
    });
    return a.slice(0, 12);
  }, [health, s1, guards, monitorLogs]);

  return (
    <div style={{ padding: 16 }}>
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title"><span className="panel-title-icon">🎛️</span>智能总控中心</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-sm btn-outline" onClick={refresh}>{loading ? '刷新中...' : '刷新'}</button>
            <button className="btn btn-sm btn-outline" onClick={() => showNotice('已保存（本地）')}>保存</button>
          </div>
        </div>
        <div className="panel-body">
          <div className="tabs">
            {[
              { id: 'overview', label: '总览' },
              { id: 'alerts', label: '告警' },
              { id: 'execution', label: '执行' },
              { id: 'docs', label: '文档' },
            ].map((t) => (
              <div key={t.id} className={`tab ${activeTab === t.id ? 'active' : ''}`} onClick={() => setActiveTab(t.id)}>
                {t.label}
              </div>
            ))}
          </div>
        </div>
      </div>

      {activeTab === 'overview' && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header"><div className="panel-title">系统状态</div></div>
          <div className="panel-body">
            <div className="market-stats">
              <div className="market-stat-item"><div className="market-stat-label">健康</div><div className="market-stat-value">{health?.overall || '-'}</div></div>
              <div className="market-stat-item"><div className="market-stat-label">S1链路</div><div className="market-stat-value">{s1?.all_passed ? '通过' : '待检查'}</div></div>
              <div className="market-stat-item"><div className="market-stat-label">数据质量拒绝</div><div className="market-stat-value">{guards?.stats?.data_quality_guard_hold ?? 0}</div></div>
              <div className="market-stat-item"><div className="market-stat-label">SLTP动态</div><div className="market-stat-value">{sltpStats?.stats?.dynamic_adjustments ?? 0}</div></div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'alerts' && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header"><div className="panel-title">告警（中文化）</div></div>
          <div className="panel-body">
            {alerts.length ? alerts.map((x, i) => <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid var(--border-light)' }}>⚠️ {x}</div>) : <div style={{ color: 'var(--text-tertiary)' }}>暂无告警</div>}
          </div>
        </div>
      )}

      {activeTab === 'execution' && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header"><div className="panel-title">最近执行（中文化）</div></div>
          <div className="panel-body">
            {(tradeHistory || []).slice(0, 10).map((t, i) => (
              <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid var(--border-light)' }}>
                <div style={{ fontWeight: 600 }}>{t.symbol || '-'} · {toCnSignal(t.side)} · {t.price ?? '-'} · {t.quantity ?? '-'}</div>
                <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                  {toCnFieldKey('reasoning')}: {translateReasoning(t.reasoning || t.reason || '')} · {toCnFieldKey('strategy')}: {toCnStrategy(t.strategy || t.strategy_name)} · {toCnFieldKey('risk_level')}: {toCnRiskLevel(t.risk_level)}
                </div>
              </div>
            ))}
            {!tradeHistory?.length && <div style={{ color: 'var(--text-tertiary)' }}>暂无交易历史</div>}
          </div>
        </div>
      )}

      {activeTab === 'docs' && (
        <div className="panel-row" style={{ marginTop: 16 }}>
          <div className="panel">
            <div className="panel-header"><div className="panel-title">文档导航</div></div>
            <div className="panel-body">
              <input className="form-input" placeholder="搜索文档" value={docQuery} onChange={(e) => setDocQuery(e.target.value)} style={{ marginBottom: 10 }} />
              {filteredDocs.map((d) => (
                <div
                  key={d.id}
                  onClick={() => setSelectedDocId(d.id)}
                  style={{ cursor: 'pointer', padding: '8px 10px', borderRadius: 8, marginBottom: 6, border: '1px solid var(--border-light)', background: selectedDoc?.id === d.id ? 'var(--bg-secondary)' : 'transparent' }}
                >
                  <div style={{ fontWeight: 600 }}>{d.title}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{d.group}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="panel" style={{ gridColumn: 'span 2' }}>
            <div className="panel-header"><div className="panel-title">{selectedDoc?.title}</div></div>
            <div className="panel-body">
              {docLoading && !selectedDocContent ? (
                <div style={{ color: 'var(--text-tertiary)' }}>文档加载中...</div>
              ) : (
                <div style={{ maxHeight: 620, overflow: 'auto' }}>
                  <ReactMarkdown>{selectedDocContent || '暂无文档内容'}</ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {notice && (
        <div style={{ position: 'fixed', top: '84px', right: '24px', padding: '10px 14px', borderRadius: '8px', color: '#fff', zIndex: 9999, background: notice.type === 'error' ? 'var(--error-color)' : 'var(--success-color)' }}>
          {notice.message}
        </div>
      )}
    </div>
  );
}

export default ControlHubModule;

