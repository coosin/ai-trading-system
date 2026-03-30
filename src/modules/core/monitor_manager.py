"""
监控告警模块 - 全智能量化交易系统的健康守护者

功能：
1. 系统监控（CPU、内存、磁盘、网络）
2. 服务监控（数据库、API、交易引擎状态）
3. 业务监控（交易频率、成功率、延迟）
4. 告警管理（阈值告警、异常检测）
5. 仪表板（实时监控仪表板）
"""

import asyncio
import json
import logging
import platform
import socket
import statistics
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


class MonitorType(Enum):
    """监控类型"""

    SYSTEM = "system"  # 系统监控
    SERVICE = "service"  # 服务监控
    BUSINESS = "business"  # 业务监控
    CUSTOM = "custom"  # 自定义监控


class AlertLevel(Enum):
    """告警级别"""

    INFO = "info"  # 信息
    WARNING = "warning"  # 警告
    ERROR = "error"  # 错误
    CRITICAL = "critical"  # 严重


class ServiceStatus(Enum):
    """服务状态"""

    HEALTHY = "healthy"  # 健康
    DEGRADED = "degraded"  # 降级
    UNHEALTHY = "unhealthy"  # 不健康
    OFFLINE = "offline"  # 离线


@dataclass
class MonitorConfig:
    """监控配置"""

    monitor_id: str
    name: str
    monitor_type: MonitorType
    enabled: bool = True
    check_interval: int = 60  # 检查间隔（秒）
    alert_thresholds: Dict[str, float] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "monitor_id": self.monitor_id,
            "name": self.name,
            "monitor_type": self.monitor_type.value,
            "enabled": self.enabled,
            "check_interval": self.check_interval,
            "alert_thresholds": self.alert_thresholds,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class MonitorMetric:
    """监控指标"""

    metric_id: str
    monitor_id: str
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    unit: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "metric_id": self.metric_id,
            "monitor_id": self.monitor_id,
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "unit": self.unit,
            "tags": self.tags,
            "metadata": self.metadata,
        }


@dataclass
class MonitorAlert:
    """监控告警"""

    alert_id: str
    monitor_id: str
    alert_level: AlertLevel
    message: str
    metric_name: str
    metric_value: float
    threshold: float
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "alert_id": self.alert_id,
            "monitor_id": self.monitor_id,
            "alert_level": self.alert_level.value,
            "message": self.message,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "metadata": self.metadata,
        }


@dataclass
class ServiceHealth:
    """服务健康状态"""

    service_name: str
    status: ServiceStatus
    response_time: float = 0.0  # 响应时间（毫秒）
    success_rate: float = 1.0  # 成功率 0-1
    last_check: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "service_name": self.service_name,
            "status": self.status.value,
            "response_time": self.response_time,
            "success_rate": self.success_rate,
            "last_check": self.last_check.isoformat(),
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class SystemMetrics:
    """系统指标"""

    timestamp: datetime = field(default_factory=datetime.now)
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    network_sent_mb: float = 0.0
    network_recv_mb: float = 0.0
    load_avg_1m: float = 0.0
    load_avg_5m: float = 0.0
    load_avg_15m: float = 0.0
    uptime_seconds: float = 0.0
    process_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_used_mb": self.memory_used_mb,
            "memory_total_mb": self.memory_total_mb,
            "disk_percent": self.disk_percent,
            "disk_used_gb": self.disk_used_gb,
            "disk_total_gb": self.disk_total_gb,
            "network_sent_mb": self.network_sent_mb,
            "network_recv_mb": self.network_recv_mb,
            "load_avg_1m": self.load_avg_1m,
            "load_avg_5m": self.load_avg_5m,
            "load_avg_15m": self.load_avg_15m,
            "uptime_seconds": self.uptime_seconds,
            "process_count": self.process_count,
        }


class MonitorManager:
    """
    监控管理器

    核心功能：
    1. 系统监控
    2. 服务监控
    3. 业务监控
    4. 告警管理
    5. 仪表板
    """

    def __init__(self, config_manager=None):
        """
        初始化监控管理器

        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager

        # 监控配置
        self.monitor_configs: Dict[str, MonitorConfig] = {}

        # 监控数据
        self.metrics: Dict[str, List[MonitorMetric]] = {}
        self.metrics_history: List[MonitorMetric] = []

        # 告警管理
        self.alerts: Dict[str, MonitorAlert] = {}
        self.alert_history: List[MonitorAlert] = []

        # 服务健康
        self.service_health: Dict[str, ServiceHealth] = {}

        # 系统指标
        self.system_metrics: List[SystemMetrics] = []

        # 统计
        self.stats = {
            "total_checks": 0,
            "total_alerts": 0,
            "active_alerts": 0,
            "system_up_time": 0,
            "last_check_time": None,
        }

        # 任务和锁
        self._tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._initialized = False
        self._running = False

        # 网络统计
        self._last_network_stats = None
        self._last_network_time = None

        logger.info("监控管理器初始化完成")

    async def initialize(self) -> None:
        """
        初始化监控管理器

        加载配置，设置默认监控
        """
        if self._initialized:
            return

        logger.info("初始化监控管理器...")

        try:
            # 加载配置
            await self._load_config()

            # 设置默认监控
            await self._setup_default_monitors()

            # 启动监控任务
            self._tasks.append(asyncio.create_task(self._system_monitoring_worker()))
            self._tasks.append(asyncio.create_task(self._service_monitoring_worker()))
            self._tasks.append(asyncio.create_task(self._alert_checking_worker()))

            self._initialized = True
            logger.info("监控管理器初始化完成")

        except Exception as e:
            logger.error(f"监控管理器初始化失败: {e}")
            traceback.print_exc()

    async def cleanup(self) -> None:
        """
        清理监控管理器

        保存状态，清理资源
        """
        logger.info("清理监控管理器...")

        self._running = False

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()

        # 保存状态
        await self._save_state()

        self._initialized = False
        logger.info("监控管理器清理完成")

    async def register_monitor(self, config: MonitorConfig) -> bool:
        """
        注册监控

        Args:
            config: 监控配置

        Returns:
            是否注册成功
        """
        async with self._lock:
            if config.monitor_id in self.monitor_configs:
                logger.warning(f"监控已存在: {config.monitor_id}")
                return False

            self.monitor_configs[config.monitor_id] = config
            self.metrics[config.monitor_id] = []

            logger.info(f"注册监控: {config.name} ({config.monitor_type.value})")
            return True

    async def unregister_monitor(self, monitor_id: str) -> bool:
        """
        取消注册监控

        Args:
            monitor_id: 监控ID

        Returns:
            是否取消成功
        """
        async with self._lock:
            if monitor_id not in self.monitor_configs:
                logger.warning(f"监控不存在: {monitor_id}")
                return False

            del self.monitor_configs[monitor_id]
            del self.metrics[monitor_id]

            logger.info(f"取消注册监控: {monitor_id}")
            return True

    async def enable_monitor(self, monitor_id: str) -> bool:
        """
        启用监控

        Args:
            monitor_id: 监控ID

        Returns:
            是否启用成功
        """
        async with self._lock:
            if monitor_id not in self.monitor_configs:
                logger.warning(f"监控不存在: {monitor_id}")
                return False

            self.monitor_configs[monitor_id].enabled = True
            logger.info(f"启用监控: {monitor_id}")
            return True

    async def disable_monitor(self, monitor_id: str) -> bool:
        """
        禁用监控

        Args:
            monitor_id: 监控ID

        Returns:
            是否禁用成功
        """
        async with self._lock:
            if monitor_id not in self.monitor_configs:
                logger.warning(f"监控不存在: {monitor_id}")
                return False

            self.monitor_configs[monitor_id].enabled = False
            logger.info(f"禁用监控: {monitor_id}")
            return True

    async def collect_metric(
        self,
        monitor_id: str,
        name: str,
        value: float,
        unit: str = "",
        tags: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        收集指标

        Args:
            monitor_id: 监控ID
            name: 指标名称
            value: 指标值
            unit: 单位
            tags: 标签

        Returns:
            是否收集成功
        """
        async with self._lock:
            if monitor_id not in self.monitor_configs:
                logger.warning(f"监控不存在: {monitor_id}")
                return False

            # 创建指标
            metric = MonitorMetric(
                metric_id=f"metric_{uuid.uuid4().hex[:8]}",
                monitor_id=monitor_id,
                name=name,
                value=value,
                unit=unit,
                tags=tags or {},
                timestamp=datetime.now(),
            )

            # 保存指标
            self.metrics[monitor_id].append(metric)
            self.metrics_history.append(metric)

            # 限制历史记录长度
            if len(self.metrics[monitor_id]) > 1000:
                self.metrics[monitor_id] = self.metrics[monitor_id][-1000:]

            if len(self.metrics_history) > 10000:
                self.metrics_history = self.metrics_history[-10000:]

            # 检查告警
            await self._check_alert_thresholds(monitor_id, metric)

            self.stats["total_checks"] += 1
            self.stats["last_check_time"] = datetime.now()

            return True

    async def get_metrics(
        self,
        monitor_id: Optional[str] = None,
        name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[MonitorMetric]:
        """
        获取指标

        Args:
            monitor_id: 过滤监控ID
            name: 过滤指标名称
            start_time: 开始时间
            end_time: 结束时间
            limit: 限制数量

        Returns:
            指标列表
        """
        if monitor_id:
            metrics = self.metrics.get(monitor_id, [])
        else:
            metrics = self.metrics_history.copy()

        # 过滤
        if name:
            metrics = [m for m in metrics if m.name == name]

        if start_time:
            metrics = [m for m in metrics if m.timestamp >= start_time]

        if end_time:
            metrics = [m for m in metrics if m.timestamp <= end_time]

        # 按时间排序（最新的在前面）
        metrics.sort(key=lambda m: m.timestamp, reverse=True)

        return metrics[:limit]

    async def get_metric_statistics(
        self,
        monitor_id: str,
        name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        获取指标统计

        Args:
            monitor_id: 监控ID
            name: 指标名称
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            指标统计
        """
        metrics = await self.get_metrics(monitor_id, name, start_time, end_time, limit=1000)

        if not metrics:
            return {"count": 0, "min": 0, "max": 0, "mean": 0, "median": 0, "std": 0}

        values = [m.value for m in metrics]

        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0,
            "first_timestamp": metrics[-1].timestamp.isoformat(),
            "last_timestamp": metrics[0].timestamp.isoformat(),
        }

    async def get_alerts(
        self,
        monitor_id: Optional[str] = None,
        alert_level: Optional[AlertLevel] = None,
        unresolved: bool = True,
    ) -> List[MonitorAlert]:
        """
        获取告警

        Args:
            monitor_id: 过滤监控ID
            alert_level: 过滤告警级别
            unresolved: 只获取未解决的告警

        Returns:
            告警列表
        """
        alerts = list(self.alerts.values())

        if monitor_id:
            alerts = [a for a in alerts if a.monitor_id == monitor_id]

        if alert_level:
            alerts = [a for a in alerts if a.alert_level == alert_level]

        if unresolved:
            alerts = [a for a in alerts if not a.resolved]

        # 按时间排序（最新的在前面）
        alerts.sort(key=lambda a: a.timestamp, reverse=True)

        return alerts

    async def acknowledge_alert(self, alert_id: str) -> bool:
        """
        确认告警

        Args:
            alert_id: 告警ID

        Returns:
            是否确认成功
        """
        async with self._lock:
            if alert_id not in self.alerts:
                return False

            self.alerts[alert_id].acknowledged = True
            logger.info(f"确认告警: {alert_id}")
            return True

    async def resolve_alert(self, alert_id: str) -> bool:
        """
        解决告警

        Args:
            alert_id: 告警ID

        Returns:
            是否解决成功
        """
        async with self._lock:
            if alert_id not in self.alerts:
                return False

            self.alerts[alert_id].resolved = True
            self.alerts[alert_id].resolved_at = datetime.now()
            self.stats["active_alerts"] = max(0, self.stats["active_alerts"] - 1)

            # 移动到历史记录
            self.alert_history.append(self.alerts[alert_id])
            del self.alerts[alert_id]

            logger.info(f"解决告警: {alert_id}")
            return True

    async def get_service_health(
        self, service_name: Optional[str] = None
    ) -> Dict[str, ServiceHealth]:
        """
        获取服务健康状态

        Args:
            service_name: 服务名称

        Returns:
            服务健康状态
        """
        if service_name:
            return {service_name: self.service_health.get(service_name)}
        else:
            return self.service_health.copy()

    async def update_service_health(
        self,
        service_name: str,
        status: ServiceStatus,
        response_time: float = 0.0,
        success_rate: float = 1.0,
        error_message: Optional[str] = None,
    ) -> None:
        """
        更新服务健康状态

        Args:
            service_name: 服务名称
            status: 状态
            response_time: 响应时间（毫秒）
            success_rate: 成功率
            error_message: 错误信息
        """
        async with self._lock:
            self.service_health[service_name] = ServiceHealth(
                service_name=service_name,
                status=status,
                response_time=response_time,
                success_rate=success_rate,
                last_check=datetime.now(),
                error_message=error_message,
            )

    async def get_system_metrics(self, limit: int = 100) -> List[SystemMetrics]:
        """
        获取系统指标

        Args:
            limit: 限制数量

        Returns:
            系统指标列表
        """
        return self.system_metrics[-limit:] if self.system_metrics else []

    async def get_system_summary(self) -> Dict[str, Any]:
        """
        获取系统摘要

        Returns:
            系统摘要
        """
        if not self.system_metrics:
            return {}

        latest = self.system_metrics[-1] if self.system_metrics else SystemMetrics()

        # 计算趋势（最近5个点）
        recent_metrics = (
            self.system_metrics[-5:] if len(self.system_metrics) >= 5 else self.system_metrics
        )

        cpu_trend = "stable"
        memory_trend = "stable"

        if len(recent_metrics) >= 2:
            cpu_values = [m.cpu_percent for m in recent_metrics]
            memory_values = [m.memory_percent for m in recent_metrics]

            if cpu_values[-1] > cpu_values[0] + 5:
                cpu_trend = "increasing"
            elif cpu_values[-1] < cpu_values[0] - 5:
                cpu_trend = "decreasing"

            if memory_values[-1] > memory_values[0] + 5:
                memory_trend = "increasing"
            elif memory_values[-1] < memory_values[0] - 5:
                memory_trend = "decreasing"

        return {
            "timestamp": latest.timestamp.isoformat(),
            "cpu": {
                "percent": latest.cpu_percent,
                "trend": cpu_trend,
                "status": (
                    "healthy"
                    if latest.cpu_percent < 80
                    else "warning" if latest.cpu_percent < 90 else "critical"
                ),
            },
            "memory": {
                "percent": latest.memory_percent,
                "used_mb": latest.memory_used_mb,
                "total_mb": latest.memory_total_mb,
                "trend": memory_trend,
                "status": (
                    "healthy"
                    if latest.memory_percent < 80
                    else "warning" if latest.memory_percent < 90 else "critical"
                ),
            },
            "disk": {
                "percent": latest.disk_percent,
                "used_gb": latest.disk_used_gb,
                "total_gb": latest.disk_total_gb,
                "status": (
                    "healthy"
                    if latest.disk_percent < 80
                    else "warning" if latest.disk_percent < 90 else "critical"
                ),
            },
            "load": {
                "1m": latest.load_avg_1m,
                "5m": latest.load_avg_5m,
                "15m": latest.load_avg_15m,
                "status": (
                    "healthy"
                    if latest.load_avg_1m < 1.0
                    else "warning" if latest.load_avg_1m < 2.0 else "critical"
                ),
            },
            "uptime": {
                "seconds": latest.uptime_seconds,
                "formatted": str(timedelta(seconds=int(latest.uptime_seconds))),
            },
        }

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """
        获取仪表板数据

        Returns:
            仪表板数据
        """
        # 系统摘要
        system_summary = await self.get_system_summary()

        # 服务健康
        service_health = await self.get_service_health()

        # 活跃告警
        active_alerts = await self.get_alerts(unresolved=True)

        # 最近指标
        recent_metrics = await self.get_metrics(limit=50)

        # 统计
        total_services = len(service_health)
        healthy_services = len(
            [s for s in service_health.values() if s.status == ServiceStatus.HEALTHY]
        )

        return {
            "system": system_summary,
            "services": {
                "total": total_services,
                "healthy": healthy_services,
                "unhealthy": total_services - healthy_services,
                "list": {name: health.to_dict() for name, health in service_health.items()},
            },
            "alerts": {
                "active": len(active_alerts),
                "critical": len([a for a in active_alerts if a.alert_level == AlertLevel.CRITICAL]),
                "warning": len([a for a in active_alerts if a.alert_level == AlertLevel.WARNING]),
                "list": [a.to_dict() for a in active_alerts[:10]],  # 最近10个告警
            },
            "metrics": {
                "recent": [m.to_dict() for m in recent_metrics[:20]],  # 最近20个指标
                "total_checks": self.stats["total_checks"],
            },
            "timestamp": datetime.now().isoformat(),
        }

    async def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计信息
        """
        async with self._lock:
            stats = self.stats.copy()
            stats.update(
                {
                    "total_monitors": len(self.monitor_configs),
                    "enabled_monitors": len(
                        [m for m in self.monitor_configs.values() if m.enabled]
                    ),
                    "total_metrics": len(self.metrics_history),
                    "total_alerts_history": len(self.alert_history),
                    "active_alerts": len(self.alerts),
                    "total_services": len(self.service_health),
                    "system_metrics_count": len(self.system_metrics),
                }
            )
            return stats

    # 私有方法

    async def _load_config(self) -> None:
        """加载监控配置"""
        if self.config_manager:
            monitor_config = await self.config_manager.get_config("monitoring", {})

            # 加载监控配置
            for monitor_data in monitor_config.get("monitors", []):
                try:
                    config = MonitorConfig(
                        monitor_id=monitor_data["monitor_id"],
                        name=monitor_data["name"],
                        monitor_type=MonitorType(monitor_data["monitor_type"]),
                        enabled=monitor_data.get("enabled", True),
                        check_interval=monitor_data.get("check_interval", 60),
                        alert_thresholds=monitor_data.get("alert_thresholds", {}),
                        tags=monitor_data.get("tags", []),
                        metadata=monitor_data.get("metadata", {}),
                    )

                    await self.register_monitor(config)

                except Exception as e:
                    logger.error(f"加载监控配置失败: {e}")

        # 如果没有配置，设置默认值
        if not self.monitor_configs:
            await self._setup_default_monitors()

    async def _setup_default_monitors(self) -> None:
        """设置默认监控"""

        # 系统CPU监控
        cpu_monitor = MonitorConfig(
            monitor_id="system_cpu",
            name="系统CPU使用率",
            monitor_type=MonitorType.SYSTEM,
            check_interval=30,
            alert_thresholds={"warning": 80.0, "critical": 90.0},  # 80%警告  # 90%严重
            tags=["system", "cpu"],
        )
        await self.register_monitor(cpu_monitor)

        # 系统内存监控
        memory_monitor = MonitorConfig(
            monitor_id="system_memory",
            name="系统内存使用率",
            monitor_type=MonitorType.SYSTEM,
            check_interval=30,
            alert_thresholds={"warning": 85.0, "critical": 95.0},  # 85%警告  # 95%严重
            tags=["system", "memory"],
        )
        await self.register_monitor(memory_monitor)

        # 系统磁盘监控
        disk_monitor = MonitorConfig(
            monitor_id="system_disk",
            name="系统磁盘使用率",
            monitor_type=MonitorType.SYSTEM,
            check_interval=300,  # 5分钟
            alert_thresholds={"warning": 85.0, "critical": 95.0},  # 85%警告  # 95%严重
            tags=["system", "disk"],
        )
        await self.register_monitor(disk_monitor)

        # API服务监控（示例）
        api_monitor = MonitorConfig(
            monitor_id="service_api",
            name="API服务健康",
            monitor_type=MonitorType.SERVICE,
            check_interval=60,
            alert_thresholds={
                "response_time_warning": 1000.0,  # 1秒警告
                "response_time_critical": 5000.0,  # 5秒严重
                "success_rate_warning": 0.95,  # 95%成功率警告
                "success_rate_critical": 0.90,  # 90%成功率严重
            },
            tags=["service", "api"],
        )
        await self.register_monitor(api_monitor)

        logger.info(f"设置 {len(self.monitor_configs)} 个默认监控")

    async def _system_monitoring_worker(self) -> None:
        """系统监控工作线程"""
        logger.info("启动系统监控线程")

        while self._initialized:
            try:
                await asyncio.sleep(30)  # 每30秒检查一次

                # 收集系统指标
                await self._collect_system_metrics()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"系统监控线程错误: {e}")
                await asyncio.sleep(30)

        logger.info("系统监控线程停止")

    async def _service_monitoring_worker(self) -> None:
        """服务监控工作线程"""
        logger.info("启动服务监控线程")

        while self._initialized:
            try:
                await asyncio.sleep(60)  # 每60秒检查一次

                # 检查服务健康
                await self._check_services_health()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"服务监控线程错误: {e}")
                await asyncio.sleep(60)

        logger.info("服务监控线程停止")

    async def _alert_checking_worker(self) -> None:
        """告警检查工作线程"""
        logger.info("启动告警检查线程")

        while self._initialized:
            try:
                await asyncio.sleep(10)  # 每10秒检查一次

                # 清理旧告警和指标
                await self._cleanup_old_data()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"告警检查线程错误: {e}")
                await asyncio.sleep(10)

        logger.info("告警检查线程停止")

    async def _collect_system_metrics(self) -> None:
        """收集系统指标"""
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            await self.collect_metric("system_cpu", "cpu_percent", cpu_percent, "%")

            # 内存使用
            memory = psutil.virtual_memory()
            await self.collect_metric("system_memory", "memory_percent", memory.percent, "%")
            await self.collect_metric(
                "system_memory", "memory_used_mb", memory.used / 1024 / 1024, "MB"
            )
            await self.collect_metric(
                "system_memory", "memory_total_mb", memory.total / 1024 / 1024, "MB"
            )

            # 磁盘使用
            disk = psutil.disk_usage("/")
            await self.collect_metric("system_disk", "disk_percent", disk.percent, "%")
            await self.collect_metric(
                "system_disk", "disk_used_gb", disk.used / 1024 / 1024 / 1024, "GB"
            )
            await self.collect_metric(
                "system_disk", "disk_total_gb", disk.total / 1024 / 1024 / 1024, "GB"
            )

            # 网络统计
            net_io = psutil.net_io_counters()
            current_time = time.time()

            if self._last_network_stats and self._last_network_time:
                time_diff = current_time - self._last_network_time

                sent_rate = (net_io.bytes_sent - self._last_network_stats.bytes_sent) / time_diff
                recv_rate = (net_io.bytes_recv - self._last_network_stats.bytes_recv) / time_diff

                await self.collect_metric(
                    "system_network", "network_sent_kbps", sent_rate / 1024 * 8, "kbps"
                )
                await self.collect_metric(
                    "system_network", "network_recv_kbps", recv_rate / 1024 * 8, "kbps"
                )

            self._last_network_stats = net_io
            self._last_network_time = current_time

            # 系统负载（Linux）
            if hasattr(psutil, "getloadavg"):
                try:
                    load_avg = psutil.getloadavg()
                    await self.collect_metric("system_load", "load_avg_1m", load_avg[0])
                    await self.collect_metric("system_load", "load_avg_5m", load_avg[1])
                    await self.collect_metric("system_load", "load_avg_15m", load_avg[2])
                except:
                    pass

            # 进程数量
            process_count = len(psutil.pids())
            await self.collect_metric("system_process", "process_count", process_count)

            # 保存完整系统指标
            system_metric = SystemMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / 1024 / 1024,
                memory_total_mb=memory.total / 1024 / 1024,
                disk_percent=disk.percent,
                disk_used_gb=disk.used / 1024 / 1024 / 1024,
                disk_total_gb=disk.total / 1024 / 1024 / 1024,
                process_count=process_count,
                uptime_seconds=time.time() - psutil.boot_time(),
            )

            if hasattr(psutil, "getloadavg"):
                try:
                    load_avg = psutil.getloadavg()
                    system_metric.load_avg_1m = load_avg[0]
                    system_metric.load_avg_5m = load_avg[1]
                    system_metric.load_avg_15m = load_avg[2]
                except:
                    pass

            async with self._lock:
                self.system_metrics.append(system_metric)

                # 限制历史记录长度
                if len(self.system_metrics) > 1000:
                    self.system_metrics = self.system_metrics[-1000:]

            logger.debug(
                f"收集系统指标: CPU={cpu_percent}%, 内存={memory.percent}%, 磁盘={disk.percent}%"
            )

        except Exception as e:
            logger.error(f"收集系统指标失败: {e}")

    async def _check_services_health(self) -> None:
        """检查服务健康"""
        # 这里应该检查各种服务的健康状态
        # 为简化，只检查示例服务

        # 检查本地API服务（示例）
        try:
            # 模拟API检查
            response_time = 50.0  # 50ms
            success_rate = 0.99  # 99%成功率

            status = ServiceStatus.HEALTHY
            if success_rate < 0.95:
                status = ServiceStatus.DEGRADED
            elif success_rate < 0.90:
                status = ServiceStatus.UNHEALTHY

            await self.update_service_health(
                service_name="api_service",
                status=status,
                response_time=response_time,
                success_rate=success_rate,
            )

            # 收集指标
            await self.collect_metric("service_api", "api_response_time", response_time, "ms")
            await self.collect_metric("service_api", "api_success_rate", success_rate * 100, "%")

        except Exception as e:
            logger.error(f"检查API服务健康失败: {e}")
            await self.update_service_health(
                service_name="api_service", status=ServiceStatus.OFFLINE, error_message=str(e)
            )

    async def _check_alert_thresholds(self, monitor_id: str, metric: MonitorMetric) -> None:
        """检查告警阈值"""
        if monitor_id not in self.monitor_configs:
            return

        config = self.monitor_configs[monitor_id]
        thresholds = config.alert_thresholds

        if not thresholds:
            return

        # 检查阈值
        alert_level = None
        threshold = None

        # 根据指标名称和阈值配置检查
        if metric.name == "cpu_percent":
            if metric.value >= thresholds.get("critical", 90):
                alert_level = AlertLevel.CRITICAL
                threshold = thresholds.get("critical", 90)
            elif metric.value >= thresholds.get("warning", 80):
                alert_level = AlertLevel.WARNING
                threshold = thresholds.get("warning", 80)

        elif metric.name == "memory_percent":
            if metric.value >= thresholds.get("critical", 95):
                alert_level = AlertLevel.CRITICAL
                threshold = thresholds.get("critical", 95)
            elif metric.value >= thresholds.get("warning", 85):
                alert_level = AlertLevel.WARNING
                threshold = thresholds.get("warning", 85)

        elif metric.name == "disk_percent":
            if metric.value >= thresholds.get("critical", 95):
                alert_level = AlertLevel.CRITICAL
                threshold = thresholds.get("critical", 95)
            elif metric.value >= thresholds.get("warning", 85):
                alert_level = AlertLevel.WARNING
                threshold = thresholds.get("warning", 85)

        elif metric.name == "api_response_time":
            if metric.value >= thresholds.get("response_time_critical", 5000):
                alert_level = AlertLevel.CRITICAL
                threshold = thresholds.get("response_time_critical", 5000)
            elif metric.value >= thresholds.get("response_time_warning", 1000):
                alert_level = AlertLevel.WARNING
                threshold = thresholds.get("response_time_warning", 1000)

        elif metric.name == "api_success_rate":
            if metric.value <= thresholds.get("success_rate_critical", 90):
                alert_level = AlertLevel.CRITICAL
                threshold = thresholds.get("success_rate_critical", 90)
            elif metric.value <= thresholds.get("success_rate_warning", 95):
                alert_level = AlertLevel.WARNING
                threshold = thresholds.get("success_rate_warning", 95)

        # 创建告警
        if alert_level:
            await self._create_alert(
                monitor_id=monitor_id,
                alert_level=alert_level,
                message=f"{config.name} - {metric.name} {metric.value}{metric.unit} 超过阈值 {threshold}",
                metric_name=metric.name,
                metric_value=metric.value,
                threshold=threshold,
            )

    async def _create_alert(
        self,
        monitor_id: str,
        alert_level: AlertLevel,
        message: str,
        metric_name: str,
        metric_value: float,
        threshold: float,
    ) -> None:
        """创建告警"""
        # 检查是否有相同未解决的告警
        existing_alerts = await self.get_alerts(monitor_id=monitor_id, unresolved=True)

        for alert in existing_alerts:
            if (
                alert.metric_name == metric_name
                and alert.alert_level == alert_level
                and abs(alert.metric_value - metric_value) < 0.1
                and (datetime.now() - alert.timestamp) < timedelta(minutes=5)
            ):
                # 相同告警在5分钟内已经存在，不重复创建
                return

        alert_id = f"alert_{uuid.uuid4().hex[:8]}"

        alert = MonitorAlert(
            alert_id=alert_id,
            monitor_id=monitor_id,
            alert_level=alert_level,
            message=message,
            metric_name=metric_name,
            metric_value=metric_value,
            threshold=threshold,
        )

        async with self._lock:
            self.alerts[alert_id] = alert
            self.stats["total_alerts"] += 1
            self.stats["active_alerts"] += 1

        logger.log(
            (
                logging.CRITICAL
                if alert_level == AlertLevel.CRITICAL
                else (
                    logging.ERROR
                    if alert_level == AlertLevel.ERROR
                    else logging.WARNING if alert_level == AlertLevel.WARNING else logging.INFO
                )
            ),
            f"监控告警 [{alert_level.value}]: {message}",
        )

    async def _cleanup_old_data(self) -> None:
        """清理旧数据"""
        current_time = datetime.now()

        async with self._lock:
            # 清理旧指标（保留7天）
            cutoff_time = current_time - timedelta(days=7)
            self.metrics_history = [m for m in self.metrics_history if m.timestamp > cutoff_time]

            # 清理旧系统指标（保留3天）
            cutoff_time = current_time - timedelta(days=3)
            self.system_metrics = [m for m in self.system_metrics if m.timestamp > cutoff_time]

            # 清理已解决的旧告警（保留30天）
            cutoff_time = current_time - timedelta(days=30)
            self.alert_history = [
                a for a in self.alert_history if not a.resolved or a.timestamp > cutoff_time
            ]

    async def _save_state(self) -> None:
        """保存状态"""
        # 在实际系统中，这里应该保存到数据库
        logger.info("保存监控管理器状态")


# 使用示例
async def example_usage():
    """监控管理器使用示例"""

    # 创建监控管理器
    monitor_manager = MonitorManager()
    await monitor_manager.initialize()

    try:
        # 等待一些数据收集
        await asyncio.sleep(5)

        # 获取系统摘要
        system_summary = await monitor_manager.get_system_summary()
        print("系统摘要:")
        print(f"  CPU: {system_summary.get('cpu', {}).get('percent', 0)}%")
        print(f"  内存: {system_summary.get('memory', {}).get('percent', 0)}%")
        print(f"  磁盘: {system_summary.get('disk', {}).get('percent', 0)}%")

        # 获取服务健康
        service_health = await monitor_manager.get_service_health()
        print(f"服务健康: {len(service_health)} 个服务")

        for name, health in service_health.items():
            print(f"  {name}: {health.status.value} (响应时间: {health.response_time}ms)")

        # 获取活跃告警
        active_alerts = await monitor_manager.get_alerts(unresolved=True)
        print(f"活跃告警: {len(active_alerts)} 个")

        for alert in active_alerts[:3]:  # 显示前3个
            print(f"  [{alert.alert_level.value}] {alert.message}")

        # 获取仪表板数据
        dashboard = await monitor_manager.get_dashboard_data()
        print(
            f"仪表板数据: 系统健康={dashboard.get('system', {}).get('cpu', {}).get('status', 'unknown')}"
        )

        # 获取统计
        stats = await monitor_manager.get_statistics()
        print(f"监控统计: {stats}")

        # 手动收集一个业务指标
        await monitor_manager.collect_metric(
            monitor_id="custom_business",
            name="trade_success_rate",
            value=98.5,
            unit="%",
            tags={"strategy": "moving_average"},
        )

        # 获取指标统计
        if "custom_business" in monitor_manager.metrics:
            metric_stats = await monitor_manager.get_metric_statistics(
                monitor_id="custom_business", name="trade_success_rate"
            )
            print(f"交易成功率统计: 平均值={metric_stats.get('mean', 0):.1f}%")

    finally:
        await monitor_manager.cleanup()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
