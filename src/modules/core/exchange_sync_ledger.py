"""
交易所对账账本（与 app 运行日志分离）

- 仅追加 JSON Lines，便于 grep / jq / 离线对账
- 记录来自交易所 REST 回填的成交要点，不等同于「全量系统 debug 日志」
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import aiofiles

_sync_log = logging.getLogger("openclaw.exchange_sync")
_append_lock = asyncio.Lock()
_recent_append_fingerprints: Dict[str, float] = {}
_append_dedupe_ttl_sec = 6 * 3600.0
_persisted_dedupe_keys: set[str] = set()
_persisted_dedupe_loaded_for: str = ""
_persisted_dedupe_max_lines = 4000


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


def _normalize_dedupe_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 10)
    if isinstance(value, dict):
        return {
            str(k): _normalize_dedupe_value(v)
            for k, v in sorted(value.items(), key=lambda item: str(item[0]))
            if str(k) != "ts_utc"
        }
    if isinstance(value, (list, tuple, set)):
        return [_normalize_dedupe_value(v) for v in list(value)]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    return str(value)


def _event_dedupe_key(event: Dict[str, Any]) -> str:
    explicit = str(event.get("dedupe_key") or "").strip()
    if explicit:
        return explicit
    basis = {
        key: _normalize_dedupe_value(event.get(key))
        for key in (
            "event",
            "symbol",
            "side",
            "order_id",
            "price",
            "quantity",
            "pnl",
            "fee",
            "exchange_fill_count",
            "exchange_pnl",
            "exchange_fee",
            "exchange_price",
            "notional_usdt_est",
            "fee_rate_est",
            "pnl_estimated",
            "fills_enriched",
            "source",
        )
        if event.get(key) is not None
    }
    if not basis:
        basis = _normalize_dedupe_value(event)
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _should_skip_append(dedupe_key: str) -> bool:
    now = time.monotonic()
    last = _recent_append_fingerprints.get(dedupe_key)
    if last is not None and (now - last) < _append_dedupe_ttl_sec:
        return True
    _recent_append_fingerprints[dedupe_key] = now
    for key, ts in list(_recent_append_fingerprints.items()):
        if (now - ts) > _append_dedupe_ttl_sec:
            _recent_append_fingerprints.pop(key, None)
    return False


def _load_persisted_dedupe_keys(path: Path) -> None:
    """从账本尾部加载已写入事件的指纹，避免重启后重复落盘。"""
    global _persisted_dedupe_loaded_for
    path_key = str(path.resolve())
    if _persisted_dedupe_loaded_for == path_key:
        return
    _persisted_dedupe_keys.clear()
    try:
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in lines[-_persisted_dedupe_max_lines:]:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                _persisted_dedupe_keys.add(_event_dedupe_key(row))
    except Exception:
        _persisted_dedupe_keys.clear()
    _persisted_dedupe_loaded_for = path_key


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
        dedupe_key = _event_dedupe_key(event)
        async with _append_lock:
            _load_persisted_dedupe_keys(path)
            if dedupe_key in _persisted_dedupe_keys:
                _sync_log.debug(
                    "truth_ledger durable-deduped event=%s symbol=%s order_id=%s",
                    event.get("event"),
                    event.get("symbol"),
                    event.get("order_id"),
                )
                return
            if _should_skip_append(dedupe_key):
                _sync_log.debug(
                    "truth_ledger deduped event=%s symbol=%s order_id=%s",
                    event.get("event"),
                    event.get("symbol"),
                    event.get("order_id"),
                )
                return
            async with aiofiles.open(path, "a", encoding="utf-8") as f:
                await f.write(line)
            _persisted_dedupe_keys.add(dedupe_key)
        _sync_log.info(
            "truth_ledger event=%s symbol=%s order_id=%s pnl_estimated=%s",
            event.get("event"),
            event.get("symbol"),
            event.get("order_id"),
            event.get("pnl_estimated"),
        )
    except Exception as e:
        _sync_log.debug("append_exchange_truth skipped: %s", e)
