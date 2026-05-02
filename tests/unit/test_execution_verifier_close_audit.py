"""ExecutionVerifier.record_close_audit — SLTP / 旁路平仓审计落盘。"""
import json
from pathlib import Path

import pytest

from src.modules.core.execution_verifier import ExecutionVerifier, ExecutionConfig


@pytest.mark.asyncio
async def test_record_close_audit_appends_jsonl(tmp_path):
    log_dir = tmp_path / "exec_logs"
    ev = ExecutionVerifier(ExecutionConfig(log_dir=str(log_dir)))
    await ev.record_close_audit(
        symbol="BTC/USDT/SWAP",
        side="long",
        size=0.01,
        success=True,
        reason="unit_test",
        source="stop_loss_take_profit",
        details={"order_id": "ord_test_1", "gateway": True},
    )
    day_files = list(log_dir.glob("*.jsonl"))
    assert len(day_files) == 1
    line = day_files[0].read_text(encoding="utf-8").strip().splitlines()[-1]
    row = json.loads(line)
    assert row["command_type"] == "close_position"
    assert row["action"] == "close_long"
    assert row["status"] == "success"
    assert row["details"].get("order_id") == "ord_test_1"


@pytest.mark.asyncio
async def test_record_close_audit_failure_has_error_message(tmp_path):
    log_dir = tmp_path / "exec_logs2"
    ev = ExecutionVerifier(ExecutionConfig(log_dir=str(log_dir)))
    await ev.record_close_audit(
        symbol="DOGE/USDT/SWAP",
        side="short",
        size=3.0,
        success=False,
        reason="sr_partial",
        details={"gateway": True},
        error_message="51006 min size",
    )
    day_files = list(log_dir.glob("*.jsonl"))
    line = day_files[0].read_text(encoding="utf-8").strip()
    row = json.loads(line)
    assert row["status"] == "failed"
    assert "51006" in (row.get("error_message") or "")
