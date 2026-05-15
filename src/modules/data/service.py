from __future__ import annotations

from typing import Any, Dict


class DataDomainService:
    def __init__(self, main_controller: Any) -> None:
        self.mc = main_controller

    async def snapshot(self, symbol: str = "BTC/USDT") -> Dict[str, Any]:
        hub = getattr(self.mc, "data_source_hub", None) if self.mc else None
        if hub and hasattr(hub, "get_unified_snapshot"):
            try:
                return await hub.get_unified_snapshot(symbol)
            except Exception as exc:
                return {"symbol": symbol, "degraded": True, "error": str(exc)}
        return {"symbol": symbol, "degraded": True, "message": "data_source_hub_unavailable"}

