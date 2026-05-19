#!/usr/bin/env python3
"""
启动后验收：轮询 /api/v1/system/health，拉取 /api/v1/system/status 与 /api/v1/system/acceptance。
用法：
  OPENCLAW_API_BASE=http://127.0.0.1:8000 python3 scripts/startup_acceptance.py
  ACCEPTANCE_BASE=http://127.0.0.1:8000 python3 scripts/startup_acceptance.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.utils.openclaw_api_client import default_openclaw_api_base


def _get(url: str, timeout: float = 90.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read().decode("utf-8", errors="replace")


def wait_health(base: str, total_wait: float = 120.0, step: float = 3.0) -> None:
    deadline = time.time() + total_wait
    last_err = ""
    while time.time() < deadline:
        try:
            code, body = _get(f"{base.rstrip('/')}/api/v1/system/health", timeout=20.0)
            if code < 400 and "healthy" in body.lower():
                print(f"[OK] /api/v1/system/health 就绪 ({code})")
                return
        except Exception as e:
            last_err = str(e)
        time.sleep(step)
    raise SystemExit(f"健康检查超时: {last_err}")


def run_trading_model_acceptance(skip: bool = False) -> int:
    if skip:
        print("\n=== CLIProxyAPI 交易别名验收 ===\n[SKIP] disabled by --skip-trading-models")
        return 0
    script = os.path.join(_REPO_ROOT, "scripts", "validate_trading_model_aliases.py")
    cmd = [sys.executable, script]
    print("\n=== CLIProxyAPI 交易别名验收 ===")
    proc = subprocess.run(cmd, check=False, cwd=_REPO_ROOT, text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout[:12000])
    if proc.returncode != 0 and proc.stderr:
        print(proc.stderr[:4000])
    return int(proc.returncode or 0)


def main() -> int:
    skip_trading_models = "--skip-trading-models" in sys.argv[1:]
    if skip_trading_models:
        sys.argv = [sys.argv[0], *[arg for arg in sys.argv[1:] if arg != "--skip-trading-models"]]
    base = (os.environ.get("OPENCLAW_API_BASE") or os.environ.get("ACCEPTANCE_BASE") or "").strip().rstrip("/")
    if not base:
        base = default_openclaw_api_base()
    print(f"验收目标: {base}")
    wait_health(base)

    paths = (
        ("/api/v1/system/health", "系统健康检查"),
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
    alias_rc = run_trading_model_acceptance(skip=skip_trading_models)
    if alias_rc != 0:
        return alias_rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
