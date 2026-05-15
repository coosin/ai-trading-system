from __future__ import annotations

from typing import Any, Dict, Optional


class StablecoinFlowAnalyzer:
    def analyze(self, snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        row = dict(snapshot or {})
        supply_change = float(row.get("stablecoin_supply_change", 0.0) or 0.0)
        exchange_netflow = float(row.get("exchange_netflow", 0.0) or 0.0)
        large_wallet_flow = float(row.get("large_wallet_flow", 0.0) or 0.0)
        score = round((supply_change * 0.45) - (exchange_netflow * 0.35) + (large_wallet_flow * 0.20), 4)
        if score >= 0.45:
            state = "risk_on_inflow"
        elif score <= -0.45:
            state = "risk_off_outflow"
        elif score != 0.0:
            state = "neutral_flow"
        else:
            state = "unknown"
        return {"stablecoin_flow_score": score, "stablecoin_flow_state": state}
