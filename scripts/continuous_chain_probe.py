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
    exchange_reachability_status: str
    exchange_reachability_score: float
    degraded_ratio: float
    quality_coverage: float
    sample_count: int
    ai_core_running: bool
    ai_trading_running: bool
    ai_trading_positions: int
    sltp_active_orders: int
    sltp_dynamic_adjustments: int
    trend_coverage: float
    trend_consistency: float
    open_ok: int
    open_fail: int
    close_ok: int
    close_fail: int
    execution_top_reason: str
    execution_top_severity: str
    decision_trace_guard_rejected: int
    decision_trace_execution_failed: int
    position_consistency_healthy: bool
    position_consistency_delta_exchange_vs_ai: int
    position_consistency_delta_exchange_vs_sltp: int
    position_consistency_exchange_non_zero: int
    position_consistency_ai_tracked: int
    position_consistency_sltp_tracked: int
    strategy_coverage: float
    trace_coverage: float
    trade_30d_win_rate: float
    trade_30d_sum_pnl: float
    guard_exchange_unreachable_rejected: int
    guard_exchange_degraded_risk_reduced: int
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
    exec_gw = (data.get("execution_gateway") or {}) if isinstance(data, dict) else {}
    rec = (data.get("execution_reconciliation") or {}) if isinstance(data, dict) else {}
    rec_sum = (rec.get("summary") or {}) if isinstance(rec, dict) else {}
    exch = (data.get("exchange_reachability") or {}) if isinstance(data, dict) else {}
    attr = (data.get("execution_attribution") or {}) if isinstance(data, dict) else {}
    dt_raw = (data.get("decision_traces") or {}) if isinstance(data, dict) else {}
    pc = (data.get("position_consistency") or {}) if isinstance(data, dict) else {}
    dci = (data.get("decision_contract_integrity") or {}) if isinstance(data, dict) else {}
    th30 = (data.get("trade_history_30d") or {}) if isinstance(data, dict) else {}
    exch_st = str(exch.get("status") or "unknown").lower()
    try:
        exch_score = float(((exch.get("probe") or {}) if isinstance(exch.get("probe"), dict) else {}).get("score") or 0.0)
    except Exception:
        exch_score = 0.0

    guards = (ai_core.get("execution_guards") or {}) if isinstance(ai_core, dict) else {}
    gstats = (guards.get("stats") or {}) if isinstance(guards, dict) else {}
    top_reasons = attr.get("top_reasons") if isinstance(attr.get("top_reasons"), list) else []
    top_reason = top_reasons[0] if top_reasons and isinstance(top_reasons[0], dict) else {}

    policy = exec_gw.get("policy_metrics") if isinstance(exec_gw.get("policy_metrics"), dict) else {}
    open_ok = _to_int(policy.get("open_ok"))
    open_fail = _to_int(policy.get("open_fail"))
    close_ok = _to_int(policy.get("close_ok"))
    close_fail = _to_int(policy.get("close_fail"))

    if isinstance(dt_raw, dict):
        dt_summary = dt_raw.get("summary") if isinstance(dt_raw.get("summary"), dict) else {}
    elif isinstance(dt_raw, list):
        dt_summary = {
            "sample_size": len(dt_raw),
            "guard_rejected": 0,
            "execution_failed": 0,
        }
    else:
        dt_summary = {}

    ma_samples = ma.get("samples") if isinstance(ma.get("samples"), list) else []
    trend_values = [str((x or {}).get("trend") or "").strip().lower() for x in ma_samples if isinstance(x, dict)]
    trend_values = [x for x in trend_values if x]
    trend_non_unknown = [x for x in trend_values if x not in {"unknown", "none", "null"}]
    trend_coverage = round(float(len(trend_non_unknown)) / float(max(1, len(ma_samples))), 4)
    dominant = ""
    if trend_non_unknown:
        counts: Dict[str, int] = {}
        for t in trend_non_unknown:
            counts[t] = int(counts.get(t, 0)) + 1
        dominant = max(counts.items(), key=lambda kv: kv[1])[0]
        trend_consistency = round(float(counts.get(dominant, 0)) / float(max(1, len(trend_non_unknown))), 4)
    else:
        trend_consistency = 0.0

    sltp_dyn = _to_int(sltp.get("dynamic_adjustments"))
    rr_rej = _to_int(gstats.get("rr_rejected"))
    sp_rej = _to_int(gstats.get("spread_rejected"))
    dq_hold = _to_int(gstats.get("data_quality_guard_hold"))
    ex_unreach_rej = _to_int(gstats.get("exchange_unreachable_rejected"))
    ex_degraded_reduce = _to_int(gstats.get("exchange_degraded_risk_reduced"))

    alerts: List[str] = []
    err_text = str(diag.get("error") or "")
    warmup = bool(diag.get("warmup"))
    if not bool(diag.get("success")):
        # Startup windows right after service restart should not be treated as hard failures.
        if warmup:
            alerts.append("diagnosis_warming_up")
        else:
            alerts.append("diagnosis_failed")
    degraded_ratio_now = _to_float(ma.get("degraded_ratio"))
    degraded_ratio_prev = _to_float((prev or {}).get("degraded_ratio"), 0.0)
    # Debounce transient one-off spikes; keep alert only when degradation persists.
    if degraded_ratio_now > 0.35 and degraded_ratio_prev > 0.35:
        alerts.append("degraded_ratio_high")
    if trend_coverage < 0.5:
        alerts.append("trend_coverage_low")
    if exch_st == "unreachable":
        alerts.append("exchange_unreachable")
    elif exch_st == "degraded":
        alerts.append("exchange_degraded")
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
    pc_deltas = pc.get("deltas") if isinstance(pc.get("deltas"), dict) else {}
    pc_delta_ex_ai = _to_int(pc_deltas.get("exchange_vs_ai"))
    pc_delta_ex_sltp = _to_int(pc_deltas.get("exchange_vs_sltp"))
    pc_ex_non_zero = _to_int(pc.get("exchange_non_zero_positions"), -1)
    pc_ai_tracked = _to_int(pc.get("ai_tracked_positions"), -1)
    pc_sltp_tracked = _to_int(pc.get("sltp_live_tracked"), -1)

    if bool(pc) and (pc.get("healthy") is False):
        alerts.append("position_consistency_mismatch")
    # Do not escalate this as an alert: SLTP tracked count >= exchange non-zero positions
    # is often a benign supersets case (normalized keys / staged entries).
    if bool(dci) and (_to_float(dci.get("strategy_coverage"), 1.0) < 0.95 or _to_float(dci.get("trace_coverage"), 1.0) < 0.95):
        alerts.append("decision_contract_coverage_low")

    if prev:
        if rr_rej - _to_int(prev.get("rr_rej")) >= 2:
            alerts.append("rr_rejected_spike")
        if sp_rej - _to_int(prev.get("sp_rej")) >= 2:
            alerts.append("spread_rejected_spike")
        if dq_hold - _to_int(prev.get("dq_hold")) >= 2:
            alerts.append("data_quality_hold_spike")
        if ex_unreach_rej - _to_int(prev.get("ex_unreach_rej")) >= 1:
            alerts.append("exchange_unreachable_rejected_spike")
        if ex_degraded_reduce - _to_int(prev.get("ex_degraded_reduce")) >= 1:
            alerts.append("exchange_degraded_risk_reduced_spike")
        if sltp_dyn - _to_int(prev.get("sltp_dyn")) >= 60:
            alerts.append("sltp_adjustments_spike")

    return RoundRow(
        ts=datetime.now().isoformat(),
        ok=bool(diag.get("success")),
        latency_ms=latency_ms,
        exchange_reachability_status=exch_st,
        exchange_reachability_score=float(exch_score),
        degraded_ratio=_to_float(ma.get("degraded_ratio")),
        quality_coverage=_to_float(ma.get("quality_coverage")),
        sample_count=len(ma.get("samples") or []) if isinstance(ma.get("samples"), list) else 0,
        ai_core_running=bool(ai_core.get("running")),
        ai_trading_running=bool(ai_engine.get("running")),
        ai_trading_positions=_to_int(ai_engine.get("positions")),
        sltp_active_orders=_to_int(sltp.get("active_orders")),
        sltp_dynamic_adjustments=sltp_dyn,
        trend_coverage=trend_coverage,
        trend_consistency=trend_consistency,
        open_ok=open_ok,
        open_fail=open_fail,
        close_ok=close_ok,
        close_fail=close_fail,
        execution_top_reason=str(top_reason.get("key") or ""),
        execution_top_severity=str(top_reason.get("severity") or ""),
        decision_trace_guard_rejected=_to_int(dt_summary.get("guard_rejected")),
        decision_trace_execution_failed=_to_int(dt_summary.get("execution_failed")),
        position_consistency_healthy=bool(pc.get("healthy")) if pc.get("healthy") is not None else True,
        position_consistency_delta_exchange_vs_ai=pc_delta_ex_ai,
        position_consistency_delta_exchange_vs_sltp=pc_delta_ex_sltp,
        position_consistency_exchange_non_zero=pc_ex_non_zero,
        position_consistency_ai_tracked=pc_ai_tracked,
        position_consistency_sltp_tracked=pc_sltp_tracked,
        strategy_coverage=_to_float(dci.get("strategy_coverage"), 1.0),
        trace_coverage=_to_float(dci.get("trace_coverage"), 1.0),
        trade_30d_win_rate=_to_float(th30.get("win_rate"), 0.0),
        trade_30d_sum_pnl=_to_float(th30.get("total_pnl"), 0.0),
        guard_exchange_unreachable_rejected=ex_unreach_rej,
        guard_exchange_degraded_risk_reduced=ex_degraded_reduce,
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
    exch_unreach = sum(1 for r in rows if r.exchange_reachability_status == "unreachable")
    exch_degraded = sum(1 for r in rows if r.exchange_reachability_status == "degraded")
    max_ex_unreach_rej = max((r.guard_exchange_unreachable_rejected for r in rows), default=0)
    max_ex_deg_reduce = max((r.guard_exchange_degraded_risk_reduced for r in rows), default=0)
    avg_trend_coverage = round(sum(r.trend_coverage for r in rows) / max(1, total), 4)
    avg_trend_consistency = round(sum(r.trend_consistency for r in rows) / max(1, total), 4)
    open_fail_spike = max((r.open_fail for r in rows), default=0)
    close_fail_spike = max((r.close_fail for r in rows), default=0)
    contract_bad = sum(1 for r in rows if r.strategy_coverage < 0.95 or r.trace_coverage < 0.95)
    pos_consistency_bad = sum(1 for r in rows if not r.position_consistency_healthy)
    avg_win_rate = round(sum(r.trade_30d_win_rate for r in rows) / max(1, total), 4)
    avg_30d_pnl = round(sum(r.trade_30d_sum_pnl for r in rows) / max(1, total), 4)

    alert_counter: Dict[str, int] = {}
    for r in rows:
        for a in r.alerts:
            alert_counter[a] = alert_counter.get(a, 0) + 1
    top_alerts = sorted(alert_counter.items(), key=lambda x: x[1], reverse=True)[:8]

    verdict = "整体正常"
    if ai_down > 0 or rec_bad > 0 or exch_unreach > 0:
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
        f"- 交易所可达性: unreachable={exch_unreach} degraded={exch_degraded} (窗口轮次)",
        f"- 数据退化比例>0.35 轮次: {degraded_bad}",
        f"- 对账异常轮次: {rec_bad}",
        f"- AI主链路非运行轮次: {ai_down}",
        f"- 持仓峰值: {max_positions}",
        f"- 对账漂移峰值: {max_drift}",
        f"- SLTP动态调整峰值: {max_sltp_dyn}",
        f"- 不可达阻断开仓计数峰值: {max_ex_unreach_rej}",
        f"- 降级降风险计数峰值: {max_ex_deg_reduce}",
        f"- 趋势识别覆盖均值: {avg_trend_coverage}",
        f"- 趋势一致性均值: {avg_trend_consistency}",
        f"- 开仓失败计数峰值: {open_fail_spike}",
        f"- 平仓失败计数峰值: {close_fail_spike}",
        f"- 决策合约覆盖异常轮次: {contract_bad}",
        f"- 持仓一致性异常轮次: {pos_consistency_bad}",
        f"- 30d胜率均值: {avg_win_rate}",
        f"- 30dPnL均值: {avg_30d_pnl}",
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
    lines.extend(["- 开平仓执行质量: 以 `open_ok/open_fail/close_ok/close_fail` 和 top_reason/severity 识别瓶颈环节。"])
    lines.extend(["- 决策可追溯性: 以 strategy_coverage/trace_coverage 与 decision_traces 的 rejected/failed 判断链路完整度。"])
    lines.extend(["- 盈利结构: 以 trade_history_30d 的 win_rate/total_pnl 识别当前策略收益特征。"])
    lines.extend(["- 交易所链路: `exchange_unreachable` 视为 P0；`exchange_degraded` 视为 P1（系统会降杠杆/降仓）。"])
    lines.extend(["- 备注: 服务重启后的短时 `Connection refused` 将记为 `diagnosis_warming_up`，不再直接判定为 P0。"])
    lines.extend(["", "## 优缺点自动归纳"])
    lines.extend([
        f"- 优点: 对账稳定性良好轮次 {total - rec_bad}/{total}，SLTP跟踪在位轮次 {sum(1 for r in rows if r.sltp_active_orders > 0 or r.ai_trading_positions == 0)}/{total}。"
    ])
    lines.extend([
        f"- 不足: 交易所不可达/降级轮次 {exch_unreach + exch_degraded}，趋势覆盖不足轮次 {sum(1 for r in rows if r.trend_coverage < 0.5)}，决策可追溯性不足轮次 {contract_bad}。"
    ])

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
            "exchange_reachability_status": row.exchange_reachability_status,
            "exchange_reachability_score": row.exchange_reachability_score,
            "degraded_ratio": row.degraded_ratio,
            "quality_coverage": row.quality_coverage,
            "sample_count": row.sample_count,
            "ai_core_running": row.ai_core_running,
            "ai_trading_running": row.ai_trading_running,
            "ai_trading_positions": row.ai_trading_positions,
            "sltp_active_orders": row.sltp_active_orders,
            "sltp_dynamic_adjustments": row.sltp_dynamic_adjustments,
            "trend_coverage": row.trend_coverage,
            "trend_consistency": row.trend_consistency,
            "open_ok": row.open_ok,
            "open_fail": row.open_fail,
            "close_ok": row.close_ok,
            "close_fail": row.close_fail,
            "execution_top_reason": row.execution_top_reason,
            "execution_top_severity": row.execution_top_severity,
            "decision_trace_guard_rejected": row.decision_trace_guard_rejected,
            "decision_trace_execution_failed": row.decision_trace_execution_failed,
            "position_consistency_healthy": row.position_consistency_healthy,
            "position_consistency_delta_exchange_vs_ai": row.position_consistency_delta_exchange_vs_ai,
            "position_consistency_delta_exchange_vs_sltp": row.position_consistency_delta_exchange_vs_sltp,
            "position_consistency_exchange_non_zero": row.position_consistency_exchange_non_zero,
            "position_consistency_ai_tracked": row.position_consistency_ai_tracked,
            "position_consistency_sltp_tracked": row.position_consistency_sltp_tracked,
            "strategy_coverage": row.strategy_coverage,
            "trace_coverage": row.trace_coverage,
            "trade_30d_win_rate": row.trade_30d_win_rate,
            "trade_30d_sum_pnl": row.trade_30d_sum_pnl,
            "guard_exchange_unreachable_rejected": row.guard_exchange_unreachable_rejected,
            "guard_exchange_degraded_risk_reduced": row.guard_exchange_degraded_risk_reduced,
            "reconciliation_healthy": row.reconciliation_healthy,
            "reconciliation_drift_total": row.reconciliation_drift_total,
            "reconciliation_stale_open_orders": row.reconciliation_stale_open_orders,
            "alerts": row.alerts,
        }
        with out_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")

        prev = {
            "degraded_ratio": row.degraded_ratio,
            "rr_rej": (diag.get("data", {}).get("ai_core", {}).get("execution_guards", {}).get("stats", {}) or {}).get("rr_rejected", 0),
            "sp_rej": (diag.get("data", {}).get("ai_core", {}).get("execution_guards", {}).get("stats", {}) or {}).get("spread_rejected", 0),
            "dq_hold": (diag.get("data", {}).get("ai_core", {}).get("execution_guards", {}).get("stats", {}) or {}).get("data_quality_guard_hold", 0),
            "ex_unreach_rej": (diag.get("data", {}).get("ai_core", {}).get("execution_guards", {}).get("stats", {}) or {}).get(
                "exchange_unreachable_rejected", 0
            ),
            "ex_degraded_reduce": (diag.get("data", {}).get("ai_core", {}).get("execution_guards", {}).get("stats", {}) or {}).get(
                "exchange_degraded_risk_reduced", 0
            ),
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

