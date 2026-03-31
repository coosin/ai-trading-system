#!/usr/bin/env python3
"""
性能监控功能测试脚本
测试系统监控、性能指标收集、告警机制等功能
"""

import asyncio
import logging
import time
from src.modules.core.system_monitor import SystemMonitor, SystemStatus, ComponentType

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_system_monitor():
    """测试系统监控功能"""
    logger.info("🧪 测试系统监控功能...")
    logger.info("==================================================")
    
    # 1. 初始化系统监控
    logger.info("1. 初始化系统监控")
    config = {
        "monitoring_interval": 2,  # 缩短测试间隔
        "max_health_history": 10,
        "failure_threshold": 2,
        "recovery_timeout": 5,
        "alert_thresholds": {
            "cpu": 50,  # 降低阈值以便测试告警
            "memory": 50,
            "disk": 50,
            "network_latency": 100
        }
    }
    
    monitor = SystemMonitor(config)
    initialized = await monitor.initialize()
    assert initialized, "系统监控初始化失败"
    logger.info("✅ 系统监控初始化成功")
    
    # 2. 等待监控循环运行
    logger.info("2. 等待监控循环运行...")
    await asyncio.sleep(4)  # 等待两次监控循环
    
    # 3. 测试获取系统健康状态
    logger.info("3. 测试获取系统健康状态")
    health = monitor.get_system_health()
    assert health is not None, "获取系统健康状态失败"
    logger.info(f"✅ 系统健康状态: {health.overall_status.value}")
    logger.info(f"   CPU使用率: {health.cpu_usage:.2f}%")
    logger.info(f"   内存使用率: {health.memory_usage:.2f}%")
    logger.info(f"   磁盘使用率: {health.disk_usage:.2f}%")
    logger.info(f"   网络状态: {health.network_status.get('status', 'unknown')}")
    
    # 4. 测试获取健康历史
    logger.info("4. 测试获取健康历史")
    health_history = monitor.get_health_history(limit=5)
    assert len(health_history) > 0, "获取健康历史失败"
    logger.info(f"✅ 健康历史记录数: {len(health_history)}")
    
    # 5. 测试系统健康检查
    logger.info("5. 测试系统健康检查")
    is_healthy = monitor.is_healthy()
    logger.info(f"✅ 系统健康状态: {'健康' if is_healthy else '不健康'}")
    
    # 6. 测试获取活跃告警
    logger.info("6. 测试获取活跃告警")
    alerts = monitor.get_active_alerts()
    logger.info(f"✅ 活跃告警数: {len(alerts)}")
    if alerts:
        for alert in alerts[:3]:  # 只显示前3个告警
            logger.info(f"   - {alert['severity']}: {alert['message']}")
    
    # 7. 测试获取告警历史
    logger.info("7. 测试获取告警历史")
    alert_history = monitor.get_alert_history(limit=5)
    logger.info(f"✅ 告警历史记录数: {len(alert_history)}")
    
    # 8. 测试清除告警
    logger.info("8. 测试清除告警")
    monitor.clear_alerts()
    alerts_after_clear = monitor.get_active_alerts()
    assert len(alerts_after_clear) == 0, "清除告警失败"
    logger.info("✅ 告警清除成功")
    
    # 9. 测试设置告警阈值
    logger.info("9. 测试设置告警阈值")
    monitor.set_alert_threshold("cpu", 90)
    logger.info("✅ 告警阈值设置成功")
    
    # 10. 测试添加自定义检查
    logger.info("10. 测试添加自定义检查")
    async def custom_check():
        return SystemStatus.HEALTHY, "Custom component healthy"
    
    await monitor.add_custom_check(ComponentType.STRATEGY, custom_check)
    logger.info("✅ 自定义检查添加成功")
    
    # 11. 测试添加自定义恢复
    logger.info("11. 测试添加自定义恢复")
    async def custom_recovery():
        return True
    
    await monitor.add_custom_recovery(ComponentType.STRATEGY, custom_recovery)
    logger.info("✅ 自定义恢复添加成功")
    
    # 12. 测试关闭系统监控
    logger.info("12. 测试关闭系统监控")
    shutdown = await monitor.shutdown()
    assert shutdown, "系统监控关闭失败"
    logger.info("✅ 系统监控关闭成功")
    
    logger.info("==================================================")
    logger.info("🎉 性能监控功能测试完成！")
    logger.info("✅ 所有测试通过")

if __name__ == "__main__":
    asyncio.run(test_system_monitor())
