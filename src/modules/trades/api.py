from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.modules.api.standard_response import ok
from src.modules.trades.service import TradesDomainService


def build_router(main_controller: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/trades", tags=["trades"])
    service = TradesDomainService(main_controller)

    @router.get("/lifecycle")
    async def trades_lifecycle(trade_limit: int = 300, recent_trades_limit: int = 20):
        return ok(await service.lifecycle(trade_limit=trade_limit, recent_trades_limit=recent_trades_limit))

    @router.post("/backfill-trace-attribution")
    async def trades_backfill_trace_attribution(dry_run: bool = True, limit: int = 1000):
        return ok(await service.backfill_trace_attribution(dry_run=dry_run, limit=limit))

    return router
