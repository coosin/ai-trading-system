from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.modules.api.module_control_api as module_control_api
import src.modules.api.monitoring_api as monitoring_api
from src.modules.api.module_control_api import _build_closed_loop_summary_data, _build_trade_lifecycle_summary


@pytest.mark.asyncio
async def test_trade_lifecycle_uses_true_recent_rows_and_pairs_hold_duration():
    class _TradeHistory:
        async def get_trade_history(self, limit: int = 300):
            return [
                {
                    "timestamp": "2026-05-18T12:00:00Z",
                    "symbol": "BTC/USDT",
                    "side": "sell",
                    "price": 110.0,
                    "quantity": 1.0,
                    "pnl": 10.0,
                    "fee": -0.5,
                    "pnl_percent": 0.05,
                    "reasoning": "take_profit",
                    "metadata": {"gateway": {"op": "close"}, "decision_action": "CLOSE_LONG", "strategy_id": "s1"},
                },
                {
                    "timestamp": "2026-05-18T11:00:00Z",
                    "symbol": "ETH/USDT",
                    "side": "sell",
                    "price": 2400.0,
                    "quantity": 1.0,
                    "pnl": 0.0,
                    "fee": -0.2,
                    "pnl_percent": 0.0,
                    "metadata": {"gateway": {"op": "open"}, "decision_action": "OPEN_SHORT", "strategy_id": "s2"},
                },
                {
                    "timestamp": "2026-05-18T10:00:00Z",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "price": 100.0,
                    "quantity": 1.0,
                    "pnl": 0.0,
                    "fee": -0.2,
                    "pnl_percent": 0.0,
                    "metadata": {"gateway": {"op": "open"}, "decision_action": "OPEN_LONG", "strategy_id": "s1"},
                },
            ]

    data = await _build_trade_lifecycle_summary(
        SimpleNamespace(trade_history_service=_TradeHistory()),
        trade_limit=10,
        recent_limit=2,
    )

    assert data["recent_rows"][0]["timestamp"] == "2026-05-18T12:00:00Z"
    assert data["recent_rows"][1]["timestamp"] == "2026-05-18T11:00:00Z"
    assert data["summary"]["opens"] == 2
    assert data["summary"]["closes"] == 1
    assert data["summary"]["avg_hold_hours"] == 2.0


@pytest.mark.asyncio
async def test_trade_lifecycle_excludes_low_fidelity_historical_rows():
    class _TradeHistory:
        async def get_trade_history(self, limit: int = 300):
            return [
                {
                    "timestamp": "2026-05-18T12:00:00Z",
                    "symbol": "BTC/USDT",
                    "side": "sell",
                    "price": 110.0,
                    "quantity": 1.0,
                    "pnl": 10.0,
                    "fee": -0.5,
                    "pnl_percent": 0.05,
                    "reasoning": "take_profit",
                    "metadata": {"gateway": {"op": "close"}, "strategy_id": "s1"},
                },
                {
                    "timestamp": "2026-05-18T10:00:00Z",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "price": 100.0,
                    "quantity": 1.0,
                    "pnl": 0.0,
                    "fee": -0.2,
                    "pnl_percent": 0.0,
                    "metadata": {"gateway": {"op": "open"}, "strategy_id": "s1"},
                },
                {
                    "timestamp": "2026-05-01T10:00:00Z",
                    "symbol": "SOL/USDT/SWAP",
                    "side": "buy",
                    "price": 150.0,
                    "quantity": 1.0,
                    "pnl": -400.0,
                    "fee": -1.0,
                    "pnl_percent": 0.0,
                    "strategy": "unknown",
                    "metadata": {"db_id": 99, "source": "historical_db"},
                },
            ]

    data = await _build_trade_lifecycle_summary(
        SimpleNamespace(trade_history_service=_TradeHistory()),
        trade_limit=10,
        recent_limit=5,
    )

    assert data["summary"]["sample_size"] == 2
    assert data["summary"]["realized_pnl"] == 10.0
    assert data["summary"]["fees"] == -0.7


@pytest.mark.asyncio
async def test_closed_loop_ignores_stale_runtime_watch_and_uses_live_trade_fallback(monkeypatch):
    class _TradeHistory:
        async def get_trade_history(self, limit: int = 1000):
            return [
                {
                    "timestamp": "2026-05-18T12:00:00Z",
                    "symbol": "BTC/USDT",
                    "side": "sell",
                    "price": 110.0,
                    "quantity": 1.0,
                    "pnl": 10.0,
                    "fee": -0.5,
                    "pnl_percent": 0.05,
                    "reasoning": "take_profit",
                    "metadata": {
                        "gateway": {"op": "close"},
                        "decision_action": "CLOSE_LONG",
                        "strategy_id": "s1",
                        "semantic_context": {"regime_label": "trend_up"},
                    },
                }
            ]

    class _Store:
        def analyze_recent(self, limit: int = 120):
            return {"summary": {"guard_rejected": 0}, "recent": []}

    async def _fake_monitoring_summary():
        return {"active_alerts": 2, "total_trades": 1, "strategies": ["s1"]}

    mc = SimpleNamespace(
        decision_trace_store=_Store(),
        trade_history_service=_TradeHistory(),
        get_system_status=lambda: None,
        _latest_account_state={"usdt_total": 3210.5},
    )

    async def _system_status():
        return {"running_modules": 7}

    mc.get_system_status = _system_status

    monkeypatch.setattr(
        module_control_api,
        "_load_runtime_json_snapshot",
        lambda *args, **kwargs: {
            "available": True,
            "fresh": False,
            "age_seconds": 99999.0,
            "last_modified": "2026-05-14T07:15:42+00:00",
            "stale_after_seconds": 1800.0,
            "payload": {
                "analysis": {
                    "latest_trade": {"symbol": "OLD/USDT"},
                    "best_regime": {"regime": "obsolete"},
                }
            },
        },
    )
    monkeypatch.setattr(monitoring_api, "get_monitoring_summary", _fake_monitoring_summary)

    data = await _build_closed_loop_summary_data(mc, trace_limit=20)

    assert data["runtime_watch"]["fresh"] is False
    assert data["observability_gaps"]["runtime_watch_fresh"] is False
    assert data["loop_health"]["equity"] == 3210.5
    assert data["exit_and_profitability"]["realized_performance"]["latest_trade"]["symbol"] == "BTC/USDT"
    assert data["exit_and_profitability"]["realized_performance"]["best_regime"]["regime"] == "trend_up"
    assert any(hint["area"] == "trade_analytics_freshness" for hint in data["optimization_hints"])


@pytest.mark.asyncio
async def test_closed_loop_filters_low_fidelity_history_and_inferrs_regime(monkeypatch):
    class _TradeHistory:
        async def get_trade_history(self, limit: int = 1000):
            return [
                {
                    "timestamp": "2026-05-18T12:00:00Z",
                    "symbol": "BTC/USDT",
                    "side": "sell",
                    "price": 110.0,
                    "quantity": 1.0,
                    "pnl": 8.0,
                    "fee": -0.5,
                    "pnl_percent": 0.04,
                    "reasoning": "take_profit",
                    "strategy": "default_trend_following_ma",
                    "metadata": {"gateway": {"op": "close"}, "strategy_id": "default_trend_following_ma"},
                },
                {
                    "timestamp": "2026-05-01T10:00:00Z",
                    "symbol": "SOL/USDT/SWAP",
                    "side": "buy",
                    "price": 150.0,
                    "quantity": 1.0,
                    "pnl": -400.0,
                    "fee": -1.0,
                    "pnl_percent": 0.0,
                    "strategy": "unknown",
                    "metadata": {"db_id": 99, "source": "historical_db"},
                },
            ]

    class _Store:
        def analyze_recent(self, limit: int = 120):
            return {"summary": {"guard_rejected": 0}, "recent": []}

    monkeypatch.setattr(
        module_control_api,
        "_load_runtime_json_snapshot",
        lambda *args, **kwargs: {"available": True, "fresh": False, "payload": {"analysis": {}}},
    )

    mc = SimpleNamespace(
        decision_trace_store=_Store(),
        trade_history_service=_TradeHistory(),
        get_system_status=lambda: None,
        _latest_account_state={"usdt_total": 1000.0},
    )

    data = await _build_closed_loop_summary_data(mc, trace_limit=20)
    realized = data["exit_and_profitability"]["realized_performance"]

    assert realized["best_regime"]["regime"] == "trend"
    assert realized["worst_regime"]["regime"] == "trend"
    assert realized["worst_regime"]["total_pnl"] == 8.0
