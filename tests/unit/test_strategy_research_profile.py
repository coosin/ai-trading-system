import pytest

from src.modules.core.strategy_manager import StrategyManager


@pytest.mark.asyncio
async def test_strategy_manager_research_profile_and_review_roundtrip():
    sm = StrategyManager(None)
    await sm.load_strategy_config(
        {
            "strategy_id": "s1",
            "name": "S1",
            "description": "desc",
            "strategy_type": "ai_generated",
            "metadata": {},
        }
    )
    assert sm.save_strategy_experiment_card(
        "s1",
        hypothesis="carry + trend survives OOS",
        experiment_card={"cost_model": {"fees_bps": 8}},
    )
    assert sm.record_strategy_review(
        "s1",
        review_type="weekly",
        answers={"what_edge": "trend persistence"},
        action_items=["monitor slippage"],
    )
    profile = sm.get_strategy_research_profile("s1")
    assert profile["hypothesis"] == "carry + trend survives OOS"
    assert profile["review_completion_status"] == "completed"
    assert profile["action_items"] == ["monitor slippage"]


@pytest.mark.asyncio
async def test_strategy_manager_peer_review_failure_case_and_sensitivity_roundtrip():
    sm = StrategyManager(None)
    await sm.load_strategy_config(
        {
            "strategy_id": "s2",
            "name": "S2",
            "description": "desc",
            "strategy_type": "ai_generated",
            "metadata": {},
        }
    )
    assert sm.record_strategy_peer_review(
        "s2",
        answers={
            "what_edge": "trend persistence",
            "why_not_immediately_gone": "execution frictions",
            "net_after_cost": "still positive",
            "failure_shape": "chop regime",
            "kill_signal": "OOS fail",
        },
        action_items=["reduce chop exposure"],
    )
    assert sm.record_strategy_failure_case(
        "s2",
        title="failed in chop",
        case_type="regime_failure",
        summary="trend logic failed in sideways regime",
        trigger="liquidity stale",
        action_taken="reduced weight",
    )
    assert sm.save_strategy_parameter_sensitivity(
        "s2",
        parameter_sensitivity={"summary": "fragile", "train_vs_oos": {"sharpe_delta": -0.8}},
    )
    profile = sm.get_strategy_research_profile("s2")
    assert profile["review_completion_status"] == "completed"
    assert profile["peer_review_answers"]["kill_signal"] == "OOS fail"
    assert profile["failure_cases"][0]["case_type"] == "regime_failure"
    assert profile["parameter_sensitivity"]["summary"] == "fragile"
