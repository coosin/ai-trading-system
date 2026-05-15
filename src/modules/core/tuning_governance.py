from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _default_persist_path() -> str:
    root = Path(__file__).resolve().parents[3]
    return str(root / "data" / "runtime" / "tuning_governance.json")


class TuningGovernance:
    """
    Controlled self-optimization gate.

    - auto-apply only for explicit whitelist items
    - record every suggestion / apply / rejection
    - keep observation metadata for later review
    """

    DEFAULT_WHITELIST: Dict[str, Dict[str, Any]] = {
        "ai_core_runtime.ai_core_min_confidence_to_open": {"min": 0.65, "max": 0.86, "auto_apply": True},
        "ai_core_runtime.default_max_margin_fraction": {"min": 0.08, "max": 0.55, "auto_apply": True},
        "ai_core_runtime.min_rr_to_trade": {"min": 0.9, "max": 2.1, "auto_apply": True},
        "ai_core_runtime.edge_min_net_reward_pct": {"min": 0.0015, "max": 0.012, "auto_apply": True},
    }

    def __init__(self, config_manager: Any = None, *, persist_path: Optional[str] = None) -> None:
        self.config_manager = config_manager
        self.persist_path = (persist_path or _default_persist_path()).strip()
        self.records: List[Dict[str, Any]] = []
        self.whitelist = dict(self.DEFAULT_WHITELIST)
        self._load()

    def _load(self) -> None:
        fp = Path(self.persist_path)
        if not fp.is_file():
            return
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.records = list(data.get("records") or [])
                wl = data.get("whitelist")
                if isinstance(wl, dict) and wl:
                    self.whitelist = dict(wl)
        except Exception as e:
            logger.warning("tuning_governance load failed: %s", e)

    def _persist(self) -> None:
        try:
            fp = Path(self.persist_path)
            fp.parent.mkdir(parents=True, exist_ok=True)
            payload = {"records": self.records[-500:], "whitelist": self.whitelist}
            fd, tmp_name = tempfile.mkstemp(prefix=".tgov_", suffix=".tmp", dir=str(fp.parent))
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                json.dump(payload, tmp, ensure_ascii=False)
            os.replace(tmp_name, str(fp))
        except Exception as e:
            logger.warning("tuning_governance persist failed: %s", e)

    async def evaluate_and_apply(
        self,
        suggestions: List[Dict[str, Any]],
        *,
        source: str,
        observation_days: int = 7,
    ) -> Dict[str, Any]:
        applied: List[Dict[str, Any]] = []
        pending: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        for suggestion in suggestions:
            section = str(suggestion.get("section") or "").strip()
            key = str(suggestion.get("key") or "").strip()
            fq = f"{section}.{key}" if section and key else ""
            rule = self.whitelist.get(fq)
            rec = {
                "timestamp": datetime.now().isoformat(),
                "source": source,
                "section": section,
                "key": key,
                "old": suggestion.get("old"),
                "new": suggestion.get("new"),
                "reason": suggestion.get("reason"),
                "expected_impact": suggestion.get("expected_impact"),
                "status": "pending",
                "observation_until": (datetime.now() + timedelta(days=max(1, int(observation_days)))).isoformat(),
            }
            if not rule:
                rec["status"] = "rejected"
                rec["rejection_reason"] = "not_whitelisted"
                rejected.append(rec)
                self.records.append(rec)
                continue

            new_value = suggestion.get("new")
            try:
                new_float = float(new_value)
            except Exception:
                rec["status"] = "rejected"
                rec["rejection_reason"] = "non_numeric_value"
                rejected.append(rec)
                self.records.append(rec)
                continue

            min_v = float(rule.get("min"))
            max_v = float(rule.get("max"))
            if new_float < min_v or new_float > max_v:
                rec["status"] = "rejected"
                rec["rejection_reason"] = "out_of_bounds"
                rec["bounds"] = {"min": min_v, "max": max_v}
                rejected.append(rec)
                self.records.append(rec)
                continue

            auto_apply = bool(rule.get("auto_apply", False))
            if auto_apply and self.config_manager is not None and hasattr(self.config_manager, "set_config"):
                await self.config_manager.set_config(section, key, new_float)
                rec["status"] = "auto_applied"
                applied.append(rec)
            else:
                rec["status"] = "approval_required"
                pending.append(rec)
            self.records.append(rec)

        self.records = self.records[-500:]
        self._persist()
        return {"applied": applied, "pending": pending, "rejected": rejected}

    def get_status(self) -> Dict[str, Any]:
        recent = self.records[-50:]
        counts = {"auto_applied": 0, "approval_required": 0, "rejected": 0}
        for row in recent:
            st = str((row or {}).get("status") or "")
            if st in counts:
                counts[st] += 1
        return {
            "whitelist": dict(self.whitelist),
            "recent_counts": counts,
            "recent_records": recent[-12:],
        }
