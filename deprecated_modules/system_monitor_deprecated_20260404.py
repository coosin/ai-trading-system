from __future__ import annotations

import asyncio
import logging
import time
import psutil
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Callable

logger = logging.getLogger(__name__)


class SystemStatus(Enum):
    """系统状态"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    DOWN = "down"


class ComponentType(Enum):
    """组件类型"""
    DATABASE = "database"
    REDIS = "redis"
    EXCHANGE_API = "exchange_api"
    ML_MODEL = "ml_model"
    LARGE_MODEL = "large_model"
    STRATEGY = "strategy"
    EXECUTION = "execution"
    MONITORING = "monitoring"
    API_SERVER = "api_server"


@dataclass
class ComponentStatus:
    """组件状态"""
    component: ComponentType
    status: SystemStatus
    timestamp: float
    message: str
    details: Dict[str, Any]


@dataclass
class SystemHealth:
    """系统健康状态"""
    timestamp: float
    overall_status: SystemStatus
    component_statuses: List[ComponentStatus]
    cpu_usage: float
    cpu_details: Dict[str, Any]
    memory_usage: float
    memory_details: Dict[str, Any]
    disk_usage: float
    disk_details: Dict[str, Any]
    network_status: Dict[str, Any]
    network_details: Dict[str, Any]
    business_metrics: Dict[str, Any]


class PerformanceAnalyzer:
    """性能分析器"""

    def __init__(self):
        """初始化性能分析器"""
        self.performance_data = []
        self.max_data_points = 1000
        self.start_times = {}

    def start_measurement(self, name: str):
        """开始性能测量

        Args:
            name: 测量名称
        """
        self.start_times[name] = time.time()

    def end_measurement(self, name: str) -> float:
        """结束性能测量

        Args:
            name: 测量名称

        Returns:
            float: 执行时间（秒）
        """
        if name in self.start_times:
            duration = time.time() - self.start_times[name]
            del self.start_times[name]
            
            # 记录性能数据
            self.performance_data.append({
                "timestamp": time.time(),
                "name": name,
                "duration": duration
            })
            
            # 限制数据点数量
            if len(self.performance_data) > self.max_data_points:
                self.performance_data = self.performance_data[-self.max_data_points:]
            
            return duration
        return 0.0

    def get_performance_stats(self, name: str = None) -> Dict[str, Any]:
        """获取性能统计信息

        Args:
            name: 测量名称，None表示所有测量

        Returns:
            Dict[str, Any]: 性能统计信息
        """
        if name:
            data = [d for d in self.performance_data if d["name"] == name]
        else:
            data = self.performance_data
        
        if not data:
            return {}
        
        durations = [d["duration"] for d in data]
        stats = {
            "count": len(durations),
            "average": sum(durations) / len(durations),
            "min": min(durations),
            "max": max(durations),
            "total": sum(durations)
        }
        
        return stats

    def get_performance_history(self, name: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取性能历史数据

        Args:
            name: 测量名称，None表示所有测量
            limit: 返回的历史记录数量

        Returns:
            List[Dict[str, Any]]: 性能历史数据
        """
        if name:
            data = [d for d in self.performance_data if d["name"] == name]
        else:
            data = self.performance_data
        
        return data[-limit:]

    def clear_performance_data(self):
        """清除性能数据"""
        self.performance_data.clear()


class SystemMonitor:
    """系统监控和故障恢复模块"""

    def __init__(self, config: Dict[str, Any]):
        """初始化系统监控

        Args:
            config: 配置信息
        """
        self.config = config
        self.enabled = False
        self.health_history = []
        self.failure_count = {}
        self.recovery_attempts = {}
        self.monitoring_interval = config.get("monitoring_interval", 10)  # 秒
        self.max_health_history = config.get("max_health_history", 100)
        self.failure_threshold = config.get("failure_threshold", 3)
        self.recovery_timeout = config.get("recovery_timeout", 60)  # 秒
        self.component_checks = {}
        self.recovery_handlers = {}
        self.alerts = []
        self.alert_thresholds = config.get("alert_thresholds", {
            "cpu": 80,
            "memory": 85,
            "disk": 90,
            "network_latency": 500
        })
        self.alert_history = []
        self.max_alert_history = config.get("max_alert_history", 100)
        self.performance_analyzer = PerformanceAnalyzer()

    async def initialize(self) -> bool:
        """初始化系统监控

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 注册组件检查函数
            self._register_component_checks()
            
            # 注册恢复处理函数
            self._register_recovery_handlers()
            
            # 启动监控循环
            asyncio.create_task(self._monitoring_loop())
            
            self.enabled = True
            logger.info("SystemMonitor initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize SystemMonitor: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭系统监控

        Returns:
            bool: 关闭是否成功
        """
        try:
            self.enabled = False
            self.health_history.clear()
            self.failure_count.clear()
            self.recovery_attempts.clear()
            logger.info("SystemMonitor shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown SystemMonitor: {e}")
            return False

    def _register_component_checks(self):
        """注册组件检查函数"""
        # 数据库检查
        async def check_database():
            try:
                # 这里应该实现数据库连接检查
                return SystemStatus.HEALTHY, "Database connection healthy"
            except Exception as e:
                return SystemStatus.CRITICAL, f"Database connection failed: {e}"
        
        # Redis检查
        async def check_redis():
            try:
                # 这里应该实现Redis连接检查
                return SystemStatus.HEALTHY, "Redis connection healthy"
            except Exception as e:
                return SystemStatus.CRITICAL, f"Redis connection failed: {e}"
        
        # 交易所API检查
        async def check_exchange_api():
            try:
                # 这里应该实现交易所API检查
                return SystemStatus.HEALTHY, "Exchange API healthy"
            except Exception as e:
                return SystemStatus.WARNING, f"Exchange API issue: {e}"
        
        # 机器学习模型检查
        async def check_ml_model():
            try:
                # 这里应该实现机器学习模型检查
                return SystemStatus.HEALTHY, "ML models healthy"
            except Exception as e:
                return SystemStatus.WARNING, f"ML model issue: {e}"
        
        # 大模型检查
        async def check_large_model():
            try:
                # 这里应该实现大模型检查
                return SystemStatus.HEALTHY, "Large models healthy"
            except Exception as e:
                return SystemStatus.WARNING, f"Large model issue: {e}"
        
        self.component_checks = {
            ComponentType.DATABASE: check_database,
            ComponentType.REDIS: check_redis,
            ComponentType.EXCHANGE_API: check_exchange_api,
            ComponentType.ML_MODEL: check_ml_model,
            ComponentType.LARGE_MODEL: check_large_model
        }

    def _register_recovery_handlers(self):
        """注册恢复处理函数"""
        # 数据库恢复
        async def recover_database():
            try:
                # 这里应该实现数据库恢复逻辑
                logger.info("Attempting to recover database connection")
                # 模拟恢复
                await asyncio.sleep(2)
                logger.info("Database connection recovered")
                return True
            except Exception as e:
                logger.error(f"Failed to recover database: {e}")
                return False
        
        # Redis恢复
        async def recover_redis():
            try:
                # 这里应该实现Redis恢复逻辑
                logger.info("Attempting to recover Redis connection")
                # 模拟恢复
                await asyncio.sleep(2)
                logger.info("Redis connection recovered")
                return True
            except Exception as e:
                logger.error(f"Failed to recover Redis: {e}")
                return False
        
        # 交易所API恢复
        async def recover_exchange_api():
            try:
                # 这里应该实现交易所API恢复逻辑
                logger.info("Attempting to recover exchange API connection")
                # 模拟恢复
                await asyncio.sleep(5)
                logger.info("Exchange API connection recovered")
                return True
            except Exception as e:
                logger.error(f"Failed to recover exchange API: {e}")
                return False
        
        self.recovery_handlers = {
            ComponentType.DATABASE: recover_database,
            ComponentType.REDIS: recover_redis,
            ComponentType.EXCHANGE_API: recover_exchange_api
        }

    async def _monitoring_loop(self):
        """监控循环"""
        while self.enabled:
            try:
                # 检查系统健康状态
                health = await self.check_system_health()
                self.health_history.append(health)
                
                # 限制历史记录大小
                if len(self.health_history) > self.max_health_history:
                    self.health_history = self.health_history[-self.max_health_history:]
                
                # 检查是否需要生成告警
                await self._check_alerts(health)
                
                # 检查故障并尝试恢复
                await self._check_failures_and_recover(health)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            await asyncio.sleep(self.monitoring_interval)

    async def check_system_health(self) -> SystemHealth:
        """检查系统健康状态

        Returns:
            SystemHealth: 系统健康状态
        """
        try:
            # 检查系统资源
            cpu_usage = psutil.cpu_percent(interval=0.1)
            cpu_details = {
                "per_cpu_usage": psutil.cpu_percent(interval=0.1, percpu=True),
                "cpu_count": psutil.cpu_count(),
                "cpu_count_logical": psutil.cpu_count(logical=True),
                "cpu_freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else {}
            }
            
            memory = psutil.virtual_memory()
            memory_usage = memory.percent
            memory_details = {
                "total": memory.total,
                "available": memory.available,
                "used": memory.used,
                "free": memory.free,
                "active": getattr(memory, 'active', 0),
                "inactive": getattr(memory, 'inactive', 0)
            }
            
            disk = psutil.disk_usage('/')
            disk_usage = disk.percent
            disk_details = {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "partitions": [{
                    "device": p.device,
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "opts": p.opts
                } for p in psutil.disk_partitions()]
            }
            
            # 检查网络状态
            network_status = await self._check_network_status()
            network_details = {
                "interfaces": dict(psutil.net_if_stats()),
                "connections": len(psutil.net_connections()),
                "io_counters": psutil.net_io_counters()._asdict()
            }
            
            # 检查组件状态
            component_statuses = await self._check_components()
            
            # 业务级别的性能指标
            business_metrics = await self._get_business_metrics()
            
            # 确定整体状态
            overall_status = self._determine_overall_status(component_statuses)
            
            return SystemHealth(
                timestamp=time.time(),
                overall_status=overall_status,
                component_statuses=component_statuses,
                cpu_usage=cpu_usage,
                cpu_details=cpu_details,
                memory_usage=memory_usage,
                memory_details=memory_details,
                disk_usage=disk_usage,
                disk_details=disk_details,
                network_status=network_status,
                network_details=network_details,
                business_metrics=business_metrics
            )
        except Exception as e:
            logger.error(f"Error checking system health: {e}")
            return SystemHealth(
                timestamp=time.time(),
                overall_status=SystemStatus.CRITICAL,
                component_statuses=[],
                cpu_usage=0,
                cpu_details={},
                memory_usage=0,
                memory_details={},
                disk_usage=0,
                disk_details={},
                network_status={},
                network_details={},
                business_metrics={}
            )

    async def _check_network_status(self) -> Dict[str, Any]:
        """检查网络状态

        Returns:
            Dict[str, Any]: 网络状态
        """
        try:
            # 这里应该实现网络状态检查
            return {
                "status": "healthy",
                "latency": 100,
                "bandwidth": "100Mbps"
            }
        except Exception as e:
            logger.error(f"Error checking network status: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def _get_business_metrics(self) -> Dict[str, Any]:
        """获取业务级别的性能指标

        Returns:
            Dict[str, Any]: 业务指标
        """
        try:
            # 业务级别的性能指标
            business_metrics = {
                "strategy_execution_time": 0.0,
                "order_response_time": 0.0,
                "market_data_update_time": 0.0,
                "risk_analysis_time": 0.0,
                "active_strategies": 0,
                "active_orders": 0,
                "completed_trades": 0,
                "error_rate": 0.0
            }
            
            # 这里可以从各个模块收集实际的业务指标
            # 例如从策略管理器获取活跃策略数量
            # 从交易执行器获取订单状态
            # 从市场分析模块获取数据更新时间
            
            return business_metrics
        except Exception as e:
            logger.error(f"Error getting business metrics: {e}")
            return {}

    async def _generate_alert(self, alert_type: str, severity: str, message: str, details: Dict[str, Any]):
        """生成告警

        Args:
            alert_type: 告警类型
            severity: 严重程度
            message: 告警消息
            details: 详细信息
        """
        alert = {
            "timestamp": time.time(),
            "type": alert_type,
            "severity": severity,
            "message": message,
            "details": details
        }
        self.alerts.append(alert)
        self.alert_history.append(alert)
        
        # 限制告警历史大小
        if len(self.alert_history) > self.max_alert_history:
            self.alert_history = self.alert_history[-self.max_alert_history:]
        
        logger.warning(f"Alert: {severity} - {message}")

    async def _check_alerts(self, health: SystemHealth):
        """检查是否需要生成告警

        Args:
            health: 系统健康状态
        """
        # 检查CPU使用率
        if health.cpu_usage > self.alert_thresholds["cpu"]:
            await self._generate_alert(
                "cpu_usage",
                "warning",
                f"CPU usage is high: {health.cpu_usage:.2f}%",
                {"cpu_usage": health.cpu_usage}
            )
        
        # 检查内存使用率
        if health.memory_usage > self.alert_thresholds["memory"]:
            await self._generate_alert(
                "memory_usage",
                "warning",
                f"Memory usage is high: {health.memory_usage:.2f}%",
                {"memory_usage": health.memory_usage}
            )
        
        # 检查磁盘使用率
        if health.disk_usage > self.alert_thresholds["disk"]:
            await self._generate_alert(
                "disk_usage",
                "warning",
                f"Disk usage is high: {health.disk_usage:.2f}%",
                {"disk_usage": health.disk_usage}
            )
        
        # 检查网络延迟
        network_latency = health.network_status.get("latency", 0)
        if network_latency > self.alert_thresholds["network_latency"]:
            await self._generate_alert(
                "network_latency",
                "warning",
                f"Network latency is high: {network_latency}ms",
                {"network_latency": network_latency}
            )
        
        # 检查组件状态
        for component_status in health.component_statuses:
            if component_status.status == SystemStatus.CRITICAL:
                await self._generate_alert(
                    "component_failure",
                    "critical",
                    f"Component {component_status.component.value} is critical: {component_status.message}",
                    {
                        "component": component_status.component.value,
                        "message": component_status.message
                    }
                )
            elif component_status.status == SystemStatus.WARNING:
                await self._generate_alert(
                    "component_warning",
                    "warning",
                    f"Component {component_status.component.value} has warning: {component_status.message}",
                    {
                        "component": component_status.component.value,
                        "message": component_status.message
                    }
                )

    async def _check_components(self) -> List[ComponentStatus]:
        """检查组件状态

        Returns:
            List[ComponentStatus]: 组件状态列表
        """
        component_statuses = []
        
        for component, check_func in self.component_checks.items():
            try:
                status, message = await check_func()
                component_statuses.append(ComponentStatus(
                    component=component,
                    status=status,
                    timestamp=time.time(),
                    message=message,
                    details={}
                ))
            except Exception as e:
                logger.error(f"Error checking component {component.value}: {e}")
                component_statuses.append(ComponentStatus(
                    component=component,
                    status=SystemStatus.CRITICAL,
                    timestamp=time.time(),
                    message=f"Error checking component: {e}",
                    details={}
                ))
        
        return component_statuses

    def _determine_overall_status(self, component_statuses: List[ComponentStatus]) -> SystemStatus:
        """确定整体状态

        Args:
            component_statuses: 组件状态列表

        Returns:
            SystemStatus: 整体状态
        """
        if not component_statuses:
            return SystemStatus.WARNING
        
        # 检查是否有关键组件故障
        for status in component_statuses:
            if status.status == SystemStatus.CRITICAL:
                return SystemStatus.CRITICAL
            elif status.status == SystemStatus.WARNING:
                return SystemStatus.WARNING
        
        return SystemStatus.HEALTHY

    async def _check_failures_and_recover(self, health: SystemHealth):
        """检查故障并尝试恢复

        Args:
            health: 系统健康状态
        """
        for component_status in health.component_statuses:
            component = component_status.component
            status = component_status.status
            
            # 检查是否需要恢复
            if status in [SystemStatus.CRITICAL, SystemStatus.DOWN]:
                # 增加故障计数
                self.failure_count[component] = self.failure_count.get(component, 0) + 1
                
                # 检查是否达到故障阈值
                if self.failure_count[component] >= self.failure_threshold:
                    # 检查是否可以恢复
                    if component in self.recovery_handlers:
                        # 检查是否在恢复超时内
                        last_attempt = self.recovery_attempts.get(component, 0)
                        if time.time() - last_attempt > self.recovery_timeout:
                            # 尝试恢复
                            logger.warning(f"Attempting to recover component: {component.value}")
                            self.recovery_attempts[component] = time.time()
                            
                            # 执行恢复
                            recovered = await self.recovery_handlers[component]()
                            if recovered:
                                # 恢复成功，重置故障计数
                                self.failure_count[component] = 0
                                logger.info(f"Component {component.value} recovered successfully")
                            else:
                                logger.error(f"Failed to recover component: {component.value}")

    def get_system_health(self) -> Optional[SystemHealth]:
        """获取当前系统健康状态

        Returns:
            Optional[SystemHealth]: 系统健康状态
        """
        if self.health_history:
            return self.health_history[-1]
        return None

    def get_health_history(self, limit: int = 10) -> List[SystemHealth]:
        """获取健康历史

        Args:
            limit: 返回的历史记录数量

        Returns:
            List[SystemHealth]: 健康历史
        """
        return self.health_history[-limit:]

    def is_healthy(self) -> bool:
        """检查系统是否健康

        Returns:
            bool: 健康状态
        """
        health = self.get_system_health()
        return health and health.overall_status in [SystemStatus.HEALTHY, SystemStatus.WARNING]

    async def add_custom_check(self, component: ComponentType, check_func: Callable[[], Awaitable[Tuple[SystemStatus, str]]]):
        """添加自定义检查函数

        Args:
            component: 组件类型
            check_func: 检查函数
        """
        self.component_checks[component] = check_func

    async def add_custom_recovery(self, component: ComponentType, recovery_func: Callable[[], Awaitable[bool]]):
        """添加自定义恢复函数

        Args:
            component: 组件类型
            recovery_func: 恢复函数
        """
        self.recovery_handlers[component] = recovery_func

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """获取当前活跃的告警

        Returns:
            List[Dict[str, Any]]: 活跃告警列表
        """
        return self.alerts

    def get_alert_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取告警历史

        Args:
            limit: 返回的历史记录数量

        Returns:
            List[Dict[str, Any]]: 告警历史
        """
        return self.alert_history[-limit:]

    def clear_alerts(self):
        """清除所有活跃告警"""
        self.alerts.clear()

    def set_alert_threshold(self, alert_type: str, threshold: float):
        """设置告警阈值

        Args:
            alert_type: 告警类型
            threshold: 阈值
        """
        if alert_type in self.alert_thresholds:
            self.alert_thresholds[alert_type] = threshold
            logger.info(f"Set alert threshold for {alert_type} to {threshold}")

    def start_performance_measurement(self, name: str):
        """开始性能测量

        Args:
            name: 测量名称
        """
        self.performance_analyzer.start_measurement(name)

    def end_performance_measurement(self, name: str) -> float:
        """结束性能测量

        Args:
            name: 测量名称

        Returns:
            float: 执行时间（秒）
        """
        return self.performance_analyzer.end_measurement(name)

    def get_performance_stats(self, name: str = None) -> Dict[str, Any]:
        """获取性能统计信息

        Args:
            name: 测量名称，None表示所有测量

        Returns:
            Dict[str, Any]: 性能统计信息
        """
        return self.performance_analyzer.get_performance_stats(name)

    def get_performance_history(self, name: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取性能历史数据

        Args:
            name: 测量名称，None表示所有测量
            limit: 返回的历史记录数量

        Returns:
            List[Dict[str, Any]]: 性能历史数据
        """
        return self.performance_analyzer.get_performance_history(name, limit)

    def clear_performance_data(self):
        """清除性能数据"""
        self.performance_analyzer.clear_performance_data()
