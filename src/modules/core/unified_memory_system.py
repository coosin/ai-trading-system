"""
统一记忆系统

整合所有记忆功能，保留现有功能，提供统一接口

核心功能：
1. 保留 AIMemoryManager 的核心记忆功能
2. 保留 HierarchicalMemoryManager 的层次化记忆
3. 整合 EnhancedMemoryManager 的增强功能
4. 整合 UnifiedIntelligentMemory 的智能特性
5. 统一接口，简化使用
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from pathlib import Path

logger = logging.getLogger(__name__)


class UnifiedMemorySystem:
    """
    统一记忆系统
    
    整合所有记忆功能，保留现有接口，提供统一管理
    """
    
    def __init__(self, workspace_path: str = None):
        """
        初始化统一记忆系统
        
        Args:
            workspace_path: 工作空间路径
        """
        self.workspace_path = workspace_path or "workspace"
        
        # 核心记忆管理器（保留现有功能）
        self.ai_memory = None
        self.hierarchical_memory = None
        self.memory_optimizer = None
        
        # 增强功能（整合自其他模块）
        self.enhanced_features = {
            "importance_evaluator": None,
            "auto_cleanup": True,
            "smart_indexing": True,
            "context_builder": True
        }
        
        # 记忆统计
        self.stats = {
            "total_memories": 0,
            "short_term_count": 0,
            "medium_term_count": 0,
            "long_term_count": 0,
            "last_cleanup": None
        }
        
        # 缓存
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 300  # 5分钟
        
        logger.info("统一记忆系统初始化")
    
    async def initialize(self) -> bool:
        """
        初始化所有记忆组件
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            logger.info("🔧 初始化统一记忆系统...")
            
            # 1. 初始化核心AI记忆管理器（保留现有功能）
            await self._init_ai_memory()
            
            # 2. 初始化层次化记忆管理器（保留现有功能）
            await self._init_hierarchical_memory()
            
            # 3. 初始化内存优化器（保留现有功能）
            await self._init_memory_optimizer()
            
            # 4. 整合增强功能（来自其他模块）
            await self._integrate_enhanced_features()
            
            # 5. 启动后台任务
            await self._start_background_tasks()
            
            logger.info("✅ 统一记忆系统初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 统一记忆系统初始化失败: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    async def _init_ai_memory(self):
        """初始化AI记忆管理器（保留现有功能）"""
        try:
            from src.modules.core.ai_memory import SmartMemoryManager
            
            self.ai_memory = SmartMemoryManager(workspace_path=self.workspace_path)
            await self.ai_memory.initialize()
            
            logger.info("✅ AI记忆管理器已初始化（保留现有功能）")
        except Exception as e:
            logger.warning(f"⚠️ AI记忆管理器初始化失败: {e}")
            self.ai_memory = None
    
    async def _init_hierarchical_memory(self):
        """初始化层次化记忆管理器（保留现有功能）"""
        try:
            from src.modules.core.hierarchical_memory import HierarchicalMemoryManager
            
            memory_path = str(Path(self.workspace_path) / "memory")
            self.hierarchical_memory = HierarchicalMemoryManager(base_path=memory_path)
            
            logger.info("✅ 层次化记忆管理器已初始化（保留现有功能）")
        except Exception as e:
            logger.warning(f"⚠️ 层次化记忆管理器初始化失败: {e}")
            self.hierarchical_memory = None
    
    async def _init_memory_optimizer(self):
        """初始化内存优化器（保留现有功能）"""
        try:
            from src.modules.core.memory_optimizer import MemoryOptimizer
            
            self.memory_optimizer = MemoryOptimizer({
                "max_memory_percent": 80,
                "cleanup_interval": 300,
                "cache_size_limit": 500
            })
            await self.memory_optimizer.start()
            
            logger.info("✅ 内存优化器已初始化（保留现有功能）")
        except Exception as e:
            logger.warning(f"⚠️ 内存优化器初始化失败: {e}")
            self.memory_optimizer = None
    
    async def _integrate_enhanced_features(self):
        """整合增强功能（来自其他记忆模块）"""
        try:
            self.enhanced_features["importance_evaluator"] = self._create_importance_evaluator()
            logger.info("✅ 增强功能整合完成")
        except Exception as e:
            logger.warning(f"⚠️ 增强功能整合失败: {e}")
    
    def _create_importance_evaluator(self):
        """创建重要性评估器"""
        try:
            from src.modules.core.unified_intelligent_memory import MemoryImportanceEvaluator
            return MemoryImportanceEvaluator()
        except Exception as e:
            logger.debug(f"重要性评估器不可用: {e}")
            return None
    
    async def _start_background_tasks(self):
        """启动后台任务"""
        try:
            # 启动定期清理任务
            asyncio.create_task(self._periodic_cleanup())
            
            logger.info("✅ 后台任务已启动")
        except Exception as e:
            logger.warning(f"⚠️ 后台任务启动失败: {e}")
    
    async def _periodic_cleanup(self):
        """定期清理任务"""
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟
                
                # 清理过期记忆
                if self.enhanced_features["auto_cleanup"]:
                    await self.cleanup_expired_memories()
                
                # 更新统计
                await self._update_stats()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"定期清理失败: {e}")
    
    async def _update_stats(self):
        """更新记忆统计"""
        try:
            if self.ai_memory:
                self.stats["short_term_count"] = len(self.ai_memory.short_term_memory) if hasattr(self.ai_memory, 'short_term_memory') else 0
                self.stats["long_term_count"] = len(self.ai_memory.long_term_memory) if hasattr(self.ai_memory, 'long_term_memory') else 0
            
            if self.hierarchical_memory:
                self.stats["medium_term_count"] = 0  # 层次化记忆的统计
                
            self.stats["total_memories"] = (
                self.stats["short_term_count"] + 
                self.stats["medium_term_count"] + 
                self.stats["long_term_count"]
            )
        except Exception as e:
            logger.debug(f"更新统计失败: {e}")
    
    # ==================== 统一记忆接口 ====================
    
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
        try:
            # 评估重要性
            importance = 0.5
            if self.enhanced_features["importance_evaluator"]:
                try:
                    importance = self.enhanced_features["importance_evaluator"].evaluate(key, value)
                except:
                    pass
            
            # 根据级别存储
            if level == "short":
                return await self._remember_short_term(key, value, metadata)
            elif level == "medium":
                return await self._remember_medium_term(key, value, metadata, importance)
            else:
                return await self._remember_long_term(key, value, metadata, importance)
                
        except Exception as e:
            logger.error(f"记忆失败: {e}")
            return False
    
    async def _remember_short_term(self, key: str, value: Any, metadata: Dict = None) -> bool:
        """短期记忆"""
        if self.ai_memory:
            try:
                await self.ai_memory.add_short_term_memory(key, value, metadata)
                return True
            except Exception as e:
                logger.debug(f"短期记忆失败: {e}")
        return False
    
    async def _remember_medium_term(self, key: str, value: Any, metadata: Dict, importance: float) -> bool:
        """中期记忆"""
        if self.hierarchical_memory:
            try:
                await self.hierarchical_memory.add_memory(key, value, metadata)
                return True
            except Exception as e:
                logger.debug(f"中期记忆失败: {e}")
        return False
    
    async def _remember_long_term(self, key: str, value: Any, metadata: Dict, importance: float) -> bool:
        """长期记忆"""
        if self.ai_memory:
            try:
                await self.ai_memory.add_long_term_memory(key, value, metadata)
                return True
            except Exception as e:
                logger.debug(f"长期记忆失败: {e}")
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
        try:
            results = []
            
            # 从不同级别搜索
            if level in ["all", "short"]:
                short_term = await self._recall_short_term(query, limit)
                results.extend(short_term)
            
            if level in ["all", "medium"]:
                medium_term = await self._recall_medium_term(query, limit)
                results.extend(medium_term)
            
            if level in ["all", "long"]:
                long_term = await self._recall_long_term(query, limit)
                results.extend(long_term)
            
            # 按重要性排序
            results.sort(key=lambda x: x.get("importance", 0), reverse=True)
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"回忆失败: {e}")
            return []
    
    async def _recall_short_term(self, query: str, limit: int) -> List[Dict]:
        """短期记忆回忆"""
        if self.ai_memory:
            try:
                return await self.ai_memory.search_short_term(query, limit)
            except:
                pass
        return []
    
    async def _recall_medium_term(self, query: str, limit: int) -> List[Dict]:
        """中期记忆回忆"""
        if self.hierarchical_memory:
            try:
                return await self.hierarchical_memory.search(query, limit)
            except:
                pass
        return []
    
    async def _recall_long_term(self, query: str, limit: int) -> List[Dict]:
        """长期记忆回忆"""
        if self.ai_memory:
            try:
                return await self.ai_memory.search_long_term(query, limit)
            except:
                pass
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
    
    # ==================== 保留现有接口 ====================
    
    def get_ai_memory(self):
        """获取AI记忆管理器（保留现有接口）"""
        return self.ai_memory
    
    def get_hierarchical_memory(self):
        """获取层次化记忆管理器（保留现有接口）"""
        return self.hierarchical_memory
    
    def get_memory_optimizer(self):
        """获取内存优化器（保留现有接口）"""
        return self.memory_optimizer
    
    # ==================== 增强功能 ====================
    
    async def build_context(self, query: str, max_tokens: int = 2000) -> str:
        """
        构建记忆上下文（增强功能）
        
        Args:
            query: 查询字符串
            max_tokens: 最大token数
        
        Returns:
            str: 记忆上下文
        """
        try:
            # 获取相关记忆
            memories = await self.recall(query, level="all", limit=20)
            
            # 构建上下文
            context_parts = []
            current_tokens = 0
            
            for memory in memories:
                memory_text = f"- {memory.get('key', '')}: {memory.get('value', '')}\n"
                memory_tokens = len(memory_text.split())
                
                if current_tokens + memory_tokens <= max_tokens:
                    context_parts.append(memory_text)
                    current_tokens += memory_tokens
                else:
                    break
            
            if context_parts:
                return "相关记忆：\n" + "".join(context_parts)
            else:
                return ""
                
        except Exception as e:
            logger.debug(f"构建上下文失败: {e}")
            return ""
    
    async def cleanup_expired_memories(self):
        """清理过期记忆（增强功能）"""
        try:
            # 清理短期记忆（超过1天）
            if self.ai_memory:
                try:
                    await self.ai_memory.cleanup_expired()
                except:
                    pass
            
            # 更新统计
            self.stats["last_cleanup"] = datetime.now()
            
            logger.debug("过期记忆清理完成")
        except Exception as e:
            logger.debug(f"清理过期记忆失败: {e}")
    
    async def optimize(self):
        """优化内存使用（增强功能）"""
        try:
            if self.memory_optimizer:
                await self.memory_optimizer.optimize()
            
            # 清理缓存
            self._cache.clear()
            
            logger.debug("内存优化完成")
        except Exception as e:
            logger.debug(f"内存优化失败: {e}")
    
    # ==================== 统计和监控 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        return {
            **self.stats,
            "ai_memory_available": self.ai_memory is not None,
            "hierarchical_memory_available": self.hierarchical_memory is not None,
            "memory_optimizer_available": self.memory_optimizer is not None,
            "enhanced_features": self.enhanced_features
        }
    
    async def save_daily_memory(self, content: str):
        """保存每日记忆"""
        if self.hierarchical_memory:
            try:
                await self.hierarchical_memory.save_daily_memory(content)
            except Exception as e:
                logger.debug(f"保存每日记忆失败: {e}")
    
    # ==================== 清理和关闭 ====================
    
    async def cleanup(self):
        """清理资源"""
        try:
            logger.info("清理统一记忆系统...")
            
            # 清理各组件
            if self.memory_optimizer:
                await self.memory_optimizer.stop()
            
            if self.ai_memory:
                try:
                    await self.ai_memory.cleanup()
                except:
                    pass
            
            # 清理缓存
            self._cache.clear()
            
            logger.info("✅ 统一记忆系统清理完成")
        except Exception as e:
            logger.error(f"清理失败: {e}")
    
    async def export_memories(self, filepath: str):
        """导出记忆"""
        try:
            import json
            
            memories = {
                "short_term": [],
                "medium_term": [],
                "long_term": [],
                "export_time": datetime.now().isoformat()
            }
            
            # 导出短期记忆
            if self.ai_memory and hasattr(self.ai_memory, 'short_term_memory'):
                memories["short_term"] = self.ai_memory.short_term_memory
            
            # 导出长期记忆
            if self.ai_memory and hasattr(self.ai_memory, 'long_term_memory'):
                memories["long_term"] = self.ai_memory.long_term_memory
            
            # 保存到文件
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(memories, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 记忆已导出到: {filepath}")
        except Exception as e:
            logger.error(f"导出记忆失败: {e}")
