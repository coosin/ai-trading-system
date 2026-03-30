"""
全智能量化交易系统 - 主入口点

系统启动和主控制器。
"""

import asyncio
import logging
import sys
import signal
from pathlib import Path
from typing import Optional

from src.modules.core.config_manager import get_config_manager, cleanup_config_manager
from src.modules.main_controller import MainController

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/app.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)


class TradingSystem:
    """交易系统主类"""
    
    def __init__(self):
        self.config_manager = None
        self.main_controller = None
        self.running = False
        self.shutdown_event = asyncio.Event()
        
    async def initialize(self) -> None:
        """初始化系统"""
        logger.info("🚀 启动全智能量化交易系统...")
        
        try:
            # 1. 初始化配置管理器
            logger.info("1. 初始化配置管理器...")
            self.config_manager = await get_config_manager()
            
            # 2. 初始化主控制器
            logger.info("2. 初始化主控制器...")
            self.main_controller = MainController(self.config_manager)
            await self.main_controller.initialize()
            
            # 3. 设置信号处理
            self._setup_signal_handlers()
            
            logger.info("✅ 系统初始化完成")
            self.running = True
            
        except Exception as e:
            logger.error(f"❌ 系统初始化失败: {e}")
            await self.shutdown()
            raise
    
    async def run(self) -> None:
        """运行系统主循环"""
        if not self.running:
            logger.error("系统未初始化，无法运行")
            return
        
        logger.info("🔄 启动系统主循环...")
        
        try:
            # 启动所有模块
            await self.main_controller.start_all_modules()
            
            # 等待关闭信号
            await self.shutdown_event.wait()
            
            logger.info("系统正在关闭...")
            
        except asyncio.CancelledError:
            logger.info("系统运行被取消")
        except Exception as e:
            logger.error(f"系统运行出错: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self) -> None:
        """关闭系统"""
        if not self.running:
            return
        
        logger.info("正在关闭系统...")
        
        try:
            # 1. 关闭主控制器
            if self.main_controller:
                await self.main_controller.shutdown()
            
            # 2. 清理配置管理器
            if self.config_manager:
                await cleanup_config_manager()
            
            self.running = False
            logger.info("✅ 系统已安全关闭")
            
        except Exception as e:
            logger.error(f"关闭系统时出错: {e}")
    
    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        loop = asyncio.get_event_loop()
        
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(self._handle_shutdown_signal(s))
            )
        
        logger.debug("信号处理器已设置")
    
    async def _handle_shutdown_signal(self, sig: signal.Signals) -> None:
        """处理关闭信号"""
        signal_name = signal.Signals(sig).name
        logger.info(f"收到信号: {signal_name}")
        self.shutdown_event.set()


async def main() -> None:
    """主函数"""
    system = TradingSystem()
    
    try:
        await system.initialize()
        await system.run()
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"系统运行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # 确保日志目录存在
    Path("logs").mkdir(exist_ok=True)
    
    # 运行主函数
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 再见！")
    except Exception as e:
        print(f"❌ 系统崩溃: {e}")
        sys.exit(1)