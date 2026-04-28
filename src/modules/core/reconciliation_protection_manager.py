from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ReconciliationProtectionManager:
    """
    Turn reconciliation anomalies into deterministic open-trade protections.

    Protection philosophy:
    - symbol drift -> block opening the affected symbol for a cooldown window
    - severe/global drift -> optionally block all new opens briefly
    """

    def __init__(self) -> None:
        self._symbol_lock_until: Dict[str, float] = {}
        self._symbol_reasons: Dict[str, str] = {}
        self._global_lock_until: float = 0.0
        self._global_reason: str = ""
        self._last_recovery_actions: List[Dict[str, Any]] = []
        self._symbol_lock_sec: float = 180.0
        self._global_lock_sec: float = 120.0
        self._metrics: Dict[str, int] = {
            "symbol_protection_hits": 0,
            "global_protection_hits": 0,
            "symbol_locks_created": 0,
            "global_locks_created": 0,
            "safe_recovery_actions": 0,
        }

    def _cleanup(self) -> None:
        now = time.time()
        for sym, until in list(self._symbol_lock_until.items()):
            if float(until or 0.0) <= now:
                self._symbol_lock_until.pop(sym, None)
                self._symbol_reasons.pop(sym, None)
        if self._global_lock_until <= now:
            self._global_lock_until = 0.0
            self._global_reason = ""

    def ingest_reconciliation(self, snapshot: Optional[Dict[str, Any]]) -> None:
        self._cleanup()
        if not isinstance(snapshot, dict):
            return

        actions: List[Dict[str, Any]] = []
        drifts = snapshot.get("position_drifts") if isinstance(snapshot.get("position_drifts"), dict) else {}
        summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
        severity = str(snapshot.get("severity") or "ok").lower()
        now = time.time()
        refresh_actions = snapshot.get("refresh_actions") if isinstance(snapshot.get("refresh_actions"), dict) else {}

        symbol_reasons: Dict[str, str] = {}
        for key, reason in (
            ("exchange_only_positions", "exchange_only_position_detected"),
            ("local_only_positions", "local_only_position_detected"),
            ("side_mismatch_positions", "side_mismatch_detected"),
            ("size_mismatch_positions", "size_mismatch_detected"),
        ):
            rows = drifts.get(key) if isinstance(drifts.get(key), list) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sym = str(row.get("symbol") or "").strip().upper()
                if sym and sym not in symbol_reasons:
                    symbol_reasons[sym] = reason

        stale = snapshot.get("order_signals") if isinstance(snapshot.get("order_signals"), dict) else {}
        for row in stale.get("stale_open_orders", []) if isinstance(stale.get("stale_open_orders"), list) else []:
            if not isinstance(row, dict):
                continue
            sym = str(row.get("symbol") or "").strip().upper()
            if sym and sym not in symbol_reasons:
                symbol_reasons[sym] = "stale_open_order_detected"

        for sym, reason in symbol_reasons.items():
            prev = float(self._symbol_lock_until.get(sym, 0.0) or 0.0)
            until = max(prev, now + float(self._symbol_lock_sec))
            self._symbol_lock_until[sym] = until
            self._symbol_reasons[sym] = reason
            if until != prev:
                self._metrics["symbol_locks_created"] = int(self._metrics.get("symbol_locks_created", 0)) + 1
                actions.append(
                    {
                        "type": "symbol_protection_lock",
                        "symbol": sym,
                        "left_sec": int(max(0.0, until - now)),
                        "reason": reason,
                        "status": "applied",
                    }
                )

        drift_total = int(summary.get("drift_total", 0) or 0)
        severe_global = severity == "critical" and drift_total >= 2
        if severe_global:
            prev = float(self._global_lock_until or 0.0)
            until = max(prev, now + float(self._global_lock_sec))
            self._global_lock_until = until
            self._global_reason = f"reconciliation_global_drift:{drift_total}"
            if until != prev:
                self._metrics["global_locks_created"] = int(self._metrics.get("global_locks_created", 0)) + 1
                actions.append(
                    {
                        "type": "global_protection_lock",
                        "left_sec": int(max(0.0, until - now)),
                        "reason": self._global_reason,
                        "status": "applied",
                    }
                )

        if refresh_actions:
            if bool(refresh_actions.get("ai_trading_engine_positions_refreshed")):
                actions.append(
                    {
                        "type": "refresh_ai_trading_engine_positions",
                        "status": "applied",
                    }
                )
            if bool(refresh_actions.get("ai_core_positions_refreshed")):
                actions.append(
                    {
                        "type": "refresh_ai_core_positions",
                        "status": "applied",
                    }
                )

        manual_required: List[Dict[str, Any]] = []
        for row in drifts.get("side_mismatch_positions", []) if isinstance(drifts.get("side_mismatch_positions"), list) else []:
            if not isinstance(row, dict):
                continue
            manual_required.append(
                {
                    "type": "manual_review_required",
                    "symbol": row.get("symbol"),
                    "reason": "side_mismatch_detected",
                    "status": "manual_required",
                }
            )
        for row in (snapshot.get("order_signals") or {}).get("open_orders_without_position", []) if isinstance((snapshot.get("order_signals") or {}).get("open_orders_without_position"), list) else []:
            if not isinstance(row, dict):
                continue
            manual_required.append(
                {
                    "type": "manual_review_required",
                    "symbol": row.get("symbol"),
                    "reason": "open_order_without_position",
                    "status": "manual_required",
                }
            )
        actions.extend(manual_required[:12])
        self._last_recovery_actions = actions[:20]
        self._metrics["safe_recovery_actions"] = len([a for a in actions if str(a.get("status")) == "applied"])

    def allow_open(self, symbol: str) -> Optional[str]:
        self._cleanup()
        now = time.time()
        if self._global_lock_until > now:
            self._metrics["global_protection_hits"] = int(self._metrics.get("global_protection_hits", 0)) + 1
            left = int(max(1.0, self._global_lock_until - now))
            return f"reconciliation_global_protection:{left}s:{self._global_reason or 'global_drift'}"

        key = str(symbol or "").strip().upper()
        until = float(self._symbol_lock_until.get(key, 0.0) or 0.0)
        if until > now:
            self._metrics["symbol_protection_hits"] = int(self._metrics.get("symbol_protection_hits", 0)) + 1
            left = int(max(1.0, until - now))
            return f"reconciliation_symbol_protection:{left}s:{self._symbol_reasons.get(key, 'symbol_drift')}"
        return None

    def get_snapshot(self) -> Dict[str, Any]:
        self._cleanup()
        now = time.time()
        active_symbols: Dict[str, Dict[str, Any]] = {}
        for sym, until in self._symbol_lock_until.items():
            left = int(max(0.0, float(until) - now))
            if left <= 0:
                continue
            active_symbols[str(sym)] = {
                "left_sec": left,
                "reason": self._symbol_reasons.get(sym, "symbol_drift"),
            }
        return {
            "timestamp": _utc_now(),
            "global_lock_active": bool(self._global_lock_until > now),
            "global_lock_left_sec": int(max(0.0, self._global_lock_until - now)),
            "global_reason": self._global_reason or None,
            "symbol_locks": active_symbols,
            "metrics": dict(self._metrics),
            "safe_recovery_actions": list(self._last_recovery_actions),
        }
