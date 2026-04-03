"""
智能缓存系统

为无人化AI交易系统提供高性能缓存能力
"""

import asyncio
import logging
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: datetime = field(default_factory=datetime.now)
    size: int = 0  # 字节数


class IntelligentCacheSystem:
    """智能缓存系统"""
    
    def __init__(self, max_size: int = 500, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        
        self._cache: Dict[str, CacheEntry] = {}
        
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "total_size": 0,
        }
        
        self.ttl_config = {
            "market_data": 10,
            "indicators": 120,
            "ai_analysis": 600,
            "account_info": 15,
            "positions": 10,
        }
        
        self._last_cleanup = datetime.now()
        self._cleanup_interval = 60
    
    async def get_or_compute(
        self,
        key: str,
        compute_func: Callable,
        ttl: Optional[int] = None,
        cache_type: Optional[str] = None
    ) -> Any:
        """
        获取或计算缓存
        
        Args:
            key: 缓存键
            compute_func: 计算函数
            ttl: 过期时间(秒)
            cache_type: 缓存类型
        
        Returns:
            缓存值或计算结果
        """
        
        # 确定TTL
        if ttl is None:
            if cache_type and cache_type in self.ttl_config:
                ttl = self.ttl_config[cache_type]
            else:
                ttl = self.default_ttl
        
        # 尝试从缓存获取
        cached_value = await self.get(key)
        
        if cached_value is not None:
            self.stats["hits"] += 1
            return cached_value
        
        # 缓存未命中，计算新值
        self.stats["misses"] += 1
        
        # 执行计算
        if asyncio.iscoroutinefunction(compute_func):
            value = await compute_func()
        else:
            value = compute_func()
        
        # 保存到缓存
        await self.set(key, value, ttl)
        
        return value
    
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        
        # 检查是否过期
        if entry.expires_at and datetime.now() > entry.expires_at:
            await self.delete(key)
            return None
        
        # 更新访问统计
        entry.access_count += 1
        entry.last_accessed = datetime.now()
        
        return entry.value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """设置缓存值"""
        
        # 计算过期时间
        if ttl is None:
            ttl = self.default_ttl
        
        expires_at = datetime.now() + timedelta(seconds=ttl)
        
        # 计算大小
        try:
            size = len(json.dumps(value))
        except:
            size = 1
        
        # 检查是否需要清理
        if len(self._cache) >= self.max_size:
            await self._evict()
        
        # 创建缓存条目
        entry = CacheEntry(
            key=key,
            value=value,
            expires_at=expires_at,
            size=size
        )
        
        self._cache[key] = entry
        self.stats["total_size"] += size
    
    async def delete(self, key: str) -> bool:
        """删除缓存"""
        
        if key not in self._cache:
            return False
        
        entry = self._cache[key]
        self.stats["total_size"] -= entry.size
        
        del self._cache[key]
        
        return True
    
    async def clear(self):
        """清空缓存"""
        
        self._cache.clear()
        self.stats["total_size"] = 0
        
        logger.info("缓存已清空")
    
    async def _evict(self):
        """清理缓存"""
        
        # 使用LRU策略
        # 按最后访问时间排序
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda x: x[1].last_accessed
        )
        
        # 删除最旧的20%
        evict_count = max(1, len(sorted_entries) // 5)
        
        for key, entry in sorted_entries[:evict_count]:
            await self.delete(key)
            self.stats["evictions"] += 1
        
        logger.debug(f"清理了{evict_count}个缓存条目")
    
    def generate_key(self, *args, **kwargs) -> str:
        """生成缓存键"""
        
        # 将参数转换为字符串
        key_parts = [str(arg) for arg in args]
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        
        key_string = ":".join(key_parts)
        
        # 使用MD5生成唯一键
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        
        total_requests = self.stats["hits"] + self.stats["misses"]
        
        return {
            "total_entries": len(self._cache),
            "max_size": self.max_size,
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "hit_rate": (self.stats["hits"] / total_requests * 100) if total_requests > 0 else 0,
            "evictions": self.stats["evictions"],
            "total_size_bytes": self.stats["total_size"],
        }
    
    async def cleanup_expired(self):
        """清理过期缓存"""
        
        now = datetime.now()
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.expires_at and now > entry.expires_at
        ]
        
        for key in expired_keys:
            await self.delete(key)
        
        if expired_keys:
            logger.debug(f"清理了{len(expired_keys)}个过期缓存")
