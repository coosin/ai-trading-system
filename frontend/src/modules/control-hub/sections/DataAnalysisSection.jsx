import React from 'react';
import { ActionList, DataTable, InsightCard, JsonDetails, MetricGrid, MiniKline, ProcessSteps } from '../components/UiBlocks';

export default function DataAnalysisSection({ state, view, updatedAt, actions, loading }) {
  const metrics = [
    { label: '最新价', value: view.tickerPrice },
    { label: '买一/卖一', value: `${view.tickerBid} / ${view.tickerAsk}` },
    { label: '点差', value: view.spread != null ? Number(view.spread).toFixed(4) : '-' },
    {
      label: '数据源',
      value: state.dataHubStatus?.提供者 || state.dataHubStatus?.provider || '-',
      hint: state.dataHubStatus?.模块 || state.dataHubStatus?.module || '',
    },
  ];
  const bids = (view.orderbookLevels?.bids || []).map((x, idx) => ({ id: `b-${idx}`, price: x[0], size: x[1] }));
  const asks = (view.orderbookLevels?.asks || []).map((x, idx) => ({ id: `a-${idx}`, price: x[0], size: x[1] }));
  const maxDepth = Math.max(
    ...bids.map((r) => Number(r.size) || 0),
    ...asks.map((r) => Number(r.size) || 0),
    1,
  );
  const depthRows = [...asks.slice().reverse(), ...bids].map((r) => ({
    ...r,
    ratio: Math.min(100, Math.round(((Number(r.size) || 0) / maxDepth) * 100)),
  }));
  const sources = Array.isArray(state.fusionSources?.available_sources)
    ? state.fusionSources.available_sources.join(', ')
    : Array.isArray(state.fusionSources?.supported_exchanges)
      ? state.fusionSources.supported_exchanges.join(', ')
      : '-';
  const trend = view.marketSymbolView?.trend || view.marketSymbolView?.summary || '暂无明确趋势信号';
  const klineRows = Array.isArray(state.klines) ? state.klines : Array.isArray(state.klines?.data) ? state.klines.data : [];
  const klineClose = klineRows.map((x) => (Array.isArray(x) ? x[4] : x?.close));
  const processRows = [
    {
      id: 'p1',
      title: '行情输入',
      desc: `最新价 ${view.tickerPrice}，买一 ${view.tickerBid}，卖一 ${view.tickerAsk}`,
      ok: view.tickerPrice !== '-',
    },
    {
      id: 'p2',
      title: '质量评估',
      desc: `数据质量分 ${view.analysisProcess?.qualityScore}，数据源 ${sources}`,
      ok: view.analysisProcess?.qualityScore !== '-',
    },
    {
      id: 'p3',
      title: '模型判断',
      desc: `趋势 ${view.analysisProcess?.trend}，置信度 ${view.analysisProcess?.confidence}`,
      ok: view.analysisProcess?.trend !== '-',
    },
    {
      id: 'p4',
      title: '输出信号',
      desc: `分析信号 ${view.analysisProcess?.signal}`,
      ok: view.analysisProcess?.signal !== '-',
    },
  ];
  const closeNums = klineClose.map((v) => Number(v)).filter((v) => Number.isFinite(v));
  const latestClose = closeNums.length ? closeNums[closeNums.length - 1] : null;
  const prevClose = closeNums.length > 1 ? closeNums[closeNums.length - 2] : null;
  const change = latestClose != null && prevClose != null && prevClose !== 0 ? ((latestClose - prevClose) / prevClose) * 100 : null;
  const high = closeNums.length ? Math.max(...closeNums) : null;
  const low = closeNums.length ? Math.min(...closeNums) : null;
  const bidSum = bids.reduce((s, x) => s + Number(x.size || 0), 0);
  const askSum = asks.reduce((s, x) => s + Number(x.size || 0), 0);
  const imbalance = bidSum + askSum > 0 ? ((bidSum - askSum) / (bidSum + askSum)) * 100 : null;
  const klineTableRows = klineRows.slice(-12).map((row, idx) => {
    const arr = Array.isArray(row) ? row : [];
    return {
      id: idx,
      t: arr[0] || row?.t || row?.timestamp || '-',
      o: arr[1] || row?.open || '-',
      h: arr[2] || row?.high || '-',
      l: arr[3] || row?.low || '-',
      c: arr[4] || row?.close || '-',
      v: arr[5] || row?.volume || '-',
    };
  });

  return (
    <div className="panel section-panel" style={{ marginTop: 16 }}>
      <div className="panel-header">
        <div className="panel-title">数据分析与实时行情</div>
      </div>
      <div className="panel-body">
        <MetricGrid items={metrics} />
        <InsightCard
          title="智能行情结论"
          content={`当前行情判断：${trend}。点差 ${view.spread != null ? Number(view.spread).toFixed(4) : '-'}，可用数据源：${sources || '-'}`}
          tone="info"
        />
        <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
          <button type="button" className="btn btn-sm btn-outline" onClick={actions.loadFast} disabled={loading.fast}>
            {loading.fast ? '刷新中' : '刷新行情'}
          </button>
          <button type="button" className="btn btn-sm btn-outline" onClick={actions.loadMedium} disabled={loading.medium}>
            {loading.medium ? '刷新中' : '刷新分析'}
          </button>
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
            行情更新时间: {updatedAt.fast || '-'} · 分析更新时间: {updatedAt.medium || '-'}
          </span>
        </div>
        <ActionList
          items={[
            '若点差持续扩大，请降低开仓频率并观察 1-3 分钟',
            '盘口买卖深度失衡时，优先小仓位试单',
            '若数据源缺失，请到“指挥与文档”页一键联调',
          ]}
        />
        <div className="sub-title">分析过程链路（可视化）</div>
        <ProcessSteps rows={processRows} />
        <div className="sub-title" style={{ marginTop: 12 }}>专业行情指标</div>
        <MetricGrid
          items={[
            { label: '短周期涨跌幅', value: change != null ? `${change.toFixed(2)}%` : '-' },
            { label: '近期最高/最低', value: high != null && low != null ? `${high} / ${low}` : '-' },
            { label: '买卖深度总量', value: `${bidSum.toFixed(2)} / ${askSum.toFixed(2)}` },
            { label: '深度失衡度', value: imbalance != null ? `${imbalance.toFixed(2)}%` : '-' },
          ]}
        />
        <div className="sub-title" style={{ marginTop: 12 }}>K线走势微图（最近40根）</div>
        <MiniKline values={klineClose} />
        <div className="sub-title" style={{ marginTop: 12 }}>最近K线明细（12根）</div>
        <DataTable
          columns={[
            { key: 't', title: '时间' },
            { key: 'o', title: '开' },
            { key: 'h', title: '高' },
            { key: 'l', title: '低' },
            { key: 'c', title: '收' },
            { key: 'v', title: '量' },
          ]}
          rows={klineTableRows}
          emptyText="暂无K线细节"
        />
        <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 8 }}>
          数据源: {state.dataHubStatus?.提供者 || state.dataHubStatus?.provider || '-'} ·
          可用渠道: {sources}
        </div>

        <div className="table-grid-two">
          <div>
            <div className="sub-title">买盘深度 Top10</div>
            <DataTable columns={[{ key: 'price', title: '价格' }, { key: 'size', title: '数量' }]} rows={bids} />
          </div>
          <div>
            <div className="sub-title">卖盘深度 Top10</div>
            <DataTable columns={[{ key: 'price', title: '价格' }, { key: 'size', title: '数量' }]} rows={asks} />
          </div>
        </div>
        <div className="sub-title" style={{ marginTop: 12 }}>深度热力视图（Top20）</div>
        <div className="depth-list">
          {depthRows.map((row) => (
            <div className="depth-row" key={row.id}>
              <div className="depth-price">{row.price}</div>
              <div className="depth-bar-wrap">
                <div className="depth-bar" style={{ width: `${row.ratio}%` }} />
              </div>
              <div className="depth-size">{row.size}</div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 10, fontWeight: 700 }}>高级原始数据（可选查看）</div>
        <JsonDetails title="融合分析原始详情" value={state.fusion || {}} />
        <JsonDetails title="统一快照原始详情" value={state.dataHubSnapshot} />
        <JsonDetails title="质量评分原始详情" value={state.qualityAdvice} />
        <JsonDetails title="AI分析原始详情" value={state.aiAnalysis} />
        <JsonDetails title="行情判断原始详情" value={view.marketSymbolView} />
      </div>
    </div>
  );
}
