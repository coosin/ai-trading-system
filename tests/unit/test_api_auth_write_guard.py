from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.modules.api.server import APIServer


def _build_guarded_api() -> APIServer:
    APIServer._active_instance = None
    api = APIServer(config_manager=None, main_controller=None, host="127.0.0.1", port=8000)
    api.trusted_hosts = ["testserver", "127.0.0.1", "localhost"]
    api.app = FastAPI()
    asyncio.run(api._add_middleware())

    @api.app.post("/api/v1/modules/demo")
    async def protected_write():
        return {"ok": True}

    return api


def test_protected_write_requires_token():
    api = _build_guarded_api()
    client = TestClient(api.app)

    res = client.post("/api/v1/modules/demo", json={"x": 1})
    assert res.status_code == 401


def test_protected_write_rejects_non_admin_role():
    api = _build_guarded_api()
    client = TestClient(api.app)
    viewer_token = api.create_access_token({"sub": "viewer", "role": "viewer"})

    res = client.post(
        "/api/v1/modules/demo",
        json={"x": 1},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert res.status_code == 403


def test_protected_write_accepts_admin_role():
    api = _build_guarded_api()
    client = TestClient(api.app)
    admin_token = api.create_access_token({"sub": "admin", "role": "admin"})

    res = client.post(
        "/api/v1/modules/demo",
        json={"x": 1},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert res.json().get("ok") is True
