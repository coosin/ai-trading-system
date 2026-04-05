"""
动态仓位管理系统

功能：
1. 基于市场波动率动态调整仓位
2. 基于账户风险状态调整仓位
3. 基于策略表现动态调整仓位
4. 支持多品种仓位分散
"""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """市场状态"""
    LOW_VOLATILITY = "low_volatility"
    NORMAL_VOLATILITY = "normal_volatility"
    HIGH_VOLATILITY = "high_volatility"
    EXTREME_VOLATILITY = "extreme_volatility"


class RiskState(Enum):
    """风险状态"""
    SAFE = "safe"
    CAUTION = "caution"
    WARNING = "warning"
    DANGER = "danger"


@dataclass
class PositionLimit:
    """仓位限制"""
    symbol: str
    max_position_value: float
    max_position_ratio: float
    current_position_value: float = 0.0
    current_position_ratio: float = 0.0
    available_ratio: float = 1.0


@dataclass
class DynamicPositionConfig:
    """动态仓位配置"""
    base_position_ratio: float = 0.1
    min_position_ratio: float = 0.01
    max_position_ratio: float = 0.3
    
    volatility_adjustment_factor: float = 0.5
    risk_adjustment_factor: float = 0.3
    performance_adjustment_factor: float = 0.2
    
    max_total_position_ratio: float = 0.8
    max_single_position_ratio: float = 0.2
    max_correlated_position_ratio: float = 0.4
    
    rebalance_interval: int = 300
    min_rebalance_change: float = 0.05


class DynamicPositionManager:
    """动态仓位管理器"""
    
    def __init__(self, config: Optional[DynamicPositionConfig] = None):
        self.config = config or DynamicPositionConfig()
        
        self.position_limits: Dict[str, PositionLimit] = {}
        self.market_regimes: Dict[str, MarketRegime] = {}
        self.risk_state = RiskState.SAFE
        
        self.volatility_history: Dict[str, List[float]] = {}
        self.performance_metrics: Dict[str, Dict] = {}
        
        self.total_position_ratio = 0.0
        self.last_rebalance_time: Optional[datetime] = None
        
        self._callbacks: List[callable] = []
    
    async def initialize(self) -> bool:
        """初始化动态仓位管理器"""
        logger.info("动态仓位管理器初始化...")
        return True
    
    def register_callback(self, callback: callable):
        """注册仓位变化回调"""
        self._callbacks.append(callback)
    
    async def calculate_dynamic_position_size(
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
        adjustment_details = {
            "symbol": symbol,
            "base_size": base_size,
            "adjustments": [],
            "final_size": base_size,
            "adjustment_ratio": 1.0
        }
        
        total_adjustment = 1.0
        
        volatility_adj = await self._calculate_volatility_adjustment(symbol, market_data)
        total_adjustment *= volatility_adj
        adjustment_details["adjustments"].append({
            "type": "volatility",
            "factor": volatility_adj,
            "reason": f"波动率调整: {volatility_adj:.2f}"
        })
        
        risk_adj = await self._calculate_risk_adjustment(account_balance, current_positions)
        total_adjustment *= risk_adj
        adjustment_details["adjustments"].append({
            "type": "risk",
            "factor": risk_adj,
            "reason": f"风险状态调整: {risk_adj:.2f}"
        })
        
        performance_adj = await self._calculate_performance_adjustment(symbol)
        total_adjustment *= performance_adj
        adjustment_details["adjustments"].append({
            "type": "performance",
            "factor": performance_adj,
            "reason": f"策略表现调整: {performance_adj:.2f}"
        })
        
        correlation_adj = await self._calculate_correlation_adjustment(symbol, current_positions)
        total_adjustment *= correlation_adj
        adjustment_details["adjustments"].append({
            "type": "correlation",
            "factor": correlation_adj,
            "reason": f"相关性调整: {correlation_adj:.2f}"
        })
        
        final_size = base_size * total_adjustment
        
        max_position_value = account_balance * self.config.max_single_position_ratio
        final_size = min(final_size, max_position_value)
        
        available_ratio = 1.0 - self.total_position_ratio
        max_available = account_balance * available_ratio
        final_size = min(final_size, max_available * 0.9)
        
        final_size = max(final_size, account_balance * self.config.min_position_ratio)
        
        adjustment_details["final_size"] = final_size
        adjustment_details["adjustment_ratio"] = total_adjustment
        
        return final_size, adjustment_details
    
    async def _calculate_volatility_adjustment(
        self,
        symbol: str,
        market_data: Optional[Dict]
    ) -> float:
        """基于波动率计算调整因子"""
        if not market_data:
            return 1.0
        
        volatility = market_data.get("volatility", 0.02)
        
        regime = self._classify_volatility_regime(volatility)
        self.market_regimes[symbol] = regime
        
        adjustments = {
            MarketRegime.LOW_VOLATILITY: 1.2,
            MarketRegime.NORMAL_VOLATILITY: 1.0,
            MarketRegime.HIGH_VOLATILITY: 0.7,
            MarketRegime.EXTREME_VOLATILITY: 0.4
        }
        
        return adjustments.get(regime, 1.0)
    
    def _classify_volatility_regime(self, volatility: float) -> MarketRegime:
        """分类波动率状态"""
        if volatility < 0.01:
            return MarketRegime.LOW_VOLATILITY
        elif volatility < 0.03:
            return MarketRegime.NORMAL_VOLATILITY
        elif volatility < 0.06:
            return MarketRegime.HIGH_VOLATILITY
        else:
            return MarketRegime.EXTREME_VOLATILITY
    
    async def _calculate_risk_adjustment(
        self,
        account_balance: float,
        current_positions: Dict[str, Any]
    ) -> float:
        """基于风险状态计算调整因子"""
        total_position_value = sum(
            pos.get("value", 0) for pos in current_positions.values()
        )
        
        position_ratio = total_position_value / account_balance if account_balance > 0 else 0
        
        if position_ratio < 0.3:
            self.risk_state = RiskState.SAFE
            return 1.2
        elif position_ratio < 0.5:
            self.risk_state = RiskState.CAUTION
            return 1.0
        elif position_ratio < 0.7:
            self.risk_state = RiskState.WARNING
            return 0.7
        else:
            self.risk_state = RiskState.DANGER
            return 0.4
    
    async def _calculate_performance_adjustment(self, symbol: str) -> float:
        """基于策略表现计算调整因子"""
        metrics = self.performance_metrics.get(symbol, {})
        
        if not metrics:
            return 1.0
        
        win_rate = metrics.get("win_rate", 0.5)
        profit_factor = metrics.get("profit_factor", 1.0)
        sharpe = metrics.get("sharpe_ratio", 0)
        
        adjustment = 1.0
        
        if win_rate > 0.6:
            adjustment *= 1.1
        elif win_rate < 0.4:
            adjustment *= 0.9
        
        if profit_factor > 1.5:
            adjustment *= 1.1
        elif profit_factor < 0.8:
            adjustment *= 0.8
        
        if sharpe > 1.0:
            adjustment *= 1.05
        elif sharpe < 0:
            adjustment *= 0.9
        
        return max(0.5, min(1.5, adjustment))
    
    async def _calculate_correlation_adjustment(
        self,
        symbol: str,
        current_positions: Dict[str, Any]
    ) -> float:
        """基于品种相关性计算调整因子"""
        if not current_positions:
            return 1.0
        
        correlated_count = 0
        for existing_symbol in current_positions:
            if self._are_correlated(symbol, existing_symbol):
                correlated_count += 1
        
        if correlated_count == 0:
            return 1.0
        elif correlated_count == 1:
            return 0.8
        elif correlated_count == 2:
            return 0.6
        else:
            return 0.4
    
    def _are_correlated(self, symbol1: str, symbol2: str) -> bool:
        """判断两个品种是否相关"""
        correlated_groups = [
            {"BTC", "BCH", "BSV"},
            {"ETH", "ETC"},
            {"DOT", "KSM"},
            {"ATOM", "OSMO"},
            {"SOL", "SRM"},
            {"AVAX", "JOE"},
            {"MATIC", "POL"},
        ]
        
        base1 = symbol1.replace("USDT", "").replace("USDC", "").replace("/", "")
        base2 = symbol2.replace("USDT", "").replace("USDC", "").replace("/", "")
        
        for group in correlated_groups:
            if base1 in group and base2 in group:
                return True
        
        return False
    
    async def update_performance_metrics(
        self,
        symbol: str,
        metrics: Dict[str, Any]
    ):
        """更新策略表现指标"""
        self.performance_metrics[symbol] = {
            **metrics,
            "updated_at": datetime.now().isoformat()
        }
    
    async def check_rebalance_needed(
        self,
        account_balance: float,
        current_positions: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """检查是否需要重新平衡仓位"""
        now = datetime.now()
        
        if self.last_rebalance_time:
            time_since_last = (now - self.last_rebalance_time).total_seconds()
            if time_since_last < self.config.rebalance_interval:
                return False, {"reason": "间隔时间未到"}
        
        total_position_value = sum(
            pos.get("value", 0) for pos in current_positions.values()
        )
        current_ratio = total_position_value / account_balance if account_balance > 0 else 0
        
        ratio_change = abs(current_ratio - self.total_position_ratio)
        
        if ratio_change >= self.config.min_rebalance_change:
            return True, {
                "reason": "仓位比例变化超过阈值",
                "change": ratio_change,
                "current_ratio": current_ratio,
                "tracked_ratio": self.total_position_ratio
            }
        
        return False, {"reason": "仓位变化在可接受范围内"}
    
    async def get_position_recommendations(
        self,
        account_balance: float,
        current_positions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """获取仓位调整建议"""
        recommendations = {
            "total_position_ratio": self.total_position_ratio,
            "risk_state": self.risk_state.value,
            "market_regimes": {k: v.value for k, v in self.market_regimes.items()},
            "suggestions": []
        }
        
        if self.risk_state == RiskState.DANGER:
            recommendations["suggestions"].append({
                "type": "reduce",
                "priority": "high",
                "message": "风险状态危险，建议减少总仓位至50%以下"
            })
        
        for symbol, regime in self.market_regimes.items():
            if regime == MarketRegime.EXTREME_VOLATILITY:
                recommendations["suggestions"].append({
                    "type": "caution",
                    "priority": "high",
                    "symbol": symbol,
                    "message": f"{symbol} 波动率极高，建议降低仓位"
                })
        
        return recommendations
    
    async def cleanup(self):
        """清理资源"""
        logger.info("动态仓位管理器清理完成")
