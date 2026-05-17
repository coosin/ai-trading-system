#!/usr/bin/env python3
"""
代理 / TUN 模式对比基准：可重复测量，便于与「旧配置」JSON 做差分。

测什么：
  - DNS、TCP:443、HTTPS OKX public/time（各跑多轮取中位数）
  - 同一 HTTPS 用「尊重环境 HTTP(S)_PROXY」与「强制不走 HTTP 代理」各测一轮（对比 TUN 下是否应关闭进程内 HTTP_PROXY）
  - 可选：交易 API /market/ticker 是否 exchange 还是 fallback

怎么用（宿主机上，每种代理拓扑各跑一次，换 --label）：
  # 旧：仅 bridge + HTTP_PROXY（典型老配置）
  python3 scripts/proxy_mode_network_benchmark.py --label old_bridge_http_proxy --runs 7 --out /tmp/net_old.json

  # 新：宿主机开 TUN 后复测
  python3 scripts/proxy_mode_network_benchmark.py --label host_tun_on --runs 7 --out /tmp/net_tun_host.json

  # 对比改善幅度
  python3 scripts/proxy_mode_network_benchmark.py --compare /tmp/net_old.json /tmp/net_tun_host.json

环境变量会写入 fingerprint，便于归档；勿把密钥写入终端。
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import sys
import time
import urllib.request
from typing import Any


def _load_env_file(path: str) -> None:
    """Load simple KEY=VALUE lines so benchmark probes match the trading service env."""
    if not path:
        return
    env_path = os.path.expanduser(path)
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def _fingerprint() -> dict[str, Any]:
    proxy_keys = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "OPENCLAW_HTTP_PROXY",
        "OPENCLAW_DOCKER_NETWORK_HOST",
        "OPENCLAW_OKX_IGNORE_ENV_PROXY",
    )
    fp: dict[str, Any] = {
        "in_docker": os.path.exists("/.dockerenv"),
    }
    for k in proxy_keys:
        v = os.environ.get(k)
        if v:
            fp[k] = "set" if len(v) > 80 else v
    return fp


def _dns_ms(host: str) -> tuple[bool, float, str]:
    t0 = time.perf_counter()
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ms = (time.perf_counter() - t0) * 1000
        if not infos:
            return False, ms, "no addresses"
        return True, ms, str(infos[0][4][0])
    except OSError as e:
        return False, (time.perf_counter() - t0) * 1000, str(e)


def _tcp_ms(host: str, port: int = 443, timeout: float = 12.0) -> tuple[bool, float, str]:
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        return True, (time.perf_counter() - t0) * 1000, "ok"
    except OSError as e:
        return False, (time.perf_counter() - t0) * 1000, str(e)


def _https_okx_time_ms(use_env_proxy: bool, timeout: float = 15.0) -> tuple[bool, float, str]:
    url = "https://www.okx.com/api/v5/public/time"
    t0 = time.perf_counter()
    try:
        if use_env_proxy:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "openclaw-proxy-bench/1"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(500)
        else:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "openclaw-proxy-bench/1"},
            )
            with opener.open(req, timeout=timeout) as r:
                body = r.read(500)
        ms = (time.perf_counter() - t0) * 1000
        ok = b'"code":"0"' in body or b'"code": "0"' in body
        return ok, ms, f"len={len(body)}"
    except Exception as e:
        return False, (time.perf_counter() - t0) * 1000, str(e)


def _median_ok(runs: list[tuple[bool, float, str]]) -> dict[str, Any]:
    oks = [r[0] for r in runs]
    times = [r[1] for r in runs if r[0]]
    return {
        "success_rate": sum(oks) / len(oks) if oks else 0.0,
        "median_ms": float(statistics.median(times)) if times else None,
        "max_ms": max((r[1] for r in runs), default=None),
        "last_error": next((r[2] for r in reversed(runs) if not r[0]), ""),
    }


def _repeat(fn, n: int) -> list[tuple[bool, float, str]]:
    return [fn() for _ in range(n)]


def _api_ticker(api_base: str, symbol: str, timeout: float = 35.0) -> dict[str, Any]:
    from urllib.parse import quote

    q = quote(symbol, safe="")
    url = f"{api_base.rstrip('/')}/api/v1/market/ticker?symbol={q}"
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "openclaw-proxy-bench/1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
        ms = (time.perf_counter() - t0) * 1000
        data = json.loads(raw)
        return {
            "ok": True,
            "latency_ms": round(ms, 1),
            "source": data.get("source"),
            "has_last": "last" in data or "price" in data,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}


def run_benchmark(runs: int, api_base: str | None, symbol: str) -> dict[str, Any]:
    dns_runs = [_dns_ms("www.okx.com") for _ in range(runs)]
    tcp_runs = [_tcp_ms("www.okx.com", 443) for _ in range(runs)]
    https_env_runs = [_https_okx_time_ms(True) for _ in range(runs)]
    https_direct_runs = [_https_okx_time_ms(False) for _ in range(runs)]

    out: dict[str, Any] = {
        "dns_www_okx_com": _median_ok(dns_runs),
        "tcp_www_okx_com_443": _median_ok(tcp_runs),
        "https_okx_public_time_respect_env_proxy": _median_ok(https_env_runs),
        "https_okx_public_time_no_http_proxy": _median_ok(https_direct_runs),
    }
    if api_base:
        out["api_market_ticker"] = _api_ticker(api_base, symbol)
    return out


def _compare_json(a: dict[str, Any], b: dict[str, Any]) -> None:
    print("对比:", a.get("label"), "→", b.get("label"))
    for key in (
        "dns_www_okx_com",
        "tcp_www_okx_com_443",
        "https_okx_public_time_respect_env_proxy",
        "https_okx_public_time_no_http_proxy",
    ):
        xa = (a.get("metrics") or {}).get(key) or {}
        xb = (b.get("metrics") or {}).get(key) or {}
        ma, mb = xa.get("median_ms"), xb.get("median_ms")
        if ma is not None and mb is not None and ma > 0:
            pct = (ma - mb) / ma * 100.0
            print(f"  {key}: median {ma:.1f}ms → {mb:.1f}ms  ({pct:+.1f}% 相对旧配置)")
        else:
            print(f"  {key}: {xa.get('median_ms')} → {xb.get('median_ms')} (success {xa.get('success_rate')} → {xb.get('success_rate')})")
    ta = (a.get("metrics") or {}).get("api_market_ticker") or {}
    tb = (b.get("metrics") or {}).get("api_market_ticker") or {}
    if ta or tb:
        print("  api_market_ticker:", ta, "→", tb)


def main() -> int:
    p = argparse.ArgumentParser(description="代理/TUN 模式网络基准与新旧配置对比")
    p.add_argument("--label", default="", help="本次运行标签，写入 JSON")
    p.add_argument("--runs", type=int, default=5, help="每类探测重复次数")
    p.add_argument("--out", default="", help="写入 JSON 路径")
    p.add_argument("--api-base", default=os.environ.get("API_BASE", ""), help="若设则测 /api/v1/market/ticker")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--env-file", default=".env", help="Load proxy env from this file before probing")
    p.add_argument("--compare", nargs=2, metavar=("OLD.json", "NEW.json"), help="对比两次归档")
    args = p.parse_args()

    if args.compare:
        with open(args.compare[0], encoding="utf-8") as f:
            old = json.load(f)
        with open(args.compare[1], encoding="utf-8") as f:
            new = json.load(f)
        _compare_json(old, new)
        return 0

    _load_env_file(args.env_file)
    api_base = args.api_base.strip() or None
    metrics = run_benchmark(args.runs, api_base, args.symbol)
    record = {
        "label": args.label or "unnamed",
        "runs": args.runs,
        "fingerprint": _fingerprint(),
        "metrics": metrics,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    print(json.dumps(record, ensure_ascii=False, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        print(f"\n已写入: {args.out}", file=sys.stderr)

    # 启发式结论（仅打印，不替代人工看数）
    he = metrics["https_okx_public_time_respect_env_proxy"]
    hd = metrics["https_okx_public_time_no_http_proxy"]
    if he.get("median_ms") and hd.get("median_ms"):
        if hd["median_ms"] < he["median_ms"] * 0.7 and hd.get("success_rate", 0) >= he.get("success_rate", 0):
            print(
                "\n提示: 「无 HTTP 代理」HTTPS 明显更快且成功率不降 → 适合开宿主机 TUN 后"
                " 对交易容器去掉 HTTP_PROXY 或设 OPENCLAW_OKX_IGNORE_ENV_PROXY=1，让流量走路由/TUN。",
                file=sys.stderr,
            )
    elif (he.get("success_rate") or 0) > 0.5 and (hd.get("success_rate") or 0) <= 0.5:
        print(
            "\n提示: 当前 OKX HTTPS 必须走 HTTP(S)_PROXY；直连失败属于当前网络拓扑预期，"
            "不要设置 OPENCLAW_OKX_IGNORE_ENV_PROXY=1。",
            file=sys.stderr,
        )
    tick = metrics.get("api_market_ticker") or {}
    if tick.get("ok") and tick.get("source") == "fallback":
        print(
            "\n提示: API ticker 仍为 fallback → 应用内 OKX REST 仍超时或失败，"
            "优先查代理 CONNECT 与 OPENCLAW_OKX_TIMEOUT_*。",
            file=sys.stderr,
        )

    # This benchmark compares network paths; in many production hosts only one path is expected
    # to work. Exit non-zero only when both OKX HTTPS paths are unhealthy.
    env_ok = (metrics["https_okx_public_time_respect_env_proxy"].get("success_rate") or 0) > 0.5
    direct_ok = (metrics["https_okx_public_time_no_http_proxy"].get("success_rate") or 0) > 0.5
    return 0 if (env_ok or direct_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
