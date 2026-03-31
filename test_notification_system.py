#!/usr/bin/env python3
"""
通知系统功能测试脚本
测试通知管理、告警发送、交易信号通知等功能
"""

import asyncio
import logging
from src.modules.notification.notification_manager import NotificationManager, NotificationType

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_notification_manager():
    """测试通知管理器功能"""
    logger.info("🧪 测试通知系统功能...")
    logger.info("==================================================")
    
    # 1. 初始化通知管理器
    logger.info("1. 初始化通知管理器")
    config = {
        "telegram": {
            "enabled": False,  # 禁用Telegram以避免实际发送
        },
        "email": {
            "enabled": False,  # 禁用邮件以避免实际发送
        }
    }
    
    notification_manager = NotificationManager(config)
    initialized = await notification_manager.initialize()
    assert initialized, "通知管理器初始化失败"
    logger.info("✅ 通知管理器初始化成功")
    
    # 2. 测试发送信息通知
    logger.info("2. 测试发送信息通知")
    success = await notification_manager.send_notification(
        "测试信息通知",
        NotificationType.INFO,
        {"test": "value"}
    )
    assert success, "发送信息通知失败"
    logger.info("✅ 信息通知发送成功")
    
    # 3. 测试发送警告通知
    logger.info("3. 测试发送警告通知")
    success = await notification_manager.send_notification(
        "测试警告通知",
        NotificationType.WARNING,
        {"severity": "medium"}
    )
    assert success, "发送警告通知失败"
    logger.info("✅ 警告通知发送成功")
    
    # 4. 测试发送错误通知
    logger.info("4. 测试发送错误通知")
    success = await notification_manager.send_notification(
        "测试错误通知",
        NotificationType.ERROR,
        {"error_code": "500"}
    )
    assert success, "发送错误通知失败"
    logger.info("✅ 错误通知发送成功")
    
    # 5. 测试发送成功通知
    logger.info("5. 测试发送成功通知")
    success = await notification_manager.send_notification(
        "测试成功通知",
        NotificationType.SUCCESS,
        {"result": "success"}
    )
    assert success, "发送成功通知失败"
    logger.info("✅ 成功通知发送成功")
    
    # 6. 测试发送交易信号通知
    logger.info("6. 测试发送交易信号通知")
    trading_signal = {
        "signal_type": "BUY",
        "asset": "BTC/USDT",
        "amount": 0.01,
        "price": 60000,
        "confidence": 0.95,
        "timestamp": "2026-03-31 10:00:00",
        "reason": "RSI指标超卖"
    }
    success = await notification_manager.send_trading_signal(trading_signal)
    assert success, "发送交易信号通知失败"
    logger.info("✅ 交易信号通知发送成功")
    
    # 7. 测试健康检查
    logger.info("7. 测试健康检查")
    is_healthy = notification_manager.is_healthy()
    assert is_healthy, "通知管理器健康检查失败"
    logger.info(f"✅ 通知管理器健康状态: {'健康' if is_healthy else '不健康'}")
    
    # 8. 测试关闭通知管理器
    logger.info("8. 测试关闭通知管理器")
    shutdown = await notification_manager.shutdown()
    assert shutdown, "通知管理器关闭失败"
    logger.info("✅ 通知管理器关闭成功")
    
    # 9. 测试关闭后发送通知
    logger.info("9. 测试关闭后发送通知")
    success = await notification_manager.send_notification(
        "测试关闭后发送通知",
        NotificationType.INFO
    )
    assert not success, "关闭后不应该能发送通知"
    logger.info("✅ 关闭后发送通知测试成功")
    
    logger.info("==================================================")
    logger.info("🎉 通知系统功能测试完成！")
    logger.info("✅ 所有测试通过")

if __name__ == "__main__":
    asyncio.run(test_notification_manager())
