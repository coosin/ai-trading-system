"""
增强监控报警系统

功能：
1. 实时监控关键指标
2. 多渠道报警（Telegram、邮件、Webhook）
3. 报警分级和聚合
4. 报警历史记录和分析
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import json

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """报警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertChannel(Enum):
    """报警渠道"""
    TELEGRAM = "telegram"
    EMAIL = "email"
    WEBHOOK = "webhook"
    LOG = "log"


@dataclass
class AlertRule:
    """报警规则"""
    rule_id: str
    name: str
    metric: str
    condition: str
    threshold: float
    level: AlertLevel
    channels: List[AlertChannel]
    cooldown: int = 300
    enabled: bool = True
    description: str = ""


@dataclass
class Alert:
    """报警"""
    alert_id: str
    rule: AlertRule
    metric_value: float
    message: str
    level: AlertLevel
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    resolved: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class MonitoringMetric:
    """监控指标"""
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)


class EnhancedMonitoringSystem:
    """增强监控系统"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        self.rules: Dict[str, AlertRule] = {}
        self.alerts: List[Alert] = []
        self.alert_history: Dict[str, datetime] = {}
        
        self.metrics: Dict[str, List[MonitoringMetric]] = {}
        self.max_metrics_history = 1000
        
        self.telegram_bot = None
        self.webhook_urls: List[str] = []
        
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._callbacks: Dict[str, List[Callable]] = {
            "on_alert": [],
            "on_resolve": [],
            "on_metric_update": []
        }
        
        self._init_default_rules()
    
    def _init_default_rules(self):
        """初始化默认报警规则"""
        default_rules = [
            AlertRule(
                rule_id="high_drawdown",
                name="高回撤预警",
                metric="drawdown_percent",
                condition=">",
                threshold=5.0,
                level=AlertLevel.WARNING,
                channels=[AlertChannel.TELEGRAM, AlertChannel.LOG],
                cooldown=1800,
                description="账户回撤超过5%"
            ),
            AlertRule(
                rule_id="critical_drawdown",
                name="严重回撤预警",
                metric="drawdown_percent",
                condition=">",
                threshold=10.0,
                level=AlertLevel.CRITICAL,
                channels=[AlertChannel.TELEGRAM, AlertChannel.LOG],
                cooldown=600,
                description="账户回撤超过10%"
            ),
            AlertRule(
                rule_id="high_position_ratio",
                name="高仓位预警",
                metric="position_ratio",
                condition=">",
                threshold=0.7,
                level=AlertLevel.WARNING,
                channels=[AlertChannel.TELEGRAM, AlertChannel.LOG],
                cooldown=1800,
                description="总仓位比例超过70%"
            ),
            AlertRule(
                rule_id="consecutive_losses",
                name="连续亏损预警",
                metric="consecutive_losses",
                condition=">=",
                threshold=3,
                level=AlertLevel.WARNING,
                channels=[AlertChannel.TELEGRAM, AlertChannel.LOG],
                cooldown=3600,
                description="连续亏损达到3次"
            ),
            AlertRule(
                rule_id="api_error_rate",
                name="API错误率预警",
                metric="api_error_rate",
                condition=">",
                threshold=0.1,
                level=AlertLevel.ERROR,
                channels=[AlertChannel.TELEGRAM, AlertChannel.LOG],
                cooldown=600,
                description="API错误率超过10%"
            ),
            AlertRule(
                rule_id="low_balance",
                name="余额不足预警",
                metric="available_balance",
                condition="<",
                threshold=100,
                level=AlertLevel.WARNING,
                channels=[AlertChannel.TELEGRAM, AlertChannel.LOG],
                cooldown=3600,
                description="可用余额不足100 USDT"
            ),
        ]
        
        for rule in default_rules:
            self.rules[rule.rule_id] = rule
    
    async def initialize(self) -> bool:
        """初始化监控系统"""
        logger.info("增强监控系统初始化...")
        
        return True
    
    def set_telegram_bot(self, bot):
        """设置Telegram机器人"""
        self.telegram_bot = bot
    
    def add_webhook_url(self, url: str):
        """添加Webhook URL"""
        self.webhook_urls.append(url)
    
    def register_callback(self, event: str, callback: Callable):
        """注册事件回调"""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    async def update_metric(
        self,
        metric_name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None
    ):
        """更新监控指标"""
        metric = MonitoringMetric(
            name=metric_name,
            value=value,
            tags=tags or {}
        )
        
        if metric_name not in self.metrics:
            self.metrics[metric_name] = []
        
        self.metrics[metric_name].append(metric)
        
        if len(self.metrics[metric_name]) > self.max_metrics_history:
            self.metrics[metric_name] = self.metrics[metric_name][-self.max_metrics_history:]
        
        await self._check_rules(metric_name, value)
        
        for callback in self._callbacks.get("on_metric_update", []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(metric)
                else:
                    callback(metric)
            except Exception as e:
                logger.error(f"指标更新回调失败: {e}")
    
    async def _check_rules(self, metric_name: str, value: float):
        """检查报警规则"""
        for rule in self.rules.values():
            if not rule.enabled or rule.metric != metric_name:
                continue
            
            triggered = self._evaluate_condition(value, rule.condition, rule.threshold)
            
            if triggered:
                await self._trigger_alert(rule, value)
    
    def _evaluate_condition(self, value: float, condition: str, threshold: float) -> bool:
        """评估条件"""
        if condition == ">":
            return value > threshold
        elif condition == ">=":
            return value >= threshold
        elif condition == "<":
            return value < threshold
        elif condition == "<=":
            return value <= threshold
        elif condition == "==":
            return value == threshold
        elif condition == "!=":
            return value != threshold
        return False
    
    async def _trigger_alert(self, rule: AlertRule, value: float):
        """触发报警"""
        now = datetime.now()
        
        if rule.rule_id in self.alert_history:
            last_alert = self.alert_history[rule.rule_id]
            if (now - last_alert).total_seconds() < rule.cooldown:
                return
        
        alert = Alert(
            alert_id=self._generate_alert_id(),
            rule=rule,
            metric_value=value,
            message=self._generate_alert_message(rule, value),
            level=rule.level
        )
        
        self.alerts.append(alert)
        self.alert_history[rule.rule_id] = now
        
        await self._send_alert(alert)
        
        for callback in self._callbacks.get("on_alert", []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                logger.error(f"报警回调失败: {e}")
    
    def _generate_alert_message(self, rule: AlertRule, value: float) -> str:
        """生成报警消息"""
        level_emoji = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.ERROR: "❌",
            AlertLevel.CRITICAL: "🚨",
            AlertLevel.EMERGENCY: "🆘"
        }
        
        emoji = level_emoji.get(rule.level, "📢")
        
        return f"{emoji} **{rule.name}**\n\n" \
               f"指标: {rule.metric}\n" \
               f"当前值: {value:.4f}\n" \
               f"阈值: {rule.threshold}\n" \
               f"级别: {rule.level.value}\n\n" \
               f"描述: {rule.description}"
    
    async def _send_alert(self, alert: Alert):
        """发送报警"""
        for channel in alert.rule.channels:
            try:
                if channel == AlertChannel.TELEGRAM and self.telegram_bot:
                    await self._send_telegram_alert(alert)
                elif channel == AlertChannel.WEBHOOK:
                    await self._send_webhook_alert(alert)
                elif channel == AlertChannel.LOG:
                    self._log_alert(alert)
            except Exception as e:
                logger.error(f"发送报警失败 ({channel.value}): {e}")
    
    async def _send_telegram_alert(self, alert: Alert):
        """发送Telegram报警"""
        if self.telegram_bot and hasattr(self.telegram_bot, 'send_message'):
            await self.telegram_bot.send_message(alert.message)
    
    async def _send_webhook_alert(self, alert: Alert):
        """发送Webhook报警"""
        import aiohttp
        
        payload = {
            "alert_id": alert.alert_id,
            "level": alert.level.value,
            "message": alert.message,
            "metric": alert.rule.metric,
            "value": alert.metric_value,
            "timestamp": alert.timestamp.isoformat()
        }
        
        for url in self.webhook_urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, timeout=5) as resp:
                        if resp.status != 200:
                            logger.warning(f"Webhook报警发送失败: {url}")
            except Exception as e:
                logger.error(f"Webhook报警发送错误: {url} - {e}")
    
    def _log_alert(self, alert: Alert):
        """记录日志报警"""
        log_levels = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.ERROR: logging.ERROR,
            AlertLevel.CRITICAL: logging.CRITICAL,
            AlertLevel.EMERGENCY: logging.CRITICAL
        }
        
        level = log_levels.get(alert.level, logging.INFO)
        logger.log(level, f"[ALERT] {alert.message}")
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """确认报警"""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    async def resolve_alert(self, alert_id: str) -> bool:
        """解决报警"""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                alert.resolved_at = datetime.now()
                
                for callback in self._callbacks.get("on_resolve", []):
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(alert)
                        else:
                            callback(alert)
                    except Exception as e:
                        logger.error(f"报警解决回调失败: {e}")
                
                return True
        return False
    
    async def add_rule(self, rule: AlertRule):
        """添加报警规则"""
        self.rules[rule.rule_id] = rule
        logger.info(f"添加报警规则: {rule.name}")
    
    async def remove_rule(self, rule_id: str) -> bool:
        """移除报警规则"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            logger.info(f"移除报警规则: {rule_id}")
            return True
        return False
    
    async def get_active_alerts(self) -> List[Alert]:
        """获取活动报警"""
        return [a for a in self.alerts if not a.resolved][-50:]
    
    async def get_metric_history(
        self,
        metric_name: str,
        limit: int = 100
    ) -> List[MonitoringMetric]:
        """获取指标历史"""
        if metric_name not in self.metrics:
            return []
        return self.metrics[metric_name][-limit:]
    
    async def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        active_alerts = await self.get_active_alerts()
        
        status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "active_alerts_count": len(active_alerts),
            "rules_count": len(self.rules),
            "metrics_count": len(self.metrics),
            "recent_alerts": []
        }
        
        critical_alerts = [a for a in active_alerts if a.level in [AlertLevel.CRITICAL, AlertLevel.EMERGENCY]]
        if critical_alerts:
            status["status"] = "critical"
        elif active_alerts:
            status["status"] = "warning"
        
        for alert in active_alerts[-5:]:
            status["recent_alerts"].append({
                "alert_id": alert.alert_id,
                "level": alert.level.value,
                "message": alert.message[:100],
                "timestamp": alert.timestamp.isoformat()
            })
        
        return status
    
    def _generate_alert_id(self) -> str:
        """生成报警ID"""
        import hashlib
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return f"alert_{timestamp}"
    
    async def start_monitoring(self):
        """启动监控"""
        self._running = True
        logger.info("监控系统启动")
    
    async def stop_monitoring(self):
        """停止监控"""
        self._running = False
        logger.info("监控系统停止")
    
    async def cleanup(self):
        """清理资源"""
        await self.stop_monitoring()
        logger.info("监控系统清理完成")
