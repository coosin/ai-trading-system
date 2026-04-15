#!/usr/bin/env python3
"""
OKX 代理健康守护（轻量版）

用途：
- 定时探测 OKX public/time 的可达性与时延
- 失败或过慢时，触发 mihomo provider healthcheck / config reload
- 输出可用于 systemd/cron 的结构化日志

示例：
  python3 scripts/okx_proxy_guard.py --runs 3
  python3 scripts/okx_proxy_guard.py --runs 3 --max-latency-ms 1200 --repair
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request


OKX_TIME_URL = "https://www.okx.com/api/v5/public/time"


def _http_get(url: str, timeout: float = 12.0) -> tuple[bool, float, str]:
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": "openclaw-okx-proxy-guard/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(512)
        ms = (time.perf_counter() - t0) * 1000.0
        ok = (b'"code":"0"' in body) or (b'"code": "0"' in body)
        return ok, ms, "ok"
    except urllib.error.HTTPError as e:
        return False, (time.perf_counter() - t0) * 1000.0, f"http_{e.code}"
    except Exception as e:
        return False, (time.perf_counter() - t0) * 1000.0, str(e)


def _mihomo_call(url: str, secret: str, method: str = "GET", body: str = "") -> tuple[bool, str]:
    req = urllib.request.Request(url, data=body.encode("utf-8") if body else None, method=method)
    req.add_header("Authorization", f"Bearer {secret}")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read(2048).decode("utf-8", errors="replace")
            return True, data
    except Exception as e:
        return False, str(e)


def _run_probe(runs: int, timeout: float) -> dict:
    rows = []
    for _ in range(max(1, runs)):
        rows.append(_http_get(OKX_TIME_URL, timeout=timeout))
    oks = [r[0] for r in rows]
    lat = [r[1] for r in rows if r[0]]
    return {
        "success_rate": (sum(1 for x in oks if x) / len(oks)) if oks else 0.0,
        "median_ms": round(statistics.median(lat), 2) if lat else None,
        "max_ms": round(max((r[1] for r in rows), default=0.0), 2),
        "last_error": next((r[2] for r in reversed(rows) if not r[0]), ""),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="OKX proxy guard")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--timeout", type=float, default=12.0)
    p.add_argument("--max-latency-ms", type=float, default=1500.0)
    p.add_argument("--repair", action="store_true", help="When unhealthy, trigger mihomo healthcheck/reload")
    p.add_argument("--mihomo-controller", default="http://127.0.0.1:9090")
    p.add_argument("--mihomo-secret", default="a930ed80f2cfed1c19d49140fa3cffe2")
    p.add_argument("--provider", default="sub_v1mk")
    p.add_argument("--reload-path", default="/etc/mihomo/config.yaml")
    args = p.parse_args()

    probe = _run_probe(args.runs, args.timeout)
    healthy = bool(probe["success_rate"] >= 0.67 and (probe["median_ms"] or 9e9) <= args.max_latency_ms)

    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "okx_probe": probe,
        "healthy": healthy,
        "repair_attempted": False,
        "repair_steps": [],
    }

    if args.repair and not healthy:
        report["repair_attempted"] = True
        hc_url = f"{args.mihomo_controller.rstrip('/')}/providers/proxies/{args.provider}/healthcheck"
        ok1, msg1 = _mihomo_call(hc_url, args.mihomo_secret, method="GET")
        report["repair_steps"].append({"step": "provider_healthcheck", "ok": ok1, "detail": msg1[:300]})

        reload_url = f"{args.mihomo_controller.rstrip('/')}/configs"
        body = json.dumps({"path": args.reload_path}, ensure_ascii=False)
        ok2, msg2 = _mihomo_call(reload_url, args.mihomo_secret, method="PUT", body=body)
        report["repair_steps"].append({"step": "reload_config", "ok": ok2, "detail": msg2[:300]})

        probe2 = _run_probe(max(2, args.runs), args.timeout)
        report["okx_probe_after_repair"] = probe2
        report["healthy_after_repair"] = bool(
            probe2["success_rate"] >= 0.67 and (probe2["median_ms"] or 9e9) <= args.max_latency_ms
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())

