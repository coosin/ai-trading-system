from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.core.ai_core_decision_engine import AICoreDecisionEngine, TradeDecision, _utcnow
from src.modules.core.decision_trace_store import DecisionTraceStore
from src.modules.core.feature_store_lite import FeatureStoreLite


def _decision() -> TradeDecision:
    return TradeDecision(
        symbol="BTC/USDT/SWAP",
        action="buy",
        side="long",
        quantity=10,
        leverage=10,
        entry_price=0.0,
        stop_loss=90.0,
        take_profit=120.0,
        confidence=0.92,
        reasoning="unit_execute_guards",
        strategy_used="unit_execute_strategy",
        risk_level="low",
        market_analysis={"quality_score": 0.85, "confidence": 0.85},
    )


def _engine(tmp_path: Path) -> AICoreDecisionEngine:
    eng = AICoreDecisionEngine()
    eng.config["leverage_min"] = 1
    eng.config["leverage_max"] = 125
    eng.config["open_requires_full_snapshot"] = False
    eng.config["analysis_hard_gate_for_open"] = False
    eng.config["sr_timing_guard_enable"] = False
    eng.config["auto_adaptive_guards"] = False
    eng.config["microstructure_enable_funding_oi_gates"] = False
    eng.config["edge_after_cost_guard_enable"] = False
    eng.config["loss_streak_cooldown_enable"] = False
    eng.config["exchange_reachability_gate_enabled"] = True
    eng.config["min_rr_to_trade"] = 0.35
    eng.config["max_spread_bps_to_trade"] = 999.0
    eng.config["max_abs_depth_imbalance_to_trade"] = 0.99
    eng.config["ai_core_min_confidence_to_open"] = 0.5
    eng.config["ai_core_min_confidence_floor"] = 0.5
    eng.config["min_confidence_to_trade"] = 0.5

    ex = MagicMock()
    ex.get_balance = AsyncMock(return_value={"USDT": {"free": 50000.0}})
    ex.get_ticker = AsyncMock(return_value={"last": 100.0, "bid": 99.9, "ask": 100.1})
    ex.get_swap_symbol_info = AsyncMock(return_value={"ctVal": 0.01, "ctValCcy": "BTC"})
    ex.get_positions = AsyncMock(return_value=[])
    eng.exchange = ex

    mc = MagicMock()
    mc.market_intelligence = None
    mc.data_source_hub = None
    mc.config_manager = None
    mc.execution_gateway = None
    mc.agent_orchestrator = SimpleNamespace(
        get_status=lambda: {"mode": "execution_governed", "workflow": "sequential_handoff"}
    )
    mc.strategy_manager = None
    mc.market_structure_engine = None
    mc.trade_event_hub = None
    mc.decision_trace_store = DecisionTraceStore(
        max_items=20,
        persist_path=str(tmp_path / "decision_trace_store.json"),
    )
    mc.feature_store_lite = FeatureStoreLite(
        max_items_per_table=20,
        persist_path=str(tmp_path / "feature_store_lite.json"),
    )
    ok_status = SimpleNamespace(value="success")
    mc.execute_command = AsyncMock(
        return_value=SimpleNamespace(status=ok_status, execution_id="exec-1", details={}, error_message=None)
    )
    eng.main_controller = mc

    eng._save_decision_to_memory = AsyncMock(return_value=None)
    eng._analyze_trade_and_update_strategy = AsyncMock(return_value=None)
    eng._sync_dynamic_sltp_after_open = AsyncMock(return_value=None)
    return eng


def test_adaptive_open_leverage_target_uses_30_to_100_range(tmp_path):
    eng = _engine(tmp_path)
    eng.config["leverage_min"] = 30
    eng.config["leverage_max"] = 100
    eng.config["default_leverage"] = 30

    d = _decision()
    d.confidence = 0.93
    d.risk_level = "low"

    high_vol = eng._adaptive_open_leverage_target(decision=d, atr_pct_1h=0.07)
    low_vol = eng._adaptive_open_leverage_target(decision=d, atr_pct_1h=0.005)

    assert 30 <= high_vol <= 100
    assert 30 <= low_vol <= 100
    assert low_vol > high_vol


@pytest.mark.asyncio
async def test_execute_decision_rejects_unreachable_exchange_and_records_governance(tmp_path):
    eng = _engine(tmp_path)
    eng.exchange.probe_public_api = AsyncMock(
        return_value={"ok": False, "status_text": "unreachable", "score": 0.0}
    )

    ok = await eng._execute_decision(_decision())

    assert ok is False
    assert eng.main_controller.execute_command.await_count == 0
    assert eng._execution_guards_stats["exchange_unreachable_rejected"] >= 1

    trace = eng.main_controller.decision_trace_store.get_recent(1)[0]
    assert trace["guard"]["reason"] == "exchange_unreachable_open_rejected"
    assert trace["workflow"]["current_stage"] == "guard:exchange_reachability"
    assert trace["workflow"]["status"] == "blocked"
    assert trace["agent_outputs"]["risk_governor_agent"]["structured_verdict"]["exchange_reachability_status"] == "unreachable"

    summary = eng.main_controller.feature_store_lite.get_summary()
    assert summary["guard_status"]["by_value"]["rejected"] >= 1
    assert summary["guard_rejection_reasons"]["by_reason"]["exchange_unreachable_open_rejected"] >= 1


@pytest.mark.asyncio
async def test_execute_decision_degraded_exchange_reduces_qty_and_leverage(tmp_path):
    eng = _engine(tmp_path)
    eng.exchange.probe_public_api = AsyncMock(
        return_value={"ok": True, "status_text": "degraded", "score": 0.42}
    )

    d = _decision()
    ok = await eng._execute_decision(d)

    assert ok is True
    assert eng._execution_guards_stats["exchange_degraded_risk_reduced"] >= 1
    assert d.quantity == 7
    assert 30 <= d.leverage < 100

    called = eng.main_controller.execute_command.await_args.kwargs
    assert called["params"]["quantity"] == 7
    assert called["params"]["leverage"] == d.leverage
    trace = eng.main_controller.decision_trace_store.get_recent(1)[0]
    assert trace["workflow"]["mode"] == "execution_governed"
    assert trace["workflow"]["current_stage"] == "guard:execution_preflight"
    assert trace["workflow"]["status"] == "passed"


@pytest.mark.asyncio
async def test_execute_decision_high_vol_advisory_only_softens_instead_of_rejecting(tmp_path):
    eng = _engine(tmp_path)
    eng.config["auto_adaptive_guards"] = True
    eng.exchange.probe_public_api = AsyncMock(
        return_value={"ok": True, "status_text": "reachable", "score": 1.0}
    )
    eng._get_technical_indicators = AsyncMock(
        return_value={"price": 100.0, "ma5_1h": 103.0, "ma20_1h": 100.0}
    )

    d = _decision()
    ok = await eng._execute_decision(d)

    assert ok is True
    assert eng.main_controller.execute_command.await_count == 1
    assert eng._execution_guards_stats.get("regime_advisory_only_softened", 0) >= 1
    assert d.quantity < 10
    assert 30 <= d.leverage < 100
    called = eng.main_controller.execute_command.await_args.kwargs
    semantic = called["params"]["semantic_context"]
    assert semantic["risk_verdict"] == "caution"
    assert semantic["execution_recommendation"] == "wait_or_slice"
    assert semantic["agent_execution_plan"]["should_block"] is False


@pytest.mark.asyncio
async def test_execute_decision_loss_streak_cooldown_rejects_and_records_reason(tmp_path):
    eng = _engine(tmp_path)
    eng.config["loss_streak_cooldown_enable"] = True
    eng.config["loss_streak_override_enable"] = False
    eng.exchange.probe_public_api = AsyncMock(
        return_value={"ok": True, "status_text": "reachable", "score": 1.0}
    )
    eng._loss_streak_cooldown_until = _utcnow() + timedelta(seconds=600)

    ok = await eng._execute_decision(_decision())

    assert ok is False
    assert eng.main_controller.execute_command.await_count == 0
    assert eng._execution_guards_stats["loss_streak_cooldown_rejected"] >= 1

    recent_guard = eng.main_controller.feature_store_lite.get_recent("guard_results", 1)[0]
    assert recent_guard["stage"] == "loss_streak"
    assert recent_guard["status"] == "rejected"
    assert recent_guard["reason"].startswith("loss_streak_cooldown_active:")


@pytest.mark.asyncio
async def test_execute_hold_decision_records_four_agent_verdicts(tmp_path):
    eng = _engine(tmp_path)

    hold = _decision()
    hold.action = "hold"
    hold.quantity = 0
    hold.leverage = 0
    hold.reasoning = "unit_hold_trace"
    hold.market_analysis = {"quality_score": 0.42, "confidence": 0.42}

    ok = await eng._execute_decision(hold)

    assert ok is True
    assert eng.main_controller.execute_command.await_count == 0

    trace = eng.main_controller.decision_trace_store.get_recent(1)[0]
    assert trace["action"] == "hold"
    assert trace["guard"]["reason"] == "hold_by_ai_decision"
    assert {
        "market_structure_agent",
        "research_agent",
        "risk_governor_agent",
        "execution_coach_agent",
    }.issubset(set((trace.get("agent_outputs") or {}).keys()))


def test_parse_ai_decision_hold_does_not_create_duplicate_parsed_trace(tmp_path):
    eng = AICoreDecisionEngine()
    eng.main_controller = SimpleNamespace(
        decision_trace_store=DecisionTraceStore(
            max_items=20,
            persist_path=str(tmp_path / "decision_trace_store.json"),
        )
    )

    decision = eng._parse_ai_decision(
        '{"action":"hold","confidence":0.31,"reasoning":"unit_parse_hold","strategy_used":"s1"}',
        "BTC/USDT",
    )

    assert decision is not None
    assert decision.action == "hold"
    assert eng.main_controller.decision_trace_store.get_recent(20) == []


def test_pre_decision_agent_advisory_builds_prompt_block(tmp_path):
    eng = _engine(tmp_path)

    advisory = eng._build_pre_decision_agent_advisory(
        symbol="BTC/USDT",
        market_data={"price": 100.0},
        technical={"trend_1h": "bullish", "trend_4h": "bullish", "trend_1d": "bullish"},
        strategy_advice={"strategies": [{"strategy_id": "unit_execute_strategy"}]},
        risk_assessment={"level": "low"},
        multi_source_analysis={"confidence": 0.72, "sentiment": "bullish", "recommendation": "buy"},
        ai_engine_analysis={"trend": "bullish", "confidence": 0.75, "reasoning": "trend aligned"},
        market_intelligence={
            "confidence": 0.7,
            "spread_bps": 8,
            "quality_score": 0.8,
            "signal_conflict_score": 0.12,
            "execution_support": {"guards": {"depth_imbalance_top5": 0.1}},
        },
    )

    assert advisory["verdicts"]
    block = eng._format_agent_advisory_block(advisory)
    assert "四智能体协同建议" in block
    assert "risk=" in block


@pytest.mark.asyncio
async def test_execute_decision_full_positions_fallback_uses_gateway_only(tmp_path):
    eng = _engine(tmp_path)
    eng.exchange.probe_public_api = AsyncMock(
        return_value={"ok": True, "status_text": "reachable", "score": 1.0}
    )
    fail_status = SimpleNamespace(value="failed")
    eng.main_controller.execute_command = AsyncMock(
        return_value=SimpleNamespace(
            status=fail_status,
            execution_id=None,
            details={},
            error_message="风控红线拦截：持仓数 5 已达到上限 5",
        )
    )
    gw = MagicMock()
    gw.close_swap = AsyncMock(return_value={"success": True, "orderId": "close-1"})
    gw.open_swap = AsyncMock(
        return_value={
            "success": True,
            "orderId": "open-1",
            "slot_release_recycled_symbol": "AVAX/USDT",
            "slot_release_recycled_side": "short",
        }
    )
    eng.main_controller.execution_gateway = gw

    ok = await eng._execute_decision(_decision())

    assert ok is True
    gw.open_swap.assert_awaited_once()
    gw.close_swap.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_decision_same_direction_ratio_rejects_without_local_replace_bypass(tmp_path):
    eng = _engine(tmp_path)
    eng.config["max_same_direction_ratio"] = 0.7
    eng.config["max_positions"] = 5
    eng.exchange.probe_public_api = AsyncMock(
        return_value={"ok": True, "status_text": "reachable", "score": 1.0}
    )
    gw = MagicMock()
    gw.open_swap = AsyncMock(return_value={"success": True, "orderId": "unexpected"})
    eng.main_controller.execution_gateway = gw
    eng.exchange.get_positions = AsyncMock(
        return_value=[
            {"symbol": "ETH/USDT/SWAP", "side": "long", "size": 1},
            {"symbol": "SOL/USDT/SWAP", "side": "long", "size": 1},
            {"symbol": "BNB/USDT/SWAP", "side": "long", "size": 1},
            {"symbol": "XRP/USDT/SWAP", "side": "long", "size": 1},
            {"symbol": "DOGE/USDT/SWAP", "side": "short", "size": 1},
        ]
    )

    ok = await eng._execute_decision(_decision())

    assert ok is False
    assert eng.main_controller.execute_command.await_count == 0
    gw.open_swap.assert_not_awaited()
