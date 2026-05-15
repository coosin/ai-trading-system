from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.modules.api.standard_response import ok
from src.modules.learning.service import LearningDomainService


def build_router(main_controller: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/learning", tags=["learning"])
    service = LearningDomainService(main_controller)

    @router.get("/overview")
    async def learning_overview():
        return ok(await service.overview())

    @router.post("/backfill-lessons")
    async def learning_backfill_lessons(dry_run: bool = True, limit: int = 500, generate_report: bool = True):
        return ok(await service.backfill_lessons(dry_run=dry_run, limit=limit, generate_report=generate_report))

    return router
