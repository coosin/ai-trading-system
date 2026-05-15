from __future__ import annotations

import asyncio
from typing import Any, Dict


class RiskDomainService:
    def __init__(self, main_controller: Any) -> None:
        self.mc = main_controller

    async def status(self) -> Dict[str, Any]:
        risk_manager = getattr(self.mc, "risk_manager", None) if self.mc else None
        if risk_manager and hasattr(risk_manager, "get_stats"):
            try:
                return await risk_manager.get_stats()
            except TypeError:
                return risk_manager.get_stats()
            except Exception as exc:
                return {"degraded": True, "error": str(exc)}
        redlines = {}
        if self.mc and hasattr(self.mc, "get_risk_redlines"):
            try:
                redlines = self.mc.get_risk_redlines()
            except Exception:
                redlines = {}
        sltp = {}
        manager = getattr(self.mc, "stop_loss_manager", None) if self.mc else None
        if manager is not None and hasattr(manager, "get_stats"):
            try:
                sltp = await asyncio.wait_for(manager.get_stats(), timeout=2.5)
            except TypeError:
                sltp = manager.get_stats()
            except Exception:
                sltp = {}
        return {"degraded": risk_manager is None, "risk_redlines": redlines, "sltp": sltp}
