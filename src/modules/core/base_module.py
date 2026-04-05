"""
模块基类

所有模块的基类，提供统一的接口和生命周期管理
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseModule(ABC):
    """
    模块基类
    
    所有模块都应该继承这个基类，确保统一的接口和生命周期管理
    """
    
    def __init__(self, name: str = None):
        """
        初始化模块基类
        
        Args:
            name: 模块名称
        """
        self.name = name or self.__class__.__name__
        self._initialized = False
        self._running = False
        self._start_time: Optional[datetime] = None
        self._stats: Dict[str, Any] = {}
        
        logger.debug(f"模块 {self.name} 实例化")
    
    async def initialize(self) -> bool:
        """
        初始化模块
        
        Returns:
            bool: 初始化是否成功
        """
        if self._initialized:
            logger.warning(f"模块 {self.name} 已经初始化")
            return True
        
        try:
            logger.info(f"🔧 初始化模块 {self.name}...")
            
            # 执行具体的初始化逻辑
            result = await self._do_initialize()
            
            if result:
                self._initialized = True
                self._start_time = datetime.now()
                logger.info(f"✅ 模块 {self.name} 初始化完成")
            else:
                logger.error(f"❌ 模块 {self.name} 初始化失败")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 模块 {self.name} 初始化异常: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    async def _do_initialize(self) -> bool:
        """
        具体的初始化逻辑（子类实现）
        
        Returns:
            bool: 初始化是否成功
        """
        return True
    
    async def start(self) -> bool:
        """
        启动模块
        
        Returns:
            bool: 启动是否成功
        """
        if not self._initialized:
            logger.warning(f"模块 {self.name} 未初始化，无法启动")
            return False
        
        if self._running:
            logger.warning(f"模块 {self.name} 已经在运行")
            return True
        
        try:
            logger.info(f"🚀 启动模块 {self.name}...")
            
            result = await self._do_start()
            
            if result:
                self._running = True
                logger.info(f"✅ 模块 {self.name} 已启动")
            else:
                logger.error(f"❌ 模块 {self.name} 启动失败")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 模块 {self.name} 启动异常: {e}")
            return False
    
    async def _do_start(self) -> bool:
        """
        具体的启动逻辑（子类实现）
        
        Returns:
            bool: 启动是否成功
        """
        return True
    
    async def stop(self):
        """停止模块"""
        if not self._running:
            return
        
        try:
            logger.info(f"🛑 停止模块 {self.name}...")
            
            await self._do_stop()
            
            self._running = False
            logger.info(f"✅ 模块 {self.name} 已停止")
            
        except Exception as e:
            logger.error(f"❌ 模块 {self.name} 停止异常: {e}")
    
    async def _do_stop(self):
        """具体的停止逻辑（子类实现）"""
        pass
    
    async def cleanup(self):
        """清理资源"""
        try:
            logger.info(f"🧹 清理模块 {self.name}...")
            
            # 先停止
            if self._running:
                await self.stop()
            
            # 执行具体清理
            await self._do_cleanup()
            
            self._initialized = False
            logger.info(f"✅ 模块 {self.name} 清理完成")
            
        except Exception as e:
            logger.error(f"❌ 模块 {self.name} 清理异常: {e}")
    
    async def _do_cleanup(self):
        """具体的清理逻辑（子类实现）"""
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取模块统计信息
        
        Returns:
            Dict: 统计信息
        """
        stats = {
            "name": self.name,
            "initialized": self._initialized,
            "running": self._running,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            **self._stats
        }
        return stats
    
    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running


class SingletonModule(BaseModule):
    """
    单例模块基类
    
    确保模块只有一个实例
    """
    
    _instances: Dict[str, 'SingletonModule'] = {}
    
    def __new__(cls, *args, **kwargs):
        """确保单例"""
        if cls.__name__ not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[cls.__name__] = instance
        return cls._instances[cls.__name__]
    
    @classmethod
    def get_instance(cls) -> Optional['SingletonModule']:
        """获取单例实例"""
        return cls._instances.get(cls.__name__)
    
    @classmethod
    def clear_instance(cls):
        """清除单例实例"""
        if cls.__name__ in cls._instances:
            del cls._instances[cls.__name__]
