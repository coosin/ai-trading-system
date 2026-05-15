from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from .derivatives_structure_analyzer import DerivativesStructureAnalyzer
from .liquidity_stress_detector import LiquidityStressDetector
from .regime_classifier import RegimeClassifier
from .stablecoin_flow_analyzer import StablecoinFlowAnalyzer


@dataclass
class MarketStructureSnapshot:
    symbol: str
    regime_label: str = "unknown"
    risk_posture: str = "neutral"
    avoid_symbols: List[str] = field(default_factory=list)
    preferred_setups: List[str] = field(default_factory=list)
    trend_state: str = "unknown"
    volatility_state: str = "unknown"
    liquidity_state: str = "unknown"
    derivatives_state: str = "unknown"
    stablecoin_flow_state: str = "unknown"
    execution_quality_state: str = "unknown"
    signal_conflict_score: float = 0.0
    confidence: float = 0.0
    inputs: Dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MarketStructureEngine:
    """
    Lightweight market-structure classifier.

    v1 goal:
    - derive stable, explainable structure labels from existing symbol snapshots
    - avoid extra network calls
    - expose outputs to diagnosis / traces / later agent orchestration
    """

    def __init__(self) -> None:
        self.stablecoin_flow_analyzer = StablecoinFlowAnalyzer()
        self.derivatives_structure_analyzer = DerivativesStructureAnalyzer()
        self.liquidity_stress_detector = LiquidityStressDetector()
        self.regime_classifier = RegimeClassifier()

    def analyze_symbol(
        self,
        symbol: str,
        snapshot: Optional[Dict[str, Any]] = None,
        *,
        execution_quality_state: Optional[str] = None,
    ) -> MarketStructureSnapshot:
        data = dict(snapshot or {})
        trend = str(data.get("trend") or data.get("trend_state") or "unknown").lower()
        confidence = self._safe_float(data.get("confidence"), 0.0)
        volatility = self._safe_float(
            data.get("atr_pct_1h", data.get("volatility", data.get("volatility_score", 0.0))),
            0.0,
        )
        quality = self._safe_float(data.get("quality_score"), 0.0)

        liquidity_view = self.liquidity_stress_detector.analyze(data)
        derivatives_view = self.derivatives_structure_analyzer.analyze(data)
        stablecoin_view = self.stablecoin_flow_analyzer.analyze(data)
        spread_bps = self._safe_float(liquidity_view.get("spread_bps"), 0.0)
        depth_imbalance = self._safe_float(liquidity_view.get("depth_imbalance"), 0.0)
        funding_rate = self._safe_float(derivatives_view.get("funding_rate"), 0.0)
        open_interest = self._safe_float(derivatives_view.get("open_interest"), 0.0)
        stablecoin_flow = self._safe_float(stablecoin_view.get("stablecoin_flow_score"), 0.0)

        volatility_state = self._classify_volatility(volatility)
        liquidity_state = str(liquidity_view.get("liquidity_state") or self._classify_liquidity(spread_bps, depth_imbalance, quality))
        derivatives_state = str(derivatives_view.get("derivatives_state") or self._classify_derivatives(funding_rate, open_interest))
        stablecoin_state = str(stablecoin_view.get("stablecoin_flow_state") or self._classify_stablecoin_flow(stablecoin_flow))
        trend_state = self._classify_trend(trend, confidence)
        regime_label = str(self.regime_classifier.classify(
            {
                "trend_state": trend_state,
                "volatility_state": volatility_state,
                "liquidity_state": liquidity_state,
                "derivatives_state": derivatives_state,
            }
        ).get("regime_label") or self._classify_regime(
            trend_state=trend_state,
            volatility_state=volatility_state,
            liquidity_state=liquidity_state,
            derivatives_state=derivatives_state,
        ))
        risk_posture = self._classify_risk_posture(
            regime_label=regime_label,
            liquidity_state=liquidity_state,
            volatility_state=volatility_state,
            derivatives_state=derivatives_state,
            confidence=confidence,
        )

        signal_conflict_score = 0.0
        if trend_state == "range" and regime_label.startswith("trend"):
            signal_conflict_score += 0.45
        if liquidity_state == "stressed":
            signal_conflict_score += 0.25
        if derivatives_state in {"overheated_long", "overheated_short"}:
            signal_conflict_score += 0.2
        if confidence < 0.45:
            signal_conflict_score += 0.2
        signal_conflict_score = round(min(max(signal_conflict_score, 0.0), 1.0), 4)
        preferred_setups = self._infer_preferred_setups(
            regime_label=regime_label,
            trend_state=trend_state,
            volatility_state=volatility_state,
            liquidity_state=liquidity_state,
            derivatives_state=derivatives_state,
            stablecoin_state=stablecoin_state,
        )
        avoid_symbols = [str(symbol or data.get("symbol") or "unknown")] if (
            liquidity_state == "stressed"
            or risk_posture == "capital_preservation"
            or signal_conflict_score >= 0.75
        ) else []

        return MarketStructureSnapshot(
            symbol=str(symbol or data.get("symbol") or "unknown"),
            regime_label=regime_label,
            risk_posture=risk_posture,
            avoid_symbols=avoid_symbols,
            preferred_setups=preferred_setups,
            trend_state=trend_state,
            volatility_state=volatility_state,
            liquidity_state=liquidity_state,
            derivatives_state=derivatives_state,
            stablecoin_flow_state=stablecoin_state,
            execution_quality_state=str(execution_quality_state or data.get("execution_quality_state") or "unknown"),
            signal_conflict_score=signal_conflict_score,
            confidence=round(confidence, 4),
            inputs={
                "spread_bps": spread_bps,
                "depth_imbalance": depth_imbalance,
                "funding_rate": funding_rate,
                "open_interest": open_interest,
                "stablecoin_flow_score": stablecoin_flow,
                "quality_score": quality,
                "liquidity_stress_score": liquidity_view.get("liquidity_stress_score"),
                "basis_bps": derivatives_view.get("basis_bps"),
            },
        )

    def summarize(self, rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        snapshots: List[Dict[str, Any]] = []
        by_regime: Dict[str, int] = {}
        by_posture: Dict[str, int] = {}
        risky: List[str] = []

        for row in rows:
            snap = self.analyze_symbol(str((row or {}).get("symbol") or "unknown"), row).to_dict()
            snapshots.append(snap)
            regime = str(snap.get("regime_label") or "unknown")
            posture = str(snap.get("risk_posture") or "unknown")
            by_regime[regime] = int(by_regime.get(regime, 0)) + 1
            by_posture[posture] = int(by_posture.get(posture, 0)) + 1
            if posture in {"defensive", "capital_preservation"}:
                risky.append(str(snap.get("symbol") or "unknown"))

        return {
            "sample_size": len(snapshots),
            "by_regime": by_regime,
            "by_risk_posture": by_posture,
            "risky_symbols": risky[:12],
            "samples": snapshots[:12],
        }

    def _classify_trend(self, trend: str, confidence: float) -> str:
        if trend in {"bull", "bullish", "up"} and confidence >= 0.55:
            return "uptrend"
        if trend in {"bear", "bearish", "down"} and confidence >= 0.55:
            return "downtrend"
        if trend in {"sideways", "neutral", "range", "ranging"}:
            return "range"
        if confidence < 0.4:
            return "uncertain"
        return "mixed"

    def _classify_volatility(self, volatility: float) -> str:
        if volatility >= 0.06:
            return "extreme"
        if volatility >= 0.03:
            return "elevated"
        if volatility >= 0.012:
            return "normal"
        return "compressed"

    def _classify_liquidity(self, spread_bps: float, depth_imbalance: float, quality: float) -> str:
        if spread_bps >= 18 or quality < 0.4:
            return "stressed"
        if spread_bps >= 8 or abs(depth_imbalance) >= 0.55:
            return "fragile"
        if spread_bps > 0:
            return "healthy"
        return "unknown"

    def _classify_derivatives(self, funding_rate: float, open_interest: float) -> str:
        if funding_rate >= 0.003:
            return "overheated_long"
        if funding_rate <= -0.003:
            return "overheated_short"
        if open_interest <= 0:
            return "unknown"
        if open_interest < 250000:
            return "thin"
        return "balanced"

    def _classify_stablecoin_flow(self, score: float) -> str:
        if score >= 0.45:
            return "risk_on_inflow"
        if score <= -0.45:
            return "risk_off_outflow"
        if score != 0.0:
            return "neutral_flow"
        return "unknown"

    def _classify_regime(
        self,
        *,
        trend_state: str,
        volatility_state: str,
        liquidity_state: str,
        derivatives_state: str,
    ) -> str:
        if liquidity_state == "stressed":
            return "liquidity_stress"
        if volatility_state == "extreme":
            return "high_volatility"
        if trend_state == "uptrend":
            return "trend_up"
        if trend_state == "downtrend":
            return "trend_down"
        if derivatives_state in {"overheated_long", "overheated_short"}:
            return "crowded_derivatives"
        if volatility_state == "compressed":
            return "volatility_compression"
        if trend_state == "range":
            return "range_bound"
        return "mixed"

    def _classify_risk_posture(
        self,
        *,
        regime_label: str,
        liquidity_state: str,
        volatility_state: str,
        derivatives_state: str,
        confidence: float,
    ) -> str:
        if liquidity_state == "stressed" or volatility_state == "extreme":
            return "capital_preservation"
        if regime_label in {"crowded_derivatives", "high_volatility"} or derivatives_state.startswith("overheated"):
            return "defensive"
        if confidence < 0.45:
            return "cautious"
        if regime_label in {"trend_up", "trend_down"} and liquidity_state == "healthy":
            return "offensive"
        return "balanced"

    def _infer_preferred_setups(
        self,
        *,
        regime_label: str,
        trend_state: str,
        volatility_state: str,
        liquidity_state: str,
        derivatives_state: str,
        stablecoin_state: str,
    ) -> List[str]:
        setups: List[str] = []
        if regime_label == "trend_up" and liquidity_state == "healthy":
            setups.append("trend_continuation_long")
        if regime_label == "trend_down" and liquidity_state == "healthy":
            setups.append("trend_continuation_short")
        if regime_label == "volatility_compression":
            setups.append("breakout_probe")
        if trend_state == "range" and volatility_state in {"compressed", "normal"}:
            setups.append("mean_reversion_scalp")
        if derivatives_state in {"overheated_long", "overheated_short"}:
            setups.append("squeeze_reversal_watch")
        if stablecoin_state == "risk_on_inflow":
            setups.append("risk_on_rotation")
        return setups[:4]

    def _safe_float(self, value: Any, default: float) -> float:
        try:
            return float(value or 0.0)
        except Exception:
            return float(default)
