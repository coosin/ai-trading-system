import json
import os
from datetime import datetime, timedelta

import pytest

from src.modules.core.optimized_memory_system import (
    MemoryCategory,
    MemoryLayer,
    OptimizedMemorySystem,
)


def _memory_payload(entry_id: str, layer: str, created_at: datetime) -> dict:
    return {
        "id": entry_id,
        "category": MemoryCategory.TRADE_RECORD.value,
        "layer": layer,
        "content": f"memory:{entry_id}",
        "metadata": {},
        "importance": 0.5,
        "created_at": created_at.isoformat(),
        "last_accessed": created_at.isoformat(),
        "access_count": 0,
        "tags": [],
        "related_ids": [],
        "compressed": False,
        "summary": None,
    }


@pytest.mark.asyncio
async def test_optimized_memory_system_limits_startup_working_and_experience_files(tmp_path):
    storage = tmp_path / "memory"
    workspace = tmp_path / "workspace"
    (workspace).mkdir()
    (workspace / "COMMANDER_PROFILE.md").write_text("profile", encoding="utf-8")
    (storage / "working").mkdir(parents=True)
    (storage / "experience").mkdir(parents=True)

    now = datetime.now()
    for idx in range(4):
        created = now - timedelta(hours=idx)
        payload = _memory_payload(f"w{idx}", MemoryLayer.WORKING.value, created)
        path = storage / "working" / f"w{idx}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        ts = created.timestamp()
        os.utime(path, (ts, ts))

    for idx in range(4):
        created = now - timedelta(days=idx)
        payload = _memory_payload(f"e{idx}", MemoryLayer.EXPERIENCE.value, created)
        path = storage / "experience" / f"e{idx}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        ts = created.timestamp()
        os.utime(path, (ts, ts))

    mem = OptimizedMemorySystem(
        storage_path=str(storage),
        workspace_path=str(workspace),
        working_days_recent=7,
        working_json_max_files=2,
        experience_json_max_files=2,
    )

    assert await mem.initialize() is True
    assert mem._stats["by_layer"][MemoryLayer.WORKING] == 2
    assert mem._stats["by_layer"][MemoryLayer.EXPERIENCE] == 2
    assert {"w0", "w1"} == {e.id for e in mem._memories.values() if e.layer == MemoryLayer.WORKING}
    assert {"e0", "e1"} == {e.id for e in mem._memories.values() if e.layer == MemoryLayer.EXPERIENCE}
