"""
系统稳定性判断器 - AI判断系统稳定性的核心能力

赋予AI对系统稳定性的判断能力，包括：
1. 实时稳定性评估
2. 趋势预测
3. 风险预警
4. 决策建议
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import statistics

logger = logging.getLogger(__name__)


class StabilityLevel(Enum):
    """稳定性等级"""
    HIGHLY_STABLE = "highly_stable"      # 高度稳定
    STABLE = "stable"                    # 稳定
    MODERATE = "moderate"                # 中等稳定
    UNSTABLE = "unstable"                # 不稳定
    CRITICAL = "critical"                # 危险


class DecisionType(Enum):
    """决策类型"""
    CONTINUE_TRADING = "continue_trading"        # 继续交易
    REDUCE_POSITION = "reduce_position"          # 减少仓位
    PAUSE_TRADING = "pause_trading"              # 暂停交易
    EMERGENCY_EXIT = "emergency_exit"            # 紧急退出
    SYSTEM_RESTART = "system_restart"            # 系统重启


@dataclass
class StabilityMetrics:
    """稳定性指标"""
    timestamp: datetime
    
    system_score: float = 0.0
    trading_score: float = 0.0
    risk_score: float = 0.0
    network_score: float = 0.0
    
    overall_score: float = 0.0
    stability_level: StabilityLevel = StabilityLevel.STABLE
    
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "system_score": self.system_score,
            "trading_score": self.trading_score,
            "risk_score": self.risk_score,
            "network_score": self.network_score,
            "overall_score": self.overall_score,
            "stability_level": self.stability_level.value,
            "issues": self.issues,
            "warnings": self.warnings
        }


@dataclass
class StabilityDecision:
    """稳定性决策"""
    decision_type: DecisionType
    confidence: float
    reason: str
    actions: List[str]
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_type": self.decision_type.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "actions": self.actions,
            "timestamp": self.timestamp.isoformat()
        }


class SystemStabilityAnalyzer:
    """
    系统稳定性分析器
    
    AI使用此模块判断系统稳定性并做出决策
    """
    
    def __init__(self, history_size: int = 100):
        """
        初始化稳定性分析器
        
        Args:
            history_size: 历史记录大小
        """
        self.history_size = history_size
        
        self._metrics_history: deque = deque(maxlen=history_size)
        self._error_history: deque = deque(maxlen=history_size)
        self._performance_history: deque = deque(maxlen=history_size)
        
        self._stability_thresholds = {
            "highly_stable": 90,
            "stable": 75,
            "moderate": 50,
            "unstable": 25,
            "critical": 0
        }
        
        self._weights = {
            "system": 0.3,
            "trading": 0.3,
            "risk": 0.25,
            "network": 0.15
        }
        
        self._last_analysis: Optional[StabilityMetrics] = None
        self._last_decision: Optional[StabilityDecision] = None
        
        logger.info("系统稳定性分析器初始化完成")
    
    async def analyze(self, context: Dict[str, Any]) -> StabilityMetrics:
        """
        分析系统稳定性
        
        Args:
            context: 包含main_controller、trading_engine等
            
        Returns:
            StabilityMetrics: 稳定性指标
        """
        system_score = await self._analyze_system_stability(context)
        trading_score = await self._analyze_trading_stability(context)
        risk_score = await self._analyze_risk_stability(context)
        network_score = await self._analyze_network_stability(context)
        
        overall_score = (
            system_score * self._weights["system"] +
            trading_score * self._weights["trading"] +
            risk_score * self._weights["risk"] +
            network_score * self._weights["network"]
        )
        
        stability_level = self._determine_stability_level(overall_score)
        
        issues = []
        warnings = []
        
        if system_score < 50:
            issues.append(f"系统稳定性低: {system_score:.1f}")
        elif system_score < 70:
            warnings.append(f"系统稳定性偏低: {system_score:.1f}")
        
        if trading_score < 50:
            issues.append(f"交易稳定性低: {trading_score:.1f}")
        elif trading_score < 70:
            warnings.append(f"交易稳定性偏低: {trading_score:.1f}")
        
        if risk_score < 50:
            issues.append(f"风险控制稳定性低: {risk_score:.1f}")
        elif risk_score < 70:
            warnings.append(f"风险控制稳定性偏低: {risk_score:.1f}")
        
        if network_score < 50:
            issues.append(f"网络稳定性低: {network_score:.1f}")
        elif network_score < 70:
            warnings.append(f"网络稳定性偏低: {network_score:.1f}")
        
        metrics = StabilityMetrics(
            timestamp=datetime.now(),
            system_score=system_score,
            trading_score=trading_score,
            risk_score=risk_score,
            network_score=network_score,
            overall_score=overall_score,
            stability_level=stability_level,
            issues=issues,
            warnings=warnings
        )
        
        self._metrics_history.append(metrics)
        self._last_analysis = metrics
        
        return metrics
    
    async def _analyze_system_stability(self, context: Dict[str, Any]) -> float:
        """分析系统稳定性"""
        score = 100.0
        
        try:
            import psutil
            
            cpu_percent = psutil.cpu_percent(interval=0.1)
            if cpu_percent > 90:
                score -= 30
            elif cpu_percent > 70:
                score -= 15
            elif cpu_percent > 50:
                score -= 5
            
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                score -= 25
            elif memory.percent > 75:
                score -= 12
            elif memory.percent > 60:
                score -= 5
            
            disk = psutil.disk_usage('/')
            if disk.percent > 95:
                score -= 20
            elif disk.percent > 85:
                score -= 10
            
        except Exception as e:
            logger.debug(f"系统指标获取失败: {e}")
            score -= 10
        
        main_controller = context.get("main_controller")
        if main_controller:
            modules = getattr(main_controller, 'modules', {})
            error_count = 0
            for name, info in modules.items():
                if hasattr(info, 'status'):
                    status_value = info.status.value if hasattr(info.status, 'value') else str(info.status)
                    if 'error' in status_value.lower():
                        error_count += 1
            
            score -= error_count * 10
        
        return max(0, min(100, score))
    
    async def _analyze_trading_stability(self, context: Dict[str, Any]) -> float:
        """分析交易稳定性"""
        score = 100.0
        
        main_controller = context.get("main_controller")
        if not main_controller:
            return 50.0
        
        trading_engine = getattr(main_controller, 'ai_trading_engine', None)
        if not trading_engine:
            return 50.0
        
        positions = getattr(trading_engine, 'positions', {})
        
        high_risk_positions = 0
        for symbol, position in positions.items():
            if isinstance(position, dict):
                pnl_percent = position.get('unrealized_pnl_percent', 0)
                if pnl_percent < -10:
                    high_risk_positions += 1
        
        score -= high_risk_positions * 15
        
        trade_history = getattr(trading_engine, 'trade_history', [])
        if len(trade_history) >= 10:
            recent_trades = trade_history[-20:]
            errors = sum(1 for t in recent_trades if t.get('status') == 'failed')
            error_rate = errors / len(recent_trades)
            
            if error_rate > 0.2:
                score -= 25
            elif error_rate > 0.1:
                score -= 15
            elif error_rate > 0.05:
                score -= 5
        
        return max(0, min(100, score))
    
    async def _analyze_risk_stability(self, context: Dict[str, Any]) -> float:
        """分析风险稳定性"""
        score = 100.0
        
        main_controller = context.get("main_controller")
        if not main_controller:
            return 70.0
        
        risk_monitor = getattr(main_controller, 'risk_monitor', None)
        if risk_monitor:
            try:
                if hasattr(risk_monitor, 'get_current_risk'):
                    risk_data = risk_monitor.get_current_risk()
                    risk_level = risk_data.get('risk_level', 'unknown')
                    
                    if risk_level == 'critical':
                        score -= 40
                    elif risk_level == 'high':
                        score -= 25
                    elif risk_level == 'medium':
                        score -= 10
            except:
                pass
        
        anomaly_detector = getattr(main_controller, 'anomaly_detector', None)
        if anomaly_detector:
            try:
                if hasattr(anomaly_detector, 'get_anomaly_count'):
                    anomaly_count = anomaly_detector.get_anomaly_count()
                    score -= min(anomaly_count * 5, 30)
            except:
                pass
        
        return max(0, min(100, score))
    
    async def _analyze_network_stability(self, context: Dict[str, Any]) -> float:
        """分析网络稳定性"""
        score = 100.0
        
        main_controller = context.get("main_controller")
        if not main_controller:
            return 70.0
        
        trading_engine = getattr(main_controller, 'ai_trading_engine', None)
        if trading_engine:
            exchange = getattr(trading_engine, 'exchange', None)
            if exchange:
                try:
                    if hasattr(exchange, 'is_connected') and callable(exchange.is_connected):
                        connected = await exchange.is_connected()
                        if not connected:
                            score -= 50
                except:
                    score -= 30
        
        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=2)
        except:
            score -= 40
        
        return max(0, min(100, score))
    
    def _determine_stability_level(self, score: float) -> StabilityLevel:
        """确定稳定性等级"""
        if score >= self._stability_thresholds["highly_stable"]:
            return StabilityLevel.HIGHLY_STABLE
        elif score >= self._stability_thresholds["stable"]:
            return StabilityLevel.STABLE
        elif score >= self._stability_thresholds["moderate"]:
            return StabilityLevel.MODERATE
        elif score >= self._stability_thresholds["unstable"]:
            return StabilityLevel.UNSTABLE
        else:
            return StabilityLevel.CRITICAL
    
    async def make_decision(
        self, 
        metrics: StabilityMetrics,
        context: Dict[str, Any]
    ) -> StabilityDecision:
        """
        基于稳定性指标做出决策
        
        Args:
            metrics: 稳定性指标
            context: 执行上下文
            
        Returns:
            StabilityDecision: 稳定性决策
        """
        decision_type = DecisionType.CONTINUE_TRADING
        confidence = 0.8
        reason = "系统运行正常"
        actions = []
        
        if metrics.stability_level == StabilityLevel.HIGHLY_STABLE:
            decision_type = DecisionType.CONTINUE_TRADING
            confidence = 0.95
            reason = "系统高度稳定，可以正常交易"
            actions = ["继续执行交易策略"]
        
        elif metrics.stability_level == StabilityLevel.STABLE:
            decision_type = DecisionType.CONTINUE_TRADING
            confidence = 0.85
            reason = "系统稳定，可以继续交易"
            actions = ["继续执行交易策略", "保持监控"]
        
        elif metrics.stability_level == StabilityLevel.MODERATE:
            decision_type = DecisionType.REDUCE_POSITION
            confidence = 0.75
            reason = "系统稳定性中等，建议降低风险"
            actions = [
                "减少新开仓位",
                "检查系统资源",
                "加强监控频率"
            ]
        
        elif metrics.stability_level == StabilityLevel.UNSTABLE:
            decision_type = DecisionType.PAUSE_TRADING
            confidence = 0.85
            reason = "系统不稳定，建议暂停交易"
            actions = [
                "暂停新开仓",
                "检查并修复问题",
                "评估现有持仓风险",
                "通知管理员"
            ]
        
        elif metrics.stability_level == StabilityLevel.CRITICAL:
            decision_type = DecisionType.EMERGENCY_EXIT
            confidence = 0.95
            reason = "系统状态危险，建议紧急处理"
            actions = [
                "紧急平仓或减仓",
                "停止所有交易活动",
                "执行系统诊断",
                "立即通知管理员"
            ]
        
        if metrics.issues:
            for issue in metrics.issues:
                if "系统" in issue and metrics.system_score < 30:
                    actions.append("执行系统维护")
                if "网络" in issue and metrics.network_score < 30:
                    actions.append("检查网络连接")
        
        decision = StabilityDecision(
            decision_type=decision_type,
            confidence=confidence,
            reason=reason,
            actions=actions
        )
        
        self._last_decision = decision
        
        return decision
    
    async def execute_decision(
        self, 
        decision: StabilityDecision,
        context: Dict[str, Any]
    ) -> bool:
        """
        执行决策
        
        Args:
            decision: 稳定性决策
            context: 执行上下文
            
        Returns:
            bool: 是否执行成功
        """
        main_controller = context.get("main_controller")
        if not main_controller:
            logger.warning("无法执行决策: 主控制器不可用")
            return False
        
        try:
            if decision.decision_type == DecisionType.CONTINUE_TRADING:
                logger.info(f"✅ 决策执行: 继续交易 - {decision.reason}")
                return True
            
            elif decision.decision_type == DecisionType.REDUCE_POSITION:
                logger.info(f"⚠️ 决策执行: 减少仓位 - {decision.reason}")
                if hasattr(main_controller, 'ai_trading_engine') and main_controller.ai_trading_engine:
                    trading_engine = main_controller.ai_trading_engine
                    if hasattr(trading_engine, 'reduce_all_positions'):
                        await trading_engine.reduce_all_positions(ratio=0.5)
                return True
            
            elif decision.decision_type == DecisionType.PAUSE_TRADING:
                logger.warning(f"⏸️ 决策执行: 暂停交易 - {decision.reason}")
                if hasattr(main_controller, 'ai_trading_engine') and main_controller.ai_trading_engine:
                    await main_controller.ai_trading_engine.stop()
                return True
            
            elif decision.decision_type == DecisionType.EMERGENCY_EXIT:
                logger.critical(f"🚨 决策执行: 紧急退出 - {decision.reason}")
                if hasattr(main_controller, 'emergency_stop') and main_controller.emergency_stop:
                    await main_controller.emergency_stop.trigger_stop(decision.reason)
                elif hasattr(main_controller, 'ai_trading_engine') and main_controller.ai_trading_engine:
                    if hasattr(main_controller.ai_trading_engine, 'emergency_close_all'):
                        await main_controller.ai_trading_engine.emergency_close_all()
                return True
            
            elif decision.decision_type == DecisionType.SYSTEM_RESTART:
                logger.warning(f"🔄 决策执行: 系统重启 - {decision.reason}")
                return True
            
            return True
            
        except Exception as e:
            logger.error(f"决策执行失败: {e}")
            return False
    
    def get_stability_trend(self, periods: int = 10) -> Dict[str, Any]:
        """
        获取稳定性趋势
        
        Args:
            periods: 分析周期数
            
        Returns:
            Dict: 趋势分析结果
        """
        if len(self._metrics_history) < 2:
            return {"trend": "unknown", "data_points": 0}
        
        recent_metrics = list(self._metrics_history)[-periods:]
        
        scores = [m.overall_score for m in recent_metrics]
        
        if len(scores) >= 3:
            trend = "stable"
            if scores[-1] > scores[0] + 5:
                trend = "improving"
            elif scores[-1] < scores[0] - 5:
                trend = "declining"
        else:
            trend = "insufficient_data"
        
        return {
            "trend": trend,
            "current_score": scores[-1] if scores else 0,
            "average_score": statistics.mean(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "data_points": len(scores)
        }
    
    def get_last_analysis(self) -> Optional[StabilityMetrics]:
        """获取最后一次分析结果"""
        return self._last_analysis
    
    def get_last_decision(self) -> Optional[StabilityDecision]:
        """获取最后一次决策"""
        return self._last_decision
