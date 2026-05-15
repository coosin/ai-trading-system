from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from src.modules.api.standard_response import ok
from src.modules.strategy.service import StrategyDomainService


def build_router(main_controller: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])
    service = StrategyDomainService(main_controller)

    @router.get("/overview")
    async def strategy_overview():
        return ok(await service.overview())

    @router.get("/list")
    async def strategy_list():
        return ok(service.list_items())

    @router.post("")
    async def strategy_create(payload: dict[str, Any] = Body(default_factory=dict)):
        try:
            result = await service.create(payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if not result.pop("ok", False):
            raise HTTPException(status_code=int(result.get("status_code", 400)), detail=result.get("detail", "strategy_create_failed"))
        return result

    @router.put("/{strategy_id}")
    async def strategy_update(strategy_id: str, payload: dict[str, Any] = Body(default_factory=dict)):
        try:
            result = await service.update(strategy_id, payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if not result.pop("ok", False):
            raise HTTPException(status_code=int(result.get("status_code", 400)), detail=result.get("detail", "strategy_update_failed"))
        return result

    @router.delete("/{strategy_id}")
    async def strategy_delete(strategy_id: str):
        try:
            result = await service.delete(strategy_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        result.pop("ok", None)
        return result

    @router.post("/{strategy_id}/approve")
    async def strategy_approve(strategy_id: str, payload: dict[str, Any] = Body(default_factory=dict)):
        try:
            result = await service.approve(strategy_id, payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if not result.pop("ok", False):
            raise HTTPException(status_code=int(result.get("status_code", 400)), detail=result.get("detail", "strategy_approve_failed"))
        return result

    @router.post("/{strategy_id}/activate")
    async def strategy_activate(strategy_id: str):
        try:
            result = await service.activate(strategy_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if not result.pop("ok", False):
            raise HTTPException(status_code=int(result.get("status_code", 400)), detail=result.get("detail", "strategy_activate_failed"))
        return result

    @router.post("/{strategy_id}/deactivate")
    async def strategy_deactivate(strategy_id: str):
        try:
            result = await service.deactivate(strategy_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if not result.pop("ok", False):
            raise HTTPException(status_code=int(result.get("status_code", 400)), detail=result.get("detail", "strategy_deactivate_failed"))
        return result

    return router
