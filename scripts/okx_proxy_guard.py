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
import os
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request


OKX_TIME_URL = "https://www.okx.com/api/v5/public/time"


def _pick_proxy(explicit_proxy: str) -> str:
    if str(explicit_proxy or "").strip():
        return str(explicit_proxy).strip()
    for key in (
        "OPENCLAW_OKX_HTTPS_PROXY",
        "OPENCLAW_OKX_HTTP_PROXY",
        "OPENCLAW_HTTPS_PROXY",
        "OPENCLAW_HTTP_PROXY",
        "HTTPS_PROXY",
        "HTTP_PROXY",
    ):
        val = str(os.getenv(key, "") or "").strip()
        if val:
            return val
    return ""


def _http_get(url: str, timeout: float = 12.0, proxy: str = "") -> tuple[bool, float, str]:
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": "openclaw-okx-proxy-guard/1.0"})
    try:
        opener = None
        if proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            )
        with (opener.open(req, timeout=timeout) if opener else urllib.request.urlopen(req, timeout=timeout)) as resp:
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
            data = resp.read().decode("utf-8", errors="replace")
            return True, data
    except Exception as e:
        return False, str(e)


def _discover_provider_names(controller: str, secret: str) -> list[str]:
    """Read available provider names from mihomo controller."""
    url = f"{controller.rstrip('/')}/providers/proxies"
    ok, msg = _mihomo_call(url, secret, method="GET")
    if not ok:
        return []
    try:
        data = json.loads(msg)
    except Exception:
        return []
    providers = data.get("providers") if isinstance(data, dict) else {}
    if not isinstance(providers, dict):
        return []
    return [str(k) for k in providers.keys() if str(k).strip()]


def _run_probe(runs: int, timeout: float, proxy: str) -> dict:
    rows = []
    for _ in range(max(1, runs)):
        rows.append(_http_get(OKX_TIME_URL, timeout=timeout, proxy=proxy))
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
    p.add_argument("--proxy", default="", help="Explicit HTTP(S) proxy URL for OKX probe")
    p.add_argument("--repair", action="store_true", help="When unhealthy, trigger mihomo healthcheck/reload")
    p.add_argument("--mihomo-controller", default="http://127.0.0.1:9090")
    p.add_argument("--mihomo-secret", default="a930ed80f2cfed1c19d49140fa3cffe2")
    p.add_argument("--provider", default="sub_v1mk")
    p.add_argument("--reload-path", default="/etc/mihomo/generated_from_openclaw.yaml")
    args = p.parse_args()

    proxy = _pick_proxy(args.proxy)
    probe = _run_probe(args.runs, args.timeout, proxy)
    healthy = bool(probe["success_rate"] >= 0.67 and (probe["median_ms"] or 9e9) <= args.max_latency_ms)

    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "proxy": proxy or None,
        "okx_probe": probe,
        "healthy": healthy,
        "repair_attempted": False,
        "repair_steps": [],
    }

    if args.repair and not healthy:
        report["repair_attempted"] = True
        # 1) provider healthcheck (auto-discover + fallback)
        discovered = _discover_provider_names(args.mihomo_controller, args.mihomo_secret)
        provider_candidates: list[str] = []
        if str(args.provider or "").strip():
            provider_candidates.append(str(args.provider).strip())
        for name in discovered:
            if name not in provider_candidates:
                provider_candidates.append(name)
        # prefer common routing groups if they exist
        preferred = ["🚀 节点选择", "♻️ 自动选择", "default"]
        provider_candidates = [x for x in preferred if x in provider_candidates] + [
            x for x in provider_candidates if x not in preferred
        ]
        ok1 = False
        msg1 = "no provider available"
        used_provider = ""
        for prov in provider_candidates[:8]:
            quoted = urllib.parse.quote(prov, safe="")
            hc_url = f"{args.mihomo_controller.rstrip('/')}/providers/proxies/{quoted}/healthcheck"
            ok_try, msg_try = _mihomo_call(hc_url, args.mihomo_secret, method="GET")
            if ok_try:
                ok1 = True
                msg1 = msg_try
                used_provider = prov
                break
            msg1 = msg_try
        report["repair_steps"].append(
            {
                "step": "provider_healthcheck",
                "ok": ok1,
                "provider": used_provider,
                "detail": (msg1 or "")[:300],
            }
        )

        # 2) config reload with fallback paths
        reload_url = f"{args.mihomo_controller.rstrip('/')}/configs"
        reload_candidates = [
            str(args.reload_path or "").strip(),
            "/etc/mihomo/generated_from_openclaw.yaml",
            "/etc/mihomo/final_best_integrated.yaml",
            "/etc/mihomo/final_best_from_vip.yaml",
            "/etc/mihomo/config.yaml",
        ]
        seen = set()
        reload_candidates = [p for p in reload_candidates if p and not (p in seen or seen.add(p))]
        ok2 = False
        msg2 = "no reload path succeeded"
        used_path = ""
        for path in reload_candidates:
            body = json.dumps({"path": path}, ensure_ascii=False)
            ok_try, msg_try = _mihomo_call(reload_url, args.mihomo_secret, method="PUT", body=body)
            if ok_try:
                ok2 = True
                msg2 = msg_try
                used_path = path
                break
            msg2 = msg_try
        report["repair_steps"].append(
            {
                "step": "reload_config",
                "ok": ok2,
                "path": used_path,
                "detail": (msg2 or "")[:300],
            }
        )

        probe2 = _run_probe(max(2, args.runs), args.timeout, proxy)
        report["okx_probe_after_repair"] = probe2
        report["healthy_after_repair"] = bool(
            probe2["success_rate"] >= 0.67 and (probe2["median_ms"] or 9e9) <= args.max_latency_ms
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
