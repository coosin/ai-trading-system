from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.modules.api.server import APIServer
from src.modules.core.strategy_manager import MarketRegime, StrategyManager


async def _build_strategy_manager() -> StrategyManager:
    sm = StrategyManager(None)
    sm.market_regime = MarketRegime.BULL
    await sm.load_strategy_config(
        {
            "strategy_id": "dsl_selected",
            "name": "Selected",
            "description": "auto selected",
            "strategy_type": "ai_generated",
            "enabled": True,
            "metadata": {
                "deployment": {"stage": "paper"},
                "review_window": {
                    "visible": True,
                    "status": "open",
                    "mode": "post_publish_observation",
                    "selection_reason": "selected_high_score",
                    "selection_rank": 1,
                    "selection_score": 1.22,
                    "review_by": "2026-05-16T12:00:00",
                },
                "research": {"score": 1.22},
            },
        }
    )
    await sm.load_strategy_config(
        {
            "strategy_id": "dsl_retired",
            "name": "Retired",
            "description": "retired low score",
            "strategy_type": "ai_generated",
            "enabled": False,
            "metadata": {
                "deployment": {"stage": "paper"},
                "review_window": {
                    "visible": True,
                    "status": "open",
                    "mode": "post_publish_observation",
                    "selection_reason": "retired_low_score",
                    "selection_rank": 5,
                    "selection_score": 0.11,
                    "review_by": "2026-05-16T18:00:00",
                },
                "research": {"score": 0.11},
            },
        }
    )
    await sm.load_strategy_config(
        {
            "strategy_id": "dsl_pending",
            "name": "Pending",
            "description": "needs human review first",
            "strategy_type": "ai_generated",
            "enabled": False,
            "metadata": {
                "deployment": {"stage": "paper"},
                "review_window": {
                    "visible": True,
                    "status": "pending_approval",
                    "mode": "pre_publish_approval",
                    "selection_reason": "selected_high_score",
                    "selection_rank": 2,
                    "selection_score": 1.05,
                    "review_by": "2026-05-15T09:00:00",
                },
                "approval": {"required": True, "state": "manual_approval_required", "approved": False},
                "research": {"score": 1.05},
            },
        }
    )
    sm.best_strategy = "dsl_selected"
    return sm


def _build_api(sm: StrategyManager) -> tuple[APIServer, TestClient]:
    APIServer._active_instance = None
    class _FakeExchange:
        async def get_positions(self):
            return [
                {"symbol": "BTC/USDT/SWAP", "size": 2, "side": "short"},
                {"symbol": "ETH/USDT/SWAP", "size": 1, "side": "long"},
            ]

    class _FakeTradeHistoryService:
        async def get_trade_history(self, start_date=None, limit=10000, **kwargs):
            return [
                {"symbol": "BTC/USDT/SWAP", "pnl": 12.5, "fee": -0.4, "pnl_percent": 0.01, "strategy": "dsl_selected", "timestamp": "2026-05-15T10:00:00"},
                {"symbol": "BTC/USDT/SWAP", "pnl": -2.5, "fee": -0.1, "pnl_percent": -0.002, "strategy": "dsl_selected", "timestamp": "2026-05-15T11:00:00"},
                {"symbol": "ETH/USDT/SWAP", "pnl": -3.0, "fee": -0.2, "pnl_percent": -0.003, "strategy": "dsl_retired"},
                {"symbol": "SOL/USDT/SWAP", "pnl": 6.0, "fee": -0.1, "pnl_percent": 0.005, "strategy": "dsl_pending", "timestamp": "2026-05-15T09:30:00"},
            ]

    ex = _FakeExchange()
    mc = SimpleNamespace(
        strategy_manager=sm,
        trade_history_service=_FakeTradeHistoryService(),
        get_exchange=lambda: ex,
        okx_exchange=ex,
    )
    api = APIServer(config_manager=None, main_controller=mc, host="127.0.0.1", port=8000)
    api.trusted_hosts = ["testserver", "127.0.0.1", "localhost"]
    api.app = FastAPI()
    asyncio.run(api._add_middleware())
    asyncio.run(api._setup_routes())
    client = TestClient(api.app)
    return api, client


def test_strategies_overview_exposes_review_window_and_selection_summary():
    sm = asyncio.run(_build_strategy_manager())
    api, client = _build_api(sm)
    token = api.create_access_token({"sub": "admin", "role": "admin"})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/strategy/overview", headers=headers)

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["summary"]["total_strategies"] == 3
    assert body["summary"]["best_strategy"] == "dsl_selected"
    assert body["summary"]["active_positions"] == 2
    assert body["summary"]["running_instances"] == 0
    assert body["summary"]["realized_pnl_24h"] == 13.0
    assert body["summary"]["realized_trades_24h"] == 4
    assert body["review_windows"]["total_visible"] == 3
    assert body["review_windows"]["pending_items"][0]["strategy_id"] == "dsl_pending"
    assert body["live_status"]["strategy_pnl_ranking_24h"][0]["strategy_id"] == "dsl_selected"
    assert body["live_status"]["strategy_pnl_ranking_24h"][0]["enabled"] is True
    assert body["live_status"]["strategy_pnl_ranking_24h"][0]["deployment_stage"] == "paper"
    assert body["live_status"]["strategy_pnl_ranking_24h"][0]["review_status"] == "open"
    assert body["live_status"]["strategy_pnl_ranking_24h"][0]["selection_rank"] == 1
    assert body["live_status"]["strategy_pnl_ranking_24h"][0]["selection_score"] == 1.22
    assert body["live_status"]["strategy_pnl_ranking_24h"][1]["strategy_id"] == "dsl_pending"
    assert body["live_status"]["strategy_pnl_ranking_24h"][1]["enabled"] is False
    assert body["live_status"]["strategy_pnl_ranking_24h"][1]["review_status"] == "pending_approval"
    assert body["live_status"]["strategy_pnl_ranking_24h"][1]["selection_rank"] == 2
    assert body["live_status"]["strategy_pnl_ranking_24h"][1]["selection_score"] == 1.05
    assert body["live_status"]["strategy_pnl_ranking_24h"][0]["expectancy_24h"] == 5.0
    assert body["live_status"]["strategy_pnl_ranking_24h"][0]["profit_factor_24h"] == 5.0
    assert body["live_status"]["strategy_pnl_ranking_24h"][0]["max_drawdown_pnl_24h"] == 2.5
    assert body["selection"]["selected_high_score"][0]["strategy_id"] == "dsl_selected"
    assert body["selection"]["retired_low_score"][0]["strategy_id"] == "dsl_retired"
