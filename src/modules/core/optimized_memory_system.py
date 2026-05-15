"""
优化版统一记忆系统 V3.0

整合所有记忆功能，解决以下问题：
1. 统一存储路径和接口
2. 添加记忆索引和快速检索
3. 实现记忆压缩和摘要
4. 添加记忆关联和遗忘机制
5. 支持多层级记忆管理

记忆层级：
- 核心层 (Core): 系统身份、用户偏好、核心规则 (永久保留)
- 工作层 (Working): 当前会话、今日交易、市场观察 (短期记忆)
- 经验层 (Experience): 交易经验、教训、成功模式 (长期记忆)
- 历史层 (History): 历史交易记录、市场数据 (按需加载)
"""

import asyncio
import logging
import json
import os
import re
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict
import aiofiles
import threading
import os

logger = logging.getLogger(__name__)


class MemoryLayer(Enum):
    CORE = "core"
    WORKING = "working"
    EXPERIENCE = "experience"
    HISTORY = "history"


class MemoryCategory(Enum):
    IDENTITY = "identity"
    USER_PREFERENCE = "user_preference"
    TRADING_RULE = "trading_rule"
    DAILY_SUMMARY = "daily_summary"
    TRADE_RECORD = "trade_record"
    MARKET_OBSERVATION = "market_observation"
    RISK_EVENT = "risk_event"
    LESSON_LEARNED = "lesson_learned"
    SUCCESS_PATTERN = "success_pattern"
    CONVERSATION = "conversation"


@dataclass
class MemoryEntry:
    id: str
    category: MemoryCategory
    layer: MemoryLayer
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    tags: Set[str] = field(default_factory=set)
    related_ids: Set[str] = field(default_factory=set)
    compressed: bool = False
    summary: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value,
            "layer": self.layer.value,
            "content": self.content,
            "metadata": self.metadata,
            "importance": self.importance,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "tags": list(self.tags),
            "related_ids": list(self.related_ids),
            "compressed": self.compressed,
            "summary": self.summary
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        return cls(
            id=data["id"],
            category=MemoryCategory(data["category"]),
            layer=MemoryLayer(data["layer"]),
            content=data["content"],
            metadata=data.get("metadata", {}),
            importance=data.get("importance", 0.5),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            access_count=data.get("access_count", 0),
            tags=set(data.get("tags", [])),
            related_ids=set(data.get("related_ids", [])),
            compressed=data.get("compressed", False),
            summary=data.get("summary")
        )


@dataclass
class MemoryIndex:
    tag_index: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    category_index: Dict[MemoryCategory, Set[str]] = field(default_factory=lambda: defaultdict(set))
    date_index: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    symbol_index: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    keyword_index: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    
    def add_entry(self, entry: MemoryEntry):
        entry_id = entry.id
        
        for tag in entry.tags:
            self.tag_index[tag].add(entry_id)
        
        self.category_index[entry.category].add(entry_id)
        
        date_key = entry.created_at.strftime("%Y-%m-%d")
        self.date_index[date_key].add(entry_id)
        
        if "symbol" in entry.metadata:
            symbol = entry.metadata["symbol"]
            self.symbol_index[symbol].add(entry_id)
        
        keywords = self._extract_keywords(entry.content)
        for kw in keywords:
            self.keyword_index[kw].add(entry_id)
    
    def remove_entry(self, entry: MemoryEntry):
        entry_id = entry.id
        
        for tag in entry.tags:
            self.tag_index[tag].discard(entry_id)
        
        self.category_index[entry.category].discard(entry_id)
        
        date_key = entry.created_at.strftime("%Y-%m-%d")
        self.date_index[date_key].discard(entry_id)
        
        if "symbol" in entry.metadata:
            symbol = entry.metadata["symbol"]
            self.symbol_index[symbol].discard(entry_id)
        
        keywords = self._extract_keywords(entry.content)
        for kw in keywords:
            self.keyword_index[kw].discard(entry_id)
    
    def _extract_keywords(self, content: str) -> List[str]:
        keywords = []
        trading_keywords = [
            "开仓", "平仓", "止损", "止盈", "做多", "做空",
            "盈利", "亏损", "爆仓", "强平", "仓位", "杠杆",
            "BTC", "ETH", "SOL", "BNB", "USDT"
        ]
        for kw in trading_keywords:
            if kw in content:
                keywords.append(kw)
        return keywords
    
    def search(self, query: str, limit: int = 10) -> Set[str]:
        results = set()
        
        if query in self.tag_index:
            results.update(self.tag_index[query])
        
        if query in self.symbol_index:
            results.update(self.symbol_index[query])
        
        if query in self.keyword_index:
            results.update(self.keyword_index[query])
        
        return results


class OptimizedMemorySystem:
    """
    优化版统一记忆系统 V3.0
    
    特性：
    1. 统一存储路径：/app/data/memory (Docker) 或 workspace/memory (本地)
    2. 多层级记忆：核心层、工作层、经验层、历史层
    3. 智能索引：标签、分类、日期、交易对、关键词索引
    4. 记忆压缩：自动压缩历史记忆，保留摘要
    5. 关联机制：记忆之间可以建立关联
    6. 遗忘机制：根据重要性和访问频率自动清理
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        workspace_path: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        config_manager: Any = None,
        *,
        working_days_recent: int = 3,
        working_json_max_files: Optional[int] = 800,
        experience_json_max_files: Optional[int] = 1200,
    ):
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self.config = config or {}
        # 启动期加载策略：减小冷启动时间；0 或未设置正数语义见 get_memory_system
        try:
            self._working_days_recent = max(1, int(working_days_recent))
        except Exception:
            self._working_days_recent = 3
        self._working_json_max_files = working_json_max_files
        self._experience_json_max_files = experience_json_max_files
        
        if os.path.exists("/.dockerenv"):
            # 容器环境固定到可持久化挂载目录，避免配置漂移到不可写路径
            self.storage_path = Path("/app/data/memory")
        elif storage_path:
            self.storage_path = Path(storage_path)
        elif config_manager:
            data_path = config_manager.get_path_sync("data_path", None)
            if data_path:
                self.storage_path = Path(data_path) / "memory"
            else:
                self.storage_path = None
        else:
            self.storage_path = Path(workspace_path or "workspace") / "memory"
        
        self._ensure_storage_path()
        
        self.workspace_path = Path(workspace_path or "workspace")
        
        self._memories: Dict[str, MemoryEntry] = {}
        self._index = MemoryIndex()
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 300
        self._async_lock = asyncio.Lock()
        
        self._retention_policy = {
            MemoryLayer.CORE: None,
            MemoryLayer.WORKING: timedelta(days=7),
            MemoryLayer.EXPERIENCE: timedelta(days=365),
            MemoryLayer.HISTORY: timedelta(days=30)
        }
        
        self._max_memories = {
            MemoryLayer.CORE: 100,
            MemoryLayer.WORKING: 1000,
            MemoryLayer.EXPERIENCE: 5000,
            MemoryLayer.HISTORY: 10000
        }
        
        self._stats = {
            "total_memories": 0,
            "by_layer": defaultdict(int),
            "by_category": defaultdict(int),
            "total_queries": 0,
            "cache_hits": 0,
            "last_cleanup": None
        }
        
        self._initialized = False
        logger.info(f"优化版记忆系统初始化，存储路径: {self.storage_path}")
    
    def _ensure_storage_path(self):
        """确保存储路径存在并可写。"""
        subdirs = ["core", "working", "experience", "history", "trades", "sessions"]

        def _prepare(path: Path) -> bool:
            try:
                path.mkdir(parents=True, exist_ok=True)
                for subdir in subdirs:
                    (path / subdir).mkdir(parents=True, exist_ok=True)
                probe = path / "working" / ".write_probe"
                with open(probe, "w", encoding="utf-8") as f:
                    f.write("")
                probe.unlink(missing_ok=True)
                return True
            except OSError:
                return False

        if _prepare(self.storage_path):
            return

        candidates: List[Path] = []
        if os.path.exists("/.dockerenv"):
            candidates.extend([Path("/app/data/memory"), Path("/app/workspace/memory")])
        candidates.append(Path("/tmp/openclaw_memory"))

        for candidate in candidates:
            if candidate == self.storage_path:
                continue
            if _prepare(candidate):
                self.storage_path = candidate
                if str(candidate).startswith("/tmp/"):
                    logger.warning(f"权限不足，使用备用路径: {candidate}")
                else:
                    logger.warning(f"权限不足，改用容器数据目录: {candidate}")
                return
    
    async def initialize(self) -> bool:
        """异步初始化"""
        if self._initialized:
            return True
        
        try:
            logger.info("🔧 初始化优化版记忆系统...")
            
            await self._load_core_memories()
            
            await self._load_recent_working_memories()
            
            await self._load_experience_memories()
            
            self._initialized = True
            logger.info("✅ 优化版记忆系统初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 记忆系统初始化失败: {e}")
            return False
    
    async def _load_core_memories(self):
        """加载核心记忆（永久保留）"""
        core_files = [
            ("COMMANDER_PROFILE.md", MemoryCategory.IDENTITY),
        ]
        
        for filename, category in core_files:
            file_path = self.workspace_path / filename
            if file_path.exists():
                try:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                    
                    entry = MemoryEntry(
                        id=self._generate_id(filename),
                        category=category,
                        layer=MemoryLayer.CORE,
                        content=content,
                        importance=1.0,
                        tags={"core", "permanent"}
                    )
                    
                    self._memories[entry.id] = entry
                    self._index.add_entry(entry)
                    self._stats["by_layer"][MemoryLayer.CORE] += 1
                    
                except Exception as e:
                    logger.warning(f"加载核心记忆 {filename} 失败: {e}")
        
        logger.info(f"✓ 加载核心记忆: {self._stats['by_layer'][MemoryLayer.CORE]} 条")
    
    async def _load_recent_working_memories(self, days: Optional[int] = None):
        """加载最近的工作记忆"""
        working_dir = self.storage_path / "working"
        if not working_dir.exists():
            return
        days = days if days is not None else int(getattr(self, "_working_days_recent", 3) or 3)
        cutoff_date = datetime.now() - timedelta(days=days)

        paths = sorted(
            working_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        cap = getattr(self, "_working_json_max_files", None)
        if isinstance(cap, int) and cap > 0 and len(paths) > cap:
            skipped = len(paths) - cap
            paths = paths[:cap]
            logger.info(
                "工作记忆启动加载限流: 载入 newest=%s，跳过较旧=%s（memory.startup.working_json_max_files）",
                len(paths),
                skipped,
            )

        for file_path in paths:
            try:
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    data = json.loads(await f.read())
                
                entry = MemoryEntry.from_dict(data)
                
                if entry.created_at >= cutoff_date:
                    self._memories[entry.id] = entry
                    self._index.add_entry(entry)
                    self._stats["by_layer"][MemoryLayer.WORKING] += 1
                    
            except Exception as e:
                logger.debug(f"加载工作记忆失败 {file_path}: {e}")
        
        logger.info(f"✓ 加载工作记忆: {self._stats['by_layer'][MemoryLayer.WORKING]} 条")
    
    async def _load_experience_memories(self):
        """加载经验记忆（长期）。

        experience_json_max_files: 限制启动时载入的 JSON 条数（按 mtime 新→旧）。
        None 表示不限制。未载入的文件仍保存在磁盘；后续若有按需加载可增强。
        """
        experience_dir = self.storage_path / "experience"
        if not experience_dir.exists():
            return

        paths = sorted(
            experience_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        cap = getattr(self, "_experience_json_max_files", None)
        if isinstance(cap, int) and cap > 0 and len(paths) > cap:
            skipped = len(paths) - cap
            paths = paths[:cap]
            logger.info(
                "经验记忆启动加载限流: 载入 newest=%s，跳过较旧=%s（memory.startup.experience_json_max_files）",
                len(paths),
                skipped,
            )

        for file_path in paths:
            try:
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    data = json.loads(await f.read())
                
                entry = MemoryEntry.from_dict(data)
                self._memories[entry.id] = entry
                self._index.add_entry(entry)
                self._stats["by_layer"][MemoryLayer.EXPERIENCE] += 1
                
            except Exception as e:
                logger.debug(f"加载经验记忆失败 {file_path}: {e}")
        
        logger.info(f"✓ 加载经验记忆: {self._stats['by_layer'][MemoryLayer.EXPERIENCE]} 条")
    
    def _generate_id(self, content: str) -> str:
        """生成唯一ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        hash_part = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"{timestamp}_{hash_part}"
    
    async def remember(
        self,
        content: str,
        category: MemoryCategory = MemoryCategory.TRADE_RECORD,
        layer: MemoryLayer = MemoryLayer.WORKING,
        importance: float = 0.5,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        记忆接口 - 存储新记忆
        
        Args:
            content: 记忆内容
            category: 记忆分类
            layer: 记忆层级
            importance: 重要性 (0.0-1.0)
            tags: 标签集合
            metadata: 元数据
        
        Returns:
            记忆ID
        """
        async with self._async_lock:
            entry = MemoryEntry(
                id=self._generate_id(content),
                category=category,
                layer=layer,
                content=content,
                importance=importance,
                tags=tags or set(),
                metadata=metadata or {}
            )
            
            self._memories[entry.id] = entry
            self._index.add_entry(entry)
            
            self._stats["total_memories"] += 1
            self._stats["by_layer"][layer] += 1
            self._stats["by_category"][category] += 1
            
            await self._persist_entry(entry)
            
            logger.debug(f"记忆已存储: {entry.id} [{layer.value}]")
            return entry.id
    
    async def recall(
        self,
        query: str,
        layer: Optional[MemoryLayer] = None,
        category: Optional[MemoryCategory] = None,
        tags: Optional[Set[str]] = None,
        limit: int = 10
    ) -> List[MemoryEntry]:
        """
        回忆接口 - 检索记忆
        
        Args:
            query: 查询字符串
            layer: 限制层级
            category: 限制分类
            tags: 限制标签
            limit: 返回数量限制
        
        Returns:
            匹配的记忆列表
        """
        self._stats["total_queries"] += 1
        
        candidate_ids = self._index.search(query)
        
        if not candidate_ids:
            candidate_ids = set(self._memories.keys())
        
        results = []
        for entry_id in candidate_ids:
            entry = self._memories.get(entry_id)
            if not entry:
                continue
            
            if layer and entry.layer != layer:
                continue
            
            if category and entry.category != category:
                continue
            
            if tags and not tags.issubset(entry.tags):
                continue
            
            if query.lower() in entry.content.lower():
                entry.last_accessed = datetime.now()
                entry.access_count += 1
                results.append(entry)
        
        results.sort(key=lambda x: (x.importance, x.access_count), reverse=True)
        
        return results[:limit]
    
    async def forget(self, memory_id: str) -> bool:
        """
        遗忘接口 - 删除记忆
        
        Args:
            memory_id: 记忆ID
        
        Returns:
            是否成功删除
        """
        async with self._async_lock:
            entry = self._memories.get(memory_id)
            if not entry:
                return False
            
            if entry.layer == MemoryLayer.CORE:
                logger.warning(f"拒绝删除核心记忆: {memory_id}")
                return False
            
            self._index.remove_entry(entry)
            del self._memories[memory_id]
            
            self._stats["total_memories"] -= 1
            self._stats["by_layer"][entry.layer] -= 1
            
            await self._delete_entry_file(entry)
            
            logger.debug(f"记忆已删除: {memory_id}")
            return True
    
    async def relate(self, memory_id1: str, memory_id2: str) -> bool:
        """
        关联接口 - 建立记忆关联
        
        Args:
            memory_id1: 记忆ID 1
            memory_id2: 记忆ID 2
        
        Returns:
            是否成功关联
        """
        entry1 = self._memories.get(memory_id1)
        entry2 = self._memories.get(memory_id2)
        
        if not entry1 or not entry2:
            return False
        
        entry1.related_ids.add(memory_id2)
        entry2.related_ids.add(memory_id1)
        
        await self._persist_entry(entry1)
        await self._persist_entry(entry2)
        
        return True
    
    async def get_related(self, memory_id: str, limit: int = 5) -> List[MemoryEntry]:
        """获取相关记忆"""
        entry = self._memories.get(memory_id)
        if not entry:
            return []
        
        related = []
        for related_id in entry.related_ids:
            related_entry = self._memories.get(related_id)
            if related_entry:
                related.append(related_entry)
        
        return related[:limit]
    
    async def compress_memory(self, memory_id: str, summary: str) -> bool:
        """
        压缩记忆 - 保留摘要，释放空间
        
        Args:
            memory_id: 记忆ID
            summary: 记忆摘要
        
        Returns:
            是否成功压缩
        """
        entry = self._memories.get(memory_id)
        if not entry or entry.compressed:
            return False
        
        entry.summary = summary
        entry.compressed = True
        entry.content = summary
        
        await self._persist_entry(entry)
        
        logger.debug(f"记忆已压缩: {memory_id}")
        return True
    
    async def build_context(
        self,
        query: str,
        max_tokens: int = 2000
    ) -> str:
        """
        构建记忆上下文 - 用于AI对话
        
        Args:
            query: 用户查询
            max_tokens: 最大token数
        
        Returns:
            记忆上下文字符串
        """
        context_parts = []
        current_tokens = 0
        
        core_memories = [m for m in self._memories.values() if m.layer == MemoryLayer.CORE]
        for memory in sorted(core_memories, key=lambda x: x.importance, reverse=True):
            text = f"[核心] {memory.content[:200]}\n"
            tokens = len(text) // 2
            
            if current_tokens + tokens <= max_tokens * 0.3:
                context_parts.append(text)
                current_tokens += tokens
        
        relevant_memories = await self.recall(query, limit=5)
        for memory in relevant_memories:
            text = f"[{memory.category.value}] {memory.content[:300]}\n"
            tokens = len(text) // 2
            
            if current_tokens + tokens <= max_tokens * 0.7:
                context_parts.append(text)
                current_tokens += tokens
        
        today = datetime.now().strftime("%Y-%m-%d")
        today_memories = self._index.date_index.get(today, set())
        for memory_id in list(today_memories)[:3]:
            memory = self._memories.get(memory_id)
            if memory:
                text = f"[今日] {memory.content[:200]}\n"
                tokens = len(text) // 2
                
                if current_tokens + tokens <= max_tokens:
                    context_parts.append(text)
                    current_tokens += tokens
        
        if context_parts:
            return "📚 相关记忆：\n" + "".join(context_parts)
        return ""
    
    async def cleanup_expired(self) -> int:
        """
        清理过期记忆
        
        Returns:
            清理的记忆数量
        """
        cleaned = 0
        now = datetime.now()
        
        async with self._async_lock:
            to_remove = []
            
            for entry in self._memories.values():
                if entry.layer == MemoryLayer.CORE:
                    continue
                
                retention = self._retention_policy.get(entry.layer)
                if not retention:
                    continue
                
                age = now - entry.created_at
                
                if age > retention:
                    importance_factor = entry.importance * 0.5
                    access_factor = min(entry.access_count / 10, 0.3)
                    keep_score = importance_factor + access_factor
                    
                    if keep_score < 0.3:
                        to_remove.append(entry.id)
            
            for memory_id in to_remove:
                await self.forget(memory_id)
                cleaned += 1
        
        self._stats["last_cleanup"] = now.isoformat()
        logger.info(f"✓ 清理过期记忆: {cleaned} 条")
        return cleaned

    def _storage_size_bytes(self) -> int:
        try:
            total = 0
            for root, _dirs, files in os.walk(self.storage_path):
                for fn in files:
                    try:
                        total += (Path(root) / fn).stat().st_size
                    except OSError:
                        continue
            return total
        except Exception:
            return 0

    async def cleanup_by_disk_threshold(
        self,
        *,
        max_bytes: int,
        categories_to_prune: Optional[Set[MemoryCategory]] = None,
        min_importance: float = 0.6,
        max_remove: int = 500,
    ) -> int:
        """
        Disk-driven cleanup: only prunes low-importance WORKING/HISTORY entries.
        CORE/EXPERIENCE are never removed here.
        """
        if not max_bytes or max_bytes <= 0:
            return 0
        cur = self._storage_size_bytes()
        if cur <= max_bytes:
            return 0

        cats = categories_to_prune or {MemoryCategory.CONVERSATION, MemoryCategory.DAILY_SUMMARY}
        removed = 0
        async with self._async_lock:
            # oldest + low importance first
            candidates = [
                e
                for e in (self._memories or {}).values()
                if e.layer in {MemoryLayer.WORKING, MemoryLayer.HISTORY}
                and e.category in cats
                and float(e.importance or 0.0) < float(min_importance)
            ]
            candidates.sort(key=lambda x: (x.created_at, float(x.importance or 0.0)))
            for e in candidates[: max(1, int(max_remove))]:
                ok = await self.forget(e.id)
                if ok:
                    removed += 1
                    if self._storage_size_bytes() <= max_bytes:
                        break
        if removed:
            logger.warning(f"🧹 磁盘阈值清理: removed={removed} size={cur}B -> <= {max_bytes}B")
        return removed
    
    async def save_trade_record(
        self,
        symbol: str,
        action: str,
        price: float,
        quantity: float,
        pnl: Optional[float] = None,
        reason: str = "",
        strategy: str = ""
    ) -> str:
        """保存交易记录"""
        content = f"{symbol} {action} @ {price} x {quantity}"
        if pnl is not None:
            content += f" | PnL: {pnl:+.4f}"
        if reason:
            content += f" | 原因: {reason}"
        
        metadata = {
            "symbol": symbol,
            "action": action,
            "price": price,
            "quantity": quantity,
            "pnl": pnl,
            "strategy": strategy
        }
        
        importance = 0.7 if pnl and pnl > 0 else 0.5
        
        memory_id = await self.remember(
            content=content,
            category=MemoryCategory.TRADE_RECORD,
            layer=MemoryLayer.WORKING,
            importance=importance,
            tags={"trade", symbol.replace("/", "_")},
            metadata=metadata
        )
        
        if pnl is not None and abs(pnl) > 0:
            await self._save_trade_lesson(symbol, action, pnl, reason)
        
        return memory_id
    
    async def _save_trade_lesson(self, symbol: str, action: str, pnl: float, reason: str):
        """保存交易教训"""
        if pnl > 0:
            category = MemoryCategory.SUCCESS_PATTERN
            lesson = f"成功: {symbol} {action} 盈利 {pnl:+.4f}"
        else:
            category = MemoryCategory.LESSON_LEARNED
            lesson = f"教训: {symbol} {action} 亏损 {abs(pnl):.4f}"
        
        if reason:
            lesson += f" - {reason}"
        
        await self.remember(
            content=lesson,
            category=category,
            layer=MemoryLayer.EXPERIENCE,
            importance=0.8 if pnl < 0 else 0.6,
            tags={"lesson", symbol.replace("/", "_")}
        )
    
    async def save_market_observation(self, observation: str, symbol: Optional[str] = None):
        """保存市场观察"""
        tags = {"market", "observation"}
        if symbol:
            tags.add(symbol.replace("/", "_"))
        
        await self.remember(
            content=observation,
            category=MemoryCategory.MARKET_OBSERVATION,
            layer=MemoryLayer.WORKING,
            importance=0.4,
            tags=tags,
            metadata={"symbol": symbol} if symbol else {}
        )
    
    async def save_risk_event(self, event: str, level: str = "warning"):
        """保存风险事件"""
        await self.remember(
            content=event,
            category=MemoryCategory.RISK_EVENT,
            layer=MemoryLayer.WORKING,
            importance=0.9 if level == "critical" else 0.7,
            tags={"risk", level}
        )
    
    async def _persist_entry(self, entry: MemoryEntry):
        """持久化记忆条目"""
        try:
            layer_dir = self.storage_path / entry.layer.value
            layer_dir.mkdir(exist_ok=True)
            
            file_path = layer_dir / f"{entry.id}.json"
            
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(entry.to_dict(), ensure_ascii=False, indent=2))
                
        except PermissionError:
            # 运行时写权限突变，切换到 fallback 再重试一次
            fallback = Path("/tmp/openclaw_memory")
            fallback.mkdir(parents=True, exist_ok=True)
            layer_dir = fallback / entry.layer.value
            layer_dir.mkdir(parents=True, exist_ok=True)
            file_path = layer_dir / f"{entry.id}.json"
            try:
                async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(entry.to_dict(), ensure_ascii=False, indent=2))
                self.storage_path = fallback
                logger.warning("记忆存储路径切换到 fallback: %s", fallback)
            except Exception as e:
                logger.error(f"持久化记忆失败: {e}")
        except Exception as e:
            logger.error(f"持久化记忆失败: {e}")
    
    async def _delete_entry_file(self, entry: MemoryEntry):
        """删除记忆文件"""
        try:
            file_path = self.storage_path / entry.layer.value / f"{entry.id}.json"
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            logger.error(f"删除记忆文件失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "storage_path": str(self.storage_path),
            "index_stats": {
                "tags": len(self._index.tag_index),
                "symbols": len(self._index.symbol_index),
                "keywords": len(self._index.keyword_index)
            }
        }
    
    async def export_memories(self, filepath: str):
        """导出所有记忆"""
        try:
            export_data = {
                "export_time": datetime.now().isoformat(),
                "stats": self.get_stats(),
                "memories": [entry.to_dict() for entry in self._memories.values()]
            }
            
            async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(export_data, ensure_ascii=False, indent=2))
            
            logger.info(f"✓ 记忆已导出: {filepath}")
        except Exception as e:
            logger.error(f"导出记忆失败: {e}")
    
    async def cleanup(self):
        """清理资源"""
        try:
            await self.cleanup_expired()
            self._cache.clear()
            logger.info("✓ 记忆系统清理完成")
        except Exception as e:
            logger.error(f"清理失败: {e}")


_memory_instance: Optional[OptimizedMemorySystem] = None


async def get_memory_system(
    storage_path: Optional[str] = None,
    workspace_path: Optional[str] = None,
    *,
    working_days_recent: int = 3,
    working_json_max_files: Optional[int] = 800,
    experience_json_max_files: Optional[int] = 1200,
) -> OptimizedMemorySystem:
    """获取记忆系统单例。

    experience_json_max_files:
      - None: 不限制（冷启动可能较慢）
      - 0 或负数: 与 None 相同（不限制），便于配置显式关闭限流
      - 正整数: 仅按修改时间载入最新的这么多条 JSON
    """
    global _memory_instance
    eff_working_cap = working_json_max_files
    if isinstance(eff_working_cap, int) and eff_working_cap <= 0:
        eff_working_cap = None
    eff_cap = experience_json_max_files
    if isinstance(eff_cap, int) and eff_cap <= 0:
        eff_cap = None
    if _memory_instance is None:
        _memory_instance = OptimizedMemorySystem(
            storage_path=storage_path,
            workspace_path=workspace_path,
            working_days_recent=working_days_recent,
            working_json_max_files=eff_working_cap,
            experience_json_max_files=eff_cap,
        )
        await _memory_instance.initialize()
    return _memory_instance
