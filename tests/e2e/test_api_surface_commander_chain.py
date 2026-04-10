"""
全链路 API 烟测（不启动真实交易所 / 不全量初始化 MainController）

覆盖：Surface 注册表、渠道契约、司令部 dispatch、S1 探针（mock）、预留 ping。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.modules.api.module_control_api import init_module_control_api


@pytest.fixture
def e2e_app():
    app = FastAPI()
    mc = MagicMock()
    mc.get_commander_capabilities = MagicMock(
        return_value={"design": "e2e_mock", "entrypoints": {"process_user_command": True}}
    )

    async def _dispatch(cmd: str, source: str = "system"):
        return {"success": True, "response": f"echo:{cmd[:20]}", "source": "mock_executor"}

    mc.process_user_command = AsyncMock(side_effect=_dispatch)
    mc.get_onchain_integrator = MagicMock(return_value=None)
    mc.data_integration = None
    mc.plugin_manager = None
    mc.skill_manager = MagicMock()
    mc.skill_manager.skills = {}
    mc.market_intelligence = None
    mc.market_intelligence_engine = None
    mc.data_source_hub = None
    mc.simulated_market = None
    mc.telegram_bot = None
    mc.execution_gateway = None
    mc.stop_loss_manager = None
    mc.strategy_manager = None
    mc.data_source_hub = None
    mc.get_exchange = MagicMock(return_value=None)
    mc.okx_exchange = None
    mc.ai_core = None
    mc.ai_trading_engine = MagicMock()
    mc.ai_trading_engine._autonomous_trading_execution_allowed = AsyncMock(return_value=False)
    mc.get_ai_managed_config = AsyncMock(
        return_value={
            "primary_controller": "ai_core",
            "single_write_owner": "ai_core",
            "enable_secondary_controller": False,
        }
    )
    mc.get_system_status = AsyncMock(return_value={"execution_spine": {"ok": True}})
    mc.force_sync_account_state = AsyncMock(return_value={"ok": True})

    init_module_control_api(app, mc)
    return app, mc


def test_surface_registry_and_channels(e2e_app):
    app, _ = e2e_app
    c = TestClient(app)
    r = c.get("/api/v1/modules/surface/registry")
    assert r.status_code == 200
    body = r.json()
    assert body.get("success") is True
    assert isinstance(body.get("catalog"), list)
    assert len(body["catalog"]) > 5
    assert body.get("contract_version")

    r2 = c.get("/api/v1/modules/surface/channels")
    assert r2.status_code == 200
    assert r2.json().get("success") is True


def test_commander_dispatch_chain(e2e_app):
    app, mc = e2e_app
    c = TestClient(app)
    r = c.post(
        "/api/v1/modules/commander/dispatch",
        json={"message": "全链路测试 ping", "source": "e2e"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out.get("success") is True
    assert "data" in out
    mc.process_user_command.assert_called_once()


def test_commander_audit_capabilities(e2e_app):
    app, _ = e2e_app
    c = TestClient(app)
    r = c.get("/api/v1/modules/commander/audit")
    assert r.status_code == 200
    body = r.json()
    assert body.get("success") is True
    checks = body.get("checks") or []
    names = {c.get("name") for c in checks}
    assert "surface.registry" in names

    cap = c.get("/api/v1/modules/commander/capabilities")
    assert cap.status_code == 200
    assert cap.json().get("success") is True


def test_reserved_ping(e2e_app):
    app, _ = e2e_app
    c = TestClient(app)
    r = c.get("/api/v1/modules/reserved/plugins/ping")
    assert r.status_code == 200
    j = r.json()
    assert j.get("reserved") is True
    assert j.get("implemented") is False


def test_s1_verify_smoke(e2e_app):
    app, _ = e2e_app
    c = TestClient(app)
    r = c.get("/api/v1/s1/verify")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert "checks" in body
