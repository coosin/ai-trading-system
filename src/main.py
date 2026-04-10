"""
全智能量化交易系统 - 主入口点

系统启动和主控制器。
"""

import asyncio
import logging
import logging.handlers
import signal
import sys
from pathlib import Path
from typing import Optional

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from src.modules.core.config_manager import ConfigManager
from src.modules.main_controller import MainController
from src.modules.api.server import APIServer
from src.utils.process_lock import ProcessLock

APP_NAME = "openclaw-trading"
_process_lock: Optional[ProcessLock] = None

_config_manager = None

async def get_config_manager() -> ConfigManager:
    """获取配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        # 自动探测并合并配置目录（data/config、config、/app/*），避免配置目录不一致导致缺省配置
        _config_manager = ConfigManager()
        await _config_manager.initialize()
    return _config_manager

async def cleanup_config_manager() -> None:
    """清理配置管理器"""
    global _config_manager
    if _config_manager:
        await _config_manager.cleanup()
        _config_manager = None

def _resolve_app_log_path() -> str:
    log_candidates = [
        Path("logs/app.log"),
        Path("/tmp/openclaw-trading/logs/app.log"),
    ]
    for p in log_candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            # probe write access
            with open(p, "a", encoding="utf-8"):
                pass
            return str(p)
        except PermissionError:
            continue
        except Exception:
            continue
    # final fallback: disable file logging by using /dev/null
    return "/dev/null"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        # IMPORTANT: use rotation to avoid filling disk
        logging.handlers.RotatingFileHandler(
            _resolve_app_log_path(),
            encoding="utf-8",
            maxBytes=int(20 * 1024 * 1024),  # 20MB per file
            backupCount=10,
        ),
    ],
)

logger = logging.getLogger(__name__)


class TradingSystem:
    """交易系统主类"""

    def __init__(self):
        self.config_manager = None
        self.main_controller = None
        self.api_server = None
        self.running = False
        self.shutdown_event = asyncio.Event()

    async def initialize(self) -> None:
        """初始化系统"""
        logger.info("🚀 启动全智能量化交易系统...")

        try:
            logger.info("1. 初始化配置管理器...")
            self.config_manager = await get_config_manager()

            logger.info("2. 初始化主控制器...")
            self.main_controller = MainController(self.config_manager)
            await self.main_controller.initialize()

            logger.info("3. 初始化API服务器...")
            api_config = await self.config_manager.get_config("api", {})
            self.api_server = APIServer(
                config_manager=self.config_manager,
                main_controller=self.main_controller,
                host=api_config.get("host", "0.0.0.0"),
                port=api_config.get("port", 8000)
            )
            await self.api_server.initialize()

            logger.info("4. 设置信号处理...")
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
            # 先启动 API（避免 start_system 因外部依赖阻塞导致“端口未监听”）
            if self.api_server:
                await self.api_server.start()
                logger.info(f"API服务器已启动，访问 http://{self.api_server.host}:{self.api_server.port}/docs 查看文档")

            # 使用 MainController 的完整启动流程（包含依赖顺序、状态管理与健康检查链路）
            await self.main_controller.start_system()

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
            if self.api_server:
                logger.info("正在关闭API服务器...")
                await self.api_server.stop()
                await self.api_server.cleanup()

            if self.main_controller:
                await self.main_controller.cleanup()

            if self.config_manager:
                await cleanup_config_manager()

            self.running = False
            logger.info("✅ 系统已安全关闭")

        except Exception as e:
            logger.error(f"关闭系统时出错: {e}")

    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        try:
            loop = asyncio.get_event_loop()

            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(
                    sig, lambda s=sig: asyncio.create_task(self._handle_shutdown_signal(s))
                )

            logger.debug("信号处理器已设置")
        except Exception as e:
            logger.warning(f"设置信号处理器失败（可能在某些环境中不支持）: {e}")

    async def _handle_shutdown_signal(self, sig: signal.Signals) -> None:
        """处理关闭信号"""
        signal_name = signal.Signals(sig).name
        logger.info(f"收到信号: {signal_name}")
        self.shutdown_event.set()


async def main() -> None:
    """主函数"""
    global _process_lock
    
    _process_lock = ProcessLock(APP_NAME)
    
    if not _process_lock.acquire():
        logger.error("❌ 另一个实例已在运行中，请先停止现有实例")
        logger.info("❌ 另一个实例已在运行中，请先停止现有实例")
        logger.info(f"   提示: 如果确认没有其他实例，请删除 /tmp/{APP_NAME}.lock 文件后重试")
        return
    
    system = TradingSystem()

    try:
        await system.initialize()
        await system.run()
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"系统运行失败: {e}")
    finally:
        if _process_lock:
            _process_lock.release()


if __name__ == "__main__":
    Path("logs").mkdir(exist_ok=True)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 再见！")
    except Exception as e:
        logger.info(f"❌ 系统崩溃: {e}")
        sys.exit(1)
