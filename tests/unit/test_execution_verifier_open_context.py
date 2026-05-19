"""ExecutionVerifier 开仓时应向 ExecutionGateway 透传决策上下文。"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.core.execution_verifier import (
    CommandType,
    ExecutionConfig,
    ExecutionResult,
    ExecutionStatus,
    ExecutionVerifier,
)


@pytest.mark.asyncio
async def test_execute_open_position_propagates_confidence_and_semantic_context(tmp_path):
    ev = ExecutionVerifier(ExecutionConfig(log_dir=str(tmp_path / "exec_logs")))
    ev.set_exchange(MagicMock())

    gw = MagicMock()
    gw.open_swap = AsyncMock(return_value={"success": True, "orderId": "ord-1", "average": 100.5})
    mc = MagicMock()
    mc.execution_gateway = gw
    ev.set_main_controller(mc)

    result = ExecutionResult(
        execution_id="exec-1",
        command_type=CommandType.OPEN_POSITION,
        action="open_long",
        status=ExecutionStatus.PENDING,
    )
    params = {
        "symbol": "BTC/USDT",
        "side": "long",
        "quantity": 1.0,
        "leverage": 20,
        "write_source": "ai_core",
        "trace_id": "trace-1",
        "strategy_id": "default_trend_following_ma",
        "decision_envelope": {
            "symbol": "BTC/USDT",
            "action": "open",
            "side": "long",
            "quantity": 1.0,
            "leverage": 20,
            "confidence": 0.83,
            "strategy_id": "default_trend_following_ma",
        },
        "semantic_context": {
            "risk_verdict": "allow",
            "execution_recommendation": "normal",
        },
    }

    out = await ev._execute_open_position(result, "BTC/USDT", params)

    assert out.status == ExecutionStatus.SUCCESS
    gw.open_swap.assert_awaited_once()
    ctx = gw.open_swap.call_args.kwargs["context"]
    assert ctx["confidence"] == pytest.approx(0.83)
    assert ctx["decision_confidence"] == pytest.approx(0.83)
    assert ctx["decision_envelope"]["confidence"] == pytest.approx(0.83)
    assert ctx["semantic_context"]["risk_verdict"] == "allow"
