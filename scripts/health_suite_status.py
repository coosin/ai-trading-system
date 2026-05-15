#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO = Path(__file__).resolve().parents[1]


def latest_file(directory: Path, pattern: str) -> Path | None:
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def parse_audit_status(path: Path | None) -> Tuple[str, List[str]]:
    if not path or not path.exists():
        return "RED", ["audit_missing"]
    text = path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"== verdict ==\s*\n([A-Z]+)", text)
    verdict = match.group(1).strip() if match else "UNKNOWN"
    bad_items = re.findall(r"- \[BAD\] ([^ ]+) \((P\d)\): (.+)", text)
    reasons = [f"{name}:{sev}" for name, sev, _ in bad_items[:6]]
    if verdict == "PASS":
        return "GREEN", reasons
    if verdict == "WARN":
        return "YELLOW", reasons or ["audit_warn"]
    if verdict == "ATTENTION":
        return "YELLOW", reasons or ["audit_attention"]
    return "RED", reasons or [f"audit_{verdict.lower()}"]


def load_monitor_status(path: Path | None) -> Tuple[str, Dict[str, Any], List[str]]:
    if not path or not path.exists():
        return "RED", {}, ["monitor_missing"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "RED", {}, ["monitor_parse_failed"]
    reasons: List[str] = []
    error_rounds = int(data.get("error_rounds", 0) or 0)
    warning_rounds = int(data.get("warning_rounds", 0) or 0)
    health_transitions = int(data.get("health_transitions", 0) or 0)
    reachability_transitions = int(data.get("reachability_transitions", 0) or 0)
    disconnect_growth = int(data.get("disconnect_growth", 0) or 0)
    circuit_break_growth = int(data.get("circuit_break_growth", 0) or 0)
    fallback_growth = int(data.get("fallback_growth", 0) or 0)
    if error_rounds > 0:
        reasons.append(f"monitor_errors={error_rounds}")
    if warning_rounds > 0:
        reasons.append(f"monitor_warnings={warning_rounds}")
    if health_transitions > 0:
        reasons.append(f"health_transitions={health_transitions}")
    if reachability_transitions > 0:
        reasons.append(f"reachability_transitions={reachability_transitions}")
    if disconnect_growth > 0:
        reasons.append(f"disconnect_growth={disconnect_growth}")
    if circuit_break_growth > 0:
        reasons.append(f"circuit_break_growth={circuit_break_growth}")
    if fallback_growth > 0:
        reasons.append(f"fallback_growth={fallback_growth}")
    if error_rounds > 0 or health_transitions > 0 or reachability_transitions > 0:
        return "RED", data, reasons
    if warning_rounds > 0 or disconnect_growth > 0 or circuit_break_growth > 0 or fallback_growth > 0:
        return "YELLOW", data, reasons
    return "GREEN", data, reasons


def combine(audit_level: str, monitor_level: str) -> str:
    order = {"GREEN": 0, "YELLOW": 1, "RED": 2}
    return max((audit_level, monitor_level), key=lambda x: order.get(x, 99))


def main() -> int:
    ap = argparse.ArgumentParser(description="Compact R/Y/G health status")
    ap.add_argument("--audit-dir", default=str(REPO / "logs" / "health"))
    ap.add_argument("--monitor-dir", default=str(REPO / "runtime"))
    ap.add_argument("--output", default=str(REPO / "logs" / "health" / "health_suite_status.json"))
    args = ap.parse_args()

    audit_dir = Path(args.audit_dir)
    monitor_dir = Path(args.monitor_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    audit_level, audit_reasons = parse_audit_status(latest_file(audit_dir, "full_system_audit_*.log"))
    monitor_level, monitor_data, monitor_reasons = load_monitor_status(latest_file(monitor_dir, "live_stability_monitor.*.summary.json"))
    overall = combine(audit_level, monitor_level)

    payload = {
        "overall": overall,
        "audit_level": audit_level,
        "monitor_level": monitor_level,
        "reasons": audit_reasons + monitor_reasons,
        "monitor_rounds": monitor_data.get("rounds"),
        "disconnect_growth": monitor_data.get("disconnect_growth"),
        "circuit_break_growth": monitor_data.get("circuit_break_growth"),
        "fallback_growth": monitor_data.get("fallback_growth"),
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if overall == "GREEN" else (2 if overall == "YELLOW" else 5)


if __name__ == "__main__":
    raise SystemExit(main())
