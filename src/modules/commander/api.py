from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.modules.api.standard_response import ok
from src.modules.commander.service import CommanderDomainService


def build_router(main_controller: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/commander", tags=["commander"])
    service = CommanderDomainService(main_controller)

    @router.get("/system-mastery")
    async def commander_system_mastery(
        symbol: str = "BTC/USDT",
        trace_limit: int = 120,
        trade_limit: int = 300,
        recent_trades_limit: int = 20,
    ):
        return ok(
            await service.system_mastery(
                symbol=symbol,
                trace_limit=trace_limit,
                trade_limit=trade_limit,
                recent_trades_limit=recent_trades_limit,
            )
        )

    @router.get("/closed-loop")
    async def commander_closed_loop(trace_limit: int = 120):
        return ok(await service.closed_loop(trace_limit=trace_limit))

    @router.get("/trading-workflow")
    async def commander_trading_workflow(
        symbol: str = "BTC/USDT",
        trace_limit: int = 200,
        trade_limit: int = 1000,
        recent_trades_limit: int = 40,
        recent_order_hours: float = 4.0,
    ):
        return ok(
            await service.trading_workflow(
                symbol=symbol,
                trace_limit=trace_limit,
                trade_limit=trade_limit,
                recent_trades_limit=recent_trades_limit,
                recent_order_hours=recent_order_hours,
            )
        )

    return router
