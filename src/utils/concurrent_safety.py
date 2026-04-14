"""
并发安全工具

提供线程安全的异步操作机制
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Generic, TypeVar, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

T = TypeVar('T')


class AsyncLock:
    """异步锁包装器"""
    
    def __init__(self, name: str = "unnamed"):
        self._lock = asyncio.Lock()
        self.name = name
        self._lock_count = 0
    
    @asynccontextmanager
    async def acquire(self):
        """获取锁"""
        async with self._lock:
            self._lock_count += 1
            logger.debug(f"锁 {self.name} 被获取 (第{self._lock_count}次)")
            try:
                yield
            finally:
                logger.debug(f"锁 {self.name} 被释放")
    
    def locked(self) -> bool:
        """检查锁是否被占用"""
        return self._lock.locked()


class ThreadSafeDict(Generic[T]):
    """线程安全的字典"""
    
    def __init__(self, name: str = "unnamed"):
        self._data: Dict[str, T] = {}
        self._lock = asyncio.Lock()
        self.name = name
    
    async def get(self, key: str, default: Optional[T] = None) -> Optional[T]:
        """获取值"""
        async with self._lock:
            return self._data.get(key, default)
    
    async def set(self, key: str, value: T) -> None:
        """设置值"""
        async with self._lock:
            self._data[key] = value
            logger.debug(f"{self.name}[{key}] 已更新")
    
    async def delete(self, key: str) -> bool:
        """删除值"""
        async with self._lock:
            if key in self._data:
                del self._data[key]
                logger.debug(f"{self.name}[{key}] 已删除")
                return True
            return False
    
    async def contains(self, key: str) -> bool:
        """检查键是否存在"""
        async with self._lock:
            return key in self._data
    
    async def keys(self) -> list:
        """获取所有键"""
        async with self._lock:
            return list(self._data.keys())
    
    async def values(self) -> list:
        """获取所有值"""
        async with self._lock:
            return list(self._data.values())
    
    async def items(self) -> list:
        """获取所有键值对"""
        async with self._lock:
            return list(self._data.items())
    
    async def clear(self) -> None:
        """清空字典"""
        async with self._lock:
            self._data.clear()
            logger.debug(f"{self.name} 已清空")
    
    async def update(self, data: Dict[str, T]) -> None:
        """批量更新"""
        async with self._lock:
            self._data.update(data)
            logger.debug(f"{self.name} 已批量更新 {len(data)} 项")
    
    async def size(self) -> int:
        """获取大小"""
        async with self._lock:
            return len(self._data)


class ThreadSafeCounter:
    """线程安全的计数器"""
    
    def __init__(self, name: str = "unnamed", initial_value: int = 0):
        self._value = initial_value
        self._lock = asyncio.Lock()
        self.name = name
    
    async def increment(self, delta: int = 1) -> int:
        """增加计数"""
        async with self._lock:
            self._value += delta
            logger.debug(f"{self.name} 增加到 {self._value}")
            return self._value
    
    async def decrement(self, delta: int = 1) -> int:
        """减少计数"""
        async with self._lock:
            self._value -= delta
            logger.debug(f"{self.name} 减少到 {self._value}")
            return self._value
    
    async def get(self) -> int:
        """获取当前值"""
        async with self._lock:
            return self._value
    
    async def set(self, value: int) -> None:
        """设置值"""
        async with self._lock:
            self._value = value
            logger.debug(f"{self.name} 设置为 {self._value}")
    
    async def reset(self) -> None:
        """重置为0"""
        async with self._lock:
            self._value = 0
            logger.debug(f"{self.name} 已重置")


@dataclass
class RateLimiterConfig:
    """速率限制器配置"""
    max_requests: int
    time_window: float  # 秒


class RateLimiter:
    """速率限制器"""
    
    def __init__(self, config: RateLimiterConfig, name: str = "unnamed"):
        self.config = config
        self.name = name
        self._requests: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> bool:
        """获取许可"""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            
            # 清理过期的请求
            while not self._requests.empty():
                timestamp = await self._requests.get()
                if now - timestamp < self.config.time_window:
                    await self._requests.put(timestamp)
                    break
            
            # 检查是否超过限制
            if self._requests.qsize() >= self.config.max_requests:
                logger.warning(f"{self.name} 速率限制触发")
                return False
            
            # 记录新请求
            await self._requests.put(now)
            return True
    
    async def wait_and_acquire(self) -> None:
        """等待并获取许可"""
        while not await self.acquire():
            await asyncio.sleep(0.1)


class SemaphorePool:
    """信号量池"""
    
    def __init__(self, max_concurrent: int, name: str = "unnamed"):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self.name = name
        self._current_count = 0
        self._lock = asyncio.Lock()
    
    @asynccontextmanager
    async def acquire(self):
        """获取信号量"""
        async with self._semaphore:
            async with self._lock:
                self._current_count += 1
                logger.debug(f"{self.name} 信号量获取 (当前: {self._current_count})")
            try:
                yield
            finally:
                async with self._lock:
                    self._current_count -= 1
                    logger.debug(f"{self.name} 信号量释放 (当前: {self._current_count})")
    
    async def get_current_count(self) -> int:
        """获取当前并发数"""
        async with self._lock:
            return self._current_count
