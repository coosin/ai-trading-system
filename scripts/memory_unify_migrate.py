#!/usr/bin/env python3
"""
Memory unification migration tool.

Design goals:
1) Backup-first (tar + manifest)
2) Normalize memory layout to a single canonical root
3) Soft restore selected legacy content (non-destructive)
"""

from __future__ import annotations

import argparse
import json
import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List


CANONICAL_SUBDIRS = ["core", "working", "experience", "history", "trades", "sessions"]
WORKSPACE_DOCS = ["SOUL.md", "IDENTITY.md", "USER.md", "INSTRUCTIONS.md", "TRADING.md", "MEMORY.md"]
LEGACY_JSON_FILES = ["ai_memory.json", "enhanced_memory.json", "unified_memory.json"]


def _now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _collect_candidates(root: Path) -> List[Path]:
    candidates = [
        root / "workspace" / "memory",
        root / "data" / "memory",
        root / "memory",
        root / "data" / "memory.db",
        root / "data" / "trade_history",
        root / "data" / "historical_data.db",
    ]
    for name in WORKSPACE_DOCS:
        candidates.append(root / "workspace" / name)
    return [p for p in candidates if p.exists()]


def backup_all(root: Path, backup_dir: Path) -> Dict:
    backup_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = backup_dir / _now()
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    tar_path = snapshot_dir / "memory_backup.tar.gz"

    items = _collect_candidates(root)
    manifest = {
        "created_at": datetime.now().isoformat(),
        "project_root": str(root),
        "items": [str(p.relative_to(root)) for p in items],
    }
    (snapshot_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    with tarfile.open(tar_path, "w:gz") as tar:
        for p in items:
            tar.add(p, arcname=str(p.relative_to(root)))
    return {"snapshot_dir": str(snapshot_dir), "tar": str(tar_path), "items": len(items)}


def normalize_layout(target_root: Path) -> Dict:
    target_root.mkdir(parents=True, exist_ok=True)
    created = []
    for d in CANONICAL_SUBDIRS:
        p = target_root / d
        p.mkdir(parents=True, exist_ok=True)
        created.append(str(p))
    return {"target_root": str(target_root), "created_dirs": created}


def restore_workspace_docs(root: Path, target_root: Path) -> Dict:
    restored = []
    core_dir = target_root / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    for name in WORKSPACE_DOCS:
        src = root / "workspace" / name
        if not src.exists():
            continue
        dst = core_dir / name
        shutil.copy2(src, dst)
        restored.append(str(dst))
    return {"restored_docs": restored}


def import_legacy_memory_json(root: Path, target_root: Path, max_items: int = 120) -> Dict:
    notes: List[str] = []
    data_memory = root / "data" / "memory"
    for file_name in LEGACY_JSON_FILES:
        p = data_memory / file_name
        if not p.exists():
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        extracted = 0
        if isinstance(raw, list):
            for item in raw[:max_items]:
                if isinstance(item, dict):
                    text = str(item.get("content") or item.get("summary") or item.get("text") or "").strip()
                    if text:
                        notes.append(f"- [{file_name}] {text[:300]}")
                        extracted += 1
        elif isinstance(raw, dict):
            for _, val in list(raw.items())[:max_items]:
                if isinstance(val, dict):
                    text = str(val.get("content") or val.get("summary") or val.get("text") or "").strip()
                    if text:
                        notes.append(f"- [{file_name}] {text[:300]}")
                        extracted += 1
        if extracted == 0:
            notes.append(f"- [{file_name}] present but no extractable content.")

    if not notes:
        return {"imported": 0, "file": None}

    out_file = target_root / "history" / f"legacy_import_{_now()}.md"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "# Legacy Memory Import Summary",
        "",
        f"- Generated at: {datetime.now().isoformat()}",
        "- Source: data/memory/{ai_memory.json, enhanced_memory.json, unified_memory.json}",
        "",
        "## Extracted Notes",
    ]
    out_file.write_text("\n".join(header + notes), encoding="utf-8")
    return {"imported": len(notes), "file": str(out_file)}


def archive_legacy_roots(root: Path, target_root: Path) -> Dict:
    archive_base = target_root / "_archive" / _now()
    archive_base.mkdir(parents=True, exist_ok=True)
    moved = []
    for rel in ["data/memory", "memory"]:
        src = root / rel
        if not src.exists():
            continue
        dst = archive_base / rel.replace("/", "_")
        if dst.exists():
            continue
        shutil.copytree(src, dst)
        moved.append({"source": str(src), "archived_copy": str(dst)})
    return {"archive_base": str(archive_base), "archived": moved}


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup and unify memory architecture safely.")
    parser.add_argument("--target-root", default="workspace/memory", help="Canonical structured memory root.")
    parser.add_argument("--backup-dir", default="backups/memory-unify", help="Backup output dir.")
    parser.add_argument("--with-restore", action="store_true", help="Restore workspace core docs into canonical root.")
    parser.add_argument("--with-legacy-import", action="store_true", help="Import legacy json memory into history note.")
    parser.add_argument("--with-archive-copy", action="store_true", help="Copy legacy roots into _archive.")
    args = parser.parse_args()

    root = _project_root()
    backup_dir = (root / args.backup_dir).resolve()
    target_root = (root / args.target_root).resolve()

    report: Dict = {
        "started_at": datetime.now().isoformat(),
        "root": str(root),
        "actions": {},
    }
    report["actions"]["backup"] = backup_all(root, backup_dir)
    report["actions"]["normalize"] = normalize_layout(target_root)
    if args.with_restore:
        report["actions"]["restore_docs"] = restore_workspace_docs(root, target_root)
    if args.with_legacy_import:
        report["actions"]["legacy_import"] = import_legacy_memory_json(root, target_root)
    if args.with_archive_copy:
        report["actions"]["archive_copy"] = archive_legacy_roots(root, target_root)
    report["finished_at"] = datetime.now().isoformat()

    report_file = backup_dir / "last_migration_report.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "report_file": str(report_file), "target_root": str(target_root)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

