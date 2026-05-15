import pytest

from src.modules.core.strategy_manager import StrategyManager


@pytest.mark.asyncio
async def test_market_structure_governance_downweight_observe_and_recover():
    sm = StrategyManager(None)
    await sm.load_strategy_config(
        {
            "strategy_id": "btc_live",
            "name": "BTC Live",
            "strategy_type": "ai_generated",
            "symbols": ["BTC/USDT"],
            "metadata": {
                "deployment": {"stage": "full", "cap_multiplier": 1.0},
                "research": {
                    "test": {"passed": True},
                    "experiment_card": {"hypothesis": "trend", "cost_model": {"fees_bps": 5}},
                    "review": {"answers": {
                        "what_edge": "edge",
                        "why_not_immediately_gone": "friction",
                        "net_after_cost": "positive",
                        "failure_shape": "reversal",
                        "kill_signal": "oos fail",
                    }},
                },
            },
        }
    )

    down = sm.record_market_structure_snapshot(
        "BTC/USDT",
        {
            "regime_label": "liquidity_stress",
            "risk_posture": "capital_preservation",
            "liquidity_state": "stressed",
            "confidence": 0.82,
            "signal_conflict_score": 0.2,
        },
        apply_now=True,
    )
    assert down["actions"][0]["action"] == "downweight"
    profile = sm.get_strategy_governance_profile("btc_live")
    assert profile["deployment_stage"] == "shadow"
    assert profile["market_structure_overlay"]["status"] == "downweighted"

    observe = sm.apply_market_structure_governance(
        "BTC/USDT",
        {
            "regime_label": "crowded_derivatives",
            "risk_posture": "defensive",
            "liquidity_state": "fragile",
            "confidence": 0.7,
            "signal_conflict_score": 0.7,
        },
    )
    assert observe["actions"][0]["action"] == "observe"
    profile = sm.get_strategy_governance_profile("btc_live")
    assert profile["market_structure_overlay"]["status"] == "observing"
    assert profile["effective_cap_multiplier"] == pytest.approx(0.125)

    recover1 = sm.apply_market_structure_governance(
        "BTC/USDT",
        {
            "regime_label": "trend_up",
            "risk_posture": "offensive",
            "liquidity_state": "healthy",
            "confidence": 0.8,
            "signal_conflict_score": 0.1,
        },
    )
    assert recover1["actions"][0]["action"] == "hold"

    recover2 = sm.apply_market_structure_governance(
        "BTC/USDT",
        {
            "regime_label": "trend_up",
            "risk_posture": "offensive",
            "liquidity_state": "healthy",
            "confidence": 0.8,
            "signal_conflict_score": 0.1,
        },
    )
    assert recover2["actions"][0]["action"] == "recover"
    profile = sm.get_strategy_governance_profile("btc_live")
    assert profile["deployment_stage"] == "full"
    assert profile["market_structure_overlay"]["status"] == "recovered"
    assert profile["effective_cap_multiplier"] == pytest.approx(1.0)

    summary = sm.get_market_structure_governance_status()
    assert "BTC/USDT" in summary["tracked_symbols"]
    assert summary["status_counts"]["recovered"] >= 1
