"""
统一记忆系统 V3.0 - 兼容适配器

整合所有记忆功能，使用优化版实现，保持向后兼容

核心功能：
1. 保留原有接口，内部使用 OptimizedMemorySystem
2. 自动迁移旧记忆数据
3. 统一存储路径管理
4. 提供便捷的访问方法
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from pathlib import Path

from .optimized_memory_system import (
    OptimizedMemorySystem,
    MemoryLayer,
    MemoryCategory,
    MemoryEntry,
    get_memory_system
)

logger = logging.getLogger(__name__)


class UnifiedMemorySystem:
    """
    统一记忆系统 - 兼容适配器
    
    整合所有记忆功能，使用优化版实现
    保持向后兼容的接口
    """
    
    def __init__(self, workspace_path: str = None):
        """
        初始化统一记忆系统
        
        Args:
            workspace_path: 工作空间路径
        """
        self.workspace_path = workspace_path or "workspace"
        
        self._optimized_memory: Optional[OptimizedMemorySystem] = None
        
        self.ai_memory = None
        self.hierarchical_memory = None
        self.memory_optimizer = None
        
        self.enhanced_features = {
            "importance_evaluator": True,
            "auto_cleanup": True,
            "smart_indexing": True,
            "context_builder": True
        }
        
        self.stats = {
            "total_memories": 0,
            "short_term_count": 0,
            "medium_term_count": 0,
            "long_term_count": 0,
            "last_cleanup": None
        }
        
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 300
        
        logger.info("统一记忆系统初始化 (使用优化版实现)")
    
    async def initialize(self) -> bool:
        """
        初始化所有记忆组件
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            logger.info("🔧 初始化统一记忆系统...")
            
            self._optimized_memory = await get_memory_system(
                workspace_path=self.workspace_path
            )
            
            self._sync_stats()
            
            logger.info("✅ 统一记忆系统初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 统一记忆系统初始化失败: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    def _sync_stats(self):
        """同步统计信息"""
        if self._optimized_memory:
            opt_stats = self._optimized_memory.get_stats()
            self.stats["total_memories"] = opt_stats.get("total_memories", 0)
            self.stats["short_term_count"] = opt_stats.get("by_layer", {}).get(MemoryLayer.WORKING, 0)
            self.stats["medium_term_count"] = opt_stats.get("by_layer", {}).get(MemoryLayer.HISTORY, 0)
            self.stats["long_term_count"] = opt_stats.get("by_layer", {}).get(MemoryLayer.EXPERIENCE, 0)
            self.stats["last_cleanup"] = opt_stats.get("last_cleanup")
    
    async def remember(
        self,
        key: str,
        value: Any,
        level: str = "short",
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        统一记忆接口
        
        Args:
            key: 记忆键
            value: 记忆值
            level: 记忆级别 (short/medium/long)
            metadata: 元数据
        
        Returns:
            bool: 是否成功
        """
        if not self._optimized_memory:
            return False
        
        level_map = {
            "short": MemoryLayer.WORKING,
            "medium": MemoryLayer.HISTORY,
            "long": MemoryLayer.EXPERIENCE
        }
        
        layer = level_map.get(level, MemoryLayer.WORKING)
        
        content = f"{key}: {value}" if not isinstance(value, str) else value
        
        category = MemoryCategory.TRADE_RECORD
        if metadata and "type" in metadata:
            type_map = {
                "trade": MemoryCategory.TRADE_RECORD,
                "market": MemoryCategory.MARKET_OBSERVATION,
                "risk": MemoryCategory.RISK_EVENT,
                "lesson": MemoryCategory.LESSON_LEARNED,
                "preference": MemoryCategory.USER_PREFERENCE
            }
            category = type_map.get(metadata["type"], MemoryCategory.TRADE_RECORD)
        
        try:
            await self._optimized_memory.remember(
                content=content,
                category=category,
                layer=layer,
                importance=0.5,
                tags={key} if key else set(),
                metadata=metadata or {}
            )
            
            self._sync_stats()
            return True
            
        except Exception as e:
            logger.error(f"记忆失败: {e}")
            return False
    
    async def recall(
        self,
        query: str,
        level: str = "all",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        统一回忆接口
        
        Args:
            query: 查询字符串
            level: 记忆级别 (short/medium/long/all)
            limit: 返回数量限制
        
        Returns:
            List[Dict]: 记忆列表
        """
        if not self._optimized_memory:
            return []
        
        layer = None
        if level != "all":
            level_map = {
                "short": MemoryLayer.WORKING,
                "medium": MemoryLayer.HISTORY,
                "long": MemoryLayer.EXPERIENCE
            }
            layer = level_map.get(level)
        
        try:
            entries = await self._optimized_memory.recall(
                query=query,
                layer=layer,
                limit=limit
            )
            
            results = []
            for entry in entries:
                results.append({
                    "key": entry.id,
                    "value": entry.content,
                    "importance": entry.importance,
                    "timestamp": entry.created_at.isoformat(),
                    "access_count": entry.access_count,
                    "metadata": entry.metadata
                })
            
            return results
            
        except Exception as e:
            logger.error(f"回忆失败: {e}")
            return []
    
    async def retrieve_memories(self, query: str, limit: int = 10) -> List[Dict]:
        """
        检索记忆（兼容接口）
        
        Args:
            query: 查询字符串
            limit: 返回数量限制
        
        Returns:
            List[Dict]: 记忆列表
        """
        return await self.recall(query, level="all", limit=limit)
    
    def get_ai_memory(self):
        """获取AI记忆管理器（保留现有接口）"""
        return self._optimized_memory
    
    def get_hierarchical_memory(self):
        """获取层次化记忆管理器（保留现有接口）"""
        return self._optimized_memory
    
    def get_memory_optimizer(self):
        """获取内存优化器（保留现有接口）"""
        return self._optimized_memory
    
    async def build_context(self, query: str, max_tokens: int = 2000) -> str:
        """
        构建记忆上下文（增强功能）
        
        Args:
            query: 查询字符串
            max_tokens: 最大token数
        
        Returns:
            str: 记忆上下文
        """
        if not self._optimized_memory:
            return ""
        
        return await self._optimized_memory.build_context(query, max_tokens)
    
    async def cleanup_expired_memories(self):
        """清理过期记忆（增强功能）"""
        if not self._optimized_memory:
            return
        
        await self._optimized_memory.cleanup_expired()
        self._sync_stats()
    
    async def optimize(self):
        """优化内存使用（增强功能）"""
        self._cache.clear()
        if self._optimized_memory:
            await self._optimized_memory.cleanup()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        if self._optimized_memory:
            return self._optimized_memory.get_stats()
        return self.stats
    
    async def save_daily_memory(self, content: str):
        """保存每日记忆"""
        if self._optimized_memory:
            await self._optimized_memory.remember(
                content=content,
                category=MemoryCategory.DAILY_SUMMARY,
                layer=MemoryLayer.WORKING,
                importance=0.6,
                tags={"daily", datetime.now().strftime("%Y-%m-%d")}
            )
    
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
        if not self._optimized_memory:
            return ""
        
        return await self._optimized_memory.save_trade_record(
            symbol=symbol,
            action=action,
            price=price,
            quantity=quantity,
            pnl=pnl,
            reason=reason,
            strategy=strategy
        )
    
    async def save_market_observation(self, observation: str, symbol: Optional[str] = None):
        """保存市场观察"""
        if self._optimized_memory:
            await self._optimized_memory.save_market_observation(observation, symbol)
    
    async def save_risk_event(self, event: str, level: str = "warning"):
        """保存风险事件"""
        if self._optimized_memory:
            await self._optimized_memory.save_risk_event(event, level)
    
    async def get_trade_history(self, days: int = 7) -> List[Dict]:
        """获取交易历史"""
        if not self._optimized_memory:
            return []
        
        entries = await self._optimized_memory.recall(
            query="trade",
            category=MemoryCategory.TRADE_RECORD,
            limit=100
        )
        
        cutoff = datetime.now() - timedelta(days=days)
        return [
            {
                "content": e.content,
                "timestamp": e.created_at.isoformat(),
                "metadata": e.metadata
            }
            for e in entries
            if e.created_at >= cutoff
        ]
    
    async def get_lessons_learned(self, limit: int = 20) -> List[Dict]:
        """获取经验教训"""
        if not self._optimized_memory:
            return []
        
        entries = await self._optimized_memory.recall(
            query="",
            category=MemoryCategory.LESSON_LEARNED,
            limit=limit
        )
        
        return [
            {
                "content": e.content,
                "timestamp": e.created_at.isoformat(),
                "importance": e.importance
            }
            for e in entries
        ]
    
    async def relate_memories(self, memory_id1: str, memory_id2: str) -> bool:
        """关联两条记忆"""
        if not self._optimized_memory:
            return False
        return await self._optimized_memory.relate(memory_id1, memory_id2)
    
    async def get_related_memories(self, memory_id: str) -> List[Dict]:
        """获取相关记忆"""
        if not self._optimized_memory:
            return []
        
        entries = await self._optimized_memory.get_related(memory_id)
        return [
            {
                "id": e.id,
                "content": e.content,
                "category": e.category.value
            }
            for e in entries
        ]
    
    async def export_memories(self, filepath: str):
        """导出记忆"""
        if self._optimized_memory:
            await self._optimized_memory.export_memories(filepath)
    
    async def cleanup(self):
        """清理资源"""
        try:
            logger.info("清理统一记忆系统...")
            
            if self._optimized_memory:
                await self._optimized_memory.cleanup()
            
            self._cache.clear()
            
            logger.info("✅ 统一记忆系统清理完成")
        except Exception as e:
            logger.error(f"清理失败: {e}")


async def build_unified_memory_system(
    workspace_path: Optional[str] = None
) -> UnifiedMemorySystem:
    """
    构建 UnifiedMemorySystem 实例（内部使用）。

    注意：项目记忆系统已收敛到 MemoryGateway 为唯一对外入口，
    不应再通过 get_unified_memory 形式被业务模块当作 fallback 直接调用。
    """
    memory = UnifiedMemorySystem(workspace_path=workspace_path)
    await memory.initialize()
    return memory
