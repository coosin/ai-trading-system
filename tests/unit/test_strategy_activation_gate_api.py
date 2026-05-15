from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.modules.api.server import APIServer
from src.modules.core.strategy_manager import StrategyManager


async def _build_strategy_manager() -> StrategyManager:
    sm = StrategyManager(None)
    await sm.load_strategy_config(
        {
            "strategy_id": "ready",
            "name": "Ready",
            "description": "ready strategy",
            "strategy_type": "ai_generated",
            "enabled": False,
        }
    )
    sm.save_strategy_experiment_card(
        "ready",
        hypothesis="trend edge",
        experiment_card={"cost_model": {"fees_bps": 8}, "market": "BTC"},
    )
    sm.record_strategy_peer_review(
        "ready",
        answers={
            "what_edge": "trend persistence",
            "why_not_immediately_gone": "execution frictions",
            "net_after_cost": "still positive",
            "failure_shape": "sideways chop",
            "kill_signal": "OOS fail",
        },
    )
    sm.strategy_configs["ready"].oos_status = "passed"
    sm.strategy_configs["ready"].live_drift_status = "healthy"

    await sm.load_strategy_config(
        {
            "strategy_id": "draft",
            "name": "Draft",
            "description": "draft strategy",
            "strategy_type": "ai_generated",
            "enabled": False,
        }
    )
    return sm


def _build_api(sm: StrategyManager) -> tuple[APIServer, TestClient]:
    APIServer._active_instance = None
    mc = SimpleNamespace(strategy_manager=sm)
    api = APIServer(config_manager=None, main_controller=mc, host="127.0.0.1", port=8000)
    api.trusted_hosts = ["testserver", "127.0.0.1", "localhost"]
    api.app = FastAPI()
    asyncio.run(api._add_middleware())
    asyncio.run(api._setup_routes())
    client = TestClient(api.app)
    return api, client


def test_strategy_activation_gate_helper():
    sm = asyncio.run(_build_strategy_manager())
    ready = sm.get_strategy_activation_gate("ready")
    draft = sm.get_strategy_activation_gate("draft")

    assert ready["eligible"] is True
    assert draft["eligible"] is False
    assert "missing_experiment_card" in draft["reasons"]
    assert "oos_not_passed" in draft["reasons"]


def test_strategy_activation_routes_enforce_research_gate():
    sm = asyncio.run(_build_strategy_manager())
    api, client = _build_api(sm)
    token = api.create_access_token({"sub": "admin", "role": "admin"})
    headers = {"Authorization": f"Bearer {token}"}

    create_blocked = client.post(
        "/api/v1/strategies",
        json={
            "strategy_id": "new_live",
            "name": "New Live",
            "description": "bad",
            "strategy_type": "ai_generated",
            "enabled": True,
        },
        headers=headers,
    )
    assert create_blocked.status_code == 400
    assert "策略未达到启用门槛" in create_blocked.json()["detail"]

    activate_blocked = client.post("/api/v1/strategies/draft/activate", headers=headers)
    assert activate_blocked.status_code == 400
    assert "策略未达到启用门槛" in activate_blocked.json()["detail"]

    update_blocked = client.put(
        "/api/v1/strategies/draft",
        json={"enabled": True},
        headers=headers,
    )
    assert update_blocked.status_code == 400

    activate_ready = client.post("/api/v1/strategies/ready/activate", headers=headers)
    assert activate_ready.status_code == 200
    assert activate_ready.json()["status"] == "success"

    create_ready = client.post(
        "/api/v1/strategies",
        json={
            "strategy_id": "new_ready",
            "name": "New Ready",
            "description": "ok",
            "strategy_type": "ai_generated",
            "enabled": True,
            "metadata": {
                "research": {
                    "hypothesis": "carry edge",
                    "experiment_card": {"hypothesis": "carry edge", "cost_model": {"fees_bps": 5}},
                    "test": {"passed": True},
                    "review": {
                        "answers": {
                            "what_edge": "carry",
                            "why_not_immediately_gone": "capacity limits",
                            "net_after_cost": "positive",
                            "failure_shape": "funding inversion",
                            "kill_signal": "OOS fail",
                        }
                    },
                },
                "live_drift_status": "healthy",
            },
        },
        headers=headers,
    )
    assert create_ready.status_code == 200
    assert create_ready.json()["status"] == "active"
