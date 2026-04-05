"""
统一智能记忆系统

提供记忆类型枚举和重要性评估器
"""

import logging
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


class UnifiedMemoryType(Enum):
    """统一记忆类型"""
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    EMOTIONAL = "emotional"
    SPATIAL = "spatial"
    TEMPORAL = "temporal"
    TRADE_RECORD = "trade_record"
    POSITION = "position"
    SIGNAL = "signal"
    DECISION = "decision"
    MARKET_DATA = "market_data"
    USER_PREFERENCE = "user_preference"
    SYSTEM_STATE = "system_state"


@dataclass
class MemoryItem:
    """记忆项"""
    id: str
    content: str
    memory_type: UnifiedMemoryType
    importance: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryImportanceEvaluator:
    """记忆重要性评估器"""
    
    def __init__(self):
        self._factors = {
            "recency": 0.3,
            "frequency": 0.3,
            "relevance": 0.2,
            "emotional_impact": 0.2
        }
    
    def evaluate(self, memory: MemoryItem) -> float:
        """评估记忆重要性"""
        score = 0.0
        
        now = datetime.now()
        age_seconds = (now - memory.created_at).total_seconds()
        recency_score = 1.0 / (1.0 + age_seconds / 3600)
        score += recency_score * self._factors["recency"]
        
        frequency_score = min(1.0, memory.access_count / 10.0)
        score += frequency_score * self._factors["frequency"]
        
        score += memory.importance * self._factors["relevance"]
        
        emotional_score = memory.metadata.get("emotional_impact", 0.5)
        score += emotional_score * self._factors["emotional_impact"]
        
        return min(1.0, max(0.0, score))
    
    def batch_evaluate(self, memories: List[MemoryItem]) -> Dict[str, float]:
        """批量评估记忆重要性"""
        return {memory.id: self.evaluate(memory) for memory in memories}


class UnifiedIntelligentMemory:
    """统一智能记忆系统"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._memories: Dict[str, MemoryItem] = {}
        self._evaluator = MemoryImportanceEvaluator()
        self._max_memories = self.config.get("max_memories", 10000)
    
    async def initialize(self) -> bool:
        """初始化记忆系统"""
        logger.info("统一智能记忆系统初始化完成")
        return True
    
    async def store(self, content: str, memory_type: UnifiedMemoryType, 
                    importance: float = 0.5, metadata: Optional[Dict] = None) -> str:
        """存储记忆"""
        import uuid
        memory_id = str(uuid.uuid4())
        
        memory = MemoryItem(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            metadata=metadata or {}
        )
        
        self._memories[memory_id] = memory
        return memory_id
    
    async def add_memory(self, content: str, memory_type: str = "semantic",
                         importance: float = 0.5, metadata: Optional[Dict] = None) -> str:
        """添加记忆（兼容接口）"""
        type_map = {
            "semantic": UnifiedMemoryType.SEMANTIC,
            "episodic": UnifiedMemoryType.EPISODIC,
            "short_term": UnifiedMemoryType.SHORT_TERM,
            "long_term": UnifiedMemoryType.LONG_TERM,
            "procedural": UnifiedMemoryType.PROCEDURAL,
            "emotional": UnifiedMemoryType.EMOTIONAL,
            "spatial": UnifiedMemoryType.SPATIAL,
            "temporal": UnifiedMemoryType.TEMPORAL
        }
        mtype = type_map.get(memory_type, UnifiedMemoryType.SEMANTIC)
        return await self.store(content, mtype, importance, metadata)
    
    async def retrieve(self, memory_id: str) -> Optional[MemoryItem]:
        """检索记忆"""
        memory = self._memories.get(memory_id)
        if memory:
            memory.last_accessed = datetime.now()
            memory.access_count += 1
        return memory
    
    async def search(self, query: str, memory_type: Optional[UnifiedMemoryType] = None,
                     limit: int = 10) -> List[MemoryItem]:
        """搜索记忆"""
        results = []
        for memory in self._memories.values():
            if query.lower() in memory.content.lower():
                if memory_type is None or memory.memory_type == memory_type:
                    results.append(memory)
        
        results.sort(key=lambda m: self._evaluator.evaluate(m), reverse=True)
        return results[:limit]
    
    async def retrieve_memories(self, query: str, min_importance: float = 0.0,
                                 limit: int = 10, memory_type: Optional[str] = None) -> List[MemoryItem]:
        """检索记忆（兼容接口）
        
        Args:
            query: 搜索查询
            min_importance: 最小重要性阈值
            limit: 返回数量限制
            memory_type: 记忆类型（字符串）
        
        Returns:
            记忆项列表
        """
        type_map = {
            "semantic": UnifiedMemoryType.SEMANTIC,
            "episodic": UnifiedMemoryType.EPISODIC,
            "short_term": UnifiedMemoryType.SHORT_TERM,
            "long_term": UnifiedMemoryType.LONG_TERM,
        }
        mtype = type_map.get(memory_type) if memory_type else None
        
        results = []
        for memory in self._memories.values():
            if memory.importance < min_importance:
                continue
            if query.lower() in memory.content.lower():
                if mtype is None or memory.memory_type == mtype:
                    results.append(memory)
        
        results.sort(key=lambda m: self._evaluator.evaluate(m), reverse=True)
        return results[:limit]
    
    async def forget(self, memory_id: str) -> bool:
        """遗忘记忆"""
        if memory_id in self._memories:
            del self._memories[memory_id]
            return True
        return False
    
    async def consolidate(self) -> int:
        """整合记忆（移除不重要的记忆）"""
        if len(self._memories) <= self._max_memories:
            return 0
        
        scores = self._evaluator.batch_evaluate(list(self._memories.values()))
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x])
        
        to_remove = len(self._memories) - self._max_memories
        for memory_id in sorted_ids[:to_remove]:
            del self._memories[memory_id]
        
        return to_remove
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        type_counts = {}
        for memory in self._memories.values():
            type_name = memory.memory_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        return {
            "total_memories": len(self._memories),
            "type_distribution": type_counts,
            "max_memories": self._max_memories
        }


_unified_memory_instance: Optional[UnifiedIntelligentMemory] = None


async def get_unified_memory() -> UnifiedIntelligentMemory:
    """获取统一记忆系统实例"""
    global _unified_memory_instance
    if _unified_memory_instance is None:
        _unified_memory_instance = UnifiedIntelligentMemory()
        await _unified_memory_instance.initialize()
    return _unified_memory_instance
