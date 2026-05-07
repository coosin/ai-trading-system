#!/usr/bin/env python3
"""
Build a safe backfill plan for historical trades where strategy is unknown/empty.

Note:
- TradeHistoryService uses append semantics for records.
- To avoid duplicate writes, this script DOES NOT rewrite records directly.
- It generates a JSON plan that can be reviewed and then applied by a targeted updater.

Usage:
  python3 scripts/migrate_strategy_ids.py --limit 500 --out data/runtime/strategy_backfill_plan.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from typing import Any, Dict

from src.modules.core.trade_history_service import TradeHistoryService
from src.modules.core.decision_contract import normalize_strategy_field


def _guess_strategy(row: Dict[str, Any]) -> str:
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    s = normalize_strategy_field(row, metadata=md, default="")
    if s:
        return s
    src = str(row.get("source") or md.get("source") or "").strip().lower()
    if src:
        return src
    return "legacy_unknown"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--out", default="data/runtime/strategy_backfill_plan.json")
    args = ap.parse_args()

    svc = TradeHistoryService()
    ok = await svc.initialize()
    if not ok:
        print("init_failed")
        return 2

    rows = await svc.get_recent_trades(limit=max(10, int(args.limit or 1000)))
    proposals = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        cur = str(row.get("strategy") or "").strip().lower()
        if cur and cur != "unknown":
            continue
        new_sid = _guess_strategy(row)
        if not new_sid:
            continue
        proposals.append(
            {
                "trade_id": row.get("trade_id"),
                "order_id": row.get("order_id"),
                "symbol": row.get("symbol"),
                "timestamp": row.get("timestamp"),
                "current_strategy": row.get("strategy"),
                "proposed_strategy_id": new_sid,
            }
        )

    out_obj = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "checked": len(rows or []),
        "proposals": proposals,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)

    print(f"checked={len(rows or [])} proposals={len(proposals)} out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
