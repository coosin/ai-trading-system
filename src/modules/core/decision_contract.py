"""
Decision contract helpers for execution path hardening.

This module standardizes decision payloads passed from AI core to
ExecutionVerifier/ExecutionGateway so fields are validated consistently.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Tuple


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def normalize_symbol(symbol: Any) -> str:
    s = str(symbol or "").strip().upper().replace("-", "/")
    if not s:
        return ""
    if "/USDT/SWAP" in s:
        return s
    if s.endswith("/SWAP"):
        return s
    if s.endswith("USDT") and "/" not in s:
        base = s.replace("USDT", "")
        if base:
            return f"{base}/USDT"
    return s


def normalize_side(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in {"long", "buy", "b"}:
        return "long"
    if s in {"short", "sell", "s"}:
        return "short"
    return ""


def normalize_action(raw: Any) -> str:
    a = str(raw or "").strip().lower()
    if a in {"buy", "open", "open_long"}:
        return "open"
    if a in {"sell", "close", "close_long", "close_short"}:
        return "close"
    if a in {"hold"}:
        return "hold"
    return a


def normalize_strategy_id(raw: Any, default: str = "ai_core_default") -> str:
    s = str(raw or "").strip()
    return s or default


def normalize_strategy_field(
    payload: Optional[Dict[str, Any]] = None,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    default: str = "unknown",
) -> str:
    p = payload if isinstance(payload, dict) else {}
    m = metadata if isinstance(metadata, dict) else {}
    sid = (
        p.get("strategy_id")
        or p.get("strategy_used")
        or p.get("strategy")
        or m.get("strategy_id")
        or m.get("strategy_used")
        or m.get("strategy")
    )
    return normalize_strategy_id(sid, default=default)


@dataclass
class DecisionEnvelope:
    symbol: str
    action: str
    side: str
    quantity: float
    leverage: int
    confidence: float
    strategy_id: str
    reasoning: str = ""
    trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def validate_envelope(payload: Dict[str, Any]) -> Tuple[bool, str]:
    symbol = normalize_symbol(payload.get("symbol"))
    action = normalize_action(payload.get("action"))
    side = normalize_side(payload.get("side"))
    qty = _to_float(payload.get("quantity"), 0.0)
    lev = _to_int(payload.get("leverage"), 0)
    conf = _to_float(payload.get("confidence"), 0.0)
    strategy_id = normalize_strategy_id(payload.get("strategy_id"), default="")

    if not symbol:
        return False, "decision_contract_invalid_symbol"
    if action not in {"open", "close", "hold"}:
        return False, "decision_contract_invalid_action"
    if action in {"open", "close"} and side not in {"long", "short"}:
        return False, "decision_contract_invalid_side"
    if action == "open" and qty <= 0:
        return False, "decision_contract_invalid_quantity"
    if action == "open" and lev <= 0:
        return False, "decision_contract_invalid_leverage"
    if conf < 0 or conf > 1.0:
        return False, "decision_contract_invalid_confidence"
    if not strategy_id:
        return False, "decision_contract_missing_strategy_id"
    return True, "ok"


def build_envelope_from_decision(decision: Any, trace_id: Optional[str] = None) -> DecisionEnvelope:
    action_raw = getattr(decision, "action", "")
    action = normalize_action(action_raw)
    side = normalize_side(getattr(decision, "side", ""))
    strategy_id = normalize_strategy_id(
        getattr(decision, "strategy_used", None),
        default="ai_core_default",
    )
    return DecisionEnvelope(
        symbol=normalize_symbol(getattr(decision, "symbol", "")),
        action=action,
        side=side,
        quantity=_to_float(getattr(decision, "quantity", 0.0), 0.0),
        leverage=_to_int(getattr(decision, "leverage", 0), 0),
        confidence=_to_float(getattr(decision, "confidence", 0.0), 0.0),
        strategy_id=strategy_id,
        reasoning=str(getattr(decision, "reasoning", "") or ""),
        trace_id=str(trace_id or ""),
    )
