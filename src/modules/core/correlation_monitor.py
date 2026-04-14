"""
品种相关性监控系统

功能：
1. 实时计算品种间相关性
2. 检测相关性变化
3. 预警过度集中风险
4. 提供分散化建议
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import math

import numpy as np

logger = logging.getLogger(__name__)


class CorrelationLevel(Enum):
    """相关性等级"""
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class CorrelationMatrix:
    """相关性矩阵"""
    symbols: List[str]
    matrix: np.ndarray
    timestamp: datetime = field(default_factory=datetime.now)
    lookback_period: int = 30


@dataclass
class CorrelationAlert:
    """相关性预警"""
    symbol1: str
    symbol2: str
    correlation: float
    level: CorrelationLevel
    message: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CorrelationMonitorConfig:
    """相关性监控配置"""
    correlation_threshold_high: float = 0.7
    correlation_threshold_extreme: float = 0.9
    lookback_periods: int = 30
    update_interval: int = 300
    max_correlated_exposure: float = 0.4
    alert_cooldown: int = 3600


class CorrelationMonitor:
    """品种相关性监控器"""
    
    def __init__(self, config: Optional[CorrelationMonitorConfig] = None):
        self.config = config or CorrelationMonitorConfig()
        
        self.price_history: Dict[str, List[Tuple[datetime, float]]] = {}
        self.returns_history: Dict[str, List[float]] = {}
        
        self.correlation_matrix: Optional[CorrelationMatrix] = None
        self.correlation_cache: Dict[Tuple[str, str], float] = {}
        
        self.alerts: List[CorrelationAlert] = []
        self.alert_history: Dict[Tuple[str, str], datetime] = {}
        
        self._callbacks: List[callable] = []
        self._running = False
    
    async def initialize(self) -> bool:
        """初始化相关性监控器"""
        logger.info("品种相关性监控器初始化...")
        return True
    
    def register_callback(self, callback: callable):
        """注册相关性预警回调"""
        self._callbacks.append(callback)
    
    async def update_price(self, symbol: str, price: float, timestamp: Optional[datetime] = None):
        """更新价格数据"""
        timestamp = timestamp or datetime.now()
        
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        self.price_history[symbol].append((timestamp, price))
        
        if len(self.price_history[symbol]) > 1:
            prev_price = self.price_history[symbol][-2][1]
            if prev_price > 0:
                ret = (price - prev_price) / prev_price
                
                if symbol not in self.returns_history:
                    self.returns_history[symbol] = []
                self.returns_history[symbol].append(ret)
        
        max_history = self.config.lookback_periods * 2
        if len(self.price_history[symbol]) > max_history:
            self.price_history[symbol] = self.price_history[symbol][-max_history:]
        if symbol in self.returns_history and len(self.returns_history[symbol]) > max_history:
            self.returns_history[symbol] = self.returns_history[symbol][-max_history:]
    
    async def calculate_correlation(self, symbol1: str, symbol2: str) -> float:
        """计算两个品种的相关性"""
        cache_key = tuple(sorted([symbol1, symbol2]))
        
        if symbol1 not in self.returns_history or symbol2 not in self.returns_history:
            return 0.0
        
        returns1 = self.returns_history[symbol1]
        returns2 = self.returns_history[symbol2]
        
        min_len = min(len(returns1), len(returns2))
        if min_len < 10:
            return 0.0
        
        lookback = min(self.config.lookback_periods, min_len)
        r1 = np.array(returns1[-lookback:])
        r2 = np.array(returns2[-lookback:])
        
        if np.std(r1) == 0 or np.std(r2) == 0:
            return 0.0
        
        correlation = np.corrcoef(r1, r2)[0, 1]
        
        if np.isnan(correlation):
            correlation = 0.0
        
        self.correlation_cache[cache_key] = float(correlation)
        
        return float(correlation)
    
    async def update_correlation_matrix(self) -> CorrelationMatrix:
        """更新相关性矩阵"""
        symbols = list(self.returns_history.keys())
        
        if len(symbols) < 2:
            return CorrelationMatrix(symbols=symbols, matrix=np.array([]))
        
        n = len(symbols)
        matrix = np.eye(n)
        
        for i in range(n):
            for j in range(i + 1, n):
                corr = await self.calculate_correlation(symbols[i], symbols[j])
                matrix[i, j] = corr
                matrix[j, i] = corr
        
        self.correlation_matrix = CorrelationMatrix(
            symbols=symbols,
            matrix=matrix,
            lookback_period=self.config.lookback_periods
        )
        
        return self.correlation_matrix
    
    def classify_correlation(self, correlation: float) -> CorrelationLevel:
        """分类相关性等级"""
        abs_corr = abs(correlation)
        
        if abs_corr < 0.3:
            return CorrelationLevel.NONE
        elif abs_corr < 0.5:
            return CorrelationLevel.LOW
        elif abs_corr < 0.7:
            return CorrelationLevel.MODERATE
        elif abs_corr < 0.9:
            return CorrelationLevel.HIGH
        else:
            return CorrelationLevel.EXTREME
    
    async def check_correlation_risks(
        self,
        current_positions: Dict[str, Any]
    ) -> List[CorrelationAlert]:
        """检查相关性风险"""
        alerts = []
        
        if not self.correlation_matrix:
            await self.update_correlation_matrix()
        
        if not self.correlation_matrix or len(self.correlation_matrix.symbols) < 2:
            return alerts
        
        position_symbols = list(current_positions.keys())
        
        for i, symbol1 in enumerate(position_symbols):
            for symbol2 in position_symbols[i + 1:]:
                if symbol1 not in self.correlation_matrix.symbols:
                    continue
                if symbol2 not in self.correlation_matrix.symbols:
                    continue
                
                idx1 = self.correlation_matrix.symbols.index(symbol1)
                idx2 = self.correlation_matrix.symbols.index(symbol2)
                
                correlation = self.correlation_matrix.matrix[idx1, idx2]
                level = self.classify_correlation(correlation)
                
                if level in [CorrelationLevel.HIGH, CorrelationLevel.EXTREME]:
                    alert_key = tuple(sorted([symbol1, symbol2]))
                    
                    if alert_key in self.alert_history:
                        last_alert = self.alert_history[alert_key]
                        if (datetime.now() - last_alert).total_seconds() < self.config.alert_cooldown:
                            continue
                    
                    alert = CorrelationAlert(
                        symbol1=symbol1,
                        symbol2=symbol2,
                        correlation=correlation,
                        level=level,
                        message=f"高相关性预警: {symbol1} 与 {symbol2} 相关性 {correlation:.2f}"
                    )
                    alerts.append(alert)
                    self.alerts.append(alert)
                    self.alert_history[alert_key] = datetime.now()
                    
                    await self._notify_alert(alert)
        
        return alerts
    
    async def calculate_correlated_exposure(
        self,
        current_positions: Dict[str, Any],
        account_balance: float
    ) -> Dict[str, Any]:
        """计算相关性敞口"""
        result = {
            "total_exposure": 0.0,
            "correlated_groups": [],
            "risk_level": "low",
            "recommendations": []
        }
        
        if not current_positions:
            return result
        
        total_value = sum(pos.get("value", 0) for pos in current_positions.values())
        result["total_exposure"] = total_value / account_balance if account_balance > 0 else 0
        
        correlated_groups = self._identify_correlated_groups(current_positions)
        
        for group in correlated_groups:
            group_value = sum(
                current_positions[symbol].get("value", 0)
                for symbol in group["symbols"]
                if symbol in current_positions
            )
            group_ratio = group_value / account_balance if account_balance > 0 else 0
            
            result["correlated_groups"].append({
                "symbols": group["symbols"],
                "correlation": group["avg_correlation"],
                "exposure_ratio": group_ratio
            })
            
            if group_ratio > self.config.max_correlated_exposure:
                result["risk_level"] = "high"
                result["recommendations"].append({
                    "type": "reduce_correlated",
                    "symbols": group["symbols"],
                    "current_ratio": group_ratio,
                    "max_ratio": self.config.max_correlated_exposure,
                    "message": f"相关性敞口过高: {group['symbols']} 共计 {group_ratio:.1%}"
                })
        
        return result
    
    def _identify_correlated_groups(
        self,
        current_positions: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """识别相关性分组"""
        groups = []
        processed = set()
        
        position_symbols = list(current_positions.keys())
        
        for symbol1 in position_symbols:
            if symbol1 in processed:
                continue
            
            group_symbols = [symbol1]
            correlations = []
            
            for symbol2 in position_symbols:
                if symbol2 == symbol1 or symbol2 in processed:
                    continue
                
                cache_key = tuple(sorted([symbol1, symbol2]))
                correlation = self.correlation_cache.get(cache_key, 0)
                
                if abs(correlation) >= self.config.correlation_threshold_high:
                    group_symbols.append(symbol2)
                    correlations.append(abs(correlation))
            
            if len(group_symbols) > 1:
                avg_corr = sum(correlations) / len(correlations) if correlations else 0
                groups.append({
                    "symbols": group_symbols,
                    "avg_correlation": avg_corr
                })
                processed.update(group_symbols)
        
        return groups
    
    async def get_diversification_score(
        self,
        current_positions: Dict[str, Any]
    ) -> float:
        """计算分散化得分"""
        if not current_positions or len(current_positions) < 2:
            return 1.0
        
        if not self.correlation_matrix:
            await self.update_correlation_matrix()
        
        if not self.correlation_matrix:
            return 1.0
        
        position_symbols = list(current_positions.keys())
        n = len(position_symbols)
        
        if n < 2:
            return 1.0
        
        total_correlation = 0
        pair_count = 0
        
        for i in range(n):
            for j in range(i + 1, n):
                symbol1, symbol2 = position_symbols[i], position_symbols[j]
                
                if symbol1 in self.correlation_matrix.symbols and symbol2 in self.correlation_matrix.symbols:
                    idx1 = self.correlation_matrix.symbols.index(symbol1)
                    idx2 = self.correlation_matrix.symbols.index(symbol2)
                    total_correlation += abs(self.correlation_matrix.matrix[idx1, idx2])
                    pair_count += 1
        
        if pair_count == 0:
            return 1.0
        
        avg_correlation = total_correlation / pair_count
        
        diversification_score = 1 - avg_correlation
        
        return max(0, min(1, diversification_score))
    
    async def _notify_alert(self, alert: CorrelationAlert):
        """通知相关性预警"""
        for callback in self._callbacks:
            try:
                await callback(alert)
            except Exception as e:
                logger.error(f"相关性预警回调失败: {e}")
    
    async def get_correlation_summary(self) -> Dict[str, Any]:
        """获取相关性摘要"""
        summary = {
            "matrix_updated": self.correlation_matrix.timestamp.isoformat() if self.correlation_matrix else None,
            "symbols_count": len(self.correlation_matrix.symbols) if self.correlation_matrix else 0,
            "high_correlation_pairs": [],
            "recent_alerts": []
        }
        
        if self.correlation_matrix and len(self.correlation_matrix.symbols) > 1:
            symbols = self.correlation_matrix.symbols
            matrix = self.correlation_matrix.matrix
            
            for i in range(len(symbols)):
                for j in range(i + 1, len(symbols)):
                    corr = matrix[i, j]
                    if abs(corr) >= self.config.correlation_threshold_high:
                        summary["high_correlation_pairs"].append({
                            "symbol1": symbols[i],
                            "symbol2": symbols[j],
                            "correlation": round(corr, 3)
                        })
        
        for alert in self.alerts[-5:]:
            summary["recent_alerts"].append({
                "symbols": [alert.symbol1, alert.symbol2],
                "correlation": round(alert.correlation, 3),
                "level": alert.level.value,
                "message": alert.message
            })
        
        return summary
    
    async def cleanup(self):
        """清理资源"""
        self._running = False
        logger.info("品种相关性监控器清理完成")
