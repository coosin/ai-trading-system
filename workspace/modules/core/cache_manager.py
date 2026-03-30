#!/usr/bin/env python3
"""
智能缓存管理器
支持多级缓存、智能失效、内存优化和Redis集成
"""

import asyncio
import functools
import gzip
import hashlib
import json
import pickle
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Union

# 尝试导入Redis
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


@dataclass
class CacheEntry:
    """缓存条目"""

    key: str
    value: Any
    timestamp: datetime
    ttl_seconds: int
    hits: int = 0
    last_access: datetime = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.last_access is None:
            self.last_access = self.timestamp
        if self.metadata is None:
            self.metadata = {}

    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.ttl_seconds <= 0:
            return False  # 永不过期

        age = (datetime.now() - self.timestamp).total_seconds()
        return age > self.ttl_seconds

    def access(self):
        """访问缓存"""
        self.hits += 1
        self.last_access = datetime.now()

    def remaining_ttl(self) -> float:
        """剩余TTL（秒）"""
        if self.ttl_seconds <= 0:
            return float("inf")

        age = (datetime.now() - self.timestamp).total_seconds()
        return max(0, self.ttl_seconds - age)


@dataclass
class CacheStats:
    """缓存统计"""

    timestamp: datetime
    total_entries: int
    total_size_bytes: int
    hits: int
    misses: int
    hit_rate: float
    evictions: int
    memory_usage_percent: float
    avg_entry_size_bytes: float
    top_keys: List[Dict[str, Any]]


class LRUCache:
    """LRU缓存实现"""

    def __init__(self, max_size: int = 1000):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if key in self.cache:
            self.cache.move_to_end(key)  # 标记为最近使用
            self.hits += 1
            return self.cache[key]
        else:
            self.misses += 1
            return None

    def set(self, key: str, value: Any):
        """设置缓存值"""
        if key in self.cache:
            self.cache[key] = value
            self.cache.move_to_end(key)
        else:
            self.cache[key] = value

            # 如果超过最大大小，移除最旧的条目
            if len(self.cache) > self.max_size:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                self.evictions += 1

    def delete(self, key: str) -> bool:
        """删除缓存值"""
        if key in self.cache:
            del self.cache[key]
            return True
        return False

    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def size(self) -> int:
        """缓存大小"""
        return len(self.cache)

    def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0

        return {
            "size": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
            "evictions": self.evictions,
            "max_size": self.max_size,
        }


class SmartCacheManager:
    """智能缓存管理器"""

    def __init__(self, config_manager=None):
        self.config_manager = config_manager

        # 多级缓存
        self.l1_cache = LRUCache(max_size=1000)  # 内存缓存
        self.l2_cache = None  # Redis缓存（可选）
        self.l3_cache = {}  # 磁盘缓存（TODO）

        # 缓存条目存储
        self.cache_entries: Dict[str, CacheEntry] = {}

        # Redis配置
        self.redis_enabled = False
        self.redis_client = None

        # 统计信息
        self.stats_history: List[CacheStats] = []
        self.total_hits = 0
        self.total_misses = 0

        # 清理任务
        self.cleanup_task = None
        self.stats_task = None
        self.is_running = False

        # 线程池用于异步操作
        self.thread_pool = ThreadPoolExecutor(max_workers=4)

        # 配置
        self.config = {
            "default_ttl_seconds": 300,  # 5分钟
            "max_memory_mb": 100,  # 最大内存使用
            "compression_enabled": True,
            "redis_enabled": False,
            "redis_host": "localhost",
            "redis_port": 6379,
            "redis_db": 0,
            "cleanup_interval_seconds": 60,
            "stats_interval_seconds": 300,
        }

        # 加载配置
        if config_manager:
            self._load_config()

    def _load_config(self):
        """加载配置"""

        if not self.config_manager:
            return

        cache_config = self.config_manager.get_config("data_sources", "cache_settings", {})

        if cache_config:
            self.config.update(
                {
                    "default_ttl_seconds": cache_config.get("ttl_seconds", 300),
                    "max_memory_mb": cache_config.get("max_size_mb", 100),
                    "compression_enabled": cache_config.get("enabled", True),
                    "redis_enabled": cache_config.get("redis_enabled", False),
                    "redis_host": cache_config.get("redis_host", "localhost"),
                    "redis_port": cache_config.get("redis_port", 6379),
                    "redis_db": cache_config.get("redis_db", 0),
                }
            )

    async def start(self):
        """启动缓存管理器"""

        if self.is_running:
            print("缓存管理器已启动")
            return

        print("🚀 启动智能缓存管理器...")
        self.is_running = True

        # 初始化Redis
        if self.config["redis_enabled"] and REDIS_AVAILABLE:
            await self._init_redis()

        # 启动清理任务
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_entries())

        # 启动统计任务
        self.stats_task = asyncio.create_task(self._collect_stats())

        print("✅ 智能缓存管理器已启动")

    async def stop(self):
        """停止缓存管理器"""

        print("🛑 停止智能缓存管理器...")
        self.is_running = False

        # 停止任务
        if self.cleanup_task:
            self.cleanup_task.cancel()
        if self.stats_task:
            self.stats_task.cancel()

        # 停止线程池
        self.thread_pool.shutdown(wait=True)

        # 断开Redis连接
        if self.redis_client:
            self.redis_client.close()

        print("✅ 智能缓存管理器已停止")

    async def _init_redis(self):
        """初始化Redis连接"""

        try:
            self.redis_client = redis.Redis(
                host=self.config["redis_host"],
                port=self.config["redis_port"],
                db=self.config["redis_db"],
                decode_responses=False,  # 保持二进制
            )

            # 测试连接
            if self.redis_client.ping():
                self.redis_enabled = True
                print(f"✅ Redis连接成功: {self.config['redis_host']}:{self.config['redis_port']}")
            else:
                print("❌ Redis连接失败")
                self.redis_enabled = False

        except Exception as e:
            print(f"❌ Redis初始化失败: {e}")
            self.redis_enabled = False

    async def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值"""

        # L1缓存检查
        l1_value = self.l1_cache.get(key)
        if l1_value is not None:
            # 检查缓存条目
            entry = self.cache_entries.get(key)
            if entry and not entry.is_expired():
                entry.access()
                self.total_hits += 1
                return l1_value

        # L2缓存检查（Redis）
        l2_value = await self._get_from_redis(key)
        if l2_value is not None:
            # 放入L1缓存
            self.l1_cache.set(key, l2_value)

            # 更新缓存条目
            entry = self.cache_entries.get(key)
            if entry:
                entry.access()

            self.total_hits += 1
            return l2_value

        # L3缓存检查（磁盘）
        # TODO: 实现磁盘缓存

        self.total_misses += 1
        return default

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = None,
        metadata: Dict[str, Any] = None,
        compress: bool = None,
    ):
        """设置缓存值"""

        if ttl_seconds is None:
            ttl_seconds = self.config["default_ttl_seconds"]

        if compress is None:
            compress = self.config["compression_enabled"]

        # 准备存储的值
        value_to_store = value
        if compress and isinstance(value, (bytes, str, dict, list)):
            value_to_store = self._compress(value)

        # 创建缓存条目
        entry = CacheEntry(
            key=key,
            value=value_to_store,
            timestamp=datetime.now(),
            ttl_seconds=ttl_seconds,
            metadata=metadata or {},
        )

        # 存储到L1缓存
        self.l1_cache.set(key, value_to_store)
        self.cache_entries[key] = entry

        # 存储到L2缓存（Redis）
        if self.redis_enabled:
            await self._set_to_redis(key, value_to_store, ttl_seconds)

        # 存储到L3缓存（磁盘）
        # TODO: 实现磁盘缓存

    async def delete(self, key: str) -> bool:
        """删除缓存值"""

        # 从L1删除
        l1_deleted = self.l1_cache.delete(key)

        # 从缓存条目删除
        if key in self.cache_entries:
            del self.cache_entries[key]

        # 从L2删除
        l2_deleted = False
        if self.redis_enabled:
            l2_deleted = await self._delete_from_redis(key)

        return l1_deleted or l2_deleted

    async def get_or_set(
        self, key: str, callback: Callable, ttl_seconds: int = None, *args, **kwargs
    ) -> Any:
        """获取或设置缓存值（缓存穿透防护）"""

        # 尝试获取缓存
        cached_value = await self.get(key)
        if cached_value is not None:
            return cached_value

        # 执行回调获取数据
        try:
            if asyncio.iscoroutinefunction(callback):
                value = await callback(*args, **kwargs)
            else:
                # 在线程池中执行同步函数
                loop = asyncio.get_event_loop()
                value = await loop.run_in_executor(
                    self.thread_pool, functools.partial(callback, *args, **kwargs)
                )

            # 设置缓存
            await self.set(key, value, ttl_seconds)

            return value

        except Exception as e:
            print(f"回调执行失败: {e}")
            raise

    async def invalidate_pattern(self, pattern: str) -> int:
        """根据模式删除缓存"""

        count = 0

        # 查找匹配的键
        matching_keys = []
        for key in list(self.cache_entries.keys()):
            if pattern in key:
                matching_keys.append(key)

        # 删除匹配的缓存
        for key in matching_keys:
            if await self.delete(key):
                count += 1

        # Redis模式删除
        if self.redis_enabled:
            try:
                # 使用SCAN避免阻塞
                cursor = 0
                while True:
                    cursor, keys = self.redis_client.scan(cursor=cursor, match=f"*{pattern}*")

                    if keys:
                        self.redis_client.delete(*keys)
                        count += len(keys)

                    if cursor == 0:
                        break

            except Exception as e:
                print(f"Redis模式删除失败: {e}")

        return count

    async def clear(self):
        """清空所有缓存"""

        # 清空L1缓存
        self.l1_cache.clear()
        self.cache_entries.clear()

        # 清空L2缓存
        if self.redis_enabled:
            try:
                self.redis_client.flushdb()
            except Exception as e:
                print(f"Redis清空失败: {e}")

        print("🧹 缓存已清空")

    async def _get_from_redis(self, key: str) -> Optional[Any]:
        """从Redis获取值"""

        if not self.redis_enabled or not self.redis_client:
            return None

        try:
            value = self.redis_client.get(key)
            if value is not None:
                # 解压缩
                return self._decompress(value)
        except Exception as e:
            print(f"Redis获取失败: {e}")

        return None

    async def _set_to_redis(self, key: str, value: Any, ttl_seconds: int):
        """设置值到Redis"""

        if not self.redis_enabled or not self.redis_client:
            return

        try:
            # 压缩
            value_to_store = (
                self._compress(value) if isinstance(value, (bytes, str, dict, list)) else value
            )

            if ttl_seconds > 0:
                self.redis_client.setex(key, ttl_seconds, value_to_store)
            else:
                self.redis_client.set(key, value_to_store)

        except Exception as e:
            print(f"Redis设置失败: {e}")

    async def _delete_from_redis(self, key: str) -> bool:
        """从Redis删除值"""

        if not self.redis_enabled or not self.redis_client:
            return False

        try:
            return self.redis_client.delete(key) > 0
        except Exception as e:
            print(f"Redis删除失败: {e}")
            return False

    def _compress(self, data: Any) -> bytes:
        """压缩数据"""

        try:
            if isinstance(data, dict) or isinstance(data, list):
                data_str = json.dumps(data, ensure_ascii=False)
                data_bytes = data_str.encode("utf-8")
            elif isinstance(data, str):
                data_bytes = data.encode("utf-8")
            elif isinstance(data, bytes):
                data_bytes = data
            else:
                # 使用pickle序列化
                data_bytes = pickle.dumps(data)

            # 使用gzip压缩
            compressed = gzip.compress(data_bytes)

            # 检查是否真的压缩了
            if len(compressed) < len(data_bytes):
                return compressed
            else:
                return data_bytes

        except Exception as e:
            print(f"压缩失败: {e}")
            if isinstance(data, bytes):
                return data
            else:
                return pickle.dumps(data)

    def _decompress(self, data: bytes) -> Any:
        """解压缩数据"""

        try:
            # 尝试gzip解压
            try:
                decompressed = gzip.decompress(data)
                data = decompressed
            except (gzip.BadGzipFile, OSError):
                pass  # 不是gzip格式

            # 尝试JSON解析
            try:
                decoded = data.decode("utf-8")
                return json.loads(decoded)
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass

            # 尝试pickle加载
            try:
                return pickle.loads(data)
            except pickle.UnpicklingError:
                pass

            # 返回原始字节
            return data

        except Exception as e:
            print(f"解压缩失败: {e}")
            return data

    async def _cleanup_expired_entries(self):
        """清理过期条目"""

        print("🧹 启动缓存清理任务...")

        while self.is_running:
            try:
                expired_keys = []
                current_time = datetime.now()

                # 查找过期条目
                for key, entry in list(self.cache_entries.items()):
                    if entry.is_expired():
                        expired_keys.append(key)

                # 删除过期条目
                for key in expired_keys:
                    await self.delete(key)

                if expired_keys:
                    print(f"🧹 清理了 {len(expired_keys)} 个过期缓存条目")

                # 清理L1缓存中的过期条目
                # LRU缓存会自动处理

                # 等待下一次清理
                await asyncio.sleep(self.config["cleanup_interval_seconds"])

            except Exception as e:
                print(f"缓存清理任务出错: {e}")
                await asyncio.sleep(30)

    async def _collect_stats(self):
        """收集统计信息"""

        print("📊 启动缓存统计收集任务...")

        while self.is_running:
            try:
                stats = await self.get_stats()
                self.stats_history.append(stats)

                # 保持历史记录长度
                if len(self.stats_history) > 100:
                    self.stats_history = self.stats_history[-100:]

                # 打印简要统计
                if len(self.stats_history) % 5 == 0:  # 每5次打印一次
                    print(
                        f"📊 缓存统计: {stats.total_entries} 条目, "
                        f"命中率 {stats.hit_rate:.2%}, "
                        f"内存使用 {stats.memory_usage_percent:.1f}%"
                    )

                # 等待下一次统计
                await asyncio.sleep(self.config["stats_interval_seconds"])

            except Exception as e:
                print(f"统计收集任务出错: {e}")
                await asyncio.sleep(60)

    async def get_stats(self) -> CacheStats:
        """获取缓存统计"""

        total_entries = len(self.cache_entries)

        # 计算总大小
        total_size = 0
        for entry in self.cache_entries.values():
            try:
                if isinstance(entry.value, bytes):
                    total_size += len(entry.value)
                else:
                    total_size += len(pickle.dumps(entry.value))
            except:
                pass

        # 计算命中率
        total_accesses = self.total_hits + self.total_misses
        hit_rate = self.total_hits / total_accesses if total_accesses > 0 else 0

        # 计算内存使用率
        max_memory_bytes = self.config["max_memory_mb"] * 1024 * 1024
        memory_usage_percent = (total_size / max_memory_bytes * 100) if max_memory_bytes > 0 else 0

        # 平均条目大小
        avg_entry_size = total_size / total_entries if total_entries > 0 else 0

        # 热门键
        top_keys = []
        for key, entry in sorted(self.cache_entries.items(), key=lambda x: x[1].hits, reverse=True)[
            :10
        ]:
            top_keys.append(
                {
                    "key": key,
                    "hits": entry.hits,
                    "age_seconds": (datetime.now() - entry.timestamp).total_seconds(),
                    "remaining_ttl": entry.remaining_ttl(),
                }
            )

        stats = CacheStats(
            timestamp=datetime.now(),
            total_entries=total_entries,
            total_size_bytes=total_size,
            hits=self.total_hits,
            misses=self.total_misses,
            hit_rate=hit_rate,
            evictions=self.l1_cache.evictions,
            memory_usage_percent=memory_usage_percent,
            avg_entry_size_bytes=avg_entry_size,
            top_keys=top_keys,
        )

        return stats

    def get_stats_history(self, limit: int = 50) -> List[CacheStats]:
        """获取统计历史"""

        return self.stats_history[-limit:]

    def generate_key(self, prefix: str, *args, **kwargs) -> str:
        """生成缓存键"""

        # 将参数转换为字符串
        args_str = "_".join(str(arg) for arg in args if arg is not None)
        kwargs_str = "_".join(f"{k}_{v}" for k, v in sorted(kwargs.items()) if v is not None)

        # 合并
        key_parts = [prefix]
        if args_str:
            key_parts.append(args_str)
        if kwargs_str:
            key_parts.append(kwargs_str)

        key = "_".join(key_parts)

        # 如果太长，使用哈希
        if len(key) > 200:
            key_hash = hashlib.md5(key.encode()).hexdigest()
            key = f"{prefix}_{key_hash}"

        return key

    def cache_decorator(self, ttl_seconds: int = None, key_prefix: str = None):
        """缓存装饰器"""

        def decorator(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                # 生成缓存键
                prefix = key_prefix or func.__name__
                cache_key = self.generate_key(prefix, *args, **kwargs)

                # 尝试获取缓存
                cached_value = await self.get(cache_key)
                if cached_value is not None:
                    return cached_value

                # 执行函数
                result = await func(*args, **kwargs)

                # 设置缓存
                await self.set(cache_key, result, ttl_seconds)

                return result

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                # 生成缓存键
                prefix = key_prefix or func.__name__
                cache_key = self.generate_key(prefix, *args, **kwargs)

                # 在线程池中执行
                loop = asyncio.get_event_loop()

                async def async_get_and_execute():
                    # 尝试获取缓存
                    cached_value = await self.get(cache_key)
                    if cached_value is not None:
                        return cached_value

                    # 执行函数
                    result = await loop.run_in_executor(
                        self.thread_pool, functools.partial(func, *args, **kwargs)
                    )

                    # 设置缓存
                    await self.set(cache_key, result, ttl_seconds)

                    return result

                # 在当前事件循环中执行
                if loop.is_running():
                    # 如果事件循环正在运行，创建任务
                    task = asyncio.create_task(async_get_and_execute())
                    return task
                else:
                    # 否则直接运行
                    return loop.run_until_complete(async_get_and_execute())

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator


# 单例实例
_cache_manager = None


def get_cache_manager(config_manager=None) -> SmartCacheManager:
    """获取缓存管理器单例"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = SmartCacheManager(config_manager)
    return _cache_manager


async def test_cache_manager():
    """测试缓存管理器"""

    cache_manager = get_cache_manager()
    await cache_manager.start()

    try:
        # 测试基本功能
        await cache_manager.set("test_key", "test_value", ttl_seconds=10)
        value = await cache_manager.get("test_key")
        print(f"获取缓存值: {value}")

        # 测试装饰器
        @cache_manager.cache_decorator(ttl_seconds=30)
        async def expensive_operation(x):
            print(f"执行昂贵操作: {x}")
            await asyncio.sleep(1)
            return x * 2

        # 第一次调用
        result1 = await expensive_operation(5)
        print(f"第一次结果: {result1}")

        # 第二次调用（应该从缓存获取）
        result2 = await expensive_operation(5)
        print(f"第二次结果: {result2}")

        # 测试get_or_set
        async def fetch_data():
            print("获取数据...")
            await asyncio.sleep(0.5)
            return {"data": "从API获取"}

        data = await cache_manager.get_or_set("api_data", fetch_data, ttl_seconds=60)
        print(f"获取或设置数据: {data}")

        # 再次获取（应该从缓存）
        data2 = await cache_manager.get_or_set("api_data", fetch_data, ttl_seconds=60)
        print(f"再次获取数据: {data2}")

        # 获取统计信息
        stats = await cache_manager.get_stats()
        print(f"缓存统计: {stats.total_entries} 条目, 命中率 {stats.hit_rate:.2%}")

        # 保持运行
        await asyncio.sleep(15)

    finally:
        await cache_manager.stop()


if __name__ == "__main__":
    asyncio.run(test_cache_manager())
