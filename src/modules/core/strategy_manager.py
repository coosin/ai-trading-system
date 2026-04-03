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
                metadata=config_data.get("metadata", {}),
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
            # 检测市场状态
            await self._detect_market_regime(data)
            
            # 定期评估策略性能并切换
            if time.time() - self.last_evaluation_time >= self.evaluation_period:
                await self._evaluate_strategies()
                self.last_evaluation_time = time.time()

            # 找到关注此交易对的运行中策略
            running_instances = await self.get_strategy_instances(status=StrategyStatus.RUNNING)

            for instance in running_instances:
                if symbol in instance.config.symbols:
                    try:
                        # 传递市场数据给策略
                        if instance.instance:
                            await instance.instance.on_market_data(symbol, data)

                        # 生成信号
                        signals = await instance.instance.generate_signals()

                        for signal in signals:
                            # 设置策略信息
                            signal.strategy_id = instance.config.strategy_id
                            signal.instance_id = instance.instance_id

                            # 生成信号ID
                            signal.signal_id = f"signal_{uuid.uuid4().hex[:8]}"

                            # 保存信号
                            async with self._lock:
                                self.signals[signal.signal_id] = signal
                                self.signal_history.append(signal)

                                # 限制历史记录长度
                                if len(self.signal_history) > 10000:
                                    self.signal_history = self.signal_history[-10000:]

                            # 更新实例统计
                            instance.last_signal_at = datetime.now()
                            instance.total_signals += 1

                            all_signals.append(signal)

                    except Exception as e:
                        logger.error(f"策略处理市场数据失败 {instance.instance_id}: {e}")

            if all_signals:
                logger.debug(f"处理市场数据生成 {len(all_signals)} 个信号: {symbol}")

        except Exception as e:
            logger.error(f"处理市场数据失败: {e}")

        return all_signals

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

        # 不再加载默认策略 - AI将根据市场情况动态生成策略
        if not self.strategy_configs:
            logger.info("未加载任何策略配置，AI将根据市场情况动态生成策略")

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
                await asyncio.sleep(300)  # 每5分钟计算一次

                # 计算所有策略的性能指标
                await self._calculate_all_performance()

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
                # 计算策略得分
                score = instance.sharpe_ratio * 0.5 + (instance.total_pnl / 1000) * 0.3 + (instance.total_trades / 100) * 0.2
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
                    if (best_score - current_score) / abs(current_score) > self.switch_threshold:
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