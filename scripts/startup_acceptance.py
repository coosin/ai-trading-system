#!/usr/bin/env python3
"""
启动后验收：轮询 /health，拉取 /api/v1/system/status 与 /api/v1/system/acceptance。
用法：
  ACCEPTANCE_BASE=http://127.0.0.1:8000 python3 scripts/startup_acceptance.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


def _get(url: str, timeout: float = 90.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read().decode("utf-8", errors="replace")


def wait_health(base: str, total_wait: float = 120.0, step: float = 3.0) -> None:
    deadline = time.time() + total_wait
    last_err = ""
    while time.time() < deadline:
        try:
            code, body = _get(f"{base.rstrip('/')}/health", timeout=20.0)
            if code < 400 and "healthy" in body.lower():
                print(f"[OK] /health 就绪 ({code})")
                return
        except Exception as e:
            last_err = str(e)
        time.sleep(step)
    raise SystemExit(f"健康检查超时: {last_err}")


def main() -> int:
    base = os.environ.get("ACCEPTANCE_BASE", "http://127.0.0.1:8000").rstrip("/")
    print(f"验收目标: {base}")
    wait_health(base)

    paths = (
        ("/health", "根健康检查"),
        ("/api/v1/system/status", "系统状态"),
        ("/api/v1/system/acceptance", "架构师验收快照"),
    )
    for path, title in paths:
        try:
            code, body = _get(f"{base}{path}")
            print(f"\n=== {title} ({path}) HTTP {code} ===")
            try:
                print(json.dumps(json.loads(body), indent=2, ensure_ascii=False)[:12000])
            except json.JSONDecodeError:
                print(body[:4000])
        except urllib.error.HTTPError as e:
            print(f"\n=== {title} HTTP {e.code} ===\n{e.read().decode('utf-8', errors='replace')[:2000]}")
        except Exception as e:
            print(f"\n=== {title} 失败 ===\n{e}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
