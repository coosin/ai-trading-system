#!/usr/bin/env python3
"""
S1 全栈自动验收（无需人工盯盘）：
1. docker-compose up -d（redis + trading-system）
2. 轮询 /health 直至就绪
3. GET /api/v1/s1/verify 校验 all_passed
4. Redis PING
5. 容器日志关键字抽检（ExecutionGateway、single_write_owner、主循环跳过等）
6. 可选：运行单元测试（pytest）

环境变量：
  VERIFY_BASE   默认 http://127.0.0.1:8000
  SKIP_PYTEST=1 跳过 pytest
  COMPOSE_BIN   docker-compose 或 docker compose
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _compose_cmd() -> list[str]:
    env = os.environ.get("COMPOSE_BIN", "").strip()
    if env:
        return env.split()
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return ["docker", "compose"]


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(REPO), **kw)


def _wait_http(url: str, timeout_sec: int = 120) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(2)
    return False


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _redis_ping() -> tuple[bool, str]:
    r = _run(
        ["docker", "exec", "openclaw-redis", "redis-cli", "ping"],
        capture_output=True,
        text=True,
    )
    ok = r.returncode == 0 and "PONG" in (r.stdout or "")
    return ok, (r.stdout or r.stderr or "").strip()


def _log_snippets() -> str:
    r = _run(
        ["docker", "logs", "--tail", "4000", "openclaw-trading"],
        capture_output=True,
        text=True,
    )
    return r.stdout or r.stderr or ""


def _pytest() -> int:
    venv_py = REPO / ".venv" / "bin" / "python"
    py = str(venv_py) if venv_py.is_file() else sys.executable
    tests = [
        "tests/unit/test_execution_gateway.py",
        "tests/unit/test_stop_loss_exchange_sync.py",
        "tests/unit/test_stop_loss_gateway_close.py",
    ]
    return _run([py, "-m", "pytest", "-q", "--tb=line", *tests]).returncode


def main() -> int:
    base = os.environ.get("VERIFY_BASE", "http://127.0.0.1:8000").rstrip("/")
    print("== S1 自动验收 ==")
    print("Repo:", REPO)

    compose = _compose_cmd()
    print("Compose:", " ".join(compose))
    up = _run(compose + ["up", "-d"], capture_output=True, text=True)
    if up.returncode != 0:
        print("docker compose up 失败:\n", up.stderr or up.stdout)
        return 1
    print("✓ compose up -d")

    health_url = f"{base}/health"
    print("等待 HTTP:", health_url)
    if not _wait_http(health_url, 120):
        print("✗ 健康检查超时")
        return 1
    print("✓ /health 就绪")

    if os.environ.get("SKIP_PYTEST") != "1":
        print("运行 pytest...")
        pr = _pytest()
        if pr != 0:
            print("✗ pytest 失败")
            return pr
        print("✓ pytest")

    verify_url = f"{base}/api/v1/s1/verify"
    print("请求:", verify_url)
    try:
        data = _get_json(verify_url)
    except Exception as e:
        print("✗ 无法拉取 /api/v1/s1/verify:", e)
        return 1

    print(json.dumps(data, ensure_ascii=False, indent=2))

    if not data.get("ok"):
        print("✗ 探针返回 ok=false")
        return 1
    if not data.get("all_passed"):
        print("✗ all_passed=false，子项见上")
        failed = [c for c in data.get("checks", []) if not c.get("passed")]
        for c in failed:
            print("  FAIL:", c.get("name"), c.get("detail"))
        return 1
    print("✓ all_passed=true")

    rp_ok, rp_msg = _redis_ping()
    print("Redis:", rp_msg or ("ok" if rp_ok else "fail"))
    if not rp_ok:
        print("✗ Redis PING 失败")
        return 1

    logs = _log_snippets()
    needles = [
        "ExecutionGateway",
        "single_write_owner",
        "🧭 执行策略(S1)",
    ]
    missing = [n for n in needles if n not in logs]
    if missing:
        print("⚠ 日志中未找到关键字（可能尚未滚动到）:", missing)
    else:
        print("✓ 日志关键字抽检通过")

    bad = [
        "Permission denied: 'data/stop_loss_orders.json'",
        "open_policy_denied",
    ]
    hits = [b for b in bad if b in logs]
    if hits:
        print("✗ 日志中发现异常片段:", hits)
        return 1

    print("== 全部通过 ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
