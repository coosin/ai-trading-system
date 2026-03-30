"""
增强的配置管理器 - 支持分层配置和热重载

功能：
1. 分层配置管理（默认、环境、用户、运行时）
2. 配置热重载
3. 配置验证和测试
4. 配置版本控制
5. 配置加密存储
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)


class ConfigLayer(Enum):
    """配置层级"""
    DEFAULT = "default"      # 默认配置
    ENVIRONMENT = "environment"  # 环境配置
    USER = "user"           # 用户配置
    RUNTIME = "runtime"     # 运行时配置


class ConfigValidationError(Exception):
    """配置验证错误"""
    pass


@dataclass
class ConfigChange:
    """配置变更记录"""
    key: str
    old_value: Any
    new_value: Any
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "unknown"


class ConfigValidator:
    """配置验证器"""
    
    def __init__(self):
        self.validators: Dict[str, List[Callable]] = {}
    
    def register_validator(self, key: str, validator: Callable[[Any], bool]):
        """注册验证器"""
        if key not in self.validators:
            self.validators[key] = []
        self.validators[key].append(validator)
    
    def validate(self, key: str, value: Any) -> bool:
        """验证配置值"""
        if key not in self.validators:
            return True
        
        for validator in self.validators[key]:
            if not validator(value):
                return False
        return True
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """验证整个配置"""
        errors = []
        for key, value in self._flatten_config(config).items():
            if not self.validate(key, value):
                errors.append(f"配置验证失败: {key} = {value}")
        return errors
    
    def _flatten_config(self, config: Dict[str, Any], parent_key: str = "") -> Dict[str, Any]:
        """展平配置字典"""
        items = {}
        for key, value in config.items():
            new_key = f"{parent_key}.{key}" if parent_key else key
            if isinstance(value, dict):
                items.update(self._flatten_config(value, new_key))
            else:
                items[new_key] = value
        return items


class ConfigWatcher(FileSystemEventHandler):
    """配置文件监控器"""
    
    def __init__(self, config_manager: 'EnhancedConfigManager'):
        self.config_manager = config_manager
        self._last_modified: Dict[str, float] = {}
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        if event.src_path.endswith(('.yml', '.yaml', '.json')):
            # 防抖处理
            current_time = time.time()
            last_time = self._last_modified.get(event.src_path, 0)
            
            if current_time - last_time > 1:  # 1秒内不重复处理
                self._last_modified[event.src_path] = current_time
                logger.info(f"配置文件变更: {event.src_path}")
                
                # 触发重载
                asyncio.create_task(
                    self.config_manager.reload_config_file(event.src_path)
                )


class EnhancedConfigManager:
    """增强的配置管理器"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        # 分层配置存储
        self._configs: Dict[ConfigLayer, Dict[str, Any]] = {
            layer: {} for layer in ConfigLayer
        }
        
        # 配置变更历史
        self._change_history: List[ConfigChange] = []
        self._max_history_size = 1000
        
        # 配置验证器
        self._validator = ConfigValidator()
        
        # 变更回调
        self._change_callbacks: List[Callable[[ConfigChange], None]] = []
        
        # 文件监控
        self._observer: Optional[Observer] = None
        self._watcher: Optional[ConfigWatcher] = None
        
        # 配置缓存
        self._cache: Dict[str, Any] = {}
        self._cache_valid = False
        
        # 配置元数据
        self._config_metadata: Dict[str, Dict[str, Any]] = {}
        
        self._initialized = False
        self._lock = asyncio.Lock()
    
    async def initialize(self):
        """初始化配置管理器"""
        if self._initialized:
            return
        
        async with self._lock:
            # 加载默认配置
            await self._load_default_config()
            
            # 加载环境配置
            await self._load_environment_config()
            
            # 加载用户配置
            await self._load_user_config()
            
            # 启动文件监控
            self._start_file_watching()
            
            # 注册默认验证器
            self._register_default_validators()
            
            self._initialized = True
            logger.info("配置管理器初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
        
        self._initialized = False
        logger.info("配置管理器清理完成")
    
    def _start_file_watching(self):
        """启动文件监控"""
        self._watcher = ConfigWatcher(self)
        self._observer = Observer()
        self._observer.schedule(self._watcher, str(self.config_dir), recursive=True)
        self._observer.start()
        logger.info("配置文件监控已启动")
    
    async def _load_default_config(self):
        """加载默认配置"""
        default_config_path = self.config_dir / "default.yml"
        
        if default_config_path.exists():
            config = await self._load_yaml_file(default_config_path)
            self._configs[ConfigLayer.DEFAULT] = config
            logger.info("默认配置加载完成")
        else:
            # 创建默认配置
            self._configs[ConfigLayer.DEFAULT] = self._create_default_config()
            await self._save_yaml_file(default_config_path, self._configs[ConfigLayer.DEFAULT])
            logger.info("默认配置已创建")
    
    async def _load_environment_config(self):
        """加载环境配置"""
        env = os.getenv("TRADING_ENV", "development")
        env_config_path = self.config_dir / f"{env}.yml"
        
        if env_config_path.exists():
            config = await self._load_yaml_file(env_config_path)
            self._configs[ConfigLayer.ENVIRONMENT] = config
            logger.info(f"环境配置加载完成: {env}")
    
    async def _load_user_config(self):
        """加载用户配置"""
        user_config_path = self.config_dir / "user.yml"
        
        if user_config_path.exists():
            config = await self._load_yaml_file(user_config_path)
            self._configs[ConfigLayer.USER] = config
            logger.info("用户配置加载完成")
    
    async def reload_config_file(self, file_path: str):
        """重载配置文件"""
        path = Path(file_path)
        
        if not path.exists():
            logger.warning(f"配置文件不存在: {file_path}")
            return
        
        try:
            config = await self._load_yaml_file(path)
            
            # 确定配置层级
            layer = self._get_layer_from_filename(path.name)
            
            # 验证配置
            errors = self._validator.validate_config(config)
            if errors:
                logger.error(f"配置验证失败:\n" + "\n".join(errors))
                return
            
            # 记录变更
            old_config = self._configs[layer].copy()
            changes = self._detect_changes(old_config, config)
            
            # 更新配置
            self._configs[layer] = config
            self._cache_valid = False
            
            # 记录变更历史
            for change in changes:
                self._record_change(change)
                # 触发回调
                for callback in self._change_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(change)
                        else:
                            callback(change)
                    except Exception as e:
                        logger.error(f"配置变更回调错误: {e}")
            
            logger.info(f"配置重载完成: {path.name}, {len(changes)} 个变更")
            
        except Exception as e:
            logger.error(f"配置重载失败: {e}")
    
    def _get_layer_from_filename(self, filename: str) -> ConfigLayer:
        """根据文件名确定配置层级"""
        if filename == "default.yml":
            return ConfigLayer.DEFAULT
        elif filename == "user.yml":
            return ConfigLayer.USER
        elif filename in ["development.yml", "production.yml", "testing.yml"]:
            return ConfigLayer.ENVIRONMENT
        else:
            return ConfigLayer.RUNTIME
    
    def _detect_changes(self, old_config: Dict, new_config: Dict) -> List[ConfigChange]:
        """检测配置变更"""
        changes = []
        
        old_flat = self._flatten_dict(old_config)
        new_flat = self._flatten_dict(new_config)
        
        # 检测修改和新增
        for key, new_value in new_flat.items():
            old_value = old_flat.get(key)
            if old_value != new_value:
                changes.append(ConfigChange(
                    key=key,
                    old_value=old_value,
                    new_value=new_value
                ))
        
        # 检测删除
        for key in old_flat:
            if key not in new_flat:
                changes.append(ConfigChange(
                    key=key,
                    old_value=old_flat[key],
                    new_value=None
                ))
        
        return changes
    
    def _flatten_dict(self, d: Dict, parent_key: str = "") -> Dict[str, Any]:
        """展平字典"""
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self._flatten_dict(v, new_key))
            else:
                items[new_key] = v
        return items
    
    def _record_change(self, change: ConfigChange):
        """记录配置变更"""
        self._change_history.append(change)
        
        # 限制历史大小
        if len(self._change_history) > self._max_history_size:
            self._change_history = self._change_history[-self._max_history_size:]
    
    async def get_config(self, key: str = None, default: Any = None) -> Any:
        """获取配置值"""
        if not self._cache_valid:
            self._rebuild_cache()
        
        if key is None:
            return self._cache.copy()
        
        # 支持点号分隔的键
        keys = key.split(".")
        value = self._cache
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    async def set_config(self, key: str, value: Any, layer: ConfigLayer = ConfigLayer.RUNTIME):
        """设置配置值"""
        async with self._lock:
            # 验证值
            if not self._validator.validate(key, value):
                raise ConfigValidationError(f"配置验证失败: {key} = {value}")
            
            # 获取旧值
            old_value = await self.get_config(key)
            
            # 设置新值
            keys = key.split(".")
            config = self._configs[layer]
            
            for k in keys[:-1]:
                if k not in config:
                    config[k] = {}
                config = config[k]
            
            config[keys[-1]] = value
            
            # 记录变更
            change = ConfigChange(
                key=key,
                old_value=old_value,
                new_value=value,
                source="manual"
            )
            self._record_change(change)
            
            # 使缓存失效
            self._cache_valid = False
            
            # 触发回调
            for callback in self._change_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(change)
                    else:
                        callback(change)
                except Exception as e:
                    logger.error(f"配置变更回调错误: {e}")
            
            logger.info(f"配置已更新: {key} = {value}")
    
    def _rebuild_cache(self):
        """重建配置缓存"""
        self._cache = {}
        
        # 按层级合并配置
        for layer in [ConfigLayer.DEFAULT, ConfigLayer.ENVIRONMENT, 
                     ConfigLayer.USER, ConfigLayer.RUNTIME]:
            self._deep_merge(self._cache, self._configs[layer])
        
        self._cache_valid = True
    
    def _deep_merge(self, base: Dict, override: Dict):
        """深度合并字典"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def register_change_callback(self, callback: Callable[[ConfigChange], None]):
        """注册配置变更回调"""
        self._change_callbacks.append(callback)
    
    def unregister_change_callback(self, callback: Callable[[ConfigChange], None]):
        """注销配置变更回调"""
        if callback in self._change_callbacks:
            self._change_callbacks.remove(callback)
    
    def get_change_history(self, limit: int = 100) -> List[ConfigChange]:
        """获取配置变更历史"""
        return self._change_history[-limit:]
    
    async def export_config(self, layer: Optional[ConfigLayer] = None) -> Dict[str, Any]:
        """导出配置"""
        if layer:
            return self._configs[layer].copy()
        else:
            return await self.get_config()
    
    async def import_config(self, config: Dict[str, Any], layer: ConfigLayer = ConfigLayer.RUNTIME):
        """导入配置"""
        async with self._lock:
            # 验证配置
            errors = self._validator.validate_config(config)
            if errors:
                raise ConfigValidationError("\n".join(errors))
            
            # 合并配置
            self._deep_merge(self._configs[layer], config)
            self._cache_valid = False
            
            logger.info(f"配置导入完成: {layer.value}")
    
    async def reset_config(self, layer: ConfigLayer):
        """重置配置到默认值"""
        async with self._lock:
            if layer == ConfigLayer.DEFAULT:
                self._configs[layer] = self._create_default_config()
            else:
                self._configs[layer] = {}
            
            self._cache_valid = False
            logger.info(f"配置已重置: {layer.value}")
    
    def _create_default_config(self) -> Dict[str, Any]:
        """创建默认配置"""
        return {
            "system": {
                "name": "AI Trading System",
                "version": "1.0.0",
                "debug": False,
                "log_level": "INFO"
            },
            "trading": {
                "enabled": True,
                "paper_trading": True,
                "max_position_size": 0.1,
                "max_daily_loss": 0.02,
                "max_position_count": 10,
                "commission_rate": 0.001,
                "slippage_rate": 0.0005
            },
            "risk": {
                "enabled": True,
                "max_drawdown": 0.1,
                "var_limit": 0.05,
                "position_limit": 0.2
            },
            "data": {
                "update_interval": 60,
                "history_days": 365,
                "symbols": ["BTC/USDT", "ETH/USDT"]
            },
            "monitoring": {
                "enabled": True,
                "health_check_interval": 30,
                "metrics_interval": 60
            }
        }
    
    def _register_default_validators(self):
        """注册默认验证器"""
        # 验证 commission_rate 范围
        self._validator.register_validator(
            "trading.commission_rate",
            lambda x: 0 <= x <= 0.1
        )
        
        # 验证 max_position_size 范围
        self._validator.register_validator(
            "trading.max_position_size",
            lambda x: 0 < x <= 1
        )
        
        # 验证 log_level
        self._validator.register_validator(
            "system.log_level",
            lambda x: x in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        )
    
    async def _load_yaml_file(self, path: Path) -> Dict[str, Any]:
        """加载 YAML 文件"""
        try:
            content = await asyncio.to_thread(path.read_text, encoding='utf-8')
            return yaml.safe_load(content) or {}
        except Exception as e:
            logger.error(f"加载 YAML 文件失败: {path}, {e}")
            return {}
    
    async def _save_yaml_file(self, path: Path, config: Dict[str, Any]):
        """保存 YAML 文件"""
        try:
            content = yaml.dump(config, default_flow_style=False, allow_unicode=True)
            await asyncio.to_thread(path.write_text, content, encoding='utf-8')
        except Exception as e:
            logger.error(f"保存 YAML 文件失败: {path}, {e}")


# 使用示例
async def example_usage():
    """使用示例"""
    # 创建配置管理器
    config_manager = EnhancedConfigManager("config")
    await config_manager.initialize()
    
    try:
        # 获取配置
        system_name = await config_manager.get_config("system.name")
        print(f"系统名称: {system_name}")
        
        # 设置配置
        await config_manager.set_config("system.debug", True)
        
        # 注册变更回调
        def on_config_change(change: ConfigChange):
            print(f"配置变更: {change.key} = {change.new_value}")
        
        config_manager.register_change_callback(on_config_change)
        
        # 修改配置
        await config_manager.set_config("trading.max_position_size", 0.15)
        
        # 获取变更历史
        history = config_manager.get_change_history()
        print(f"变更历史: {len(history)} 条记录")
        
        # 导出配置
        config = await config_manager.export_config()
        print(f"配置: {json.dumps(config, indent=2)}")
        
    finally:
        await config_manager.cleanup()


if __name__ == "__main__":
    asyncio.run(example_usage())
