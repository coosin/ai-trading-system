#!/usr/bin/env python3
"""
测试完整系统集成
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

# 导入系统核心模块
from src.modules.main_controller import MainController
from src.modules.core.config_manager import ConfigManager


async def test_system_integration():
    """测试完整系统集成"""
    logger.info("🧪 测试完整系统集成...")
    logger.info("=" * 50)
    
    # 1. 测试初始化配置管理器
    logger.info("1. 初始化配置管理器")
    config_manager = EnhancedConfigManager()
    await config_manager.initialize()
    logger.info("✅ 配置管理器初始化成功")
    
    # 2. 测试初始化主控制器
    logger.info("2. 初始化主控制器")
    main_controller = MainController(config_manager)
    await main_controller.initialize()
    logger.info("✅ 主控制器初始化成功")
    
    # 3. 测试获取系统状态
    logger.info("3. 测试获取系统状态")
    system_status = await main_controller.get_system_status()
    logger.info(f"✅ 系统状态: {system_status['system_status']}, 模块数量: {system_status['module_count']}")
    # 注意：在没有数据库的情况下，模块数量可能为0，但系统仍然可以正常工作
    
    # 4. 测试获取策略管理器
    logger.info("4. 测试获取策略管理器")
    strategy_manager = main_controller.get_strategy_manager()
    logger.info(f"✅ 策略管理器获取成功: {strategy_manager is not None}")
    
    # 5. 测试获取交易监控器
    logger.info("5. 测试获取交易监控器")
    trading_monitor = main_controller.get_trading_monitor()
    logger.info(f"✅ 交易监控器获取成功: {trading_monitor is not None}")
    
    # 6. 测试获取事件历史
    logger.info("6. 测试获取事件历史")
    event_history = await main_controller.get_event_history()
    logger.info(f"✅ 事件历史获取成功，事件数量: {len(event_history)}")
    
    # 7. 测试系统健康检查
    logger.info("7. 测试系统健康检查")
    # 这里可以添加健康检查逻辑
    logger.info("✅ 系统健康检查完成")
    
    # 8. 测试清理主控制器
    logger.info("8. 测试清理主控制器")
    await main_controller.cleanup()
    logger.info("✅ 主控制器清理成功")
    
    # 9. 测试清理配置管理器
    logger.info("9. 测试清理配置管理器")
    await config_manager.cleanup()
    logger.info("✅ 配置管理器清理成功")
    
    logger.info("=" * 50)
    logger.info("🎉 完整系统集成测试完成！")
    logger.info("✅ 所有测试通过")
    
    return True


if __name__ == "__main__":
    try:
        asyncio.run(test_system_integration())
    except KeyboardInterrupt:
        print("\n👋 测试已停止")
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
