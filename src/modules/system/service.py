from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict


class SystemService:
    def __init__(self, main_controller: Any) -> None:
        self.mc = main_controller

    async def health(self) -> Dict[str, Any]:
        mc = self.mc
        status = "healthy" if mc is not None else "degraded"
        exchange = None
        reachability: Dict[str, Any] = {"ok": None, "status": "unknown"}
        try:
            exchange = mc.get_exchange() if mc and hasattr(mc, "get_exchange") else getattr(mc, "okx_exchange", None)
        except Exception:
            exchange = None
        probe = getattr(exchange, "probe_public_api", None) if exchange is not None else None
        if callable(probe):
            try:
                result = await asyncio.wait_for(probe(timeout_sec=4.2), timeout=5.0)
            except Exception as exc:
                result = {"ok": False, "reason": "probe_exception", "error": str(exc)[:220]}
            probe_status = str((result or {}).get("status_text") or "").strip().lower()
            ok = bool((result or {}).get("ok"))
            core_time_ok = bool((result or {}).get("core_time_ok"))
            if probe_status not in {"reachable", "degraded", "unreachable"}:
                probe_status = "reachable" if ok else "unreachable"
            reachability = {"ok": ok, "status": probe_status, "probe": result}
            if probe_status == "unreachable" or not core_time_ok:
                status = "degraded"
                reachability["hint"] = "Check TLS CA chain / proxy / upstream network."
        elif exchange is None:
            reachability = {"ok": None, "status": "unknown", "message": "exchange_unavailable"}
        else:
            reachability = {"ok": None, "status": "unknown", "message": "probe_not_supported"}
        return {
            "status": status,
            "main_controller": mc is not None,
            "exchange_bound": exchange is not None,
            "exchange_reachability": reachability,
            "timestamp": datetime.now().isoformat(),
        }

    async def status(self) -> Dict[str, Any]:
        mc = self.mc
        if mc and hasattr(mc, "get_system_status"):
            try:
                return await mc.get_system_status()
            except Exception as exc:
                return {"degraded": True, "error": str(exc)}
        return {"degraded": True, "message": "main_controller_unavailable"}
