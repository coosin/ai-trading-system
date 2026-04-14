#!/usr/bin/env python3
"""
24小时连续巡检脚本（可缩短为任意时长）。

默认巡检接口：
- /health
- /api/v1/s1/verify
- /api/v1/modules/ai/guards
- /api/v1/modules/system/health
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib import error, request


DEFAULT_THRESHOLDS = {
    "max_rr_rejected_per_interval": 20,
    "max_spread_rejected_per_interval": 20,
    "max_depth_imbalance_rejected_per_interval": 20,
    "max_data_quality_holds_per_interval": 30,
    "max_dynamic_adjustments_per_interval": 80,
}


@dataclass
class GuardSnapshot:
    rr_rejected: int = 0
    spread_rejected: int = 0
    depth_rejected: int = 0
    data_quality_hold: int = 0


def _fetch_json(url: str, timeout: int = 8) -> Tuple[bool, Any, str]:
    try:
        req = request.Request(url, headers={"Accept": "application/json"})
        with request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
            return True, json.loads(text) if text else {}, ""
    except error.HTTPError as e:
        return False, None, f"http_{e.code}"
    except Exception as e:
        return False, None, str(e)


def _load_thresholds(path: Optional[str]) -> Dict[str, int]:
    if not path:
        return dict(DEFAULT_THRESHOLDS)
    p = Path(path)
    if not p.exists():
        return dict(DEFAULT_THRESHOLDS)
    try:
        user_data = json.loads(p.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_THRESHOLDS)
        for k, v in (user_data or {}).items():
            if k in merged:
                merged[k] = int(v)
        return merged
    except Exception:
        return dict(DEFAULT_THRESHOLDS)


def _extract_guard_snapshot(guards_payload: Dict[str, Any]) -> GuardSnapshot:
    stats = ((guards_payload or {}).get("stats") or {})
    return GuardSnapshot(
        rr_rejected=int(stats.get("rr_rejected", 0) or 0),
        spread_rejected=int(stats.get("spread_rejected", 0) or 0),
        depth_rejected=int(stats.get("depth_imbalance_rejected", 0) or 0),
        data_quality_hold=int(stats.get("data_quality_guard_hold", 0) or 0),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="连续巡检交易系统关键健康指标")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API 基础地址")
    parser.add_argument("--interval-sec", type=int, default=300, help="巡检间隔秒")
    parser.add_argument("--hours", type=float, default=24.0, help="巡检时长（小时）")
    parser.add_argument("--iterations", type=int, default=0, help="固定轮数（>0 时优先生效）")
    parser.add_argument("--thresholds", default="docs/system-monitor-thresholds.example.json", help="阈值配置JSON")
    parser.add_argument("--output", default="logs/system_probe_report.jsonl", help="输出报告JSONL")
    args = parser.parse_args()

    thresholds = _load_thresholds(args.thresholds)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    base = args.base_url.rstrip("/")
    endpoints = {
        "health": f"{base}/health",
        "s1_verify": f"{base}/api/v1/s1/verify",
        "ai_guards": f"{base}/api/v1/modules/ai/guards",
        "system_health": f"{base}/api/v1/modules/system/health",
        "sltp_stats": f"{base}/api/v1/modules/stop-loss/stats",
    }

    start = time.time()
    max_iters = args.iterations if args.iterations > 0 else int((args.hours * 3600) // max(1, args.interval_sec))
    max_iters = max(1, max_iters)

    prev_guard = GuardSnapshot()
    prev_dynamic_adjustments = 0
    total_alerts = 0

    for i in range(max_iters):
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        rec: Dict[str, Any] = {"ts": ts, "iteration": i + 1, "alerts": []}

        ok_health, data_health, err_health = _fetch_json(endpoints["health"])
        rec["health_ok"] = bool(ok_health and isinstance(data_health, dict))
        if not rec["health_ok"]:
            rec["alerts"].append(f"health_unavailable:{err_health}")

        ok_verify, data_verify, err_verify = _fetch_json(endpoints["s1_verify"])
        verify_ok = bool(ok_verify and isinstance(data_verify, dict) and data_verify.get("all_passed", False))
        rec["s1_verify_ok"] = verify_ok
        if not verify_ok:
            rec["alerts"].append(f"s1_verify_fail:{err_verify or 'all_passed_false'}")

        ok_guards, data_guards, err_guards = _fetch_json(endpoints["ai_guards"])
        if ok_guards and isinstance(data_guards, dict):
            snap = _extract_guard_snapshot(data_guards)
            d_rr = max(0, snap.rr_rejected - prev_guard.rr_rejected)
            d_sp = max(0, snap.spread_rejected - prev_guard.spread_rejected)
            d_dp = max(0, snap.depth_rejected - prev_guard.depth_rejected)
            d_dq = max(0, snap.data_quality_hold - prev_guard.data_quality_hold)
            rec["guards_delta"] = {
                "rr_rejected": d_rr,
                "spread_rejected": d_sp,
                "depth_imbalance_rejected": d_dp,
                "data_quality_guard_hold": d_dq,
            }
            if d_rr > thresholds["max_rr_rejected_per_interval"]:
                rec["alerts"].append(f"rr_rejected_spike:{d_rr}")
            if d_sp > thresholds["max_spread_rejected_per_interval"]:
                rec["alerts"].append(f"spread_rejected_spike:{d_sp}")
            if d_dp > thresholds["max_depth_imbalance_rejected_per_interval"]:
                rec["alerts"].append(f"depth_rejected_spike:{d_dp}")
            if d_dq > thresholds["max_data_quality_holds_per_interval"]:
                rec["alerts"].append(f"data_quality_hold_spike:{d_dq}")
            prev_guard = snap
        else:
            rec["alerts"].append(f"ai_guards_unavailable:{err_guards}")

        ok_sltp, data_sltp, err_sltp = _fetch_json(endpoints["sltp_stats"])
        if ok_sltp and isinstance(data_sltp, dict):
            cur_adj = int(data_sltp.get("dynamic_adjustments", 0) or 0)
            d_adj = max(0, cur_adj - prev_dynamic_adjustments)
            rec["sltp_dynamic_adjustments_delta"] = d_adj
            if d_adj > thresholds["max_dynamic_adjustments_per_interval"]:
                rec["alerts"].append(f"sltp_adjustments_spike:{d_adj}")
            prev_dynamic_adjustments = cur_adj
        else:
            # 某些版本尚未开放该接口，404 记为信息项，不计入告警。
            if str(err_sltp).startswith("http_404"):
                rec["sltp_stats_optional"] = "not_available"
            else:
                rec["alerts"].append(f"sltp_stats_unavailable:{err_sltp}")

        ok_sys, _, err_sys = _fetch_json(endpoints["system_health"])
        if not ok_sys:
            rec["alerts"].append(f"system_health_unavailable:{err_sys}")

        if rec["alerts"]:
            total_alerts += len(rec["alerts"])

        with output.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        print(f"[{ts}] round={i+1}/{max_iters} alerts={len(rec['alerts'])}")
        if i < max_iters - 1:
            time.sleep(max(1, args.interval_sec))

    elapsed = round(time.time() - start, 2)
    print(f"done rounds={max_iters} total_alerts={total_alerts} elapsed_sec={elapsed} report={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

