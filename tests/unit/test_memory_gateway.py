import pytest

from src.modules.memory.memory_gateway import MemoryGateway


class _FakeEntry:
    def __init__(self, entry_id, content, importance, metadata, created_at, access_count=0):
        self.id = entry_id
        self.content = content
        self.importance = importance
        self.metadata = metadata
        self.created_at = created_at
        self.access_count = access_count
        self.category = "conversation"
        self.layer = "working"
        self.tags = set()


class _FakeBackend:
    def __init__(self):
        from datetime import datetime

        self._memories = {}
        self._dt = datetime
        self._counter = 0

    async def remember(self, content, category=None, layer=None, importance=0.5, tags=None, metadata=None):
        self._counter += 1
        entry_id = f"m{self._counter}"
        self._memories[entry_id] = _FakeEntry(
            entry_id=entry_id,
            content=content,
            importance=importance,
            metadata=metadata or {},
            created_at=self._dt.now(),
            access_count=0,
        )
        return entry_id

    async def recall(self, query, limit=10, category=None):
        items = list(self._memories.values())
        if query:
            items = [i for i in items if query.lower() in i.content.lower()]
        return items[:limit]

    async def forget(self, memory_id):
        return self._memories.pop(memory_id, None) is not None

    async def build_context(self, query, max_tokens=2000):
        return f"context:{query}:{max_tokens}"

    def get_stats(self):
        return {"total_memories": len(self._memories)}


@pytest.mark.asyncio
async def test_memory_gateway_store_and_scope_recall(tmp_path):
    backend = _FakeBackend()
    gateway = await MemoryGateway.create(backend, str(tmp_path))

    await gateway.store("BTC signal", scope="global", category="decision", importance=0.9)
    await gateway.store("ETH private", scope="agent:a1", category="decision", importance=0.9)

    scoped = await gateway.recall("signal", scope="global", limit=10)
    assert len(scoped) == 1
    assert scoped[0].content == "BTC signal"
    assert isinstance(scoped[0].metadata, dict)
    trace = gateway.get_last_recall_trace()
    assert isinstance(trace, dict)
    assert "provider" in trace


@pytest.mark.asyncio
async def test_memory_gateway_legacy_methods(tmp_path):
    backend = _FakeBackend()
    gateway = await MemoryGateway.create(backend, str(tmp_path))

    memory_id = await gateway.add_user_preference("risk", "low", "keep drawdown small")
    assert memory_id

    result = await gateway.retrieve_memories("risk", min_importance=0.0, limit=5)
    assert result
    assert "risk" in result[0].content


@pytest.mark.asyncio
async def test_memory_gateway_workspace_file_update(tmp_path):
    backend = _FakeBackend()
    gateway = await MemoryGateway.create(backend, str(tmp_path))

    ok = await gateway.update_workspace_memory("USER.md", "hello", notify_user=False)
    assert ok is True

    files = gateway.get_workspace_memory("USER.md")
    assert files["USER.md"] == "hello"


@pytest.mark.asyncio
async def test_memory_gateway_add_memory_accepts_legacy_kwargs(tmp_path):
    backend = _FakeBackend()
    gateway = await MemoryGateway.create(backend, str(tmp_path))

    memory_id = await gateway.add_memory(
        memory_type="strategy",
        content="legacy add_memory payload",
        source_module="ai_core_decision_engine",
        importance=0.9,
        priority="high",
        tags=["ai_strategy", "auto_generated"],
    )
    assert memory_id

    recalled = await gateway.retrieve_memories("legacy add_memory", min_importance=0.0, limit=5)
    assert recalled
    assert recalled[0].importance == 0.9
    assert recalled[0].metadata.get("priority") == "high"
    assert recalled[0].metadata.get("tags") == ["ai_strategy", "auto_generated"]
