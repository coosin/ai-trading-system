from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.modules.api.standard_response import ok
from src.modules.plugins.service import PluginsDomainService


def build_router(main_controller: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])
    service = PluginsDomainService(main_controller)

    @router.get("/registry")
    async def plugins_registry():
        return ok(await service.registry())

    return router

