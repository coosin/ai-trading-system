from types import SimpleNamespace

import pytest

from src.modules.core.strategy_manager import MarketRegime, StrategyLifecycleStage, StrategyManager, StrategyType


def _cfg(strategy_id: str, strategy_type: StrategyType, score: float, enabled: bool = True):
    return SimpleNamespace(
        strategy_id=strategy_id,
        strategy_type=strategy_type,
        enabled=enabled,
        metadata={
            "research": {"score": score},
            "deployment": {"stage": "paper"},
        },
        stage=StrategyLifecycleStage.OOS_VALIDATING,
        updated_at=None,
    )


@pytest.mark.asyncio
async def test_auto_select_high_score_strategies_retires_low_ranked_research():
    sm = StrategyManager(SimpleNamespace())
    sm.market_regime = MarketRegime.BULL
    sm.strategy_configs = {
        "dsl_top_1": _cfg("dsl_top_1", StrategyType.TREND_FOLLOWING, 1.25, enabled=False),
        "dsl_top_2": _cfg("dsl_top_2", StrategyType.TREND_FOLLOWING, 1.1, enabled=False),
        "dsl_top_3": _cfg("dsl_top_3", StrategyType.ML_BASED, 1.0, enabled=False),
        "dsl_low_1": _cfg("dsl_low_1", StrategyType.MEAN_REVERSION, 0.2, enabled=True),
    }

    result = await sm._auto_select_high_score_strategies()

    assert result["selected"] == ["dsl_top_1", "dsl_top_2", "dsl_top_3"]
    assert result["retired"] == ["dsl_low_1"]
    assert sm.strategy_configs["dsl_top_1"].enabled is True
    assert sm.strategy_configs["dsl_low_1"].enabled is False
    assert sm.strategy_configs["dsl_low_1"].stage == StrategyLifecycleStage.RETIRED
    assert sm.strategy_configs["dsl_top_1"].metadata["review_window"]["selection_reason"] == "selected_high_score"
    assert sm.strategy_configs["dsl_low_1"].metadata["review_window"]["selection_reason"] == "retired_low_score"


def test_strategy_pool_score_adapts_to_market_regime():
    sm = StrategyManager(SimpleNamespace())
    trend_cfg = _cfg("dsl_trend", StrategyType.TREND_FOLLOWING, 1.0)
    mean_cfg = _cfg("dsl_mean", StrategyType.MEAN_REVERSION, 1.0)

    sm.market_regime = MarketRegime.BULL
    trend_score = sm._calc_strategy_pool_score("dsl_trend", trend_cfg)
    mean_score = sm._calc_strategy_pool_score("dsl_mean", mean_cfg)

    assert trend_score > mean_score
