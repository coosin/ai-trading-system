"""
插件系统

功能：
1. 插件接口定义
2. 插件加载和管理
3. 插件生命周期管理
4. 插件依赖管理
"""

import importlib
import importlib.util
import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class Plugin(ABC):
    """插件基类"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化插件
        
        Args:
            config: 插件配置
        """
        self.config = config
        self.name = config.get("name", self.__class__.__name__)
        self.version = config.get("version", "1.0.0")
        self.description = config.get("description", "")
        self.enabled = config.get("enabled", True)
    
    @abstractmethod
    async def initialize(self) -> bool:
        """初始化插件
        
        Returns:
            是否初始化成功
        """
        pass
    
    @abstractmethod
    async def start(self) -> bool:
        """启动插件
        
        Returns:
            是否启动成功
        """
        pass
    
    @abstractmethod
    async def stop(self) -> bool:
        """停止插件
        
        Returns:
            是否停止成功
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> bool:
        """清理插件
        
        Returns:
            是否清理成功
        """
        pass
    
    def get_info(self) -> Dict[str, Any]:
        """获取插件信息
        
        Returns:
            插件信息
        """
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "enabled": self.enabled
        }


class PluginManager:
    """插件管理器"""
    
    def __init__(self, config_manager=None):
        """初始化插件管理器
        
        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager
        self.plugins: Dict[str, Plugin] = {}
        self.plugin_paths: List[str] = []
        self.plugin_configs: Dict[str, Dict[str, Any]] = {}
    
    async def initialize(self) -> None:
        """初始化插件管理器"""
        # 加载插件配置
        if self.config_manager:
            plugins_config = await self.config_manager.get_config("plugins", {})
            self.plugin_configs = plugins_config.get("plugins", {})
        
        # Runtime plugins live outside the standard API domain package.
        self.register_plugin_path("plugins")
    
    def register_plugin_path(self, path: str) -> None:
        """注册插件路径
        
        Args:
            path: 插件路径
        """
        absolute_path = os.path.abspath(path)
        if absolute_path not in self.plugin_paths and os.path.exists(absolute_path):
            self.plugin_paths.append(absolute_path)
            logger.info(f"注册插件路径: {absolute_path}")
    
    async def load_plugins(self) -> List[str]:
        """加载所有插件
        
        Returns:
            加载成功的插件列表
        """
        loaded_plugins = []
        
        # 从配置中加载插件
        for plugin_name, plugin_config in self.plugin_configs.items():
            if plugin_config.get("enabled", True):
                if await self.load_plugin(plugin_name, plugin_config):
                    loaded_plugins.append(plugin_name)
        
        # 从插件路径中加载插件
        for plugin_path in self.plugin_paths:
            if os.path.exists(plugin_path):
                for item in os.listdir(plugin_path):
                    item_path = os.path.join(plugin_path, item)
                    if os.path.isdir(item_path) and not item.startswith((".", "__")):
                        if not os.path.exists(os.path.join(item_path, "main.py")):
                            continue
                        plugin_name = item
                        if plugin_name not in self.plugins:
                            plugin_config = self.plugin_configs.get(plugin_name, {"enabled": True})
                            if plugin_config.get("enabled", True):
                                if await self.load_plugin_from_path(plugin_name, item_path, plugin_config):
                                    loaded_plugins.append(plugin_name)
        
        return loaded_plugins
    
    async def load_plugin(self, plugin_name: str, plugin_config: Dict[str, Any]) -> bool:
        """加载指定插件
        
        Args:
            plugin_name: 插件名称
            plugin_config: 插件配置
            
        Returns:
            是否加载成功
        """
        try:
            # 从配置中获取插件类路径
            plugin_class_path = plugin_config.get("class_path")
            if not plugin_class_path:
                logger.warning(f"插件 {plugin_name} 缺少 class_path 配置")
                return False
            
            # 导入插件类
            module_path, class_name = plugin_class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, class_name)
            
            # 创建插件实例
            plugin = plugin_class(plugin_config)
            
            # 初始化插件
            if await plugin.initialize():
                self.plugins[plugin_name] = plugin
                logger.info(f"加载插件成功: {plugin_name}")
                return True
            else:
                logger.error(f"插件 {plugin_name} 初始化失败")
                return False
        except Exception as e:
            logger.error(f"加载插件 {plugin_name} 失败: {e}")
            return False
    
    async def load_plugin_from_path(self, plugin_name: str, plugin_path: str, plugin_config: Dict[str, Any]) -> bool:
        """从路径加载插件
        
        Args:
            plugin_name: 插件名称
            plugin_path: 插件路径
            plugin_config: 插件配置
            
        Returns:
            是否加载成功
        """
        try:
            # 检查插件结构
            main_file = os.path.join(plugin_path, "main.py")
            if not os.path.exists(main_file):
                logger.warning(f"插件 {plugin_name} 缺少 main.py 文件")
                return False
            
            # 动态导入插件
            spec = importlib.util.spec_from_file_location(plugin_name, main_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 查找插件类
            plugin_class = None
            for name, obj in module.__dict__.items():
                if isinstance(obj, type) and issubclass(obj, Plugin) and obj != Plugin:
                    plugin_class = obj
                    break
            
            if not plugin_class:
                logger.warning(f"插件 {plugin_name} 缺少 Plugin 子类")
                return False
            
            # 创建插件实例
            plugin = plugin_class(plugin_config)
            
            # 初始化插件
            if await plugin.initialize():
                self.plugins[plugin_name] = plugin
                logger.info(f"从路径加载插件成功: {plugin_name}")
                return True
            else:
                logger.error(f"插件 {plugin_name} 初始化失败")
                return False
        except Exception as e:
            logger.error(f"从路径加载插件 {plugin_name} 失败: {e}")
            return False
    
    async def start_plugins(self) -> List[str]:
        """启动所有插件
        
        Returns:
            启动成功的插件列表
        """
        started_plugins = []
        for plugin_name, plugin in self.plugins.items():
            if await plugin.start():
                started_plugins.append(plugin_name)
        return started_plugins
    
    async def stop_plugins(self) -> List[str]:
        """停止所有插件
        
        Returns:
            停止成功的插件列表
        """
        stopped_plugins = []
        for plugin_name, plugin in self.plugins.items():
            if await plugin.stop():
                stopped_plugins.append(plugin_name)
        return stopped_plugins
    
    async def cleanup_plugins(self) -> List[str]:
        """清理所有插件
        
        Returns:
            清理成功的插件列表
        """
        cleaned_plugins = []
        for plugin_name, plugin in self.plugins.items():
            if await plugin.cleanup():
                cleaned_plugins.append(plugin_name)
        return cleaned_plugins
    
    def get_plugin(self, plugin_name: str) -> Optional[Plugin]:
        """获取插件实例
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            插件实例
        """
        return self.plugins.get(plugin_name)
    
    def get_all_plugins(self) -> Dict[str, Plugin]:
        """获取所有插件
        
        Returns:
            插件字典
        """
        return self.plugins
    
    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """获取插件信息
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            插件信息
        """
        plugin = self.plugins.get(plugin_name)
        if plugin:
            return plugin.get_info()
        return None
    
    def get_all_plugin_info(self) -> Dict[str, Dict[str, Any]]:
        """获取所有插件信息
        
        Returns:
            插件信息字典
        """
        return {
            plugin_name: plugin.get_info()
            for plugin_name, plugin in self.plugins.items()
        }
    
    async def reload_plugin(self, plugin_name: str) -> bool:
        """重新加载插件
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            是否重新加载成功
        """
        if plugin_name in self.plugins:
            # 先停止和清理插件
            plugin = self.plugins[plugin_name]
            await plugin.stop()
            await plugin.cleanup()
            
            # 从配置中重新加载
            plugin_config = self.plugin_configs.get(plugin_name, {})
            if await self.load_plugin(plugin_name, plugin_config):
                await self.plugins[plugin_name].start()
                return True
        return False
    
    async def unload_plugin(self, plugin_name: str) -> bool:
        """卸载插件
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            是否卸载成功
        """
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            await plugin.stop()
            await plugin.cleanup()
            del self.plugins[plugin_name]
            logger.info(f"卸载插件: {plugin_name}")
            return True
        return False
