#!/usr/bin/env python3
"""
Continuous runtime probe for trading full-chain health.

Chain covered:
1) data collection quality
2) analysis pipeline health
3) intelligent open/close decision path
4) SLTP tracking/monitoring
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _http_json(url: str, timeout: float = 20.0) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


@dataclass
class RoundRow:
    ts: str
    ok: bool
    latency_ms: int
    degraded_ratio: float
    quality_coverage: float
    sample_count: int
    ai_core_running: bool
    ai_trading_running: bool
    ai_trading_positions: int
    sltp_active_orders: int
    sltp_dynamic_adjustments: int
    reconciliation_healthy: bool
    reconciliation_drift_total: int
    reconciliation_stale_open_orders: int
    alerts: List[str]


def _extract_row(diag: Dict[str, Any], latency_ms: int, prev: Dict[str, Any] | None) -> RoundRow:
    data = (diag.get("data") or {}) if isinstance(diag, dict) else {}
    assess = (data.get("analysis_pipeline_assessment") or {}) if isinstance(data, dict) else {}
    ma = (assess.get("market_analysis") or {}) if isinstance(assess, dict) else {}
    ai_core = (data.get("ai_core") or {}) if isinstance(data, dict) else {}
    ai_engine = (data.get("ai_trading_engine") or {}) if isinstance(data, dict) else {}
    sltp = (data.get("sltp") or {}) if isinstance(data, dict) else {}
    rec = (data.get("execution_reconciliation") or {}) if isinstance(data, dict) else {}
    rec_sum = (rec.get("summary") or {}) if isinstance(rec, dict) else {}

    guards = (ai_core.get("execution_guards") or {}) if isinstance(ai_core, dict) else {}
    gstats = (guards.get("stats") or {}) if isinstance(guards, dict) else {}

    sltp_dyn = _to_int(sltp.get("dynamic_adjustments"))
    rr_rej = _to_int(gstats.get("rr_rejected"))
    sp_rej = _to_int(gstats.get("spread_rejected"))
    dq_hold = _to_int(gstats.get("data_quality_guard_hold"))

    alerts: List[str] = []
    err_text = str(diag.get("error") or "")
    warmup = bool(diag.get("warmup"))
    if not bool(diag.get("success")):
        # Startup windows right after service restart should not be treated as hard failures.
        if warmup:
            alerts.append("diagnosis_warming_up")
        else:
            alerts.append("diagnosis_failed")
    if _to_float(ma.get("degraded_ratio")) > 0.35:
        alerts.append("degraded_ratio_high")
    if not bool(ai_core.get("running")):
        alerts.append("ai_core_not_running")
    if not bool(ai_engine.get("running")):
        alerts.append("ai_trading_not_running")
    if not bool(rec.get("healthy", True)):
        alerts.append("reconciliation_unhealthy")
    if _to_int(rec_sum.get("drift_total")) > 0:
        alerts.append("reconciliation_drift_present")
    if _to_int(ai_engine.get("positions")) > 0 and _to_int(sltp.get("active_orders")) <= 0:
        alerts.append("positions_without_sltp_tracking")

    if prev:
        if rr_rej - _to_int(prev.get("rr_rej")) >= 2:
            alerts.append("rr_rejected_spike")
        if sp_rej - _to_int(prev.get("sp_rej")) >= 2:
            alerts.append("spread_rejected_spike")
        if dq_hold - _to_int(prev.get("dq_hold")) >= 2:
            alerts.append("data_quality_hold_spike")
        if sltp_dyn - _to_int(prev.get("sltp_dyn")) >= 60:
            alerts.append("sltp_adjustments_spike")

    return RoundRow(
        ts=datetime.now().isoformat(),
        ok=bool(diag.get("success")),
        latency_ms=latency_ms,
        degraded_ratio=_to_float(ma.get("degraded_ratio")),
        quality_coverage=_to_float(ma.get("quality_coverage")),
        sample_count=len(ma.get("samples") or []) if isinstance(ma.get("samples"), list) else 0,
        ai_core_running=bool(ai_core.get("running")),
        ai_trading_running=bool(ai_engine.get("running")),
        ai_trading_positions=_to_int(ai_engine.get("positions")),
        sltp_active_orders=_to_int(sltp.get("active_orders")),
        sltp_dynamic_adjustments=sltp_dyn,
        reconciliation_healthy=bool(rec.get("healthy", False)),
        reconciliation_drift_total=_to_int(rec_sum.get("drift_total")),
        reconciliation_stale_open_orders=_to_int(rec_sum.get("stale_open_orders")),
        alerts=alerts,
    )


def _write_summary(rows: List[RoundRow], out_md: Path, duration_sec: int, interval_sec: int) -> None:
    total = len(rows)
    ok_count = sum(1 for r in rows if r.ok)
    alert_rounds = sum(1 for r in rows if r.alerts)
    warmup_rounds = sum(1 for r in rows if "diagnosis_warming_up" in (r.alerts or []))
    degraded_bad = sum(1 for r in rows if r.degraded_ratio > 0.35)
    rec_bad = sum(1 for r in rows if not r.reconciliation_healthy)
    ai_down = sum(1 for r in rows if (not r.ai_core_running) or (not r.ai_trading_running))
    avg_latency = int(sum(r.latency_ms for r in rows) / max(1, total))
    max_latency = max((r.latency_ms for r in rows), default=0)
    max_sltp_dyn = max((r.sltp_dynamic_adjustments for r in rows), default=0)
    max_positions = max((r.ai_trading_positions for r in rows), default=0)
    max_drift = max((r.reconciliation_drift_total for r in rows), default=0)

    alert_counter: Dict[str, int] = {}
    for r in rows:
        for a in r.alerts:
            alert_counter[a] = alert_counter.get(a, 0) + 1
    top_alerts = sorted(alert_counter.items(), key=lambda x: x[1], reverse=True)[:8]

    verdict = "整体正常"
    if ai_down > 0 or rec_bad > 0:
        verdict = "存在关键异常"
    elif degraded_bad > max(1, total // 4):
        verdict = "数据链路波动偏高"
    elif alert_rounds > max(2, total // 3):
        verdict = "存在轻中度波动"

    lines = [
        "# 全链路实时巡检报告",
        "",
        f"- 采样窗口: {duration_sec}s（间隔 {interval_sec}s）",
        f"- 总采样点: {total}",
        f"- 诊断成功率: {ok_count}/{total} ({(ok_count/max(1,total))*100:.1f}%)",
        f"- 预热窗口轮次: {warmup_rounds}",
        f"- 结论: **{verdict}**",
        "",
        "## 核心健康指标",
        f"- 诊断接口延迟: 平均 {avg_latency}ms, 峰值 {max_latency}ms",
        f"- 数据退化比例>0.35 轮次: {degraded_bad}",
        f"- 对账异常轮次: {rec_bad}",
        f"- AI主链路非运行轮次: {ai_down}",
        f"- 持仓峰值: {max_positions}",
        f"- 对账漂移峰值: {max_drift}",
        f"- SLTP动态调整峰值: {max_sltp_dyn}",
        "",
        "## 告警分布",
    ]
    if top_alerts:
        lines.extend([f"- `{k}`: {v}" for k, v in top_alerts])
    else:
        lines.append("- 无告警")

    lines.extend(["", "## 运行判断", "- 数据采集链路: 以 `degraded_ratio/quality_coverage` 为准，若长期高退化需继续优化采集重试与缓存。"])
    lines.extend(["- 数据分析链路: 以 diagnosis 可用率 + market_analysis 样本稳定性判断。"])
    lines.extend(["- 智能开平仓链路: 以 ai_core/ai_trading 运行状态 + guard 拒绝脉冲判断。"])
    lines.extend(["- 止盈止损链路: 以 `positions` 与 `sltp.active_orders/dynamic_adjustments` 联动判断是否在持续跟踪。"])
    lines.extend(["- 备注: 服务重启后的短时 `Connection refused` 将记为 `diagnosis_warming_up`，不再直接判定为 P0。"])

    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Continuous full-chain runtime probe")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--duration-sec", type=int, default=600)
    ap.add_argument("--interval-sec", type=int, default=20)
    ap.add_argument("--out-jsonl", default="logs/chain_runtime_probe.jsonl")
    ap.add_argument("--out-md", default="logs/chain_runtime_probe_summary.md")
    args = ap.parse_args()

    out_jsonl = Path(args.out_jsonl)
    out_md = Path(args.out_md)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    base = args.base_url.rstrip("/")
    diagnosis_url = f"{base}/api/v1/modules/commander/trading-diagnosis?limit_events=5"
    rounds = max(1, int(args.duration_sec // max(1, args.interval_sec)))

    rows: List[RoundRow] = []
    prev: Dict[str, Any] | None = None

    for i in range(rounds):
        t0 = time.time()
        diag: Dict[str, Any] = {"success": False, "error": "unknown"}
        try:
            diag = _http_json(diagnosis_url, timeout=25.0)
        except Exception as e:
            em = str(e)
            warmup = (i < 3) and (
                ("Connection refused" in em)
                or ("[Errno 111]" in em)
                or ("timed out" in em.lower())
            )
            diag = {"success": False, "error": em, "warmup": warmup}
        latency_ms = int((time.time() - t0) * 1000)
        row = _extract_row(diag, latency_ms, prev)
        rows.append(row)

        slim = {
            "ts": row.ts,
            "ok": row.ok,
            "latency_ms": row.latency_ms,
            "degraded_ratio": row.degraded_ratio,
            "quality_coverage": row.quality_coverage,
            "sample_count": row.sample_count,
            "ai_core_running": row.ai_core_running,
            "ai_trading_running": row.ai_trading_running,
            "ai_trading_positions": row.ai_trading_positions,
            "sltp_active_orders": row.sltp_active_orders,
            "sltp_dynamic_adjustments": row.sltp_dynamic_adjustments,
            "reconciliation_healthy": row.reconciliation_healthy,
            "reconciliation_drift_total": row.reconciliation_drift_total,
            "reconciliation_stale_open_orders": row.reconciliation_stale_open_orders,
            "alerts": row.alerts,
        }
        with out_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")

        prev = {
            "rr_rej": (diag.get("data", {}).get("ai_core", {}).get("execution_guards", {}).get("stats", {}) or {}).get("rr_rejected", 0),
            "sp_rej": (diag.get("data", {}).get("ai_core", {}).get("execution_guards", {}).get("stats", {}) or {}).get("spread_rejected", 0),
            "dq_hold": (diag.get("data", {}).get("ai_core", {}).get("execution_guards", {}).get("stats", {}) or {}).get("data_quality_guard_hold", 0),
            "sltp_dyn": (diag.get("data", {}).get("sltp", {}) or {}).get("dynamic_adjustments", 0),
        }

        if i < rounds - 1:
            time.sleep(max(1, args.interval_sec))

    _write_summary(rows, out_md, args.duration_sec, args.interval_sec)
    print(f"probe_jsonl={out_jsonl}")
    print(f"probe_summary={out_md}")
    print(f"rounds={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

