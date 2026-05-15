from __future__ import annotations

from datetime import datetime
from typing import Any, Dict


def ok(data: Any = None, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "success": True,
        "data": data if data is not None else {},
        "timestamp": datetime.now().isoformat(),
    }
    payload.update(extra)
    return payload


def fail(message: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "success": False,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }
    payload.update(extra)
    return payload

