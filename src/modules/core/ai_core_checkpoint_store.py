from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_path() -> str:
    p = (os.getenv("OPENCLAW_AI_CORE_CHECKPOINT_JSON") or "").strip()
    if p:
        return p
    root = Path(__file__).resolve().parents[3]
    return str(root / "data" / "runtime" / "ai_core_checkpoint.json")


class AICoreCheckpointStore:
    """
    Lightweight JSON checkpoint for AI core runtime state.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = str(path or _default_path())

    def save(self, state: Dict[str, Any]) -> bool:
        try:
            fp = Path(self._path)
            fp.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": _utcnow_iso(),
                "state": state,
            }
            fd, tmp_name = tempfile.mkstemp(prefix=".ai_core_ckpt_", suffix=".tmp", dir=str(fp.parent))
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp_name, str(fp))
            return True
        except Exception as e:
            logger.warning("ai_core checkpoint save failed: %s", e)
            return False

    def load(self) -> Optional[Dict[str, Any]]:
        fp = Path(self._path)
        if not fp.is_file():
            return None
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return None
            st = payload.get("state")
            return st if isinstance(st, dict) else None
        except Exception as e:
            logger.warning("ai_core checkpoint load failed: %s", e)
            return None
