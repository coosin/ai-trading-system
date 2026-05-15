from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.modules.api.module_control_api import _summarize_trace_workflow_focus
from src.modules.core.heartbeat_monitor import HeartbeatMonitor


def test_summarize_trace_workflow_focus_picks_top_stage_and_status():
    traces = {
        "top_workflow_stages": [
            {"key": "reconciliation", "count": 4},
            {"key": "execution:open", "count": 2},
        ],
        "top_workflow_statuses": [
            {"key": "reconcile_blocked", "count": 3},
            {"key": "completed", "count": 2},
        ],
    }

    summary = _summarize_trace_workflow_focus(traces)

    assert summary["top_stage"]["key"] == "reconciliation"
    assert summary["top_status"]["key"] == "reconcile_blocked"


@pytest.mark.asyncio
async def test_heartbeat_reconciliation_alert_includes_workflow_focus():
    sent = []

    async def _notify(title, message, priority):
        sent.append({"title": title, "message": message, "priority": priority})

    hb = HeartbeatMonitor(
        trading_engine=None,
        skill_manager=None,
        memory_manager=None,
        notification_handler=_notify,
        main_controller=SimpleNamespace(),
    )
    hb._build_trading_diagnosis = AsyncMock(
        return_value={
            "execution_gateway": {
                "policy_metrics": {"open_fail": 0, "close_fail": 0},
                "recent_events": [],
                "reconciliation": {
                    "healthy": False,
                    "severity": "warning",
                    "summary": {"drift_total": 2, "stale_open_orders": 1},
                    "safe_recovery": {},
                },
                "reconciliation_protection": {"global_lock_active": True, "symbol_locks": {"BTC/USDT": {}}},
            },
            "sltp": {"sr_partial_tp_failed": 0},
            "decision_traces_summary": {
                "top_workflow_stages": [{"key": "reconciliation", "count": 5}],
                "top_workflow_statuses": [{"key": "reconcile_blocked", "count": 4}],
            },
        }
    )

    await hb._trading_diagnosis_report_and_alerts({})

    assert any(item["title"] == "⚠️ 交易状态对账异常" for item in sent)
    assert any(item["title"] == "🛡️ 对账保护已生效" for item in sent)
    assert any("workflow_focus stage=reconciliation status=reconcile_blocked" in item["message"] for item in sent)
