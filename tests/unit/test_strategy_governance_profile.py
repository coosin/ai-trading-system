import pytest

from src.modules.core.strategy_manager import StrategyLifecycleStage, StrategyManager


@pytest.mark.asyncio
async def test_strategy_manager_governance_profile_maps_deployment_stage():
    sm = StrategyManager(None)
    cfg = await sm.load_strategy_config(
        {
            "strategy_id": "research_btc_v1",
            "name": "Research BTC",
            "strategy_type": "ai_generated",
            "metadata": {
                "deployment": {"stage": "shadow", "cap_multiplier": 0.25},
                "research": {"test": {"passed": True}},
            },
        }
    )
    assert cfg is not None
    profile = sm.get_strategy_governance_profile("research_btc_v1")
    assert profile["stage"] == StrategyLifecycleStage.LIMITED_LIVE.value
    assert profile["oos_status"] == "passed"

    changed = sm.set_strategy_governance_state(
        "research_btc_v1",
        stage=StrategyLifecycleStage.SCALED_LIVE,
        live_drift_status="healthy",
        reason="unit_test",
    )
    assert changed is True
    profile = sm.get_strategy_governance_profile("research_btc_v1")
    assert profile["stage"] == StrategyLifecycleStage.SCALED_LIVE.value
    assert profile["live_drift_status"] == "healthy"
