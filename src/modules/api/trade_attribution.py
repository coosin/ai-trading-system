from __future__ import annotations

from typing import Any, Callable, Dict, Optional


PLACEHOLDER_STRATEGY_NAMES = {
    "",
    "?",
    "-",
    "na",
    "n/a",
    "none",
    "null",
    "unknown",
    "unassigned",
}


DecisionTraceLookup = Optional[Callable[[str], Optional[Dict[str, Any]]]]


def is_placeholder_strategy_name(name: Any) -> bool:
    return str(name or "").strip().lower() in PLACEHOLDER_STRATEGY_NAMES


def extract_trade_trace_id(row: Dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return ""
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    gateway = md.get("gateway") if isinstance(md.get("gateway"), dict) else {}
    context = gateway.get("context") if isinstance(gateway.get("context"), dict) else {}
    return str(
        md.get("trace_id")
        or md.get("decision_trace_id")
        or md.get("root_trace_id")
        or row.get("trace_id")
        or context.get("decision_trace_id")
        or context.get("root_trace_id")
        or context.get("trace_id")
        or context.get("TraceId")
        or context.get("traceId")
        or ""
    ).strip()


def raw_trade_strategy_name(row: Dict[str, Any]) -> str:
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    gateway = md.get("gateway") if isinstance(md.get("gateway"), dict) else {}
    context = gateway.get("context") if isinstance(gateway.get("context"), dict) else {}
    return str(
        md.get("strategy_id")
        or md.get("strategy_used")
        or row.get("strategy")
        or row.get("strategy_used")
        or context.get("strategy_id")
        or context.get("strategy_used")
        or ""
    ).strip()


def trade_source_name(row: Dict[str, Any], default: str = "") -> str:
    if not isinstance(row, dict):
        return str(default or "")
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    gateway = md.get("gateway") if isinstance(md.get("gateway"), dict) else {}
    return str(
        gateway.get("source")
        or md.get("source")
        or row.get("source")
        or default
        or ""
    ).strip()


def infer_strategy_name_from_trace_item(trace_item: Optional[Dict[str, Any]]) -> str:
    item = trace_item if isinstance(trace_item, dict) else {}
    intent = item.get("intent") if isinstance(item.get("intent"), dict) else {}
    extras = intent.get("extras") if isinstance(intent.get("extras"), dict) else {}
    market = item.get("market_context") if isinstance(item.get("market_context"), dict) else {}
    agents = item.get("agent_outputs") if isinstance(item.get("agent_outputs"), dict) else {}
    research = agents.get("research_agent") if isinstance(agents.get("research_agent"), dict) else {}
    research_structured = (
        research.get("structured_verdict") if isinstance(research.get("structured_verdict"), dict) else {}
    )
    governance = (
        research_structured.get("governance") if isinstance(research_structured.get("governance"), dict) else {}
    )
    candidates = [
        intent.get("strategy_used"),
        extras.get("strategy_id"),
        governance.get("strategy_id"),
        research.get("input_context_ref"),
    ]
    for name in candidates:
        text = str(name or "").strip()
        if text and not is_placeholder_strategy_name(text):
            return text

    for name in list(market.get("knowledge_refs") or []):
        text = str(name or "").strip()
        if text and not is_placeholder_strategy_name(text):
            return text

    source = str(item.get("source") or "").strip().lower()
    reasoning = str(intent.get("reasoning") or "").strip().lower()
    if "llm_unavailable_fallback" in reasoning:
        return "s1_llm_unavailable_fallback"
    if "ai_autonomy_override" in reasoning:
        return "s1_ai_autonomy_override"
    if source == "proactive_scanner":
        return "scanner_opportunity"
    if any(
        extras.get(key)
        for key in (
            "opportunity_type",
            "upstream_scanner_trace_id",
            "upstream_scanner_opportunity_type",
        )
    ):
        return "scanner_opportunity"
    return ""


def resolve_trade_strategy_name(
    row: Dict[str, Any],
    *,
    decision_trace_lookup: DecisionTraceLookup = None,
    default: str = "",
) -> str:
    raw = raw_trade_strategy_name(row)
    if raw and not is_placeholder_strategy_name(raw):
        return raw

    trace_id = extract_trade_trace_id(row)
    if decision_trace_lookup and trace_id:
        try:
            resolved = infer_strategy_name_from_trace_item(decision_trace_lookup(trace_id))
        except Exception:
            resolved = ""
        if resolved:
            return resolved

    reasoning = str(row.get("reasoning") or row.get("reason") or "").strip().lower()
    if "llm_unavailable_fallback" in reasoning:
        return "s1_llm_unavailable_fallback"
    if "ai_autonomy_override" in reasoning:
        return "s1_ai_autonomy_override"

    source = trade_source_name(row).lower()
    if source == "stop_loss_take_profit":
        return "sltp_auto_exit"
    if source == "proactive_scanner":
        return "scanner_opportunity"
    return str(default or "").strip()


def has_attributable_trade_strategy(
    row: Dict[str, Any],
    *,
    decision_trace_lookup: DecisionTraceLookup = None,
) -> bool:
    return bool(resolve_trade_strategy_name(row, decision_trace_lookup=decision_trace_lookup, default=""))
