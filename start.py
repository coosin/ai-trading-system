#!/usr/bin/env python3
"""
OpenClaw Trading - 系统启动脚本
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from src.utils.env_config import load_environment
load_environment()

from src.modules.core.config_manager import get_config_manager
from src.modules.main_controller import MainController

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/trading.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("🚀 启动 OpenClaw Trading 全智能量化交易系统")
    logger.info("=" * 80)
    
    # 检查必需的环境变量
    from src.utils.env_config import EnvConfig
    if not os.getenv("AICLIENT_API_KEY", "").strip():
        logger.warning(
            "未检测到 AICLIENT_API_KEY：与 AIClient-2-API 的 REQUIRED_API_KEY 一致，"
            "否则默认 LLM（gemini-2.5-flash）无法完成鉴权。"
        )
    
    # 打印环境变量摘要
    EnvConfig.print_env_summary()
    
    # 初始化配置管理器
    logger.info("\n📋 初始化配置管理器...")
    config_manager = await get_config_manager()
    
    # 初始化主控制器
    logger.info("\n🔧 初始化主控制器...")
    controller = MainController(config_manager)
    await controller.initialize()
    
    # 启动系统
    logger.info("\n🚀 启动系统...")
    success = await controller.start_system()
    
    if success:
        logger.info("\n" + "=" * 80)
        logger.info("✅ 系统启动成功!")
        logger.info("=" * 80)
        logger.info("\n📊 系统状态:")
        logger.info(f"  - 运行模式: {os.getenv('MODE', 'simulation')}")
        logger.info(f"  - 交易对: {os.getenv('TRADING_SYMBOLS', 'BTC/USDT,ETH/USDT')}")
        logger.info("  - AI模型: gemini-2.5-flash（经本地 AIClient OpenAI 兼容端点）")
        logger.info(f"  - API端口: {os.getenv('API_PORT', '8000')}")
        logger.info("\n💡 提示:")
        logger.info("  - 访问 http://localhost:8000/docs 查看API文档")
        logger.info("  - 按 Ctrl+C 停止系统")
        logger.info("=" * 80 + "\n")
        
        try:
            # 保持运行
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n\n🛑 收到停止信号...")
    else:
        logger.error("❌ 系统启动失败")
        sys.exit(1)
    
    # 清理
    logger.info("\n🧹 清理资源...")
    await controller.cleanup()
    logger.info("✅ 系统已安全关闭")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 系统已退出")
    except Exception as e:
        logger.error(f"❌ 系统异常退出: {e}", exc_info=True)
        sys.exit(1)
