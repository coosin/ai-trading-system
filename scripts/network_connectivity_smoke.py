#!/usr/bin/env python3
"""
轻量网络自检：DNS + TCP/HTTPS 可达性（不依赖交易所密钥）。
用于部署后快速确认容器/宿主机出站网络正常。

说明:
- 本脚本使用标准库 `socket` / `urllib`，**不会自动读取 HTTP_PROXY**（与 curl 不同）。
  若生产依赖 Clash HTTP 端口，请在**进程环境**或**系统 TUN/透明代理**层保证出站，并参考 deploy/HOST_CLASH_EGRESS.md。
- 若 DNS 将 OKX 解析到 **169.254.x.x**，多为污染/劫持或与 Clash fake-ip 未放行 +.okx.com；见文末 HINT 与
  `scripts/production_network_baseline.py --apply`（需 /etc/clash/config.yaml）。

用法:
  python3 scripts/network_connectivity_smoke.py
  python3 scripts/network_connectivity_smoke.py --redis   # 需 REDIS_HOST / REDIS_PORT
  OPENCLAW_API_BASE=http://127.0.0.1:8000 python3 scripts/network_connectivity_smoke.py --include-api
  python3 scripts/network_connectivity_smoke.py --api-url http://127.0.0.1:8000/api/v1/system/health
  python3 scripts/network_connectivity_smoke.py --https-okx   # 额外 GET OKX /api/v5/public/time（仍不经 HTTP_PROXY）
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import urllib.error
import urllib.request

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.utils.openclaw_api_client import openclaw_api_url


def _summarize_proxy_env() -> str:
    parts: list[str] = []
    for k in (
        "OPENCLAW_HTTP_PROXY",
        "OPENCLAW_HTTPS_PROXY",
        "OPENCLAW_ALL_PROXY",
        "NO_PROXY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
    ):
        v = (os.environ.get(k) or "").strip()
        parts.append(f"{k}={'set' if v else 'empty'}")
    return " ".join(parts)


def _extract_ip_from_dns_line(msg: str) -> str:
    if " -> " in msg:
        return msg.split(" -> ", 1)[1].strip()
    return ""


def _dns_repair_hints(host: str, resolved_ip: str) -> list[str]:
    """Actionable hints when OKX resolution looks poisoned or fake-ip mis-tunneled."""
    hints: list[str] = []
    h = (host or "").lower()
    ip = (resolved_ip or "").strip()
    if not ip or "okx" not in h:
        return hints
    if ip.startswith("169.254."):
        hints.append(
            "OKX 解析到 169.254.x.x：多为 DNS 污染/劫持（国内部分递归 DNS 对 okx 返回假地址）。"
            "建议：Clash/mihomo 为 `+.okx.com`/`+.okex.com` 配置 nameserver-policy 指向 1.1.1.1，并把 `+.okx.com` 加入 fake-ip-filter；"
            "或运行 `sudo python3 scripts/production_network_baseline.py --apply`（写入 /etc/clash/config.yaml 后需重启 clash）。"
        )
    if ip.startswith("198.18."):
        hints.append(
            "OKX 解析到 198.18.x.x（Clash fake-ip 段）：若随后 TCP/TLS 失败，请确认 fake-ip-filter 含 `+.okx.com`/`+.okex.com`，"
            "或对 OKX 域名使用 REAL-IP/DIRECT 规则，避免假 IP 与真实路由不一致。"
        )
    if ip in {"0.0.0.0", "::"}:
        hints.append("OKX 解析到无效地址：请检查本机 resolv.conf / systemd-resolved / 容器 DNS。")
    return hints


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
        help="可选：本机 API 健康检查完整 URL",
    )
    p.add_argument(
        "--include-api",
        action="store_true",
        help="额外请求本机 OpenClaw health（OPENCLAW_API_BASE / ACCEPTANCE_BASE / BASE_URL 或默认 127.0.0.1:8000）",
    )
    p.add_argument(
        "--https-okx",
        action="store_true",
        help="额外 GET https://www.okx.com/api/v5/public/time（不经 HTTP_PROXY；与 TCP 互补）",
    )
    args = p.parse_args()

    print("[env]", _summarize_proxy_env())

    ok_all = True
    all_hints: list[str] = []

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
    elif args.include_api:
        u = openclaw_api_url("/api/v1/system/health")
        checks.append(("API health", lambda url=u: _check_https(url, timeout=15.0)))
    if args.https_okx:
        checks.append(
            (
                "HTTPS OKX /time",
                lambda: _check_https("https://www.okx.com/api/v5/public/time", timeout=12.0),
            )
        )

    for name, fn in checks:
        ok, msg = fn()
        tag = "OK " if ok else "FAIL"
        hints_here: list[str] = []
        if name.startswith("DNS okx"):
            ip = _extract_ip_from_dns_line(msg)
            hints_here = _dns_repair_hints("www.okx.com", ip)
            if hints_here:
                tag = "WARN"
                ok = False
        ok_all = ok_all and ok
        print(f"[{tag}] {name}: {msg}")
        for hint in hints_here:
            print(f"[HINT] {hint}")
            all_hints.append(hint)

    proxy_empty = all(
        (os.environ.get(k) or "").strip() == ""
        for k in ("OPENCLAW_HTTP_PROXY", "OPENCLAW_HTTPS_PROXY", "OPENCLAW_ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY")
    )

    if not ok_all:
        if proxy_empty:
            line = (
                "[HINT] 当前未设置 HTTP(S)_PROXY / OPENCLAW_*_PROXY：本脚本走系统直连。"
                "若交易进程依赖宿主机 Clash，请在 .env 或 systemd 环境中注入 OPENCLAW_HTTP(S)_PROXY，"
                "或改用 TUN/hostnet（见 deploy/HOST_CLASH_EGRESS.md）。"
            )
            print(line)
            all_hints.append(line.replace("[HINT] ", ""))

    exit_code = 0 if ok_all else 1

    if ok_all:
        print("NETWORK_SMOKE=PASS")
        return 0
    print("NETWORK_SMOKE=FAIL")
    if all_hints:
        print("\n--- REPAIR_CHECKLIST (dedup) ---")
        seen: set[str] = set()
        for h in all_hints:
            if h not in seen:
                seen.add(h)
                print(f"- {h}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
