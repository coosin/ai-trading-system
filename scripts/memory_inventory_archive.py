#!/usr/bin/env python3
"""
记忆库盘点与可选归档（只移动文件，不删数据库记录）。

默认只读扫描；使用 --archive 将「顶层的、非四分层目录的」文件移到 _archive/。

用法：
  python3 scripts/memory_inventory_archive.py --roots data/memory workspace/memory
  python3 scripts/memory_inventory_archive.py --roots data/memory --archive --archive-to data/memory/_archive/20260409
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _walk_layer(root: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "path": str(root),
        "exists": root.exists(),
        "layers": {},
        "orphan_files": [],
        "total_files": 0,
        "total_bytes": 0,
    }
    if not root.exists():
        return out

    for sub in sorted(root.iterdir()):
        if sub.is_dir():
            name = sub.name
            if name.startswith("_"):
                continue
            files = list(sub.rglob("*.json"))
            nbytes = sum(f.stat().st_size for f in files if f.is_file())
            out["layers"][name] = {"file_count": len(files), "bytes": nbytes}
            out["total_files"] += len(files)
            out["total_bytes"] += nbytes
        elif sub.is_file():
            out["orphan_files"].append(str(sub))
            out["total_files"] += 1
            out["total_bytes"] += sub.stat().st_size
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Memory library inventory / optional archive")
    ap.add_argument(
        "--roots",
        nargs="+",
        default=["data/memory", "workspace/memory"],
        help="Roots to scan (default: data/memory workspace/memory)",
    )
    ap.add_argument("--report", default="", help="Write JSON report to this path")
    ap.add_argument("--archive", action="store_true", help="Move orphan root-level files to archive dir")
    ap.add_argument("--archive-to", default="", help="Archive directory (required if --archive)")
    args = ap.parse_args()

    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "roots": [],
        "archived": [],
    }

    for r in args.roots:
        root = Path(r)
        info = _walk_layer(root)
        report["roots"].append(info)

        if args.archive:
            dest_root = Path(args.archive_to or "")
            if not dest_root:
                print("ERROR: --archive-to is required when using --archive")
                return 2
            dest_root.mkdir(parents=True, exist_ok=True)
            for of in info.get("orphan_files", []):
                p = Path(of)
                if not p.is_file():
                    continue
                # only archive loose json / md at root (not inside layers)
                if p.parent.resolve() != root.resolve():
                    continue
                target = dest_root / p.name
                if target.exists():
                    target = dest_root / f"{p.stem}_{datetime.now().strftime('%H%M%S')}{p.suffix}"
                shutil.move(str(p), str(target))
                report["archived"].append({"from": str(p), "to": str(target)})

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
