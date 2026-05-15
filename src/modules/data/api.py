from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.modules.api.standard_response import ok
from src.modules.data.service import DataDomainService


def build_router(main_controller: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/data", tags=["data"])
    service = DataDomainService(main_controller)

    @router.get("/snapshot")
    async def data_snapshot(symbol: str = "BTC/USDT"):
        return ok(await service.snapshot(symbol=symbol))

    return router

