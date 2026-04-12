#!/usr/bin/env python3
"""
OKX 连通性基准：在容器/本机对比多种出站方式，便于选择 compose 默认值。

用法（容器内，tests 已挂载时）:
  python3 /app/tests/manual/benchmark_okx_connectivity.py

仅依赖 aiohttp + certifi（与交易系统一致）。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import ssl
import statistics
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import certifi

URL = "https://www.okx.com/api/v5/public/time"


def _ssl() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


async def one_get(
    session: aiohttp.ClientSession,
    *,
    proxy: Optional[str],
    timeout_total: float = 12.0,
) -> Tuple[bool, float, str]:
    t0 = time.perf_counter()
    to = aiohttp.ClientTimeout(total=timeout_total, connect=6, sock_read=10)
    try:
        async with session.get(URL, proxy=proxy, timeout=to) as r:
            await r.read()
            ok = r.status == 200
            return ok, time.perf_counter() - t0, f"status={r.status}"
    except Exception as e:
        return False, time.perf_counter() - t0, f"{type(e).__name__}: {e}"


async def bench_mode(
    label: str,
    *,
    proxy: Optional[str],
    iterations: int,
    timeout_total: float = 12.0,
) -> Dict[str, Any]:
    latencies: List[float] = []
    fails = 0
    last_msg = ""
    connector = aiohttp.TCPConnector(ssl=_ssl())
    async with aiohttp.ClientSession(connector=connector) as session:
        for _ in range(iterations):
            ok, dt, msg = await one_get(session, proxy=proxy, timeout_total=timeout_total)
            last_msg = msg
            if ok:
                latencies.append(dt)
            else:
                fails += 1
            await asyncio.sleep(0.15)
    ok_count = len(latencies)
    out: Dict[str, Any] = {
        "mode": label,
        "ok": ok_count,
        "fail": fails,
        "success_rate": round(ok_count / max(1, iterations), 4),
        "last_error": last_msg if fails else "",
    }
    if latencies:
        out["latency_p50_ms"] = round(statistics.median(latencies) * 1000, 2)
        out["latency_mean_ms"] = round(statistics.mean(latencies) * 1000, 2)
        if len(latencies) > 1:
            out["latency_stdev_ms"] = round(statistics.stdev(latencies) * 1000, 2)
    return out


async def bench_fallback(
    env_proxy: Optional[str],
    iterations: int,
) -> Dict[str, Any]:
    """先短超时走 env 代理，失败则直连（模拟 OPENCLAW_OKX_PROXY_ONLY=0 + 直连自愈）。"""
    latencies: List[float] = []
    fails = 0
    last_msg = ""
    connector = aiohttp.TCPConnector(ssl=_ssl())
    async with aiohttp.ClientSession(connector=connector) as session:
        for _ in range(iterations):
            t0 = time.perf_counter()
            ok, _dt1, msg1 = await one_get(session, proxy=env_proxy, timeout_total=4.0)
            if ok:
                latencies.append(time.perf_counter() - t0)
            elif env_proxy:
                ok2, _dt2, msg2 = await one_get(session, proxy=None, timeout_total=12.0)
                if ok2:
                    latencies.append(time.perf_counter() - t0)
                else:
                    fails += 1
                    last_msg = f"{msg1} | {msg2}"
            else:
                fails += 1
                last_msg = msg1
            await asyncio.sleep(0.15)
    ok_count = len(latencies)
    return {
        "mode": "proxy_then_direct_fallback",
        "ok": ok_count,
        "fail": fails,
        "success_rate": round(ok_count / max(1, iterations), 4),
        "last_error": last_msg if fails else "",
        **(
            {
                "latency_p50_ms": round(statistics.median(latencies) * 1000, 2),
                "latency_mean_ms": round(statistics.mean(latencies) * 1000, 2),
            }
            if latencies
            else {}
        ),
    }


async def amain() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("-n", "--iterations", type=int, default=5, help="每种模式重复次数")
    args = p.parse_args()
    n = max(1, min(args.iterations, 30))
    env_proxy = (
        os.getenv("OPENCLAW_HTTPS_PROXY")
        or os.getenv("OPENCLAW_HTTP_PROXY")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("HTTP_PROXY")
        or None
    )
    rows: List[Dict[str, Any]] = []
    rows.append(await bench_mode("aiohttp_direct (proxy=None)", proxy=None, iterations=n))
    if env_proxy:
        # 坏代理时单次会卡满超时，用较短 total 加快排障
        rows.append(
            await bench_mode(
                f"aiohttp_env_proxy ({env_proxy})",
                proxy=env_proxy,
                iterations=n,
                timeout_total=5.0,
            )
        )
        rows.append(await bench_fallback(env_proxy, iterations=n))
    else:
        rows.append({"mode": "aiohttp_env_proxy", "skipped": True, "reason": "no HTTP(S)_PROXY in env"})

    print("OKX connectivity benchmark")
    print("URL:", URL)
    print("iterations per mode:", n)
    print("-" * 72)
    for r in rows:
        if r.get("skipped"):
            print(r)
            continue
        print(
            f"{r['mode']:<38} ok={r['ok']}/{n} rate={r['success_rate']}",
            end="",
        )
        if "latency_p50_ms" in r:
            print(f" p50={r['latency_p50_ms']}ms mean={r.get('latency_mean_ms')}ms", end="")
        print()
        if r.get("fail") and r.get("last_error"):
            print(f"  last: {r['last_error'][:200]}")

    best = max((r for r in rows if not r.get("skipped")), key=lambda x: (x.get("success_rate", 0), x.get("ok", 0)))
    print("-" * 72)
    print("recommended (by success_rate):", best.get("mode"))


if __name__ == "__main__":
    asyncio.run(amain())
