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
import os
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
from src.modules.api.monitoring_api import (
    set_trading_monitor,
    set_anomaly_detector,
    set_enhanced_monitoring,
)
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
from src.modules.simulation.simulation_exchange import SimulationExchange
from src.modules.strategies.strategy_evaluator import StrategyEvaluator

# 导入新增的升级模块
from src.modules.core.dynamic_position_manager import DynamicPositionManager, DynamicPositionConfig
from src.modules.core.correlation_monitor import CorrelationMonitor, CorrelationMonitorConfig
from src.modules.core.strategy_hot_loader import StrategyHotLoader
from src.modules.core.audit_logger import AuditLogger, AuditConfig, AuditEventType, AuditSeverity
from src.modules.monitoring.enhanced_monitoring import EnhancedMonitoringSystem, AlertLevel, AlertChannel

# 导入止盈止损管理模块
from src.modules.core.stop_loss_take_profit import (
    StopLossTakeProfitManager,
    StopLossConfig,
    TakeProfitConfig,
    StopLossTakeProfitOrder,
    StopType,
    TakeProfitType,
    stop_loss_take_profit_config_from_mapping,
)

# 导入执行验证模块
from src.modules.core.execution_verifier import (
    ExecutionVerifier,
    ExecutionConfig,
    ExecutionResult,
    CommandType,
    ExecutionStatus
)

# 导入动态币种筛选器
from src.modules.core.dynamic_symbol_selector import (
    DynamicSymbolSelector,
    DynamicSymbolSelectorConfig,
    SymbolScore,
    SelectionCriteria
)

# 导入智能系统组件
from src.modules.skills import (
    SkillManager,
    SystemDiagnosisSkill,
    PerformanceAnalysisSkill,
    RiskAssessmentSkill,
    OptimizationSkill,
    AutoRepairSkill,
    SystemMaintenanceSkill,
    CodeEditorSkill,
    CodeDeveloperSkill,
    CodeReviewerSkill,
    ExternalResourceSkill,
    WebSearchSkill,
    SelfLearningSkill
)
from src.modules.core.system_stability_analyzer import (
    SystemStabilityAnalyzer,
    StabilityLevel,
    DecisionType
)
from src.modules.core.autonomous_developer import AutonomousDeveloper
from src.modules.core.heartbeat_monitor import HeartbeatMonitor
from src.modules.core.smart_notification import SmartNotificationSystem

# 导入统一信息收集分析管理器
from src.modules.data.unified_info_collector import UnifiedInfoCollector, InfoCollectorConfig
from src.modules.memory.memory_gateway import MemoryGateway
from src.modules.commander_agent import CommanderAgentRuntime, commander_capabilities

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
    _active_instance = None

    def __init__(self, config_manager=None):
        """
        初始化主控制器

        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager
        self._owns_config_manager = False
        MainController._active_instance = self

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
        self._last_strategy_research_at: Optional[datetime] = None
        self._strategy_research_running = False

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
        self.simulation_exchange = None
        self.market_data_exchange = None
        self.execution_exchange = None
        
        # 数据库管理器
        self.database_manager = None

        # 全局风险管理器（单例，供资金管理/交易引擎等复用）
        self.risk_manager = None
        
        # 业务流程管理器
        self.business_process_manager = None
        
        # 全智能AI交易引擎
        self.ai_trading_engine = None
        
        # AI记忆管理器
        self.ai_memory_manager = None
        self.memory_gateway = None
        
        # 内存优化器
        self.memory_optimizer = None
        
        # 智能系统组件
        self.hierarchical_memory = None          # 层次化记忆管理器
        self.skill_manager = None                # 技能管理器
        self.heartbeat_monitor = None            # 心跳监控器
        self.smart_notification = None           # 智能通知系统
        self.stability_analyzer = None           # 系统稳定性分析器
        self.autonomous_developer = None         # 自主开发框架
        
        # 统一系统
        self.unified_memory = None               # 统一记忆系统
        self.unified_data_manager = None         # 统一数据管理器
        self.unified_strategy_system = None      # 统一策略系统
        self.unified_trade_system = None         # 统一交易系统
        self.unified_risk_system = None          # 统一风险系统
        self.unified_info_collector = None       # 统一信息收集器
        self.data_source_hub = None              # 统一数据源中心
        
        # 新增升级模块
        self.dynamic_position_manager = None     # 动态仓位管理器
        self.correlation_monitor = None          # 品种相关性监控器
        self.strategy_hot_loader = None          # 策略热加载器
        self.audit_logger = None                 # 审计日志记录器
        self.enhanced_monitoring = None          # 增强监控系统
        self.stop_loss_manager = None            # 止盈止损管理器
        self.execution_verifier = None           # 执行验证器
        self.execution_gateway = None            # 单一执行出口 (S1)
        self.dynamic_symbol_selector = None      # 动态币种筛选器

        # 默认配置
        self.auto_restart_modules = True
        self.max_restart_attempts = 3
        self.health_check_interval = 30  # 秒
        self.event_history_limit = 1000

        logger.info("主控制器初始化完成")

    @classmethod
    def get_active_instance(cls):
        """Return the latest live MainController instance (best-effort)."""
        return cls._active_instance

    # --- lightweight accessors (reduce attribute coupling) ---
    def get_exchange(self):
        """Best-effort exchange accessor (keeps backward compatibility)."""
        if getattr(self, "okx_exchange", None) is not None:
            return self.okx_exchange
        return getattr(self, "exchange", None)

    def get_llm_integration(self):
        return getattr(self, "llm_integration", None)

    def get_telegram_bot(self):
        return getattr(self, "telegram_bot", None)

    def get_strategy_manager(self):
        return getattr(self, "strategy_manager", None)

    def get_data_integration(self):
        return getattr(self, "data_integration", None)

    def get_third_party_data_integrator(self):
        return getattr(self, "third_party_data_integrator", None)

    def get_onchain_integrator(self):
        return getattr(self, "onchain_integrator", None)

    def get_memory_gateway(self):
        return getattr(self, "memory_gateway", None)

    def get_commander_capabilities(self) -> Dict[str, Any]:
        """司令部能力清单（委托 commander_agent.runtime，与 OpenClaw 回路/子智能体说明对齐）。"""
        return commander_capabilities(self)

    async def get_primary_ai_brain(self):
        """Return the current primary AI brain controller instance."""
        policy = await self._get_ai_brain_policy()
        primary = str(policy.get("primary_controller", "ai_core")).strip().lower()
        if primary == "ai_trading_engine":
            brain = getattr(self, "ai_trading_engine", None)
            if brain:
                return brain
            return getattr(self, "ai_core", None)
        brain = getattr(self, "ai_core", None)
        if brain:
            return brain
        return getattr(self, "ai_trading_engine", None)

    async def process_user_command(self, command: str, source: str = "system") -> Dict[str, Any]:
        """
        Unified communication entrypoint — 委托 `CommanderAgentRuntime`（OpenClaw agent-loop 阶段对齐）。

        重要：主链路须先走「指令执行器」再回退核心大脑；显式子智能体见
        `/司令部子任务:<id>:<正文>`（如 research / chat / executor）。
        """
        if not hasattr(self, "_commander_agent_runtime"):
            self._commander_agent_runtime = CommanderAgentRuntime()
        return await self._commander_agent_runtime.run(self, command, source=source)

    def _deep_merge_dict(self, base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base or {})
        for k, v in (updates or {}).items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = self._deep_merge_dict(merged[k], v)
            else:
                merged[k] = v
        return merged

    async def get_ai_managed_config(self, section: str, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Unified config entrypoint for AI-managed modules."""
        cfg: Dict[str, Any] = dict(defaults or {})
        if self.config_manager:
            try:
                section_cfg = await self.config_manager.get_config(section, {})
                if isinstance(section_cfg, dict):
                    cfg = self._deep_merge_dict(cfg, section_cfg)
            except Exception as e:
                logger.debug(f"读取模块配置失败 [{section}]，使用默认值: {e}")
        return cfg

    async def _get_ai_brain_policy(self) -> Dict[str, Any]:
        return await self.get_ai_managed_config(
            "ai_brain",
            {
                "primary_controller": "ai_core",
                "single_write_owner": "ai_core",
                "enable_secondary_controller": False,
                "enable_autonomous_executor": True,
            },
        )

    async def _start_ai_brain_controllers(self) -> None:
        policy = await self._get_ai_brain_policy()
        primary = str(policy.get("primary_controller", "ai_core")).strip().lower()
        swo = str(policy.get("single_write_owner", primary)).strip().lower()
        enable_secondary = bool(policy.get("enable_secondary_controller", False))

        logger.info(
            "🧭 执行策略(S1): primary=%s single_write_owner=%s secondary=%s",
            primary,
            swo,
            enable_secondary,
        )
        if primary != swo:
            logger.warning(
                "⚠️ primary_controller(%s) 与 single_write_owner(%s) 不一致，请确认配置有意为之",
                primary,
                swo,
            )

        if primary == "ai_trading_engine":
            if self.ai_trading_engine:
                await self.ai_trading_engine.start()
                logger.info("🧠 AI主控已启动: ai_trading_engine")
            if enable_secondary and hasattr(self, "ai_core") and self.ai_core:
                await self.ai_core.start()
                logger.info("🧠 次级AI控制器已启动: ai_core")
            return

        # default primary: ai_core
        if hasattr(self, "ai_core") and self.ai_core:
            await self.ai_core.start()
            logger.info("🧠 AI主控已启动: ai_core")
        if self.ai_trading_engine:
            # 即使在 ai_core 独占写入时，也启动 AITradingEngine 的被动能力：
            # - 风险监控
            # - 账户/持仓同步
            # - 监控与优化循环
            # 其主交易循环仍由 single_write_owner 策略自动抑制，不会与 ai_core 抢写。
            await self.ai_trading_engine.start()
            if enable_secondary:
                logger.info("🧠 次级AI控制器已启动: ai_trading_engine")
            else:
                logger.info("🛡️ AITradingEngine 已以被动监控模式启动（写入权仍受 S1 策略约束）")

    async def _start_ai_autonomous_supervision(self) -> None:
        policy = await self._get_ai_brain_policy()
        if not bool(policy.get("enable_autonomous_executor", True)):
            return
        if hasattr(self, "ai_command_executor") and self.ai_command_executor:
            try:
                await self.ai_command_executor.start_autonomous_work()
                logger.info("🤖 AICommandExecutor 自主监督循环已启动")
            except Exception as e:
                logger.error(f"启动 AICommandExecutor 自主监督失败: {e}")

    async def initialize(self) -> None:
        """
        初始化主控制器

        加载配置，设置事件处理器
        """
        if self._initialized:
            return

        logger.info("初始化主控制器...")

        # 如果未显式传入配置管理器，则创建默认实例，保证可独立初始化（单测/脚本场景）
        if self.config_manager is None:
            from src.modules.core.config_manager import ConfigManager
            self.config_manager = ConfigManager()
            self._owns_config_manager = True
            await self.config_manager.initialize()

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
        
        # 初始化唯一记忆后端（OptimizedMemorySystem）
        from src.modules.core.optimized_memory_system import get_memory_system
        import os

        # Prefer centralized config paths; fallback to env/default.
        cfg_workspace_path = None
        try:
            cfg_workspace_path = await self.config_manager.get_config("paths", "workspace_path", None)
        except Exception:
            cfg_workspace_path = None

        workspace_path = cfg_workspace_path or os.environ.get("WORKSPACE_PATH", "/app/workspace")
        
        optimized_memory = await get_memory_system(workspace_path=workspace_path)
        logger.info("✅ 优化记忆系统初始化完成（唯一后端）")

        # 统一记忆网关（单入口）：结构化记忆可召回，workspace markdown 作为日志层
        self.memory_gateway = await MemoryGateway.create(
            memory_backend=optimized_memory,
            workspace_path=workspace_path,
            config_manager=self.config_manager,
        )

        # 保留现有接口名称，统一指向 MemoryGateway（唯一入口）
        self.unified_memory = self.memory_gateway
        self.ai_memory_manager = self.memory_gateway
        self.hierarchical_memory = self.memory_gateway
        self.memory_optimizer = optimized_memory
        logger.info("✅ 记忆系统已统一：MemoryGateway + OptimizedMemorySystem")
        
        # 初始化统一交易历史服务（新增）
        try:
            from src.modules.core.trade_history_service import TradeHistoryService

            trade_history_base_path = "data/trade_history"
            try:
                trade_history_base_path = await self.config_manager.get_config(
                    "paths", "trade_history_path", trade_history_base_path
                )
            except Exception:
                pass

            self.trade_history_service = TradeHistoryService(
                config={
                    "cache_max_size": 1000,
                    "base_path": trade_history_base_path
                }
            )
            await self.trade_history_service.initialize()
            
            # 连接记忆管理器
            if self.hierarchical_memory:
                await self.trade_history_service.set_memory_manager(self.hierarchical_memory)
                logger.info("✅ 交易历史服务已连接到记忆系统")
            
            logger.info("✅ 统一交易历史服务初始化完成")
        except Exception as e:
            logger.warning(f"⚠️ 交易历史服务初始化失败: {e}")
            self.trade_history_service = None
        
        # 初始化智能系统组件
        try:
            # 层次化记忆管理器已在统一记忆系统中初始化
            logger.info("✅ 层次化记忆管理器已由统一记忆系统管理")
            
            # 初始化技能管理器
            self.skill_manager = SkillManager()
            self.skill_manager.register_skill(SystemDiagnosisSkill())
            self.skill_manager.register_skill(PerformanceAnalysisSkill())
            self.skill_manager.register_skill(RiskAssessmentSkill())
            self.skill_manager.register_skill(OptimizationSkill())
            self.skill_manager.register_skill(AutoRepairSkill())
            self.skill_manager.register_skill(SystemMaintenanceSkill())
            self.skill_manager.register_skill(CodeEditorSkill())
            self.skill_manager.register_skill(CodeDeveloperSkill(config_manager=self.config_manager))
            self.skill_manager.register_skill(CodeReviewerSkill())
            self.skill_manager.register_skill(ExternalResourceSkill())
            self.skill_manager.register_skill(WebSearchSkill())
            self.skill_manager.register_skill(SelfLearningSkill())
            logger.info(f"✅ 技能管理器初始化完成 - 已注册 {len(self.skill_manager.skills)} 个技能")
            
            # 初始化系统稳定性分析器
            self.stability_analyzer = SystemStabilityAnalyzer()
            logger.info("✅ 系统稳定性分析器已初始化")
            
            # 初始化自主开发框架
            self.autonomous_developer = AutonomousDeveloper(config_manager=self.config_manager)
            self.autonomous_developer.set_skills(
                code_editor=self.skill_manager.get_skill("code_editor"),
                code_developer=self.skill_manager.get_skill("code_developer"),
                code_reviewer=self.skill_manager.get_skill("code_reviewer")
            )
            logger.info("✅ 自主开发框架已初始化")
            
            # 初始化智能通知系统
            notification_cfg = {}
            try:
                notification_cfg = await self.config_manager.get_config("notifications", {})
            except Exception:
                notification_cfg = {}
            smart_cfg = notification_cfg.get("smart", {}) if isinstance(notification_cfg, dict) else {}
            self.smart_notification = SmartNotificationSystem(
                send_func=self._send_notification_direct,
                config=smart_cfg,
            )
            logger.info("✅ 智能通知系统初始化完成")
            
        except Exception as e:
            logger.error(f"智能系统组件初始化失败: {e}", exc_info=True)
        
        # 初始化大模型集成系统，使用统一记忆系统
        self.llm_integration = EnhancedLLMIntegration(
            llm_manager=self.enhanced_llm_manager,
            memory_manager=self.ai_memory_manager
        )
        
        # 设置增强记忆系统（用于对话记录）
        if self.ai_memory_manager:
            self.llm_integration.enhanced_memory = self.ai_memory_manager
            logger.info("✅ 增强记忆系统已连接到LLM集成")
        
        # 设置统一记忆系统（增强功能）
        if self.unified_memory:
            self.llm_integration.unified_memory = self.unified_memory

        # 对话记忆条数/Budget 与 memory.context_policy 对齐
        if self.config_manager:
            self.llm_integration.policy_config_manager = self.config_manager
        
        logger.info("大模型集成系统已连接到统一记忆系统")
        
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
        await self.strategy_manager.initialize()
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
        
        # 初始化策略组合优化器，并从策略池预置条目（否则 unified 系统内优化器为空壳）
        self.portfolio_optimizer = PortfolioOptimizer()
        try:
            seeded = self.portfolio_optimizer.seed_from_strategy_manager(self.strategy_manager)
            if seeded:
                logger.info("✅ 组合优化器已从策略池预置 %d 条", seeded)
        except Exception as e:
            logger.warning("⚠️ 组合优化器预置失败: %s", e)
        
        # 初始化参数优化器
        self.parameter_optimizer = ParameterOptimizer()
        
        # 初始化增强回测系统
        self.enhanced_backtester = BacktestEngine()

        # 初始化策略研究流水线（DSL + walk-forward）
        try:
            from src.modules.research.strategy_research_pipeline import StrategyResearchPipeline

            self.strategy_research_pipeline = StrategyResearchPipeline(main_controller=self)
            logger.info("✅ 策略研究流水线已初始化（walk-forward + 门控）")
        except Exception as e:
            self.strategy_research_pipeline = None
            logger.warning(f"⚠️ 策略研究流水线初始化失败: {e}")
        
        # 初始化增强数据存储系统
        self.data_storage = EnhancedDataStorage()
        
        # 初始化数据备份管理器
        self.backup_manager = DataBackupManager()
        # 启动定时备份任务
        self._tasks.append(asyncio.create_task(self.backup_manager.schedule_backup()))
        
        # 初始化策略评估器
        self.strategy_evaluator = StrategyEvaluator("main")
        
        # 初始化自然语言接口（传入main_controller以支持技能包和情感智能）
        self.natural_language_interface = NaturalLanguageInterface(
            self.llm_integration,
            main_controller=self,
            config_manager=self.config_manager,
        )
        
        # 初始化Telegram机器人（仅当有config_manager时）
        if self.config_manager:
            telegram_config = await self.config_manager.get_config("telegram", {})
            logger.info(f"📱 Telegram配置: {telegram_config}")
            
            proxy_config = await self.config_manager.get_config("proxy", {})
            if isinstance(proxy_config, dict) and proxy_config.get("enabled"):
                from src.modules.core.network_env_from_config import (
                    build_proxy_url_from_config,
                )

                purl = build_proxy_url_from_config(proxy_config)
                if purl:
                    telegram_config["proxy"] = purl
                    logger.info("Telegram 使用主配置代理: %s", purl)
            
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
        
        # 初始化模拟合约交易管理器（若任一配置声明 simulation）
        trading_config = await self.config_manager.get_config("trading", {})
        system_config = await self.config_manager.get_config("system", {})
        exchanges_config = await self.config_manager.get_config("exchanges", {})
        top_mode = await self.config_manager.get_config("mode", None)

        is_simulation_mode = (
            str(trading_config.get("mode", "")).lower() == "simulation"
            or str(system_config.get("mode", "")).lower() == "simulation"
            or str(top_mode or "").lower() == "simulation"
            or bool(trading_config.get("paper_trading"))
            or bool(await self.config_manager.get_config("simulation_mode", False))
        )
        use_real_market_data = bool(
            (trading_config.get("simulation", {}) or {}).get("use_real_market_data", False)
            or system_config.get("use_real_market_data", False)
            or bool(await self.config_manager.get_config("use_real_market_data", False))
        )
        use_official_okx_demo = bool(
            (trading_config.get("simulation", {}) or {}).get("use_official_okx_demo", False)
            or system_config.get("use_official_okx_demo", False)
            or bool(await self.config_manager.get_config("use_official_okx_demo", False))
        )

        if is_simulation_mode and (not use_official_okx_demo):
            simulation_config = dict(trading_config.get("simulation", {}) or {})
            mock_exchange_cfg = exchanges_config.get("mock", {}) if isinstance(exchanges_config, dict) else {}
            env_initial_balance = os.getenv("INITIAL_BALANCE")
            resolved_initial_capital = (
                simulation_config.get("initial_capital")
                or simulation_config.get("initial_balance")
                or (mock_exchange_cfg.get("initial_balance") if isinstance(mock_exchange_cfg, dict) else None)
                or env_initial_balance
                or 10000
            )
            simulation_config["initial_capital"] = float(resolved_initial_capital)

            self.contract_simulator = ContractSimulator(simulation_config)
            await self.contract_simulator.initialize()
            self.simulation_exchange = SimulationExchange(
                simulation_config,
                market=self.simulated_market,
                contract_simulator=self.contract_simulator,
            )
            logger.info("模拟合约交易管理器已启动，初始资金=%.2f USDT", simulation_config["initial_capital"])
        else:
            self.contract_simulator = None
            self.simulation_exchange = None
        
        # 初始化数据库管理器
        self.database_manager = DatabaseManager(self.config_manager)
        await self.database_manager.initialize()

        # 风险管理器尽早初始化，避免 IntelligentFundManager 等模块使用「另一套」临时实例
        try:
            from src.modules.core.risk_manager import RiskManager

            self.risk_manager = RiskManager()
            await self.risk_manager.initialize()
            logger.info("✅ 风险管理器已初始化（全局单例）")
        except Exception as e:
            logger.warning(f"⚠️ 风险管理器初始化失败: {e}")
            self.risk_manager = None
        
        # 初始化统一系统
        await self._init_unified_systems()
        
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
            intelligent_monitoring_cfg = await self.get_ai_managed_config("intelligent_monitoring", {})
            self.intelligent_monitoring = IntelligentMonitoringSystem(
                intelligent_monitoring_cfg,
                config_manager=self.config_manager,
            )
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
            if self.risk_manager is None:
                self.risk_manager = RiskManager()
                await self.risk_manager.initialize()
                logger.info("✅ 风险管理器延迟初始化（供资金管理器绑定）")
            self.fund_manager = IntelligentFundManager(
                db_manager=self.database_manager,
                risk_manager=self.risk_manager,
                config=fund_config
            )
            await self.fund_manager.initialize()
            logger.info("✅ 智能资金管理器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 智能资金管理器初始化失败: {e}")
            self.fund_manager = None
        
        # 初始化实时数据采集器
        try:
            from src.modules.data.realtime_data_collector import RealTimeDataCollector
            self.realtime_data_collector = RealTimeDataCollector(
                business_process_manager=self.business_process_manager
            )
            await self.realtime_data_collector.initialize()
            logger.info("✅ 实时数据采集器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 实时数据采集器初始化失败: {e}")
            self.realtime_data_collector = None
        
        # 初始化情感分析器
        try:
            from src.modules.intelligence.sentiment_analyzer import SentimentAnalyzer
            sentiment_config = {
                "sources": ["twitter", "reddit", "news", "telegram"],
                "model_config": {
                    "threshold": 0.3,
                    "window_size": 60,
                    "min_confidence": 0.5
                }
            }
            self.sentiment_analyzer = SentimentAnalyzer(
                db_manager=self.database_manager,
                config=sentiment_config
            )
            await self.sentiment_analyzer.initialize()
            logger.info("✅ 情感分析器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 情感分析器初始化失败: {e}")
            self.sentiment_analyzer = None
        
        # 初始化全智能AI交易引擎
        from src.modules.core.ai_trading_engine import AITradingEngine
        self.ai_trading_engine = AITradingEngine(self)
        await self.ai_trading_engine.initialize()
        logger.info("✅ 全智能AI交易引擎初始化完成")
        
        # 连接交易历史服务到AI交易引擎（新增）
        if self.ai_trading_engine and self.trade_history_service:
            self.ai_trading_engine.trade_history_service = self.trade_history_service
            logger.info("✅ 交易历史服务已连接到AI交易引擎")
        
        # 设置便捷引用（用于AICommandExecutor等模块访问）
        if self.ai_trading_engine and hasattr(self.ai_trading_engine, 'exchange'):
            self.market_data_exchange = self.ai_trading_engine.exchange
            if is_simulation_mode and self.simulation_exchange and use_real_market_data:
                # 混合模式：行情/分析走真实交易所，执行仍走模拟交易所
                self.okx_exchange = self.market_data_exchange
                self.execution_exchange = self.simulation_exchange
                logger.info("✅ 混合模式已启用：真实行情 + 模拟执行")
            elif is_simulation_mode and use_official_okx_demo:
                # 官方模拟盘模式：走 OKX 官方模拟通道（x-simulated-trading: 1）
                self.okx_exchange = self.market_data_exchange
                self.execution_exchange = self.okx_exchange
                logger.info("✅ 官方模拟盘模式：真实行情 + 官方模拟下单（OKX Demo）")
            else:
                self.okx_exchange = self.ai_trading_engine.exchange
                self.execution_exchange = self.okx_exchange
                logger.info("✅ OKX交易所引用已设置")
            if getattr(self, "data_source_hub", None) and hasattr(self.data_source_hub, "bind_main_controller"):
                self.data_source_hub.bind_main_controller(self)

        # S1：单一实盘执行出口（与 ai_brain.single_write_owner 协同）
        try:
            from src.modules.core.execution_gateway import ExecutionGateway

            self.execution_gateway = ExecutionGateway(self)
            _pol = await self._get_ai_brain_policy()
            _swo = str(_pol.get("single_write_owner", "ai_core")).strip().lower()
            logger.info("✅ ExecutionGateway 已就绪 single_write_owner=%s", _swo)
        except Exception as e:
            logger.warning("⚠️ ExecutionGateway 初始化失败: %s", e)
            self.execution_gateway = None
        
        if self.ai_trading_engine and hasattr(self.ai_trading_engine, 'risk_monitor'):
            self.risk_monitor = self.ai_trading_engine.risk_monitor
            logger.info("✅ 风险监控引用已设置")
        
        # 添加历史数据存储引用
        if self.ai_trading_engine and hasattr(self.ai_trading_engine, 'data_storage'):
            self.historical_data_storage = self.ai_trading_engine.data_storage
            logger.info("✅ 历史数据存储引用已设置")
        
        # 添加市场分析器引用
        if self.unified_info_collector and hasattr(self.unified_info_collector, 'market_analyzer'):
            self.market_analyzer = self.unified_info_collector.market_analyzer
            logger.info("✅ 市场分析器引用已设置")
        
        # 添加链上数据集成器引用
        if self.unified_info_collector and hasattr(self.unified_info_collector, 'onchain_integrator'):
            self.onchain_integrator = self.unified_info_collector.onchain_integrator
            logger.info("✅ 链上数据集成器引用已设置")
        
        # 添加回测引擎引用
        if hasattr(self, 'enhanced_backtester') and self.enhanced_backtester:
            self.backtest_engine = self.enhanced_backtester
            logger.info("✅ 回测引擎引用已设置")

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
        
        # 初始化统一信息收集分析管理器（交易对与 trading.symbols / unified_info_collector 对齐）
        try:
            default_uic_symbols = [
                "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
                "XRP/USDT", "ADA/USDT", "DOGE/USDT", "DOT/USDT",
            ]
            uic_yaml: Dict[str, Any] = {}
            uic_symbols: List[str] = []
            if self.config_manager:
                try:
                    uic_yaml = await self.config_manager.get_config(
                        "unified_info_collector", {}
                    ) or {}
                except Exception:
                    uic_yaml = {}
            if not isinstance(uic_yaml, dict):
                uic_yaml = {}
            raw_uic = uic_yaml.get("symbols")
            if isinstance(raw_uic, list) and raw_uic:
                uic_symbols = [str(s) for s in raw_uic if s]
            if not uic_symbols and self.config_manager:
                try:
                    trading_cfg = await self.config_manager.get_config("trading", {}) or {}
                    if isinstance(trading_cfg, dict):
                        ts = trading_cfg.get("symbols")
                        if isinstance(ts, list) and ts:
                            uic_symbols = [str(s) for s in ts if s]
                except Exception:
                    pass
            if not uic_symbols:
                uic_symbols = list(default_uic_symbols)

            ic_extra: Dict[str, Any] = {}
            for k in (
                "enabled",
                "enable_realtime_collection",
                "enable_market_analysis",
                "enable_sentiment_analysis",
                "enable_onchain_analysis",
            ):
                if k in uic_yaml:
                    ic_extra[k] = bool(uic_yaml[k])
            if "update_interval" in uic_yaml:
                try:
                    ic_extra["update_interval"] = float(uic_yaml["update_interval"])
                except (TypeError, ValueError):
                    pass
            if "cache_ttl" in uic_yaml:
                try:
                    ic_extra["cache_ttl"] = int(uic_yaml["cache_ttl"])
                except (TypeError, ValueError):
                    pass
            if "max_cache_size" in uic_yaml:
                try:
                    ic_extra["max_cache_size"] = int(uic_yaml["max_cache_size"])
                except (TypeError, ValueError):
                    pass
            ss = uic_yaml.get("sentiment_sources")
            if isinstance(ss, list) and ss:
                ic_extra["sentiment_sources"] = [str(x) for x in ss if x]

            info_collector_config = InfoCollectorConfig(
                symbols=uic_symbols,
                **ic_extra,
            )
            self.unified_info_collector = UnifiedInfoCollector(
                main_controller=self,
                config=info_collector_config
            )
            await self.unified_info_collector.initialize()
            logger.info("✅ 统一信息收集分析管理器已初始化")

            # 统一信息收集器初始化后，再同步关键分析引用（避免初始化顺序导致引用为空）
            if hasattr(self.unified_info_collector, "market_analyzer"):
                self.market_analyzer = self.unified_info_collector.market_analyzer
                logger.info("✅ 市场分析器引用已同步")
            if hasattr(self.unified_info_collector, "onchain_integrator"):
                self.onchain_integrator = self.unified_info_collector.onchain_integrator
                logger.info("✅ 链上数据集成器引用已同步")
        except Exception as e:
            logger.warning(f"⚠️ 统一信息收集分析管理器初始化失败: {e}")
            self.unified_info_collector = None

        # 初始化统一数据源中心（双渠道）
        try:
            from src.modules.data.data_source_hub import DataSourceHub
            self.data_source_hub = DataSourceHub(self)
            if hasattr(self.data_source_hub, "bind_main_controller"):
                self.data_source_hub.bind_main_controller(self)
            logger.info("✅ 统一数据源中心已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 统一数据源中心初始化失败: {e}")
            self.data_source_hub = None

        # 初始化第三方数据集成器（社交/新闻/恐慌贪婪等）
        try:
            from src.modules.data.third_party_data_integrator import ThirdPartyDataIntegrator
            self.third_party_data_integrator = ThirdPartyDataIntegrator()
            logger.info("✅ 第三方数据集成器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 第三方数据集成器初始化失败: {e}")
            self.third_party_data_integrator = None

        # 初始化外部数据集成（多源冗余/健康报告；供主动性系统与司令部引用）
        try:
            from src.modules.data.data_integration import DataIntegration
            self.data_integration = DataIntegration(
                config={},
                third_party_integrator=getattr(self, "third_party_data_integrator", None),
            )
            # Best-effort: no required sources, but allow future registration.
            try:
                await self.data_integration.initialize_all()
            except Exception:
                pass
            logger.info("✅ DataIntegration 已初始化")
        except Exception as e:
            logger.warning(f"⚠️ DataIntegration 初始化失败: {e}")
            self.data_integration = None

        if self.data_integration and self.ai_trading_engine:
            fusion = getattr(self.ai_trading_engine, "data_fusion", None)
            if fusion is not None and hasattr(fusion, "set_data_integration"):
                try:
                    fusion.set_data_integration(self.data_integration)
                    logger.info("✅ MultiSourceDataFusion 已绑定 DataIntegration")
                except Exception as e:
                    logger.debug("绑定 DataIntegration 到 data_fusion 失败: %s", e)

        # 初始化市场情报汇总引擎（只读：汇总行情/信号，供 ai_core/风控/前端复用）
        try:
            from src.modules.core.market_intelligence_engine import MarketIntelligenceEngine

            mi_cfg = {}
            try:
                mi_cfg = await self.get_ai_managed_config("market_intelligence", {})
            except Exception:
                mi_cfg = {}
            self.market_intelligence = MarketIntelligenceEngine(self, mi_cfg)
            await self.market_intelligence.initialize()
            await self.market_intelligence.start()
            # Alias for callers expecting market_intelligence_engine name.
            self.market_intelligence_engine = self.market_intelligence
            logger.info("✅ MarketIntelligenceEngine 已启动")
        except Exception as e:
            logger.warning("⚠️ MarketIntelligenceEngine 初始化失败: %s", e)
            self.market_intelligence = None
            self.market_intelligence_engine = None
        
        # 初始化缓存管理器
        try:
            from src.modules.core.cache_manager import CacheManager
            self.cache_manager = CacheManager()
            await self.cache_manager.initialize()
            logger.info("✅ 缓存管理器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 缓存管理器初始化失败: {e}")
            self.cache_manager = None
        
        # 初始化日志管理器
        try:
            from src.modules.core.log_manager import LogManager
            self.log_manager = LogManager()
            await self.log_manager.initialize()
            logger.info("✅ 日志管理器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 日志管理器初始化失败: {e}")
            self.log_manager = None
        
        # 初始化系统监控器
        try:
            from src.modules.core.system_monitor import SystemMonitor
            system_monitor_cfg = await self.get_ai_managed_config("system_monitor", {})
            self.system_monitor = SystemMonitor(
                system_monitor_cfg,
                config_manager=self.config_manager,
            )
            await self.system_monitor.initialize()
            logger.info("✅ 系统监控器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 系统监控器初始化失败: {e}")
        
        # 初始化性能监控器
        try:
            from src.modules.core.performance_monitor import performance_monitor
            self.performance_monitor = performance_monitor
            
            async def on_performance_alert(alert):
                if self.telegram_bot:
                    level_emoji = "⚠️" if alert.get("level") == "warning" else "🚨"
                    await self.telegram_bot.send_message(
                        f"{level_emoji} 性能告警\n\n{alert.get('message', '未知告警')}"
                    )
            
            self.performance_monitor.add_alert_callback(on_performance_alert)
            logger.info("✅ 性能监控器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 性能监控器初始化失败: {e}")
            self.system_monitor = None
        
        # 初始化主动性AI系统
        try:
            from src.modules.core.proactive_ai_system import ProactiveAIOrchestrator
            proactive_defaults = {
                "scan_interval": 30,
                "deep_scan_interval": 300,
                "collect_interval": 300,
                "action_cooldown": 60
            }
            # 配置优先级：
            # 1) ai_managed_config("proactive_ai") 作为运行期可调覆盖
            # 2) config.yaml 的 proactive_scanner 作为基准（包含 auto_execute 等关键开关）
            # 3) proactive_defaults 兜底
            file_cfg = {}
            try:
                if self.config_manager:
                    file_cfg = await self.config_manager.get_config("proactive_scanner", {}) or {}
            except Exception:
                file_cfg = {}
            proactive_cfg = await self.get_ai_managed_config(
                "proactive_ai",
                {**proactive_defaults, **(file_cfg if isinstance(file_cfg, dict) else {})},
            )
            if isinstance(file_cfg, dict):
                # 确保 file_cfg 的关键字段不会被 defaults 盖掉（但仍允许 ai_managed 覆盖）
                proactive_cfg = {**file_cfg, **(proactive_cfg if isinstance(proactive_cfg, dict) else {})}
            self.proactive_ai = ProactiveAIOrchestrator(
                self,
                proactive_cfg,
                config_manager=self.config_manager,
            )
            await self.proactive_ai.initialize()
            logger.info("✅ 主动性AI系统已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 主动性AI系统初始化失败: {e}")
            self.proactive_ai = None
        
        # 风险管理器已在数据库初始化后创建；此处仅补登（防止早期路径被跳过）
        if self.risk_manager is None:
            try:
                from src.modules.core.risk_manager import RiskManager

                self.risk_manager = RiskManager()
                await self.risk_manager.initialize()
                logger.info("✅ 风险管理器已初始化（补登）")
            except Exception as e:
                logger.warning(f"⚠️ 风险管理器初始化失败: {e}")
                self.risk_manager = None
        
        # ========== 新增升级模块初始化 ==========
        
        # 初始化动态仓位管理器
        try:
            position_config = DynamicPositionConfig(
                base_position_ratio=0.1,
                max_position_ratio=0.3,
                max_total_position_ratio=0.8
            )
            self.dynamic_position_manager = DynamicPositionManager(position_config)
            await self.dynamic_position_manager.initialize()
            logger.info("✅ 动态仓位管理器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 动态仓位管理器初始化失败: {e}")
            self.dynamic_position_manager = None
        
        # 初始化品种相关性监控器
        try:
            correlation_config = CorrelationMonitorConfig(
                correlation_threshold_high=0.7,
                lookback_periods=30
            )
            self.correlation_monitor = CorrelationMonitor(correlation_config)
            await self.correlation_monitor.initialize()
            
            # 注册相关性预警回调
            async def on_correlation_alert(alert):
                if self.telegram_bot:
                    await self.telegram_bot.send_message(
                        f"📊 相关性预警\n\n{alert.message}"
                    )
            self.correlation_monitor.register_callback(on_correlation_alert)
            logger.info("✅ 品种相关性监控器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 品种相关性监控器初始化失败: {e}")
            self.correlation_monitor = None
        
        # 初始化审计日志记录器（必须在其他模块之前初始化）
        try:
            audit_config = AuditConfig(
                log_dir="logs/audit",
                retention_days=90
            )
            self.audit_logger = AuditLogger(audit_config)
            await self.audit_logger.initialize()
            logger.info("✅ 审计日志记录器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 审计日志记录器初始化失败: {e}")
            self.audit_logger = None
        
        # 初始化策略热加载器
        try:
            self.strategy_hot_loader = StrategyHotLoader()
            await self.strategy_hot_loader.initialize()
            
            # 注册策略加载回调
            async def on_strategy_load(strategy_name, instance):
                if self.audit_logger:
                    await self.audit_logger.log_event(
                        AuditEventType.STRATEGY_LOAD,
                        AuditSeverity.INFO,
                        f"策略加载: {strategy_name}",
                        {"version": instance.version.version_id}
                    )
            self.strategy_hot_loader.register_callback("on_load", on_strategy_load)
            logger.info("✅ 策略热加载器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 策略热加载器初始化失败: {e}")
            self.strategy_hot_loader = None
        
        # 初始化增强监控系统
        try:
            enhanced_monitoring_cfg = await self.get_ai_managed_config("enhanced_monitoring", {})
            self.enhanced_monitoring = EnhancedMonitoringSystem(
                enhanced_monitoring_cfg,
                config_manager=self.config_manager,
            )
            await self.enhanced_monitoring.initialize()
            
            # 设置Telegram机器人
            if self.telegram_bot:
                self.enhanced_monitoring.set_telegram_bot(self.telegram_bot)
            
            # 注册报警回调
            async def on_alert(alert):
                if self.audit_logger:
                    await self.audit_logger.log_risk_alert(
                        alert.rule.name,
                        alert.message,
                        {"metric": alert.rule.metric, "value": alert.metric_value},
                        AuditSeverity.WARNING if alert.level == AlertLevel.WARNING else AuditSeverity.ERROR
                    )
            self.enhanced_monitoring.register_callback("on_alert", on_alert)
            logger.info("✅ 增强监控系统已初始化")
            set_enhanced_monitoring(self.enhanced_monitoring)
        except Exception as e:
            logger.warning(f"⚠️ 增强监控系统初始化失败: {e}")
            self.enhanced_monitoring = None
            set_enhanced_monitoring(None)
        
        # 初始化止盈止损管理器（配置来自 openclaw.embedded.yml / 磁盘 openclaw.yml / local.* / 环境变量）
        try:
            sltp_raw = await self.config_manager.get_config("stop_loss_take_profit", {}) or {}
            if not isinstance(sltp_raw, dict):
                sltp_raw = {}
            strat_raw = await self.config_manager.get_config("strategy", {}) or {}
            if not isinstance(strat_raw, dict):
                strat_raw = {}
            sltp_config = stop_loss_take_profit_config_from_mapping(
                sltp_raw, strategy_section=strat_raw
            )
            logger.info(
                "止盈止损配置来源=config_manager trailing_only_mode=%s initial=%.4f tier2_thr=%.4f execute_exchange=%s",
                sltp_config.trailing_only_mode,
                sltp_config.initial_trailing_offset,
                sltp_config.profit_tier2_pnl_threshold,
                sltp_config.execute_exchange_on_trigger,
            )
            self.stop_loss_manager = StopLossTakeProfitManager(sltp_config)
            self.stop_loss_manager.set_main_controller(self)
            await self.stop_loss_manager.initialize()
            
            # 设置关联组件
            if self.audit_logger:
                self.stop_loss_manager.set_audit_logger(self.audit_logger)
            if self.enhanced_monitoring:
                self.stop_loss_manager.set_enhanced_monitoring(self.enhanced_monitoring)
            
            # 注册止盈止损回调
            async def on_stop_loss_trigger(order, current_price):
                logger.warning(f"🚨 止损触发: {order.symbol} @ {current_price}")
                if self.telegram_bot:
                    pnl_percent = (current_price - order.entry_price) / order.entry_price if order.side == "long" \
                                  else (order.entry_price - current_price) / order.entry_price
                    await self.telegram_bot.send_message(
                        f"🚨 止损触发\n\n"
                        f"交易对: {order.symbol}\n"
                        f"方向: {order.side}\n"
                        f"入场价: {order.entry_price:.4f}\n"
                        f"止损价: {order.stop_loss_price:.4f}\n"
                        f"当前价: {current_price:.4f}\n"
                        f"亏损: {pnl_percent*100:.2f}%"
                    )
            
            async def on_take_profit_trigger(order, current_price):
                logger.info(f"🎯 止盈触发: {order.symbol} @ {current_price}")
                if self.telegram_bot:
                    pnl_percent = (current_price - order.entry_price) / order.entry_price if order.side == "long" \
                                  else (order.entry_price - current_price) / order.entry_price
                    await self.telegram_bot.send_message(
                        f"🎯 止盈触发\n\n"
                        f"交易对: {order.symbol}\n"
                        f"方向: {order.side}\n"
                        f"入场价: {order.entry_price:.4f}\n"
                        f"止盈价: {order.take_profit_price:.4f}\n"
                        f"当前价: {current_price:.4f}\n"
                        f"盈利: {pnl_percent*100:.2f}%"
                    )
            
            self.stop_loss_manager.register_callback("on_stop_loss", on_stop_loss_trigger)
            self.stop_loss_manager.register_callback("on_take_profit", on_take_profit_trigger)
            
            logger.info("✅ 止盈止损管理器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 止盈止损管理器初始化失败: {e}")
            self.stop_loss_manager = None
        
        # 初始化执行验证器
        try:
            exec_config = ExecutionConfig(
                timeout_seconds=30,
                max_retries=3,
                enable_verification=True
            )
            self.execution_verifier = ExecutionVerifier(exec_config)
            
            # 设置关联组件
            if hasattr(self, 'okx_exchange') and self.okx_exchange:
                self.execution_verifier.set_exchange(self.okx_exchange)
            if self.audit_logger:
                self.execution_verifier.set_audit_logger(self.audit_logger)
            if self.stop_loss_manager:
                self.execution_verifier.set_stop_loss_manager(self.stop_loss_manager)
            self.execution_verifier.set_main_controller(self)
            
            logger.info("✅ 执行验证器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 执行验证器初始化失败: {e}")
            self.execution_verifier = None
        
        # 初始化动态币种筛选器（参数来自 trading / trading.contract）
        try:
            trading_cfg = await self.config_manager.get_config("trading", {}) or {}
            contract = (
                trading_cfg.get("contract") if isinstance(trading_cfg.get("contract"), dict) else {}
            )
            dyn = (
                trading_cfg.get("dynamic_symbols")
                if isinstance(trading_cfg.get("dynamic_symbols"), dict)
                else {}
            )
            su = str(contract.get("symbol_universe", "full_exchange") or "full_exchange").lower()
            restricted = su in ("whitelist", "restricted", "list")
            allowed = contract.get("allowed_symbols")
            if not isinstance(allowed, list) or not allowed:
                allowed = trading_cfg.get("symbols") or []
            base_include = dyn.get("always_include")
            if not isinstance(base_include, list) or not base_include:
                base_include = trading_cfg.get("symbols") or ["BTC/USDT", "ETH/USDT"]
            selector_config = DynamicSymbolSelectorConfig(
                max_symbols=int(dyn.get("max_symbols", 12) or 12),
                min_symbols=int(dyn.get("min_symbols", 2) or 2),
                selection_interval=int(
                    dyn.get("selection_interval", 300) or 300
                ),
                min_24h_volume=float(dyn.get("min_24h_volume", 10_000_000) or 10_000_000),
                enable_auto_discovery=bool(dyn.get("enable_auto_discovery", True)),
                always_include=[str(x) for x in base_include if x],
                always_exclude=[str(x) for x in (dyn.get("always_exclude") or []) if x],
                restricted_universe=restricted,
                allowed_symbols=[str(x) for x in allowed if x] if restricted else [],
            )
            self.dynamic_symbol_selector = DynamicSymbolSelector(selector_config)
            await self.dynamic_symbol_selector.initialize()
            
            # 设置交易所
            if hasattr(self, 'okx_exchange') and self.okx_exchange:
                self.dynamic_symbol_selector.set_exchange(self.okx_exchange)
            await self.dynamic_symbol_selector.start()
            
            logger.info("✅ 动态币种筛选器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 动态币种筛选器初始化失败: {e}")
            self.dynamic_symbol_selector = None
        
        # 初始化API服务器
        try:
            from src.modules.api.server import APIServer
            self.api_server = APIServer(main_controller=self)
            await self.api_server.initialize()
            logger.info("✅ API服务器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ API服务器初始化失败: {e}")
            self.api_server = None

        # 交易事件中枢（Intent/Fill/Position）：向前端 WS 与 TG 预留统一出口
        try:
            if self.event_system:
                from src.modules.core.trade_event_hub import TradeEventHub

                self.trade_event_hub = TradeEventHub(
                    self.event_system,
                    api_server=self.api_server,
                    telegram_bot=None,
                    notify_fn=self._send_notification_handler,
                    buffer_size=800,
                    tg_enabled=True,
                    tg_min_interval_sec=2.0,
                )
                logger.info("✅ TradeEventHub 已初始化")
        except Exception as e:
            logger.warning("⚠️ TradeEventHub 初始化失败: %s", e)
            self.trade_event_hub = None

        # 注册默认事件处理器
        self._register_default_handlers()

        # 启动事件处理任务
        self._running = True
        self._tasks.append(asyncio.create_task(self._health_check_worker()))
        self._tasks.append(asyncio.create_task(self._strategy_research_worker()))

        self._initialized = True
        logger.info("主控制器初始化完成")

    async def _init_unified_systems(self):
        """初始化统一系统"""
        try:
            logger.info("🔧 初始化统一系统...")
            
            # 初始化统一数据管理器（复用已存在的组件）
            try:
                from src.modules.data.unified_data_manager import UnifiedDataManager
                unified_data_cfg = await self.get_ai_managed_config("unified_data_manager", {})
                self.unified_data_manager = UnifiedDataManager(
                    unified_data_cfg,
                    config_manager=self.config_manager,
                )
                # 复用已初始化的组件
                if self.data_storage:
                    self.unified_data_manager.storage = self.data_storage
                if self.backup_manager:
                    self.unified_data_manager.backup = self.backup_manager
                await self.unified_data_manager.initialize()
                logger.info("✅ 统一数据管理器已初始化（复用现有组件）")
            except Exception as e:
                logger.warning(f"⚠️ 统一数据管理器初始化失败: {e}")
                self.unified_data_manager = None
            
            # 初始化统一策略系统（复用已存在的组件）
            try:
                from src.modules.strategies.unified_strategy_system import UnifiedStrategySystem
                unified_strategy_cfg = await self.get_ai_managed_config("unified_strategy_system", {})
                self.unified_strategy_system = UnifiedStrategySystem(
                    unified_strategy_cfg,
                    config_manager=self.config_manager,
                )
                # 复用已初始化的组件
                if self.strategy_manager:
                    self.unified_strategy_system.manager = self.strategy_manager
                if self.strategy_evaluator:
                    self.unified_strategy_system.evaluator = self.strategy_evaluator
                if self.portfolio_optimizer:
                    if self.unified_strategy_system.optimizer:
                        self.unified_strategy_system.optimizer["portfolio"] = self.portfolio_optimizer
                if self.parameter_optimizer:
                    if self.unified_strategy_system.optimizer:
                        self.unified_strategy_system.optimizer["parameter"] = self.parameter_optimizer
                if self.enhanced_backtester:
                    self.unified_strategy_system.backtester = self.enhanced_backtester
                await self.unified_strategy_system.initialize()
                logger.info("✅ 统一策略系统已初始化（复用现有组件）")
            except Exception as e:
                logger.warning(f"⚠️ 统一策略系统初始化失败: {e}")
                self.unified_strategy_system = None
            
            # 初始化统一交易系统
            try:
                from src.modules.trading.unified_trade_system import UnifiedTradeSystem
                unified_trade_cfg = await self.get_ai_managed_config("unified_trade_system", {})
                self.unified_trade_system = UnifiedTradeSystem(
                    unified_trade_cfg,
                    config_manager=self.config_manager,
                )
                # 复用已初始化的组件
                if self.trading_monitor:
                    self.unified_trade_system.monitor = self.trading_monitor
                if self.simulation_exchange:
                    self.unified_trade_system.set_execution_backend(self.simulation_exchange)
                await self.unified_trade_system.initialize()
                logger.info("✅ 统一交易系统已初始化（复用现有组件）")
            except Exception as e:
                logger.warning(f"⚠️ 统一交易系统初始化失败: {e}")
                self.unified_trade_system = None
            
            # 初始化统一风险系统
            try:
                from src.modules.risk.unified_risk_system import UnifiedRiskSystem
                unified_risk_cfg = await self.get_ai_managed_config("unified_risk_system", {})
                self.unified_risk_system = UnifiedRiskSystem(
                    unified_risk_cfg,
                    config_manager=self.config_manager,
                )
                # 复用已初始化的组件
                if hasattr(self, 'intelligent_monitoring') and self.intelligent_monitoring:
                    self.unified_risk_system.monitor = self.intelligent_monitoring
                if hasattr(self, 'portfolio_optimizer') and self.portfolio_optimizer:
                    self.unified_risk_system.optimizer = self.portfolio_optimizer
                await self.unified_risk_system.initialize()
                logger.info("✅ 统一风险系统已初始化（复用现有组件）")
            except Exception as e:
                logger.warning(f"⚠️ 统一风险系统初始化失败: {e}")
                self.unified_risk_system = None
            
            logger.info("✅ 统一系统初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 统一系统初始化失败: {e}")

    async def cleanup(self) -> None:
        """
        清理主控制器

        停止所有模块，清理资源
        """
        logger.info("清理主控制器...")

        self._running = False

        # 停止所有模块
        await self.stop_all_modules()
        if getattr(self, "dynamic_symbol_selector", None):
            try:
                await self.dynamic_symbol_selector.stop()
            except Exception:
                pass

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
            
        # 清理统一系统
        if hasattr(self, 'unified_data_manager') and self.unified_data_manager:
            await self.unified_data_manager.cleanup()
            self.unified_data_manager = None
        
        if hasattr(self, 'unified_strategy_system') and self.unified_strategy_system:
            await self.unified_strategy_system.cleanup()
            self.unified_strategy_system = None
        
        if hasattr(self, 'unified_trade_system') and self.unified_trade_system:
            await self.unified_trade_system.cleanup()
            self.unified_trade_system = None
        
        if hasattr(self, 'unified_risk_system') and self.unified_risk_system:
            await self.unified_risk_system.cleanup()
            self.unified_risk_system = None
        
        # 清理新增升级模块
        if hasattr(self, 'dynamic_position_manager') and self.dynamic_position_manager:
            await self.dynamic_position_manager.cleanup()
            self.dynamic_position_manager = None
        
        if hasattr(self, 'correlation_monitor') and self.correlation_monitor:
            await self.correlation_monitor.cleanup()
            self.correlation_monitor = None
        
        if hasattr(self, 'strategy_hot_loader') and self.strategy_hot_loader:
            await self.strategy_hot_loader.cleanup()
            self.strategy_hot_loader = None
        
        if hasattr(self, 'audit_logger') and self.audit_logger:
            await self.audit_logger.cleanup()
            self.audit_logger = None
        
        if hasattr(self, 'enhanced_monitoring') and self.enhanced_monitoring:
            await self.enhanced_monitoring.cleanup()
            set_enhanced_monitoring(None)
            self.enhanced_monitoring = None
        
        # 清理止盈止损管理器
        if hasattr(self, 'stop_loss_manager') and self.stop_loss_manager:
            await self.stop_loss_manager.cleanup()
            self.stop_loss_manager = None
            
        self._initialized = False

        # 清理默认创建的配置管理器
        if getattr(self, "_owns_config_manager", False) and self.config_manager:
            try:
                await self.config_manager.cleanup()
            except Exception:
                pass
            self.config_manager = None
            self._owns_config_manager = False

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
            # 勿在持锁期间 await 长任务：否则 get_system_status / acceptance 等会与启动串行抢同一把锁而长时间无响应。
            async with self._lock:
                if self.system_status == ModuleStatus.RUNNING:
                    logger.warning("系统已经在运行")
                    return True
                self.system_status = ModuleStatus.STARTING
                self.start_time = datetime.now()
                self.stop_time = None

            # 发送系统启动事件
            await self.emit_event(
                EventType.SYSTEM_START, "controller", {"timestamp": self.start_time.isoformat()}
            )

            # 按依赖顺序启动模块
            success = await self._start_modules_in_order()

            if not success:
                async with self._lock:
                    self.system_status = ModuleStatus.ERROR
                logger.error("系统启动失败")
                return False

            async with self._lock:
                self.system_status = ModuleStatus.RUNNING
                self._running = True
            logger.info("系统启动成功")

            # 验证关键模块连接状态
            await self._verify_module_connections()

            # 启动AI核心控制器（单脑仲裁，避免双控制器并行下单）
            await self._start_ai_brain_controllers()
            await self._start_ai_autonomous_supervision()

            # 重启动后的强制接管：同步余额/持仓，并把持仓接入 SLTP 跟踪与仓位管理。
            try:
                # OKX REST 在网络抖动时可能长时间阻塞；启动链路不能被这一步卡死
                await asyncio.wait_for(self.force_sync_account_state(reason="startup"), timeout=12.0)
            except Exception as e:
                logger.warning(f"⚠️ 启动同步余额/持仓失败（不阻塞启动）: {e}")

            # 启动主动性AI系统 - 让AI主动工作
            if self.proactive_ai:
                try:
                    await self.proactive_ai.start()
                    logger.info("🚀 主动性AI系统已启动 - AI将主动扫描市场、分析信息、执行交易")
                except Exception as e:
                    logger.error(f"❌ 主动性AI系统启动失败: {e}")

            # 启动止盈止损监控
            await self.start_stop_loss_monitoring()

            # 启动心跳监控器
            if not self.heartbeat_monitor and self.ai_trading_engine and self.skill_manager:
                try:
                    hb_cfg = {}
                    try:
                        hb_cfg = await self.config_manager.get_config("heartbeat", {}) if self.config_manager else {}
                    except Exception:
                        hb_cfg = {}
                    self.heartbeat_monitor = HeartbeatMonitor(
                        trading_engine=self.ai_trading_engine,
                        skill_manager=self.skill_manager,
                        memory_manager=self.hierarchical_memory,
                        notification_handler=self._send_notification_handler,
                        interval=int(hb_cfg.get("interval_sec", 1800)) if isinstance(hb_cfg, dict) else 1800,
                        config_manager=self.config_manager,
                    )
                    if isinstance(hb_cfg, dict):
                        try:
                            self.heartbeat_monitor.market_opportunity_cooldown_sec = int(
                                hb_cfg.get("market_opportunity_notice_cooldown_sec", 21600)
                            )
                            self.heartbeat_monitor.market_opportunity_notice_enabled = bool(
                                hb_cfg.get("market_opportunity_notice_enabled", False)
                            )
                        except Exception:
                            pass
                    logger.info("✅ 心跳监控器已初始化")
                except Exception as e:
                    logger.error(f"心跳监控器初始化失败: {e}")

            # 启动心跳监控任务
            if self.heartbeat_monitor:
                try:
                    heartbeat_task = asyncio.create_task(self.heartbeat_monitor.start())
                    self._tasks.append(heartbeat_task)
                    logger.info("💓 心跳监控器已启动 - 主动式系统监控")
                except Exception as e:
                    logger.error(f"心跳监控器启动失败: {e}")

            # 发送心跳事件
            await self.emit_event(
                EventType.HEARTBEAT, "controller", {"status": "running", "uptime": 0}
            )

            return True

        except Exception as e:
            async with self._lock:
                self.system_status = ModuleStatus.ERROR
            logger.error(f"系统启动异常: {e}")
            traceback.print_exc()
            return False

    async def force_sync_account_state(self, reason: str = "manual") -> Dict[str, Any]:
        """
        强制同步并接管交易现场数据：
        - 钱包余额（USDT 等）
        - 持仓（用于司令部快照、SLTP 跟踪、动态仓位管理）
        """
        out: Dict[str, Any] = {"reason": reason, "timestamp": datetime.now().isoformat(), "balance": None, "positions": None}
        ex = self.get_exchange() if hasattr(self, "get_exchange") else None
        ex = ex or getattr(self, "okx_exchange", None)
        if not ex:
            out["error"] = "exchange_missing"
            return out

        try:
            inv = getattr(ex, "invalidate_account_caches", None)
            if callable(inv):
                inv()
        except Exception:
            pass

        # 1) balance（可用余额简表 + 明细）
        try:
            bal = await ex.get_balance()
            out["balance"] = bal
            if hasattr(ex, "get_balances"):
                rows = await ex.get_balances()
                details = []
                usdt_free = 0.0
                usdt_total = 0.0
                for b in rows or []:
                    try:
                        asset = str(getattr(b, "asset", "") or "")
                        free_v = float(getattr(b, "free", 0.0) or 0.0)
                        total_v = float(getattr(b, "total", 0.0) or 0.0)
                    except Exception:
                        continue
                    if not asset:
                        continue
                    details.append({"asset": asset, "free": free_v, "total": total_v})
                    if asset.upper() == "USDT":
                        usdt_free = free_v
                        usdt_total = total_v
                out["balance_details"] = details
                out["balance_detail_count"] = len(details)
                out["usdt_free"] = usdt_free
                out["usdt_total"] = usdt_total
        except Exception as e:
            out["balance_error"] = str(e)

        # 2) positions
        try:
            pos = await ex.get_positions()
            out["positions"] = pos
        except Exception as e:
            out["positions_error"] = str(e)

        # 缓存到控制器，供快照/指挥台复用
        self._latest_account_state = out

        # 3) 写入记忆，便于 AI 复盘与持续接管
        gw = getattr(self, "memory_gateway", None)
        if gw and hasattr(gw, "add_memory"):
            try:
                await gw.add_memory(
                    memory_type="trade_record",
                    content=f"重启/同步接管({reason})：余额与持仓已同步。",
                    summary="系统重启后强制同步余额/持仓",
                    metadata={"reason": reason, "balance": out.get("balance"), "positions": out.get("positions")},
                    source_module="main_controller",
                    importance=0.75,
                )
            except Exception:
                pass

        # 4) SLTP 接管：把交易所持仓同步到 SLTP 跟踪
        try:
            if getattr(self, "stop_loss_manager", None):
                if getattr(self, "okx_exchange", None):
                    self.stop_loss_manager.set_exchange(self.okx_exchange)
                out["sltp_sync"] = await self.stop_loss_manager.sync_open_positions_from_exchange()
        except Exception as e:
            out["sltp_sync_error"] = str(e)

        # 5) 可观测性：非零持仓数量（原始 API 解析后）
        try:
            raw = out.get("positions")
            if isinstance(raw, list):
                nz = 0
                for p in raw:
                    if not isinstance(p, dict):
                        continue
                    try:
                        sz = float(p.get("pos", p.get("size", 0)) or 0)
                    except (TypeError, ValueError):
                        sz = 0.0
                    if abs(sz) > 1e-12:
                        nz += 1
                out["nonzero_position_count"] = nz
        except Exception:
            pass

        return out

    async def get_account_sync_diagnostics(self) -> Dict[str, Any]:
        """
        排查「交易所 ↔ 系统」持仓/余额是否一致：
        数据来源均为实时接口 + 本地 SLTP 状态，不依赖本机成交记录笔数。
        """
        diag: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "exchange": None,
            "balance_error": None,
            "positions_error": None,
            "nonzero_positions": 0,
            "position_samples": [],
            "account_config": None,
            "sltp": None,
            "sltp_config": None,
            "latest_cache": getattr(self, "_latest_account_state", None),
        }
        ex = self.get_exchange() if hasattr(self, "get_exchange") else None
        ex = ex or getattr(self, "okx_exchange", None)
        if not ex:
            diag["exchange"] = "missing"
            return diag
        diag["exchange"] = type(ex).__name__

        try:
            inv = getattr(ex, "invalidate_account_caches", None)
            if callable(inv):
                inv()
        except Exception:
            pass

        try:
            req = getattr(ex, "_make_request", None)
            if callable(req):
                cfg_rows = await req("GET", "/api/v5/account/config")
                if isinstance(cfg_rows, list) and cfg_rows:
                    row = cfg_rows[0] if isinstance(cfg_rows[0], dict) else {}
                    diag["account_config"] = {
                        "uid": row.get("uid"),
                        "mainUid": row.get("mainUid"),
                        "acctLv": row.get("acctLv"),
                        "posMode": row.get("posMode"),
                        "perm": row.get("perm"),
                        "level": row.get("level"),
                    }
        except Exception as e:
            diag["account_config_error"] = str(e)

        try:
            bal = await ex.get_balance()
            diag["balance_keys"] = list(bal.keys())[:20] if isinstance(bal, dict) else str(type(bal))
            if hasattr(ex, "get_balances"):
                rows = await ex.get_balances()
                usdt_row = None
                for b in rows or []:
                    try:
                        if str(getattr(b, "asset", "") or "").upper() == "USDT":
                            usdt_row = {
                                "free": float(getattr(b, "free", 0.0) or 0.0),
                                "total": float(getattr(b, "total", 0.0) or 0.0),
                            }
                            break
                    except Exception:
                        continue
                diag["balance_detail_count"] = len(rows or [])
                diag["usdt_balance"] = usdt_row or {"free": 0.0, "total": 0.0}
        except Exception as e:
            diag["balance_error"] = str(e)

        try:
            pos = await ex.get_positions()
            nz = []
            for p in pos or []:
                if not isinstance(p, dict):
                    continue
                try:
                    sz = float(p.get("pos", p.get("size", 0)) or 0)
                except (TypeError, ValueError):
                    sz = 0.0
                if abs(sz) > 1e-12:
                    nz.append(p)
            diag["nonzero_positions"] = len(nz)
            for p in nz[:8]:
                diag["position_samples"].append(
                    {
                        "instId": p.get("instId"),
                        "symbol": p.get("symbol"),
                        "side": p.get("side"),
                        "posSide_raw": p.get("posSide_raw"),
                        "size": p.get("size"),
                        "entry_price": p.get("entry_price"),
                        "mark_px": p.get("mark_px"),
                    }
                )
        except Exception as e:
            diag["positions_error"] = str(e)

        mgr = getattr(self, "stop_loss_manager", None)
        if mgr:
            try:
                diag["sltp"] = mgr.get_stats()
                cfg = getattr(mgr, "config", None)
                if cfg:
                    diag["sltp_config"] = {
                        "sync_exchange_positions_on_startup": getattr(cfg, "sync_exchange_positions_on_startup", None),
                        "exchange_resync_interval_sec": getattr(cfg, "exchange_resync_interval_sec", None),
                    }
            except Exception as e:
                diag["sltp_error"] = str(e)

        return diag

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
                
                # 停止心跳监控器
                if self.heartbeat_monitor:
                    try:
                        self.heartbeat_monitor.stop()
                        logger.info("💔 心跳监控器已停止")
                    except Exception as e:
                        logger.error(f"停止心跳监控器失败: {e}")
                
                # 清空通知队列
                if self.smart_notification:
                    try:
                        await self.smart_notification.flush()
                        logger.info("📢 通知队列已清空")
                    except Exception as e:
                        logger.error(f"清空通知队列失败: {e}")
                
                # 保存最终记忆
                if self.hierarchical_memory:
                    try:
                        summary = f"""# 系统关闭总结 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 运行统计
- 运行时间: {datetime.now() - self.start_time if self.start_time else 'N/A'}
- 处理事件: {self.metrics.get('total_events', 0)}
- 错误次数: {self.metrics.get('total_errors', 0)}

## 系统状态
- 最终状态: {self.system_status.value}
"""
                        await self.hierarchical_memory.save_daily_memory(summary)
                        logger.info("💾 最终记忆已保存")
                    except Exception as e:
                        logger.error(f"保存最终记忆失败: {e}")

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

        # 启动AI控制器（单脑仲裁）
        try:
            await self._start_ai_brain_controllers()
            await self._start_ai_autonomous_supervision()
        except Exception as e:
            logger.error(f"AI主控启动失败: {e}")
            success = False

        # 启动主动性AI系统
        if self.proactive_ai:
            try:
                await self.proactive_ai.start()
                logger.info("🚀 主动性AI系统已启动 - AI将主动扫描市场、分析信息、执行交易")
            except Exception as e:
                logger.error(f"主动性AI系统启动失败: {e}")

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

        # 停止AI自主监督循环
        if hasattr(self, "ai_command_executor") and self.ai_command_executor:
            try:
                await self.ai_command_executor.stop_autonomous_work()
                logger.info("🛑 AICommandExecutor 自主监督循环已停止")
            except Exception as e:
                logger.error(f"停止 AICommandExecutor 自主监督失败: {e}")

        # 先停止AI核心决策引擎
        if hasattr(self, 'ai_core') and self.ai_core:
            try:
                await self.ai_core.stop()
                logger.info("🛑 AI核心决策引擎已停止")
            except Exception as e:
                logger.error(f"AI核心决策引擎停止失败: {e}")

        # 停止主动性AI系统
        if hasattr(self, 'proactive_ai') and self.proactive_ai:
            try:
                await self.proactive_ai.stop()
                logger.info("🛑 主动性AI系统已停止")
            except Exception as e:
                logger.error(f"主动性AI系统停止失败: {e}")

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

            core_to_legacy_map = {
                CoreEventType.SYSTEM_START: EventType.SYSTEM_START,
                CoreEventType.SYSTEM_STOP: EventType.SYSTEM_STOP,
                CoreEventType.MODULE_STARTED: EventType.MODULE_STARTED,
                CoreEventType.MODULE_STOPPED: EventType.MODULE_STOPPED,
                CoreEventType.MODULE_ERROR: EventType.MODULE_ERROR,
                CoreEventType.CONFIG_CHANGED: EventType.CONFIG_CHANGED,
                CoreEventType.DATA_RECEIVED: EventType.DATA_RECEIVED,
                CoreEventType.TRADE_SIGNAL: EventType.TRADE_SIGNAL,
                CoreEventType.RISK_ALERT: EventType.ALERT,
            }

            async def _wrapper(core_event):
                try:
                    legacy_event = SystemEvent(
                        id=getattr(core_event, "id", str(uuid.uuid4())),
                        type=core_to_legacy_map.get(getattr(core_event, "type", None), event_type),
                        source=getattr(core_event, "source", "unknown"),
                        data=getattr(core_event, "data", {}) or {},
                        priority=0,
                    )
                    if asyncio.iscoroutinefunction(handler):
                        await handler(legacy_event)
                    else:
                        handler(legacy_event)
                except Exception as e:
                    logger.error(f"事件处理器执行错误: {e}")

            self.event_system.subscribe(core_event_type, _wrapper)
        
        logger.debug(f"注册事件处理器: {event_type.value} -> {handler.__name__}")

    async def _verify_module_connections(self):
        """验证关键模块连接状态"""
        logger.info("🔍 验证模块连接状态...")
        
        # 定义关键模块检查列表
        critical_modules = {
            "核心系统": ["event_system", "data_quality_system", "fault_tolerance", "enhanced_llm_manager"],
            "AI决策": ["llm_integration", "ai_trading_engine", "ai_core"],
            "智能系统": ["hierarchical_memory", "skill_manager", "smart_notification"],
            "交易系统": ["trading_monitor", "strategy_manager", "risk_monitor"],
            "数据存储": ["data_storage", "backup_manager", "database_manager"],
            "通知系统": ["telegram_bot", "natural_language_interface"],
            "安全风控": ["emergency_stop", "intelligent_monitoring", "security_manager", "fund_manager"],
            "信息收集分析": ["unified_info_collector"],
            "升级模块": ["dynamic_position_manager", "correlation_monitor", "strategy_hot_loader", "audit_logger", "enhanced_monitoring", "stop_loss_manager"],
        }
        
        total_checked = 0
        connected_count = 0
        missing_modules = []
        
        for category, modules in critical_modules.items():
            for module_name in modules:
                total_checked += 1
                module = getattr(self, module_name, None)
                
                if module is not None:
                    connected_count += 1
                else:
                    missing_modules.append((category, module_name))
        
        # 计算连接率
        connection_rate = (connected_count / total_checked * 100) if total_checked > 0 else 0
        
        logger.info(f"📊 模块连接状态: {connected_count}/{total_checked} ({connection_rate:.1f}%)")
        
        # 如果有缺失的关键模块，记录警告
        if missing_modules:
            logger.warning(f"⚠️ 缺失模块 ({len(missing_modules)}):")
            for category, module_name in missing_modules[:5]:  # 只显示前5个
                logger.warning(f"   - [{category}] {module_name}")
        
        # 如果连接率低于80%，发出警告
        if connection_rate < 80:
            logger.warning(f"⚠️ 模块连接率较低 ({connection_rate:.1f}%)，请检查系统配置")
        else:
            logger.info(f"✅ 模块连接状态良好 ({connection_rate:.1f}%)")

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
            # 回退路径：仅在无增强事件系统时调用旧处理器，避免重复派发
            if event_type in self.event_handlers:
                for handler in self.event_handlers[event_type]:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event)
                        else:
                            handler(event)
                    except Exception as e:
                        logger.error(f"事件处理器执行错误: {e}")

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

            # 兼容：若 self.modules 未注册完整，回退到按关键属性统计真实模块连接状态
            fallback_module_names = [
                "event_system", "data_quality_system", "fault_tolerance", "enhanced_llm_manager",
                "llm_integration", "ai_trading_engine", "ai_core",
                "hierarchical_memory", "skill_manager", "smart_notification",
                "trading_monitor", "strategy_manager", "risk_monitor",
                "data_storage", "backup_manager", "database_manager",
                "telegram_bot", "natural_language_interface",
                "emergency_stop", "intelligent_monitoring", "security_manager", "fund_manager",
                "unified_info_collector",
                "dynamic_position_manager", "correlation_monitor", "strategy_hot_loader",
                "audit_logger", "enhanced_monitoring", "stop_loss_manager",
            ]
            fallback_connected = [n for n in fallback_module_names if getattr(self, n, None) is not None]
            fallback_statuses = {
                n: {"status": "connected", "health": "unknown", "uptime": 0, "error_count": 0}
                for n in fallback_connected
            }

            module_count = len(self.modules) if len(self.modules) > 0 else len(fallback_module_names)
            running_modules = (
                len([m for m in self.modules.values() if m.status == ModuleStatus.RUNNING])
                if len(self.modules) > 0
                else len(fallback_connected)
            )

            out: Dict[str, Any] = {
                "system_status": self.system_status.value,
                "start_time": self.start_time.isoformat() if self.start_time else None,
                "stop_time": self.stop_time.isoformat() if self.stop_time else None,
                "uptime": (
                    (datetime.now() - self.start_time).total_seconds()
                    if self.start_time and self.system_status == ModuleStatus.RUNNING
                    else 0
                ),
                "module_count": module_count,
                "running_modules": running_modules,
                "module_statuses": module_statuses if module_statuses else fallback_statuses,
                "metrics": self.metrics.copy(),
            }
            if getattr(self, "execution_gateway", None):
                try:
                    out["execution_spine"] = await self.execution_gateway.get_snapshot()
                except Exception as e:
                    out["execution_spine"] = {"error": str(e)}
            return out

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
    
    async def check_system_stability(self) -> Dict[str, Any]:
        """
        检查系统稳定性
        
        Returns:
            稳定性分析结果
        """
        if not self.stability_analyzer:
            return {"error": "稳定性分析器未初始化"}
        
        context = {
            "main_controller": self,
            "trading_engine": self.ai_trading_engine if hasattr(self, 'ai_trading_engine') else None
        }
        
        metrics = await self.stability_analyzer.analyze(context)
        decision = await self.stability_analyzer.make_decision(metrics, context)
        
        return {
            "stability_metrics": metrics.to_dict(),
            "decision": decision.to_dict(),
            "trend": self.stability_analyzer.get_stability_trend()
        }
    
    async def execute_stability_decision(self) -> bool:
        """
        执行稳定性决策
        
        Returns:
            是否执行成功
        """
        if not self.stability_analyzer:
            logger.warning("稳定性分析器未初始化")
            return False
        
        last_decision = self.stability_analyzer.get_last_decision()
        if not last_decision:
            return False
        
        context = {
            "main_controller": self,
            "trading_engine": self.ai_trading_engine if hasattr(self, 'ai_trading_engine') else None
        }
        
        return await self.stability_analyzer.execute_decision(last_decision, context)
    
    async def perform_system_maintenance(self) -> Dict[str, Any]:
        """
        执行系统维护
        
        Returns:
            维护结果
        """
        if not self.skill_manager:
            return {"error": "技能管理器未初始化"}
        
        system_maintenance_skill = self.skill_manager.get_skill("system_maintenance")
        if not system_maintenance_skill:
            return {"error": "系统维护技能未注册"}
        
        context = {
            "main_controller": self,
            "trading_engine": self.ai_trading_engine if hasattr(self, 'ai_trading_engine') else None
        }
        
        result = await system_maintenance_skill.execute(context)
        
        return result.to_dict()
    
    def get_ai_capabilities(self) -> Dict[str, Any]:
        """
        获取AI能力列表
        
        Returns:
            AI能力信息
        """
        capabilities = {
            "skills": [],
            "stability_analysis": False,
            "auto_maintenance": False,
            "decision_making": False,
            "code_editing": False,
            "code_development": False,
            "code_review": False,
            "autonomous_development": False
        }
        
        if self.skill_manager:
            capabilities["skills"] = [
                {
                    "name": skill.name,
                    "description": skill.description,
                    "priority": skill.priority.value if hasattr(skill.priority, 'value') else str(skill.priority)
                }
                for skill in self.skill_manager.skills.values()
            ]
            capabilities["auto_maintenance"] = any(
                s.name == "system_maintenance" for s in self.skill_manager.skills.values()
            )
            capabilities["code_editing"] = any(
                s.name == "code_editor" for s in self.skill_manager.skills.values()
            )
            capabilities["code_development"] = any(
                s.name == "code_developer" for s in self.skill_manager.skills.values()
            )
            capabilities["code_review"] = any(
                s.name == "code_reviewer" for s in self.skill_manager.skills.values()
            )
        
        if self.stability_analyzer:
            capabilities["stability_analysis"] = True
            capabilities["decision_making"] = True
            
            last_analysis = self.stability_analyzer.get_last_analysis()
            if last_analysis:
                capabilities["current_stability"] = last_analysis.to_dict()
            
            last_decision = self.stability_analyzer.get_last_decision()
            if last_decision:
                capabilities["last_decision"] = last_decision.to_dict()
        
        if self.autonomous_developer:
            capabilities["autonomous_development"] = True
            capabilities["developer_tasks"] = self.autonomous_developer.get_all_tasks()
        
        return capabilities
    
    async def create_development_task(
        self,
        name: str,
        description: str,
        requirements: List[str]
    ) -> Dict[str, Any]:
        """
        创建开发任务
        
        Args:
            name: 任务名称
            description: 任务描述
            requirements: 需求列表
            
        Returns:
            任务信息
        """
        if not self.autonomous_developer:
            return {"error": "自主开发框架未初始化"}
        
        task = await self.autonomous_developer.create_task(
            name=name,
            description=description,
            requirements=requirements
        )
        
        return task.to_dict()
    
    async def execute_development_task(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """
        执行开发任务
        
        Args:
            task_id: 任务ID，如果为None则执行当前任务
            
        Returns:
            执行结果
        """
        if not self.autonomous_developer:
            return {"error": "自主开发框架未初始化"}
        
        task = None
        if task_id:
            for t in self.autonomous_developer.tasks:
                if t.task_id == task_id:
                    task = t
                    break
        
        result = await self.autonomous_developer.execute_task(task)
        
        return result.to_dict()
    
    async def edit_code(
        self,
        file_path: str,
        edit_type: str,
        content: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        description: str = ""
    ) -> Dict[str, Any]:
        """
        编辑代码
        
        Args:
            file_path: 文件路径
            edit_type: 编辑类型 (insert/delete/replace)
            content: 新内容
            start_line: 起始行
            end_line: 结束行
            description: 描述
            
        Returns:
            编辑结果
        """
        if not self.skill_manager:
            return {"error": "技能管理器未初始化"}
        
        code_editor = self.skill_manager.get_skill("code_editor")
        if not code_editor:
            return {"error": "代码编辑技能未注册"}
        
        from src.modules.skills.code_editor_skill import EditOperation
        
        context = {
            "edit_request": {
                "operation": "edit",
                "file_path": file_path,
                "edit_type": edit_type,
                "content": content,
                "start_line": start_line,
                "end_line": end_line,
                "description": description
            }
        }
        
        result = await code_editor.execute(context)
        
        return result.to_dict()
    
    async def review_code(self, file_path: str) -> Dict[str, Any]:
        """
        审查代码
        
        Args:
            file_path: 文件路径
            
        Returns:
            审查结果
        """
        if not self.skill_manager:
            return {"error": "技能管理器未初始化"}
        
        code_reviewer = self.skill_manager.get_skill("code_reviewer")
        if not code_reviewer:
            return {"error": "代码审查技能未注册"}
        
        context = {
            "review_request": {
                "operation": "review_file",
                "file_path": file_path
            }
        }
        
        result = await code_reviewer.execute(context)
        
        return result.to_dict()
    
    async def generate_code(
        self,
        dev_type: str,
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成代码
        
        Args:
            dev_type: 开发类型
            spec: 规格说明
            
        Returns:
            生成结果
        """
        if not self.skill_manager:
            return {"error": "技能管理器未初始化"}
        
        code_developer = self.skill_manager.get_skill("code_developer")
        if not code_developer:
            return {"error": "代码开发技能未注册"}
        
        context = {
            "dev_request": {
                "operation": "create",
                "dev_type": dev_type,
                "spec": spec
            }
        }
        
        result = await code_developer.execute(context)
        
        return result.to_dict()
    
    
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

        # 生产结果反哺：把实时交易表现同步给策略管理器，触发自适应参数优化
        if self.strategy_manager and hasattr(self.strategy_manager, "apply_trade_feedback"):
            try:
                await self.strategy_manager.apply_trade_feedback(
                    strategy_id=strategy_name,
                    pnl=float(total_pnl),
                    win_rate=float(win_rate),
                    max_drawdown=float(max_drawdown),
                    total_trades=int(total_trades),
                )
            except Exception as e:
                logger.warning(f"策略交易反馈优化失败({strategy_name}): {e}")

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

    async def _strategy_research_worker(self) -> None:
        """
        自动策略研发工作线程：
        - 按 research 配置周期触发 walk-forward 研发
        - 将通过门控的策略自动发布并启动实例
        """
        logger.info("自动策略研发工作线程启动")
        while self._running:
            try:
                cfg = await self.config_manager.get_config("research", {}) if self.config_manager else {}
                cfg = cfg if isinstance(cfg, dict) else {}
                enabled = bool(cfg.get("enabled", True))
                auto_run = bool(cfg.get("auto_run", True))
                interval_minutes = float(cfg.get("auto_interval_minutes", 360) or 360)
                interval_seconds = max(300, int(interval_minutes * 60))
                loop_sleep = min(60, max(20, self.health_check_interval))

                if not enabled or not auto_run:
                    await asyncio.sleep(loop_sleep)
                    continue

                due = (
                    self._last_strategy_research_at is None
                    or (datetime.now() - self._last_strategy_research_at).total_seconds() >= interval_seconds
                )
                if not due or self._strategy_research_running:
                    await asyncio.sleep(loop_sleep)
                    continue

                pipeline = getattr(self, "strategy_research_pipeline", None)
                if not pipeline:
                    await asyncio.sleep(loop_sleep)
                    continue

                symbols = cfg.get("symbols") or ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
                if isinstance(symbols, str):
                    symbols = [symbols]
                if bool(cfg.get("dynamic_scan_for_research", True)):
                    selector = getattr(self, "dynamic_symbol_selector", None)
                    if selector and hasattr(selector, "get_trading_symbols"):
                        try:
                            dyn_symbols = await selector.get_trading_symbols()
                            if dyn_symbols:
                                symbols = dyn_symbols
                        except Exception:
                            pass
                max_scan = int(cfg.get("symbol_scan_limit", 12) or 12)
                symbols = [str(s) for s in symbols if s][:max(1, max_scan)]
                timeframe = str(cfg.get("timeframe", "1h") or "1h")
                lookback_days = int(cfg.get("lookback_days", 30) or 30)

                self._strategy_research_running = True
                try:
                    result = await pipeline.run_cycle(
                        symbols=symbols,
                        timeframe=timeframe,
                        lookback_days=lookback_days,
                    )
                    self._last_strategy_research_at = datetime.now()
                    published_cnt = len((result or {}).get("published", []))
                    logger.info(
                        "自动策略研发完成: symbols=%s published=%s backtest_calls=%s",
                        symbols,
                        published_cnt,
                        (result or {}).get("backtest_calls", 0),
                    )
                finally:
                    self._strategy_research_running = False

                await asyncio.sleep(loop_sleep)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._strategy_research_running = False
                logger.error(f"自动策略研发线程异常: {e}")
                await asyncio.sleep(30)
        logger.info("自动策略研发工作线程停止")

    async def _send_notification_direct(self, title: str, message: str, priority: str = "medium"):
        """直接发送通知到底层渠道（不做智能去重/节流）。"""
        channels = {"telegram", "log"}
        try:
            if self.config_manager:
                msg = await self.config_manager.get_config("messaging", {}) or {}
                inst = msg.get("instant") if isinstance(msg.get("instant"), dict) else {}
                if inst.get("enabled") is False:
                    log_level = {
                        "critical": logging.CRITICAL,
                        "high": logging.WARNING,
                        "medium": logging.INFO,
                        "low": logging.DEBUG,
                    }.get(priority.lower(), logging.INFO)
                    logger.log(
                        log_level, f"📢 [messaging.instant 已关闭] {title}: {message[:200]}"
                    )
                    return
                ch = inst.get("channels")
                if isinstance(ch, list) and ch:
                    channels = {str(x).strip().lower() for x in ch if x}
        except Exception:
            pass

        # 发送到Telegram
        if "telegram" in channels and self.telegram_bot:
            try:
                await self.telegram_bot.send_message(f"{title}\n\n{message}")
                logger.debug(f"Telegram通知已发送: {title}")
            except Exception as e:
                # Avoid log spam when chat_id/proxy is misconfigured.
                now = datetime.now()
                window_sec = 1800
                try:
                    cfg = await self.config_manager.get_config("notifications", {}) if self.config_manager else {}
                    if isinstance(cfg, dict):
                        window_sec = int(cfg.get("telegram", {}).get("failure_dedup_window_sec", window_sec))
                except Exception:
                    pass
                if not hasattr(self, "_telegram_fail_dedup"):
                    self._telegram_fail_dedup = {}  # type: ignore[attr-defined]
                key = str(e)
                last = self._telegram_fail_dedup.get(key)  # type: ignore[attr-defined]
                if not last or (now - last).total_seconds() > window_sec:
                    self._telegram_fail_dedup[key] = now  # type: ignore[attr-defined]
                    logger.error(f"Telegram通知发送失败: {e}")

        if "log" in channels:
            log_level = {
                "critical": logging.CRITICAL,
                "high": logging.WARNING,
                "medium": logging.INFO,
                "low": logging.DEBUG,
            }.get(priority.lower(), logging.INFO)
            logger.log(log_level, f"📢 [{priority.upper()}] {title}: {message[:100]}")

    async def _send_notification_handler(self, title: str, message: str, priority: str = "medium"):
        """
        通知处理方法 - 统一的通知发送接口
        
        Args:
            title: 通知标题
            message: 通知内容
            priority: 优先级
        """
        try:
            if self.config_manager:
                try:
                    msg = await self.config_manager.get_config("messaging", {}) or {}
                    inst = msg.get("instant") if isinstance(msg.get("instant"), dict) else {}
                    if inst.get("enabled") is False:
                        logger.debug("即时消息通道已关闭(messaging.instant)，跳过: %s", title)
                        return
                except Exception:
                    pass

            # Hard-block low-value "opportunity discovery" notifications.
            try:
                block_phrases = []
                if self.config_manager:
                    ncfg = await self.config_manager.get_config("notifications", {}) or {}
                    if isinstance(ncfg, dict):
                        smart = ncfg.get("smart", {}) if isinstance(ncfg.get("smart", {}), dict) else {}
                        block_phrases = [str(x) for x in smart.get("block_phrases", []) or []]
                text = f"{title}\n{message}"
                if any(p and p in text for p in block_phrases):
                    logger.debug(f"通知已过滤(命中关键词): {title}")
                    return
            except Exception:
                pass

            # Route through SmartNotificationSystem so dedup/rate-limit/batch always applies.
            if self.smart_notification:
                try:
                    cfg = await self.config_manager.get_config("notifications", {}) if self.config_manager else {}
                    smart_cfg = cfg.get("smart", {}) if isinstance(cfg, dict) and isinstance(cfg.get("smart"), dict) else {}
                    self.smart_notification.apply_config(smart_cfg)
                except Exception:
                    pass
                await self.smart_notification.send(title, message, priority=priority, category="general")
                return

            await self._send_notification_direct(title, message, priority)
            
        except Exception as e:
            logger.error(f"通知处理失败: {e}")

    async def build_ai_commander_snapshot(self, symbol: str = "BTC/USDT") -> Dict[str, Any]:
        """
        AI司令部快照：为TG/前端统一提供关键运行态与决策信息。
        """
        out: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "system": {},
            "data_hub": {},
            "strategy": {},
            "execution": {},
            "risk": {},
            "account": {},
            "alerts": [],
        }
        try:
            status = await self.get_system_status()
            out["system"] = {
                "system_status": status.get("system_status"),
                "module_count": status.get("module_count"),
                "running_modules": status.get("running_modules"),
            }
        except Exception as e:
            out["alerts"].append(f"系统状态读取失败: {e}")

        hub = getattr(self, "data_source_hub", None)
        if hub and hasattr(hub, "get_unified_snapshot"):
            try:
                snap = await hub.get_unified_snapshot(symbol)
                out["data_hub"] = {
                    "symbol": symbol,
                    "quality": (snap.get("数据质量评估") or {}),
                    "advisor": (snap.get("数据质量与作用评分") or {}),
                    "provenance": ((snap.get("数据来源状态") or {}).get("provenance")),
                }
                # analysis moved to MarketIntelligenceEngine
                try:
                    mi = getattr(self, "market_intelligence", None)
                    if mi and hasattr(mi, "get_symbol_view"):
                        view = await mi.get_symbol_view(symbol, include_snapshot=False)
                        out["data_hub"]["market_intelligence"] = (
                            view.to_dict() if hasattr(view, "to_dict") else {}
                        )
                except Exception:
                    out["data_hub"]["market_intelligence"] = {}
                for a in (snap.get("监控告警") or []):
                    if isinstance(a, dict):
                        out["alerts"].append(str(a.get("标题") or "数据告警") + ": " + str(a.get("消息") or ""))
            except Exception as e:
                out["alerts"].append(f"数据中心快照失败: {e}")

        sm = getattr(self, "strategy_manager", None)
        if sm and hasattr(sm, "get_optimization_status"):
            try:
                st = sm.get_optimization_status()
                out["strategy"] = {
                    "total_strategies": st.get("total_strategies"),
                    "pool_limit": st.get("pool_limit"),
                    "daily_optimization": st.get("daily_optimization"),
                    "deployment_stage_counts": st.get("deployment_stage_counts"),
                }
            except Exception as e:
                out["alerts"].append(f"策略状态读取失败: {e}")

        gw = getattr(self, "execution_gateway", None)
        if gw and hasattr(gw, "get_snapshot"):
            try:
                out["execution"] = await gw.get_snapshot()
            except Exception as e:
                out["alerts"].append(f"执行网关快照失败: {e}")

        slm = getattr(self, "stop_loss_manager", None)
        if slm and hasattr(slm, "get_stats"):
            try:
                out["risk"]["sltp"] = slm.get_stats()
            except Exception as e:
                out["alerts"].append(f"SLTP统计读取失败: {e}")

        # 账户/持仓接管快照（重启后强制同步的结果）
        try:
            st = getattr(self, "_latest_account_state", None) or {}
            out["account"] = {
                "balance": st.get("balance"),
                "positions": st.get("positions"),
                "synced_at": st.get("timestamp"),
            }
        except Exception:
            pass

        # 动态仓位管理建议（若可用）
        try:
            bal = out.get("account", {}).get("balance") or {}
            usdt = bal.get("USDT", bal.get("usdt", 0)) if isinstance(bal, dict) else 0
            if isinstance(usdt, dict):
                available = usdt.get("free", usdt.get("available", 0))
            else:
                available = usdt
            positions = out.get("account", {}).get("positions") or []
            # normalize positions to dict with value
            pos_map: Dict[str, Any] = {}
            if isinstance(positions, list):
                for p in positions:
                    if isinstance(p, dict):
                        sym = p.get("symbol") or p.get("instId") or p.get("instrument_id")
                        if sym:
                            try:
                                v = float(p.get("notional") or p.get("value") or 0)
                            except Exception:
                                v = 0.0
                            pos_map[str(sym)] = {"value": v, **p}
            if available and hasattr(self, "get_position_recommendations"):
                reco = await self.get_position_recommendations(account_balance=float(available), current_positions=pos_map)
                out["risk"]["position_recommendations"] = reco
        except Exception:
            pass
        return out

    async def run_ai_commander_chores(self, symbol: str = "BTC/USDT", trigger_optimize: bool = False) -> Dict[str, Any]:
        """
        AI司令部日常任务（轻量、安全版）：
        1) 拉取全局快照
        2) 可选触发一次策略优化批次
        """
        report = await self.build_ai_commander_snapshot(symbol=symbol)
        report["chores"] = {"trigger_optimize": bool(trigger_optimize), "optimize_result": None}
        if trigger_optimize:
            sm = getattr(self, "strategy_manager", None)
            if sm and hasattr(sm, "trigger_daily_optimization_now"):
                try:
                    report["chores"]["optimize_result"] = await sm.trigger_daily_optimization_now()
                except Exception as e:
                    report["chores"]["optimize_result"] = {"success": False, "message": str(e)}
            else:
                report["chores"]["optimize_result"] = {"success": False, "message": "策略管理器不可用"}
        return report

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
                    if self._running and self.auto_restart_modules and module_name and module_name in self.modules:
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
                if self._running and self.auto_restart_modules and module_name and module_name in self.modules:
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

    # ========== 新增升级模块便捷方法 ==========

    def get_dynamic_position_manager(self) -> Optional[DynamicPositionManager]:
        """获取动态仓位管理器实例"""
        return self.dynamic_position_manager
    
    async def calculate_dynamic_position(
        self,
        symbol: str,
        base_size: float,
        account_balance: float,
        current_positions: Dict[str, Any],
        market_data: Optional[Dict] = None
    ) -> Tuple[float, Dict[str, Any]]:
        """
        计算动态仓位大小
        
        Args:
            symbol: 交易对
            base_size: 基础仓位大小
            account_balance: 账户余额
            current_positions: 当前持仓
            market_data: 市场数据
        
        Returns:
            (调整后仓位大小, 调整详情)
        """
        if not self.dynamic_position_manager:
            return base_size, {"error": "动态仓位管理器未初始化"}
        
        return await self.dynamic_position_manager.calculate_dynamic_position_size(
            symbol, base_size, account_balance, current_positions, market_data
        )
    
    async def get_position_recommendations(
        self,
        account_balance: float,
        current_positions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """获取仓位调整建议"""
        if not self.dynamic_position_manager:
            return {"error": "动态仓位管理器未初始化"}
        
        return await self.dynamic_position_manager.get_position_recommendations(
            account_balance, current_positions
        )
    
    def get_correlation_monitor(self) -> Optional[CorrelationMonitor]:
        """获取品种相关性监控器实例"""
        return self.correlation_monitor
    
    async def check_correlation_risks(
        self,
        current_positions: Dict[str, Any]
    ) -> List[Any]:
        """检查相关性风险"""
        if not self.correlation_monitor:
            return []
        
        return await self.correlation_monitor.check_correlation_risks(current_positions)
    
    async def get_diversification_score(
        self,
        current_positions: Dict[str, Any]
    ) -> float:
        """获取分散化得分"""
        if not self.correlation_monitor:
            return 1.0
        
        return await self.correlation_monitor.get_diversification_score(current_positions)
    
    async def get_correlation_summary(self) -> Dict[str, Any]:
        """获取相关性摘要"""
        if not self.correlation_monitor:
            return {"error": "相关性监控器未初始化"}
        
        return await self.correlation_monitor.get_correlation_summary()
    
    def get_strategy_hot_loader(self) -> Optional[StrategyHotLoader]:
        """获取策略热加载器实例"""
        return self.strategy_hot_loader
    
    async def hot_reload_strategy(self, strategy_name: str) -> bool:
        """热加载策略"""
        if not self.strategy_hot_loader:
            logger.warning("策略热加载器未初始化")
            return False
        
        return await self.strategy_hot_loader.reload_strategy(strategy_name)
    
    async def hot_load_strategy(
        self,
        strategy_name: str,
        strategy_path: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """热加载新策略"""
        if not self.strategy_hot_loader:
            logger.warning("策略热加载器未初始化")
            return False
        
        return await self.strategy_hot_loader.load_strategy(strategy_name, strategy_path, config)
    
    async def rollback_strategy(self, strategy_name: str, version_id: Optional[str] = None) -> bool:
        """回滚策略版本"""
        if not self.strategy_hot_loader:
            logger.warning("策略热加载器未初始化")
            return False
        
        return await self.strategy_hot_loader.rollback_strategy(strategy_name, version_id)
    
    async def list_hot_strategies(self) -> List[Dict[str, Any]]:
        """列出热加载的策略"""
        if not self.strategy_hot_loader:
            return []
        
        return await self.strategy_hot_loader.list_strategies()
    
    def get_audit_logger(self) -> Optional[AuditLogger]:
        """获取审计日志记录器实例"""
        return self.audit_logger
    
    async def log_audit_event(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        source: str = "system"
    ) -> Optional[str]:
        """记录审计事件"""
        if not self.audit_logger:
            return None
        
        return await self.audit_logger.log_event(
            event_type, severity, action, details, source
        )
    
    async def log_trade_audit(
        self,
        action: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_id: Optional[str] = None
    ) -> Optional[str]:
        """记录交易审计日志"""
        if not self.audit_logger:
            return None
        
        return await self.audit_logger.log_trade(
            action, symbol, side, quantity, price, order_id
        )
    
    async def generate_audit_report(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """生成审计报告"""
        if not self.audit_logger:
            return {"error": "审计日志记录器未初始化"}
        
        return await self.audit_logger.generate_report(start_time, end_time)
    
    def get_enhanced_monitoring_system(self) -> Optional[EnhancedMonitoringSystem]:
        """获取增强监控系统实例"""
        return self.enhanced_monitoring
    
    async def update_monitoring_metric(
        self,
        metric_name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None
    ):
        """更新监控指标"""
        if self.enhanced_monitoring:
            await self.enhanced_monitoring.update_metric(metric_name, value, tags)
    
    async def get_active_alerts(self) -> List[Any]:
        """获取活动报警"""
        if not self.enhanced_monitoring:
            return []
        
        return await self.enhanced_monitoring.get_active_alerts()
    
    async def get_monitoring_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        if not self.enhanced_monitoring:
            return {"status": "unavailable"}
        
        return await self.enhanced_monitoring.get_system_status()
    
    async def add_alert_rule(
        self,
        rule_id: str,
        name: str,
        metric: str,
        condition: str,
        threshold: float,
        level: str = "warning"
    ) -> bool:
        """添加报警规则"""
        if not self.enhanced_monitoring:
            return False
        
        from src.modules.monitoring.enhanced_monitoring import AlertRule
        
        level_map = {
            "info": AlertLevel.INFO,
            "warning": AlertLevel.WARNING,
            "error": AlertLevel.ERROR,
            "critical": AlertLevel.CRITICAL
        }
        
        rule = AlertRule(
            rule_id=rule_id,
            name=name,
            metric=metric,
            condition=condition,
            threshold=threshold,
            level=level_map.get(level, AlertLevel.WARNING),
            channels=[AlertChannel.TELEGRAM, AlertChannel.LOG]
        )
        
        await self.enhanced_monitoring.add_rule(rule)
        return True
    
    async def get_upgrade_modules_status(self) -> Dict[str, Any]:
        """获取升级模块状态"""
        return {
            "dynamic_position_manager": {
                "available": self.dynamic_position_manager is not None,
                "status": "active" if self.dynamic_position_manager else "unavailable"
            },
            "correlation_monitor": {
                "available": self.correlation_monitor is not None,
                "status": "active" if self.correlation_monitor else "unavailable"
            },
            "strategy_hot_loader": {
                "available": self.strategy_hot_loader is not None,
                "status": "active" if self.strategy_hot_loader else "unavailable"
            },
            "audit_logger": {
                "available": self.audit_logger is not None,
                "status": "active" if self.audit_logger else "unavailable"
            },
            "enhanced_monitoring": {
                "available": self.enhanced_monitoring is not None,
                "status": "active" if self.enhanced_monitoring else "unavailable"
            },
            "stop_loss_manager": {
                "available": self.stop_loss_manager is not None,
                "status": "active" if self.stop_loss_manager else "unavailable"
            }
        }
    
    # ========== 止盈止损管理便捷方法 ==========
    
    def get_stop_loss_manager(self) -> Optional[StopLossTakeProfitManager]:
        """获取止盈止损管理器实例"""
        return self.stop_loss_manager
    
    async def create_stop_loss_order(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        stop_loss_percent: float = 0.03,
        take_profit_percent: float = 0.06,
        enable_trailing: bool = True,
        trailing_offset: float = 0.02,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[StopLossTakeProfitOrder]:
        """
        创建止盈止损订单
        
        Args:
            symbol: 交易对
            side: 方向 (long/short)
            entry_price: 入场价格
            quantity: 数量
            stop_loss_percent: 止损百分比 (默认3%)
            take_profit_percent: 止盈百分比 (默认6%)
            enable_trailing: 启用移动止损
            trailing_offset: 移动止损偏移量
        
        Returns:
            止盈止损订单
        """
        if not self.stop_loss_manager:
            logger.warning("止盈止损管理器未初始化")
            return None
        
        sl_config = StopLossConfig(
            stop_type=StopType.PERCENTAGE,
            stop_value=stop_loss_percent,
            trailing_offset=trailing_offset if enable_trailing else 0
        )
        
        tp_config = TakeProfitConfig(
            tp_type=TakeProfitType.PERCENTAGE,
            tp_value=take_profit_percent
        )
        
        order = await self.stop_loss_manager.create_order(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss_config=sl_config,
            take_profit_config=tp_config,
            metadata=metadata,
        )
        
        logger.info(f"✅ 创建止盈止损订单: {symbol} {side} 止损={stop_loss_percent*100:.1f}% 止盈={take_profit_percent*100:.1f}%")
        
        return order
    
    async def update_stop_loss_price(self, symbol: str, current_price: float) -> Optional[StopLossTakeProfitOrder]:
        """
        更新止盈止损价格
        
        Args:
            symbol: 交易对
            current_price: 当前价格
        
        Returns:
            如果触发止盈止损，返回订单
        """
        if not self.stop_loss_manager:
            return None
        
        return await self.stop_loss_manager.update_price(symbol, current_price)
    
    async def modify_stop_loss(
        self,
        symbol: str,
        new_stop_loss: Optional[float] = None,
        new_take_profit: Optional[float] = None
    ) -> Optional[StopLossTakeProfitOrder]:
        """
        修改止盈止损价格
        
        Args:
            symbol: 交易对
            new_stop_loss: 新止损价格
            new_take_profit: 新止盈价格
        
        Returns:
            修改后的订单
        """
        if not self.stop_loss_manager:
            return None
        
        return await self.stop_loss_manager.modify_order(symbol, new_stop_loss, new_take_profit)
    
    async def cancel_stop_loss_order(self, symbol: str) -> bool:
        """取消止盈止损订单"""
        if not self.stop_loss_manager:
            return False
        
        return await self.stop_loss_manager.cancel_order(symbol)
    
    async def get_active_stop_loss_orders(self) -> List[StopLossTakeProfitOrder]:
        """获取所有活动的止盈止损订单"""
        if not self.stop_loss_manager:
            return []
        
        return await self.stop_loss_manager.get_all_active_orders()
    
    async def get_stop_loss_stats(self) -> Dict[str, Any]:
        """获取止盈止损统计信息"""
        if not self.stop_loss_manager:
            return {"error": "止盈止损管理器未初始化"}
        
        return self.stop_loss_manager.get_stats()
    
    async def start_stop_loss_monitoring(self):
        """启动止盈止损监控"""
        logger.info("🔄 正在启动止盈止损监控...")
        if self.stop_loss_manager:
            logger.info("✅ 止损管理器存在，设置交易所...")
            if hasattr(self, 'okx_exchange') and self.okx_exchange:
                self.stop_loss_manager.set_exchange(self.okx_exchange)
                logger.info("✅ 交易所已设置给止损管理器")
            else:
                logger.warning("⚠️ OKX交易所未设置，止损监控将无法获取价格")
            await self.stop_loss_manager.start()
            logger.info("✅ 止盈止损监控已启动")
            try:
                sync_res = await self.stop_loss_manager.sync_open_positions_from_exchange()
                logger.info(f"📌 交易所持仓已同步至止盈止损跟踪: {sync_res}")
            except Exception as e:
                logger.warning(f"⚠️ 交易所持仓同步至止盈止损失败（不影响启动）: {e}")
        else:
            logger.warning("⚠️ 止损管理器未初始化，跳过启动")
    
    async def stop_stop_loss_monitoring(self):
        """停止止盈止损监控"""
        if self.stop_loss_manager:
            await self.stop_loss_manager.stop()
            logger.info("止盈止损监控已停止")
    
    # ========== 执行验证便捷方法 ==========
    
    def get_execution_verifier(self) -> Optional[ExecutionVerifier]:
        """获取执行验证器实例"""
        return self.execution_verifier
    
    async def execute_command(
        self,
        command_type: CommandType,
        action: str,
        symbol: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[ExecutionResult]:
        """
        执行命令并返回验证结果
        
        Args:
            command_type: 命令类型
            action: 操作描述
            symbol: 交易对
            params: 执行参数
        
        Returns:
            执行结果（包含验证信息）
        """
        if not self.execution_verifier:
            logger.warning("执行验证器未初始化")
            return None

        if getattr(self, "execution_gateway", None):
            try:
                tick_src = "execution_verifier"
                if params and isinstance(params, dict):
                    tick_src = str(
                        params.get("write_source")
                        or params.get("source")
                        or "execution_verifier"
                    ).strip() or "execution_verifier"
                self.execution_gateway.record_tick(
                    tick_src,
                    f"{command_type.value}:{action}",
                )
            except Exception:
                pass
        
        result = await self.execution_verifier.execute(
            command_type=command_type,
            action=action,
            symbol=symbol,
            params=params
        )
        
        return result
    
    async def query_execution_status(self, query: str) -> Dict[str, Any]:
        """
        查询执行状态（自然语言查询）
        
        Args:
            query: 查询内容，如"最近执行了什么"、"查看持仓"、"有什么失败的"
        
        Returns:
            查询结果
        """
        if not self.execution_verifier:
            return {"error": "执行验证器未初始化"}
        
        return await self.execution_verifier.query_execution(query)
    
    async def get_recent_executions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的执行记录"""
        if not self.execution_verifier:
            return []
        
        executions = await self.execution_verifier.get_recent_executions(limit)
        return [e.to_dict() for e in executions]
    
    async def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计信息"""
        if not self.execution_verifier:
            return {"error": "执行验证器未初始化"}
        
        return self.execution_verifier.get_stats()
    
    async def verify_position_opened(self, symbol: str) -> Dict[str, Any]:
        """验证仓位是否已开"""
        if not self.execution_verifier:
            return {"verified": False, "error": "执行验证器未初始化"}
        
        recent = await self.execution_verifier.get_recent_executions(10)
        for execution in recent:
            if (execution.command_type == CommandType.OPEN_POSITION and 
                execution.symbol == symbol and 
                execution.status == ExecutionStatus.SUCCESS):
                return {
                    "verified": True,
                    "execution_id": execution.execution_id,
                    "details": execution.details
                }
        
        return {"verified": False, "message": f"未找到 {symbol} 的开仓记录"}
    
    async def verify_stop_loss_set(self, symbol: str) -> Dict[str, Any]:
        """验证止损是否已设置"""
        if not self.stop_loss_manager:
            return {"verified": False, "error": "止盈止损管理器未初始化"}
        
        order = await self.stop_loss_manager.get_order(symbol)
        if order:
            return {
                "verified": True,
                "stop_loss": order.stop_loss_price,
                "take_profit": order.take_profit_price,
                "trailing_activated": order.trailing_stop_activated
            }
        
        return {"verified": False, "message": f"未找到 {symbol} 的止盈止损设置"}


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
            "trading_execution", MockModule(), dependencies=["data_pipeline", "cache_manager"]
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
