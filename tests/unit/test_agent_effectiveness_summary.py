from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.modules.api.module_control_api import _build_agent_effectiveness_summary


class _Store:
    def __init__(self, rows):
        self._rows = list(rows)

    def get_recent(self, limit: int = 120):
        return self._rows[:limit]


class _TradeHistory:
    def __init__(self, rows):
        self._rows = list(rows)

    async def get_trade_history(self, limit: int = 500):
        return self._rows[:limit]


def _agent_outputs() -> dict:
    payload = {
        "confidence": 0.5,
        "next_action": "observe",
        "structured_verdict": {"risk_verdict": "ok"},
    }
    return {
        "market_structure_agent": dict(payload),
        "research_agent": dict(payload),
        "risk_governor_agent": dict(payload),
        "execution_coach_agent": dict(payload),
    }


@pytest.mark.asyncio
async def test_agent_effectiveness_uses_no_execution_diagnosis_when_store_sample_has_no_execs():
    mc = SimpleNamespace(
        decision_trace_store=_Store(
            [
                {
                    "trace_id": "trace-store-1",
                    "symbol": "BTC/USDT",
                    "workflow": {"status": "blocked"},
                    "guard": {"status": "rejected"},
                    "execution": {},
                    "agent_outputs": _agent_outputs(),
                }
            ]
        ),
        trade_history_service=_TradeHistory(
            [
                {
                    "symbol": "BTC/USDT",
                    "pnl": 10.0,
                    "metadata": {"trace_id": "trace-realized-1", "strategy_id": "s1"},
                }
            ]
        ),
    )

    data = await _build_agent_effectiveness_summary(mc, trace_limit=20, trade_limit=20)

    assert data["summary"]["executed_trace_count"] == 0
    assert data["attribution_diagnostics"]["diagnosis"] == "store_sample_contains_no_executions"
    assert any(
        issue["issue"] == "当前 trace 样本没有成功执行记录，无法评估真实收益闭环"
        for issue in data["top_issues"]
    )
    assert not any(
        issue["issue"] == "四智能体与真实已实现收益仍缺少可靠闭环归因"
        for issue in data["top_issues"]
    )


@pytest.mark.asyncio
async def test_agent_effectiveness_keeps_mismatch_diagnosis_when_execs_exist_without_overlap():
    mc = SimpleNamespace(
        decision_trace_store=_Store(
            [
                {
                    "trace_id": "trace-store-1",
                    "symbol": "BTC/USDT",
                    "workflow": {"status": "completed"},
                    "guard": {"status": "passed"},
                    "execution": {"status": "success"},
                    "agent_outputs": _agent_outputs(),
                }
            ]
        ),
        trade_history_service=_TradeHistory(
            [
                {
                    "symbol": "BTC/USDT",
                    "pnl": 10.0,
                    "metadata": {"trace_id": "trace-realized-1", "strategy_id": "s1"},
                }
            ]
        ),
    )

    data = await _build_agent_effectiveness_summary(mc, trace_limit=20, trade_limit=20)

    assert data["summary"]["executed_trace_count"] == 1
    assert data["attribution_diagnostics"]["diagnosis"] == "realized_trace_namespace_mismatch"
    assert any(
        issue["issue"] == "四智能体与真实已实现收益仍缺少可靠闭环归因"
        for issue in data["top_issues"]
    )
