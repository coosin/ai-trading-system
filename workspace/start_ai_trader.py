#!/usr/bin/env python3
"""
全智能量化交易系统启动脚本
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime

# 添加模块路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def print_banner():
    """打印启动横幅"""

    banner = """
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║     🚀 全智能量化交易系统 v1.0                          ║
    ║     🤖 AI-Driven Quantitative Trading System             ║
    ║                                                          ║
    ║     功能特性:                                            ║
    ║     • 多模型AI决策引擎                                   ║
    ║     • 智能订单执行系统                                   ║
    ║     • 实时风险管理                                       ║
    ║     • 自适应学习优化                                     ║
    ║     • 7x24h无人值守运行                                 ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """

    print(banner)


def create_directories():
    """创建必要目录"""

    base_dir = os.path.dirname(os.path.abspath(__file__))
    directories = ["logs", "database", "cache", "reports"]

    for dir_name in directories:
        dir_path = os.path.join(base_dir, dir_name)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"📁 创建目录: {dir_path}")

    return base_dir


def check_dependencies():
    """检查依赖"""

    required_packages = ["aiohttp", "numpy", "pandas", "websockets", "dataclasses"]

    missing_packages = []

    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print("❌ 缺少依赖包:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\n请使用以下命令安装:")
        print(f"   pip install {' '.join(missing_packages)}")
        return False

    return True


def parse_arguments():
    """解析命令行参数"""

    parser = argparse.ArgumentParser(
        description="全智能量化交易系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
运行模式说明:
  paper     - 模拟交易模式，不连接真实交易所
  live      - 实盘交易模式，连接真实交易所
  backtest  - 回测模式，使用历史数据测试策略
  monitor   - 仅监控模式，不执行交易

示例:
  %(prog)s --mode paper --symbols BTCUSDT,ETHUSDT
  %(prog)s --mode live --config ./config/trading.json
  %(prog)s --mode backtest --start 2024-01-01 --end 2024-06-01
        """,
    )

    parser.add_argument(
        "--mode",
        type=str,
        choices=["paper", "live", "backtest", "monitor"],
        default="paper",
        help="运行模式 (默认: paper)",
    )

    parser.add_argument(
        "--symbols", type=str, default="BTCUSDT,ETHUSDT,SOLUSDT", help="监控的交易对，用逗号分隔"
    )

    parser.add_argument("--config", type=str, default=None, help="配置文件路径")

    parser.add_argument("--capital", type=float, default=10000.0, help="初始资金 (默认: 10000)")

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日志级别 (默认: INFO)",
    )

    parser.add_argument("--no-banner", action="store_true", help="不显示启动横幅")

    parser.add_argument("--version", action="version", version="全智能量化交易系统 v1.0")

    # 回测专用参数
    parser.add_argument("--start-date", type=str, help="回测开始日期 (YYYY-MM-DD)")

    parser.add_argument("--end-date", type=str, help="回测结束日期 (YYYY-MM-DD)")

    parser.add_argument("--timeframe", type=str, default="1h", help="K线时间周期 (默认: 1h)")

    return parser.parse_args()


def setup_logging(log_level: str, base_dir: str):
    """设置日志系统"""

    import logging

    # 日志格式
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # 设置根日志
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level))
    console_formatter = logging.Formatter(log_format, date_format)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器
    log_file = os.path.join(
        base_dir, "logs", f'trading_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    )
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(log_format, date_format)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    print(f"📝 日志文件: {log_file}")

    return root_logger


def validate_arguments(args):
    """验证参数"""

    # 检查资金
    if args.capital <= 0:
        print("❌ 错误: 初始资金必须大于0")
        return False

    # 检查交易对
    symbols = args.symbols.split(",")
    if len(symbols) == 0:
        print("❌ 错误: 至少需要指定一个交易对")
        return False

    # 检查回测参数
    if args.mode == "backtest":
        if not args.start_date or not args.end_date:
            print("❌ 错误: 回测模式需要指定开始日期和结束日期")
            return False

        try:
            from datetime import datetime

            start = datetime.strptime(args.start_date, "%Y-%m-%d")
            end = datetime.strptime(args.end_date, "%Y-%m-%d")

            if start >= end:
                print("❌ 错误: 开始日期必须早于结束日期")
                return False
        except ValueError:
            print("❌ 错误: 日期格式应为 YYYY-MM-DD")
            return False

    return True


async def run_system(args, base_dir, logger):
    """运行交易系统"""

    try:
        from modules.main_controller import get_controller

        # 获取控制器实例
        controller = get_controller()

        # 设置运行参数
        mode_map = {
            "paper": "paper_trading",
            "live": "live_trading",
            "backtest": "backtesting",
            "monitor": "monitoring",
        }

        run_mode = mode_map.get(args.mode, "paper_trading")

        # 设置初始资金
        controller.portfolio.total_capital = args.capital
        controller.portfolio.available_capital = args.capital

        # 设置监控币种
        controller.monitored_symbols = args.symbols.split(",")

        # 注册事件回调
        def on_signal_generated(event_type, data):
            symbol = data.get("symbol")
            signal = data.get("signal", {})
            decision = signal.get("decision")
            confidence = signal.get("confidence", 0)

            if confidence > 0.6 and decision != "HOLD":
                logger.info(f"📡 交易信号: {symbol} {decision} (置信度: {confidence:.2f})")

        def on_order_created(event_type, data):
            order_id = data.get("order_id")
            symbol = data.get("symbol")
            side = data.get("side")
            quantity = data.get("quantity")
            price = data.get("price")

            logger.info(f"📝 创建订单: {order_id} {side} {quantity} {symbol} @ {price}")

        def on_error_occurred(event_type, data):
            task = data.get("task", "unknown")
            error = data.get("error", "unknown error")

            logger.error(f"❌ {task} 任务出错: {error}")

        controller.register_callback("signal_generated", on_signal_generated)
        controller.register_callback("order_created", on_order_created)
        controller.register_callback("error_occurred", on_error_occurred)

        # 启动系统
        logger.info(f"🚀 启动交易系统 (模式: {run_mode})")
        logger.info(f"💰 初始资金: ${args.capital:,.2f}")
        logger.info(f"📊 监控币种: {', '.join(controller.monitored_symbols)}")

        await controller.start(run_mode)

    except Exception as e:
        logger.error(f"系统运行失败: {e}")
        raise


def main():
    """主函数"""

    # 解析参数
    args = parse_arguments()

    # 验证参数
    if not validate_arguments(args):
        sys.exit(1)

    # 显示横幅
    if not args.no_banner:
        print_banner()

    # 检查依赖
    if not check_dependencies():
        sys.exit(1)

    # 创建目录
    base_dir = create_directories()

    # 设置日志
    logger = setup_logging(args.log_level, base_dir)

    # 显示启动信息
    print("\n" + "=" * 60)
    print("📋 启动配置:")
    print(f"   运行模式: {args.mode}")
    print(f"   交易对: {args.symbols}")
    print(f"   初始资金: ${args.capital:,.2f}")
    print(f"   日志级别: {args.log_level}")

    if args.mode == "backtest":
        print(f"   回测期间: {args.start_date} 至 {args.end_date}")
        print(f"   K线周期: {args.timeframe}")

    print("=" * 60 + "\n")

    # 运行系统
    try:
        asyncio.run(run_system(args, base_dir, logger))
    except KeyboardInterrupt:
        print("\n\n👋 用户中断，系统已停止")
    except Exception as e:
        print(f"\n\n❌ 系统运行出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
