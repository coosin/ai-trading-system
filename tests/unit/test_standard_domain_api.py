from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.modules.api.standard_domains import STANDARD_DOMAINS
from src.modules.api.standard_registry import attach_standard_domain_apis, build_standard_surface, canonical_routes


def _app(mc: object | None = None) -> TestClient:
    app = FastAPI()
    attach_standard_domain_apis(app, mc)
    return TestClient(app)


def test_standard_surface_has_one_canonical_route_per_capability():
    routes = canonical_routes()
    capabilities = [r.capability for r in routes if r.status == "canonical"]
    assert len(capabilities) == len(set(capabilities))
    surface = build_standard_surface()
    assert surface["api_style"] == "/api/v1/{domain}/..."
    assert set(STANDARD_DOMAINS).issubset(set(surface["domains"]))
    assert "/api/v1/commander/system-mastery" in {r["path"] for r in surface["routes"]}


def test_standard_surface_registry_endpoint():
    client = _app()
    resp = client.get("/api/v1/surface/registry")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert set(STANDARD_DOMAINS).issubset(set(data["domains"]))
    assert "strategy" in data["by_domain"]


def test_standard_strategy_overview_preserves_core_functionality():
    cfg = MagicMock()
    cfg.strategy_id = "s1"
    cfg.name = "S1"
    cfg.description = "score selected"
    cfg.enabled = True
    cfg.metadata = {
        "deployment": {"stage": "paper"},
        "review_window": {
            "visible": True,
            "status": "open",
            "selection_reason": "selected_high_score",
            "selection_rank": 1,
            "selection_score": 1.2,
        },
    }
    cfg.stage = "paper"
    cfg.oos_status = "passed"
    cfg.live_drift_status = "stable"

    class _SM:
        strategy_configs = {"s1": cfg}
        best_strategy = "s1"
        market_regime = "bull"

        async def get_statistics(self):
            return {"running_instances": 0, "total_instances": 0}

        def get_optimization_status(self):
            return {"total_strategies": 1}

    class _THS:
        async def get_trade_history(self, **kwargs):
            return [{"strategy": "s1", "pnl": 10.0, "fee": -0.1}]

    mc = SimpleNamespace(strategy_manager=_SM(), trade_history_service=_THS(), get_exchange=lambda: None)
    client = _app(mc)
    resp = client.get("/api/v1/strategy/overview")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["summary"]["total_strategies"] == 1
    assert data["summary"]["best_strategy"] == "s1"
    assert data["selection"]["selected_high_score"][0]["strategy_id"] == "s1"
    assert data["live_status"]["strategy_pnl_ranking_24h"][0]["strategy_id"] == "s1"


def test_standard_profit_loop_endpoints_are_available_without_full_controller():
    client = _app(SimpleNamespace())
    for path in (
        "/api/v1/trades/lifecycle",
        "/api/v1/agents/effectiveness",
        "/api/v1/commander/system-mastery",
        "/api/v1/execution/spine",
        "/api/v1/plugins/registry",
    ):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.json()["success"] is True


def test_learning_overview_and_backfill_expose_post_trade_review():
    class _THS:
        async def get_trade_history(self, **kwargs):
            return [
                {
                    "symbol": "BTC/USDT",
                    "pnl": 12.0,
                    "fee": -1.0,
                    "reasoning": "take_profit",
                    "metadata": {"gateway": {"op": "close", "context": {"trace_id": "t1"}}, "strategy_id": "s1"},
                },
                {
                    "symbol": "SOL/USDT",
                    "pnl": -20.0,
                    "fee": -1.0,
                    "reasoning": "stop_loss",
                    "metadata": {"gateway": {"op": "close"}, "strategy_id": "s2"},
                },
            ]

    class _LE:
        lessons = []
        learning_reports = []

        def get_status(self):
            return {"running": True, "total_lessons": 0, "reports_generated": 0}

        def _add_lesson(self, lesson):
            self.lessons.append(lesson)

        async def _generate_learning_report(self):
            self.learning_reports.append({"ok": True})
            return self.learning_reports[-1]

        async def generate_retrieval_practice_deck(self):
            return {"cards": []}

    le = _LE()
    mc = SimpleNamespace(ai_learning_engine=le, trade_history_service=_THS())
    client = _app(mc)

    overview = client.get("/api/v1/learning/overview")
    assert overview.status_code == 200
    data = overview.json()["data"]
    assert data["post_trade_review"]["closed_trades"] == 2
    assert data["coverage_gaps"]

    dry = client.post("/api/v1/learning/backfill-lessons?dry_run=true")
    assert dry.status_code == 200
    assert dry.json()["data"]["would_write"] > 0
    assert le.lessons == []

    write = client.post("/api/v1/learning/backfill-lessons?dry_run=false")
    assert write.status_code == 200
    assert write.json()["data"]["written"] > 0
    assert write.json()["data"]["report_generated"] is True
    assert write.json()["data"]["retrieval_deck_generated"] is True
    assert le.lessons


def test_standard_system_and_risk_keep_operational_detail():
    class _Exchange:
        async def probe_public_api(self, timeout_sec: float = 0.0):
            return {"ok": True, "core_time_ok": True, "status_text": "reachable", "timeout_sec": timeout_sec}

    class _SLTP:
        async def get_stats(self):
            return {"active_orders": 2}

    mc = SimpleNamespace(
        okx_exchange=_Exchange(),
        stop_loss_manager=_SLTP(),
        get_exchange=lambda: _Exchange(),
        get_risk_redlines=lambda: {"max_drawdown": 0.1},
    )
    client = _app(mc)

    health = client.get("/api/v1/system/health")
    assert health.status_code == 200
    health_data = health.json()["data"]
    assert health_data["exchange_bound"] is True
    assert health_data["exchange_reachability"]["status"] == "reachable"

    risk = client.get("/api/v1/risk/status")
    assert risk.status_code == 200
    risk_data = risk.json()["data"]
    assert risk_data["risk_redlines"]["max_drawdown"] == 0.1
    assert risk_data["sltp"]["active_orders"] == 2
