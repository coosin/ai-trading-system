"""
增强的策略管理和机器学习集成系统

功能：
1. 策略注册和管理 - 支持多种策略类型
2. 策略组合和权重调整 - 动态权重分配
3. 策略性能评估 - 多维度性能指标
4. 模型管理和版本控制 - 支持模型版本管理
5. 自动模型更新 - 基于性能的自动模型优化
6. 多模型融合 - 集成多个模型的预测结果
7. 智能策略选择 - 基于市场环境的策略选择
"""

import asyncio
import logging
import pickle
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.ensemble import VotingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from src.modules.intelligence.machine_learning.model_manager import ModelManager, ModelType
from src.modules.intelligence.machine_learning.model_optimizer import ModelOptimizer

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """策略类型"""
    TREND = "trend"            # 趋势策略
    MEAN_REVERSION = "mean_reversion"  # 均值回归策略
    BREAKOUT = "breakout"        # 突破策略
    ARBITRAGE = "arbitrage"      # 套利策略
    SCALPING = "scalping"        # 高频策略
    ML_BASED = "ml_based"        # 机器学习策略


class StrategyStatus(Enum):
    """策略状态"""
    ACTIVE = "active"        # 活跃
    PAUSED = "paused"        # 暂停
    DISABLED = "disabled"      # 禁用
    TESTING = "testing"        # 测试中


class MarketRegime(Enum):
    """市场状态"""
    BULL = "bull"          # 牛市
    BEAR = "bear"          # 熊市
    SIDEWAYS = "sideways"    # 横盘
    VOLATILE = "volatile"    # 高波动
    LOW_VOLUME = "low_volume"  # 低成交量


@dataclass
class StrategyPerformance:
    """策略性能"""
    strategy_id: str
    total_trades: int
    win_rate: float
    average_win: float
    average_loss: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    total_return: float
    timestamp: datetime = field(default_factory=datetime.now)
    market_regime: Optional[MarketRegime] = None


@dataclass
class StrategySignal:
    """策略信号"""
    strategy_id: str
    symbol: str
    side: str  # "buy", "sell", "hold"
    price: float
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, strategy_id: str, config: Dict[str, Any]):
        self.strategy_id = strategy_id
        self.config = config
        self.status = StrategyStatus.ACTIVE
        self.performance = StrategyPerformance(
            strategy_id=strategy_id,
            total_trades=0,
            win_rate=0.0,
            average_win=0.0,
            average_loss=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            profit_factor=0.0,
            total_return=0.0
        )
        self.last_trade_time = None
        self.signals: List[StrategySignal] = []
    
    @abstractmethod
    async def generate_signal(self, data: pd.DataFrame, symbol: str) -> StrategySignal:
        """生成交易信号"""
        pass
    
    @abstractmethod
    async def evaluate_performance(self, data: pd.DataFrame) -> StrategyPerformance:
        """评估策略性能"""
        pass
    
    async def update_performance(self, performance: StrategyPerformance):
        """更新策略性能"""
        self.performance = performance
    
    async def pause(self):
        """暂停策略"""
        self.status = StrategyStatus.PAUSED
    
    async def resume(self):
        """恢复策略"""
        self.status = StrategyStatus.ACTIVE
    
    async def disable(self):
        """禁用策略"""
        self.status = StrategyStatus.DISABLED


class TrendStrategy(BaseStrategy):
    """趋势策略"""
    
    def __init__(self, strategy_id: str, config: Dict[str, Any]):
        super().__init__(strategy_id, config)
        self.ma_fast = config.get("ma_fast", 20)
        self.ma_slow = config.get("ma_slow", 50)
    
    async def generate_signal(self, data: pd.DataFrame, symbol: str) -> StrategySignal:
        """生成交易信号"""
        if len(data) < self.ma_slow:
            return StrategySignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                side="hold",
                price=data["close"].iloc[-1],
                confidence=0.5
            )
        
        # 计算移动平均线
        data["ma_fast"] = data["close"].rolling(window=self.ma_fast).mean()
        data["ma_slow"] = data["close"].rolling(window=self.ma_slow).mean()
        
        # 生成信号
        if data["ma_fast"].iloc[-1] > data["ma_slow"].iloc[-1] and \
           data["ma_fast"].iloc[-2] <= data["ma_slow"].iloc[-2]:
            return StrategySignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                side="buy",
                price=data["close"].iloc[-1],
                confidence=0.7
            )
        elif data["ma_fast"].iloc[-1] < data["ma_slow"].iloc[-1] and \
             data["ma_fast"].iloc[-2] >= data["ma_slow"].iloc[-2]:
            return StrategySignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                side="sell",
                price=data["close"].iloc[-1],
                confidence=0.7
            )
        else:
            return StrategySignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                side="hold",
                price=data["close"].iloc[-1],
                confidence=0.5
            )
    
    async def evaluate_performance(self, data: pd.DataFrame) -> StrategyPerformance:
        """评估策略性能"""
        # 模拟性能评估
        return StrategyPerformance(
            strategy_id=self.strategy_id,
            total_trades=100,
            win_rate=0.6,
            average_win=0.02,
            average_loss=0.015,
            max_drawdown=0.05,
            sharpe_ratio=1.5,
            sortino_ratio=1.8,
            profit_factor=1.6,
            total_return=0.2
        )


class MLStrategy(BaseStrategy):
    """机器学习策略"""
    
    def __init__(self, strategy_id: str, config: Dict[str, Any]):
        super().__init__(strategy_id, config)
        self.model_type = config.get("model_type", ModelType.LSTM)
        self.model_manager = None
        self.model_optimizer = None
    
    async def initialize(self, model_manager: ModelManager):
        """初始化策略"""
        self.model_manager = model_manager
        self.model_optimizer = ModelOptimizer(model_manager, {})
        await self.model_optimizer.initialize()
    
    async def generate_signal(self, data: pd.DataFrame, symbol: str) -> StrategySignal:
        """生成交易信号"""
        if not self.model_manager:
            return StrategySignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                side="hold",
                price=data["close"].iloc[-1],
                confidence=0.5
            )
        
        # 准备特征
        features = await self._prepare_features(data)
        
        # 预测价格
        prediction = await self.model_manager.predict(self.model_type, features)
        
        # 生成信号
        current_price = data["close"].iloc[-1]
        price_change = (prediction - current_price) / current_price
        
        if price_change > 0.01:
            return StrategySignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                side="buy",
                price=current_price,
                confidence=min(0.9, 0.5 + abs(price_change) * 10)
            )
        elif price_change < -0.01:
            return StrategySignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                side="sell",
                price=current_price,
                confidence=min(0.9, 0.5 + abs(price_change) * 10)
            )
        else:
            return StrategySignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                side="hold",
                price=current_price,
                confidence=0.5
            )
    
    async def _prepare_features(self, data: pd.DataFrame) -> np.ndarray:
        """准备特征"""
        # 计算技术指标
        data["returns"] = data["close"].pct_change()
        data["volatility"] = data["returns"].rolling(window=20).std()
        data["rsi"] = await self._calculate_rsi(data, 14)
        
        # 选择特征
        features = data[["returns", "volatility", "rsi"]].dropna().values
        
        # 标准化
        scaler = StandardScaler()
        features = scaler.fit_transform(features)
        
        return features[-1:]
    
    async def _calculate_rsi(self, data: pd.DataFrame, period: int) -> pd.Series:
        """计算RSI"""
        delta = data["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    async def evaluate_performance(self, data: pd.DataFrame) -> StrategyPerformance:
        """评估策略性能"""
        # 模拟性能评估
        return StrategyPerformance(
            strategy_id=self.strategy_id,
            total_trades=120,
            win_rate=0.65,
            average_win=0.025,
            average_loss=0.012,
            max_drawdown=0.04,
            sharpe_ratio=1.8,
            sortino_ratio=2.1,
            profit_factor=1.8,
            total_return=0.25
        )


class StrategyManager:
    """策略管理器"""
    
    def __init__(self):
        self.strategies: Dict[str, BaseStrategy] = {}
        self.strategy_weights: Dict[str, float] = {}
        self.model_manager: Optional[ModelManager] = None
        self.market_regime = MarketRegime.SIDEWAYS
    
    async def initialize(self, model_manager: Optional[ModelManager] = None):
        """初始化策略管理器"""
        self.model_manager = model_manager
        logger.info("策略管理器初始化完成")
    
    def register_strategy(self, strategy: BaseStrategy):
        """注册策略"""
        self.strategies[strategy.strategy_id] = strategy
        self.strategy_weights[strategy.strategy_id] = 1.0 / len(self.strategies) if self.strategies else 1.0
        logger.info(f"注册策略: {strategy.strategy_id}")
    
    async def generate_signals(self, data: pd.DataFrame, symbol: str) -> List[StrategySignal]:
        """生成所有策略的信号"""
        signals = []
        
        for strategy_id, strategy in self.strategies.items():
            if strategy.status == StrategyStatus.ACTIVE:
                try:
                    signal = await strategy.generate_signal(data, symbol)
                    signals.append(signal)
                except Exception as e:
                    logger.error(f"策略 {strategy_id} 生成信号错误: {e}")
        
        return signals
    
    async def get_aggregated_signal(self, data: pd.DataFrame, symbol: str) -> StrategySignal:
        """获取聚合信号"""
        signals = await self.generate_signals(data, symbol)
        
        if not signals:
            return StrategySignal(
                strategy_id="aggregated",
                symbol=symbol,
                side="hold",
                price=data["close"].iloc[-1],
                confidence=0.5
            )
        
        # 计算加权信号
        buy_score = 0.0
        sell_score = 0.0
        total_weight = 0.0
        
        for signal in signals:
            weight = self.strategy_weights.get(signal.strategy_id, 1.0)
            if signal.side == "buy":
                buy_score += signal.confidence * weight
            elif signal.side == "sell":
                sell_score += signal.confidence * weight
            total_weight += weight
        
        if total_weight > 0:
            buy_score /= total_weight
            sell_score /= total_weight
        
        # 确定最终信号
        if buy_score > sell_score and buy_score > 0.6:
            side = "buy"
            confidence = buy_score
        elif sell_score > buy_score and sell_score > 0.6:
            side = "sell"
            confidence = sell_score
        else:
            side = "hold"
            confidence = 0.5
        
        return StrategySignal(
            strategy_id="aggregated",
            symbol=symbol,
            side=side,
            price=data["close"].iloc[-1],
            confidence=confidence,
            metadata={"buy_score": buy_score, "sell_score": sell_score}
        )
    
    async def update_strategy_weights(self, performance_data: Dict[str, StrategyPerformance]):
        """根据性能更新策略权重"""
        # 基于夏普比率计算权重
        total_sharpe = sum(p.sharpe_ratio for p in performance_data.values() if p.sharpe_ratio > 0)
        
        if total_sharpe > 0:
            for strategy_id, performance in performance_data.items():
                if strategy_id in self.strategies and performance.sharpe_ratio > 0:
                    self.strategy_weights[strategy_id] = performance.sharpe_ratio / total_sharpe
            
            # 归一化权重
            total_weight = sum(self.strategy_weights.values())
            if total_weight > 0:
                for strategy_id in self.strategy_weights:
                    self.strategy_weights[strategy_id] /= total_weight
            
            logger.info("策略权重已更新")
    
    async def evaluate_strategies(self, data: pd.DataFrame) -> Dict[str, StrategyPerformance]:
        """评估所有策略"""
        performances = {}
        
        for strategy_id, strategy in self.strategies.items():
            try:
                performance = await strategy.evaluate_performance(data)
                performances[strategy_id] = performance
                await strategy.update_performance(performance)
            except Exception as e:
                logger.error(f"评估策略 {strategy_id} 错误: {e}")
        
        # 更新策略权重
        await self.update_strategy_weights(performances)
        
        return performances
    
    async def detect_market_regime(self, data: pd.DataFrame) -> MarketRegime:
        """检测市场状态"""
        if len(data) < 20:
            return MarketRegime.SIDEWAYS
        
        # 计算市场指标
        returns = data["close"].pct_change()
        volatility = returns.rolling(window=20).std().iloc[-1]
        trend = (data["close"].iloc[-1] / data["close"].iloc[-20] - 1) * 100
        volume_change = (data["volume"].iloc[-1] / data["volume"].rolling(window=20).mean().iloc[-1] - 1) * 100
        
        # 检测市场状态
        if trend > 5 and volatility < 0.02:
            regime = MarketRegime.BULL
        elif trend < -5 and volatility < 0.02:
            regime = MarketRegime.BEAR
        elif volatility > 0.03:
            regime = MarketRegime.VOLATILE
        elif volume_change < -50:
            regime = MarketRegime.LOW_VOLUME
        else:
            regime = MarketRegime.SIDEWAYS
        
        self.market_regime = regime
        return regime
    
    async def adjust_strategies_for_regime(self, regime: MarketRegime):
        """根据市场状态调整策略"""
        # 基于市场状态调整策略权重
        regime_weights = {
            MarketRegime.BULL: {
                "trend": 0.6,
                "mean_reversion": 0.1,
                "breakout": 0.2,
                "ml_based": 0.1
            },
            MarketRegime.BEAR: {
                "trend": 0.1,
                "mean_reversion": 0.6,
                "breakout": 0.1,
                "ml_based": 0.2
            },
            MarketRegime.SIDEWAYS: {
                "trend": 0.2,
                "mean_reversion": 0.4,
                "breakout": 0.3,
                "ml_based": 0.1
            },
            MarketRegime.VOLATILE: {
                "trend": 0.3,
                "mean_reversion": 0.2,
                "breakout": 0.2,
                "ml_based": 0.3
            },
            MarketRegime.LOW_VOLUME: {
                "trend": 0.1,
                "mean_reversion": 0.2,
                "breakout": 0.1,
                "ml_based": 0.6
            }
        }
        
        weights = regime_weights.get(regime, regime_weights[MarketRegime.SIDEWAYS])
        
        # 调整策略权重
        for strategy_id, strategy in self.strategies.items():
            # 根据策略类型调整权重
            for strategy_type, weight in weights.items():
                if strategy_type in strategy_id.lower():
                    self.strategy_weights[strategy_id] = weight
                    break
        
        # 归一化权重
        total_weight = sum(self.strategy_weights.values())
        if total_weight > 0:
            for strategy_id in self.strategy_weights:
                self.strategy_weights[strategy_id] /= total_weight
        
        logger.info(f"根据市场状态 {regime.value} 调整策略权重")
    
    def get_strategy(self, strategy_id: str) -> Optional[BaseStrategy]:
        """获取策略"""
        return self.strategies.get(strategy_id)
    
    def get_all_strategies(self) -> Dict[str, BaseStrategy]:
        """获取所有策略"""
        return self.strategies
    
    def get_strategy_weights(self) -> Dict[str, float]:
        """获取策略权重"""
        return self.strategy_weights
    
    def set_strategy_weight(self, strategy_id: str, weight: float):
        """设置策略权重"""
        if strategy_id in self.strategies:
            self.strategy_weights[strategy_id] = weight
            # 归一化权重
            total_weight = sum(self.strategy_weights.values())
            if total_weight > 0:
                for sid in self.strategy_weights:
                    self.strategy_weights[sid] /= total_weight
    
    async def optimize_strategies(self):
        """优化策略"""
        # 这里可以添加策略参数优化逻辑
        logger.info("策略优化完成")


class EnhancedStrategySystem:
    """增强的策略系统"""
    
    def __init__(self):
        self.strategy_manager = StrategyManager()
        self.model_manager = None
        self.model_optimizer = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def initialize(self, model_manager: Optional[ModelManager] = None):
        """初始化策略系统"""
        self.model_manager = model_manager
        if model_manager:
            self.model_optimizer = ModelOptimizer(model_manager, {})
            await self.model_optimizer.initialize()
        
        await self.strategy_manager.initialize(model_manager)
        self._running = True
        self._task = asyncio.create_task(self._optimization_loop())
        logger.info("增强策略系统初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        if self.model_optimizer:
            await self.model_optimizer.shutdown()
        
        logger.info("增强策略系统清理完成")
    
    def register_strategy(self, strategy: BaseStrategy):
        """注册策略"""
        self.strategy_manager.register_strategy(strategy)
        
        # 如果是机器学习策略，初始化模型
        if isinstance(strategy, MLStrategy) and self.model_manager:
            asyncio.create_task(strategy.initialize(self.model_manager))
    
    async def generate_signal(self, data: pd.DataFrame, symbol: str) -> StrategySignal:
        """生成交易信号"""
        # 检测市场状态
        regime = await self.strategy_manager.detect_market_regime(data)
        
        # 根据市场状态调整策略
        await self.strategy_manager.adjust_strategies_for_regime(regime)
        
        # 生成聚合信号
        return await self.strategy_manager.get_aggregated_signal(data, symbol)
    
    async def evaluate_strategies(self, data: pd.DataFrame) -> Dict[str, StrategyPerformance]:
        """评估策略"""
        return await self.strategy_manager.evaluate_strategies(data)
    
    async def _optimization_loop(self):
        """优化循环"""
        while self._running:
            try:
                # 定期优化策略
                await self.strategy_manager.optimize_strategies()
                
                # 定期优化模型
                if self.model_optimizer:
                    for model_type in ModelType:
                        await self.model_optimizer.check_and_optimize(model_type)
                
                await asyncio.sleep(3600)  # 每小时优化一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"优化循环错误: {e}")
                await asyncio.sleep(3600)
    
    def get_strategy_manager(self) -> StrategyManager:
        """获取策略管理器"""
        return self.strategy_manager
    
    def get_model_manager(self) -> Optional[ModelManager]:
        """获取模型管理器"""
        return self.model_manager


# 使用示例
async def example_usage():
    """使用示例"""
    # 创建策略系统
    strategy_system = EnhancedStrategySystem()
    
    # 初始化模型管理器
    model_manager = ModelManager({})
    await model_manager.initialize()
    
    # 初始化策略系统
    await strategy_system.initialize(model_manager)
    
    try:
        # 注册策略
        trend_strategy = TrendStrategy("trend_ma", {"ma_fast": 20, "ma_slow": 50})
        ml_strategy = MLStrategy("ml_lstm", {"model_type": ModelType.LSTM})
        
        strategy_system.register_strategy(trend_strategy)
        strategy_system.register_strategy(ml_strategy)
        
        # 创建测试数据
        np.random.seed(42)
        dates = pd.date_range("2023-01-01", periods=100, freq="D")
        prices = 50000 + np.cumsum(np.random.normal(0, 100, 100))
        volumes = np.random.normal(1000, 200, 100)
        
        data = pd.DataFrame({
            "timestamp": dates,
            "open": prices,
            "high": prices + np.random.normal(50, 20, 100),
            "low": prices - np.random.normal(50, 20, 100),
            "close": prices,
            "volume": volumes
        })
        
        # 生成信号
        signal = await strategy_system.generate_signal(data, "BTC/USDT")
        print(f"生成的信号: {signal.side} at {signal.price} (置信度: {signal.confidence:.2f})")
        
        # 评估策略
        performances = await strategy_system.evaluate_strategies(data)
        for strategy_id, performance in performances.items():
            print(f"策略 {strategy_id} 夏普比率: {performance.sharpe_ratio:.2f}, 总收益: {performance.total_return:.2f}")
        
        # 获取策略权重
        weights = strategy_system.get_strategy_manager().get_strategy_weights()
        print(f"策略权重: {weights}")
        
    finally:
        await strategy_system.cleanup()
        await model_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(example_usage())
