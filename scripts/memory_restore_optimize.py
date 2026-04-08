#!/usr/bin/env python3
"""
Restore and optimize trading memory from backup archive.

Features:
- Restore from memory_backup.tar.gz (legacy json/docs)
- Noise filtering + deduplication
- Classification into trading-focused memory categories
- Seed AI commander role/boundary/skills pack files
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _iso() -> str:
    return datetime.now().isoformat()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _latest_backup_tar(root: Path) -> Optional[Path]:
    base = root / "backups" / "memory-unify"
    if not base.exists():
        return None
    cands = sorted(base.glob("*/memory_backup.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


def _stable_id(prefix: str, text: str) -> str:
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()[:10]
    return f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{prefix}_{digest}"


def _is_noise(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    if len(t) < 8:
        return True
    noise_markers = [
        "traceback",
        "permission denied",
        "module not found",
        "failed to resolve",
        "unsupported sandbox",
        "command not found",
        "__pycache__",
    ]
    return any(m in t for m in noise_markers)


def _classify(text: str) -> Tuple[str, str, List[str], float]:
    """
    Returns: category, layer, tags, importance
    """
    t = text.lower()
    if any(k in t for k in ["止损", "止盈", "stop loss", "take profit", "强平", "风险", "回撤"]):
        return ("risk_event", "experience", ["risk", "sltp"], 0.82)
    if any(k in t for k in ["策略优化", "优化", "optimize", "参数", "回测", "backtest", "strategy"]):
        return ("lesson_learned", "experience", ["strategy", "optimization"], 0.78)
    if any(k in t for k in ["开仓", "平仓", "做多", "做空", "成交", "position", "trade"]):
        return ("trade_record", "experience", ["trade", "execution"], 0.74)
    if any(k in t for k in ["职责", "边界", "人格", "身份", "规则"]):
        return ("trading_rule", "core", ["governance"], 0.9)
    return ("market_observation", "working", ["market"], 0.62)


def _write_memory_entry(target_root: Path, category: str, layer: str, text: str, tags: List[str], importance: float, metadata: Dict[str, Any]) -> Path:
    out_dir = target_root / layer
    out_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "id": _stable_id(layer[:3], text),
        "category": category,
        "layer": layer,
        "content": text,
        "metadata": metadata,
        "importance": float(max(0.05, min(1.0, importance))),
        "created_at": _iso(),
        "last_accessed": _iso(),
        "access_count": 0,
        "tags": sorted(set(tags)),
        "related_ids": [],
        "compressed": False,
        "summary": text[:180],
    }
    out = out_dir / f"{entry['id']}.json"
    out.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _extract_texts_from_json_obj(raw: Any) -> List[str]:
    texts: List[str] = []
    if isinstance(raw, dict) and any(k in raw for k in ["content", "summary", "text"]):
        text = str(raw.get("content") or raw.get("summary") or raw.get("text") or "").strip()
        if text:
            texts.append(text)
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                text = str(item.get("content") or item.get("summary") or item.get("text") or "").strip()
                if text:
                    texts.append(text)
    elif isinstance(raw, dict):
        for _, val in raw.items():
            if isinstance(val, dict):
                text = str(val.get("content") or val.get("summary") or val.get("text") or "").strip()
                if text:
                    texts.append(text)
    return texts


def restore_from_tar(root: Path, tar_path: Path, target_root: Path, max_items: int) -> Dict[str, Any]:
    restored_files: List[str] = []
    seen_hash = set()
    imported = 0

    with tarfile.open(tar_path, "r:gz") as tar:
        members = [m for m in tar.getmembers() if m.isfile()]
        for m in members:
            name = m.name
            if not name.endswith(".json"):
                continue
            if ("data/memory/" not in name) and ("workspace/memory/" not in name):
                continue
            f = tar.extractfile(m)
            if not f:
                continue
            try:
                raw = json.loads(f.read().decode("utf-8", errors="ignore"))
            except Exception:
                continue
            texts = _extract_texts_from_json_obj(raw)
            for text in texts:
                if imported >= max_items:
                    break
                if _is_noise(text):
                    continue
                h = hashlib.md5(text.encode("utf-8")).hexdigest()
                if h in seen_hash:
                    continue
                seen_hash.add(h)
                category, layer, tags, importance = _classify(text)
                out = _write_memory_entry(
                    target_root=target_root,
                    category=category,
                    layer=layer,
                    text=text,
                    tags=tags,
                    importance=importance,
                    metadata={"source": f"backup:{name}", "imported_at": _iso()},
                )
                restored_files.append(str(out))
                imported += 1
            if imported >= max_items:
                break

    return {"imported": imported, "files": restored_files}


def seed_skill_pack(target_root: Path) -> Dict[str, Any]:
    core_dir = target_root / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    p = core_dir / "SKILL_PACK_TRADING_OPS.md"
    content = """# Trading Ops Skill Pack

## Identity
- 我是交易系统司令部AI助手，具备自主分析、执行建议、风险提示与复盘能力。

## Duties
- 触发策略研发/回测/优化，并输出摘要与建议。
- 在授权边界内执行交易动作（开仓、平仓、减仓、加仓）。
- 跟踪并建议止盈止损调整，记录风险事件。
- 执行系统巡检，发现异常并推送告警与处置建议。
- 自动做经验总结，沉淀为可检索记忆。

## Boundaries
- 涉及高风险动作（大额、杠杆提升、批量平仓）必须二次确认。
- 禁止泄露密钥、凭据、敏感内部配置。
- 数据质量异常时必须降级并提示风险，不盲目执行。

## Action Skills
- strategy.research.run
- strategy.backtest.run
- strategy.optimize.run
- execution.open.force
- execution.close.force
- risk.sltp.adjust
- system.inspection.run
- alert.escalation.push
- memory.summary.daily
"""
    p.write_text(content, encoding="utf-8")
    return {"skill_pack": str(p)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore optimized memory from backup archive.")
    parser.add_argument("--tar", default="", help="Path to memory_backup.tar.gz (default: latest)")
    parser.add_argument("--target-root", default="workspace/memory", help="Target memory root")
    parser.add_argument("--max-items", type=int, default=300, help="Max imported entries")
    args = parser.parse_args()

    root = _project_root()
    tar_path = Path(args.tar).resolve() if args.tar else _latest_backup_tar(root)
    if not tar_path or not tar_path.exists():
        raise SystemExit("No backup tar found. Please provide --tar.")

    target_root = (root / args.target_root).resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    report = {
        "started_at": _iso(),
        "tar": str(tar_path),
        "target_root": str(target_root),
        "restore": restore_from_tar(root, tar_path, target_root, args.max_items),
        "seed": seed_skill_pack(target_root),
        "finished_at": _iso(),
    }
    out = root / "backups" / "memory-unify" / f"restore_report_{_now()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "report": str(out), "imported": report["restore"]["imported"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

