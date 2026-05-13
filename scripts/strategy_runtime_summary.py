#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str, timeout: float = 8.0) -> Dict[str, Any]:
    try:
        with urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"raw": data}
    except HTTPError as e:
        return {"error": f"http_error:{e.code}"}
    except URLError as e:
        return {"error": f"url_error:{e.reason}"}
    except Exception as e:
        return {"error": f"error:{type(e).__name__}:{e}"}


def read_journal(service: str, since: str) -> str:
    cmd = ["journalctl", "-u", service, "--since", since, "--no-pager"]
    try:
        return subprocess.check_output(cmd, text=True, errors="replace")
    except subprocess.CalledProcessError as e:
        return e.output or ""


def classify_hold_reason(
    reasoning: str,
    tags: Dict[str, Any],
    upstream: str,
    sr_snapshot: Dict[str, Any],
) -> List[str]:
    txt = str(reasoning or "")
    low = txt.lower()
    out: List[str] = []
    if "llm_unavailable_fallback_hold" in low:
        out.append("llm_fallback_hold")
    if (
        "sr入场" in txt
        or "sr条件" in txt
        or "sr确认" in txt
        or "near_support" in low
        or "near_resistance" in low
        or "breakout" in low
        or "breakdown" in low
    ):
        out.append("sr_confirmation_missing")
    near_support = bool(sr_snapshot.get("near_support", False))
    near_resistance = bool(sr_snapshot.get("near_resistance", False))
    breakout_up = bool(sr_snapshot.get("breakout_up_confirmed", False))
    breakdown_down = bool(sr_snapshot.get("breakdown_down_confirmed", False))
    weak_long = bool(sr_snapshot.get("scanner_weak_long_trigger", False))
    weak_short = bool(sr_snapshot.get("scanner_weak_short_trigger", False))
    if tags.get("no_sr_entry_trigger") or not any(
        (near_support, near_resistance, breakout_up, breakdown_down, weak_long, weak_short)
    ):
        out.append("no_sr_entry_trigger")
    if weak_long or weak_short:
        out.append("scanner_weak_sr_present")
    if "long" in low or "做多" in txt or "buy" in low:
        if not near_support:
            out.append("long_missing_near_support")
        if not breakout_up:
            out.append("long_missing_breakout")
    if "short" in low or "做空" in txt or "sell" in low:
        if not near_resistance:
            out.append("short_missing_near_resistance")
        if not breakdown_down:
            out.append("short_missing_breakdown")
    if tags.get("mtf_conflict") or "多周期" in txt or "周期冲突" in txt:
        out.append("mtf_conflict")
    if tags.get("evidence_incomplete") or "证据不足" in txt or "缺乏明确入场" in txt:
        out.append("evidence_incomplete")
    if tags.get("neutral_market") or "neutral" in low or "中性" in txt or "观望" in txt:
        out.append("neutral_market")
    if tags.get("low_confidence") or "信心不足" in txt or "置信度" in txt:
        out.append("low_confidence")
    if upstream and ("扫描" in txt or "scanner" in low):
        out.append("scanner_conflict")
    if not out:
        out.append("uncategorized_hold")
    return out


def journal_counts(text: str) -> Dict[str, Any]:
    patterns = {
        "scanner_batches": r"发现 \d+ 个交易机会",
        "scanner_hint_ingested": r"已接收扫描机会提示:",
        "ai_analyze_started": r"🧠 AI分析 ",
        "ai_done_hold": r"✅ AI决策完成: .* hold",
        "ai_fallback_no_decision": r"AI未返回决策，启用规则兜底:",
        "llm_circuit_break": r"LLM circuit-break:",
        "open_ok": r"ExecutionGateway: open_swap ok",
        "close_ok": r"ExecutionGateway: close_swap ok",
        "exec_gate_reject": r"执行门控拒绝:",
        "scanner_precheck_reject": r"实时数据预检未通过",
        "evidence_downgraded": r"开仓证据降级放行",
    }
    out: Dict[str, Any] = {k: len(re.findall(p, text)) for k, p in patterns.items()}
    hint_rows = re.findall(r"已接收扫描机会提示: ([A-Z0-9/]+) ([a-z_]+)", text)
    analyze_rows = re.findall(r"🧠 AI分析 ([A-Z0-9/]+)\.\.\.", text)
    fallback_rows = re.findall(r"AI未返回决策，启用规则兜底: ([A-Z0-9/]+)", text)
    hold_rows = re.findall(r"AI决策完成: ([A-Z0-9/]+) hold", text)
    llm_break_rows = re.findall(
        r"LLM circuit-break: mark ([^ ]+) unhealthy \d+s reason=([A-Z_]+)",
        text,
    )
    out["scanner_hint_symbols"] = Counter(sym for sym, _ in hint_rows).most_common(10)
    out["scanner_hint_types"] = Counter(kind for _, kind in hint_rows).most_common(10)
    out["ai_analyze_symbols"] = Counter(analyze_rows).most_common(10)
    out["ai_fallback_symbols"] = Counter(fallback_rows).most_common(10)
    out["ai_hold_symbols"] = Counter(hold_rows).most_common(10)
    out["llm_break_models"] = Counter(model for model, _ in llm_break_rows).most_common(10)
    out["llm_break_reasons"] = Counter(reason for _, reason in llm_break_rows).most_common(10)
    return out


def summarize_traces(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    source_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    guard_reason_counts: Counter[str] = Counter()
    hold_tag_counts: Counter[str] = Counter()
    hold_reason_class_counts: Counter[str] = Counter()
    sr_subreason_counts: Counter[str] = Counter()
    upstream_types: Counter[str] = Counter()
    weak_sr_reason_counts: Counter[str] = Counter()
    weak_sr_direction_counts: Counter[str] = Counter()
    weak_sr_eligible_count = 0
    linked = 0

    for row in rows:
        if not isinstance(row, dict):
            continue
        source_counts[str(row.get("source") or "unknown")] += 1
        symbol_counts[str(row.get("symbol") or "unknown")] += 1
        guard = row.get("guard") if isinstance(row.get("guard"), dict) else {}
        reason = str(guard.get("reason") or "")
        if reason:
            guard_reason_counts[reason] += 1
        extras = guard.get("extras") if isinstance(guard.get("extras"), dict) else {}
        tags = extras.get("hold_reason_tags") if isinstance(extras.get("hold_reason_tags"), dict) else {}
        sr_snapshot = extras.get("sr_snapshot") if isinstance(extras.get("sr_snapshot"), dict) else {}
        weak_reason = str(sr_snapshot.get("scanner_weak_reason") or "")
        weak_long = bool(sr_snapshot.get("scanner_weak_long_trigger", False))
        weak_short = bool(sr_snapshot.get("scanner_weak_short_trigger", False))
        if weak_reason:
            weak_sr_reason_counts[weak_reason] += 1
        if weak_long:
            weak_sr_direction_counts["long"] += 1
            weak_sr_eligible_count += 1
        if weak_short:
            weak_sr_direction_counts["short"] += 1
            weak_sr_eligible_count += 1
        for key, value in tags.items():
            if value:
                hold_tag_counts[str(key)] += 1
        upstream = str(extras.get("upstream_scanner_opportunity_type") or "")
        if upstream:
            upstream_types[upstream] += 1
        if extras.get("upstream_scanner_trace_id"):
            linked += 1
        if reason == "hold_by_ai_decision":
            intent = row.get("intent") if isinstance(row.get("intent"), dict) else {}
            reasoning = str(intent.get("reasoning") or "")
            for cls in classify_hold_reason(reasoning, tags, upstream, sr_snapshot):
                hold_reason_class_counts[cls] += 1
                if cls in {
                    "no_sr_entry_trigger",
                    "long_missing_near_support",
                    "long_missing_breakout",
                    "short_missing_near_resistance",
                    "short_missing_breakdown",
                }:
                    sr_subreason_counts[cls] += 1

    return {
        "trace_count": len(rows),
        "source_counts": source_counts.most_common(),
        "symbol_counts": symbol_counts.most_common(10),
        "guard_reason_counts": guard_reason_counts.most_common(12),
        "hold_tag_counts": hold_tag_counts.most_common(12),
        "hold_reason_class_counts": hold_reason_class_counts.most_common(12),
        "sr_subreason_counts": sr_subreason_counts.most_common(12),
        "upstream_scanner_types": upstream_types.most_common(10),
        "weak_sr_reason_counts": weak_sr_reason_counts.most_common(12),
        "weak_sr_direction_counts": weak_sr_direction_counts.most_common(4),
        "weak_sr_eligible_count": weak_sr_eligible_count,
        "linked_upstream_scanner_traces": linked,
    }


def build_report(base_url: str, service: str, since: str, trace_path: Path, trace_limit: int) -> Dict[str, Any]:
    journal = read_journal(service, since)
    api_data = fetch_json(f"{base_url}/api/v1/modules/commander/decision-traces?limit={trace_limit}", timeout=10.0)
    api_recent: List[Dict[str, Any]] = []
    if isinstance(api_data.get("data"), dict):
        recent = api_data.get("data", {}).get("recent")
        if isinstance(recent, list):
            api_recent = [r for r in recent if isinstance(r, dict)]
    trace_rows: List[Dict[str, Any]] = []
    if trace_path.is_file():
        try:
            loaded = json.loads(trace_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                trace_rows = [r for r in loaded if isinstance(r, dict)][-trace_limit:]
        except Exception:
            trace_rows = []
    summary_rows = api_recent or trace_rows

    return {
        "ts": now_utc(),
        "service": service,
        "since": since,
        "base_url": base_url,
        "journal": journal_counts(journal),
        "decision_trace_api": api_data.get("data", api_data),
        "decision_trace_source": "api_recent" if api_recent else "local_store",
        "decision_trace_store": summarize_traces(summary_rows),
    }


def print_summary(report: Dict[str, Any]) -> None:
    journal = report.get("journal", {})
    store = report.get("decision_trace_store", {})
    api = report.get("decision_trace_api", {})
    summary = api.get("summary", {}) if isinstance(api, dict) else {}
    top_guards = api.get("top_guard_reasons", []) if isinstance(api, dict) else []

    line = (
        f"[{report.get('ts')}] "
        f"scanner_batches={journal.get('scanner_batches', 0)} "
        f"hints={journal.get('scanner_hint_ingested', 0)} "
        f"analyze={journal.get('ai_analyze_started', 0)} "
        f"holds={journal.get('ai_done_hold', 0)} "
        f"fallbacks={journal.get('ai_fallback_no_decision', 0)} "
        f"llm_breaks={journal.get('llm_circuit_break', 0)} "
        f"open_ok={journal.get('open_ok', 0)} close_ok={journal.get('close_ok', 0)} "
        f"trace_rejected={summary.get('guard_rejected', '?')} trace_passed={summary.get('guard_passed', '?')} "
        f"linked_scanner={store.get('linked_upstream_scanner_traces', 0)} "
        f"trace_src={report.get('decision_trace_source', 'unknown')} "
        f"weak_sr_ok={store.get('weak_sr_eligible_count', 0)}"
    )
    print(line)
    if top_guards:
        print("top_guard_reasons:", json.dumps(top_guards[:6], ensure_ascii=False))
    if journal.get("scanner_hint_symbols"):
        print("scanner_hint_symbols:", json.dumps(journal["scanner_hint_symbols"], ensure_ascii=False))
    if journal.get("llm_break_models"):
        print("llm_break_models:", json.dumps(journal["llm_break_models"][:6], ensure_ascii=False))
    if journal.get("llm_break_reasons"):
        print("llm_break_reasons:", json.dumps(journal["llm_break_reasons"][:6], ensure_ascii=False))
    if store.get("hold_tag_counts"):
        print("hold_tag_counts:", json.dumps(store["hold_tag_counts"][:6], ensure_ascii=False))
    if store.get("hold_reason_class_counts"):
        print("hold_reason_classes:", json.dumps(store["hold_reason_class_counts"][:6], ensure_ascii=False))
    if store.get("sr_subreason_counts"):
        print("sr_subreasons:", json.dumps(store["sr_subreason_counts"][:6], ensure_ascii=False))
    if store.get("weak_sr_direction_counts"):
        print("weak_sr_directions:", json.dumps(store["weak_sr_direction_counts"][:4], ensure_ascii=False))
    if store.get("weak_sr_reason_counts"):
        print("weak_sr_reasons:", json.dumps(store["weak_sr_reason_counts"][:8], ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize runtime strategy behavior from journal + decision traces")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--service", default="openclaw-trading.service")
    parser.add_argument("--since", default="30 minutes ago")
    parser.add_argument(
        "--trace-path",
        default="/home/cool/ai-trading-system/data/runtime/decision_trace_store.json",
    )
    parser.add_argument("--trace-limit", type=int, default=120)
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    report = build_report(
        base_url=args.base_url,
        service=args.service,
        since=args.since,
        trace_path=Path(args.trace_path),
        trace_limit=max(20, int(args.trace_limit)),
    )
    print_summary(report)
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
