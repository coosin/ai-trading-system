#!/usr/bin/env python3

import asyncio
import logging
import sys
from typing import Dict, Any

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 添加项目根目录到路径
sys.path.insert(0, '/home/cool/.openclaw-trading')

from src.modules.core.system_monitor import SystemMonitor

async def test_system_monitor():
    """测试系统监控"""
    logging.info("=== 测试系统监控 ===")
    
    # 初始化系统监控
    monitor_config = {
        "monitoring_interval": 5,
        "max_health_history": 100,
        "failure_threshold": 3,
        "recovery_timeout": 60,
        "alert_thresholds": {
            "cpu": 80,
            "memory": 85,
            "disk": 90,
            "network_latency": 500
        }
    }
    
    system_monitor = SystemMonitor(monitor_config)
    await system_monitor.initialize()
    
    # 测试系统健康检查
    for i in range(3):
        health = await system_monitor.check_system_health()
        logging.info(f"系统健康状态: {health.overall_status.value}")
        logging.info(f"CPU使用率: {health.cpu_usage:.2f}%")
        logging.info(f"内存使用率: {health.memory_usage:.2f}%")
        logging.info(f"磁盘使用率: {health.disk_usage:.2f}%")
        
        # 检查组件状态
        for component_status in health.component_statuses:
            logging.info(f"组件 {component_status.component.value}: {component_status.status.value} - {component_status.message}")
        
        await asyncio.sleep(2)
    
    # 测试告警功能
    alerts = system_monitor.get_active_alerts()
    logging.info(f"活跃告警数量: {len(alerts)}")
    for alert in alerts:
        logging.info(f"告警: {alert['severity']} - {alert['message']}")
    
    # 测试告警历史
    alert_history = system_monitor.get_alert_history(5)
    logging.info(f"告警历史数量: {len(alert_history)}")
    
    # 测试清除告警
    system_monitor.clear_alerts()
    logging.info(f"清除告警后活跃告警数量: {len(system_monitor.get_active_alerts())}")
    
    # 关闭系统监控
    await system_monitor.shutdown()

async def main():
    """主测试函数"""
    try:
        await test_system_monitor()
        logging.info("所有测试完成")
    except Exception as e:
        logging.error(f"测试过程中出现错误: {e}")

if __name__ == "__main__":
    asyncio.run(main())
