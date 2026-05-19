#!/usr/bin/env python3
"""
OpenClaw full-system audit.

Goals:
- Use the project runtime environment (.venv) for deterministic checks
- Inspect live API health / trading diagnostics / risk state
- Scan recent logs for critical signals
- Optionally run focused regression tests
- Never place real orders

Usage:
  .venv/bin/python scripts/full_system_audit.py
  .venv/bin/python scripts/full_system_audit.py --base-url http://127.0.0.1:8000
  .venv/bin/python scripts/full_system_audit.py --skip-tests
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.utils.openclaw_api_client import default_openclaw_api_base


TEST_TARGETS: Sequence[str] = (
    "tests/unit/test_decision_engine.py",
    "tests/unit/test_enhanced_llm_manager_resilience.py",
    "tests/unit/test_okx_exchange_resilience.py",
    "tests/unit/test_execution_gateway.py",
    "tests/unit/test_ai_core_execution_guards.py",
    "tests/unit/test_trading_contract_settings.py",
    "tests/unit/test_stop_loss_exchange_sync.py",
    "tests/unit/test_execution_verifier_close_audit.py",
    "tests/test_ai_trading_engine.py",
)


@dataclass
class Check:
    name: str
    ok: bool
    severity: str
    detail: str
    data: Optional[Dict[str, Any]] = None


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def http_json(url: str, timeout: float = 20.0) -> Tuple[bool, Dict[str, Any]]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            return True, json.loads(raw)
        except Exception:
            return False, {"error": "json_decode_failed", "raw": raw[:4000]}
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = str(e)
        return False, {"error": f"http_{e.code}", "raw": raw[:4000]}
    except Exception as e:
        return False, {"error": f"{type(e).__name__}: {e}"}


def add(out: List[Check], name: str, ok: bool, severity: str, detail: str, data: Optional[Dict[str, Any]] = None) -> None:
    out.append(Check(name=name, ok=bool(ok), severity=severity, detail=detail, data=data))


def _parse_iso8601(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _is_expected_order_rejection(event: Dict[str, Any]) -> bool:
    code = str(event.get("error_code") or "").strip().upper()
    detail = str(event.get("detail") or "")
    if code in {"POLICY_DENIED", "HOSTING_MODE_DENIED"}:
        return True
    expected_markers = (
        "policy_denied",
        "open_policy_denied",
        "托管模式拦截",
        "分层开仓拦截",
        "置信度",
        "执行建议等待",
    )
    return any(marker in detail for marker in expected_markers)


def _resolve_last_order_state(exec_gw: Dict[str, Any]) -> Tuple[Optional[bool], Optional[str], str]:
    last_order_success = exec_gw.get("last_order_success")
    last_order_at = exec_gw.get("last_order_at")
    snapshot_dt = _parse_iso8601(last_order_at)
    newest_event_dt: Optional[datetime] = None
    newest_event_success: Optional[bool] = None
    newest_event_at: Optional[str] = None

    for event in exec_gw.get("recent_events") or []:
        if not isinstance(event, dict):
            continue
        if event.get("success") is False and _is_expected_order_rejection(event):
            continue
        event_dt = _parse_iso8601(event.get("ts"))
        if event_dt is None:
            continue
        if newest_event_dt is None or event_dt > newest_event_dt:
            newest_event_dt = event_dt
            newest_event_success = event.get("success")
            newest_event_at = event.get("ts")

    if newest_event_dt is not None and (snapshot_dt is None or newest_event_dt >= snapshot_dt):
        return (None if newest_event_success is None else bool(newest_event_success), newest_event_at, "recent_event")
    return (None if last_order_success is None else bool(last_order_success), last_order_at, "snapshot")


def latest_file(directory: Path, pattern: str) -> Optional[Path]:
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def load_latest_monitor_summary() -> Dict[str, Any]:
    path = latest_file(REPO / "runtime", "live_stability_monitor.*.summary.json")
    if not path or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def summarize_log_window(log_path: Path, tail_lines: int = 2000) -> Dict[str, Any]:
    if not log_path.exists():
        return {"exists": False}
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-tail_lines:]
    counters = {
        "errors": 0,
        "exceptions": 0,
        "tracebacks": 0,
        "circuit_breaks": 0,
        "disconnects": 0,
        "fallbacks": 0,
        "okx_session_rebuilt": 0,
    }
    samples: List[str] = []
    for line in lines:
        low = line.lower()
        if " error " in low or low.endswith(" error") or " - error -" in low:
            counters["errors"] += 1
        if "exception" in low:
            counters["exceptions"] += 1
        if "traceback" in low:
            counters["tracebacks"] += 1
        if "circuit-break" in low:
            counters["circuit_breaks"] += 1
        if "server disconnected" in low or "remoteprotocolerror" in low or "incomplete chunked read" in low:
            counters["disconnects"] += 1
        if "尝试回退模型" in line:
            counters["fallbacks"] += 1
        if "okx会话已重建" in line:
            counters["okx_session_rebuilt"] += 1
        if len(samples) < 8 and (
            "error" in low
            or "exception" in low
            or "traceback" in low
            or "circuit-break" in low
            or "尝试回退模型" in line
            or "okx会话已重建" in line
        ):
            samples.append(line)
    counters["exists"] = True
    counters["tail_lines"] = tail_lines
    counters["samples"] = samples
    return counters


def disk_memory_snapshot() -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    total, used, free = shutil.disk_usage(REPO)
    data["disk_repo_total_gb"] = round(total / (1024**3), 2)
    data["disk_repo_used_gb"] = round(used / (1024**3), 2)
    data["disk_repo_free_gb"] = round(free / (1024**3), 2)
    data["disk_repo_used_pct"] = round((used / total) * 100, 2) if total else None
    if Path("/proc/meminfo").exists():
        meminfo: Dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            try:
                meminfo[k.strip()] = int(v.strip().split()[0])
            except Exception:
                continue
        total_kb = meminfo.get("MemTotal", 0)
        avail_kb = meminfo.get("MemAvailable", 0)
        swap_total_kb = meminfo.get("SwapTotal", 0)
        swap_free_kb = meminfo.get("SwapFree", 0)
        data["mem_total_gb"] = round(total_kb / (1024**2), 2) if total_kb else None
        data["mem_available_gb"] = round(avail_kb / (1024**2), 2) if avail_kb else None
        data["mem_available_pct"] = round((avail_kb / total_kb) * 100, 2) if total_kb else None
        data["swap_total_gb"] = round(swap_total_kb / (1024**2), 2) if swap_total_kb else None
        data["swap_used_gb"] = round((swap_total_kb - swap_free_kb) / (1024**2), 2) if swap_total_kb else 0.0
    return data


def run_tests(venv_python: Path, timeout_sec: int) -> Dict[str, Any]:
    cmd = [str(venv_python), "-m", "pytest", "-q", *TEST_TARGETS]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
        return {
            "returncode": proc.returncode,
            "stdout_tail": "\n".join(proc.stdout.splitlines()[-30:]),
            "stderr_tail": "\n".join(proc.stderr.splitlines()[-30:]),
            "cmd": cmd,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "returncode": None,
            "error": f"timeout_after_{timeout_sec}s",
            "stdout_tail": "\n".join((e.stdout or "").splitlines()[-30:]),
            "stderr_tail": "\n".join((e.stderr or "").splitlines()[-30:]),
            "cmd": cmd,
        }
    except OSError as e:
        return {
            "returncode": None,
            "error": f"{type(e).__name__}: {e}",
            "stdout_tail": "",
            "stderr_tail": "",
            "cmd": cmd,
        }


def run_trading_model_checks(venv_python: Path, timeout_sec: float) -> Dict[str, Any]:
    script = REPO / "scripts" / "validate_trading_model_aliases.py"
    python_bin = venv_python if venv_python.exists() else Path(sys.executable)
    cmd = [str(python_bin), str(script), "--output-json", "--timeout", str(timeout_sec)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            text=True,
            capture_output=True,
            timeout=max(int(timeout_sec * 4), 60),
            check=False,
        )
        parsed: Dict[str, Any] | None = None
        if proc.stdout.strip():
            try:
                maybe = json.loads(proc.stdout)
                if isinstance(maybe, dict):
                    parsed = maybe
            except Exception:
                parsed = None
        return {
            "returncode": proc.returncode,
            "stdout_tail": "\n".join(proc.stdout.splitlines()[-60:]),
            "stderr_tail": "\n".join(proc.stderr.splitlines()[-30:]),
            "report": parsed,
            "cmd": cmd,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "returncode": None,
            "error": f"timeout_after_{max(int(timeout_sec * 4), 60)}s",
            "stdout_tail": "\n".join((e.stdout or "").splitlines()[-60:]),
            "stderr_tail": "\n".join((e.stderr or "").splitlines()[-30:]),
            "cmd": cmd,
        }
    except OSError as e:
        return {
            "returncode": None,
            "error": f"{type(e).__name__}: {e}",
            "stdout_tail": "",
            "stderr_tail": "",
            "cmd": cmd,
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("OPENCLAW_API_BASE") or os.environ.get("BASE_URL") or "")
    ap.add_argument("--timeout-sec", type=float, default=20.0)
    ap.add_argument("--diag-timeout-sec", type=float, default=30.0)
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--skip-trading-models", action="store_true")
    ap.add_argument("--test-timeout-sec", type=int, default=900)
    ap.add_argument("--log-tail-lines", type=int, default=2000)
    args = ap.parse_args()

    base = str(args.base_url or "").strip().rstrip("/") or default_openclaw_api_base()
    venv_python = REPO / ".venv" / "bin" / "python"
    checks: List[Check] = []

    print(f"[{now()}] full_system_audit base={base}")
    add(checks, "venv_python", venv_python.exists(), "P0", str(venv_python))

    # API health
    ok, health = http_json(f"{base}/api/v1/system/health", timeout=args.timeout_sec)
    if not ok:
        add(checks, "system_health", False, "P0", f"unreachable: {health.get('error')}", health)
    else:
        data = health.get("data") if isinstance(health.get("data"), dict) else {}
        status = str(data.get("status") or "unknown").lower()
        reach = data.get("exchange_reachability") if isinstance(data.get("exchange_reachability"), dict) else {}
        reach_status = str(reach.get("status") or "unknown").lower()
        add(checks, "system_health", status == "healthy", "P1" if status != "healthy" else "P3", f"status={status}", {"exchange_reachability": reach_status})
        add(
            checks,
            "exchange_reachability",
            reach_status in {"reachable", "degraded"},
            "P1" if reach_status not in {"reachable", "degraded"} else "P3",
            f"status={reach_status}",
            reach,
        )

    # deeper diagnostics
    diag_ok, diag = http_json(
        f"{base}/api/v1/modules/commander/trading-diagnosis?limit_events=20&timeout_sec={args.diag_timeout_sec}",
        timeout=max(args.diag_timeout_sec + 5.0, args.timeout_sec),
    )
    if not diag_ok or not bool(diag.get("success")):
        add(checks, "trading_diagnosis", False, "P1", f"failed: {diag.get('error') or diag.get('message')}", diag)
    else:
        data = diag.get("data") if isinstance(diag.get("data"), dict) else {}
        issues = data.get("issues")
        warnings = data.get("warnings")
        exec_gw = data.get("execution_gateway") if isinstance(data.get("execution_gateway"), dict) else {}
        add(checks, "trading_diagnosis", True, "P3", "responsive")
        add(checks, "trading_issues", not bool(issues), "P1" if issues else "P3", f"issues={0 if not issues else len(issues)}")
        add(checks, "trading_warnings", not bool(warnings), "P2" if warnings else "P3", f"warnings={0 if not warnings else len(warnings)}")
        add(checks, "exchange_connected", bool(exec_gw.get("exchange_connected")), "P1", f"exchange_connected={bool(exec_gw.get('exchange_connected'))}")
        last_order_success, last_order_at, last_order_source = _resolve_last_order_state(exec_gw)
        if last_order_success is None:
            add(
                checks,
                "last_order_success",
                True,
                "P3",
                "last_order_success=unobserved",
                {"last_order_at": last_order_at, "source": last_order_source},
            )
        else:
            add(
                checks,
                "last_order_success",
                bool(last_order_success),
                "P2",
                f"last_order_success={bool(last_order_success)}",
                {"last_order_at": last_order_at, "source": last_order_source},
            )

    # module audit / risk / account / data hub
    for name, path, severity, evaluator in (
        ("module_health", "/api/v1/modules/system/health", "P1", lambda p: str(p.get("overall") or "").lower() == "healthy"),
        ("risk_status", "/api/v1/modules/risk/status", "P1", lambda p: str((p.get("circuit_breaker") or {}).get("status") or "").lower() == "closed"),
        ("account_diagnostics", "/api/v1/modules/commander/account-diagnostics", "P1", lambda p: (p.get("data") or {}).get("balance_error") is None and (p.get("data") or {}).get("positions_error") is None),
        ("data_hub_status", "/api/v1/data-hub/status", "P1", lambda p: bool(((p.get("data") or {}).get("健康")))),
        ("commander_audit", "/api/v1/modules/commander/audit", "P1", lambda p: bool(p.get("all_passed"))),
        ("s1_verify", "/api/v1/s1/verify", "P1", lambda p: bool(p.get("all_passed"))),
    ):
        ok, payload = http_json(f"{base}{path}", timeout=args.timeout_sec)
        if not ok:
            add(checks, name, False, severity, f"unreachable: {payload.get('error')}", payload)
            continue
        try:
            passed = bool(evaluator(payload))
        except Exception as e:
            passed = False
            payload = {"error": f"evaluator_failed: {type(e).__name__}: {e}", "payload": payload}
        add(checks, name, passed, severity if not passed else "P3", "passed" if passed else "failed", payload if not passed else None)

    # host resources
    host = disk_memory_snapshot()
    disk_ok = float(host.get("disk_repo_used_pct") or 0.0) < 90.0
    mem_ok = host.get("mem_available_pct") is None or float(host.get("mem_available_pct") or 0.0) >= 10.0
    swap_ok = host.get("swap_total_gb") in (None, 0.0) or float(host.get("swap_used_gb") or 0.0) < float(host.get("swap_total_gb") or 0.0) * 0.7
    add(checks, "disk_headroom", disk_ok, "P1" if not disk_ok else "P3", f"used_pct={host.get('disk_repo_used_pct')}", host)
    add(checks, "memory_headroom", mem_ok, "P1" if not mem_ok else "P3", f"available_pct={host.get('mem_available_pct')}", host)
    add(checks, "swap_pressure", swap_ok, "P2" if not swap_ok else "P3", f"swap_used_gb={host.get('swap_used_gb')}", host)

    # log scan
    monitor_summary = load_latest_monitor_summary()
    disconnect_growth = int(monitor_summary.get("disconnect_growth", 0) or 0)
    circuit_break_growth = int(monitor_summary.get("circuit_break_growth", 0) or 0)
    log_summary = summarize_log_window(REPO / "logs" / "app.log", tail_lines=args.log_tail_lines)
    add(checks, "app_log_exists", bool(log_summary.get("exists")), "P1", "logs/app.log present" if log_summary.get("exists") else "logs/app.log missing")
    if log_summary.get("exists"):
        add(
            checks,
            "recent_tracebacks",
            int(log_summary.get("tracebacks", 0)) == 0,
            "P1" if int(log_summary.get("tracebacks", 0)) > 0 else "P3",
            f"tracebacks={log_summary.get('tracebacks')}",
            log_summary if int(log_summary.get("tracebacks", 0)) > 0 else None,
        )
        add(
            checks,
            "recent_disconnects",
            int(log_summary.get("disconnects", 0)) < 10 or disconnect_growth == 0,
            "P2" if int(log_summary.get("disconnects", 0)) >= 10 and disconnect_growth > 0 else "P3",
            (
                f"disconnects={log_summary.get('disconnects')}"
                if int(log_summary.get("disconnects", 0)) < 10 or disconnect_growth > 0
                else f"disconnects={log_summary.get('disconnects')} stabilized"
            ),
            (
                {**log_summary, "monitor_disconnect_growth": disconnect_growth}
                if int(log_summary.get("disconnects", 0)) >= 10 and disconnect_growth > 0
                else None
            ),
        )
        add(
            checks,
            "recent_circuit_breaks",
            int(log_summary.get("circuit_breaks", 0)) < 10 or circuit_break_growth == 0,
            "P2" if int(log_summary.get("circuit_breaks", 0)) >= 10 and circuit_break_growth > 0 else "P3",
            (
                f"circuit_breaks={log_summary.get('circuit_breaks')}"
                if int(log_summary.get("circuit_breaks", 0)) < 10 or circuit_break_growth > 0
                else f"circuit_breaks={log_summary.get('circuit_breaks')} stabilized"
            ),
            (
                {**log_summary, "monitor_circuit_break_growth": circuit_break_growth}
                if int(log_summary.get("circuit_breaks", 0)) >= 10 and circuit_break_growth > 0
                else None
            ),
        )

    # CLIProxyAPI trading alias contract
    if args.skip_trading_models:
        add(checks, "trading_model_aliases", True, "P3", "skipped by flag")
        trading_model_result = None
    else:
        trading_model_result = run_trading_model_checks(venv_python, timeout_sec=args.timeout_sec)
        trading_model_rc = trading_model_result.get("returncode")
        trading_model_ok = isinstance(trading_model_rc, int) and trading_model_rc == 0
        report = trading_model_result.get("report")
        detail = (
            f"returncode={trading_model_rc}"
            if trading_model_result.get("error") is None
            else str(trading_model_result.get("error"))
        )
        if isinstance(report, dict):
            failed = [
                item.get("name")
                for item in (report.get("checks") or [])
                if isinstance(item, dict) and not bool(item.get("ok"))
            ]
            if failed:
                detail = f"failed_checks={failed}"
            elif trading_model_ok:
                detail = "alias contract verified"
        add(
            checks,
            "trading_model_aliases",
            trading_model_ok,
            "P1" if not trading_model_ok else "P3",
            detail,
            trading_model_result if not trading_model_ok else report,
        )

    # focused tests
    if args.skip_tests:
        add(checks, "focused_pytest", True, "P3", "skipped by flag")
        test_result = None
    elif not venv_python.exists():
        test_result = {
            "returncode": None,
            "error": f"missing_python: {venv_python}",
            "cmd": [str(venv_python), "-m", "pytest", "-q", *TEST_TARGETS],
        }
        add(checks, "focused_pytest", False, "P0", "skipped: venv python missing", test_result)
    else:
        test_result = run_tests(venv_python, timeout_sec=args.test_timeout_sec)
        test_returncode = test_result.get("returncode")
        test_ok = isinstance(test_returncode, int) and test_returncode == 0
        add(
            checks,
            "focused_pytest",
            test_ok,
            "P1" if not test_ok else "P3",
            (
                f"returncode={test_returncode}"
                if test_result.get("error") is None
                else str(test_result.get("error"))
            ),
            test_result if not test_ok else None,
        )

    p0 = [c for c in checks if not c.ok and c.severity == "P0"]
    p1 = [c for c in checks if not c.ok and c.severity == "P1"]
    p2 = [c for c in checks if not c.ok and c.severity == "P2"]
    verdict = "PASS"
    if p0:
        verdict = "FAIL"
    elif p1:
        verdict = "ATTENTION"
    elif p2:
        verdict = "WARN"

    print("\n== verdict ==")
    print(verdict)
    print("\n== checks ==")
    for c in checks:
        flag = "OK" if c.ok else "BAD"
        print(f"- [{flag}] {c.name} ({c.severity}): {c.detail}")

    if p0 or p1 or p2:
        print("\n== findings ==")
        for c in [*p0, *p1, *p2][:10]:
            extra = ""
            if c.data:
                if "samples" in c.data:
                    extra = f" samples={len(c.data.get('samples') or [])}"
                elif "error" in c.data:
                    extra = f" error={c.data.get('error')}"
            print(f"- {c.name}: {c.detail}{extra}")

    if test_result and not (isinstance(test_result.get("returncode"), int) and int(test_result.get("returncode")) == 0):
        print("\n== pytest stdout tail ==")
        print(test_result.get("stdout_tail") or "")
        if test_result.get("stderr_tail"):
            print("\n== pytest stderr tail ==")
            print(test_result.get("stderr_tail") or "")

    return 0 if verdict == "PASS" else (2 if verdict in {"WARN", "ATTENTION"} else 5)


if __name__ == "__main__":
    raise SystemExit(main())
