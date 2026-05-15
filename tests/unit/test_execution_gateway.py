"""Unit tests for ExecutionGateway (S1 policy + narrow exit)."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.modules.core.decision_trace_store import DecisionTraceStore
from src.modules.core.execution_gateway import ExecutionGateway


def _mc_with_exchange(ex, swo="ai_core", ai_brain=None):
    mc = MagicMock()
    # Important: ExecutionGateway._exchange() prefers execution_exchange first.
    # MagicMock would otherwise fabricate a truthy attribute and break awaits.
    mc.execution_exchange = None
    mc.exchange = None
    mc.okx_exchange = ex
    brain = ai_brain or {"single_write_owner": swo, "primary_controller": swo}
    mc.get_ai_managed_config = AsyncMock(
        return_value=brain
    )
    mc.config_manager = MagicMock()
    mc.config_manager.get_config_sync = MagicMock(return_value=brain)
    return mc


def _mc_with_exchange_and_policy(ex, swo="ai_core", hosting_mode="full_auto", automation_profile="semi_auto", redlines=None, ai_brain=None):
    mc = _mc_with_exchange(ex, swo=swo, ai_brain=ai_brain)
    mc.get_hosting_mode = MagicMock(return_value=hosting_mode)
    mc.get_automation_profile = MagicMock(return_value=automation_profile)
    mc.get_risk_redlines = MagicMock(return_value=(redlines or {}))
    return mc


@pytest.mark.asyncio
async def test_close_denied_when_source_not_swo():
    ex = MagicMock()
    ex.close_swap_position = AsyncMock(return_value={"success": True})
    gw = ExecutionGateway(_mc_with_exchange(ex))
    res = await gw.close_swap("BTC/USDT", "long", None, "ai_trading_engine", "t")
    assert res["success"] is False
    assert "policy_denied" in res.get("error", "")
    ex.close_swap_position.assert_not_called()


@pytest.mark.asyncio
async def test_close_allowed_for_stop_loss_take_profit():
    ex = MagicMock()
    ex.close_swap_position = AsyncMock(return_value={"success": True, "orderId": "1"})
    gw = ExecutionGateway(_mc_with_exchange(ex))
    res = await gw.close_swap("BTC/USDT", "long", 1.0, "stop_loss_take_profit", "sl")
    assert res["success"] is True
    ex.close_swap_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_allowed_for_manual():
    ex = MagicMock()
    ex.close_swap_position = AsyncMock(return_value={"success": True, "orderId": "m1"})
    gw = ExecutionGateway(_mc_with_exchange(ex, swo="ai_core"))
    res = await gw.close_swap("BTC/USDT", "short", None, "manual", "user_api")
    assert res["success"] is True
    ex.close_swap_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_open_denied_when_source_not_swo():
    ex = MagicMock()
    ex.set_leverage = AsyncMock(return_value={"success": True})
    ex.open_swap_position = AsyncMock(return_value={"success": True})
    gw = ExecutionGateway(_mc_with_exchange(ex))
    res = await gw.open_swap("BTC/USDT", "long", 1.0, 20, "ai_trading_engine", "t")
    assert res["success"] is False
    assert "open_policy_denied" in res.get("error", "")
    ex.open_swap_position.assert_not_called()


@pytest.mark.asyncio
async def test_open_denied_for_legacy_execution_verifier_tag():
    """write_source 必须显式为 SWO（如 ai_core），不再放行裸 execution_verifier。"""
    ex = MagicMock()
    ex.set_leverage = AsyncMock(return_value={"success": True})
    ex.open_swap_position = AsyncMock(return_value={"success": True})
    gw = ExecutionGateway(_mc_with_exchange(ex, swo="ai_core"))
    res = await gw.open_swap("BTC/USDT", "long", 1.0, 20, "execution_verifier", "t")
    assert res["success"] is False
    assert "open_policy_denied" in res.get("error", "")
    ex.open_swap_position.assert_not_called()


@pytest.mark.asyncio
async def test_open_allowed_for_ai_core():
    ex = MagicMock()
    ex.set_leverage = AsyncMock(return_value={"success": True})
    ex.open_swap_position = AsyncMock(return_value={"success": True, "orderId": "x"})
    gw = ExecutionGateway(_mc_with_exchange(ex, swo="ai_core"))
    res = await gw.open_swap("BTC/USDT", "long", 1.0, 20, "ai_core", "decision")
    assert res["success"] is True
    ex.open_swap_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_idempotent_within_ttl():
    ex = MagicMock()
    ex.close_swap_position = AsyncMock(return_value={"success": True})
    gw = ExecutionGateway(_mc_with_exchange(ex))
    r1 = await gw.close_swap("ETH/USDT", "short", 2.0, "stop_loss_take_profit", "a")
    r2 = await gw.close_swap("ETH/USDT", "short", 2.0, "stop_loss_take_profit", "b")
    assert r1.get("success") is True
    assert r2.get("skipped") is True
    ex.close_swap_position.assert_awaited_once()

@pytest.mark.asyncio
async def test_close_denied_for_system_source():
    ex = MagicMock()
    ex.close_swap_position = AsyncMock(return_value={"success": True})
    gw = ExecutionGateway(_mc_with_exchange(ex, swo="ai_core"))
    res = await gw.close_swap("BTC/USDT", "long", None, "system", "proactive")
    assert res["success"] is False
    assert "policy_denied" in res.get("error", "")
    ex.close_swap_position.assert_not_called()


@pytest.mark.asyncio
async def test_open_denied_in_semi_auto_without_manual_approval():
    ex = MagicMock()
    ex.open_swap_position = AsyncMock(return_value={"success": True, "orderId": "x"})
    mc = _mc_with_exchange_and_policy(ex, swo="ai_core", hosting_mode="semi_auto")
    gw = ExecutionGateway(mc)
    res = await gw.open_swap("BTC/USDT", "long", 1.0, 20, "ai_core", "decision")
    assert res["success"] is False
    assert "半自动" in res.get("error", "") or "semi" in res.get("error", "")
    ex.open_swap_position.assert_not_called()


@pytest.mark.asyncio
async def test_open_allowed_in_semi_auto_with_manual_approval():
    ex = MagicMock()
    ex.open_swap_position = AsyncMock(return_value={"success": True, "orderId": "x"})
    mc = _mc_with_exchange_and_policy(ex, swo="ai_core", hosting_mode="semi_auto")
    gw = ExecutionGateway(mc)
    res = await gw.open_swap(
        "BTC/USDT",
        "long",
        1.0,
        20,
        "ai_core",
        "decision",
        context={"manual_approved": True},
    )
    assert res["success"] is True
    ex.open_swap_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_open_denied_by_risk_redlines_max_positions():
    ex = MagicMock()
    ex.get_positions = AsyncMock(return_value=[{"symbol": "ETH/USDT", "size": 1.0, "side": "long"}])
    ex.open_swap_position = AsyncMock(return_value={"success": True, "orderId": "x"})
    mc = _mc_with_exchange_and_policy(ex, swo="ai_core", redlines={"max_positions": 1})
    gw = ExecutionGateway(mc)
    res = await gw.open_swap("BTC/USDT", "long", 1.0, 20, "ai_core", "decision")
    assert res["success"] is False
    assert "风控红线" in res.get("error", "") or "max_positions" in res.get("error", "")
    ex.open_swap_position.assert_not_called()


@pytest.mark.asyncio
async def test_open_same_symbol_scale_in_not_blocked_by_max_positions():
    ex = MagicMock()
    ex.get_positions = AsyncMock(return_value=[{"symbol": "BTC/USDT/SWAP", "size": 1.0, "side": "long"}])
    ex.open_swap_position = AsyncMock(return_value={"success": True, "orderId": "x"})
    mc = _mc_with_exchange_and_policy(ex, swo="ai_core", redlines={"max_positions": 1})
    gw = ExecutionGateway(mc)
    gw._reconciler.build_snapshot = AsyncMock(
        return_value={
            "healthy": True,
            "severity": "ok",
            "summary": {"drift_total": 0, "stale_open_orders": 0},
            "position_drifts": {},
            "order_signals": {},
            "safe_recovery": {"policy": "safe_only_no_cancel_no_force_close"},
            "exchange_errors": {},
        }
    )
    res = await gw.open_swap("BTC/USDT", "long", 1.0, 20, "ai_core", "decision")
    assert res["success"] is True
    ex.open_swap_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_open_denied_by_max_positions_includes_slot_release_candidates():
    ex = MagicMock()
    ex.get_positions = AsyncMock(
        return_value=[
            {"symbol": "BTC/USDT/SWAP", "size": 1.0, "side": "long", "unrealized_pnl": 3.7, "unrealized_pnl_ratio": 0.12, "notional_value": 790},
            {"symbol": "AVAX/USDT/SWAP", "size": 3.4, "side": "short", "unrealized_pnl": 0.02, "unrealized_pnl_ratio": 0.0069, "notional_value": 33.2},
        ]
    )
    ex.open_swap_position = AsyncMock(return_value={"success": True, "orderId": "x"})
    mc = _mc_with_exchange_and_policy(ex, swo="ai_core", redlines={"max_positions": 2})
    mc.stop_loss_manager = MagicMock()
    mc.stop_loss_manager.get_stats = MagicMock(
        return_value={"sr_recent_events": [{"symbol": "AVAX/USDT/SWAP", "event": "sr_near_support_partial_tp"}]}
    )
    gw = ExecutionGateway(mc)
    ctx = {}
    res = await gw.open_swap("ETH/USDT", "long", 1.0, 20, "ai_core", "decision", context=ctx)
    assert res["success"] is False
    assert "候选释放槽位" in res.get("error", "")
    assert isinstance(ctx.get("slot_release_candidates"), list)
    assert ctx["slot_release_candidates"][0]["symbol"] == "AVAX/USDT"
    ex.open_swap_position.assert_not_called()


@pytest.mark.asyncio
async def test_open_full_positions_can_replace_worst_and_retry():
    full_positions = [
        {"symbol": "BTC/USDT/SWAP", "size": 1.0, "side": "long", "unrealized_pnl": 3.7, "unrealized_pnl_ratio": 0.12, "notional_value": 790},
        {"symbol": "AVAX/USDT/SWAP", "size": 3.4, "side": "short", "unrealized_pnl": 0.02, "unrealized_pnl_ratio": 0.0069, "notional_value": 33.2},
    ]
    after_close_positions = [
        {"symbol": "BTC/USDT/SWAP", "size": 1.0, "side": "long", "unrealized_pnl": 3.7, "unrealized_pnl_ratio": 0.12, "notional_value": 790},
    ]
    ex = MagicMock()
    ex.get_positions = AsyncMock(
        side_effect=[
            full_positions,       # first redline check
            full_positions,       # close before-size snapshot
            after_close_positions,  # close post-check snapshot
            after_close_positions,  # retry open redline check
        ]
    )
    ex.close_swap_position = AsyncMock(return_value={"success": True, "orderId": "c1"})
    ex.open_swap_position = AsyncMock(return_value={"success": True, "orderId": "o1"})
    mc = _mc_with_exchange_and_policy(ex, swo="ai_core", redlines={"max_positions": 2})
    mc.stop_loss_manager = MagicMock()
    mc.stop_loss_manager.get_stats = MagicMock(
        return_value={"sr_recent_events": [{"symbol": "AVAX/USDT/SWAP", "event": "sr_near_support_partial_tp"}]}
    )
    gw = ExecutionGateway(mc)
    gw._reconciler.build_snapshot = AsyncMock(
        return_value={
            "healthy": True,
            "severity": "ok",
            "summary": {"drift_total": 0, "stale_open_orders": 0},
            "position_drifts": {},
            "order_signals": {},
            "safe_recovery": {"policy": "safe_only_no_cancel_no_force_close"},
            "exchange_errors": {},
        }
    )
    res = await gw.open_swap(
        "ETH/USDT",
        "long",
        1.0,
        20,
        "ai_core",
        "decision",
        context={"confidence": 0.82, "semantic_context": {"risk_verdict": "review", "execution_recommendation": "normal"}},
    )
    assert res["success"] is True
    ex.close_swap_position.assert_awaited_once()
    ex.open_swap_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_snapshot_exposes_replace_worst_policy_from_ai_brain():
    ex = MagicMock()
    mc = _mc_with_exchange(
        ex,
        swo="ai_core",
        ai_brain={
            "single_write_owner": "ai_core",
            "primary_controller": "ai_core",
            "policy": {
                "enable_replace_worst_on_full_positions": False,
                "replace_worst_min_confidence": 0.83,
            },
        },
    )
    gw = ExecutionGateway(mc)
    gw._reconciler.build_snapshot = AsyncMock(
        return_value={
            "healthy": True,
            "severity": "ok",
            "summary": {"drift_total": 0, "stale_open_orders": 0},
            "position_drifts": {},
            "order_signals": {},
            "safe_recovery": {"policy": "safe_only_no_cancel_no_force_close"},
            "exchange_errors": {},
        }
    )

    snap = await gw.get_snapshot()

    assert snap["replace_worst_policy"] == {
        "enable_replace_worst_on_full_positions": False,
        "replace_worst_min_confidence": 0.83,
    }


@pytest.mark.asyncio
async def test_open_records_semantic_context_into_trace():
    ex = MagicMock()
    ex.set_leverage = AsyncMock(return_value={"success": True})
    ex.open_swap_position = AsyncMock(return_value={"success": True, "orderId": "x"})
    mc = _mc_with_exchange(ex, swo="ai_core")
    mc.decision_trace_store = DecisionTraceStore(max_items=20, persist_path="")
    gw = ExecutionGateway(mc)
    gw._reconciler.build_snapshot = AsyncMock(
        return_value={
            "healthy": True,
            "severity": "ok",
            "summary": {"drift_total": 0, "stale_open_orders": 0},
            "position_drifts": {},
            "order_signals": {},
            "safe_recovery": {"policy": "safe_only_no_cancel_no_force_close"},
            "exchange_errors": {},
        }
    )
    res = await gw.open_swap(
        "BTC/USDT",
        "long",
        1.0,
        20,
        "ai_core",
        "decision",
        context={
            "trace_id": "trace-semantic-open",
            "semantic_context": {
                "regime_label": "trend_up",
                "risk_posture": "balanced",
                "execution_recommendation": "normal",
            },
        },
    )
    assert res["success"] is True
    row = mc.decision_trace_store.get_by_trace_id("trace-semantic-open")
    assert row is not None
    assert row["reconciliation"]["status"] == "success"
    assert row["execution"]["status"] == "success"
    assert row["workflow"]["current_stage"] == "execution:open"
    assert row["workflow"]["status"] == "completed"
    assert row["market_context"]["regime_label"] == "trend_up"
    assert [x["stage"] for x in row["stage_history"][-2:]] == ["reconciliation", "execution:open"]


@pytest.mark.asyncio
async def test_open_reconciliation_blocked_records_trace():
    ex = MagicMock()
    ex.set_leverage = AsyncMock(return_value={"success": True})
    ex.open_swap_position = AsyncMock(return_value={"success": True, "orderId": "x"})
    mc = _mc_with_exchange(ex, swo="ai_core")
    mc.decision_trace_store = DecisionTraceStore(max_items=20, persist_path="")
    gw = ExecutionGateway(mc)
    gw._reconciler.build_snapshot = AsyncMock(
        return_value={
            "healthy": False,
            "severity": "critical",
            "summary": {"drift_total": 2, "stale_open_orders": 1},
            "position_drifts": {"local_only_positions": [{"symbol": "BTC/USDT"}]},
            "order_signals": {"open_orders_without_position": [{"symbol": "BTC/USDT"}]},
            "safe_recovery": {"policy": "safe_only_no_cancel_no_force_close"},
            "exchange_errors": {},
        }
    )
    gw._reconciliation_protection.allow_open = MagicMock(
        return_value="reconciliation_symbol_protection:120s:symbol_drift"
    )

    res = await gw.open_swap(
        "BTC/USDT",
        "long",
        1.0,
        20,
        "ai_core",
        "decision",
        context={"trace_id": "trace-reconciliation-block"},
    )

    assert res["success"] is False
    assert "reconciliation_symbol_protection" in res["error"]
    ex.open_swap_position.assert_not_called()
    row = mc.decision_trace_store.get_by_trace_id("trace-reconciliation-block")
    assert row is not None
    assert row["reconciliation"]["status"] == "blocked"
    assert row["workflow"]["current_stage"] == "reconciliation"
    assert row["workflow"]["status"] == "reconcile_blocked"


def test_recent_events_persist_across_gateway_restart(tmp_path, monkeypatch):
    persist_path = tmp_path / "execution_gateway_recent_events.json"
    monkeypatch.setenv("OPENCLAW_EXECUTION_GATEWAY_RECENT_EVENTS_JSON", str(persist_path))
    monkeypatch.setenv("OPENCLAW_EXECUTION_GATEWAY_RECENT_EVENTS_PERSIST", "1")
    ex = MagicMock()
    gw = ExecutionGateway(_mc_with_exchange(ex, swo="ai_core"))

    gw._record_order(
        "ai_core",
        "open",
        False,
        "风控红线拦截：持仓数 5 已达到上限 5 (max_positions)",
        symbol="DOGE/USDT",
        side="long",
        size=12.0,
        leverage=10,
        reason="decision",
        context={"trace_id": "trace-persist-1"},
    )

    payload = json.loads(persist_path.read_text(encoding="utf-8"))
    assert payload["recent_events"][-1]["symbol"] == "DOGE/USDT"
    assert payload["recent_events"][-1]["error_code"] == "RISK_REDLINE_DENIED"

    gw2 = ExecutionGateway(_mc_with_exchange(ex, swo="ai_core"))
    assert gw2._snapshot.recent_events[-1]["symbol"] == "DOGE/USDT"
    assert gw2._snapshot.recent_events[-1]["error_code"] == "RISK_REDLINE_DENIED"


@pytest.mark.asyncio
async def test_close_records_reconciliation_before_execution():
    ex = MagicMock()
    ex.close_swap_position = AsyncMock(return_value={"success": True, "orderId": "c1"})
    ex.get_positions = AsyncMock(return_value=[])
    mc = _mc_with_exchange(ex, swo="ai_core")
    mc.decision_trace_store = DecisionTraceStore(max_items=20, persist_path="")
    gw = ExecutionGateway(mc)
    gw._reconciler.build_snapshot = AsyncMock(
        return_value={
            "healthy": True,
            "severity": "ok",
            "summary": {"drift_total": 0, "stale_open_orders": 0},
            "position_drifts": {},
            "order_signals": {},
            "safe_recovery": {"policy": "safe_only_no_cancel_no_force_close"},
            "exchange_errors": {},
        }
    )

    res = await gw.close_swap(
        "BTC/USDT",
        "long",
        1.0,
        "manual",
        "user_api",
        context={"trace_id": "trace-close-reconciliation"},
    )

    assert res["success"] is True
    row = mc.decision_trace_store.get_by_trace_id("trace-close-reconciliation")
    assert row is not None
    assert row["reconciliation"]["status"] == "success"
    assert row["execution"]["status"] == "success"
    assert row["workflow"]["current_stage"] == "execution:close"
    assert [x["stage"] for x in row["stage_history"][-2:]] == ["reconciliation", "execution:close"]
