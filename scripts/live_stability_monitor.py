#!/usr/bin/env python3
"""
Live stability monitor for OpenClaw.

Focus:
- API health drift
- Exchange reachability drift
- LLM circuit-break / fallback growth
- Network disconnect growth
- Trade guard rejection growth

This script is read-only and does not place orders.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_json(url: str, timeout: float = 15.0) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw), None
    except urllib.error.HTTPError as e:
        return None, f"http_error:{e.code}"
    except Exception as e:
        return None, f"{type(e).__name__}:{e}"


def dig(obj: Any, *path: str, default: Any = None) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def read_log_tail_counts(log_path: Path, tail_lines: int) -> Dict[str, int]:
    if not log_path.exists():
        return {
            "disconnects": 0,
            "circuit_breaks": 0,
            "fallbacks": 0,
            "okx_session_rebuilt": 0,
            "guard_reject_lines": 0,
        }
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-tail_lines:]
    counts = {
        "disconnects": 0,
        "circuit_breaks": 0,
        "fallbacks": 0,
        "okx_session_rebuilt": 0,
        "guard_reject_lines": 0,
    }
    for line in lines:
        low = line.lower()
        if "可重试" not in line and (
            "remoteprotocolerror" in low or "server disconnected" in low or "incomplete chunked read" in low
        ):
            counts["disconnects"] += 1
        if "circuit-break" in low:
            counts["circuit_breaks"] += 1
        if "尝试回退模型" in line:
            counts["fallbacks"] += 1
        if "okx会话已重建" in line:
            counts["okx_session_rebuilt"] += 1
        if "执行门控拒绝" in line:
            counts["guard_reject_lines"] += 1
    return counts


@dataclass
class RoundSnapshot:
    ts: str
    health_status: str
    exchange_reachability: str
    trading_diag_ok: bool
    risk_circuit_status: str
    exchange_connected: bool
    ai_core_running: bool
    llm_circuit_breaks: int
    llm_fallbacks: int
    network_disconnects: int
    okx_session_rebuilt: int
    guard_reject_lines: int
    rr_rejected: int
    sr_timing_rejected: int
    exchange_unreachable_rejected: int
    exchange_degraded_risk_reduced: int
    position_count: int
    active_orders: int
    warnings: List[str]
    errors: List[str]


def collect(base_url: str, log_path: Path, tail_lines: int, timeout: float) -> RoundSnapshot:
    warnings: List[str] = []
    errors: List[str] = []

    health, err = http_json(f"{base_url}/api/v1/system/health", timeout=timeout)
    if err:
        errors.append(f"health:{err}")
        health = {}
    diag, err = http_json(
        f"{base_url}/api/v1/modules/commander/trading-diagnosis?limit_events=20&timeout_sec=20",
        timeout=max(timeout, 25.0),
    )
    if err:
        errors.append(f"trading_diagnosis:{err}")
        diag = {}
    risk, err = http_json(f"{base_url}/api/v1/modules/risk/status", timeout=timeout)
    if err:
        errors.append(f"risk:{err}")
        risk = {}

    log_counts = read_log_tail_counts(log_path, tail_lines=tail_lines)

    health_data = health.get("data") if isinstance(health, dict) else {}
    diag_data = diag.get("data") if isinstance(diag, dict) else {}
    if not isinstance(health_data, dict):
        warnings.append("health_payload_invalid")
        health_data = {}
    if not isinstance(diag_data, dict):
        warnings.append("trading_diag_payload_invalid")
        diag_data = {}
    ai_core = diag_data.get("ai_core") if isinstance(diag_data.get("ai_core"), dict) else {}
    exec_gw = diag_data.get("execution_gateway") if isinstance(diag_data.get("execution_gateway"), dict) else {}
    sltp = diag_data.get("sltp") if isinstance(diag_data.get("sltp"), dict) else {}
    guards = dig(ai_core, "execution_guards", "stats", default={}) or {}

    health_status = str(dig(health_data, "status", default="unknown")).lower()
    reachability = str(dig(health_data, "exchange_reachability", "status", default="unknown")).lower()
    risk_circuit = str(dig(risk, "circuit_breaker", "status", default="unknown")).lower()
    trading_diag_ok = bool(dig(diag, "success", default=False))
    exchange_connected = bool(exec_gw.get("exchange_connected"))
    ai_core_running = bool(ai_core.get("running"))
    position_count = to_int(dig(risk, "last_check", "position_count", default=0))
    active_orders = to_int(sltp.get("active_orders"))

    if health_status != "healthy":
        warnings.append(f"health={health_status}")
    if reachability not in {"reachable", "degraded"}:
        warnings.append(f"exchange_reachability={reachability}")
    if risk_circuit != "closed":
        warnings.append(f"risk_circuit={risk_circuit}")
    if not trading_diag_ok:
        warnings.append("trading_diag_failed")
    if not exchange_connected:
        warnings.append("exchange_disconnected")
    if not ai_core_running:
        warnings.append("ai_core_not_running")

    return RoundSnapshot(
        ts=now_utc(),
        health_status=health_status,
        exchange_reachability=reachability,
        trading_diag_ok=trading_diag_ok,
        risk_circuit_status=risk_circuit,
        exchange_connected=exchange_connected,
        ai_core_running=ai_core_running,
        llm_circuit_breaks=log_counts["circuit_breaks"],
        llm_fallbacks=log_counts["fallbacks"],
        network_disconnects=log_counts["disconnects"],
        okx_session_rebuilt=log_counts["okx_session_rebuilt"],
        guard_reject_lines=log_counts["guard_reject_lines"],
        rr_rejected=to_int(guards.get("rr_rejected")),
        sr_timing_rejected=to_int(guards.get("sr_timing_rejected")),
        exchange_unreachable_rejected=to_int(guards.get("exchange_unreachable_rejected")),
        exchange_degraded_risk_reduced=to_int(guards.get("exchange_degraded_risk_reduced")),
        position_count=position_count,
        active_orders=active_orders,
        warnings=warnings,
        errors=errors,
    )


def summarize(cur: RoundSnapshot, prev: Optional[RoundSnapshot]) -> str:
    events: List[str] = []
    if prev:
        if cur.health_status != prev.health_status:
            events.append(f"health:{prev.health_status}->{cur.health_status}")
        if cur.exchange_reachability != prev.exchange_reachability:
            events.append(f"reach:{prev.exchange_reachability}->{cur.exchange_reachability}")
        for key in (
            "llm_circuit_breaks",
            "llm_fallbacks",
            "network_disconnects",
            "okx_session_rebuilt",
            "guard_reject_lines",
            "rr_rejected",
            "sr_timing_rejected",
            "exchange_unreachable_rejected",
            "exchange_degraded_risk_reduced",
        ):
            dv = getattr(cur, key) - getattr(prev, key)
            if dv > 0:
                events.append(f"{key}+{dv}")
    line = (
        f"[{cur.ts}] health={cur.health_status} reach={cur.exchange_reachability} "
        f"diag={'ok' if cur.trading_diag_ok else 'bad'} risk_cb={cur.risk_circuit_status} "
        f"exch={'on' if cur.exchange_connected else 'off'} ai_core={'on' if cur.ai_core_running else 'off'} "
        f"pos={cur.position_count} sltp_active={cur.active_orders} "
        f"log(disconnect={cur.network_disconnects},cb={cur.llm_circuit_breaks},fb={cur.llm_fallbacks},okx_rebuild={cur.okx_session_rebuilt},guard={cur.guard_reject_lines}) "
        f"guards(rr={cur.rr_rejected},sr={cur.sr_timing_rejected},unreach={cur.exchange_unreachable_rejected},degraded_reduce={cur.exchange_degraded_risk_reduced})"
    )
    if cur.warnings:
        line += " warnings=" + ",".join(cur.warnings)
    if cur.errors:
        line += " errors=" + ",".join(cur.errors)
    if events:
        line += " events=" + ";".join(events)
    return line


def write_summary(rounds: List[RoundSnapshot], out_path: Path) -> None:
    if not rounds:
        return
    first = rounds[0]
    last = rounds[-1]
    summary = {
        "started_at": first.ts,
        "ended_at": last.ts,
        "rounds": len(rounds),
        "health_transitions": sum(1 for i in range(1, len(rounds)) if rounds[i].health_status != rounds[i - 1].health_status),
        "reachability_transitions": sum(1 for i in range(1, len(rounds)) if rounds[i].exchange_reachability != rounds[i - 1].exchange_reachability),
        "disconnect_growth": last.network_disconnects - first.network_disconnects,
        "circuit_break_growth": last.llm_circuit_breaks - first.llm_circuit_breaks,
        "fallback_growth": last.llm_fallbacks - first.llm_fallbacks,
        "okx_rebuild_growth": last.okx_session_rebuilt - first.okx_session_rebuilt,
        "guard_reject_growth": last.guard_reject_lines - first.guard_reject_lines,
        "rr_rejected_growth": last.rr_rejected - first.rr_rejected,
        "sr_rejected_growth": last.sr_timing_rejected - first.sr_timing_rejected,
        "exchange_unreachable_rejected_growth": last.exchange_unreachable_rejected - first.exchange_unreachable_rejected,
        "exchange_degraded_risk_reduced_growth": last.exchange_degraded_risk_reduced - first.exchange_degraded_risk_reduced,
        "warning_rounds": sum(1 for r in rounds if r.warnings),
        "error_rounds": sum(1 for r in rounds if r.errors),
        "last_round": asdict(last),
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Observe live OpenClaw stability drift")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--interval-sec", type=float, default=30.0)
    ap.add_argument("--duration-min", type=float, default=30.0)
    ap.add_argument("--iterations", type=int, default=0, help="Overrides duration when > 0")
    ap.add_argument("--timeout-sec", type=float, default=15.0)
    ap.add_argument("--log-tail-lines", type=int, default=2000)
    ap.add_argument("--log-path", default=str(REPO / "logs" / "app.log"))
    ap.add_argument("--out", default=str(REPO / "runtime" / "live_stability_monitor.jsonl"))
    ap.add_argument("--summary-out", default=str(REPO / "runtime" / "live_stability_monitor.summary.json"))
    args = ap.parse_args()

    out_path = Path(args.out)
    summary_path = Path(args.summary_out)
    log_path = Path(args.log_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    rounds: List[RoundSnapshot] = []
    prev: Optional[RoundSnapshot] = None
    max_iters = int(args.iterations) if int(args.iterations) > 0 else max(1, int((float(args.duration_min) * 60.0) / max(1.0, float(args.interval_sec))))

    for _ in range(max_iters):
        snap = collect(args.base_url.rstrip("/"), log_path, int(args.log_tail_lines), float(args.timeout_sec))
        rounds.append(snap)
        out_path.open("a", encoding="utf-8").write(json.dumps(asdict(snap), ensure_ascii=False) + "\n")
        print(summarize(snap, prev), flush=True)
        prev = snap
        if len(rounds) < max_iters:
            time.sleep(max(1.0, float(args.interval_sec)))

    write_summary(rounds, summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
