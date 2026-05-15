from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.modules.api.standard_response import ok
from src.modules.memory.service import MemoryDomainService


def build_router(main_controller: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/memory", tags=["memory"])
    service = MemoryDomainService(main_controller)

    @router.get("/overview")
    async def memory_overview():
        return ok(await service.overview())

    return router

