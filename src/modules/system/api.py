from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.modules.api.standard_registry import build_standard_surface
from src.modules.api.standard_response import ok
from src.modules.system.service import SystemService


def build_router(main_controller: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["system"])
    service = SystemService(main_controller)

    @router.get("/system/health")
    async def system_health():
        return ok(await service.health())

    @router.get("/system/status")
    async def system_status():
        return ok(await service.status())

    @router.get("/surface/registry")
    async def surface_registry():
        return ok(build_standard_surface())

    return router

