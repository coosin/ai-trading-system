export function toCnSignal(signal) {
  const s = String(signal || '').toLowerCase();
  if (s === 'buy') return '买入';
  if (s === 'sell') return '卖出';
  if (s === 'hold') return '观望';
  if (s === 'long') return '做多';
  if (s === 'short') return '做空';
  return signal || '-';
}

export function toCnRiskLevel(level) {
  const s = String(level || '').toLowerCase();
  if (s === 'low') return '低';
  if (s === 'medium') return '中';
  if (s === 'high') return '高';
  return level || '-';
}

export function toCnStrategy(name) {
  const s = String(name || '');
  const map = {
    default_trend_following_ma: '默认趋势跟随均线策略',
    volatility_breakout: '波动突破策略',
    scalp_reversion: '剥头皮回归策略',
    pinbar_reversal: '抓针反转策略',
  };
  return map[s] || s || '-';
}

export function translateReasoning(text) {
  const src = String(text || '');
  if (!src) return '-';
  return src
    .replaceAll('hold_avoidance_override', '避免空转观望增强规则')
    .replaceAll('fusion_conf', '融合置信度')
    .replaceAll('fusion_sent', '融合情绪值')
    .replaceAll('tech_trend_1h', '1小时技术趋势')
    .replaceAll('bullish', '看涨')
    .replaceAll('bearish', '看跌')
    .replaceAll('neutral', '中性');
}

export function toCnFieldKey(key) {
  const map = {
    signal: '信号',
    confidence: '置信度',
    reasoning: '决策理由',
    strategy: '策略',
    strategy_name: '策略名称',
    risk_level: '风险等级',
    leverage: '杠杆',
    stop_loss: '止损',
    take_profit: '止盈',
    side: '方向',
    action: '操作',
    symbol: '交易对',
    price: '价格',
    quantity: '数量',
    timestamp: '时间',
  };
  return map[key] || key;
}

