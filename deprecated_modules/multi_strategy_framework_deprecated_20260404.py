from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Union, Callable

import numpy as np
import pandas as pd

from src.modules.core.data_fusion import FusedDataPoint
from src.modules.core.risk_manager import RiskLevel

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """策略类型"""
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    SCALPING = "scalping"
    ARBITRAGE = "arbitrage"
    MOMENTUM = "momentum"
    CONTRARIAN = "contrarian"
    DYNAMIC = "dynamic"


class StrategyStatus(Enum):
    """策略状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class StrategyPerformance:
    """策略性能"""
    strategy_type: StrategyType
    total_trades: int
    win_rate: float
    average_profit: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    average_holding_period: float
    last_updated: float


@dataclass
class StrategySignal:
    """策略信号"""
    strategy_type: StrategyType
    symbol: str
    action: str  # buy, sell, hold
    price: float
    timestamp: float
    confidence: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class BaseStrategy:
    """基础策略类"""

    def __init__(self, strategy_type: StrategyType, config: Dict[str, Any]):
        """初始化策略

        Args:
            strategy_type: 策略类型
            config: 配置信息
        """
        self.strategy_type = strategy_type
        self.config = config
        self.status = StrategyStatus.INACTIVE
        self.performance = StrategyPerformance(
            strategy_type=strategy_type,
            total_trades=0,
            win_rate=0.0,
            average_profit=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            profit_factor=0.0,
            average_holding_period=0.0,
            last_updated=time.time()
        )

    async def initialize(self) -> bool:
        """初始化策略

        Returns:
            bool: 初始化是否成功
        """
        try:
            self.status = StrategyStatus.ACTIVE
            logger.info(f"Strategy {self.strategy_type.value} initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize strategy {self.strategy_type.value}: {e}")
            self.status = StrategyStatus.ERROR
            return False

    async def shutdown(self) -> bool:
        """关闭策略

        Returns:
            bool: 关闭是否成功
        """
        try:
            self.status = StrategyStatus.INACTIVE
            logger.info(f"Strategy {self.strategy_type.value} shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown strategy {self.strategy_type.value}: {e}")
            return False

    async def generate_signal(self, symbol: str, data: List[FusedDataPoint]) -> Optional[StrategySignal]:
        """生成交易信号

        Args:
            symbol: 交易对
            data: 融合数据点列表

        Returns:
            Optional[StrategySignal]: 交易信号
        """
        raise NotImplementedError("Subclasses must implement generate_signal method")

    async def update_performance(self, trade_result: Dict[str, Any]):
        """更新策略性能

        Args:
            trade_result: 交易结果
        """
        try:
            # 这里应该实现具体的性能更新逻辑
            # 暂时使用模拟数据
            self.performance.total_trades += 1
            self.performance.last_updated = time.time()
        except Exception as e:
            logger.error(f"Error updating performance: {e}")

    def get_performance(self) -> StrategyPerformance:
        """获取策略性能

        Returns:
            StrategyPerformance: 策略性能
        """
        return self.performance

    def get_status(self) -> StrategyStatus:
        """获取策略状态

        Returns:
            StrategyStatus: 策略状态
        """
        return self.status


class TrendFollowingStrategy(BaseStrategy):
    """趋势跟踪策略"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(StrategyType.TREND_FOLLOWING, config)

    async def generate_signal(self, symbol: str, data: List[FusedDataPoint]) -> Optional[StrategySignal]:
        """生成交易信号

        Args:
            symbol: 交易对
            data: 融合数据点列表

        Returns:
            Optional[StrategySignal]: 交易信号
        """
        try:
            # 这里应该实现具体的趋势跟踪逻辑
            # 暂时返回一个模拟信号
            return StrategySignal(
                strategy_type=self.strategy_type,
                symbol=symbol,
                action="hold",
                price=0,
                timestamp=time.time(),
                confidence=0.5
            )
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return None


class MeanReversionStrategy(BaseStrategy):
    """均值回归策略"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(StrategyType.MEAN_REVERSION, config)

    async def generate_signal(self, symbol: str, data: List[FusedDataPoint]) -> Optional[StrategySignal]:
        """生成交易信号

        Args:
            symbol: 交易对
            data: 融合数据点列表

        Returns:
            Optional[StrategySignal]: 交易信号
        """
        try:
            # 这里应该实现具体的均值回归逻辑
            # 暂时返回一个模拟信号
            return StrategySignal(
                strategy_type=self.strategy_type,
                symbol=symbol,
                action="hold",
                price=0,
                timestamp=time.time(),
                confidence=0.5
            )
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return None


class BreakoutStrategy(BaseStrategy):
    """突破策略"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(StrategyType.BREAKOUT, config)

    async def generate_signal(self, symbol: str, data: List[FusedDataPoint]) -> Optional[StrategySignal]:
        """生成交易信号

        Args:
            symbol: 交易对
            data: 融合数据点列表

        Returns:
            Optional[StrategySignal]: 交易信号
        """
        try:
            # 这里应该实现具体的突破策略逻辑
            # 暂时返回一个模拟信号
            return StrategySignal(
                strategy_type=self.strategy_type,
                symbol=symbol,
                action="hold",
                price=0,
                timestamp=time.time(),
                confidence=0.5
            )
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return None


class MultiStrategyFramework:
    """多策略框架"""

    def __init__(self, config: Dict[str, Any]):
        """初始化多策略框架

        Args:
            config: 配置信息
        """
        self.config = config
        self.strategies = {}
        self.active_strategies = []
        self.enabled = False
        self.strategy_weights = {}
        self.performance_history = {}

    async def initialize(self) -> bool:
        """初始化多策略框架

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 初始化所有策略
            strategy_configs = self.config.get("strategies", {})
            
            # 创建并初始化策略
            if strategy_configs.get("trend_following", {}).get("enabled", False):
                self.strategies[StrategyType.TREND_FOLLOWING] = TrendFollowingStrategy(
                    strategy_configs.get("trend_following", {})
                )
                await self.strategies[StrategyType.TREND_FOLLOWING].initialize()
                self.active_strategies.append(StrategyType.TREND_FOLLOWING)
            
            if strategy_configs.get("mean_reversion", {}).get("enabled", False):
                self.strategies[StrategyType.MEAN_REVERSION] = MeanReversionStrategy(
                    strategy_configs.get("mean_reversion", {})
                )
                await self.strategies[StrategyType.MEAN_REVERSION].initialize()
                self.active_strategies.append(StrategyType.MEAN_REVERSION)
            
            if strategy_configs.get("breakout", {}).get("enabled", False):
                self.strategies[StrategyType.BREAKOUT] = BreakoutStrategy(
                    strategy_configs.get("breakout", {})
                )
                await self.strategies[StrategyType.BREAKOUT].initialize()
                self.active_strategies.append(StrategyType.BREAKOUT)
            
            # 初始化策略权重
            self._initialize_strategy_weights()
            
            # 初始化性能历史
            for strategy_type in self.strategies:
                self.performance_history[strategy_type] = []
            
            self.enabled = True
            logger.info("MultiStrategyFramework initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize MultiStrategyFramework: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭多策略框架

        Returns:
            bool: 关闭是否成功
        """
        try:
            # 关闭所有策略
            for strategy in self.strategies.values():
                await strategy.shutdown()
            
            self.enabled = False
            self.strategies.clear()
            self.active_strategies.clear()
            self.strategy_weights.clear()
            self.performance_history.clear()
            logger.info("MultiStrategyFramework shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown MultiStrategyFramework: {e}")
            return False

    def _initialize_strategy_weights(self):
        """初始化策略权重"""
        for strategy_type in self.strategies:
            self.strategy_weights[strategy_type] = 1.0 / len(self.strategies)

    async def generate_combined_signal(self, symbol: str, data: List[FusedDataPoint]) -> Optional[StrategySignal]:
        """生成组合信号

        Args:
            symbol: 交易对
            data: 融合数据点列表

        Returns:
            Optional[StrategySignal]: 组合交易信号
        """
        try:
            if not self.enabled:
                logger.warning("MultiStrategyFramework is not enabled")
                return None
            
            # 生成所有策略的信号
            signals = []
            for strategy_type in self.active_strategies:
                strategy = self.strategies[strategy_type]
                if strategy.get_status() == StrategyStatus.ACTIVE:
                    signal = await strategy.generate_signal(symbol, data)
                    if signal:
                        signals.append(signal)
            
            if not signals:
                return None
            
            # 组合信号
            combined_signal = self._combine_signals(signals)
            return combined_signal
        except Exception as e:
            logger.error(f"Error generating combined signal: {e}")
            return None

    def _combine_signals(self, signals: List[StrategySignal]) -> StrategySignal:
        """组合信号

        Args:
            signals: 信号列表

        Returns:
            StrategySignal: 组合信号
        """
        # 这里应该实现具体的信号组合逻辑
        # 暂时返回第一个信号
        return signals[0]

    async def update_strategy_weights(self):
        """更新策略权重"""
        try:
            # 基于性能更新策略权重
            total_performance = 0.0
            performances = {}
            
            for strategy_type in self.strategies:
                performance = self.strategies[strategy_type].get_performance()
                # 使用夏普比率作为性能指标
                performance_score = performance.sharpe_ratio
                performances[strategy_type] = performance_score
                total_performance += max(0, performance_score)
            
            # 更新权重
            if total_performance > 0:
                for strategy_type in self.strategies:
                    self.strategy_weights[strategy_type] = max(0, performances[strategy_type]) / total_performance
            
            logger.info(f"Updated strategy weights: {self.strategy_weights}")
        except Exception as e:
            logger.error(f"Error updating strategy weights: {e}")

    async def switch_strategy(self, market_condition: str, risk_level: RiskLevel):
        """根据市场条件和风险等级切换策略

        Args:
            market_condition: 市场条件
            risk_level: 风险等级
        """
        try:
            # 基于市场条件和风险等级调整策略
            if market_condition == "bullish":
                # 牛市适合趋势跟踪和动量策略
                self._activate_strategies([StrategyType.TREND_FOLLOWING, StrategyType.MOMENTUM])
            elif market_condition == "bearish":
                # 熊市适合均值回归和套利策略
                self._activate_strategies([StrategyType.MEAN_REVERSION, StrategyType.ARBITRAGE])
            else:
                # 中性市场适合突破和反转策略
                self._activate_strategies([StrategyType.BREAKOUT, StrategyType.CONTRARIAN])
            
            # 根据风险等级调整策略参数
            for strategy_type in self.active_strategies:
                strategy = self.strategies.get(strategy_type)
                if strategy:
                    await self._adjust_strategy_parameters(strategy, risk_level)
            
            logger.info(f"Switched strategies based on market condition: {market_condition} and risk level: {risk_level.value}")
        except Exception as e:
            logger.error(f"Error switching strategy: {e}")

    def _activate_strategies(self, strategy_types: List[StrategyType]):
        """激活指定的策略

        Args:
            strategy_types: 策略类型列表
        """
        # 停用过时的策略
        for strategy_type in self.active_strategies:
            if strategy_type not in strategy_types:
                strategy = self.strategies.get(strategy_type)
                if strategy:
                    strategy.status = StrategyStatus.PAUSED
        
        # 激活新策略
        self.active_strategies = []
        for strategy_type in strategy_types:
            if strategy_type in self.strategies:
                strategy = self.strategies[strategy_type]
                strategy.status = StrategyStatus.ACTIVE
                self.active_strategies.append(strategy_type)

    async def _adjust_strategy_parameters(self, strategy: BaseStrategy, risk_level: RiskLevel):
        """调整策略参数

        Args:
            strategy: 策略
            risk_level: 风险等级
        """
        # 这里应该实现具体的参数调整逻辑
        # 暂时只记录日志
        logger.info(f"Adjusting parameters for strategy {strategy.strategy_type.value} based on risk level: {risk_level.value}")

    async def update_performance(self, strategy_type: StrategyType, trade_result: Dict[str, Any]):
        """更新策略性能

        Args:
            strategy_type: 策略类型
            trade_result: 交易结果
        """
        try:
            if strategy_type in self.strategies:
                strategy = self.strategies[strategy_type]
                await strategy.update_performance(trade_result)
                
                # 记录性能历史
                performance = strategy.get_performance()
                self.performance_history[strategy_type].append(performance)
                
                # 限制历史记录大小
                if len(self.performance_history[strategy_type]) > 100:
                    self.performance_history[strategy_type] = self.performance_history[strategy_type][-100:]
        except Exception as e:
            logger.error(f"Error updating strategy performance: {e}")

    def get_strategy_performance(self) -> Dict[StrategyType, StrategyPerformance]:
        """获取策略性能

        Returns:
            Dict[StrategyType, StrategyPerformance]: 策略性能字典
        """
        return {strategy_type: strategy.get_performance() for strategy_type, strategy in self.strategies.items()}

    def get_strategy_weights(self) -> Dict[StrategyType, float]:
        """获取策略权重

        Returns:
            Dict[StrategyType, float]: 策略权重字典
        """
        return self.strategy_weights

    def get_active_strategies(self) -> List[StrategyType]:
        """获取活跃策略

        Returns:
            List[StrategyType]: 活跃策略列表
        """
        return self.active_strategies

    def is_healthy(self) -> bool:
        """检查多策略框架健康状态

        Returns:
            bool: 健康状态
        """
        if not self.enabled:
            return False
        
        # 检查是否有活跃策略
        if not self.active_strategies:
            logger.warning("No active strategies")
            return False
        
        # 检查策略状态
        for strategy_type in self.active_strategies:
            strategy = self.strategies.get(strategy_type)
            if not strategy or strategy.get_status() == StrategyStatus.ERROR:
                logger.warning(f"Strategy {strategy_type.value} is in error state")
                return False
        
        return True
