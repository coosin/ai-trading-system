"""
智能监控系统

提供系统健康监控、性能分析和异常检测功能
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from src.modules.core.module_config_utils import resolve_module_config

logger = logging.getLogger(__name__)


@dataclass
class MonitoringMetric:
    """监控指标"""
    name: str
    value: float
    unit: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class AlertRule:
    """告警规则"""
    name: str
    metric_name: str
    condition: str  # "gt", "lt", "eq", "ne"
    threshold: float
    severity: str = "warning"  # info, warning, critical
    enabled: bool = True
    cooldown: int = 300  # 冷却时间（秒）
    last_triggered: Optional[datetime] = None


@dataclass
class Alert:
    """告警"""
    rule_name: str
    metric_name: str
    metric_value: float
    threshold: float
    severity: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False


class IntelligentMonitoringSystem:
    """智能监控系统"""
    
    def __init__(self, config: Optional[Dict] = None, config_manager=None):
        self.config = resolve_module_config(
            config=config,
            config_manager=config_manager,
            section="intelligent_monitoring",
            defaults={},
        )
        
        self._metrics: Dict[str, List[MonitoringMetric]] = {}
        self._max_metrics = self.config.get("max_metrics", 1000)
        
        self._alert_rules: Dict[str, AlertRule] = {}
        self._alerts: List[Alert] = []
        self._alert_callbacks: List[Callable] = []
        
        self._health_status: Dict[str, Dict[str, Any]] = {}
        self._component_checks: Dict[str, Callable] = {}
        
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
    
    async def initialize(self) -> bool:
        """初始化监控系统"""
        self._setup_default_alert_rules()
        logger.info("✅ 智能监控系统初始化完成")
        return True
    
    def _setup_default_alert_rules(self) -> None:
        """设置默认告警规则"""
        default_rules = [
            AlertRule("cpu_high", "cpu_percent", "gt", 80, "warning"),
            AlertRule("cpu_critical", "cpu_percent", "gt", 95, "critical"),
            AlertRule("memory_high", "memory_percent", "gt", 80, "warning"),
            AlertRule("memory_critical", "memory_percent", "gt", 95, "critical"),
            AlertRule("disk_high", "disk_percent", "gt", 80, "warning"),
            AlertRule("disk_critical", "disk_percent", "gt", 95, "critical"),
            AlertRule("error_rate_high", "error_rate", "gt", 0.1, "warning"),
            AlertRule("latency_high", "latency_ms", "gt", 1000, "warning"),
        ]
        
        for rule in default_rules:
            self._alert_rules[rule.name] = rule
    
    async def start(self) -> None:
        """启动监控"""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("智能监控系统已启动")
    
    async def stop(self) -> None:
        """停止监控"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("智能监控系统已停止")
    
    async def _monitor_loop(self) -> None:
        """监控循环"""
        interval = self.config.get("monitor_interval", 30)
        
        while self._running:
            try:
                await self._collect_metrics()
                await self._check_alerts()
                await self._check_components()
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
            
            await asyncio.sleep(interval)
    
    async def _collect_metrics(self) -> None:
        """收集指标"""
        try:
            import psutil
            
            self.record_metric("cpu_percent", psutil.cpu_percent(interval=1))
            
            memory = psutil.virtual_memory()
            self.record_metric("memory_percent", memory.percent)
            self.record_metric("memory_used_gb", memory.used / (1024**3))
            
            disk = psutil.disk_usage('/')
            self.record_metric("disk_percent", disk.percent)
            self.record_metric("disk_used_gb", disk.used / (1024**3))
            
        except Exception as e:
            logger.warning(f"收集指标失败: {e}")
    
    async def _check_alerts(self) -> None:
        """检查告警"""
        for rule in self._alert_rules.values():
            if not rule.enabled:
                continue
            
            if rule.metric_name not in self._metrics:
                continue
            
            latest_metric = self._metrics[rule.metric_name][-1]
            
            triggered = False
            if rule.condition == "gt" and latest_metric.value > rule.threshold:
                triggered = True
            elif rule.condition == "lt" and latest_metric.value < rule.threshold:
                triggered = True
            elif rule.condition == "eq" and latest_metric.value == rule.threshold:
                triggered = True
            elif rule.condition == "ne" and latest_metric.value != rule.threshold:
                triggered = True
            
            if triggered:
                if rule.last_triggered:
                    elapsed = (datetime.now() - rule.last_triggered).total_seconds()
                    if elapsed < rule.cooldown:
                        continue
                
                alert = Alert(
                    rule_name=rule.name,
                    metric_name=rule.metric_name,
                    metric_value=latest_metric.value,
                    threshold=rule.threshold,
                    severity=rule.severity,
                    message=f"{rule.metric_name} {rule.condition} {rule.threshold}: current={latest_metric.value}"
                )
                
                self._alerts.append(alert)
                rule.last_triggered = datetime.now()
                
                await self._trigger_alert_callback(alert)
    
    async def _trigger_alert_callback(self, alert: Alert) -> None:
        """触发告警回调"""
        logger.warning(f"告警: {alert.message}")
        
        for callback in self._alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                logger.error(f"告警回调执行失败: {e}")
    
    async def _check_components(self) -> None:
        """检查组件健康状态"""
        for name, check_func in self._component_checks.items():
            try:
                if asyncio.iscoroutinefunction(check_func):
                    result = await check_func()
                else:
                    result = check_func()
                
                self._health_status[name] = {
                    "status": "healthy" if result else "unhealthy",
                    "last_check": datetime.now().isoformat()
                }
            except Exception as e:
                self._health_status[name] = {
                    "status": "error",
                    "error": str(e),
                    "last_check": datetime.now().isoformat()
                }
    
    def record_metric(self, name: str, value: float, unit: str = "", 
                      tags: Optional[Dict[str, str]] = None) -> None:
        """记录指标"""
        metric = MonitoringMetric(
            name=name,
            value=value,
            unit=unit,
            tags=tags or {}
        )
        
        if name not in self._metrics:
            self._metrics[name] = []
        
        self._metrics[name].append(metric)
        
        if len(self._metrics[name]) > self._max_metrics:
            self._metrics[name] = self._metrics[name][-self._max_metrics:]
    
    def add_alert_rule(self, rule: AlertRule) -> None:
        """添加告警规则"""
        self._alert_rules[rule.name] = rule
    
    def add_alert_callback(self, callback: Callable) -> None:
        """添加告警回调"""
        self._alert_callbacks.append(callback)
    
    def register_component_check(self, name: str, check_func: Callable) -> None:
        """注册组件检查"""
        self._component_checks[name] = check_func
    
    def get_metrics(self, name: str, limit: int = 100) -> List[MonitoringMetric]:
        """获取指标历史"""
        if name not in self._metrics:
            return []
        return self._metrics[name][-limit:]
    
    def get_latest_metric(self, name: str) -> Optional[MonitoringMetric]:
        """获取最新指标"""
        if name not in self._metrics or not self._metrics[name]:
            return None
        return self._metrics[name][-1]
    
    def get_alerts(self, limit: int = 100, severity: Optional[str] = None) -> List[Alert]:
        """获取告警列表"""
        alerts = self._alerts
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return alerts[-limit:]
    
    def get_health_status(self) -> Dict[str, Dict[str, Any]]:
        """获取健康状态"""
        return self._health_status
    
    def get_summary(self) -> Dict[str, Any]:
        """获取监控摘要"""
        return {
            "metrics_count": sum(len(m) for m in self._metrics.values()),
            "alerts_count": len(self._alerts),
            "components": len(self._health_status),
            "alert_rules": len(self._alert_rules),
            "running": self._running
        }
