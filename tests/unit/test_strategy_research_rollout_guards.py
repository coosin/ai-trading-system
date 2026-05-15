from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.research.strategy_research_pipeline import StrategyResearchPipeline


@pytest.mark.asyncio
async def test_publish_defaults_to_auto_paper_with_visible_review_window():
    strategy_manager = MagicMock()
    strategy_manager.load_strategy_config = AsyncMock(
        side_effect=lambda cfg: SimpleNamespace(metadata=cfg.get("metadata", {}))
    )
    strategy_manager.save_strategy_experiment_card = MagicMock()
    strategy_manager.record_strategy_review = MagicMock()
    strategy_manager.save_strategy_parameter_sensitivity = MagicMock()
    strategy_manager.record_strategy_failure_case = MagicMock()
    strategy_manager.get_strategy_instances = AsyncMock(return_value=[])
    strategy_manager.create_strategy_instance = AsyncMock(return_value="inst-1")
    strategy_manager.initialize_strategy = AsyncMock(return_value=True)
    strategy_manager.start_strategy = AsyncMock(return_value=True)
    strategy_manager.get_strategy_activation_gate = MagicMock(
        return_value={"eligible": True, "reasons": [], "stage": "oos_validating"}
    )
    strategy_manager.set_strategy_governance_state = MagicMock()

    controller = SimpleNamespace(
        strategy_manager=strategy_manager,
        log_audit_event=None,
        memory_gateway=None,
        feature_store_lite=None,
    )
    pipeline = StrategyResearchPipeline(main_controller=controller)

    item = await pipeline._publish(
        dsl={
            "symbol": "BTC/USDT",
            "name": "guarded rollout",
            "timeframe": "1h",
            "entry": [{"type": "breakout"}],
            "exit": [{"type": "atr"}],
            "parameters": {},
        },
        test_metrics={"pnl": 12.0, "sharpe": 1.3, "max_drawdown": 0.1, "trades": 12},
        train_metrics={"pnl": 20.0, "sharpe": 1.5, "max_drawdown": 0.08, "trades": 18},
        score=1.25,
        decision="publish",
        research_cfg={},
    )

    assert item is not None
    assert item["deployment_stage"] == "paper"
    assert item["enabled"] is True
    assert item["manual_approval_required"] is False
    assert item["review_window"]["visible"] is True
    assert item["review_window"]["status"] == "open"
    assert item["review_window"]["mode"] == "post_publish_observation"
    strategy_manager.create_strategy_instance.assert_awaited_once()
    loaded_cfg = strategy_manager.load_strategy_config.await_args.args[0]
    assert loaded_cfg["enabled"] is True
    assert loaded_cfg["metadata"]["approval"]["state"] == "approved"
    assert loaded_cfg["metadata"]["review_window"]["visible"] is True


@pytest.mark.asyncio
async def test_publish_respects_activation_gate_when_auto_activate_enabled():
    strategy_manager = MagicMock()
    strategy_manager.load_strategy_config = AsyncMock(
        side_effect=lambda cfg: SimpleNamespace(metadata=cfg.get("metadata", {}))
    )
    strategy_manager.save_strategy_experiment_card = MagicMock()
    strategy_manager.record_strategy_review = MagicMock()
    strategy_manager.save_strategy_parameter_sensitivity = MagicMock()
    strategy_manager.record_strategy_failure_case = MagicMock()
    strategy_manager.get_strategy_instances = AsyncMock(return_value=[])
    strategy_manager.create_strategy_instance = AsyncMock(return_value="inst-2")
    strategy_manager.initialize_strategy = AsyncMock(return_value=True)
    strategy_manager.start_strategy = AsyncMock(return_value=True)
    strategy_manager.get_strategy_activation_gate = MagicMock(
        return_value={"eligible": False, "reasons": ["missing_peer_review_5q"], "stage": "oos_validating"}
    )
    strategy_manager.set_strategy_governance_state = MagicMock()

    controller = SimpleNamespace(
        strategy_manager=strategy_manager,
        log_audit_event=None,
        memory_gateway=None,
        feature_store_lite=None,
    )
    pipeline = StrategyResearchPipeline(main_controller=controller)

    item = await pipeline._publish(
        dsl={
            "symbol": "ETH/USDT",
            "name": "gated activation",
            "timeframe": "1h",
            "entry": [{"type": "mean_reversion"}],
            "exit": [{"type": "atr"}],
            "parameters": {},
        },
        test_metrics={"pnl": 8.0, "sharpe": 1.15, "max_drawdown": 0.12, "trades": 10},
        train_metrics={"pnl": 18.0, "sharpe": 1.4, "max_drawdown": 0.07, "trades": 16},
        score=1.2,
        decision="production_small",
        research_cfg={
            "rollout": {
                "manual_approval_required": False,
                "auto_enable_published": True,
                "auto_activate_published": True,
                "require_activation_gate": True,
                "max_auto_activate_stage": "paper",
                "force_paper_stage": True,
            },
            "governance": {
                "production_auto_activate_allowed": True,
            },
        },
    )

    assert item is not None
    assert item["enabled"] is True
    assert item["manual_approval_required"] is False
    assert item["activated"] is False
    assert "missing_peer_review_5q" in item["activation_blockers"]
    strategy_manager.create_strategy_instance.assert_not_awaited()
