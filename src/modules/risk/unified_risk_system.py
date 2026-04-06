"""
统一风险系统

整合所有风险管理功能：
1. 风险评估
2. 风险监控
3. 风险优化
4. 风险报告
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UnifiedRiskSystem:
    """
    统一风险系统
    
    整合所有风险管理功能，提供统一接口
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化统一风险系统
        
        Args:
            config: 配置字典
        """
        self.config = config or {}
        
        # 子模块（保留现有模块的引用）
        self.assessor = None
        self.monitor = None
        self.optimizer = None
        
        # 风险指标
        self.risk_metrics: Dict[str, Any] = {}
        
        # 风险历史
        self.risk_history: List[Dict] = []
        
        # 风险阈值
        self.risk_thresholds = {
            "max_drawdown": 0.2,  # 最大回撤
            "max_leverage": 3.0,  # 最大杠杆
            "max_position_size": 0.1,  # 最大仓位
            "max_daily_loss": 0.05,  # 最大日损失
        }
        
        # 统计信息
        self.stats = {
            "total_assessments": 0,
            "high_risk_events": 0,
            "critical_risk_events": 0,
            "last_assessment": None
        }
        
        logger.info("统一风险系统初始化")
    
    async def initialize(self) -> bool:
        """
        初始化所有子模块
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            logger.info("🔧 初始化统一风险系统...")
            
            # 初始化风险评估器
            await self._init_assessor()
            
            # 初始化风险监控器
            await self._init_monitor()
            
            # 初始化风险优化器
            await self._init_optimizer()
            
            logger.info("✅ 统一风险系统初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 统一风险系统初始化失败: {e}")
            return False
    
    async def _init_assessor(self):
        """初始化风险评估器"""
        try:
            # 风险评估功能整合到此系统
            self.assessor = {}
            logger.info("✅ 风险评估器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 风险评估器初始化失败: {e}")
            self.assessor = None
    
    async def _init_monitor(self):
        """初始化风险监控器"""
        try:
            from src.modules.monitoring.intelligent_monitoring import IntelligentMonitoringSystem
            self.monitor = IntelligentMonitoringSystem()
            logger.info("✅ 风险监控器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 风险监控器初始化失败: {e}")
            self.monitor = None
    
    async def _init_optimizer(self):
        """初始化风险优化器"""
        try:
            from src.modules.strategies.portfolio_optimizer import PortfolioOptimizer
            self.optimizer = PortfolioOptimizer()
            logger.info("✅ 风险优化器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 风险优化器初始化失败: {e}")
            self.optimizer = None
    
    # ==================== 风险评估 ====================
    
    async def assess_risk(self, portfolio: Dict[str, Any]) -> Dict[str, Any]:
        """
        评估风险
        
        Args:
            portfolio: 投资组合信息
        
        Returns:
            Dict: 风险评估结果
        """
        try:
            # 计算风险指标
            metrics = await self._calculate_risk_metrics(portfolio)
            
            # 确定风险等级
            risk_level = self._determine_risk_level(metrics)
            
            # 生成风险评估报告
            assessment = {
                "timestamp": datetime.now(),
                "portfolio": portfolio,
                "metrics": metrics,
                "risk_level": risk_level,
                "recommendations": await self._generate_recommendations(metrics, risk_level)
            }
            
            # 保存到历史
            self.risk_history.append(assessment)
            
            # 更新统计
            self.stats["total_assessments"] += 1
            self.stats["last_assessment"] = datetime.now()
            
            if risk_level == RiskLevel.HIGH:
                self.stats["high_risk_events"] += 1
            elif risk_level == RiskLevel.CRITICAL:
                self.stats["critical_risk_events"] += 1
            
            logger.info(f"风险评估完成: {risk_level.value}")
            return assessment
            
        except Exception as e:
            logger.error(f"风险评估失败: {e}")
            return {"error": str(e)}
    
    async def _calculate_risk_metrics(self, portfolio: Dict) -> Dict[str, float]:
        """
        计算风险指标
        
        Args:
            portfolio: 投资组合
        
        Returns:
            Dict: 风险指标
        """
        try:
            metrics = {}
            
            # 计算回撤
            if "equity_curve" in portfolio:
                metrics["drawdown"] = self._calculate_drawdown(portfolio["equity_curve"])
            
            # 计算杠杆
            if "positions" in portfolio:
                metrics["leverage"] = self._calculate_leverage(portfolio["positions"])
            
            # 计算仓位集中度
            if "positions" in portfolio:
                metrics["concentration"] = self._calculate_concentration(portfolio["positions"])
            
            # 计算波动率
            if "returns" in portfolio:
                metrics["volatility"] = self._calculate_volatility(portfolio["returns"])
            
            return metrics
            
        except Exception as e:
            logger.error(f"计算风险指标失败: {e}")
            return {}
    
    def _calculate_drawdown(self, equity_curve: List[float]) -> float:
        """计算最大回撤"""
        try:
            if not equity_curve:
                return 0.0
            
            peak = equity_curve[0]
            max_drawdown = 0.0
            
            for equity in equity_curve:
                if equity > peak:
                    peak = equity
                
                drawdown = (peak - equity) / peak if peak > 0 else 0
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            
            return max_drawdown
        except Exception as e:
            logger.debug(f"计算最大回撤失败: {e}")
            return 0.0
    
    def _calculate_leverage(self, positions: List[Dict]) -> float:
        """计算杠杆"""
        try:
            if not positions:
                return 0.0
            
            total_value = sum(p.get("value", 0) for p in positions)
            total_margin = sum(p.get("margin", 0) for p in positions)
            
            return total_value / total_margin if total_margin > 0 else 0.0
        except Exception as e:
            logger.debug(f"计算杠杆失败: {e}")
            return 0.0
    
    def _calculate_concentration(self, positions: List[Dict]) -> float:
        """计算仓位集中度"""
        try:
            if not positions:
                return 0.0
            
            total_value = sum(p.get("value", 0) for p in positions)
            if total_value == 0:
                return 0.0
            
            max_position = max(p.get("value", 0) for p in positions)
            return max_position / total_value
        except Exception as e:
            logger.debug(f"计算仓位集中度失败: {e}")
            return 0.0
    
    def _calculate_volatility(self, returns: List[float]) -> float:
        """计算波动率"""
        try:
            if not returns:
                return 0.0
            
            import statistics
            return statistics.stdev(returns) if len(returns) > 1 else 0.0
        except Exception as e:
            logger.debug(f"计算波动率失败: {e}")
            return 0.0
    
    def _determine_risk_level(self, metrics: Dict[str, float]) -> RiskLevel:
        """
        确定风险等级
        
        Args:
            metrics: 风险指标
        
        Returns:
            RiskLevel: 风险等级
        """
        try:
            # 检查是否超过阈值
            if metrics.get("drawdown", 0) > self.risk_thresholds["max_drawdown"]:
                return RiskLevel.CRITICAL
            
            if metrics.get("leverage", 0) > self.risk_thresholds["max_leverage"]:
                return RiskLevel.HIGH
            
            if metrics.get("concentration", 0) > self.risk_thresholds["max_position_size"]:
                return RiskLevel.HIGH
            
            # 综合评估
            risk_score = 0
            for metric, value in metrics.items():
                if metric in self.risk_thresholds:
                    if value > self.risk_thresholds[metric]:
                        risk_score += 1
            
            if risk_score >= 3:
                return RiskLevel.CRITICAL
            elif risk_score >= 2:
                return RiskLevel.HIGH
            elif risk_score >= 1:
                return RiskLevel.MEDIUM
            else:
                return RiskLevel.LOW
            
        except Exception as e:
            logger.error(f"确定风险等级失败: {e}")
            return RiskLevel.MEDIUM
    
    async def _generate_recommendations(self, metrics: Dict, risk_level: RiskLevel) -> List[str]:
        """
        生成风险建议
        
        Args:
            metrics: 风险指标
            risk_level: 风险等级
        
        Returns:
            List[str]: 建议列表
        """
        recommendations = []
        
        if metrics.get("drawdown", 0) > self.risk_thresholds["max_drawdown"]:
            recommendations.append("减少仓位，控制回撤")
        
        if metrics.get("leverage", 0) > self.risk_thresholds["max_leverage"]:
            recommendations.append("降低杠杆，减少风险敞口")
        
        if metrics.get("concentration", 0) > self.risk_thresholds["max_position_size"]:
            recommendations.append("分散投资，降低集中度")
        
        if risk_level == RiskLevel.CRITICAL:
            recommendations.append("立即停止交易，重新评估策略")
        
        return recommendations
    
    # ==================== 风险监控 ====================
    
    async def monitor_risk(self) -> Dict[str, Any]:
        """
        监控风险
        
        Returns:
            Dict: 监控结果
        """
        try:
            # 使用监控器
            if self.monitor:
                try:
                    status = await self.monitor.get_system_status()
                    return {
                        "monitor_status": status,
                        "risk_metrics": self.risk_metrics
                    }
                except Exception as e:
                    logger.debug(f"风险监控器状态获取失败: {e}")
            
            return {
                "risk_metrics": self.risk_metrics,
                "last_update": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"监控风险失败: {e}")
            return {"error": str(e)}
    
    async def get_risk_alerts(self) -> List[Dict[str, Any]]:
        """
        获取风险告警
        
        Returns:
            List[Dict]: 告警列表
        """
        try:
            alerts = []
            
            # 检查风险指标
            for metric, value in self.risk_metrics.items():
                if metric in self.risk_thresholds:
                    if value > self.risk_thresholds[metric]:
                        alerts.append({
                            "metric": metric,
                            "value": value,
                            "threshold": self.risk_thresholds[metric],
                            "level": "high" if value > self.risk_thresholds[metric] * 1.5 else "medium",
                            "timestamp": datetime.now().isoformat()
                        })
            
            return alerts
            
        except Exception as e:
            logger.error(f"获取风险告警失败: {e}")
            return []
    
    # ==================== 风险优化 ====================
    
    async def optimize_risk(self, portfolio: Dict[str, Any]) -> Dict[str, Any]:
        """
        优化风险
        
        Args:
            portfolio: 投资组合
        
        Returns:
            Dict: 优化结果
        """
        try:
            if not self.optimizer:
                return {"error": "optimizer_not_available"}
            
            # 使用优化器
            try:
                result = await self.optimizer.risk_parity_optimization(portfolio)
                logger.info("风险优化完成")
                return result
            except Exception as e:
                logger.debug(f"风险优化器执行失败: {e}")
                return {"error": "optimization_failed"}
            
        except Exception as e:
            logger.error(f"优化风险失败: {e}")
            return {"error": str(e)}
    
    # ==================== 风险报告 ====================
    
    async def generate_risk_report(self) -> Dict[str, Any]:
        """
        生成风险报告
        
        Returns:
            Dict: 风险报告
        """
        try:
            return {
                "timestamp": datetime.now().isoformat(),
                "risk_metrics": self.risk_metrics,
                "risk_thresholds": self.risk_thresholds,
                "statistics": self.stats,
                "recent_history": self.risk_history[-10:]  # 最近10次评估
            }
            
        except Exception as e:
            logger.error(f"生成风险报告失败: {e}")
            return {"error": str(e)}
    
    # ==================== 统计和监控 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict: 统计信息
        """
        return {
            **self.stats,
            "assessor_available": self.assessor is not None,
            "monitor_available": self.monitor is not None,
            "optimizer_available": self.optimizer is not None
        }
    
    # ==================== 清理 ====================
    
    async def cleanup(self):
        """清理资源"""
        try:
            logger.info("清理统一风险系统...")
            
            # 清理历史
            self.risk_history.clear()
            
            logger.info("✅ 统一风险系统清理完成")
        except Exception as e:
            logger.error(f"清理失败: {e}")
