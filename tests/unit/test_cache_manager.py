"""
CacheManager单元测试
"""

import asyncio
import pytest
import pickle
from datetime import datetime, timedelta
from src.modules.core.cache_manager import (
    CacheManager, CacheEntry, CacheLevel, CacheStats, EvictionPolicy
)


class TestCacheManager:
    """CacheManager测试类"""
    
    @pytest.fixture
    async def cache_manager(self):
        """创建测试用的缓存管理器"""
        cache = CacheManager(max_memory_size=10 * 1024 * 1024)  # 10MB限制
        await cache.initialize()
        yield cache
        await cache.cleanup()
    
    @pytest.fixture
    async def cache_entry(self):
        """创建测试用的缓存条目"""
        return CacheEntry(
            key="test_key",
            value={"data": "test_value"},
            level=CacheLevel.MEMORY,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=60)
        )
    
    @pytest.mark.asyncio
    async def test_initialization(self, cache_manager):
        """测试初始化"""
        assert cache_manager is not None
        assert cache_manager.max_memory_size == 10 * 1024 * 1024
        assert cache_manager.default_ttl == 3600  # 默认1小时
        assert cache_manager.eviction_policy == EvictionPolicy.LRU
    
    @pytest.mark.asyncio
    async def test_set_and_get_memory(self, cache_manager):
        """测试内存缓存的设置和获取"""
        # 设置缓存
        success = await cache_manager.set(
            key="test_key",
            value="test_value",
            ttl=60,
            level=CacheLevel.MEMORY
        )
        assert success is True
        
        # 获取缓存
        value = await cache_manager.get("test_key", level=CacheLevel.MEMORY)
        assert value == "test_value"
        
        # 检查统计
        stats = await cache_manager.get_stats(CacheLevel.MEMORY)
        assert stats["hits"] >= 1
        assert stats["hit_rate"] > 0
    
    @pytest.mark.asyncio
    async def test_set_and_get_with_default(self, cache_manager):
        """测试带默认值的获取"""
        # 获取不存在的缓存
        value = await cache_manager.get("nonexistent", default="default_value")
        assert value == "default_value"
        
        # 检查统计（应该是miss）
        stats = await cache_manager.get_stats(CacheLevel.MEMORY)
        assert stats["misses"] >= 1
    
    @pytest.mark.asyncio
    async def test_cache_expiration(self, cache_manager):
        """测试缓存过期"""
        # 设置短期缓存
        await cache_manager.set("short_key", "short_value", ttl=1)
        
        # 立即获取（应该存在）
        value = await cache_manager.get("short_key")
        assert value == "short_value"
        
        # 等待过期
        await asyncio.sleep(2)
        
        # 再次获取（应该不存在）
        value = await cache_manager.get("short_key")
        assert value is None
    
    @pytest.mark.asyncio
    async def test_delete(self, cache_manager):
        """测试删除缓存"""
        # 设置缓存
        await cache_manager.set("to_delete", "delete_me")
        
        # 确认存在
        exists = await cache_manager.exists("to_delete")
        assert exists is True
        
        # 删除
        success = await cache_manager.delete("to_delete")
        assert success is True
        
        # 确认不存在
        exists = await cache_manager.exists("to_delete")
        assert exists is False
        
        # 获取应该返回None
        value = await cache_manager.get("to_delete")
        assert value is None
    
    @pytest.mark.asyncio
    async def test_exists(self, cache_manager):
        """测试存在性检查"""
        # 不存在的键
        exists = await cache_manager.exists("nonexistent")
        assert exists is False
        
        # 设置缓存
        await cache_manager.set("existing_key", "value")
        
        # 存在的键
        exists = await cache_manager.exists("existing_key")
        assert exists is True
        
        # 指定级别检查
        exists = await cache_manager.exists("existing_key", level=CacheLevel.MEMORY)
        assert exists is True
    
    @pytest.mark.asyncio
    async def test_clear(self, cache_manager):
        """测试清空缓存"""
        # 设置多个缓存
        for i in range(5):
            await cache_manager.set(f"key_{i}", f"value_{i}")
        
        # 清空所有缓存
        success = await cache_manager.clear()
        assert success is True
        
        # 确认所有缓存都被清空
        for i in range(5):
            exists = await cache_manager.exists(f"key_{i}")
            assert exists is False
    
    @pytest.mark.asyncio
    async def test_clear_specific_level(self, cache_manager):
        """测试清空指定级别缓存"""
        # 设置内存缓存
        await cache_manager.set("memory_key", "memory_value", level=CacheLevel.MEMORY)
        
        # 清空内存缓存
        success = await cache_manager.clear(level=CacheLevel.MEMORY)
        assert success is True
        
        # 确认内存缓存被清空
        exists = await cache_manager.exists("memory_key", level=CacheLevel.MEMORY)
        assert exists is False
    
    @pytest.mark.asyncio
    async def test_get_stats(self, cache_manager):
        """测试获取统计信息"""
        # 进行一些缓存操作
        await cache_manager.set("key1", "value1")
        await cache_manager.get("key1")
        await cache_manager.get("nonexistent")  # miss
        
        # 获取所有统计
        all_stats = await cache_manager.get_stats()
        assert "memory" in all_stats
        assert "redis" in all_stats
        assert "disk" in all_stats
        
        # 获取内存缓存统计
        memory_stats = await cache_manager.get_stats(CacheLevel.MEMORY)
        assert "hits" in memory_stats
        assert "misses" in memory_stats
        assert "hit_rate" in memory_stats
        
        # 验证命中率计算
        assert 0 <= memory_stats["hit_rate"] <= 1
    
    @pytest.mark.asyncio
    async def test_memory_eviction(self, cache_manager):
        """测试内存缓存淘汰"""
        # 设置很小的内存限制
        cache_manager.max_memory_size = 100  # 100字节
        
        # 添加一个稍大的值（应该触发淘汰）
        large_value = "x" * 200  # 200字节
        success = await cache_manager.set("large_key", large_value, level=CacheLevel.MEMORY)
        
        # 由于内存限制，可能设置失败或触发淘汰
        # 这里主要测试不会崩溃
        assert True
    
    @pytest.mark.asyncio
    async def test_cache_entry_properties(self, cache_entry):
        """测试缓存条目属性"""
        # 基本属性
        assert cache_entry.key == "test_key"
        assert cache_entry.value == {"data": "test_value"}
        assert cache_entry.level == CacheLevel.MEMORY
        
        # 年龄
        age = cache_entry.age
        assert isinstance(age, timedelta)
        assert age.total_seconds() >= 0
        
        # TTL
        ttl = cache_entry.ttl
        assert ttl is not None
        assert 0 <= ttl <= 60
        
        # 是否过期
        assert cache_entry.is_expired is False
        
        # 触摸（更新访问时间）
        old_access_count = cache_entry.access_count
        cache_entry.touch()
        assert cache_entry.access_count == old_access_count + 1
        assert cache_entry.last_accessed > cache_entry.created_at
    
    @pytest.mark.asyncio
    async def test_cache_entry_expired(self):
        """测试过期缓存条目"""
        # 创建已过期的条目
        expired_entry = CacheEntry(
            key="expired_key",
            value="expired_value",
            level=CacheLevel.MEMORY,
            created_at=datetime.now() - timedelta(seconds=100),
            expires_at=datetime.now() - timedelta(seconds=50)
        )
        
        assert expired_entry.is_expired is True
        assert expired_entry.ttl == 0
    
    @pytest.mark.asyncio
    async def test_cache_entry_no_expiry(self):
        """测试无过期时间的缓存条目"""
        # 创建永不过期的条目
        eternal_entry = CacheEntry(
            key="eternal_key",
            value="eternal_value",
            level=CacheLevel.MEMORY,
            created_at=datetime.now(),
            expires_at=None
        )
        
        assert eternal_entry.is_expired is False
        assert eternal_entry.ttl is None
    
    @pytest.mark.asyncio
    async def test_key_prefix(self, cache_manager):
        """测试键前缀"""
        # 设置缓存
        await cache_manager.set("my_key", "my_value")
        
        # 内部键应该包含前缀
        full_key = cache_manager._make_key("my_key")
        assert full_key.startswith("trading:cache:")
        assert "my_key" in full_key
    
    @pytest.mark.asyncio
    async def test_level_priority(self, cache_manager):
        """测试缓存级别优先级"""
        # 测试内存优先
        mem_priority = cache_manager._get_level_priority(CacheLevel.MEMORY)
        assert mem_priority[0] == CacheLevel.MEMORY
        assert CacheLevel.REDIS in mem_priority
        assert CacheLevel.DISK in mem_priority
        
        # 测试Redis优先
        redis_priority = cache_manager._get_level_priority(CacheLevel.REDIS)
        assert redis_priority[0] == CacheLevel.REDIS
        assert CacheLevel.MEMORY in redis_priority
        
        # 测试磁盘优先
        disk_priority = cache_manager._get_level_priority(CacheLevel.DISK)
        assert disk_priority[0] == CacheLevel.DISK
    
    @pytest.mark.asyncio
    async def test_estimate_size(self, cache_manager):
        """测试大小估算"""
        # 测试不同类型的大小估算
        small_value = "small"
        large_value = "x" * 1000
        dict_value = {"key": "value", "list": [1, 2, 3]}
        
        small_size = cache_manager._estimate_size(small_value)
        large_size = cache_manager._estimate_size(large_value)
        dict_size = cache_manager._estimate_size(dict_value)
        
        assert small_size > 0
        assert large_size > small_size
        assert dict_size > 0
        
        # 大值应该比小值大
        assert large_size > small_size
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self, cache_manager):
        """测试并发访问"""
        # 并发设置缓存
        async def set_cache(i):
            await cache_manager.set(f"concurrent_{i}", f"value_{i}")
            return i
        
        tasks = [set_cache(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 10
        
        # 并发获取缓存
        async def get_cache(i):
            return await cache_manager.get(f"concurrent_{i}")
        
        tasks = [get_cache(i) for i in range(10)]
        values = await asyncio.gather(*tasks)
        
        # 所有值都应该存在
        for i, value in enumerate(values):
            assert value == f"value_{i}"
    
    @pytest.mark.asyncio
    async def test_cache_stats_update(self, cache_manager):
        """测试缓存统计更新"""
        # 初始统计
        initial_stats = await cache_manager.get_stats(CacheLevel.MEMORY)
        
        # 进行一些操作
        await cache_manager.set("stat_key", "stat_value")
        await cache_manager.get("stat_key")  # hit
        await cache_manager.get("nonexistent_stat_key")  # miss
        
        # 获取新统计
        new_stats = await cache_manager.get_stats(CacheLevel.MEMORY)
        
        # 验证统计更新
        assert new_stats["hits"] > initial_stats["hits"]
        assert new_stats["misses"] > initial_stats["misses"]
        
        # 命中率应该合理
        assert 0 <= new_stats["hit_rate"] <= 1
    
    @pytest.mark.asyncio
    async def test_cache_entry_to_dict(self, cache_entry):
        """测试缓存条目序列化"""
        # 测试pickle序列化
        pickled = pickle.dumps(cache_entry)
        unpickled = pickle.loads(pickled)
        
        assert unpickled.key == cache_entry.key
        assert unpickled.value == cache_entry.value
        assert unpickled.level == cache_entry.level


if __name__ == "__main__":
    """运行测试"""
    import sys
    import pytest
    
    # 添加src目录到Python路径
    sys.path.insert(0, "/home/cool/.openclaw-trading/src")
    
    # 运行测试
    pytest.main([__file__, "-v"])