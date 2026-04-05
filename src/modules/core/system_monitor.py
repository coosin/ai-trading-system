"""
系统监控模块

提供系统资源监控、性能分析和健康检查功能
"""

import asyncio
import logging
import os
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

import psutil

logger = logging.getLogger(__name__)


@dataclass
class SystemMetrics:
    """系统指标"""
    timestamp: datetime = field(default_factory=datetime.now)
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used: float = 0.0
    memory_total: float = 0.0
    disk_percent: float = 0.0
    disk_used: float = 0.0
    disk_total: float = 0.0
    network_bytes_sent: int = 0
    network_bytes_recv: int = 0
    process_count: int = 0
    load_average: tuple = (0.0, 0.0, 0.0)


@dataclass
class HealthStatus:
    """健康状态"""
    component: str
    status: str  # healthy, warning, critical
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)


class SystemMonitor:
    """系统监控器"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        self._metrics_history: List[SystemMetrics] = []
        self._max_history = self.config.get("max_history", 1000)
        
        self._health_checks: Dict[str, Callable] = {}
        self._health_status: Dict[str, HealthStatus] = {}
        
        self._alerts: List[Dict[str, Any]] = []
        self._alert_callbacks: List[Callable] = []
        
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        self._thresholds = {
            "cpu_warning": self.config.get("cpu_warning", 80),
            "cpu_critical": self.config.get("cpu_critical", 95),
            "memory_warning": self.config.get("memory_warning", 80),
            "memory_critical": self.config.get("memory_critical", 95),
            "disk_warning": self.config.get("disk_warning", 80),
            "disk_critical": self.config.get("disk_critical", 95),
        }
    
    async def initialize(self) -> bool:
        """初始化系统监控器"""
        logger.info("系统监控器初始化完成")
        return True
    
    async def start(self) -> None:
        """启动监控"""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("系统监控器已启动")
    
    async def stop(self) -> None:
        """停止监控"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("系统监控器已停止")
    
    async def _monitor_loop(self) -> None:
        """监控循环"""
        interval = self.config.get("monitor_interval", 60)
        
        while self._running:
            try:
                metrics = await self.collect_metrics()
                self._metrics_history.append(metrics)
                
                if len(self._metrics_history) > self._max_history:
                    self._metrics_history = self._metrics_history[-self._max_history:]
                
                await self._check_thresholds(metrics)
                await self._run_health_checks()
                
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
            
            await asyncio.sleep(interval)
    
    async def collect_metrics(self) -> SystemMetrics:
        """收集系统指标"""
        metrics = SystemMetrics()
        
        try:
            metrics.cpu_percent = psutil.cpu_percent(interval=1)
            
            memory = psutil.virtual_memory()
            metrics.memory_percent = memory.percent
            metrics.memory_used = memory.used / (1024 ** 3)
            metrics.memory_total = memory.total / (1024 ** 3)
            
            disk = psutil.disk_usage('/')
            metrics.disk_percent = disk.percent
            metrics.disk_used = disk.used / (1024 ** 3)
            metrics.disk_total = disk.total / (1024 ** 3)
            
            net = psutil.net_io_counters()
            metrics.network_bytes_sent = net.bytes_sent
            metrics.network_bytes_recv = net.bytes_recv
            
            metrics.process_count = len(psutil.pids())
            
            if hasattr(os, 'getloadavg'):
                metrics.load_average = os.getloadavg()
            
        except Exception as e:
            logger.warning(f"收集系统指标失败: {e}")
        
        return metrics
    
    async def _check_thresholds(self, metrics: SystemMetrics) -> None:
        """检查阈值"""
        alerts = []
        
        if metrics.cpu_percent >= self._thresholds["cpu_critical"]:
            alerts.append({
                "type": "cpu",
                "level": "critical",
                "message": f"CPU使用率过高: {metrics.cpu_percent:.1f}%"
            })
        elif metrics.cpu_percent >= self._thresholds["cpu_warning"]:
            alerts.append({
                "type": "cpu",
                "level": "warning",
                "message": f"CPU使用率警告: {metrics.cpu_percent:.1f}%"
            })
        
        if metrics.memory_percent >= self._thresholds["memory_critical"]:
            alerts.append({
                "type": "memory",
                "level": "critical",
                "message": f"内存使用率过高: {metrics.memory_percent:.1f}%"
            })
        elif metrics.memory_percent >= self._thresholds["memory_warning"]:
            alerts.append({
                "type": "memory",
                "level": "warning",
                "message": f"内存使用率警告: {metrics.memory_percent:.1f}%"
            })
        
        if metrics.disk_percent >= self._thresholds["disk_critical"]:
            alerts.append({
                "type": "disk",
                "level": "critical",
                "message": f"磁盘使用率过高: {metrics.disk_percent:.1f}%"
            })
        elif metrics.disk_percent >= self._thresholds["disk_warning"]:
            alerts.append({
                "type": "disk",
                "level": "warning",
                "message": f"磁盘使用率警告: {metrics.disk_percent:.1f}%"
            })
        
        for alert in alerts:
            await self._trigger_alert(alert)
    
    async def _trigger_alert(self, alert: Dict[str, Any]) -> None:
        """触发告警"""
        alert["timestamp"] = datetime.now().isoformat()
        self._alerts.append(alert)
        
        logger.warning(f"系统告警: {alert['message']}")
        
        for callback in self._alert_callbacks:
            try:
                await callback(alert) if asyncio.iscoroutinefunction(callback) else callback(alert)
            except Exception as e:
                logger.error(f"告警回调执行失败: {e}")
    
    def register_health_check(self, name: str, check_func: Callable) -> None:
        """注册健康检查"""
        self._health_checks[name] = check_func
        logger.info(f"注册健康检查: {name}")
    
    async def _run_health_checks(self) -> None:
        """运行健康检查"""
        for name, check_func in self._health_checks.items():
            try:
                if asyncio.iscoroutinefunction(check_func):
                    result = await check_func()
                else:
                    result = check_func()
                
                if isinstance(result, dict):
                    self._health_status[name] = HealthStatus(
                        component=name,
                        status=result.get("status", "healthy"),
                        message=result.get("message", ""),
                        details=result.get("details", {})
                    )
                elif isinstance(result, bool):
                    self._health_status[name] = HealthStatus(
                        component=name,
                        status="healthy" if result else "critical",
                        message="OK" if result else "Check failed"
                    )
            except Exception as e:
                self._health_status[name] = HealthStatus(
                    component=name,
                    status="critical",
                    message=str(e)
                )
    
    def add_alert_callback(self, callback: Callable) -> None:
        """添加告警回调"""
        self._alert_callbacks.append(callback)
    
    def get_current_metrics(self) -> Optional[SystemMetrics]:
        """获取当前指标"""
        if self._metrics_history:
            return self._metrics_history[-1]
        return None
    
    def get_metrics_history(self, limit: int = 100) -> List[SystemMetrics]:
        """获取历史指标"""
        return self._metrics_history[-limit:]
    
    def get_health_status(self) -> Dict[str, HealthStatus]:
        """获取健康状态"""
        return self._health_status
    
    def get_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取告警列表"""
        return self._alerts[-limit:]
    
    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        return {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_count": psutil.cpu_count(),
            "cpu_freq": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
            "memory_total": psutil.virtual_memory().total / (1024 ** 3),
            "disk_total": psutil.disk_usage('/').total / (1024 ** 3),
            "hostname": platform.node(),
        }
