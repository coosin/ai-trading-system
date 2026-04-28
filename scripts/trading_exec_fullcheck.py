#!/usr/bin/env python3
"""
One-click retest: execution attribution + SR sim + learning seed.

This script does not place real orders.
It does, however, call learning seed-and-run, which mutates learning memory / reports
and may update runtime config overrides as part of the acceptance flow.

Usage:
  python3 scripts/trading_exec_fullcheck.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
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


def http_json_retry(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    timeout: float = 45.0,
    retries: int = 3,
    backoff_sec: float = 1.5,
) -> dict:
    last: dict = {"success": False, "error": "unknown", "url": url}
    for i in range(max(1, int(retries))):
        last = http_json(method, url, body=body, timeout=timeout)
        if bool(last.get("success")):
            return last
        # Retry only for timeout/connection-like failures.
        err = str(last.get("error") or "").lower()
        if i >= max(1, int(retries)) - 1:
            break
        if ("timed out" in err) or ("connection" in err) or ("refused" in err):
            time.sleep(backoff_sec * float(i + 1))
            continue
        break
    return last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base url")
    ap.add_argument("--limit-events", type=int, default=20)
    ap.add_argument("--seed-n", type=int, default=8)
    ap.add_argument("--seed-symbol", default="BTC/USDT/SWAP")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")

    print("== 1) trading-diagnosis (before) ==")
    diag1 = http_json_retry("GET", f"{base}/api/v1/modules/commander/trading-diagnosis?limit_events={args.limit_events}")
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
    rec1 = data1.get("execution_reconciliation") or {}
    if isinstance(rec1, dict):
        sm1 = rec1.get("summary") or {}
        print(
            "execution_reconciliation:",
            {k: rec1.get(k) for k in ("healthy", "severity")},
            {k: sm1.get(k) for k in ("exchange_positions", "ai_trading_engine_positions", "ai_core_positions", "drift_total", "stale_open_orders")},
        )
    rcp1 = data1.get("execution_reconciliation_protection") or {}
    if isinstance(rcp1, dict):
        print(
            "execution_reconciliation_protection:",
            {
                "global_lock_active": rcp1.get("global_lock_active"),
                "symbol_locks": len((rcp1.get("symbol_locks") or {})) if isinstance(rcp1.get("symbol_locks"), dict) else 0,
            },
        )
    sr1 = data1.get("execution_safe_recovery") or {}
    if isinstance(sr1, dict):
        auto1 = sr1.get("automatic_actions_attempted") or []
        print("execution_safe_recovery:", {"policy": sr1.get("policy"), "auto_actions": len(auto1) if isinstance(auto1, list) else 0})

    print("\n== 2) SR/SLTP simtest (local) ==")
    here = os.path.dirname(os.path.abspath(__file__))
    sim = os.path.join(here, "sltp_sr_simtest.py")
    r = subprocess.run([sys.executable, sim], check=False, capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print("simtest_failed:", r.stderr.strip()[:400])

    print("\n== 3) learning seed-and-run ==")
    seed = http_json_retry(
        "POST",
        f"{base}/api/v1/modules/commander/learning/seed-and-run",
        body={"n": args.seed_n, "symbol": args.seed_symbol},
        timeout=40.0,
        retries=3,
        backoff_sec=2.0,
    )
    print("success:", seed.get("success"), "seeded:", seed.get("seeded"))
    if not seed.get("success"):
        print("error:", seed.get("message") or seed.get("error"))

    print("\n== 4) trading-diagnosis (after) ==")
    diag2 = http_json_retry("GET", f"{base}/api/v1/modules/commander/trading-diagnosis?limit_events={args.limit_events}")
    if not diag2.get("success"):
        print("error:", diag2.get("error"))
    data2 = (diag2.get("data") or {}) if isinstance(diag2, dict) else {}
    le = data2.get("ai_learning_engine") or {}
    print("learning:", {k: le.get(k) for k in ("enabled", "total_lessons", "last_run_at", "last_optimize_at") if isinstance(le, dict)})
    tlf = data2.get("trace_learning_feedback") or {}
    if isinstance(tlf, dict):
        print(
            "trace_learning_feedback:",
            {k: tlf.get(k) for k in ("sample_size", "guard_rejected", "execution_failed", "reconciliation_blocked", "updated_at")},
        )
    attr2 = data2.get("execution_attribution") or {}
    print("failures_in_window:", attr2.get("failures_in_window"))
    top2 = attr2.get("top_reasons") or []
    if isinstance(top2, list) and top2:
        print("top_reason:", top2[0].get("key"), "count=", top2[0].get("count"))

    print("\n== 5) decision-traces review ==")
    traces = http_json_retry(
        "GET",
        f"{base}/api/v1/modules/commander/decision-traces?limit=20",
        timeout=45.0,
        retries=3,
        backoff_sec=1.5,
    )
    if not traces.get("success"):
        print("error:", traces.get("message") or traces.get("error"))
    td = (traces.get("data") or {}) if isinstance(traces, dict) else {}
    sm = td.get("summary") or {}
    print(
        "decision_trace_summary:",
        {k: sm.get(k) for k in ("sample_size", "guard_rejected", "guard_passed", "execution_success", "execution_failed", "reconciliation_blocked")},
    )
    tgr = td.get("top_guard_reasons") or []
    if isinstance(tgr, list) and tgr:
        print("top_guard_reason:", tgr[0].get("key"), "count=", tgr[0].get("count"))
    ter = td.get("top_execution_failures") or []
    if isinstance(ter, list) and ter:
        print("top_execution_failure:", ter[0].get("key"), "count=", ter[0].get("count"))
    trb = td.get("top_reconciliation_blocks") or []
    if isinstance(trb, list) and trb:
        print("top_reconciliation_block:", trb[0].get("key"), "count=", trb[0].get("count"))

    print("\nDONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

