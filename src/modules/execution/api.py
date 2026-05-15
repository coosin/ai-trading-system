from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.modules.api.standard_response import ok
from src.modules.execution.service import ExecutionDomainService


def build_router(main_controller: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/execution", tags=["execution"])
    service = ExecutionDomainService(main_controller)

    @router.get("/spine")
    async def execution_spine():
        return ok(await service.spine())

    return router

