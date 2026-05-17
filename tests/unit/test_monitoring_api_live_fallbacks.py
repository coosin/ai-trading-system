from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.modules.api.monitoring_api as monitoring_api


class _Monitor:
    def get_market_data_status(self):
        return {}

    def get_risk_metrics(self):
        return None

    def get_monitoring_summary(self):
        return {"active_alerts": 0, "total_trades": 0, "strategies": [], "symbols": []}


@pytest.mark.asyncio
async def test_monitoring_risk_falls_back_to_live_positions(monkeypatch):
    class _Exchange:
        async def get_positions(self):
            return [{"symbol": "ETH/USDT/SWAP", "size": 1.0, "notional_value": 240.0, "leverage": 12.0}]

        async def get_balance(self):
            return {}

    ex = _Exchange()
    mc = SimpleNamespace(get_exchange=lambda: ex, okx_exchange=ex, _latest_account_state={})
    monkeypatch.setattr(monitoring_api, "_trading_monitor", _Monitor())
    monkeypatch.setattr(monitoring_api, "_main_controller", mc)

    payload = await monitoring_api.get_risk_metrics()

    assert payload["source"] == "main_controller:positions_estimated"
    assert payload["total_exposure"] == 240.0
    assert payload["position_count"] == 1
    assert payload["warming"] is True


@pytest.mark.asyncio
async def test_monitoring_market_data_falls_back_to_live_hub(monkeypatch):
    class _Exchange:
        async def get_positions(self):
            return [{"symbol": "ETH/USDT/SWAP", "size": 1.0}]

    class _Hub:
        async def get_ticker(self, symbol: str):
            return {
                "symbol": symbol,
                "last": 2480.5,
                "bid": 2480.2,
                "ask": 2480.8,
                "volume": 12.0,
                "change_24h": 0.8,
                "timestamp": "2026-05-18T09:00:00Z",
            }

    ex = _Exchange()
    mc = SimpleNamespace(
        data_source_hub=_Hub(),
        get_exchange=lambda: ex,
        okx_exchange=ex,
        _latest_account_state={},
    )
    monkeypatch.setattr(monitoring_api, "_trading_monitor", _Monitor())
    monkeypatch.setattr(monitoring_api, "_main_controller", mc)

    payload = await monitoring_api.get_market_data_status()

    assert "ETH/USDT/SWAP" in payload
    assert payload["ETH/USDT/SWAP"]["last_price"] == 2480.5
    assert payload["ETH/USDT/SWAP"]["source"] == "main_controller:data_source_hub"


@pytest.mark.asyncio
async def test_monitoring_strategy_and_trade_history_filter_placeholder_rows(monkeypatch):
    class _TradeHistory:
        async def get_trade_history(self, **kwargs):
            return [
                {
                    "timestamp": "2026-05-18T10:00:00Z",
                    "symbol": "BTC/USDT",
                    "side": "sell",
                    "price": 102.0,
                    "quantity": 1.0,
                    "executed_quantity": 1.0,
                    "fee": -0.2,
                    "pnl": 3.5,
                    "pnl_percent": 0.01,
                    "status": "filled",
                    "strategy": "trend_live",
                    "metadata": {"strategy_id": "trend_live", "gateway": {"op": "close"}},
                },
                {
                    "timestamp": "2026-05-18T09:59:00Z",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "price": 0.0,
                    "quantity": 0.0,
                    "executed_quantity": 0.0,
                    "fee": 0.0,
                    "pnl": 0.0,
                    "pnl_percent": 0.0,
                    "status": "filled",
                    "strategy": "none",
                    "metadata": {"strategy_id": "none"},
                },
                {
                    "timestamp": "2026-05-18T09:58:00Z",
                    "symbol": "ETH/USDT",
                    "side": "buy",
                    "price": 2500.0,
                    "quantity": 1.0,
                    "executed_quantity": 1.0,
                    "fee": -0.1,
                    "pnl": 0.0,
                    "pnl_percent": 0.0,
                    "status": "filled",
                    "strategy": "s1_waiting_open_only",
                    "metadata": {"strategy_id": "s1_waiting_open_only", "gateway": {"op": "open"}},
                },
                {
                    "timestamp": "2026-05-18T09:57:00Z",
                    "symbol": "SOL/USDT/SWAP",
                    "side": "buy",
                    "price": 150.0,
                    "quantity": 1.0,
                    "executed_quantity": 1.0,
                    "fee": -0.2,
                    "pnl": -4.0,
                    "pnl_percent": 0.0,
                    "status": "filled",
                    "strategy": "unknown",
                    "metadata": {"db_id": 1, "source": "historical_db"},
                },
            ]

    mc = SimpleNamespace(trade_history_service=_TradeHistory())
    monkeypatch.setattr(monitoring_api, "_trading_monitor", _Monitor())
    monkeypatch.setattr(monitoring_api, "_main_controller", mc)

    trades = await monitoring_api.get_trade_history(limit=10)
    strategies = await monitoring_api.get_strategy_performance()

    assert len(trades) == 2
    assert trades[0]["strategy"] == "trend_live"
    assert any(row["strategy"] == "s1_waiting_open_only" for row in trades)
    assert "trend_live" in strategies
    assert "none" not in strategies
    assert "s1_waiting_open_only" not in strategies
    assert "unattributed" not in strategies


@pytest.mark.asyncio
async def test_monitoring_trade_history_resolves_placeholder_strategy_via_trace(monkeypatch):
    class _TradeHistory:
        async def get_trade_history(self, **kwargs):
            return [
                {
                    "timestamp": "2026-05-18T10:01:00Z",
                    "symbol": "ETH/USDT",
                    "side": "buy",
                    "price": 2200.0,
                    "quantity": 1.0,
                    "executed_quantity": 1.0,
                    "fee": -0.1,
                    "pnl": 2.0,
                    "pnl_percent": 0.01,
                    "status": "filled",
                    "strategy": "none",
                    "reasoning": "execution_verifier_close",
                    "metadata": {
                        "strategy_id": "none",
                        "gateway": {
                            "op": "close",
                            "source": "ai_core",
                            "context": {"trace_id": "trace-autonomy-1"},
                        },
                    },
                },
                {
                    "timestamp": "2026-05-18T10:00:00Z",
                    "symbol": "LINK/USDT/SWAP",
                    "side": "sell",
                    "price": 9.8,
                    "quantity": 1.0,
                    "executed_quantity": 1.0,
                    "fee": -0.01,
                    "pnl": -0.2,
                    "pnl_percent": -0.01,
                    "status": "filled",
                    "strategy": "none",
                    "reasoning": "stop_loss",
                    "metadata": {
                        "strategy_id": "none",
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

    mc = SimpleNamespace(trade_history_service=_TradeHistory(), decision_trace_store=_TraceStore())
    monkeypatch.setattr(monitoring_api, "_trading_monitor", _Monitor())
    monkeypatch.setattr(monitoring_api, "_main_controller", mc)

    trades = await monitoring_api.get_trade_history(limit=10)
    strategies = await monitoring_api.get_strategy_performance()

    assert trades[0]["strategy"] == "s1_ai_autonomy_override"
    assert trades[1]["strategy"] == "sltp_auto_exit"
    assert "s1_ai_autonomy_override" in strategies
    assert "sltp_auto_exit" in strategies
