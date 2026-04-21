#!/usr/bin/env python3
"""
One-off SLTP migration utility.

Purpose:
- Remove legacy `pending_close` records that have retried far beyond policy.
- Keep a timestamped backup and write an audit report for traceability.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


def now_tag() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def load_orders(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("stop_loss_orders.json must be a JSON object")
    data.setdefault("orders", {})
    data.setdefault("stats", {})
    if not isinstance(data["orders"], dict):
        raise ValueError("stop_loss_orders.json field 'orders' must be an object")
    return data


def summarize(orders: Dict[str, Any]) -> Dict[str, int]:
    c: Counter[str] = Counter()
    for _, item in orders.items():
        if isinstance(item, dict):
            c[str(item.get("status"))] += 1
    return dict(c)


def select_stale_pending(
    orders: Dict[str, Any],
    retry_threshold: int,
) -> List[Tuple[str, Dict[str, Any], int]]:
    out: List[Tuple[str, Dict[str, Any], int]] = []
    for oid, item in orders.items():
        if not isinstance(item, dict):
            continue
        if str(item.get("status")) != "pending_close":
            continue
        meta = item.get("metadata") or {}
        attempts = int(meta.get("pending_close_attempts", 0) or 0)
        if attempts >= retry_threshold:
            out.append((oid, item, attempts))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate legacy SLTP pending_close records")
    ap.add_argument(
        "--file",
        default="/home/cool/ai-trading-system/data/stop_loss_orders.json",
        help="Path to SLTP persistence file",
    )
    ap.add_argument(
        "--retry-threshold",
        type=int,
        default=100,
        help="Delete pending_close rows with attempts >= this value",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default is dry-run)",
    )
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    data = load_orders(path)
    orders: Dict[str, Any] = data["orders"]
    before = summarize(orders)
    stale = select_stale_pending(orders, retry_threshold=args.retry_threshold)

    report = {
        "timestamp": datetime.now().isoformat(),
        "file": str(path),
        "apply": bool(args.apply),
        "retry_threshold": int(args.retry_threshold),
        "before_status_counts": before,
        "remove_count": len(stale),
        "removed_items": [
            {
                "order_id": oid,
                "attempts": attempts,
                "symbol": item.get("symbol"),
                "side": item.get("side"),
                "status": item.get("status"),
                "index_key": (item.get("metadata") or {}).get("index_key"),
            }
            for oid, item, attempts in stale
        ],
    }

    if args.apply and stale:
        backup = path.with_name(f"{path.name}.bak.migrate-{now_tag()}")
        shutil.copy2(path, backup)
        for oid, _, _ in stale:
            orders.pop(oid, None)
        data["orders"] = orders
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        report["backup"] = str(backup)
        report["after_status_counts"] = summarize(orders)
    else:
        report["after_status_counts"] = before

    report_path = path.with_name(f"sltp_migration_report_{now_tag()}.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    print(f"report_file={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

