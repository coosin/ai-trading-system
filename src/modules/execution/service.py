from __future__ import annotations

from typing import Any, Dict


class ExecutionDomainService:
    def __init__(self, main_controller: Any) -> None:
        self.mc = main_controller

    async def spine(self) -> Dict[str, Any]:
        gateway = getattr(self.mc, "execution_gateway", None) if self.mc else None
        if gateway and hasattr(gateway, "get_snapshot"):
            try:
                return await gateway.get_snapshot()
            except Exception as exc:
                return {"degraded": True, "error": str(exc)}
        return {"degraded": True, "message": "execution_gateway_unavailable", "single_write_spine": "ExecutionGateway"}

