"""
交易所对账账本（与 app 运行日志分离）

- 仅追加 JSON Lines，便于 grep / jq / 离线对账
- 记录来自交易所 REST 回填的成交要点，不等同于「全量系统 debug 日志」
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import aiofiles

_sync_log = logging.getLogger("openclaw.exchange_sync")
_append_lock = asyncio.Lock()


def _resolve_ledger_path() -> Path:
    for d in (Path("logs/exchange_sync"), Path("/tmp/openclaw-trading/logs/exchange_sync")):
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".ledger_write_probe"
            probe.write_bytes(b"")
            probe.unlink()
            return d / "exchange_truth.jsonl"
        except OSError:
            continue
    return Path("/tmp/exchange_truth.jsonl")


async def append_exchange_truth(event: Dict[str, Any]) -> None:
    """追加一条「交易所侧事实」摘要（失败静默，不影响交易主路径）。"""
    try:
        row: Dict[str, Any] = {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "channel": "exchange_truth",
            **event,
        }
        path = _resolve_ledger_path()
        line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
        async with _append_lock:
            async with aiofiles.open(path, "a", encoding="utf-8") as f:
                await f.write(line)
        _sync_log.info(
            "truth_ledger event=%s symbol=%s order_id=%s pnl_estimated=%s",
            event.get("event"),
            event.get("symbol"),
            event.get("order_id"),
            event.get("pnl_estimated"),
        )
    except Exception as e:
        _sync_log.debug("append_exchange_truth skipped: %s", e)
