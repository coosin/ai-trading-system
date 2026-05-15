from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.modules.account.service import AccountService
from src.modules.api.standard_response import ok


def build_router(main_controller: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/account", tags=["account"])
    service = AccountService(main_controller)

    @router.get("/snapshot")
    async def account_snapshot():
        return ok(await service.snapshot())

    return router

