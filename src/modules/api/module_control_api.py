"""
模块控制API - 提供所有系统模块的集中控制接口
"""

import asyncio
import json
import logging
import re
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PLACEHOLDER_STRATEGY_NAMES = {
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


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        if x == x:
            return x
    except Exception:
        pass
    return float(default)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _parse_iso_datetime(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return datetime.min


def _trade_row_operation(row: Dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return ""
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    gateway = md.get("gateway") if isinstance(md.get("gateway"), dict) else {}
    op = str(gateway.get("op") or "").strip().lower()
    if op in {"open", "close"}:
        return op
    action = str(row.get("action") or md.get("action") or md.get("trade_phase") or "").strip().lower()
    if action in {"open", "opened"}:
        return "open"
    if action in {"close", "closed"}:
        return "close"
    decision_action = str(md.get("decision_action") or "").strip().upper()
    if decision_action.startswith("OPEN_"):
        return "open"
    if decision_action.startswith("CLOSE_"):
        return "close"
    return ""


def _trade_row_leg_side(row: Dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return ""
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    decision_action = str(md.get("decision_action") or "").strip().upper()
    if decision_action.endswith("_LONG"):
        return "long"
    if decision_action.endswith("_SHORT"):
        return "short"
    op = _trade_row_operation(row)
    side = str(row.get("side") or "").strip().lower()
    if op == "open":
        return "long" if side == "buy" else ("short" if side == "sell" else "")
    if op == "close":
        return "long" if side == "sell" else ("short" if side == "buy" else "")
    return ""


def _load_runtime_json(filename: str) -> Dict[str, Any]:
    try:
        runtime_dir = Path(__file__).resolve().parents[3] / "runtime"
        payload = json.loads((runtime_dir / filename).read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _load_runtime_json_snapshot(filename: str, *, stale_after_sec: float = 1800.0) -> Dict[str, Any]:
    runtime_dir = Path(__file__).resolve().parents[3] / "runtime"
    path = runtime_dir / filename
    out: Dict[str, Any] = {
        "path": str(path),
        "available": False,
        "fresh": False,
        "stale_after_seconds": float(stale_after_sec),
        "age_seconds": None,
        "last_modified": None,
        "payload": {},
    }
    try:
        stat = path.stat()
        payload = json.loads(path.read_text(encoding="utf-8"))
        age_seconds = max(0.0, time.time() - float(stat.st_mtime))
        out.update(
            {
                "available": True,
                "fresh": age_seconds <= float(stale_after_sec),
                "age_seconds": round(age_seconds, 3),
                "last_modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "payload": payload if isinstance(payload, dict) else {},
            }
        )
    except Exception as e:
        out["error"] = str(e)
    return out


def _load_recent_capacity_block_from_runtime() -> Optional[Dict[str, Any]]:
    try:
        runtime_dir = Path(__file__).resolve().parents[3] / "data" / "runtime"
        payload = json.loads((runtime_dir / "execution_gateway_recent_events.json").read_text(encoding="utf-8"))
        events = payload.get("recent_events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            return None
        for evt in reversed(events):
            if not isinstance(evt, dict):
                continue
            if evt.get("success") is not False:
                continue
            if str(evt.get("op") or "").lower() != "open":
                continue
            if str(evt.get("error_code") or "").upper() != "RISK_REDLINE_DENIED":
                continue
            detail = str(evt.get("detail") or "")
            reason = str(evt.get("reason") or "")
            if "max_positions" not in detail.lower() and "持仓数" not in detail and "max_positions" not in reason.lower():
                continue
            out = dict(evt)
            out["source"] = "runtime_recent_events"
            return out
    except Exception:
        return None
    return None


def _load_recent_capacity_block_from_app_log() -> Optional[Dict[str, Any]]:
    try:
        log_path = Path(__file__).resolve().parents[3] / "logs" / "app.log"
        ts_pat = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+-\s+")
        detail_pat = re.compile(r"(风控红线拦截：持仓数 .*?(?:；候选释放槽位: .*?)?)$")
        chunk_size = 256 * 1024
        with log_path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            offset = size
            carry = b""
            while offset > 0:
                read_size = min(chunk_size, offset)
                offset -= read_size
                fh.seek(offset)
                chunk = fh.read(read_size)
                text = (chunk + carry).decode("utf-8", errors="replace")
                lines = text.splitlines()
                if offset > 0 and lines:
                    carry = lines[0].encode("utf-8", errors="ignore")
                    lines = lines[1:]
                else:
                    carry = b""
                for line in reversed(lines):
                    if "风控红线拦截：持仓数" not in line:
                        continue
                    m_ts = ts_pat.search(line)
                    m_detail = detail_pat.search(line)
                    detail = m_detail.group(1).strip() if m_detail else line.strip()
                    if "max_positions" not in detail.lower() and "持仓数" not in detail:
                        continue
                    return {
                        "ts": m_ts.group(1).replace(" ", "T") + "Z" if m_ts else "-",
                        "symbol": "?",
                        "detail": detail,
                        "source": "app_log",
                    }
    except Exception:
        return None
    return None


def _summarize_trace_workflow_focus(traces: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(traces, dict):
        return {"top_stage": None, "top_status": None}
    top_stages = traces.get("top_workflow_stages") if isinstance(traces.get("top_workflow_stages"), list) else []
    top_statuses = traces.get("top_workflow_statuses") if isinstance(traces.get("top_workflow_statuses"), list) else []
    top_stage = top_stages[0] if top_stages else None
    top_status = top_statuses[0] if top_statuses else None
    return {
        "top_stage": top_stage if isinstance(top_stage, dict) else None,
        "top_status": top_status if isinstance(top_status, dict) else None,
    }


async def _get_live_position_count(main_controller: Any) -> int:
    try:
        ex = main_controller.get_exchange() if hasattr(main_controller, "get_exchange") else getattr(main_controller, "okx_exchange", None)
        if ex and hasattr(ex, "get_positions"):
            rows = await ex.get_positions()
            return len([r for r in (rows or []) if isinstance(r, dict) and abs(_safe_float(r.get("size") or r.get("pos") or r.get("positionAmt"))) > 1e-12])
    except Exception:
        pass
    try:
        st = getattr(main_controller, "_latest_account_state", None)
        rows = st.get("positions") if isinstance(st, dict) else None
        if isinstance(rows, list):
            return len([r for r in rows if isinstance(r, dict) and abs(_safe_float(r.get("size") or r.get("pos") or r.get("positionAmt"))) > 1e-12])
    except Exception:
        pass
    return 0


async def _get_live_sltp_active_order_count(main_controller: Any) -> int:
    sltp = getattr(main_controller, "stop_loss_manager", None)
    if not sltp:
        return 0
    try:
        if hasattr(sltp, "get_all_active_orders"):
            return len(await sltp.get_all_active_orders())
    except Exception:
        pass
    try:
        stats = sltp.get_stats() if hasattr(sltp, "get_stats") else {}
        return _safe_int((stats or {}).get("active_orders", 0))
    except Exception:
        return 0


async def _get_live_equity(main_controller: Any) -> float:
    mc = main_controller
    if not mc:
        return 0.0
    try:
        latest = getattr(mc, "_latest_account_state", {}) or {}
        if isinstance(latest, dict):
            portfolio_value = 0.0
            for key in ("usdt_total", "usdt_free", "total_equity", "equity", "totalEq"):
                portfolio_value = max(portfolio_value, _safe_float(latest.get(key)))
            balance_view = latest.get("balance")
            if isinstance(balance_view, dict):
                portfolio_value = max(
                    portfolio_value,
                    _safe_float(balance_view.get("USDT") or balance_view.get("usdt")),
                )
            if portfolio_value > 0:
                return portfolio_value
    except Exception:
        pass
    try:
        ex = mc.get_exchange() if hasattr(mc, "get_exchange") else getattr(mc, "okx_exchange", None)
        if ex and hasattr(ex, "get_balance"):
            acct = await ex.get_balance()
            if isinstance(acct, dict):
                return max(
                    _safe_float(acct.get("total_equity") or acct.get("equity") or acct.get("totalEq")),
                    _safe_float(((acct.get("USDT") or {}).get("total")) if isinstance(acct.get("USDT"), dict) else 0.0),
                    _safe_float(acct.get("USDT") or acct.get("usdt")),
                )
    except Exception:
        pass
    return 0.0


async def _build_agent_effectiveness_summary(
    main_controller: Any,
    *,
    trace_limit: int = 120,
    trade_limit: int = 500,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "summary": {
            "trace_sample_size": 0,
            "agent_trace_coverage": 0,
            "agent_trace_coverage_ratio": 0.0,
            "full_stack_trace_count": 0,
            "blocked_trace_count": 0,
            "executed_trace_count": 0,
            "trade_linked_trace_count": 0,
            "realized_trade_linked_trace_count": 0,
        },
        "agents": {},
        "top_issues": [],
    }
    if not main_controller:
        out["summary"]["message"] = "main_controller_unavailable"
        return out

    store = getattr(main_controller, "decision_trace_store", None)
    if not store or not hasattr(store, "get_recent"):
        out["summary"]["message"] = "decision_trace_store_unavailable"
        return out

    rows = list(store.get_recent(limit=int(trace_limit or 120)) or [])
    agent_names = [
        "market_structure_agent",
        "research_agent",
        "risk_governor_agent",
        "execution_coach_agent",
    ]
    out["summary"]["trace_sample_size"] = len(rows)

    trade_rows: List[Dict[str, Any]] = []
    ths = getattr(main_controller, "trade_history_service", None)
    if ths and hasattr(ths, "get_trade_history"):
        try:
            trade_rows = await ths.get_trade_history(limit=max(50, int(trade_limit or 500)))
        except Exception:
            trade_rows = []

    open_trace_ids: set[str] = set()
    realized_trace_ids: set[str] = set()
    trade_trace_prefixes: Counter[str] = Counter()
    realized_trace_prefixes: Counter[str] = Counter()
    realized_trace_examples: List[str] = []
    realized_by_strategy: Dict[str, Dict[str, float]] = defaultdict(lambda: {"count": 0.0, "pnl": 0.0})
    for row in trade_rows or []:
        if not isinstance(row, dict):
            continue
        meta = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
        trace_id = _extract_trade_trace_id(row)
        if trace_id:
            open_trace_ids.add(trace_id)
            trade_trace_prefixes[_trace_namespace(trace_id)] += 1
            pnl_v = _safe_float(row.get("pnl"))
            pnl_pct_v = _safe_float(row.get("pnl_percent"))
            if abs(pnl_v) > 1e-12 or abs(pnl_pct_v) > 1e-12:
                realized_trace_ids.add(trace_id)
                realized_trace_prefixes[_trace_namespace(trace_id)] += 1
                if len(realized_trace_examples) < 8:
                    realized_trace_examples.append(trace_id)
        strategy_id = str(meta.get("strategy_id") or row.get("strategy") or "").strip()
        pnl_v = _safe_float(row.get("pnl"))
        pnl_pct_v = _safe_float(row.get("pnl_percent"))
        if strategy_id and (abs(pnl_v) > 1e-12 or abs(pnl_pct_v) > 1e-12):
            realized_by_strategy[strategy_id]["count"] += 1.0
            realized_by_strategy[strategy_id]["pnl"] += pnl_v

    per_agent: Dict[str, Dict[str, Any]] = {}
    agent_trace_coverage = 0
    full_stack_count = 0
    blocked_trace_count = 0
    executed_trace_count = 0
    linked_trace_count = 0
    realized_linked_trace_count = 0
    store_trace_ids: set[str] = set()
    store_trace_prefixes: Counter[str] = Counter()

    for name in agent_names:
        per_agent[name] = {
            "participated": 0,
            "avg_confidence": 0.0,
            "blocking_flag_count": 0,
            "workflow_blocked_count": 0,
            "guard_rejected_count": 0,
            "execution_success_count": 0,
            "trade_linked_count": 0,
            "realized_trade_linked_count": 0,
            "next_actions": [],
            "verdicts": [],
            "top_symbols": [],
        }

    for row in rows:
        if not isinstance(row, dict):
            continue
        trace_id = str(row.get("trace_id") or "").strip()
        if trace_id:
            store_trace_ids.add(trace_id)
            store_trace_prefixes[_trace_namespace(trace_id)] += 1
        workflow = row.get("workflow", {}) if isinstance(row.get("workflow"), dict) else {}
        guard = row.get("guard", {}) if isinstance(row.get("guard"), dict) else {}
        execution = row.get("execution", {}) if isinstance(row.get("execution"), dict) else {}
        agent_outputs = row.get("agent_outputs", {}) if isinstance(row.get("agent_outputs"), dict) else {}
        participating = [name for name in agent_names if isinstance(agent_outputs.get(name), dict)]
        if participating:
            agent_trace_coverage += 1
        if len(participating) == len(agent_names):
            full_stack_count += 1
        if str(workflow.get("status") or "").lower() == "blocked":
            blocked_trace_count += 1
        if str(execution.get("status") or "").lower() == "success":
            executed_trace_count += 1
        if trace_id and trace_id in open_trace_ids:
            linked_trace_count += 1
        if trace_id and trace_id in realized_trace_ids:
            realized_linked_trace_count += 1

        for name in participating:
            payload = agent_outputs.get(name, {}) if isinstance(agent_outputs.get(name), dict) else {}
            stat = per_agent[name]
            stat["participated"] += 1
            stat["avg_confidence"] += _safe_float(payload.get("confidence"))
            if payload.get("blocking_flags"):
                stat["blocking_flag_count"] += 1
            if str(workflow.get("status") or "").lower() == "blocked":
                stat["workflow_blocked_count"] += 1
            if str(guard.get("status") or "").lower() == "rejected":
                stat["guard_rejected_count"] += 1
            if str(execution.get("status") or "").lower() == "success":
                stat["execution_success_count"] += 1
            if trace_id and trace_id in open_trace_ids:
                stat["trade_linked_count"] += 1
            if trace_id and trace_id in realized_trace_ids:
                stat["realized_trade_linked_count"] += 1
            stat.setdefault("_next_action_counter", Counter())
            stat.setdefault("_verdict_counter", Counter())
            stat.setdefault("_symbol_counter", Counter())
            stat["_next_action_counter"][str(payload.get("next_action") or "unknown")] += 1
            structured = payload.get("structured_verdict", {}) if isinstance(payload.get("structured_verdict"), dict) else {}
            verdict = (
                structured.get("risk_verdict")
                or structured.get("execution_recommendation")
                or structured.get("regime_label")
                or payload.get("summary")
                or "unknown"
            )
            stat["_verdict_counter"][str(verdict)] += 1
            stat["_symbol_counter"][str(row.get("symbol") or "UNKNOWN")] += 1

    for name, stat in per_agent.items():
        participated = int(stat.get("participated", 0) or 0)
        if participated > 0:
            stat["avg_confidence"] = round(float(stat.get("avg_confidence", 0.0) or 0.0) / participated, 4)
        else:
            stat["avg_confidence"] = 0.0
        stat["coverage_ratio"] = round(participated / max(1, len(rows)), 4)
        stat["workflow_blocked_ratio"] = round(
            float(stat.get("workflow_blocked_count", 0) or 0) / max(1, participated),
            4,
        )
        stat["execution_success_ratio"] = round(
            float(stat.get("execution_success_count", 0) or 0) / max(1, participated),
            4,
        )
        stat["next_actions"] = [
            {"key": k, "count": int(v)}
            for k, v in stat.pop("_next_action_counter", Counter()).most_common(5)
        ]
        stat["verdicts"] = [
            {"key": k, "count": int(v)}
            for k, v in stat.pop("_verdict_counter", Counter()).most_common(5)
        ]
        stat["top_symbols"] = [
            {"key": k, "count": int(v)}
            for k, v in stat.pop("_symbol_counter", Counter()).most_common(5)
        ]

    out["summary"].update(
        {
            "agent_trace_coverage": int(agent_trace_coverage),
            "agent_trace_coverage_ratio": round(agent_trace_coverage / max(1, len(rows)), 4),
            "full_stack_trace_count": int(full_stack_count),
            "blocked_trace_count": int(blocked_trace_count),
            "executed_trace_count": int(executed_trace_count),
            "trade_linked_trace_count": int(linked_trace_count),
            "realized_trade_linked_trace_count": int(realized_linked_trace_count),
        }
    )
    out["agents"] = per_agent
    realized_intersection = realized_trace_ids & store_trace_ids
    attribution_diagnosis = "insufficient_trace_data"
    if realized_trace_ids and store_trace_ids:
        if executed_trace_count == 0:
            attribution_diagnosis = "store_sample_contains_no_executions"
        elif realized_intersection:
            attribution_diagnosis = "ok"
        else:
            attribution_diagnosis = "realized_trace_namespace_mismatch"
    out["attribution_diagnostics"] = {
        "store_trace_count": len(store_trace_ids),
        "trade_trace_count": len(open_trace_ids),
        "realized_trace_count": len(realized_trace_ids),
        "realized_store_intersection_count": len(realized_intersection),
        "store_trace_namespaces": [{"key": k, "count": int(v)} for k, v in store_trace_prefixes.most_common(8)],
        "trade_trace_namespaces": [{"key": k, "count": int(v)} for k, v in trade_trace_prefixes.most_common(8)],
        "realized_trace_namespaces": [{"key": k, "count": int(v)} for k, v in realized_trace_prefixes.most_common(8)],
        "realized_trace_examples": realized_trace_examples,
        "intersection_examples": list(sorted(realized_intersection))[:8],
        "diagnosis": attribution_diagnosis,
    }

    top_issues: List[Dict[str, Any]] = []
    if len(rows) > 0 and agent_trace_coverage / max(1, len(rows)) < 0.4:
        top_issues.append(
            {
                "priority": "high",
                "issue": "四智能体覆盖率过低",
                "evidence": {
                    "trace_sample_size": len(rows),
                    "agent_trace_coverage": int(agent_trace_coverage),
                    "coverage_ratio": round(agent_trace_coverage / max(1, len(rows)), 4),
                },
                "recommendation": "优先把 4-agent advisory 链路提升到主决策主路径，否则它们对盈利没有实际控制权。",
            }
        )
    if per_agent["research_agent"]["participated"] > 0 and per_agent["research_agent"]["blocking_flag_count"] >= int(
        per_agent["research_agent"]["participated"]
    ):
        top_issues.append(
            {
                "priority": "high",
                "issue": "research_agent 长期处于研究未完成状态",
                "evidence": {
                    "participated": per_agent["research_agent"]["participated"],
                    "blocking_flag_count": per_agent["research_agent"]["blocking_flag_count"],
                    "top_verdicts": per_agent["research_agent"]["verdicts"][:3],
                },
                "recommendation": "将 research_agent 从实时阻塞角色降级为复盘/评分输入，否则会持续拖低开仓率。",
            }
        )
    if per_agent["execution_coach_agent"]["participated"] > 0:
        normal_count = next(
            (int(x.get("count", 0) or 0) for x in per_agent["execution_coach_agent"]["verdicts"] if str(x.get("key") or "") == "normal"),
            0,
        )
        if normal_count == per_agent["execution_coach_agent"]["participated"]:
            top_issues.append(
                {
                    "priority": "medium",
                    "issue": "execution_coach_agent 输出缺乏区分度",
                    "evidence": {
                        "participated": per_agent["execution_coach_agent"]["participated"],
                        "verdicts": per_agent["execution_coach_agent"]["verdicts"][:3],
                    },
                    "recommendation": "增加 wait_or_slice / reduce_size / cancel_chase 等明确执行动作，否则执行教练对盈利提升有限。",
                }
            )
    if executed_trace_count == 0 and len(rows) > 0:
        top_issues.append(
            {
                "priority": "medium",
                "issue": "当前 trace 样本没有成功执行记录，无法评估真实收益闭环",
                "evidence": {
                    "trace_sample_size": len(rows),
                    "executed_trace_count": int(executed_trace_count),
                    "blocked_trace_count": int(blocked_trace_count),
                    "realized_trace_count": len(realized_trace_ids),
                    "attribution_diagnosis": out["attribution_diagnostics"]["diagnosis"],
                },
                "recommendation": "等待出现 execution=success 的新样本，或增大 trace_limit 后再评估四智能体对真实收益的影响。",
            }
        )
    elif realized_linked_trace_count == 0:
        top_issues.append(
            {
                "priority": "high",
                "issue": "四智能体与真实已实现收益仍缺少可靠闭环归因",
                "evidence": {
                    "trade_linked_trace_count": int(linked_trace_count),
                    "realized_trade_linked_trace_count": int(realized_linked_trace_count),
                    "attribution_diagnosis": out["attribution_diagnostics"]["diagnosis"],
                    "realized_trace_namespaces": out["attribution_diagnostics"]["realized_trace_namespaces"][:3],
                    "store_trace_namespaces": out["attribution_diagnostics"]["store_trace_namespaces"][:3],
                    "realized_strategy_examples": [
                        {"strategy_id": k, "count": int(v.get("count", 0) or 0), "pnl": round(float(v.get("pnl", 0.0) or 0.0), 6)}
                        for k, v in sorted(realized_by_strategy.items(), key=lambda kv: float(kv[1].get("pnl", 0.0)), reverse=True)[:5]
                    ],
                },
                "recommendation": "继续打通 trace_id 从开仓到平仓的收益回写，否则无法证明四智能体是否真正提升盈利。",
            }
        )
    out["top_issues"] = top_issues
    return out


def _trace_namespace(trace_id: str) -> str:
    tid = str(trace_id or "").strip()
    if not tid:
        return "missing"
    if tid.startswith("sltp:"):
        return "sltp"
    if tid.startswith("scanner-"):
        return "scanner"
    if tid.startswith("hold-"):
        return "hold"
    if tid.startswith("parsed-hold-"):
        return "parsed_hold"
    if re.fullmatch(r"[0-9a-fA-F-]{32,36}", tid):
        return "uuid"
    return tid.split(":", 1)[0].split("-", 1)[0] or "other"


def _extract_trade_trace_id(row: Dict[str, Any]) -> str:
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


def _extract_trade_semantic_context(row: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    direct = md.get("semantic_context")
    if isinstance(direct, dict):
        return direct
    gateway = md.get("gateway") if isinstance(md.get("gateway"), dict) else {}
    context = gateway.get("context") if isinstance(gateway.get("context"), dict) else {}
    payload = context.get("semantic_context")
    return payload if isinstance(payload, dict) else {}


async def _build_live_trade_context(main_controller: Any, *, limit: int = 1000) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "latest_trade": {},
        "best_regime": {},
        "worst_regime": {},
        "symbol_summaries": [],
        "source": "trade_history_service",
    }
    ths = getattr(main_controller, "trade_history_service", None) if main_controller else None
    if not ths or not hasattr(ths, "get_trade_history"):
        out["source"] = "trade_history_service_unavailable"
        return out
    try:
        rows = await ths.get_trade_history(limit=max(100, int(limit or 1000)))
    except Exception:
        out["source"] = "trade_history_service_failed"
        return out

    ordered_rows = sorted(
        [row for row in (rows or []) if isinstance(row, dict)],
        key=lambda row: _parse_iso_datetime(row.get("timestamp")),
        reverse=True,
    )
    if not ordered_rows:
        return out

    latest = ordered_rows[0]
    latest_md = latest.get("metadata") if isinstance(latest.get("metadata"), dict) else {}
    latest_semantic = _extract_trade_semantic_context(latest)
    latest_regime = _infer_regime_from_trade_row(latest)
    out["latest_trade"] = {
        "timestamp": latest.get("timestamp"),
        "trade_id": latest.get("trade_id") or latest.get("order_id") or latest.get("id"),
        "symbol": latest.get("symbol"),
        "side": latest.get("side"),
        "operation": _trade_row_operation(latest),
        "price": _safe_float(latest.get("price")),
        "quantity": _safe_float(latest.get("quantity") or latest.get("size") or latest.get("executed_quantity")),
        "pnl": _safe_float(latest.get("pnl")),
        "fee": _safe_float(latest.get("fee")),
        "reasoning": latest.get("reasoning"),
        "strategy_id": latest_md.get("strategy_id") or latest.get("strategy"),
        "regime_label": latest_semantic.get("regime_label") or latest_md.get("regime_label") or latest_regime.get("regime"),
        "trace_id": _extract_trade_trace_id(latest) or None,
    }

    regime_buckets: Dict[str, Dict[str, Any]] = {}
    symbol_buckets: Dict[str, Dict[str, Any]] = {}
    for row in ordered_rows:
        if _is_low_fidelity_historical_trade_row(row):
            continue
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        op = _trade_row_operation(row)
        pnl = _safe_float(row.get("pnl"))
        fee = _safe_float(row.get("fee"))
        pnl_pct = _safe_float(row.get("pnl_percent"))
        ts = row.get("timestamp")

        bucket = symbol_buckets.setdefault(
            symbol,
            {
                "symbol": symbol,
                "rows": 0,
                "opens": 0,
                "closes": 0,
                "realized_closes": 0,
                "total_pnl": 0.0,
                "total_fee": 0.0,
                "net_after_fees": 0.0,
                "last_timestamp": ts,
            },
        )
        bucket["rows"] += 1
        bucket["total_fee"] += fee
        bucket["net_after_fees"] += pnl + fee
        if op == "open":
            bucket["opens"] += 1
        elif op == "close":
            bucket["closes"] += 1
            bucket["realized_closes"] += 1
            bucket["total_pnl"] += pnl
        if not bucket.get("last_timestamp"):
            bucket["last_timestamp"] = ts

        if op != "close" and abs(pnl) <= 1e-12 and abs(pnl_pct) <= 1e-12:
            continue
        regime_info = _infer_regime_from_trade_row(row)
        regime = str(regime_info.get("regime") or "unknown").strip().lower() or "unknown"
        if regime == "unknown":
            continue
        regime_bucket = regime_buckets.setdefault(
            regime,
            {"regime": regime, "total_trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0},
        )
        regime_bucket["total_trades"] += 1
        regime_bucket["total_pnl"] += pnl
        if pnl > 1e-12:
            regime_bucket["wins"] += 1
        elif pnl < -1e-12:
            regime_bucket["losses"] += 1

    regime_rows: List[Dict[str, Any]] = []
    for item in regime_buckets.values():
        total_trades = _safe_int(item.get("total_trades"))
        wins = _safe_int(item.get("wins"))
        total_pnl = _safe_float(item.get("total_pnl"))
        regime_rows.append(
            {
                "regime": item.get("regime"),
                "total_trades": total_trades,
                "win_rate": round((wins / total_trades), 4) if total_trades > 0 else 0.0,
                "total_pnl": round(total_pnl, 6),
                "expectancy": round((total_pnl / total_trades), 6) if total_trades > 0 else 0.0,
            }
        )
    regime_rows.sort(key=lambda item: (_safe_float(item.get("total_pnl")), _safe_int(item.get("total_trades"))), reverse=True)
    if regime_rows:
        out["best_regime"] = regime_rows[0]
        out["worst_regime"] = regime_rows[-1]

    symbol_rows: List[Dict[str, Any]] = []
    for item in symbol_buckets.values():
        symbol_rows.append(
            {
                "symbol": item.get("symbol"),
                "rows": _safe_int(item.get("rows")),
                "opens": _safe_int(item.get("opens")),
                "closes": _safe_int(item.get("closes")),
                "realized_closes": _safe_int(item.get("realized_closes")),
                "total_pnl": round(_safe_float(item.get("total_pnl")), 6),
                "total_fee": round(_safe_float(item.get("total_fee")), 6),
                "net_after_fees": round(_safe_float(item.get("net_after_fees")), 6),
                "last_timestamp": item.get("last_timestamp"),
            }
        )
    symbol_rows.sort(key=lambda item: (_safe_float(item.get("net_after_fees")), item.get("last_timestamp") or ""), reverse=True)
    out["symbol_summaries"] = symbol_rows[:10]
    return out


async def _build_trade_lifecycle_summary(
    main_controller: Any,
    *,
    trade_limit: int = 300,
    recent_limit: int = 20,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "summary": {
            "sample_size": 0,
            "opens": 0,
            "closes": 0,
            "realized_pnl": 0.0,
            "fees": 0.0,
            "net_pnl_plus_fees": 0.0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "trace_linked_rows": 0,
            "avg_hold_hours": 0.0,
        },
        "close_reason_top": [],
        "recent_rows": [],
        "exit_review": {
            "take_profit_positive_count": 0,
            "stop_loss_negative_count": 0,
            "partial_take_profit_positive_count": 0,
        },
    }
    ths = getattr(main_controller, "trade_history_service", None) if main_controller else None
    if not ths or not hasattr(ths, "get_trade_history"):
        out["summary"]["message"] = "trade_history_service_unavailable"
        return out
    try:
        rows = await ths.get_trade_history(limit=max(50, int(trade_limit or 300)))
    except Exception as e:
        out["summary"]["message"] = f"trade_history_load_failed:{e}"
        return out

    close_reason_counter: Counter[str] = Counter()
    open_legs: Dict[tuple[str, str], List[datetime]] = defaultdict(list)
    durations_sec: List[float] = []
    wins = 0
    losses = 0
    realized_pnl = 0.0
    fees = 0.0
    opens = 0
    closes = 0
    trace_linked_rows = 0
    recent_rows: List[Dict[str, Any]] = []
    exit_review = {
        "take_profit_positive_count": 0,
        "stop_loss_negative_count": 0,
        "partial_take_profit_positive_count": 0,
    }

    ordered_rows = sorted(
        [
            row
            for row in (rows or [])
            if isinstance(row, dict) and not _is_low_fidelity_historical_trade_row(row)
        ],
        key=lambda row: _parse_iso_datetime(row.get("timestamp")),
        reverse=True,
    )
    chronological_rows = list(reversed(ordered_rows))
    for row in chronological_rows:
        if not isinstance(row, dict):
            continue
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        gateway = md.get("gateway") if isinstance(md.get("gateway"), dict) else {}
        op = _trade_row_operation(row) or str(gateway.get("op") or "").lower()
        fees += _safe_float(row.get("fee"))
        if _extract_trade_trace_id(row):
            trace_linked_rows += 1
        ts = _parse_iso_datetime(row.get("timestamp"))
        if ts == datetime.min:
            ts = None
        symbol = str(row.get("symbol") or "").upper()
        leg_side = _trade_row_leg_side(row)
        leg_key = (symbol, leg_side)
        if op == "open":
            opens += 1
            if ts is not None and symbol and leg_side:
                open_legs[leg_key].append(ts)
        elif op == "close":
            closes += 1
            pnl = _safe_float(row.get("pnl"))
            realized_pnl += pnl
            if pnl > 1e-9:
                wins += 1
            elif pnl < -1e-9:
                losses += 1
            reason = str(row.get("reasoning") or gateway.get("reason") or "?")
            close_reason_counter[reason] += 1
            low_reason = reason.lower()
            if "take_profit" in low_reason and pnl > 0:
                exit_review["take_profit_positive_count"] += 1
            if "partial_take_profit" in low_reason and pnl > 0:
                exit_review["partial_take_profit_positive_count"] += 1
            if "stop_loss" in low_reason and pnl < 0:
                exit_review["stop_loss_negative_count"] += 1
            if ts is not None and symbol and leg_side:
                queue = open_legs.get(leg_key) or []
                if queue:
                    opened_at = queue.pop(0)
                    delta = (ts - opened_at).total_seconds()
                    if delta >= 0:
                        durations_sec.append(delta)

    for row in ordered_rows[: max(1, int(recent_limit or 20))]:
        if not isinstance(row, dict):
            continue
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        gateway = md.get("gateway") if isinstance(md.get("gateway"), dict) else {}
        semantic = _extract_trade_semantic_context(row)
        recent_rows.append(
            {
                "timestamp": row.get("timestamp"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "operation": _trade_row_operation(row) or str(gateway.get("op") or "").lower(),
                "price": row.get("price"),
                "quantity": row.get("quantity") or row.get("size"),
                "pnl": _safe_float(row.get("pnl")),
                "fee": _safe_float(row.get("fee")),
                "pnl_percent": _safe_float(row.get("pnl_percent")),
                "reasoning": row.get("reasoning") or gateway.get("reason"),
                "trace_id": _extract_trade_trace_id(row) or None,
                "strategy_id": md.get("strategy_id") or row.get("strategy"),
                "regime_label": semantic.get("regime_label") or md.get("regime_label"),
                "risk_verdict": semantic.get("risk_verdict"),
                "execution_recommendation": semantic.get("execution_recommendation"),
            }
        )

    decided = wins + losses
    avg_hold_hours = (sum(durations_sec) / (len(durations_sec) * 3600.0)) if durations_sec else 0.0
    out["summary"].update(
        {
            "sample_size": len(ordered_rows),
            "opens": int(opens),
            "closes": int(closes),
            "realized_pnl": round(realized_pnl, 6),
            "fees": round(fees, 6),
            "net_pnl_plus_fees": round(realized_pnl + fees, 6),
            "wins": int(wins),
            "losses": int(losses),
            "win_rate": round((wins / decided), 4) if decided > 0 else 0.0,
            "trace_linked_rows": int(trace_linked_rows),
            "avg_hold_hours": round(avg_hold_hours, 4),
        }
    )
    out["close_reason_top"] = [{"reason": k, "count": int(v)} for k, v in close_reason_counter.most_common(8)]
    out["recent_rows"] = recent_rows
    out["exit_review"] = exit_review
    return out


async def _build_closed_loop_summary_data(main_controller: Any, *, trace_limit: int = 120) -> Dict[str, Any]:
    mc = main_controller
    store = getattr(mc, "decision_trace_store", None)
    traces = store.analyze_recent(limit=int(trace_limit or 120)) if (store and hasattr(store, "analyze_recent")) else {}
    summary = traces.get("summary", {}) if isinstance(traces, dict) else {}
    workflow_focus = _summarize_trace_workflow_focus(traces)
    recent = traces.get("recent", []) if isinstance(traces, dict) else []

    watch_snapshot = _load_runtime_json_snapshot("realtime_watch.latest.json")
    watch = watch_snapshot.get("payload", {}) if isinstance(watch_snapshot.get("payload"), dict) else {}
    watch_fresh = bool(watch_snapshot.get("fresh"))
    analysis = watch.get("analysis", {}) if (watch_fresh and isinstance(watch.get("analysis"), dict)) else {}
    live_trade_context = await _build_live_trade_context(mc, limit=max(240, int(trace_limit or 120) * 8))
    latest_trade = analysis.get("latest_trade", {}) if isinstance(analysis.get("latest_trade"), dict) else {}
    best_regime = analysis.get("best_regime", {}) if isinstance(analysis.get("best_regime"), dict) else {}
    worst_regime = analysis.get("worst_regime", {}) if isinstance(analysis.get("worst_regime"), dict) else {}
    symbol_summaries = analysis.get("symbol_summaries", []) if isinstance(analysis.get("symbol_summaries"), list) else []
    if not latest_trade:
        latest_trade = live_trade_context.get("latest_trade", {}) if isinstance(live_trade_context.get("latest_trade"), dict) else {}
    if not best_regime:
        best_regime = live_trade_context.get("best_regime", {}) if isinstance(live_trade_context.get("best_regime"), dict) else {}
    if not worst_regime:
        worst_regime = live_trade_context.get("worst_regime", {}) if isinstance(live_trade_context.get("worst_regime"), dict) else {}
    if not symbol_summaries:
        symbol_summaries = live_trade_context.get("symbol_summaries", []) if isinstance(live_trade_context.get("symbol_summaries"), list) else []
    ai_core = getattr(mc, "ai_core", None)
    rejected_rows = list(getattr(ai_core, "_rejected_signals", []) or []) if ai_core is not None else []
    recent_advisory_rows = [
        row for row in reversed(rejected_rows[-120:])
        if isinstance(row, dict) and str(row.get("reason") or "") == "regime_advisory_only_rejected"
    ]
    llm_manager = getattr(mc, "enhanced_llm_manager", None) or (getattr(ai_core, "llm", None) if ai_core is not None else None)
    sltp = getattr(mc, "stop_loss_manager", None)
    sltp_stats = sltp.get_stats() if (sltp and hasattr(sltp, "get_stats")) else {}

    gateway = getattr(mc, "execution_gateway", None)
    gateway_snapshot = await gateway.get_snapshot() if (gateway and hasattr(gateway, "get_snapshot")) else {}
    policy_metrics = gateway_snapshot.get("policy_metrics", {}) if isinstance(gateway_snapshot, dict) else {}
    reconciliation = gateway_snapshot.get("reconciliation", {}) if isinstance(gateway_snapshot, dict) else {}
    recon_summary = reconciliation.get("summary", {}) if isinstance(reconciliation, dict) else {}

    monitor_summary = {}
    try:
        from src.modules.api.monitoring_api import get_monitoring_summary
        monitor_summary = await get_monitoring_summary()
    except Exception:
        monitor_summary = {}

    reason_counter: Counter[str] = Counter()
    stage_counter: Counter[str] = Counter()
    symbol_counter: Counter[str] = Counter()
    hold_tag_counter: Counter[str] = Counter()
    hold_symbol_counter: Counter[str] = Counter()
    hold_regime_counter: Counter[str] = Counter()
    hold_strategy_counter: Counter[str] = Counter()
    hold_fallback_reason_counter: Counter[str] = Counter()
    hold_fallback_model_counter: Counter[str] = Counter()
    hold_recent_samples: List[Dict[str, Any]] = []
    hold_fallback_count = 0
    for row in recent:
        if not isinstance(row, dict):
            continue
        guard = row.get("guard", {}) if isinstance(row.get("guard"), dict) else {}
        reason = str(guard.get("reason") or row.get("reason") or "unknown")
        stage = str(guard.get("stage") or row.get("stage") or "unknown")
        symbol = str(row.get("symbol") or "unknown")
        reason_counter[reason] += 1
        stage_counter[stage] += 1
        symbol_counter[symbol] += 1
        if reason == "hold_by_ai_decision":
            guard_extras = guard.get("extras") if isinstance(guard.get("extras"), dict) else {}
            intent = row.get("intent") if isinstance(row.get("intent"), dict) else {}
            intent_extras = intent.get("extras") if isinstance(intent.get("extras"), dict) else {}
            extras = guard_extras or intent_extras
            hold_tags = extras.get("hold_reason_tags") if isinstance(extras.get("hold_reason_tags"), dict) else {}
            sr_snapshot = extras.get("sr_snapshot") if isinstance(extras.get("sr_snapshot"), dict) else {}
            regime = str(extras.get("regime") or extras.get("market_regime") or "unknown")
            strategy_used = str(intent.get("strategy_used") or extras.get("strategy_used") or "")
            reasoning_excerpt = str(extras.get("reasoning_excerpt") or intent.get("reasoning") or "")
            llm_failure_reason = str(extras.get("llm_failure_reason") or "")
            llm_model_id = str(extras.get("llm_model_id") or "")
            hold_symbol_counter[symbol] += 1
            hold_regime_counter[regime] += 1
            hold_strategy_counter[strategy_used or "unknown"] += 1
            for tag_name, enabled in hold_tags.items():
                if bool(enabled):
                    hold_tag_counter[str(tag_name)] += 1
            if (
                bool(hold_tags.get("llm_unavailable_fallback", False))
                or "llm_unavailable_fallback" in reasoning_excerpt.lower()
                or "fallback" in strategy_used.lower()
            ):
                hold_fallback_count += 1
                hold_fallback_reason_counter[llm_failure_reason or "unknown"] += 1
                hold_fallback_model_counter[llm_model_id or "unknown"] += 1
            if len(hold_recent_samples) < 10:
                hold_recent_samples.append(
                    {
                        "ts": row.get("updated_at") or row.get("created_at"),
                        "symbol": symbol,
                        "side": row.get("side"),
                        "confidence": intent.get("confidence"),
                        "risk_level": extras.get("risk_level"),
                        "strategy_used": strategy_used,
                        "regime": regime,
                        "reasoning_excerpt": reasoning_excerpt,
                        "llm_fallback_kind": extras.get("llm_fallback_kind"),
                        "llm_failure_reason": llm_failure_reason or None,
                        "llm_error_code": extras.get("llm_error_code"),
                        "llm_model_id": llm_model_id or None,
                        "llm_provider": extras.get("llm_provider"),
                        "llm_latency_ms": extras.get("llm_latency_ms"),
                        "active_tags": [str(k) for k, enabled in hold_tags.items() if bool(enabled)],
                        "sr_trigger_present": not bool(hold_tags.get("no_sr_entry_trigger", False)),
                        "sr_snapshot": sr_snapshot,
                    }
                )

    top_reject_reasons = [{"reason": k, "count": int(v)} for k, v in reason_counter.most_common(8)]
    top_reject_symbols = [{"symbol": k, "count": int(v)} for k, v in symbol_counter.most_common(8)]
    top_reject_stages = [{"stage": k, "count": int(v)} for k, v in stage_counter.most_common(8)]
    top_hold_tags = [{"tag": k, "count": int(v)} for k, v in hold_tag_counter.most_common(8)]
    top_hold_symbols = [{"symbol": k, "count": int(v)} for k, v in hold_symbol_counter.most_common(8)]
    top_hold_regimes = [{"regime": k, "count": int(v)} for k, v in hold_regime_counter.most_common(8)]
    top_hold_strategies = [{"strategy_used": k, "count": int(v)} for k, v in hold_strategy_counter.most_common(8)]
    top_fallback_reasons = [{"reason": k, "count": int(v)} for k, v in hold_fallback_reason_counter.most_common(8)]
    top_fallback_models = [{"model_id": k, "count": int(v)} for k, v in hold_fallback_model_counter.most_common(8)]
    hold_total = int(sum(hold_symbol_counter.values()))
    hold_fallback_ratio = float(hold_fallback_count) / float(hold_total) if hold_total > 0 else 0.0
    llm_diag: Dict[str, Any] = {}
    try:
        if llm_manager is not None:
            task_map = getattr(llm_manager, "task_model_mapping", {}) or {}
            decision_model_order: List[str] = []
            for task_key, model_ids in task_map.items():
                task_name = str(getattr(task_key, "value", task_key) or "")
                if task_name == "decision_making" and isinstance(model_ids, list):
                    decision_model_order = [str(mid) for mid in model_ids]
                    break
            raw_unhealthy = getattr(llm_manager, "_unhealthy_until", {}) or {}
            active_circuit_breaks: List[Dict[str, Any]] = []
            now_ts = time.time()
            if isinstance(raw_unhealthy, dict):
                for model_id, until_ts in raw_unhealthy.items():
                    remaining = max(0.0, float(until_ts or 0.0) - now_ts)
                    if remaining > 0:
                        active_circuit_breaks.append(
                            {
                                "model_id": str(model_id),
                                "seconds_remaining": round(remaining, 1),
                            }
                        )
            usage_rows: List[Dict[str, Any]] = []
            usage_stats = llm_manager.get_usage_stats() if hasattr(llm_manager, "get_usage_stats") else {}
            if isinstance(usage_stats, dict):
                for model_id, stat in usage_stats.items():
                    total_calls = _safe_int(getattr(stat, "total_calls", 0))
                    success_calls = _safe_int(getattr(stat, "successful_calls", 0))
                    success_rate = (float(success_calls) / float(total_calls)) if total_calls > 0 else 0.0
                    usage_rows.append(
                        {
                            "model_id": str(model_id),
                            "total_calls": total_calls,
                            "successful_calls": success_calls,
                            "failed_calls": _safe_int(getattr(stat, "failed_calls", 0)),
                            "success_rate": round(success_rate, 4),
                            "avg_latency_ms": round(_safe_float(getattr(stat, "avg_latency_ms", 0.0)), 1),
                        }
                    )
            usage_rows.sort(key=lambda x: (-x["total_calls"], x["model_id"]))
            llm_diag = {
                "default_model": str(getattr(llm_manager, "default_model", "") or ""),
                "decision_model_order": decision_model_order,
                "active_circuit_breaks": active_circuit_breaks,
                "usage": usage_rows[:8],
            }
    except Exception:
        llm_diag = {}

    tp_net_edge_suppressed = _safe_int((sltp_stats or {}).get("tp_net_edge_suppressed", analysis.get("tp_net_edge_suppressed", 0)))
    opportunities_blocked = {
        "guard_rejected": _safe_int(summary.get("guard_rejected", 0)),
        "guard_passed": _safe_int(summary.get("guard_passed", 0)),
        "execution_success": _safe_int(summary.get("execution_success", 0)),
        "execution_failed": _safe_int(summary.get("execution_failed", 0)),
        "reconciliation_blocked": _safe_int(summary.get("reconciliation_blocked", 0)),
        "rr_rejected": _safe_int(analysis.get("rr_rejected", 0)),
        "sr_timing_rejected": _safe_int(analysis.get("sr_timing_rejected", 0)),
        "open_evidence_rejected": _safe_int(analysis.get("open_evidence_rejected", 0)),
        "regime_advisory_only_rejected": _safe_int(analysis.get("regime_advisory_only_rejected", len(recent_advisory_rows))),
        "tp_net_edge_suppressed": tp_net_edge_suppressed,
    }
    tp_suppressed_by_regime_raw = (sltp_stats or {}).get("tp_net_edge_suppressed_by_regime") or analysis.get("tp_net_edge_suppressed_by_regime", {})
    tp_suppressed_by_reason_raw = (sltp_stats or {}).get("tp_net_edge_suppressed_by_reason") or analysis.get("tp_net_edge_suppressed_by_reason", {})
    tp_suppressed_by_regime = (
        {str(k): _safe_int(v) for k, v in tp_suppressed_by_regime_raw.items() if _safe_int(v) > 0}
        if isinstance(tp_suppressed_by_regime_raw, dict)
        else {}
    )
    tp_suppressed_by_reason = (
        {str(k): _safe_int(v) for k, v in tp_suppressed_by_reason_raw.items() if _safe_int(v) > 0}
        if isinstance(tp_suppressed_by_reason_raw, dict)
        else {}
    )
    tp_top_regimes = [{"regime": k, "count": int(v)} for k, v in sorted(tp_suppressed_by_regime.items(), key=lambda kv: int(kv[1]), reverse=True)[:5]]
    tp_top_reasons = [{"reason": k, "count": int(v)} for k, v in sorted(tp_suppressed_by_reason.items(), key=lambda kv: int(kv[1]), reverse=True)[:5]]
    tp_recent_events = (
        (sltp_stats or {}).get("tp_edge_recent_events")
        if isinstance((sltp_stats or {}).get("tp_edge_recent_events"), list)
        else analysis.get("tp_edge_recent_events")
    )
    tp_recent_samples = list(tp_recent_events or [])[-10:]
    tp_recent_by_regime: Counter[str] = Counter()
    tp_recent_by_reason: Counter[str] = Counter()
    for row in tp_recent_samples:
        if not isinstance(row, dict):
            continue
        tp_recent_by_regime[str(row.get("regime") or "unknown")] += 1
        tp_recent_by_reason[str(row.get("reason") or "unknown")] += 1
    tp_recent_top_regimes = [{"regime": k, "count": int(v)} for k, v in tp_recent_by_regime.most_common(5)]
    tp_recent_top_reasons = [{"reason": k, "count": int(v)} for k, v in tp_recent_by_reason.most_common(5)]
    advisory_symbol_counts: Counter[str] = Counter()
    advisory_recent_samples: List[Dict[str, Any]] = []
    for row in recent_advisory_rows:
        symbol = str(row.get("symbol") or "unknown")
        advisory_symbol_counts[symbol] += 1
        if len(advisory_recent_samples) < 10:
            extras = row.get("extras") if isinstance(row.get("extras"), dict) else {}
            advisory_recent_samples.append(
                {
                    "ts": row.get("ts"),
                    "symbol": symbol,
                    "side": row.get("side"),
                    "confidence": row.get("confidence"),
                    "entry_price": row.get("entry_price"),
                    "regime": str(extras.get("regime") or "unknown"),
                }
            )
    advisory_top_symbols = [{"symbol": k, "count": int(v)} for k, v in advisory_symbol_counts.most_common(5)]

    realized_perf = {
        "best_regime": best_regime,
        "worst_regime": worst_regime,
        "equity": _safe_float(analysis.get("equity")),
        "position_count": _safe_int(analysis.get("position_count", 0)),
        "latest_trade": latest_trade,
    }
    live_position_count = await _get_live_position_count(mc)
    live_active_orders = await _get_live_sltp_active_order_count(mc)
    gateway_equity = _safe_float(analysis.get("equity"))
    if gateway_equity <= 0:
        gateway_equity = await _get_live_equity(mc)

    monitoring_gap = {
        "monitoring_total_trades": _safe_int(monitor_summary.get("total_trades", 0)) if isinstance(monitor_summary, dict) else 0,
        "strategy_perf_sources": len((monitor_summary.get("strategies") or [])) if isinstance(monitor_summary, dict) else 0,
        "latest_trade_present_in_runtime_watch": bool(watch_fresh and isinstance(analysis.get("latest_trade"), dict) and analysis.get("latest_trade")),
        "runtime_watch_fresh": watch_fresh,
        "runtime_watch_age_seconds": watch_snapshot.get("age_seconds"),
    }

    optimization_hints: List[Dict[str, Any]] = []
    if not watch_fresh:
        optimization_hints.append(
            {
                "priority": "high",
                "area": "trade_analytics_freshness",
                "issue": "runtime_watch 快照已经过期，闭环摘要已切到真实成交回退口径",
                "evidence": {
                    "runtime_watch_age_seconds": watch_snapshot.get("age_seconds"),
                    "runtime_watch_last_modified": watch_snapshot.get("last_modified"),
                    "fallback_source": live_trade_context.get("source"),
                },
                "recommendation": "恢复 realtime_watch 刷新后再观察其增量价值；在此之前，以 trade_history_service 与 live 风控口径为准。",
            }
        )
    if monitoring_gap["monitoring_total_trades"] == 0 and latest_trade:
        optimization_hints.append(
            {
                "priority": "high",
                "area": "observability",
                "issue": "监控口径未接入真实成交闭环",
                "evidence": {
                    "monitoring_total_trades": monitoring_gap["monitoring_total_trades"],
                    "runtime_latest_trade_id": latest_trade.get("trade_id"),
                },
                "recommendation": "将 runtime_watch / 历史成交源回填到 monitoring_api 的 trades/strategies 汇总，避免收益面板空白。",
            }
        )
    if worst_regime and _safe_float(worst_regime.get("total_pnl")) < 0:
        optimization_hints.append(
            {
                "priority": "high",
                "area": "strategy_regime",
                "issue": "波动 regime 持续亏损",
                "evidence": {
                    "regime": worst_regime.get("regime"),
                    "total_trades": _safe_int(worst_regime.get("total_trades", 0)),
                    "win_rate": _safe_float(worst_regime.get("win_rate")),
                    "total_pnl": _safe_float(worst_regime.get("total_pnl")),
                    "expectancy": _safe_float(worst_regime.get("expectancy")),
                },
                "recommendation": "对 volatile regime 降杠杆/降仓位，或直接切换到 advisory-only，直到该 regime 的 expectancy 回正。",
            }
        )
    if opportunities_blocked["regime_advisory_only_rejected"] > 0:
        optimization_hints.append(
            {
                "priority": "medium",
                "area": "execution_guard",
                "issue": "volatile regime 已进入 advisory-only 拦截",
                "evidence": {
                    "regime_advisory_only_rejected": opportunities_blocked["regime_advisory_only_rejected"],
                    "top_symbols": advisory_top_symbols,
                },
                "recommendation": "继续观察被拦截样本是否集中在 volatile；若后续 expectancy 回正，再逐步恢复小仓试单。",
            }
        )
    tp_recent_suppressed = len(tp_recent_samples)
    if tp_recent_suppressed >= 10:
        top_regime = tp_recent_top_regimes[0] if tp_recent_top_regimes else {}
        optimization_hints.append(
            {
                "priority": "medium",
                "area": "exit_logic",
                "issue": "近期止盈净收益门槛抑制次数偏高",
                "evidence": {
                    "recent_window_count": tp_recent_suppressed,
                    "top_regimes": tp_recent_top_regimes,
                    "top_reasons": tp_recent_top_reasons,
                    "lifetime_total": opportunities_blocked["tp_net_edge_suppressed"],
                },
                "recommendation": (
                    f"优先复核 {top_regime.get('regime', 'top regime')} 的 TP 分层和 min_net 阈值，"
                    "避免小盈利长期无法兑现，资金占用过久。"
                ),
            }
        )
    if best_regime and worst_regime and str(best_regime.get("regime")) != str(worst_regime.get("regime")):
        optimization_hints.append(
            {
                "priority": "medium",
                "area": "capital_allocation",
                "issue": "不同 regime 收益差异大",
                "evidence": {
                    "best_regime": {
                        "name": best_regime.get("regime"),
                        "pnl": _safe_float(best_regime.get("total_pnl")),
                        "win_rate": _safe_float(best_regime.get("win_rate")),
                    },
                    "worst_regime": {
                        "name": worst_regime.get("regime"),
                        "pnl": _safe_float(worst_regime.get("total_pnl")),
                        "win_rate": _safe_float(worst_regime.get("win_rate")),
                    },
                },
                "recommendation": "把仓位和开仓预算向正 expectancy regime 倾斜，负 expectancy regime 只保留试探仓。",
            }
        )
    if hold_fallback_count >= 3:
        optimization_hints.append(
            {
                "priority": "high",
                "area": "llm_availability",
                "issue": "部分 hold 由 LLM 不可用回退触发",
                "evidence": {
                    "fallback_hold_count": hold_fallback_count,
                    "fallback_hold_ratio": round(hold_fallback_ratio, 4),
                    "hold_total": hold_total,
                    "top_fallback_reasons": top_fallback_reasons[:5],
                    "top_fallback_models": top_fallback_models[:5],
                    "top_hold_strategies": top_hold_strategies[:5],
                },
                "recommendation": "优先排查 LLM 可用性、超时和 provider 降级，否则会把系统性 fallback 误判成策略过于保守。",
            }
        )
    if llm_diag.get("active_circuit_breaks"):
        top_break = (llm_diag.get("active_circuit_breaks") or [{}])[0]
        optimization_hints.append(
            {
                "priority": "high",
                "area": "llm_routing",
                "issue": "决策模型存在活跃熔断",
                "evidence": {
                    "default_model": llm_diag.get("default_model"),
                    "decision_model_order": llm_diag.get("decision_model_order"),
                    "active_circuit_breaks": llm_diag.get("active_circuit_breaks"),
                },
                "recommendation": (
                    f"优先处理 {top_break.get('model_id', 'primary model')} 的连通性；"
                    "若短期内仍频繁熔断，可把 decision_making 前置到更稳的模型。"
                ),
            }
        )
    if _safe_int(recon_summary.get("drift_total", 0)) > 0:
        optimization_hints.append(
            {
                "priority": "high",
                "area": "execution_reconciliation",
                "issue": "本地与交易所持仓存在漂移",
                "evidence": {"reconciliation": recon_summary},
                "recommendation": "先修正持仓漂移，再谈收益优化，否则收益统计和止盈止损判断都不可信。",
            }
        )
    top_stage = workflow_focus.get("top_stage") if isinstance(workflow_focus, dict) else None
    top_status = workflow_focus.get("top_status") if isinstance(workflow_focus, dict) else None
    if (
        isinstance(top_stage, dict)
        and str(top_stage.get("key") or "") == "reconciliation"
        and isinstance(top_status, dict)
        and str(top_status.get("key") or "") in {"blocked", "reconcile_blocked"}
    ):
        optimization_hints.append(
            {
                "priority": "high",
                "area": "execution_workflow",
                "issue": "近期决策主要卡在 reconciliation 阶段",
                "evidence": {
                    "top_workflow_stage": top_stage,
                    "top_workflow_status": top_status,
                    "decision_trace_summary": summary,
                },
                "recommendation": "优先修复持仓同步、孤儿订单和对账保护触发根因，再调整策略阈值。",
            }
        )
    running_modules = _safe_int(analysis.get("running_modules", 0))
    if running_modules <= 0 and hasattr(mc, "get_system_status"):
        try:
            sys_status = await mc.get_system_status()
            if isinstance(sys_status, dict):
                running_modules = _safe_int(sys_status.get("running_modules", 0))
        except Exception:
            running_modules = 0

    return {
        "runtime_watch": {
            "available": bool(watch_snapshot.get("available")),
            "fresh": watch_fresh,
            "age_seconds": watch_snapshot.get("age_seconds"),
            "last_modified": watch_snapshot.get("last_modified"),
            "stale_after_seconds": watch_snapshot.get("stale_after_seconds"),
            "fallback_source": live_trade_context.get("source"),
        },
        "loop_health": {
            "verdict": analysis.get("verdict") or ("PASS" if _safe_int(recon_summary.get("drift_total", 0)) == 0 else "WARN"),
            "risk_level": analysis.get("risk_level") or ("low" if _safe_int(recon_summary.get("drift_total", 0)) == 0 else "medium"),
            "running_modules": running_modules,
            "active_alerts": _safe_int(analysis.get("active_alerts", monitor_summary.get("active_alerts", 0))),
            "active_orders": live_active_orders,
            "position_count": live_position_count,
            "equity": gateway_equity,
            "source": {
                "active_orders": "stop_loss_manager.get_all_active_orders",
                "position_count": "exchange.get_positions",
                "equity": "runtime_watch_or_exchange_balance",
            },
        },
        "agent_effectiveness": await _build_agent_effectiveness_summary(
            mc,
            trace_limit=int(trace_limit or 120),
            trade_limit=max(200, int(trace_limit or 120) * 4),
        ),
        "signal_and_guard": {
            "decision_traces_summary": summary,
            "workflow_focus": workflow_focus,
            "top_reject_reasons": top_reject_reasons,
            "top_reject_symbols": top_reject_symbols,
            "top_reject_stages": top_reject_stages,
            "hold_diagnostics": {
                "top_tags": top_hold_tags,
                "top_symbols": top_hold_symbols,
                "top_regimes": top_hold_regimes,
                "top_strategies": top_hold_strategies,
                "top_fallback_reasons": top_fallback_reasons,
                "top_fallback_models": top_fallback_models,
                "fallback_hold_count": hold_fallback_count,
                "fallback_hold_ratio": round(hold_fallback_ratio, 4),
                "hold_total": hold_total,
                "recent_samples": hold_recent_samples,
            },
            "current_symbol_bias": symbol_summaries,
        },
        "execution_and_reconciliation": {
            "policy_metrics": policy_metrics,
            "reconciliation_summary": recon_summary,
        },
        "exit_and_profitability": {
            "realized_performance": realized_perf,
            "opportunity_blocks": opportunities_blocked,
            "regime_advisory_only": {
                "top_symbols": advisory_top_symbols,
                "recent_samples": advisory_recent_samples,
            },
            "tp_edge_suppression": {
                "recent_window_count": tp_recent_suppressed,
                "recent_by_regime": dict(tp_recent_by_regime),
                "recent_by_reason": dict(tp_recent_by_reason),
                "recent_top_regimes": tp_recent_top_regimes,
                "recent_top_reasons": tp_recent_top_reasons,
                "lifetime_total": opportunities_blocked["tp_net_edge_suppressed"],
                "by_regime": tp_suppressed_by_regime,
                "by_reason": tp_suppressed_by_reason,
                "top_regimes": tp_top_regimes,
                "top_reasons": tp_top_reasons,
                "recent_samples": tp_recent_samples,
            },
        },
        "llm_diagnostics": llm_diag,
        "observability_gaps": monitoring_gap,
        "optimization_hints": optimization_hints,
    }


async def _build_system_mastery_snapshot(
    main_controller: Any,
    *,
    symbol: str = "BTC/USDT",
    trace_limit: int = 120,
    trade_limit: int = 300,
    recent_trades_limit: int = 20,
) -> Dict[str, Any]:
    mc = main_controller
    closed_loop = await _build_closed_loop_summary_data(mc, trace_limit=int(trace_limit or 120))
    trade_lifecycle = await _build_trade_lifecycle_summary(
        mc,
        trade_limit=int(trade_limit or 300),
        recent_limit=int(recent_trades_limit or 20),
    )

    system_status: Dict[str, Any] = {}
    if mc and hasattr(mc, "get_system_status"):
        try:
            system_status = await mc.get_system_status()
        except Exception as e:
            system_status = {"error": str(e)}

    commander_snapshot: Dict[str, Any] = {}
    if mc and hasattr(mc, "build_ai_commander_snapshot"):
        try:
            commander_snapshot = await asyncio.wait_for(mc.build_ai_commander_snapshot(symbol=symbol), timeout=8.0)
        except Exception as e:
            commander_snapshot = {"error": str(e)}

    unified_market_snapshot: Dict[str, Any] = {}
    hub = getattr(mc, "data_source_hub", None) if mc else None
    if hub and hasattr(hub, "get_unified_snapshot"):
        try:
            unified_market_snapshot = await asyncio.wait_for(hub.get_unified_snapshot(symbol), timeout=6.0)
        except Exception as e:
            unified_market_snapshot = {"error": str(e)}

    learning_status: Dict[str, Any] = {}
    le = getattr(mc, "ai_learning_engine", None) if mc else None
    if le and hasattr(le, "get_status"):
        try:
            learning_status = le.get_status()
        except Exception as e:
            learning_status = {"error": str(e)}

    hold_diag = (((closed_loop.get("signal_and_guard") or {}).get("hold_diagnostics") or {}) if isinstance(closed_loop, dict) else {})
    workflow_focus = (((closed_loop.get("signal_and_guard") or {}).get("workflow_focus") or {}) if isinstance(closed_loop, dict) else {})
    trade_summary = (trade_lifecycle.get("summary") or {}) if isinstance(trade_lifecycle, dict) else {}
    loop_health = (closed_loop.get("loop_health") or {}) if isinstance(closed_loop, dict) else {}
    top_stage = workflow_focus.get("top_stage") if isinstance(workflow_focus, dict) else None
    top_status = workflow_focus.get("top_status") if isinstance(workflow_focus, dict) else None

    coverage_gaps: List[Dict[str, Any]] = []
    if not trade_summary.get("trace_linked_rows"):
        coverage_gaps.append(
            {
                "id": "trade_trace_linkage",
                "status": "missing_or_weak",
                "message": "成交与决策 trace_id 关联不足，无法稳定评估开仓判断到平仓结果的全链路表现。",
            }
        )
    coverage_gaps.append(
        {
            "id": "rejected_signal_followthrough",
            "status": "not_fully_persisted",
            "message": "拒单后行情走势的逐笔跟踪尚未形成稳定持久化字段；当前只能看到拒单原因，不能完整复盘其后走势合理性。",
        }
    )
    coverage_gaps.append(
        {
            "id": "exit_timing_quality",
            "status": "partial",
            "message": "当前已能看到平仓原因与收益，但“是否过早/过晚”仍主要依赖 reason/TP 抑制统计，缺少统一的时机评分。",
        }
    )

    return {
        "interface": {
            "name": "commander.system_mastery",
            "version": "2026.05.16",
            "transport": "http_json",
            "path": "/api/v1/modules/commander/system-mastery",
            "purpose": "单接口掌握系统状态、交易闭环、故障、学习与优化证据。",
        },
        "query": {
            "symbol": symbol,
            "trace_limit": int(trace_limit or 120),
            "trade_limit": int(trade_limit or 300),
            "recent_trades_limit": int(recent_trades_limit or 20),
        },
        "overview": {
            "loop_verdict": loop_health.get("verdict"),
            "risk_level": loop_health.get("risk_level"),
            "equity": loop_health.get("equity"),
            "active_orders": loop_health.get("active_orders"),
            "position_count": loop_health.get("position_count"),
            "recent_net_pnl_plus_fees": trade_summary.get("net_pnl_plus_fees"),
            "recent_win_rate": trade_summary.get("win_rate"),
            "top_hold_tag": ((hold_diag.get("top_tags") or [{}])[0] if isinstance(hold_diag.get("top_tags"), list) and hold_diag.get("top_tags") else None),
            "top_workflow_stage": top_stage,
            "top_workflow_status": top_status,
        },
        "system_runtime": system_status,
        "market_and_account": {
            "symbol": symbol,
            "commander_snapshot": commander_snapshot,
            "unified_market_snapshot": unified_market_snapshot,
        },
        "decision_execution_loop": closed_loop,
        "trade_lifecycle": trade_lifecycle,
        "learning_and_optimization": {
            "learning_status": learning_status,
            "optimization_hints": closed_loop.get("optimization_hints", []) if isinstance(closed_loop, dict) else [],
        },
        "coverage_gaps": coverage_gaps,
    }


def _parse_trade_timestamp_utc(raw: Any) -> Optional[datetime]:
    try:
        if not raw:
            return None
        s = str(raw)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        ts = datetime.fromisoformat(s)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    except Exception:
        return None


def _trade_gateway_context(row: Dict[str, Any]) -> Dict[str, Any]:
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    gw = md.get("gateway") if isinstance(md.get("gateway"), dict) else {}
    ctx = gw.get("context") if isinstance(gw.get("context"), dict) else {}
    return {"metadata": md, "gateway": gw, "context": ctx}


def _trade_operation(row: Dict[str, Any]) -> str:
    g = _trade_gateway_context(row)
    return str(row.get("trade_phase") or row.get("action") or g["gateway"].get("op") or "").strip().lower() or "unknown"


def _trade_source(row: Dict[str, Any]) -> str:
    g = _trade_gateway_context(row)
    return str(row.get("source") or g["gateway"].get("source") or "unknown").strip() or "unknown"


def _trade_reason(row: Dict[str, Any]) -> str:
    g = _trade_gateway_context(row)
    return str(row.get("reasoning") or g["gateway"].get("reason") or "unknown").strip() or "unknown"


def _trade_strategy(row: Dict[str, Any]) -> str:
    g = _trade_gateway_context(row)
    return str(
        row.get("strategy")
        or row.get("strategy_id")
        or g["context"].get("strategy_used")
        or g["context"].get("strategy_id")
        or "unknown"
    ).strip() or "unknown"


def _trade_regime(row: Dict[str, Any]) -> str:
    g = _trade_gateway_context(row)
    md = g["metadata"]
    ctx = g["context"]
    mcx = md.get("market_context") if isinstance(md.get("market_context"), dict) else {}
    semantic = md.get("semantic_context") if isinstance(md.get("semantic_context"), dict) else {}
    gp = ctx.get("guard_profile") if isinstance(ctx.get("guard_profile"), dict) else {}
    sem = ctx.get("semantic_context") if isinstance(ctx.get("semantic_context"), dict) else {}
    return str(
        mcx.get("regime")
        or semantic.get("regime_label")
        or semantic.get("regime")
        or gp.get("regime")
        or sem.get("regime_label")
        or sem.get("regime")
        or "unknown"
    ).strip() or "unknown"


def _norm_trade_symbol(symbol: Any) -> str:
    return str(symbol or "unknown").replace("/SWAP", "").strip() or "unknown"


def _is_placeholder_strategy_name(name: Any) -> bool:
    return str(name or "").strip().lower() in _PLACEHOLDER_STRATEGY_NAMES


def _is_low_fidelity_historical_trade_row(row: Dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    g = _trade_gateway_context(row)
    md = g["metadata"]
    gw = g["gateway"]
    ctx = g["context"]
    source = str(row.get("source") or md.get("source") or "").strip().lower()
    if source not in {"historical_db", "legacy"}:
        return False
    if not _is_placeholder_strategy_name(_trade_strategy(row)):
        return False
    if _extract_trade_trace_id(row):
        return False
    if str(row.get("reasoning") or "").strip():
        return False
    if gw or ctx:
        return False
    if any(
        md.get(key)
        for key in ("market_context", "semantic_context", "open_timestamp", "close_timestamp", "raw", "regime_label")
    ):
        return False
    return True


def _infer_regime_from_trade_row(row: Dict[str, Any]) -> Dict[str, Any]:
    direct = str(_trade_regime(row) or "").strip().lower()
    if direct and direct != "unknown":
        return {"regime": direct, "inferred": False}
    strategy = str(_trade_strategy(row) or "").strip().lower()
    reasoning = str(_trade_reason(row) or "").strip().lower()
    text = f"{strategy} {reasoning}"
    if any(k in text for k in ("trend", "breakout", "momentum", "bull", "bear", "moving_average", "_ma")):
        return {"regime": "trend", "inferred": True}
    if any(k in text for k in ("support", "resistance", "mean_reversion", "bollinger", "sr_near")):
        return {"regime": "range", "inferred": True}
    if any(k in text for k in ("stop_loss", "volatility", "spike", "liq", "liquidity_stress")):
        return {"regime": "volatile", "inferred": True}
    return {"regime": "unknown", "inferred": False}


def _compact_trade_row(row: Dict[str, Any]) -> Dict[str, Any]:
    g = _trade_gateway_context(row)
    ctx = g["context"]
    return {
        "timestamp": row.get("timestamp"),
        "symbol": row.get("symbol"),
        "operation": _trade_operation(row),
        "side": row.get("side"),
        "quantity": _safe_float(row.get("quantity")),
        "price": _safe_float(row.get("price")),
        "pnl": _safe_float(row.get("pnl")),
        "fee": _safe_float(row.get("fee")),
        "net": round(_safe_float(row.get("pnl")) + _safe_float(row.get("fee")), 6),
        "strategy": _trade_strategy(row),
        "source": _trade_source(row),
        "reason": _trade_reason(row),
        "regime": _trade_regime(row),
        "leverage": row.get("leverage"),
        "trace_id": _extract_trade_trace_id(row) or None,
        "decision_reasoning_excerpt": str(ctx.get("decision_reasoning") or "")[:360],
    }


async def _load_recent_trade_rows_for_window(
    main_controller: Any,
    *,
    start_utc: datetime,
    end_utc: datetime,
    limit: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set = set()

    def _add(row: Dict[str, Any]) -> None:
        if not isinstance(row, dict):
            return
        ts = _parse_trade_timestamp_utc(row.get("timestamp"))
        if not ts or ts < start_utc or ts > end_utc:
            return
        key = str(row.get("trade_id") or row.get("order_id") or f"{row.get('timestamp')}|{row.get('symbol')}|{row.get('side')}|{row.get('quantity')}|{row.get('price')}")
        if key in seen:
            return
        seen.add(key)
        rows.append(row)

    ths = getattr(main_controller, "trade_history_service", None) if main_controller else None
    if ths and hasattr(ths, "get_trade_history"):
        try:
            got = await ths.get_trade_history(start_date=start_utc, end_date=end_utc, limit=max(1, int(limit or 1000)))
            for row in got or []:
                _add(row)
        except Exception:
            pass

    # Fallback to the durable JSONL file. Some service caches are loaded in ascending windows;
    # this guarantees recent-order attribution sees the same facts as the audit trail.
    try:
        fp = Path(__file__).resolve().parents[3] / "data" / "trade_history" / "trades.jsonl"
        if fp.is_file():
            for line in fp.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    _add(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass

    rows.sort(key=lambda r: str(r.get("timestamp") or ""))
    return rows[-max(1, int(limit or 1000)) :]


async def _build_recent_order_attribution(
    main_controller: Any,
    *,
    hours: float = 4.0,
    limit: int = 1000,
) -> Dict[str, Any]:
    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(hours=max(0.25, min(float(hours or 4.0), 168.0)))
    rows = await _load_recent_trade_rows_for_window(
        main_controller,
        start_utc=start_utc,
        end_utc=end_utc,
        limit=max(50, int(limit or 1000)),
    )

    def _bucket() -> Dict[str, Any]:
        return {
            "rows": 0,
            "opens": 0,
            "closes": 0,
            "pnl": 0.0,
            "fees": 0.0,
            "net": 0.0,
            "wins": 0,
            "losses": 0,
            "notional": 0.0,
        }

    buckets: Dict[str, Dict[str, Dict[str, Any]]] = {
        "by_source": defaultdict(_bucket),
        "by_strategy": defaultdict(_bucket),
        "by_symbol": defaultdict(_bucket),
        "by_regime": defaultdict(_bucket),
        "by_open_reason": defaultdict(_bucket),
        "by_close_reason": defaultdict(_bucket),
    }
    summary = _bucket()
    recent_orders: List[Dict[str, Any]] = []

    for row in rows:
        op = _trade_operation(row)
        pnl = _safe_float(row.get("pnl"))
        fee = _safe_float(row.get("fee"))
        raw = (row.get("metadata") or {}).get("raw") if isinstance(row.get("metadata"), dict) else {}
        notional = _safe_float((raw or {}).get("notional_usdt_est")) if isinstance(raw, dict) else 0.0
        if notional <= 0:
            notional = abs(_safe_float(row.get("price")) * _safe_float(row.get("quantity")))

        def _acc(name: str, key: str) -> None:
            b = buckets[name][key or "unknown"]
            b["rows"] += 1
            b["opens"] += int(op == "open")
            b["closes"] += int(op == "close")
            b["pnl"] += pnl
            b["fees"] += fee
            b["net"] += pnl + fee
            b["wins"] += int(op == "close" and pnl > 0)
            b["losses"] += int(op == "close" and pnl < 0)
            b["notional"] += notional

        summary["rows"] += 1
        summary["opens"] += int(op == "open")
        summary["closes"] += int(op == "close")
        summary["pnl"] += pnl
        summary["fees"] += fee
        summary["net"] += pnl + fee
        summary["wins"] += int(op == "close" and pnl > 0)
        summary["losses"] += int(op == "close" and pnl < 0)
        summary["notional"] += notional

        _acc("by_source", _trade_source(row))
        _acc("by_strategy", _trade_strategy(row))
        _acc("by_symbol", _norm_trade_symbol(row.get("symbol")))
        _acc("by_regime", _trade_regime(row))
        if op == "open":
            _acc("by_open_reason", _trade_reason(row))
        elif op == "close":
            _acc("by_close_reason", _trade_reason(row))
        recent_orders.append(_compact_trade_row(row))

    def _finalize_map(mp: Dict[str, Dict[str, Any]], key_name: str) -> List[Dict[str, Any]]:
        out = []
        for key, val in mp.items():
            row = {key_name: key}
            row.update(
                {
                    k: (round(v, 6) if isinstance(v, float) else v)
                    for k, v in val.items()
                }
            )
            row["close_win_rate"] = round(float(val["wins"]) / float(val["closes"]), 4) if int(val["closes"]) > 0 else 0.0
            out.append(row)
        return sorted(out, key=lambda x: _safe_float(x.get("net")), reverse=True)

    summary_out = {
        k: (round(v, 6) if isinstance(v, float) else v)
        for k, v in summary.items()
    }
    summary_out["close_win_rate"] = round(float(summary["wins"]) / float(summary["closes"]), 4) if int(summary["closes"]) > 0 else 0.0
    summary_out["open_fee_drag"] = round(sum(_safe_float(r.get("fee")) for r in rows if _trade_operation(r) == "open"), 6)
    summary_out["close_net"] = round(sum(_safe_float(r.get("pnl")) + _safe_float(r.get("fee")) for r in rows if _trade_operation(r) == "close"), 6)

    optimization_targets: List[Dict[str, Any]] = []
    by_symbol = _finalize_map(buckets["by_symbol"], "symbol")
    by_strategy = _finalize_map(buckets["by_strategy"], "strategy")
    by_close_reason = _finalize_map(buckets["by_close_reason"], "close_reason")
    worst_open_symbols = [x for x in by_symbol if int(x.get("opens") or 0) > 0 and _safe_float(x.get("net")) < 0][:5]
    tiny_tp = [
        x for x in by_close_reason
        if str(x.get("close_reason") or "").lower() in {"take_profit", "partial_take_profit", "sr_near_resistance_partial_take_profit", "sr_near_support_partial_take_profit"}
        and _safe_float(x.get("net")) <= 0
    ]
    if worst_open_symbols:
        optimization_targets.append(
            {
                "area": "entry_sizing_and_adds",
                "priority": "high",
                "issue": "recent opens are fee-negative and still carrying risk",
                "evidence": worst_open_symbols,
                "suggestion": "按 symbol+side 增加连续加仓冷却；只有浮盈或趋势二次确认后允许加仓。",
            }
        )
    if tiny_tp:
        optimization_targets.append(
            {
                "area": "exit_min_net_profit",
                "priority": "medium",
                "issue": "take-profit exists but net after fees is non-positive",
                "evidence": tiny_tp,
                "suggestion": "按 symbol/notional 提高最小净止盈检查，避免手续费型假盈利。",
            }
        )
    if any(x.get("strategy") == "default_trend_following_ma" and _safe_float(x.get("net")) < 0 and int(x.get("opens") or 0) >= 3 for x in by_strategy):
        optimization_targets.append(
            {
                "area": "strategy_entry_logic",
                "priority": "medium",
                "issue": "trend strategy opened multiple positions without realized exits in the window",
                "evidence": [x for x in by_strategy if x.get("strategy") == "default_trend_following_ma"][:1],
                "suggestion": "趋势策略增加未平仓风险预算和同向加仓间隔，避免单策略快速堆仓。",
            }
        )

    return {
        "window": {
            "hours": round(float(hours or 4.0), 4),
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
        },
        "summary": summary_out,
        "source_attribution": _finalize_map(buckets["by_source"], "source"),
        "strategy_attribution": by_strategy,
        "symbol_attribution": by_symbol,
        "regime_attribution": _finalize_map(buckets["by_regime"], "regime"),
        "open_logic": _finalize_map(buckets["by_open_reason"], "open_reason"),
        "close_logic": by_close_reason,
        "recent_orders": recent_orders[-80:],
        "optimization_targets": optimization_targets,
    }


async def _build_trading_workflow_report(
    main_controller: Any,
    *,
    symbol: str = "BTC/USDT",
    trace_limit: int = 200,
    trade_limit: int = 1000,
    recent_trades_limit: int = 40,
    recent_order_hours: float = 4.0,
) -> Dict[str, Any]:
    """Compact read model for the full trading workflow and optimization loop."""
    mc = main_controller
    closed_loop = await _build_closed_loop_summary_data(mc, trace_limit=int(trace_limit or 200))
    trade_lifecycle = await _build_trade_lifecycle_summary(
        mc,
        trade_limit=int(trade_limit or 1000),
        recent_limit=int(recent_trades_limit or 40),
    )

    system_status: Dict[str, Any] = {}
    if mc and hasattr(mc, "get_system_status"):
        try:
            system_status = await mc.get_system_status()
        except Exception as e:
            system_status = {"error": str(e)}

    positions: List[Dict[str, Any]] = []
    try:
        ex = mc.get_exchange() if hasattr(mc, "get_exchange") else getattr(mc, "okx_exchange", None)
        if ex and hasattr(ex, "get_positions"):
            raw_positions = await ex.get_positions()
            for row in raw_positions or []:
                if not isinstance(row, dict):
                    continue
                size = _safe_float(row.get("size") or row.get("pos") or row.get("positionAmt"))
                if abs(size) <= 1e-12:
                    continue
                positions.append(
                    {
                        "symbol": row.get("symbol") or row.get("instId"),
                        "side": row.get("side") or row.get("posSide"),
                        "size": size,
                        "entry_price": _safe_float(row.get("entry_price") or row.get("avgPx") or row.get("entryPrice")),
                        "mark_price": _safe_float(row.get("mark_px") or row.get("mark_price") or row.get("markPx")),
                        "unrealized_pnl": _safe_float(row.get("unrealized_pnl") or row.get("upl") or row.get("unrealizedPnl")),
                        "notional_value": _safe_float(row.get("notional_value") or row.get("notionalUsd") or row.get("notional")),
                        "leverage": _safe_float(row.get("leverage") or row.get("lever")),
                    }
                )
    except Exception:
        positions = []

    active_sltp_orders: List[Dict[str, Any]] = []
    try:
        sltp = getattr(mc, "stop_loss_manager", None)
        if sltp and hasattr(sltp, "get_all_active_orders"):
            for order in await sltp.get_all_active_orders():
                if hasattr(order, "to_dict"):
                    row = order.to_dict()
                elif isinstance(order, dict):
                    row = order
                else:
                    row = {}
                active_sltp_orders.append(
                    {
                        "order_id": row.get("order_id"),
                        "symbol": row.get("symbol"),
                        "side": row.get("side"),
                        "entry_price": row.get("entry_price"),
                        "remaining_quantity": row.get("remaining_quantity") or row.get("quantity"),
                        "stop_loss_price": row.get("stop_loss_price"),
                        "take_profit_price": row.get("take_profit_price"),
                        "trailing_stop_activated": row.get("trailing_stop_activated"),
                        "breakeven_activated": row.get("breakeven_activated"),
                        "status": row.get("status"),
                    }
                )
    except Exception:
        active_sltp_orders = []

    market_snapshot: Dict[str, Any] = {}
    try:
        hub = getattr(mc, "data_source_hub", None)
        if hub and hasattr(hub, "get_unified_snapshot"):
            market_snapshot = await asyncio.wait_for(hub.get_unified_snapshot(symbol), timeout=20.0)
    except Exception as e:
        market_snapshot = {"symbol": symbol, "degraded": True, "error": repr(e)}

    gateway_snapshot: Dict[str, Any] = {}
    recent_events: List[Dict[str, Any]] = []
    try:
        gw = getattr(mc, "execution_gateway", None)
        if gw and hasattr(gw, "get_snapshot"):
            gateway_snapshot = await gw.get_snapshot()
        if gw and hasattr(gw, "get_recent_events"):
            recent_events = await gw.get_recent_events(limit=40)
    except Exception:
        gateway_snapshot = {}
        recent_events = []

    compact_events: List[Dict[str, Any]] = []
    for evt in recent_events[-40:]:
        if not isinstance(evt, dict):
            continue
        ctx = evt.get("context") if isinstance(evt.get("context"), dict) else {}
        compact_events.append(
            {
                "ts": evt.get("ts"),
                "op": evt.get("op"),
                "symbol": evt.get("symbol"),
                "side": evt.get("side"),
                "size": evt.get("size"),
                "leverage": evt.get("leverage"),
                "source": evt.get("source"),
                "reason": evt.get("reason"),
                "success": evt.get("success"),
                "error_code": evt.get("error_code"),
                "detail": str(evt.get("detail") or "")[:220],
                "trace_id": evt.get("trace_id"),
                "strategy_used": ctx.get("strategy_used") or ctx.get("strategy_id"),
                "decision_reasoning": str(ctx.get("decision_reasoning") or "")[:360],
                "sltp_reason": ctx.get("sltp_reason"),
                "trigger_pnl_percent": ctx.get("trigger_pnl_percent"),
            }
        )

    recent_order_attribution = await _build_recent_order_attribution(
        mc,
        hours=float(recent_order_hours or 4.0),
        limit=max(200, int(trade_limit or 1000)),
    )

    signal_guard = closed_loop.get("signal_and_guard") if isinstance(closed_loop, dict) else {}
    exit_profit = closed_loop.get("exit_and_profitability") if isinstance(closed_loop, dict) else {}
    optimization_hints = closed_loop.get("optimization_hints", []) if isinstance(closed_loop, dict) else []
    agent_effectiveness = closed_loop.get("agent_effectiveness", {}) if isinstance(closed_loop, dict) else {}
    trade_summary = trade_lifecycle.get("summary", {}) if isinstance(trade_lifecycle, dict) else {}
    close_reason_top = trade_lifecycle.get("close_reason_top", []) if isinstance(trade_lifecycle, dict) else []
    opportunity_blocks = (exit_profit.get("opportunity_blocks") or {}) if isinstance(exit_profit, dict) else {}
    realized_perf = (exit_profit.get("realized_performance") or {}) if isinstance(exit_profit, dict) else {}
    decision_summary = signal_guard.get("decision_traces_summary") if isinstance(signal_guard, dict) else {}
    agent_summary = agent_effectiveness.get("summary") if isinstance(agent_effectiveness, dict) else {}
    trace_sample_size = _safe_int(decision_summary.get("sample_size"))
    trade_sample_size = _safe_int(trade_summary.get("sample_size"))
    trace_linked_rows = _safe_int(trade_summary.get("trace_linked_rows"))
    trace_linkage_ratio = round(float(trace_linked_rows) / float(trade_sample_size), 4) if trade_sample_size > 0 else 0.0
    guard_rejected = _safe_int(decision_summary.get("guard_rejected"))
    guard_passed = _safe_int(decision_summary.get("guard_passed"))
    decision_total = guard_rejected + guard_passed
    guard_pass_rate = round(float(guard_passed) / float(decision_total), 4) if decision_total > 0 else 0.0
    exec_events = [e for e in compact_events if str(e.get("op") or "").lower() in {"open", "close"}]
    exec_success = len([e for e in exec_events if e.get("success") is True])
    execution_success_ratio = round(float(exec_success) / float(len(exec_events)), 4) if exec_events else 1.0
    win_rate = _safe_float(trade_summary.get("win_rate"))
    net_pnl = _safe_float(trade_summary.get("net_pnl_plus_fees"))
    agent_coverage_ratio = _safe_float((agent_summary or {}).get("agent_trace_coverage_ratio"))
    tp_suppressed = _safe_int(opportunity_blocks.get("tp_net_edge_suppressed"))
    tp_suppression_per_trade = round(float(tp_suppressed) / float(trade_sample_size), 4) if trade_sample_size > 0 else 0.0

    data_quality = {}
    if isinstance(market_snapshot, dict):
        quality_block = market_snapshot.get("数据质量与作用评分") if isinstance(market_snapshot.get("数据质量与作用评分"), dict) else {}
        if not quality_block:
            quality_block = market_snapshot.get("数据质量评估") if isinstance(market_snapshot.get("数据质量评估"), dict) else {}
        data_quality = {
            "quality_score": _safe_float(quality_block.get("quality_score") or quality_block.get("score"), 0.0),
            "confidence": _safe_float(quality_block.get("confidence"), 0.0),
            "grade": quality_block.get("grade"),
            "provenance": ((market_snapshot.get("数据来源状态") or {}).get("provenance") if isinstance(market_snapshot.get("数据来源状态"), dict) else None),
            "degraded": bool(market_snapshot.get("degraded") or market_snapshot.get("error")),
        }

    workflow_actions: List[Dict[str, Any]] = []
    worst_regime = realized_perf.get("worst_regime") if isinstance(realized_perf, dict) else {}
    if isinstance(worst_regime, dict) and _safe_float(worst_regime.get("total_pnl")) < 0:
        workflow_actions.append(
            {
                "priority": "high",
                "area": "entry_regime_filter",
                "action": "keep_volatile_small_or_advisory_only",
                "reason": "volatile regime has negative expectancy",
                "evidence": {
                    "regime": worst_regime.get("regime"),
                    "expectancy": worst_regime.get("expectancy"),
                    "total_pnl": worst_regime.get("total_pnl"),
                    "win_rate": worst_regime.get("win_rate"),
                },
            }
        )
    if _safe_int(opportunity_blocks.get("tp_net_edge_suppressed")) > 500:
        workflow_actions.append(
            {
                "priority": "medium",
                "area": "exit_logic",
                "action": "review_min_net_take_profit_thresholds",
                "reason": "TP edge gate suppresses many small exits",
                "evidence": {
                    "tp_net_edge_suppressed": opportunity_blocks.get("tp_net_edge_suppressed"),
                    "tp_edge_suppression": exit_profit.get("tp_edge_suppression") if isinstance(exit_profit, dict) else {},
                },
            }
        )
    agent_summary = agent_effectiveness.get("summary") if isinstance(agent_effectiveness, dict) else {}
    if _safe_float((agent_summary or {}).get("agent_trace_coverage_ratio")) < 0.25:
        workflow_actions.append(
            {
                "priority": "high",
                "area": "agent_workflow",
                "action": "promote_4_agent_advisory_to_main_path_observation",
                "reason": "agent coverage is too low to optimize PnL causally",
                "evidence": {
                    "coverage_ratio": (agent_summary or {}).get("agent_trace_coverage_ratio"),
                    "full_stack_trace_count": (agent_summary or {}).get("full_stack_trace_count"),
                },
            }
        )
    hold_diag = (signal_guard.get("hold_diagnostics") or {}) if isinstance(signal_guard, dict) else {}
    if _safe_int(hold_diag.get("fallback_hold_count")) > 0:
        workflow_actions.append(
            {
                "priority": "medium",
                "area": "llm_routing",
                "action": "stabilize_decision_model_fallback",
                "reason": "LLM unavailable fallback is affecting hold decisions",
                "evidence": {
                    "fallback_hold_count": hold_diag.get("fallback_hold_count"),
                    "top_fallback_reasons": hold_diag.get("top_fallback_reasons"),
                },
            }
        )

    kpi_scorecard = {
        "data_quality": {
            "score": data_quality.get("quality_score"),
            "confidence": data_quality.get("confidence"),
            "grade": data_quality.get("grade"),
            "provenance": data_quality.get("provenance"),
            "status": (
                "unavailable"
                if bool(data_quality.get("degraded"))
                else ("ok" if _safe_float(data_quality.get("quality_score")) >= 0.85 else "watch")
            ),
            "why_it_matters": "数据质量低时不应放宽开仓门槛，只能降风险或补数据。",
        },
        "decision_selectivity": {
            "sample_size": trace_sample_size,
            "guard_pass_rate": guard_pass_rate,
            "guard_rejected": guard_rejected,
            "guard_passed": guard_passed,
            "status": "very_strict" if decision_total > 0 and guard_pass_rate < 0.05 else "ok",
            "why_it_matters": "开仓通过率过低时，要区分是过滤有效还是阈值过紧。",
        },
        "execution_quality": {
            "recent_event_count": len(exec_events),
            "success_ratio": execution_success_ratio,
            "reconciliation_healthy": bool(((gateway_snapshot or {}).get("reconciliation") or {}).get("healthy", False)) if isinstance((gateway_snapshot or {}).get("reconciliation"), dict) else None,
            "status": "ok" if execution_success_ratio >= 0.85 else "watch",
            "why_it_matters": "执行成功率低时优先修交易所/风控/幂等，不应先调策略参数。",
        },
        "exit_quality": {
            "trade_sample_size": trade_sample_size,
            "win_rate": win_rate,
            "net_pnl_plus_fees": net_pnl,
            "tp_suppressed": tp_suppressed,
            "tp_suppression_per_trade": tp_suppression_per_trade,
            "status": "profitable_but_tp_constrained" if net_pnl > 0 and tp_suppression_per_trade > 0.5 else ("ok" if net_pnl >= 0 else "loss_making"),
            "why_it_matters": "退出逻辑决定盈利兑现和回吐，TP 抑制过高会拖慢资金周转。",
        },
        "attribution_quality": {
            "trace_linkage_ratio": trace_linkage_ratio,
            "trace_linked_rows": trace_linked_rows,
            "agent_coverage_ratio": agent_coverage_ratio,
            "status": "weak" if trace_linkage_ratio < 0.7 or agent_coverage_ratio < 0.25 else "ok",
            "why_it_matters": "归因不足时，参数优化只能给建议，不能自动强应用。",
        },
    }

    parameter_recommendations: List[Dict[str, Any]] = []
    worst_regime_name = str((worst_regime or {}).get("regime") or "").lower() if isinstance(worst_regime, dict) else ""
    if worst_regime_name in {"volatile", "high_vol"} and _safe_float((worst_regime or {}).get("expectancy")) < 0:
        parameter_recommendations.append(
            {
                "priority": "high",
                "parameter_family": "entry.regime_policy_matrix",
                "target_keys": [
                    "ai_core.regime_policy_matrix.volatile.qty_mult",
                    "ai_core.regime_policy_matrix.volatile.leverage_mult",
                    "strategy_manager.market_regime_strategy_multiplier.*.volatile",
                ],
                "recommendation": "keep_or_tighten",
                "suggested_direction": "decrease_size_and_selection_weight",
                "evidence": {
                    "worst_regime": worst_regime,
                    "current_action": "volatile 已降权，应继续以小仓/观察为主，直到 expectancy 回正。",
                },
                "guardrail": "不要因为开仓少而放宽 volatile；只有连续样本 expectancy > 0 且 win_rate > 0.50 后才恢复。",
            }
        )
    if tp_suppression_per_trade > 0.5:
        parameter_recommendations.append(
            {
                "priority": "medium",
                "parameter_family": "exit.min_net_take_profit",
                "target_keys": [
                    "sltp.min_net_take_profit_percent",
                    "sltp.min_net_take_profit_regime_overrides.normal",
                    "sltp.min_net_take_profit_regime_overrides.range",
                    "sltp.min_net_take_profit_regime_overrides.low_vol_grind",
                ],
                "recommendation": "watch_after_recent_threshold_reduction",
                "suggested_direction": "lower_only_for_profitable_low_vol_or_range",
                "evidence": {
                    "tp_suppressed": tp_suppressed,
                    "tp_suppression_per_trade": tp_suppression_per_trade,
                    "net_pnl_plus_fees": net_pnl,
                },
                "guardrail": "high_vol/volatile 的净止盈门槛不要同步下调，避免手续费型假盈利。",
            }
        )
    top_rejects = signal_guard.get("top_reject_reasons") if isinstance(signal_guard, dict) else []
    top_reject_keys = [str(x.get("reason") or x.get("key") or "") for x in top_rejects if isinstance(x, dict)]
    if any("risk_reward_low" in x for x in top_reject_keys):
        parameter_recommendations.append(
            {
                "priority": "medium",
                "parameter_family": "entry.min_rr_to_trade",
                "target_keys": ["ai_core.min_rr_to_trade", "ai_core.regime_profile_overrides.*.min_rr_mult"],
                "recommendation": "do_not_blindly_loosen",
                "suggested_direction": "segment_by_regime_symbol_session_before_change",
                "evidence": {"top_reject_reasons": top_rejects[:5], "guard_pass_rate": guard_pass_rate, "net_pnl_plus_fees": net_pnl},
                "guardrail": "如果当前净收益为正且 volatile 亏损，RR 门槛应按 regime 分层，不应全局降低。",
            }
        )
    if any("entry_slippage" in x for x in top_reject_keys):
        parameter_recommendations.append(
            {
                "priority": "medium",
                "parameter_family": "entry.slippage_and_spread",
                "target_keys": ["ai_core.max_spread_bps_to_trade", "ai_core.max_entry_slippage_to_trade"],
                "recommendation": "collect_distribution_before_loosen",
                "suggested_direction": "loosen_only_for_high_liquidity_symbols",
                "evidence": {"top_reject_reasons": top_rejects[:5], "execution_success_ratio": execution_success_ratio},
                "guardrail": "滑点/点差放宽会直接提高成本，必须按 symbol/session 分组。",
            }
        )
    if agent_coverage_ratio < 0.25:
        parameter_recommendations.append(
            {
                "priority": "high",
                "parameter_family": "observability.agent_coverage",
                "target_keys": ["decision_trace.agent_outputs", "agent_orchestrator.main_path_coverage"],
                "recommendation": "improve_data_capture_before_auto_tuning",
                "suggested_direction": "increase_advisory_snapshot_persistence",
                "evidence": {"agent_coverage_ratio": agent_coverage_ratio, "trace_sample_size": trace_sample_size},
                "guardrail": "智能体覆盖率低时，不要把 agent verdict 当作自动调参主依据。",
            }
        )

    optimization_readiness = {
        "ready_for_safe_recommendations": bool(trade_sample_size >= 100 and trace_sample_size >= 100),
        "ready_for_auto_apply": bool(
            trade_sample_size >= 300
            and trace_linkage_ratio >= 0.7
            and agent_coverage_ratio >= 0.25
            and execution_success_ratio >= 0.9
        ),
        "blocking_gaps": [
            gap
            for gap in [
                {"id": "trade_sample_size", "message": "成交样本不足 300，不建议自动应用参数。"} if trade_sample_size < 300 else None,
                {"id": "data_quality", "message": "行情/数据质量快照不可用或低于 0.85。"} if bool(data_quality.get("degraded")) or _safe_float(data_quality.get("quality_score")) < 0.85 else None,
                {"id": "trace_linkage", "message": "成交 trace 归因覆盖不足 70%。"} if trace_linkage_ratio < 0.7 else None,
                {"id": "agent_coverage", "message": "四智能体覆盖不足 25%，暂不能用于自动调参。"} if agent_coverage_ratio < 0.25 else None,
                {"id": "execution_success", "message": "执行成功率不足 90%，应先修执行链路。"} if execution_success_ratio < 0.9 else None,
            ]
            if gap
        ],
        "recommended_read_cycle": [
            "读取 /api/v1/commander/trading-workflow",
            "先看 kpi_scorecard.status",
            "再看 parameter_recommendations.priority=high",
            "只在 ready_for_auto_apply=true 时允许自动应用；否则只生成建议和观测任务。",
        ],
    }

    return {
        "interface": {
            "name": "commander.trading_workflow",
            "version": "2026.05.16",
            "path": "/api/v1/commander/trading-workflow",
            "purpose": "Read-only end-to-end trading workflow state, reasons, outcomes, and optimization actions.",
        },
        "query": {
            "symbol": symbol,
            "trace_limit": int(trace_limit or 200),
            "trade_limit": int(trade_limit or 1000),
            "recent_trades_limit": int(recent_trades_limit or 40),
            "recent_order_hours": float(recent_order_hours or 4.0),
        },
        "health": {
            "system_status": system_status.get("system_status"),
            "running_modules": system_status.get("running_modules"),
            "module_count": system_status.get("module_count"),
            "exchange_connected": (gateway_snapshot or {}).get("exchange_connected"),
            "single_write_owner": (gateway_snapshot or {}).get("single_write_owner"),
            "reconciliation": (gateway_snapshot or {}).get("reconciliation"),
            "loop_health": closed_loop.get("loop_health") if isinstance(closed_loop, dict) else {},
        },
        "data_and_market": {
            "symbol": symbol,
            "snapshot": market_snapshot,
        },
        "current_exposure": {
            "positions": positions,
            "active_sltp_orders": active_sltp_orders,
            "position_count": len(positions),
            "active_sltp_count": len(active_sltp_orders),
        },
        "decision_and_guard": {
            "summary": signal_guard.get("decision_traces_summary") if isinstance(signal_guard, dict) else {},
            "workflow_focus": signal_guard.get("workflow_focus") if isinstance(signal_guard, dict) else {},
            "top_reject_reasons": signal_guard.get("top_reject_reasons") if isinstance(signal_guard, dict) else [],
            "top_reject_symbols": signal_guard.get("top_reject_symbols") if isinstance(signal_guard, dict) else [],
            "hold_diagnostics": hold_diag,
        },
        "execution": {
            "policy_metrics": (gateway_snapshot or {}).get("policy_metrics"),
            "execution_attribution": (gateway_snapshot or {}).get("execution_attribution"),
            "recent_events": compact_events,
        },
        "recent_order_attribution": recent_order_attribution,
        "exits_and_pnl": {
            "trade_summary": trade_summary,
            "close_reason_top": close_reason_top,
            "exit_review": trade_lifecycle.get("exit_review") if isinstance(trade_lifecycle, dict) else {},
            "realized_performance": realized_perf,
            "opportunity_blocks": opportunity_blocks,
            "tp_edge_suppression": exit_profit.get("tp_edge_suppression") if isinstance(exit_profit, dict) else {},
        },
        "learning_and_agents": {
            "agent_effectiveness": agent_effectiveness,
            "learning_optimization_hints": optimization_hints,
        },
        "optimization_read_model": {
            "kpi_scorecard": kpi_scorecard,
            "optimization_readiness": optimization_readiness,
            "parameter_recommendations": parameter_recommendations,
            "guardrails": [
                "执行/对账不健康时，禁止调策略阈值。",
                "数据质量低时，只允许降风险，不允许放宽开仓。",
                "volatile/high_vol 负期望时，禁止全局降低 RR 或置信度门槛。",
                "归因覆盖不足时，参数建议只能人工审核，不能自动应用。",
            ],
        },
        "workflow_actions": workflow_actions,
    }


def init_module_control_api(app, main_controller):
    """初始化模块控制API"""
    
    from fastapi import APIRouter, Body

    router = APIRouter(prefix="/api/v1/modules", tags=["modules"])
    trade_router = APIRouter(prefix="/api/v1/trade", tags=["trade"])
    market_router = APIRouter(prefix="/api/v1/market", tags=["market"])
    research_jobs: Dict[str, Dict[str, Any]] = {}
    research_jobs_lock = asyncio.Lock()
    research_semaphore = asyncio.Semaphore(1)
    dispatch_jobs: Dict[str, Dict[str, Any]] = {}
    dispatch_jobs_lock = asyncio.Lock()

    async def _check_unified_data_quality(
        symbol: str = "BTC/USDT",
        min_score: float = 0.5,
    ) -> Dict[str, Any]:
        mc = main_controller
        if not mc:
            return {"ok": False, "score": None, "message": "主控制器未初始化"}
        hub = getattr(mc, "data_source_hub", None)
        if not hub or not hasattr(hub, "get_unified_snapshot"):
            return {"ok": True, "score": None, "message": "统一数据源中心不可用，跳过门控"}
        try:
            # 防止上游行情/交易所抖动导致 API 入口阻塞。
            snap = await asyncio.wait_for(hub.get_unified_snapshot(symbol), timeout=6.0)
            quality = (snap.get("数据质量评估") or {}) if isinstance(snap, dict) else {}
            score = quality.get("score")
            score_f = float(score) if score is not None else None
            if score_f is None:
                return {"ok": True, "score": None, "message": "未返回质量分，跳过门控"}
            return {
                "ok": score_f >= float(min_score),
                "score": score_f,
                "symbol": symbol,
                "message": f"数据质量={score_f:.3f}, 阈值={float(min_score):.3f}",
            }
        except asyncio.TimeoutError:
            return {"ok": True, "score": None, "message": "质量门控超时，已降级放行"}
        except Exception as e:
            return {"ok": True, "score": None, "message": f"质量门控检查失败，已降级放行: {e}"}

    async def _notify_quality_warning(title: str, gate: Dict[str, Any]) -> None:
        """将数据质量告警推送到统一通知通道（含 TG 等），不中断主流程。"""
        try:
            if not main_controller:
                return
            symbol = str(gate.get("symbol") or "BTC/USDT")
            ai_line = ""
            # analysis moved to MarketIntelligenceEngine
            mi = getattr(main_controller, "market_intelligence", None)
            if mi and hasattr(mi, "get_symbol_view"):
                try:
                    view = await mi.get_symbol_view(symbol, include_snapshot=False)
                    ai_line = (
                        f"\nMI: 趋势={getattr(view, 'trend', '-') or '-'} | 倾向={getattr(view, 'action_bias', '-') or '-'} | "
                        f"置信度={getattr(view, 'confidence', None) if getattr(view, 'confidence', None) is not None else '-'}"
                    )
                    summary = str(getattr(view, "summary", "") or "").strip()
                    if summary:
                        ai_line += f"\n摘要: {summary[:180]}"
                except Exception:
                    pass
            msg = f"{title}\n{gate.get('message', '')}{ai_line}"
            if hasattr(main_controller, "_send_notification_handler"):
                await main_controller._send_notification_handler("数据质量告警", msg, priority="medium")
        except Exception:
            pass

    async def _run_research_job(job_id: str, payload: Dict[str, Any]) -> None:
        """后台执行研究任务，避免阻塞 API worker。"""
        if not main_controller:
            async with research_jobs_lock:
                research_jobs[job_id]["status"] = "failed"
                research_jobs[job_id]["message"] = "主控制器未初始化"
                research_jobs[job_id]["finished_at"] = datetime.now().isoformat()
            return

        pipeline = getattr(main_controller, "strategy_research_pipeline", None)
        if not pipeline:
            async with research_jobs_lock:
                research_jobs[job_id]["status"] = "failed"
                research_jobs[job_id]["message"] = "策略研究流水线未初始化"
                research_jobs[job_id]["finished_at"] = datetime.now().isoformat()
            return

        raw_syms = payload.get("symbols") or ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
        if isinstance(raw_syms, str):
            symbols = [raw_syms]
        elif isinstance(raw_syms, list):
            symbols = [str(s) for s in raw_syms if s]
        else:
            symbols = ["BTC/USDT", "ETH/USDT"]

        timeframe = str(payload.get("timeframe") or "1h")
        lookback_days = max(7, int(payload.get("lookback_days") or 28))
        timeout_sec = max(120, int(payload.get("timeout_seconds") or 1800))
        max_symbols = max(1, int(payload.get("max_symbols") or min(6, len(symbols))))
        sym_slice = symbols[:max_symbols]

        async with research_jobs_lock:
            research_jobs[job_id].update(
                {
                    "status": "running",
                    "symbols_used": sym_slice,
                    "timeframe": timeframe,
                    "lookback_days": lookback_days,
                    "timeout_seconds": timeout_sec,
                    "started_at": datetime.now().isoformat(),
                }
            )

        try:
            async with research_semaphore:
                result = await asyncio.wait_for(
                    pipeline.run_cycle(symbols=sym_slice, timeframe=timeframe, lookback_days=lookback_days),
                    timeout=timeout_sec,
                )
            async with research_jobs_lock:
                research_jobs[job_id].update(
                    {
                        "status": "completed",
                        "result": result,
                        "finished_at": datetime.now().isoformat(),
                    }
                )
        except asyncio.TimeoutError:
            async with research_jobs_lock:
                research_jobs[job_id].update(
                    {
                        "status": "failed",
                        "message": f"策略研发执行超时（>{timeout_sec}s）",
                        "finished_at": datetime.now().isoformat(),
                    }
                )
        except Exception as e:
            logger.exception("手动策略研发失败")
            async with research_jobs_lock:
                research_jobs[job_id].update(
                    {
                        "status": "failed",
                        "message": str(e),
                        "finished_at": datetime.now().isoformat(),
                    }
                )

    @trade_router.get("/events")
    async def get_trade_events(
        limit: int = 200,
        cursor: Optional[int] = None,
        type: Optional[str] = None,  # noqa: A002 (fastapi query param)
        symbol: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取最近交易域事件（Intent/Fill/Position）。
        前端可轮询或配合 WebSocket 订阅 channel=trade.*（支持前缀通配符）。
        """
        mc = main_controller
        hub = getattr(mc, "trade_event_hub", None) if mc else None
        if not hub or not (hasattr(hub, "query_recent") or hasattr(hub, "get_recent")):
            return {"ok": False, "events": [], "message": "TradeEventHub unavailable"}
        try:
            if hasattr(hub, "query_recent"):
                q = hub.query_recent(limit=int(limit or 200), cursor=cursor, event_type=type, symbol=symbol, trace_id=trace_id)
                return {"ok": True, **q}
            return {"ok": True, "events": hub.get_recent(limit=int(limit or 200))}
        except Exception as e:
            return {"ok": False, "events": [], "message": str(e)}

    @trade_router.get("/execution_spine")
    async def get_execution_spine_snapshot() -> Dict[str, Any]:
        """返回 S1 ExecutionGateway 快照（包含 policy_metrics）。"""
        mc = main_controller
        gw = getattr(mc, "execution_gateway", None) if mc else None
        if not gw or not hasattr(gw, "get_snapshot"):
            return {"ok": False, "message": "ExecutionGateway unavailable"}
        try:
            snap = await gw.get_snapshot()
            return {"ok": True, "snapshot": snap}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    # NOTE: symbols contain '/', use :path to match the whole remainder.
    @market_router.get("/symbol/{symbol:path}")
    async def get_market_symbol_view(
        symbol: str,
        include_snapshot: bool = False,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        """统一行情汇总：单品种视图（供前端/模块复用）。"""
        def _normalize_market_symbol(raw: str) -> str:
            s = str(raw or "").strip().upper().replace("-", "/")
            if not s:
                return "BTC/USDT"
            # Bare asset symbol like BTC -> BTC/USDT to avoid false degraded reads.
            if "/" not in s:
                if s.endswith("USDT"):
                    base = s[:-4].strip()
                    return f"{base}/USDT" if base else "BTC/USDT"
                return f"{s}/USDT"
            parts = [p for p in s.split("/") if p]
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
            return "BTC/USDT"

        symbol = _normalize_market_symbol(symbol)
        mc = main_controller
        mi = getattr(mc, "market_intelligence", None) if mc else None
        if not mi or not hasattr(mi, "get_symbol_view"):
            return {"ok": False, "message": "MarketIntelligenceEngine unavailable"}
        def _ensure_execution_support_schema(view_obj: Dict[str, Any]) -> Dict[str, Any]:
            """Keep response schema stable under degraded/cached paths."""
            if not isinstance(view_obj, dict):
                return {}
            es = view_obj.get("execution_support")
            if not isinstance(es, dict):
                es = {}
            if not isinstance(es.get("stable_anomalies"), list):
                es["stable_anomalies"] = []
            if not isinstance(es.get("anomaly_stability"), dict):
                es["anomaly_stability"] = {
                    "confirm_hits": 2,
                    "ttl_sec": 900,
                    "items": [],
                }
            if not isinstance(es.get("extra_provider_summary"), dict):
                es["extra_provider_summary"] = {
                    "aicoin_enabled": False,
                    "coinglass_enabled": False,
                }
            view_obj["execution_support"] = es
            return view_obj
        try:
            # Avoid blocking the control-plane. Prefer cached view when upstream is unstable.
            try:
                cached = mi.get_cached_symbol_view(symbol) if hasattr(mi, "get_cached_symbol_view") else {}
            except Exception:
                cached = {}
            if cached and not bool(include_snapshot):
                out_view = _ensure_execution_support_schema(dict(cached))
                if fields:
                    allow = {k.strip() for k in str(fields).split(",") if k.strip()}
                    allow.add("symbol")
                    allow.add("timestamp")
                    out_view = {k: v for k, v in out_view.items() if k in allow}
                return {
                    "ok": True,
                    "view": out_view,
                    "snapshot": None,
                    "degraded": True,
                    "message": "symbol_view_cached",
                    "degraded_reason": {
                        "code": "cached_fastpath",
                        "source": "market_intelligence_cache",
                        "include_snapshot": bool(include_snapshot),
                        "note": "返回缓存快照以保证控制面快速响应",
                    },
                }
            # include_snapshot 请求：优先返回缓存，并触发后台异步刷新，避免前台阻塞慢源链路。
            if cached and bool(include_snapshot):
                out_view = _ensure_execution_support_schema(dict(cached))
                try:
                    if hasattr(mi, "refresh_symbol_async"):
                        asyncio.create_task(mi.refresh_symbol_async(symbol, include_snapshot=True))
                except Exception:
                    pass
                if fields:
                    allow = {k.strip() for k in str(fields).split(",") if k.strip()}
                    allow.add("symbol")
                    allow.add("timestamp")
                    out_view = {k: v for k, v in out_view.items() if k in allow}
                return {
                    "ok": True,
                    "view": out_view,
                    "snapshot": None,
                    "degraded": bool(out_view.get("partial", False)),
                    "message": "symbol_view_cached_refreshing",
                    "degraded_reason": {
                        "code": "cached_refreshing",
                        "source": "market_intelligence_cache",
                        "include_snapshot": True,
                        "note": "已返回缓存并触发后台刷新",
                    },
                }

            # include_snapshot 请求但无缓存：先返回快路径视图（不阻塞），并后台刷新完整快照。
            if bool(include_snapshot) and not cached:
                try:
                    # 立刻返回 warming stub：保证控制面/诊断接口首次响应毫秒级。
                    # 后台异步刷新会把缓存补齐，后续请求会走 symbol_view_cached_refreshing。
                    out_view = _ensure_execution_support_schema(
                        {
                            "symbol": symbol,
                            "timestamp": None,
                            "trend": "unknown",
                            "action_bias": "hold",
                            "confidence": None,
                            "quality_score": None,
                            "spread_bps": None,
                            "atr_pct_1h": None,
                            "price": None,
                            "funding_rate": None,
                            "depth_imbalance": None,
                            "partial": True,
                            "cache_age_sec": None,
                        }
                    )
                except Exception:
                    out_view = _ensure_execution_support_schema({})
                try:
                    if hasattr(mi, "refresh_symbol_async"):
                        asyncio.create_task(mi.refresh_symbol_async(symbol, include_snapshot=True))
                except Exception:
                    pass
                if fields:
                    allow = {k.strip() for k in str(fields).split(",") if k.strip()}
                    allow.add("symbol")
                    allow.add("timestamp")
                    out_view = {k: v for k, v in out_view.items() if k in allow}
                return {
                    "ok": True,
                    "view": out_view,
                    "snapshot": None,
                    "degraded": True,
                    "message": "symbol_view_fastpath_refreshing",
                    "degraded_reason": {
                        "code": "fastpath_refreshing",
                        "source": "market_intelligence_get_symbol_view",
                        "include_snapshot": True,
                        "note": "无缓存：已返回快路径并触发后台刷新",
                    },
                }

            # unified_snapshot has its own bounded budget (DataSourceHub.snapshot_timeout_sec, default ~2.5s).
            # In proxy-only environments, scheduling + JSON + partial collectors can push the end-to-end
            # call slightly above 3s. Use a slightly larger cap to avoid false "timeout_degraded".
            req_timeout = 10.5 if bool(include_snapshot) else 4.5
            view = await asyncio.wait_for(
                mi.get_symbol_view(
                    symbol,
                    include_snapshot=bool(include_snapshot),
                    # API 默认查询不带 snapshot 时，优先快路径，避免被重采集拖慢并产生误导性 timeout。
                    prefer_fast_only=not bool(include_snapshot),
                ),
                timeout=req_timeout,
            )
            out_view = view.to_dict()
            out_view = _ensure_execution_support_schema(out_view)
            if fields:
                allow = {k.strip() for k in str(fields).split(",") if k.strip()}
                allow.add("symbol")
                allow.add("timestamp")
                out_view = {k: v for k, v in out_view.items() if k in allow}
            return {
                "ok": True,
                "view": out_view,
                "snapshot": view.snapshot if include_snapshot else None,
                "degraded": False,
                "degraded_reason": None,
            }
        except asyncio.TimeoutError:
            try:
                cached = mi.get_cached_symbol_view(symbol) if hasattr(mi, "get_cached_symbol_view") else {}
            except Exception:
                cached = {}
            cached = _ensure_execution_support_schema(dict(cached) if isinstance(cached, dict) else {})
            return {
                "ok": True,
                "view": cached or {},
                "snapshot": None,
                "degraded": True,
                "message": "symbol_view_timeout_degraded",
                "degraded_reason": {
                    "code": "upstream_timeout",
                    "source": "market_intelligence_get_symbol_view",
                    "include_snapshot": bool(include_snapshot),
                    "note": "上游采集超时，已降级为缓存/空结果",
                },
            }
        except Exception as e:
            return {
                "ok": False,
                "message": str(e),
                "degraded": True,
                "degraded_reason": {
                    "code": "internal_error",
                    "source": "market_symbol_view_handler",
                    "include_snapshot": bool(include_snapshot),
                    "note": "接口内部异常，请查看服务日志",
                },
            }

    @market_router.get("/state")
    async def get_market_state(timeout_sec: float = 3.2) -> Dict[str, Any]:
        """统一行情汇总：全局市场状态（多 symbol 聚合）。"""
        mc = main_controller
        mi = getattr(mc, "market_intelligence", None) if mc else None
        if not mi or not hasattr(mi, "get_market_state"):
            return {"ok": False, "message": "MarketIntelligenceEngine unavailable"}
        timeout_sec = max(1.5, min(float(timeout_sec or 3.2), 8.0))
        try:
            # 防止聚合计算/上游抖动导致 API 阻塞（前端/运维需要“快返回”）。
            # market_state is a fan-out aggregation. Keep it bounded but avoid being too tight.
            started_at = datetime.now()
            state = await asyncio.wait_for(mi.get_market_state(), timeout=timeout_sec)
            latency_ms = int((datetime.now() - started_at).total_seconds() * 1000)
            return {"ok": True, "state": state, "degraded": False, "latency_ms": latency_ms}
        except asyncio.TimeoutError:
            cached = None
            try:
                cached = mi.get_cached_market_state() if hasattr(mi, "get_cached_market_state") else None
            except Exception:
                cached = None
            return {
                "ok": True,
                "state": cached or {},
                "degraded": True,
                "message": "market_state_timeout_degraded",
                "timeout_sec": timeout_sec,
            }
        except Exception as e:
            return {"ok": False, "message": str(e)}

    @router.get("/list")
    async def get_all_modules():
        """获取所有模块列表和状态"""
        modules = []
        
        if main_controller:
            if hasattr(main_controller, 'ai_trading_engine') and main_controller.ai_trading_engine:
                modules.append({
                    "id": "ai_trading_engine",
                    "name": "AI交易引擎",
                    "category": "核心",
                    "status": "running" if main_controller.ai_trading_engine._running else "stopped",
                    "health": "healthy",
                    "description": "全智能AI交易引擎，自动分析市场并执行交易",
                    "controls": ["start", "stop", "analyze"]
                })
            
            if hasattr(main_controller, 'llm_integration') and main_controller.llm_integration:
                modules.append({
                    "id": "llm_integration",
                    "name": "AI大模型集成",
                    "category": "AI",
                    "status": "running",
                    "health": "healthy",
                    "description": "大语言模型集成系统，支持讯飞、百度千帆等",
                    "controls": ["chat", "analyze"]
                })
            
            if hasattr(main_controller, 'telegram_bot') and main_controller.telegram_bot:
                modules.append({
                    "id": "telegram_bot",
                    "name": "Telegram机器人",
                    "category": "通信",
                    "status": "running",
                    "health": "healthy",
                    "description": "Telegram通信机器人，接收用户指令并发送通知",
                    "controls": ["start", "stop", "test"]
                })
            
            if hasattr(main_controller, 'emergency_stop') and main_controller.emergency_stop:
                modules.append({
                    "id": "emergency_stop",
                    "name": "紧急停止系统",
                    "category": "安全",
                    "status": "ready",
                    "health": "healthy",
                    "description": "紧急情况下自动停止交易",
                    "controls": ["trigger", "reset"]
                })
            
            if hasattr(main_controller, 'intelligent_monitoring') and main_controller.intelligent_monitoring:
                modules.append({
                    "id": "intelligent_monitoring",
                    "name": "智能监控系统",
                    "category": "监控",
                    "status": "running",
                    "health": "healthy",
                    "description": "监控系统健康状态和性能指标",
                    "controls": ["check", "alert"]
                })
            
            if hasattr(main_controller, 'security_manager') and main_controller.security_manager:
                modules.append({
                    "id": "security_manager",
                    "name": "安全管理器",
                    "category": "安全",
                    "status": "running",
                    "health": "healthy",
                    "description": "系统安全检测和防护",
                    "controls": ["scan", "audit"]
                })
            
            if hasattr(main_controller, 'fund_manager') and main_controller.fund_manager:
                modules.append({
                    "id": "fund_manager",
                    "name": "智能资金管理器",
                    "category": "资金",
                    "status": "running" if main_controller.fund_manager.enabled else "stopped",
                    "health": "healthy",
                    "description": "智能资金分配和仓位管理",
                    "controls": ["start", "stop", "rebalance"]
                })
            
            if hasattr(main_controller, 'ai_learning_engine') and main_controller.ai_learning_engine:
                modules.append({
                    "id": "ai_learning_engine",
                    "name": "AI学习引擎",
                    "category": "AI",
                    "status": "running" if main_controller.ai_learning_engine._running else "stopped",
                    "health": "healthy",
                    "description": "自动学习交易经验并优化策略",
                    "controls": ["start", "stop", "learn"]
                })
            
            if hasattr(main_controller, 'anomaly_detector') and main_controller.anomaly_detector:
                modules.append({
                    "id": "anomaly_detector",
                    "name": "异常检测器",
                    "category": "监控",
                    "status": "running",
                    "health": "healthy",
                    "description": "检测市场异常和系统异常",
                    "controls": ["detect", "report"]
                })
            
            if hasattr(main_controller, 'strategy_manager') and main_controller.strategy_manager:
                modules.append({
                    "id": "strategy_manager",
                    "name": "策略管理器",
                    "category": "策略",
                    "status": "running",
                    "health": "healthy",
                    "description": "管理多个交易策略",
                    "controls": ["list", "activate", "deactivate"]
                })
            
            if hasattr(main_controller, 'portfolio_optimizer') and main_controller.portfolio_optimizer:
                modules.append({
                    "id": "portfolio_optimizer",
                    "name": "组合优化器",
                    "category": "策略",
                    "status": "ready",
                    "health": "healthy",
                    "description": "优化投资组合配置",
                    "controls": ["optimize", "rebalance"]
                })
            
            if hasattr(main_controller, 'backup_manager') and main_controller.backup_manager:
                modules.append({
                    "id": "backup_manager",
                    "name": "数据备份管理器",
                    "category": "数据",
                    "status": "running",
                    "health": "healthy",
                    "description": "自动备份系统数据",
                    "controls": ["backup", "restore", "schedule"]
                })
        
        return {
            "modules": modules,
            "total": len(modules),
            "timestamp": datetime.now().isoformat()
        }
    
    @router.post("/{module_id}/control")
    async def control_module(module_id: str, action: str, params: Optional[Dict] = None):
        """控制指定模块"""
        params = params or {}
        result = {"success": False, "message": ""}
        
        try:
            if module_id == "ai_trading_engine":
                if main_controller and hasattr(main_controller, 'ai_trading_engine'):
                    engine = main_controller.ai_trading_engine
                    if action == "start":
                        if not engine._running:
                            await engine.start()
                        result = {"success": True, "message": "AI交易引擎已启动"}
                    elif action == "stop":
                        await engine.stop()
                        result = {"success": True, "message": "AI交易引擎已停止"}
                    elif action == "analyze":
                        symbol = params.get("symbol", "BTC/USDT")
                        result = {"success": True, "message": f"开始分析 {symbol}", "data": {"symbol": symbol}}
            
            elif module_id == "telegram_bot":
                if main_controller and hasattr(main_controller, 'telegram_bot'):
                    bot = main_controller.telegram_bot
                    if action == "test":
                        result = {"success": True, "message": "Telegram机器人测试成功"}
            
            elif module_id == "emergency_stop":
                if main_controller and hasattr(main_controller, 'emergency_stop'):
                    es = main_controller.emergency_stop
                    if action == "trigger":
                        await es._trigger_emergency(
                            level="HIGH",
                            type="manual_trigger",
                            description="手动触发紧急停止"
                        )
                        result = {"success": True, "message": "紧急停止已触发"}
                    elif action == "reset":
                        es._is_emergency_mode = False
                        result = {"success": True, "message": "紧急停止已重置"}
            
            elif module_id == "fund_manager":
                if main_controller and hasattr(main_controller, 'fund_manager'):
                    fm = main_controller.fund_manager
                    if action == "start":
                        fm.enabled = True
                        result = {"success": True, "message": "资金管理器已启动"}
                    elif action == "stop":
                        fm.enabled = False
                        result = {"success": True, "message": "资金管理器已停止"}
            
            elif module_id == "ai_learning_engine":
                if main_controller and hasattr(main_controller, 'ai_learning_engine'):
                    le = main_controller.ai_learning_engine
                    if action == "start":
                        await le.start()
                        result = {"success": True, "message": "AI学习引擎已启动"}
                    elif action == "stop":
                        await le.stop()
                        result = {"success": True, "message": "AI学习引擎已停止"}
            
            else:
                result = {"success": False, "message": f"未知模块: {module_id}"}
        
        except Exception as e:
            result = {"success": False, "message": f"操作失败: {str(e)}"}
        
        return result
    
    @router.get("/trading/symbols")
    async def get_trading_symbols():
        """获取交易对配置"""
        blacklist = []
        selector_payload = None
        if main_controller and hasattr(main_controller, "dynamic_symbol_selector"):
            selector = getattr(main_controller, "dynamic_symbol_selector", None)
            if selector is not None:
                try:
                    symbols = await selector.get_trading_symbols()
                    stats = selector.get_stats() if hasattr(selector, "get_stats") else {}
                    if symbols:
                        selector_payload = {
                            "symbols": symbols,
                            "blacklist": blacklist,
                            "message": "dynamic symbol selector active",
                            "source": "dynamic_symbol_selector",
                            "selector_stats": stats,
                        }
                except Exception:
                    pass
        if selector_payload is not None:
            return selector_payload
        if main_controller and hasattr(main_controller, 'ai_trading_engine'):
            engine = main_controller.ai_trading_engine
            if hasattr(engine, 'symbols'):
                return {
                    "symbols": engine.symbols,
                    "blacklist": blacklist,
                    "message": "engine symbol config",
                    "source": "ai_trading_engine",
                }
        return {
            "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
            "blacklist": blacklist,
            "source": "default_fallback",
        }
    
    @router.post("/trading/symbols/config")
    async def config_trading_symbols(config: Dict[str, Any]):
        """配置交易对"""
        symbols = config.get("symbols", [])
        blacklist = config.get("blacklist", [])
        
        if main_controller and hasattr(main_controller, 'ai_trading_engine'):
            engine = main_controller.ai_trading_engine
            filtered_symbols = [s for s in symbols if s not in blacklist]
            engine.symbols = filtered_symbols
            return {
                "success": True,
                "message": f"交易对已更新，黑名单: {blacklist}",
                "symbols": filtered_symbols,
                "blacklist": blacklist
            }
        
        return {"success": False, "message": "AI交易引擎未初始化"}
    
    @router.get("/models")
    async def get_ai_models():
        """获取AI模型列表"""
        models = []
        if main_controller and hasattr(main_controller, 'enhanced_llm_manager'):
            mgr = main_controller.enhanced_llm_manager
            for model_id, config in mgr.models.items():
                models.append({
                    "id": model_id,
                    "name": config.display_name,
                    "provider": config.provider.value,
                    "priority": config.priority,
                    "enabled": config.enabled,
                    "context_window": config.context_window
                })
        
        return {
            "models": models,
            "total": len(models)
        }
    
    @router.post("/models/{model_id}/select")
    async def select_ai_model(model_id: str):
        """选择AI模型"""
        if main_controller and hasattr(main_controller, 'enhanced_llm_manager'):
            mgr = main_controller.enhanced_llm_manager
            if model_id in mgr.models:
                mgr.default_model = model_id
                return {"success": True, "message": f"已切换到模型: {model_id}"}
        
        return {"success": False, "message": "模型不存在"}
    
    @router.get("/risk/status")
    async def get_risk_status():
        """获取风险状态"""
        risk_data = {
            "circuit_breaker": {"status": "closed", "trigger_count": 0},
            "daily_trades": 0,
            "hourly_trades": 0,
            "consecutive_losses": 0,
            "current_drawdown": 0.0,
            "risk_level": "low"
        }

        def _resolve_risk_monitor():
            if not main_controller:
                return None
            if hasattr(main_controller, 'risk_monitor') and main_controller.risk_monitor:
                return main_controller.risk_monitor
            if (
                hasattr(main_controller, 'ai_trading_engine')
                and main_controller.ai_trading_engine
                and hasattr(main_controller.ai_trading_engine, 'risk_monitor')
                and main_controller.ai_trading_engine.risk_monitor
            ):
                return main_controller.ai_trading_engine.risk_monitor
            return None

        if main_controller:
            monitor = _resolve_risk_monitor()

            if monitor:
                status = monitor.get_status() if hasattr(monitor, "get_status") else {}
                risk_data.update(status if isinstance(status, dict) else {})
                risk_data["monitor_running"] = bool(
                    (status or {}).get("running", False) if isinstance(status, dict) else False
                )
            
            if hasattr(main_controller, 'ai_trading_engine') and main_controller.ai_trading_engine:
                engine = main_controller.ai_trading_engine
                if hasattr(engine, 'enhanced_risk') and engine.enhanced_risk:
                    risk_status = engine.enhanced_risk.get_risk_status()
                    risk_data["circuit_breaker"] = risk_status.get("circuit_breaker", {})
                    risk_data["risk_level"] = risk_status.get("trading_state", {}).get("daily_trades", 0) > 15 and "medium" or "low"
        
        return risk_data

    @router.get("/risk/config")
    async def get_risk_config():
        """读取账户风险监控阈值配置"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        monitor = None
        if hasattr(main_controller, 'risk_monitor') and main_controller.risk_monitor:
            monitor = main_controller.risk_monitor
        elif (
            hasattr(main_controller, 'ai_trading_engine')
            and main_controller.ai_trading_engine
            and hasattr(main_controller.ai_trading_engine, 'risk_monitor')
            and main_controller.ai_trading_engine.risk_monitor
        ):
            monitor = main_controller.ai_trading_engine.risk_monitor
        if not monitor:
            return {"success": False, "message": "风险监控未初始化"}
        return {
            "success": True,
            "config": dict(getattr(monitor, "risk_config", {}) or {}),
            "running": bool(getattr(monitor, "_running", False)),
        }

    @router.post("/risk/config")
    async def update_risk_config(payload: Dict[str, Any]):
        """更新账户风险监控阈值（运行期生效）"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        monitor = None
        if hasattr(main_controller, 'risk_monitor') and main_controller.risk_monitor:
            monitor = main_controller.risk_monitor
        elif (
            hasattr(main_controller, 'ai_trading_engine')
            and main_controller.ai_trading_engine
            and hasattr(main_controller.ai_trading_engine, 'risk_monitor')
            and main_controller.ai_trading_engine.risk_monitor
        ):
            monitor = main_controller.ai_trading_engine.risk_monitor
        if not monitor:
            return {"success": False, "message": "风险监控未初始化"}

        allowed = {
            "margin_ratio_warning",
            "margin_ratio_critical",
            "unrealized_loss_warning",
            "unrealized_loss_critical",
            "liquidation_distance_warning",
            "liquidation_distance_critical",
            "monitor_interval",
        }
        applied: Dict[str, Any] = {}
        for k, v in (payload or {}).items():
            if k not in allowed or v is None:
                continue
            try:
                if k == "monitor_interval":
                    monitor.risk_config[k] = max(2, int(float(v)))
                else:
                    monitor.risk_config[k] = float(v)
                applied[k] = monitor.risk_config[k]
            except Exception:
                continue
        return {"success": True, "applied": applied, "config": dict(monitor.risk_config)}
    
    @router.post("/risk/reset")
    async def reset_risk_counters():
        """重置风险计数器"""
        if main_controller and hasattr(main_controller, 'ai_trading_engine'):
            engine = main_controller.ai_trading_engine
            if hasattr(engine, 'enhanced_risk') and engine.enhanced_risk:
                await engine.enhanced_risk.reset_daily_counters()
                await engine.enhanced_risk.reset_hourly_counters()
                return {"success": True, "message": "风险计数器已重置"}
        
        return {"success": True, "message": "风险计数器已重置"}

    @router.get("/ai/guards")
    async def get_ai_execution_guards():
        """获取 AI 执行门控配置与触发统计"""
        if not main_controller or not hasattr(main_controller, "ai_core") or not main_controller.ai_core:
            return {"success": False, "message": "AI核心决策引擎未初始化"}
        try:
            st = main_controller.ai_core.get_status() if hasattr(main_controller.ai_core, "get_status") else {}
            guards = (st or {}).get("execution_guards", {})
            return {
                "success": True,
                "config": guards.get("config", {}),
                "adaptive_profile": guards.get("adaptive_profile", {}),
                "group_overrides": guards.get("group_overrides", {}),
                "frequency_profile": guards.get("frequency_profile", "balanced"),
                "last_frequency_profile_switch_at": guards.get("last_frequency_profile_switch_at"),
                "group_last_tuned_at": guards.get("group_last_tuned_at", {}),
                "global_last_tuned_at": guards.get("global_last_tuned_at"),
                "stats": guards.get("stats", {}),
            }
        except Exception as e:
            return {"success": False, "message": f"读取执行门控失败: {e}"}

    @router.post("/ai/guards")
    async def update_ai_execution_guards(config: Dict[str, Any]):
        """更新 AI 执行门控阈值（运行期生效）"""
        if not main_controller or not hasattr(main_controller, "ai_core") or not main_controller.ai_core:
            return {"success": False, "message": "AI核心决策引擎未初始化"}
        ai_core = main_controller.ai_core
        allowed = {
            "min_trade_interval",
            "min_confidence_to_trade",
            "ai_core_min_confidence_to_open",
            "ai_core_min_confidence_floor",
            "min_data_quality_to_trade",
            "analysis_hard_gate_for_open",
            "analysis_min_confidence_for_open",
            "analysis_require_not_degraded_for_open",
            "open_allow_snapshot_timeout_fallback",
            "open_requires_full_snapshot",
            "open_attempt_klines_recovery_fetch",
            "open_klines_recovery_fetch_timeout_s",
            "open_klines_recovery_fetch_limit",
            "open_klines_recovery_min_bars",
            "open_allow_klines_missing_evidence_fallback",
            "open_klines_missing_evidence_qty_mult",
            "min_rr_to_trade",
            "max_spread_bps_to_trade",
            "max_abs_depth_imbalance_to_trade",
            "degraded_data_quantity_factor",
            "boost_on_low_risk",
            "low_risk_rr_multiplier",
            "low_risk_spread_multiplier",
            "high_risk_rr_multiplier",
            "high_risk_spread_multiplier",
            "regime_enable",
            "regime_low_vol_atr_pct",
            "regime_high_vol_atr_pct",
            "regime_trend_threshold",
            "regime_low_liquidity_spread_bps",
            "regime_profile_overrides",
            "regime_policy_matrix",
            "pnl_health_sizing_enable",
            "pnl_health_lookback_trades",
            "pnl_health_bad_expectancy",
            "pnl_health_bad_drawdown",
            "pnl_health_bad_factor",
            "pnl_health_good_expectancy",
            "pnl_health_good_drawdown",
            "pnl_health_good_factor",
            "edge_after_cost_guard_enable",
            "edge_min_net_reward_pct",
            "edge_fee_rate_per_side",
            "edge_slippage_rate_per_side",
            "edge_spread_penalty_weight",
            "loss_streak_cooldown_enable",
            "loss_streak_trigger",
            "loss_streak_lookback",
            "loss_streak_cooldown_sec",
            "loss_streak_min_abs_loss",
            "auto_frequency_profile_switch",
            "frequency_profile_switch_telegram_notify",
            "frequency_profile_cooldown_seconds",
            "frequency_profile_lookback_trades",
            "frequency_profile_max_drawdown_guard",
            "auto_adaptive_guards",
            "auto_tune_guards",
            "auto_tune_by_symbol_group",
            "auto_tune_by_session",
            "auto_tune_global_enabled",
            "auto_tune_global_cooldown_seconds",
            "auto_tune_global_step_rr",
            "auto_tune_global_step_spread_bps",
            "auto_tune_global_max_cumulative_rr_delta_from_baseline",
            "auto_tune_global_max_cumulative_spread_bps_delta_from_baseline",
            "auto_tune_step_rr",
            "auto_tune_step_spread_bps",
            "auto_tune_group_step_rr",
            "auto_tune_group_step_spread_bps",
            "auto_tune_cooldown_seconds",
            "auto_tune_min_rr_delta",
            "auto_tune_min_spread_delta_bps",
            "auto_tune_sltp_params",
            "auto_tune_sltp_cooldown_seconds",
            "auto_tune_sltp_step_tighten",
            "auto_tune_sltp_step_extend",
            "critical_risk_auto_close",
            "critical_risk_auto_close_liq_only",
            "critical_risk_auto_close_max_liq_distance",
            "critical_risk_auto_close_min_loss_pct",
            "hold_avoidance_override_enabled",
            "hold_avoidance_override_cooldown_sec",
            "hold_avoidance_override_min_abs_sentiment",
            "hold_avoidance_override_min_mi_quality_score",
            "hold_avoidance_override_require_mi_trend_alignment",
            "ai_autonomy_minimal_gates_enabled",
            "ai_autonomy_min_conf_floor",
            "ai_autonomy_min_mi_confidence",
            "ai_autonomy_min_mi_quality_score",
            "ai_autonomy_allow_neutral_with_trend",
            "ai_autonomy_require_trend_alignment",
            "ai_autonomy_enable_mtf_conflict_release",
            "ai_autonomy_mtf_conflict_release_requires_mi_bias",
            "ai_autonomy_conflict_subtype_release_enabled",
            "ai_autonomy_conflict_release_min_rsi_1h_for_long",
            "ai_autonomy_conflict_release_max_rsi_1h_for_short",
            "ai_autonomy_conflict_release_min_abs_change_24h",
            "ai_autonomy_conflict_release_require_mi_confidence",
            "auto_tune_hold_override_enabled",
            "auto_tune_hold_override_min_interval_seconds",
            "auto_tune_hold_override_cooldown_seconds",
            "auto_tune_hold_override_window_traces",
            "auto_tune_hold_override_min_traces",
            "auto_tune_hold_override_step_min_abs_sentiment",
            "auto_tune_hold_override_step_min_mi_quality_score",
            "auto_tune_hold_override_min_abs_sentiment_bounds",
            "auto_tune_hold_override_min_mi_quality_score_bounds",
            "auto_tune_hold_override_max_steps_per_cooldown",
            "auto_tune_hold_override_hold_ratio_trigger",
            "auto_tune_hold_override_open_ratio_trigger",
            "auto_tune_hold_override_tighten_hold_ratio",
            "auto_tune_hold_override_win_rate_floor",
            "auto_tune_hold_override_avg_pnl_floor",
            "auto_tune_hold_override_allow_relax_without_recent_pnl",
            "auto_tune_hold_override_max_total_min_abs_sentiment_delta_from_baseline",
            "auto_tune_hold_override_max_total_min_mi_quality_score_delta_from_baseline",
        }
        applied: Dict[str, Any] = {}
        for k, v in (config or {}).items():
            if k in allowed and v is not None:
                try:
                    if k in (
                        "auto_adaptive_guards",
                        "auto_tune_guards",
                        "auto_tune_by_symbol_group",
                        "auto_tune_by_session",
                        "auto_tune_global_enabled",
                        "auto_tune_sltp_params",
                        "boost_on_low_risk",
                        "auto_frequency_profile_switch",
                        "frequency_profile_switch_telegram_notify",
                        "auto_tune_hold_override_enabled",
                        "auto_tune_hold_override_allow_relax_without_recent_pnl",
                        "analysis_hard_gate_for_open",
                        "analysis_require_not_degraded_for_open",
                        "open_allow_snapshot_timeout_fallback",
                        "open_requires_full_snapshot",
                        "open_attempt_klines_recovery_fetch",
                        "open_allow_klines_missing_evidence_fallback",
                        "ai_autonomy_minimal_gates_enabled",
                        "ai_autonomy_allow_neutral_with_trend",
                        "ai_autonomy_require_trend_alignment",
                        "ai_autonomy_enable_mtf_conflict_release",
                        "ai_autonomy_mtf_conflict_release_requires_mi_bias",
                        "ai_autonomy_conflict_subtype_release_enabled",
                        "ai_autonomy_conflict_release_require_mi_confidence",
                    ):
                        ai_core.config[k] = bool(v)
                        applied[k] = bool(v)
                    elif k in (
                        "auto_tune_group_step_rr",
                        "auto_tune_group_step_spread_bps",
                    ):
                        if isinstance(v, str) and v.strip().lower() in ("", "null", "none"):
                            ai_core.config[k] = None
                            applied[k] = None
                        else:
                            ai_core.config[k] = float(v)
                            applied[k] = float(ai_core.config[k])
                    elif k in (
                        "auto_tune_hold_override_min_abs_sentiment_bounds",
                        "auto_tune_hold_override_min_mi_quality_score_bounds",
                        "regime_profile_overrides",
                        "regime_policy_matrix",
                    ):
                        ai_core.config[k] = v
                        applied[k] = v
                    else:
                        ai_core.config[k] = float(v)
                        applied[k] = float(v)
                except Exception:
                    continue

        # Persist applied keys to config_manager so ai_core runtime refresh
        # will not overwrite API-updated values on next loop.
        try:
            cm = getattr(main_controller, "config_manager", None) if main_controller else None
            if cm is not None and hasattr(cm, "set_config"):
                for k, v in (applied or {}).items():
                    try:
                        await cm.set_config("ai_core_runtime", str(k), v, validate=False)
                    except Exception:
                        continue
        except Exception:
            pass
        return {
            "success": True,
            "message": "执行门控配置已更新",
            "applied": applied,
        }

    @router.get("/ai/learning-feedback")
    async def get_ai_learning_feedback():
        """
        获取 AI 交易引擎的止损复盘与信号惩罚状态（验收可视化接口）。
        说明：
        - stop_loss_hits 每累计 3 次，会将该信号额外开仓门槛 +0.05（上限 +0.15）
        """
        if not main_controller or not hasattr(main_controller, "ai_trading_engine") or not main_controller.ai_trading_engine:
            return {"success": False, "message": "AI交易引擎未初始化"}
        engine = main_controller.ai_trading_engine
        try:
            stats_raw = getattr(engine, "_signal_stop_loss_stats", {}) or {}
            if not isinstance(stats_raw, dict):
                stats_raw = {}

            rows: List[Dict[str, Any]] = []
            for signal_key, item in stats_raw.items():
                it = item if isinstance(item, dict) else {}
                hits = int(it.get("stop_loss_hits", 0) or 0)
                steps = hits // 3
                extra = min(0.15, 0.05 * steps)
                rows.append(
                    {
                        "signal_key": str(signal_key),
                        "stop_loss_hits": hits,
                        "penalty_steps": steps,
                        "extra_confidence_threshold": float(round(extra, 4)),
                        "last_at": it.get("last_at"),
                    }
                )

            rows.sort(key=lambda x: (x.get("stop_loss_hits", 0), x.get("last_at") or ""), reverse=True)

            ai_cfg = getattr(engine, "ai_config", {}) or {}
            base_min_conf = float(ai_cfg.get("min_confidence", 0.75) or 0.75)
            penalty_step_hits = int(ai_cfg.get("penalty_step_hits", 3) or 3)
            penalty_step_threshold = float(ai_cfg.get("penalty_step_threshold", 0.05) or 0.05)
            penalty_max_threshold = float(ai_cfg.get("penalty_max_threshold", 0.15) or 0.15)
            max_pos_ratio = float(ai_cfg.get("max_position_value_ratio", 0.05) or 0.05)
            try:
                from src.modules.core.trading_limits import resolve_position_limits

                limits = await resolve_position_limits(config_manager=getattr(main_controller, "config_manager", None))
                hard_max_positions = int(limits.hard_max_positions)
            except Exception:
                hard_max_positions = int(ai_cfg.get("hard_max_positions", 5) or 5)
            require_trend_for_open = bool(ai_cfg.get("require_trend_for_open", True))
            tracked_signals = len(rows)
            penalized_signals = sum(1 for r in rows if float(r.get("extra_confidence_threshold", 0)) > 0)
            total_stop_loss_hits = sum(int(r.get("stop_loss_hits", 0) or 0) for r in rows)
            max_extra_threshold = float(
                round(max((float(r.get("extra_confidence_threshold", 0) or 0) for r in rows), default=0.0), 4)
            )

            return {
                "success": True,
                "summary": {
                    "tracked_signals": tracked_signals,
                    "penalized_signals": penalized_signals,
                    "penalized_ratio": float(round((penalized_signals / tracked_signals), 4)) if tracked_signals else 0.0,
                    "total_stop_loss_hits": total_stop_loss_hits,
                    "base_min_confidence": base_min_conf,
                    "max_extra_confidence_threshold": max_extra_threshold,
                    "effective_min_confidence_upper_bound": float(
                        round(
                            base_min_conf + max_extra_threshold,
                            4,
                        )
                    ),
                    "penalty_rule": {
                        "step_hits": penalty_step_hits,
                        "step_threshold": penalty_step_threshold,
                        "max_threshold": penalty_max_threshold,
                    },
                    "max_position_value_ratio": max_pos_ratio,
                    "hard_max_positions": hard_max_positions,
                    "require_trend_for_open": require_trend_for_open,
                },
                "signals": rows[:200],
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": f"读取学习反馈失败: {e}"}

    @router.get("/ai/frequency-profile")
    async def get_ai_frequency_profile():
        """读取当前开单频率档位（根据关键门控参数推断）"""
        if not main_controller or not hasattr(main_controller, "ai_core") or not main_controller.ai_core:
            return {"success": False, "message": "AI核心决策引擎未初始化"}
        ai_core = main_controller.ai_core
        cfg = ai_core.config if hasattr(ai_core, "config") else {}
        min_interval = float(cfg.get("min_trade_interval", 120) or 120)
        min_conf = float(cfg.get("min_confidence_to_trade", 0.75) or 0.75)
        min_rr = float(cfg.get("min_rr_to_trade", 1.2) or 1.2)
        spread = float(cfg.get("max_spread_bps_to_trade", 35.0) or 35.0)
        prof_status = (
            ai_core.get_frequency_profile_status()
            if hasattr(ai_core, "get_frequency_profile_status")
            else {
                "profile": getattr(ai_core, "_frequency_profile", "balanced"),
                "last_switch_at": (
                    ai_core._last_frequency_profile_switch_at.isoformat()
                    if hasattr(ai_core, "_last_frequency_profile_switch_at") and ai_core._last_frequency_profile_switch_at
                    else None
                ),
                "last_switch_detail": getattr(ai_core, "_last_frequency_profile_switch_detail", {}),
            }
        )
        # 优先使用运行时真实档位；启发式推断仅做兜底（避免与当前 profile 参数漂移产生误报）。
        runtime_profile = str(prof_status.get("profile") or "").strip().lower()
        if runtime_profile in ("conservative", "balanced", "aggressive"):
            inferred = runtime_profile
        else:
            if min_interval <= 70 and min_rr <= 1.10 and spread >= 45.0:
                inferred = "aggressive"
            elif min_interval <= 90 and min_rr <= 1.15 and spread >= 40.0:
                inferred = "balanced"
            else:
                inferred = "conservative"
        return {
            "success": True,
            "inferred_profile": inferred,
            "runtime_profile": prof_status.get("profile"),
            "last_switch_at": prof_status.get("last_switch_at"),
            "last_switch_detail": prof_status.get("last_switch_detail"),
            "config": {
                "min_trade_interval": min_interval,
                "min_confidence_to_trade": min_conf,
                "min_rr_to_trade": min_rr,
                "max_spread_bps_to_trade": spread,
                "boost_on_low_risk": bool(cfg.get("boost_on_low_risk", True)),
            },
        }

    def _build_frequency_profile_explain_payload(
        runtime_profile: str,
        inferred_profile: str,
        last_switch_at: Optional[str],
        last_switch_detail: Dict[str, Any],
    ) -> Dict[str, Any]:
        detail = dict(last_switch_detail or {})
        source = str(detail.get("source") or "unknown")
        reason_metrics = detail.get("reason_metrics") if isinstance(detail.get("reason_metrics"), dict) else {}
        market_ctx = detail.get("market_signal_context") if isinstance(detail.get("market_signal_context"), dict) else {}
        top_anomalies = market_ctx.get("top_anomalies") if isinstance(market_ctx.get("top_anomalies"), list) else []
        applied = detail.get("applied") if isinstance(detail.get("applied"), dict) else {}
        mode = "auto" if source == "auto" else ("manual" if source == "manual_api" else "unknown")

        explain = []
        if mode == "auto":
            win_rate = reason_metrics.get("win_rate")
            dd = reason_metrics.get("max_drawdown")
            risk_ratio = reason_metrics.get("mi_risk_ratio")
            if win_rate is not None:
                explain.append(f"win_rate={win_rate}")
            if dd is not None:
                explain.append(f"max_drawdown={dd}")
            if risk_ratio is not None:
                explain.append(f"mi_risk_ratio={risk_ratio}")
            if top_anomalies:
                tops = [str((x or {}).get("anomaly") or "") for x in top_anomalies[:3] if isinstance(x, dict)]
                tops = [x for x in tops if x]
                if tops:
                    explain.append(f"top_anomalies={','.join(tops)}")
        elif mode == "manual":
            if applied:
                explain.append("manual_api_applied")
            explain.append(f"from={detail.get('from')} to={detail.get('to')}")
        else:
            explain.append("switch_detail_unavailable")

        return {
            "mode": mode,
            "source": source,
            "runtime_profile": runtime_profile,
            "inferred_profile": inferred_profile,
            "last_switch_at": last_switch_at,
            "switch": {
                "from": detail.get("from"),
                "to": detail.get("to"),
                "timestamp": detail.get("timestamp") or last_switch_at,
            },
            "reason_metrics": reason_metrics,
            "market_signal_context": {
                "top_anomalies": top_anomalies,
            },
            "applied": applied,
            "explain_text": "; ".join(explain),
        }

    @router.get("/ai/frequency-profile/explain")
    async def get_ai_frequency_profile_explain():
        """统一返回手动/自动切档解释，便于 OpenClaw 前端稳定渲染。"""
        raw = await get_ai_frequency_profile()
        if not isinstance(raw, dict) or not bool(raw.get("success")):
            return {
                "success": False,
                "message": (raw or {}).get("message", "读取频率档位状态失败") if isinstance(raw, dict) else "读取频率档位状态失败",
            }
        payload = _build_frequency_profile_explain_payload(
            runtime_profile=str(raw.get("runtime_profile") or ""),
            inferred_profile=str(raw.get("inferred_profile") or ""),
            last_switch_at=raw.get("last_switch_at"),
            last_switch_detail=raw.get("last_switch_detail") if isinstance(raw.get("last_switch_detail"), dict) else {},
        )
        return {
            "success": True,
            "ok": True,
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "data": payload,
        }

    @router.post("/ai/frequency-profile")
    async def set_ai_frequency_profile(payload: Dict[str, Any]):
        """一键切换开单频率档位（运行期生效）：conservative / balanced / aggressive"""
        if not main_controller or not hasattr(main_controller, "ai_core") or not main_controller.ai_core:
            return {"success": False, "message": "AI核心决策引擎未初始化"}
        ai_core = main_controller.ai_core
        requested = str((payload or {}).get("profile", "balanced")).strip().lower()
        profiles = (
            ai_core._get_frequency_profiles()
            if hasattr(ai_core, "_get_frequency_profiles")
            else {}
        )
        if requested not in profiles:
            return {
                "success": False,
                "message": "无效档位，支持: conservative / balanced / aggressive",
            }
        old_profile = str(getattr(ai_core, "_frequency_profile", "unknown") or "unknown")
        if hasattr(ai_core, "_apply_frequency_profile"):
            applied = ai_core._apply_frequency_profile(requested)
        else:
            applied = {}
            for k, v in profiles[requested].items():
                ai_core.config[k] = v
                applied[k] = v
        # 记录手动切档明细，便于 OpenClaw 直接观测来源与参数变化。
        try:
            ai_core._last_frequency_profile_switch_detail = {
                "source": "manual_api",
                "from": old_profile,
                "to": requested,
                "timestamp": datetime.now().isoformat(),
                "applied": dict(applied or {}),
            }
        except Exception:
            pass
        return {
            "success": True,
            "message": f"已切换到 {requested} 档位",
            "profile": requested,
            "applied": applied,
        }
    
    @router.get("/memory/stats")
    async def get_memory_stats():
        """获取记忆系统统计"""
        stats = {
            "short_term_count": 0,
            "long_term_count": 0,
            "trade_records": 0,
            "risk_events": 0
        }
        
        if main_controller:
            if hasattr(main_controller, 'ai_memory_manager') and main_controller.ai_memory_manager:
                mem = main_controller.ai_memory_manager
                if hasattr(mem, "get_stats"):
                    try:
                        raw = mem.get_stats() or {}
                        if isinstance(raw, dict):
                            backend = raw.get("backend") if isinstance(raw.get("backend"), dict) else {}
                            quality = raw.get("quality") if isinstance(raw.get("quality"), dict) else {}
                            by_layer = quality.get("by_layer") if isinstance(quality.get("by_layer"), dict) else {}
                            by_category = quality.get("by_category") if isinstance(quality.get("by_category"), dict) else {}
                            stats["short_term_count"] = int(
                                by_layer.get("working", 0)
                                or backend.get("by_layer", {}).get("working", 0)
                                or raw.get("short_term_count", raw.get("short_term", 0))
                                or 0
                            )
                            stats["long_term_count"] = int(
                                by_layer.get("experience", 0)
                                or backend.get("by_layer", {}).get("experience", 0)
                                or raw.get("long_term_count", raw.get("long_term", 0))
                                or 0
                            )
                            stats["trade_records"] = int(
                                quality.get("trade_record_total", 0)
                                or by_category.get("trade_record", 0)
                                or backend.get("by_category", {}).get("trade_record", 0)
                                or raw.get("trade_records", raw.get("trades", 0))
                                or 0
                            )
                            stats["risk_events"] = int(
                                by_category.get("risk_event", 0)
                                or backend.get("by_category", {}).get("risk_event", 0)
                                or raw.get("risk_events", raw.get("risks", 0))
                                or 0
                            )
                    except Exception:
                        pass
                # 兼容旧版内存管理器(list字段)与新版网关(get_stats接口)
                if stats["short_term_count"] == 0 and hasattr(mem, "get_stats"):
                    try:
                        raw = mem.get_stats() or {}
                        if isinstance(raw, dict):
                            stats["short_term_count"] = int(raw.get("short_term_count", raw.get("short_term", 0)) or 0)
                            stats["long_term_count"] = int(raw.get("long_term_count", raw.get("long_term", 0)) or 0)
                            stats["trade_records"] = int(raw.get("trade_records", raw.get("trades", 0)) or 0)
                            stats["risk_events"] = int(raw.get("risk_events", raw.get("risks", 0)) or 0)
                    except Exception:
                        pass
                if stats["short_term_count"] == 0 and hasattr(mem, "short_term_memory"):
                    try:
                        stats["short_term_count"] = len(getattr(mem, "short_term_memory") or [])
                    except Exception:
                        pass
                if stats["long_term_count"] == 0 and hasattr(mem, "long_term_memory"):
                    try:
                        stats["long_term_count"] = len(getattr(mem, "long_term_memory") or [])
                    except Exception:
                        pass
        
        return stats

    @router.get("/stop-loss/stats")
    async def get_stop_loss_stats():
        """获取止盈止损跟踪统计"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        try:
            slm = getattr(main_controller, "stop_loss_manager", None)
            if not slm:
                return {"success": False, "message": "止盈止损管理器未初始化"}
            data = slm.get_stats() if hasattr(slm, "get_stats") else {}
            return {"success": True, "stats": data or {}}
        except Exception as e:
            return {"success": False, "message": f"读取止盈止损统计失败: {e}"}

    @router.get("/stop-loss/active-orders")
    async def get_stop_loss_active_orders(limit: int = 50):
        """获取当前活动 SLTP 订单明细（用于前端展示“有止损/止盈”）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        try:
            slm = getattr(main_controller, "stop_loss_manager", None)
            if not slm:
                return {"success": False, "message": "止盈止损管理器未初始化"}
            if not hasattr(slm, "get_all_active_orders"):
                return {"success": False, "message": "止盈止损明细接口不可用"}
            orders = await slm.get_all_active_orders()
            rows = []
            for o in (orders or [])[: max(0, int(limit or 50))]:
                try:
                    rows.append(o.to_dict() if hasattr(o, "to_dict") else dict(o))
                except Exception:
                    continue
            return {"success": True, "data": rows, "count": len(rows), "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": f"读取活动 SLTP 订单失败: {e}"}

    @router.get("/stop-loss/profit-protect-debug")
    async def get_stop_loss_profit_protect_debug(limit: int = 30):
        """调试盈利保护加速器：配置 + 活跃订单的生效参数。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        try:
            slm = getattr(main_controller, "stop_loss_manager", None)
            if not slm:
                return {"success": False, "message": "止盈止损管理器未初始化"}
            cfg = getattr(slm, "config", None)
            cfg_out: Dict[str, Any] = {}
            if cfg is not None:
                try:
                    cfg_out = {
                        "profit_protect_accelerator_enable": bool(getattr(cfg, "profit_protect_accelerator_enable", False)),
                        "profit_protect_trigger_1": float(getattr(cfg, "profit_protect_trigger_1", 0.0) or 0.0),
                        "profit_protect_lock_1": float(getattr(cfg, "profit_protect_lock_1", 0.0) or 0.0),
                        "profit_protect_trigger_2": float(getattr(cfg, "profit_protect_trigger_2", 0.0) or 0.0),
                        "profit_protect_lock_2": float(getattr(cfg, "profit_protect_lock_2", 0.0) or 0.0),
                        "profit_protect_tighten_factor": float(getattr(cfg, "profit_protect_tighten_factor", 0.0) or 0.0),
                        "profit_protect_regime_overrides": dict(getattr(cfg, "profit_protect_regime_overrides", {}) or {}),
                    }
                except Exception:
                    cfg_out = {}
            if not hasattr(slm, "get_all_active_orders"):
                return {
                    "success": True,
                    "config": cfg_out,
                    "data": [],
                    "count": 0,
                    "message": "止盈止损明细接口不可用",
                    "timestamp": datetime.now().isoformat(),
                }
            orders = await slm.get_all_active_orders()
            rows: List[Dict[str, Any]] = []
            for o in (orders or [])[: max(0, int(limit or 30))]:
                try:
                    obj = o.to_dict() if hasattr(o, "to_dict") else dict(o)
                except Exception:
                    continue
                md = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
                gp = md.get("guard_profile") if isinstance(md.get("guard_profile"), dict) else {}
                rows.append(
                    {
                        "order_id": obj.get("order_id"),
                        "symbol": obj.get("symbol"),
                        "side": obj.get("side"),
                        "entry_price": obj.get("entry_price"),
                        "current_price": obj.get("current_price"),
                        "stop_loss_price": obj.get("stop_loss_price"),
                        "trailing_stop_offset": obj.get("trailing_stop_offset"),
                        "regime": (
                            md.get("profit_protect_regime")
                            or gp.get("regime")
                            or gp.get("profile")
                            or "unknown"
                        ),
                        "profit_protect_stage": md.get("profit_protect_stage"),
                        "profit_protect_lock_pct": md.get("profit_protect_lock_pct"),
                        "profit_protect_trigger_1_effective": md.get("profit_protect_trigger_1_effective"),
                        "profit_protect_trigger_2_effective": md.get("profit_protect_trigger_2_effective"),
                        "profit_protect_tighten_effective": md.get("profit_protect_tighten_effective"),
                        "profit_protect_applied_at": md.get("profit_protect_applied_at"),
                    }
                )
            return {
                "success": True,
                "config": cfg_out,
                "data": rows,
                "count": len(rows),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": f"读取盈利保护调试信息失败: {e}"}

    @router.get("/profit/ops-overview")
    async def get_profit_ops_overview(
        days: int = 30,
        sample_limit: int = 200,
        active_order_limit: int = 20,
    ):
        """盈利运营一屏视图：归因 + 健康度 + 盈利保护调试。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        try:
            # 1) AI execution guards snapshot
            ai_guard = {}
            try:
                ai_core = getattr(main_controller, "ai_core", None)
                st = ai_core.get_status() if ai_core and hasattr(ai_core, "get_status") else {}
                ai_guard = (st or {}).get("execution_guards", {}) if isinstance(st, dict) else {}
            except Exception:
                ai_guard = {}

            # 2) Trade history / attribution & readiness
            trade_service = getattr(main_controller, "trade_history_service", None)
            regime_rows: List[Dict[str, Any]] = []
            health = {
                "sample": {"total": 0, "with_regime": 0, "with_effective_qty_factor": 0, "nonzero_pnl": 0, "nonzero_pnl_percent": 0},
                "coverage": {"regime_coverage": 0.0, "qty_factor_coverage": 0.0, "nonzero_pnl_coverage": 0.0, "nonzero_pnl_percent_coverage": 0.0},
                "readiness": {"ready_for_regime_tuning": False, "rules": {"min_samples": 20, "min_regime_coverage": 0.6, "min_nonzero_pnl_coverage": 0.5}},
            }
            if trade_service and hasattr(trade_service, "get_trade_history"):
                start_date = datetime.now() - timedelta(days=max(1, int(days or 30)))
                rows = await trade_service.get_trade_history(start_date=start_date, limit=max(50, int(sample_limit or 2000)))
                clean_rows: List[Dict[str, Any]] = []
                for r in (rows or []):
                    if not isinstance(r, dict):
                        continue
                    md = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
                    src = str((md.get("source") or r.get("source") or "")).strip().lower()
                    if src == "db_bootstrap":
                        continue
                    pnl = float(r.get("pnl", 0) or 0)
                    pnl_pct = float(r.get("pnl_percent", 0) or 0)
                    if not (abs(pnl) > 1e-12 or abs(pnl_pct) > 1e-12):
                        continue
                    clean_rows.append(r)

                def _infer_regime_from_trade(r: Dict[str, Any]) -> Dict[str, Any]:
                    md = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
                    mkt = md.get("market_context") if isinstance(md.get("market_context"), dict) else {}
                    direct = (
                        mkt.get("regime")
                        or md.get("regime")
                        or md.get("market_regime")
                        or r.get("market_regime")
                        or ""
                    )
                    direct_s = str(direct or "").strip().lower()
                    if direct_s and direct_s != "unknown":
                        return {"regime": direct_s, "inferred": False}

                    strategy = str(
                        md.get("strategy_id")
                        or md.get("strategy_used")
                        or r.get("strategy")
                        or ""
                    ).strip().lower()
                    reasoning = str(r.get("reasoning") or "").strip().lower()
                    text = f"{strategy} {reasoning}"
                    if any(k in text for k in ("trend", "breakout", "momentum", "bull", "bear")):
                        return {"regime": "trend", "inferred": True}
                    if any(k in text for k in ("support", "resistance", "mean_reversion", "sr_near")):
                        return {"regime": "range", "inferred": True}
                    if any(k in text for k in ("stop_loss", "volatility", "spike")):
                        return {"regime": "volatile", "inferred": True}
                    return {"regime": "unknown", "inferred": False}

                # Attribution grouped by regime
                grp: Dict[str, Dict[str, Any]] = {}
                with_regime = 0
                with_qf = 0
                nonzero_pnl = 0
                nonzero_pnl_pct = 0
                for r in clean_rows:
                    md = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
                    mkt = md.get("market_context") if isinstance(md.get("market_context"), dict) else {}
                    regime = str((_infer_regime_from_trade(r) or {}).get("regime") or "unknown").strip().lower() or "unknown"
                    if regime and regime != "unknown":
                        with_regime += 1
                    if mkt.get("effective_qty_factor") is not None:
                        with_qf += 1
                    pnl = float(r.get("pnl", 0) or 0)
                    pnl_pct = float(r.get("pnl_percent", 0) or 0)
                    if abs(pnl) > 1e-12:
                        nonzero_pnl += 1
                    if abs(pnl_pct) > 1e-12:
                        nonzero_pnl_pct += 1

                    g = grp.get(regime)
                    if not g:
                        g = {
                            "regime": regime,
                            "total_trades": 0,
                            "winning_trades": 0,
                            "losing_trades": 0,
                            "total_pnl": 0.0,
                            "total_fees": 0.0,
                            "sum_qty_factor": 0.0,
                            "qty_factor_count": 0,
                            "sum_pnl_percent": 0.0,
                            "pnl_percent_count": 0,
                            "gross_profit": 0.0,
                            "gross_loss": 0.0,
                        }
                        grp[regime] = g
                    g["total_trades"] += 1
                    g["total_pnl"] += pnl
                    g["total_fees"] += float(r.get("fee", 0) or 0)
                    qf = float(mkt.get("effective_qty_factor", 1.0) or 1.0)
                    g["sum_qty_factor"] += qf
                    g["qty_factor_count"] += 1
                    if abs(pnl_pct) > 1e-12:
                        g["sum_pnl_percent"] += pnl_pct
                        g["pnl_percent_count"] += 1
                    if pnl > 0:
                        g["winning_trades"] += 1
                        g["gross_profit"] += pnl
                    elif pnl < 0:
                        g["losing_trades"] += 1
                        g["gross_loss"] += abs(pnl)

                for regime, g in grp.items():
                    total = int(g["total_trades"])
                    win_rate = (int(g["winning_trades"]) / total) if total else 0.0
                    pf = (float(g["gross_profit"]) / float(g["gross_loss"])) if float(g["gross_loss"]) > 0 else (9999.0 if float(g["gross_profit"]) > 0 else 0.0)
                    expectancy = float(g["total_pnl"]) / total if total else 0.0
                    regime_rows.append(
                        {
                            "regime": regime,
                            "total_trades": total,
                            "winning_trades": int(g["winning_trades"]),
                            "losing_trades": int(g["losing_trades"]),
                            "win_rate": round(win_rate * 100, 2),
                            "profit_factor": round(float(pf), 4),
                            "expectancy": round(float(expectancy), 6),
                            "total_pnl": round(float(g["total_pnl"]), 6),
                            "total_fees": round(float(g["total_fees"]), 6),
                            "avg_pnl_percent": round(float(g["sum_pnl_percent"]) / max(1, int(g["pnl_percent_count"])), 6),
                            "avg_effective_qty_factor": round(float(g["sum_qty_factor"]) / max(1, int(g["qty_factor_count"])), 6),
                        }
                    )
                regime_rows.sort(key=lambda x: x.get("total_trades", 0), reverse=True)

                total = len(clean_rows)
                regime_cov = (with_regime / total) if total else 0.0
                qty_cov = (with_qf / total) if total else 0.0
                pnl_cov = (nonzero_pnl / total) if total else 0.0
                pnl_pct_cov = (nonzero_pnl_pct / total) if total else 0.0
                ready = bool(total >= 20 and regime_cov >= 0.6 and pnl_cov >= 0.5)
                health = {
                    "sample": {
                        "total": int(total),
                        "with_regime": int(with_regime),
                        "with_effective_qty_factor": int(with_qf),
                        "nonzero_pnl": int(nonzero_pnl),
                        "nonzero_pnl_percent": int(nonzero_pnl_pct),
                    },
                    "coverage": {
                        "regime_coverage": round(regime_cov, 4),
                        "qty_factor_coverage": round(qty_cov, 4),
                        "nonzero_pnl_coverage": round(pnl_cov, 4),
                        "nonzero_pnl_percent_coverage": round(pnl_pct_cov, 4),
                    },
                    "readiness": {
                        "ready_for_regime_tuning": ready,
                        "rules": {"min_samples": 20, "min_regime_coverage": 0.6, "min_nonzero_pnl_coverage": 0.5},
                    },
                }

            # 3) Profit protect debug summary
            protect_cfg: Dict[str, Any] = {}
            protect_orders: List[Dict[str, Any]] = []
            slm = getattr(main_controller, "stop_loss_manager", None)
            if slm:
                cfg = getattr(slm, "config", None)
                if cfg is not None:
                    try:
                        protect_cfg = {
                            "profit_protect_accelerator_enable": bool(getattr(cfg, "profit_protect_accelerator_enable", False)),
                            "profit_protect_trigger_1": float(getattr(cfg, "profit_protect_trigger_1", 0.0) or 0.0),
                            "profit_protect_lock_1": float(getattr(cfg, "profit_protect_lock_1", 0.0) or 0.0),
                            "profit_protect_trigger_2": float(getattr(cfg, "profit_protect_trigger_2", 0.0) or 0.0),
                            "profit_protect_lock_2": float(getattr(cfg, "profit_protect_lock_2", 0.0) or 0.0),
                            "profit_protect_tighten_factor": float(getattr(cfg, "profit_protect_tighten_factor", 0.0) or 0.0),
                            "profit_protect_regime_overrides": dict(getattr(cfg, "profit_protect_regime_overrides", {}) or {}),
                        }
                    except Exception:
                        protect_cfg = {}
                if hasattr(slm, "get_all_active_orders"):
                    orders = await slm.get_all_active_orders()
                    for o in (orders or [])[: max(0, int(active_order_limit or 20))]:
                        try:
                            obj = o.to_dict() if hasattr(o, "to_dict") else dict(o)
                        except Exception:
                            continue
                        md = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
                        gp = md.get("guard_profile") if isinstance(md.get("guard_profile"), dict) else {}
                        protect_orders.append(
                            {
                                "order_id": obj.get("order_id"),
                                "symbol": obj.get("symbol"),
                                "side": obj.get("side"),
                                "regime": md.get("profit_protect_regime") or gp.get("regime") or gp.get("profile") or "unknown",
                                "profit_protect_stage": md.get("profit_protect_stage"),
                                "profit_protect_lock_pct": md.get("profit_protect_lock_pct"),
                                "profit_protect_trigger_1_effective": md.get("profit_protect_trigger_1_effective"),
                                "profit_protect_trigger_2_effective": md.get("profit_protect_trigger_2_effective"),
                                "profit_protect_tighten_effective": md.get("profit_protect_tighten_effective"),
                            }
                        )

            return {
                "success": True,
                "ok": True,
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "days": int(days or 30),
                "profit_attribution": {
                    "regime": regime_rows,
                    "health": health,
                },
                "profit_protect_debug": {
                    "config": protect_cfg,
                    "active_orders": protect_orders,
                    "active_count": len(protect_orders),
                },
                "execution_guards": {
                    "config": (ai_guard.get("config") or {}) if isinstance(ai_guard, dict) else {},
                    "adaptive_profile": (ai_guard.get("adaptive_profile") or {}) if isinstance(ai_guard, dict) else {},
                    "stats": (ai_guard.get("stats") or {}) if isinstance(ai_guard, dict) else {},
                },
            }
        except Exception as e:
            return {"success": False, "message": f"读取盈利运营总览失败: {e}"}

    @router.get("/stop-loss/config")
    async def get_stop_loss_config():
        """获取 SLTP 配置（分层止盈/移动止盈/移动止损参数）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        try:
            slm = getattr(main_controller, "stop_loss_manager", None)
            if not slm:
                return {"success": False, "message": "止盈止损管理器未初始化"}
            cfg = getattr(slm, "config", None)
            if cfg is None:
                return {"success": True, "data": {}, "timestamp": datetime.now().isoformat()}
            # dataclass friendly
            try:
                from dataclasses import asdict

                data = asdict(cfg)
            except Exception:
                data = dict(cfg) if isinstance(cfg, dict) else {"repr": repr(cfg)}
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": f"读取 SLTP 配置失败: {e}"}
    
    @router.get("/system/health")
    async def get_system_health():
        """获取系统健康状态"""
        health = {
            "overall": "healthy",
            "modules": {},
            "timestamp": datetime.now().isoformat()
        }
        
        if main_controller:
            modules_to_check = [
                ("ai_trading_engine", "AI交易引擎"),
                ("llm_integration", "AI大模型"),
                ("telegram_bot", "Telegram机器人"),
                ("database_manager", "数据库"),
                ("event_system", "事件系统"),
                ("emergency_stop", "紧急停止"),
                ("security_manager", "安全管理"),
                ("fund_manager", "资金管理")
            ]
            
            healthy_count = 0
            for attr, name in modules_to_check:
                if hasattr(main_controller, attr):
                    module = getattr(main_controller, attr)
                    is_healthy = module is not None
                    health["modules"][name] = {
                        "status": "healthy" if is_healthy else "unavailable",
                        "running": is_healthy
                    }
                    if is_healthy:
                        healthy_count += 1
                else:
                    health["modules"][name] = {
                        "status": "unavailable",
                        "running": False
                    }
            
            total = len(modules_to_check)
            health["overall"] = "healthy" if healthy_count == total else "degraded" if healthy_count > total // 2 else "unhealthy"
            health["healthy_count"] = healthy_count
            health["total_count"] = total
        
        return health

    @router.get("/health")
    async def get_root_health_alias():
        """兼容旧探针：/api/v1/modules/health。"""
        return await get_system_health()

    @router.get("/status")
    async def get_modules_status_alias():
        """兼容旧探针：/api/v1/modules/status。"""
        if not main_controller or not hasattr(main_controller, "get_system_status"):
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        try:
            data = await main_controller.get_system_status()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/strategy/optimization-status")
    async def get_strategy_optimization_status():
        """
        预留给前端的策略优化状态接口：
        - 策略池总量/上限
        - 每日优化进度与结果
        - 最近一次策略池清理时间
        """
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            sm = main_controller.strategy_manager
            if hasattr(sm, "get_optimization_status"):
                data = sm.get_optimization_status()
            else:
                data = {
                    "pool_limit": 30,
                    "total_strategies": len(getattr(sm, "strategy_configs", {}) or {}),
                    "daily_optimization": {},
                    "last_daily_optimization_date": None,
                    "last_pool_prune_at": None,
                }
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": f"读取策略优化状态失败: {e}"}

    @router.post("/strategy/optimization-config")
    async def update_strategy_optimization_config(config: Dict[str, Any]):
        """热更新策略优化运行参数（前端可直接调用）。"""
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            sm = main_controller.strategy_manager
            if not hasattr(sm, "update_optimization_runtime_config"):
                return {"success": False, "message": "当前策略管理器不支持热更新优化参数"}
            applied = sm.update_optimization_runtime_config(config or {})
            return {
                "success": True,
                "message": "策略优化参数已更新",
                "applied": applied,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": f"更新策略优化参数失败: {e}"}

    @router.get("/strategy/optimization-config")
    async def get_strategy_optimization_config():
        """读取当前策略优化运行参数。"""
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            sm = main_controller.strategy_manager
            status = sm.get_optimization_status() if hasattr(sm, "get_optimization_status") else {}
            return {
                "success": True,
                "config": (status.get("runtime_config", {}) if isinstance(status, dict) else {}),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": f"读取策略优化参数失败: {e}"}

    @router.post("/strategy/optimize-now")
    async def trigger_strategy_optimization_now():
        """手动触发一次每日优化批次（用于运维/验收）。"""
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            gate = await _check_unified_data_quality(symbol="BTC/USDT", min_score=0.45)
            if not gate.get("ok", True):
                await _notify_quality_warning("优化任务低质量放行（AI自主判断）", gate)
            sm = main_controller.strategy_manager
            if hasattr(sm, "trigger_daily_optimization_now"):
                out = await sm.trigger_daily_optimization_now()
                if isinstance(out, dict):
                    out["quality_gate"] = gate
                return out
            await sm._run_daily_strategy_optimization()  # type: ignore[attr-defined]
            return {"success": True, "message": "已触发每日优化批次", "quality_gate": gate}
        except Exception as e:
            return {"success": False, "message": f"触发每日优化失败: {e}"}

    @router.post("/strategy/trade-feedback")
    async def submit_strategy_trade_feedback(payload: Dict[str, Any]):
        """
        提交交易结果反馈，驱动策略参数自适应收敛并可联动优化批次。
        body: strategy_id, pnl, win_rate?, max_drawdown?, total_trades?, force_optimize?
        """
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            gate = await _check_unified_data_quality(symbol=str(payload.get("symbol") or "BTC/USDT"), min_score=0.4)
            if not gate.get("ok", True):
                await _notify_quality_warning("交易反馈低质量放行（AI自主判断）", gate)
            sm = main_controller.strategy_manager
            strategy_id = str(payload.get("strategy_id") or "").strip()
            if not strategy_id:
                return {"success": False, "message": "strategy_id 不能为空"}
            pnl = float(payload.get("pnl", 0.0) or 0.0)
            win_rate = payload.get("win_rate")
            max_drawdown = payload.get("max_drawdown")
            total_trades = payload.get("total_trades")
            force_optimize = bool(payload.get("force_optimize", False))
            if hasattr(sm, "apply_trade_feedback"):
                out = await sm.apply_trade_feedback(
                    strategy_id=strategy_id,
                    pnl=pnl,
                    win_rate=win_rate,
                    max_drawdown=max_drawdown,
                    total_trades=total_trades,
                    force_optimize=force_optimize,
                )
                return {"success": True, "data": out, "quality_gate": gate, "timestamp": datetime.now().isoformat()}
            return {"success": False, "message": "当前策略管理器不支持交易反馈优化"}
        except Exception as e:
            return {"success": False, "message": f"提交交易反馈失败: {e}"}

    @router.get("/execution/production-audit")
    async def get_production_execution_audit():
        """
        生产执行链路审查：
        开仓、平仓、止盈、止损、跟踪止损、交易所连通、执行网关状态。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        mc = main_controller
        out: Dict[str, Any] = {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "checks": {},
        }
        try:
            gw = getattr(mc, "execution_gateway", None)
            out["checks"]["execution_gateway"] = bool(gw is not None)
            if gw:
                out["execution_spine"] = await gw.get_snapshot()

            ex = mc.get_exchange() if hasattr(mc, "get_exchange") else None
            out["checks"]["exchange_connected"] = bool(ex is not None)

            slm = getattr(mc, "stop_loss_manager", None)
            out["checks"]["stop_loss_manager"] = bool(slm is not None)
            if slm:
                stats = slm.get_stats()
                out["sltp_stats"] = stats
                out["checks"]["dynamic_market_adjustment"] = bool(
                    getattr(slm.config, "enable_dynamic_market_adjustment", False)
                )
                out["checks"]["trailing_stop_enabled"] = bool(
                    getattr(slm.config, "enable_trailing_stop", False)
                )
                out["checks"]["execute_exchange_on_trigger"] = bool(
                    getattr(slm.config, "execute_exchange_on_trigger", False)
                )
                active_orders = await slm.get_all_active_orders()
                out["active_orders"] = [o.to_dict() for o in active_orders[:20]]

            return out
        except Exception as e:
            return {"success": False, "message": f"生产执行审查失败: {e}", "timestamp": datetime.now().isoformat()}

    @router.post("/strategy/research-run")
    async def run_strategy_research_now(payload: Optional[Dict[str, Any]] = Body(None)):
        """
        手动触发策略研发流水线（walk-forward + 门控），不受「有持仓则跳过」限制。
        可选 JSON：symbols, timeframe, lookback_days, timeout_seconds, max_symbols
        """
        payload = payload or {}
        raw_symbols = payload.get("symbols") or ["BTC/USDT"]
        if isinstance(raw_symbols, str):
            gate_symbol = raw_symbols
        elif isinstance(raw_symbols, list) and raw_symbols:
            gate_symbol = str(raw_symbols[0])
        else:
            gate_symbol = "BTC/USDT"
        gate = await _check_unified_data_quality(
            symbol=gate_symbol,
            min_score=float(payload.get("min_data_quality", 0.5) or 0.5),
        )
        if not gate.get("ok", True):
            await _notify_quality_warning("研究任务低质量放行（AI自主判断）", gate)
        job_id = f"research_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        job = {
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.now().isoformat(),
            "payload": payload,
            "result": None,
            "message": "",
            "started_at": None,
            "finished_at": None,
        }
        async with research_jobs_lock:
            research_jobs[job_id] = job
            # 控制历史长度，避免内存无限增长
            if len(research_jobs) > 50:
                old_keys = sorted(
                    research_jobs.keys(),
                    key=lambda k: research_jobs[k].get("created_at", "")
                )[:-50]
                for k in old_keys:
                    research_jobs.pop(k, None)
        asyncio.create_task(_run_research_job(job_id, payload))
        return {
            "success": True,
            "message": "策略研究任务已提交后台执行",
            "job_id": job_id,
            "status": "queued",
            "quality_gate": gate,
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/strategy/research-jobs")
    async def list_strategy_research_jobs(limit: int = 20):
        """查询最近策略研究任务列表。"""
        safe_limit = max(1, min(int(limit), 100))
        async with research_jobs_lock:
            jobs = sorted(
                research_jobs.values(),
                key=lambda x: x.get("created_at", ""),
                reverse=True,
            )[:safe_limit]
        return {"success": True, "jobs": jobs, "timestamp": datetime.now().isoformat()}

    @router.get("/strategy/research-jobs/{job_id}")
    async def get_strategy_research_job(job_id: str):
        """查询单个策略研究任务状态。"""
        async with research_jobs_lock:
            job = research_jobs.get(job_id)
        if not job:
            return {"success": False, "message": "任务不存在", "job_id": job_id}
        return {"success": True, "job": job, "timestamp": datetime.now().isoformat()}

    @router.get("/strategy/research-profile/{strategy_id}")
    async def get_strategy_research_profile(strategy_id: str):
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        sm = main_controller.strategy_manager
        if not hasattr(sm, "get_strategy_research_profile"):
            return {"success": False, "message": "当前策略管理器不支持研究画像"}
        return {"success": True, "data": sm.get_strategy_research_profile(strategy_id), "timestamp": datetime.now().isoformat()}

    @router.post("/strategy/research-profile/{strategy_id}/experiment-card")
    async def save_strategy_experiment_card_api(strategy_id: str, payload: Dict[str, Any] = Body(default_factory=dict)):
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        sm = main_controller.strategy_manager
        if not hasattr(sm, "save_strategy_experiment_card"):
            return {"success": False, "message": "当前策略管理器不支持实验卡"}
        hypothesis = str((payload or {}).get("hypothesis") or "").strip()
        if not hypothesis:
            return {"success": False, "message": "hypothesis 不能为空"}
        ok = sm.save_strategy_experiment_card(
            strategy_id,
            hypothesis=hypothesis,
            experiment_card=dict((payload or {}).get("experiment_card") or {}),
        )
        return {"success": bool(ok), "strategy_id": strategy_id, "timestamp": datetime.now().isoformat()}

    @router.post("/strategy/research-profile/{strategy_id}/peer-review")
    async def save_strategy_peer_review_api(strategy_id: str, payload: Dict[str, Any] = Body(default_factory=dict)):
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        sm = main_controller.strategy_manager
        if not hasattr(sm, "record_strategy_peer_review"):
            return {"success": False, "message": "当前策略管理器不支持同伴评审"}
        ok = sm.record_strategy_peer_review(
            strategy_id,
            answers=dict((payload or {}).get("answers") or {}),
            action_items=list((payload or {}).get("action_items") or []),
            status=str((payload or {}).get("status") or "completed"),
        )
        return {
            "success": bool(ok),
            "message": "missing required peer review answers" if not ok else "peer review saved",
            "strategy_id": strategy_id,
            "timestamp": datetime.now().isoformat(),
        }

    @router.post("/strategy/research-profile/{strategy_id}/failure-case")
    async def save_strategy_failure_case_api(strategy_id: str, payload: Dict[str, Any] = Body(default_factory=dict)):
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        sm = main_controller.strategy_manager
        if not hasattr(sm, "record_strategy_failure_case"):
            return {"success": False, "message": "当前策略管理器不支持失败案例"}
        title = str((payload or {}).get("title") or "").strip()
        summary = str((payload or {}).get("summary") or "").strip()
        if not title or not summary:
            return {"success": False, "message": "title 和 summary 不能为空"}
        ok = sm.record_strategy_failure_case(
            strategy_id,
            title=title,
            case_type=str((payload or {}).get("case_type") or "execution_failure"),
            summary=summary,
            trigger=str((payload or {}).get("trigger") or ""),
            action_taken=str((payload or {}).get("action_taken") or ""),
            metadata=dict((payload or {}).get("metadata") or {}),
        )
        return {"success": bool(ok), "strategy_id": strategy_id, "timestamp": datetime.now().isoformat()}

    @router.post("/strategy/research-profile/{strategy_id}/parameter-sensitivity")
    async def save_strategy_parameter_sensitivity_api(strategy_id: str, payload: Dict[str, Any] = Body(default_factory=dict)):
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        sm = main_controller.strategy_manager
        if not hasattr(sm, "save_strategy_parameter_sensitivity"):
            return {"success": False, "message": "当前策略管理器不支持参数敏感性摘要"}
        ok = sm.save_strategy_parameter_sensitivity(
            strategy_id,
            parameter_sensitivity=dict((payload or {}).get("parameter_sensitivity") or {}),
        )
        return {"success": bool(ok), "strategy_id": strategy_id, "timestamp": datetime.now().isoformat()}

    @router.get("/memory/daily-summary")
    async def get_memory_daily_summary(limit: int = 6):
        """
        获取每日复盘摘要（用于前端卡片与TG快速查看）。
        """
        safe_limit = max(1, min(int(limit), 20))
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        gateway = getattr(main_controller, "memory_gateway", None)
        if not gateway:
            return {"success": False, "message": "记忆网关不可用"}
        try:
            rows = await gateway.recall(query="每日交易复盘 自动总结", limit=safe_limit, min_importance=0.5)
            data: List[Dict[str, Any]] = []
            for r in rows:
                data.append(
                    {
                        "id": getattr(r, "id", None),
                        "content": getattr(r, "content", ""),
                        "importance": getattr(r, "importance", None),
                        "timestamp": getattr(r, "timestamp", None),
                        "metadata": getattr(r, "metadata", {}) if hasattr(r, "metadata") else {},
                    }
                )
            # 兜底：部分情况下召回模型可能漏召回，直接从内存后端筛选“每日复盘”类记录。
            if not data:
                backend = getattr(gateway, "memory_backend", None)
                memories = getattr(backend, "_memories", {}) if backend else {}
                fallback_rows: List[Dict[str, Any]] = []
                for mid, entry in (memories or {}).items():
                    try:
                        content = str(getattr(entry, "content", "") or "")
                        metadata = getattr(entry, "metadata", {}) or {}
                        src = str(metadata.get("source_module") or "")
                        if ("每日交易复盘" in content) or ("复盘" in content and src == "ai_command_executor"):
                            fallback_rows.append(
                                {
                                    "id": mid,
                                    "content": content,
                                    "importance": float(getattr(entry, "importance", 0.0) or 0.0),
                                    "timestamp": (
                                        getattr(entry, "created_at", None).isoformat()
                                        if getattr(entry, "created_at", None) is not None
                                        else None
                                    ),
                                    "metadata": metadata,
                                }
                            )
                    except Exception:
                        continue
                fallback_rows = sorted(
                    fallback_rows,
                    key=lambda x: str(x.get("timestamp") or ""),
                    reverse=True,
                )[:safe_limit]
                data = fallback_rows
            return {"success": True, "data": data, "count": len(data), "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/memory/daily-summary/run")
    async def run_memory_daily_summary():
        """
        手动触发一次每日复盘写入（AI执行器路径）。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        exe = getattr(main_controller, "ai_command_executor", None)
        if not exe or not hasattr(exe, "_auto_daily_summary"):
            return {"success": False, "message": "AI执行器不可用"}
        try:
            ok = await exe._auto_daily_summary(force=True)
            return {
                "success": bool(ok),
                "message": "已触发每日复盘写入" if ok else "每日复盘写入失败",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    async def _build_commander_fast_snapshot(symbol: str = "BTC/USDT") -> Dict[str, Any]:
        """快速快照：优先返回核心状态，避免重聚合阻塞。"""
        out: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "mode": "fast",
            "system": {},
            "strategy": {},
            "execution": {},
            "risk": {},
            "account": {},
            "data_hub": {"symbol": symbol},
            "alerts": [],
        }
        mc = main_controller
        if not mc:
            return out
        FAST_TIMEOUT_S = 4.0
        try:
            st = await asyncio.wait_for(mc.get_system_status(), timeout=FAST_TIMEOUT_S)
            out["system"] = {
                "system_status": st.get("system_status"),
                "module_count": st.get("module_count"),
                "running_modules": st.get("running_modules"),
            }
            if hasattr(mc, "get_hosting_mode"):
                out["system"]["hosting_mode"] = mc.get_hosting_mode()
        except Exception as e:
            out["alerts"].append(f"系统状态读取失败: {e}")

        try:
            sm = getattr(mc, "strategy_manager", None)
            if sm and hasattr(sm, "get_optimization_status"):
                s = sm.get_optimization_status()
                out["strategy"] = {
                    "total_strategies": s.get("total_strategies"),
                    "pool_limit": s.get("pool_limit"),
                    "daily_optimization": s.get("daily_optimization"),
                    "deployment_stage_counts": s.get("deployment_stage_counts"),
                }
        except Exception as e:
            out["alerts"].append(f"策略状态读取失败: {e}")

        try:
            gw = getattr(mc, "execution_gateway", None)
            if gw and hasattr(gw, "get_snapshot"):
                out["execution"] = await asyncio.wait_for(gw.get_snapshot(), timeout=FAST_TIMEOUT_S)
        except Exception as e:
            out["alerts"].append(f"执行网关快照失败: {e}")

        try:
            slm = getattr(mc, "stop_loss_manager", None)
            if slm and hasattr(slm, "get_stats"):
                out["risk"]["sltp"] = slm.get_stats()
        except Exception as e:
            out["alerts"].append(f"SLTP统计读取失败: {e}")

        # 账户/持仓（快速版）：只读缓存，避免因交易所/网络抖动导致快照阻塞。
        try:
            st = getattr(mc, "_latest_account_state", None)
            if isinstance(st, dict) and st.get("timestamp"):
                try:
                    raw = str(st["timestamp"]).replace("Z", "")
                    t0 = datetime.fromisoformat(raw[:26])
                    if (datetime.now() - t0).total_seconds() > 45:
                        out["alerts"].append("account_state_stale>45s")
                except Exception:
                    pass
            st = st if isinstance(st, dict) else {}
            out["account"] = {
                "balance": st.get("balance"),
                "positions": st.get("positions"),
                "synced_at": st.get("timestamp"),
            }
            # Fallback: when cache is stale/empty, use ai_trading_engine in-memory positions to avoid false "0 positions".
            if not isinstance(out["account"].get("positions"), list):
                out["account"]["positions"] = []
            if len(out["account"]["positions"]) == 0:
                te = getattr(mc, "ai_trading_engine", None)
                te_pos = getattr(te, "positions", {}) if te else {}
                if isinstance(te_pos, dict) and te_pos:
                    rebuilt: List[Dict[str, Any]] = []
                    for sym, p in te_pos.items():
                        try:
                            rebuilt.append(
                                {
                                    "symbol": getattr(p, "symbol", sym),
                                    "side": getattr(p, "side", None),
                                    "size": float(getattr(p, "quantity", 0.0) or 0.0),
                                    "entry_price": float(getattr(p, "entry_price", 0.0) or 0.0),
                                    "mark_price": float(getattr(p, "current_price", 0.0) or 0.0),
                                    "unrealized_pnl": float(getattr(p, "unrealized_pnl", 0.0) or 0.0),
                                }
                            )
                        except Exception:
                            continue
                    out["account"]["positions"] = rebuilt
                    out["account"]["synced_at"] = datetime.now().isoformat()
                    out["alerts"].append("account_positions_from_ai_trading_engine_fallback")
            # Last fallback: short direct exchange pull (non-blocking timeout) for fast snapshot correctness.
            if len(out["account"]["positions"]) == 0:
                try:
                    ex = mc.get_exchange() if hasattr(mc, "get_exchange") else None
                    if ex and hasattr(ex, "get_positions"):
                        raw_positions = await asyncio.wait_for(ex.get_positions(), timeout=2.5)
                        rebuilt2: List[Dict[str, Any]] = []
                        for p in raw_positions or []:
                            if not isinstance(p, dict):
                                continue
                            try:
                                sz = float(p.get("size", p.get("pos", 0)) or 0)
                            except Exception:
                                sz = 0.0
                            if abs(sz) <= 1e-12:
                                continue
                            rebuilt2.append(
                                {
                                    "symbol": p.get("symbol") or p.get("instId"),
                                    "side": p.get("side"),
                                    "size": sz,
                                    "entry_price": p.get("entry_price"),
                                    "mark_price": p.get("mark_px") or p.get("mark_price"),
                                    "unrealized_pnl": p.get("unrealized_pnl"),
                                }
                            )
                        if rebuilt2:
                            out["account"]["positions"] = rebuilt2
                            out["account"]["synced_at"] = datetime.now().isoformat()
                            out["alerts"].append("account_positions_from_exchange_fallback")
                except Exception:
                    pass
        except Exception:
            pass

        # 仓位管理建议（快速版：仅在能得到可用余额时生成）
        try:
            bal = out.get("account", {}).get("balance") or {}
            usdt = bal.get("USDT", bal.get("usdt", 0)) if isinstance(bal, dict) else 0
            if isinstance(usdt, dict):
                available = usdt.get("free", usdt.get("available", 0))
            else:
                available = usdt
            positions = out.get("account", {}).get("positions") or []
            pos_map: Dict[str, Any] = {}
            if isinstance(positions, list):
                for p in positions:
                    if isinstance(p, dict):
                        sym = p.get("symbol") or p.get("instId") or p.get("instrument_id")
                        if sym:
                            try:
                                v = float(p.get("notional") or p.get("value") or 0)
                            except Exception:
                                v = 0.0
                            pos_map[str(sym)] = {"value": v, **p}
            if available and hasattr(mc, "get_position_recommendations"):
                try:
                    out["risk"]["position_recommendations"] = await asyncio.wait_for(
                        mc.get_position_recommendations(
                            account_balance=float(available),
                            current_positions=pos_map,
                        ),
                        timeout=1.8,
                    )
                except Exception:
                    out["risk"]["position_recommendations"] = out["risk"].get("position_recommendations") or {}
        except Exception:
            pass

        # 数据/分析模块快照（快速版：不触发交易所重型聚合）
        try:
            di = getattr(mc, "data_integration", None)
            if di and hasattr(di, "get_source_health_report"):
                out["data_hub"]["data_integration_health"] = di.get_source_health_report()
        except Exception:
            pass
        try:
            tpi = getattr(mc, "third_party_data_integrator", None)
            if tpi:
                prov = getattr(tpi, "providers", {}) or {}
                disabled = list(getattr(tpi, "_disabled_providers", set()) or [])
                diag: Dict[str, Any] = {}
                if hasattr(tpi, "get_diagnostics"):
                    try:
                        diag = tpi.get_diagnostics()
                    except Exception:
                        diag = {}
                out["data_hub"]["third_party"] = {
                    "provider_count": len(prov),
                    "disabled_count": len(disabled),
                    "diagnostics": diag,
                }
        except Exception:
            pass
        try:
            mi = getattr(mc, "market_intelligence", None) or getattr(mc, "market_intelligence_engine", None)
            if mi:
                cached = mi.get_cached_symbol_view(symbol) if hasattr(mi, "get_cached_symbol_view") else {}
                if cached:
                    out["data_hub"]["market_intelligence"] = cached
                elif hasattr(mi, "get_symbol_view"):
                    view = await asyncio.wait_for(mi.get_symbol_view(symbol, include_snapshot=False), timeout=2.2)
                    out["data_hub"]["market_intelligence"] = view.to_dict() if hasattr(view, "to_dict") else {}
                # Still empty: report warm-up state so caller knows it's connected.
                if not out["data_hub"].get("market_intelligence"):
                    out["data_hub"]["market_intelligence"] = {
                        "status": "warming_up",
                        "hint": "market_intelligence_connected_but_no_cached_view_yet",
                    }
        except Exception:
            out["data_hub"]["market_intelligence"] = out["data_hub"].get("market_intelligence") or {
                "status": "warming_up_or_busy",
            }
        return out

    @router.get("/commander/snapshot")
    async def commander_snapshot(symbol: str = "BTC/USDT", mode: str = "fast"):
        """司令部统一快照：前端/TG/运维可共享。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        if not hasattr(main_controller, "build_ai_commander_snapshot"):
            return {"success": False, "message": "司令部快照能力不可用"}
        try:
            mode_l = str(mode or "fast").strip().lower()
            if mode_l == "full":
                data = await asyncio.wait_for(
                    main_controller.build_ai_commander_snapshot(symbol=symbol),
                    timeout=15.0,
                )
                data["mode"] = "full"
            else:
                data = await asyncio.wait_for(_build_commander_fast_snapshot(symbol=symbol), timeout=8.0)
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except asyncio.TimeoutError:
            return {
                "success": True,
                "data": {
                    "timestamp": datetime.now().isoformat(),
                    "mode": "fast_degraded_timeout",
                    "alerts": ["snapshot_timeout_degraded"],
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/hosting-mode")
    async def commander_get_hosting_mode():
        """获取当前托管模式（full_auto / semi_auto）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_hosting_mode"):
            return {"success": False, "message": "托管模式能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            mode = main_controller.get_hosting_mode()
            return {
                "success": True,
                "data": {
                    "mode": mode,
                    "mode_zh": "全自动" if mode == "full_auto" else "半自动",
                    "description": (
                        "AI全自动托管：系统可自主开平仓并自动风控"
                        if mode == "full_auto"
                        else "半自动托管：策略开仓需人工确认，平仓风控仍自动执行"
                    ),
                    "allowed_values": [
                        {"value": "full_auto", "label": "全自动"},
                        {"value": "semi_auto", "label": "半自动"},
                    ],
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/hosting-guard")
    async def commander_get_hosting_guard():
        """获取托管守护配置与状态（后端自动降级/恢复中枢）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_hosting_guard_status"):
            return {"success": False, "message": "托管守护能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_hosting_guard_status()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/automation-profile")
    async def commander_get_automation_profile():
        """获取自动化协同级别（conservative / semi_auto / full_auto）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_automation_profile"):
            return {"success": False, "message": "自动化级别能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            p = main_controller.get_automation_profile()
            return {"success": True, "data": {"profile": p}, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/automation-profile")
    async def commander_set_automation_profile(payload: Dict[str, Any] = Body(default_factory=dict)):
        """设置自动化协同级别。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "set_automation_profile"):
            return {"success": False, "message": "自动化级别能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            p = str((payload or {}).get("profile") or "").strip()
            current = main_controller.set_automation_profile(p)
            return {"success": True, "data": {"profile": current}, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/risk-redlines")
    async def commander_get_risk_redlines():
        """获取统一风控红线。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_risk_redlines"):
            return {"success": False, "message": "风控红线能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_risk_redlines()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/risk-redlines")
    async def commander_update_risk_redlines(payload: Dict[str, Any] = Body(default_factory=dict)):
        """更新统一风控红线。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "update_risk_redlines"):
            return {"success": False, "message": "风控红线能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.update_risk_redlines(payload or {})
            return {"success": True, "data": data, "message": "风控红线已更新", "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/hosting-guard")
    async def commander_update_hosting_guard(payload: Dict[str, Any] = Body(default_factory=dict)):
        """更新托管守护配置。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "update_hosting_guard_config"):
            return {"success": False, "message": "托管守护能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.update_hosting_guard_config(payload or {})
            return {"success": True, "data": data, "message": "托管守护配置已更新", "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/architecture/layers")
    async def commander_architecture_layers():
        """系统分层架构状态（L1-L5）与托管守护状态。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_architecture_layers_status"):
            return {"success": False, "message": "分层架构状态能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_architecture_layers_status()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/upgrade/benchmark")
    async def commander_upgrade_benchmark():
        """外部基线能力对照（Agent Trade Kit / Agent Skills 映射结果）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_external_benchmark_matrix"):
            return {"success": False, "message": "基线对照能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_external_benchmark_matrix()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/tool-contract")
    async def commander_tool_contract():
        """标准工具契约清单（供 OpenClaw/MCP/CLI 对接）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_tool_contract_catalog"):
            return {"success": False, "message": "工具契约能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_tool_contract_catalog()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/governance-audit")
    async def commander_governance_audit(limit: int = 100):
        """治理审计流：托管切换、自动化分级、红线更新等变更回放。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_governance_audit"):
            return {"success": False, "message": "治理审计能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_governance_audit(limit=limit)
            return {"success": True, "data": {"items": data}, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/upgrade/run")
    async def commander_upgrade_run(payload: Dict[str, Any] = Body(default_factory=dict)):
        """
        一键升级闭环执行：
        - 账户同步
        - 司令部任务/策略优化
        - 分层验收
        - 托管守护验收
        - 回撤统计验收
        - 外部基线对照
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "run_upgrade_pipeline"):
            return {"success": False, "message": "一键升级能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            symbol = str((payload or {}).get("symbol") or "BTC/USDT")
            trigger_optimize = bool((payload or {}).get("trigger_optimize", True))
            force_account_sync = bool((payload or {}).get("force_account_sync", True))
            auto_fallback_to_semi = bool((payload or {}).get("auto_fallback_to_semi", True))
            data = await main_controller.run_upgrade_pipeline(
                symbol=symbol,
                trigger_optimize=trigger_optimize,
                force_account_sync=force_account_sync,
                auto_fallback_to_semi=auto_fallback_to_semi,
            )
            return {"success": bool(data.get("success")), "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/hosting-mode")
    async def commander_set_hosting_mode(payload: Dict[str, Any] = Body(default_factory=dict)):
        """切换托管模式。mode: full_auto / semi_auto"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "set_hosting_mode"):
            return {"success": False, "message": "托管模式能力不可用", "timestamp": datetime.now().isoformat()}
        mode = str((payload or {}).get("mode") or "").strip()
        mode_l = mode.lower()
        normalized = mode_l
        if mode in {"全自动", "自动"} or mode_l in {"full", "auto"}:
            normalized = "full_auto"
        elif mode in {"半自动"} or mode_l in {"semi", "semi-automatic", "semi_automatic"}:
            normalized = "semi_auto"
        if normalized not in {"full_auto", "semi_auto"}:
            return {
                "success": False,
                "message": "mode 仅支持: full_auto/全自动 或 semi_auto/半自动",
                "timestamp": datetime.now().isoformat(),
            }
        try:
            current = main_controller.set_hosting_mode(normalized)
            return {
                "success": True,
                "data": {
                    "mode": current,
                    "mode_zh": "全自动" if current == "full_auto" else "半自动",
                },
                "message": (
                    "已切换为全自动托管（AI自主开平仓）"
                    if current == "full_auto"
                    else "已切换为半自动托管（开仓需人工确认）"
                ),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/capabilities")
    async def commander_capabilities():
        """司令部能力与子智能体清单（对齐 OpenClaw 文档中的回路/专家概念，便于运维对接）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_commander_capabilities"):
            return {"success": False, "message": "capabilities 不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_commander_capabilities()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/openclaw-integration")
    async def commander_openclaw_integration():
        """OpenClaw 对接状态：读取入口、实时通道、推送配置就绪度。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        try:
            hub = getattr(main_controller, "trade_event_hub", None)
            push_enabled = bool(getattr(hub, "_openclaw_push_enabled", False)) if hub else False
            push_url = str(getattr(hub, "_openclaw_push_url", "") or "") if hub else ""
            queue_size = 0
            queue_max = 0
            if hub and getattr(hub, "_openclaw_push_queue", None) is not None:
                q = getattr(hub, "_openclaw_push_queue")
                queue_size = int(q.qsize())
                queue_max = int(getattr(q, "maxsize", 0))
            data = {
                "dispatch_ready": bool(hasattr(main_controller, "process_user_command")),
                "capabilities_ready": bool(hasattr(main_controller, "get_commander_capabilities")),
                "tool_contract_ready": bool(hasattr(main_controller, "get_tool_contract_catalog")),
                "event_hub_ready": bool(hub is not None),
                "event_stream_replay_ready": bool(hub and hasattr(hub, "query_recent")),
                "system_alert_bridge_ready": bool(hub and hasattr(hub, "publish_system_alert")),
                "openclaw_push": {
                    "enabled": push_enabled,
                    "url_configured": bool(push_url),
                    "queue_size": queue_size,
                    "queue_max": queue_max,
                },
                "required_realtime_channels": ["trade.intent", "trade.fill", "trade.position", "market.update", "system.alert"],
                "required_read_endpoints": [
                    "/api/v1/modules/commander/capabilities",
                    "/api/v1/modules/commander/tool-contract",
                    "/api/v1/modules/commander/snapshot",
                    "/api/v1/modules/commander/account-diagnostics",
                    "/api/v1/trade/events",
                ],
            }
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/chores")
    async def commander_chores(payload: Dict[str, Any] = Body(default_factory=dict)):
        """触发司令部日常任务。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        if not hasattr(main_controller, "run_ai_commander_chores"):
            return {"success": False, "message": "司令部日常任务能力不可用"}
        try:
            symbol = str((payload or {}).get("symbol") or "BTC/USDT")
            trigger_optimize = bool((payload or {}).get("trigger_optimize", False))
            data = await main_controller.run_ai_commander_chores(symbol=symbol, trigger_optimize=trigger_optimize)
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/dispatch")
    async def commander_dispatch(payload: Dict[str, Any] = Body(default_factory=dict)):
        """
        司令部统一指令入口：把前端消息与TG消息统一到同一处理链路。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        if not hasattr(main_controller, "process_user_command"):
            return {"success": False, "message": "司令部指令入口不可用"}
        text = str((payload or {}).get("message") or "").strip()
        if not text:
            return {"success": False, "message": "message 不能为空"}
        source = str((payload or {}).get("source") or "control_hub")
        async_mode = bool((payload or {}).get("async_mode", False))
        try:
            timeout_s = float((payload or {}).get("timeout_sec", 12.0) or 12.0)
        except Exception:
            timeout_s = 12.0
        timeout_s = max(2.0, min(timeout_s, 90.0))
        try:
            if async_mode:
                job_id = str(uuid.uuid4())
                async with dispatch_jobs_lock:
                    dispatch_jobs[job_id] = {
                        "job_id": job_id,
                        "status": "queued",
                        "created_at": datetime.now().isoformat(),
                        "source": source,
                        "message_preview": text[:120],
                        "result": None,
                        "error": None,
                    }

                async def _run_dispatch_job() -> None:
                    async with dispatch_jobs_lock:
                        if job_id in dispatch_jobs:
                            dispatch_jobs[job_id]["status"] = "running"
                            dispatch_jobs[job_id]["started_at"] = datetime.now().isoformat()
                    try:
                        out = await main_controller.process_user_command(text, source=source)
                        async with dispatch_jobs_lock:
                            if job_id in dispatch_jobs:
                                dispatch_jobs[job_id]["status"] = "completed"
                                dispatch_jobs[job_id]["finished_at"] = datetime.now().isoformat()
                                dispatch_jobs[job_id]["result"] = out
                    except Exception as e:
                        async with dispatch_jobs_lock:
                            if job_id in dispatch_jobs:
                                dispatch_jobs[job_id]["status"] = "failed"
                                dispatch_jobs[job_id]["finished_at"] = datetime.now().isoformat()
                                dispatch_jobs[job_id]["error"] = str(e)

                asyncio.create_task(_run_dispatch_job())
                return {
                    "success": True,
                    "accepted": True,
                    "status": "queued",
                    "job_id": job_id,
                    "message": "指令已受理，后台执行中",
                    "timestamp": datetime.now().isoformat(),
                }

            out = await asyncio.wait_for(
                main_controller.process_user_command(text, source=source),
                timeout=timeout_s,
            )
            return {"success": True, "data": out, "timeout_sec": timeout_s, "timestamp": datetime.now().isoformat()}
        except asyncio.TimeoutError:
            # 避免前端超时卡死；建议客户端改用 async_mode=true 拉取结果。
            return {
                "success": False,
                "status": "timeout",
                "timeout_sec": timeout_s,
                "message": "司令部处理超时，请使用 async_mode=true 重试并轮询 job 结果",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/dispatch/jobs/{job_id}")
    async def commander_dispatch_job(job_id: str):
        """查询异步 dispatch 任务状态。"""
        async with dispatch_jobs_lock:
            job = dispatch_jobs.get(job_id)
            if not job:
                return {"success": False, "message": "job 不存在", "job_id": job_id, "timestamp": datetime.now().isoformat()}
            return {"success": True, "data": job, "timestamp": datetime.now().isoformat()}

    @router.get("/commander/audit")
    async def commander_audit(enrich: bool = False):
        """
        司令部全链路审查：检查前端/消息通道/后端关键能力是否已接入。
        enrich=true 时附带第三方限速诊断摘要与记忆网关快照（供运维质检）。
        """
        checks: List[Dict[str, Any]] = []

        def add(name: str, passed: bool, detail: str = "") -> None:
            checks.append({"name": name, "passed": bool(passed), "detail": detail})

        if not main_controller:
            add("main_controller", False, "missing")
            return {"success": False, "checks": checks, "all_passed": False, "timestamp": datetime.now().isoformat()}

        mc = main_controller
        add("commander.snapshot", hasattr(mc, "build_ai_commander_snapshot"), "build_ai_commander_snapshot")
        add("commander.chores", hasattr(mc, "run_ai_commander_chores"), "run_ai_commander_chores")
        add("commander.dispatch", hasattr(mc, "process_user_command"), "process_user_command")
        add("commander.capabilities", hasattr(mc, "get_commander_capabilities"), "get_commander_capabilities")
        add("surface.registry", True, "GET /api/v1/modules/surface/registry")
        add("surface.data_integration_health", True, "GET /api/v1/modules/data/integration/health")
        add("surface.plugins_status", True, "GET /api/v1/modules/plugins/status")
        add("message.telegram", bool(getattr(mc, "telegram_bot", None)), "telegram_bot")
        add("notification.unified", hasattr(mc, "_send_notification_handler"), "_send_notification_handler")
        add("memory.gateway", bool(getattr(mc, "memory_gateway", None)), "memory_gateway")
        add(
            "commander.unrestricted",
            str(__import__("os").environ.get("OPENCLAW_COMMANDER_UNRESTRICTED", "1")).strip().lower() not in {"0", "false", "no", "off"},
            "OPENCLAW_COMMANDER_UNRESTRICTED",
        )
        add("data.hub", bool(getattr(mc, "data_source_hub", None)), "data_source_hub")
        add("data.integration", bool(getattr(mc, "data_integration", None)), "data_integration")
        tpi = getattr(mc, "third_party_data_integrator", None)
        add("data.third_party", bool(tpi), "third_party_data_integrator")
        add(
            "data.third_party.diagnostics",
            bool(tpi and hasattr(tpi, "get_diagnostics")),
            "get_diagnostics for rate-limit QC",
        )
        add("analysis.market_intelligence", bool(getattr(mc, "market_intelligence", None)), "market_intelligence")
        add("plugin.manager", bool(getattr(mc, "plugin_manager", None)), "plugin_manager")
        add("strategy.manager", bool(getattr(mc, "strategy_manager", None)), "strategy_manager")
        add("risk.sltp", bool(getattr(mc, "stop_loss_manager", None)), "stop_loss_manager")
        add("execution.gateway", bool(getattr(mc, "execution_gateway", None)), "execution_gateway")
        add("api.module_control", True, "routes_registered")
        all_passed = all(c["passed"] for c in checks)
        out: Dict[str, Any] = {
            "success": True,
            "all_passed": all_passed,
            "checks": checks,
            "timestamp": datetime.now().isoformat(),
            "architecture": {
                "pattern": "commander_centric",
                "summary": (
                    "司令部(CommanderAgentRuntime)为统一入口：process_user_command → 指令执行器/子智能体(specialists)/记忆网关；"
                    "各业务模块为子系统，由 MainController 装配；实时消息(Telegram 等)与 HTTP dispatch 同源接入。"
                ),
            },
        }
        if enrich:
            out["third_party_diagnostics"] = {}
            if tpi and hasattr(tpi, "get_diagnostics"):
                try:
                    out["third_party_diagnostics"] = tpi.get_diagnostics()
                except Exception as e:
                    out["third_party_diagnostics"] = {"error": str(e)}
            gw = getattr(mc, "memory_gateway", None)
            out["memory_quick"] = {}
            if gw:
                try:
                    out["memory_quick"] = {
                        "stats": gw.get_stats() if hasattr(gw, "get_stats") else {},
                        "summary": gw.get_summary_status() if hasattr(gw, "get_summary_status") else {},
                    }
                except Exception as e:
                    out["memory_quick"] = {"error": str(e)}
            tb = getattr(mc, "telegram_bot", None)
            out["realtime_channels"] = {
                "telegram_configured": tb is not None,
                "hint": "前端/脚本与 Bot 均可用 POST /api/v1/modules/commander/dispatch 统一 source 标签",
            }
        return out

    @router.get("/commander/memory/status")
    async def commander_memory_status():
        """司令部记忆系统自检：网关/后端统计/召回命中率等。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        gw = getattr(main_controller, "memory_gateway", None)
        if not gw:
            return {"success": False, "message": "MemoryGateway 未就绪", "timestamp": datetime.now().isoformat()}
        try:
            stats = gw.get_stats() if hasattr(gw, "get_stats") else {}
            summary = gw.get_summary_status() if hasattr(gw, "get_summary_status") else {}
            return {
                "success": True,
                "data": {
                    "stats": stats,
                    "summary": summary,
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/memory/workspace")
    async def commander_memory_workspace(filename: str = ""):
        """读取 workspace 记忆文件（默认读取允许集合；可用 env 放开全部）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        gw = getattr(main_controller, "memory_gateway", None)
        if not gw or not hasattr(gw, "get_workspace_memory"):
            return {"success": False, "message": "MemoryGateway 未就绪", "timestamp": datetime.now().isoformat()}
        try:
            data = gw.get_workspace_memory(filename=filename or None)
            # 避免一次性回传超大：每个文件最多返回 200k 字符
            clipped = {}
            for k, v in (data or {}).items():
                s = v if isinstance(v, str) else str(v)
                clipped[k] = s if len(s) <= 200_000 else (s[:200_000] + "\n\n…已截断…")
            return {"success": True, "data": clipped, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/memory/persona-preview")
    async def commander_memory_persona_preview(source: str = "api"):
        """
        司令部人格/身份/职责是否已注入：返回「将被注入到对话提示词的摘要」预览。
        用于排查“司令部好像不知道自己是谁/做什么”的问题。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        exe = getattr(main_controller, "ai_command_executor", None)
        if not exe or not hasattr(exe, "_get_user_rules_context"):
            return {"success": False, "message": "AICommandExecutor 未就绪", "timestamp": datetime.now().isoformat()}
        try:
            # _get_user_rules_context 会包含 CHARTER + startup bundle + boundaries prose + 关键记忆片段
            text = await exe._get_user_rules_context()
            cap = 18_000
            preview = text if len(text) <= cap else (text[:cap] + "\n\n…已截断…")
            return {
                "success": True,
                "data": {
                    "source": source,
                    "preview": preview,
                    "length": len(text),
                    "has_startup_bundle": bool(getattr(exe, "_workspace_startup_bundle", "") or ""),
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/account-diagnostics")
    async def commander_account_diagnostics():
        """
        交易所实时持仓/余额 vs 本地 SLTP 跟踪 — 排查同步问题（不依赖本机成交笔数）。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_account_sync_diagnostics"):
            return {"success": False, "message": "诊断接口不可用", "timestamp": datetime.now().isoformat()}
        try:
            # 账户私有接口在代理抖动时可能接近 20s；放宽超时以减少误判降级。
            data = await asyncio.wait_for(main_controller.get_account_sync_diagnostics(), timeout=45.0)
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except asyncio.TimeoutError:
            # 降级时也返回关键事实，避免前端误判为 exchange=None / positions=0。
            ex_name = None
            try:
                ex = main_controller.get_exchange() if hasattr(main_controller, "get_exchange") else None
                ex_name = type(ex).__name__ if ex is not None else None
            except Exception:
                ex_name = None
            st = getattr(main_controller, "_latest_account_state", None)
            cached_positions = []
            if isinstance(st, dict) and isinstance(st.get("positions"), list):
                cached_positions = st.get("positions") or []
            elif (
                getattr(main_controller, "ai_trading_engine", None) is not None
                and isinstance(getattr(main_controller.ai_trading_engine, "positions", None), dict)
            ):
                cached_positions = list(main_controller.ai_trading_engine.positions.values())
            return {
                "success": True,
                "degraded": True,
                "data": {
                    "status": "timeout_degraded",
                    "hint": "account_diagnostics_timeout",
                    "exchange": ex_name,
                    "cached_position_count": len(cached_positions),
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/trading-diagnosis")
    async def commander_trading_diagnosis(
        limit_events: int = 20,
        include_deep: bool = False,
        timeout_sec: float = 8.0,
    ):
        """
        全面体检：开/平仓技术判断、执行脊柱、SLTP 出场、学习引擎是否在运转与写回。
        用于验收“智能体是否正常运用性能、并能自总结经验教训自动优化策略”。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        mc = main_controller
        out: Dict[str, Any] = {"timestamp": datetime.now().isoformat()}
        started = time.monotonic()
        total_budget = max(2.0, min(30.0, float(timeout_sec or 8.0)))
        def _remaining(default: float) -> float:
            left = total_budget - (time.monotonic() - started)
            return max(0.25, min(float(default), left))

        # 1) ai_core / ai_trading_engine 状态（技术判断路径）
        core = getattr(mc, "ai_core", None)
        try:
            out["ai_core"] = core.get_status() if (core and hasattr(core, "get_status")) else None
        except Exception as e:
            out["ai_core_error"] = str(e)
        try:
            if core and hasattr(core, "get_opportunity_cost_summary"):
                # 与 _remaining 解耦：前置同步路径若较慢，共享 total_budget 会把子预算压到 0.25s，导致稳定 Timeout。
                _diag_sl = max(2.0, min(30.0, float(timeout_sec or 8.0)))
                budget = max(5.5, min(14.0, _diag_sl * 0.52))
                out["opportunity_cost"] = await asyncio.wait_for(
                    core.get_opportunity_cost_summary(lookback=120),
                    timeout=budget,
                )
                _oc = out.get("opportunity_cost")
                if isinstance(_oc, dict):
                    _oc = dict(_oc)
                    _oc["diagnosis_wait_budget_sec"] = round(float(budget), 4)
                    out["opportunity_cost"] = _oc
        except asyncio.TimeoutError:
            try:
                _diag_sl = max(2.0, min(30.0, float(timeout_sec or 8.0)))
                _b = max(5.5, min(14.0, _diag_sl * 0.52))
                out["opportunity_cost_budget_sec"] = round(float(_b), 4)
            except Exception:
                pass
            out["opportunity_cost_error"] = "opportunity_cost_timeout"
        except Exception as e:
            out["opportunity_cost_error"] = str(e)
        try:
            eng = getattr(mc, "ai_trading_engine", None)
            out["ai_trading_engine"] = eng.get_status() if (eng and hasattr(eng, "get_status")) else None
        except Exception as e:
            out["ai_trading_engine_error"] = str(e)

        # 2) ExecutionGateway（执行成功率、回查一致性、recent events）
        try:
            gw = getattr(mc, "execution_gateway", None)
            if gw and hasattr(gw, "get_snapshot"):
                snap = await asyncio.wait_for(gw.get_snapshot(), timeout=_remaining(0.9))
                if gw and hasattr(gw, "get_recent_events"):
                    snap["recent_events"] = await asyncio.wait_for(
                        gw.get_recent_events(limit=int(limit_events or 20)),
                        timeout=_remaining(1.2),
                    )
                out["execution_gateway"] = snap
                out["execution_reconciliation"] = (
                    snap.get("reconciliation") if isinstance(snap, dict) else None
                )
                out["execution_reconciliation_protection"] = (
                    snap.get("reconciliation_protection") if isinstance(snap, dict) else None
                )
                out["execution_safe_recovery"] = (
                    ((snap.get("reconciliation") or {}).get("safe_recovery"))
                    if isinstance(snap, dict) and isinstance(snap.get("reconciliation"), dict)
                    else None
                )
                out["decision_traces"] = (
                    snap.get("decision_traces") if isinstance(snap, dict) else None
                )
            else:
                out["execution_gateway"] = None
                out["execution_reconciliation"] = None
                out["execution_reconciliation_protection"] = None
                out["execution_safe_recovery"] = None
                out["decision_traces"] = None
        except asyncio.TimeoutError:
            out["execution_gateway"] = {"degraded": True, "message": "execution_gateway_timeout"}
        except Exception as e:
            out["execution_gateway_error"] = str(e)

        # 3) SLTP（含 SR 关键位出场观测）
        try:
            sltp = getattr(mc, "stop_loss_manager", None)
            out["sltp"] = sltp.get_stats() if (sltp and hasattr(sltp, "get_stats")) else None
        except Exception as e:
            out["sltp_error"] = str(e)

        # 3.1) Position consistency quick check (exchange vs ai_core/engine vs SLTP live index)
        try:
            ex_non_zero = None
            ai_count = None
            sltp_live = None
            ex = mc.get_exchange() if hasattr(mc, "get_exchange") else None
            if ex and hasattr(ex, "get_positions"):
                try:
                    ps = await asyncio.wait_for(ex.get_positions(), timeout=_remaining(1.2))
                    if isinstance(ps, list):
                        ex_non_zero = 0
                        for p in ps:
                            if not isinstance(p, dict):
                                continue
                            try:
                                v = float(p.get("size", p.get("pos", 0)) or 0)
                            except Exception:
                                v = 0.0
                            if abs(v) > 1e-12:
                                ex_non_zero += 1
                except Exception:
                    ex_non_zero = None
            try:
                core = getattr(mc, "ai_core", None)
                if core and isinstance(getattr(core, "positions", None), dict):
                    ai_count = len(getattr(core, "positions", {}) or {})
                elif getattr(mc, "ai_trading_engine", None) is not None and isinstance(
                    getattr(mc.ai_trading_engine, "positions", None), dict
                ):
                    ai_count = len(getattr(mc.ai_trading_engine, "positions", {}) or {})
            except Exception:
                ai_count = None
            try:
                sltp_stats = out.get("sltp") if isinstance(out.get("sltp"), dict) else {}
                # stop_loss_take_profit stats already expose live tracked orders count
                if isinstance(sltp_stats, dict):
                    sltp_live = int(
                        sltp_stats.get("active_orders")
                        or sltp_stats.get("live_norm_key_count")
                        or 0
                    )
            except Exception:
                sltp_live = None

            deltas = {}
            if ex_non_zero is not None and ai_count is not None:
                deltas["exchange_vs_ai"] = int(ex_non_zero) - int(ai_count)
            if ex_non_zero is not None and sltp_live is not None:
                deltas["exchange_vs_sltp"] = int(ex_non_zero) - int(sltp_live)
            # Consistency policy:
            # - exchange_vs_ai must be exactly 0 (authoritative position count alignment)
            # - exchange_vs_sltp is only unhealthy when positive (exchange has more live positions than SLTP tracking)
            #   negative means SLTP tracks equal/more entries (can happen with staged/duplicate keys), treat as non-fatal.
            healthy = True
            if "exchange_vs_ai" in deltas and abs(int(deltas["exchange_vs_ai"])) > 0:
                healthy = False
            if "exchange_vs_sltp" in deltas and int(deltas["exchange_vs_sltp"]) > 0:
                healthy = False
            out["position_consistency"] = {
                "healthy": healthy if deltas else None,
                "policy_version": "pc_v2_ex_ai_strict_ex_sltp_positive_only",
                "exchange_non_zero_positions": ex_non_zero,
                "ai_tracked_positions": ai_count,
                "sltp_live_tracked": sltp_live,
                "deltas": deltas,
            }
        except Exception as e:
            out["position_consistency_error"] = str(e)

        # 3.2) Exchange reachability quick probe (surface TLS/proxy/network issues in diagnosis)
        try:
            exch_diag: Dict[str, Any] = {"ok": None}
            ex_probe = mc.get_exchange() if hasattr(mc, "get_exchange") else None
            if not ex_probe:
                ex_probe = getattr(mc, "okx_exchange", None)
            if ex_probe is None:
                exch_diag = {"ok": False, "status": "missing", "message": "exchange_unavailable"}
            else:
                probe = getattr(ex_probe, "probe_public_api", None)
                if callable(probe):
                    try:
                        # Avoid over-sensitive degraded spikes from short transient latency.
                        # Keep bounded by overall diagnosis budget via _remaining().
                        pr = await asyncio.wait_for(probe(timeout_sec=2.8), timeout=_remaining(3.4))
                    except Exception as _e:
                        pr = {"ok": False, "reason": "probe_exception", "error": str(_e)[:220]}
                    probe_status = str((pr or {}).get("status_text") or "").strip().lower()
                    if probe_status not in {"reachable", "degraded", "unreachable"}:
                        probe_status = "reachable" if bool((pr or {}).get("ok")) else "unreachable"
                    exch_diag = {
                        "ok": bool((pr or {}).get("ok")),
                        "status": probe_status,
                        "probe": pr,
                    }
                    if probe_status == "unreachable":
                        exch_diag["hint"] = (
                            "Check TLS CA chain / proxy MITM root (OPENCLAW_SSL_CA_BUNDLE) / network."
                        )
                else:
                    exch_diag = {"ok": None, "status": "unknown", "message": "probe_not_supported"}
            out["exchange_reachability"] = exch_diag
        except asyncio.TimeoutError:
            out["exchange_reachability"] = {"ok": None, "status": "unknown", "message": "probe_timeout"}
        except Exception as e:
            out["exchange_reachability_error"] = str(e)

        # 4) AI 学习引擎（经验教训/优化循环）
        try:
            le = getattr(mc, "ai_learning_engine", None)
            out["ai_learning_engine"] = le.get_status() if (le and hasattr(le, "get_status")) else None
            if isinstance(out.get("ai_learning_engine"), dict):
                out["trace_learning_feedback"] = (out.get("ai_learning_engine") or {}).get("trace_feedback")
                out["learning_analytics"] = (out.get("ai_learning_engine") or {}).get("learning_analytics")
                out["weekly_research_review"] = (out.get("ai_learning_engine") or {}).get("weekly_review")
        except Exception as e:
            out["ai_learning_engine_error"] = str(e)

        # 4.1) Market structure / agent orchestration / controlled tuning
        try:
            ms_rows: List[Dict[str, Any]] = []
            mi = getattr(mc, "market_intelligence", None) or getattr(mc, "market_intelligence_engine", None)
            symbols = []
            try:
                symbols = list(getattr(mc, "symbols", []) or [])
            except Exception:
                symbols = []
            if mi and hasattr(mi, "get_cached_symbol_view"):
                for sym in symbols[:12]:
                    try:
                        row = mi.get_cached_symbol_view(sym) or {}
                    except Exception:
                        row = {}
                    if isinstance(row, dict) and row:
                        row = dict(row)
                        row.setdefault("symbol", sym)
                        ms_rows.append(row)
            mse = getattr(mc, "market_structure_engine", None)
            if mse and hasattr(mse, "summarize"):
                out["market_structure"] = mse.summarize(ms_rows)
            else:
                out["market_structure"] = {"sample_size": 0, "samples": []}
        except Exception as e:
            out["market_structure_error"] = str(e)

        try:
            orch = getattr(mc, "agent_orchestrator", None)
            out["agent_orchestration"] = orch.get_status() if (orch and hasattr(orch, "get_status")) else None
        except Exception as e:
            out["agent_orchestration_error"] = str(e)

        try:
            sm = getattr(mc, "strategy_manager", None)
            out["market_structure_governance"] = (
                sm.get_market_structure_governance_status()
                if (sm and hasattr(sm, "get_market_structure_governance_status"))
                else None
            )
        except Exception as e:
            out["market_structure_governance_error"] = str(e)

        try:
            gov = getattr(mc, "tuning_governance", None)
            out["tuning_governance"] = gov.get_status() if (gov and hasattr(gov, "get_status")) else None
        except Exception as e:
            out["tuning_governance_error"] = str(e)

        try:
            mg = getattr(mc, "memory_gateway", None)
            out["memory_architecture"] = (
                mg.get_layered_memory_overview() if (mg and hasattr(mg, "get_layered_memory_overview")) else None
            )
        except Exception as e:
            out["memory_architecture_error"] = str(e)
        try:
            fs = getattr(mc, "feature_store_lite", None)
            out["feature_store_lite"] = fs.get_summary() if (fs and hasattr(fs, "get_summary")) else None
        except Exception as e:
            out["feature_store_lite_error"] = str(e)

        # 5) TradeHistory 统计（用于盈利/亏损结构评估）
        try:
            ths = getattr(mc, "trade_history_service", None)
            if ths and hasattr(ths, "get_statistics"):
                # 诊断接口优先快返回，避免为了强制刷新历史统计而阻塞整条验收链路。
                out["trade_history_30d"] = await asyncio.wait_for(
                    ths.get_statistics(days=30, force_refresh=False),
                    timeout=2.5,
                )
                st = out.get("trade_history_30d") if isinstance(out.get("trade_history_30d"), dict) else {}
                if isinstance(st, dict):
                    out["strategy_distribution_30d"] = st.get("strategy_distribution") or {}
        except asyncio.TimeoutError:
            out["trade_history_30d"] = {"degraded": True, "message": "trade_history_stats_timeout"}
        except Exception as e:
            out["trade_history_error"] = str(e)

        # 5.1) Unified analysis pipeline assessment (fast by default; deep optional)
        try:
            assess: Dict[str, Any] = {}
            gw = getattr(mc, "execution_gateway", None)
            swo = "ai_core"
            try:
                if gw and hasattr(gw, "single_write_owner"):
                    swo = await asyncio.wait_for(gw.single_write_owner(), timeout=_remaining(0.8))
            except Exception:
                swo = "ai_core"
            assess["pipeline"] = {
                "single_write_owner": str(swo or "ai_core"),
                "include_deep": bool(include_deep),
                "mode": "deep" if bool(include_deep) else "fast",
            }

            # fast mode: use cached symbol views only, avoid slow snapshot calls
            mi = getattr(mc, "market_intelligence", None)
            sampled_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "AVAX/USDT"]
            rows: List[Dict[str, Any]] = []
            degraded_cnt = 0
            if mi and hasattr(mi, "get_cached_symbol_view"):
                for sym in sampled_symbols:
                    vd = {}
                    try:
                        vd = mi.get_cached_symbol_view(sym) or {}
                    except Exception:
                        vd = {}
                    if not isinstance(vd, dict):
                        vd = {}
                    prov = str(vd.get("provenance") or "")
                    partial = bool(vd.get("partial", False))
                    conf_v = vd.get("confidence")
                    trend_v = str(vd.get("trend") or "").strip().lower()
                    try:
                        conf_f = float(conf_v) if conf_v is not None else None
                    except Exception:
                        conf_f = None
                    weak_but_usable = bool(
                        partial
                        and conf_f is not None
                        and conf_f >= 0.4
                        and trend_v in {"bullish", "bearish", "sideways"}
                    )
                    degraded = (
                        (not bool(vd))
                        or (partial and not weak_but_usable)
                        or ("degraded" in prov.lower())
                        or ("fastpath" in prov.lower() and not weak_but_usable)
                    )
                    fallback_used = False
                    fallback_error = None
                    # If cached view is degraded/unknown, do one bounded refresh attempt
                    # to avoid persistent false degraded_ratio spikes caused by stale weak cache.
                    if degraded or (not isinstance(vd, dict)) or (not vd):
                        gv = getattr(mi, "get_symbol_view", None)
                        if callable(gv):
                            try:
                                sv = await asyncio.wait_for(
                                    # Need a full snapshot-quality refresh here; fastpath-only view
                                    # is intentionally partial and would keep degraded=true.
                                    gv(sym, include_snapshot=True, prefer_fast_only=False),
                                    timeout=_remaining(1.8),
                                )
                                vd2 = sv.to_dict() if hasattr(sv, "to_dict") else (sv if isinstance(sv, dict) else {})
                                if isinstance(vd2, dict) and vd2:
                                    prov2 = str(vd2.get("provenance") or "")
                                    partial2 = bool(vd2.get("partial", False))
                                    conf2_v = vd2.get("confidence")
                                    trend2_v = str(vd2.get("trend") or "").strip().lower()
                                    try:
                                        conf2_f = float(conf2_v) if conf2_v is not None else None
                                    except Exception:
                                        conf2_f = None
                                    weak2_usable = bool(
                                        partial2
                                        and conf2_f is not None
                                        and conf2_f >= 0.4
                                        and trend2_v in {"bullish", "bearish", "sideways"}
                                    )
                                    degraded2 = (
                                        (partial2 and not weak2_usable)
                                        or ("degraded" in prov2.lower())
                                        or ("fastpath" in prov2.lower() and not weak2_usable)
                                    )
                                    # use refreshed view if it is stronger, or if cache was empty
                                    if (not degraded2) or (not vd):
                                        vd = vd2
                                        prov = prov2
                                        partial = partial2
                                        weak_but_usable = weak2_usable
                                        degraded = degraded2
                                        fallback_used = True
                            except Exception as _e:
                                fallback_error = type(_e).__name__
                    error = None
                    if not isinstance(vd, dict) or not vd:
                        degraded = True
                        error = "cached_symbol_view_missing"
                    last_good_fresh = None
                    try:
                        lg_ts = float((getattr(mi, "_last_good_view_ts", {}) or {}).get(sym, 0) or 0)
                        lg_ttl = float(getattr(mi, "_last_good_view_ttl_sec", 180) or 180)
                        if lg_ts > 0:
                            last_good_fresh = bool((time.time() - lg_ts) <= lg_ttl)
                    except Exception:
                        last_good_fresh = None
                    if degraded:
                        degraded_cnt += 1
                    rows.append(
                        {
                            "symbol": sym,
                            "quality_score": vd.get("quality_score"),
                            "confidence": vd.get("confidence"),
                            "trend": vd.get("trend"),
                            "provenance": prov,
                            "partial": partial,
                            "degraded": degraded,
                            "weak_but_usable": weak_but_usable,
                            "fallback_used": fallback_used,
                            "fallback_error": fallback_error,
                            "last_good_fresh": last_good_fresh,
                            "error": error,
                        }
                    )
            assess["market_analysis"] = {
                "sampled_symbols": sampled_symbols,
                "degraded_ratio": round(float(degraded_cnt) / float(max(1, len(sampled_symbols))), 4),
                "samples": rows,
            }
            # lightweight recent outcome
            decision_health = {"sample_size": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "sum_pnl": 0.0, "expectancy": 0.0}
            ths = getattr(mc, "trade_history_service", None)
            if ths and hasattr(ths, "get_recent_trades"):
                recents = await asyncio.wait_for(ths.get_recent_trades(limit=40), timeout=_remaining(1.2))
                vals = [float((r or {}).get("pnl", 0) or 0) for r in (recents or []) if isinstance(r, dict)]
                if vals:
                    w = sum(1 for v in vals if v > 0)
                    l = sum(1 for v in vals if v < 0)
                    total = len(vals)
                    sum_pnl = float(sum(vals))
                    decision_health = {
                        "sample_size": total,
                        "wins": w,
                        "losses": l,
                        "win_rate": round(float(w) / float(total), 4),
                        "sum_pnl": round(sum_pnl, 6),
                        "expectancy": round(sum_pnl / float(total), 6),
                    }
            assess["decision_outcome_recent"] = decision_health

            le = getattr(mc, "ai_learning_engine", None)
            le_st = le.get_status() if (le and hasattr(le, "get_status")) else {}
            assess["learning_effectiveness"] = {
                "running": bool((le_st or {}).get("running", False)),
                "total_lessons": int((le_st or {}).get("total_lessons", 0) or 0),
                "reports_generated": int((le_st or {}).get("reports_generated", 0) or 0),
                "trace_feedback": (le_st or {}).get("trace_feedback"),
            }
            out["analysis_pipeline_assessment"] = assess
        except asyncio.TimeoutError:
            out["analysis_pipeline_assessment"] = {"degraded": True, "message": "analysis_pipeline_timeout"}
        except Exception as e:
            out["analysis_pipeline_assessment_error"] = str(e)

        # 5.2) Entry timing diagnosis: HOLD tags + rejected open reasons (especially SR timing)
        try:
            etd: Dict[str, Any] = {}
            core = getattr(mc, "ai_core", None)
            dts = getattr(mc, "decision_trace_store", None)
            if dts and hasattr(dts, "analyze_recent"):
                ana = dts.analyze_recent(limit=120) or {}
                top_hold_tags = ana.get("top_hold_reason_tags") if isinstance(ana, dict) else []
                etd["hold_trace_summary"] = (ana.get("summary") if isinstance(ana, dict) else {}) or {}
                etd["top_hold_reason_tags"] = top_hold_tags or []
                hold_tag_map = {
                    "mtf_conflict": "多周期冲突",
                    "low_confidence": "置信度不足",
                    "quality_insufficient": "数据质量不足",
                    "trend_misalignment": "趋势不一致",
                    "evidence_incomplete": "证据不完整",
                    "neutral_market": "中性/震荡市况",
                    "llm_unavailable_fallback": "LLM降级回退",
                    "no_sr_entry_trigger": "未出现SR入场触发",
                }
                etd["top_hold_reason_labels"] = [
                    {
                        "key": str(item.get("key") or ""),
                        "label": hold_tag_map.get(str(item.get("key") or ""), str(item.get("key") or "")),
                        "count": int(item.get("count", 0) or 0),
                    }
                    for item in (top_hold_tags or [])
                    if isinstance(item, dict)
                ]

            rejected_rows = list(getattr(core, "_rejected_signals", []) or []) if core is not None else []
            recent_rejected = rejected_rows[-120:]
            reason_counts: Dict[str, int] = {}
            reason_samples: Dict[str, List[Dict[str, Any]]] = {}
            for row in recent_rejected:
                if not isinstance(row, dict):
                    continue
                reason = str(row.get("reason") or "unknown")
                reason_counts[reason] = int(reason_counts.get(reason, 0)) + 1
                reason_samples.setdefault(reason, [])
                if len(reason_samples[reason]) < 3:
                    reason_samples[reason].append(
                        {
                            "ts": row.get("ts"),
                            "symbol": row.get("symbol"),
                            "side": row.get("side"),
                            "confidence": row.get("confidence"),
                            "entry_price": row.get("entry_price"),
                            "extras": row.get("extras") if isinstance(row.get("extras"), dict) else {},
                        }
                    )
            reason_label_map = {
                "sr_entry_confirmation_missing_long": "多头缺少SR入场确认",
                "sr_entry_confirmation_missing_short": "空头缺少SR入场确认",
                "sr_timing_long_near_resistance": "多头贴近阻力未突破",
                "sr_timing_short_near_support": "空头贴近支撑未跌破",
                "same_direction_ratio_rejected": "同向集中度过高",
                "loss_streak_cooldown_active": "连亏冷却中",
                "loss_streak_cooldown_triggered": "触发连亏冷却",
            }
            top_rejected_reasons = [
                {
                    "key": key,
                    "label": reason_label_map.get(key, key),
                    "count": int(count),
                    "samples": reason_samples.get(key, [])[:3],
                }
                for key, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            ]
            sr_keys = {
                "sr_entry_confirmation_missing_long",
                "sr_entry_confirmation_missing_short",
                "sr_timing_long_near_resistance",
                "sr_timing_short_near_support",
            }
            sr_reason_total = sum(int(reason_counts.get(k, 0) or 0) for k in sr_keys)
            etd["rejected_signal_window"] = {
                "sample_size": len(recent_rejected),
                "top_reasons": top_rejected_reasons,
                "sr_related_rejections": sr_reason_total,
            }
            if sr_reason_total > 0:
                etd["summary"] = (
                    f"最近拒单里 SR 择时相关原因 {sr_reason_total} 次，"
                    "说明当前系统已开始把“位置不对”与“证据不足”分开。"
                )
            elif top_rejected_reasons:
                lead = top_rejected_reasons[0]
                etd["summary"] = (
                    f"最近拒单主因是 {lead.get('label')}（{lead.get('count')} 次），"
                    "可优先围绕该原因调参。"
                )
            else:
                etd["summary"] = "最近窗口没有明显的开仓拒单样本。"
            out["entry_timing_diagnosis"] = etd
        except Exception as e:
            out["entry_timing_diagnosis_error"] = str(e)

        # 6) 自动总结的“经验教训”与建议（轻量，避免误导）
        try:
            core = getattr(mc, "ai_core", None)
            gw = getattr(mc, "execution_gateway", None)
            dts = getattr(mc, "decision_trace_store", None)
            trace_analysis = dts.analyze_recent(limit=80) if (dts and hasattr(dts, "analyze_recent")) else {}
            hints: List[str] = []
            if core and hasattr(core, "get_status"):
                st = core.get_status() or {}
                guards = ((st.get("execution_guards") or {}).get("stats") or {}) if isinstance(st, dict) else {}
                top = sorted([(k, int(v)) for k, v in (guards or {}).items()], key=lambda x: x[1], reverse=True)[:6]
                if top:
                    hints.append("ai_core 门控Top: " + ", ".join([f"{k}={v}" for k, v in top]))
            if gw and hasattr(gw, "get_policy_metrics"):
                pm = gw.get_policy_metrics() or {}
                hints.append("execution 脊柱: " + ", ".join([f"{k}={pm.get(k)}" for k in ("open_ok","open_fail","close_ok","close_fail")]))
            eg = out.get("execution_gateway") if isinstance(out.get("execution_gateway"), dict) else {}
            rwp = eg.get("replace_worst_policy") if isinstance(eg.get("replace_worst_policy"), dict) else {}
            if rwp:
                hints.append(
                    "replace_worst policy: "
                    + ", ".join(
                        [
                            f"enabled={bool(rwp.get('enable_replace_worst_on_full_positions', False))}",
                            f"min_conf={float(rwp.get('replace_worst_min_confidence', 0.75) or 0.75):.2f}",
                        ]
                    )
                )
            rec = out.get("execution_reconciliation") if isinstance(out.get("execution_reconciliation"), dict) else {}
            if rec:
                sm = rec.get("summary") if isinstance(rec.get("summary"), dict) else {}
                hints.append(
                    "execution 对账: "
                    + ", ".join(
                        [
                            f"healthy={rec.get('healthy')}",
                            f"severity={rec.get('severity')}",
                            f"drift_total={sm.get('drift_total', 0)}",
                            f"stale_open_orders={sm.get('stale_open_orders', 0)}",
                        ]
                    )
                )
            wf_focus = _summarize_trace_workflow_focus(trace_analysis)
            if isinstance(wf_focus.get("top_stage"), dict) or isinstance(wf_focus.get("top_status"), dict):
                stage_key = str(((wf_focus.get("top_stage") or {}).get("key")) or "-")
                status_key = str(((wf_focus.get("top_status") or {}).get("key")) or "-")
                hints.append(f"decision workflow 卡点: stage={stage_key}, status={status_key}")
            rcp = out.get("execution_reconciliation_protection") if isinstance(out.get("execution_reconciliation_protection"), dict) else {}
            if rcp:
                sl = rcp.get("symbol_locks") if isinstance(rcp.get("symbol_locks"), dict) else {}
                hints.append(
                    "reconciliation protection: "
                    + ", ".join(
                        [
                            f"global={bool(rcp.get('global_lock_active', False))}",
                            f"symbol_locks={len(sl)}",
                        ]
                    )
                )
                acts = rcp.get("safe_recovery_actions") if isinstance(rcp.get("safe_recovery_actions"), list) else []
                if acts:
                    hints.append(f"safe recovery actions={len(acts)}")
            out["diagnosis_hints"] = hints
        except Exception:
            pass

        # 6.1) Canonical position limits snapshot (single entry validation)
        try:
            from src.modules.core.trading_limits import resolve_position_limits

            limits = await resolve_position_limits(config_manager=getattr(mc, "config_manager", None))
            out["position_limits_snapshot"] = limits.to_dict()
            hints = out.get("diagnosis_hints") if isinstance(out.get("diagnosis_hints"), list) else []
            eg = out.get("execution_gateway") if isinstance(out.get("execution_gateway"), dict) else {}
            rwp = eg.get("replace_worst_policy") if isinstance(eg.get("replace_worst_policy"), dict) else {}
            if hints and rwp and not bool(rwp.get("enable_replace_worst_on_full_positions", False)):
                lim = out["position_limits_snapshot"] if isinstance(out.get("position_limits_snapshot"), dict) else {}
                hard_cap = int(lim.get("hard_max_positions", 0) or 0)
                oneway_cap = int(lim.get("max_positions_oneway", 0) or 0)
                cap = hard_cap or oneway_cap
                if cap > 0:
                    hints.append(
                        f"full position behavior: replace_worst disabled, reaching max_positions={cap} will hard-block new opens until a slot is freed"
                    )
                    events = (eg.get("recent_events") or []) if isinstance(eg.get("recent_events"), list) else []
                    recent_capacity_blocks = []
                    for evt in events:
                        if not isinstance(evt, dict):
                            continue
                        if evt.get("success") is not False:
                            continue
                        if str(evt.get("op") or "").lower() != "open":
                            continue
                        if str(evt.get("error_code") or "").upper() != "RISK_REDLINE_DENIED":
                            continue
                        detail = str(evt.get("detail") or "")
                        reason = str(evt.get("reason") or "")
                        if "max_positions" not in detail.lower() and "持仓数" not in detail and "max_positions" not in reason.lower():
                            continue
                        recent_capacity_blocks.append(evt)
                    latest = recent_capacity_blocks[-1] if recent_capacity_blocks else None
                    if latest is None and not events:
                        latest = _load_recent_capacity_block_from_runtime()
                    if latest is None and not events:
                        latest = _load_recent_capacity_block_from_app_log()
                    if latest:
                        symbol = str(latest.get("symbol") or "?")
                        ts = str(latest.get("ts") or "-")
                        source = str(latest.get("source") or "recent_events")
                        source_suffix = "" if source == "recent_events" else f", source={source}"
                        hints.insert(
                            0,
                            f"recent capacity block: ts={ts}, symbol={symbol}, open was rejected by max_positions redline while replace_worst was disabled{source_suffix}",
                        )
        except Exception as e:
            out["position_limits_snapshot_error"] = str(e)

        # 7) Execution failures attribution: Top reasons + samples + action hints
        try:
            eg = out.get("execution_gateway") if isinstance(out.get("execution_gateway"), dict) else {}
            events = (eg.get("recent_events") or []) if isinstance(eg.get("recent_events"), list) else []
            # focus on failures only; split benign terminal-close noise from actionable failures
            fails_all = [e for e in events if isinstance(e, dict) and e.get("success") is False]
            benign_codes = {"ALREADY_CLOSED_NO_POSITION"}
            benign_fails = [
                e for e in fails_all
                if str(e.get("error_code") or "").upper() in benign_codes
            ]
            fails = [
                e for e in fails_all
                if str(e.get("error_code") or "").upper() not in benign_codes
            ]

            def _key(e: Dict[str, Any]) -> str:
                op = str(e.get("op") or "unknown")
                code = str(e.get("error_code") or "UNKNOWN")
                phase = str(e.get("phase") or "unknown")
                return f"{op}:{code}:{phase}"

            counts: Dict[str, int] = {}
            samples: Dict[str, List[Dict[str, Any]]] = {}
            for e in fails:
                k = _key(e)
                counts[k] = int(counts.get(k, 0)) + 1
                samples.setdefault(k, [])
                if len(samples[k]) < 3:
                    samples[k].append(
                        {
                            "ts": e.get("ts"),
                            "symbol": e.get("symbol"),
                            "side": e.get("side"),
                            "source": e.get("source"),
                            "reason": e.get("reason"),
                            "detail": str(e.get("detail") or "")[:220],
                            "trace_id": e.get("trace_id"),
                            "endpoint": e.get("endpoint"),
                            "retriable": bool(e.get("retriable")),
                        }
                    )

            top_keys = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:8]

            def _group_from_exchange_code(code: str) -> str:
                c = str(code or "").upper()
                if c in {"TIMEOUT", "CONNECTION_ERROR", "NETWORK_ERROR", "NO_EXCHANGE"}:
                    return "exchange_connectivity"
                if c in {"INSUFFICIENT_MARGIN", "INSUFFICIENT_FUNDS", "SIZE_TOO_SMALL"}:
                    return "positioning_capital"
                if c in {"INSTRUMENT_INVALID"}:
                    return "symbol_contract"
                if c in {"POLICY_DENIED", "HOSTING_MODE_DENIED", "RISK_REDLINE_DENIED", "OPEN_COOLDOWN_ACTIVE"}:
                    return "risk_policy"
                if c in {"ALREADY_CLOSED_NO_POSITION", "POST_CHECK_ANOMALY"}:
                    return "post_trade_reconcile"
                return "exchange_other"

            group_label_map = {
                "exchange_connectivity": "交易所连通性",
                "positioning_capital": "仓位与资金",
                "symbol_contract": "标的与合约",
                "risk_policy": "风控与策略规则",
                "post_trade_reconcile": "事后对账与收敛",
                "exchange_other": "交易所其他",
                "evidence_quality": "证据与数据质量",
                "signal_confidence": "信号置信度",
                "risk_reward": "盈亏比",
                "microstructure": "微结构",
                "ai_core_other": "AI核心其他",
                "other": "其他",
            }

            def _action_hint(code: str) -> str:
                code = str(code or "").upper()
                return {
                    "POLICY_DENIED": "检查 single_write_owner/来源(source) 是否符合规则；必要时用 manual 或 force_close。",
                    "HOSTING_MODE_DENIED": "当前半自动托管：需在指令/接口里标记 manual_approved 或用 manual source。",
                    "OPEN_COOLDOWN_ACTIVE": "开仓冷却中：等待冷却结束或降低同品种反复触发；检查为何连续失败。",
                    "RISK_REDLINE_DENIED": "触发风控红线：检查 max_positions/保证金占用/风险参数。",
                    "NO_EXCHANGE": "交易所连接为空：检查主控 exchange 初始化/凭证/网络。",
                    "TIMEOUT": "网络或交易所接口超时：检查代理稳定性、OKX 私有接口延迟与重试策略。",
                    "CONNECTION_ERROR": "连接异常：检查网络/代理/会话重建；必要时触发 exchange session rebuild。",
                    "NETWORK_ERROR": "网络故障：检查 DNS/出网/代理。",
                    "INSUFFICIENT_MARGIN": "保证金不足：降低仓位/杠杆或补充资金；检查 margin_mode。",
                    "INSUFFICIENT_FUNDS": "余额不足：检查资金与费用预留。",
                    "SIZE_TOO_SMALL": "下单张数过小：检查 minSz/lotSz，修正 size 计算与步进对齐。",
                    "INSTRUMENT_INVALID": "合约标的无效：检查 symbol 规范化与 instId。",
                    "ALREADY_CLOSED_NO_POSITION": "终态噪声(已无可平仓位)：通常为并发/延迟导致的重复 close，可忽略并检查幂等收敛。",
                    "EXCHANGE_ALL_OPERATIONS_FAILED": "交易所拒单(All operations failed)：检查 reduceOnly/posSide/参数组合，必要时走 close-position fallback。",
                    "POST_CHECK_ANOMALY": "平仓后复核异常：检查 positions 刷新延迟/是否实际成交；必要时二次 close-position。",
                }.get(code, "查看 detail/endpoint/trace_id 对照交易所返回，补齐映射或加更具体的重试/降级。")

            def _severity_from_exchange_code(code: str) -> str:
                c = str(code or "").upper()
                if c in {
                    "NO_EXCHANGE",
                    "TIMEOUT",
                    "CONNECTION_ERROR",
                    "NETWORK_ERROR",
                    "POLICY_DENIED",
                    "HOSTING_MODE_DENIED",
                    "RISK_REDLINE_DENIED",
                }:
                    return "block"
                if c in {"ALREADY_CLOSED_NO_POSITION", "POST_CHECK_ANOMALY"}:
                    return "warn"
                return "warn"

            reason_label_map = {
                "AI_CORE_GUARD:EXCHANGE_UNREACHABLE_OPEN_REJECTED": "交易所不可达拒单",
                "AI_CORE_GUARD:EXCHANGE_DEGRADED_RISK_REDUCED": "交易所降级降风险",
                "AI_CORE_GUARD:ANALYSIS_HARD_REJECTED": "分析硬门控拒单",
                "AI_CORE_GUARD:CONFIDENCE_OPEN_REJECTED": "置信度不足拒单",
                "AI_CORE_GUARD:OPEN_EVIDENCE_REJECTED": "证据不足拒单",
                "AI_CORE_GUARD:RR_REJECTED": "盈亏比不足拒单",
                "AI_CORE_GUARD:SPREAD_REJECTED": "点差过大拒单",
                "AI_CORE_GUARD:DEPTH_IMBALANCE_REJECTED": "深度失衡拒单",
                "AI_CORE_GUARD:FUNDING_RATE_REJECTED": "资金费率过高拒单",
                "AI_CORE_GUARD:OPEN_INTEREST_REJECTED": "持仓量不足拒单",
                "TIMEOUT": "交易所超时",
                "CONNECTION_ERROR": "交易所连接错误",
                "NETWORK_ERROR": "网络错误",
                "NO_EXCHANGE": "交易所不可用",
                "POLICY_DENIED": "策略规则拒绝",
                "HOSTING_MODE_DENIED": "托管模式拒绝",
                "RISK_REDLINE_DENIED": "触发风险红线",
                "OPEN_COOLDOWN_ACTIVE": "开仓冷却中",
                "INSUFFICIENT_MARGIN": "保证金不足",
                "INSUFFICIENT_FUNDS": "余额不足",
                "SIZE_TOO_SMALL": "下单张数过小",
                "INSTRUMENT_INVALID": "无效合约标的",
                "ALREADY_CLOSED_NO_POSITION": "无仓可平（幂等）",
                "POST_CHECK_ANOMALY": "平仓后复核异常",
                "EXCHANGE_ALL_OPERATIONS_FAILED": "交易所全路径拒绝",
            }

            top: List[Dict[str, Any]] = []
            for k, v in top_keys:
                # k = op:code:phase
                parts = k.split(":")
                code = parts[1] if len(parts) > 1 else "UNKNOWN"
                top.append(
                    {
                        "key": k,
                        "key_label": reason_label_map.get(k, code),
                        "count": int(v),
                        "severity": _severity_from_exchange_code(code),
                        "category": "exchange_failure",
                        "group": _group_from_exchange_code(code),
                        "action_hint": _action_hint(code),
                        "samples": samples.get(k, [])[:3],
                    }
                )

            # Merge ai_core execution guard counters to make "no-open" reasons visible
            # even when rejection happened before exchange API calls.
            guard_map = {
                "exchange_unreachable_rejected": "AI_CORE_GUARD:EXCHANGE_UNREACHABLE_OPEN_REJECTED",
                "exchange_degraded_risk_reduced": "AI_CORE_GUARD:EXCHANGE_DEGRADED_RISK_REDUCED",
                "analysis_hard_rejected": "AI_CORE_GUARD:ANALYSIS_HARD_REJECTED",
                "confidence_open_rejected": "AI_CORE_GUARD:CONFIDENCE_OPEN_REJECTED",
                "open_evidence_rejected": "AI_CORE_GUARD:OPEN_EVIDENCE_REJECTED",
                "rr_rejected": "AI_CORE_GUARD:RR_REJECTED",
                "spread_rejected": "AI_CORE_GUARD:SPREAD_REJECTED",
                "depth_imbalance_rejected": "AI_CORE_GUARD:DEPTH_IMBALANCE_REJECTED",
                "funding_rate_rejected": "AI_CORE_GUARD:FUNDING_RATE_REJECTED",
                "open_interest_rejected": "AI_CORE_GUARD:OPEN_INTEREST_REJECTED",
            }
            guard_hints = {
                "exchange_unreachable_rejected": "交易所不可达，已阻断开仓；优先修复 TLS/代理/网络后再恢复自动开仓。",
                "exchange_degraded_risk_reduced": "交易所降级可达，系统已自动降杠杆/降仓位；关注连接质量恢复。",
                "analysis_hard_rejected": "分析硬门控拒绝：检查 quality/confidence/degraded 与 analysis_hard_gate 配置。",
                "confidence_open_rejected": "置信度不足拒绝开仓：检查 ai_core_min_confidence_to_open 与 regime 加成。",
                "open_evidence_rejected": "证据不足拒绝开仓：检查快照/K线是否缺失与超时。",
                "rr_rejected": "盈亏比不足拒绝开仓：检查 SLTP 参数与 min_rr_to_trade。",
                "spread_rejected": "点差过大拒绝开仓：检查流动性、交易时段与 max_spread_bps_to_trade。",
                "depth_imbalance_rejected": "盘口深度失衡拒绝开仓：检查 max_abs_depth_imbalance_to_trade 与 microstructure_use_notional_top20_imbalance。",
                "funding_rate_rejected": "资金费率过高拒绝开仓：检查 microstructure_max_abs_funding_rate_to_trade 与交易拥挤度。",
                "open_interest_rejected": "持仓量过低拒绝开仓：检查 microstructure_min_open_interest_to_trade 与品种流动性。",
            }
            guard_severity = {
                "exchange_unreachable_rejected": "block",
                "exchange_degraded_risk_reduced": "reduce",
                "analysis_hard_rejected": "block",
                "confidence_open_rejected": "block",
                "open_evidence_rejected": "block",
                "rr_rejected": "block",
                "spread_rejected": "block",
                "depth_imbalance_rejected": "block",
                "funding_rate_rejected": "block",
                "open_interest_rejected": "block",
            }
            guard_group = {
                "exchange_unreachable_rejected": "exchange_connectivity",
                "exchange_degraded_risk_reduced": "exchange_connectivity",
                "analysis_hard_rejected": "evidence_quality",
                "open_evidence_rejected": "evidence_quality",
                "confidence_open_rejected": "signal_confidence",
                "rr_rejected": "risk_reward",
                "spread_rejected": "microstructure",
                "depth_imbalance_rejected": "microstructure",
                "funding_rate_rejected": "microstructure",
                "open_interest_rejected": "microstructure",
            }
            ai_core_diag = out.get("ai_core") if isinstance(out.get("ai_core"), dict) else {}
            eg_cfg = ai_core_diag.get("execution_guards") if isinstance(ai_core_diag.get("execution_guards"), dict) else {}
            eg_stats = eg_cfg.get("stats") if isinstance(eg_cfg.get("stats"), dict) else {}
            for stat_key, reason_key in guard_map.items():
                cnt = int(eg_stats.get(stat_key, 0) or 0)
                if cnt <= 0:
                    continue
                top.append(
                    {
                        "key": reason_key,
                        "key_label": reason_label_map.get(reason_key, reason_key),
                        "count": cnt,
                        "severity": guard_severity.get(stat_key, "warn"),
                        "category": "ai_core_guard",
                        "group": guard_group.get(stat_key, "ai_core_other"),
                        "action_hint": guard_hints.get(stat_key, "检查 ai_core 执行门控配置与实时诊断。"),
                        "samples": [],
                    }
                )
            top = sorted(top, key=lambda x: int(x.get("count", 0)), reverse=True)[:12]
            grouped: Dict[str, Dict[str, Any]] = {}
            for item in top:
                grp = str(item.get("group") or "other")
                cur = grouped.get(grp)
                if not cur:
                    cur = {
                        "group": grp,
                        "group_label": group_label_map.get(grp, grp),
                        "count": 0,
                        "severity": "warn",
                        "top_keys": [],
                    }
                    grouped[grp] = cur
                cur["count"] = int(cur.get("count", 0)) + int(item.get("count", 0) or 0)
                sev = str(item.get("severity") or "warn")
                if sev == "block":
                    cur["severity"] = "block"
                elif sev == "reduce" and str(cur.get("severity")) != "block":
                    cur["severity"] = "reduce"
                if len(cur["top_keys"]) < 3:
                    cur["top_keys"].append(str(item.get("key") or ""))
            lead = top[0] if top else None
            lead_group = (
                sorted(
                    list(grouped.values()),
                    key=lambda x: int(x.get("count", 0)),
                    reverse=True,
                )[0]
                if grouped
                else None
            )
            summary = "最近窗口未发现显著拒单/降级主因。"
            summary_label = "运行稳定，未发现显著阻塞。"
            if isinstance(lead, dict):
                sev = str(lead.get("severity") or "warn")
                key = str(lead.get("key") or "")
                key_label = str(lead.get("key_label") or key)
                cnt = int(lead.get("count", 0) or 0)
                grp = str((lead_group or {}).get("group") or lead.get("group") or "other")
                grp_label = str((lead_group or {}).get("group_label") or group_label_map.get(grp, grp))
                grp_cnt = int((lead_group or {}).get("count", 0) or 0) if isinstance(lead_group, dict) else cnt
                if sev == "block":
                    summary = (
                        f"主风险分组={grp_label}（{grp_cnt} 次）；"
                        f"主阻塞原因={key}（{cnt} 次），已触发阻断策略。"
                    )
                    summary_label = (
                        f"{grp_label}为当前主阻塞（{grp_cnt}次），"
                        f"其中{key_label}最突出（{cnt}次）。"
                    )
                elif sev == "reduce":
                    summary = (
                        f"主风险分组={grp_label}（{grp_cnt} 次）；"
                        f"主降风险原因={key}（{cnt} 次），系统在降杠杆/降仓运行。"
                    )
                    summary_label = (
                        f"{grp_label}为当前主降风险来源（{grp_cnt}次），"
                        f"核心因素为{key_label}（{cnt}次）。"
                    )
                else:
                    summary = (
                        f"主风险分组={grp_label}（{grp_cnt} 次）；"
                        f"主要告警原因={key}（{cnt} 次），建议结合样本继续排查。"
                    )
                    summary_label = (
                        f"{grp_label}告警占比最高（{grp_cnt}次），"
                        f"重点关注{key_label}（{cnt}次）。"
                    )

            out["execution_attribution"] = {
                "failures_in_window": len(fails),
                "benign_failures_in_window": len(benign_fails),
                "benign_failure_codes": sorted(list(benign_codes)),
                "top_reasons": top,
                "grouped_reasons": sorted(
                    list(grouped.values()),
                    key=lambda x: int(x.get("count", 0)),
                    reverse=True,
                ),
                "summary": summary,
                "summary_label": summary_label,
            }
        except Exception as e:
            out["execution_attribution_error"] = str(e)

        # 8) Decision contract integrity snapshot (strategy/trace attribution health)
        try:
            eg = out.get("execution_gateway") if isinstance(out.get("execution_gateway"), dict) else {}
            raw_events = (eg.get("recent_events") or []) if isinstance(eg.get("recent_events"), list) else []
            start_time = getattr(mc, "start_time", None)
            runtime_events: List[Dict[str, Any]] = []
            for e in raw_events:
                if not isinstance(e, dict):
                    continue
                if start_time is None:
                    runtime_events.append(e)
                    continue
                try:
                    ets = datetime.fromisoformat(str(e.get("ts") or "").replace("Z", "+00:00")).replace(tzinfo=None)
                    if ets >= start_time:
                        runtime_events.append(e)
                except Exception:
                    continue
            events = runtime_events if start_time is not None else raw_events
            total = 0
            miss_strategy = 0
            miss_trace = 0
            miss_both = 0
            by_source: Dict[str, Dict[str, int]] = {}
            samples: List[Dict[str, Any]] = []
            for e in events:
                if not isinstance(e, dict):
                    continue
                if str(e.get("op") or "").strip().lower() not in {"open", "close"}:
                    continue
                total += 1
                src = str(e.get("source") or "unknown")
                ctx = e.get("context") if isinstance(e.get("context"), dict) else {}
                sid = str(
                    ctx.get("strategy_used")
                    or ctx.get("strategy_id")
                    or ctx.get("strategy")
                    or ""
                ).strip()
                tid = str(e.get("trace_id") or "").strip()
                ms = int(not bool(sid))
                mt = int(not bool(tid))
                if ms:
                    miss_strategy += 1
                if mt:
                    miss_trace += 1
                if ms and mt:
                    miss_both += 1
                g = by_source.get(src)
                if not g:
                    g = {"total": 0, "missing_strategy": 0, "missing_trace": 0}
                    by_source[src] = g
                g["total"] += 1
                g["missing_strategy"] += ms
                g["missing_trace"] += mt
                if (ms or mt) and len(samples) < 8:
                    samples.append(
                        {
                            "ts": e.get("ts"),
                            "op": e.get("op"),
                            "symbol": e.get("symbol"),
                            "source": src,
                            "has_strategy": not ms,
                            "has_trace": not mt,
                            "detail": str(e.get("detail") or "")[:180],
                        }
                    )

            coverage_strategy = (1.0 - float(miss_strategy) / float(total)) if total > 0 else 1.0
            coverage_trace = (1.0 - float(miss_trace) / float(total)) if total > 0 else 1.0
            out["decision_contract_integrity"] = {
                "sample_size": int(total),
                "raw_recent_event_count": len(raw_events),
                "runtime_event_count": len(events),
                "runtime_window_start": start_time.isoformat() if isinstance(start_time, datetime) else None,
                "missing_strategy": int(miss_strategy),
                "missing_trace": int(miss_trace),
                "missing_both": int(miss_both),
                "strategy_coverage": round(float(coverage_strategy), 4),
                "trace_coverage": round(float(coverage_trace), 4),
                "by_source": by_source,
                "samples": samples,
                "healthy": bool(total == 0 or (coverage_strategy >= 0.95 and coverage_trace >= 0.95)),
                "note": "no_runtime_execution_events_since_start" if total == 0 and start_time is not None else None,
            }
            if not bool(out["decision_contract_integrity"]["healthy"]):
                hints = out.get("diagnosis_hints") if isinstance(out.get("diagnosis_hints"), list) else []
                hints.append(
                    "decision_contract_integrity unhealthy: strategy/trace coverage 低于阈值，"
                    "请优先检查 open/close 调用链是否统一透传 decision_envelope + strategy_id + trace_id。"
                )
                out["diagnosis_hints"] = hints
        except Exception as e:
            out["decision_contract_integrity_error"] = str(e)

        return {"success": True, "data": out, "timestamp": datetime.now().isoformat()}

    @router.get("/commander/decision-traces")
    async def commander_decision_traces(limit: int = 50):
        """
        最近 AI 决策轨迹聚合复盘：
        - 门控拒绝原因分布
        - 执行失败分布
        - 对账保护阻断分布
        - 最近轨迹样本
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        try:
            store = getattr(main_controller, "decision_trace_store", None)
            if not store:
                return {
                    "success": True,
                    "data": {"summary": {"sample_size": 0}, "recent": []},
                    "timestamp": datetime.now().isoformat(),
                }
            if hasattr(store, "analyze_recent"):
                data = store.analyze_recent(limit=int(limit or 50))
            else:
                data = {"summary": {"sample_size": 0}, "recent": []}
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/agent-effectiveness")
    async def commander_agent_effectiveness(trace_limit: int = 120, trade_limit: int = 500):
        """
        四智能体有效性摘要：
        - 覆盖率/阻塞率/执行到达率
        - 各智能体的 verdict 分布与 next_action 分布
        - 是否已建立与真实收益的闭环归因
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        try:
            data = await _build_agent_effectiveness_summary(
                main_controller,
                trace_limit=int(trace_limit or 120),
                trade_limit=int(trade_limit or 500),
            )
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/closed-loop-summary")
    async def commander_closed_loop_summary(trace_limit: int = 120):
        """
        交易闭环摘要：
        - 信号/门控/执行/持仓/退出/收益 的一页式诊断
        - 优先面向运行中系统的优化排查，而不是纯历史报表
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        try:
            data = await _build_closed_loop_summary_data(main_controller, trace_limit=int(trace_limit or 120))
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/trading-workflow")
    async def commander_trading_workflow(
        symbol: str = "BTC/USDT",
        trace_limit: int = 200,
        trade_limit: int = 1000,
        recent_trades_limit: int = 40,
        recent_order_hours: float = 4.0,
    ):
        """
        交易全链路工作流报告：
        - 数据/行情/市场结构
        - 当前持仓与 SLTP
        - 开仓门控、拒单、执行事件
        - 平仓原因、收益归因、优化动作
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        try:
            data = await _build_trading_workflow_report(
                main_controller,
                symbol=symbol,
                trace_limit=int(trace_limit or 200),
                trade_limit=int(trade_limit or 1000),
                recent_trades_limit=int(recent_trades_limit or 40),
                recent_order_hours=float(recent_order_hours or 4.0),
            )
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/system-mastery")
    async def commander_system_mastery(
        symbol: str = "BTC/USDT",
        trace_limit: int = 120,
        trade_limit: int = 300,
        recent_trades_limit: int = 20,
    ):
        """
        单接口全局总览：
        - 系统运行 / 故障 / 行情 / 账户 / 持仓
        - 决策 / 拒单 / 执行 / 止盈止损 / 收益
        - 学习状态 / 优化建议 / 观测缺口
        目标：让脚本、前端、人工复盘统一围绕一个标准读取入口。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        try:
            data = await _build_system_mastery_snapshot(
                main_controller,
                symbol=symbol,
                trace_limit=int(trace_limit or 120),
                trade_limit=int(trade_limit or 300),
                recent_trades_limit=int(recent_trades_limit or 20),
            )
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/decision-traces/{trace_id}")
    async def commander_decision_trace_detail(trace_id: str):
        """按 trace_id 查看单条 AI 决策链路。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        try:
            store = getattr(main_controller, "decision_trace_store", None)
            row = store.get_by_trace_id(trace_id) if (store and hasattr(store, "get_by_trace_id")) else None
            if not row:
                return {"success": False, "message": "trace_id not found", "timestamp": datetime.now().isoformat()}
            return {"success": True, "data": row, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/learning/seed-and-run")
    async def commander_learning_seed_and_run(payload: Dict[str, Any] = Body(default_factory=dict)):
        """
        体检/验收用：注入少量合成 trade_close 记忆，并立即触发一次学习周期。
        - 不会触发真实交易
        - 仅用于验证“自我总结与自动优化策略”的闭环是否通
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        mc = main_controller
        mg = getattr(mc, "memory_gateway", None)
        le = getattr(mc, "ai_learning_engine", None)
        if not mg or not hasattr(mg, "add_memory"):
            return {"success": False, "message": "memory_gateway 未就绪", "timestamp": datetime.now().isoformat()}
        if not le:
            return {"success": False, "message": "ai_learning_engine 未就绪", "timestamp": datetime.now().isoformat()}

        # Runtime wiring fix: seed 使用 memory_gateway 写入，学习引擎读取 memory_manager。
        # 若两者未绑定，会导致 _analyze_and_learn() 直接返回且统计不更新。
        if getattr(le, "memory_manager", None) is None:
            le.memory_manager = mg

        n = int((payload or {}).get("n", 8) or 8)
        n = max(3, min(30, n))
        symbol = str((payload or {}).get("symbol") or "BTC/USDT/SWAP")
        base_pnl_pct = float((payload or {}).get("base_pnl_percent", 0.012) or 0.012)
        lesson_pnl_percent = float((payload or {}).get("lesson_pnl_percent", 6.0) or 6.0)
        lesson_pnl_percent = max(5.1, min(40.0, lesson_pnl_percent))
        now = datetime.now()
        seeded = 0
        try:
            for i in range(n):
                # Alternating win/loss patterns to trigger timing/risk lessons.
                pnl_pct = base_pnl_pct if (i % 3 != 0) else (-base_pnl_pct * 1.4)
                pnl = pnl_pct * 100.0
                side = "sell" if pnl_pct >= 0 else "buy"
                await mg.add_memory(
                    memory_type="trade_record",
                    content=f"[synthetic] trade_close {symbol} pnl_pct={pnl_pct:+.4%}",
                    metadata={
                        "kind": "trade_close",
                        "synthetic": True,
                        "symbol": symbol,
                        "side": side,
                        "pnl": float(pnl),
                        "pnl_percent": float(pnl_pct),
                        "timestamp": (now.isoformat()),
                        "reason": "synthetic_seed_for_learning_acceptance",
                    },
                    source_module="module_control_api",
                    importance=0.6,
                    tags=["trade_close", "synthetic", "learning_seed"],
                )
                # Also feed the learning engine's direct intake path so diagnosis metrics
                # update immediately even when memory backend adapters differ.
                if hasattr(le, "record_trade_result"):
                    lesson_pct = lesson_pnl_percent if pnl_pct >= 0 else (-lesson_pnl_percent * 1.2)
                    await le.record_trade_result(
                        {
                            "symbol": symbol,
                            "side": side,
                            "pnl": float(pnl),
                            "pnl_percent": float(lesson_pct),
                            "reason": "synthetic_seed_for_learning_acceptance",
                            "strategy": "seed_acceptance",
                            "timestamp": now.isoformat(),
                        }
                    )
                seeded += 1
        except Exception as e:
            return {"success": False, "message": f"seed_failed: {e}", "seeded": seeded, "timestamp": datetime.now().isoformat()}

        # Run one learning cycle immediately (best-effort)
        try:
            await le._analyze_and_learn()
            await le._generate_learning_report()
            await le._optimize_decision_rules()
        except Exception as e:
            return {"success": False, "message": f"learning_run_failed: {e}", "seeded": seeded, "timestamp": datetime.now().isoformat()}

        return {
            "success": True,
            "seeded": seeded,
            "learning_status": le.get_status() if hasattr(le, "get_status") else {},
            "timestamp": datetime.now().isoformat(),
        }

    @router.post("/commander/learning/weekly-review")
    async def commander_learning_weekly_review(payload: Dict[str, Any] = Body(default_factory=dict)):
        """生成并返回本周研究复盘与学习分析摘要。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        mc = main_controller
        le = getattr(mc, "ai_learning_engine", None)
        if not le or not hasattr(le, "generate_weekly_research_review"):
            return {"success": False, "message": "ai_learning_engine 未就绪", "timestamp": datetime.now().isoformat()}
        try:
            force = bool((payload or {}).get("force", False))
            review = await le.generate_weekly_research_review(force=force)
            status = le.get_status() if hasattr(le, "get_status") else {}
            return {
                "success": True,
                "data": {
                    "weekly_review": review,
                    "learning_analytics": (status or {}).get("learning_analytics"),
                    "retrieval_deck": (status or {}).get("retrieval_deck"),
                    "self_review": (status or {}).get("self_review"),
                    "tuning_governance": (status or {}).get("tuning_governance"),
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/learning/retrieval-deck")
    async def commander_learning_retrieval_deck(payload: Dict[str, Any] = Body(default_factory=dict)):
        """生成主动回忆题卡。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        mc = main_controller
        le = getattr(mc, "ai_learning_engine", None)
        if not le or not hasattr(le, "generate_retrieval_practice_deck"):
            return {"success": False, "message": "ai_learning_engine 未就绪", "timestamp": datetime.now().isoformat()}
        try:
            limit = int((payload or {}).get("limit", 10) or 10)
            deck = await le.generate_retrieval_practice_deck(limit=limit)
            return {"success": True, "data": deck, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/agents/advisory-snapshot")
    async def commander_agents_advisory_snapshot(payload: Dict[str, Any] = Body(default_factory=dict)):
        """返回 market/research/risk/execution 四类 advisory agent 的当前判定。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        mc = main_controller
        orch = getattr(mc, "agent_orchestrator", None)
        if not orch or not hasattr(orch, "evaluate_advisory_snapshot"):
            return {"success": False, "message": "agent_orchestrator 未就绪", "timestamp": datetime.now().isoformat()}
        symbol = str((payload or {}).get("symbol") or "BTC/USDT")
        market_snapshot = dict((payload or {}).get("market_snapshot") or {})
        semantic_context = dict((payload or {}).get("semantic_context") or {})
        strategy_id = str((payload or {}).get("strategy_id") or "")
        sm = getattr(mc, "strategy_manager", None)
        governance = sm.get_strategy_governance_profile(strategy_id) if (sm and strategy_id and hasattr(sm, "get_strategy_governance_profile")) else {}
        research_profile = sm.get_strategy_research_profile(strategy_id) if (sm and strategy_id and hasattr(sm, "get_strategy_research_profile")) else {}
        data = orch.evaluate_advisory_snapshot(
            symbol=symbol,
            market_snapshot=market_snapshot,
            semantic_context=semantic_context,
            governance=governance,
            research_profile=research_profile,
            decision_confidence=float((payload or {}).get("decision_confidence", 0.0) or 0.0),
            trace_id=str((payload or {}).get("trace_id") or ""),
        )
        return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}

    @router.get("/market-structure/multi-source-snapshot")
    async def market_structure_multi_source_snapshot(symbol: str = "BTC/USDT"):
        """聚合 data hub / market intelligence / proactive scanner 后输出统一市场结构快照。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        mc = main_controller
        base: Dict[str, Any] = {"symbol": symbol}
        try:
            hub = getattr(mc, "data_source_hub", None)
            if hub and hasattr(hub, "get_unified_snapshot"):
                snap = await hub.get_unified_snapshot(symbol)
                if isinstance(snap, dict):
                    base.update(
                        {
                            "spread_bps": ((snap.get("microstructure") or {}).get("spread_bps")),
                            "depth_imbalance": ((snap.get("microstructure") or {}).get("depth_imbalance")),
                            "funding_rate": ((snap.get("derivatives") or {}).get("funding_rate")),
                            "open_interest": ((snap.get("derivatives") or {}).get("open_interest")),
                            "basis_bps": ((snap.get("derivatives") or {}).get("basis_bps")),
                            "stablecoin_supply_change": ((snap.get("flows") or {}).get("stablecoin_supply_change")),
                            "exchange_netflow": ((snap.get("flows") or {}).get("exchange_netflow")),
                            "large_wallet_flow": ((snap.get("flows") or {}).get("large_wallet_flow")),
                            "quality_score": ((snap.get("quality") or {}).get("score")),
                        }
                    )
        except Exception:
            pass
        try:
            mi = getattr(mc, "market_intelligence", None)
            if mi and hasattr(mi, "get_cached_symbol_view"):
                view = mi.get_cached_symbol_view(symbol) or {}
                if isinstance(view, dict):
                    for key in ("trend", "confidence", "spread_bps", "depth_imbalance", "quality_score"):
                        if base.get(key) in (None, "", 0, 0.0):
                            base[key] = view.get(key)
        except Exception:
            pass
        try:
            scanner = getattr(getattr(mc, "proactive_ai", None), "market_scanner", None)
            if scanner and hasattr(scanner, "get_market_state"):
                mstate = scanner.get_market_state() or {}
                if isinstance(mstate, dict):
                    flows = mstate.get("flows") if isinstance(mstate.get("flows"), dict) else {}
                    deriv = mstate.get("derivatives") if isinstance(mstate.get("derivatives"), dict) else {}
                    base.setdefault("stablecoin_supply_change", flows.get("stablecoin_supply_change"))
                    base.setdefault("exchange_netflow", flows.get("exchange_netflow"))
                    base.setdefault("large_wallet_flow", flows.get("large_wallet_flow"))
                    base.setdefault("basis_bps", deriv.get("basis_bps"))
        except Exception:
            pass
        try:
            fs = getattr(mc, "feature_store_lite", None)
            if fs and hasattr(fs, "append_raw_market_event"):
                fs.append_raw_market_event(symbol, dict(base))
        except Exception:
            pass
        mse = getattr(mc, "market_structure_engine", None)
        if not mse or not hasattr(mse, "analyze_symbol"):
            return {"success": False, "message": "market_structure_engine 未就绪", "timestamp": datetime.now().isoformat()}
        snap = mse.analyze_symbol(symbol, base).to_dict()
        governance_update = None
        try:
            sm = getattr(mc, "strategy_manager", None)
            if sm and hasattr(sm, "record_market_structure_snapshot"):
                governance_update = sm.record_market_structure_snapshot(symbol, snap, apply_now=True)
        except Exception:
            governance_update = None
        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "market_structure": snap,
                "source_snapshot": base,
                "governance_update": governance_update,
            },
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/commander/research-cockpit")
    async def commander_research_cockpit(symbol: str = "BTC/USDT"):
        """研究/学习/治理/市场结构的聚合驾驶舱接口。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        mc = main_controller
        out: Dict[str, Any] = {"symbol": symbol}

        try:
            structure = await market_structure_multi_source_snapshot(symbol=symbol)
            out["market_structure"] = structure.get("data") if isinstance(structure, dict) else None
        except Exception as e:
            out["market_structure_error"] = str(e)

        try:
            fs = getattr(mc, "feature_store_lite", None)
            out["feature_store"] = {
                "summary": fs.get_summary() if (fs and hasattr(fs, "get_summary")) else None,
                "raw_market_events": fs.get_recent("raw_market_events", 12) if (fs and hasattr(fs, "get_recent")) else [],
                "derived_features": fs.get_recent("derived_features", 12) if (fs and hasattr(fs, "get_recent")) else [],
                "decision_contexts": fs.get_recent("decision_context_snapshots", 12) if (fs and hasattr(fs, "get_recent")) else [],
                "research_labels": fs.get_recent("research_labels", 12) if (fs and hasattr(fs, "get_recent")) else [],
                "execution_outcomes": fs.get_recent("execution_outcomes", 12) if (fs and hasattr(fs, "get_recent")) else [],
            }
        except Exception as e:
            out["feature_store_error"] = str(e)

        try:
            le = getattr(mc, "ai_learning_engine", None)
            status = le.get_status() if (le and hasattr(le, "get_status")) else {}
            out["learning"] = {
                "weekly_review": (status or {}).get("weekly_review"),
                "analytics": (status or {}).get("learning_analytics"),
                "retrieval_deck": (status or {}).get("retrieval_deck"),
                "self_review": (status or {}).get("self_review"),
            }
        except Exception as e:
            out["learning_error"] = str(e)

        try:
            sm = getattr(mc, "strategy_manager", None)
            strategy_rows: List[Dict[str, Any]] = []
            stage_counts: Dict[str, int] = {}
            review_done = 0
            total = 0
            failure_case_total = 0
            if sm and getattr(sm, "strategy_configs", None):
                for sid, cfg in list((sm.strategy_configs or {}).items())[:100]:
                    gov = sm.get_strategy_governance_profile(sid) if hasattr(sm, "get_strategy_governance_profile") else {}
                    rp = sm.get_strategy_research_profile(sid) if hasattr(sm, "get_strategy_research_profile") else {}
                    stage = str(gov.get("stage") or "unknown")
                    stage_counts[stage] = int(stage_counts.get(stage, 0)) + 1
                    total += 1
                    if rp.get("review_completion_status") == "completed":
                        review_done += 1
                    failure_case_total += len(rp.get("failure_cases") or [])
                    strategy_rows.append(
                        {
                            "strategy_id": sid,
                            "name": getattr(cfg, "name", sid),
                            "stage": stage,
                            "oos_status": gov.get("oos_status"),
                            "live_drift_status": gov.get("live_drift_status"),
                            "market_structure_overlay_status": ((gov.get("market_structure_overlay") or {}).get("status") if isinstance(gov.get("market_structure_overlay"), dict) else None),
                            "effective_cap_multiplier": gov.get("effective_cap_multiplier"),
                            "review_completion_status": rp.get("review_completion_status"),
                            "last_review_type": rp.get("last_review_type"),
                            "hypothesis": rp.get("hypothesis"),
                            "failure_case_count": len(rp.get("failure_cases") or []),
                            "parameter_sensitivity_summary": ((rp.get("parameter_sensitivity") or {}).get("summary") if isinstance(rp.get("parameter_sensitivity"), dict) else None),
                        }
                    )
            out["research"] = {
                "strategy_rows": strategy_rows[:40],
                "funnel": {"total": total, "by_stage": stage_counts},
                "review_completion_rate": round((review_done / total), 4) if total else 0.0,
                "failure_case_total": failure_case_total,
                "market_structure_governance": (sm.get_market_structure_governance_status() if (sm and hasattr(sm, "get_market_structure_governance_status")) else None),
            }
        except Exception as e:
            out["research_error"] = str(e)

        try:
            orch = getattr(mc, "agent_orchestrator", None)
            if orch and hasattr(orch, "evaluate_advisory_snapshot"):
                ms = ((out.get("market_structure") or {}).get("source_snapshot")) if isinstance(out.get("market_structure"), dict) else {}
                out["agent_panel"] = orch.evaluate_advisory_snapshot(
                    symbol=symbol,
                    market_snapshot=ms or {"symbol": symbol},
                    semantic_context=((out.get("market_structure") or {}).get("market_structure")) if isinstance(out.get("market_structure"), dict) else {},
                    governance={},
                    research_profile={},
                    decision_confidence=float((((out.get("market_structure") or {}).get("market_structure")) or {}).get("confidence", 0.0) or 0.0),
                    trace_id="research-cockpit",
                )
        except Exception as e:
            out["agent_panel_error"] = str(e)

        return {"success": True, "data": out, "timestamp": datetime.now().isoformat()}

    @router.post("/commander/account-sync/run")
    async def commander_account_sync_run(payload: Dict[str, Any] = Body(default_factory=dict)):
        """强制同步余额/持仓并接管 SLTP（与启动时 force_sync 相同语义）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "force_sync_account_state"):
            return {"success": False, "message": "同步能力不可用", "timestamp": datetime.now().isoformat()}
        reason = str((payload or {}).get("reason") or "api")
        try:
            # 与 diagnostics 对齐：账户私有接口偶发抖动时，避免 API 长时间悬挂。
            data = await asyncio.wait_for(
                main_controller.force_sync_account_state(reason=reason),
                timeout=45.0,
            )
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except asyncio.TimeoutError:
            return {
                "success": True,
                "degraded": True,
                "data": {"status": "timeout_degraded", "hint": "account_sync_timeout", "reason": reason},
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    s1_router = APIRouter(prefix="/api/v1/s1", tags=["s1"])

    @s1_router.get("/verify")
    async def s1_full_verify():
        """
        S1 全自动验收探针：主控、ExecutionGateway、策略配置、交易所、止盈止损。
        供脚本/监控轮询；返回 all_passed 与各子检查项。
        """
        checks: List[Dict[str, Any]] = []
        details: Dict[str, Any] = {}

        def add_check(name: str, passed: bool, detail: str = "") -> None:
            checks.append({"name": name, "passed": bool(passed), "detail": detail})

        if not main_controller:
            add_check("main_controller", False, "missing")
            return {"ok": False, "all_passed": False, "checks": checks, "details": details}

        add_check("main_controller", True, "present")
        mc = main_controller

        gw = getattr(mc, "execution_gateway", None)
        add_check("execution_gateway", gw is not None, "missing" if gw is None else "ok")
        if gw:
            try:
                snap = await asyncio.wait_for(gw.get_snapshot(), timeout=2.5)
                details["execution_spine"] = snap
                add_check(
                    "execution_spine.single_write_owner",
                    bool(snap.get("single_write_owner")),
                    str(snap.get("single_write_owner") or ""),
                )
            except asyncio.TimeoutError:
                details["execution_spine"] = {"degraded": True, "error": "snapshot_timeout"}
                add_check("execution_spine", False, "snapshot_timeout")
            except Exception as e:
                add_check("execution_spine", False, str(e))

        ac = getattr(mc, "ai_core", None)
        add_check("ai_core", ac is not None, "missing" if ac is None else "ok")

        try:
            brain = await asyncio.wait_for(
                mc.get_ai_managed_config(
                    "ai_brain",
                    {
                        "primary_controller": "ai_core",
                        "single_write_owner": "ai_core",
                        "enable_secondary_controller": False,
                    },
                ),
                timeout=2.0,
            )
            details["ai_brain"] = {
                "primary_controller": brain.get("primary_controller"),
                "single_write_owner": brain.get("single_write_owner"),
                "enable_secondary_controller": brain.get("enable_secondary_controller"),
            }
            swo = str(brain.get("single_write_owner") or brain.get("primary_controller") or "").strip().lower()
            add_check("ai_brain.single_write_owner", bool(swo), swo or "empty")
            pri = str(brain.get("primary_controller") or "").strip().lower()
            coherent = (not pri or not swo) or (pri == swo)
            add_check(
                "ai_brain.primary_coherent_with_swo",
                coherent,
                f"primary={pri} swo={swo}" + ("" if coherent else " (建议保持一致)"),
            )
        except Exception as e:
            add_check("ai_brain_config", False, str(e))

        sl = getattr(mc, "stop_loss_manager", None)
        add_check("stop_loss_manager", sl is not None, "missing" if sl is None else "ok")

        ex = mc.get_exchange() if hasattr(mc, "get_exchange") else None
        ex = ex or getattr(mc, "okx_exchange", None)
        add_check("exchange", ex is not None, "missing" if ex is None else type(ex).__name__)

        ait = getattr(mc, "ai_trading_engine", None)
        if ait and hasattr(ait, "_autonomous_trading_execution_allowed"):
            try:
                allow_loop = await asyncio.wait_for(
                    ait._autonomous_trading_execution_allowed(),
                    timeout=2.0,
                )
                details["ai_trading_engine"] = {
                    "autonomous_trading_loop_allowed": allow_loop,
                }
                try:
                    pol = await asyncio.wait_for(
                        mc.get_ai_managed_config("ai_brain", {}),
                        timeout=2.0,
                    )
                    swo2 = str(
                        pol.get("single_write_owner") or pol.get("primary_controller") or "ai_core"
                    ).strip().lower()
                except Exception:
                    swo2 = "ai_core"
                if swo2 == "ai_core":
                    add_check(
                        "s1_aitrading_loop_suppressed_when_swo_ai_core",
                        not allow_loop,
                        "loop allowed (unexpected)" if allow_loop else "main loop skipped as expected",
                    )
                else:
                    add_check(
                        "s1_aitrading_loop_policy",
                        True,
                        f"swo={swo2} allow_loop={allow_loop}",
                    )
            except Exception as e:
                add_check("ai_trading_engine_policy", False, str(e))

        try:
            sys_status = await asyncio.wait_for(mc.get_system_status(), timeout=4.0)
            details["system_status_keys"] = list(sys_status.keys()) if isinstance(sys_status, dict) else []
            if isinstance(sys_status, dict) and "execution_spine" in sys_status:
                add_check("get_system_status.execution_spine", True, "present")
            else:
                add_check("get_system_status.execution_spine", False, "missing in status payload")
        except asyncio.TimeoutError:
            add_check("get_system_status", False, "timeout")
        except Exception as e:
            add_check("get_system_status", False, str(e))

        all_passed = all(c.get("passed") for c in checks)
        return {
            "ok": True,
            "all_passed": all_passed,
            "timestamp": datetime.now().isoformat(),
            "checks": checks,
            "details": details,
        }

    from src.modules.api.module_surface import attach_module_surface_routes
    from src.modules.api.standard_registry import attach_standard_domain_apis

    attach_module_surface_routes(router, main_controller)

    # 标准化域 API：测试和轻量启动路径直接调用 init_module_control_api 时也能获得
    # /api/v1/{domain}/... 新入口。旧 modules 路由仍暂存为底层能力来源。
    attach_standard_domain_apis(app, main_controller)

    app.include_router(router)
    app.include_router(trade_router)
    app.include_router(market_router)
    app.include_router(s1_router)
    logger.info("✅ 模块控制API已初始化")
