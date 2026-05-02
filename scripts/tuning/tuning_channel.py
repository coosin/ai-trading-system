import argparse
import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# Ensure local imports work when running as a standalone script.
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from ai_proposal import propose_hold_override_relaxation
from quality_eval import evaluate_traces_quality, _parse_iso_ts


def _fetch_json(url: str, timeout_s: float = 20.0) -> Any:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def _post_json(url: str, payload: Dict[str, Any], timeout_s: float = 20.0) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def fetch_ai_guards(api_base: str) -> Dict[str, Any]:
    url = api_base.rstrip("/") + "/api/v1/modules/ai/guards"
    obj = _fetch_json(url, timeout_s=20.0)
    if not isinstance(obj, dict) or not obj.get("success"):
        raise RuntimeError(f"fetch_ai_guards failed: {obj}")
    return obj.get("config") or {}


def update_ai_guards(api_base: str, config_updates: Dict[str, Any]) -> Dict[str, Any]:
    url = api_base.rstrip("/") + "/api/v1/modules/ai/guards"
    # Endpoint expects flat JSON body, not {"config": {...}} wrapper.
    payload = dict(config_updates or {})
    obj = _post_json(url, payload, timeout_s=20.0)
    if not isinstance(obj, dict) or not obj.get("success"):
        raise RuntimeError(f"update_ai_guards failed: {obj}")
    return obj


def fetch_decision_traces(api_base: str, limit: int = 200) -> List[Dict[str, Any]]:
    url = api_base.rstrip("/") + f"/api/v1/modules/commander/decision-traces?limit={int(limit)}"
    obj = _fetch_json(url, timeout_s=20.0)
    if not isinstance(obj, dict) or not obj.get("success", True):
        return []
    data = obj.get("data")
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        # common shapes
        for k in ("traces", "recent", "decision_traces"):
            if isinstance(data.get(k), list):
                return [x for x in data[k] if isinstance(x, dict)]
        # otherwise take values lists
        for v in data.values():
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def fetch_trading_diagnosis(api_base: str) -> Dict[str, Any]:
    url = api_base.rstrip("/") + "/api/v1/modules/commander/trading-diagnosis?limit_events=50"
    obj = _fetch_json(url, timeout_s=25.0)
    if not isinstance(obj, dict):
        return {}
    return obj.get("data") or obj


def filter_traces_by_time(
    traces: List[Dict[str, Any]],
    start_ts: float,
    end_ts: float,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for t in traces:
        if not isinstance(t, dict):
            continue
        ts = _parse_iso_ts(t.get("created_at"))
        if ts is None:
            continue
        if start_ts <= ts <= end_ts:
            out.append(t)
    return out


def summarize_funnel(traces: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute simple funnel counters:
      - open_count: action open/buy/sell
      - hold_count: action hold
      - guard reasons distribution
    """
    hold = 0
    open_count = 0
    guard_reason_counts: Dict[str, int] = {}
    total = 0
    for t in traces:
        a = t.get("action") or (t.get("execution") or {}).get("action")
        if not isinstance(a, str):
            continue
        total += 1
        if a.lower() == "hold":
            hold += 1
        elif a.lower() in ("open", "buy", "sell"):
            open_count += 1
        g = t.get("guard") or {}
        if isinstance(g, dict) and g.get("reason"):
            r = str(g.get("reason"))
            guard_reason_counts[r] = int(guard_reason_counts.get(r, 0)) + 1
    hold_ratio = (hold / total) if total else 0.0
    open_ratio = (open_count / total) if total else 0.0
    hold_reason = int(guard_reason_counts.get("hold_by_ai_decision", 0))
    hold_ratio_reason = (hold_reason / total) if total else 0.0
    return {
        "total": total,
        "hold_count": hold,
        "open_count": open_count,
        "hold_ratio": hold_ratio,
        "open_ratio": open_ratio,
        "hold_by_ai_decision_count": hold_reason,
        "hold_by_ai_decision_ratio": hold_ratio_reason,
        "guard_reason_counts": dict(sorted(guard_reason_counts.items(), key=lambda kv: kv[1], reverse=True)[:20]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", default="http://127.0.0.1:8000", help="Trading system API base")
    ap.add_argument("--validation-minutes", type=int, default=45, help="Validation window (minutes)")
    ap.add_argument("--baseline-minutes", type=int, default=60, help="Baseline window (minutes) before changes")
    ap.add_argument("--quality-horizon-minutes", type=int, default=60, help="Quality horizon (minutes) for realized 1h metrics")
    ap.add_argument("--kline-limit", type=int, default=240, help="Max klines fetched per symbol")
    ap.add_argument("--max-traces-quality", type=int, default=20, help="Limit traces evaluated for quality metrics")
    ap.add_argument("--min-post-samples", type=int, default=8, help="Minimum post-window trace samples for reliable decision")
    ap.add_argument("--auto-approve", action="store_true", help="Apply without manual approval")
    ap.add_argument("--run-id", default=None, help="Optional run id override")
    args = ap.parse_args()

    api_base = args.api_base.rstrip("/")
    now = time.time()
    baseline_end = now
    baseline_start = baseline_end - args.baseline_minutes * 60
    run_id = args.run_id or f"tuning-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out_dir = "/home/cool/ai-trading-system/workspace/tuning_runs"
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, f"{run_id}.json")

    # 1) Baseline
    all_traces = fetch_decision_traces(api_base, limit=400)
    baseline_traces = filter_traces_by_time(all_traces, baseline_start, baseline_end)
    baseline_funnel = summarize_funnel(baseline_traces)
    baseline_quality = None
    if baseline_traces:
        # Evaluate quality for a small set of traces; focus on holds that would be suppressed.
        # (Quality horizon is realized, so we can compute immediately.)
        horizon_sec = args.quality_horizon_minutes * 60
        # Select traces with hold_by_ai_decision guard or action hold.
        q_traces = [
            t
            for t in baseline_traces
            if (t.get("guard") or {}).get("reason") == "hold_by_ai_decision"
            or (t.get("action") or (t.get("execution") or {}).get("action")) == "hold"
        ]
        _, baseline_quality = evaluate_traces_quality(
            q_traces,
            api_base=api_base,
            horizon_sec=horizon_sec,
            kline_limit=args.kline_limit,
            max_traces=args.max_traces_quality,
            now_ts=baseline_end,
        )

    # 2) Current guard config
    current_guard_cfg = fetch_ai_guards(api_base)
    current_hold_cfg = {
        "hold_avoidance_override_enabled": current_guard_cfg.get("hold_avoidance_override_enabled", True),
        "hold_avoidance_override_cooldown_sec": current_guard_cfg.get("hold_avoidance_override_cooldown_sec", 1200),
        "hold_avoidance_override_min_abs_sentiment": current_guard_cfg.get("hold_avoidance_override_min_abs_sentiment", 0.06),
        "hold_avoidance_override_min_mi_quality_score": current_guard_cfg.get("hold_avoidance_override_min_mi_quality_score", 0.62),
        "hold_avoidance_override_require_mi_trend_alignment": current_guard_cfg.get("hold_avoidance_override_require_mi_trend_alignment", True),
    }

    baseline_counts = {
        "hold_ratio": baseline_funnel.get("hold_ratio", 0.0),
        "open_ratio": baseline_funnel.get("open_ratio", 0.0),
        "hold_by_ai_decision_ratio": baseline_funnel.get("hold_by_ai_decision_ratio", 0.0),
    }

    # 3) AI proposal (heuristic) for manual approval
    proposal = propose_hold_override_relaxation(
        current_hold_cfg=current_hold_cfg,
        baseline_counts=baseline_counts,
        baseline_quality=baseline_quality,
    )

    report: Dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(),
        "api_base": api_base,
        "baseline": {
            "window_minutes": args.baseline_minutes,
            "start_ts": baseline_start,
            "end_ts": baseline_end,
            "funnel": baseline_funnel,
            "quality": baseline_quality,
        },
        "proposal": {
            "proposal_id": proposal.proposal_id,
            "confidence": proposal.confidence,
            "target_keys": proposal.target_keys,
            "rationale": proposal.rationale,
        },
        "validation": {
            "window_minutes": args.validation_minutes,
            "quality_horizon_minutes": args.quality_horizon_minutes,
        },
        "execution": {
            "approved": None,
            "applied": None,
            "rollback": None,
            "before_guard_cfg": current_hold_cfg,
            "after_guard_cfg": None,
        },
    }

    # 4) Manual approval
    if not args.auto_approve:
        print("\n=== AI Proposal (Manual Approval Required) ===")
        print(json.dumps(report["proposal"], ensure_ascii=False, indent=2))
        choice = input("Type 'yes' to apply, otherwise abort: ").strip().lower()
        approved = choice == "yes"
    else:
        approved = True

    report["execution"]["approved"] = approved
    if not approved:
        report["execution"]["applied"] = False
        report["execution"]["rollback"] = False
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"Aborted. Report saved to: {report_path}")
        return

    # 5) Apply
    before_cfg_full = fetch_ai_guards(api_base)
    applied_updates = dict(proposal.target_keys)
    # Only send numeric keys and the explicit bool.
    update_ai_guards(api_base, applied_updates)
    after_cfg_full = fetch_ai_guards(api_base)
    report["execution"]["applied"] = True
    report["execution"]["after_guard_cfg"] = {
        k: after_cfg_full.get(k) for k in proposal.target_keys.keys()
    }

    # 6) Validation window
    start_ts = time.time()
    end_ts = start_ts + args.validation_minutes * 60
    print(f"Validation started for ~{args.validation_minutes} minutes: {run_id}")
    while time.time() < end_ts:
        time.sleep(10)

    # 7) Post stats
    traces_after = fetch_decision_traces(api_base, limit=600)
    post_traces = filter_traces_by_time(traces_after, start_ts, end_ts)
    post_funnel = summarize_funnel(post_traces)
    horizon_sec = args.quality_horizon_minutes * 60

    # Evaluate realized quality for opened decisions and hold_by_ai_decision during the window.
    # (Quality is computed using now_ts=end_ts, so it's fully realized for signals older than horizon.)
    q_open = [
        t
        for t in post_traces
        if (t.get("action") or (t.get("execution") or {}).get("action")) in ("open", "buy", "sell")
    ]
    q_hold = [
        t
        for t in post_traces
        if (t.get("guard") or {}).get("reason") == "hold_by_ai_decision"
        or (t.get("action") or (t.get("execution") or {}).get("action")) == "hold"
    ]

    _, q_open_summary = evaluate_traces_quality(
        q_open,
        api_base=api_base,
        horizon_sec=horizon_sec,
        kline_limit=args.kline_limit,
        max_traces=args.max_traces_quality,
        now_ts=end_ts,
    )
    _, q_hold_summary = evaluate_traces_quality(
        q_hold,
        api_base=api_base,
        horizon_sec=horizon_sec,
        kline_limit=args.kline_limit,
        max_traces=args.max_traces_quality,
        now_ts=end_ts,
    )

    report["validation"]["window_start_ts"] = start_ts
    report["validation"]["window_end_ts"] = end_ts
    report["validation"]["post_funnel"] = post_funnel
    report["validation"]["post_quality_open"] = q_open_summary
    report["validation"]["post_quality_hold"] = q_hold_summary

    # 8) Rollback decision
    # Use ratios instead of absolute counts because post window can have fewer traces.
    base_open = float(baseline_funnel.get("open_count", 0) or 0)
    post_open = float(post_funnel.get("open_count", 0) or 0)
    post_total = int(post_funnel.get("total", 0) or 0)
    base_open_ratio = float(baseline_funnel.get("open_ratio", 0.0) or 0.0)
    post_open_ratio = float(post_funnel.get("open_ratio", 0.0) or 0.0)
    base_hold_ratio = float(baseline_funnel.get("hold_by_ai_decision_ratio", 0.0) or 0.0)
    post_hold_ratio = float(post_funnel.get("hold_by_ai_decision_ratio", 0.0) or 0.0)

    # Minimal improvement expectations for 30~60 minutes window.
    hold_delta = base_hold_ratio - post_hold_ratio

    # Use conservative thresholds.
    should_rollback = False
    rollback_reasons: List[str] = []
    if post_total < max(1, int(args.min_post_samples or 8)):
        should_rollback = True
        rollback_reasons.append(
            f"inconclusive_low_post_samples (post_total={post_total}, required={int(args.min_post_samples or 8)})"
        )
    else:
        if post_open_ratio + 1e-9 < max(0.0, base_open_ratio - 0.05):
            should_rollback = True
            rollback_reasons.append(
                f"open_ratio deteriorated (base={base_open_ratio:.3f}, post={post_open_ratio:.3f})"
            )
        if hold_delta < -0.05:
            should_rollback = True
            rollback_reasons.append(
                f"hold_by_ai_decision_ratio worsened (base={base_hold_ratio:.3f}, post={post_hold_ratio:.3f})"
            )

    report["execution"]["rollback"] = should_rollback
    report["execution"]["rollback_reasons"] = rollback_reasons

    # 9) Rollback if needed
    if should_rollback:
        # Restore only the keys we changed.
        restore_updates = {k: before_cfg_full.get(k) for k in applied_updates.keys()}
        update_ai_guards(api_base, restore_updates)
        final_cfg = fetch_ai_guards(api_base)
        report["execution"]["after_rollback_cfg"] = {k: final_cfg.get(k) for k in restore_updates.keys()}

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    status_str = "APPLIED+KEPT" if not should_rollback else "ROLLED_BACK"
    print(f"Trial finished: {status_str}. Report saved to: {report_path}")


if __name__ == "__main__":
    main()

