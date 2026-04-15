#!/usr/bin/env python3
"""
升级回归检查脚本：
- 检查关键治理接口可用
- 检查一键升级闭环可执行
"""

from __future__ import annotations

import json
import sys
from urllib import request


BASE = "http://127.0.0.1:8000/api/v1/modules"


def get_json(path: str) -> dict:
    with request.urlopen(f"{BASE}{path}", timeout=30) as resp:
        data = resp.read().decode("utf-8", errors="replace")
    return json.loads(data)


def post_json(path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(f"{BASE}{path}", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=120) as resp:
        data = resp.read().decode("utf-8", errors="replace")
    return json.loads(data)


def main() -> int:
    checks = [
        ("/commander/hosting-mode", "GET"),
        ("/commander/hosting-guard", "GET"),
        ("/commander/automation-profile", "GET"),
        ("/commander/risk-redlines", "GET"),
        ("/commander/architecture/layers", "GET"),
        ("/commander/upgrade/benchmark", "GET"),
        ("/commander/tool-contract", "GET"),
        ("/commander/governance-audit?limit=20", "GET"),
    ]
    failed = []
    for path, method in checks:
        try:
            if method == "GET":
                out = get_json(path)
            else:
                out = {}
            ok = bool(out.get("success", False))
            print(f"[{'OK' if ok else 'X '}] {method} {path}")
            if not ok:
                failed.append(f"{method} {path}")
        except Exception as e:
            print(f"[X ] {method} {path} -> {e}")
            failed.append(f"{method} {path}")

    try:
        up = post_json(
            "/commander/upgrade/run",
            {
                "symbol": "BTC/USDT",
                "trigger_optimize": False,
                "force_account_sync": True,
                "auto_fallback_to_semi": True,
            },
        )
        ok = bool(up.get("success", False))
        print(f"[{'OK' if ok else 'X '}] POST /commander/upgrade/run")
        if not ok:
            failed.append("POST /commander/upgrade/run")
    except Exception as e:
        print(f"[X ] POST /commander/upgrade/run -> {e}")
        failed.append("POST /commander/upgrade/run")

    if failed:
        print("FAILED_CHECKS:", ", ".join(failed))
        return 1
    print("ALL_CHECKS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

