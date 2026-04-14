"""
记忆管理器 - 系统交互记忆和上下文管理

功能：
1. 对话历史记录和检索
2. 用户偏好学习
3. 上下文管理
4. 长期记忆存储
5. 记忆压缩和摘要
"""

import asyncio
import json
import logging
import sqlite3
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """记忆类型"""
    CONVERSATION = "conversation"      # 对话记忆
    PREFERENCE = "preference"          # 用户偏好
    CONTEXT = "context"                # 上下文信息
    KNOWLEDGE = "knowledge"            # 知识记忆
    EVENT = "event"                    # 事件记忆


class MemoryPriority(Enum):
    """记忆优先级"""
    CRITICAL = 0      # 关键记忆，永久保留
    HIGH = 1          # 高优先级，长期保留
    NORMAL = 2        # 普通优先级，定期清理
    LOW = 3           # 低优先级，快速清理


@dataclass
class Memory:
    """记忆条目"""
    id: str
    type: MemoryType
    content: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    priority: MemoryPriority = MemoryPriority.NORMAL
    tags: List[str] = field(default_factory=list)
    source: str = "system"             # 记忆来源
    user_id: Optional[str] = None      # 关联用户
    session_id: Optional[str] = None   # 关联会话
    access_count: int = 0              # 访问次数
    last_accessed: Optional[datetime] = None
    expiry: Optional[datetime] = None  # 过期时间
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority.value,
            "tags": self.tags,
            "source": self.source,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "expiry": self.expiry.isoformat() if self.expiry else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Memory':
        """从字典创建"""
        return cls(
            id=data["id"],
            type=MemoryType(data["type"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            priority=MemoryPriority(data["priority"]),
            tags=data.get("tags", []),
            source=data.get("source", "system"),
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
            access_count=data.get("access_count", 0),
            last_accessed=datetime.fromisoformat(data["last_accessed"]) if data.get("last_accessed") else None,
            expiry=datetime.fromisoformat(data["expiry"]) if data.get("expiry") else None
        )


@dataclass
class ConversationContext:
    """对话上下文"""
    session_id: str
    user_id: Optional[str] = None
    messages: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None):
        """添加消息"""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        self.messages.append(message)
        self.last_active = datetime.now()
        
        # 限制历史消息数量（保留最近 50 条）
        if len(self.messages) > 50:
            self.messages = self.messages[-50:]
    
    def get_recent_messages(self, count: int = 10) -> List[Dict[str, Any]]:
        """获取最近的消息"""
        return self.messages[-count:]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "messages": self.messages,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "metadata": self.metadata
        }


class MemoryManager:
    """
    记忆管理器
    
    功能：
    1. 管理对话历史
    2. 存储用户偏好
    3. 维护上下文信息
    4. 支持记忆检索和关联
    """
    
    def __init__(self, db_path: str = "data/memory.db"):
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()
        self._initialized = False
        
        # 内存缓存
        self._conversation_cache: Dict[str, ConversationContext] = {}
        self._preference_cache: Dict[str, Dict[str, Any]] = {}
        
        # 配置
        self.max_conversation_history = 50
        self.memory_retention_days = {
            MemoryPriority.CRITICAL: 365 * 10,  # 10年
            MemoryPriority.HIGH: 365,            # 1年
            MemoryPriority.NORMAL: 30,           # 30天
            MemoryPriority.LOW: 7                # 7天
        }
    
    async def initialize(self):
        """初始化记忆管理器"""
        logger.info("初始化记忆管理器...")
        
        # 创建数据库表
        await self._init_database()
        
        self._initialized = True
        logger.info("记忆管理器初始化完成")
    
    async def _init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建记忆表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                priority INTEGER NOT NULL,
                tags TEXT,
                source TEXT,
                user_id TEXT,
                session_id TEXT,
                access_count INTEGER DEFAULT 0,
                last_accessed TEXT,
                expiry TEXT
            )
        ''')
        
        # 创建索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp)
        ''')
        
        # 创建对话上下文表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                messages TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_active TEXT NOT NULL,
                metadata TEXT
            )
        ''')
        
        # 创建用户偏好表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                preferences TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("记忆数据库初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        logger.info("清理记忆管理器...")
        
        # 保存缓存到数据库
        await self._save_cache_to_db()
        
        if self._connection:
            self._connection.close()
            self._connection = None
        
        logger.info("记忆管理器清理完成")
    
    async def _save_cache_to_db(self):
        """保存缓存到数据库"""
        # 保存对话上下文
        for session_id, context in self._conversation_cache.items():
            await self._save_conversation(context)
        
        # 保存用户偏好
        for user_id, preferences in self._preference_cache.items():
            await self._save_user_preferences(user_id, preferences)
    
    # ========== 对话记忆管理 ==========
    
    async def create_conversation(self, session_id: str, user_id: Optional[str] = None) -> ConversationContext:
        """创建新对话"""
        context = ConversationContext(
            session_id=session_id,
            user_id=user_id
        )
        self._conversation_cache[session_id] = context
        return context
    
    async def get_conversation(self, session_id: str) -> Optional[ConversationContext]:
        """获取对话上下文"""
        # 先从缓存查找
        if session_id in self._conversation_cache:
            return self._conversation_cache[session_id]
        
        # 从数据库加载
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM conversations WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            context = ConversationContext(
                session_id=row[0],
                user_id=row[1],
                messages=json.loads(row[2]),
                created_at=datetime.fromisoformat(row[3]),
                last_active=datetime.fromisoformat(row[4]),
                metadata=json.loads(row[5]) if row[5] else {}
            )
            self._conversation_cache[session_id] = context
            return context
        
        return None
    
    async def add_message(self, session_id: str, role: str, content: str, 
                         user_id: Optional[str] = None, metadata: Dict[str, Any] = None):
        """添加对话消息"""
        context = await self.get_conversation(session_id)
        
        if context is None:
            context = await self.create_conversation(session_id, user_id)
        
        context.add_message(role, content, metadata)
        
        # 保存到数据库
        await self._save_conversation(context)
        
        # 同时保存为记忆
        await self.add_memory(
            type=MemoryType.CONVERSATION,
            content={
                "session_id": session_id,
                "role": role,
                "content": content,
                "metadata": metadata
            },
            user_id=user_id,
            session_id=session_id,
            priority=MemoryPriority.NORMAL
        )
    
    async def _save_conversation(self, context: ConversationContext):
        """保存对话到数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO conversations 
            (session_id, user_id, messages, created_at, last_active, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            context.session_id,
            context.user_id,
            json.dumps(context.messages),
            context.created_at.isoformat(),
            context.last_active.isoformat(),
            json.dumps(context.metadata)
        ))
        
        conn.commit()
        conn.close()
    
    async def get_conversation_history(self, session_id: str, count: int = 10) -> List[Dict[str, Any]]:
        """获取对话历史"""
        context = await self.get_conversation(session_id)
        if context:
            return context.get_recent_messages(count)
        return []
    
    # ========== 用户偏好管理 ==========
    
    async def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """获取用户偏好"""
        # 先从缓存查找
        if user_id in self._preference_cache:
            return self._preference_cache[user_id]
        
        # 从数据库加载
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT preferences FROM user_preferences WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            preferences = json.loads(row[0])
            self._preference_cache[user_id] = preferences
            return preferences
        
        return {}
    
    async def set_user_preference(self, user_id: str, key: str, value: Any):
        """设置用户偏好"""
        preferences = await self.get_user_preferences(user_id)
        preferences[key] = value
        
        self._preference_cache[user_id] = preferences
        await self._save_user_preferences(user_id, preferences)
        
        # 保存为记忆
        await self.add_memory(
            type=MemoryType.PREFERENCE,
            content={
                "user_id": user_id,
                "key": key,
                "value": value
            },
            user_id=user_id,
            priority=MemoryPriority.HIGH
        )
    
    async def _save_user_preferences(self, user_id: str, preferences: Dict[str, Any]):
        """保存用户偏好到数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_preferences 
            (user_id, preferences, updated_at)
            VALUES (?, ?, ?)
        ''', (
            user_id,
            json.dumps(preferences),
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    # ========== 通用记忆管理 ==========
    
    async def add_memory(self, type: MemoryType, content: Dict[str, Any],
                        priority: MemoryPriority = MemoryPriority.NORMAL,
                        tags: List[str] = None, source: str = "system",
                        user_id: Optional[str] = None,
                        session_id: Optional[str] = None) -> str:
        """添加记忆"""
        memory_id = hashlib.md5(
            f"{type.value}:{json.dumps(content, sort_keys=True)}:{datetime.now()}".encode()
        ).hexdigest()
        
        # 计算过期时间
        retention_days = self.memory_retention_days.get(priority, 30)
        expiry = datetime.now() + timedelta(days=retention_days)
        
        memory = Memory(
            id=memory_id,
            type=type,
            content=content,
            priority=priority,
            tags=tags or [],
            source=source,
            user_id=user_id,
            session_id=session_id,
            expiry=expiry
        )
        
        # 保存到数据库
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO memories 
            (id, type, content, timestamp, priority, tags, source, user_id, session_id, expiry)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            memory.id,
            memory.type.value,
            json.dumps(memory.content),
            memory.timestamp.isoformat(),
            memory.priority.value,
            json.dumps(memory.tags),
            memory.source,
            memory.user_id,
            memory.session_id,
            memory.expiry.isoformat() if memory.expiry else None
        ))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"添加记忆: {memory_id} (类型: {type.value})")
        return memory_id
    
    async def get_memories(self, type: MemoryType = None, user_id: str = None,
                          session_id: str = None, tags: List[str] = None,
                          limit: int = 100) -> List[Memory]:
        """检索记忆"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM memories WHERE 1=1"
        params = []
        
        if type:
            query += " AND type = ?"
            params.append(type.value)
        
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        
        if tags:
            for tag in tags:
                query += " AND tags LIKE ?"
                params.append(f'%"{tag}"%')
        
        # 排除过期记忆
        query += " AND (expiry IS NULL OR expiry > ?)"
        params.append(datetime.now().isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        memories = []
        for row in rows:
            memory = Memory(
                id=row[0],
                type=MemoryType(row[1]),
                content=json.loads(row[2]),
                timestamp=datetime.fromisoformat(row[3]),
                priority=MemoryPriority(row[4]),
                tags=json.loads(row[5]) if row[5] else [],
                source=row[6],
                user_id=row[7],
                session_id=row[8],
                access_count=row[9],
                last_accessed=datetime.fromisoformat(row[10]) if row[10] else None,
                expiry=datetime.fromisoformat(row[11]) if row[11] else None
            )
            memories.append(memory)
        
        return memories
    
    async def search_memories(self, query: str, user_id: str = None,
                             limit: int = 10) -> List[Memory]:
        """搜索记忆（简单关键词匹配）"""
        all_memories = await self.get_memories(user_id=user_id, limit=1000)
        
        # 简单关键词匹配
        query_lower = query.lower()
        scored_memories = []
        
        for memory in all_memories:
            score = 0
            content_str = json.dumps(memory.content).lower()
            
            # 内容匹配
            if query_lower in content_str:
                score += 10
            
            # 标签匹配
            for tag in memory.tags:
                if query_lower in tag.lower():
                    score += 5
            
            # 时间衰减（越新的记忆分数越高）
            days_old = (datetime.now() - memory.timestamp).days
            score += max(0, 30 - days_old) / 3
            
            # 访问频率
            score += memory.access_count * 0.5
            
            if score > 0:
                scored_memories.append((score, memory))
        
        # 按分数排序
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        
        return [memory for _, memory in scored_memories[:limit]]
    
    async def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted
    
    async def clear_old_memories(self):
        """清理过期记忆"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute(
            "DELETE FROM memories WHERE expiry IS NOT NULL AND expiry < ?",
            (now,)
        )
        deleted_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f"清理了 {deleted_count} 条过期记忆")
        return deleted_count
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """获取记忆统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 总记忆数
        cursor.execute("SELECT COUNT(*) FROM memories")
        total_memories = cursor.fetchone()[0]
        
        # 按类型统计
        cursor.execute("SELECT type, COUNT(*) FROM memories GROUP BY type")
        type_counts = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 过期记忆数
        cursor.execute(
            "SELECT COUNT(*) FROM memories WHERE expiry IS NOT NULL AND expiry < ?",
            (datetime.now().isoformat(),)
        )
        expired_memories = cursor.fetchone()[0]
        
        # 对话数
        cursor.execute("SELECT COUNT(*) FROM conversations")
        total_conversations = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_memories": total_memories,
            "type_counts": type_counts,
            "expired_memories": expired_memories,
            "total_conversations": total_conversations,
            "cached_conversations": len(self._conversation_cache),
            "cached_preferences": len(self._preference_cache)
        }


# 全局记忆管理器实例
_memory_manager: Optional[MemoryManager] = None


async def get_memory_manager() -> MemoryManager:
    """获取记忆管理器实例"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
        await _memory_manager.initialize()
    return _memory_manager
