from __future__ import annotations

from typing import Any, Dict, Optional


class RegimeClassifier:
    def classify(self, snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        row = dict(snapshot or {})
        trend_state = str(row.get("trend_state") or row.get("trend") or "unknown")
        volatility_state = str(row.get("volatility_state") or "unknown")
        liquidity_state = str(row.get("liquidity_state") or "unknown")
        derivatives_state = str(row.get("derivatives_state") or "unknown")
        if liquidity_state == "stressed":
            regime = "liquidity_stress"
        elif volatility_state == "extreme":
            regime = "high_volatility"
        elif trend_state == "uptrend":
            regime = "trend_up"
        elif trend_state == "downtrend":
            regime = "trend_down"
        elif derivatives_state in {"overheated_long", "overheated_short"}:
            regime = "crowded_derivatives"
        elif volatility_state == "compressed":
            regime = "volatility_compression"
        elif trend_state == "range":
            regime = "range_bound"
        else:
            regime = "mixed"
        return {"regime_label": regime}
