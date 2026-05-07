#!/usr/bin/env python3
"""
Operator-friendly reconciliation triage report.

This script DOES NOT place orders.
It calls /api/v1/trades/reconcile/report and writes a Markdown report for humans.

Usage:
  python3 scripts/reconcile_report_triage.py --base-url http://127.0.0.1:8000 --days 7 --top-n 20
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import urllib.request


def _http_json(url: str, timeout: float = 20.0) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _mini(rows: List[Dict[str, Any]], n: int = 8) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in (rows or [])[: max(1, int(n))]:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "symbol": r.get("symbol"),
                "order_id": r.get("order_id"),
                "matched": bool(r.get("matched")),
                "match_method": r.get("match_method"),
                "pnl_delta": _to_float(r.get("pnl_delta")),
                "fee_delta": _to_float(r.get("fee_delta")),
                "ex_fill_count": r.get("ex_fill_count"),
                "db_pnl": _to_float(r.get("db_pnl")),
                "ex_pnl": _to_float(r.get("ex_pnl")),
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="reconcile report triage")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--symbol", default="")
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--timeout-sec", type=float, default=8.0)
    ap.add_argument("--out", default="logs/reconcile_gap_report.md")
    args = ap.parse_args()

    base = str(args.base_url).rstrip("/")
    q = {
        "days": str(int(args.days)),
        "top_n": str(int(args.top_n)),
        "timeout_sec": str(float(args.timeout_sec)),
    }
    if str(args.symbol or "").strip():
        q["symbol"] = str(args.symbol).strip()
    query = "&".join([f"{k}={urllib.request.quote(v)}" for k, v in q.items()])
    url = f"{base}/api/v1/trades/reconcile/report?{query}"

    payload = _http_json(url, timeout=max(10.0, float(args.timeout_sec) + 3.0))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not bool(payload.get("success")):
        out.write_text(
            "\n".join(
                [
                    "# 对账差异报告（失败）",
                    "",
                    f"- generated_at: {datetime.now().isoformat()}",
                    f"- url: {url}",
                    f"- message: {payload.get('message')}",
                    f"- details: {payload.get('details')}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(f"report written (failed): {out}")
        return 2

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    lines: List[str] = [
        "# 对账差异报告（Triage）",
        "",
        f"- generated_at: {payload.get('generated_at') or datetime.now().isoformat()}",
        f"- period_days: {payload.get('period_days')}",
        f"- symbol: {payload.get('symbol') or 'ALL'}",
        "",
        "## 摘要",
        f"- candidate_rows: {summary.get('candidate_rows')}",
        f"- matched: {summary.get('matched')}",
        f"- missing_on_exchange: {summary.get('missing_on_exchange')}",
        f"- match_rate: {summary.get('match_rate')}",
        f"- matched_by_order_id: {summary.get('matched_by_order_id')}",
        f"- matched_by_time_window: {summary.get('matched_by_time_window')}",
        f"- sum_abs_pnl_delta: {summary.get('sum_abs_pnl_delta')}",
        f"- sum_abs_fee_delta: {summary.get('sum_abs_fee_delta')}",
        f"- match_method_distribution: {json.dumps(summary.get('match_method_distribution') or {}, ensure_ascii=False)}",
        f"- pnl_delta_abs_ge_0_5_count: {summary.get('pnl_delta_abs_ge_0_5_count')}",
        f"- fee_delta_abs_ge_0_5_count: {summary.get('fee_delta_abs_ge_0_5_count')}",
        "",
        "## 建议优先级",
        "1. 先看 `top_missing_on_exchange`（系统有记录但交易所未找到 fills）",
        "2. 再看 `top_time_window_matches`（order_id 链路缺失或历史样本不足）",
        "3. 最后看 `top_pnl_delta` / `top_fee_delta`（核对费用、合约 ctVal 与均价聚合）",
        "",
        "## TOP missing_on_exchange",
        "```json",
        json.dumps(_mini(payload.get("top_missing_on_exchange") or [], n=10), ensure_ascii=False, indent=2),
        "```",
        "",
        "## TOP time_window matches",
        "```json",
        json.dumps(_mini(payload.get("top_time_window_matches") or [], n=10), ensure_ascii=False, indent=2),
        "```",
        "",
        "## TOP pnl_delta",
        "```json",
        json.dumps(_mini(payload.get("top_pnl_delta") or [], n=10), ensure_ascii=False, indent=2),
        "```",
        "",
        "## TOP fee_delta",
        "```json",
        json.dumps(_mini(payload.get("top_fee_delta") or [], n=10), ensure_ascii=False, indent=2),
        "```",
        "",
    ]

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

