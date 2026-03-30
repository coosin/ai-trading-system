"""
主控制器模块 - 全智能量化交易系统的大脑

功能：
1. 模块生命周期管理（启动、停止、重启）
2. 模块间通信协调（消息总线）
3. 系统状态监控（健康检查）
4. 错误处理和恢复（故障转移）
5. 配置管理（动态配置更新）
6. 事件驱动架构
"""

import asyncio
import json
import logging
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.modules.core.event_system import EnhancedEventSystem, EventType as CoreEventType
from src.modules.core.enhanced_data_quality import EnhancedDataQualitySystem
from src.modules.core.enhanced_fault_tolerance import EnhancedFaultTolerance
from src.modules.core.llm_integration import EnhancedLLMIntegration
from src.modules.monitoring.trading_monitor import TradingMonitor
from src.modules.api.monitoring_api import set_trading_monitor
from src.modules.strategies.multi_strategy_manager import MultiStrategyManager
from src.modules.api.strategy_api import init_strategy_api

logger = logging.getLogger(__name__)


class ModuleStatus(Enum):
    """模块状态"""

    STOPPED = "stopped"  # 已停止
    STARTING = "starting"  # 启动中
    RUNNING = "running"  # 运行中
    STOPPING = "stopping"  # 停止中
    ERROR = "error"  # 错误状态
    DEGRADED = "degraded"  # 降级运行


class EventType(Enum):
    """事件类型"""

    SYSTEM_START = "system_start"  # 系统启动
    SYSTEM_STOP = "system_stop"  # 系统停止
    MODULE_STARTED = "module_started"  # 模块启动完成
    MODULE_STOPPED = "module_stopped"  # 模块停止完成
    MODULE_ERROR = "module_error"  # 模块错误
    CONFIG_CHANGED = "config_changed"  # 配置变更
    DATA_RECEIVED = "data_received"  # 数据接收
    TRADE_SIGNAL = "trade_signal"  # 交易信号
    ALERT = "alert"  # 警报
    HEARTBEAT = "heartbeat"  # 心跳


class HealthStatus(Enum):
    """健康状态"""

    HEALTHY = "healthy"  # 健康
    WARNING = "warning"  # 警告
    CRITICAL = "critical"  # 严重
    UNKNOWN = "unknown"  # 未知


@dataclass
class ModuleInfo:
    """模块信息"""

    name: str
    module: Any
    status: ModuleStatus = ModuleStatus.STOPPED
    start_time: Optional[datetime] = None
    stop_time: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None
    health_status: HealthStatus = HealthStatus.UNKNOWN
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def uptime(self) -> Optional[timedelta]:
        """运行时间"""
        if self.start_time and self.status == ModuleStatus.RUNNING:
            return datetime.now() - self.start_time
        return None

    @property
    def is_healthy(self) -> bool:
        """是否健康"""
        return self.health_status == HealthStatus.HEALTHY


@dataclass
class SystemEvent:
    """系统事件"""

    id: str
    type: EventType
    source: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    priority: int = 0  # 0=最低，10=最高

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type.value,
            "source": self.source,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority,
        }


@dataclass
class HealthCheckResult:
    """健康检查结果"""

    module_name: str
    status: HealthStatus
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    metrics: Dict[str, Any] = field(default_factory=dict)


class MainController:
    """
    主控制器

    核心功能：
    1. 模块生命周期管理
    2. 模块间通信协调
    3. 系统状态监控
    4. 错误处理和恢复
    5. 配置管理
    6. 事件驱动架构
    """

    def __init__(self, config_manager=None):
        """
        初始化主控制器

        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager

        # 模块管理
        self.modules: Dict[str, ModuleInfo] = {}
        self.module_dependencies: Dict[str, List[str]] = {}

        # 事件系统
        self.event_history: List[SystemEvent] = []

        # 健康检查
        self.health_checks: Dict[str, Callable] = {}
        self.last_health_check: Dict[str, datetime] = {}

        # 系统状态
        self.system_status: ModuleStatus = ModuleStatus.STOPPED
        self.start_time: Optional[datetime] = None
        self.stop_time: Optional[datetime] = None

        # 监控
        self.metrics: Dict[str, Any] = {
            "total_events": 0,
            "total_errors": 0,
            "module_starts": 0,
            "module_stops": 0,
            "event_processing_time_ms": 0,
            "avg_event_latency_ms": 0,
        }

        # 任务和锁
        self._tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._initialized = False
        self._running = False

        # 增强事件系统
        self.event_system = None
        
        # 数据质量监控系统
        self.data_quality_system = None
        
        # 容错机制系统
        self.fault_tolerance = None
        
        # 大模型集成系统
        self.llm_integration = None
        
        # 交易监控器
        self.trading_monitor = None
        
        # 多策略管理器
        self.strategy_manager = None

        # 默认配置
        self.auto_restart_modules = True
        self.max_restart_attempts = 3
        self.health_check_interval = 30  # 秒
        self.event_history_limit = 1000

        logger.info("主控制器初始化完成")

    async def initialize(self) -> None:
        """
        初始化主控制器

        加载配置，设置事件处理器
        """
        if self._initialized:
            return

        logger.info("初始化主控制器...")

        # 加载配置
        if self.config_manager:
            controller_config = await self.config_manager.get_config("controller", {})
            self.auto_restart_modules = controller_config.get("auto_restart_modules", True)
            self.max_restart_attempts = controller_config.get("max_restart_attempts", 3)
            self.health_check_interval = controller_config.get("health_check_interval", 30)
            self.event_history_limit = controller_config.get("event_history_limit", 1000)

        # 初始化增强事件系统
        self.event_system = EnhancedEventSystem("data/events.db")
        await self.event_system.initialize()
        
        # 初始化数据质量监控系统
        self.data_quality_system = EnhancedDataQualitySystem()
        await self.data_quality_system.initialize()
        
        # 初始化容错机制系统
        self.fault_tolerance = EnhancedFaultTolerance()
        await self.fault_tolerance.initialize()
        
        # 初始化大模型集成系统
        self.llm_integration = EnhancedLLMIntegration()
        # 从配置中获取大模型配置
        llm_config = await self.config_manager.get_config("llm", {})
        await self.llm_integration.initialize(llm_config)
        
        # 初始化交易监控器
        self.trading_monitor = TradingMonitor({})
        await self.trading_monitor.initialize()
        # 设置监控器实例到API模块
        set_trading_monitor(self.trading_monitor)
        
        # 初始化多策略管理器
        strategy_config = await self.config_manager.get_config("strategy", {})
        self.strategy_manager = MultiStrategyManager(strategy_config)
        # 初始化策略API
        init_strategy_api(self.strategy_manager)

        # 注册默认事件处理器
        self._register_default_handlers()

        # 启动事件处理任务
        self._running = True
        self._tasks.append(asyncio.create_task(self._health_check_worker()))

        self._initialized = True
        logger.info("主控制器初始化完成")

    async def cleanup(self) -> None:
        """
        清理主控制器

        停止所有模块，清理资源
        """
        logger.info("清理主控制器...")

        self._running = False

        # 停止所有模块
        await self.stop_all_modules()

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        self.modules.clear()
        
        # 清理增强事件系统
        if self.event_system:
            await self.event_system.cleanup()
            self.event_system = None
        
        # 清理数据质量监控系统
        if self.data_quality_system:
            await self.data_quality_system.cleanup()
            self.data_quality_system = None
        
        # 清理容错机制系统
        if self.fault_tolerance:
            await self.fault_tolerance.cleanup()
            self.fault_tolerance = None
        
        # 清理大模型集成系统
        if self.llm_integration:
            await self.llm_integration.cleanup()
            self.llm_integration = None
        
        # 清理交易监控器
        if self.trading_monitor:
            await self.trading_monitor.shutdown()
            self.trading_monitor = None
        
        # 清理多策略管理器
        self.strategy_manager = None
            
        self._initialized = False

        logger.info("主控制器清理完成")

    async def start_system(self) -> bool:
        """
        启动系统

        启动所有模块，开始事件处理

        Returns:
            是否启动成功
        """
        if self.system_status == ModuleStatus.RUNNING:
            logger.warning("系统已经在运行")
            return True

        logger.info("启动系统...")

        try:
            async with self._lock:
                self.system_status = ModuleStatus.STARTING
                self.start_time = datetime.now()
                self.stop_time = None

                # 发送系统启动事件
                await self.emit_event(
                    EventType.SYSTEM_START, "controller", {"timestamp": self.start_time.isoformat()}
                )

                # 按依赖顺序启动模块
                success = await self._start_modules_in_order()

                if success:
                    self.system_status = ModuleStatus.RUNNING
                    self._running = True
                    logger.info("系统启动成功")

                    # 发送心跳事件
                    await self.emit_event(
                        EventType.HEARTBEAT, "controller", {"status": "running", "uptime": 0}
                    )

                    return True
                else:
                    self.system_status = ModuleStatus.ERROR
                    logger.error("系统启动失败")
                    return False

        except Exception as e:
            self.system_status = ModuleStatus.ERROR
            logger.error(f"系统启动异常: {e}")
            traceback.print_exc()
            return False

    async def stop_system(self) -> bool:
        """
        停止系统

        停止所有模块，清理资源

        Returns:
            是否停止成功
        """
        if self.system_status == ModuleStatus.STOPPED:
            logger.warning("系统已经停止")
            return True

        logger.info("停止系统...")

        try:
            async with self._lock:
                self.system_status = ModuleStatus.STOPPING

                # 发送系统停止事件
                await self.emit_event(
                    EventType.SYSTEM_STOP, "controller", {"timestamp": datetime.now().isoformat()}
                )

                # 停止所有模块（逆序）
                await self.stop_all_modules(reverse=True)

                self.system_status = ModuleStatus.STOPPED
                self.stop_time = datetime.now()
                self._running = False

                logger.info("系统停止成功")
                return True

        except Exception as e:
            logger.error(f"系统停止异常: {e}")
            traceback.print_exc()
            return False

    def register_module(self, name: str, module: Any, dependencies: List[str] = None) -> bool:
        """
        注册模块

        Args:
            name: 模块名称
            module: 模块实例
            dependencies: 依赖的模块列表

        Returns:
            是否注册成功
        """
        if name in self.modules:
            logger.warning(f"模块已存在: {name}")
            return False

        module_info = ModuleInfo(name=name, module=module)
        self.modules[name] = module_info

        if dependencies:
            self.module_dependencies[name] = dependencies

        logger.info(f"注册模块: {name}" + (f" (依赖: {dependencies})" if dependencies else ""))
        return True

    async def start_module(self, name: str) -> bool:
        """
        启动单个模块

        Args:
            name: 模块名称

        Returns:
            是否启动成功
        """
        if name not in self.modules:
            logger.error(f"模块不存在: {name}")
            return False

        module_info = self.modules[name]

        if module_info.status == ModuleStatus.RUNNING:
            logger.warning(f"模块已经在运行: {name}")
            return True

        logger.info(f"启动模块: {name}")

        try:
            # 检查依赖
            if name in self.module_dependencies:
                for dep in self.module_dependencies[name]:
                    if dep not in self.modules or self.modules[dep].status != ModuleStatus.RUNNING:
                        logger.error(f"模块 {name} 依赖的模块 {dep} 未运行")
                        return False

            # 设置状态
            module_info.status = ModuleStatus.STARTING

            # 调用模块的initialize方法（如果存在）
            module = module_info.module
            if hasattr(module, "initialize") and callable(module.initialize):
                await module.initialize()

            # 调用模块的start方法（如果存在）
            if hasattr(module, "start") and callable(module.start):
                await module.start()

            # 更新状态
            module_info.status = ModuleStatus.RUNNING
            module_info.start_time = datetime.now()
            module_info.stop_time = None
            module_info.health_status = HealthStatus.HEALTHY

            self.metrics["module_starts"] += 1

            # 发送模块启动事件
            await self.emit_event(
                EventType.MODULE_STARTED,
                name,
                {"module": name, "timestamp": module_info.start_time.isoformat()},
            )

            logger.info(f"模块启动成功: {name}")
            return True

        except Exception as e:
            module_info.status = ModuleStatus.ERROR
            module_info.last_error = str(e)
            module_info.error_count += 1

            self.metrics["total_errors"] += 1

            logger.error(f"模块启动失败 {name}: {e}")
            traceback.print_exc()

            # 发送错误事件
            await self.emit_event(
                EventType.MODULE_ERROR,
                name,
                {"module": name, "error": str(e), "error_count": module_info.error_count},
            )

            return False

    async def stop_module(self, name: str) -> bool:
        """
        停止单个模块

        Args:
            name: 模块名称

        Returns:
            是否停止成功
        """
        if name not in self.modules:
            logger.error(f"模块不存在: {name}")
            return False

        module_info = self.modules[name]

        if module_info.status == ModuleStatus.STOPPED:
            logger.warning(f"模块已经停止: {name}")
            return True

        logger.info(f"停止模块: {name}")

        try:
            # 设置状态
            module_info.status = ModuleStatus.STOPPING

            # 调用模块的stop方法（如果存在）
            module = module_info.module
            if hasattr(module, "stop") and callable(module.stop):
                await module.stop()

            # 调用模块的cleanup方法（如果存在）
            if hasattr(module, "cleanup") and callable(module.cleanup):
                await module.cleanup()

            # 更新状态
            module_info.status = ModuleStatus.STOPPED
            module_info.stop_time = datetime.now()

            self.metrics["module_stops"] += 1

            # 发送模块停止事件
            await self.emit_event(
                EventType.MODULE_STOPPED,
                name,
                {"module": name, "timestamp": module_info.stop_time.isoformat()},
            )

            logger.info(f"模块停止成功: {name}")
            return True

        except Exception as e:
            module_info.status = ModuleStatus.ERROR
            module_info.last_error = str(e)
            module_info.error_count += 1

            logger.error(f"模块停止失败 {name}: {e}")
            traceback.print_exc()

            return False

    async def restart_module(self, name: str) -> bool:
        """
        重启模块

        Args:
            name: 模块名称

        Returns:
            是否重启成功
        """
        logger.info(f"重启模块: {name}")

        # 先停止
        stopped = await self.stop_module(name)
        if not stopped:
            return False

        # 等待一小段时间
        await asyncio.sleep(1)

        # 再启动
        started = await self.start_module(name)
        return started

    async def start_all_modules(self) -> bool:
        """
        启动所有模块

        Returns:
            是否所有模块都启动成功
        """
        logger.info("启动所有模块...")

        success = True
        for name in self.modules:
            if not await self.start_module(name):
                success = False

        return success

    async def stop_all_modules(self, reverse: bool = False) -> bool:
        """
        停止所有模块

        Args:
            reverse: 是否逆序停止

        Returns:
            是否所有模块都停止成功
        """
        logger.info("停止所有模块..." + (" (逆序)" if reverse else ""))

        success = True
        module_names = list(self.modules.keys())

        if reverse:
            module_names.reverse()

        for name in module_names:
            if not await self.stop_module(name):
                success = False

        return success

    def register_event_handler(self, event_type: EventType, handler: Callable) -> None:
        """
        注册事件处理器

        Args:
            event_type: 事件类型
            handler: 处理函数
        """
        if self.event_system:
            # 转换为核心事件类型
            core_event_type_map = {
                EventType.SYSTEM_START: CoreEventType.SYSTEM_START,
                EventType.SYSTEM_STOP: CoreEventType.SYSTEM_STOP,
                EventType.MODULE_STARTED: CoreEventType.MODULE_STARTED,
                EventType.MODULE_STOPPED: CoreEventType.MODULE_STOPPED,
                EventType.MODULE_ERROR: CoreEventType.MODULE_ERROR,
                EventType.CONFIG_CHANGED: CoreEventType.CONFIG_CHANGED,
                EventType.DATA_RECEIVED: CoreEventType.DATA_RECEIVED,
                EventType.TRADE_SIGNAL: CoreEventType.TRADE_SIGNAL,
                EventType.ALERT: CoreEventType.RISK_ALERT,
                EventType.HEARTBEAT: CoreEventType.SYSTEM_START
            }
            
            core_event_type = core_event_type_map.get(event_type, CoreEventType.SYSTEM_START)
            self.event_system.subscribe(core_event_type, handler)
            logger.debug(f"注册事件处理器: {event_type.value} -> {handler.__name__}")
        else:
            # 回退到旧的事件处理器系统
            if event_type not in self.event_handlers:
                self.event_handlers[event_type] = []

            self.event_handlers[event_type].append(handler)
            logger.debug(f"注册事件处理器: {event_type.value} -> {handler.__name__}")

    async def emit_event(
        self, event_type: EventType, source: str, data: Dict[str, Any], priority: int = 0
    ) -> None:
        """
        发送事件

        Args:
            event_type: 事件类型
            source: 事件源
            data: 事件数据
            priority: 优先级
        """
        if self.event_system:
            # 转换为核心事件类型
            core_event_type_map = {
                EventType.SYSTEM_START: CoreEventType.SYSTEM_START,
                EventType.SYSTEM_STOP: CoreEventType.SYSTEM_STOP,
                EventType.MODULE_STARTED: CoreEventType.MODULE_STARTED,
                EventType.MODULE_STOPPED: CoreEventType.MODULE_STOPPED,
                EventType.MODULE_ERROR: CoreEventType.MODULE_ERROR,
                EventType.CONFIG_CHANGED: CoreEventType.CONFIG_CHANGED,
                EventType.DATA_RECEIVED: CoreEventType.DATA_RECEIVED,
                EventType.TRADE_SIGNAL: CoreEventType.TRADE_SIGNAL,
                EventType.ALERT: CoreEventType.RISK_ALERT,
                EventType.HEARTBEAT: CoreEventType.SYSTEM_START
            }
            
            core_event_type = core_event_type_map.get(event_type, CoreEventType.SYSTEM_START)
            
            # 转换优先级
            from src.modules.core.event_system import EventPriority
            event_priority = EventPriority.NORMAL
            if priority >= 8:
                event_priority = EventPriority.CRITICAL
            elif priority >= 5:
                event_priority = EventPriority.HIGH
            elif priority <= 2:
                event_priority = EventPriority.LOW
            
            # 使用增强事件系统发送事件
            await self.event_system.emit(
                event_type=core_event_type,
                source=source,
                data=data,
                priority=event_priority
            )
            
            self.metrics["total_events"] += 1
            logger.debug(f"发送事件: {event_type.value} from {source}")
        else:
            # 回退到旧的事件队列
            event = SystemEvent(
                id=str(uuid.uuid4()), type=event_type, source=source, data=data, priority=priority
            )
            
            try:
                await self.event_queue.put(event)
                self.metrics["total_events"] += 1
                logger.debug(f"发送事件: {event_type.value} from {source}")
            except asyncio.QueueFull:
                logger.warning("事件队列已满，丢弃事件")

    def register_health_check(self, module_name: str, check_func: Callable) -> None:
        """
        注册健康检查

        Args:
            module_name: 模块名称
            check_func: 检查函数，返回HealthCheckResult
        """
        self.health_checks[module_name] = check_func
        logger.info(f"注册健康检查: {module_name}")

    async def get_system_status(self) -> Dict[str, Any]:
        """
        获取系统状态

        Returns:
            系统状态信息
        """
        async with self._lock:
            module_statuses = {}
            for name, info in self.modules.items():
                module_statuses[name] = {
                    "status": info.status.value,
                    "health": info.health_status.value,
                    "uptime": info.uptime.total_seconds() if info.uptime else 0,
                    "error_count": info.error_count,
                    "last_error": info.last_error,
                    "start_time": info.start_time.isoformat() if info.start_time else None,
                    "stop_time": info.stop_time.isoformat() if info.stop_time else None,
                }

            return {
                "system_status": self.system_status.value,
                "start_time": self.start_time.isoformat() if self.start_time else None,
                "stop_time": self.stop_time.isoformat() if self.stop_time else None,
                "uptime": (
                    (datetime.now() - self.start_time).total_seconds()
                    if self.start_time and self.system_status == ModuleStatus.RUNNING
                    else 0
                ),
                "module_count": len(self.modules),
                "running_modules": len(
                    [m for m in self.modules.values() if m.status == ModuleStatus.RUNNING]
                ),
                "module_statuses": module_statuses,
                "metrics": self.metrics.copy(),
            }

    async def get_event_history(
        self, limit: int = 100, event_type: Optional[EventType] = None
    ) -> List[Dict[str, Any]]:
        """
        获取事件历史

        Args:
            limit: 返回的最大事件数
            event_type: 过滤事件类型

        Returns:
            事件历史列表
        """
        events = self.event_history.copy()

        if event_type:
            events = [e for e in events if e.type == event_type]

        events.sort(key=lambda e: e.timestamp, reverse=True)
        return [e.to_dict() for e in events[:limit]]
    
    async def check_data_quality(self, data_source: str, data: Any) -> Dict[str, Any]:
        """
        检查数据质量

        Args:
            data_source: 数据源名称
            data: 要检查的数据

        Returns:
            数据质量报告
        """
        if self.data_quality_system:
            return await self.data_quality_system.check_data_source(data_source, data)
        return {"error": "数据质量系统未初始化"}
    
    def get_data_quality_report(self, data_source: str) -> Optional[Dict[str, Any]]:
        """
        获取数据质量报告

        Args:
            data_source: 数据源名称

        Returns:
            最新的数据质量报告
        """
        if self.data_quality_system:
            return self.data_quality_system.get_latest_report(data_source)
        return None
    
    async def execute_with_protection(self, func: Callable, component: str, *args, **kwargs) -> Any:
        """
        执行受保护的调用

        Args:
            func: 要执行的函数
            component: 组件名称
            *args: 函数参数
            **kwargs: 函数关键字参数

        Returns:
            函数执行结果
        """
        if self.fault_tolerance:
            return await self.fault_tolerance.execute_with_protection(func, component, *args, **kwargs)
        # 回退到直接执行
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    
    def register_recovery_handler(self, component: str, handler: Callable[[], bool]):
        """
        注册组件恢复处理器

        Args:
            component: 组件名称
            handler: 恢复处理函数
        """
        if self.fault_tolerance:
            self.fault_tolerance.register_recovery_handler(component, handler)
    
    def get_fault_tolerance_stats(self) -> Dict[str, Any]:
        """
        获取容错机制统计信息

        Returns:
            容错机制统计信息
        """
        if self.fault_tolerance:
            return self.fault_tolerance.get_stats()
        return {"error": "容错系统未初始化"}
    
    async def analyze_market(self, market_data: Dict[str, Any], provider: Optional[str] = None) -> Dict[str, Any]:
        """
        分析市场数据

        Args:
            market_data: 市场数据
            provider: 大模型提供者

        Returns:
            市场分析结果
        """
        if self.llm_integration:
            return await self.llm_integration.analyze_market(market_data, provider)
        return {"error": "大模型系统未初始化"}
    
    async def generate_strategy(self, market_analysis: Dict[str, Any], provider: Optional[str] = None) -> Dict[str, Any]:
        """
        生成交易策略

        Args:
            market_analysis: 市场分析结果
            provider: 大模型提供者

        Returns:
            交易策略
        """
        if self.llm_integration:
            return await self.llm_integration.generate_strategy(market_analysis, provider)
        return {"error": "大模型系统未初始化"}
    
    async def generate_trading_signal(self, market_data: Dict[str, Any], provider: Optional[str] = None) -> Dict[str, Any]:
        """
        生成交易信号

        Args:
            market_data: 市场数据
            provider: 大模型提供者

        Returns:
            交易信号
        """
        if self.llm_integration:
            return await self.llm_integration.generate_trading_signal(market_data, provider)
        return {"error": "大模型系统未初始化"}
    
    async def analyze_news(self, news: List[str], provider: Optional[str] = None) -> Dict[str, Any]:
        """
        分析新闻

        Args:
            news: 新闻列表
            provider: 大模型提供者

        Returns:
            新闻分析结果
        """
        if self.llm_integration:
            return await self.llm_integration.analyze_news(news, provider)
        return {"error": "大模型系统未初始化"}
    
    async def evaluate_risk(self, position: Dict[str, Any], provider: Optional[str] = None) -> Dict[str, Any]:
        """
        评估风险

        Args:
            position: 交易仓位
            provider: 大模型提供者

        Returns:
            风险评估结果
        """
        if self.llm_integration:
            return await self.llm_integration.evaluate_risk(position, provider)
        return {"error": "大模型系统未初始化"}
    
    async def generate_text(self, prompt: str, provider: Optional[str] = None, **kwargs) -> Any:
        """
        生成文本

        Args:
            prompt: 提示词
            provider: 大模型提供者
            **kwargs: 额外参数

        Returns:
            生成的文本
        """
        if self.llm_integration:
            return await self.llm_integration.generate(prompt, provider, **kwargs)
        return {"error": "大模型系统未初始化"}
    
    def get_trading_monitor(self) -> Optional[TradingMonitor]:
        """
        获取交易监控器实例

        Returns:
            交易监控器实例
        """
        return self.trading_monitor
    
    def get_strategy_manager(self) -> Optional[MultiStrategyManager]:
        """
        获取多策略管理器实例

        Returns:
            多策略管理器实例
        """
        return self.strategy_manager
    
    async def generate_trading_signals(self, market_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        生成交易信号

        Args:
            market_data: 市场数据

        Returns:
            交易信号列表
        """
        if self.strategy_manager:
            return self.strategy_manager.generate_signals(market_data)
        return []
    
    async def get_strategy_performance(self) -> Dict[str, Any]:
        """
        获取策略性能

        Returns:
            策略性能指标
        """
        if self.strategy_manager:
            return self.strategy_manager.get_strategy_performance()
        return {}
    
    async def add_strategy(self, strategy):
        """
        添加策略

        Args:
            strategy: 策略实例
        """
        if self.strategy_manager:
            self.strategy_manager.add_strategy(strategy)
    
    async def update_market_data(self, symbol: str, last_price: float, volume: float, bid: float, ask: float):
        """
        更新市场数据

        Args:
            symbol: 交易对
            last_price: 最新价格
            volume: 交易量
            bid: 买价
            ask: 卖价
        """
        if self.trading_monitor:
            self.trading_monitor.update_market_data(symbol, last_price, volume, bid, ask)
    
    async def update_risk_metrics(self, portfolio_value: float, total_exposure: float, var_95: float, 
                              max_position_size: float, leverage_used: float, margin_level: float):
        """
        更新风险指标

        Args:
            portfolio_value: 组合价值
            total_exposure: 总敞口
            var_95: 95% VaR
            max_position_size: 最大仓位大小
            leverage_used: 使用的杠杆
            margin_level: 保证金水平
        """
        if self.trading_monitor:
            from src.modules.monitoring.trading_monitor import RiskMetrics
            import time
            
            risk_metrics = RiskMetrics(
                portfolio_value=portfolio_value,
                total_exposure=total_exposure,
                var_95=var_95,
                max_position_size=max_position_size,
                leverage_used=leverage_used,
                margin_level=margin_level,
                last_update=time.time()
            )
            
            self.trading_monitor.update_risk_metrics(risk_metrics)
    
    async def update_strategy_performance(self, strategy_name: str, total_trades: int, win_trades: int, 
                                       loss_trades: int, win_rate: float, total_pnl: float, 
                                       max_drawdown: float, sharpe_ratio: float):
        """
        更新策略性能

        Args:
            strategy_name: 策略名称
            total_trades: 总交易次数
            win_trades: 盈利交易次数
            loss_trades: 亏损交易次数
            win_rate: 胜率
            total_pnl: 总盈亏
            max_drawdown: 最大回撤
            sharpe_ratio: 夏普比率
        """
        if self.trading_monitor:
            from src.modules.monitoring.trading_monitor import StrategyPerformance
            import time
            
            performance = StrategyPerformance(
                strategy_name=strategy_name,
                total_trades=total_trades,
                win_trades=win_trades,
                loss_trades=loss_trades,
                win_rate=win_rate,
                total_pnl=total_pnl,
                max_drawdown=max_drawdown,
                sharpe_ratio=sharpe_ratio,
                last_update=time.time()
            )
            
            self.trading_monitor.update_strategy_performance(strategy_name, performance)

    # 私有方法

    async def _start_modules_in_order(self) -> bool:
        """
        按依赖顺序启动模块

        Returns:
            是否所有模块都启动成功
        """
        # 拓扑排序启动
        started = set()
        remaining = set(self.modules.keys())
        max_attempts = 3

        while remaining:
            made_progress = False

            for name in list(remaining):
                # 检查依赖是否满足
                dependencies = self.module_dependencies.get(name, [])
                if all(dep in started for dep in dependencies):
                    # 尝试启动模块
                    for attempt in range(max_attempts):
                        if await self.start_module(name):
                            started.add(name)
                            remaining.remove(name)
                            made_progress = True
                            break
                        elif attempt < max_attempts - 1:
                            logger.warning(f"模块 {name} 启动失败，第 {attempt + 1} 次重试")
                            await asyncio.sleep(2)

                    if name not in started:
                        logger.error(f"模块 {name} 启动失败，达到最大重试次数")

            if not made_progress and remaining:
                # 有循环依赖或无法启动的模块
                logger.error(f"无法启动的模块: {remaining}")
                for name in remaining:
                    logger.error(f"  - {name}: 依赖 {self.module_dependencies.get(name, [])}")
                return False

        return True



    async def _health_check_worker(self) -> None:
        """
        健康检查工作线程
        """
        logger.info("健康检查工作线程启动")

        while self._running:
            try:
                await asyncio.sleep(self.health_check_interval)

                # 执行所有注册的健康检查
                for module_name, check_func in self.health_checks.items():
                    if module_name in self.modules:
                        try:
                            if asyncio.iscoroutinefunction(check_func):
                                result = await check_func()
                            else:
                                result = check_func()

                            if isinstance(result, HealthCheckResult):
                                module_info = self.modules[module_name]
                                module_info.health_status = result.status

                                # 如果健康状态变差，发送警报
                                if result.status == HealthStatus.CRITICAL:
                                    await self.emit_event(
                                        EventType.ALERT,
                                        "health_check",
                                        {
                                            "module": module_name,
                                            "status": result.status.value,
                                            "message": result.message,
                                            "metrics": result.metrics,
                                        },
                                        priority=8,
                                    )

                            self.last_health_check[module_name] = datetime.now()

                        except Exception as e:
                            logger.error(f"健康检查错误 {module_name}: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查工作线程异常: {e}")
                await asyncio.sleep(self.health_check_interval)

        logger.info("健康检查工作线程停止")

    def _register_default_handlers(self) -> None:
        """注册默认事件处理器"""

        async def log_event_handler(event):
            """日志事件处理器"""
            logger.info(f"事件: {event.type.value} from {event.source}")

        async def error_event_handler(event):
            """错误事件处理器"""
            if event.type == CoreEventType.MODULE_ERROR:
                module_name = event.data.get("module")
                error_msg = event.data.get("error")

                # 自动重启模块
                if self.auto_restart_modules and module_name and module_name in self.modules:

                    module_info = self.modules[module_name]
                    if module_info.error_count <= self.max_restart_attempts:
                        logger.info(f"尝试自动重启模块: {module_name}")
                        await self.restart_module(module_name)

        async def config_change_handler(event):
            """配置变更处理器"""
            if event.type == CoreEventType.CONFIG_CHANGED:
                # 重新加载配置并通知模块
                logger.info("配置变更，重新加载系统配置")
                # 这里可以实现配置热重载逻辑

        # 注册处理器
        if self.event_system:
            self.event_system.subscribe(CoreEventType.SYSTEM_START, log_event_handler)
            self.event_system.subscribe(CoreEventType.SYSTEM_STOP, log_event_handler)
            self.event_system.subscribe(CoreEventType.MODULE_STARTED, log_event_handler)
            self.event_system.subscribe(CoreEventType.MODULE_STOPPED, log_event_handler)
            self.event_system.subscribe(CoreEventType.MODULE_ERROR, error_event_handler)
            self.event_system.subscribe(CoreEventType.CONFIG_CHANGED, config_change_handler)
            self.event_system.subscribe(CoreEventType.RISK_ALERT, log_event_handler)
        else:
            # 回退到旧的事件处理器系统
            async def old_log_event_handler(event: SystemEvent):
                """日志事件处理器"""
                logger.info(f"事件: {event.type.value} from {event.source}")

            async def old_error_event_handler(event: SystemEvent):
                """错误事件处理器"""
                if event.type == EventType.MODULE_ERROR:
                    module_name = event.data.get("module")
                    error_msg = event.data.get("error")

                    # 自动重启模块
                    if self.auto_restart_modules and module_name and module_name in self.modules:

                        module_info = self.modules[module_name]
                        if module_info.error_count <= self.max_restart_attempts:
                            logger.info(f"尝试自动重启模块: {module_name}")
                            await self.restart_module(module_name)

            async def old_config_change_handler(event: SystemEvent):
                """配置变更处理器"""
                if event.type == EventType.CONFIG_CHANGED:
                    # 重新加载配置并通知模块
                    logger.info("配置变更，重新加载系统配置")
                    # 这里可以实现配置热重载逻辑

            # 注册处理器
            self.register_event_handler(EventType.SYSTEM_START, old_log_event_handler)
            self.register_event_handler(EventType.SYSTEM_STOP, old_log_event_handler)
            self.register_event_handler(EventType.MODULE_STARTED, old_log_event_handler)
            self.register_event_handler(EventType.MODULE_STOPPED, old_log_event_handler)
            self.register_event_handler(EventType.MODULE_ERROR, old_error_event_handler)
            self.register_event_handler(EventType.CONFIG_CHANGED, old_config_change_handler)
            self.register_event_handler(EventType.ALERT, old_log_event_handler)
            self.register_event_handler(EventType.HEARTBEAT, old_log_event_handler)


# 使用示例
async def example_usage():
    """主控制器使用示例"""

    # 创建主控制器
    controller = MainController()
    await controller.initialize()

    try:
        # 注册模块（模拟）
        class MockModule:
            async def initialize(self):
                print("MockModule initialized")

            async def start(self):
                print("MockModule started")

            async def stop(self):
                print("MockModule stopped")

            async def cleanup(self):
                print("MockModule cleaned up")

        # 注册模块
        controller.register_module("data_pipeline", MockModule())
        controller.register_module("cache_manager", MockModule(), dependencies=["data_pipeline"])
        controller.register_module(
            "trade_engine", MockModule(), dependencies=["data_pipeline", "cache_manager"]
        )

        # 注册事件处理器
        def custom_event_handler(event: SystemEvent):
            print(f"Custom handler: {event.type.value} - {event.data}")

        controller.register_event_handler(EventType.DATA_RECEIVED, custom_event_handler)
        controller.register_event_handler(EventType.TRADE_SIGNAL, custom_event_handler)

        # 启动系统
        success = await controller.start_system()
        print(f"系统启动: {'成功' if success else '失败'}")

        if success:
            # 运行一段时间
            await asyncio.sleep(5)

            # 获取系统状态
            status = await controller.get_system_status()
            print(f"系统状态: {json.dumps(status, indent=2, default=str)}")

            # 发送测试事件
            await controller.emit_event(
                EventType.DATA_RECEIVED,
                "test_source",
                {"symbol": "BTC/USDT", "price": 50000, "volume": 100},
            )

            await asyncio.sleep(2)

            # 停止系统
            await controller.stop_system()

    finally:
        await controller.cleanup()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
