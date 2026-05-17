from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


CANONICAL_AGENT_OUTPUT_NAMES = {
    "market_structure_agent",
    "research_agent",
    "risk_governor_agent",
    "execution_coach_agent",
    "execution_gateway",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_persist_path() -> str:
    """
    Optional JSON snapshot for warm restart. Override with OPENCLAW_DECISION_TRACE_STORE_JSON.

    Anchored to repo root (this file: src/modules/core/...) so persistence works even when
    cwd is not the project directory (systemd/docker/exec from another folder).
    """
    p = (os.getenv("OPENCLAW_DECISION_TRACE_STORE_JSON") or "").strip()
    if p:
        return p
    root = Path(__file__).resolve().parents[3]
    return str(root / "data" / "runtime" / "decision_trace_store.json")


class DecisionTraceStore:
    """
    Lightweight in-memory trace store for decision -> guard -> execution lifecycle.
    """

    def __init__(self, max_items: int = 300, *, persist_path: Optional[str] = None) -> None:
        self._max_items = max(50, int(max_items or 300))
        self._items: List[Dict[str, Any]] = []
        self._by_trace_id: Dict[str, Dict[str, Any]] = {}
        self._persist_path: Optional[str] = None
        disabled = str(os.getenv("OPENCLAW_DECISION_TRACE_PERSIST", "1")).strip().lower() in (
            "0",
            "false",
            "no",
            "off",
        )
        # None means "use the production default"; an explicit empty string is
        # used by unit tests and ephemeral stores to disable disk persistence.
        path = (_default_persist_path() if persist_path is None else str(persist_path)).strip()
        if (not disabled) and path:
            self._persist_path = path
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self._persist_path:
            return
        fp = Path(self._persist_path)
        if not fp.is_file():
            return
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return
            items: List[Dict[str, Any]] = []
            for row in data:
                if not isinstance(row, dict):
                    continue
                tid = str(row.get("trace_id") or "").strip()
                if not tid:
                    continue
                self._sanitize_row(row)
                items.append(row)
            while len(items) > self._max_items:
                items.pop(0)
            self._items = items
            self._by_trace_id = {str(r.get("trace_id") or ""): r for r in items if r.get("trace_id")}
        except Exception as e:
            logger.warning("decision_trace_store load failed: %s", e)

    def _sanitize_row(self, row: Dict[str, Any]) -> None:
        if not isinstance(row, dict):
            return
        agents = row.get("agent_outputs") if isinstance(row.get("agent_outputs"), dict) else {}
        semantic = row.get("semantic_signals") if isinstance(row.get("semantic_signals"), dict) else {}
        clean_agents: Dict[str, Any] = {}
        clean_semantic: Dict[str, Any] = dict(semantic)
        for name, payload in agents.items():
            key = str(name or "").strip()
            if not key or not isinstance(payload, dict):
                continue
            if key in CANONICAL_AGENT_OUTPUT_NAMES:
                clean_agents[key] = payload
            else:
                clean_semantic[key] = payload
        row["agent_outputs"] = clean_agents
        if clean_semantic:
            row["semantic_signals"] = clean_semantic

    def _persist_to_disk(self) -> None:
        if not self._persist_path:
            return
        try:
            fp = Path(self._persist_path)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=".dts_", suffix=".tmp", dir=str(fp.parent))
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                json.dump(self._items, tmp, ensure_ascii=False)
            os.replace(tmp_name, str(fp))
        except Exception as e:
            logger.warning("decision_trace_store persist failed: %s", e)

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
                "market_context": {},
                "agent_outputs": {},
                "semantic_signals": {},
                "workflow": {
                    "mode": None,
                    "current_stage": None,
                    "status": "pending",
                    "workflow_path": [],
                    "last_transition_at": _utc_now(),
                },
                "stage_history": [],
                "learning": {},
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
        self._merge_semantic_fields(cur, extras or {}, source="intent")
        self._advance_workflow(
            cur,
            stage="intent",
            status="recorded",
            mode=self._extract_workflow_mode(extras or {}),
            workflow_path=self._extract_workflow_path(extras or {}),
        )
        self._persist_to_disk()

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
        self._merge_semantic_fields(cur, extras or {}, source="guard")
        wf_status = "blocked" if status in {"rejected", "skipped"} else ("passed" if status in {"passed", "allowed"} else status)
        self._advance_workflow(cur, stage=f"guard:{str(stage or '').strip() or 'unknown'}", status=wf_status)
        self._persist_to_disk()

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
        self._merge_semantic_fields(cur, extras or {}, source="execution")
        wf_status = "completed" if status == "success" else ("failed" if status in {"failed", "error", "rejected"} else status)
        self._advance_workflow(cur, stage=f"execution:{str(op or source or 'unknown')}", status=wf_status)
        self._persist_to_disk()

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
        self._merge_semantic_fields(cur, extras or {}, source="reconciliation")
        wf_status = "reconciled" if status == "success" else ("reconcile_blocked" if status in {"blocked", "failed", "error"} else status)
        self._advance_workflow(cur, stage="reconciliation", status=wf_status)
        self._persist_to_disk()

    def record_agent_verdict(
        self,
        *,
        trace_id: str,
        agent_name: str,
        verdict: Dict[str, Any],
    ) -> None:
        cur = self._touch(trace_id)
        outputs = cur.get("agent_outputs") if isinstance(cur.get("agent_outputs"), dict) else {}
        outputs[str(agent_name or "unknown")] = dict(verdict or {})
        cur["agent_outputs"] = outputs
        self._merge_semantic_fields(cur, verdict or {}, source=str(agent_name or "agent"))
        self._persist_to_disk()

    def record_learning_feedback(
        self,
        *,
        trace_id: str,
        lesson_summary: str,
        mistake_tags: Optional[List[str]] = None,
        tuning_suggestion: Optional[Dict[str, Any]] = None,
        self_review_score: Optional[float] = None,
    ) -> None:
        cur = self._touch(trace_id)
        cur["learning"] = {
            "at": _utc_now(),
            "lesson_summary": str(lesson_summary or "")[:500],
            "mistake_tags": list(mistake_tags or []),
            "tuning_suggestion": dict(tuning_suggestion or {}),
            "self_review_score": self_review_score,
        }
        self._persist_to_disk()

    def record_workflow_stage(
        self,
        *,
        trace_id: str,
        stage: str,
        status: str,
        mode: Optional[str] = None,
        workflow_path: Optional[List[str]] = None,
        extras: Optional[Dict[str, Any]] = None,
    ) -> None:
        cur = self._touch(trace_id)
        self._advance_workflow(
            cur,
            stage=stage,
            status=status,
            mode=mode,
            workflow_path=workflow_path,
            extras=extras,
        )
        self._persist_to_disk()

    def _merge_semantic_fields(self, cur: Dict[str, Any], extras: Dict[str, Any], *, source: str) -> None:
        if not isinstance(extras, dict):
            return
        market = cur.get("market_context") if isinstance(cur.get("market_context"), dict) else {}
        for field in (
            "regime_label",
            "risk_posture",
            "trend_state",
            "volatility_state",
            "liquidity_state",
            "derivatives_state",
            "stablecoin_flow_state",
            "execution_quality_state",
            "signal_conflict_score",
            "strategy_stage",
            "oos_status",
            "live_drift_status",
            "memory_refs",
            "knowledge_refs",
        ):
            val = extras.get(field)
            if val is None and field == "regime_label":
                val = extras.get("regime")
            if val is not None:
                market[field] = val
        cur["market_context"] = market
        signals = cur.get("semantic_signals") if isinstance(cur.get("semantic_signals"), dict) else {}
        if any(k in extras for k in ("risk_verdict", "execution_recommendation", "lesson_summary", "tuning_suggestion")):
            signals[source] = {
                "risk_verdict": extras.get("risk_verdict"),
                "execution_recommendation": extras.get("execution_recommendation"),
                "lesson_summary": extras.get("lesson_summary"),
                "mistake_tags": extras.get("mistake_tags"),
                "tuning_suggestion": extras.get("tuning_suggestion"),
            }
            cur["semantic_signals"] = signals

    @staticmethod
    def _extract_workflow_mode(extras: Dict[str, Any]) -> Optional[str]:
        if not isinstance(extras, dict):
            return None
        raw = extras.get("workflow_mode")
        if raw is not None:
            return str(raw)
        dc = extras.get("decision_trace_contract")
        if isinstance(dc, dict) and dc.get("workflow_mode") is not None:
            return str(dc.get("workflow_mode"))
        return None

    @staticmethod
    def _extract_workflow_path(extras: Dict[str, Any]) -> Optional[List[str]]:
        if not isinstance(extras, dict):
            return None
        raw = extras.get("workflow_path")
        if isinstance(raw, list):
            return [str(x) for x in raw if str(x or "").strip()]
        return None

    def _advance_workflow(
        self,
        cur: Dict[str, Any],
        *,
        stage: str,
        status: str,
        mode: Optional[str] = None,
        workflow_path: Optional[List[str]] = None,
        extras: Optional[Dict[str, Any]] = None,
    ) -> None:
        wf = cur.get("workflow") if isinstance(cur.get("workflow"), dict) else {}
        now = _utc_now()
        if mode is not None:
            wf["mode"] = str(mode)
        if workflow_path:
            wf["workflow_path"] = [str(x) for x in workflow_path if str(x or "").strip()]
        wf["current_stage"] = str(stage or "unknown")
        wf["status"] = str(status or "unknown")
        wf["last_transition_at"] = now
        cur["workflow"] = wf

        history = cur.get("stage_history") if isinstance(cur.get("stage_history"), list) else []
        payload: Dict[str, Any] = {"at": now, "stage": str(stage or "unknown"), "status": str(status or "unknown")}
        if mode is not None:
            payload["mode"] = str(mode)
        if extras:
            payload["extras"] = dict(extras)
        if not history or history[-1].get("stage") != payload["stage"] or history[-1].get("status") != payload["status"]:
            history.append(payload)
        cur["stage_history"] = history

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
        hold_reason_tags: Dict[str, int] = {}
        regimes: Dict[str, int] = {}
        risk_verdicts: Dict[str, int] = {}
        strategy_stages: Dict[str, int] = {}
        workflow_stages: Dict[str, int] = {}
        workflow_statuses: Dict[str, int] = {}

        for row in rows:
            if not isinstance(row, dict):
                continue
            sym = str(row.get("symbol") or "")
            if sym:
                symbol_counts[sym] = int(symbol_counts.get(sym, 0)) + 1

            guard = row.get("guard") if isinstance(row.get("guard"), dict) else {}
            extras_g = guard.get("extras") if isinstance(guard.get("extras"), dict) else {}
            hrt = extras_g.get("hold_reason_tags")
            if isinstance(hrt, dict):
                for tk, tv in hrt.items():
                    if tv:
                        hold_reason_tags[str(tk)] = int(hold_reason_tags.get(str(tk), 0)) + 1
            market_context = row.get("market_context") if isinstance(row.get("market_context"), dict) else {}
            regime = str(market_context.get("regime_label") or "")
            if regime:
                regimes[regime] = int(regimes.get(regime, 0)) + 1
            stage_name = str(market_context.get("strategy_stage") or "")
            if stage_name:
                strategy_stages[stage_name] = int(strategy_stages.get(stage_name, 0)) + 1
            agent_outputs = row.get("agent_outputs") if isinstance(row.get("agent_outputs"), dict) else {}
            semantic_signals = row.get("semantic_signals") if isinstance(row.get("semantic_signals"), dict) else {}
            counted_risk_verdict = False
            for _agent_name, verdict in agent_outputs.items():
                if not isinstance(verdict, dict):
                    continue
                risk_verdict = str(verdict.get("risk_verdict") or "")
                if risk_verdict:
                    risk_verdicts[risk_verdict] = int(risk_verdicts.get(risk_verdict, 0)) + 1
                    counted_risk_verdict = True
            if not counted_risk_verdict:
                for verdict in semantic_signals.values():
                    if not isinstance(verdict, dict):
                        continue
                    risk_verdict = str(verdict.get("risk_verdict") or "")
                    if risk_verdict:
                        risk_verdicts[risk_verdict] = int(risk_verdicts.get(risk_verdict, 0)) + 1
            workflow = row.get("workflow") if isinstance(row.get("workflow"), dict) else {}
            wf_stage = str(workflow.get("current_stage") or "")
            if wf_stage:
                workflow_stages[wf_stage] = int(workflow_stages.get(wf_stage, 0)) + 1
            wf_status = str(workflow.get("status") or "")
            if wf_status:
                workflow_statuses[wf_status] = int(workflow_statuses.get(wf_status, 0)) + 1
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
            "top_hold_reason_tags": _top(hold_reason_tags),
            "top_regimes": _top(regimes),
            "top_risk_verdicts": _top(risk_verdicts),
            "top_strategy_stages": _top(strategy_stages),
            "top_workflow_stages": _top(workflow_stages),
            "top_workflow_statuses": _top(workflow_statuses),
            "top_execution_failures": _top(execution_details),
            "top_reconciliation_blocks": _top(reconciliation_details),
            "top_symbols": _top(symbol_counts),
            "recent": rows,
        }
