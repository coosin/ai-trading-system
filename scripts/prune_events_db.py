#!/usr/bin/env python3
"""
Prune old rows from data/events.db (SQLite) and optionally VACUUM.

Safe offline maintenance when events.db grows very large.
If the trading system holds the DB lock, stop the service first or copy the file and prune the copy.

Examples:
  OPENCLAW_EVENTS_DB=/home/cool/ai-trading-system/data/events.db \\
    python3 scripts/prune_events_db.py --keep-days 45 --vacuum

Dry-run (no writes):
  python3 scripts/prune_events_db.py --keep-days 30 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Prune EnhancedEventSystem SQLite events table.")
    ap.add_argument("--db", default=os.getenv("OPENCLAW_EVENTS_DB", ""), help="Path to events.db")
    ap.add_argument("--keep-days", type=int, default=90, help="Delete rows older than N days (by timestamp column)")
    ap.add_argument("--vacuum", action="store_true", help="Run VACUUM after delete (rewrites DB)")
    ap.add_argument("--dry-run", action="store_true", help="Print counts only")
    args = ap.parse_args()

    db_path = (args.db or "").strip() or str(_repo_root() / "data" / "events.db")
    p = Path(db_path)
    if not p.is_file():
        print(f"ERROR: db not found: {p}", file=sys.stderr)
        return 2

    before_size = p.stat().st_size
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, int(args.keep_days)))).isoformat()

    conn = sqlite3.connect(str(p), timeout=90.0)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM events")
        total = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM events WHERE timestamp < ?", (cutoff,))
        to_del = int(cur.fetchone()[0])
        print(f"db={p} size_mb={before_size/1024/1024:.2f} rows={total} older_than_cutoff={to_del} cutoff_iso={cutoff}")
        if args.dry_run:
            return 0
        if to_del > 0:
            cur.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
            conn.commit()
            print(f"deleted_rows={cur.rowcount if hasattr(cur,'rowcount') else to_del}")
        if args.vacuum:
            conn.execute("VACUUM")
            conn.commit()
    finally:
        conn.close()

    after_size = p.stat().st_size
    print(f"after_size_mb={after_size/1024/1024:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
