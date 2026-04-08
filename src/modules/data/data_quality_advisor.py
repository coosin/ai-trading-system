"""
数据质量与作用评分顾问（插件化风格）。

功能：
1) 对统一快照进行质量评分与有效性评分
2) 维护短期历史窗口，评估稳定性与可用性趋势
3) 生成可执行的优化建议
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional


@dataclass
class DataQualityAdviceResult:
    symbol: str
    timestamp: str
    quality_score: float
    effectiveness_score: float
    stability_score: float
    confidence: float
    grade: str
    suggestions: List[str]
    diagnostics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "quality_score": self.quality_score,
            "effectiveness_score": self.effectiveness_score,
            "stability_score": self.stability_score,
            "confidence": self.confidence,
            "grade": self.grade,
            "suggestions": self.suggestions,
            "diagnostics": self.diagnostics,
        }


class DataQualityAdvisor:
    """对数据质量和历史表现给出评分与建议。"""

    def __init__(self, window_size: int = 60):
        self.window_size = max(20, int(window_size))
        self._quality_hist: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=self.window_size))
        self._effect_hist: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=self.window_size))

    @staticmethod
    def _safe_float(v: Any, default: float = 0.0) -> float:
        try:
            return float(v)
        except Exception:
            return default

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 0.85:
            return "A"
        if score >= 0.7:
            return "B"
        if score >= 0.5:
            return "C"
        return "D"

    def evaluate(self, symbol: str, snapshot: Dict[str, Any]) -> DataQualityAdviceResult:
        now = datetime.now().isoformat()
        q = (snapshot.get("数据质量评估") or {}) if isinstance(snapshot, dict) else {}
        q_score = self._safe_float(q.get("score"), 0.0)

        channel_a = snapshot.get("渠道A_交易所实时执行数据") or {}
        channel_b = snapshot.get("渠道B_链上新闻舆情数据") or {}
        analysis = snapshot.get("统一分析判断") or {}

        # 作用评分：衡量这份数据对“可交易决策”的支持程度
        has_price = self._safe_float((channel_a.get("ticker") or {}).get("price"), 0.0) > 0
        has_orderbook = bool((channel_a.get("order_book") or {}).get("bids"))
        has_position_info = isinstance(channel_a.get("positions"), list)
        has_signal = bool(analysis.get("recommendation") or analysis.get("trend"))
        has_intel = bool((channel_b.get("sentiment") or {}) or (channel_b.get("onchain") or {}))
        effect_score = (
            (0.25 if has_price else 0.0)
            + (0.2 if has_orderbook else 0.0)
            + (0.15 if has_position_info else 0.0)
            + (0.2 if has_signal else 0.0)
            + (0.2 if has_intel else 0.0)
        )

        self._quality_hist[symbol].append(q_score)
        self._effect_hist[symbol].append(effect_score)

        q_hist = list(self._quality_hist[symbol])
        e_hist = list(self._effect_hist[symbol])
        q_avg = sum(q_hist) / max(1, len(q_hist))
        e_avg = sum(e_hist) / max(1, len(e_hist))

        # 稳定性：最近窗口方差越小越稳定
        q_var = sum((x - q_avg) ** 2 for x in q_hist) / max(1, len(q_hist))
        stability = max(0.0, min(1.0, 1.0 - min(1.0, q_var * 6.0)))

        # 综合置信：质量均值 + 作用均值 + 稳定性
        confidence = max(0.0, min(1.0, 0.45 * q_avg + 0.35 * e_avg + 0.20 * stability))
        grade = self._grade(confidence)

        suggestions: List[str] = []
        if not has_orderbook:
            suggestions.append("补强订单簿深度采集，提升开平仓时机判断精度。")
        if not has_intel:
            suggestions.append("链上/舆情通道数据不足，建议检查第三方数据源可用性。")
        if q_score < 0.5:
            suggestions.append("当前数据质量偏低，建议降杠杆并缩小仓位。")
        if stability < 0.6:
            suggestions.append("数据稳定性波动较大，建议提高缓存与重试策略。")
        if effect_score < 0.6:
            suggestions.append("数据对交易决策支撑不足，建议完善信号特征与执行反馈回灌。")
        if not suggestions:
            suggestions.append("数据质量与作用表现良好，可维持当前策略节奏并持续监控。")

        diagnostics = {
            "has_price": has_price,
            "has_orderbook": has_orderbook,
            "has_position_info": has_position_info,
            "has_signal": has_signal,
            "has_intel": has_intel,
            "quality_current": q_score,
            "quality_avg": q_avg,
            "effectiveness_avg": e_avg,
            "quality_variance": q_var,
            "window_size": len(q_hist),
        }

        return DataQualityAdviceResult(
            symbol=symbol,
            timestamp=now,
            quality_score=round(q_score, 4),
            effectiveness_score=round(effect_score, 4),
            stability_score=round(stability, 4),
            confidence=round(confidence, 4),
            grade=grade,
            suggestions=suggestions,
            diagnostics=diagnostics,
        )
