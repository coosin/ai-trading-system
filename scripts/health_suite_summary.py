#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]


def latest_file(directory: Path, pattern: str) -> Optional[Path]:
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def parse_audit_log(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {"exists": False}
    text = path.read_text(encoding="utf-8", errors="ignore")
    verdict_match = re.search(r"== verdict ==\s*\n([A-Z]+)", text)
    verdict = verdict_match.group(1).strip() if verdict_match else "UNKNOWN"
    checks: List[Dict[str, str]] = []
    for flag, name, severity, detail in re.findall(r"- \[(OK|BAD)\] ([^ ]+) \((P\d)\): (.+)", text):
        checks.append(
            {
                "ok": str(flag == "OK").lower(),
                "name": name,
                "severity": severity,
                "detail": detail.strip(),
            }
        )
    bad = [c for c in checks if c["ok"] == "false"]
    return {
        "exists": True,
        "path": str(path),
        "verdict": verdict,
        "checks": checks,
        "bad_checks": bad,
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
    }


def load_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {"exists": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"exists": True, "path": str(path), "error": f"{type(e).__name__}: {e}"}
    if isinstance(data, dict):
        data["exists"] = True
        data["path"] = str(path)
        data["updated_at"] = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        return data
    return {"exists": True, "path": str(path), "error": "not_a_json_object"}


def format_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f}{unit}"
        value /= 1024.0
    return f"{num_bytes}B"


def collect_sizes() -> Dict[str, Any]:
    targets = [
        REPO / "runtime",
        REPO / "logs",
        REPO / "logs" / "health",
        REPO / "runtime" / "realtime_watch.jsonl",
    ]
    out: Dict[str, Any] = {}
    for path in targets:
        if not path.exists():
            out[str(path.relative_to(REPO))] = {"exists": False}
            continue
        if path.is_file():
            out[str(path.relative_to(REPO))] = {
                "exists": True,
                "size_bytes": path.stat().st_size,
                "size": format_size(path.stat().st_size),
            }
            continue
        total = 0
        for child in path.rglob("*"):
            if child.is_file():
                try:
                    total += child.stat().st_size
                except FileNotFoundError:
                    pass
        out[str(path.relative_to(REPO))] = {"exists": True, "size_bytes": total, "size": format_size(total)}
    return out


def build_markdown(audit: Dict[str, Any], monitor: Dict[str, Any], sizes: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Health Suite Summary")
    lines.append("")
    lines.append(f"- Generated at: {datetime.now().isoformat()}")
    if audit.get("exists"):
        lines.append(f"- Latest audit: `{audit.get('path')}`")
        lines.append(f"- Audit verdict: `{audit.get('verdict', 'UNKNOWN')}`")
    else:
        lines.append("- Latest audit: missing")
    if monitor.get("exists"):
        lines.append(f"- Latest monitor summary: `{monitor.get('path')}`")
        lines.append(f"- Monitor rounds: `{monitor.get('rounds', '?')}`")
    else:
        lines.append("- Latest monitor summary: missing")

    lines.append("")
    lines.append("## Current Status")
    if audit.get("exists"):
        bad = audit.get("bad_checks") or []
        if bad:
            for item in bad[:8]:
                lines.append(f"- Audit issue `{item.get('name')}` ({item.get('severity')}): {item.get('detail')}")
        else:
            lines.append("- Audit reports no failing checks.")
    else:
        lines.append("- Audit status unavailable.")

    if monitor.get("exists"):
        lines.append(f"- Health transitions: `{monitor.get('health_transitions', 0)}`")
        lines.append(f"- Reachability transitions: `{monitor.get('reachability_transitions', 0)}`")
        lines.append(f"- Disconnect growth: `{monitor.get('disconnect_growth', 0)}`")
        lines.append(f"- Circuit-break growth: `{monitor.get('circuit_break_growth', 0)}`")
        lines.append(f"- Fallback growth: `{monitor.get('fallback_growth', 0)}`")
        lines.append(f"- Guard reject growth: `{monitor.get('guard_reject_growth', 0)}`")
        lines.append(f"- Warning rounds: `{monitor.get('warning_rounds', 0)}`")
        lines.append(f"- Error rounds: `{monitor.get('error_rounds', 0)}`")
    else:
        lines.append("- Monitor summary unavailable.")

    lines.append("")
    lines.append("## Storage")
    for name, meta in sizes.items():
        if meta.get("exists"):
            lines.append(f"- `{name}`: `{meta.get('size')}`")
        else:
            lines.append(f"- `{name}`: missing")

    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize latest health audit and monitor outputs")
    ap.add_argument("--audit-dir", default=str(REPO / "logs" / "health"))
    ap.add_argument("--monitor-dir", default=str(REPO / "runtime"))
    ap.add_argument("--output", default=str(REPO / "logs" / "health" / "health_suite_summary.md"))
    args = ap.parse_args()

    audit_dir = Path(args.audit_dir)
    monitor_dir = Path(args.monitor_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    audit = parse_audit_log(latest_file(audit_dir, "full_system_audit_*.log"))
    monitor = load_json(latest_file(monitor_dir, "live_stability_monitor.*.summary.json"))
    sizes = collect_sizes()
    md = build_markdown(audit, monitor, sizes)
    output.write_text(md, encoding="utf-8")
    print(f"summary written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
