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
from typing import Any, Dict, List, Optional, Set

from src.modules.core.optimized_memory_system import (
    MemoryCategory,
    MemoryLayer,
    OptimizedMemorySystem,
)

from src.modules.memory.providers.native import NativeMemoryProvider
from src.modules.memory.memory_schema import attach_idempotency, trade_idempotency_fingerprint

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
    ALLOWED_WORKSPACE_FILES = {"COMMANDER_PROFILE.md"}
    ENV_ALLOW_ALL_WORKSPACE_FILES = "OPENCLAW_COMMANDER_ALLOW_ALL_WORKSPACE_FILES"

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
        self._last_recall_trace: Dict[str, Any] = {}
        self._recall_calls: int = 0
        self._recall_nonempty_hits: int = 0

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
        category: Any = "conversation",
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        # 兼容：部分调用侧会把 Enum（例如 UnifiedMemoryType）直接当 category 传入
        # 下游 _map_category/_map_layer 会对字符串调用 strip/lower，需先统一成字符串
        try:
            if hasattr(category, "value"):
                category = str(category.value)
            else:
                category = str(category)
        except Exception:
            category = "conversation"
        if self._should_skip_store(category=category, content=content, importance=importance, metadata=metadata):
            return "skipped"
        md = dict(metadata or {})
        md.setdefault("created_at", datetime.now().isoformat())
        md.setdefault("scope", scope or self.DEFAULT_SCOPE)
        fp = trade_idempotency_fingerprint(category, md)
        if fp:
            md = attach_idempotency(md, fp)
        exist = self._find_dedup_existing_id(category=str(category), fingerprint=fp, metadata=md)
        if exist:
            return exist
        mapped_category = self._map_category(category)
        mapped_layer = self._map_layer(category)
        memory_id = await self.memory_backend.remember(
            content=content,
            category=mapped_category,
            layer=mapped_layer,
            importance=importance,
            tags={f"scope:{md['scope']}", f"cat:{category}"},
            metadata=md,
        )
        # Lightweight markdown journaling (OpenClaw-style):
        # keep a human-readable daily trail alongside structured memory.
        try:
            self._append_daily_markdown_entry(
                content=content,
                category=str(category),
                importance=float(importance),
                metadata=md,
            )
        except Exception as e:
            logger.debug(f"append daily markdown skipped: {e}")
        return memory_id

    def _append_daily_markdown_entry(
        self,
        *,
        content: str,
        category: str,
        importance: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        text = str(content or "").strip()
        if len(text) < 2:
            return
        now = datetime.now()
        daily_dir = self.workspace_path / "memory" / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        daily_path = daily_dir / f"{now.strftime('%Y-%m-%d')}.md"
        scope = str((metadata or {}).get("scope", self.DEFAULT_SCOPE))
        line = (
            f"- {now.strftime('%H:%M:%S')} | cat={category} | scope={scope} "
            f"| imp={float(importance):.2f} | {text[:500]}\n"
        )
        if not daily_path.exists():
            header = (
                f"# Daily Memory {now.strftime('%Y-%m-%d')}\n\n"
                "Auto-generated journal from MemoryGateway.store.\n\n"
            )
            daily_path.write_text(header + line, encoding="utf-8")
            return
        with daily_path.open("a", encoding="utf-8") as f:
            f.write(line)

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
        rerank_enabled = False
        rerank_candidate_pool_size = 12
        try:
            if self.config_manager:
                cfg = self.config_manager.get_config_sync("memory", None, {}) or {}
                retrieval = cfg.get("retrieval", {}) if isinstance(cfg, dict) else {}
                if isinstance(retrieval, dict):
                    retrieval_mode = str(retrieval.get("mode", retrieval_mode))
                    vector_weight = float(retrieval.get("vector_weight", vector_weight))
                    bm25_weight = float(retrieval.get("bm25_weight", bm25_weight))
                    min_score = float(retrieval.get("min_score", min_score))
                    rr = retrieval.get("rerank", {})
                    if isinstance(rr, dict):
                        rerank_enabled = bool(rr.get("enabled", rerank_enabled))
                        rerank_candidate_pool_size = int(rr.get("candidate_pool_size", rerank_candidate_pool_size))
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
            rerank_enabled=rerank_enabled,
            rerank_candidate_pool_size=rerank_candidate_pool_size,
        )
        self._last_recall_trace = dict(result.trace or {})
        self._recall_calls += 1
        records: List[MemoryRecord] = []
        for item in result.items:
            md = dict(item.metadata or {})
            md.setdefault("score", item.score)
            md.setdefault("reasons", item.reasons)
            if self._is_noise_entry(memory_id=str(item.id), content=str(item.content), metadata=md):
                continue
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
        if records:
            self._recall_nonempty_hits += 1
        return records

    def get_last_recall_trace(self) -> Dict[str, Any]:
        """Best-effort recall trace for observability."""
        return dict(self._last_recall_trace or {})

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

    async def enforce_disk_policy(self) -> Dict[str, Any]:
        """
        Best-effort disk-driven cleanup for WORKING/HISTORY layers.
        Config: memory.disk_policy.max_bytes (int), memory.disk_policy.min_importance (float)
        """
        max_bytes = 0
        min_importance = 0.6
        try:
            cfg = self.config_manager.get_config_sync("memory", None, {}) if self.config_manager else {}
            disk = cfg.get("disk_policy", {}) if isinstance(cfg, dict) else {}
            if isinstance(disk, dict):
                max_bytes = int(disk.get("max_bytes", 0) or 0)
                min_importance = float(disk.get("min_importance", min_importance))
        except Exception:
            pass

        removed = 0
        if max_bytes and hasattr(self.memory_backend, "cleanup_by_disk_threshold"):
            try:
                removed = await self.memory_backend.cleanup_by_disk_threshold(
                    max_bytes=max_bytes,
                    min_importance=min_importance,
                )
            except Exception as e:
                logger.debug(f"disk_policy cleanup failed: {e}")
        return {"max_bytes": max_bytes, "min_importance": min_importance, "removed": removed}

    def get_summary_status(self) -> Dict[str, Any]:
        """Return best-effort counters for daily/weekly summaries."""
        out = {"daily": {"count": 0, "latest_date": None}, "weekly": {"count": 0, "latest_date": None}}
        try:
            mems = getattr(self.memory_backend, "_memories", {}) or {}
            for _id, entry in mems.items():
                md = dict(getattr(entry, "metadata", {}) or {})
                kind = str(md.get("kind") or "")
                date = md.get("date")
                if kind == "daily_summary":
                    out["daily"]["count"] += 1
                    if isinstance(date, str) and (out["daily"]["latest_date"] is None or date > out["daily"]["latest_date"]):
                        out["daily"]["latest_date"] = date
                if kind == "weekly_summary":
                    out["weekly"]["count"] += 1
                    if isinstance(date, str) and (out["weekly"]["latest_date"] is None or date > out["weekly"]["latest_date"]):
                        out["weekly"]["latest_date"] = date
        except Exception:
            pass
        return out

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
        **kwargs: Any,
    ) -> str:
        md = dict(metadata or {})
        if summary:
            md["summary"] = summary
        if source_module:
            md["source_module"] = source_module
        # Backward-compatible passthrough for legacy callers that provide
        # extra semantic hints (e.g. priority, tags) on add_memory().
        for key in ("priority", "tags", "memory_scope", "context", "timestamp"):
            if key in kwargs and kwargs[key] is not None:
                md[key] = kwargs[key]
        importance = float(kwargs.get("importance", md.pop("importance", 0.5)))
        return await self.store(
            content=content,
            category=memory_type or "conversation",
            importance=importance,
            metadata=md,
        )

    async def recent_conversation(
        self,
        *,
        scope: Optional[str] = None,
        limit: int = 6,
    ) -> List[MemoryRecord]:
        """
        Return most recent conversation memories, independent of query similarity.
        This is the "sessionMemory" style safety net to prevent amnesia.
        """
        try:
            memories = getattr(self.memory_backend, "_memories", {})
            items = []
            for _id, entry in (memories or {}).items():
                try:
                    if getattr(entry, "category", None) != MemoryCategory.CONVERSATION:
                        continue
                    md = dict(getattr(entry, "metadata", {}) or {})
                    if self._is_noise_entry(memory_id=str(_id), content=str(getattr(entry, "content", "")), metadata=md):
                        continue
                    if scope and str(md.get("scope", "")).strip() != scope:
                        continue
                    created_at = getattr(entry, "created_at", None)
                    if created_at is None:
                        created_at_raw = md.get("created_at")
                        created_at = datetime.fromisoformat(created_at_raw) if isinstance(created_at_raw, str) else datetime.now()
                    items.append((created_at, _id, entry, md))
                except Exception:
                    continue
            items.sort(key=lambda x: x[0], reverse=True)
            out: List[MemoryRecord] = []
            for created_at, _id, entry, md in items[: max(1, int(limit))]:
                out.append(
                    MemoryRecord(
                        id=str(_id),
                        content=str(getattr(entry, "content", "")),
                        importance=float(getattr(entry, "importance", 0.5)),
                        metadata=md,
                        timestamp=created_at.isoformat(),
                        access_count=int(md.get("access_count", 0)) if isinstance(md, dict) else 0,
                    )
                )
            return out
        except Exception:
            return []

    def _is_noise_entry(self, memory_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        text = (content or "").strip().lower()
        if not text:
            return True
        try:
            cfg = self.config_manager.get_config_sync("memory", None, {}) if self.config_manager else {}
            auto = cfg.get("auto_capture", {}) if isinstance(cfg, dict) else {}
            policy = auto.get("policy", {}) if isinstance(auto, dict) else {}
            deny_ids = {str(x) for x in (policy.get("deny_memory_ids", []) or [])}
            if memory_id and memory_id in deny_ids:
                return True
            deny_contains = [str(x).lower() for x in (policy.get("deny_content_contains", []) or [])]
            for frag in deny_contains:
                if frag and frag in text:
                    return True
        except Exception:
            pass
        return False

    def _should_skip_store(
        self,
        *,
        category: str,
        content: str,
        importance: float,
        metadata: Optional[Dict[str, Any]],
    ) -> bool:
        try:
            cfg = {}
            if self.config_manager:
                cfg = self.config_manager.get_config_sync("memory", None, {}) or {}
            auto = cfg.get("auto_capture", {}) if isinstance(cfg, dict) else {}
            if not isinstance(auto, dict) or not bool(auto.get("enabled", True)):
                return False
            policy = auto.get("policy", {}) if isinstance(auto, dict) else {}
            if not isinstance(policy, dict):
                return False

            deny_categories = set(policy.get("deny_categories", []) or [])
            if category in deny_categories:
                return True

            deny_contains = [str(x).lower() for x in (policy.get("deny_content_contains", []) or [])]
            lowered = (content or "").lower()
            for frag in deny_contains:
                if frag and frag in lowered:
                    return True

            md = dict(metadata or {})
            tags_val = md.get("tags")
            tags: Set[str] = set()
            if isinstance(tags_val, (list, set, tuple)):
                tags = {str(t) for t in tags_val}
            deny_tags = set(policy.get("deny_tags", []) or [])
            if tags and deny_tags and any(t in deny_tags for t in tags):
                return True

            min_by_cat = policy.get("min_importance_by_category", {}) if isinstance(policy, dict) else {}
            if isinstance(min_by_cat, dict):
                min_imp = float(min_by_cat.get(category, 0.0))
                if float(importance) < min_imp:
                    return True
        except Exception:
            return False
        return False

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

    # ---------- hierarchical/unified legacy compatibility ----------
    async def save_daily_memory(self, content: str) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        await self.store(
            content=content or "",
            category="daily_summary",
            importance=0.6,
            metadata={"kind": "daily_summary", "date": today, "source": "memory_gateway"},
        )

    async def load_recent_memories(self, days: int = 2) -> List[str]:
        cutoff = datetime.now() - timedelta(days=max(1, int(days or 1)))
        entries = await self.memory_backend.recall(
            query="",
            category=MemoryCategory.DAILY_SUMMARY,
            limit=max(8, int(days or 2) * 8),
        )
        out: List[str] = []
        for e in sorted(entries, key=lambda x: x.created_at, reverse=True):
            try:
                if e.created_at >= cutoff:
                    txt = str(getattr(e, "content", "") or "").strip()
                    if txt:
                        out.append(txt)
            except Exception:
                continue
        return out

    async def save_lesson_learned(self, lesson_type: str, lesson: str, context: str) -> None:
        payload = f"[{lesson_type}] {lesson}\n上下文: {context}".strip()
        await self.store(
            content=payload,
            category="lesson_learned",
            importance=0.75,
            metadata={"lesson_type": lesson_type, "context": context, "source": "memory_gateway"},
        )

    async def save_knowledge_document(
        self,
        title: str,
        content: str,
        *,
        knowledge_type: str = "governance_rule",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        body = f"{title}\n\n{content}".strip()
        md = dict(metadata or {})
        md.update({"knowledge_type": knowledge_type, "title": title, "source": "memory_gateway"})
        return await self.store(
            content=body,
            category="knowledge_document",
            importance=0.9,
            metadata=md,
        )

    def get_layered_memory_overview(self) -> Dict[str, Any]:
        mems = getattr(self.memory_backend, "_memories", {}) or {}
        semantic_layers = {
            "short_term_context": 0,
            "working_memory": 0,
            "long_term_experience": 0,
            "knowledge_base": 0,
        }
        kind_counts: Dict[str, int] = {}
        for _id, entry in mems.items():
            layer = getattr(entry, "layer", None)
            layer_value = getattr(layer, "value", str(layer or ""))
            md = dict(getattr(entry, "metadata", {}) or {})
            kind = str(md.get("kind") or md.get("knowledge_type") or "").strip().lower()
            if layer_value == "core":
                semantic_layers["knowledge_base"] += 1
            elif layer_value == "experience":
                semantic_layers["long_term_experience"] += 1
            elif layer_value == "working":
                if kind in {"daily_summary", "weekly_summary"}:
                    semantic_layers["working_memory"] += 1
                else:
                    semantic_layers["short_term_context"] += 1
            elif layer_value == "history":
                semantic_layers["long_term_experience"] += 1
            if kind:
                kind_counts[kind] = int(kind_counts.get(kind, 0)) + 1
        return {
            "semantic_layers": semantic_layers,
            "kind_counts": kind_counts,
        }

    async def consolidate_memories(self) -> None:
        if hasattr(self.memory_backend, "cleanup_expired"):
            try:
                await self.memory_backend.cleanup_expired()
            except Exception:
                pass

    def get_workspace_memory(self, filename: Optional[str] = None) -> Dict[str, str]:
        allow_all = False
        try:
            env = __import__("os").environ
            v = str((env.get(self.ENV_ALLOW_ALL_WORKSPACE_FILES, "") or "")).strip()
            unrestricted = str((env.get("OPENCLAW_COMMANDER_UNRESTRICTED", "1") or "")).strip().lower() not in {
                "0", "false", "no", "off"
            }
            allow_all = (v in {
                "1",
                "true",
                "True",
                "yes",
                "YES",
            }) or unrestricted
        except Exception:
            allow_all = False

        if allow_all:
            files = [filename] if filename else sorted([p.name for p in self.workspace_path.glob("*.md")])
        else:
            files = [filename] if filename else sorted(self.ALLOWED_WORKSPACE_FILES)
        result: Dict[str, str] = {}
        for name in files:
            if not allow_all and name not in self.ALLOWED_WORKSPACE_FILES:
                continue
            path = self.workspace_path / name
            if path.exists():
                try:
                    result[name] = path.read_text(encoding="utf-8")
                except Exception as e:
                    logger.warning(f"读取工作区记忆文件失败 {name}: {e}")
        return result

    async def update_workspace_memory(self, filename: str, content: str, notify_user: bool = True) -> bool:
        allow_all = False
        try:
            env = __import__("os").environ
            v = str((env.get(self.ENV_ALLOW_ALL_WORKSPACE_FILES, "") or "")).strip()
            unrestricted = str((env.get("OPENCLAW_COMMANDER_UNRESTRICTED", "1") or "")).strip().lower() not in {
                "0", "false", "no", "off"
            }
            allow_all = (v in {
                "1",
                "true",
                "True",
                "yes",
                "YES",
            }) or unrestricted
        except Exception:
            allow_all = False
        if not allow_all and filename not in self.ALLOWED_WORKSPACE_FILES:
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
                "recall": {
                    "calls": self._recall_calls,
                    "nonempty_hits": self._recall_nonempty_hits,
                    "hit_rate": (
                        round(self._recall_nonempty_hits / max(self._recall_calls, 1), 4)
                    ),
                },
            },
            "backend": stats,
            "quality": self.get_quality_metrics(),
        }

    def get_quality_metrics(self) -> Dict[str, Any]:
        """Distribution + duplication hints for governance (best-effort, in-process)."""
        thresh = 8
        try:
            cfg = self.config_manager.get_config_sync("memory", None, {}) if self.config_manager else {}
            qm = (cfg.get("quality_metrics") or {}) if isinstance(cfg, dict) else {}
            if isinstance(qm, dict):
                thresh = int(qm.get("short_content_threshold", thresh))
        except Exception:
            pass

        mems = getattr(self.memory_backend, "_memories", {}) or {}
        total = len(mems)
        empty_content = 0
        short_content = 0
        by_layer: Dict[str, int] = {}
        by_cat: Dict[str, int] = {}
        trade_with_order = 0
        trade_total = 0
        idem_dup: Dict[str, int] = {}

        for _id, entry in mems.items():
            layer = getattr(entry, "layer", None)
            if layer is not None:
                lk = getattr(layer, "value", str(layer))
                by_layer[lk] = by_layer.get(lk, 0) + 1
            cat = getattr(entry, "category", None)
            ck = getattr(cat, "value", str(cat)) if cat else "unknown"
            by_cat[ck] = by_cat.get(ck, 0) + 1
            c = str(getattr(entry, "content", "") or "").strip()
            if not c:
                empty_content += 1
            elif len(c) < thresh:
                short_content += 1
            if ck == "trade_record":
                trade_total += 1
                md = dict(getattr(entry, "metadata", {}) or {})
                if md.get("order_id") or md.get("orderId"):
                    trade_with_order += 1
            md2 = dict(getattr(entry, "metadata", {}) or {})
            ik = md2.get("idempotency_key")
            if ik:
                sik = str(ik)
                idem_dup[sik] = idem_dup.get(sik, 0) + 1

        duplicate_idem_keys = sum(1 for _k, v in idem_dup.items() if v > 1)
        top_duplicate_idem = sorted(
            ((k, v) for k, v in idem_dup.items() if v > 1), key=lambda x: -x[1]
        )[:12]

        return {
            "total_entries": total,
            "empty_content": empty_content,
            "short_content_lt": short_content,
            "short_content_threshold": thresh,
            "by_layer": by_layer,
            "by_category": by_cat,
            "trade_record_total": trade_total,
            "trade_record_with_order_id": trade_with_order,
            "duplicate_idempotency_keys": duplicate_idem_keys,
            "top_duplicate_idempotency_keys": [{"key": k, "count": v} for k, v in top_duplicate_idem],
        }

    def _find_dedup_existing_id(
        self,
        *,
        category: str,
        fingerprint: Optional[str],
        metadata: Dict[str, Any],
    ) -> Optional[str]:
        if not fingerprint:
            return None
        try:
            cfg = self.config_manager.get_config_sync("memory", None, {}) if self.config_manager else {}
            dedup = cfg.get("dedup", {}) if isinstance(cfg, dict) else {}
            if not isinstance(dedup, dict) or not bool(dedup.get("enabled", True)):
                return None
            cats = [str(c).strip().lower() for c in (dedup.get("categories") or ["trade_record", "risk_event"])]
            if str(category).strip().lower() not in cats:
                return None
            window = int(dedup.get("window_sec", 172800))
            cutoff = datetime.now() - timedelta(seconds=max(window, 60))
            target_cat = self._map_category(category)
            mems = getattr(self.memory_backend, "_memories", {}) or {}
            for mid, entry in mems.items():
                if getattr(entry, "category", None) != target_cat:
                    continue
                created = getattr(entry, "created_at", None)
                if created is not None and created < cutoff:
                    continue
                emd = dict(getattr(entry, "metadata", {}) or {})
                other = trade_idempotency_fingerprint(category, emd)
                if other and other == fingerprint:
                    return str(mid)
        except Exception:
            return None
        return None

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
            "knowledge_document": MemoryCategory.TRADING_RULE,
            "market_observation": MemoryCategory.MARKET_OBSERVATION,
            "market_regime_case": MemoryCategory.MARKET_OBSERVATION,
            "risk_event": MemoryCategory.RISK_EVENT,
            "execution_incident": MemoryCategory.RISK_EVENT,
            "user_preference": MemoryCategory.USER_PREFERENCE,
            "decision": MemoryCategory.LESSON_LEARNED,
            "agent_misjudgment_case": MemoryCategory.LESSON_LEARNED,
            "strategy_drift_case": MemoryCategory.LESSON_LEARNED,
            "tuning_attempt": MemoryCategory.LESSON_LEARNED,
            "tuning_result": MemoryCategory.LESSON_LEARNED,
            "approved_rule_change": MemoryCategory.LESSON_LEARNED,
            "rejected_rule_change": MemoryCategory.LESSON_LEARNED,
            "weekly_lesson": MemoryCategory.LESSON_LEARNED,
            "system_state": MemoryCategory.DAILY_SUMMARY,
            "daily_summary": MemoryCategory.DAILY_SUMMARY,
            "lesson_learned": MemoryCategory.LESSON_LEARNED,
        }
        return mapping.get(key, MemoryCategory.CONVERSATION)

    def _map_layer(self, category: str) -> MemoryLayer:
        key = (category or "").strip().lower()
        if key in {"trading_rule", "user_preference", "knowledge_document"}:
            return MemoryLayer.CORE
        if key in {
            "decision",
            "lesson_learned",
            "trade_record",
            "risk_event",
            "market_regime_case",
            "execution_incident",
            "strategy_drift_case",
            "agent_misjudgment_case",
            "tuning_attempt",
            "tuning_result",
            "approved_rule_change",
            "rejected_rule_change",
            "weekly_lesson",
        }:
            return MemoryLayer.EXPERIENCE
        if key in {"daily_summary"}:
            return MemoryLayer.WORKING
        return MemoryLayer.WORKING
