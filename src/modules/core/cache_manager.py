"""
缓存管理器模块 - 全智能量化交易系统的性能核心

功能：
1. 多级缓存支持（内存、Redis、磁盘）
2. 智能缓存策略（LRU、TTL、LFU）
3. 缓存预热和预加载
4. 缓存监控和统计
5. 分布式缓存支持
"""

import asyncio
import hashlib
import json
import logging
import pickle
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

# 尝试导入aioredis，如果不兼容则使用备用方案
try:
    import aioredis
    HAS_AIOREDIS = True
except (ImportError, TypeError):
    HAS_AIOREDIS = False
    aioredis = None

try:
    import msgpack
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False
    msgpack = None

logger = logging.getLogger(__name__)


class CacheLevel(Enum):
    """缓存级别"""

    MEMORY = "memory"  # 内存缓存（最快）
    REDIS = "redis"  # Redis缓存（分布式）
    DISK = "disk"  # 磁盘缓存（持久化）


class EvictionPolicy(Enum):
    """缓存淘汰策略"""

    LRU = "lru"  # 最近最少使用
    LFU = "lfu"  # 最不经常使用
    TTL = "ttl"  # 生存时间
    RANDOM = "random"  # 随机淘汰


class CacheStatus(Enum):
    """缓存状态"""

    HIT = "hit"  # 缓存命中
    MISS = "miss"  # 缓存未命中
    EXPIRED = "expired"  # 缓存过期
    STALE = "stale"  # 缓存陈旧但可用


@dataclass
class CacheEntry:
    """缓存条目"""

    key: str
    value: Any
    level: CacheLevel
    created_at: datetime
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    @property
    def age(self) -> timedelta:
        """缓存年龄"""
        return datetime.now() - self.created_at

    @property
    def ttl(self) -> Optional[float]:
        """剩余生存时间（秒）"""
        if self.expires_at is None:
            return None
        ttl = (self.expires_at - datetime.now()).total_seconds()
        return max(0, ttl) if ttl > 0 else 0

    def touch(self) -> None:
        """更新访问时间"""
        self.last_accessed = datetime.now()
        self.access_count += 1


@dataclass
class CacheStats:
    """缓存统计"""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size_bytes: int = 0
    average_load_time_ms: float = 0.0
    hit_rate: float = 0.0

    def update_hit_rate(self) -> None:
        """更新命中率"""
        total = self.hits + self.misses
        self.hit_rate = self.hits / total if total > 0 else 0.0


class CacheManager:
    """
    缓存管理器

    核心功能：
    1. 多级缓存管理
    2. 智能缓存策略
    3. 缓存预热和预加载
    4. 缓存监控和统计
    5. 分布式缓存支持
    """

    def __init__(self, config_manager=None, max_memory_size: int = 100 * 1024 * 1024):
        """
        初始化缓存管理器

        Args:
            config_manager: 配置管理器实例
            max_memory_size: 内存缓存最大大小（字节）
        """
        self.config_manager = config_manager
        self.max_memory_size = max_memory_size

        # 内存缓存（使用OrderedDict实现LRU）
        self.memory_cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.memory_size = 0

        # Redis客户端
        self.redis_client: Optional[aioredis.Redis] = None
        self.redis_connected = False

        # 磁盘缓存路径
        self.disk_cache_path = "/tmp/cache"

        # 配置
        self.default_ttl = 3600  # 默认1小时
        self.eviction_policy = EvictionPolicy.LRU
        self.enable_compression = True
        self.enable_encryption = False

        # 统计信息
        self.stats: Dict[CacheLevel, CacheStats] = {
            CacheLevel.MEMORY: CacheStats(),
            CacheLevel.REDIS: CacheStats(),
            CacheLevel.DISK: CacheStats(),
        }

        # 缓存键前缀
        self.key_prefix = "trading:cache:"

        # 锁和状态
        self._lock = asyncio.Lock()
        self._initialized = False
        self._cleanup_task: Optional[asyncio.Task] = None

        logger.info(f"缓存管理器初始化，内存限制: {max_memory_size / 1024 / 1024:.1f}MB")

    async def initialize(self) -> None:
        """
        初始化缓存管理器

        连接Redis，加载配置，启动清理任务
        """
        if self._initialized:
            return

        logger.info("初始化缓存管理器...")

        # 加载配置
        if self.config_manager:
            cache_config = await self.config_manager.get_config("cache", {})
            self.default_ttl = cache_config.get("default_ttl", self.default_ttl)
            self.eviction_policy = EvictionPolicy(cache_config.get("eviction_policy", "lru"))
            self.enable_compression = cache_config.get("enable_compression", True)
            self.enable_encryption = cache_config.get("enable_encryption", False)
            self.max_memory_size = cache_config.get("max_memory_size", self.max_memory_size)

        # 连接Redis（如果配置了）
        redis_config = await self._get_redis_config()
        if redis_config and HAS_AIOREDIS and aioredis:
            try:
                self.redis_client = await aioredis.from_url(
                    f"redis://{redis_config.get('host', 'localhost')}:{redis_config.get('port', 6379)}",
                    password=redis_config.get("password"),
                    db=redis_config.get("db", 0),
                    encoding="utf-8",
                    decode_responses=False,
                )
                await self.redis_client.ping()
                self.redis_connected = True
                logger.info("Redis连接成功")
            except Exception as e:
                logger.warning(f"Redis连接失败: {e}, 将使用内存缓存")
        elif redis_config:
            logger.debug("aioredis未正确加载，跳过Redis连接")

        # 创建磁盘缓存目录
        import os

        os.makedirs(self.disk_cache_path, exist_ok=True)

        # 启动清理任务
        self._cleanup_task = asyncio.create_task(self._cleanup_worker())

        self._initialized = True
        logger.info("缓存管理器初始化完成")

    async def cleanup(self) -> None:
        """
        清理缓存管理器

        关闭连接，停止任务
        """
        logger.info("清理缓存管理器...")

        self._initialized = False

        # 停止清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # 关闭Redis连接
        if self.redis_client:
            await self.redis_client.close()
            self.redis_connected = False

        # 清空内存缓存
        self.memory_cache.clear()
        self.memory_size = 0

        logger.info("缓存管理器清理完成")

    async def get(
        self, key: str, default: Any = None, level: CacheLevel = CacheLevel.MEMORY
    ) -> Any:
        """
        获取缓存值

        Args:
            key: 缓存键
            default: 默认值（如果未找到）
            level: 缓存级别（优先从该级别查找）

        Returns:
            缓存值或默认值
        """
        async with self._lock:
            # 生成完整键
            full_key = self._make_key(key)

            # 按级别优先级查找
            levels_to_try = self._get_level_priority(level)

            for cache_level in levels_to_try:
                try:
                    value = await self._get_from_level(full_key, cache_level)
                    if value is not None:
                        # 更新统计
                        self.stats[cache_level].hits += 1
                        self.stats[cache_level].update_hit_rate()

                        # 如果从非内存缓存找到，可以提升到内存缓存
                        if cache_level != CacheLevel.MEMORY:
                            await self._set_to_level(
                                full_key, value, CacheLevel.MEMORY, ttl=self.default_ttl
                            )

                        logger.debug(f"缓存命中: {key} [{cache_level.value}]")
                        return value

                except Exception as e:
                    logger.error(f"从{cache_level.value}缓存获取失败 {key}: {e}")

            # 未找到
            for cache_level in levels_to_try:
                self.stats[cache_level].misses += 1
                self.stats[cache_level].update_hit_rate()

            logger.debug(f"缓存未命中: {key}")
            return default

    async def set(
        self, key: str, value: Any, ttl: Optional[int] = None, level: CacheLevel = CacheLevel.MEMORY
    ) -> bool:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 生存时间（秒），None表示永不过期
            level: 缓存级别

        Returns:
            是否设置成功
        """
        async with self._lock:
            # 生成完整键
            full_key = self._make_key(key)

            # 设置TTL
            if ttl is None:
                ttl = self.default_ttl

            try:
                success = await self._set_to_level(full_key, value, level, ttl)
                if success:
                    logger.debug(f"缓存设置: {key} [{level.value}], TTL: {ttl}s")
                return success

            except Exception as e:
                logger.error(f"设置缓存失败 {key} [{level.value}]: {e}")
                return False

    async def delete(self, key: str, level: Optional[CacheLevel] = None) -> bool:
        """
        删除缓存值

        Args:
            key: 缓存键
            level: 缓存级别（None表示所有级别）

        Returns:
            是否删除成功
        """
        async with self._lock:
            full_key = self._make_key(key)
            success = True

            if level is None:
                # 从所有级别删除
                for cache_level in CacheLevel:
                    try:
                        if not await self._delete_from_level(full_key, cache_level):
                            success = False
                    except Exception as e:
                        logger.error(f"从{cache_level.value}缓存删除失败 {key}: {e}")
                        success = False
            else:
                # 从指定级别删除
                try:
                    success = await self._delete_from_level(full_key, level)
                except Exception as e:
                    logger.error(f"从{level.value}缓存删除失败 {key}: {e}")
                    success = False

            if success:
                logger.debug(f"缓存删除: {key}" + (f" [{level.value}]" if level else ""))

            return success

    async def exists(self, key: str, level: Optional[CacheLevel] = None) -> bool:
        """
        检查缓存是否存在

        Args:
            key: 缓存键
            level: 缓存级别（None表示任何级别）

        Returns:
            是否存在
        """
        async with self._lock:
            full_key = self._make_key(key)

            if level is None:
                # 检查任何级别
                for cache_level in CacheLevel:
                    try:
                        if await self._exists_in_level(full_key, cache_level):
                            return True
                    except Exception:
                        continue
                return False
            else:
                # 检查指定级别
                try:
                    return await self._exists_in_level(full_key, level)
                except Exception:
                    return False

    async def clear(self, level: Optional[CacheLevel] = None) -> bool:
        """
        清空缓存

        Args:
            level: 缓存级别（None表示所有级别）

        Returns:
            是否清空成功
        """
        async with self._lock:
            success = True

            if level is None:
                # 清空所有级别
                for cache_level in CacheLevel:
                    try:
                        if not await self._clear_level(cache_level):
                            success = False
                    except Exception as e:
                        logger.error(f"清空{cache_level.value}缓存失败: {e}")
                        success = False
            else:
                # 清空指定级别
                try:
                    success = await self._clear_level(level)
                except Exception as e:
                    logger.error(f"清空{level.value}缓存失败: {e}")
                    success = False

            if success:
                logger.info(f"缓存清空完成" + (f" [{level.value}]" if level else ""))

            return success

    async def get_stats(self, level: Optional[CacheLevel] = None) -> Dict[str, Any]:
        """
        获取缓存统计

        Args:
            level: 缓存级别（None表示所有级别）

        Returns:
            统计信息
        """
        async with self._lock:
            if level:
                stats = self.stats[level]
                return {
                    "level": level.value,
                    "hits": stats.hits,
                    "misses": stats.misses,
                    "hit_rate": stats.hit_rate,
                    "evictions": stats.evictions,
                    "size_bytes": stats.size_bytes,
                    "average_load_time_ms": stats.average_load_time_ms,
                }
            else:
                result = {}
                for cache_level, stats in self.stats.items():
                    result[cache_level.value] = {
                        "hits": stats.hits,
                        "misses": stats.misses,
                        "hit_rate": stats.hit_rate,
                        "evictions": stats.evictions,
                        "size_bytes": stats.size_bytes,
                        "average_load_time_ms": stats.average_load_time_ms,
                    }
                return result

    async def warmup(self, keys: List[str], loader: Callable[[str], Awaitable[Any]]) -> None:
        """
        缓存预热

        Args:
            keys: 要预热的键列表
            loader: 加载函数，接收键返回值
        """
        logger.info(f"开始缓存预热，{len(keys)}个键")

        tasks = []
        for key in keys:
            task = asyncio.create_task(self._warmup_key(key, loader))
            tasks.append(task)

        # 并发预热
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if not isinstance(r, Exception))
        logger.info(f"缓存预热完成，成功: {success_count}/{len(keys)}")

    async def prefetch(self, pattern: str, level: CacheLevel = CacheLevel.MEMORY) -> List[str]:
        """
        缓存预取

        Args:
            pattern: 键模式（支持通配符）
            level: 缓存级别

        Returns:
            预取的键列表
        """
        # 这里可以实现基于模式的预取逻辑
        # 例如：预取所有以某个前缀开头的键

        logger.info(f"缓存预取: {pattern} [{level.value}]")
        return []

    # 私有方法

    def _make_key(self, key: str) -> str:
        """生成完整缓存键"""
        return f"{self.key_prefix}{key}"

    def _get_level_priority(self, preferred_level: CacheLevel) -> List[CacheLevel]:
        """获取缓存级别优先级列表"""
        if preferred_level == CacheLevel.MEMORY:
            return [CacheLevel.MEMORY, CacheLevel.REDIS, CacheLevel.DISK]
        elif preferred_level == CacheLevel.REDIS:
            return [CacheLevel.REDIS, CacheLevel.MEMORY, CacheLevel.DISK]
        else:  # DISK
            return [CacheLevel.DISK, CacheLevel.REDIS, CacheLevel.MEMORY]

    async def _get_from_level(self, key: str, level: CacheLevel) -> Any:
        """从指定级别获取缓存"""
        if level == CacheLevel.MEMORY:
            return self._get_from_memory(key)
        elif level == CacheLevel.REDIS:
            return await self._get_from_redis(key)
        elif level == CacheLevel.DISK:
            return await self._get_from_disk(key)
        else:
            raise ValueError(f"不支持的缓存级别: {level}")

    async def _set_to_level(self, key: str, value: Any, level: CacheLevel, ttl: int) -> bool:
        """设置缓存到指定级别"""
        if level == CacheLevel.MEMORY:
            return self._set_to_memory(key, value, ttl)
        elif level == CacheLevel.REDIS:
            return await self._set_to_redis(key, value, ttl)
        elif level == CacheLevel.DISK:
            return await self._set_to_disk(key, value, ttl)
        else:
            raise ValueError(f"不支持的缓存级别: {level}")

    async def _delete_from_level(self, key: str, level: CacheLevel) -> bool:
        """从指定级别删除缓存"""
        if level == CacheLevel.MEMORY:
            return self._delete_from_memory(key)
        elif level == CacheLevel.REDIS:
            return await self._delete_from_redis(key)
        elif level == CacheLevel.DISK:
            return await self._delete_from_disk(key)
        else:
            raise ValueError(f"不支持的缓存级别: {level}")

    async def _exists_in_level(self, key: str, level: CacheLevel) -> bool:
        """检查指定级别是否存在"""
        if level == CacheLevel.MEMORY:
            return key in self.memory_cache
        elif level == CacheLevel.REDIS:
            if not self.redis_connected:
                return False
            return await self.redis_client.exists(key) > 0
        elif level == CacheLevel.DISK:
            import os

            return os.path.exists(self._get_disk_path(key))
        else:
            raise ValueError(f"不支持的缓存级别: {level}")

    async def _clear_level(self, level: CacheLevel) -> bool:
        """清空指定级别缓存"""
        if level == CacheLevel.MEMORY:
            self.memory_cache.clear()
            self.memory_size = 0
            self.stats[level].size_bytes = 0
            return True
        elif level == CacheLevel.REDIS:
            if not self.redis_connected:
                return False
            await self.redis_client.flushdb()
            return True
        elif level == CacheLevel.DISK:
            import shutil

            try:
                shutil.rmtree(self.disk_cache_path)
                os.makedirs(self.disk_cache_path, exist_ok=True)
                return True
            except Exception:
                return False
        else:
            raise ValueError(f"不支持的缓存级别: {level}")

    # 内存缓存实现

    def _get_from_memory(self, key: str) -> Any:
        """从内存获取缓存"""
        if key not in self.memory_cache:
            return None

        entry = self.memory_cache[key]

        # 检查是否过期
        if entry.is_expired:
            del self.memory_cache[key]
            self.memory_size -= self._estimate_size(entry.value)
            self.stats[CacheLevel.MEMORY].evictions += 1
            return None

        # 更新访问时间（LRU）
        self.memory_cache.move_to_end(key)
        entry.touch()

        return entry.value

    def _set_to_memory(self, key: str, value: Any, ttl: int) -> bool:
        """设置内存缓存"""
        # 检查内存限制
        value_size = self._estimate_size(value)

        # 如果超出限制，执行淘汰
        while self.memory_size + value_size > self.max_memory_size and self.memory_cache:
            self._evict_from_memory()

        # 创建缓存条目
        expires_at = datetime.now() + timedelta(seconds=ttl) if ttl > 0 else None
        entry = CacheEntry(
            key=key,
            value=value,
            level=CacheLevel.MEMORY,
            created_at=datetime.now(),
            expires_at=expires_at,
        )

        # 添加或更新
        if key in self.memory_cache:
            old_entry = self.memory_cache[key]
            self.memory_size -= self._estimate_size(old_entry.value)

        self.memory_cache[key] = entry
        self.memory_cache.move_to_end(key)  # 移动到最近使用
        self.memory_size += value_size
        self.stats[CacheLevel.MEMORY].size_bytes = self.memory_size

        return True

    def _delete_from_memory(self, key: str) -> bool:
        """从内存删除缓存"""
        if key in self.memory_cache:
            entry = self.memory_cache[key]
            self.memory_size -= self._estimate_size(entry.value)
            del self.memory_cache[key]
            self.stats[CacheLevel.MEMORY].size_bytes = self.memory_size
            return True
        return False

    def _evict_from_memory(self) -> None:
        """从内存淘汰缓存（根据策略）"""
        if not self.memory_cache:
            return

        if self.eviction_policy == EvictionPolicy.LRU:
            # LRU：淘汰最久未使用的
            key, entry = next(iter(self.memory_cache.items()))
        elif self.eviction_policy == EvictionPolicy.LFU:
            # LFU：淘汰访问次数最少的
            key = min(self.memory_cache.keys(), key=lambda k: self.memory_cache[k].access_count)
            entry = self.memory_cache[key]
        elif self.eviction_policy == EvictionPolicy.TTL:
            # TTL：淘汰最早过期的
            key = min(
                self.memory_cache.keys(),
                key=lambda k: (
                    self.memory_cache[k].expires_at
                    if self.memory_cache[k].expires_at
                    else datetime.max
                ),
            )
            entry = self.memory_cache[key]
        else:  # RANDOM
            # 随机淘汰
            import random

            key = random.choice(list(self.memory_cache.keys()))
            entry = self.memory_cache[key]

        # 删除
        del self.memory_cache[key]
        self.memory_size -= self._estimate_size(entry.value)
        self.stats[CacheLevel.MEMORY].evictions += 1
        self.stats[CacheLevel.MEMORY].size_bytes = self.memory_size

        logger.debug(f"内存缓存淘汰: {key}")

    # Redis缓存实现

    async def _get_from_redis(self, key: str) -> Any:
        """从Redis获取缓存"""
        if not self.redis_connected:
            return None

        try:
            data = await self.redis_client.get(key)
            if data is None:
                return None

            # 反序列化
            if self.enable_compression:
                # 这里可以实现压缩解压
                pass

            value = pickle.loads(data)
            return value

        except Exception as e:
            logger.error(f"从Redis获取缓存失败 {key}: {e}")
            return None

    async def _set_to_redis(self, key: str, value: Any, ttl: int) -> bool:
        """设置Redis缓存"""
        if not self.redis_connected:
            return False

        try:
            # 序列化
            data = pickle.dumps(value)

            if self.enable_compression:
                # 这里可以实现压缩
                pass

            # 设置缓存
            if ttl > 0:
                await self.redis_client.setex(key, ttl, data)
            else:
                await self.redis_client.set(key, data)

            return True

        except Exception as e:
            logger.error(f"设置Redis缓存失败 {key}: {e}")
            return False

    async def _delete_from_redis(self, key: str) -> bool:
        """从Redis删除缓存"""
        if not self.redis_connected:
            return False

        try:
            result = await self.redis_client.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"从Redis删除缓存失败 {key}: {e}")
            return False

    # 磁盘缓存实现

    def _get_disk_path(self, key: str) -> str:
        """获取磁盘缓存路径"""
        # 使用哈希避免文件名过长
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return f"{self.disk_cache_path}/{key_hash}.cache"

    async def _get_from_disk(self, key: str) -> Any:
        """从磁盘获取缓存"""
        import os

        import aiofiles

        path = self._get_disk_path(key)
        if not os.path.exists(path):
            return None

        try:
            async with aiofiles.open(path, "rb") as f:
                data = await f.read()

            # 检查是否过期（通过文件修改时间）
            stat = os.stat(path)
            created_time = datetime.fromtimestamp(stat.st_mtime)
            max_age = timedelta(days=7)  # 磁盘缓存最大保存7天

            if datetime.now() - created_time > max_age:
                os.remove(path)
                return None

            # 反序列化
            value = pickle.loads(data)
            return value

        except Exception as e:
            logger.error(f"从磁盘获取缓存失败 {key}: {e}")
            return None

    async def _set_to_disk(self, key: str, value: Any, ttl: int) -> bool:
        """设置磁盘缓存"""
        import os

        import aiofiles

        # 磁盘缓存忽略TTL，使用文件系统时间
        path = self._get_disk_path(key)

        try:
            # 序列化
            data = pickle.dumps(value)

            async with aiofiles.open(path, "wb") as f:
                await f.write(data)

            return True

        except Exception as e:
            logger.error(f"设置磁盘缓存失败 {key}: {e}")
            return False

    async def _delete_from_disk(self, key: str) -> bool:
        """从磁盘删除缓存"""
        import os

        path = self._get_disk_path(key)
        if os.path.exists(path):
            try:
                os.remove(path)
                return True
            except Exception as e:
                logger.error(f"从磁盘删除缓存失败 {key}: {e}")
                return False
        return False

    # 辅助方法

    def _estimate_size(self, value: Any) -> int:
        """估算值的大小（字节）"""
        try:
            # 使用pickle序列化来估算大小
            data = pickle.dumps(value)
            return len(data)
        except:
            # 如果序列化失败，返回估计值
            return 1024  # 默认1KB

    async def _get_redis_config(self) -> Optional[Dict[str, Any]]:
        """获取Redis配置"""
        import os
        if self.config_manager:
            config = await self.config_manager.get_config("redis", None)
            if config:
                return config
        
        if os.path.exists("/.dockerenv"):
            return {
                "host": os.environ.get("REDIS_HOST", "openclaw-redis"),
                "port": int(os.environ.get("REDIS_PORT", 6379)),
                "db": 0
            }
        return None

    async def _cleanup_worker(self) -> None:
        """清理工作线程"""
        logger.info("启动缓存清理线程")

        while self._initialized:
            try:
                await asyncio.sleep(60)  # 每分钟清理一次

                # 清理过期的内存缓存
                expired_keys = []
                for key, entry in list(self.memory_cache.items()):
                    if entry.is_expired:
                        expired_keys.append(key)

                for key in expired_keys:
                    self._delete_from_memory(key)

                if expired_keys:
                    logger.debug(f"清理了 {len(expired_keys)} 个过期的内存缓存")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"缓存清理错误: {e}")
                await asyncio.sleep(60)

    async def _warmup_key(self, key: str, loader: Callable[[str], Awaitable[Any]]) -> None:
        """预热单个键"""
        try:
            value = await loader(key)
            if value is not None:
                await self.set(key, value, level=CacheLevel.MEMORY)
                logger.debug(f"缓存预热成功: {key}")
        except Exception as e:
            logger.warning(f"缓存预热失败 {key}: {e}")


# 使用示例
async def example_usage():
    """缓存管理器使用示例"""

    # 创建缓存管理器
    cache = CacheManager(max_memory_size=50 * 1024 * 1024)  # 50MB内存缓存
    await cache.initialize()

    try:
        # 设置缓存
        await cache.set("user:1", {"name": "Alice", "age": 30}, ttl=300)
        await cache.set("product:100", {"id": 100, "name": "Laptop", "price": 999.99}, ttl=600)

        # 获取缓存
        user = await cache.get("user:1")
        logger.info(f"用户缓存: {user}")

        product = await cache.get("product:100")
        logger.info(f"产品缓存: {product}")

        # 检查是否存在
        exists = await cache.exists("user:1")
        logger.info(f"用户缓存是否存在: {exists}")

        # 获取统计信息
        stats = await cache.get_stats()
        logger.info(f"缓存统计: {stats}")

        # 批量操作
        for i in range(10):
            await cache.set(f"item:{i}", f"value_{i}", ttl=60)

        # 预热缓存
        async def data_loader(key: str):
            # 模拟从数据库加载数据
            await asyncio.sleep(0.1)
            return f"loaded_{key}"

        await cache.warmup(["prefetch:1", "prefetch:2", "prefetch:3"], data_loader)

        # 清理
        await cache.delete("user:1")

    finally:
        await cache.cleanup()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
