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
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from src.modules.core.event_system import EnhancedEventSystem, EventType as CoreEventType
from src.modules.core.enhanced_data_quality import EnhancedDataQualitySystem
from src.modules.core.enhanced_fault_tolerance import EnhancedFaultTolerance
from src.modules.core.llm_integration import EnhancedLLMIntegration
from src.modules.core.enhanced_llm_manager import EnhancedLLMManager, TaskType
from src.modules.core.plugin_system import PluginManager
from src.modules.core.database_manager import DatabaseManager
from src.modules.core.business_process_manager import BusinessProcessManager
from src.modules.notification.telegram_bot import TelegramBot
from src.modules.monitoring.trading_monitor import TradingMonitor
from src.modules.api.monitoring_api import set_trading_monitor, set_anomaly_detector
from src.modules.core.strategy_manager import StrategyManager
from src.modules.strategies.portfolio_optimizer import PortfolioOptimizer
from src.modules.strategies.parameter_optimizer import ParameterOptimizer
from src.modules.backtesting.backtest_engine import BacktestEngine
from src.modules.data.enhanced_data_storage import EnhancedDataStorage
from src.modules.data.data_backup import DataBackupManager
from src.modules.api.strategy_api import init_strategy_api
from src.modules.intelligence.anomaly_detection import AnomalyDetector, AnomalyDetectionConfig
from src.modules.intelligence.natural_language_interface import NaturalLanguageInterface
from src.modules.simulation.simulated_market import SimulatedMarket
from src.modules.simulation.contract_simulator import ContractSimulator
from src.modules.strategies.strategy_evaluator import StrategyEvaluator

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
        self.event_handlers: Dict[EventType, List[Callable]] = {}
        self.event_queue = asyncio.Queue()

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
        
        # 增强大模型管理器
        self.enhanced_llm_manager = None
        
        # Telegram机器人
        self.telegram_bot = None
        
        # 交易监控器
        self.trading_monitor = None
        
        # 多策略管理器
        self.strategy_manager = None
        
        # 插件管理器
        self.plugin_manager = None
        
        # 异常检测器
        self.anomaly_detector = None
        
        # 策略组合优化器
        self.portfolio_optimizer = None
        
        # 参数优化器
        self.parameter_optimizer = None
        
        # 增强回测系统
        self.enhanced_backtester = None
        
        # 增强数据存储系统
        self.data_storage = None
        
        # 数据备份管理器
        self.backup_manager = None
        
        # 策略评估器
        self.strategy_evaluator = None
        
        # 自然语言接口
        self.natural_language_interface = None
        
        # 模拟交易市场
        self.simulated_market = None
        
        # 数据库管理器
        self.database_manager = None
        
        # 业务流程管理器
        self.business_process_manager = None
        
        # 全智能AI交易引擎
        self.ai_trading_engine = None
        
        # AI记忆管理器
        self.ai_memory_manager = None

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

        # 设置默认配置
        self.auto_restart_modules = True
        self.max_restart_attempts = 3
        self.health_check_interval = 30
        self.event_history_limit = 1000
        
        # 加载配置
        if self.config_manager:
            controller_config = await self.config_manager.get_config("controller", {})
            self.auto_restart_modules = controller_config.get("auto_restart_modules", self.auto_restart_modules)
            self.max_restart_attempts = controller_config.get("max_restart_attempts", self.max_restart_attempts)
            self.health_check_interval = controller_config.get("health_check_interval", self.health_check_interval)
            self.event_history_limit = controller_config.get("event_history_limit", self.event_history_limit)

        # 初始化增强事件系统
        self.event_system = EnhancedEventSystem("data/events.db")
        await self.event_system.initialize()
        
        # 初始化数据质量监控系统
        self.data_quality_system = EnhancedDataQualitySystem()
        await self.data_quality_system.initialize()
        
        # 初始化容错机制系统
        self.fault_tolerance = EnhancedFaultTolerance()
        await self.fault_tolerance.initialize()
        
        # 初始化增强大模型管理器（先初始化，以便传递给其他组件）
        llm_config = {}
        if self.config_manager:
            llm_config = await self.config_manager.get_config("llm", {})
        
        self.enhanced_llm_manager = EnhancedLLMManager()
        await self.enhanced_llm_manager.initialize(llm_config)
        
        # 初始化AI记忆管理器
        from src.modules.core.ai_memory import AIMemoryManager
        from src.modules.core.enhanced_memory_manager import get_enhanced_memory_manager
        import os
        workspace_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "workspace")
        self.ai_memory_manager = AIMemoryManager(workspace_path=workspace_path)
        logger.info("✅ AI记忆管理器初始化完成")
        
        # 初始化增强记忆管理器
        try:
            enhanced_memory = get_enhanced_memory_manager(workspace_path=workspace_path)
            logger.info("✅ 增强记忆管理器初始化完成")
        except Exception as e:
            logger.warning(f"增强记忆管理器初始化失败: {e}")
            enhanced_memory = None
        
        # 初始化大模型集成系统，使用已初始化的enhanced_llm_manager和ai_memory_manager
        self.llm_integration = EnhancedLLMIntegration(
            llm_manager=self.enhanced_llm_manager,
            memory_manager=self.ai_memory_manager
        )
        
        # 设置增强记忆管理器
        if enhanced_memory:
            self.llm_integration.enhanced_memory = enhanced_memory
        
        logger.info("大模型集成系统已连接到增强大模型管理器和AI记忆管理器")
        
        # 初始化AI指令执行器
        from src.modules.core.ai_command_executor import AICommandExecutor
        self.ai_command_executor = AICommandExecutor(main_controller=self)
        await self.ai_command_executor.initialize()
        logger.info("✅ AI指令执行器初始化完成")
        
        # 初始化AI学习引擎
        try:
            from src.modules.core.ai_learning_engine import AILearningEngine
            self.ai_learning_engine = AILearningEngine(
                memory_manager=self.ai_memory_manager,
                llm_integration=self.llm_integration
            )
            await self.ai_learning_engine.start()
            logger.info("✅ AI学习引擎初始化完成")
        except Exception as e:
            logger.warning(f"⚠️ AI学习引擎初始化失败: {e}")
        
        # 初始化交易监控器
        self.trading_monitor = TradingMonitor({})
        await self.trading_monitor.initialize()
        # 设置监控器实例到API模块
        set_trading_monitor(self.trading_monitor)
        
        # 初始化多策略管理器
        self.strategy_manager = StrategyManager(self.config_manager)
        # 初始化策略API
        init_strategy_api(self.strategy_manager)
        
        # 初始化插件管理器（仅当有config_manager时）
        if self.config_manager:
            self.plugin_manager = PluginManager(self.config_manager)
            await self.plugin_manager.initialize()
            # 加载插件
            loaded_plugins = await self.plugin_manager.load_plugins()
            logger.info(f"加载插件: {loaded_plugins}")
            # 启动插件
            started_plugins = await self.plugin_manager.start_plugins()
            logger.info(f"启动插件: {started_plugins}")
        
        # 初始化异常检测器
        self.anomaly_detector = AnomalyDetector(AnomalyDetectionConfig())
        await self.anomaly_detector.initialize()
        # 设置异常检测器实例到API模块
        set_anomaly_detector(self.anomaly_detector)
        
        # 初始化策略组合优化器
        self.portfolio_optimizer = PortfolioOptimizer()
        
        # 初始化参数优化器
        self.parameter_optimizer = ParameterOptimizer()
        
        # 初始化增强回测系统
        self.enhanced_backtester = BacktestEngine()
        
        # 初始化增强数据存储系统
        self.data_storage = EnhancedDataStorage()
        
        # 初始化数据备份管理器
        self.backup_manager = DataBackupManager()
        # 启动定时备份任务
        self._tasks.append(asyncio.create_task(self.backup_manager.schedule_backup()))
        
        # 初始化策略评估器
        self.strategy_evaluator = StrategyEvaluator("main")
        
        # 初始化自然语言接口
        self.natural_language_interface = NaturalLanguageInterface(self.llm_integration)
        
        # 初始化Telegram机器人（仅当有config_manager时）
        if self.config_manager:
            telegram_config = await self.config_manager.get_config("telegram", {})
            
            # 获取代理配置
            proxy_config = await self.config_manager.get_config("proxy", {})
            if proxy_config.get("enabled") and proxy_config.get("use_global_proxy"):
                global_proxy = proxy_config.get("global_proxy", {})
                if global_proxy.get("enabled"):
                    proxy_url = f"{global_proxy.get('proxy_type', 'http')}://{global_proxy.get('host')}:{global_proxy.get('port')}"
                    telegram_config["proxy"] = proxy_url
                    logger.info(f"Telegram机器人配置代理: {proxy_url}")
            
            self.telegram_bot = TelegramBot(
                telegram_config,
                nli=self.natural_language_interface,
                llm_integration=self.llm_integration,
                main_controller=self
            )
            await self.telegram_bot.initialize()
            await self.telegram_bot.start()
        
        # 初始化模拟交易市场
        self.simulated_market = SimulatedMarket()
        await self.simulated_market.initialize()
        
        # 初始化模拟合约交易管理器（如果配置为模拟模式）
        trading_config = await self.config_manager.get_config("trading", {})
        if trading_config.get("mode") == "simulation":
            simulation_config = trading_config.get("simulation", {})
            self.contract_simulator = ContractSimulator(simulation_config)
            await self.contract_simulator.initialize()
            logger.info("模拟合约交易管理器已启动")
        else:
            self.contract_simulator = None
        
        # 初始化数据库管理器
        self.database_manager = DatabaseManager(self.config_manager)
        await self.database_manager.initialize()
        
        # 初始化业务流程管理器
        self.business_process_manager = BusinessProcessManager(self)
        await self.business_process_manager.initialize()
        
        # 初始化紧急停止系统
        try:
            from src.modules.safety.emergency_stop import EmergencyStopSystem
            self.emergency_stop = EmergencyStopSystem()
            logger.info("✅ 紧急停止系统已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 紧急停止系统初始化失败: {e}")
            self.emergency_stop = None
        
        # 初始化智能监控系统
        try:
            from src.modules.monitoring.intelligent_monitoring import IntelligentMonitoringSystem
            self.intelligent_monitoring = IntelligentMonitoringSystem()
            logger.info("✅ 智能监控系统已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 智能监控系统初始化失败: {e}")
            self.intelligent_monitoring = None
        
        # 初始化安全管理器
        try:
            from src.modules.security.security_manager import SecurityManager
            self.security_manager = SecurityManager()
            logger.info("✅ 安全管理器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 安全管理器初始化失败: {e}")
            self.security_manager = None
        
        # 初始化智能资金管理器
        try:
            from src.modules.core.intelligent_fund_manager import IntelligentFundManager
            from src.modules.core.risk_manager import RiskManager
            fund_config = {
                "initial_funds": 10000,
                "risk_per_trade": 0.02,
                "max_leverage": 3
            }
            risk_mgr = RiskManager()
            self.fund_manager = IntelligentFundManager(
                db_manager=self.database_manager,
                risk_manager=risk_mgr,
                config=fund_config
            )
            await self.fund_manager.initialize()
            logger.info("✅ 智能资金管理器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 智能资金管理器初始化失败: {e}")
            self.fund_manager = None
        
        # 初始化全智能AI交易引擎
        from src.modules.core.ai_trading_engine import AITradingEngine
        self.ai_trading_engine = AITradingEngine(self)
        await self.ai_trading_engine.initialize()
        logger.info("✅ 全智能AI交易引擎初始化完成")
        
        # 设置便捷引用（用于AICommandExecutor等模块访问）
        if self.ai_trading_engine and hasattr(self.ai_trading_engine, 'exchange'):
            self.okx_exchange = self.ai_trading_engine.exchange
            logger.info("✅ OKX交易所引用已设置")
        
        if self.ai_trading_engine and hasattr(self.ai_trading_engine, 'risk_monitor'):
            self.risk_monitor = self.ai_trading_engine.risk_monitor
            logger.info("✅ 风险监控引用已设置")

        # 初始化AI核心决策引擎 - AI是交易决策的核心
        try:
            from src.modules.core.ai_core_decision_engine import AICoreDecisionEngine
            self.ai_core = AICoreDecisionEngine(self)
            await self.ai_core.initialize()
            logger.info("✅ AI核心决策引擎初始化完成 - AI全权决策模式")
            
            # 兼容性：保留active_trader引用
            self.active_trader = self.ai_core
        except Exception as e:
            logger.error(f"❌ AI核心决策引擎初始化失败: {e}")
            self.ai_core = None
            self.active_trader = None

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
        
        # 清理增强大模型管理器
        if self.enhanced_llm_manager:
            await self.enhanced_llm_manager.cleanup()
            self.enhanced_llm_manager = None
        
        # 清理Telegram机器人
        if self.telegram_bot:
            await self.telegram_bot.shutdown()
            self.telegram_bot = None
        
        # 清理交易监控器
        if self.trading_monitor:
            await self.trading_monitor.shutdown()
            self.trading_monitor = None
        
        # 清理AI学习引擎
        if hasattr(self, 'ai_learning_engine') and self.ai_learning_engine:
            await self.ai_learning_engine.stop()
            self.ai_learning_engine = None
        
        # 清理多策略管理器
        self.strategy_manager = None
        
        # 清理插件管理器
        if self.plugin_manager:
            await self.plugin_manager.stop_plugins()
            await self.plugin_manager.cleanup_plugins()
            self.plugin_manager = None
        
        # 清理异常检测器
        if self.anomaly_detector:
            await self.anomaly_detector.shutdown()
            self.anomaly_detector = None
        
        # 清理数据库管理器
        if self.database_manager:
            await self.database_manager.cleanup()
            self.database_manager = None
        
        # 清理业务流程管理器
        if self.business_process_manager:
            await self.business_process_manager.shutdown()
            self.business_process_manager = None
        
        # 清理紧急停止系统
        if hasattr(self, 'emergency_stop') and self.emergency_stop:
            self.emergency_stop = None
        
        # 清理智能监控系统
        if hasattr(self, 'intelligent_monitoring') and self.intelligent_monitoring:
            self.intelligent_monitoring = None
        
        # 清理安全管理器
        if hasattr(self, 'security_manager') and self.security_manager:
            self.security_manager = None
        
        # 清理智能资金管理器
        if hasattr(self, 'fund_manager') and self.fund_manager:
            await self.fund_manager.shutdown()
            self.fund_manager = None
            
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
                    
                    # 启动全智能AI交易引擎
                    if self.ai_trading_engine:
                        await self.ai_trading_engine.start()
                        logger.info("🚀 全智能AI交易引擎已启动，开始全自动交易")

                    # 启动AI核心决策引擎 - AI全权决策
                    if hasattr(self, 'ai_core') and self.ai_core:
                        await self.ai_core.start()
                        logger.info("🧠 AI核心决策引擎已启动 - AI全权决策模式")

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

        # 启动全智能AI交易引擎
        if self.ai_trading_engine:
            try:
                await self.ai_trading_engine.start()
                logger.info("🚀 全智能AI交易引擎已启动，开始全自动交易")
            except Exception as e:
                logger.error(f"AI交易引擎启动失败: {e}")
                success = False

        # 启动主动交易执行器
        if hasattr(self, 'active_trader') and self.active_trader:
            try:
                await self.active_trader.start()
                logger.info("🎯 主动交易执行器已启动，开始实盘交易")
            except Exception as e:
                logger.error(f"主动交易执行器启动失败: {e}")
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

        # 先停止AI核心决策引擎
        if hasattr(self, 'ai_core') and self.ai_core:
            try:
                await self.ai_core.stop()
                logger.info("🛑 AI核心决策引擎已停止")
            except Exception as e:
                logger.error(f"AI核心决策引擎停止失败: {e}")

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
        # 总是向旧的事件处理器系统添加，以确保测试通过
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
        
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
        # 总是添加到事件历史
        event = SystemEvent(
            id=str(uuid.uuid4()), type=event_type, source=source, data=data, priority=priority
        )
        self.event_history.append(event)
        
        # 限制历史记录大小
        if len(self.event_history) > self.event_history_limit:
            self.event_history = self.event_history[-self.event_history_limit:]
        
        # 调用旧的事件处理器（如果有）
        if event_type in self.event_handlers:
            for handler in self.event_handlers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logger.error(f"事件处理器执行错误: {e}")
        
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
    
    def get_strategy_manager(self) -> Optional[StrategyManager]:
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
    
    def get_plugin_manager(self) -> Optional[PluginManager]:
        """
        获取插件管理器实例

        Returns:
            插件管理器实例
        """
        return self.plugin_manager
    
    async def load_plugin(self, plugin_name: str, plugin_config: Dict[str, Any]) -> bool:
        """
        加载插件

        Args:
            plugin_name: 插件名称
            plugin_config: 插件配置

        Returns:
            是否加载成功
        """
        if self.plugin_manager:
            return await self.plugin_manager.load_plugin(plugin_name, plugin_config)
        return False
    
    async def reload_plugin(self, plugin_name: str) -> bool:
        """
        重新加载插件

        Args:
            plugin_name: 插件名称

        Returns:
            是否重新加载成功
        """
        if self.plugin_manager:
            return await self.plugin_manager.reload_plugin(plugin_name)
        return False
    
    async def unload_plugin(self, plugin_name: str) -> bool:
        """
        卸载插件

        Args:
            plugin_name: 插件名称

        Returns:
            是否卸载成功
        """
        if self.plugin_manager:
            return await self.plugin_manager.unload_plugin(plugin_name)
        return False
    
    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """
        获取插件信息

        Args:
            plugin_name: 插件名称

        Returns:
            插件信息
        """
        if self.plugin_manager:
            return self.plugin_manager.get_plugin_info(plugin_name)
        return None
    
    def get_all_plugin_info(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有插件信息

        Returns:
            插件信息字典
        """
        if self.plugin_manager:
            return self.plugin_manager.get_all_plugin_info()
        return {}
    
    def get_portfolio_optimizer(self) -> Optional[PortfolioOptimizer]:
        """
        获取策略组合优化器实例

        Returns:
            策略组合优化器实例
        """
        return self.portfolio_optimizer
    
    async def optimize_portfolio(self, optimization_type: str, strategies_data: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
        """
        优化策略组合

        Args:
            optimization_type: 优化类型 (mean_variance, risk_parity, max_sharpe, min_variance)
            strategies_data: 策略数据，包含returns, volatility, correlation

        Returns:
            优化后的权重
        """
        if not self.portfolio_optimizer:
            return {}
        
        # 添加策略到优化器
        for strategy_name, data in strategies_data.items():
            self.portfolio_optimizer.add_strategy(
                strategy_name,
                data['returns'],
                data['volatility'],
                data['correlation']
            )
        
        # 执行优化
        if optimization_type == 'mean_variance':
            return self.portfolio_optimizer.mean_variance_optimization()
        elif optimization_type == 'risk_parity':
            return self.portfolio_optimizer.risk_parity_optimization()
        elif optimization_type == 'max_sharpe':
            return self.portfolio_optimizer.maximum_sharpe_ratio_portfolio()
        elif optimization_type == 'min_variance':
            return self.portfolio_optimizer.minimum_variance_portfolio()
        else:
            return {}
    
    async def get_efficient_frontier(self, strategies_data: Dict[str, Dict[str, Any]], num_points: int = 100) -> pd.DataFrame:
        """
        获取有效前沿

        Args:
            strategies_data: 策略数据
            num_points: 有效前沿上的点数量

        Returns:
            有效前沿数据框
        """
        if not self.portfolio_optimizer:
            return pd.DataFrame()
        
        # 添加策略到优化器
        for strategy_name, data in strategies_data.items():
            self.portfolio_optimizer.add_strategy(
                strategy_name,
                data['returns'],
                data['volatility'],
                data['correlation']
            )
        
        return self.portfolio_optimizer.efficient_frontier(num_points)
    
    def get_parameter_optimizer(self) -> Optional[ParameterOptimizer]:
        """
        获取参数优化器实例

        Returns:
            参数优化器实例
        """
        return self.parameter_optimizer
    
    async def optimize_strategy_parameters(self, strategy_name: str, method: str, 
                                         param_space: Dict[str, Any], 
                                         backtest_data: pd.DataFrame, 
                                         **kwargs) -> Dict[str, Any]:
        """
        优化策略参数

        Args:
            strategy_name: 策略名称
            method: 优化方法
            param_space: 参数空间
            backtest_data: 回测数据
            **kwargs: 额外参数

        Returns:
            优化结果
        """
        if not self.parameter_optimizer or not self.strategy_manager:
            return {}
        
        # 获取策略实例
        strategy = self.strategy_manager.get_strategy(strategy_name)
        if not strategy:
            return {}
        
        # 设置策略到优化器
        self.parameter_optimizer.set_strategy(strategy)
        
        # 执行优化
        return self.parameter_optimizer.optimize(method, param_space, backtest_data, **kwargs)
    
    async def get_optimization_history(self) -> List[Dict[str, Any]]:
        """
        获取优化历史

        Returns:
            优化历史记录
        """
        if not self.parameter_optimizer:
            return []
        return self.parameter_optimizer.get_optimization_history()
    
    def get_enhanced_backtester(self) -> Optional[BacktestEngine]:
        """
        获取增强回测系统实例

        Returns:
            增强回测系统实例
        """
        return self.enhanced_backtester
    
    async def run_multi_strategy_backtest(self, strategies: Dict[str, Any], 
                                         market_data: Dict[str, pd.DataFrame], 
                                         start_date: Optional[datetime] = None, 
                                         end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        运行多策略协同回测

        Args:
            strategies: 策略字典
            market_data: 市场数据
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            回测结果
        """
        if not self.enhanced_backtester:
            return {}
        
        # 添加策略
        for strategy_name, strategy in strategies.items():
            self.enhanced_backtester.add_strategy(strategy_name, strategy)
        
        # 添加市场数据
        for symbol, data in market_data.items():
            self.enhanced_backtester.add_market_data(symbol, data)
        
        # 运行回测
        result = self.enhanced_backtester.run_multi_strategy_backtest(start_date, end_date)
        
        return {
            'total_return': result.total_return,
            'sharpe_ratio': result.sharpe_ratio,
            'max_drawdown': result.max_drawdown,
            'win_rate': result.win_rate,
            'total_trades': result.total_trades,
            'profit_factor': result.profit_factor,
            'calmar_ratio': result.calmar_ratio,
            'sortino_ratio': result.sortino_ratio,
            'trades': result.trades,
            'equity_curve': result.equity_curve.to_dict() if result.equity_curve is not None else {},
            'positions': result.positions
        }
    
    async def run_cross_market_arbitrage_backtest(self, symbol1: str, symbol2: str, 
                                                  market_data: Dict[str, pd.DataFrame], 
                                                  spread_threshold: float = 0.01, 
                                                  start_date: Optional[datetime] = None, 
                                                  end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        运行跨市场套利回测

        Args:
            symbol1: 第一个交易对
            symbol2: 第二个交易对
            market_data: 市场数据
            spread_threshold: 价差阈值
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            回测结果
        """
        if not self.enhanced_backtester:
            return {}
        
        # 添加市场数据
        for symbol, data in market_data.items():
            self.enhanced_backtester.add_market_data(symbol, data)
        
        # 运行回测
        result = self.enhanced_backtester.run_cross_market_arbitrage_backtest(
            symbol1, symbol2, spread_threshold, start_date, end_date
        )
        
        return {
            'total_return': result.total_return,
            'sharpe_ratio': result.sharpe_ratio,
            'max_drawdown': result.max_drawdown,
            'win_rate': result.win_rate,
            'total_trades': result.total_trades,
            'profit_factor': result.profit_factor,
            'calmar_ratio': result.calmar_ratio,
            'sortino_ratio': result.sortino_ratio,
            'trades': result.trades,
            'equity_curve': result.equity_curve.to_dict() if result.equity_curve is not None else {},
            'positions': result.positions
        }
    
    def get_data_storage(self) -> Optional[EnhancedDataStorage]:
        """
        获取增强数据存储系统实例

        Returns:
            增强数据存储系统实例
        """
        return self.data_storage
    
    async def save_market_data(self, symbol: str, data: pd.DataFrame, timeframe: str = "1m") -> bool:
        """
        保存市场数据

        Args:
            symbol: 交易对
            data: 市场数据
            timeframe: 时间周期

        Returns:
            是否保存成功
        """
        if not self.data_storage:
            return False
        return self.data_storage.save_market_data(symbol, data, timeframe)
    
    async def load_market_data(self, symbol: str, start_time: datetime, end_time: datetime, 
                             timeframe: str = "1m") -> pd.DataFrame:
        """
        加载市场数据

        Args:
            symbol: 交易对
            start_time: 开始时间
            end_time: 结束时间
            timeframe: 时间周期

        Returns:
            市场数据
        """
        if not self.data_storage:
            return pd.DataFrame()
        return self.data_storage.load_market_data(symbol, start_time, end_time, timeframe)
    
    async def get_available_symbols(self) -> List[str]:
        """
        获取可用的交易对

        Returns:
            交易对列表
        """
        if not self.data_storage:
            return []
        return self.data_storage.get_available_symbols()
    
    async def get_available_timeframes(self, symbol: str) -> List[str]:
        """
        获取可用的时间周期

        Args:
            symbol: 交易对

        Returns:
            时间周期列表
        """
        if not self.data_storage:
            return []
        return self.data_storage.get_available_timeframes(symbol)
    
    async def get_data_range(self, symbol: str, timeframe: str = "1m") -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        获取数据的时间范围

        Args:
            symbol: 交易对
            timeframe: 时间周期

        Returns:
            (开始时间, 结束时间)
        """
        if not self.data_storage:
            return None, None
        return self.data_storage.get_data_range(symbol, timeframe)
    
    async def delete_market_data(self, symbol: str, timeframe: str = "1m", 
                               start_time: Optional[datetime] = None, 
                               end_time: Optional[datetime] = None) -> bool:
        """
        删除市场数据

        Args:
            symbol: 交易对
            timeframe: 时间周期
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            是否删除成功
        """
        if not self.data_storage:
            return False
        return self.data_storage.delete_market_data(symbol, timeframe, start_time, end_time)
    
    async def optimize_data_storage(self, symbol: str, timeframe: str = "1m") -> bool:
        """
        优化数据存储

        Args:
            symbol: 交易对
            timeframe: 时间周期

        Returns:
            是否优化成功
        """
        if not self.data_storage:
            return False
        return self.data_storage.optimize_storage(symbol, timeframe)
    
    def get_backup_manager(self) -> Optional[DataBackupManager]:
        """
        获取数据备份管理器实例

        Returns:
            数据备份管理器实例
        """
        return self.backup_manager
    
    async def create_backup(self, backup_name: Optional[str] = None, 
                          include_data: bool = True, 
                          include_config: bool = True, 
                          include_logs: bool = False) -> str:
        """
        创建数据备份

        Args:
            backup_name: 备份名称
            include_data: 是否包含数据
            include_config: 是否包含配置
            include_logs: 是否包含日志

        Returns:
            备份文件路径
        """
        if not self.backup_manager:
            return ""
        return await self.backup_manager.create_backup(backup_name, include_data, include_config, include_logs)
    
    async def restore_backup(self, backup_file: str, 
                           restore_data: bool = True, 
                           restore_config: bool = True, 
                           restore_logs: bool = False) -> bool:
        """
        恢复数据备份

        Args:
            backup_file: 备份文件路径
            restore_data: 是否恢复数据
            restore_config: 是否恢复配置
            restore_logs: 是否恢复日志

        Returns:
            是否恢复成功
        """
        if not self.backup_manager:
            return False
        return await self.backup_manager.restore_backup(backup_file, restore_data, restore_config, restore_logs)
    
    async def list_backups(self) -> List[Dict[str, Any]]:
        """
        列出所有备份

        Returns:
            备份列表
        """
        if not self.backup_manager:
            return []
        return await self.backup_manager.list_backups()
    
    async def delete_backup(self, backup_file: str) -> bool:
        """
        删除备份

        Args:
            backup_file: 备份文件路径

        Returns:
            是否删除成功
        """
        if not self.backup_manager:
            return False
        return await self.backup_manager.delete_backup(backup_file)
    
    async def configure_backup(self, config: Dict[str, Any]):
        """
        配置备份设置

        Args:
            config: 备份配置
        """
        if self.backup_manager:
            await self.backup_manager.configure_backup(config)
    
    def get_strategy_evaluator(self) -> Optional[StrategyEvaluator]:
        """
        获取策略评估器实例

        Returns:
            策略评估器实例
        """
        return self.strategy_evaluator
    
    async def evaluate_strategy(self, strategy_name: str, returns: List[float], trades: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        评估策略性能

        Args:
            strategy_name: 策略名称
            returns: 收益数据
            trades: 交易记录

        Returns:
            策略评估报告
        """
        if not self.strategy_evaluator:
            return {}
        
        # 创建临时评估器
        evaluator = StrategyEvaluator(strategy_name)
        evaluator.add_returns(returns)
        if trades:
            for trade in trades:
                evaluator.add_trade(trade)
        
        return evaluator.get_evaluation_report()
    
    async def get_strategy_risk_metrics(self, strategy_name: str, returns: List[float]) -> Dict[str, Any]:
        """
        获取策略风险指标

        Args:
            strategy_name: 策略名称
            returns: 收益数据

        Returns:
            风险指标
        """
        if not self.strategy_evaluator:
            return {}
        
        evaluator = StrategyEvaluator(strategy_name)
        evaluator.add_returns(returns)
        return evaluator.get_risk_metrics()
    
    async def get_strategy_performance_metrics(self, strategy_name: str, returns: List[float]) -> Dict[str, Any]:
        """
        获取策略性能指标

        Args:
            strategy_name: 策略名称
            returns: 收益数据

        Returns:
            性能指标
        """
        if not self.strategy_evaluator:
            return {}
        
        evaluator = StrategyEvaluator(strategy_name)
        evaluator.add_returns(returns)
        return evaluator.get_performance_metrics()
    
    async def get_strategy_trade_metrics(self, strategy_name: str, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        获取策略交易指标

        Args:
            strategy_name: 策略名称
            trades: 交易记录

        Returns:
            交易指标
        """
        if not self.strategy_evaluator:
            return {}
        
        evaluator = StrategyEvaluator(strategy_name)
        for trade in trades:
            evaluator.add_trade(trade)
        return evaluator.get_trade_metrics()
    
    def get_natural_language_interface(self) -> Optional[NaturalLanguageInterface]:
        """
        获取自然语言接口实例

        Returns:
            自然语言接口实例
        """
        return self.natural_language_interface
    
    def get_database_manager(self) -> Optional[DatabaseManager]:
        """
        获取数据库管理器实例

        Returns:
            数据库管理器实例
        """
        return self.database_manager
    
    def get_business_process_manager(self) -> Optional[BusinessProcessManager]:
        """
        获取业务流程管理器实例

        Returns:
            业务流程管理器实例
        """
        return self.business_process_manager
    
    async def process_natural_language_query(self, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        处理自然语言查询

        Args:
            query: 自然语言查询
            context: 上下文信息

        Returns:
            处理结果
        """
        if not self.natural_language_interface:
            return {
                "error": "自然语言接口未初始化",
                "message": "无法处理自然语言查询"
            }
        return await self.natural_language_interface.process_query(query, context)
    
    async def respond_to_natural_language_query(self, query: str, context: Dict[str, Any] = None) -> str:
        """
        处理自然语言查询并生成响应

        Args:
            query: 自然语言查询
            context: 上下文信息

        Returns:
            自然语言响应
        """
        if not self.natural_language_interface:
            return "自然语言接口未初始化，无法处理查询"
        return await self.natural_language_interface.process_and_respond(query, context)
    
    def get_available_commands(self) -> Dict[str, Dict[str, Any]]:
        """
        获取可用的自然语言命令

        Returns:
            可用命令列表
        """
        if not self.natural_language_interface:
            return {}
        return self.natural_language_interface.get_available_commands()
    
    def add_natural_language_command(self, command_name: str, description: str, keywords: list, function: str) -> bool:
        """
        添加新的自然语言命令

        Args:
            command_name: 命令名称
            description: 命令描述
            keywords: 关键词列表
            function: 关联函数

        Returns:
            是否添加成功
        """
        if not self.natural_language_interface:
            return False
        return self.natural_language_interface.add_command(command_name, description, keywords, function)
    
    def remove_natural_language_command(self, command_name: str) -> bool:
        """
        删除自然语言命令

        Args:
            command_name: 命令名称

        Returns:
            是否删除成功
        """
        if not self.natural_language_interface:
            return False
        return self.natural_language_interface.remove_command(command_name)
    
    def get_simulated_market(self) -> Optional[SimulatedMarket]:
        """
        获取模拟交易市场实例

        Returns:
            模拟交易市场实例
        """
        return self.simulated_market
    
    async def start_simulated_market(self):
        """
        启动模拟交易市场
        """
        if self.simulated_market:
            await self.simulated_market.start()
    
    async def stop_simulated_market(self):
        """
        停止模拟交易市场
        """
        if self.simulated_market:
            await self.simulated_market.stop()
    
    def execute_simulated_order(self, symbol: str, side: str, size: float, price: Optional[float] = None) -> Dict[str, Any]:
        """
        在模拟市场中执行订单

        Args:
            symbol: 交易对
            side: 交易方向 (buy/sell)
            size: 交易数量
            price: 交易价格（市价单为None）

        Returns:
            订单执行结果
        """
        if not self.simulated_market:
            return {"error": "模拟市场未初始化"}
        return self.simulated_market.execute_order(symbol, side, size, price)
    
    def get_simulated_market_data(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> pd.DataFrame:
        """
        获取模拟市场的历史数据

        Args:
            symbol: 交易对
            timeframe: 时间周期
            limit: 数据条数

        Returns:
            历史数据DataFrame
        """
        if not self.simulated_market:
            return pd.DataFrame()
        return self.simulated_market.get_historical_data(symbol, timeframe, limit)
    
    def get_simulated_market_state(self) -> Dict[str, Any]:
        """
        获取模拟市场状态

        Returns:
            市场状态
        """
        if not self.simulated_market:
            return {"error": "模拟市场未初始化"}
        return self.simulated_market.get_market_state()
    
    def reset_simulated_market(self):
        """
        重置模拟市场
        """
        if self.simulated_market:
            self.simulated_market.reset()
    
    def set_simulated_market_parameters(self, volatility: Optional[float] = None, trend_strength: Optional[float] = None, 
                                      liquidity: Optional[float] = None, spread: Optional[float] = None):
        """
        设置模拟市场参数

        Args:
            volatility: 波动率
            trend_strength: 趋势强度
            liquidity: 流动性
            spread: 买卖价差
        """
        if self.simulated_market:
            if volatility is not None:
                self.simulated_market.set_volatility(volatility)
            if trend_strength is not None:
                self.simulated_market.set_trend_strength(trend_strength)
            if liquidity is not None:
                self.simulated_market.set_liquidity(liquidity)
            if spread is not None:
                self.simulated_market.set_spread(spread)
    
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
            if hasattr(event, 'type'):
                if event.type == CoreEventType.MODULE_ERROR or event.type == EventType.MODULE_ERROR:
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
            if hasattr(event, 'type'):
                if event.type == CoreEventType.CONFIG_CHANGED or event.type == EventType.CONFIG_CHANGED:
                    # 重新加载配置并通知模块
                    logger.info("配置变更，重新加载系统配置")
                    # 这里可以实现配置热重载逻辑

        # 总是向旧的事件处理器系统注册（用于测试）
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

        # 注册处理器到旧的系统（确保测试通过）
        self.register_event_handler(EventType.SYSTEM_START, old_log_event_handler)
        self.register_event_handler(EventType.SYSTEM_STOP, old_log_event_handler)
        self.register_event_handler(EventType.MODULE_STARTED, old_log_event_handler)
        self.register_event_handler(EventType.MODULE_STOPPED, old_log_event_handler)
        self.register_event_handler(EventType.MODULE_ERROR, old_error_event_handler)
        self.register_event_handler(EventType.CONFIG_CHANGED, old_config_change_handler)
        self.register_event_handler(EventType.ALERT, old_log_event_handler)
        self.register_event_handler(EventType.HEARTBEAT, old_log_event_handler)

        # 注册到增强事件系统（如果可用）
        if self.event_system:
            self.event_system.subscribe(CoreEventType.SYSTEM_START, log_event_handler)
            self.event_system.subscribe(CoreEventType.SYSTEM_STOP, log_event_handler)
            self.event_system.subscribe(CoreEventType.MODULE_STARTED, log_event_handler)
            self.event_system.subscribe(CoreEventType.MODULE_STOPPED, log_event_handler)
            self.event_system.subscribe(CoreEventType.MODULE_ERROR, error_event_handler)
            self.event_system.subscribe(CoreEventType.CONFIG_CHANGED, config_change_handler)
            self.event_system.subscribe(CoreEventType.RISK_ALERT, log_event_handler)


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
                logger.info("MockModule initialized")

            async def start(self):
                logger.info("MockModule started")

            async def stop(self):
                logger.info("MockModule stopped")

            async def cleanup(self):
                logger.info("MockModule cleaned up")

        # 注册模块
        controller.register_module("data_pipeline", MockModule())
        controller.register_module("cache_manager", MockModule(), dependencies=["data_pipeline"])
        controller.register_module(
            "trade_engine", MockModule(), dependencies=["data_pipeline", "cache_manager"]
        )

        # 注册事件处理器
        def custom_event_handler(event: SystemEvent):
            logger.info(f"Custom handler: {event.type.value} - {event.data}")

        controller.register_event_handler(EventType.DATA_RECEIVED, custom_event_handler)
        controller.register_event_handler(EventType.TRADE_SIGNAL, custom_event_handler)

        # 启动系统
        success = await controller.start_system()
        logger.info(f"系统启动: {'成功' if success else '失败'}")

        if success:
            # 运行一段时间
            await asyncio.sleep(5)

            # 获取系统状态
            status = await controller.get_system_status()
            logger.info(f"系统状态: {json.dumps(status, indent=2, default=str)}")

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
