"""
OpenClaw 对外 HTTP API 基址解析（脚本 / 巡检 / 工具共用）。

优先级：``OPENCLAW_API_BASE`` > ``ACCEPTANCE_BASE`` > ``BASE_URL`` > 默认本机 8000。
"""

from __future__ import annotations

import os


def default_openclaw_api_base() -> str:
    base = (
        (os.environ.get("OPENCLAW_API_BASE") or "").strip()
        or (os.environ.get("ACCEPTANCE_BASE") or "").strip()
        or (os.environ.get("BASE_URL") or "").strip()
        or "http://127.0.0.1:8000"
    )
    return base.rstrip("/")


def openclaw_api_url(path: str) -> str:
    """path 须以 ``/`` 开头（例如 ``/api/v1/system/health``）。"""
    p = path.strip()
    if not p.startswith("/"):
        p = "/" + p
    return default_openclaw_api_base() + p
