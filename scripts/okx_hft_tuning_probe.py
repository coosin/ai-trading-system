#!/usr/bin/env python3
"""
OKX high-frequency probe for concurrency/throttle tuning.

Run inside container for realistic result:
docker exec -i openclaw-trading python - < scripts/okx_hft_tuning_probe.py
"""

from __future__ import annotations

import asyncio
import os
import ssl
import statistics
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

import aiohttp
import certifi


TARGETS = [
    "https://www.okx.com/api/v5/public/time",
    "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP",
    "https://www.okx.com/api/v5/public/open-interest?instId=BTC-USDT-SWAP",
]


@dataclass
class ProbeResult:
    concurrency: int
    interval: float
    total: int
    ok: int
    fail: int
    p50_ms: float
    p95_ms: float
    elapsed_s: float

    @property
    def success_rate(self) -> float:
        return self.ok / self.total if self.total else 0.0

    @property
    def rps(self) -> float:
        return self.total / self.elapsed_s if self.elapsed_s > 0 else 0.0


def ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


async def run_case(proxy: str, concurrency: int, interval: float, total: int = 120) -> ProbeResult:
    sem = asyncio.Semaphore(concurrency)
    latencies: List[float] = []
    ok = 0
    fail = 0
    lock = asyncio.Lock()
    last_ts = 0.0

    timeout = aiohttp.ClientTimeout(total=20, connect=8, sock_read=12)
    connector = aiohttp.TCPConnector(ssl=ssl_ctx())
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        async def worker(i: int) -> None:
            nonlocal ok, fail, last_ts
            url = TARGETS[i % len(TARGETS)]
            async with sem:
                async with lock:
                    now = time.monotonic()
                    delta = now - last_ts
                    if delta < interval:
                        await asyncio.sleep(interval - delta)
                    last_ts = time.monotonic()
                t0 = time.monotonic()
                try:
                    async with session.get(url, proxy=proxy) as resp:
                        body = await resp.json(content_type=None)
                        if resp.status == 200 and str(body.get("code", "")) == "0":
                            ok += 1
                        else:
                            fail += 1
                except Exception:
                    fail += 1
                finally:
                    latencies.append((time.monotonic() - t0) * 1000.0)

        start = time.monotonic()
        await asyncio.gather(*(worker(i) for i in range(total)))
        elapsed = time.monotonic() - start

    p50 = statistics.median(latencies) if latencies else 0.0
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else (max(latencies) if latencies else 0.0)
    return ProbeResult(concurrency, interval, total, ok, fail, round(p50, 2), round(p95, 2), round(elapsed, 2))


async def main() -> None:
    proxy = os.getenv("OPENCLAW_HTTP_PROXY")
    if not proxy:
        raise SystemExit("OPENCLAW_HTTP_PROXY is required")

    matrix: List[Tuple[int, float]] = [
        (2, 0.10),
        (4, 0.10),
        (4, 0.15),
        (4, 0.20),
        (6, 0.15),
        (6, 0.20),
    ]

    results: List[ProbeResult] = []
    print("Starting OKX HFT probe ...")
    for c, i in matrix:
        r = await run_case(proxy=proxy, concurrency=c, interval=i)
        results.append(r)
        print(
            f"case c={c} i={i:.2f} -> ok={r.ok}/{r.total} fail={r.fail} "
            f"succ={r.success_rate:.2%} p50={r.p50_ms}ms p95={r.p95_ms}ms rps={r.rps:.2f}"
        )

    # heuristic: prioritize success, then p95, then rps
    best = sorted(results, key=lambda x: (-x.success_rate, x.p95_ms, -x.rps))[0]
    print("\nRecommended:")
    print(
        f"OPENCLAW_OKX_MAX_CONCURRENCY={best.concurrency}\n"
        f"OPENCLAW_OKX_MIN_REQUEST_INTERVAL={best.interval}"
    )


if __name__ == "__main__":
    asyncio.run(main())

