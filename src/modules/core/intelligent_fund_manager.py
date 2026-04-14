from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Union

import numpy as np
import pandas as pd

from src.modules.core.database_manager import DatabaseManager
from src.modules.core.risk_manager import RiskManager, RiskLevel

logger = logging.getLogger(__name__)


class FundAllocationStrategy(Enum):
    """资金分配策略"""
    CONSERVATIVE = "conservative"  # 保守策略
    MODERATE = "moderate"  #  moderate策略
    AGGRESSIVE = "aggressive"  # 激进策略
    DYNAMIC = "dynamic"  # 动态策略


class MarketCondition(Enum):
    """市场条件"""
    BEARISH = "bearish"  # 熊市
    NEUTRAL = "neutral"  # 中性
    BULLISH = "bullish"  # 牛市


@dataclass
class FundAllocation:
    """资金分配信息"""
    timestamp: float
    strategy: FundAllocationStrategy
    market_condition: MarketCondition
    allocations: Dict[str, float]  # 资产分配比例
    risk_budget: float  # 风险预算
    confidence: float  # 置信度


@dataclass
class PositionSizing:
    """仓位大小信息"""
    symbol: str
    size: float  # 仓位大小（金额）
    leverage: float  # 杠杆
    risk_per_trade: float  # 每笔交易风险
    confidence: float  # 置信度


class IntelligentFundManager:
    """智能资金管理系统"""

    def __init__(self, db_manager: DatabaseManager, risk_manager: RiskManager, config: Dict[str, Any]):
        """初始化智能资金管理系统

        Args:
            db_manager: 数据库管理器
            risk_manager: 风险管理系统
            config: 配置信息
        """
        self.db_manager = db_manager
        self.risk_manager = risk_manager
        self.config = config
        self.fund_allocations = []
        self.current_allocation = {}
        self.total_funds = config.get("initial_funds", 10000)  # 初始资金
        self.risk_per_trade = config.get("risk_per_trade", 0.02)  # 每笔交易风险
        self.max_leverage = config.get("max_leverage", 3)  # 最大杠杆
        self.enabled = False

    async def initialize(self) -> bool:
        """初始化智能资金管理系统

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 加载历史资金分配数据
            await self._load_fund_allocations()
            
            # 初始化资金监控任务
            asyncio.create_task(self._fund_monitoring_loop())

            self.enabled = True
            logger.info("IntelligentFundManager initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize IntelligentFundManager: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭智能资金管理系统

        Returns:
            bool: 关闭是否成功
        """
        try:
            self.enabled = False
            self.fund_allocations.clear()
            self.current_allocation.clear()
            logger.info("IntelligentFundManager shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown IntelligentFundManager: {e}")
            return False

    async def _fund_monitoring_loop(self):
        """资金监控循环"""
        while self.enabled:
            try:
                # 评估当前市场条件
                market_condition = await self._assess_market_condition()
                
                # 计算资金分配
                allocation = await self._calculate_fund_allocation(market_condition)
                if allocation:
                    self.fund_allocations.append(allocation)
                    # 限制历史记录大小
                    if len(self.fund_allocations) > 1000:
                        self.fund_allocations = self.fund_allocations[-1000:]
                    
                    # 更新当前分配
                    self.current_allocation = allocation.allocations
            except Exception as e:
                logger.error(f"Error in fund monitoring loop: {e}")
            
            await asyncio.sleep(300)  # 每5分钟检查一次

    async def _assess_market_condition(self) -> MarketCondition:
        """评估市场条件

        Returns:
            MarketCondition: 市场条件
        """
        try:
            # 这里应该基于市场数据评估市场条件
            # 暂时使用模拟数据
            market_score = np.random.normal(0, 0.5)
            
            if market_score > 0.3:
                return MarketCondition.BULLISH
            elif market_score < -0.3:
                return MarketCondition.BEARISH
            else:
                return MarketCondition.NEUTRAL
        except Exception as e:
            logger.error(f"Error assessing market condition: {e}")
            return MarketCondition.NEUTRAL

    async def _calculate_fund_allocation(self, market_condition: MarketCondition) -> Optional[FundAllocation]:
        """计算资金分配

        Args:
            market_condition: 市场条件

        Returns:
            Optional[FundAllocation]: 资金分配信息
        """
        try:
            timestamp = time.time()
            allocations = {}
            
            # 获取当前风险评估
            risk_assessment = await self.risk_manager.assess_overall_risk()
            risk_level = risk_assessment.risk_level if risk_assessment else RiskLevel.MEDIUM
            
            # 根据市场条件和风险等级确定分配策略
            strategy = await self._determine_strategy(market_condition, risk_level)
            
            # 计算风险预算
            risk_budget = await self._calculate_risk_budget(strategy, risk_level)
            
            # 根据策略计算资产分配
            if strategy == FundAllocationStrategy.CONSERVATIVE:
                allocations = {
                    "USDT": 0.7,  # 70% 稳定币
                    "BTC": 0.15,  # 15% 比特币
                    "ETH": 0.1,   # 10% 以太坊
                    "ALT": 0.05   # 5% 其他代币
                }
            elif strategy == FundAllocationStrategy.MODERATE:
                allocations = {
                    "USDT": 0.5,  # 50% 稳定币
                    "BTC": 0.25,  # 25% 比特币
                    "ETH": 0.15,  # 15% 以太坊
                    "ALT": 0.1    # 10% 其他代币
                }
            elif strategy == FundAllocationStrategy.AGGRESSIVE:
                allocations = {
                    "USDT": 0.3,  # 30% 稳定币
                    "BTC": 0.3,   # 30% 比特币
                    "ETH": 0.2,   # 20% 以太坊
                    "ALT": 0.2    # 20% 其他代币
                }
            else:  # DYNAMIC
                # 动态策略：根据市场条件和风险等级调整
                base_allocations = {
                    "USDT": 0.5,
                    "BTC": 0.25,
                    "ETH": 0.15,
                    "ALT": 0.1
                }
                
                # 根据市场条件调整
                if market_condition == MarketCondition.BULLISH:
                    base_allocations["USDT"] -= 0.2
                    base_allocations["BTC"] += 0.1
                    base_allocations["ETH"] += 0.05
                    base_allocations["ALT"] += 0.05
                elif market_condition == MarketCondition.BEARISH:
                    base_allocations["USDT"] += 0.2
                    base_allocations["BTC"] -= 0.1
                    base_allocations["ETH"] -= 0.05
                    base_allocations["ALT"] -= 0.05
                
                # 根据风险等级调整
                if risk_level == RiskLevel.HIGH or risk_level == RiskLevel.EXTREME:
                    base_allocations["USDT"] += 0.1
                    base_allocations["BTC"] -= 0.05
                    base_allocations["ETH"] -= 0.03
                    base_allocations["ALT"] -= 0.02
                
                # 确保分配比例总和为1
                total = sum(base_allocations.values())
                allocations = {k: v / total for k, v in base_allocations.items()}
            
            # 计算置信度
            confidence = await self._calculate_confidence(strategy, market_condition, risk_level)
            
            return FundAllocation(
                timestamp=timestamp,
                strategy=strategy,
                market_condition=market_condition,
                allocations=allocations,
                risk_budget=risk_budget,
                confidence=confidence
            )
        except Exception as e:
            logger.error(f"Error calculating fund allocation: {e}")
            return None

    async def _determine_strategy(self, market_condition: MarketCondition, risk_level: RiskLevel) -> FundAllocationStrategy:
        """确定资金分配策略

        Args:
            market_condition: 市场条件
            risk_level: 风险等级

        Returns:
            FundAllocationStrategy: 资金分配策略
        """
        try:
            # 根据市场条件和风险等级确定策略
            if risk_level == RiskLevel.HIGH or risk_level == RiskLevel.EXTREME:
                return FundAllocationStrategy.CONSERVATIVE
            elif market_condition == MarketCondition.BULLISH:
                return FundAllocationStrategy.AGGRESSIVE
            elif market_condition == MarketCondition.BEARISH:
                return FundAllocationStrategy.CONSERVATIVE
            else:
                return FundAllocationStrategy.MODERATE
        except Exception as e:
            logger.error(f"Error determining strategy: {e}")
            return FundAllocationStrategy.MODERATE

    async def _calculate_risk_budget(self, strategy: FundAllocationStrategy, risk_level: RiskLevel) -> float:
        """计算风险预算

        Args:
            strategy: 资金分配策略
            risk_level: 风险等级

        Returns:
            float: 风险预算
        """
        try:
            # 基础风险预算
            base_budget = 0.02  # 2%
            
            # 根据策略调整
            if strategy == FundAllocationStrategy.CONSERVATIVE:
                base_budget *= 0.5
            elif strategy == FundAllocationStrategy.AGGRESSIVE:
                base_budget *= 1.5
            
            # 根据风险等级调整
            if risk_level == RiskLevel.HIGH or risk_level == RiskLevel.EXTREME:
                base_budget *= 0.5
            
            return min(0.05, max(0.005, base_budget))  # 限制在0.5%-5%之间
        except Exception as e:
            logger.error(f"Error calculating risk budget: {e}")
            return 0.02

    async def _calculate_confidence(self, strategy: FundAllocationStrategy, market_condition: MarketCondition, risk_level: RiskLevel) -> float:
        """计算置信度

        Args:
            strategy: 资金分配策略
            market_condition: 市场条件
            risk_level: 风险等级

        Returns:
            float: 置信度
        """
        try:
            # 基础置信度
            base_confidence = 0.7
            
            # 根据策略调整
            if strategy == FundAllocationStrategy.DYNAMIC:
                base_confidence += 0.1
            
            # 根据市场条件调整
            if market_condition == MarketCondition.NEUTRAL:
                base_confidence -= 0.1
            
            # 根据风险等级调整
            if risk_level == RiskLevel.HIGH or risk_level == RiskLevel.EXTREME:
                base_confidence -= 0.1
            
            return min(1.0, max(0.3, base_confidence))
        except Exception as e:
            logger.error(f"Error calculating confidence: {e}")
            return 0.5

    async def calculate_position_size(self, symbol: str, entry_price: float, stop_loss: float, confidence: float = 0.5) -> Optional[PositionSizing]:
        """计算仓位大小

        Args:
            symbol: 交易对
            entry_price: 入场价格
            stop_loss: 止损价格
            confidence: 置信度

        Returns:
            Optional[PositionSizing]: 仓位大小信息
        """
        try:
            # 计算每笔交易可承受的损失
            max_loss = self.total_funds * self.risk_per_trade
            
            # 计算价格变动百分比
            price_diff = abs(entry_price - stop_loss)
            risk_per_unit = price_diff / entry_price
            
            if risk_per_unit <= 0:
                logger.warning("Invalid stop loss price")
                return None
            
            # 计算仓位大小
            size = max_loss / price_diff
            
            # 根据置信度调整仓位
            size *= confidence
            
            # 计算杠杆
            leverage = min(self.max_leverage, 1.0 / (risk_per_unit * self.risk_per_trade))
            leverage = max(1.0, leverage)  # 最小杠杆为1
            
            # 计算每笔交易风险
            risk_per_trade = (price_diff * size) / self.total_funds
            
            return PositionSizing(
                symbol=symbol,
                size=size,
                leverage=leverage,
                risk_per_trade=risk_per_trade,
                confidence=confidence
            )
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return None

    async def update_total_funds(self, new_funds: float) -> bool:
        """更新总资金

        Args:
            new_funds: 新的总资金

        Returns:
            bool: 更新是否成功
        """
        try:
            self.total_funds = new_funds
            logger.info(f"Updated total funds to: {new_funds}")
            return True
        except Exception as e:
            logger.error(f"Error updating total funds: {e}")
            return False

    async def get_optimal_leverage(self, symbol: str, market_condition: MarketCondition) -> float:
        """获取最优杠杆

        Args:
            symbol: 交易对
            market_condition: 市场条件

        Returns:
            float: 最优杠杆
        """
        try:
            # 基础杠杆
            base_leverage = 1.0
            
            # 根据市场条件调整
            if market_condition == MarketCondition.BULLISH:
                base_leverage = min(self.max_leverage, 2.0)
            elif market_condition == MarketCondition.BEARISH:
                base_leverage = 1.0
            else:
                base_leverage = 1.5
            
            # 根据交易对调整
            if symbol in ["BTC/USDT", "ETH/USDT"]:
                base_leverage = min(self.max_leverage, base_leverage * 1.2)
            
            return base_leverage
        except Exception as e:
            logger.error(f"Error getting optimal leverage: {e}")
            return 1.0

    async def _load_fund_allocations(self):
        """加载资金分配历史数据"""
        try:
            # 这里应该从数据库加载历史资金分配数据
            # 暂时使用模拟数据
            pass
        except Exception as e:
            logger.error(f"Error loading fund allocations: {e}")

    def get_current_allocation(self) -> Dict[str, float]:
        """获取当前资金分配

        Returns:
            Dict[str, float]: 资金分配比例
        """
        return self.current_allocation

    def get_fund_allocations(self, limit: int = 100) -> List[FundAllocation]:
        """获取资金分配历史

        Args:
            limit: 返回的历史记录数量

        Returns:
            List[FundAllocation]: 资金分配历史
        """
        return self.fund_allocations[-limit:]

    def get_total_funds(self) -> float:
        """获取总资金

        Returns:
            float: 总资金
        """
        return self.total_funds

    def is_healthy(self) -> bool:
        """检查资金管理系统健康状态

        Returns:
            bool: 健康状态
        """
        return self.enabled


    async def cleanup(self):
        """清理资源"""
        pass
