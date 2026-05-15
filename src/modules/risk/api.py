from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.modules.api.standard_response import ok
from src.modules.risk.service import RiskDomainService


def build_router(main_controller: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/risk", tags=["risk"])
    service = RiskDomainService(main_controller)

    @router.get("/status")
    async def risk_status():
        return ok(await service.status())

    return router

