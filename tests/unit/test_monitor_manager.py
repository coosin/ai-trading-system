"""
MonitorManager单元测试
"""

import asyncio
from datetime import datetime, timedelta

import pytest

try:
    from src.modules.core.monitor_manager import (  # type: ignore
        AlertLevel,
        MonitorAlert,
        MonitorConfig,
        MonitorManager,
        MonitorMetric,
        MonitorType,
        ServiceHealth,
        ServiceStatus,
        SystemMetrics,
    )
except ModuleNotFoundError:
    pytest.skip("monitor_manager 模块已迁移/移除：跳过旧测试", allow_module_level=True)


class TestMonitorManager:
    """MonitorManager测试类"""

    @pytest.fixture
    async def monitor_manager(self):
        """创建测试用的监控管理器"""
        manager = MonitorManager()
        await manager.initialize()
        yield manager
        await manager.cleanup()

    @pytest.fixture
    def sample_monitor_config(self):
        """创建示例监控配置"""
        return MonitorConfig(
            monitor_id="test_monitor_1",
            name="测试监控",
            monitor_type=MonitorType.SYSTEM,
            alert_thresholds={"warning": 80.0, "critical": 90.0},
            tags=["test", "system"],
        )

    @pytest.mark.asyncio
    async def test_initialization(self, monitor_manager):
        """测试初始化"""
        assert monitor_manager is not None
        assert len(monitor_manager.monitor_configs) > 0  # 应该有默认监控
        assert len(monitor_manager.metrics) > 0  # 应该有默认监控的指标存储
        assert monitor_manager.stats["total_checks"] >= 0

    @pytest.mark.asyncio
    async def test_monitor_config_properties(self, sample_monitor_config):
        """测试监控配置属性"""
        config = sample_monitor_config

        assert config.monitor_id == "test_monitor_1"
        assert config.name == "测试监控"
        assert config.monitor_type == MonitorType.SYSTEM
        assert config.enabled is True
        assert config.check_interval == 60
        assert config.alert_thresholds["warning"] == 80.0
        assert config.alert_thresholds["critical"] == 90.0
        assert config.tags == ["test", "system"]
        assert config.created_at is not None
        assert config.updated_at is not None

        # 测试转换为字典
        config_dict = config.to_dict()
        assert config_dict["monitor_id"] == "test_monitor_1"
        assert config_dict["name"] == "测试监控"
        assert config_dict["monitor_type"] == "system"
        assert config_dict["enabled"] is True
        assert "created_at" in config_dict
        assert "updated_at" in config_dict

    @pytest.mark.asyncio
    async def test_register_monitor(self, monitor_manager, sample_monitor_config):
        """测试注册监控"""
        success = await monitor_manager.register_monitor(sample_monitor_config)

        assert success is True
        assert sample_monitor_config.monitor_id in monitor_manager.monitor_configs
        assert sample_monitor_config.monitor_id in monitor_manager.metrics

        # 重复注册应该失败
        success_again = await monitor_manager.register_monitor(sample_monitor_config)
        assert success_again is False

    @pytest.mark.asyncio
    async def test_enable_disable_monitor(self, monitor_manager, sample_monitor_config):
        """测试启用禁用监控"""
        # 先注册监控
        await monitor_manager.register_monitor(sample_monitor_config)

        # 禁用监控
        disabled = await monitor_manager.disable_monitor(sample_monitor_config.monitor_id)
        assert disabled is True
        assert monitor_manager.monitor_configs[sample_monitor_config.monitor_id].enabled is False

        # 启用监控
        enabled = await monitor_manager.enable_monitor(sample_monitor_config.monitor_id)
        assert enabled is True
        assert monitor_manager.monitor_configs[sample_monitor_config.monitor_id].enabled is True

    @pytest.mark.asyncio
    async def test_collect_metric(self, monitor_manager, sample_monitor_config):
        """测试收集指标"""
        # 先注册监控
        await monitor_manager.register_monitor(sample_monitor_config)

        # 收集指标
        success = await monitor_manager.collect_metric(
            monitor_id=sample_monitor_config.monitor_id,
            name="test_metric",
            value=75.5,
            unit="%",
            tags={"source": "test"},
        )

        assert success is True

        # 检查指标是否保存
        metrics = monitor_manager.metrics[sample_monitor_config.monitor_id]
        assert len(metrics) > 0

        metric = metrics[-1]
        assert metric.monitor_id == sample_monitor_config.monitor_id
        assert metric.name == "test_metric"
        assert metric.value == 75.5
        assert metric.unit == "%"
        assert metric.tags["source"] == "test"

    @pytest.mark.asyncio
    async def test_collect_metric_for_nonexistent_monitor(self, monitor_manager):
        """测试为不存在的监控收集指标"""
        success = await monitor_manager.collect_metric(
            monitor_id="nonexistent_monitor", name="test_metric", value=50.0
        )

        assert success is False

    @pytest.mark.asyncio
    async def test_get_metrics(self, monitor_manager, sample_monitor_config):
        """测试获取指标"""
        # 注册监控并收集指标
        await monitor_manager.register_monitor(sample_monitor_config)

        for i in range(5):
            await monitor_manager.collect_metric(
                monitor_id=sample_monitor_config.monitor_id, name=f"metric_{i}", value=10.0 * i
            )

        # 获取所有指标
        all_metrics = await monitor_manager.get_metrics()
        assert len(all_metrics) >= 5

        # 按监控ID过滤
        monitor_metrics = await monitor_manager.get_metrics(
            monitor_id=sample_monitor_config.monitor_id
        )
        assert len(monitor_metrics) >= 5
        assert all(m.monitor_id == sample_monitor_config.monitor_id for m in monitor_metrics)

        # 按名称过滤
        specific_metrics = await monitor_manager.get_metrics(
            monitor_id=sample_monitor_config.monitor_id, name="metric_2"
        )
        assert len(specific_metrics) >= 1
        assert all(m.name == "metric_2" for m in specific_metrics)

        # 按时间过滤
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)

        recent_metrics = await monitor_manager.get_metrics(start_time=hour_ago, end_time=now)
        assert len(recent_metrics) >= 5

        # 限制数量
        limited_metrics = await monitor_manager.get_metrics(limit=2)
        assert len(limited_metrics) <= 2

    @pytest.mark.asyncio
    async def test_get_metric_statistics(self, monitor_manager, sample_monitor_config):
        """测试获取指标统计"""
        # 注册监控并收集指标
        await monitor_manager.register_monitor(sample_monitor_config)

        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        for value in values:
            await monitor_manager.collect_metric(
                monitor_id=sample_monitor_config.monitor_id, name="test_stat_metric", value=value
            )

        # 获取统计
        stats = await monitor_manager.get_metric_statistics(
            monitor_id=sample_monitor_config.monitor_id, name="test_stat_metric"
        )

        assert stats["count"] >= 5
        assert stats["min"] == 10.0
        assert stats["max"] == 50.0
        assert 30.0 <= stats["mean"] <= 30.0  # 平均值应该是30
        assert "std" in stats
        assert "first_timestamp" in stats
        assert "last_timestamp" in stats

    @pytest.mark.asyncio
    async def test_monitor_metric_properties(self):
        """测试监控指标属性"""
        # 创建监控指标
        metric = MonitorMetric(
            metric_id="test_metric_1",
            monitor_id="test_monitor",
            name="cpu_percent",
            value=75.5,
            unit="%",
            tags={"host": "server1", "type": "system"},
            metadata={"source": "psutil"},
        )

        # 检查属性
        assert metric.metric_id == "test_metric_1"
        assert metric.monitor_id == "test_monitor"
        assert metric.name == "cpu_percent"
        assert metric.value == 75.5
        assert metric.unit == "%"
        assert metric.tags["host"] == "server1"
        assert metric.tags["type"] == "system"
        assert metric.metadata["source"] == "psutil"
        assert metric.timestamp is not None

        # 测试转换为字典
        metric_dict = metric.to_dict()
        assert metric_dict["metric_id"] == "test_metric_1"
        assert metric_dict["monitor_id"] == "test_monitor"
        assert metric_dict["name"] == "cpu_percent"
        assert metric_dict["value"] == 75.5
        assert metric_dict["unit"] == "%"
        assert metric_dict["tags"]["host"] == "server1"
        assert "timestamp" in metric_dict

    @pytest.mark.asyncio
    async def test_get_alerts(self, monitor_manager, sample_monitor_config):
        """测试获取告警"""
        # 注册监控
        await monitor_manager.register_monitor(sample_monitor_config)

        # 创建测试告警
        alert_id = "test_alert_1"
        alert = MonitorAlert(
            alert_id=alert_id,
            monitor_id=sample_monitor_config.monitor_id,
            alert_level=AlertLevel.WARNING,
            message="测试警告告警",
            metric_name="cpu_percent",
            metric_value=85.0,
            threshold=80.0,
        )

        # 手动添加到管理器
        monitor_manager.alerts[alert_id] = alert
        monitor_manager.stats["active_alerts"] = 1
        monitor_manager.stats["total_alerts"] = 1

        # 获取所有告警
        all_alerts = await monitor_manager.get_alerts()
        assert len(all_alerts) >= 1

        # 按监控ID过滤
        monitor_alerts = await monitor_manager.get_alerts(
            monitor_id=sample_monitor_config.monitor_id
        )
        assert len(monitor_alerts) >= 1
        assert all(a.monitor_id == sample_monitor_config.monitor_id for a in monitor_alerts)

        # 按告警级别过滤
        warning_alerts = await monitor_manager.get_alerts(alert_level=AlertLevel.WARNING)
        assert len(warning_alerts) >= 1
        assert all(a.alert_level == AlertLevel.WARNING for a in warning_alerts)

        # 获取未解决的告警
        unresolved_alerts = await monitor_manager.get_alerts(unresolved=True)
        assert len(unresolved_alerts) >= 1
        assert all(not a.resolved for a in unresolved_alerts)

    @pytest.mark.asyncio
    async def test_acknowledge_resolve_alert(self, monitor_manager, sample_monitor_config):
        """测试确认和解决告警"""
        # 注册监控
        await monitor_manager.register_monitor(sample_monitor_config)

        # 创建测试告警
        alert_id = "test_alert_2"
        alert = MonitorAlert(
            alert_id=alert_id,
            monitor_id=sample_monitor_config.monitor_id,
            alert_level=AlertLevel.ERROR,
            message="测试错误告警",
            metric_name="memory_percent",
            metric_value=92.0,
            threshold=90.0,
        )

        # 手动添加到管理器
        monitor_manager.alerts[alert_id] = alert
        monitor_manager.stats["active_alerts"] = 1
        monitor_manager.stats["total_alerts"] = 1

        # 确认告警
        acknowledged = await monitor_manager.acknowledge_alert(alert_id)
        assert acknowledged is True
        assert monitor_manager.alerts[alert_id].acknowledged is True

        # 解决告警
        resolved = await monitor_manager.resolve_alert(alert_id)
        assert resolved is True
        assert alert_id not in monitor_manager.alerts
        assert monitor_manager.stats["active_alerts"] == 0

        # 检查是否移动到历史记录
        assert len(monitor_manager.alert_history) > 0
        last_alert = monitor_manager.alert_history[-1]
        assert last_alert.alert_id == alert_id
        assert last_alert.resolved is True
        assert last_alert.resolved_at is not None

    @pytest.mark.asyncio
    async def test_monitor_alert_properties(self):
        """测试监控告警属性"""
        # 创建监控告警
        alert = MonitorAlert(
            alert_id="test_alert_3",
            monitor_id="test_monitor",
            alert_level=AlertLevel.CRITICAL,
            message="CPU使用率超过临界阈值",
            metric_name="cpu_percent",
            metric_value=95.5,
            threshold=90.0,
        )

        # 检查属性
        assert alert.alert_id == "test_alert_3"
        assert alert.monitor_id == "test_monitor"
        assert alert.alert_level == AlertLevel.CRITICAL
        assert alert.message == "CPU使用率超过临界阈值"
        assert alert.metric_name == "cpu_percent"
        assert alert.metric_value == 95.5
        assert alert.threshold == 90.0
        assert alert.timestamp is not None
        assert alert.acknowledged is False
        assert alert.resolved is False
        assert alert.resolved_at is None

        # 解决告警
        alert.resolved = True
        alert.resolved_at = datetime.now()

        # 测试转换为字典
        alert_dict = alert.to_dict()
        assert alert_dict["alert_id"] == "test_alert_3"
        assert alert_dict["monitor_id"] == "test_monitor"
        assert alert_dict["alert_level"] == "critical"
        assert alert_dict["message"] == "CPU使用率超过临界阈值"
        assert alert_dict["metric_value"] == 95.5
        assert alert_dict["threshold"] == 90.0
        assert "timestamp" in alert_dict
        assert alert_dict["acknowledged"] is False
        assert alert_dict["resolved"] is True
        assert "resolved_at" in alert_dict

    @pytest.mark.asyncio
    async def test_service_health_properties(self):
        """测试服务健康属性"""
        # 创建服务健康状态
        health = ServiceHealth(
            service_name="api_service",
            status=ServiceStatus.HEALTHY,
            response_time=45.2,
            success_rate=0.995,
            error_message=None,
            metadata={"version": "1.2.3"},
        )

        # 检查属性
        assert health.service_name == "api_service"
        assert health.status == ServiceStatus.HEALTHY
        assert health.response_time == 45.2
        assert health.success_rate == 0.995
        assert health.error_message is None
        assert health.metadata["version"] == "1.2.3"
        assert health.last_check is not None

        # 测试转换为字典
        health_dict = health.to_dict()
        assert health_dict["service_name"] == "api_service"
        assert health_dict["status"] == "healthy"
        assert health_dict["response_time"] == 45.2
        assert health_dict["success_rate"] == 0.995
        assert health_dict["error_message"] is None
        assert health_dict["metadata"]["version"] == "1.2.3"
        assert "last_check" in health_dict

    @pytest.mark.asyncio
    async def test_update_service_health(self, monitor_manager):
        """测试更新服务健康状态"""
        # 更新服务健康
        await monitor_manager.update_service_health(
            service_name="test_service",
            status=ServiceStatus.HEALTHY,
            response_time=100.5,
            success_rate=0.98,
            error_message=None,
        )

        # 获取服务健康
        health_map = await monitor_manager.get_service_health()
        assert "test_service" in health_map

        health = health_map["test_service"]
        assert health.service_name == "test_service"
        assert health.status == ServiceStatus.HEALTHY
        assert health.response_time == 100.5
        assert health.success_rate == 0.98
        assert health.error_message is None

    @pytest.mark.asyncio
    async def test_get_service_health(self, monitor_manager):
        """测试获取服务健康状态"""
        # 更新多个服务
        await monitor_manager.update_service_health(
            service_name="service_1", status=ServiceStatus.HEALTHY, response_time=50.0
        )

        await monitor_manager.update_service_health(
            service_name="service_2",
            status=ServiceStatus.DEGRADED,
            response_time=200.0,
            success_rate=0.95,
        )

        # 获取所有服务
        all_services = await monitor_manager.get_service_health()
        assert len(all_services) >= 2

        # 获取特定服务
        service_1 = await monitor_manager.get_service_health("service_1")
        assert "service_1" in service_1
        assert service_1["service_1"].service_name == "service_1"
        assert service_1["service_1"].status == ServiceStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_system_metrics_properties(self):
        """测试系统指标属性"""
        # 创建系统指标
        system_metric = SystemMetrics(
            cpu_percent=45.5,
            memory_percent=62.3,
            memory_used_mb=8192.0,
            memory_total_mb=16384.0,
            disk_percent=75.8,
            disk_used_gb=500.0,
            disk_total_gb=1000.0,
            network_sent_mb=1024.5,
            network_recv_mb=2048.7,
            load_avg_1m=0.8,
            load_avg_5m=1.2,
            load_avg_15m=1.5,
            uptime_seconds=86400.0,  # 1天
            process_count=150,
        )

        # 检查属性
        assert system_metric.cpu_percent == 45.5
        assert system_metric.memory_percent == 62.3
        assert system_metric.memory_used_mb == 8192.0
        assert system_metric.memory_total_mb == 16384.0
        assert system_metric.disk_percent == 75.8
        assert system_metric.disk_used_gb == 500.0
        assert system_metric.disk_total_gb == 1000.0
        assert system_metric.network_sent_mb == 1024.5
        assert system_metric.network_recv_mb == 2048.7
        assert system_metric.load_avg_1m == 0.8
        assert system_metric.load_avg_5m == 1.2
        assert system_metric.load_avg_15m == 1.5
        assert system_metric.uptime_seconds == 86400.0
        assert system_metric.process_count == 150
        assert system_metric.timestamp is not None

        # 测试转换为字典
        metric_dict = system_metric.to_dict()
        assert metric_dict["cpu_percent"] == 45.5
        assert metric_dict["memory_percent"] == 62.3
        assert metric_dict["disk_percent"] == 75.8
        assert metric_dict["load_avg_1m"] == 0.8
        assert metric_dict["uptime_seconds"] == 86400.0
        assert "timestamp" in metric_dict

    @pytest.mark.asyncio
    async def test_get_system_metrics(self, monitor_manager):
        """测试获取系统指标"""
        # 获取系统指标
        system_metrics = await monitor_manager.get_system_metrics(limit=10)

        assert isinstance(system_metrics, list)
        if system_metrics:  # 如果有数据
            assert all(isinstance(m, SystemMetrics) for m in system_metrics)

    @pytest.mark.asyncio
    async def test_get_system_summary(self, monitor_manager):
        """测试获取系统摘要"""
        summary = await monitor_manager.get_system_summary()

        assert isinstance(summary, dict)
        if summary:  # 如果有数据
            assert "timestamp" in summary
            assert "cpu" in summary
            assert "memory" in summary
            assert "disk" in summary
            assert "load" in summary
            assert "uptime" in summary

    @pytest.mark.asyncio
    async def test_get_dashboard_data(self, monitor_manager):
        """测试获取仪表板数据"""
        dashboard = await monitor_manager.get_dashboard_data()

        assert isinstance(dashboard, dict)
        assert "system" in dashboard
        assert "services" in dashboard
        assert "alerts" in dashboard
        assert "metrics" in dashboard
        assert "timestamp" in dashboard

        # 检查服务部分
        services = dashboard["services"]
        assert "total" in services
        assert "healthy" in services
        assert "unhealthy" in services
        assert "list" in services

        # 检查告警部分
        alerts = dashboard["alerts"]
        assert "active" in alerts
        assert "critical" in alerts
        assert "warning" in alerts
        assert "list" in alerts

    @pytest.mark.asyncio
    async def test_get_statistics(self, monitor_manager):
        """测试获取统计信息"""
        stats = await monitor_manager.get_statistics()

        assert isinstance(stats, dict)
        assert "total_checks" in stats
        assert "total_alerts" in stats
        assert "active_alerts" in stats
        assert "total_monitors" in stats
        assert "enabled_monitors" in stats
        assert "total_metrics" in stats
        assert "total_services" in stats

    @pytest.mark.asyncio
    async def test_enum_values(self):
        """测试枚举值"""
        # 监控类型
        assert MonitorType.SYSTEM.value == "system"
        assert MonitorType.SERVICE.value == "service"
        assert MonitorType.BUSINESS.value == "business"
        assert MonitorType.CUSTOM.value == "custom"

        # 告警级别
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.ERROR.value == "error"
        assert AlertLevel.CRITICAL.value == "critical"

        # 服务状态
        assert ServiceStatus.HEALTHY.value == "healthy"
        assert ServiceStatus.DEGRADED.value == "degraded"
        assert ServiceStatus.UNHEALTHY.value == "unhealthy"
        assert ServiceStatus.OFFLINE.value == "offline"

    @pytest.mark.asyncio
    async def test_unregister_monitor(self, monitor_manager, sample_monitor_config):
        """测试取消注册监控"""
        # 先注册监控
        await monitor_manager.register_monitor(sample_monitor_config)
        assert sample_monitor_config.monitor_id in monitor_manager.monitor_configs

        # 取消注册
        success = await monitor_manager.unregister_monitor(sample_monitor_config.monitor_id)
        assert success is True
        assert sample_monitor_config.monitor_id not in monitor_manager.monitor_configs

        # 取消不存在的监控应该失败
        failed = await monitor_manager.unregister_monitor("nonexistent_monitor")
        assert failed is False

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, monitor_manager, sample_monitor_config):
        """测试并发操作"""
        # 注册监控
        await monitor_manager.register_monitor(sample_monitor_config)

        # 并发收集指标
        async def collect_metric_task(i):
            return await monitor_manager.collect_metric(
                monitor_id=sample_monitor_config.monitor_id, name=f"metric_{i}", value=i * 10.0
            )

        # 创建多个收集任务
        tasks = [collect_metric_task(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # 检查结果
        assert len(results) == 10
        assert all(r is True for r in results)

        # 检查指标数量
        metrics = await monitor_manager.get_metrics(monitor_id=sample_monitor_config.monitor_id)
        assert len(metrics) >= 10


if __name__ == "__main__":
    """运行测试"""
    import sys

    import pytest

    # 添加src目录到Python路径
    sys.path.insert(0, "/home/cool/.openclaw-trading/src")

    # 运行测试
    pytest.main([__file__, "-v"])
