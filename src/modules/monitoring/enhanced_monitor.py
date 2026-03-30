"""
增强型监控告警系统 - 全面的系统监控和告警

功能：
1. 多维度监控（系统、交易、策略、风险）
2. 灵活的告警规则配置
3. 多渠道告警通知（邮件、短信、Webhook）
4. 监控仪表盘数据提供
5. 历史数据存储和分析
"""

import asyncio
import logging
import sqlite3
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable, Union
from enum import Enum
import psutil

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """指标类型"""
    SYSTEM_CPU = "system_cpu"
    SYSTEM_MEMORY = "system_memory"
    SYSTEM_DISK = "system_disk"
    SYSTEM_NETWORK = "system_network"
    TRADE_PNL = "trade_pnl"
    TRADE_VOLUME = "trade_volume"
    STRATEGY_PERFORMANCE = "strategy_performance"
    RISK_VAR = "risk_var"
    RISK_DRAWDOWN = "risk_drawdown"
    API_LATENCY = "api_latency"
    API_ERROR_RATE = "api_error_rate"


class AlertSeverity(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertStatus(Enum):
    """告警状态"""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


@dataclass
class MetricValue:
    """指标值"""
    metric_type: MetricType
    value: float
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_type": self.metric_type.value,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels
        }


@dataclass
class AlertRule:
    """告警规则"""
    rule_id: str
    name: str
    description: str
    metric_type: MetricType
    condition: str  # '>', '<', '==', '!=', '>=', '<='
    threshold: float
    severity: AlertSeverity
    duration: int  # 持续时间（秒）
    enabled: bool = True
    notification_channels: List[str] = field(default_factory=list)
    auto_resolve: bool = True
    resolve_condition: Optional[str] = None
    resolve_threshold: Optional[float] = None


@dataclass
class Alert:
    """告警"""
    alert_id: str
    rule_id: str
    rule_name: str
    severity: AlertSeverity
    status: AlertStatus
    message: str
    metric_value: MetricValue
    triggered_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_by: Optional[str] = None
    notification_sent: bool = False


@dataclass
class NotificationChannel:
    """通知渠道"""
    channel_id: str
    name: str
    channel_type: str  # email, sms, webhook, telegram
    config: Dict[str, Any]
    enabled: bool = True


class EnhancedMonitoringSystem:
    """
    增强型监控告警系统
    
    功能：
    1. 实时指标收集
    2. 告警规则评估
    3. 多渠道通知
    4. 历史数据存储
    """
    
    def __init__(self, db_path: str = "data/monitoring.db"):
        self.db_path = db_path
        self._initialized = False
        self._running = False
        
        # 监控数据
        self.metrics_buffer: List[MetricValue] = []
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self.notification_channels: Dict[str, NotificationChannel] = {}
        
        # 回调函数
        self._metric_callbacks: List[Callable] = []
        self._alert_callbacks: List[Callable] = []
        
        # 任务
        self._collection_task: Optional[asyncio.Task] = None
        self._evaluation_task: Optional[asyncio.Task] = None
        
        # 统计
        self.metrics_collected = 0
        self.alerts_triggered = 0
    
    async def initialize(self):
        """初始化监控系统"""
        logger.info("初始化监控系统...")
        await self._init_database()
        await self._load_alert_rules()
        await self._load_notification_channels()
        self._initialized = True
        self._running = True
        
        # 启动监控任务
        self._collection_task = asyncio.create_task(self._metrics_collection_loop())
        self._evaluation_task = asyncio.create_task(self._alert_evaluation_loop())
        
        logger.info("监控系统初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        logger.info("清理监控系统...")
        self._running = False
        
        if self._collection_task:
            self._collection_task.cancel()
        if self._evaluation_task:
            self._evaluation_task.cancel()
        
        # 保存未持久化的数据
        await self._flush_metrics_buffer()
        
        logger.info("监控系统清理完成")
    
    async def _init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 指标表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_type TEXT NOT NULL,
                value REAL NOT NULL,
                timestamp TEXT NOT NULL,
                labels TEXT
            )
        ''')
        
        # 告警规则表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alert_rules (
                rule_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                metric_type TEXT NOT NULL,
                condition TEXT NOT NULL,
                threshold REAL NOT NULL,
                severity TEXT NOT NULL,
                duration INTEGER NOT NULL,
                enabled INTEGER DEFAULT 1,
                notification_channels TEXT,
                auto_resolve INTEGER DEFAULT 1,
                resolve_condition TEXT,
                resolve_threshold REAL
            )
        ''')
        
        # 告警历史表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id TEXT PRIMARY KEY,
                rule_id TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                metric_value TEXT NOT NULL,
                triggered_at TEXT NOT NULL,
                acknowledged_at TEXT,
                resolved_at TEXT,
                acknowledged_by TEXT,
                resolved_by TEXT,
                notification_sent INTEGER DEFAULT 0
            )
        ''')
        
        # 通知渠道表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notification_channels (
                channel_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                channel_type TEXT NOT NULL,
                config TEXT NOT NULL,
                enabled INTEGER DEFAULT 1
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_metrics_time ON metrics(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_metrics_type ON metrics(metric_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(triggered_at)')
        
        conn.commit()
        conn.close()
        logger.info("监控数据库初始化完成")
    
    async def _load_alert_rules(self):
        """加载告警规则"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM alert_rules WHERE enabled = 1")
        rows = cursor.fetchall()
        
        for row in rows:
            rule = AlertRule(
                rule_id=row[0],
                name=row[1],
                description=row[2],
                metric_type=MetricType(row[3]),
                condition=row[4],
                threshold=row[5],
                severity=AlertSeverity(row[6]),
                duration=row[7],
                enabled=bool(row[8]),
                notification_channels=json.loads(row[9]) if row[9] else [],
                auto_resolve=bool(row[10]),
                resolve_condition=row[11],
                resolve_threshold=row[12]
            )
            self.alert_rules[rule.rule_id] = rule
        
        conn.close()
        logger.info(f"加载了 {len(self.alert_rules)} 条告警规则")
    
    async def _load_notification_channels(self):
        """加载通知渠道"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM notification_channels WHERE enabled = 1")
        rows = cursor.fetchall()
        
        for row in rows:
            channel = NotificationChannel(
                channel_id=row[0],
                name=row[1],
                channel_type=row[2],
                config=json.loads(row[3]),
                enabled=bool(row[4])
            )
            self.notification_channels[channel.channel_id] = channel
        
        conn.close()
        logger.info(f"加载了 {len(self.notification_channels)} 个通知渠道")
    
    async def _metrics_collection_loop(self):
        """指标收集循环"""
        logger.info("启动指标收集循环")
        
        while self._running:
            try:
                # 收集系统指标
                await self._collect_system_metrics()
                
                # 每10秒收集一次
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"指标收集出错: {e}")
    
    async def _collect_system_metrics(self):
        """收集系统指标"""
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            await self.record_metric(MetricType.SYSTEM_CPU, cpu_percent)
            
            # 内存使用率
            memory = psutil.virtual_memory()
            await self.record_metric(MetricType.SYSTEM_MEMORY, memory.percent)
            
            # 磁盘使用率
            disk = psutil.disk_usage('/')
            await self.record_metric(MetricType.SYSTEM_DISK, disk.percent)
            
        except Exception as e:
            logger.error(f"收集系统指标失败: {e}")
    
    async def record_metric(self, metric_type: MetricType, value: float, labels: Dict[str, str] = None):
        """记录指标"""
        metric = MetricValue(
            metric_type=metric_type,
            value=value,
            timestamp=datetime.now(),
            labels=labels or {}
        )
        
        self.metrics_buffer.append(metric)
        self.metrics_collected += 1
        
        # 触发回调
        for callback in self._metric_callbacks:
            try:
                await callback(metric)
            except Exception as e:
                logger.error(f"指标回调出错: {e}")
        
        # 批量持久化
        if len(self.metrics_buffer) >= 100:
            await self._flush_metrics_buffer()
    
    async def _flush_metrics_buffer(self):
        """持久化指标缓冲区"""
        if not self.metrics_buffer:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for metric in self.metrics_buffer:
            cursor.execute('''
                INSERT INTO metrics (metric_type, value, timestamp, labels)
                VALUES (?, ?, ?, ?)
            ''', (
                metric.metric_type.value,
                metric.value,
                metric.timestamp.isoformat(),
                json.dumps(metric.labels)
            ))
        
        conn.commit()
        conn.close()
        
        self.metrics_buffer.clear()
    
    async def _alert_evaluation_loop(self):
        """告警评估循环"""
        logger.info("启动告警评估循环")
        
        while self._running:
            try:
                # 评估告警规则
                await self._evaluate_alert_rules()
                
                # 每5秒评估一次
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"告警评估出错: {e}")
    
    async def _evaluate_alert_rules(self):
        """评估告警规则"""
        for rule in self.alert_rules.values():
            if not rule.enabled:
                continue
            
            try:
                # 获取最新指标值
                metric_value = await self._get_latest_metric(rule.metric_type)
                if metric_value is None:
                    continue
                
                # 评估条件
                triggered = self._evaluate_condition(
                    metric_value.value, 
                    rule.condition, 
                    rule.threshold
                )
                
                if triggered:
                    # 检查是否已存在活跃的告警
                    existing_alert = self._find_active_alert(rule.rule_id)
                    if existing_alert is None:
                        # 创建新告警
                        await self._create_alert(rule, metric_value)
                else:
                    # 检查是否需要自动恢复
                    if rule.auto_resolve:
                        await self._auto_resolve_alert(rule.rule_id, metric_value)
                        
            except Exception as e:
                logger.error(f"评估规则 {rule.rule_id} 失败: {e}")
    
    def _evaluate_condition(self, value: float, condition: str, threshold: float) -> bool:
        """评估条件"""
        if condition == '>':
            return value > threshold
        elif condition == '<':
            return value < threshold
        elif condition == '>=':
            return value >= threshold
        elif condition == '<=':
            return value <= threshold
        elif condition == '==':
            return value == threshold
        elif condition == '!=':
            return value != threshold
        return False
    
    async def _get_latest_metric(self, metric_type: MetricType) -> Optional[MetricValue]:
        """获取最新指标值"""
        # 从缓冲区查找
        for metric in reversed(self.metrics_buffer):
            if metric.metric_type == metric_type:
                return metric
        
        # 从数据库查找
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT metric_type, value, timestamp, labels
            FROM metrics
            WHERE metric_type = ?
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (metric_type.value,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return MetricValue(
                metric_type=MetricType(row[0]),
                value=row[1],
                timestamp=datetime.fromisoformat(row[2]),
                labels=json.loads(row[3]) if row[3] else {}
            )
        
        return None
    
    def _find_active_alert(self, rule_id: str) -> Optional[Alert]:
        """查找活跃的告警"""
        for alert in self.active_alerts.values():
            if alert.rule_id == rule_id and alert.status == AlertStatus.ACTIVE:
                return alert
        return None
    
    async def _create_alert(self, rule: AlertRule, metric_value: MetricValue):
        """创建告警"""
        alert_id = f"alert_{int(time.time())}_{rule.rule_id}"
        
        message = f"{rule.name}: {metric_value.value:.2f} {rule.condition} {rule.threshold}"
        
        alert = Alert(
            alert_id=alert_id,
            rule_id=rule.rule_id,
            rule_name=rule.name,
            severity=rule.severity,
            status=AlertStatus.ACTIVE,
            message=message,
            metric_value=metric_value,
            triggered_at=datetime.now()
        )
        
        self.active_alerts[alert_id] = alert
        self.alert_history.append(alert)
        self.alerts_triggered += 1
        
        # 持久化
        await self._persist_alert(alert)
        
        # 发送通知
        await self._send_notification(alert, rule)
        
        # 触发回调
        for callback in self._alert_callbacks:
            try:
                await callback(alert)
            except Exception as e:
                logger.error(f"告警回调出错: {e}")
        
        logger.warning(f"告警触发: {message}")
    
    async def _persist_alert(self, alert: Alert):
        """持久化告警"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO alerts
            (alert_id, rule_id, rule_name, severity, status, message, metric_value,
             triggered_at, acknowledged_at, resolved_at, acknowledged_by, resolved_by, notification_sent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            alert.alert_id,
            alert.rule_id,
            alert.rule_name,
            alert.severity.value,
            alert.status.value,
            alert.message,
            json.dumps(alert.metric_value.to_dict()),
            alert.triggered_at.isoformat(),
            alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
            alert.resolved_at.isoformat() if alert.resolved_at else None,
            alert.acknowledged_by,
            alert.resolved_by,
            int(alert.notification_sent)
        ))
        
        conn.commit()
        conn.close()
    
    async def _send_notification(self, alert: Alert, rule: AlertRule):
        """发送通知"""
        for channel_id in rule.notification_channels:
            channel = self.notification_channels.get(channel_id)
            if not channel or not channel.enabled:
                continue
            
            try:
                if channel.channel_type == "webhook":
                    await self._send_webhook_notification(channel, alert)
                elif channel.channel_type == "email":
                    await self._send_email_notification(channel, alert)
                elif channel.channel_type == "telegram":
                    await self._send_telegram_notification(channel, alert)
                    
            except Exception as e:
                logger.error(f"发送通知失败 ({channel_id}): {e}")
        
        alert.notification_sent = True
    
    async def _send_webhook_notification(self, channel: NotificationChannel, alert: Alert):
        """发送Webhook通知"""
        import aiohttp
        
        webhook_url = channel.config.get('url')
        if not webhook_url:
            return
        
        payload = {
            "alert_id": alert.alert_id,
            "rule_name": alert.rule_name,
            "severity": alert.severity.value,
            "message": alert.message,
            "value": alert.metric_value.value,
            "timestamp": alert.triggered_at.isoformat()
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload) as response:
                if response.status == 200:
                    logger.info(f"Webhook通知发送成功: {alert.alert_id}")
    
    async def _send_email_notification(self, channel: NotificationChannel, alert: Alert):
        """发送邮件通知（简化）"""
        # 实际实现需要使用邮件库如smtplib
        logger.info(f"邮件通知: {alert.message}")
    
    async def _send_telegram_notification(self, channel: NotificationChannel, alert: Alert):
        """发送Telegram通知（简化）"""
        # 实际实现需要使用python-telegram-bot
        logger.info(f"Telegram通知: {alert.message}")
    
    async def _auto_resolve_alert(self, rule_id: str, metric_value: MetricValue):
        """自动恢复告警"""
        alert = self._find_active_alert(rule_id)
        if alert is None:
            return
        
        rule = self.alert_rules.get(rule_id)
        if not rule or not rule.auto_resolve:
            return
        
        # 检查恢复条件
        if rule.resolve_condition and rule.resolve_threshold:
            resolved = self._evaluate_condition(
                metric_value.value,
                rule.resolve_condition,
                rule.resolve_threshold
            )
            
            if resolved:
                await self.resolve_alert(alert.alert_id, "system")
    
    async def acknowledge_alert(self, alert_id: str, user_id: str) -> bool:
        """确认告警"""
        if alert_id not in self.active_alerts:
            return False
        
        alert = self.active_alerts[alert_id]
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now()
        alert.acknowledged_by = user_id
        
        await self._persist_alert(alert)
        logger.info(f"告警已确认: {alert_id} by {user_id}")
        return True
    
    async def resolve_alert(self, alert_id: str, user_id: str) -> bool:
        """解决告警"""
        if alert_id not in self.active_alerts:
            return False
        
        alert = self.active_alerts[alert_id]
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now()
        alert.resolved_by = user_id
        
        await self._persist_alert(alert)
        
        # 从活跃告警中移除
        del self.active_alerts[alert_id]
        
        logger.info(f"告警已解决: {alert_id} by {user_id}")
        return True
    
    def get_active_alerts(self, severity: AlertSeverity = None) -> List[Alert]:
        """获取活跃告警"""
        alerts = list(self.active_alerts.values())
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return sorted(alerts, key=lambda x: x.triggered_at, reverse=True)
    
    def get_metrics_summary(self, hours: int = 24) -> Dict[str, Any]:
        """获取指标摘要"""
        cutoff = datetime.now() - timedelta(hours=hours)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT metric_type, AVG(value), MIN(value), MAX(value)
            FROM metrics
            WHERE timestamp > ?
            GROUP BY metric_type
        ''', (cutoff.isoformat(),))
        
        summary = {}
        for row in cursor.fetchall():
            summary[row[0]] = {
                "avg": row[1],
                "min": row[2],
                "max": row[3]
            }
        
        conn.close()
        return summary
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取仪表盘数据"""
        return {
            "system_metrics": self.get_metrics_summary(1),
            "active_alerts": len(self.active_alerts),
            "alerts_by_severity": {
                severity.value: len([a for a in self.active_alerts.values() if a.severity == severity])
                for severity in AlertSeverity
            },
            "total_metrics_collected": self.metrics_collected,
            "total_alerts_triggered": self.alerts_triggered,
            "system_status": "healthy" if len(self.active_alerts) == 0 else "warning"
        }


# 全局监控实例
_monitoring_system: Optional[EnhancedMonitoringSystem] = None


async def get_monitoring_system() -> EnhancedMonitoringSystem:
    """获取监控系统实例"""
    global _monitoring_system
    if _monitoring_system is None:
        _monitoring_system = EnhancedMonitoringSystem()
        await _monitoring_system.initialize()
    return _monitoring_system
