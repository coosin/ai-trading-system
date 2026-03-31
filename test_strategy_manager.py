#!/usr/bin/env python3
"""
测试策略管理功能
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

# 导入策略相关模块
from src.modules.core.strategy_manager import StrategyManager
from src.modules.strategies.strategy_base import Strategy


class TestStrategy(Strategy):
    """测试策略"""
    
    def __init__(self, config):
        super().__init__(config)
        self.active = False  # 默认未激活
        self.pnl = 0
        self.wins = 0
        self.total_trades = 0
    
    def generate_signal(self, market_data):
        """生成交易信号"""
        return {
            "symbol": "BTCUSDT",
            "side": "buy",
            "price": 50000.0,
            "quantity": 0.01,
            "type": "market"
        }
    
    def get_performance(self):
        """获取策略性能"""
        return {
            "total_pnl": self.pnl,
            "win_rate": self.wins / self.total_trades if self.total_trades > 0 else 0,
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.1
        }
    
    def update_parameters(self, params):
        """更新策略参数"""
        self.config.update(params)
    
    def is_active(self):
        """检查策略是否激活"""
        return self.active


async def test_strategy_management():
    """测试策略管理功能"""
    logger.info("🧪 测试策略管理功能...")
    logger.info("=" * 50)
    
    # 1. 测试初始化策略管理器
    logger.info("1. 初始化策略管理器")
    config = {
        "switch_threshold": 0.05,
        "evaluation_period": 3600
    }
    strategy_manager = MultiStrategyManager(config)
    logger.info("✅ 策略管理器初始化成功")
    
    # 2. 测试添加策略
    logger.info("2. 测试添加策略")
    strategy1 = TestStrategy({"name": "RSI策略"})
    strategy2 = TestStrategy({"name": "MACD策略"})
    strategy3 = TestStrategy({"name": "布林带策略"})
    
    strategy_manager.add_strategy(strategy1)
    strategy_manager.add_strategy(strategy2)
    strategy_manager.add_strategy(strategy3)
    
    strategies = strategy_manager.get_all_strategies()
    logger.info(f"✅ 已添加策略: {strategies}")
    assert len(strategies) == 3, "策略添加失败"
    
    # 3. 测试激活策略
    logger.info("3. 测试激活策略")
    strategy_manager.activate_strategy("RSI策略")
    strategy_manager.activate_strategy("MACD策略")
    
    active_strategies = strategy_manager.get_active_strategies()
    logger.info(f"✅ 激活的策略: {active_strategies}")
    assert len(active_strategies) == 2, "策略激活失败"
    
    # 4. 测试停用策略
    logger.info("4. 测试停用策略")
    strategy_manager.deactivate_strategy("RSI策略")
    
    active_strategies = strategy_manager.get_active_strategies()
    logger.info(f"✅ 激活的策略: {active_strategies}")
    assert len(active_strategies) == 1, "策略停用失败"
    
    # 5. 测试策略参数更新
    logger.info("5. 测试策略参数更新")
    strategy_manager.update_strategy_parameters("MACD策略", {"fast_period": 12, "slow_period": 26})
    logger.info("✅ 策略参数更新成功")
    
    # 6. 测试策略性能评估
    logger.info("6. 测试策略性能评估")
    strategy_manager.evaluate_strategies()
    performance = strategy_manager.get_strategy_performance()
    logger.info(f"✅ 策略性能评估完成: {list(performance.keys())}")
    
    # 7. 测试生成交易信号
    logger.info("7. 测试生成交易信号")
    market_data = {
        "BTCUSDT": {
            "price": 50000.0,
            "volume": 1000000,
            "timestamp": "2024-01-01T00:00:00Z"
        }
    }
    signals = strategy_manager.generate_signals(market_data)
    logger.info(f"✅ 生成交易信号: {len(signals)} 个")
    assert len(signals) > 0, "交易信号生成失败"
    
    # 8. 测试获取最佳策略
    logger.info("8. 测试获取最佳策略")
    best_strategy = strategy_manager.get_best_strategy()
    logger.info(f"✅ 当前最佳策略: {best_strategy}")
    
    # 9. 测试移除策略
    logger.info("9. 测试移除策略")
    strategy_manager.remove_strategy("布林带策略")
    strategies = strategy_manager.get_all_strategies()
    logger.info(f"✅ 剩余策略: {strategies}")
    assert len(strategies) == 2, "策略移除失败"
    
    logger.info("=" * 50)
    logger.info("🎉 策略管理功能测试完成！")
    logger.info("✅ 所有测试通过")
    
    return True


if __name__ == "__main__":
    try:
        asyncio.run(test_strategy_management())
    except KeyboardInterrupt:
        print("\n👋 测试已停止")
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
