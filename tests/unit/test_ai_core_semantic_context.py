from types import SimpleNamespace
from unittest.mock import MagicMock

from src.modules.core.ai_core_decision_engine import AICoreDecisionEngine, TradeDecision


def test_build_semantic_trade_context_enriches_agent_inputs():
    eng = AICoreDecisionEngine()

    strategy_manager = MagicMock()
    strategy_manager.get_strategy_governance_profile.return_value = {
        "strategy_id": "trend_v1",
        "stage": "limited_live",
        "oos_status": "passed",
        "live_drift_status": "healthy",
        "deployment_stage": "paper",
        "effective_cap_multiplier": 0.8,
        "market_structure_overlay": {"status": "normal"},
        "updated_at": "2025-01-01T00:00:00",
    }
    strategy_manager.get_strategy_research_profile.return_value = {
        "strategy_id": "trend_v1",
        "hypothesis": "trend continuation",
        "review_status": "approved",
        "review_completion_status": "completed",
        "last_review_type": "weekly",
        "last_reviewed_at": "2025-01-02T00:00:00",
        "action_items": ["monitor slippage"],
        "peer_review_answers": {
            "what_edge": "trend persistence",
            "why_not_immediately_gone": "fragmented liquidity",
            "net_after_cost": "positive",
            "failure_shape": "range chop",
            "kill_signal": "drift",
        },
        "failure_cases": [{"kind": "range_chop"}],
        "parameter_sensitivity": {"lookback": "medium"},
    }

    market_structure_engine = MagicMock()
    market_structure_engine.analyze_symbol.return_value = SimpleNamespace(
        to_dict=lambda: {
            "regime_label": "trend",
            "risk_posture": "balanced",
            "trend_state": "bullish",
            "volatility_state": "normal",
            "liquidity_state": "healthy",
            "derivatives_state": "supportive",
            "stablecoin_flow_state": "neutral",
            "execution_quality_state": "good",
            "signal_conflict_score": 0.11,
            "avoid_symbols": [],
            "preferred_setups": ["pullback"],
        }
    )

    eng.main_controller = SimpleNamespace(
        strategy_manager=strategy_manager,
        market_structure_engine=market_structure_engine,
        feature_store_lite=None,
    )

    ctx = eng._build_semantic_trade_context(
        symbol="BTC/USDT",
        strategy_used="trend_v1",
        market_analysis={
            "price": 100.0,
            "confidence": 0.81,
            "trend": "bullish",
            "spread_bps": 7.5,
            "depth_imbalance": 0.44,
            "funding_rate": 0.0003,
            "open_interest": 123456.0,
            "quality_score": 0.86,
            "recommendation": "follow_trend",
            "sentiment": "bullish",
            "reasoning": "test semantic context",
            "exchange_reachability": {"status": "degraded", "ok": True},
            "memory_refs": ["mem-1", "mem-1", "mem-2"],
        },
        confidence=0.81,
        risk_level="low",
    )

    assert ctx["strategy_id"] == "trend_v1"
    assert ctx["spread_bps"] == 7.5
    assert ctx["depth_imbalance"] == 0.44
    assert ctx["exchange_reachability_status"] == "degraded"
    assert ctx["exchange_reachability_ok"] is True
    assert ctx["research_review_completion_status"] == "completed"
    assert ctx["missing_peer_review_answers"] == []
    assert ctx["research_failure_case_count"] == 1
    assert ctx["parameter_sensitivity_keys"] == ["lookback"]
    assert ctx["knowledge_refs"] == ["trend_v1"]
    assert ctx["memory_refs"] == ["mem-1", "mem-2"]
    assert ctx["governance_summary"]["deployment_stage"] == "paper"
    assert ctx["research_summary"]["hypothesis"] == "trend continuation"
    assert ctx["llm_fallback"] is False
    assert ctx["research_review_ready"] is True
    assert ctx["peer_review_complete"] is True
    assert ctx["profitability_scale_in_ready"] is True


def test_build_semantic_trade_context_marks_scale_in_as_not_ready_when_reason_is_weak():
    eng = AICoreDecisionEngine()

    strategy_manager = MagicMock()
    strategy_manager.get_strategy_governance_profile.return_value = {"strategy_id": "trend_v1"}
    strategy_manager.get_strategy_research_profile.return_value = {
        "strategy_id": "trend_v1",
        "review_status": "draft",
        "review_completion_status": "missing",
        "peer_review_answers": {
            "what_edge": "trend persistence",
        },
    }

    market_structure_engine = MagicMock()
    market_structure_engine.analyze_symbol.return_value = SimpleNamespace(
        to_dict=lambda: {
            "regime_label": "trend",
            "risk_posture": "balanced",
            "trend_state": "bullish",
            "volatility_state": "normal",
            "liquidity_state": "healthy",
            "derivatives_state": "supportive",
            "stablecoin_flow_state": "neutral",
            "execution_quality_state": "good",
            "signal_conflict_score": 0.11,
            "avoid_symbols": [],
            "preferred_setups": ["pullback"],
        }
    )

    eng.main_controller = SimpleNamespace(
        strategy_manager=strategy_manager,
        market_structure_engine=market_structure_engine,
        feature_store_lite=None,
    )

    ctx = eng._build_semantic_trade_context(
        symbol="BTC/USDT",
        strategy_used="trend_v1",
        market_analysis={
            "quality_score": 0.61,
            "llm_fallback": True,
        },
        confidence=0.81,
        risk_level="low",
    )

    assert ctx["profitability_scale_in_ready"] is False
    assert "llm_fallback" in ctx["profitability_scale_in_blockers"]
    assert "research_review_incomplete" in ctx["profitability_scale_in_blockers"]
    assert "peer_review_incomplete" in ctx["profitability_scale_in_blockers"]
    assert "quality_below_scale_in_floor" in ctx["profitability_scale_in_blockers"]


def test_degraded_hold_is_blocked_from_hold_avoidance_override():
    decision = TradeDecision(
        symbol="BTC/USDT",
        action="hold",
        side="long",
        quantity=0,
        leverage=20,
        entry_price=100.0,
        stop_loss=0.0,
        take_profit=0.0,
        confidence=0.0,
        reasoning="llm_unavailable_fallback_hold",
        strategy_used="s1_llm_unavailable_fallback",
        risk_level="medium",
        market_analysis={"llm_fallback": True},
    )

    assert AICoreDecisionEngine._decision_is_degraded_hold_for_profit_protection(decision) is True


def test_normal_hold_is_not_blocked_from_hold_avoidance_override():
    decision = TradeDecision(
        symbol="BTC/USDT",
        action="hold",
        side="long",
        quantity=0,
        leverage=20,
        entry_price=100.0,
        stop_loss=0.0,
        take_profit=0.0,
        confidence=0.62,
        reasoning="await clearer trend alignment",
        strategy_used="trend_v1",
        risk_level="low",
        market_analysis={"quality_score": 0.84},
    )

    assert AICoreDecisionEngine._decision_is_degraded_hold_for_profit_protection(decision) is False
