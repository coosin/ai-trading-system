#!/usr/bin/env python3
"""
全栈集成检查：宿主机公网 + 交易 API（OKX 经 hub的行情、data-hub、第三方审计、workspace、s1）。

用法：
  python3 scripts/full_system_integration_check.py
  API_BASE=http://127.0.0.1:8000 python3 scripts/full_system_integration_check.py
  python3 scripts/full_system_integration_check.py --host-only
"""
from __future__ import annotations

import argparse
import json
import os
from urllib.parse import quote

import urllib.request


def _get(url: str, timeout: float = 45.0) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "openclaw-full-check/1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read().decode("utf-8", errors="replace")


def _check_public_apis() -> list[tuple[str, bool, str]]:
    import time as _time

    out: list[tuple[str, bool, str]] = []
    checks = [
        ("OKX public time", "https://www.okx.com/api/v5/public/time", 1),
        ("Binance ping", "https://api.binance.com/api/v3/ping", 1),
        ("CoinGecko ping", "https://api.coingecko.com/api/v3/ping", 3),
    ]
    for name, url, retries in checks:
        last_err = ""
        ok = False
        msg = ""
        for attempt in range(retries):
            try:
                code, body = _get(url, 25.0)
                ok = code == 200
                msg = f"HTTP {code} {body[:100]!r}"
                if ok:
                    break
                last_err = msg
            except Exception as e:
                last_err = str(e)
            if attempt + 1 < retries:
                _time.sleep(2.0)
        out.append((name, ok, msg if ok else last_err))
    return out


def _api_probe(base: str, path: str, timeout: float = 60.0) -> tuple[bool, str]:
    url = f"{base.rstrip('/')}{path}"
    try:
        code, raw = _get(url, timeout)
        if code >= 400:
            return False, f"HTTP {code} {raw[:500]}"
        return True, raw[:8000]
    except Exception as e:
        return False, str(e)


def _summarize_json_snippet(title: str, raw: str, max_len: int = 1200) -> None:
    print(f"\n--- {title} (前 {max_len} 字符) ---")
    try:
        obj = json.loads(raw)
        print(json.dumps(obj, ensure_ascii=False, indent=2)[:max_len])
    except json.JSONDecodeError:
        print(raw[:max_len])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host-only", action="store_true", help="只测宿主机到 OKX/Binance/CoinGecko 公网")
    p.add_argument("--api-base", default=os.environ.get("API_BASE", "http://127.0.0.1:8000"))
    p.add_argument("--symbol", default="BTC/USDT")
    args = p.parse_args()
    base = args.api_base.rstrip("/")
    sym_q = quote(args.symbol, safe="")

    print("=" * 60)
    print("A. 宿主机公网（不经过交易进程）")
    print("=" * 60)
    pub_results = _check_public_apis()
    for name, ok, msg in pub_results:
        tag = "OK " if ok else "FAIL"
        print(f"  [{tag}] {name}: {msg}")
    pub_ok = all(x[1] for x in pub_results)
    if args.host_only:
        return 0 if pub_ok else 1

    print("\n" + "=" * 60)
    print("B. 交易 API（需 openclaw-trading 已启动）")
    print("=" * 60)

    ok_health, health_body = _api_probe(base, "/health", 15.0)
    print(f"  [{'OK ' if ok_health else 'FAIL'}] GET /health")
    if not ok_health:
        print(" ", health_body[:300])
        print("\n交易 API 不可达。请先: docker compose up -d")
        return 1

    routes: list[tuple[str, str]] = [
        ("GET /api/v1/exchanges", "/api/v1/exchanges"),
        ("GET /api/v1/market/ticker", f"/api/v1/market/ticker?symbol={sym_q}"),
        ("GET /api/v1/market/klines", f"/api/v1/market/klines?symbol={sym_q}&interval=1m&limit=3"),
        ("GET /api/v1/market/orderbook", f"/api/v1/market/orderbook?symbol={sym_q}&depth=5"),
        ("GET /api/v1/data-hub/status", "/api/v1/data-hub/status"),
        ("GET /api/v1/data-hub/unified-snapshot", f"/api/v1/data-hub/unified-snapshot?symbol={sym_q}"),
        ("GET /api/v1/system/status", "/api/v1/system/status"),
        ("GET /api/v1/system/acceptance", "/api/v1/system/acceptance"),
        ("GET /api/v1/modules/commander/audit", "/api/v1/modules/commander/audit?enrich=true"),
        ("GET /api/v1/modules/commander/account-diagnostics", "/api/v1/modules/commander/account-diagnostics"),
        ("GET /api/v1/ai/memory/workspace-files", "/api/v1/ai/memory/workspace-files"),
        ("GET /api/v1/s1/verify", "/api/v1/s1/verify"),
    ]

    failed = 0
    for title, path in routes:
        ok, body = _api_probe(base, path, 90.0)
        if not ok:
            failed += 1
        tag = "OK " if ok else "FAIL"
        print(f"  [{tag}] {title}")
        if not ok:
            print("       ", body[:400])

    for title, path in [
        ("exchanges", "/api/v1/exchanges"),
        ("ticker", f"/api/v1/market/ticker?symbol={sym_q}"),
    ]:
        ok, body = _api_probe(base, path, 60.0)
        if ok:
            _summarize_json_snippet(title, body, 1500)
            if title == "ticker":
                try:
                    td = json.loads(body)
                    if td.get("source") == "fallback":
                        print(
                            "\n 注意行情 ticker 为 fallback：DataSourceHub 未拿到交易所有效 last/bid/ask，"
                            "常见原因：经代理的 OKX REST 超时/被掐断。请查 unified-snapshot 里 exch.* 与日志。"
                        )
                except json.JSONDecodeError:
                    pass

    ok_s1, s1_body = _api_probe(base, "/api/v1/s1/verify", 60.0)
    if ok_s1:
        try:
            d = json.loads(s1_body)
            ap = d.get("all_passed")
            print(f"\n  s1/verify all_passed = {ap}")
            if ap is False:
                for c in d.get("checks") or []:
                    if not c.get("passed"):
                        print("    FAIL:", c.get("name"), c.get("detail"))
        except json.JSONDecodeError:
            pass

    print("\n" + "=" * 60)
    print("汇总")
    print("=" * 60)
    cg_ok = pub_results[2][1] if len(pub_results) > 2 else True
    print(f"  宿主机公网 OKX+Binance: {'PASS' if pub_results[0][1] and pub_results[1][1] else 'FAIL'}")
    print(f"  宿主机 CoinGecko（3 次重试）: {'PASS' if cg_ok else 'WARN（间歇 TLS/链路，不等同应用内数据源）'}")
    print(f"  交易 API 路由失败数: {failed} / {len(routes)}")
    core_ok = failed == 0 and pub_results[0][1] and pub_results[1][1]
    if core_ok and cg_ok:
        print("\n  FULL_SYSTEM_CHECK=PASS")
        return 0
    if core_ok and not cg_ok:
        print("\n  FULL_SYSTEM_CHECK=PASS_WITH_COINGECKO_WARN")
        return 0
    print("\n  FULL_SYSTEM_CHECK=FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
