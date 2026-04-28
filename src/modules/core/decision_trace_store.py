from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class DecisionTraceStore:
    """
    Lightweight in-memory trace store for decision -> guard -> execution lifecycle.
    """

    def __init__(self, max_items: int = 300) -> None:
        self._max_items = max(50, int(max_items or 300))
        self._items: List[Dict[str, Any]] = []
        self._by_trace_id: Dict[str, Dict[str, Any]] = {}

    def _touch(self, trace_id: str) -> Dict[str, Any]:
        tid = str(trace_id or "").strip()
        if not tid:
            tid = f"trace-{len(self._items)+1}"
        cur = self._by_trace_id.get(tid)
        if cur is None:
            cur = {
                "trace_id": tid,
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
                "symbol": None,
                "side": None,
                "action": None,
                "source": "ai_core",
                "intent": {},
                "guard": {},
                "execution": {},
                "reconciliation": {},
            }
            self._items.append(cur)
            self._by_trace_id[tid] = cur
            if len(self._items) > self._max_items:
                old = self._items.pop(0)
                self._by_trace_id.pop(str(old.get("trace_id") or ""), None)
        cur["updated_at"] = _utc_now()
        return cur

    def record_intent(
        self,
        *,
        trace_id: str,
        symbol: str,
        side: str,
        action: str,
        source: str,
        confidence: Optional[float] = None,
        strategy_used: Optional[str] = None,
        reasoning: Optional[str] = None,
        quantity: Optional[float] = None,
        leverage: Optional[int] = None,
        extras: Optional[Dict[str, Any]] = None,
    ) -> None:
        cur = self._touch(trace_id)
        cur["symbol"] = symbol
        cur["side"] = side
        cur["action"] = action
        cur["source"] = source
        cur["intent"] = {
            "at": _utc_now(),
            "confidence": confidence,
            "strategy_used": strategy_used,
            "reasoning": str(reasoning or "")[:400],
            "quantity": quantity,
            "leverage": leverage,
            "extras": dict(extras or {}),
        }

    def record_guard_result(
        self,
        *,
        trace_id: str,
        status: str,
        reason: str,
        stage: str,
        extras: Optional[Dict[str, Any]] = None,
    ) -> None:
        cur = self._touch(trace_id)
        cur["guard"] = {
            "at": _utc_now(),
            "status": status,
            "reason": str(reason or "")[:300],
            "stage": str(stage or "")[:120],
            "extras": dict(extras or {}),
        }

    def record_execution_result(
        self,
        *,
        trace_id: str,
        status: str,
        detail: str,
        source: Optional[str] = None,
        op: Optional[str] = None,
        extras: Optional[Dict[str, Any]] = None,
    ) -> None:
        cur = self._touch(trace_id)
        cur["execution"] = {
            "at": _utc_now(),
            "status": status,
            "detail": str(detail or "")[:500],
            "source": source,
            "op": op,
            "extras": dict(extras or {}),
        }

    def record_reconciliation_result(
        self,
        *,
        trace_id: str,
        status: str,
        detail: str,
        extras: Optional[Dict[str, Any]] = None,
    ) -> None:
        cur = self._touch(trace_id)
        cur["reconciliation"] = {
            "at": _utc_now(),
            "status": status,
            "detail": str(detail or "")[:300],
            "extras": dict(extras or {}),
        }

    def get_recent(self, limit: int = 30) -> List[Dict[str, Any]]:
        lim = max(1, min(int(limit or 30), self._max_items))
        return list(self._items[-lim:])

    def get_by_trace_id(self, trace_id: str) -> Optional[Dict[str, Any]]:
        tid = str(trace_id or "").strip()
        if not tid:
            return None
        item = self._by_trace_id.get(tid)
        return dict(item) if isinstance(item, dict) else None

    def analyze_recent(self, limit: int = 50) -> Dict[str, Any]:
        rows = self.get_recent(limit=limit)
        summary = {
            "sample_size": len(rows),
            "guard_rejected": 0,
            "guard_passed": 0,
            "execution_success": 0,
            "execution_failed": 0,
            "reconciliation_blocked": 0,
        }
        guard_reasons: Dict[str, int] = {}
        execution_details: Dict[str, int] = {}
        reconciliation_details: Dict[str, int] = {}
        symbol_counts: Dict[str, int] = {}

        for row in rows:
            if not isinstance(row, dict):
                continue
            sym = str(row.get("symbol") or "")
            if sym:
                symbol_counts[sym] = int(symbol_counts.get(sym, 0)) + 1

            guard = row.get("guard") if isinstance(row.get("guard"), dict) else {}
            g_status = str(guard.get("status") or "")
            g_reason = str(guard.get("reason") or "")
            if g_status == "rejected":
                summary["guard_rejected"] += 1
                if g_reason:
                    guard_reasons[g_reason] = int(guard_reasons.get(g_reason, 0)) + 1
            elif g_status == "passed":
                summary["guard_passed"] += 1

            execution = row.get("execution") if isinstance(row.get("execution"), dict) else {}
            e_status = str(execution.get("status") or "")
            e_detail = str(execution.get("detail") or "")
            if e_status == "success":
                summary["execution_success"] += 1
            elif e_status == "failed":
                summary["execution_failed"] += 1
                if e_detail:
                    execution_details[e_detail] = int(execution_details.get(e_detail, 0)) + 1

            reconciliation = row.get("reconciliation") if isinstance(row.get("reconciliation"), dict) else {}
            r_status = str(reconciliation.get("status") or "")
            r_detail = str(reconciliation.get("detail") or "")
            if r_status == "blocked":
                summary["reconciliation_blocked"] += 1
                if r_detail:
                    reconciliation_details[r_detail] = int(reconciliation_details.get(r_detail, 0)) + 1

        def _top(d: Dict[str, int], n: int = 8) -> List[Dict[str, Any]]:
            return [{"key": k, "count": v} for k, v in sorted(d.items(), key=lambda x: x[1], reverse=True)[:n]]

        return {
            "summary": summary,
            "top_guard_reasons": _top(guard_reasons),
            "top_execution_failures": _top(execution_details),
            "top_reconciliation_blocks": _top(reconciliation_details),
            "top_symbols": _top(symbol_counts),
            "recent": rows,
        }
