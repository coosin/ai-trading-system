#!/usr/bin/env python3
"""
轻量网络自检：DNS + HTTPS 可达性（不依赖交易所密钥）。
用于部署后快速确认容器/宿主机出站网络正常。

用法:
  python3 scripts/network_connectivity_smoke.py
  python3 scripts/network_connectivity_smoke.py --redis   # 需 REDIS_HOST / REDIS_PORT
  python3 scripts/network_connectivity_smoke.py --api-url http://127.0.0.1:8000/health
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import urllib.error
import urllib.request


def _check_dns(host: str) -> tuple[bool, str]:
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not infos:
            return False, f"{host}: no addresses"
        return True, f"{host} -> {infos[0][4][0]}"
    except OSError as e:
        return False, f"{host}: {e}"


def _check_tcp_connect(host: str, port: int = 443, timeout: float = 12.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            pass
        return True, f"TCP {host}:{port} reachable"
    except OSError as e:
        return False, f"TCP {host}:{port}: {e}"


def _check_https(url: str, timeout: float = 12.0) -> tuple[bool, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "openclaw-network-smoke/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"{url} HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return e.code in (401, 403, 404), f"{url} HTTP {e.code} (treated ok for reachability)"
    except Exception as e:
        return False, f"{url}: {e}"


def _check_redis() -> tuple[bool, str]:
    host = os.environ.get("REDIS_HOST", "127.0.0.1")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    try:
        import redis

        r = redis.Redis(host=host, port=port, socket_connect_timeout=3)
        if r.ping():
            return True, f"redis {host}:{port} PONG"
        return False, f"redis {host}:{port} no PONG"
    except ImportError:
        return False, "redis-py not installed"
    except Exception as e:
        return False, f"redis {host}:{port}: {e}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--redis", action="store_true", help="Also ping Redis (REDIS_HOST/REDIS_PORT)")
    p.add_argument(
        "--api-url",
        default="",
        help="可选：本机 API 健康检查 URL（如 http://127.0.0.1:8000/health）",
    )
    args = p.parse_args()

    ok_all = True
    checks = [
        ("DNS okx.com", lambda: _check_dns("www.okx.com")),
        ("DNS cloudflare", lambda: _check_dns("one.one.one.one")),
        # 用 TCP 443 代替 HTTPS GET：透明代理/TUN 场景下 TLS 握手常被中间盒干扰，不代表交易 API 不可用
        ("TCP443 OKX", lambda: _check_tcp_connect("www.okx.com", 443)),
    ]
    if args.redis:
        checks.append(("Redis ping", _check_redis))
    if (args.api_url or "").strip():
        u = (args.api_url or "").strip()
        checks.append(("API health", lambda url=u: _check_https(url, timeout=15.0)))

    for name, fn in checks:
        ok, msg = fn()
        ok_all = ok_all and ok
        tag = "OK " if ok else "FAIL"
        print(f"[{tag}] {name}: {msg}")

    if ok_all:
        print("NETWORK_SMOKE=PASS")
        return 0
    print("NETWORK_SMOKE=FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
