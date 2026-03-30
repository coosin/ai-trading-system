from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Union

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.covariance import LedoitWolf

from src.modules.core.database_manager import DatabaseManager

logger = logging.getLogger(__name__)


class RiskMetricType(Enum):
    """风险指标类型"""
    VAR = "var"  # 风险价值
    CVAR = "cvar"  # 条件风险价值
    MAX_DRAWDOWN = "max_drawdown"  # 最大回撤
    SHARPE_RATIO = "sharpe_ratio"  # 夏普比率
    SORTINO_RATIO = "sortino_ratio"  # 索提诺比率
    BETA = "beta"  # 贝塔系数
    VOLATILITY = "volatility"  # 波动率
    LIQUIDITY_RISK = "liquidity_risk"  # 流动性风险
    SYSTEMIC_RISK = "systemic_risk"  # 系统性风险


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class RiskAssessment:
    """风险评估结果"""
    timestamp: float
    risk_score: float
    risk_level: RiskLevel
    metrics: Dict[RiskMetricType, float]
    recommendations: List[str]
    confidence: float


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    amount: float
    price: float
    entry_time: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    leverage: float = 1.0


class AdvancedRiskManager:
    """高级风险管理系统"""

    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]):
        """初始化高级风险管理系统

        Args:
            db_manager: 数据库管理器
            config: 配置信息
        """
        self.db_manager = db_manager
        self.config = config
        self.positions = {}
        self.risk_history = []
        self.risk_thresholds = config.get("risk_thresholds", {
            "low": 0.2,
            "medium": 0.4,
            "high": 0.7,
            "extreme": 1.0
        })
        self.var_confidence = config.get("var_confidence", 0.95)
        self.var_horizon = config.get("var_horizon", 1)  # 1天
        self.max_position_size = config.get("max_position_size", 0.1)  # 最大仓位比例
        self.max_leverage = config.get("max_leverage", 3)  # 最大杠杆
        self.max_drawdown = config.get("max_drawdown", 0.2)  # 最大回撤
        self.enabled = False

    async def initialize(self) -> bool:
        """初始化高级风险管理系统

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 加载历史风险数据
            await self._load_risk_history()
            
            # 初始化风险监控任务
            asyncio.create_task(self._risk_monitoring_loop())

            self.enabled = True
            logger.info("AdvancedRiskManager initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize AdvancedRiskManager: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭高级风险管理系统

        Returns:
            bool: 关闭是否成功
        """
        try:
            self.enabled = False
            self.positions.clear()
            self.risk_history.clear()
            logger.info("AdvancedRiskManager shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown AdvancedRiskManager: {e}")
            return False

    async def _risk_monitoring_loop(self):
        """风险监控循环"""
        while self.enabled:
            try:
                # 评估当前风险
                assessment = await self.assess_overall_risk()
                if assessment:
                    self.risk_history.append(assessment)
                    # 限制历史记录大小
                    if len(self.risk_history) > 1000:
                        self.risk_history = self.risk_history[-1000:]
                    
                    # 检查风险是否超过阈值
                    if assessment.risk_level in [RiskLevel.HIGH, RiskLevel.EXTREME]:
                        logger.warning(f"High risk detected: {assessment.risk_level.value}, score: {assessment.risk_score}")
                        # 执行风险控制措施
                        await self._execute_risk_control(assessment)
            except Exception as e:
                logger.error(f"Error in risk monitoring loop: {e}")
            
            await asyncio.sleep(60)  # 每分钟检查一次

    async def assess_overall_risk(self) -> Optional[RiskAssessment]:
        """评估整体风险

        Returns:
            Optional[RiskAssessment]: 风险评估结果
        """
        try:
            if not self.enabled:
                logger.warning("AdvancedRiskManager is not enabled")
                return None

            timestamp = time.time()
            metrics = {}
            recommendations = []

            # 计算各项风险指标
            if self.positions:
                # 计算投资组合风险
                portfolio_risk = await self._calculate_portfolio_risk()
                metrics.update(portfolio_risk)
                
                # 计算最大回撤
                max_drawdown = await self._calculate_max_drawdown()
                metrics[RiskMetricType.MAX_DRAWDOWN] = max_drawdown
                
                # 计算夏普比率
                sharpe_ratio = await self._calculate_sharpe_ratio()
                metrics[RiskMetricType.SHARPE_RATIO] = sharpe_ratio
                
                # 计算索提诺比率
                sortino_ratio = await self._calculate_sortino_ratio()
                metrics[RiskMetricType.SORTINO_RATIO] = sortino_ratio
            else:
                # 无持仓时的默认风险
                metrics = {
                    RiskMetricType.VAR: 0.0,
                    RiskMetricType.CVAR: 0.0,
                    RiskMetricType.MAX_DRAWDOWN: 0.0,
                    RiskMetricType.SHARPE_RATIO: 0.0,
                    RiskMetricType.SORTINO_RATIO: 0.0,
                    RiskMetricType.VOLATILITY: 0.0,
                    RiskMetricType.LIQUIDITY_RISK: 0.0,
                    RiskMetricType.SYSTEMIC_RISK: 0.0
                }

            # 计算综合风险分数
            risk_score = await self._calculate_risk_score(metrics)
            risk_level = self._get_risk_level(risk_score)

            # 生成风险建议
            recommendations = await self._generate_recommendations(metrics, risk_level)

            # 计算置信度
            confidence = await self._calculate_confidence(metrics)

            return RiskAssessment(
                timestamp=timestamp,
                risk_score=risk_score,
                risk_level=risk_level,
                metrics=metrics,
                recommendations=recommendations,
                confidence=confidence
            )
        except Exception as e:
            logger.error(f"Error assessing overall risk: {e}")
            return None

    async def assess_position_risk(self, position: Position) -> Dict[str, Any]:
        """评估单个持仓风险

        Args:
            position: 持仓信息

        Returns:
            Dict[str, Any]: 风险评估结果
        """
        try:
            risk_metrics = {}

            # 计算价格波动率（模拟数据）
            volatility = np.random.normal(0.02, 0.01)  # 假设2%的日波动率
            risk_metrics["volatility"] = volatility

            # 计算风险价值(VaR)
            var = position.price * volatility * np.sqrt(self.var_horizon) * norm.ppf(self.var_confidence)
            risk_metrics["var"] = var

            # 计算条件风险价值(CVaR)
            cvar = position.price * volatility * np.sqrt(self.var_horizon) * norm.pdf(norm.ppf(self.var_confidence)) / (1 - self.var_confidence)
            risk_metrics["cvar"] = cvar

            # 计算杠杆风险
            leverage_risk = position.leverage * var / position.price
            risk_metrics["leverage_risk"] = leverage_risk

            # 计算流动性风险
            liquidity_risk = await self._calculate_liquidity_risk(position.symbol)
            risk_metrics["liquidity_risk"] = liquidity_risk

            # 计算综合风险分数
            risk_score = (var / position.price) * position.leverage + liquidity_risk
            risk_metrics["risk_score"] = risk_score

            # 确定风险等级
            risk_level = self._get_risk_level(risk_score)
            risk_metrics["risk_level"] = risk_level.value

            return risk_metrics
        except Exception as e:
            logger.error(f"Error assessing position risk: {e}")
            return {}

    async def _calculate_portfolio_risk(self) -> Dict[RiskMetricType, float]:
        """计算投资组合风险

        Returns:
            Dict[RiskMetricType, float]: 风险指标
        """
        try:
            # 模拟投资组合数据
            symbols = list(self.positions.keys())
            if not symbols:
                return {}

            # 模拟收益率数据
            returns = np.random.normal(0, 0.02, (252, len(symbols)))  # 一年的日收益率
            
            # 计算协方差矩阵
            cov_matrix = LedoitWolf().fit(returns).covariance_
            
            # 模拟持仓权重
            weights = np.array([self.positions[symbol].amount * self.positions[symbol].price for symbol in symbols])
            weights = weights / np.sum(weights) if np.sum(weights) > 0 else np.ones(len(symbols)) / len(symbols)
            
            # 计算投资组合波动率
            portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            
            # 计算VaR
            var = portfolio_volatility * np.sqrt(self.var_horizon) * norm.ppf(self.var_confidence)
            
            # 计算CVaR
            cvar = portfolio_volatility * np.sqrt(self.var_horizon) * norm.pdf(norm.ppf(self.var_confidence)) / (1 - self.var_confidence)
            
            # 计算贝塔系数（模拟）
            beta = np.random.normal(1, 0.3)
            
            # 计算流动性风险（模拟）
            liquidity_risk = np.random.normal(0.1, 0.05)
            
            # 计算系统性风险（模拟）
            systemic_risk = np.random.normal(0.15, 0.05)
            
            return {
                RiskMetricType.VAR: var,
                RiskMetricType.CVAR: cvar,
                RiskMetricType.VOLATILITY: portfolio_volatility,
                RiskMetricType.BETA: beta,
                RiskMetricType.LIQUIDITY_RISK: liquidity_risk,
                RiskMetricType.SYSTEMIC_RISK: systemic_risk
            }
        except Exception as e:
            logger.error(f"Error calculating portfolio risk: {e}")
            return {}

    async def _calculate_max_drawdown(self) -> float:
        """计算最大回撤

        Returns:
            float: 最大回撤
        """
        try:
            # 模拟历史净值数据
            nav = [1.0]
            for _ in range(100):
                nav.append(nav[-1] * (1 + np.random.normal(0, 0.02)))
            
            # 计算回撤
            drawdowns = []
            peak = nav[0]
            for value in nav[1:]:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak
                drawdowns.append(drawdown)
            
            return max(drawdowns) if drawdowns else 0.0
        except Exception as e:
            logger.error(f"Error calculating max drawdown: {e}")
            return 0.0

    async def _calculate_sharpe_ratio(self) -> float:
        """计算夏普比率

        Returns:
            float: 夏普比率
        """
        try:
            # 模拟收益率数据
            returns = np.random.normal(0.0005, 0.02, 252)  # 日收益率
            risk_free_rate = 0.0001  # 无风险利率
            
            # 计算夏普比率
            excess_returns = returns - risk_free_rate
            sharpe_ratio = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)  # 年化
            
            return sharpe_ratio
        except Exception as e:
            logger.error(f"Error calculating sharpe ratio: {e}")
            return 0.0

    async def _calculate_sortino_ratio(self) -> float:
        """计算索提诺比率

        Returns:
            float: 索提诺比率
        """
        try:
            # 模拟收益率数据
            returns = np.random.normal(0.0005, 0.02, 252)  # 日收益率
            risk_free_rate = 0.0001  # 无风险利率
            
            # 计算索提诺比率
            excess_returns = returns - risk_free_rate
            downside_returns = [r for r in excess_returns if r < 0]
            downside_std = np.std(downside_returns) if downside_returns else 1.0
            sortino_ratio = np.mean(excess_returns) / downside_std * np.sqrt(252)  # 年化
            
            return sortino_ratio
        except Exception as e:
            logger.error(f"Error calculating sortino ratio: {e}")
            return 0.0

    async def _calculate_liquidity_risk(self, symbol: str) -> float:
        """计算流动性风险

        Args:
            symbol: 交易对

        Returns:
            float: 流动性风险分数
        """
        try:
            # 模拟流动性风险
            # 实际应该基于交易量、买卖价差等计算
            return np.random.normal(0.1, 0.05)
        except Exception as e:
            logger.error(f"Error calculating liquidity risk: {e}")
            return 0.5

    async def _calculate_risk_score(self, metrics: Dict[RiskMetricType, float]) -> float:
        """计算综合风险分数

        Args:
            metrics: 风险指标

        Returns:
            float: 风险分数
        """
        try:
            if not metrics:
                return 0.0

            # 权重
            weights = {
                RiskMetricType.VAR: 0.2,
                RiskMetricType.CVAR: 0.2,
                RiskMetricType.MAX_DRAWDOWN: 0.15,
                RiskMetricType.VOLATILITY: 0.15,
                RiskMetricType.LIQUIDITY_RISK: 0.1,
                RiskMetricType.SYSTEMIC_RISK: 0.1,
                RiskMetricType.SHARPE_RATIO: -0.05,  # 负权重，夏普比率越高风险越低
                RiskMetricType.SORTINO_RATIO: -0.05  # 负权重，索提诺比率越高风险越低
            }

            # 计算加权风险分数
            risk_score = 0.0
            total_weight = 0.0

            for metric, value in metrics.items():
                if metric in weights:
                    # 标准化值
                    if metric in [RiskMetricType.SHARPE_RATIO, RiskMetricType.SORTINO_RATIO]:
                        # 对于比率指标，进行标准化
                        normalized_value = min(1.0, max(-1.0, value / 5))
                    else:
                        # 对于风险指标，进行标准化
                        normalized_value = min(1.0, value)
                    
                    risk_score += normalized_value * weights[metric]
                    total_weight += abs(weights[metric])

            if total_weight > 0:
                risk_score = risk_score / total_weight
            
            # 确保风险分数在0-1之间
            return max(0.0, min(1.0, risk_score))
        except Exception as e:
            logger.error(f"Error calculating risk score: {e}")
            return 0.5

    def _get_risk_level(self, risk_score: float) -> RiskLevel:
        """根据风险分数确定风险等级

        Args:
            risk_score: 风险分数

        Returns:
            RiskLevel: 风险等级
        """
        if risk_score >= self.risk_thresholds["extreme"]:
            return RiskLevel.EXTREME
        elif risk_score >= self.risk_thresholds["high"]:
            return RiskLevel.HIGH
        elif risk_score >= self.risk_thresholds["medium"]:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    async def _generate_recommendations(self, metrics: Dict[RiskMetricType, float], risk_level: RiskLevel) -> List[str]:
        """生成风险建议

        Args:
            metrics: 风险指标
            risk_level: 风险等级

        Returns:
            List[str]: 建议列表
        """
        recommendations = []

        if risk_level in [RiskLevel.HIGH, RiskLevel.EXTREME]:
            recommendations.append("降低仓位以控制风险")
            recommendations.append("增加止损位以限制潜在损失")
            recommendations.append("减少杠杆使用")
            
            if RiskMetricType.VOLATILITY in metrics and metrics[RiskMetricType.VOLATILITY] > 0.03:
                recommendations.append("考虑对冲策略以降低波动率")
            
            if RiskMetricType.LIQUIDITY_RISK in metrics and metrics[RiskMetricType.LIQUIDITY_RISK] > 0.3:
                recommendations.append("减少流动性差的资产持仓")
        elif risk_level == RiskLevel.MEDIUM:
            recommendations.append("保持当前仓位，但密切监控风险")
            recommendations.append("确保止损位设置合理")
        else:
            recommendations.append("风险水平可接受，可以考虑适当增加仓位")

        # 基于夏普比率的建议
        if RiskMetricType.SHARPE_RATIO in metrics:
            sharpe = metrics[RiskMetricType.SHARPE_RATIO]
            if sharpe > 1.5:
                recommendations.append("夏普比率良好，可以考虑增加风险敞口")
            elif sharpe < 0.5:
                recommendations.append("夏普比率较低，建议调整投资组合")

        return recommendations

    async def _calculate_confidence(self, metrics: Dict[RiskMetricType, float]) -> float:
        """计算风险评估的置信度

        Args:
            metrics: 风险指标

        Returns:
            float: 置信度
        """
        try:
            # 基于指标数量和数据质量计算置信度
            if not metrics:
                return 0.3
            
            # 指标数量越多，置信度越高
            metric_count = len(metrics)
            base_confidence = min(1.0, metric_count / 8)  # 假设最多8个指标
            
            # 对于关键指标的存在给予额外置信度
            key_metrics = [RiskMetricType.VAR, RiskMetricType.MAX_DRAWDOWN, RiskMetricType.SHARPE_RATIO]
            key_metric_count = sum(1 for metric in key_metrics if metric in metrics)
            confidence_boost = key_metric_count * 0.1
            
            total_confidence = min(1.0, base_confidence + confidence_boost)
            return total_confidence
        except Exception as e:
            logger.error(f"Error calculating confidence: {e}")
            return 0.5

    async def _execute_risk_control(self, assessment: RiskAssessment):
        """执行风险控制措施

        Args:
            assessment: 风险评估结果
        """
        try:
            # 基于风险等级执行不同的控制措施
            if assessment.risk_level == RiskLevel.EXTREME:
                # 极端风险：平仓部分高风险仓位
                await self._reduce_position_sizes(0.5)  # 减少50%仓位
                await self._set_stricter_stop_losses()
            elif assessment.risk_level == RiskLevel.HIGH:
                # 高风险：减少仓位和调整止损
                await self._reduce_position_sizes(0.3)  # 减少30%仓位
                await self._set_stricter_stop_losses()
        except Exception as e:
            logger.error(f"Error executing risk control: {e}")

    async def _reduce_position_sizes(self, reduction_factor: float):
        """减少仓位大小

        Args:
            reduction_factor: 减少比例
        """
        try:
            for symbol, position in list(self.positions.items()):
                # 减少仓位
                new_amount = position.amount * (1 - reduction_factor)
                if new_amount > 0:
                    position.amount = new_amount
                    logger.info(f"Reduced position size for {symbol} by {reduction_factor * 100}%")
                else:
                    # 平仓
                    del self.positions[symbol]
                    logger.info(f"Closed position for {symbol} due to risk control")
        except Exception as e:
            logger.error(f"Error reducing position sizes: {e}")

    async def _set_stricter_stop_losses(self):
        """设置更严格的止损位"""
        try:
            for symbol, position in self.positions.items():
                # 设置更严格的止损位（例如，从5%调整到3%）
                if position.stop_loss is None:
                    # 如果没有设置止损，设置一个
                    position.stop_loss = position.price * 0.97  # 3%止损
                else:
                    # 调整现有止损位
                    current_stop_loss = position.stop_loss
                    new_stop_loss = position.price * 0.97  # 3%止损
                    if new_stop_loss > current_stop_loss:  # 更严格的止损
                        position.stop_loss = new_stop_loss
                logger.info(f"Set stricter stop loss for {symbol} at {position.stop_loss}")
        except Exception as e:
            logger.error(f"Error setting stricter stop losses: {e}")

    async def add_position(self, symbol: str, amount: float, price: float, leverage: float = 1.0, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> bool:
        """添加持仓

        Args:
            symbol: 交易对
            amount: 数量
            price: 价格
            leverage: 杠杆
            stop_loss: 止损价格
            take_profit: 止盈价格

        Returns:
            bool: 是否添加成功
        """
        try:
            # 检查杠杆是否超过限制
            if leverage > self.max_leverage:
                logger.warning(f"Leverage {leverage} exceeds maximum allowed {self.max_leverage}")
                return False

            # 检查仓位大小是否超过限制
            position_value = amount * price
            total_value = sum(p.amount * p.price for p in self.positions.values()) + position_value
            if position_value / total_value > self.max_position_size:
                logger.warning(f"Position size exceeds maximum allowed {self.max_position_size}")
                return False

            # 创建持仓
            position = Position(
                symbol=symbol,
                amount=amount,
                price=price,
                entry_time=time.time(),
                stop_loss=stop_loss,
                take_profit=take_profit,
                leverage=leverage
            )

            # 评估持仓风险
            risk_metrics = await self.assess_position_risk(position)
            risk_score = risk_metrics.get("risk_score", 0.0)
            risk_level = RiskLevel(risk_metrics.get("risk_level", "medium"))

            if risk_level in [RiskLevel.HIGH, RiskLevel.EXTREME]:
                logger.warning(f"Position risk too high: {risk_level.value}, score: {risk_score}")
                return False

            # 添加持仓
            self.positions[symbol] = position
            logger.info(f"Added position for {symbol}: {amount} at {price}")
            return True
        except Exception as e:
            logger.error(f"Error adding position: {e}")
            return False

    async def remove_position(self, symbol: str) -> bool:
        """移除持仓

        Args:
            symbol: 交易对

        Returns:
            bool: 是否移除成功
        """
        try:
            if symbol in self.positions:
                del self.positions[symbol]
                logger.info(f"Removed position for {symbol}")
                return True
            else:
                logger.warning(f"Position for {symbol} not found")
                return False
        except Exception as e:
            logger.error(f"Error removing position: {e}")
            return False

    async def _load_risk_history(self):
        """加载风险历史数据"""
        try:
            # 这里应该从数据库加载历史风险数据
            # 暂时使用模拟数据
            pass
        except Exception as e:
            logger.error(f"Error loading risk history: {e}")

    def get_positions(self) -> Dict[str, Position]:
        """获取所有持仓

        Returns:
            Dict[str, Position]: 持仓字典
        """
        return self.positions

    def get_risk_history(self, limit: int = 100) -> List[RiskAssessment]:
        """获取风险历史

        Args:
            limit: 返回的历史记录数量

        Returns:
            List[RiskAssessment]: 风险评估历史
        """
        return self.risk_history[-limit:]

    def is_healthy(self) -> bool:
        """检查风险管理系统健康状态

        Returns:
            bool: 健康状态
        """
        return self.enabled