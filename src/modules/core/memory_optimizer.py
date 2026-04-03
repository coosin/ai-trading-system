"""
内存优化模块
优化系统内存使用，防止内存泄漏
"""

import asyncio
import logging
import gc
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import weakref

logger = logging.getLogger(__name__)


@dataclass
class MemoryStats:
    """内存统计"""
    total_memory: int
    used_memory: int
    free_memory: int
    memory_percent: float
    swap_used: int
    timestamp: datetime


class MemoryOptimizer:
    """内存优化器"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        self.max_memory_percent = self.config.get("max_memory_percent", 80)
        self.cleanup_interval = self.config.get("cleanup_interval", 300)
        self.cache_size_limit = self.config.get("cache_size_limit", 500)
        
        self._running = False
        self._memory_history: List[MemoryStats] = []
        self._weak_refs: Dict[str, weakref.ref] = {}
        
    async def start(self):
        """启动内存优化器"""
        self._running = True
        asyncio.create_task(self._monitor_loop())
        logger.info("✅ 内存优化器已启动")
    
    async def stop(self):
        """停止内存优化器"""
        self._running = False
        logger.info("内存优化器已停止")
    
    async def _monitor_loop(self):
        """内存监控循环"""
        while self._running:
            try:
                stats = await self.get_memory_stats()
                self._memory_history.append(stats)
                
                if len(self._memory_history) > 100:
                    self._memory_history = self._memory_history[-100:]
                
                if stats.memory_percent > self.max_memory_percent:
                    logger.warning(f"⚠️ 内存使用过高: {stats.memory_percent:.1f}%")
                    await self.optimize_memory()
                
                await asyncio.sleep(self.cleanup_interval)
                
            except Exception as e:
                logger.error(f"内存监控错误: {e}")
                await asyncio.sleep(60)
    
    async def get_memory_stats(self) -> MemoryStats:
        """获取内存统计"""
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(':')
                        value = int(parts[1])
                        meminfo[key] = value
            
            total = meminfo.get('MemTotal', 0) * 1024
            free = meminfo.get('MemFree', 0) * 1024
            available = meminfo.get('MemAvailable', free) * 1024
            used = total - available
            swap_used = meminfo.get('SwapUsed', 0) * 1024 if 'SwapUsed' in meminfo else 0
            
            percent = (used / total * 100) if total > 0 else 0
            
            return MemoryStats(
                total_memory=total,
                used_memory=used,
                free_memory=available,
                memory_percent=percent,
                swap_used=swap_used,
                timestamp=datetime.now()
            )
        except Exception as e:
            logger.debug(f"获取内存统计失败: {e}")
            return MemoryStats(
                total_memory=0,
                used_memory=0,
                free_memory=0,
                memory_percent=0,
                swap_used=0,
                timestamp=datetime.now()
            )
    
    async def optimize_memory(self):
        """优化内存使用"""
        logger.info("🔧 开始内存优化...")
        
        before = await self.get_memory_stats()
        
        gc.collect()
        
        cleaned = gc.collect()
        logger.info(f"   GC清理: {cleaned} 个对象")
        
        self._weak_refs = {k: v for k, v in self._weak_refs.items() if v() is not None}
        
        after = await self.get_memory_stats()
        
        freed = before.used_memory - after.used_memory
        if freed > 0:
            logger.info(f"✅ 内存优化完成，释放: {freed / 1024 / 1024:.1f} MB")
        
        return {
            "before_percent": before.memory_percent,
            "after_percent": after.memory_percent,
            "freed_bytes": freed,
            "gc_collected": cleaned
        }
    
    def register_weak_ref(self, key: str, obj: Any):
        """注册弱引用"""
        try:
            self._weak_refs[key] = weakref.ref(obj)
        except TypeError:
            pass
    
    def get_optimization_report(self) -> Dict[str, Any]:
        """获取优化报告"""
        if not self._memory_history:
            return {"message": "暂无内存历史数据"}
        
        recent = self._memory_history[-10:]
        avg_percent = sum(m.memory_percent for m in recent) / len(recent)
        
        return {
            "current_memory_percent": recent[-1].memory_percent if recent else 0,
            "average_memory_percent": avg_percent,
            "max_memory_percent": self.max_memory_percent,
            "weak_refs_count": len(self._weak_refs),
            "history_count": len(self._memory_history),
            "status": "healthy" if avg_percent < self.max_memory_percent else "warning"
        }


memory_optimizer = MemoryOptimizer()
