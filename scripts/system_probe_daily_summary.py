#!/usr/bin/env python3
"""
将 continuous_system_probe 的 JSONL 报告汇总成中文日报。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _parse_ts_hour(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:00")
    except Exception:
        return "unknown"


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _suggestions(alert_counter: Counter[str]) -> List[str]:
    tips: List[str] = []
    rr = sum(v for k, v in alert_counter.items() if k.startswith("rr_rejected_spike"))
    sp = sum(v for k, v in alert_counter.items() if k.startswith("spread_rejected_spike"))
    dq = sum(v for k, v in alert_counter.items() if k.startswith("data_quality_hold_spike"))
    sltp = sum(v for k, v in alert_counter.items() if k.startswith("sltp_adjustments_spike"))
    health = sum(v for k, v in alert_counter.items() if "unavailable" in k or "s1_verify_fail" in k)

    if health > 0:
        tips.append("优先排查 API 可用性与网络连通，确认 /api/v1/system/health 与 /api/v1/s1/verify 持续可用。")
    if sp > 0:
        tips.append("价差拒绝偏高，建议放宽 max_spread_bps_to_trade 或减少低流动性时段交易。")
    if rr > 0:
        tips.append("RR 拒绝偏高，建议检查止损/止盈参数是否过紧，或小幅下调 min_rr_to_trade。")
    if dq > 0:
        tips.append("数据质量 hold 偏高，建议提升数据源稳定性并检查第三方数据可用性。")
    if sltp > 0:
        tips.append("SLTP 动态调整频繁，建议降低 auto_tune_sltp_step_extend 或提高学习冷却时间。")
    if not tips:
        tips.append("整体稳定，保持当前参数并继续观察下一周期。")
    return tips


def main() -> int:
    parser = argparse.ArgumentParser(description="系统巡检日报汇总")
    parser.add_argument("--input", default="logs/system_probe_report.jsonl", help="输入 JSONL 路径")
    parser.add_argument("--output", default="logs/system_probe_daily_summary.md", help="输出 Markdown 路径")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = _load_jsonl(input_path)
    total = len(rows)
    alerts_total = 0
    rounds_with_alerts = 0
    alert_counter: Counter[str] = Counter()
    warmup_counter = 0
    hour_counter: Counter[str] = Counter()

    max_rr = 0
    max_sp = 0
    max_dp = 0
    max_dq = 0
    max_sltp_adj = 0

    for r in rows:
        alerts = list(r.get("alerts", []) or [])
        non_warmup_alerts = [a for a in alerts if str(a) != "diagnosis_warming_up"]
        warmup_counter += sum(1 for a in alerts if str(a) == "diagnosis_warming_up")
        if non_warmup_alerts:
            rounds_with_alerts += 1
        alerts_total += len(non_warmup_alerts)
        for a in non_warmup_alerts:
            alert_counter[str(a)] += 1
            hour_counter[_parse_ts_hour(str(r.get("ts", "")))] += 1

        gd = r.get("guards_delta", {}) or {}
        max_rr = max(max_rr, int(gd.get("rr_rejected", 0) or 0))
        max_sp = max(max_sp, int(gd.get("spread_rejected", 0) or 0))
        max_dp = max(max_dp, int(gd.get("depth_imbalance_rejected", 0) or 0))
        max_dq = max(max_dq, int(gd.get("data_quality_guard_hold", 0) or 0))
        max_sltp_adj = max(max_sltp_adj, int(r.get("sltp_dynamic_adjustments_delta", 0) or 0))

    top_alerts = alert_counter.most_common(8)
    top_hours = hour_counter.most_common(5)
    suggest = _suggestions(alert_counter)

    lines = [
        "# 系统巡检日报",
        "",
        f"- 生成时间: {datetime.now().isoformat()}",
        f"- 输入文件: `{input_path}`",
        f"- 总轮次: {total}",
        f"- 告警总数: {alerts_total}",
        f"- 含告警轮次: {rounds_with_alerts}",
        f"- 预热轮次(降噪不计入告警): {warmup_counter}",
        "",
        "## 峰值指标",
        f"- RR拒绝单轮峰值: {max_rr}",
        f"- 价差拒绝单轮峰值: {max_sp}",
        f"- 深度失衡拒绝单轮峰值: {max_dp}",
        f"- 数据质量Hold单轮峰值: {max_dq}",
        f"- SLTP动态调整单轮峰值: {max_sltp_adj}",
        "",
        "## 高频告警",
    ]
    if top_alerts:
        lines.extend([f"- `{k}`: {v} 次" for k, v in top_alerts])
    else:
        lines.append("- 无告警")

    lines.extend(["", "## 高风险时段",])
    if top_hours:
        lines.extend([f"- {h}: {c} 次告警" for h, c in top_hours])
    else:
        lines.append("- 无明显高风险时段")

    lines.extend(["", "## 调整建议",])
    lines.extend([f"- {s}" for s in suggest])

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"summary written: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

