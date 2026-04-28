#!/usr/bin/env python3
"""
One-click retest: execution attribution + SR sim + learning seed.

This script is safe by default:
- Only calls read-only diagnosis endpoints, SR sim (local), and learning seed endpoint.
- Does NOT place real orders.

Usage:
  python3 scripts/trading_exec_fullcheck.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request


def http_json(method: str, url: str, body: dict | None = None, timeout: float = 25.0) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except Exception as e:
        return {"success": False, "error": str(e), "url": url}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base url")
    ap.add_argument("--limit-events", type=int, default=20)
    ap.add_argument("--seed-n", type=int, default=8)
    ap.add_argument("--seed-symbol", default="BTC/USDT/SWAP")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")

    print("== 1) trading-diagnosis (before) ==")
    diag1 = http_json("GET", f"{base}/api/v1/modules/commander/trading-diagnosis?limit_events={args.limit_events}")
    print("success:", diag1.get("success"))
    if not diag1.get("success"):
        print("error:", diag1.get("error"))
    data1 = (diag1.get("data") or {}) if isinstance(diag1, dict) else {}
    pl = data1.get("position_limits_snapshot") if isinstance(data1, dict) else None
    if isinstance(pl, dict):
        print(
            "position_limits_snapshot:",
            {k: pl.get(k) for k in ("symbol_max_margin_ratio", "max_same_direction_positions", "max_positions_oneway", "max_positions_hedge", "hard_max_positions")},
        )
    attr1 = data1.get("execution_attribution") or {}
    print("failures_in_window:", attr1.get("failures_in_window"))
    top = attr1.get("top_reasons") or []
    if isinstance(top, list) and top:
        print("top_reason:", top[0].get("key"), "count=", top[0].get("count"))

    print("\n== 2) SR/SLTP simtest (local) ==")
    here = os.path.dirname(os.path.abspath(__file__))
    sim = os.path.join(here, "sltp_sr_simtest.py")
    r = subprocess.run([sys.executable, sim], check=False, capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print("simtest_failed:", r.stderr.strip()[:400])

    print("\n== 3) learning seed-and-run ==")
    seed = http_json(
        "POST",
        f"{base}/api/v1/modules/commander/learning/seed-and-run",
        body={"n": args.seed_n, "symbol": args.seed_symbol},
        timeout=40.0,
    )
    print("success:", seed.get("success"), "seeded:", seed.get("seeded"))
    if not seed.get("success"):
        print("error:", seed.get("message") or seed.get("error"))

    print("\n== 4) trading-diagnosis (after) ==")
    diag2 = http_json("GET", f"{base}/api/v1/modules/commander/trading-diagnosis?limit_events={args.limit_events}")
    if not diag2.get("success"):
        print("error:", diag2.get("error"))
    data2 = (diag2.get("data") or {}) if isinstance(diag2, dict) else {}
    le = data2.get("ai_learning_engine") or {}
    print("learning:", {k: le.get(k) for k in ("enabled", "total_lessons", "last_run_at", "last_optimize_at") if isinstance(le, dict)})
    attr2 = data2.get("execution_attribution") or {}
    print("failures_in_window:", attr2.get("failures_in_window"))
    top2 = attr2.get("top_reasons") or []
    if isinstance(top2, list) and top2:
        print("top_reason:", top2[0].get("key"), "count=", top2[0].get("count"))

    print("\nDONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

