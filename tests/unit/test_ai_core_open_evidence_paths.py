"""ai_core 开仓证据链：K 线恢复 / 缩量放宽（回归，替代已移除的 debug smoke 脚本）。"""
from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.modules.core.ai_core_decision_engine import AICoreDecisionEngine, TradeDecision


def _engine_for_evidence_smoke() -> AICoreDecisionEngine:
    eng = AICoreDecisionEngine()
    eng.config["leverage_min"] = 1
    eng.config["leverage_max"] = 125
    eng.config["exchange_reachability_gate_enabled"] = False
    eng.config["loss_streak_cooldown_enable"] = False
    eng.config["open_requires_full_snapshot"] = True
    eng.config["open_attempt_klines_recovery_fetch"] = True
    eng.config["open_allow_klines_missing_evidence_fallback"] = True
    eng.config["open_klines_missing_evidence_qty_mult"] = 0.62
    eng.config["analysis_hard_gate_for_open"] = False
    eng.config["sr_timing_guard_enable"] = False
    eng.config["auto_adaptive_guards"] = False
    eng.config["microstructure_enable_funding_oi_gates"] = False
    eng.config["edge_after_cost_guard_enable"] = False
    eng.config["min_rr_to_trade"] = 0.35
    eng.config["max_spread_bps_to_trade"] = 999.0
    eng.config["max_abs_depth_imbalance_to_trade"] = 0.99
    eng.config["ai_core_min_confidence_to_open"] = 0.5
    eng.config["ai_core_min_confidence_floor"] = 0.5
    eng.config["min_confidence_to_trade"] = 0.5
    return eng


def _open_decision(quantity: int = 10) -> TradeDecision:
    return TradeDecision(
        symbol="BTC/USDT/SWAP",
        action="buy",
        side="long",
        quantity=quantity,
        leverage=5,
        entry_price=0.0,
        stop_loss=90.0,
        take_profit=110.0,
        confidence=0.92,
        reasoning="unit_open_evidence_paths",
        strategy_used="unit_smoke_strategy",
        risk_level="low",
        market_analysis={
            "quality_score": 0.72,
            "confidence": 0.72,
            "provenance": "multi_source_fusion",
            "partial": False,
        },
    )


@pytest.mark.asyncio
async def test_open_evidence_klines_recovery_increments_stat():
    eng = _engine_for_evidence_smoke()

    view = MagicMock()
    view.partial = True
    view.errors = ["klines_missing_in_snapshot"]
    mi = MagicMock()
    mi.get_symbol_view = AsyncMock(return_value=view)

    bars = [{"high": 5.0, "low": 4.0, "close": 4.5} for _ in range(25)]
    hub = MagicMock()
    hub.get_klines = AsyncMock(return_value=bars)

    ex = MagicMock()
    ex.get_balance = AsyncMock(return_value={"USDT": {"free": 50000.0}})
    ex.get_ticker = AsyncMock(return_value={"last": 100.0, "bid": 99.9, "ask": 100.1})
    ex.get_swap_symbol_info = AsyncMock(return_value={"ctVal": 0.01, "ctValCcy": "BTC"})

    ok_status = SimpleNamespace(value="success")
    exec_res = SimpleNamespace(status=ok_status, execution_id="e1", details={}, error_message=None)
    mc = MagicMock()
    mc.market_intelligence = mi
    mc.data_source_hub = hub
    mc.config_manager = None
    mc.execute_command = AsyncMock(return_value=exec_res)
    mc.execution_gateway = None

    eng.main_controller = mc
    eng.exchange = ex
    eng._get_technical_indicators = AsyncMock(
        return_value={
            "near_resistance": False,
            "near_support": True,
            "breakout_up_confirmed": True,
            "breakdown_down_confirmed": False,
            "dist_to_resistance_pct": 0.05,
            "dist_to_support_pct": 0.002,
            "resistance_1h": 110.0,
            "support_1h": 90.0,
        }
    )

    d = _open_decision()
    ok = await eng._execute_decision(d)
    assert ok is True
    assert int(eng._execution_guards_stats.get("open_evidence_klines_recovered", 0)) >= 1
    assert int(eng._execution_guards_stats.get("open_evidence_rejected", 0)) == 0


@pytest.mark.asyncio
async def test_open_evidence_klines_relaxed_reduces_qty():
    eng = _engine_for_evidence_smoke()

    view = MagicMock()
    view.partial = True
    view.errors = ["klines_missing_in_snapshot"]
    mi = MagicMock()
    mi.get_symbol_view = AsyncMock(return_value=view)

    hub = MagicMock()
    hub.get_klines = AsyncMock(return_value=[])

    ex = MagicMock()
    ex.get_balance = AsyncMock(return_value={"USDT": {"free": 50000.0}})
    ex.get_ticker = AsyncMock(return_value={"last": 100.0, "bid": 99.9, "ask": 100.1})
    ex.get_swap_symbol_info = AsyncMock(return_value={"ctVal": 0.01, "ctValCcy": "BTC"})

    ok_status = SimpleNamespace(value="success")
    exec_res = SimpleNamespace(status=ok_status, execution_id="e2", details={}, error_message=None)
    mc = MagicMock()
    mc.market_intelligence = mi
    mc.data_source_hub = hub
    mc.config_manager = None
    mc.execute_command = AsyncMock(return_value=exec_res)
    mc.execution_gateway = None

    eng.main_controller = mc
    eng.exchange = ex
    eng._get_technical_indicators = AsyncMock(
        return_value={
            "near_resistance": False,
            "near_support": True,
            "breakout_up_confirmed": True,
            "breakdown_down_confirmed": False,
            "dist_to_resistance_pct": 0.05,
            "dist_to_support_pct": 0.002,
            "resistance_1h": 110.0,
            "support_1h": 90.0,
        }
    )

    d = _open_decision(10)
    ok = await eng._execute_decision(d)
    assert ok is True
    assert int(eng._execution_guards_stats.get("open_evidence_klines_relaxed_ok", 0)) >= 1
    assert float(d.quantity) == 6.0
    assert int(eng._execution_guards_stats.get("open_evidence_rejected", 0)) == 0
