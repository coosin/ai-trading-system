from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.modules.api.standard_response import ok
from src.modules.market.service import MarketService


def build_router(main_controller: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/market", tags=["market"])
    service = MarketService(main_controller)

    @router.get("/snapshot")
    async def market_snapshot(symbol: str = "BTC/USDT"):
        return ok(await service.snapshot(symbol=symbol))

    return router

