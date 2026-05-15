from __future__ import annotations

from typing import Any, Dict, Optional


class DerivativesStructureAnalyzer:
    def analyze(self, snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        row = dict(snapshot or {})
        funding_rate = float(row.get("funding_rate", 0.0) or 0.0)
        open_interest = float(row.get("open_interest", 0.0) or 0.0)
        basis_bps = float(row.get("basis_bps", 0.0) or 0.0)
        if funding_rate >= 0.003 or basis_bps >= 35:
            state = "overheated_long"
        elif funding_rate <= -0.003 or basis_bps <= -35:
            state = "overheated_short"
        elif open_interest > 0 and open_interest < 250000:
            state = "thin"
        elif open_interest > 0:
            state = "balanced"
        else:
            state = "unknown"
        return {
            "funding_rate": funding_rate,
            "open_interest": open_interest,
            "basis_bps": basis_bps,
            "derivatives_state": state,
        }
