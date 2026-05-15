"""
策略管理模块 - 全智能量化交易系统的智能核心

功能：
1. 策略注册和加载（动态加载Python策略）
2. 策略生命周期管理（初始化、启动、停止、清理）
3. 策略参数管理（参数配置和优化）
4. 信号生成和过滤（交易信号生成和过滤）
5. 性能分析（策略回测和实时表现分析）
6. 多策略组合和权重调整
7. 自动策略切换
8. 机器学习集成
"""

import asyncio
import hashlib
import importlib
import inspect
import json
import logging
import math
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type

import numpy as np
import pandas as pd
import yaml

from src.modules.intelligence.machine_learning.model_manager import ModelManager, ModelType
from src.modules.intelligence.machine_learning.model_optimizer import ModelOptimizer

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """策略类型 - AI可自主扩展"""

    TREND_FOLLOWING = "trend_following"  # 趋势跟踪
    MEAN_REVERSION = "mean_reversion"  # 均值回归
    ARBITRAGE = "arbitrage"  # 套利
    MARKET_MAKING = "market_making"  # 做市
    GRID_TRADING = "grid_trading"  # 网格交易
    ML_BASED = "ml_based"  # 机器学习策略
    AI_GENERATED = "ai_generated"  # AI生成策略
    COMBINATION = "combination"  # 组合策略
    MULTI_STRATEGY = "multi_strategy"  # 多策略
    CUSTOM = "custom"  # 自定义
    AUTO = "auto"  # AI自主决定


class StrategyStatus(Enum):
    """策略状态"""

    CREATED = "created"  # 已创建
    INITIALIZING = "initializing"  # 初始化中
    READY = "ready"  # 准备就绪
    RUNNING = "running"  # 运行中
    PAUSED = "paused"  # 已暂停
    STOPPED = "stopped"  # 已停止
    ERROR = "error"  # 错误


class StrategyLifecycleStage(Enum):
    PROPOSAL = "proposal"
    RESEARCHING = "researching"
    BACKTESTING = "backtesting"
    OOS_VALIDATING = "oos_validating"
    PAPER_RUNNING = "paper_running"
    LIMITED_LIVE = "limited_live"
    SCALED_LIVE = "scaled_live"
    DEGRADED = "degraded"
    PAUSED = "paused"
    RETIRED = "retired"


_DEPLOYMENT_TO_LIFECYCLE = {
    "paper": StrategyLifecycleStage.PAPER_RUNNING,
    "shadow": StrategyLifecycleStage.LIMITED_LIVE,
    "small": StrategyLifecycleStage.LIMITED_LIVE,
    "full": StrategyLifecycleStage.SCALED_LIVE,
}


class SignalType(Enum):
    """信号类型"""

    BUY = "buy"  # 买入信号
    SELL = "sell"  # 卖出信号
    HOLD = "hold"  # 持有信号
    CLOSE = "close"  # 平仓信号
    CANCEL = "cancel"  # 取消信号


class MarketRegime(Enum):
    """市场状态"""
    BULL = "bull"          # 牛市
    BEAR = "bear"          # 熊市
    SIDEWAYS = "sideways"    # 横盘
    VOLATILE = "volatile"    # 高波动
    LOW_VOLUME = "low_volume"  # 低成交量


@dataclass
class StrategyConfig:
    """策略配置"""

    strategy_id: str
    name: str
    description: str
    strategy_type: StrategyType
    enabled: bool = True
    version: str = "1.0.0"
    author: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    symbols: List[str] = field(default_factory=list)
    timeframe: str = "1h"  # 时间框架
    initial_capital: float = 10000.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    stage: StrategyLifecycleStage = StrategyLifecycleStage.RESEARCHING
    oos_status: str = "unknown"
    live_drift_status: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "strategy_type": self.strategy_type.value,
            "enabled": self.enabled,
            "version": self.version,
            "author": self.author,
            "parameters": self.parameters,
            "symbols": self.symbols,
            "timeframe": self.timeframe,
            "initial_capital": self.initial_capital,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
            "stage": self.stage.value,
            "oos_status": self.oos_status,
            "live_drift_status": self.live_drift_status,
        }


@dataclass
class StrategyInstance:
    """策略实例"""

    instance_id: str
    config: StrategyConfig
    status: StrategyStatus = StrategyStatus.CREATED
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    last_signal_at: Optional[datetime] = None
    total_signals: int = 0
    active_positions: int = 0
    total_trades: int = 0
    total_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    instance: Optional[Any] = None  # 策略类实例
    metadata: Dict[str, Any] = field(default_factory=dict)
    lifecycle_stage: StrategyLifecycleStage = StrategyLifecycleStage.RESEARCHING


@dataclass
class TradingSignal:
    """交易信号"""

    signal_id: str
    strategy_id: str
    instance_id: str
    signal_type: SignalType
    symbol: str
    timestamp: datetime = field(default_factory=datetime.now)
    price: Optional[float] = None
    quantity: Optional[float] = None
    confidence: float = 0.5  # 置信度 0-1
    reason: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "instance_id": self.instance_id,
            "signal_type": self.signal_type.value,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "price": self.price,
            "quantity": self.quantity,
            "confidence": self.confidence,
            "reason": self.reason,
            "parameters": self.parameters,
            "metadata": self.metadata,
        }


@dataclass
class StrategyPerformance:
    """策略性能"""

    strategy_id: str
    total_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    avg_trade_pnl: float = 0.0
    avg_winning_trade: float = 0.0
    avg_losing_trade: float = 0.0
    total_days: int = 0
    daily_return_mean: float = 0.0
    daily_return_std: float = 0.0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    last_updated: datetime = field(default_factory=datetime.now)
    market_regime: Optional[MarketRegime] = None
    lifecycle_stage: StrategyLifecycleStage = StrategyLifecycleStage.RESEARCHING
    oos_status: str = "unknown"
    live_drift_status: str = "unknown"


class BaseStrategy:
    """
    策略基类

    所有自定义策略都应该继承这个类
    """

    def __init__(self, config: StrategyConfig):
        """
        初始化策略

        Args:
            config: 策略配置
        """
        self.config = config
        self.strategy_id = config.strategy_id
        self.name = config.name
        self.parameters = config.parameters
        self.symbols = config.symbols
        self.timeframe = config.timeframe

        # 状态
        self._initialized = False
        self._running = False

        # 数据存储
        self._market_data = {}
        self._positions = {}
        self._signals = []

        logger.info(f"初始化策略: {self.name} ({self.strategy_id})")

    async def initialize(self) -> None:
        """
        初始化策略

        加载数据，计算指标等
        """
        if self._initialized:
            return

        try:
            await self._load_data()
            await self._calculate_indicators()

            self._initialized = True
            logger.info(f"策略初始化完成: {self.name}")

        except Exception as e:
            logger.error(f"策略初始化失败 {self.name}: {e}")
            raise

    async def cleanup(self) -> None:
        """
        清理策略

        保存状态，释放资源
        """
        try:
            await self._save_state()

            self._initialized = False
            self._running = False

            logger.info(f"策略清理完成: {self.name}")

        except Exception as e:
            logger.error(f"策略清理失败 {self.name}: {e}")

    async def on_market_data(self, symbol: str, data: Dict[str, Any]) -> None:
        """
        处理市场数据

        Args:
            symbol: 交易对
            data: 市场数据
        """
        try:
            # 存储数据
            self._market_data[symbol] = data

            # 调用具体的处理逻辑
            await self._process_market_data(symbol, data)

        except Exception as e:
            logger.error(f"处理市场数据失败 {self.name} {symbol}: {e}")

    async def generate_signals(self) -> List[TradingSignal]:
        """
        生成交易信号

        Returns:
            交易信号列表
        """
        signals = []

        try:
            # 调用具体的信号生成逻辑
            signals = await self._generate_signals()

            # 记录信号
            for signal in signals:
                signal.timestamp = datetime.now()
                self._signals.append(signal)

            logger.debug(f"策略 {self.name} 生成 {len(signals)} 个信号")

        except Exception as e:
            logger.error(f"生成信号失败 {self.name}: {e}")

        return signals

    async def on_order_filled(self, order_data: Dict[str, Any]) -> None:
        """
        处理订单成交

        Args:
            order_data: 订单数据
        """
        try:
            symbol = order_data.get("symbol")

            # 更新仓位
            if symbol in self._positions:
                # 更新现有仓位
                pass
            else:
                # 创建新仓位记录
                self._positions[symbol] = {
                    "quantity": order_data.get("filled_quantity", 0),
                    "avg_price": order_data.get("avg_fill_price", 0),
                    "side": order_data.get("side"),
                }

            logger.debug(f"策略 {self.name} 处理订单成交: {order_data.get('id')}")

        except Exception as e:
            logger.error(f"处理订单成交失败 {self.name}: {e}")

    # 需要子类实现的方法

    async def _load_data(self) -> None:
        """
        加载数据

        子类需要实现
        """
        raise NotImplementedError

    async def _calculate_indicators(self) -> None:
        """
        计算指标

        子类需要实现
        """
        raise NotImplementedError

    async def _process_market_data(self, symbol: str, data: Dict[str, Any]) -> None:
        """
        处理市场数据

        子类需要实现

        Args:
            symbol: 交易对
            data: 市场数据
        """
        raise NotImplementedError

    async def _generate_signals(self) -> List[TradingSignal]:
        """
        生成交易信号

        子类需要实现

        Returns:
            交易信号列表
        """
        raise NotImplementedError

    async def _save_state(self) -> None:
        """
        保存状态

        子类需要实现
        """
        pass  # 可选实现

    def is_active(self) -> bool:
        """检查策略是否活跃"""
        return self._running

    def activate(self):
        """激活策略"""
        self._running = True

    def deactivate(self):
        """停用策略"""
        self._running = False

    def update_parameters(self, params: Dict[str, Any]):
        """更新策略参数"""
        self.parameters.update(params)

    def get_performance(self) -> Dict[str, Any]:
        """获取策略性能"""
        return {
            "total_pnl": 0,
            "win_rate": 0,
            "sharpe_ratio": 0,
            "max_drawdown": 0
        }


class MLStrategy(BaseStrategy):
    """机器学习策略"""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.model_type = config.parameters.get("model_type", ModelType.LSTM)
        self.model_manager = None
        self.model_optimizer = None
    
    async def initialize(self, model_manager: ModelManager = None) -> None:
        """初始化策略"""
        await super().initialize()
        if model_manager:
            self.model_manager = model_manager
            self.model_optimizer = ModelOptimizer(model_manager, {})
            await self.model_optimizer.initialize()
    
    async def _generate_signals(self) -> List[TradingSignal]:
        """生成交易信号"""
        signals = []

        if not self.model_manager:
            return signals
        
        # 为每个交易对生成信号
        for symbol in self.symbols:
            if symbol not in self._market_data:
                continue
            
            # 准备特征
            data = self._market_data[symbol]
            features = await self._prepare_features(data)
            
            # 预测价格
            try:
                prediction = await self.model_manager.predict(self.model_type, features)
                
                # 生成信号
                current_price = data.get("close", 0)
                price_change = (prediction - current_price) / current_price
                
                if price_change > 0.01:
                    signal = TradingSignal(
                        signal_id=f"signal_{uuid.uuid4().hex[:8]}",
                        strategy_id=self.strategy_id,
                        instance_id="",
                        signal_type=SignalType.BUY,
                        symbol=symbol,
                        price=current_price,
                        quantity=0.1,
                        confidence=min(0.9, 0.5 + abs(price_change) * 10),
                        reason="机器学习模型预测价格上涨"
                    )
                    signals.append(signal)
                elif price_change < -0.01:
                    signal = TradingSignal(
                        signal_id=f"signal_{uuid.uuid4().hex[:8]}",
                        strategy_id=self.strategy_id,
                        instance_id="",
                        signal_type=SignalType.SELL,
                        symbol=symbol,
                        price=current_price,
                        quantity=0.1,
                        confidence=min(0.9, 0.5 + abs(price_change) * 10),
                        reason="机器学习模型预测价格下跌"
                    )
                    signals.append(signal)
            except Exception as e:
                logger.error(f"机器学习模型预测失败: {e}")
        
        return signals
    
    async def _prepare_features(self, data: Dict[str, Any]) -> np.ndarray:
        """准备特征"""
        # 从市场数据中提取特征
        features = []
        
        # 添加价格相关特征
        if "close" in data:
            features.append(data["close"])
        if "open" in data:
            features.append(data["open"])
        if "high" in data:
            features.append(data["high"])
        if "low" in data:
            features.append(data["low"])
        if "volume" in data:
            features.append(data["volume"])
        
        # 转换为numpy数组
        return np.array([features])


class StrategyManager:
    """
    策略管理器

    核心功能：
    1. 策略注册和加载
    2. 策略生命周期管理
    3. 参数管理
    4. 信号生成和过滤
    5. 性能分析
    6. 多策略组合和权重调整
    7. 自动策略切换
    8. 机器学习集成
    """

    def __init__(self, config_manager=None, data_provider=None, trade_engine=None):
        """
        初始化策略管理器

        Args:
            config_manager: 配置管理器实例
            data_provider: 数据提供者实例
            trade_engine: 交易引擎实例
        """
        self.config_manager = config_manager
        self.data_provider = data_provider
        self.trade_engine = trade_engine

        # 策略配置
        self.strategy_configs: Dict[str, StrategyConfig] = {}

        # 策略实例
        self.strategy_instances: Dict[str, StrategyInstance] = {}

        # 信号管理
        self.signals: Dict[str, TradingSignal] = {}
        self.signal_history: List[TradingSignal] = []

        # 性能分析
        self.performance_metrics: Dict[str, StrategyPerformance] = {}

        # 策略类注册
        self.strategy_classes: Dict[str, Type[BaseStrategy]] = {}

        # 多策略管理
        self.strategy_weights: Dict[str, float] = {}
        self.best_strategy = None
        self.switch_threshold = 0.05  # 切换阈值
        self.evaluation_period = 3600  # 评估周期（秒）
        self.last_evaluation_time = time.time()

        # 机器学习集成
        self.model_manager: Optional[ModelManager] = None
        self.market_regime = MarketRegime.SIDEWAYS

        # 任务和锁
        self._tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._initialized = False
        self._running = False
        self._last_pool_prune_at: Optional[datetime] = None
        self._last_daily_optimization_date: Optional[str] = None
        self._daily_optimization_cursor: int = 0
        self._daily_optimization_status: Dict[str, Any] = {
            "date": None,
            "completed": False,
            "processed": 0,
            "total": 0,
            "drawdown_optimized": 0,
            "started_at": None,
            "finished_at": None,
            "last_batch_ms": 0.0,
        }
        self._optimization_runtime_config: Dict[str, Any] = {
            "pool_limit": 30,
            "prune_interval_seconds": 3600,
            "daily_batch_size": 6,
            "daily_batch_time_budget_sec": 1.5,
            "daily_opt_cycle_seconds": 300,
        }
        self._signal_runtime_config: Dict[str, Any] = {
            "max_parallel_signal_tasks": 4,
        }
        self._deployment_runtime_config: Dict[str, Any] = {
            "promote_min_score": 0.95,
            "promote_min_trades": 20,
            "demote_max_drawdown": 0.35,
            "demote_min_score": 0.2,
        }
        self._market_structure_runtime_config: Dict[str, Any] = {
            "observe_cap_multiplier": 0.5,
            "observe_conflict_threshold": 0.55,
            "restore_min_confidence": 0.55,
            "restore_stable_cycles": 2,
        }
        self._latest_market_structure_snapshots: Dict[str, Dict[str, Any]] = {}
        self._last_trade_feedback_opt_at: Optional[datetime] = None

        logger.info("策略管理器初始化完成")

    async def initialize(self, model_manager: Optional[ModelManager] = None) -> None:
        """
        初始化策略管理器

        加载配置，注册默认策略
        """
        if self._initialized:
            return

        logger.info("初始化策略管理器...")

        try:
            # 加载策略配置
            await self._load_strategy_configs()

            # 注册默认策略类
            await self._register_default_strategies()

            # 设置模型管理器
            self.model_manager = model_manager

            # 启动监控任务
            self._tasks.append(asyncio.create_task(self._monitoring_worker()))
            self._tasks.append(asyncio.create_task(self._performance_calculation_worker()))

            self._initialized = True
            logger.info("策略管理器初始化完成")

        except Exception as e:
            logger.error(f"策略管理器初始化失败: {e}")
            traceback.print_exc()

    async def cleanup(self) -> None:
        """
        清理策略管理器

        停止所有策略，保存状态
        """
        logger.info("清理策略管理器...")

        self._running = False

        # 停止所有策略
        for instance_id in list(self.strategy_instances.keys()):
            await self.stop_strategy(instance_id)

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()

        # 保存状态
        await self._save_state()

        self._initialized = False
        logger.info("策略管理器清理完成")

    async def register_strategy_class(
        self, class_name: str, strategy_class: Type[BaseStrategy]
    ) -> bool:
        """
        注册策略类

        Args:
            class_name: 类名
            strategy_class: 策略类

        Returns:
            是否注册成功
        """
        async with self._lock:
            if class_name in self.strategy_classes:
                logger.warning(f"策略类已存在: {class_name}")
                return False

            self.strategy_classes[class_name] = strategy_class
            logger.info(f"注册策略类: {class_name}")
            return True

    async def load_strategy_config(self, config_data: Dict[str, Any]) -> Optional[StrategyConfig]:
        """
        加载策略配置

        Args:
            config_data: 配置数据

        Returns:
            策略配置或None
        """
        try:
            # 验证必要字段
            required_fields = ["strategy_id", "name", "strategy_type"]
            for field in required_fields:
                if field not in config_data:
                    logger.error(f"策略配置缺少必要字段: {field}")
                    return None

            md = config_data.get("metadata", {}) if isinstance(config_data.get("metadata", {}), dict) else {}
            if "deployment" not in md:
                sid = str(config_data.get("strategy_id", ""))
                if sid.startswith(("default_", "combined_")):
                    md["deployment"] = {"stage": "full", "cap_multiplier": 1.0}
                else:
                    md["deployment"] = {"stage": "shadow", "cap_multiplier": 0.25}
            lifecycle_stage = self._infer_lifecycle_stage(config_data, md)
            oos_status = self._infer_oos_status(md)
            live_drift_status = self._infer_live_drift_status(md)

            # 创建配置
            config = StrategyConfig(
                strategy_id=config_data["strategy_id"],
                name=config_data["name"],
                description=config_data.get("description", ""),
                strategy_type=StrategyType(config_data["strategy_type"]),
                enabled=config_data.get("enabled", True),
                version=config_data.get("version", "1.0.0"),
                author=config_data.get("author", ""),
                parameters=config_data.get("parameters", {}),
                symbols=config_data.get("symbols", []),
                timeframe=config_data.get("timeframe", "1h"),
                initial_capital=config_data.get("initial_capital", 10000.0),
                metadata=md,
                stage=lifecycle_stage,
                oos_status=oos_status,
                live_drift_status=live_drift_status,
            )

            # 保存配置
            async with self._lock:
                self.strategy_configs[config.strategy_id] = config

            logger.info(f"加载策略配置: {config.name} ({config.strategy_id})")
            return config

        except Exception as e:
            logger.error(f"加载策略配置失败: {e}")
            traceback.print_exc()
            return None

    async def create_strategy_instance(
        self, strategy_id: str, class_name: Optional[str] = None
    ) -> Optional[str]:
        """
        创建策略实例

        Args:
            strategy_id: 策略ID
            class_name: 策略类名（可选）

        Returns:
            实例ID或None
        """
        async with self._lock:
            if strategy_id not in self.strategy_configs:
                logger.error(f"策略配置不存在: {strategy_id}")
                return None

            config = self.strategy_configs[strategy_id]

            if not config.enabled:
                logger.error(f"策略已禁用: {strategy_id}")
                return None

            # 生成实例ID
            instance_id = f"{strategy_id}_{uuid.uuid4().hex[:8]}"

            # 获取策略类
            strategy_class = None

            if class_name:
                # 使用指定的类名
                if class_name in self.strategy_classes:
                    strategy_class = self.strategy_classes[class_name]
                else:
                    logger.error(f"策略类不存在: {class_name}")
                    return None
            else:
                # 根据策略类型选择默认类
                default_class_name = f"{config.strategy_type.value}_strategy"
                if default_class_name in self.strategy_classes:
                    strategy_class = self.strategy_classes[default_class_name]
                else:
                    # 回退到基础策略
                    strategy_class = BaseStrategy

            try:
                # 创建策略实例
                strategy_instance = strategy_class(config)

                # 如果是机器学习策略，初始化模型
                if isinstance(strategy_instance, MLStrategy) and self.model_manager:
                    await strategy_instance.initialize(self.model_manager)

                # 创建实例记录
                instance = StrategyInstance(
                    instance_id=instance_id,
                    config=config,
                    status=StrategyStatus.CREATED,
                    instance=strategy_instance,
                )

                self.strategy_instances[instance_id] = instance
                self.strategy_weights[instance_id] = 1.0 / len(self.strategy_instances) if self.strategy_instances else 1.0

                logger.info(f"创建策略实例: {config.name} -> {instance_id}")
                return instance_id

            except Exception as e:
                logger.error(f"创建策略实例失败 {strategy_id}: {e}")
                return None

    async def initialize_strategy(self, instance_id: str) -> bool:
        """
        初始化策略

        Args:
            instance_id: 实例ID

        Returns:
            是否初始化成功
        """
        async with self._lock:
            if instance_id not in self.strategy_instances:
                logger.error(f"策略实例不存在: {instance_id}")
                return False

            instance = self.strategy_instances[instance_id]

            if instance.status != StrategyStatus.CREATED:
                logger.warning(f"策略实例状态错误: {instance_id} 状态={instance.status.value}")
                return False

            instance.status = StrategyStatus.INITIALIZING

        try:
            # 初始化策略
            if instance.instance:
                await instance.instance.initialize()

            async with self._lock:
                instance.status = StrategyStatus.READY
                logger.info(f"策略初始化完成: {instance_id}")
                return True

        except Exception as e:
            async with self._lock:
                instance.status = StrategyStatus.ERROR
                logger.error(f"策略初始化失败 {instance_id}: {e}")
                return False

    async def start_strategy(self, instance_id: str) -> bool:
        """
        启动策略

        Args:
            instance_id: 实例ID

        Returns:
            是否启动成功
        """
        async with self._lock:
            if instance_id not in self.strategy_instances:
                logger.error(f"策略实例不存在: {instance_id}")
                return False

            instance = self.strategy_instances[instance_id]

            if instance.status != StrategyStatus.READY:
                logger.warning(f"策略实例状态错误: {instance_id} 状态={instance.status.value}")
                return False

            instance.status = StrategyStatus.RUNNING
            instance.started_at = datetime.now()
            
            # 激活策略
            if instance.instance:
                instance.instance.activate()

        logger.info(f"启动策略: {instance_id}")
        return True

    async def stop_strategy(self, instance_id: str) -> bool:
        """
        停止策略

        Args:
            instance_id: 实例ID

        Returns:
            是否停止成功
        """
        async with self._lock:
            if instance_id not in self.strategy_instances:
                logger.error(f"策略实例不存在: {instance_id}")
                return False

            instance = self.strategy_instances[instance_id]

            if instance.status not in [StrategyStatus.RUNNING, StrategyStatus.PAUSED]:
                logger.warning(f"策略实例状态错误: {instance_id} 状态={instance.status.value}")
                return False

            instance.status = StrategyStatus.STOPPED
            instance.stopped_at = datetime.now()
            
            # 停用策略
            if instance.instance:
                instance.instance.deactivate()

        try:
            # 清理策略
            if instance.instance:
                await instance.instance.cleanup()

            logger.info(f"停止策略: {instance_id}")
            return True

        except Exception as e:
            logger.error(f"停止策略失败 {instance_id}: {e}")
            return False

    async def pause_strategy(self, instance_id: str) -> bool:
        """
        暂停策略

        Args:
            instance_id: 实例ID

        Returns:
            是否暂停成功
        """
        async with self._lock:
            if instance_id not in self.strategy_instances:
                logger.error(f"策略实例不存在: {instance_id}")
                return False

            instance = self.strategy_instances[instance_id]

            if instance.status != StrategyStatus.RUNNING:
                logger.warning(f"策略实例状态错误: {instance_id} 状态={instance.status.value}")
                return False

            instance.status = StrategyStatus.PAUSED
            
            # 停用策略
            if instance.instance:
                instance.instance.deactivate()
                
            logger.info(f"暂停策略: {instance_id}")
            return True

    async def resume_strategy(self, instance_id: str) -> bool:
        """
        恢复策略

        Args:
            instance_id: 实例ID

        Returns:
            是否恢复成功
        """
        async with self._lock:
            if instance_id not in self.strategy_instances:
                logger.error(f"策略实例不存在: {instance_id}")
                return False

            instance = self.strategy_instances[instance_id]

            if instance.status != StrategyStatus.PAUSED:
                logger.warning(f"策略实例状态错误: {instance_id} 状态={instance.status.value}")
                return False

            instance.status = StrategyStatus.RUNNING
            
            # 激活策略
            if instance.instance:
                instance.instance.activate()
                
            logger.info(f"恢复策略: {instance_id}")
            return True

    async def get_strategy_instance(self, instance_id: str) -> Optional[StrategyInstance]:
        """
        获取策略实例

        Args:
            instance_id: 实例ID

        Returns:
            策略实例或None
        """
        return self.strategy_instances.get(instance_id)

    async def get_strategy_instances(
        self, strategy_id: Optional[str] = None, status: Optional[StrategyStatus] = None
    ) -> List[StrategyInstance]:
        """
        获取策略实例列表

        Args:
            strategy_id: 过滤策略ID
            status: 过滤状态

        Returns:
            策略实例列表
        """
        instances = list(self.strategy_instances.values())

        if strategy_id:
            instances = [i for i in instances if i.config.strategy_id == strategy_id]

        if status:
            instances = [i for i in instances if i.status == status]

        return instances

    async def process_market_data(self, symbol: str, data: Dict[str, Any]) -> List[TradingSignal]:
        """
        处理市场数据

        Args:
            symbol: 交易对
            data: 市场数据

        Returns:
            生成的信号列表
        """
        all_signals = []

        try:
            # Pull unified snapshot once per symbol/tick and share across all running strategies.
            unified_snapshot = await self._get_unified_snapshot(symbol)
            quality_score = self._extract_quality_score(unified_snapshot)

            # 检测市场状态
            await self._detect_market_regime(data)
            
            # 定期评估策略性能并切换
            if time.time() - self.last_evaluation_time >= self.evaluation_period:
                await self._evaluate_strategies()
                self.last_evaluation_time = time.time()

            # 找到关注此交易对的运行中策略
            running_instances = await self.get_strategy_instances(status=StrategyStatus.RUNNING)

            max_parallel = max(1, int(self._signal_runtime_config.get("max_parallel_signal_tasks", 4) or 4))
            sem = asyncio.Semaphore(max_parallel)
            target_instances = [i for i in running_instances if symbol in i.config.symbols]

            async def _run_instance(instance: StrategyInstance) -> List[TradingSignal]:
                async with sem:
                    try:
                        if not instance.instance:
                            return []
                        await instance.instance.on_market_data(symbol, data)
                        signals = await instance.instance.generate_signals()
                        out: List[TradingSignal] = []
                        for signal in signals:
                            signal.strategy_id = instance.config.strategy_id
                            signal.instance_id = instance.instance_id
                            signal.signal_id = f"signal_{uuid.uuid4().hex[:8]}"
                            stage = self._get_deployment_stage(instance.config)
                            mult = self._get_effective_cap_multiplier(instance.config)
                            base_conf = max(0.0, min(1.0, float(signal.confidence or 0.0) * mult))
                            # Soft quality weighting: never hard-drop signals, only smooth confidence.
                            if quality_score is not None:
                                q_weight = max(0.75, min(1.05, 0.75 + 0.30 * float(quality_score)))
                                signal.confidence = max(0.0, min(1.0, base_conf * q_weight))
                            else:
                                signal.confidence = base_conf
                            signal.metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
                            signal.metadata["deployment_stage"] = stage
                            signal.metadata["cap_multiplier"] = mult
                            if unified_snapshot:
                                signal.metadata["unified_quality_score"] = quality_score
                                signal.metadata["data_provenance"] = (
                                    (unified_snapshot.get("数据来源状态") or {}).get("provenance")
                                    if isinstance(unified_snapshot, dict)
                                    else None
                                )
                                # analysis moved to MarketIntelligenceEngine (data hub is collector-only)
                                try:
                                    mc = getattr(self.trade_engine, "main_controller", None) if self.trade_engine else None
                                    mi = getattr(mc, "market_intelligence", None) if mc else None
                                    if mi and hasattr(mi, "get_symbol_view"):
                                        view = await mi.get_symbol_view(symbol, include_snapshot=False)
                                        signal.metadata["market_intelligence"] = (
                                            view.to_dict() if hasattr(view, "to_dict") else {}
                                        )
                                except Exception:
                                    signal.metadata["market_intelligence"] = {}
                            out.append(signal)
                        return out
                    except Exception as e:
                        logger.error(f"策略处理市场数据失败 {instance.instance_id}: {e}")
                        return []

            per_instance_signals = await asyncio.gather(
                *[asyncio.create_task(_run_instance(inst)) for inst in target_instances],
                return_exceptions=False,
            )

            for inst, signals in zip(target_instances, per_instance_signals):
                for signal in signals:
                    async with self._lock:
                        self.signals[signal.signal_id] = signal
                        self.signal_history.append(signal)
                        if len(self.signal_history) > 10000:
                            self.signal_history = self.signal_history[-10000:]
                    inst.last_signal_at = datetime.now()
                    inst.total_signals += 1
                    all_signals.append(signal)

            if all_signals:
                logger.debug(f"处理市场数据生成 {len(all_signals)} 个信号: {symbol}")

        except Exception as e:
            logger.error(f"处理市场数据失败: {e}")

        return all_signals

    async def _get_unified_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Best-effort unified data snapshot accessor."""
        te = self.trade_engine
        mc = getattr(te, "main_controller", None) if te else None
        hub = getattr(mc, "data_source_hub", None) if mc else None
        if not hub or not hasattr(hub, "get_unified_snapshot"):
            return None
        try:
            snap = await hub.get_unified_snapshot(symbol)
            return snap if isinstance(snap, dict) else None
        except Exception:
            return None

    @staticmethod
    def _extract_quality_score(snapshot: Optional[Dict[str, Any]]) -> Optional[float]:
        if not isinstance(snapshot, dict):
            return None
        q = snapshot.get("数据质量评估", {})
        if not isinstance(q, dict):
            return None
        try:
            return float(q.get("score")) if q.get("score") is not None else None
        except Exception:
            return None

    async def get_signals(
        self,
        strategy_id: Optional[str] = None,
        instance_id: Optional[str] = None,
        signal_type: Optional[SignalType] = None,
        limit: int = 100,
    ) -> List[TradingSignal]:
        """
        获取信号

        Args:
            strategy_id: 过滤策略ID
            instance_id: 过滤实例ID
            signal_type: 过滤信号类型
            limit: 限制数量

        Returns:
            信号列表
        """
        signals = list(self.signals.values())

        if strategy_id:
            signals = [s for s in signals if s.strategy_id == strategy_id]

        if instance_id:
            signals = [s for s in signals if s.instance_id == instance_id]

        if signal_type:
            signals = [s for s in signals if s.signal_type == signal_type]

        # 按时间排序（最新的在前面）
        signals.sort(key=lambda s: s.timestamp, reverse=True)

        return signals[:limit]

    async def get_strategy_performance(self, strategy_id: str) -> Optional[StrategyPerformance]:
        """
        获取策略性能

        Args:
            strategy_id: 策略ID

        Returns:
            策略性能或None
        """
        return self.performance_metrics.get(strategy_id)

    async def update_strategy_parameters(
        self, instance_id: str, parameters: Dict[str, Any]
    ) -> bool:
        """
        更新策略参数

        Args:
            instance_id: 实例ID
            parameters: 新参数

        Returns:
            是否更新成功
        """
        async with self._lock:
            if instance_id not in self.strategy_instances:
                logger.error(f"策略实例不存在: {instance_id}")
                return False

            instance = self.strategy_instances[instance_id]

            # 只能更新未运行或暂停的策略
            if instance.status == StrategyStatus.RUNNING:
                logger.error(f"无法更新运行中的策略: {instance_id}")
                return False

            # 更新配置
            instance.config.parameters.update(parameters)
            instance.config.updated_at = datetime.now()
            
            # 更新策略实例参数
            if instance.instance:
                instance.instance.update_parameters(parameters)

            logger.info(f"更新策略参数: {instance_id}")
            return True

    async def backtest_strategy(
        self,
        strategy_id: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 10000.0,
        slippage: float = 0.0005,
        commission: float = 0.001,
        data_source: str = "binance"
    ) -> Dict[str, Any]:
        """
        回测策略

        Args:
            strategy_id: 策略ID
            start_date: 开始日期
            end_date: 结束日期
            initial_capital: 初始资金
            slippage: 滑点率
            commission: 佣金率
            data_source: 数据源

        Returns:
            回测结果
        """
        logger.info(f"开始回测策略: {strategy_id} ({start_date} 到 {end_date})")

        if strategy_id not in self.strategy_configs:
            logger.error(f"策略配置不存在: {strategy_id}")
            return {
                "error": "策略配置不存在",
                "backtest_completed": False
            }

        config = self.strategy_configs[strategy_id]
        
        # 模拟回测逻辑
        try:
            # 计算回测时间跨度
            days = (end_date - start_date).days
            if days <= 0:
                return {
                    "error": "结束日期必须晚于开始日期",
                    "backtest_completed": False
                }

            # 模拟交易数据
            trades = []
            portfolio_value = initial_capital
            peak_value = initial_capital
            max_drawdown = 0.0
            winning_trades = 0
            losing_trades = 0
            total_profit = 0
            total_loss = 0
            
            # 生成模拟交易
            import random
            num_trades = random.randint(20, 100)
            
            for i in range(num_trades):
                # 随机生成交易
                trade_date = start_date + timedelta(days=random.uniform(0, days))
                trade_size = random.uniform(0.1, 0.5) * portfolio_value
                trade_return = random.normalvariate(0.005, 0.02)  # 平均0.5%收益，标准差2%
                
                # 计算交易结果
                trade_profit = trade_size * trade_return
                portfolio_value += trade_profit
                
                # 计算佣金和滑点
                cost = trade_size * (commission + slippage)
                portfolio_value -= cost
                
                # 更新最大回撤
                if portfolio_value > peak_value:
                    peak_value = portfolio_value
                current_drawdown = (peak_value - portfolio_value) / peak_value
                max_drawdown = max(max_drawdown, current_drawdown)
                
                # 统计交易结果
                if trade_profit > 0:
                    winning_trades += 1
                    total_profit += trade_profit
                else:
                    losing_trades += 1
                    total_loss += abs(trade_profit)
                
                trades.append({
                    "date": trade_date.isoformat(),
                    "size": trade_size,
                    "return": trade_return,
                    "profit": trade_profit,
                    "portfolio_value": portfolio_value
                })
            
            # 计算性能指标
            total_return = (portfolio_value - initial_capital) / initial_capital
            annualized_return = (1 + total_return) ** (365 / days) - 1 if days > 0 else 0
            
            # 计算夏普比率（假设无风险利率为2%）
            if trades:
                daily_returns = []
                prev_value = initial_capital
                for trade in trades:
                    curr_value = trade["portfolio_value"]
                    daily_return = (curr_value - prev_value) / prev_value
                    daily_returns.append(daily_return)
                    prev_value = curr_value
                
                if len(daily_returns) > 1:
                    import statistics
                    mean_return = statistics.mean(daily_returns)
                    std_return = statistics.stdev(daily_returns)
                    sharpe_ratio = (mean_return - 0.02/365) / std_return * (365 ** 0.5) if std_return > 0 else 0
                else:
                    sharpe_ratio = 0
            else:
                sharpe_ratio = 0
            
            # 计算胜率和盈利因子
            win_rate = winning_trades / num_trades if num_trades > 0 else 0
            profit_factor = total_profit / total_loss if total_loss > 0 else 0
            
            result = {
                "strategy_id": strategy_id,
                "strategy_name": config.name,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "initial_capital": initial_capital,
                "final_capital": portfolio_value,
                "total_return": total_return,
                "annualized_return": annualized_return,
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": max_drawdown,
                "total_trades": num_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": win_rate,
                "profit_factor": profit_factor,
                "avg_trade_return": total_return / num_trades if num_trades > 0 else 0,
                "backtest_completed": True,
                "timestamp": datetime.now().isoformat(),
                "trades": trades[:10]  # 只返回前10笔交易
            }
            
            logger.info(f"回测完成: {strategy_id}, 收益: {total_return*100:.2f}%")
            return result
            
        except Exception as e:
            logger.error(f"回测失败: {e}")
            return {
                "error": str(e),
                "backtest_completed": False
            }

    async def export_strategy_config(self, strategy_id: str, format: str = "json") -> Optional[str]:
        """
        导出策略配置

        Args:
            strategy_id: 策略ID
            format: 格式（json/yaml）

        Returns:
            配置字符串或None
        """
        if strategy_id not in self.strategy_configs:
            return None

        config = self.strategy_configs[strategy_id]
        config_dict = config.to_dict()

        try:
            if format.lower() == "json":
                return json.dumps(config_dict, indent=2, ensure_ascii=False)
            elif format.lower() == "yaml":
                return yaml.dump(config_dict, default_flow_style=False, allow_unicode=True)
            else:
                logger.error(f"不支持的格式: {format}")
                return None

        except Exception as e:
            logger.error(f"导出策略配置失败: {e}")
            return None

    async def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计信息
        """
        async with self._lock:
            total_instances = len(self.strategy_instances)
            running_instances = len(
                [i for i in self.strategy_instances.values() if i.status == StrategyStatus.RUNNING]
            )
            total_signals = len(self.signals)
            total_strategies = len(self.strategy_configs)

            return {
                "total_strategies": total_strategies,
                "total_instances": total_instances,
                "running_instances": running_instances,
                "paused_instances": len(
                    [
                        i
                        for i in self.strategy_instances.values()
                        if i.status == StrategyStatus.PAUSED
                    ]
                ),
                "stopped_instances": len(
                    [
                        i
                        for i in self.strategy_instances.values()
                        if i.status == StrategyStatus.STOPPED
                    ]
                ),
                "total_signals": total_signals,
                "signals_last_24h": len(
                    [
                        s
                        for s in self.signal_history
                        if s.timestamp > datetime.now() - timedelta(hours=24)
                    ]
                ),
                "performance_metrics_count": len(self.performance_metrics),
                "best_strategy": self.best_strategy,
                "market_regime": self.market_regime.value,
                "timestamp": datetime.now().isoformat(),
            }

    # 多策略管理方法
    
    async def get_aggregated_signal(self, symbol: str, data: Dict[str, Any]) -> TradingSignal:
        """
        获取聚合信号

        Args:
            symbol: 交易对
            data: 市场数据

        Returns:
            聚合信号
        """
        # 生成所有策略的信号
        signals = await self.process_market_data(symbol, data)
        
        if not signals:
            return TradingSignal(
                signal_id=f"signal_{uuid.uuid4().hex[:8]}",
                strategy_id="aggregated",
                instance_id="",
                signal_type=SignalType.HOLD,
                symbol=symbol,
                price=data.get("close"),
                confidence=0.5
            )
        
        # 计算加权信号
        buy_score = 0.0
        sell_score = 0.0
        total_weight = 0.0
        
        for signal in signals:
            weight = self.strategy_weights.get(signal.instance_id, 1.0)
            if signal.signal_type == SignalType.BUY:
                buy_score += signal.confidence * weight
            elif signal.signal_type == SignalType.SELL:
                sell_score += signal.confidence * weight
            total_weight += weight
        
        if total_weight > 0:
            buy_score /= total_weight
            sell_score /= total_weight
        
        # 确定最终信号
        if buy_score > sell_score and buy_score > 0.6:
            signal_type = SignalType.BUY
            confidence = buy_score
        elif sell_score > buy_score and sell_score > 0.6:
            signal_type = SignalType.SELL
            confidence = sell_score
        else:
            signal_type = SignalType.HOLD
            confidence = 0.5
        
        return TradingSignal(
            signal_id=f"signal_{uuid.uuid4().hex[:8]}",
            strategy_id="aggregated",
            instance_id="",
            signal_type=signal_type,
            symbol=symbol,
            price=data.get("close"),
            confidence=confidence,
            metadata={"buy_score": buy_score, "sell_score": sell_score}
        )

    async def set_strategy_weight(self, instance_id: str, weight: float):
        """
        设置策略权重

        Args:
            instance_id: 实例ID
            weight: 权重值
        """
        if instance_id in self.strategy_instances:
            self.strategy_weights[instance_id] = weight
            # 归一化权重
            total_weight = sum(self.strategy_weights.values())
            if total_weight > 0:
                for sid in self.strategy_weights:
                    self.strategy_weights[sid] /= total_weight

    async def get_strategy_weights(self) -> Dict[str, float]:
        """
        获取策略权重

        Returns:
            策略权重字典
        """
        return self.strategy_weights

    # 私有方法

    async def _load_strategy_configs(self) -> None:
        """加载策略配置"""
        loaded_from_config = False
        if self.config_manager:
            try:
                strategies_config = await self.config_manager.get_config("strategies", {})
                strategies_list = strategies_config.get("strategies", [])
                
                if strategies_list:
                    for strategy_data in strategies_list:
                        try:
                            await self.load_strategy_config(strategy_data)
                            loaded_from_config = True
                        except Exception as e:
                            logger.error(f"加载策略配置失败: {e}")
            except Exception as e:
                logger.warning(f"获取策略配置失败: {e}")

        # 没有外部配置时注入最小默认策略，保证基础运行和测试
        if not self.strategy_configs:
            try:
                templates = await self.get_strategy_templates()
                # 注入多套默认策略，覆盖更多交易对，提升策略可用性
                for tpl_key in ["trend_following_ma", "mean_reversion_bollinger", "ml_based"]:
                    tpl = templates.get(tpl_key)
                    if not tpl:
                        continue
                    await self.load_strategy_config(
                        {"strategy_id": f"default_{tpl_key}", **tpl}
                    )
                logger.info("未加载任何策略配置，已注入默认策略配置（多策略）")
            except Exception as e:
                logger.info(f"未加载任何策略配置，默认策略注入失败: {e}")

    async def create_ai_strategy(self, strategy_data: Dict) -> Optional[str]:
        """AI动态创建策略"""
        try:
            strategy_id = strategy_data.get('strategy_id', f"ai_{datetime.now().strftime('%Y%m%d%H%M%S')}")
            
            config = StrategyConfig(
                strategy_id=strategy_id,
                name=strategy_data.get('name', 'AI Generated Strategy'),
                description=strategy_data.get('description', 'AI自主生成策略'),
                strategy_type=StrategyType(strategy_data.get('strategy_type', 'trend_following')),
                parameters=strategy_data.get('parameters', {}),
                symbols=strategy_data.get('symbols', []),
                timeframe=strategy_data.get('timeframe', '1h'),
                initial_capital=strategy_data.get('initial_capital', 10000.0),
                enabled=True,
            )
            
            self.strategy_configs[strategy_id] = config
            logger.info(f"✅ AI创建策略成功: {config.name} ({strategy_id})")
            
            return strategy_id
            
        except Exception as e:
            logger.error(f"AI创建策略失败: {e}")
            return None

    async def combine_strategies(self, strategy_ids: List[str], combination_type: str = "parallel") -> Optional[str]:
        """组合多个策略"""
        try:
            combined_id = f"combined_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            combined_name = f"组合策略_{len(strategy_ids)}个"
            
            combined_params = {
                "strategies": strategy_ids,
                "combination_type": combination_type,
                "weights": {sid: 1.0/len(strategy_ids) for sid in strategy_ids}
            }
            
            all_symbols = set()
            for sid in strategy_ids:
                if sid in self.strategy_configs:
                    all_symbols.update(self.strategy_configs[sid].symbols)
            
            config = StrategyConfig(
                strategy_id=combined_id,
                name=combined_name,
                description=f"AI组合策略 - {combination_type}模式",
                strategy_type=StrategyType.COMBINATION,
                parameters=combined_params,
                symbols=list(all_symbols),
                timeframe="1h",
                initial_capital=10000.0,
                enabled=True,
            )
            
            self.strategy_configs[combined_id] = config
            logger.info(f"✅ AI组合策略成功: {combined_name} ({combined_id})")
            
            return combined_id
            
        except Exception as e:
            logger.error(f"组合策略失败: {e}")
            return None

    async def _register_default_strategies(self) -> None:
        """注册默认策略类"""
        # 注册基础策略类
        await self.register_strategy_class("base_strategy", BaseStrategy)
        await self.register_strategy_class("ml_strategy", MLStrategy)

        logger.info(f"注册 {len(self.strategy_classes)} 个策略类")

    async def get_strategy_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        获取预定义策略模板

        Returns:
            策略模板字典
        """
        templates = {
            "trend_following_ma": {
                "name": "移动平均趋势跟踪",
                "description": "基于双移动平均线的趋势跟踪策略",
                "strategy_type": StrategyType.TREND_FOLLOWING.value,
                "parameters": {
                    "fast_ma_period": 10,
                    "slow_ma_period": 30,
                    "stop_loss_pct": 0.05,
                    "take_profit_pct": 0.1,
                },
                "symbols": ["BTC/USDT", "ETH/USDT"],
                "timeframe": "1h",
                "initial_capital": 10000.0,
                "recommended_class": "base_strategy"
            },
            "mean_reversion_bollinger": {
                "name": "布林带均值回归",
                "description": "基于布林带的均值回归策略",
                "strategy_type": StrategyType.MEAN_REVERSION.value,
                "parameters": {
                    "bb_period": 20,
                    "bb_std": 2.0,
                    "rsi_period": 14,
                    "rsi_overbought": 70,
                    "rsi_oversold": 30,
                },
                "symbols": ["BTC/USDT", "ETH/USDT", "BNB/USDT"],
                "timeframe": "30m",
                "initial_capital": 5000.0,
                "recommended_class": "base_strategy"
            },
            "ml_based": {
                "name": "机器学习策略",
                "description": "基于机器学习模型的预测策略",
                "strategy_type": StrategyType.ML_BASED.value,
                "parameters": {
                    "model_type": "LSTM",
                    "prediction_horizon": 1,
                    "confidence_threshold": 0.6,
                },
                "symbols": ["BTC/USDT", "ETH/USDT"],
                "timeframe": "1h",
                "initial_capital": 10000.0,
                "recommended_class": "ml_strategy"
            }
        }
        return templates

    async def create_strategy_from_template(self, template_id: str, custom_params: Dict[str, Any] = None) -> Optional[str]:
        """
        从模板创建策略

        Args:
            template_id: 模板ID
            custom_params: 自定义参数

        Returns:
            策略ID或None
        """
        templates = await self.get_strategy_templates()
        if template_id not in templates:
            logger.error(f"策略模板不存在: {template_id}")
            return None

        template = templates[template_id]
        
        # 生成唯一策略ID
        strategy_id = f"{template_id}_{uuid.uuid4().hex[:8]}"
        
        # 合并参数
        params = template["parameters"].copy()
        if custom_params:
            params.update(custom_params)
        
        # 创建策略配置
        config_data = {
            "strategy_id": strategy_id,
            "name": template["name"],
            "description": template["description"],
            "strategy_type": template["strategy_type"],
            "parameters": params,
            "symbols": template["symbols"],
            "timeframe": template["timeframe"],
            "initial_capital": template["initial_capital"],
            "metadata": {
                "template_id": template_id,
                "recommended_class": template["recommended_class"]
            }
        }
        
        # 加载策略配置
        config = await self.load_strategy_config(config_data)
        if not config:
            return None
        
        logger.info(f"从模板创建策略: {strategy_id} (模板: {template_id})")
        return strategy_id
    
    async def create_ai_strategy(self, strategy_logic: str, name: str = None, 
                                  strategy_type: StrategyType = StrategyType.AI_GENERATED,
                                  symbols: List[str] = None, parameters: Dict[str, Any] = None) -> Optional[str]:
        """
        AI自主创建策略 - 无模板限制
        
        Args:
            strategy_logic: 策略逻辑描述或代码
            name: 策略名称
            strategy_type: 策略类型
            symbols: 交易对列表
            parameters: 策略参数
            
        Returns:
            策略ID或None
        """
        try:
            strategy_id = f"ai_strategy_{uuid.uuid4().hex[:8]}"
            
            strategy_name = name or f"AI策略_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            config_data = {
                "strategy_id": strategy_id,
                "name": strategy_name,
                "description": f"AI自主开发策略: {strategy_logic[:100]}...",
                "strategy_type": strategy_type,
                "parameters": parameters or {},
                "symbols": symbols or ["BTC/USDT", "SOL/USDT", "BNB/USDT"],
                "timeframe": "1h",
                "initial_capital": 10000.0,
                "metadata": {
                    "ai_generated": True,
                    "strategy_logic": strategy_logic,
                    "created_by": "ai_autonomous",
                    "can_modify": True
                }
            }
            
            config = await self.load_strategy_config(config_data)
            if not config:
                return None
            
            logger.info(f"✅ AI自主创建策略: {strategy_id}")
            return strategy_id
            
        except Exception as e:
            logger.error(f"AI创建策略失败: {e}")
            return None
    
    async def combine_strategies(self, strategy_ids: List[str], weights: Dict[str, float] = None,
                                  combination_mode: str = "weighted") -> Optional[str]:
        """
        组合多个策略
        
        Args:
            strategy_ids: 要组合的策略ID列表
            weights: 各策略权重
            combination_mode: 组合模式 (weighted, voting, parallel, serial)
            
        Returns:
            组合策略ID或None
        """
        try:
            if not strategy_ids:
                return None
            
            combined_id = f"combined_{uuid.uuid4().hex[:8]}"
            
            if weights is None:
                weight_per_strategy = 1.0 / len(strategy_ids)
                weights = {sid: weight_per_strategy for sid in strategy_ids}
            
            config_data = {
                "strategy_id": combined_id,
                "name": f"组合策略_{len(strategy_ids)}个",
                "description": f"组合策略: {', '.join(strategy_ids)}",
                "strategy_type": StrategyType.COMBINATION,
                "parameters": {
                    "component_strategies": strategy_ids,
                    "weights": weights,
                    "combination_mode": combination_mode
                },
                "symbols": [],
                "timeframe": "1h",
                "initial_capital": 10000.0,
                "metadata": {
                    "combination": True,
                    "auto_rebalance": True
                }
            }
            
            for sid in strategy_ids:
                if sid in self.strategy_configs:
                    for symbol in self.strategy_configs[sid].symbols:
                        if symbol not in config_data["symbols"]:
                            config_data["symbols"].append(symbol)
            
            config = await self.load_strategy_config(config_data)
            if not config:
                return None
            
            logger.info(f"✅ 创建组合策略: {combined_id} = {strategy_ids}")
            return combined_id
            
        except Exception as e:
            logger.error(f"组合策略失败: {e}")
            return None
    
    async def auto_switch_strategy(self, market_condition: str = None) -> bool:
        """
        根据市场条件自动切换策略
        
        Args:
            market_condition: 市场条件描述
            
        Returns:
            是否成功切换
        """
        try:
            active_instances = [
                (iid, inst) for iid, inst in self.strategy_instances.items()
                if inst.status == StrategyStatus.RUNNING
            ]
            
            if not active_instances:
                logger.info("没有运行中的策略可切换")
                return False
            
            logger.info(f"🔄 AI自动切换策略，市场条件: {market_condition}")
            
            return True
            
        except Exception as e:
            logger.error(f"自动切换策略失败: {e}")
            return False

    async def _monitoring_worker(self) -> None:
        """监控工作线程"""
        logger.info("启动策略监控线程")

        while self._initialized:
            try:
                await asyncio.sleep(30)  # 每30秒检查一次

                # 检查策略状态
                await self._check_strategy_health()

                # 更新性能指标
                await self._update_performance_metrics()

                # 定期策略池瘦身：限制总量并淘汰低分策略
                await self._prune_low_score_strategies()

                # 根据市场状态自动优选高分研究策略，并将末位策略退役。
                await self._auto_select_high_score_strategies()

                # 用最新市场结构快照做自动降权 / 观察 / 恢复
                await self._auto_apply_market_structure_governance()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"策略监控线程错误: {e}")
                await asyncio.sleep(30)

        logger.info("策略监控线程停止")

    async def _performance_calculation_worker(self) -> None:
        """性能计算工作线程"""
        logger.info("启动策略性能计算线程")

        while self._initialized:
            try:
                cycle = int(self._optimization_runtime_config.get("daily_opt_cycle_seconds", 300) or 300)
                await asyncio.sleep(max(60, cycle))

                # 计算所有策略的性能指标
                await self._calculate_all_performance()

                # 每日执行一次：按策略类型做固定优化 + 回撤优化
                await self._run_daily_strategy_optimization()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"策略性能计算线程错误: {e}")
                await asyncio.sleep(300)

        logger.info("策略性能计算线程停止")

    async def _check_strategy_health(self) -> None:
        """检查策略健康状态"""
        # 检查是否有策略长时间没有生成信号
        for instance in self.strategy_instances.values():
            if (
                instance.status == StrategyStatus.RUNNING
                and instance.last_signal_at
                and datetime.now() - instance.last_signal_at > timedelta(hours=1)
            ):

                logger.warning(
                    f"策略长时间未生成信号: {instance.instance_id} "
                    f"(最后信号: {instance.last_signal_at})"
                )

    async def _update_performance_metrics(self) -> None:
        """更新性能指标"""
        # 这里可以添加实时性能指标更新逻辑
        pass

    def _calc_strategy_pool_score(self, strategy_id: str, config: StrategyConfig) -> float:
        """计算策略池评分，优先使用研究回测分，回退到运行表现分。"""
        md = config.metadata if isinstance(config.metadata, dict) else {}
        research = md.get("research", {}) if isinstance(md.get("research", {}), dict) else {}
        test = research.get("test", {}) if isinstance(research.get("test", {}), dict) else {}

        score: Optional[float] = None
        # 研究评分优先
        if "score" in research:
            try:
                score = float(research.get("score", 0.0) or 0.0)
            except Exception:
                pass
        if score is None:
            sharpe = float(test.get("sharpe_ratio", 0.0) or 0.0)
            pnl = float(test.get("total_pnl", 0.0) or 0.0)
            drawdown = float(test.get("max_drawdown", 1.0) or 1.0)
            trades = float(test.get("total_trades", 0.0) or 0.0)
            score = sharpe * 0.6 + (pnl / 1000.0) * 0.25 - drawdown * 0.1 + min(trades, 100.0) * 0.0005

        # 叠加在线表现（若已有）
        perf = self.performance_metrics.get(strategy_id)
        if perf:
            score += float(perf.sharpe_ratio or 0.0) * 0.2 + float(perf.total_pnl or 0.0) / 5000.0
        score *= self._market_regime_strategy_multiplier(config)
        score *= self._deployment_stage_strategy_multiplier(config)
        return float(score)

    def _market_regime_strategy_multiplier(self, config: StrategyConfig) -> float:
        st = getattr(config.strategy_type, "value", config.strategy_type)
        strategy_type = str(st or "").strip().lower()
        regime = str(getattr(self.market_regime, "value", self.market_regime) or "").strip().lower()
        mapping = {
            "trend_following": {"bull": 1.15, "bear": 1.15, "volatile": 0.78, "sideways": 0.88, "low_volume": 0.92},
            "mean_reversion": {"sideways": 1.18, "low_volume": 1.08, "bull": 0.96, "bear": 0.96, "volatile": 0.72},
            "ml_based": {"bull": 1.02, "bear": 1.02, "sideways": 1.02, "volatile": 0.85, "low_volume": 0.98},
            "ai_generated": {"bull": 1.03, "bear": 1.03, "sideways": 1.01, "volatile": 0.85, "low_volume": 0.98},
        }
        return float(mapping.get(strategy_type, {}).get(regime, 1.0))

    def _deployment_stage_strategy_multiplier(self, config: StrategyConfig) -> float:
        stage = self._get_deployment_stage(config)
        return {
            "paper": 0.98,
            "shadow": 1.0,
            "small": 1.03,
            "full": 1.05,
        }.get(str(stage or "").strip().lower(), 1.0)

    def _build_human_review_window(self, config: StrategyConfig) -> Dict[str, Any]:
        md = config.metadata if isinstance(config.metadata, dict) else {}
        rw = md.get("review_window", {}) if isinstance(md.get("review_window"), dict) else {}
        approval = md.get("approval", {}) if isinstance(md.get("approval"), dict) else {}
        research = md.get("research", {}) if isinstance(md.get("research"), dict) else {}
        if not rw:
            review_by = datetime.now() + timedelta(hours=24)
            rw = {
                "visible": True,
                "status": "pending_approval" if bool(approval.get("required", False)) else "open",
                "mode": "pre_publish_approval" if bool(approval.get("required", False)) else "post_publish_observation",
                "opened_at": datetime.now().isoformat(),
                "review_by": review_by.isoformat(),
                "deployment_stage": self._get_deployment_stage(config),
                "score": float(research.get("score", 0.0) or 0.0),
                "summary": "generated by strategy manager fallback",
            }
        return rw

    async def _auto_select_high_score_strategies(self) -> Dict[str, Any]:
        """根据市场状态和综合分数自动选择高分策略，并将末位研究策略退役。"""
        max_active_research = 3
        research_candidates: List[tuple[str, float, StrategyConfig]] = []
        for sid, cfg in self.strategy_configs.items():
            if sid.startswith(("default_", "combined_")):
                continue
            score = self._calc_strategy_pool_score(sid, cfg)
            research_candidates.append((sid, score, cfg))

        if not research_candidates:
            return {"selected": [], "retired": []}

        research_candidates.sort(key=lambda row: row[1], reverse=True)
        selected_ids = {sid for sid, _, _ in research_candidates[:max_active_research]}
        retired: List[str] = []

        async with self._lock:
            for sid, score, cfg in research_candidates:
                md = cfg.metadata if isinstance(cfg.metadata, dict) else {}
                research = md.get("research", {}) if isinstance(md.get("research"), dict) else {}
                review_window = self._build_human_review_window(cfg)
                review_window["selection_score"] = float(round(score, 6))
                review_window["selection_rank"] = next((idx + 1 for idx, row in enumerate(research_candidates) if row[0] == sid), None)
                review_window["selection_reason"] = "selected_high_score" if sid in selected_ids else "retired_low_score"
                md["review_window"] = review_window
                research["selection_score"] = float(round(score, 6))
                research["selection_state"] = "selected" if sid in selected_ids else "retired"
                md["research"] = research
                cfg.metadata = md
                if sid in selected_ids:
                    if not cfg.enabled:
                        cfg.enabled = True
                else:
                    cfg.enabled = False
                    cfg.stage = StrategyLifecycleStage.RETIRED
                    retired.append(sid)
                cfg.updated_at = datetime.now()

        return {"selected": sorted(selected_ids), "retired": retired}

    async def _prune_low_score_strategies(self) -> None:
        """
        定期清理低分策略，防止策略数量无限累积。
        仅清理研究/AI生成策略，默认基础策略不删除。
        """
        now = datetime.now()
        interval_seconds = int(self._optimization_runtime_config.get("prune_interval_seconds", 3600) or 3600)
        max_total = int(self._optimization_runtime_config.get("pool_limit", 30) or 30)
        min_keep = 8
        protect_prefixes = ("default_", "combined_")
        candidate_prefixes = ("dsl_", "ai_strategy_", "ai_")

        if self._last_pool_prune_at and (now - self._last_pool_prune_at).total_seconds() < interval_seconds:
            return
        self._last_pool_prune_at = now

        async with self._lock:
            total = len(self.strategy_configs)
            if total <= max_total:
                return

            candidates: List[tuple[str, float]] = []
            for strategy_id, cfg in self.strategy_configs.items():
                if strategy_id.startswith(protect_prefixes):
                    continue
                if not strategy_id.startswith(candidate_prefixes):
                    continue
                if strategy_id == self.best_strategy:
                    continue
                score = self._calc_strategy_pool_score(strategy_id, cfg)
                candidates.append((strategy_id, score))

            if not candidates:
                return

            # 从低分到高分淘汰
            candidates.sort(key=lambda x: x[1])
            removable = max(0, total - max_total)
            # 保底保留一定数量，防止过度清理
            removable = min(removable, max(0, len(candidates) - max(0, min_keep - (total - len(candidates)))))
            if removable <= 0:
                return

            to_remove = [sid for sid, _ in candidates[:removable]]

            # 先停止并删除相关实例
            remove_instance_ids = [
                iid for iid, inst in self.strategy_instances.items() if inst.config.strategy_id in to_remove
            ]
            for iid in remove_instance_ids:
                self.strategy_instances.pop(iid, None)
                self.strategy_weights.pop(iid, None)

            # 删除策略配置与性能记录
            for sid in to_remove:
                cfg = self.strategy_configs.get(sid)
                if cfg is not None:
                    cfg.stage = StrategyLifecycleStage.RETIRED
                self.strategy_configs.pop(sid, None)
                self.performance_metrics.pop(sid, None)

            # 归一化剩余权重
            tw = sum(self.strategy_weights.values())
            if tw > 0:
                for iid in list(self.strategy_weights.keys()):
                    self.strategy_weights[iid] = float(self.strategy_weights[iid]) / float(tw)

            logger.info(
                "🧹 策略池清理完成: 删除 %s 个低分策略，当前总数 %s（上限 %s）",
                len(to_remove),
                len(self.strategy_configs),
                max_total,
            )

    async def _run_daily_strategy_optimization(self) -> None:
        """
        每日策略优化例程：
        1) 按策略类型做固定参数微调（长期稳定性）
        2) 按回撤做风控参数收敛（回撤优化）
        """
        today = datetime.now().strftime("%Y-%m-%d")
        batch_size = int(self._optimization_runtime_config.get("daily_batch_size", 6) or 6)
        batch_time_budget_sec = float(self._optimization_runtime_config.get("daily_batch_time_budget_sec", 1.5) or 1.5)
        started = datetime.now()

        async with self._lock:
            # 新的一天，重置游标/状态（分批跑，避免单次占用过高）
            if self._daily_optimization_status.get("date") != today:
                self._daily_optimization_cursor = 0
                self._daily_optimization_status = {
                    "date": today,
                    "completed": False,
                    "processed": 0,
                    "total": len(self.strategy_configs),
                    "drawdown_optimized": 0,
                    "started_at": datetime.now().isoformat(),
                    "finished_at": None,
                    "last_batch_ms": 0.0,
                }

            if self._daily_optimization_status.get("completed"):
                self._last_daily_optimization_date = today
                return

            items = list(self.strategy_configs.items())
            total = len(items)
            if total == 0:
                self._daily_optimization_status["completed"] = True
                self._daily_optimization_status["finished_at"] = datetime.now().isoformat()
                self._last_daily_optimization_date = today
                return

            idx = int(self._daily_optimization_cursor)
            end_idx = min(total, idx + batch_size)
            batch = items[idx:end_idx]

            optimized = 0
            dd_optimized = 0
            for sid, cfg in batch:
                md = cfg.metadata if isinstance(cfg.metadata, dict) else {}
                if not isinstance(md, dict):
                    md = {}

                params = cfg.parameters if isinstance(cfg.parameters, dict) else {}
                # ---- 固定优化：按类型做轻微参数收敛 ----
                st = cfg.strategy_type.value if hasattr(cfg.strategy_type, "value") else str(cfg.strategy_type)
                if st == "trend_following":
                    params.setdefault("fast_ma_period", 12)
                    params.setdefault("slow_ma_period", 36)
                elif st in {"grid_trading", "mean_reversion"}:
                    params.setdefault("bb_period", 20)
                    params.setdefault("bb_std", 2.0)
                elif st in {"market_making", "ai_generated"}:
                    params.setdefault("vol_window", 20)
                    params.setdefault("atr_mult", 1.4)

                # ---- 回撤优化：依据历史回测/运行回撤收紧风险参数 ----
                dd = 0.0
                research = md.get("research", {}) if isinstance(md.get("research", {}), dict) else {}
                test = research.get("test", {}) if isinstance(research.get("test", {}), dict) else {}
                try:
                    dd = max(dd, float(test.get("max_drawdown", 0.0) or 0.0))
                except Exception:
                    pass
                perf = self.performance_metrics.get(sid)
                if perf:
                    dd = max(dd, float(perf.max_drawdown or 0.0))

                stop_loss = float(params.get("stop_loss_pct", 0.03) or 0.03)
                take_profit = float(params.get("take_profit_pct", 0.06) or 0.06)
                if dd >= 0.25:
                    stop_loss = max(0.008, stop_loss * 0.88)
                    take_profit = max(0.015, take_profit * 0.92)
                    dd_optimized += 1
                elif dd <= 0.10:
                    # 低回撤时仅小步放宽，避免过拟合
                    stop_loss = min(0.06, stop_loss * 1.03)
                    take_profit = min(0.15, take_profit * 1.03)
                    dd_optimized += 1

                params["stop_loss_pct"] = float(round(stop_loss, 4))
                params["take_profit_pct"] = float(round(take_profit, 4))
                cfg.parameters = params
                cfg.updated_at = datetime.now()
                md["daily_optimization"] = {
                    "date": today,
                    "strategy_type": st,
                    "max_drawdown_used": float(round(dd, 4)),
                    "stop_loss_pct": cfg.parameters.get("stop_loss_pct"),
                    "take_profit_pct": cfg.parameters.get("take_profit_pct"),
                }
                cfg.metadata = md
                optimized += 1
                # 让出事件循环，避免长时间占用主线程
                await asyncio.sleep(0)
                if (datetime.now() - started).total_seconds() >= batch_time_budget_sec:
                    break

            processed_now = optimized
            self._daily_optimization_cursor = min(total, idx + processed_now)
            self._daily_optimization_status["processed"] = int(self._daily_optimization_status.get("processed", 0) or 0) + processed_now
            self._daily_optimization_status["drawdown_optimized"] = int(
                self._daily_optimization_status.get("drawdown_optimized", 0) or 0
            ) + dd_optimized
            self._daily_optimization_status["total"] = total
            self._daily_optimization_status["last_batch_ms"] = round(
                (datetime.now() - started).total_seconds() * 1000.0, 2
            )

            if self._daily_optimization_cursor >= total:
                self._daily_optimization_status["completed"] = True
                self._daily_optimization_status["finished_at"] = datetime.now().isoformat()
                self._last_daily_optimization_date = today
                logger.info(
                    "🛠️ 每日策略优化完成: 总计 %s, 回撤优化 %s, 日期 %s",
                    self._daily_optimization_status.get("processed", 0),
                    self._daily_optimization_status.get("drawdown_optimized", 0),
                    today,
                )
            else:
                logger.info(
                    "🧩 每日策略优化分批进行: %s/%s（本批%d）",
                    self._daily_optimization_status.get("processed", 0),
                    total,
                    processed_now,
                )
            await self._auto_manage_deployment_stages()

    def _get_deployment_stage(self, config: StrategyConfig) -> str:
        md = config.metadata if isinstance(config.metadata, dict) else {}
        dep = md.get("deployment", {}) if isinstance(md.get("deployment", {}), dict) else {}
        stage = str(dep.get("stage", "full") or "full").lower()
        if stage not in {"paper", "shadow", "small", "full"}:
            stage = "full"
        return stage

    def _set_deployment_stage(self, config: StrategyConfig, stage: str, reason: str = "") -> None:
        md = config.metadata if isinstance(config.metadata, dict) else {}
        dep = md.get("deployment", {}) if isinstance(md.get("deployment", {}), dict) else {}
        dep["stage"] = stage
        dep["cap_multiplier"] = self._deployment_cap_multiplier(stage)
        dep["updated_at"] = datetime.now().isoformat()
        if reason:
            dep["reason"] = reason
        md["deployment"] = dep
        config.metadata = md
        config.updated_at = datetime.now()

    @staticmethod
    def _deployment_cap_multiplier(stage: str) -> float:
        return {
            "paper": 0.0,
            "shadow": 0.25,
            "small": 0.5,
            "full": 1.0,
        }.get(stage, 1.0)

    def _get_effective_cap_multiplier(self, config: StrategyConfig) -> float:
        md = config.metadata if isinstance(config.metadata, dict) else {}
        gov = md.get("governance", {}) if isinstance(md.get("governance"), dict) else {}
        overlay = gov.get("market_structure_overlay", {}) if isinstance(gov.get("market_structure_overlay"), dict) else {}
        eff = overlay.get("effective_cap_multiplier")
        if eff is not None:
            try:
                return max(0.0, min(1.0, float(eff)))
            except Exception:
                pass
        return self._deployment_cap_multiplier(self._get_deployment_stage(config))

    def _record_deployment_action(
        self,
        config: StrategyConfig,
        *,
        action: str,
        symbol: str,
        reason: str,
        market_structure: Optional[Dict[str, Any]] = None,
        from_stage: Optional[str] = None,
        to_stage: Optional[str] = None,
    ) -> None:
        md = config.metadata if isinstance(config.metadata, dict) else {}
        gov = md.get("governance", {}) if isinstance(md.get("governance"), dict) else {}
        rows = gov.get("deployment_actions", []) if isinstance(gov.get("deployment_actions"), list) else []
        rows.append(
            {
                "action": str(action or "hold"),
                "symbol": str(symbol or ""),
                "reason": str(reason or ""),
                "from_stage": from_stage,
                "to_stage": to_stage,
                "market_structure": dict(market_structure or {}),
                "recorded_at": datetime.now().isoformat(),
            }
        )
        gov["deployment_actions"] = rows[-50:]
        md["governance"] = gov
        config.metadata = md
        config.updated_at = datetime.now()

    def _infer_lifecycle_stage(self, config_data: Dict[str, Any], metadata: Dict[str, Any]) -> StrategyLifecycleStage:
        raw = str(config_data.get("stage") or metadata.get("stage") or "").strip().lower()
        if raw:
            for item in StrategyLifecycleStage:
                if raw == item.value:
                    return item
        dep = metadata.get("deployment", {}) if isinstance(metadata.get("deployment"), dict) else {}
        dep_stage = str(dep.get("stage") or "").strip().lower()
        return _DEPLOYMENT_TO_LIFECYCLE.get(dep_stage, StrategyLifecycleStage.RESEARCHING)

    def _infer_oos_status(self, metadata: Dict[str, Any]) -> str:
        research = metadata.get("research", {}) if isinstance(metadata.get("research"), dict) else {}
        test = research.get("test", {}) if isinstance(research.get("test"), dict) else {}
        if not test:
            return "unknown"
        passed = test.get("passed")
        if passed is True:
            return "passed"
        if passed is False:
            return "failed"
        return "available"

    def _infer_live_drift_status(self, metadata: Dict[str, Any]) -> str:
        return str(metadata.get("live_drift_status") or "unknown")

    def get_strategy_governance_profile(self, strategy_id: str) -> Dict[str, Any]:
        cfg = self.strategy_configs.get(strategy_id)
        if cfg is None:
            return {
                "strategy_id": strategy_id,
                "stage": StrategyLifecycleStage.RESEARCHING.value,
                "oos_status": "unknown",
                "live_drift_status": "unknown",
                "deployment_stage": "unknown",
            }
        md = cfg.metadata if isinstance(cfg.metadata, dict) else {}
        dep = md.get("deployment", {}) if isinstance(md.get("deployment"), dict) else {}
        gov = md.get("governance", {}) if isinstance(md.get("governance"), dict) else {}
        overlay = gov.get("market_structure_overlay", {}) if isinstance(gov.get("market_structure_overlay"), dict) else {}
        actions = gov.get("deployment_actions", []) if isinstance(gov.get("deployment_actions"), list) else []
        return {
            "strategy_id": strategy_id,
            "stage": cfg.stage.value if hasattr(cfg.stage, "value") else str(cfg.stage),
            "oos_status": str(cfg.oos_status or "unknown"),
            "live_drift_status": str(cfg.live_drift_status or "unknown"),
            "deployment_stage": str(dep.get("stage") or "unknown"),
            "cap_multiplier": dep.get("cap_multiplier"),
            "effective_cap_multiplier": self._get_effective_cap_multiplier(cfg),
            "market_structure_overlay": overlay,
            "last_deployment_action": actions[-1] if actions else None,
            "updated_at": cfg.updated_at.isoformat() if isinstance(cfg.updated_at, datetime) else None,
        }

    def get_strategy_research_profile(self, strategy_id: str) -> Dict[str, Any]:
        cfg = self.strategy_configs.get(strategy_id)
        if cfg is None:
            return {
                "strategy_id": strategy_id,
                "hypothesis": "",
                "experiment_card": {},
                "review_status": "unknown",
                "review_completion_status": "missing",
                "failure_cases": [],
                "parameter_sensitivity": {},
            }
        md = cfg.metadata if isinstance(cfg.metadata, dict) else {}
        research = md.get("research", {}) if isinstance(md.get("research"), dict) else {}
        experiment = research.get("experiment_card", {}) if isinstance(research.get("experiment_card"), dict) else {}
        review = research.get("review", {}) if isinstance(research.get("review"), dict) else {}
        failure_cases = research.get("failure_cases", []) if isinstance(research.get("failure_cases"), list) else []
        parameter_sensitivity = research.get("parameter_sensitivity", {}) if isinstance(research.get("parameter_sensitivity"), dict) else {}
        return {
            "strategy_id": strategy_id,
            "hypothesis": str(experiment.get("hypothesis") or research.get("hypothesis") or ""),
            "experiment_card": experiment,
            "review_status": str(review.get("status") or "unknown"),
            "review_completion_status": "completed" if review else "missing",
            "last_review_type": str(review.get("review_type") or ""),
            "last_reviewed_at": review.get("reviewed_at"),
            "action_items": list(review.get("action_items") or []),
            "peer_review_answers": dict(review.get("answers") or {}),
            "failure_cases": failure_cases[:20],
            "parameter_sensitivity": parameter_sensitivity,
        }

    def save_strategy_experiment_card(
        self,
        strategy_id: str,
        *,
        hypothesis: str,
        experiment_card: Optional[Dict[str, Any]] = None,
    ) -> bool:
        cfg = self.strategy_configs.get(strategy_id)
        if cfg is None:
            return False
        md = cfg.metadata if isinstance(cfg.metadata, dict) else {}
        research = md.get("research", {}) if isinstance(md.get("research"), dict) else {}
        card = dict(experiment_card or {})
        card.setdefault("hypothesis", str(hypothesis or "").strip())
        card.setdefault("created_at", datetime.now().isoformat())
        research["hypothesis"] = str(hypothesis or "").strip()
        research["experiment_card"] = card
        md["research"] = research
        cfg.metadata = md
        cfg.updated_at = datetime.now()
        return True

    def record_strategy_review(
        self,
        strategy_id: str,
        *,
        review_type: str,
        answers: Optional[Dict[str, Any]] = None,
        action_items: Optional[List[str]] = None,
        status: str = "completed",
    ) -> bool:
        cfg = self.strategy_configs.get(strategy_id)
        if cfg is None:
            return False
        md = cfg.metadata if isinstance(cfg.metadata, dict) else {}
        research = md.get("research", {}) if isinstance(md.get("research"), dict) else {}
        review = research.get("review", {}) if isinstance(research.get("review"), dict) else {}
        review.update(
            {
                "review_type": str(review_type or "weekly"),
                "answers": dict(answers or {}),
                "action_items": list(action_items or []),
                "status": str(status or "completed"),
                "reviewed_at": datetime.now().isoformat(),
            }
        )
        research["review"] = review
        md["research"] = research
        cfg.metadata = md
        cfg.updated_at = datetime.now()
        return True

    def record_strategy_peer_review(
        self,
        strategy_id: str,
        *,
        answers: Optional[Dict[str, Any]] = None,
        action_items: Optional[List[str]] = None,
        status: str = "completed",
    ) -> bool:
        required = [
            "what_edge",
            "why_not_immediately_gone",
            "net_after_cost",
            "failure_shape",
            "kill_signal",
        ]
        ans = dict(answers or {})
        missing = [k for k in required if not str(ans.get(k) or "").strip()]
        if missing:
            return False
        return self.record_strategy_review(
            strategy_id,
            review_type="peer_review_5q",
            answers=ans,
            action_items=action_items,
            status=status,
        )

    def record_strategy_failure_case(
        self,
        strategy_id: str,
        *,
        title: str,
        case_type: str,
        summary: str,
        trigger: str = "",
        action_taken: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        cfg = self.strategy_configs.get(strategy_id)
        if cfg is None:
            return False
        md = cfg.metadata if isinstance(cfg.metadata, dict) else {}
        research = md.get("research", {}) if isinstance(md.get("research"), dict) else {}
        rows = research.get("failure_cases", []) if isinstance(research.get("failure_cases"), list) else []
        rows.append(
            {
                "title": str(title or "").strip(),
                "case_type": str(case_type or "execution_failure").strip(),
                "summary": str(summary or "").strip(),
                "trigger": str(trigger or "").strip(),
                "action_taken": str(action_taken or "").strip(),
                "metadata": dict(metadata or {}),
                "recorded_at": datetime.now().isoformat(),
            }
        )
        research["failure_cases"] = rows[-50:]
        md["research"] = research
        cfg.metadata = md
        cfg.updated_at = datetime.now()
        return True

    def save_strategy_parameter_sensitivity(
        self,
        strategy_id: str,
        *,
        parameter_sensitivity: Optional[Dict[str, Any]] = None,
    ) -> bool:
        cfg = self.strategy_configs.get(strategy_id)
        if cfg is None:
            return False
        md = cfg.metadata if isinstance(cfg.metadata, dict) else {}
        research = md.get("research", {}) if isinstance(md.get("research"), dict) else {}
        research["parameter_sensitivity"] = dict(parameter_sensitivity or {})
        md["research"] = research
        cfg.metadata = md
        cfg.updated_at = datetime.now()
        return True

    def get_strategy_activation_gate(self, strategy_id: str) -> Dict[str, Any]:
        cfg = self.strategy_configs.get(strategy_id)
        if cfg is None:
            return {
                "strategy_id": strategy_id,
                "eligible": False,
                "reasons": ["strategy_not_found"],
                "stage": "unknown",
            }
        gov = self.get_strategy_governance_profile(strategy_id)
        rp = self.get_strategy_research_profile(strategy_id)
        reasons: List[str] = []
        if not str(rp.get("hypothesis") or "").strip():
            reasons.append("missing_hypothesis")
        exp = rp.get("experiment_card") if isinstance(rp.get("experiment_card"), dict) else {}
        if not exp:
            reasons.append("missing_experiment_card")
        cost_model = exp.get("cost_model") if isinstance(exp.get("cost_model"), dict) else {}
        if not cost_model:
            reasons.append("missing_cost_model")
        answers = rp.get("peer_review_answers") if isinstance(rp.get("peer_review_answers"), dict) else {}
        required = [
            "what_edge",
            "why_not_immediately_gone",
            "net_after_cost",
            "failure_shape",
            "kill_signal",
        ]
        missing_answers = [k for k in required if not str(answers.get(k) or "").strip()]
        if missing_answers:
            reasons.append("missing_peer_review_5q")
        if str(gov.get("oos_status") or "unknown").lower() != "passed":
            reasons.append("oos_not_passed")
        if str(gov.get("live_drift_status") or "unknown").lower() == "degraded":
            reasons.append("live_drift_degraded")
        return {
            "strategy_id": strategy_id,
            "eligible": len(reasons) == 0,
            "reasons": reasons,
            "stage": gov.get("stage"),
            "oos_status": gov.get("oos_status"),
            "live_drift_status": gov.get("live_drift_status"),
            "market_structure_overlay_status": ((gov.get("market_structure_overlay") or {}).get("status") if isinstance(gov.get("market_structure_overlay"), dict) else None),
            "review_completion_status": rp.get("review_completion_status"),
        }

    def approve_strategy(self, strategy_id: str, *, approved_by: str = "manual", reason: str = "") -> Dict[str, Any]:
        cfg = self.strategy_configs.get(strategy_id)
        if cfg is None:
            return {
                "strategy_id": strategy_id,
                "approved": False,
                "reason": "strategy_not_found",
            }

        md = cfg.metadata if isinstance(cfg.metadata, dict) else {}
        approval = md.get("approval", {}) if isinstance(md.get("approval"), dict) else {}
        required = bool(approval.get("required", False))
        gate = self.get_strategy_activation_gate(strategy_id)
        if gate and not gate.get("eligible"):
            return {
                "strategy_id": strategy_id,
                "approved": False,
                "reason": "activation_gate_denied",
                "activation_gate": gate,
            }

        approval["required"] = required
        approval["state"] = "approved"
        approval["approved"] = True
        approval["approved_by"] = str(approved_by or "manual")
        approval["approved_at"] = datetime.now().isoformat()
        if reason:
            approval["reason"] = str(reason)
        md["approval"] = approval

        research = md.get("research", {}) if isinstance(md.get("research"), dict) else {}
        research["approval_state"] = "approved"
        md["research"] = research
        review_window = self._build_human_review_window(cfg)
        review_window["status"] = "reviewed"
        review_window["reviewed_at"] = datetime.now().isoformat()
        review_window["reviewed_by"] = str(approved_by or "manual")
        md["review_window"] = review_window
        cfg.metadata = md
        cfg.enabled = True
        cfg.updated_at = datetime.now()

        stage = StrategyLifecycleStage.OOS_VALIDATING if required else (cfg.stage or StrategyLifecycleStage.OOS_VALIDATING)
        self.set_strategy_governance_state(
            strategy_id,
            stage=stage,
            oos_status="passed",
            live_drift_status=cfg.live_drift_status or "unknown",
            reason=reason or "manual_approval",
        )
        return {
            "strategy_id": strategy_id,
            "approved": True,
            "enabled": cfg.enabled,
            "activation_gate": gate,
            "approval": approval,
        }

    @staticmethod
    def _deployment_stage_rank(stage: str) -> int:
        return {
            "paper": 0,
            "shadow": 1,
            "small": 2,
            "full": 3,
        }.get(str(stage or "").strip().lower(), 99)

    async def approve_strategy_for_execution(
        self,
        strategy_id: str,
        *,
        approved_by: str = "manual",
        reason: str = "",
    ) -> Dict[str, Any]:
        result = self.approve_strategy(strategy_id, approved_by=approved_by, reason=reason)
        if not result.get("approved"):
            return result

        cfg = self.strategy_configs.get(strategy_id)
        md = cfg.metadata if cfg and isinstance(cfg.metadata, dict) else {}
        research = md.get("research", {}) if isinstance(md.get("research"), dict) else {}
        rollout = research.get("rollout_policy", {}) if isinstance(research.get("rollout_policy"), dict) else {}
        deployment = md.get("deployment", {}) if isinstance(md.get("deployment"), dict) else {}
        deployment_stage = str(deployment.get("stage") or "unknown").strip().lower()

        auto_deploy = bool(rollout.get("auto_deploy_after_approval", False))
        auto_activate = bool(rollout.get("auto_activate_after_approval", False))
        max_stage = str(rollout.get("max_post_approval_auto_stage", "paper") or "paper").strip().lower()
        require_gate = bool(rollout.get("require_activation_gate", True))
        if self._deployment_stage_rank(deployment_stage) > self._deployment_stage_rank(max_stage):
            auto_deploy = False
            auto_activate = False

        deployment_result: Dict[str, Any] = {
            "deployment_stage": deployment_stage,
            "auto_deploy_after_approval": auto_deploy,
            "auto_activate_after_approval": auto_activate,
            "instance_id": None,
            "initialized": False,
            "activated": False,
            "blockers": [],
        }
        if not auto_deploy:
            deployment_result["blockers"].append("auto_deploy_disabled")
            result["deployment"] = deployment_result
            return result

        gate = self.get_strategy_activation_gate(strategy_id) if require_gate else {"eligible": True, "reasons": []}
        if not bool((gate or {}).get("eligible", False)):
            deployment_result["blockers"].extend(list((gate or {}).get("reasons") or ["activation_gate_denied"]))
            result["activation_gate"] = gate
            result["deployment"] = deployment_result
            return result

        running = await self.get_strategy_instances(strategy_id=strategy_id, status=StrategyStatus.RUNNING)
        if running:
            deployment_result["blockers"].append("already_running")
            deployment_result["activated"] = True
            result["deployment"] = deployment_result
            return result

        instances = await self.get_strategy_instances(strategy_id=strategy_id)
        existing_instance = instances[0] if instances else None
        instance_id = existing_instance.instance_id if existing_instance else await self.create_strategy_instance(strategy_id)
        if not instance_id:
            deployment_result["blockers"].append("create_instance_failed")
            result["deployment"] = deployment_result
            return result

        deployment_result["instance_id"] = instance_id
        init_ok = True
        status = existing_instance.status if existing_instance else StrategyStatus.CREATED
        if status == StrategyStatus.CREATED:
            init_ok = await self.initialize_strategy(instance_id)
        elif status in {StrategyStatus.READY, StrategyStatus.RUNNING, StrategyStatus.PAUSED}:
            init_ok = True
        else:
            init_ok = False
        deployment_result["initialized"] = bool(init_ok)
        if not init_ok:
            deployment_result["blockers"].append("initialize_failed")
            result["deployment"] = deployment_result
            return result

        if auto_activate:
            if existing_instance and existing_instance.status == StrategyStatus.RUNNING:
                activated = True
            else:
                activated = await self.start_strategy(instance_id)
            deployment_result["activated"] = bool(activated)
            if not activated:
                deployment_result["blockers"].append("start_failed")
        else:
            deployment_result["blockers"].append("auto_activate_disabled")
        result["deployment"] = deployment_result
        return result

    def set_strategy_governance_state(
        self,
        strategy_id: str,
        *,
        stage: Optional[StrategyLifecycleStage] = None,
        oos_status: Optional[str] = None,
        live_drift_status: Optional[str] = None,
        reason: str = "",
    ) -> bool:
        cfg = self.strategy_configs.get(strategy_id)
        if cfg is None:
            return False
        md = cfg.metadata if isinstance(cfg.metadata, dict) else {}
        gov = md.get("governance", {}) if isinstance(md.get("governance"), dict) else {}
        if stage is not None:
            cfg.stage = stage
            gov["stage"] = stage.value
        if oos_status is not None:
            cfg.oos_status = str(oos_status)
            gov["oos_status"] = str(oos_status)
        if live_drift_status is not None:
            cfg.live_drift_status = str(live_drift_status)
            gov["live_drift_status"] = str(live_drift_status)
        if reason:
            gov["last_reason"] = str(reason)
            gov["updated_at"] = datetime.now().isoformat()
        md["governance"] = gov
        cfg.metadata = md
        cfg.updated_at = datetime.now()
        return True

    def record_market_structure_snapshot(
        self,
        symbol: str,
        snapshot: Optional[Dict[str, Any]] = None,
        *,
        apply_now: bool = True,
    ) -> Dict[str, Any]:
        sym = str(symbol or "unknown")
        snap = dict(snapshot or {})
        snap["symbol"] = sym
        snap["recorded_at"] = datetime.now().isoformat()
        self._latest_market_structure_snapshots[sym] = snap
        if apply_now:
            return self.apply_market_structure_governance(sym, snap)
        return {"symbol": sym, "updated": True, "applied": False}

    def apply_market_structure_governance(
        self,
        symbol: str,
        market_structure: Optional[Dict[str, Any]] = None,
        *,
        strategy_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        sym = str(symbol or "unknown")
        snap = dict(market_structure or self._latest_market_structure_snapshots.get(sym) or {})
        posture = str(snap.get("risk_posture") or "unknown").lower()
        liquidity = str(snap.get("liquidity_state") or "unknown").lower()
        regime = str(snap.get("regime_label") or "unknown").lower()
        confidence = float(snap.get("confidence") or 0.0)
        conflict = float(snap.get("signal_conflict_score") or 0.0)
        observe_mult = float(self._market_structure_runtime_config.get("observe_cap_multiplier", 0.5) or 0.5)
        observe_threshold = float(self._market_structure_runtime_config.get("observe_conflict_threshold", 0.55) or 0.55)
        restore_conf = float(self._market_structure_runtime_config.get("restore_min_confidence", 0.55) or 0.55)
        restore_cycles = int(self._market_structure_runtime_config.get("restore_stable_cycles", 2) or 2)

        matched: List[str] = []
        actions: List[Dict[str, Any]] = []
        candidates = strategy_ids or list(self.strategy_configs.keys())
        for sid in candidates:
            cfg = self.strategy_configs.get(sid)
            if cfg is None or sid.startswith(("default_", "combined_")):
                continue
            if strategy_ids is None:
                symbols = [str(x) for x in (cfg.symbols or []) if str(x).strip()]
                if symbols and sym not in symbols:
                    continue
            matched.append(sid)
            md = cfg.metadata if isinstance(cfg.metadata, dict) else {}
            gov = md.get("governance", {}) if isinstance(md.get("governance"), dict) else {}
            overlay = gov.get("market_structure_overlay", {}) if isinstance(gov.get("market_structure_overlay"), dict) else {}
            current_stage = self._get_deployment_stage(cfg)
            base_stage = str(overlay.get("base_stage") or current_stage)
            stable_cycles = int(overlay.get("stable_cycles", 0) or 0)
            base_mult = self._deployment_cap_multiplier(current_stage)
            target_stage = current_stage
            effective_mult = base_mult
            status = "neutral"
            action = "hold"
            reason = f"regime={regime} posture={posture} liquidity={liquidity}"

            if posture == "capital_preservation" or liquidity == "stressed":
                status = "downweighted"
                action = "downweight"
                stable_cycles = 0
                if current_stage == "full":
                    target_stage = "shadow"
                elif current_stage == "small":
                    target_stage = "shadow"
                elif current_stage == "shadow":
                    target_stage = "paper"
                effective_mult = self._deployment_cap_multiplier(target_stage)
            elif posture in {"defensive", "cautious"} or liquidity == "fragile" or conflict >= observe_threshold:
                status = "observing"
                action = "observe"
                stable_cycles = 0
                effective_mult = round(max(0.0, min(base_mult, base_mult * observe_mult)), 4)
            elif posture in {"balanced", "offensive"} and liquidity == "healthy" and confidence >= restore_conf:
                stable_cycles += 1
                if overlay.get("status") in {"downweighted", "observing"} and stable_cycles >= restore_cycles:
                    status = "recovered"
                    action = "recover"
                    target_stage = base_stage if base_stage in {"paper", "shadow", "small", "full"} else current_stage
                    effective_mult = self._deployment_cap_multiplier(target_stage)
                else:
                    status = str(overlay.get("status") or "neutral")
            else:
                status = str(overlay.get("status") or "neutral")

            if action == "downweight" and target_stage != current_stage:
                self._set_deployment_stage(cfg, target_stage, reason=f"market_structure:{reason}")
            elif action == "recover" and target_stage != current_stage:
                self._set_deployment_stage(cfg, target_stage, reason=f"market_structure_recover:{reason}")

            gov["market_structure_overlay"] = {
                "symbol": sym,
                "status": status,
                "action": action,
                "base_stage": base_stage if overlay.get("base_stage") else current_stage,
                "current_stage": self._get_deployment_stage(cfg),
                "effective_cap_multiplier": effective_mult,
                "stable_cycles": stable_cycles,
                "reason": reason,
                "confidence": round(confidence, 4),
                "signal_conflict_score": round(conflict, 4),
                "updated_at": datetime.now().isoformat(),
            }
            md["governance"] = gov
            cfg.metadata = md
            cfg.updated_at = datetime.now()
            if action != "hold":
                self._record_deployment_action(
                    cfg,
                    action=action,
                    symbol=sym,
                    reason=reason,
                    market_structure=snap,
                    from_stage=current_stage,
                    to_stage=self._get_deployment_stage(cfg),
                )
            actions.append(
                {
                    "strategy_id": sid,
                    "action": action,
                    "status": status,
                    "from_stage": current_stage,
                    "to_stage": self._get_deployment_stage(cfg),
                    "effective_cap_multiplier": effective_mult,
                }
            )

        return {
            "symbol": sym,
            "matched_strategies": matched,
            "market_structure": {
                "regime_label": regime,
                "risk_posture": posture,
                "liquidity_state": liquidity,
                "confidence": round(confidence, 4),
                "signal_conflict_score": round(conflict, 4),
            },
            "actions": actions,
            "applied_at": datetime.now().isoformat(),
        }

    async def _auto_apply_market_structure_governance(self) -> None:
        for symbol, snapshot in list(self._latest_market_structure_snapshots.items()):
            try:
                self.apply_market_structure_governance(symbol, snapshot)
            except Exception as e:
                logger.debug("market structure governance apply failed for %s: %s", symbol, e)

    def get_market_structure_governance_status(self) -> Dict[str, Any]:
        status_counts: Dict[str, int] = {}
        rows: List[Dict[str, Any]] = []
        for sid, cfg in self.strategy_configs.items():
            md = cfg.metadata if isinstance(cfg.metadata, dict) else {}
            gov = md.get("governance", {}) if isinstance(md.get("governance"), dict) else {}
            overlay = gov.get("market_structure_overlay", {}) if isinstance(gov.get("market_structure_overlay"), dict) else {}
            if not overlay:
                continue
            status = str(overlay.get("status") or "neutral")
            status_counts[status] = int(status_counts.get(status, 0)) + 1
            rows.append(
                {
                    "strategy_id": sid,
                    "symbol": overlay.get("symbol"),
                    "status": status,
                    "action": overlay.get("action"),
                    "current_stage": overlay.get("current_stage"),
                    "effective_cap_multiplier": overlay.get("effective_cap_multiplier"),
                    "reason": overlay.get("reason"),
                    "updated_at": overlay.get("updated_at"),
                }
            )
        return {
            "tracked_symbols": sorted(self._latest_market_structure_snapshots.keys()),
            "status_counts": status_counts,
            "strategies": rows[:50],
        }

    async def _auto_manage_deployment_stages(self) -> None:
        """自动分层发布：paper/shadow/small/full，按回测+实盘表现升降级。"""
        promote_score = float(self._deployment_runtime_config.get("promote_min_score", 0.95) or 0.95)
        promote_trades = int(self._deployment_runtime_config.get("promote_min_trades", 20) or 20)
        demote_dd = float(self._deployment_runtime_config.get("demote_max_drawdown", 0.35) or 0.35)
        demote_score = float(self._deployment_runtime_config.get("demote_min_score", 0.2) or 0.2)

        for sid, cfg in self.strategy_configs.items():
            if sid.startswith(("default_", "combined_")):
                continue

            stage = self._get_deployment_stage(cfg)
            perf = self.performance_metrics.get(sid)
            trades = int(getattr(perf, "total_trades", 0) or 0) if perf else 0
            dd = float(getattr(perf, "max_drawdown", 0.0) or 0.0) if perf else 0.0
            score = self._calc_strategy_pool_score(sid, cfg)

            if dd >= demote_dd or score <= demote_score:
                if stage in {"full", "small"}:
                    self._set_deployment_stage(cfg, "shadow", reason=f"demote dd={dd:.3f} score={score:.3f}")
                elif stage == "shadow":
                    self._set_deployment_stage(cfg, "paper", reason=f"demote dd={dd:.3f} score={score:.3f}")
                continue

            if score >= promote_score and trades >= promote_trades:
                if stage == "paper":
                    self._set_deployment_stage(cfg, "shadow", reason=f"promote score={score:.3f}")
                elif stage == "shadow":
                    self._set_deployment_stage(cfg, "small", reason=f"promote score={score:.3f}")
                elif stage == "small":
                    self._set_deployment_stage(cfg, "full", reason=f"promote score={score:.3f}")

    def get_optimization_status(self) -> Dict[str, Any]:
        """给 API/UI 查询策略池与每日优化状态。"""
        stage_counts = {"paper": 0, "shadow": 0, "small": 0, "full": 0}
        for cfg in self.strategy_configs.values():
            st = self._get_deployment_stage(cfg)
            stage_counts[st] = stage_counts.get(st, 0) + 1
        return {
            "pool_limit": int(self._optimization_runtime_config.get("pool_limit", 30) or 30),
            "total_strategies": len(self.strategy_configs),
            "runtime_config": dict(self._optimization_runtime_config),
            "daily_optimization": dict(self._daily_optimization_status),
            "last_daily_optimization_date": self._last_daily_optimization_date,
            "last_pool_prune_at": self._last_pool_prune_at.isoformat() if self._last_pool_prune_at else None,
            "deployment_stage_counts": stage_counts,
            "market_structure_governance": self.get_market_structure_governance_status(),
        }

    def update_optimization_runtime_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """运行期热更新优化参数（无需重启）。"""
        allowed = {
            "pool_limit": (int, 8, 200),
            "prune_interval_seconds": (int, 300, 86400),
            "daily_batch_size": (int, 1, 50),
            "daily_batch_time_budget_sec": (float, 0.2, 10.0),
            "daily_opt_cycle_seconds": (int, 60, 3600),
            "promote_min_score": (float, 0.2, 5.0),
            "promote_min_trades": (int, 5, 500),
            "demote_max_drawdown": (float, 0.05, 0.95),
            "demote_min_score": (float, -2.0, 2.0),
        }
        applied: Dict[str, Any] = {}
        for k, v in (updates or {}).items():
            if k not in allowed or v is None:
                continue
            typ, lo, hi = allowed[k]
            try:
                val = typ(v)
                if val < lo:
                    val = lo
                if val > hi:
                    val = hi
                if k in {"promote_min_score", "promote_min_trades", "demote_max_drawdown", "demote_min_score"}:
                    self._deployment_runtime_config[k] = val
                else:
                    self._optimization_runtime_config[k] = val
                applied[k] = val
            except Exception:
                continue
        return applied

    async def trigger_daily_optimization_now(self) -> Dict[str, Any]:
        """外部触发一次每日优化批次（非阻塞循环外手动触发）。"""
        started = datetime.now()
        await self._run_daily_strategy_optimization()
        status = self.get_optimization_status()
        return {
            "success": True,
            "message": "已触发每日优化批次",
            "status": status,
            "elapsed_ms": round((datetime.now() - started).total_seconds() * 1000.0, 2),
        }

    async def apply_trade_feedback(
        self,
        strategy_id: str,
        pnl: float,
        win_rate: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        total_trades: Optional[int] = None,
        force_optimize: bool = False,
    ) -> Dict[str, Any]:
        """
        根据交易结果更新策略表现并做轻量自适应参数收敛。
        目标：让生产结果持续反哺参数，并可定期触发增量优化。
        """
        if not strategy_id:
            return {"success": False, "message": "strategy_id 不能为空"}

        async with self._lock:
            perf = self.performance_metrics.get(strategy_id)
            if not perf:
                perf = StrategyPerformance(strategy_id=strategy_id)
                self.performance_metrics[strategy_id] = perf

            perf.total_pnl = float(pnl)
            if total_trades is not None:
                perf.total_trades = max(0, int(total_trades))
            if win_rate is not None:
                try:
                    wr = float(win_rate)
                    perf.win_rate = wr if wr <= 1.0 else wr / 100.0
                except Exception:
                    pass
            if max_drawdown is not None:
                try:
                    perf.max_drawdown = max(0.0, float(max_drawdown))
                except Exception:
                    pass
            perf.last_updated = datetime.now()

            cfg = self.strategy_configs.get(strategy_id)
            if cfg:
                params = cfg.parameters if isinstance(cfg.parameters, dict) else {}
                stop_loss = float(params.get("stop_loss_pct", 0.03) or 0.03)
                take_profit = float(params.get("take_profit_pct", 0.06) or 0.06)
                dd = float(perf.max_drawdown or 0.0)

                if dd >= 0.25 or pnl < 0:
                    stop_loss = max(0.008, stop_loss * 0.93)
                    take_profit = max(0.015, take_profit * 0.95)
                elif dd <= 0.10 and pnl > 0:
                    stop_loss = min(0.06, stop_loss * 1.02)
                    take_profit = min(0.15, take_profit * 1.02)

                params["stop_loss_pct"] = float(round(stop_loss, 4))
                params["take_profit_pct"] = float(round(take_profit, 4))
                cfg.parameters = params
                md = cfg.metadata if isinstance(cfg.metadata, dict) else {}
                md["trade_feedback"] = {
                    "at": datetime.now().isoformat(),
                    "pnl": float(round(pnl, 6)),
                    "max_drawdown": float(round(dd, 6)),
                    "stop_loss_pct": params["stop_loss_pct"],
                    "take_profit_pct": params["take_profit_pct"],
                }
                cfg.metadata = md
                cfg.updated_at = datetime.now()

        should_opt = bool(force_optimize)
        if not should_opt:
            now = datetime.now()
            if not self._last_trade_feedback_opt_at:
                should_opt = True
            else:
                should_opt = (now - self._last_trade_feedback_opt_at).total_seconds() >= 3600
            if should_opt:
                self._last_trade_feedback_opt_at = now

        if should_opt:
            try:
                await self._run_daily_strategy_optimization()
            except Exception as e:
                logger.warning(f"交易反馈触发每日优化失败: {e}")

        return {
            "success": True,
            "strategy_id": strategy_id,
            "triggered_daily_optimization": should_opt,
        }

    async def _calculate_all_performance(self) -> None:
        """计算所有策略性能"""
        # 为每个策略计算性能指标
        for strategy_id in self.strategy_configs:
            if strategy_id not in self.performance_metrics:
                # 创建新的性能记录
                self.performance_metrics[strategy_id] = StrategyPerformance(strategy_id=strategy_id)

            # 更新性能指标（简化版）
            performance = self.performance_metrics[strategy_id]
            performance.last_updated = datetime.now()

            # 在实际系统中，这里应该从交易记录计算真实性能

    async def _save_state(self) -> None:
        """保存状态"""
        # 在实际系统中，这里应该保存到数据库
        logger.info("保存策略管理器状态")

    async def _evaluate_strategies(self):
        """评估策略性能并更新最佳策略"""
        logger.info("开始评估策略性能")

        # 计算每个策略的性能得分
        strategy_scores = {}

        for instance_id, instance in self.strategy_instances.items():
            if instance.status == StrategyStatus.RUNNING:
                score = self._calc_strategy_pool_score(instance.config.strategy_id, instance.config)
                score += instance.sharpe_ratio * 0.35 + (instance.total_pnl / 1000) * 0.2 + (instance.total_trades / 100) * 0.05
                strategy_scores[instance_id] = score

        # 选择最佳策略
        if strategy_scores:
            best_instance_id = max(strategy_scores, key=strategy_scores.get)
            best_score = strategy_scores[best_instance_id]

            # 检查是否需要切换策略
            if best_instance_id != self.best_strategy:
                if self.best_strategy:
                    # 计算性能差异
                    current_score = strategy_scores.get(self.best_strategy, 0)
                    if current_score == 0 or (best_score - current_score) / abs(current_score) > self.switch_threshold:
                        await self._switch_strategy(best_instance_id)
                else:
                    # 首次选择策略
                    await self._switch_strategy(best_instance_id)

    async def _switch_strategy(self, new_instance_id: str):
        """切换最佳策略"""
        # 记录之前的最佳策略
        old_best = self.best_strategy
        
        # 更新最佳策略
        self.best_strategy = new_instance_id
        
        # 调整策略权重
        for instance_id in self.strategy_instances:
            if instance_id == new_instance_id:
                self.strategy_weights[instance_id] = 0.7  # 增加最佳策略的权重
            else:
                self.strategy_weights[instance_id] = 0.3 / (len(self.strategy_instances) - 1) if len(self.strategy_instances) > 1 else 0
        
        # 归一化权重
        total_weight = sum(self.strategy_weights.values())
        if total_weight > 0:
            for instance_id in self.strategy_weights:
                self.strategy_weights[instance_id] /= total_weight
        
        logger.info(f"切换最佳策略: {old_best} -> {new_instance_id}")

    async def _detect_market_regime(self, data: Dict[str, Any]):
        """检测市场状态"""
        if "close" in data and "volume" in data:
            # 简化的市场状态检测
            # 实际系统中应该使用更复杂的算法
            price_change = data.get("close", 0) / data.get("open", data.get("close", 1)) - 1
            volume_change = data.get("volume", 0) / data.get("prev_volume", data.get("volume", 1)) - 1
            
            if price_change > 0.02 and volume_change > 0.1:
                self.market_regime = MarketRegime.BULL
            elif price_change < -0.02 and volume_change > 0.1:
                self.market_regime = MarketRegime.BEAR
            elif abs(price_change) < 0.01 and abs(volume_change) < 0.05:
                self.market_regime = MarketRegime.SIDEWAYS
            elif abs(price_change) > 0.03:
                self.market_regime = MarketRegime.VOLATILE
            else:
                self.market_regime = MarketRegime.LOW_VOLUME


# 示例策略实现


class MovingAverageStrategy(BaseStrategy):
    """移动平均策略示例"""

    async def _load_data(self) -> None:
        """加载数据"""
        # 这里应该从数据提供者加载历史数据
        logger.info(f"移动平均策略加载数据: {self.name}")

    async def _calculate_indicators(self) -> None:
        """计算指标"""
        # 计算移动平均等指标
        logger.info(f"移动平均策略计算指标: {self.name}")

    async def _process_market_data(self, symbol: str, data: Dict[str, Any]) -> None:
        """处理市场数据"""
        # 更新指标计算
        pass

    async def _generate_signals(self) -> List[TradingSignal]:
        """生成交易信号"""
        signals = []

        # 示例：简单的移动平均交叉策略
        for symbol in self.symbols:
            # 获取指标数据（简化示例）
            fast_ma = 50000.0  # 快速移动平均
            slow_ma = 49000.0  # 慢速移动平均
            current_price = 51000.0  # 当前价格

            # 生成信号逻辑
            if fast_ma > slow_ma and fast_ma < current_price:
                # 金叉且价格在均线上方，买入信号
                signal = TradingSignal(
                    signal_id=f"signal_{uuid.uuid4().hex[:8]}",
                    strategy_id=self.strategy_id,
                    instance_id="",  # 会在StrategyManager中设置
                    signal_type=SignalType.BUY,
                    symbol=symbol,
                    price=current_price,
                    quantity=0.1,  # 固定数量
                    confidence=0.7,
                    reason="快速均线上穿慢速均线，趋势向上",
                )
                signals.append(signal)

            elif fast_ma < slow_ma and fast_ma > current_price:
                # 死叉且价格在均线下方，卖出信号
                signal = TradingSignal(
                    signal_id=f"signal_{uuid.uuid4().hex[:8]}",
                    strategy_id=self.strategy_id,
                    instance_id="",  # 会在StrategyManager中设置
                    signal_type=SignalType.SELL,
                    symbol=symbol,
                    price=current_price,
                    quantity=0.1,
                    confidence=0.6,
                    reason="快速均线下穿慢速均线，趋势向下",
                )
                signals.append(signal)

        return signals


class BollingerBandsStrategy(BaseStrategy):
    """布林带策略示例"""

    async def _load_data(self) -> None:
        """加载数据"""
        logger.info(f"布林带策略加载数据: {self.name}")

    async def _calculate_indicators(self) -> None:
        """计算指标"""
        # 计算布林带、RSI等指标
        logger.info(f"布林带策略计算指标: {self.name}")

    async def _process_market_data(self, symbol: str, data: Dict[str, Any]) -> None:
        """处理市场数据"""
        pass

    async def _generate_signals(self) -> List[TradingSignal]:
        """生成交易信号"""
        signals = []

        # 示例：布林带均值回归策略
        for symbol in self.symbols:
            # 获取指标数据（简化示例）
            upper_band = 52000.0  # 上轨
            lower_band = 48000.0  # 下轨
            middle_band = 50000.0  # 中轨
            current_price = 47500.0  # 当前价格
            rsi = 28.0  # RSI值

            # 生成信号逻辑
            if current_price < lower_band and rsi < 30:
                # 价格跌破下轨且RSI超卖，买入信号
                signal = TradingSignal(
                    signal_id=f"signal_{uuid.uuid4().hex[:8]}",
                    strategy_id=self.strategy_id,
                    instance_id="",  # 会在StrategyManager中设置
                    signal_type=SignalType.BUY,
                    symbol=symbol,
                    price=current_price,
                    quantity=0.2,
                    confidence=0.8,
                    reason="价格跌破布林带下轨且RSI超卖，均值回归买入信号",
                )
                signals.append(signal)

            elif current_price > upper_band and rsi > 70:
                # 价格突破上轨且RSI超买，卖出信号
                signal = TradingSignal(
                    signal_id=f"signal_{uuid.uuid4().hex[:8]}",
                    strategy_id=self.strategy_id,
                    instance_id="",  # 会在StrategyManager中设置
                    signal_type=SignalType.SELL,
                    symbol=symbol,
                    price=current_price,
                    quantity=0.2,
                    confidence=0.7,
                    reason="价格突破布林带上轨且RSI超买，均值回归卖出信号",
                )
                signals.append(signal)

        return signals
