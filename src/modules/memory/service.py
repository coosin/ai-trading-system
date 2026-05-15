from __future__ import annotations

from typing import Any, Dict


class MemoryDomainService:
    def __init__(self, main_controller: Any) -> None:
        self.mc = main_controller

    async def overview(self) -> Dict[str, Any]:
        gateway = getattr(self.mc, "memory_gateway", None) if self.mc else None
        if gateway:
            if hasattr(gateway, "get_summary_status"):
                try:
                    return gateway.get_summary_status()
                except Exception:
                    pass
            if hasattr(gateway, "get_stats"):
                try:
                    return gateway.get_stats()
                except Exception:
                    pass
        return {"degraded": True, "message": "memory_gateway_unavailable"}

