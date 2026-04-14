import React from 'react';

export function StatusBadge({ ok, text }) {
  return <span className={`status-badge ${ok ? 'ok' : 'bad'}`}>{text}</span>;
}

export function MetricGrid({ items }) {
  return (
    <div className="metric-grid">
      {items.map((item) => (
        <div className="metric-card" key={item.label}>
          <div className="metric-label">{item.label}</div>
          <div className="metric-value">{item.value}</div>
          {item.hint ? <div className="metric-hint">{item.hint}</div> : null}
        </div>
      ))}
    </div>
  );
}

export function DataTable({ columns, rows, emptyText = '暂无数据' }) {
  return (
    <div className="table-wrap">
      <table className="pro-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key}>{col.title}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row, idx) => (
              <tr key={row.id || idx}>
                {columns.map((col) => (
                  <td key={`${idx}-${col.key}`}>{row[col.key] ?? '-'}</td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={columns.length} className="table-empty">{emptyText}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function JsonDetails({ title, value }) {
  return (
    <details className="json-details">
      <summary>{title}</summary>
      <pre>{JSON.stringify(value ?? {}, null, 2)}</pre>
    </details>
  );
}

export function InsightCard({ title, content, tone = 'normal' }) {
  return (
    <div className={`insight-card ${tone}`}>
      <div className="insight-title">{title}</div>
      <div className="insight-content">{content}</div>
    </div>
  );
}

export function ActionList({ items = [] }) {
  return (
    <div className="action-list">
      {items.map((item, idx) => (
        <div className="action-item" key={item + idx}>
          <span className="action-index">{idx + 1}</span>
          <span>{item}</span>
        </div>
      ))}
    </div>
  );
}

export function ProcessSteps({ rows = [], emptyText = '暂无过程数据' }) {
  if (!rows.length) {
    return <div className="table-empty" style={{ border: '1px solid var(--border-light)', borderRadius: 10 }}>{emptyText}</div>;
  }
  return (
    <div className="process-steps">
      {rows.map((row, idx) => (
        <div className="process-step" key={row.id || idx}>
          <div className="process-dot">{idx + 1}</div>
          <div className="process-main">
            <div className="process-title">{row.title}</div>
            <div className="process-desc">{row.desc}</div>
          </div>
          <div className={`process-status ${row.ok ? 'ok' : 'bad'}`}>{row.ok ? '正常' : '待确认'}</div>
        </div>
      ))}
    </div>
  );
}

export function MiniKline({ values = [] }) {
  const nums = values.map((v) => Number(v)).filter((v) => Number.isFinite(v));
  if (!nums.length) return <div className="table-empty">暂无K线数据</div>;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = Math.max(max - min, 1e-9);
  const bars = nums.slice(-40).map((v, i) => ({
    id: i,
    h: Math.max(8, Math.round(((v - min) / span) * 44) + 8),
  }));
  return (
    <div className="mini-kline">
      {bars.map((b) => (
        <div key={b.id} className="mini-kline-bar" style={{ height: `${b.h}px` }} />
      ))}
    </div>
  );
}
