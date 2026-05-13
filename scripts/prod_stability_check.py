#!/usr/bin/env python3
"""
Production-grade stability acceptance check (no real orders).

Goals:
- Catch multi-instance / binding split issues early
- Verify health + exchange reachability degradation semantics
- Verify trading-diagnosis is responsive and key invariants are sane

Usage:
  OPENCLAW_API_BASE=http://127.0.0.1:8000 python3 scripts/prod_stability_check.py
  BASE_URL=http://127.0.0.1:8000 python3 scripts/prod_stability_check.py
  python3 scripts/prod_stability_check.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.utils.openclaw_api_client import default_openclaw_api_base

def _now() -> str:
    return datetime.now().isoformat()


def _http_json(method: str, url: str, *, body: Optional[dict] = None, timeout: float = 12.0) -> Dict[str, Any]:
    data = None
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return {"success": False, "error": "json_decode_failed", "raw": raw[:2000]}


def _try_get(url: str, timeout: float = 10.0) -> Tuple[bool, Dict[str, Any]]:
    try:
        return True, _http_json("GET", url, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = str(e)
        return False, {"success": False, "error": f"http_{e.code}", "raw": raw[:2000]}
    except Exception as e:
        return False, {"success": False, "error": str(e)[:240]}


@dataclass
class CheckItem:
    id: str
    ok: bool
    severity: str
    detail: str
    data: Optional[Dict[str, Any]] = None


def _add(items: List[CheckItem], cid: str, ok: bool, severity: str, detail: str, data: Optional[Dict[str, Any]] = None) -> None:
    items.append(CheckItem(id=cid, ok=bool(ok), severity=str(severity), detail=str(detail), data=data))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base-url",
        default=os.environ.get("OPENCLAW_API_BASE")
        or os.environ.get("BASE_URL")
        or os.environ.get("ACCEPTANCE_BASE")
        or "",
        help="API 根，如 http://127.0.0.1:8000；默认同 OPENCLAW_API_BASE / BASE_URL / ACCEPTANCE_BASE",
    )
    ap.add_argument("--timeout-sec", type=float, default=12.0)
    ap.add_argument("--diag-timeout-sec", type=float, default=8.0)
    # Cold start in production can take > 60s (module init + exchange + background tasks).
    ap.add_argument("--max-health-wait-sec", type=float, default=150.0)
    ap.add_argument("--require-health", action="store_true", help="Fail if /system/health is not healthy (not just reachable)")
    args = ap.parse_args()

    base = (str(args.base_url or "").strip().rstrip("/") or default_openclaw_api_base())
    t = float(args.timeout_sec or 12.0)
    diag_t = float(args.diag_timeout_sec or 8.0)

    print(f"[{_now()}] prod_stability_check base={base}")
    items: List[CheckItem] = []

    # 0) Wait for health endpoint to be ready.
    health_url = f"{base}/api/v1/system/health"
    deadline = time.time() + float(args.max_health_wait_sec or 45.0)
    last_health: Dict[str, Any] = {}
    while time.time() < deadline:
        ok, payload = _try_get(health_url, timeout=min(8.0, t))
        if ok and isinstance(payload, dict) and payload.get("success"):
            last_health = payload
            break
        time.sleep(2.0)
    if not last_health:
        _add(items, "health_endpoint", False, "P0", f"/system/health not ready: {health_url}")
    else:
        d = last_health.get("data") if isinstance(last_health.get("data"), dict) else {}
        st = str(d.get("status") or "unknown").lower()
        reach = d.get("exchange_reachability") if isinstance(d.get("exchange_reachability"), dict) else {}
        reach_st = str(reach.get("status") or "unknown").lower()
        if st != "healthy" and reach_st == "unreachable":
            # Probe once more to avoid one-shot transient network jitter causing false ATTENTION.
            time.sleep(0.6)
            ok2, payload2 = _try_get(health_url, timeout=min(8.0, t))
            if ok2 and isinstance(payload2, dict) and payload2.get("success"):
                d2 = payload2.get("data") if isinstance(payload2.get("data"), dict) else {}
                st2 = str(d2.get("status") or "unknown").lower()
                reach2 = d2.get("exchange_reachability") if isinstance(d2.get("exchange_reachability"), dict) else {}
                reach_st2 = str(reach2.get("status") or "unknown").lower()
                if st2 == "healthy":
                    st = st2
                    reach = reach2
                    reach_st = reach_st2
                    _add(items, "health_transient_recovered", True, "P2", "health degraded transient recovered on retry")
        # For production acceptance:
        # - unreachable => P1 (operator action required; open should be blocked)
        # - degraded + degraded reachability => treat as warning (P2), not ATTENTION
        if st != "healthy" and reach_st == "degraded":
            _add(items, "health_degraded_warning", True, "P2", f"system.status={st} (reachability=degraded)", {"exchange_reachability": reach})
            _add(items, "health_status", True, "P2", f"system.status={st}", {"exchange_reachability": reach})
        else:
            _add(items, "health_status", st == "healthy", "P1" if st != "healthy" else "P3", f"system.status={st}", {"exchange_reachability": reach})
        _add(items, "exchange_reachability", reach_st in {"reachable", "degraded", "unreachable", "unknown"}, "P2", f"exchange_reachability.status={reach_st}")
        if args.require_health and st != "healthy":
            _add(items, "require_health", False, "P0", f"require_health set but status={st}")

    # 1) Binding split check (multi-instance / stale process signal)
    bind_url = f"{base}/api/v1/debug/exchange-binding"
    ok_bind, bind = _try_get(bind_url, timeout=min(8.0, t))
    if not ok_bind:
        _add(items, "binding_probe", False, "P2", "debug/exchange-binding unavailable", {"error": bind.get("error")})
    else:
        b = bind.get("binding") if isinstance(bind.get("binding"), dict) else {}
        same = bool(b.get("same_main_controller_object"))
        _add(items, "binding_same_mc", same, "P1" if not same else "P3", f"same_main_controller_object={same}", {"binding": b})

    # 2) System acceptance snapshot (architect view)
    acc_url = f"{base}/api/v1/system/acceptance"
    ok_acc, acc = _try_get(acc_url, timeout=min(10.0, t))
    if not ok_acc:
        _add(items, "system_acceptance", False, "P2", "/system/acceptance unavailable", {"error": acc.get("error")})
    else:
        verdict = str(acc.get("verdict") or "ATTENTION").upper()
        _add(items, "system_acceptance_verdict", verdict == "PASS", "P1" if verdict != "PASS" else "P3", f"acceptance.verdict={verdict}")

    # 3) S1 verify (execution spine + core rails)
    s1_url = f"{base}/api/v1/s1/verify"
    ok_s1, s1 = _try_get(s1_url, timeout=min(12.0, t))
    if not ok_s1:
        _add(items, "s1_verify", False, "P1", "/s1/verify unavailable", {"error": s1.get("error")})
    else:
        passed = bool(s1.get("all_passed"))
        _add(items, "s1_verify_passed", passed, "P1" if not passed else "P3", f"s1.all_passed={passed}", {"failed": s1.get("failed")})

    # 4) trading-diagnosis responsiveness + key invariants
    diag_url = f"{base}/api/v1/modules/commander/trading-diagnosis?limit_events=20&timeout_sec={diag_t}"
    ok_diag, diag = _try_get(diag_url, timeout=max(12.0, diag_t + 3.0))
    if not ok_diag or not bool(diag.get("success")):
        _add(items, "trading_diagnosis", False, "P1", "trading-diagnosis unavailable or failed", {"error": diag.get("error") or diag.get("message")})
    else:
        data = diag.get("data") if isinstance(diag.get("data"), dict) else {}
        exch = data.get("exchange_reachability") if isinstance(data.get("exchange_reachability"), dict) else {}
        exch_st = str(exch.get("status") or "unknown").lower()
        attr = data.get("execution_attribution") if isinstance(data.get("execution_attribution"), dict) else {}
        summ = str(attr.get("summary") or "")
        rec = data.get("execution_reconciliation") if isinstance(data.get("execution_reconciliation"), dict) else {}
        rec_sum = rec.get("summary") if isinstance(rec.get("summary"), dict) else {}
        drift = int(rec_sum.get("drift_total", 0) or 0)
        stale_open = int(rec_sum.get("stale_open_orders", 0) or 0)
        _add(items, "diag_exchange_reachability", exch_st in {"reachable", "degraded", "unreachable", "unknown"}, "P2", f"diag.exchange_reachability={exch_st}", {"probe": exch.get("probe")})
        _add(items, "diag_attr_summary_present", bool(summ.strip()), "P2", "execution_attribution.summary present" if summ.strip() else "execution_attribution.summary missing")
        _add(items, "reconciliation_drift", drift == 0, "P1" if drift > 0 else "P3", f"reconciliation.drift_total={drift}")
        _add(items, "stale_open_orders", stale_open == 0, "P1" if stale_open > 0 else "P3", f"reconciliation.stale_open_orders={stale_open}")

    # Final verdict
    p0 = [x for x in items if (not x.ok) and x.severity == "P0"]
    p1 = [x for x in items if (not x.ok) and x.severity == "P1"]
    verdict = "PASS"
    if p0:
        verdict = "FAIL"
    elif p1:
        verdict = "ATTENTION"

    print("\n== verdict ==")
    print(verdict)
    print("\n== checks ==")
    for it in items:
        flag = "OK" if it.ok else "BAD"
        print(f"- [{flag}] {it.id} ({it.severity}): {it.detail}")
    if verdict != "PASS":
        print("\n== hints ==")
        for it in [x for x in items if not x.ok][:8]:
            if it.data:
                print(f"- {it.id}: {it.detail} data_keys={list(it.data.keys())[:6]}")

    return 0 if verdict == "PASS" else (2 if verdict == "ATTENTION" else 5)


if __name__ == "__main__":
    raise SystemExit(main())

