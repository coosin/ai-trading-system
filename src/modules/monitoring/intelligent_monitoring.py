"""
智能监控和告警系统

为无人化AI交易系统提供全面的监控和告警功能
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertType(str, Enum):
    """告警类型"""
    SYSTEM_HEALTH = "system_health"
    API_PERFORMANCE = "api_performance"
    DATA_QUALITY = "data_quality"
    AI_MODEL = "ai_model"
    FUND_SAFETY = "fund_safety"
    TRADING_ANOMALY = "trading_anomaly"
    RISK_BREACH = "risk_breach"
    NETWORK_ISSUE = "network_issue"


@dataclass
class Alert:
    """告警信息"""
    id: str
    level: AlertLevel
    type: AlertType
    title: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    resolved: bool = False
    escalation_count: int = 0


@dataclass
class SystemHealthMetrics:
    """系统健康指标"""
    
    # API性能
    api_latency: float = 0.0
    api_success_rate: float = 100.0
    api_timeout_count: int = 0
    
    # 数据质量
    data_freshness: float = 0.0  # 秒
    data_completeness: float = 100.0
    data_accuracy: float = 100.0
    
    # AI模型状态
    ai_model_status: str = "healthy"
    ai_response_time: float = 0.0
    ai_confidence_avg: float = 0.0
    
    # 资金安全
    account_balance: float = 0.0
    available_margin: float = 0.0
    position_risk: float = 0.0
    daily_pnl: float = 0.0
    
    # 系统资源
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    
    # 交易状态
    active_positions: int = 0
    pending_orders: int = 0
    trade_count_today: int = 0
    
    # 健康评分
    overall_health_score: float = 100.0
    timestamp: datetime = field(default_factory=datetime.now)


class IntelligentMonitoringSystem:
    """智能监控系统"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # 告警配置
        self.alert_thresholds = {
            "api_latency_warning": 5.0,      # 秒
            "api_latency_critical": 10.0,
            "api_success_rate_warning": 95.0,  # 百分比
            "api_success_rate_critical": 90.0,
            "data_freshness_warning": 60.0,    # 秒
            "data_freshness_critical": 120.0,
            "ai_response_time_warning": 30.0,  # 秒
            "ai_response_time_critical": 60.0,
            "ai_confidence_warning": 0.6,      # 百分比
            "ai_confidence_critical": 0.5,
            "position_risk_warning": 0.7,      # 百分比
            "position_risk_critical": 0.85,
            "daily_loss_warning": 0.03,        # 百分比
            "daily_loss_critical": 0.05,
            "cpu_usage_warning": 70.0,         # 百分比
            "cpu_usage_critical": 90.0,
            "memory_usage_warning": 80.0,      # 百分比
            "memory_usage_critical": 95.0,
        }
        
        # 告警历史
        self.alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        
        # 健康指标历史
        self.health_history: List[SystemHealthMetrics] = []
        
        # 监控状态
        self._running = False
        self._monitoring_task: Optional[asyncio.Task] = None
        
        # 告警处理器
        self.alert_handlers: List[callable] = []
        
        # 升级配置
        self.escalation_config = {
            "info_escalation_minutes": 60,
            "warning_escalation_minutes": 30,
            "error_escalation_minutes": 15,
            "critical_escalation_minutes": 5,
            "emergency_escalation_minutes": 1,
        }
    
    async def start_monitoring(self):
        """启动监控"""
        if self._running:
            return
        
        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("✅ 智能监控系统已启动")
    
    async def stop_monitoring(self):
        """停止监控"""
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("🛑 智能监控系统已停止")
    
    async def _monitoring_loop(self):
        """监控循环"""
        while self._running:
            try:
                # 1. 收集健康指标
                metrics = await self._collect_health_metrics()
                
                # 2. 保存历史
                self.health_history.append(metrics)
                
                # 保持最近100条记录
                if len(self.health_history) > 100:
                    self.health_history.pop(0)
                
                # 3. 检查告警条件
                await self._check_alert_conditions(metrics)
                
                # 4. 处理告警升级
                await self._process_alert_escalation()
                
                # 5. 计算健康评分
                health_score = self._calculate_health_score(metrics)
                
                # 6. 记录状态
                logger.debug(
                    f"系统健康度: {health_score:.1f}% | "
                    f"API延迟: {metrics.api_latency:.2f}s | "
                    f"AI响应: {metrics.ai_response_time:.2f}s"
                )
                
                # 每10秒监控一次
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(5)
    
    async def _collect_health_metrics(self) -> SystemHealthMetrics:
        """收集健康指标"""
        metrics = SystemHealthMetrics()
        
        try:
            # 这里应该从实际系统收集数据
            # 暂时返回模拟数据
            metrics.api_latency = 0.5
            metrics.api_success_rate = 99.5
            metrics.data_freshness = 10.0
            metrics.ai_response_time = 2.0
            metrics.ai_confidence_avg = 0.75
            metrics.cpu_usage = 45.0
            metrics.memory_usage = 60.0
            metrics.overall_health_score = 95.0
            
        except Exception as e:
            logger.error(f"收集健康指标失败: {e}")
        
        return metrics
    
    async def _check_alert_conditions(self, metrics: SystemHealthMetrics):
        """检查告警条件"""
        
        # API延迟检查
        if metrics.api_latency > self.alert_thresholds["api_latency_critical"]:
            await self._create_alert(
                level=AlertLevel.CRITICAL,
                type=AlertType.API_PERFORMANCE,
                title="API延迟严重",
                message=f"API延迟{metrics.api_latency:.2f}秒，超过临界值{self.alert_thresholds['api_latency_critical']}秒",
                data={"latency": metrics.api_latency}
            )
        elif metrics.api_latency > self.alert_thresholds["api_latency_warning"]:
            await self._create_alert(
                level=AlertLevel.WARNING,
                type=AlertType.API_PERFORMANCE,
                title="API延迟警告",
                message=f"API延迟{metrics.api_latency:.2f}秒，超过警告值{self.alert_thresholds['api_latency_warning']}秒",
                data={"latency": metrics.api_latency}
            )
        
        # AI响应时间检查
        if metrics.ai_response_time > self.alert_thresholds["ai_response_time_critical"]:
            await self._create_alert(
                level=AlertLevel.CRITICAL,
                type=AlertType.AI_MODEL,
                title="AI响应超时",
                message=f"AI响应时间{metrics.ai_response_time:.2f}秒，可能影响交易决策",
                data={"response_time": metrics.ai_response_time}
            )
        
        # 系统资源检查
        if metrics.cpu_usage > self.alert_thresholds["cpu_usage_critical"]:
            await self._create_alert(
                level=AlertLevel.CRITICAL,
                type=AlertType.SYSTEM_HEALTH,
                title="CPU使用率过高",
                message=f"CPU使用率{metrics.cpu_usage:.1f}%，可能影响系统性能",
                data={"cpu_usage": metrics.cpu_usage}
            )
        
        if metrics.memory_usage > self.alert_thresholds["memory_usage_critical"]:
            await self._create_alert(
                level=AlertLevel.CRITICAL,
                type=AlertType.SYSTEM_HEALTH,
                title="内存使用率过高",
                message=f"内存使用率{metrics.memory_usage:.1f}%，可能导致系统崩溃",
                data={"memory_usage": metrics.memory_usage}
            )
    
    async def _create_alert(
        self,
        level: AlertLevel,
        type: AlertType,
        title: str,
        message: str,
        data: Dict[str, Any]
    ):
        """创建告警"""
        import uuid
        
        alert_id = str(uuid.uuid4())
        
        alert = Alert(
            id=alert_id,
            level=level,
            type=type,
            title=title,
            message=message,
            data=data
        )
        
        # 检查是否已存在相同告警
        existing_alert = self._find_similar_alert(alert)
        if existing_alert:
            # 更新现有告警
            existing_alert.escalation_count += 1
            existing_alert.timestamp = datetime.now()
            logger.debug(f"更新告警: {title} (升级次数: {existing_alert.escalation_count})")
        else:
            # 创建新告警
            self.alerts[alert_id] = alert
            self.alert_history.append(alert)
            
            logger.warning(f"🚨 新告警 [{level.value.upper()}]: {title} - {message}")
            
            # 触发告警处理器
            for handler in self.alert_handlers:
                try:
                    await handler(alert)
                except Exception as e:
                    logger.error(f"告警处理器执行失败: {e}")
    
    def _find_similar_alert(self, new_alert: Alert) -> Optional[Alert]:
        """查找相似告警"""
        for alert in self.alerts.values():
            if (alert.type == new_alert.type and 
                alert.title == new_alert.title and
                not alert.resolved):
                return alert
        return None
    
    async def _process_alert_escalation(self):
        """处理告警升级"""
        now = datetime.now()
        
        for alert in list(self.alerts.values()):
            if alert.resolved:
                continue
            
            # 计算告警持续时间
            duration_minutes = (now - alert.timestamp).total_seconds() / 60
            
            # 根据告警级别获取升级时间
            escalation_key = f"{alert.level.value}_escalation_minutes"
            escalation_minutes = self.escalation_config.get(escalation_key, 30)
            
            # 检查是否需要升级
            if duration_minutes >= escalation_minutes * (alert.escalation_count + 1):
                alert.escalation_count += 1
                logger.warning(
                    f"⚠️ 告警升级: {alert.title} "
                    f"(持续{duration_minutes:.1f}分钟, 升级{alert.escalation_count}次)"
                )
                
                # 发送升级通知
                await self._send_escalation_notification(alert)
    
    async def _send_escalation_notification(self, alert: Alert):
        """发送升级通知"""
        # 这里应该集成通知系统
        logger.critical(
            f"🔔 告警升级通知: [{alert.level.value.upper()}] {alert.title}\n"
            f"消息: {alert.message}\n"
            f"持续时间: {(datetime.now() - alert.timestamp).total_seconds() / 60:.1f}分钟\n"
            f"升级次数: {alert.escalation_count}"
        )
    
    def _calculate_health_score(self, metrics: SystemHealthMetrics) -> float:
        """计算健康评分"""
        score = 100.0
        
        # API性能 (权重25%)
        if metrics.api_latency > self.alert_thresholds["api_latency_critical"]:
            score -= 25
        elif metrics.api_latency > self.alert_thresholds["api_latency_warning"]:
            score -= 10
        
        # AI模型状态 (权重25%)
        if metrics.ai_response_time > self.alert_thresholds["ai_response_time_critical"]:
            score -= 25
        elif metrics.ai_response_time > self.alert_thresholds["ai_response_time_warning"]:
            score -= 10
        
        # 系统资源 (权重25%)
        if metrics.cpu_usage > self.alert_thresholds["cpu_usage_critical"]:
            score -= 15
        elif metrics.cpu_usage > self.alert_thresholds["cpu_usage_warning"]:
            score -= 5
        
        if metrics.memory_usage > self.alert_thresholds["memory_usage_critical"]:
            score -= 10
        elif metrics.memory_usage > self.alert_thresholds["memory_usage_warning"]:
            score -= 5
        
        # 数据质量 (权重25%)
        if metrics.data_freshness > self.alert_thresholds["data_freshness_critical"]:
            score -= 25
        elif metrics.data_freshness > self.alert_thresholds["data_freshness_warning"]:
            score -= 10
        
        return max(0, score)
    
    def add_alert_handler(self, handler: callable):
        """添加告警处理器"""
        self.alert_handlers.append(handler)
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """确认告警"""
        if alert_id in self.alerts:
            self.alerts[alert_id].acknowledged = True
            logger.info(f"告警已确认: {alert_id}")
            return True
        return False
    
    async def resolve_alert(self, alert_id: str) -> bool:
        """解决告警"""
        if alert_id in self.alerts:
            self.alerts[alert_id].resolved = True
            logger.info(f"告警已解决: {alert_id}")
            return True
        return False
    
    def get_active_alerts(self) -> List[Alert]:
        """获取活动告警"""
        return [alert for alert in self.alerts.values() if not alert.resolved]
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        if not self.health_history:
            return {"status": "unknown", "score": 0}
        
        latest_metrics = self.health_history[-1]
        
        return {
            "status": "healthy" if latest_metrics.overall_health_score >= 80 else "degraded",
            "score": latest_metrics.overall_health_score,
            "metrics": {
                "api_latency": latest_metrics.api_latency,
                "ai_response_time": latest_metrics.ai_response_time,
                "cpu_usage": latest_metrics.cpu_usage,
                "memory_usage": latest_metrics.memory_usage,
            },
            "active_alerts": len(self.get_active_alerts()),
            "timestamp": latest_metrics.timestamp.isoformat()
        }
