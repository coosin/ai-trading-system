"""
主控制器模块

协调所有模块的运行，处理模块间通信和依赖。
系统状态管理和故障恢复，提供统一的管理接口。
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SystemMode(Enum):
    """系统运行模式"""
    BACKTEST = "backtest"          # 回测模式：历史数据测试
    PAPER_TRADING = "paper"        # 模拟交易：实时数据，虚拟资金
    LIVE_TRADING = "live"          # 实盘交易：连接真实交易所
    TRAINING = "training"          # 训练模式：模型训练和优化
    DEVELOPMENT = "development"    # 开发模式：调试和测试


class ModuleStatus(Enum):
    """模块状态"""
    STOPPED = "stopped"      # 已停止
    INITIALIZING = "init"    # 初始化中
    RUNNING = "running"      # 运行中
    PAUSED = "paused"        # 已暂停
    ERROR = "error"          # 错误状态
    SHUTTING_DOWN = "shutdown"  # 关闭中


@dataclass
class ModuleInfo:
    """模块信息"""
    name: str
    status: ModuleStatus
    last_error: Optional[str] = None
    uptime: float = 0.0
    metrics: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {}


class SystemModule(ABC):
    """系统模块基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.status = ModuleStatus.STOPPED
        self._start_time: Optional[float] = None
        self._dependencies: List[str] = []
    
    @abstractmethod
    async def initialize(self) -> None:
        """初始化模块"""
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """启动模块"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """停止模块"""
        pass
    
    @abstractmethod
    async def get_metrics(self) -> Dict[str, Any]:
        """获取模块指标"""
        pass
    
    def add_dependency(self, module_name: str) -> None:
        """添加模块依赖"""
        if module_name not in self._dependencies:
            self._dependencies.append(module_name)
    
    def get_dependencies(self) -> List[str]:
        """获取模块依赖"""
        return self._dependencies.copy()
    
    def _update_status(self, status: ModuleStatus) -> None:
        """更新模块状态"""
        old_status = self.status
        self.status = status
        
        if status == ModuleStatus.RUNNING and self._start_time is None:
            self._start_time = asyncio.get_event_loop().time()
        elif status != ModuleStatus.RUNNING:
            self._start_time = None
        
        logger.debug(f"模块 {self.name} 状态变更: {old_status} -> {status}")


class MainController:
    """
    主控制器
    
    职责：
    1. 协调所有模块的运行
    2. 处理模块间通信和依赖
    3. 系统状态管理和故障恢复
    4. 提供统一的管理接口
    """
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.modules: Dict[str, SystemModule] = {}
        self.module_status: Dict[str, ModuleInfo] = {}
        self.system_mode: SystemMode = SystemMode.DEVELOPMENT
        self.running = False
        self._module_lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None
        
        # 初始化模块
        self._initialize_modules()
    
    def _initialize_modules(self) -> None:
        """初始化所有模块"""
        # 这里会注册所有系统模块
        # 实际实现中会根据配置动态加载模块
        pass
    
    async def initialize(self) -> None:
        """初始化主控制器"""
        logger.info("初始化主控制器...")
        
        # 从配置获取系统模式
        mode_str = await self.config_manager.get_config("system", "mode", "development")
        try:
            self.system_mode = SystemMode(mode_str.lower())
        except ValueError:
            logger.warning(f"无效的系统模式: {mode_str}, 使用默认模式: development")
            self.system_mode = SystemMode.DEVELOPMENT
        
        logger.info(f"系统模式: {self.system_mode.value}")
        
        # 初始化所有模块
        await self._initialize_all_modules()
        
        logger.info("主控制器初始化完成")
    
    async def _initialize_all_modules(self) -> None:
        """初始化所有模块"""
        async with self._module_lock:
            for name, module in self.modules.items():
                try:
                    logger.info(f"初始化模块: {name}")
                    await module.initialize()
                    self.module_status[name] = ModuleInfo(
                        name=name,
                        status=ModuleStatus.INITIALIZING
                    )
                    logger.info(f"模块 {name} 初始化完成")
                except Exception as e:
                    logger.error(f"模块 {name} 初始化失败: {e}")
                    self.module_status[name] = ModuleInfo(
                        name=name,
                        status=ModuleStatus.ERROR,
                        last_error=str(e)
                    )
    
    async def start_all_modules(self) -> None:
        """启动所有模块"""
        if self.running:
            logger.warning("系统已经在运行")
            return
        
        logger.info("启动所有模块...")
        self.running = True
        
        # 检查依赖并启动模块
        await self._start_modules_with_dependencies()
        
        # 启动健康检查
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        logger.info("所有模块已启动")
    
    async def _start_modules_with_dependencies(self) -> None:
        """按依赖顺序启动模块"""
        # 拓扑排序：先启动没有依赖的模块
        started = set()
        modules_to_start = list(self.modules.keys())
        
        while modules_to_start:
            can_start = []
            
            for module_name in modules_to_start:
                module = self.modules[module_name]
                dependencies = module.get_dependencies()
                
                # 检查所有依赖是否都已启动
                if all(dep in started for dep in dependencies):
                    can_start.append(module_name)
            
            if not can_start:
                # 检测循环依赖
                logger.error(f"无法启动模块，可能存在循环依赖: {modules_to_start}")
                break
            
            # 启动可启动的模块
            for module_name in can_start:
                await self._start_single_module(module_name)
                started.add(module_name)
                modules_to_start.remove(module_name)
        
        logger.info(f"已启动 {len(started)} 个模块")
    
    async def _start_single_module(self, module_name: str) -> None:
        """启动单个模块"""
        module = self.modules[module_name]
        
        try:
            logger.info(f"启动模块: {module_name}")
            await module.start()
            
            # 更新状态
            if module_name in self.module_status:
                self.module_status[module_name].status = ModuleStatus.RUNNING
            else:
                self.module_status[module_name] = ModuleInfo(
                    name=module_name,
                    status=ModuleStatus.RUNNING
                )
            
            logger.info(f"模块 {module_name} 启动成功")
            
        except Exception as e:
            logger.error(f"模块 {module_name} 启动失败: {e}")
            if module_name in self.module_status:
                self.module_status[module_name].status = ModuleStatus.ERROR
                self.module_status[module_name].last_error = str(e)
    
    async def stop_all_modules(self) -> None:
        """停止所有模块"""
        if not self.running:
            return
        
        logger.info("停止所有模块...")
        self.running = False
        
        # 停止健康检查
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # 反向停止模块（先停止依赖其他模块的模块）
        modules_to_stop = list(self.modules.keys())
        
        while modules_to_stop:
            can_stop = []
            
            for module_name in modules_to_stop:
                module = self.modules[module_name]
                dependencies = module.get_dependencies()
                
                # 检查是否有其他模块依赖此模块
                dependent_modules = [
                    name for name in modules_to_stop 
                    if name != module_name and 
                    module_name in self.modules[name].get_dependencies()
                ]
                
                if not dependent_modules:
                    can_stop.append(module_name)
            
            if not can_stop:
                # 强制停止剩余模块
                logger.warning(f"强制停止剩余模块: {modules_to_stop}")
                can_stop = modules_to_stop
            
            # 停止可停止的模块
            for module_name in can_stop:
                await self._stop_single_module(module_name)
                modules_to_stop.remove(module_name)
        
        logger.info("所有模块已停止")
    
    async def _stop_single_module(self, module_name: str) -> None:
        """停止单个模块"""
        module = self.modules[module_name]
        
        try:
            logger.info(f"停止模块: {module_name}")
            await module.stop()
            
            # 更新状态
            if module_name in self.module_status:
                self.module_status[module_name].status = ModuleStatus.STOPPED
            
            logger.info(f"模块 {module_name} 已停止")
            
        except Exception as e:
            logger.error(f"模块 {module_name} 停止失败: {e}")
    
    async def pause_module(self, module_name: str) -> bool:
        """暂停模块"""
        if module_name not in self.modules:
            logger.error(f"模块不存在: {module_name}")
            return False
        
        module = self.modules[module_name]
        
        try:
            # 这里需要模块支持暂停功能
            # 简化实现：直接停止
            await module.stop()
            self.module_status[module_name].status = ModuleStatus.PAUSED
            logger.info(f"模块 {module_name} 已暂停")
            return True
            
        except Exception as e:
            logger.error(f"暂停模块 {module_name} 失败: {e}")
            return False
    
    async def resume_module(self, module_name: str) -> bool:
        """恢复模块"""
        if module_name not in self.modules:
            logger.error(f"模块不存在: {module_name}")
            return False
        
        module = self.modules[module_name]
        
        try:
            await module.start()
            self.module_status[module_name].status = ModuleStatus.RUNNING
            logger.info(f"模块 {module_name} 已恢复")
            return True
            
        except Exception as e:
            logger.error(f"恢复模块 {module_name} 失败: {e}")
            return False
    
    async def restart_module(self, module_name: str) -> bool:
        """重启模块"""
        if module_name not in self.modules:
            logger.error(f"模块不存在: {module_name}")
            return False
        
        logger.info(f"重启模块: {module_name}")
        
        try:
            await self._stop_single_module(module_name)
            await asyncio.sleep(1)  # 等待一下
            await self._start_single_module(module_name)
            
            logger.info(f"模块 {module_name} 重启成功")
            return True
            
        except Exception as e:
            logger.error(f"重启模块 {module_name} 失败: {e}")
            return False
    
    async def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        status = {
            "running": self.running,
            "mode": self.system_mode.value,
            "modules": {}
        }
        
        async with self._module_lock:
            for name, module_info in self.module_status.items():
                # 获取模块指标
                metrics = {}
                if name in self.modules:
                    try:
                        metrics = await self.modules[name].get_metrics()
                    except Exception as e:
                        logger.debug(f"获取模块 {name} 指标失败: {e}")
                
                status["modules"][name] = {
                    "status": module_info.status.value,
                    "last_error": module_info.last_error,
                    "uptime": module_info.uptime,
                    "metrics": metrics
                }
        
        return status
    
    async def change_system_mode(self, new_mode: SystemMode) -> bool:
        """更改系统模式"""
        if self.running:
            logger.error("无法在系统运行时更改模式")
            return False
        
        old_mode = self.system_mode
        self.system_mode = new_mode
        
        # 保存到配置
        await self.config_manager.set_config("system", "mode", new_mode.value)
        
        logger.info(f"系统模式已更改: {old_mode.value} -> {new_mode.value}")
        return True
    
    async def register_module(self, module: SystemModule) -> bool:
        """注册新模块"""
        async with self._module_lock:
            if module.name in self.modules:
                logger.error(f"模块已存在: {module.name}")
                return False
            
            self.modules[module.name] = module
            
            # 如果系统已在运行，初始化并启动新模块
            if self.running:
                try:
                    await module.initialize()
                    await module.start()
                    self.module_status[module.name] = ModuleInfo(
                        name=module.name,
                        status=ModuleStatus.RUNNING
                    )
                except Exception as e:
                    logger.error(f"注册并启动模块 {module.name} 失败: {e}")
                    self.module_status[module.name] = ModuleInfo(
                        name=module.name,
                        status=ModuleStatus.ERROR,
                        last_error=str(e)
                    )
                    return False
            
            logger.info(f"已注册模块: {module.name}")
            return True
    
    async def unregister_module(self, module_name: str) -> bool:
        """注销模块"""
        async with self._module_lock:
            if module_name not in self.modules:
                logger.error(f"模块不存在: {module_name}")
                return False
            
            # 如果模块在运行，先停止
            if self.running and module_name in self.module_status:
                if self.module_status[module_name].status == ModuleStatus.RUNNING:
                    await self._stop_single_module(module_name)
            
            # 移除模块
            del self.modules[module_name]
            if module_name in self.module_status:
                del self.module_status[module_name]
            
            logger.info(f"已注销模块: {module_name}")
            return True
    
    async def _health_check_loop(self) -> None:
        """健康检查循环"""
        logger.info("启动健康检查循环")
        
        while self.running:
            try:
                await asyncio.sleep(30)  # 每30秒检查一次
                await self._perform_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查出错: {e}")
    
    async def _perform_health_check(self) -> None:
        """执行健康检查"""
        async with self._module_lock:
            for name, module_info in self.module_status.items():
                if module_info.status == ModuleStatus.RUNNING:
                    # 检查模块是否健康
                    try:
                        metrics = await self.modules[name].get_metrics()
                        
                        # 更新运行时间
                        loop_time = asyncio.get_event_loop().time()
                        if self.modules[name]._start_time:
                            module_info.uptime = loop_time - self.modules[name]._start_time
                        
                        # 更新指标
                        module_info.metrics = metrics
                        
                        # 这里可以添加更多的健康检查逻辑
                        # 例如：检查错误率、延迟等
                        
                    except Exception as e:
                        logger.warning(f"模块 {name} 健康检查失败: {e}")
                        module_info.status = ModuleStatus.ERROR
                        module_info.last_error = str(e)
    
    async def shutdown(self) -> None:
        """关闭主控制器"""
        logger.info("关闭主控制器...")
        
        await self.stop_all_modules()
        
        # 清理资源
        self.modules.clear()
        self.module_status.clear()
        
        logger.info("主控制器已关闭")


# 示例模块实现
class ExampleModule(SystemModule):
    """示例模块"""
    
    def __init__(self, name: str):
        super().__init__(name)
        self.counter = 0
    
    async def initialize(self) -> None:
        logger.info(f"初始化示例模块: {self.name}")
        self.counter = 0
        self._update_status(ModuleStatus.INITIALIZING)
    
    async def start(self) -> None:
        logger.info(f"启动示例模块: {self.name}")
        self.counter = 0
        self._update_status(ModuleStatus.RUNNING)
    
    async def stop(self) -> None:
        logger.info(f"停止示例模块: {self.name}")
        self._update_status(ModuleStatus.STOPPED)
    
    async def get_metrics(self) -> Dict[str, Any]:
        return {
            "counter": self.counter,
            "status": self.status.value
        }


if __name__ == "__main__":
    import asyncio
    
    async def test():
        from unittest.mock import AsyncMock
        
        # 模拟配置管理器
        config_mock = AsyncMock()
        config_mock.get_config.return_value = "development"
        
        # 创建主控制器
        controller = MainController(config_mock)
        
        # 注册示例模块
        example_module = ExampleModule("example")
        await controller.register_module(example_module)
        
        # 初始化
        await controller.initialize()
        
        # 启动
        await controller.start_all_modules()
        
        # 获取状态
        status = await controller.get_system_status()
        print("系统状态:", status)
        
        # 运行一会儿
        await asyncio.sleep(2)
        
        # 停止
        await controller.shutdown()
    
    asyncio.run(test())