from __future__ import annotations

from typing import Any, Dict

from src.modules.api.module_control_api import _build_trade_lifecycle_summary


class TradesDomainService:
    def __init__(self, main_controller: Any) -> None:
        self.mc = main_controller

    async def lifecycle(self, trade_limit: int = 300, recent_trades_limit: int = 20) -> Dict[str, Any]:
        return await _build_trade_lifecycle_summary(
            self.mc,
            trade_limit=int(trade_limit or 300),
            recent_limit=int(recent_trades_limit or 20),
        )

    async def backfill_trace_attribution(self, *, dry_run: bool = True, limit: int = 1000) -> Dict[str, Any]:
        ths = getattr(self.mc, "trade_history_service", None) if self.mc else None
        if not ths or not hasattr(ths, "backfill_close_trace_attribution"):
            return {"success": False, "message": "trade_history_service_unavailable"}
        return await ths.backfill_close_trace_attribution(dry_run=bool(dry_run), limit=int(limit or 1000))
