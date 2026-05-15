"""
Memory schema helpers for the unified MemoryGateway pipeline.

Goal:
- Keep every entry short, atomic, and queryable.
- Make trading memories easy to summarize (daily/weekly) and recall.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set


# Canonical categories (string API used by MemoryGateway.store/add_memory)
C_CONVERSATION = "conversation"
C_TRADE_RECORD = "trade_record"
C_RISK_EVENT = "risk_event"
C_DECISION = "decision"
C_MARKET_OBSERVATION = "market_observation"
C_TRADING_RULE = "trading_rule"
C_USER_PREFERENCE = "user_preference"
C_SYSTEM_STATE = "system_state"
C_DAILY_SUMMARY = "daily_summary"
C_LESSON_LEARNED = "lesson_learned"
C_MARKET_REGIME_CASE = "market_regime_case"
C_EXECUTION_INCIDENT = "execution_incident"
C_STRATEGY_DRIFT_CASE = "strategy_drift_case"
C_AGENT_MISJUDGMENT_CASE = "agent_misjudgment_case"
C_TUNING_ATTEMPT = "tuning_attempt"
C_TUNING_RESULT = "tuning_result"
C_APPROVED_RULE_CHANGE = "approved_rule_change"
C_REJECTED_RULE_CHANGE = "rejected_rule_change"
C_WEEKLY_LESSON = "weekly_lesson"
C_KNOWLEDGE_DOCUMENT = "knowledge_document"


def now_iso() -> str:
    return datetime.now().isoformat()


def _clean(s: Any) -> str:
    return str(s or "").strip()


def symbol_tag(symbol: Optional[str]) -> Optional[str]:
    s = _clean(symbol)
    if not s:
        return None
    # Normalize BTC/USDT -> BTC-USDT to avoid "/" token splitting issues
    return f"symbol:{s.replace('/', '-').upper()}"


def kind_tag(kind: Optional[str]) -> Optional[str]:
    k = _clean(kind).lower()
    return f"kind:{k}" if k else None


def tags(*parts: Optional[str], extra: Optional[Iterable[str]] = None) -> List[str]:
    out: List[str] = []
    for p in parts:
        if p:
            out.append(str(p))
    if extra:
        for t in extra:
            tt = _clean(t)
            if tt:
                out.append(tt)
    # stable de-dup
    seen: Set[str] = set()
    dedup: List[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            dedup.append(t)
    return dedup


def base_metadata(
    *,
    source_module: str,
    scope: Optional[str] = None,
    kind: Optional[str] = None,
    symbol: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    md: Dict[str, Any] = {"created_at": now_iso(), "source_module": source_module}
    if scope:
        md["scope"] = str(scope)
    if kind:
        md["kind"] = str(kind)
    if symbol:
        md["symbol"] = str(symbol)
    if extra:
        md.update(extra)
    return md


@dataclass(frozen=True)
class SummaryKey:
    """Idempotency key for periodic summaries."""

    kind: str  # daily_summary | weekly_summary
    date: str  # YYYY-MM-DD (daily) or YYYY-WW (weekly)

    def to_metadata(self) -> Dict[str, Any]:
        return {"kind": self.kind, "date": self.date}


def trade_idempotency_fingerprint(category: str, metadata: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Stable key for deduplicating trade / risk / sltp writes within a time window.
    Callers may set metadata['idempotency_key'] explicitly (highest priority).
    """
    md = dict(metadata or {})
    ik = _clean(md.get("idempotency_key"))
    if ik:
        return ik

    oid = md.get("order_id") or md.get("orderId")
    if oid is not None and str(oid).strip():
        return f"order:{str(oid).strip()}"

    coid = md.get("client_oid") or md.get("clientOrderId") or md.get("clOrdId")
    if coid is not None and str(coid).strip():
        return f"client_order:{str(coid).strip()}"

    pos = md.get("position_key")
    kind = str(md.get("kind") or "").strip().lower()
    if pos and str(pos).strip() and kind:
        return f"pos:{kind}:{str(pos).strip()}"

    sk = md.get("sltp_track_key") or md.get("sltp_event_key")
    if sk and str(sk).strip():
        return f"sltp:{str(sk).strip()}"

    sym = _clean(md.get("symbol")).replace("/", "-").upper()
    trig = md.get("trigger_reason") or md.get("triggered_at") or md.get("trigger_ts")
    if sym and kind.startswith("sltp") and trig:
        return f"sltp:{sym}:{kind}:{trig}"

    if kind in {"trade_open", "trade_close", "trade_execution"} and sym:
        px = md.get("price") or md.get("close_price") or md.get("open_price")
        qty = md.get("quantity")
        ts = _clean(md.get("created_at"))[:19]
        if px is not None and qty is not None:
            return f"trade:{kind}:{sym}:{px}:{qty}:{ts}"

    return None


def attach_idempotency(metadata: Dict[str, Any], key: Optional[str]) -> Dict[str, Any]:
    if key and "idempotency_key" not in metadata:
        metadata = dict(metadata)
        metadata["idempotency_key"] = key
    return metadata
