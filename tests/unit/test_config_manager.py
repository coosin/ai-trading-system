"""
ConfigManager单元测试
"""

import pytest
import asyncio
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from src.modules.core.config_manager import (
    ConfigManager, 
    ConfigTransaction, 
    ConfigValidationError,
    ConfigNotFoundError
)


class TestConfigManager:
    """ConfigManager测试类"""
    
    @pytest.fixture
    async def config_manager(self):
        """创建配置管理器测试实例"""
        # 使用临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir(exist_ok=True)
            
            manager = ConfigManager(config_dir=str(config_dir), watch_interval=0)
            await manager.initialize()
            yield manager
            await manager.cleanup()
    
    @pytest.fixture
    def sample_json_config(self, tmp_path):
        """创建示例JSON配置文件"""
        config_file = tmp_path / "config" / "database.json"
        config_file.parent.mkdir(exist_ok=True)
        
        config_data = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "username": "trader",
                "password": "secret123"
            }
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f)
        
        return str(config_file)
    
    @pytest.fixture
    def sample_yaml_config(self, tmp_path):
        """创建示例YAML配置文件"""
        config_file = tmp_path / "config" / "redis.yaml"
        config_file.parent.mkdir(exist_ok=True)
        
        config_data = """
        redis:
          host: "redis.local"
          port: 6379
          db: 0
          password: "redispass"
        """
        
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(config_data)
        
        return str(config_file)
    
    @pytest.mark.asyncio
    async def test_initialization(self, config_manager):
        """测试初始化"""
        assert config_manager._initialized is True
        assert isinstance(config_manager._config, dict)
    
    @pytest.mark.asyncio
    async def test_set_and_get_config(self, config_manager):
        """测试设置和获取配置"""
        # 设置配置
        success = await config_manager.set_config("test", "key1", "value1")
        assert success is True
        
        # 获取配置
        value = await config_manager.get_config("test", "key1")
        assert value == "value1"
        
        # 获取不存在的配置（有默认值）
        value = await config_manager.get_config("test", "nonexistent", default="default")
        assert value == "default"
        
        # 获取不存在的配置（无默认值）
        value = await config_manager.get_config("test", "nonexistent")
        assert value is None
    
    @pytest.mark.asyncio
    async def test_get_all_configs(self, config_manager):
        """测试获取所有配置"""
        # 设置多个配置
        await config_manager.set_config("section1", "key1", "value1")
        await config_manager.set_config("section1", "key2", "value2")
        await config_manager.set_config("section2", "key1", "value3")
        
        # 获取所有配置
        all_configs = await config_manager.get_all_configs()
        
        assert "section1" in all_configs
        assert "section2" in all_configs
        assert all_configs["section1"]["key1"] == "value1"
        assert all_configs["section1"]["key2"] == "value2"
        assert all_configs["section2"]["key1"] == "value3"
    
    @pytest.mark.asyncio
    async def test_watch_config_changes(self, config_manager):
        """测试配置变更监听"""
        # 监听器回调
        changes = []
        
        async def callback(section, key, old_value, new_value):
            changes.append((section, key, old_value, new_value))
        
        # 注册监听器
        await config_manager.watch_config("test", "key1", callback)
        
        # 设置配置（应该触发监听器）
        await config_manager.set_config("test", "key1", "new_value")
        
        # 给监听器一点时间执行
        await asyncio.sleep(0.1)
        
        # 验证监听器被调用
        assert len(changes) == 1
        assert changes[0] == ("test", "key1", None, "new_value")
        
        # 再次设置配置
        await config_manager.set_config("test", "key1", "another_value")
        await asyncio.sleep(0.1)
        
        assert len(changes) == 2
        assert changes[1] == ("test", "key1", "new_value", "another_value")
    
    @pytest.mark.asyncio
    async def test_unwatch_config(self, config_manager):
        """测试取消监听配置变更"""
        changes = []
        
        async def callback(section, key, old_value, new_value):
            changes.append((section, key, old_value, new_value))
        
        # 注册监听器
        await config_manager.watch_config("test", "key1", callback)
        
        # 取消监听
        await config_manager.unwatch_config("test", "key1", callback)
        
        # 设置配置（不应该触发监听器）
        await config_manager.set_config("test", "key1", "value1")
        await asyncio.sleep(0.1)
        
        # 验证监听器没有被调用
        assert len(changes) == 0
    
    @pytest.mark.asyncio
    async def test_config_transaction(self, config_manager):
        """测试配置事务"""
        # 使用事务设置多个配置
        async with config_manager.transaction() as transaction:
            await transaction.set_config("db", "host", "localhost")
            await transaction.set_config("db", "port", 5432)
            await transaction.set_config("db", "user", "admin")
        
        # 验证配置已设置
        host = await config_manager.get_config("db", "host")
        port = await config_manager.get_config("db", "port")
        user = await config_manager.get_config("db", "user")
        
        assert host == "localhost"
        assert port == 5432
        assert user == "admin"
    
    @pytest.mark.asyncio
    async def test_config_transaction_rollback(self, config_manager):
        """测试配置事务回滚"""
        # 先设置一个配置
        await config_manager.set_config("test", "existing", "old_value")
        
        try:
            async with config_manager.transaction() as transaction:
                await transaction.set_config("test", "existing", "new_value")
                await transaction.set_config("test", "new_key", "new_value2")
                # 模拟异常导致回滚
                raise ValueError("模拟异常")
        except ValueError:
            pass
        
        # 验证配置没有改变
        existing = await config_manager.get_config("test", "existing")
        new_key = await config_manager.get_config("test", "new_key")
        
        assert existing == "old_value"  # 应该回滚到旧值
        assert new_key is None  # 新配置应该不存在
    
    @pytest.mark.asyncio
    async def test_load_json_config_file(self, sample_json_config, tmp_path):
        """测试加载JSON配置文件"""
        config_dir = Path(sample_json_config).parent
        manager = ConfigManager(config_dir=str(config_dir), watch_interval=0)
        await manager.initialize()
        
        # 验证配置已加载
        host = await manager.get_config("database", "host")
        port = await manager.get_config("database", "port")
        username = await manager.get_config("database", "username")
        
        assert host == "localhost"
        assert port == 5432
        assert username == "trader"
        
        await manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_load_yaml_config_file(self, sample_yaml_config, tmp_path):
        """测试加载YAML配置文件"""
        config_dir = Path(sample_yaml_config).parent
        manager = ConfigManager(config_dir=str(config_dir), watch_interval=0)
        await manager.initialize()
        
        # 验证配置已加载
        host = await manager.get_config("redis", "host")
        port = await manager.get_config("redis", "port")
        
        assert host == "redis.local"
        assert port == 6379
        
        await manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_load_environment_configs(self, config_manager, monkeypatch):
        """测试加载环境变量配置"""
        # 设置环境变量
        monkeypatch.setenv("TRADING_DATABASE_HOST", "env-host")
        monkeypatch.setenv("TRADING_DATABASE_PORT", "5433")
        monkeypatch.setenv("TRADING_REDIS_HOST", "env-redis")
        monkeypatch.setenv("TRADING_REDIS_PORT", "6380")
        
        # 重新加载配置（包括环境变量）
        await config_manager.reload()
        
        # 验证环境变量配置已加载
        db_host = await config_manager.get_config("database", "host")
        db_port = await config_manager.get_config("database", "port")
        redis_host = await config_manager.get_config("redis", "host")
        redis_port = await config_manager.get_config("redis", "port")
        
        assert db_host == "env-host"
        assert db_port == "5433"
        assert redis_host == "env-redis"
        assert redis_port == "6380"
    
    @pytest.mark.asyncio
    async def test_save_config_to_file(self, config_manager, tmp_path):
        """测试保存配置到文件"""
        config_dir = Path(tmp_path) / "config"
        
        # 设置配置
        await config_manager.set_config("test_section", "key1", "value1")
        await config_manager.set_config("test_section", "key2", {"nested": "value"})
        
        # 验证文件已创建
        config_file = config_dir / "test_section.json"
        assert config_file.exists()
        
        # 验证文件内容
        with open(config_file, 'r', encoding='utf-8') as f:
            saved_config = json.load(f)
        
        assert saved_config["key1"] == "value1"
        assert saved_config["key2"] == {"nested": "value"}
    
    @pytest.mark.asyncio
    async def test_config_validation_with_schema(self, config_manager):
        """测试配置模式验证"""
        from pydantic import BaseModel, validator
        
        # 定义配置模式
        class DatabaseConfig(BaseModel):
            host: str
            port: int
            username: str
            password: str
            
            @validator('port')
            def validate_port(cls, v):
                if not 1 <= v <= 65535:
                    raise ValueError('端口必须在1-65535之间')
                return v
        
        # 注册模式
        config_manager.register_schema("database", DatabaseConfig)
        
        # 验证有效的配置
        success = await config_manager.set_config(
            "database", "host", "localhost", validate=True
        )
        assert success is True
        
        # 验证无效的配置（应该失败）
        success = await config_manager.set_config(
            "database", "port", 70000, validate=True
        )
        assert success is False  # 端口无效
    
    @pytest.mark.asyncio
    async def test_get_change_history(self, config_manager):
        """测试获取配置变更历史"""
        # 设置多个配置
        await config_manager.set_config("test", "key1", "value1")
        await config_manager.set_config("test", "key2", "value2")
        await config_manager.set_config("test", "key1", "value3")  # 更新
        
        # 获取变更历史
        history = await config_manager.get_change_history()
        
        assert len(history) >= 3
        assert history[-1].section == "test"
        assert history[-1].key == "key1"
        assert history[-1].old_value == "value1"
        assert history[-1].new_value == "value3"
    
    @pytest.mark.asyncio
    async def test_reload_config(self, config_manager, tmp_path):
        """测试重新加载配置"""
        config_dir = Path(tmp_path) / "config"
        config_file = config_dir / "test.json"
        
        # 初始配置
        initial_config = {"test": {"key1": "initial"}}
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(initial_config, f)
        
        # 重新加载
        await config_manager.reload()
        
        # 验证初始配置
        value = await config_manager.get_config("test", "key1")
        assert value == "initial"
        
        # 修改配置文件
        updated_config = {"test": {"key1": "updated", "key2": "new"}}
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(updated_config, f)
        
        # 再次重新加载
        await config_manager.reload()
        
        # 验证更新后的配置
        value1 = await config_manager.get_config("test", "key1")
        value2 = await config_manager.get_config("test", "key2")
        
        assert value1 == "updated"
        assert value2 == "new"
    
    @pytest.mark.asyncio
    async def test_cleanup_stops_watching(self, tmp_path):
        """测试清理停止文件监控"""
        config_dir = Path(tmp_path) / "config"
        config_dir.mkdir(exist_ok=True)
        
        # 创建带监控的配置管理器
        manager = ConfigManager(config_dir=str(config_dir), watch_interval=1)
        await manager.initialize()
        
        # 验证监控任务在运行
        assert manager._watch_task is not None
        assert not manager._watch_task.done()
        
        # 清理
        await manager.cleanup()
        
        # 验证监控任务已停止
        assert manager._watch_task is None
        assert manager._initialized is False
    
    @pytest.mark.asyncio
    async def test_default_value_types(self, config_manager):
        """测试不同类型默认值"""
        # 测试各种类型的配置值
        test_cases = [
            ("string", "hello"),
            ("int", 42),
            ("float", 3.14),
            ("bool", True),
            ("list", [1, 2, 3]),
            ("dict", {"key": "value"}),
            ("none", None),
        ]
        
        for key, value in test_cases:
            await config_manager.set_config("types", key, value)
            retrieved = await config_manager.get_config("types", key)
            assert retrieved == value
    
    @pytest.mark.asyncio
    async def test_nested_config_access(self, config_manager):
        """测试嵌套配置访问"""
        # 设置嵌套配置
        nested_config = {
            "level1": {
                "level2": {
                    "level3": "deep_value"
                }
            }
        }
        
        await config_manager.set_config("nested", "config", nested_config)
        
        # 获取并验证
        retrieved = await config_manager.get_config("nested", "config")
        assert retrieved["level1"]["level2"]["level3"] == "deep_value"
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self, config_manager):
        """测试并发访问配置管理器"""
        # 并发设置配置
        async def set_config_task(key_suffix):
            await config_manager.set_config("concurrent", f"key_{key_suffix}", f"value_{key_suffix}")
        
        # 创建多个并发任务
        tasks = [set_config_task(i) for i in range(10)]
        await asyncio.gather(*tasks)
        
        # 验证所有配置都已设置
        for i in range(10):
            value = await config_manager.get_config("concurrent", f"key_{i}")
            assert value == f"value_{i}"
    
    @pytest.mark.asyncio
    async def test_error_handling_invalid_file(self, tmp_path):
        """测试无效文件处理的错误处理"""
        config_dir = Path(tmp_path) / "config"
        config_dir.mkdir(exist_ok=True)
        
        # 创建无效的JSON文件
        invalid_file = config_dir / "invalid.json"
        with open(invalid_file, 'w', encoding='utf-8') as f:
            f.write("{invalid json}")
        
        # 应该不会崩溃
        manager = ConfigManager(config_dir=str(config_dir), watch_interval=0)
        await manager.initialize()
        
        # 管理器应该仍然可用
        await manager.set_config("test", "key", "value")
        value = await manager.get_config("test", "key")
        assert value == "value"
        
        await manager.cleanup()


class TestConfigTransaction:
    """ConfigTransaction测试类"""
    
    @pytest.fixture
    async def transaction(self, config_manager):
        """创建配置事务实例"""
        return ConfigTransaction(config_manager)
    
    @pytest.mark.asyncio
    async def test_transaction_commit(self, transaction, config_manager):
        """测试事务提交"""
        # 在事务中添加配置
        await transaction.set_config("test", "key1", "value1")
        await transaction.set_config("test", "key2", "value2")
        
        # 提交前配置不应该存在
        value1 = await config_manager.get_config("test", "key1")
        value2 = await config_manager.get_config("test", "key2")
        assert value1 is None
        assert value2 is None
        
        # 提交事务
        await transaction.commit()
        
        # 提交后配置应该存在
        value1 = await config_manager.get_config("test", "key1")
        value2 = await config_manager.get_config("test", "key2")
        assert value1 == "value1"
        assert value2 == "value2"
    
    @pytest.mark.asyncio
    async def test_transaction_rollback(self, transaction, config_manager):
        """测试事务回滚"""
        # 在事务中添加配置
        await transaction.set_config("test", "key1", "value1")
        await transaction.set_config("test", "key2", "value2")
        
        # 回滚事务
        await transaction.rollback()
        
        # 尝试提交（应该什么都不做）
        await transaction.commit()
        
        # 配置不应该存在
        value1 = await config_manager.get_config("test", "key1")
        value2 = await config_manager.get_config("test", "key2")
        assert value1 is None
        assert value2 is None
    
    @pytest.mark.asyncio
    async def test_double_commit(self, transaction):
        """测试重复提交"""
        await transaction.set_config("test", "key", "value")
        await transaction.commit()
        
        # 第二次提交应该什么都不做
        await transaction.commit()
    
    @pytest.mark.asyncio
    async def test_transaction_with_existing_config(self, transaction, config_manager):
        """测试事务处理现有配置"""
        # 先设置一个配置
        await config_manager.set_config("test", "existing", "old_value")
        
        # 在事务中更新
        await transaction.set_config("test", "existing", "new_value")
        await transaction.commit()
        
        # 验证配置已更新
        value = await config_manager.get_config("test", "existing")
        assert value == "new_value"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])