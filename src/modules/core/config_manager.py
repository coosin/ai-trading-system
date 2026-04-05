"""
配置管理器模块

负责统一配置加载、管理、验证和热重载。
支持多格式配置（JSON/YAML/Env）、配置验证和默认值设置。
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# 容错导入
try:
    import yaml
except ImportError:
    yaml = None
    logging.warning("yaml模块未安装，跳过YAML配置文件")

try:
    from pydantic import BaseModel, ValidationError
except ImportError:
    BaseModel = None
    ValidationError = None
    logging.warning("pydantic模块未安装，使用简化的配置验证")

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """配置验证错误"""

    pass


class ConfigNotFoundError(Exception):
    """配置未找到错误"""

    pass


@dataclass
class ConfigChange:
    """配置变更记录"""

    section: str
    key: str
    old_value: Any
    new_value: Any
    timestamp: float


class ConfigSchema:
    """配置模式基类"""

    pass

if BaseModel:
    class ConfigSchema(BaseModel):
        """配置模式基类"""

        pass


class ConfigManager:
    """
    配置管理器

    特性：
    1. 统一配置加载和管理
    2. 多格式配置支持 (JSON/YAML/Env)
    3. 配置验证和默认值设置
    4. 配置热重载支持
    5. 配置变更通知机制
    """

    def __init__(self, config_dir: str = "config", watch_interval: int = 30):
        """
        初始化配置管理器

        Args:
            config_dir: 配置文件目录
            watch_interval: 配置监控间隔（秒）
        """
        self.config_dir = Path(config_dir)
        self.watch_interval = watch_interval
        self._config: Dict[str, Dict[str, Any]] = {}
        self._schemas: Dict[str, ConfigSchema] = {}
        self._watchers: Dict[str, List[Callable]] = {}
        self._file_timestamps: Dict[str, float] = {}
        self._change_history: List[ConfigChange] = []
        self._lock = asyncio.Lock()
        self._watch_task: Optional[asyncio.Task] = None
        self._initialized = False

        # 确保配置目录存在
        self.config_dir.mkdir(exist_ok=True)

    async def initialize(self) -> None:
        """
        初始化配置管理器

        加载所有配置文件并启动监控任务
        """
        if self._initialized:
            return

        logger.info("初始化配置管理器...")

        # 加载配置文件
        await self._load_all_configs()

        # 启动配置监控
        if self.watch_interval > 0:
            self._watch_task = asyncio.create_task(self._watch_config_files())

        self._initialized = True
        logger.info("配置管理器初始化完成")

    async def cleanup(self) -> None:
        """
        清理配置管理器

        停止监控任务
        """
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

        self._initialized = False
        logger.info("配置管理器已清理")

    async def get_config(self, section: str, key: Any = None, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            section: 配置段名
            key: 配置键名（可选）
            default: 默认值（如果配置不存在）

        Returns:
            配置值
        """
        async with self._lock:
            # 如果只传递了两个参数，第二个参数作为default
            if key is not None and not isinstance(key, str):
                default = key
                key = None
            
            if key:
                section_config = self._config.get(section, {})
                value = section_config.get(key)

                if value is None and default is not None:
                    return default

                return value
            else:
                # 如果没有指定key，返回整个section
                return self._config.get(section, default)

    async def set_config(self, section: str, key: str, value: Any, validate: bool = True) -> bool:
        """
        设置配置值

        Args:
            section: 配置段名
            key: 配置键名
            value: 配置值
            validate: 是否验证配置

        Returns:
            是否设置成功
        """
        async with self._lock:
            # 获取旧值
            old_value = None
            if section in self._config and key in self._config[section]:
                old_value = self._config[section][key]

            # 验证配置（如果启用了验证）
            if validate:
                if BaseModel and section in self._schemas:
                    try:
                        schema = self._schemas[section]
                        # 创建临时配置进行验证
                        temp_config = {key: value}
                        schema(**temp_config)
                    except ValidationError as e:
                        logger.error(f"配置验证失败: {e}")
                        return False
                else:
                    # 简化验证（不依赖pydantic）
                    if not self._validate_value(value):
                        logger.error(f"配置验证失败: 值类型无效")
                        return False

            # 更新配置
            if section not in self._config:
                self._config[section] = {}

            self._config[section][key] = value

            # 记录变更
            change = ConfigChange(
                section=section,
                key=key,
                old_value=old_value,
                new_value=value,
                timestamp=asyncio.get_event_loop().time(),
            )
            self._change_history.append(change)

            # 保存到文件
            await self._save_section_to_file(section)

            # 通知观察者
            await self._notify_watchers(section, key, old_value, value)

            logger.info(f"配置已更新: {section}.{key} = {value}")
            return True

    def _validate_value(self, value: Any) -> bool:
        """简化验证"""
        # 允许所有基本类型
        return True

    async def watch_config(self, section: str, key: str, callback: Callable) -> None:
        """
        监听配置变更

        Args:
            section: 配置段名
            key: 配置键名
            callback: 回调函数，接收(section, key, old_value, new_value)
        """
        watch_key = f"{section}.{key}"
        if watch_key not in self._watchers:
            self._watchers[watch_key] = []

        self._watchers[watch_key].append(callback)
        logger.debug(f"已注册配置监听器: {watch_key}")

    async def unwatch_config(self, section: str, key: str, callback: Callable) -> None:
        """
        取消监听配置变更

        Args:
            section: 配置段名
            key: 配置键名
            callback: 要移除的回调函数
        """
        watch_key = f"{section}.{key}"
        if watch_key in self._watchers and callback in self._watchers[watch_key]:
            self._watchers[watch_key].remove(callback)
            logger.debug(f"已移除配置监听器: {watch_key}")

    async def reload(self) -> None:
        """
        重新加载所有配置文件
        """
        async with self._lock:
            logger.info("重新加载配置文件...")
            await self._load_all_configs()
            logger.info("配置文件重载完成")

    def register_schema(self, section: str, schema: ConfigSchema) -> None:
        """
        注册配置模式

        Args:
            section: 配置段名
            schema: 配置模式类
        """
        self._schemas[section] = schema
        logger.debug(f"已注册配置模式: {section}")

    async def get_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有配置

        Returns:
            所有配置的字典
        """
        async with self._lock:
            return self._config.copy()

    async def get_change_history(self, limit: int = 100) -> List[ConfigChange]:
        """
        获取配置变更历史

        Args:
            limit: 返回的最大记录数

        Returns:
            配置变更历史列表
        """
        async with self._lock:
            return self._change_history[-limit:]

    @asynccontextmanager
    async def transaction(self):
        """
        配置事务上下文管理器

        用法：
        async with config_manager.transaction() as transaction:
            await transaction.set_config('section', 'key1', 'value1')
            await transaction.set_config('section', 'key2', 'value2')
            # 所有变更在退出上下文时一起应用
        """
        transaction = ConfigTransaction(self)
        try:
            yield transaction
            await transaction.commit()
        except Exception as e:
            await transaction.rollback()
            raise e

    # 私有方法

    async def _load_all_configs(self) -> None:
        """加载所有配置文件"""
        config_files = list(self.config_dir.glob("*.json"))

        # 如果有yaml支持，添加yaml文件
        if yaml:
            config_files.extend(list(self.config_dir.glob("*.yaml")))
            config_files.extend(list(self.config_dir.glob("*.yml")))

        for config_file in config_files:
            await self._load_config_file(config_file)

        # 加载环境变量
        await self._load_environment_configs()

    async def _load_config_file(self, config_file: Path) -> None:
        """加载配置文件"""
        try:
            # 记录文件时间戳
            self._file_timestamps[str(config_file)] = config_file.stat().st_mtime

            # 根据文件扩展名解析
            if config_file.suffix == ".json":
                with open(config_file, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            elif config_file.suffix in [".yaml", ".yml"]:
                if yaml:
                    with open(config_file, "r", encoding="utf-8") as f:
                        config_data = yaml.safe_load(f)
                else:
                    logger.warning(f"无法加载YAML文件，缺少yaml模块: {config_file}")
                    return
            else:
                logger.warning(f"不支持的配置文件格式: {config_file}")
                return

            # 合并配置
            for section, values in config_data.items():
                if not isinstance(values, dict):
                    self._config[section] = values
                    continue

                if section not in self._config:
                    self._config[section] = {}

                self._config[section].update(values)

            logger.info(f"已加载配置文件: {config_file}")

        except Exception as e:
            logger.error(f"加载配置文件失败 {config_file}: {e}")

    async def _load_environment_configs(self) -> None:
        """加载环境变量配置"""
        # 环境变量前缀
        env_prefix = "TRADING_"

        for key, value in os.environ.items():
            if key.startswith(env_prefix):
                # 解析配置键：TRADING_SECTION_KEY -> section.key
                parts = key[len(env_prefix) :].split("_", 1)
                if len(parts) == 2:
                    section = parts[0].lower()
                    config_key = parts[1].lower()

                    # 转换值类型
                    try:
                        # 尝试解析为JSON
                        parsed_value = json.loads(value)
                    except (json.JSONDecodeError, ValueError):
                        # 如果失败，保持字符串
                        parsed_value = value

                    if section not in self._config:
                        self._config[section] = {}

                    self._config[section][config_key] = parsed_value

        logger.debug("已加载环境变量配置")

    async def _save_section_to_file(self, section: str) -> None:
        """保存配置段到文件"""
        config_file = self.config_dir / f"{section}.json"

        try:
            section_config = self._config.get(section, {})

            # 如果配置为空，删除文件
            if not section_config and config_file.exists():
                config_file.unlink()
                return

            # 保存到文件
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(section_config, f, indent=2, ensure_ascii=False)

            # 更新文件时间戳
            self._file_timestamps[str(config_file)] = config_file.stat().st_mtime

            logger.debug(f"已保存配置到文件: {config_file}")

        except Exception as e:
            logger.error(f"保存配置文件失败 {config_file}: {e}")

    async def _watch_config_files(self) -> None:
        """监控配置文件变化"""
        logger.info(f"开始监控配置文件，间隔: {self.watch_interval}秒")

        while True:
            try:
                await asyncio.sleep(self.watch_interval)

                changed_files = []
                for file_path_str, last_mtime in self._file_timestamps.items():
                    file_path = Path(file_path_str)
                    if file_path.exists():
                        current_mtime = file_path.stat().st_mtime
                        if current_mtime > last_mtime:
                            changed_files.append(file_path)
                            self._file_timestamps[file_path_str] = current_mtime

                if changed_files:
                    logger.info(f"检测到配置文件变化: {changed_files}")
                    await self.reload()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"配置文件监控出错: {e}")

    async def _notify_watchers(
        self, section: str, key: str, old_value: Any, new_value: Any
    ) -> None:
        """通知配置观察者"""
        watch_key = f"{section}.{key}"

        if watch_key in self._watchers:
            for callback in self._watchers[watch_key]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(section, key, old_value, new_value)
                    else:
                        callback(section, key, old_value, new_value)
                except Exception as e:
                    logger.error(f"配置回调函数执行失败: {e}")


class ConfigTransaction:
    """配置事务"""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.changes: List[tuple] = []  # (section, key, value)
        self.committed = False

    async def set_config(self, section: str, key: str, value: Any) -> None:
        """在事务中设置配置"""
        self.changes.append((section, key, value))

    async def commit(self) -> None:
        """提交事务"""
        if self.committed:
            return

        for section, key, value in self.changes:
            await self.config_manager.set_config(section, key, value, validate=False)

        self.committed = True

    async def rollback(self) -> None:
        """回滚事务"""
        self.changes.clear()


# 默认配置管理器实例
_default_config_manager: Optional[ConfigManager] = None


async def get_config_manager() -> ConfigManager:
    """获取默认配置管理器实例"""
    global _default_config_manager

    if _default_config_manager is None:
        _default_config_manager = ConfigManager()
        await _default_config_manager.initialize()

    return _default_config_manager


async def cleanup_config_manager() -> None:
    """清理默认配置管理器"""
    global _default_config_manager

    if _default_config_manager:
        await _default_config_manager.cleanup()
        _default_config_manager = None


# 示例使用
if __name__ == "__main__":
    import asyncio

    async def example():
        # 创建配置管理器
        config = ConfigManager()
        await config.initialize()

        # 设置配置
        await config.set_config("database", "host", "localhost")
        await config.set_config("database", "port", 5432)
        await config.set_config("database", "username", "trader")

        # 获取配置
        host = await config.get_config("database", "host")
        port = await config.get_config("database", "port")
        logger.info(f"数据库配置: {host}:{port}")

        # 监听配置变更
        async def on_database_change(section, key, old_value, new_value):
            logger.info(f"数据库配置变更: {section}.{key} = {old_value} -> {new_value}")

        await config.watch_config("database", "host", on_database_change)

        # 修改配置（会触发监听器）
        await config.set_config("database", "host", "127.0.0.1")

        # 使用事务
        async with config.transaction() as transaction:
            await transaction.set_config("redis", "host", "localhost")
            await transaction.set_config("redis", "port", 6379)

        # 获取所有配置
        all_configs = await config.get_all_configs()
        logger.info("所有配置:", json.dumps(all_configs, indent=2))

        # 清理
        await config.cleanup()

    asyncio.run(example())
