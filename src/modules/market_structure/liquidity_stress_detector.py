from __future__ import annotations

from typing import Any, Dict, Optional


class LiquidityStressDetector:
    def analyze(self, snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        row = dict(snapshot or {})
        spread_bps = float(row.get("spread_bps", 0.0) or 0.0)
        depth_imbalance = float(row.get("depth_imbalance", 0.0) or 0.0)
        refill_speed = float(row.get("order_book_refill_speed", 0.0) or 0.0)
        quality = float(row.get("quality_score", 0.0) or 0.0)
        stress_score = round((spread_bps / 20.0) + abs(depth_imbalance) * 0.7 + max(0.0, 0.5 - refill_speed), 4)
        if spread_bps >= 18 or quality < 0.4 or stress_score >= 1.6:
            state = "stressed"
        elif spread_bps >= 8 or abs(depth_imbalance) >= 0.55:
            state = "fragile"
        elif spread_bps > 0:
            state = "healthy"
        else:
            state = "unknown"
        return {
            "spread_bps": spread_bps,
            "depth_imbalance": depth_imbalance,
            "order_book_refill_speed": refill_speed,
            "liquidity_stress_score": stress_score,
            "liquidity_state": state,
        }
