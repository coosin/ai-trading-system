"""
Unified memory gateway.

Provides a single entrypoint for memory operations with:
- scope-aware retrieval/storage metadata
- structured memory (recall source) + workspace markdown (journal source) split
- compatibility wrappers for legacy modules
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.modules.core.optimized_memory_system import (
    MemoryCategory,
    MemoryLayer,
    OptimizedMemorySystem,
)

from src.modules.memory.providers.native import NativeMemoryProvider

logger = logging.getLogger(__name__)


@dataclass
class MemoryRecord:
    """Compatibility memory record for old call sites."""

    id: str
    content: str
    importance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "importance": self.importance,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "access_count": self.access_count,
        }


class MemoryGateway:
    """
    Unified gateway used by MainController and API entrypoints.
    """

    DEFAULT_SCOPE = "global"
    ALLOWED_WORKSPACE_FILES = {"SOUL.md", "IDENTITY.md", "USER.md", "INSTRUCTIONS.md", "TRADING.md"}

    def __init__(
        self,
        memory_backend: OptimizedMemorySystem,
        workspace_path: str,
        config_manager: Any = None,
    ):
        self.memory_backend = memory_backend
        self.workspace_path = Path(workspace_path)
        self.config_manager = config_manager
        self.provider = NativeMemoryProvider(backend=memory_backend)

    @classmethod
    async def create(
        cls,
        memory_backend: OptimizedMemorySystem,
        workspace_path: str,
        config_manager: Any = None,
    ) -> "MemoryGateway":
        gateway = cls(
            memory_backend=memory_backend,
            workspace_path=workspace_path,
            config_manager=config_manager,
        )
        try:
            gateway.workspace_path.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            fallback = Path("/tmp/openclaw_workspace")
            fallback.mkdir(parents=True, exist_ok=True)
            gateway.workspace_path = fallback
            logger.warning(f"记忆网关工作区权限不足，使用备用路径: {fallback}")
        return gateway

    # ---------- generic API ----------
    async def store(
        self,
        content: str,
        *,
        scope: str = DEFAULT_SCOPE,
        category: str = "conversation",
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        md = dict(metadata or {})
        md.setdefault("scope", scope or self.DEFAULT_SCOPE)
        mapped_category = self._map_category(category)
        mapped_layer = self._map_layer(category)
        return await self.memory_backend.remember(
            content=content,
            category=mapped_category,
            layer=mapped_layer,
            importance=importance,
            tags={f"scope:{md['scope']}", f"cat:{category}"},
            metadata=md,
        )

    async def recall(
        self,
        query: str,
        *,
        scope: Optional[str] = None,
        limit: int = 10,
        min_importance: float = 0.0,
    ) -> List[MemoryRecord]:
        # Resolve retrieval config (if available)
        retrieval_mode = "hybrid"
        vector_weight = 0.7
        bm25_weight = 0.3
        min_score = 0.0
        try:
            if self.config_manager:
                cfg = self.config_manager.get_config_sync("memory", None, {}) or {}
                retrieval = cfg.get("retrieval", {}) if isinstance(cfg, dict) else {}
                if isinstance(retrieval, dict):
                    retrieval_mode = str(retrieval.get("mode", retrieval_mode))
                    vector_weight = float(retrieval.get("vector_weight", vector_weight))
                    bm25_weight = float(retrieval.get("bm25_weight", bm25_weight))
                    min_score = float(retrieval.get("min_score", min_score))
        except Exception:
            pass

        result = await self.provider.recall(
            query=query,
            scope=scope,
            limit=limit,
            min_importance=min_importance,
            retrieval_mode=retrieval_mode,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
            min_score=min_score,
        )
        records: List[MemoryRecord] = []
        for item in result.items:
            md = dict(item.metadata or {})
            md.setdefault("score", item.score)
            md.setdefault("reasons", item.reasons)
            records.append(
                MemoryRecord(
                    id=item.id,
                    content=item.content,
                    importance=float(item.importance),
                    metadata=md,
                    timestamp=datetime.now().isoformat(),
                    access_count=int(md.get("access_count", 0)) if isinstance(md, dict) else 0,
                )
            )
        return records

    async def update(self, memory_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        try:
            old = getattr(self.memory_backend, "_memories", {}).get(memory_id)
            if old is None:
                return False
            await self.memory_backend.forget(memory_id)
            new_metadata = dict(getattr(old, "metadata", {}) or {})
            if metadata:
                new_metadata.update(metadata)
            await self.memory_backend.remember(
                content=content,
                category=getattr(old, "category", MemoryCategory.CONVERSATION),
                layer=getattr(old, "layer", MemoryLayer.WORKING),
                importance=float(getattr(old, "importance", 0.5)),
                tags=set(getattr(old, "tags", set())),
                metadata=new_metadata,
            )
            return True
        except Exception as e:
            logger.error(f"更新记忆失败: {e}")
            return False

    async def forget(self, memory_id: str) -> bool:
        return await self.memory_backend.forget(memory_id)

    # ---------- legacy compatibility ----------
    async def retrieve_memories(
        self,
        query: str,
        min_importance: float = 0.0,
        limit: int = 10,
        memory_type: Optional[str] = None,
    ) -> List[MemoryRecord]:
        scope = None
        if memory_type and memory_type.startswith("scope:"):
            scope = memory_type.split(":", 1)[1].strip()
        return await self.recall(
            query=query,
            scope=scope,
            limit=limit,
            min_importance=min_importance,
        )

    async def add_memory(
        self,
        memory_type: str,
        content: str,
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        source_module: Optional[str] = None,
    ) -> str:
        md = dict(metadata or {})
        if summary:
            md["summary"] = summary
        if source_module:
            md["source_module"] = source_module
        return await self.store(
            content=content,
            category=memory_type or "conversation",
            importance=float(md.pop("importance", 0.5)),
            metadata=md,
        )

    async def process_user_input(self, user_input: str) -> Dict[str, Any]:
        text = (user_input or "").strip()
        if not text:
            return {"recorded": False, "message": "empty_input"}

        lowered = text.lower()
        category = "conversation"
        blacklist_updated = False
        authorization_updated = False
        if any(k in lowered for k in ["黑名单", "禁区", "不要操作"]):
            category = "risk_event"
            blacklist_updated = True
        elif any(k in lowered for k in ["全权", "授权", "自动交易"]):
            category = "decision"
            authorization_updated = True
        elif any(k in lowered for k in ["偏好", "喜欢", "不喜欢"]):
            category = "user_preference"

        memory_id = await self.store(
            content=text,
            category=category,
            importance=0.8 if (blacklist_updated or authorization_updated) else 0.6,
            metadata={"source": "user_input"},
        )
        return {
            "recorded": True,
            "memory_id": memory_id,
            "message": "stored",
            "blacklist_updated": blacklist_updated,
            "authorization_updated": authorization_updated,
        }

    async def add_system_instruction(self, instruction: str, context: str = "") -> str:
        content = f"{instruction}\n\n上下文: {context}".strip()
        return await self.store(
            content=content,
            category="trading_rule",
            importance=0.9,
            metadata={"source": "api_instruction"},
        )

    async def add_user_preference(self, key: str, value: Any, description: str = "") -> str:
        content = f"{key}: {value}" + (f"\n备注: {description}" if description else "")
        return await self.store(
            content=content,
            category="user_preference",
            importance=0.8,
            metadata={"preference_key": key, "source": "api_preference"},
        )

    async def summarize_trade_history(self, days: int = 30) -> str:
        cutoff = datetime.now() - timedelta(days=max(days, 1))
        entries = await self.memory_backend.recall(query="", category=MemoryCategory.TRADE_RECORD, limit=500)
        selected = [e for e in entries if e.created_at >= cutoff]
        if not selected:
            return f"{days}天内暂无交易记忆。"
        lines = [
            f"- {e.created_at.strftime('%Y-%m-%d %H:%M')} | {e.content[:120]}"
            for e in sorted(selected, key=lambda x: x.created_at, reverse=True)[:50]
        ]
        return "\n".join(lines)

    def get_workspace_memory(self, filename: Optional[str] = None) -> Dict[str, str]:
        files = [filename] if filename else sorted(self.ALLOWED_WORKSPACE_FILES)
        result: Dict[str, str] = {}
        for name in files:
            if name not in self.ALLOWED_WORKSPACE_FILES:
                continue
            path = self.workspace_path / name
            if path.exists():
                try:
                    result[name] = path.read_text(encoding="utf-8")
                except Exception as e:
                    logger.warning(f"读取工作区记忆文件失败 {name}: {e}")
        return result

    async def update_workspace_memory(self, filename: str, content: str, notify_user: bool = True) -> bool:
        if filename not in self.ALLOWED_WORKSPACE_FILES:
            return False
        try:
            path = self.workspace_path / filename
            path.write_text(content or "", encoding="utf-8")
            await self.store(
                content=f"update_workspace_memory: {filename}",
                category="decision",
                importance=0.6,
                metadata={"filename": filename, "notify_user": bool(notify_user)},
            )
            return True
        except Exception as e:
            logger.error(f"更新工作区记忆文件失败: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        stats = self.memory_backend.get_stats()
        return {
            "gateway": {
                "workspace_path": str(self.workspace_path),
                "allowed_workspace_files": sorted(self.ALLOWED_WORKSPACE_FILES),
                "default_scope": self.DEFAULT_SCOPE,
            },
            "backend": stats,
        }

    async def build_context(self, query: str, max_tokens: int = 2000) -> str:
        return await self.memory_backend.build_context(query, max_tokens=max_tokens)

    async def remember(
        self,
        content: str,
        category: str = "conversation",
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        return await self.store(
            content=content,
            category=category,
            importance=importance,
            metadata=metadata,
        )

    # ---------- internal helpers ----------
    def _map_category(self, category: str) -> MemoryCategory:
        key = (category or "").strip().lower()
        mapping = {
            "conversation": MemoryCategory.CONVERSATION,
            "trade_record": MemoryCategory.TRADE_RECORD,
            "trading_rule": MemoryCategory.TRADING_RULE,
            "market_observation": MemoryCategory.MARKET_OBSERVATION,
            "risk_event": MemoryCategory.RISK_EVENT,
            "user_preference": MemoryCategory.USER_PREFERENCE,
            "decision": MemoryCategory.LESSON_LEARNED,
            "system_state": MemoryCategory.DAILY_SUMMARY,
        }
        return mapping.get(key, MemoryCategory.CONVERSATION)

    def _map_layer(self, category: str) -> MemoryLayer:
        key = (category or "").strip().lower()
        if key in {"trading_rule", "user_preference"}:
            return MemoryLayer.CORE
        if key in {"decision", "trade_record", "risk_event"}:
            return MemoryLayer.EXPERIENCE
        return MemoryLayer.WORKING
