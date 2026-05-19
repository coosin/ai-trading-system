#!/usr/bin/env python3
"""
离线去重交易所真值账本。

- 默认 dry-run：仅输出重复统计，不修改文件
- --apply：写回去重后的账本，并保留一个 .bak 备份
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modules.core.exchange_sync_ledger import _event_dedupe_key


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--path",
        default="logs/exchange_sync/exchange_truth.jsonl",
        help="账本路径",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="实际写回去重后的账本（默认仅统计）",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.path)
    if not path.exists():
        print(f"[error] ledger not found: {path}")
        return 1

    lines = path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    kept: list[str] = []
    dropped = 0
    invalid = 0

    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            invalid += 1
            kept.append(line)
            continue
        key = _event_dedupe_key(row)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        kept.append(json.dumps(row, ensure_ascii=False, default=str))

    print(f"[summary] total={len(lines)} kept={len(kept)} dropped={dropped} invalid={invalid}")

    if not args.apply:
        return 0

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    print(f"[apply] wrote deduped ledger to {path}")
    print(f"[backup] {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
