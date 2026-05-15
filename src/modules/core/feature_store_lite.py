from __future__ import annotations

from collections import Counter, deque
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional


class FeatureStoreLite:
    """
    Lightweight in-process feature/event registry.

    Keeps the latest slices of:
    - raw_market_events
    - derived_features
    - decision_context_snapshots
    - guard_results
    - execution_outcomes
    - research_labels
    """

    def __init__(self, max_items_per_table: int = 500, persist_path: Optional[str] = None) -> None:
        cap = max(50, int(max_items_per_table or 500))
        self.max_items_per_table = cap
        self.persist_path = str(persist_path or self._default_persist_path())
        self._tables: Dict[str, Deque[Dict[str, Any]]] = {
            "raw_market_events": deque(maxlen=cap),
            "derived_features": deque(maxlen=cap),
            "decision_context_snapshots": deque(maxlen=cap),
            "guard_results": deque(maxlen=cap),
            "execution_outcomes": deque(maxlen=cap),
            "research_labels": deque(maxlen=cap),
        }
        self._load()

    def append(self, table: str, row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        name = str(table or "").strip()
        if name not in self._tables:
            raise KeyError(f"unknown feature table: {name}")
        payload = dict(row or {})
        payload.setdefault("recorded_at", datetime.now().isoformat())
        self._tables[name].append(payload)
        self._persist()
        return payload

    def append_raw_market_event(self, symbol: str, row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = dict(row or {})
        payload.setdefault("symbol", symbol)
        return self.append("raw_market_events", payload)

    def append_derived_features(self, symbol: str, row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = dict(row or {})
        payload.setdefault("symbol", symbol)
        return self.append("derived_features", payload)

    def append_decision_context(self, trace_id: str, row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = dict(row or {})
        payload.setdefault("trace_id", trace_id)
        return self.append("decision_context_snapshots", payload)

    def append_execution_outcome(self, trace_id: str, row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = dict(row or {})
        payload.setdefault("trace_id", trace_id)
        return self.append("execution_outcomes", payload)

    def append_guard_result(self, trace_id: str, row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = dict(row or {})
        payload.setdefault("trace_id", trace_id)
        return self.append("guard_results", payload)

    def append_research_label(self, strategy_id: str, row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = dict(row or {})
        payload.setdefault("strategy_id", strategy_id)
        return self.append("research_labels", payload)

    def get_recent(self, table: str, limit: int = 20) -> List[Dict[str, Any]]:
        name = str(table or "").strip()
        if name not in self._tables:
            return []
        n = max(1, min(int(limit or 20), self.max_items_per_table))
        return list(self._tables[name])[-n:]

    def get_summary(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "tables": {
                name: {"count": len(rows), "latest_recorded_at": rows[-1].get("recorded_at") if rows else None}
                for name, rows in self._tables.items()
            }
        }
        out["decision_funnel"] = self._decision_funnel_summary()
        out["guard_status"] = self._counter_summary("guard_results", "status")
        out["execution_status"] = self._counter_summary("execution_outcomes", "status")
        out["execution_operations"] = self._counter_summary("execution_outcomes", "op")
        out["execution_symbols"] = self._counter_summary("execution_outcomes", "symbol")
        out["research_stage"] = self._counter_summary("research_labels", "stage")
        out["guard_rejection_reasons"] = self._guard_rejection_summary()
        out["persist_path"] = self.persist_path
        return out

    def _counter_summary(self, table: str, field: str) -> Dict[str, Any]:
        ctr = Counter()
        for row in self._tables.get(table, []):
            key = str((row or {}).get(field) or "unknown")
            ctr[key] += 1
        return {"sample_size": sum(ctr.values()), "by_value": dict(ctr)}

    def _decision_funnel_summary(self) -> Dict[str, Any]:
        ctr = Counter()
        for row in self._tables.get("decision_context_snapshots", []):
            key = str((row or {}).get("decision_action") or "unknown")
            ctr[key] += 1
        return {"sample_size": sum(ctr.values()), "by_action": dict(ctr)}

    def _guard_rejection_summary(self) -> Dict[str, Any]:
        ctr = Counter()
        for row in self._tables.get("guard_results", []):
            status = str((row or {}).get("status") or "")
            if status != "rejected":
                continue
            reason = (row or {}).get("reason")
            if reason:
                ctr[str(reason)] += 1
        return {"sample_size": sum(ctr.values()), "by_reason": dict(ctr)}

    @staticmethod
    def _default_persist_path() -> Path:
        root = Path(__file__).resolve().parents[3]
        return root / "data" / "runtime" / "feature_store_lite.json"

    def _load(self) -> None:
        path = Path(self.persist_path)
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        tables = payload.get("tables") if isinstance(payload, dict) else {}
        if not isinstance(tables, dict):
            return
        for name, rows in tables.items():
            if name not in self._tables or not isinstance(rows, list):
                continue
            self._tables[name].clear()
            for row in rows[-self.max_items_per_table:]:
                if isinstance(row, dict):
                    self._tables[name].append(dict(row))

    def _persist(self) -> None:
        path = Path(self.persist_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "persisted_at": datetime.now().isoformat(),
                "max_items_per_table": self.max_items_per_table,
                "tables": {name: list(rows) for name, rows in self._tables.items()},
            }
            path.write_text(json.dumps(payload, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")
        except Exception:
            return
