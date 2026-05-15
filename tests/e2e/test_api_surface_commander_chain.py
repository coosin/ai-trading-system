"""
全链路 API 烟测（不启动真实交易所 / 不全量初始化 MainController）

覆盖：Surface 注册表、渠道契约、司令部 dispatch、S1 探针（mock）、预留 ping。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.modules.api.module_control_api as module_control_api
from src.modules.api.module_control_api import init_module_control_api
from src.modules.market_structure import MarketStructureEngine


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
    mc.market_structure_engine = MarketStructureEngine()
    mc.feature_store_lite = MagicMock()
    mc.feature_store_lite.get_summary = MagicMock(return_value={"tables": {"research_labels": {"count": 1}}})
    mc.feature_store_lite.get_recent = MagicMock(return_value=[])
    mc.feature_store_lite.append_raw_market_event = MagicMock()
    mc.ai_learning_engine = MagicMock()
    mc.ai_learning_engine.get_status = MagicMock(
        return_value={
            "weekly_review": {"generated_at": "2026-01-01T00:00:00", "review_markdown": "weekly"},
            "learning_analytics": {"retrieval_accuracy": 0.7, "research_conversion_rate": 0.5},
            "retrieval_deck": {"cards": [{"question": "q1", "answer": "a1"}]},
            "self_review": {"lesson_summary": "ok"},
        }
    )
    mc.strategy_manager = MagicMock()
    mc.strategy_manager.strategy_configs = {
        "s1": MagicMock(name="S1"),
    }
    mc.strategy_manager.get_strategy_governance_profile = MagicMock(
        return_value={"strategy_id": "s1", "stage": "limited_live", "oos_status": "passed", "live_drift_status": "unknown"}
    )
    mc.strategy_manager.get_strategy_research_profile = MagicMock(
        return_value={
            "strategy_id": "s1",
            "hypothesis": "trend continuation",
            "review_completion_status": "completed",
            "last_review_type": "weekly",
            "failure_cases": [{"title": "oos fail"}],
            "parameter_sensitivity": {"summary": "stable"},
        }
    )
    mc.strategy_manager.save_strategy_experiment_card = MagicMock(return_value=True)
    mc.strategy_manager.record_strategy_peer_review = MagicMock(return_value=True)
    mc.strategy_manager.record_strategy_failure_case = MagicMock(return_value=True)
    mc.strategy_manager.save_strategy_parameter_sensitivity = MagicMock(return_value=True)
    mc.strategy_manager.record_market_structure_snapshot = MagicMock(
        return_value={"symbol": "BTC/USDT", "actions": [{"strategy_id": "s1", "action": "observe"}]}
    )
    mc.strategy_manager.get_market_structure_governance_status = MagicMock(
        return_value={"tracked_symbols": ["BTC/USDT"], "status_counts": {"observing": 1}, "strategies": [{"strategy_id": "s1", "status": "observing"}]}
    )

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


def test_market_structure_and_research_cockpit_endpoints(e2e_app):
    app, mc = e2e_app
    c = TestClient(app)
    ms = c.get("/api/v1/modules/market-structure/multi-source-snapshot?symbol=BTC/USDT")
    assert ms.status_code == 200
    msj = ms.json()
    assert msj.get("success") is True
    assert "market_structure" in (msj.get("data") or {})
    assert "governance_update" in (msj.get("data") or {})
    mc.feature_store_lite.append_raw_market_event.assert_called()

    rc = c.get("/api/v1/modules/commander/research-cockpit?symbol=BTC/USDT")
    assert rc.status_code == 200
    rcj = rc.json()
    assert rcj.get("success") is True
    data = rcj.get("data") or {}
    assert "research" in data
    assert "learning" in data
    assert "raw_market_events" in (data.get("feature_store") or {})
    assert "derived_features" in (data.get("feature_store") or {})
    assert "market_structure_governance" in (data.get("research") or {})


def test_strategy_research_profile_write_endpoints(e2e_app):
    app, mc = e2e_app
    c = TestClient(app)
    r1 = c.get("/api/v1/modules/strategy/research-profile/s1")
    assert r1.status_code == 200
    assert r1.json().get("success") is True

    r2 = c.post("/api/v1/modules/strategy/research-profile/s1/experiment-card", json={"hypothesis": "trend edge", "experiment_card": {"market": "BTC"}})
    assert r2.status_code == 200
    assert r2.json().get("success") is True
    mc.strategy_manager.save_strategy_experiment_card.assert_called_once()

    r3 = c.post(
        "/api/v1/modules/strategy/research-profile/s1/peer-review",
        json={"answers": {
            "what_edge": "edge",
            "why_not_immediately_gone": "friction",
            "net_after_cost": "positive",
            "failure_shape": "chop",
            "kill_signal": "oos fail",
        }},
    )
    assert r3.status_code == 200
    assert r3.json().get("success") is True

    r4 = c.post("/api/v1/modules/strategy/research-profile/s1/failure-case", json={"title": "case", "summary": "summary"})
    assert r4.status_code == 200
    assert r4.json().get("success") is True

    r5 = c.post("/api/v1/modules/strategy/research-profile/s1/parameter-sensitivity", json={"parameter_sensitivity": {"summary": "stable"}})
    assert r5.status_code == 200
    assert r5.json().get("success") is True


def test_trading_diagnosis_includes_replace_worst_policy_hint(e2e_app):
    app, mc = e2e_app
    c = TestClient(app)
    mc.execution_gateway = MagicMock()
    mc.execution_gateway.get_snapshot = AsyncMock(
        return_value={
            "policy_metrics": {"open_ok": 1, "open_fail": 0, "close_ok": 2, "close_fail": 0},
            "replace_worst_policy": {
                "enable_replace_worst_on_full_positions": False,
                "replace_worst_min_confidence": 0.75,
            },
            "reconciliation": {
                "healthy": True,
                "severity": "ok",
                "summary": {"drift_total": 0, "stale_open_orders": 0},
                "safe_recovery": {},
            },
            "reconciliation_protection": {"global_lock_active": False, "symbol_locks": {}},
            "decision_traces": [],
        }
    )
    mc.execution_gateway.get_recent_events = AsyncMock(
        return_value=[
            {
                "success": False,
                "op": "open",
                "ts": "2026-05-14T10:06:00Z",
                "symbol": "BTC/USDT",
                "error_code": "RISK_REDLINE_DENIED",
                "reason": "risk_redline_max_positions",
                "detail": "风控红线拦截：持仓数 4 已达到上限 4 (max_positions)",
            }
        ]
    )
    mc.ai_core = MagicMock()
    mc.ai_core.get_status = MagicMock(return_value={"execution_guards": {"stats": {"spread_rejected": 1}}})
    mc.config_manager = MagicMock()
    mc.config_manager.get_config = AsyncMock(
        return_value={
            "position_limits": {
                "max_positions_oneway": 3,
                "max_positions_hedge": 4,
                "hard_max_positions": 4,
            }
        }
    )

    r = c.get("/api/v1/modules/commander/trading-diagnosis?limit_events=5")

    assert r.status_code == 200
    body = r.json()
    assert body.get("success") is True
    hints = (body.get("data") or {}).get("diagnosis_hints") or []
    assert any("replace_worst policy: enabled=False, min_conf=0.75" in str(item) for item in hints)
    assert any(
        "full position behavior: replace_worst disabled, reaching max_positions=4 will hard-block new opens until a slot is freed" in str(item)
        for item in hints
    )
    assert any(
        "recent capacity block: ts=2026-05-14T10:06:00Z, symbol=BTC/USDT, open was rejected by max_positions redline while replace_worst was disabled" in str(item)
        for item in hints
    )
    assert hints[0] == (
        "recent capacity block: ts=2026-05-14T10:06:00Z, symbol=BTC/USDT, open was rejected by max_positions redline while replace_worst was disabled"
    )


def test_trading_diagnosis_falls_back_to_app_log_when_recent_events_empty(e2e_app, monkeypatch):
    app, mc = e2e_app
    c = TestClient(app)
    mc.execution_gateway = MagicMock()
    mc.execution_gateway.get_snapshot = AsyncMock(
        return_value={
            "policy_metrics": {"open_ok": 1, "open_fail": 0, "close_ok": 2, "close_fail": 0},
            "replace_worst_policy": {
                "enable_replace_worst_on_full_positions": False,
                "replace_worst_min_confidence": 0.75,
            },
            "reconciliation": {
                "healthy": True,
                "severity": "ok",
                "summary": {"drift_total": 0, "stale_open_orders": 0},
                "safe_recovery": {},
            },
            "reconciliation_protection": {"global_lock_active": False, "symbol_locks": {}},
            "decision_traces": [],
        }
    )
    mc.execution_gateway.get_recent_events = AsyncMock(return_value=[])
    mc.ai_core = MagicMock()
    mc.ai_core.get_status = MagicMock(return_value={"execution_guards": {"stats": {"spread_rejected": 1}}})
    mc.config_manager = MagicMock()
    mc.config_manager.get_config = AsyncMock(
        return_value={
            "position_limits": {
                "max_positions_oneway": 3,
                "max_positions_hedge": 4,
                "hard_max_positions": 4,
            }
        }
    )
    monkeypatch.setattr(
        module_control_api,
        "_load_recent_capacity_block_from_runtime",
        lambda: None,
    )
    monkeypatch.setattr(
        module_control_api,
        "_load_recent_capacity_block_from_app_log",
        lambda: {
            "ts": "2026-05-14T09:35:49Z",
            "symbol": "?",
            "detail": "风控红线拦截：持仓数 5 已达到上限 5；候选释放槽位: AVAX/USDT(short), DOT/USDT(short)",
            "source": "app_log",
        },
    )

    r = c.get("/api/v1/modules/commander/trading-diagnosis?limit_events=5")

    assert r.status_code == 200
    body = r.json()
    assert body.get("success") is True
    hints = (body.get("data") or {}).get("diagnosis_hints") or []
    assert hints[0] == (
        "recent capacity block: ts=2026-05-14T09:35:49Z, symbol=?, open was rejected by max_positions redline while replace_worst was disabled, source=app_log"
    )


def test_trading_diagnosis_prefers_runtime_recent_events_when_recent_events_empty(e2e_app, monkeypatch):
    app, mc = e2e_app
    c = TestClient(app)
    mc.execution_gateway = MagicMock()
    mc.execution_gateway.get_snapshot = AsyncMock(
        return_value={
            "policy_metrics": {"open_ok": 1, "open_fail": 0, "close_ok": 2, "close_fail": 0},
            "replace_worst_policy": {
                "enable_replace_worst_on_full_positions": False,
                "replace_worst_min_confidence": 0.75,
            },
            "reconciliation": {
                "healthy": True,
                "severity": "ok",
                "summary": {"drift_total": 0, "stale_open_orders": 0},
                "safe_recovery": {},
            },
            "reconciliation_protection": {"global_lock_active": False, "symbol_locks": {}},
            "decision_traces": [],
        }
    )
    mc.execution_gateway.get_recent_events = AsyncMock(return_value=[])
    mc.ai_core = MagicMock()
    mc.ai_core.get_status = MagicMock(return_value={"execution_guards": {"stats": {"spread_rejected": 1}}})
    mc.config_manager = MagicMock()
    mc.config_manager.get_config = AsyncMock(
        return_value={
            "position_limits": {
                "max_positions_oneway": 3,
                "max_positions_hedge": 4,
                "hard_max_positions": 4,
            }
        }
    )
    monkeypatch.setattr(
        module_control_api,
        "_load_recent_capacity_block_from_runtime",
        lambda: {
            "ts": "2026-05-14T09:49:11Z",
            "symbol": "DOGE/USDT",
            "detail": "风控红线拦截：持仓数 5 已达到上限 5",
            "source": "runtime_recent_events",
        },
    )
    monkeypatch.setattr(
        module_control_api,
        "_load_recent_capacity_block_from_app_log",
        lambda: {
            "ts": "2026-05-14T09:35:49Z",
            "symbol": "?",
            "detail": "风控红线拦截：持仓数 5 已达到上限 5",
            "source": "app_log",
        },
    )

    r = c.get("/api/v1/modules/commander/trading-diagnosis?limit_events=5")

    assert r.status_code == 200
    body = r.json()
    assert body.get("success") is True
    hints = (body.get("data") or {}).get("diagnosis_hints") or []
    assert hints[0] == (
        "recent capacity block: ts=2026-05-14T09:49:11Z, symbol=DOGE/USDT, open was rejected by max_positions redline while replace_worst was disabled, source=runtime_recent_events"
    )
