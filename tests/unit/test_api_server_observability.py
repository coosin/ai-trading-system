from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.modules.api.server import APIServer


def _build_api(mc: object | None = None) -> tuple[APIServer, TestClient]:
    APIServer._active_instance = None
    api = APIServer(config_manager=None, main_controller=mc, host="127.0.0.1", port=8000)
    api.trusted_hosts = ["testserver", "127.0.0.1", "localhost"]
    api.app = FastAPI()
    asyncio.run(api._add_middleware())
    asyncio.run(api._setup_routes())
    return api, TestClient(api.app)


def test_market_data_route_uses_bound_data_source_hub():
    class _Hub:
        def __init__(self) -> None:
            self.calls = []

        def bind_main_controller(self, mc: object | None) -> None:
            self.mc = mc

        async def get_klines(self, symbol: str, interval: str = "1m", limit: int = 100):
            self.calls.append((symbol, interval, limit))
            return [
                {
                    "timestamp": 1,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.5,
                    "close": 100.5,
                    "volume": 10.0,
                }
            ]

    hub = _Hub()
    _, client = _build_api(SimpleNamespace(data_source_hub=hub))

    resp = client.get("/api/v1/market/data?symbol=BTC/USDT&interval=5m&limit=1")

    assert resp.status_code == 200
    assert resp.json()[0]["close"] == 100.5
    assert hub.calls == [("BTC/USDT", "5m", 1)]


def test_risk_metrics_marks_account_state_warming():
    class _Exchange:
        async def get_positions(self):
            return [{"size": 1.0, "notional_value": 200.0, "leverage": 20.0}]

        async def get_balance(self):
            return {}

    ex = _Exchange()
    mc = SimpleNamespace(get_exchange=lambda: ex, okx_exchange=ex, _latest_account_state={})
    _, client = _build_api(mc)

    resp = client.get("/api/v1/risk/metrics")

    assert resp.status_code == 200
    body = resp.json()
    assert body["warming"] is True
    assert body["degraded"] is True
    assert body["portfolio_value"] == 0.0
    assert body["portfolio_value_source"] == "warming_unavailable"
    assert body["portfolio_value_lower_bound"] == 10.0
    assert "account_state_warming" in body["warnings"]


def test_get_uptime_uses_real_runtime_delta():
    api, _ = _build_api()
    api._started_at = datetime.now() - timedelta(hours=1, minutes=2, seconds=3)

    uptime = api._get_uptime()

    assert uptime != "0 days, 0:00:00"
    assert "1:02:03" in uptime


def test_trade_routes_resolve_placeholder_strategy_via_trace_store():
    class _THS:
        async def get_trade_history(self, **kwargs):
            return [
                {
                    "trade_id": "close-1",
                    "order_id": "order-close-1",
                    "timestamp": "2026-05-18T10:01:00Z",
                    "symbol": "ETH/USDT",
                    "side": "buy",
                    "price": 2200.0,
                    "quantity": 1.0,
                    "fee": -0.1,
                    "pnl": 2.0,
                    "pnl_percent": 0.01,
                    "status": "filled",
                    "strategy": "none",
                    "reasoning": "execution_verifier_close",
                    "metadata": {
                        "strategy_id": "none",
                        "source": "historical_db",
                        "gateway": {
                            "op": "close",
                            "source": "ai_core",
                            "context": {"trace_id": "trace-autonomy-1"},
                        },
                    },
                },
                {
                    "trade_id": "close-2",
                    "order_id": "order-close-2",
                    "timestamp": "2026-05-18T10:00:00Z",
                    "symbol": "LINK/USDT/SWAP",
                    "side": "sell",
                    "price": 9.8,
                    "quantity": 1.0,
                    "fee": -0.01,
                    "pnl": -0.2,
                    "pnl_percent": -0.01,
                    "status": "filled",
                    "strategy": "none",
                    "reasoning": "stop_loss",
                    "metadata": {
                        "strategy_id": "none",
                        "source": "historical_db",
                        "gateway": {
                            "op": "close",
                            "source": "stop_loss_take_profit",
                            "context": {},
                        },
                    },
                },
            ]

    class _TraceStore:
        def get_by_trace_id(self, trace_id: str):
            if trace_id != "trace-autonomy-1":
                return None
            return {
                "trace_id": trace_id,
                "source": "ai_core",
                "intent": {
                    "strategy_used": "none",
                    "reasoning": "ai_autonomy_override: strict=True autonomy=True",
                    "extras": {},
                },
            }

    mc = SimpleNamespace(trade_history_service=_THS(), decision_trace_store=_TraceStore())
    _, client = _build_api(mc)

    trades_resp = client.get("/api/v1/trades?limit=10")

    assert trades_resp.status_code == 200
    trades = trades_resp.json()["trades"]
    assert trades[0]["strategy"] == "s1_ai_autonomy_override"
    assert trades[0]["source"] == "ai_core"
    assert trades[1]["strategy"] == "sltp_auto_exit"
    assert trades[1]["source"] == "stop_loss_take_profit"

    analytics_resp = client.get("/api/v1/trades/analytics/summary?days=30")

    assert analytics_resp.status_code == 200
    by_strategy = analytics_resp.json()["by_strategy_top"]
    keys = {row["key"] for row in by_strategy}
    assert "s1_ai_autonomy_override" in keys
    assert "sltp_auto_exit" in keys
    assert "none" not in keys
