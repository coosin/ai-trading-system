from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.modules.core.strategy_manager import StrategyLifecycleStage, StrategyManager


def test_approve_strategy_enables_pending_strategy_after_gate_passes():
    sm = StrategyManager(SimpleNamespace())
    sm.strategy_configs["pending"] = SimpleNamespace(
        strategy_id="pending",
        enabled=False,
        metadata={
            "approval": {"required": True, "state": "manual_approval_required", "approved": False},
            "research": {
                "hypothesis": "trend edge",
                "experiment_card": {"cost_model": {"fees_bps": 8}},
                "review": {
                    "answers": {
                        "what_edge": "trend",
                        "why_not_immediately_gone": "frictions",
                        "net_after_cost": "positive",
                        "failure_shape": "chop",
                        "kill_signal": "oos fail",
                    }
                },
            },
            "governance": {"stage": "proposal"},
        },
        stage=StrategyLifecycleStage.PROPOSAL,
        oos_status="passed",
        live_drift_status="healthy",
        updated_at=None,
    )

    result = sm.approve_strategy("pending", approved_by="qa", reason="manual review ok")

    assert result["approved"] is True
    assert sm.strategy_configs["pending"].enabled is True
    assert sm.strategy_configs["pending"].metadata["approval"]["state"] == "approved"
    assert sm.strategy_configs["pending"].metadata["approval"]["approved_by"] == "qa"
    assert sm.strategy_configs["pending"].stage == StrategyLifecycleStage.OOS_VALIDATING


def test_approve_strategy_rejects_when_activation_gate_fails():
    sm = StrategyManager(SimpleNamespace())
    sm.strategy_configs["draft"] = SimpleNamespace(
        strategy_id="draft",
        enabled=False,
        metadata={"approval": {"required": True, "state": "manual_approval_required", "approved": False}},
        stage=StrategyLifecycleStage.PROPOSAL,
        oos_status="unknown",
        live_drift_status="unknown",
        updated_at=None,
    )

    result = sm.approve_strategy("draft", approved_by="qa")

    assert result["approved"] is False
    assert result["reason"] == "activation_gate_denied"
    assert sm.strategy_configs["draft"].enabled is False


@pytest.mark.asyncio
async def test_approve_strategy_for_execution_keeps_default_manual_separation():
    sm = StrategyManager(SimpleNamespace())
    sm.strategy_configs["pending"] = SimpleNamespace(
        strategy_id="pending",
        enabled=False,
        metadata={
            "approval": {"required": True, "state": "manual_approval_required", "approved": False},
            "research": {
                "hypothesis": "trend edge",
                "experiment_card": {"cost_model": {"fees_bps": 8}},
                "review": {
                    "answers": {
                        "what_edge": "trend",
                        "why_not_immediately_gone": "frictions",
                        "net_after_cost": "positive",
                        "failure_shape": "chop",
                        "kill_signal": "oos fail",
                    }
                },
                "rollout_policy": {
                    "auto_deploy_after_approval": False,
                    "auto_activate_after_approval": False,
                    "max_post_approval_auto_stage": "paper",
                    "require_activation_gate": True,
                },
            },
            "deployment": {"stage": "paper"},
            "governance": {"stage": "proposal"},
        },
        stage=StrategyLifecycleStage.PROPOSAL,
        oos_status="passed",
        live_drift_status="healthy",
        updated_at=None,
    )
    sm.create_strategy_instance = AsyncMock()

    result = await sm.approve_strategy_for_execution("pending", approved_by="qa")

    assert result["approved"] is True
    assert result["deployment"]["instance_id"] is None
    assert "auto_deploy_disabled" in result["deployment"]["blockers"]
    sm.create_strategy_instance.assert_not_awaited()


@pytest.mark.asyncio
async def test_approve_strategy_for_execution_can_auto_start_paper_instance():
    sm = StrategyManager(SimpleNamespace())
    sm.strategy_configs["pending"] = SimpleNamespace(
        strategy_id="pending",
        enabled=False,
        metadata={
            "approval": {"required": True, "state": "manual_approval_required", "approved": False},
            "research": {
                "hypothesis": "trend edge",
                "experiment_card": {"cost_model": {"fees_bps": 8}},
                "review": {
                    "answers": {
                        "what_edge": "trend",
                        "why_not_immediately_gone": "frictions",
                        "net_after_cost": "positive",
                        "failure_shape": "chop",
                        "kill_signal": "oos fail",
                    }
                },
                "rollout_policy": {
                    "auto_deploy_after_approval": True,
                    "auto_activate_after_approval": True,
                    "max_post_approval_auto_stage": "paper",
                    "require_activation_gate": True,
                },
            },
            "deployment": {"stage": "paper"},
            "governance": {"stage": "proposal"},
        },
        stage=StrategyLifecycleStage.PROPOSAL,
        oos_status="passed",
        live_drift_status="healthy",
        updated_at=None,
    )
    sm.get_strategy_instances = AsyncMock(side_effect=[[], []])
    sm.create_strategy_instance = AsyncMock(return_value="inst-1")
    sm.initialize_strategy = AsyncMock(return_value=True)
    sm.start_strategy = AsyncMock(return_value=True)

    result = await sm.approve_strategy_for_execution("pending", approved_by="qa")

    assert result["approved"] is True
    assert result["deployment"]["instance_id"] == "inst-1"
    assert result["deployment"]["initialized"] is True
    assert result["deployment"]["activated"] is True
    sm.create_strategy_instance.assert_awaited_once_with("pending")
    sm.initialize_strategy.assert_awaited_once_with("inst-1")
    sm.start_strategy.assert_awaited_once_with("inst-1")
