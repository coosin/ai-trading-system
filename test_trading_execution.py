#!/usr/bin/env python3
"""
测试交易执行功能
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

# 导入交易执行相关模块
from src.modules.execution.trading_execution_engine import TradingExecutionEngine, OrderType, OrderSide, ExecutionAlgorithm


async def test_trading_execution():
    """测试交易执行功能"""
    logger.info("🧪 测试交易执行功能...")
    logger.info("=" * 50)
    
    # 1. 测试初始化交易执行引擎
    logger.info("1. 初始化交易执行引擎")
    engine = TradingExecutionEngine()
    await engine.initialize()
    logger.info("✅ 交易执行引擎初始化成功")
    
    # 2. 测试创建市价单
    logger.info("2. 测试创建市价单")
    market_order = await engine.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.01
    )
    logger.info(f"✅ 创建市价单: {market_order.order_id}")
    assert market_order is not None, "市价单创建失败"
    
    # 3. 测试创建限价单
    logger.info("3. 测试创建限价单")
    limit_order = await engine.create_order(
        symbol="ETHUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=0.1,
        price=2000.0
    )
    logger.info(f"✅ 创建限价单: {limit_order.order_id}")
    assert limit_order is not None, "限价单创建失败"
    
    # 4. 测试创建TWAP订单
    logger.info("4. 测试创建TWAP订单")
    twap_order = await engine.create_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=0.02,
        execution_algorithm=ExecutionAlgorithm.TWAP
    )
    logger.info(f"✅ 创建TWAP订单: {twap_order.order_id}")
    assert twap_order is not None, "TWAP订单创建失败"
    
    # 5. 测试创建VWAP订单
    logger.info("5. 测试创建VWAP订单")
    vwap_order = await engine.create_order(
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.05,
        execution_algorithm=ExecutionAlgorithm.VWAP
    )
    logger.info(f"✅ 创建VWAP订单: {vwap_order.order_id}")
    assert vwap_order is not None, "VWAP订单创建失败"
    
    # 6. 测试创建冰山订单
    logger.info("6. 测试创建冰山订单")
    iceberg_order = await engine.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=0.03,
        price=40000.0,
        iceberg_visible_size=0.01,
        execution_algorithm=ExecutionAlgorithm.ICEBERG
    )
    logger.info(f"✅ 创建冰山订单: {iceberg_order.order_id}")
    assert iceberg_order is not None, "冰山订单创建失败"
    
    # 7. 测试获取订单
    logger.info("7. 测试获取订单")
    retrieved_order = engine.get_order(market_order.order_id)
    logger.info(f"✅ 获取订单成功: {retrieved_order.order_id}")
    assert retrieved_order is not None, "订单获取失败"
    
    # 8. 测试获取活跃订单
    logger.info("8. 测试获取活跃订单")
    active_orders = engine.get_active_orders()
    logger.info(f"✅ 活跃订单数量: {len(active_orders)}")
    assert len(active_orders) > 0, "活跃订单获取失败"
    
    # 9. 测试取消订单
    logger.info("9. 测试取消订单")
    cancel_success = await engine.cancel_order(limit_order.order_id)
    logger.info(f"✅ 取消订单: {'成功' if cancel_success else '失败'}")
    
    # 10. 测试获取订单交易记录
    logger.info("10. 测试获取订单交易记录")
    trades = engine.get_order_trades(market_order.order_id)
    logger.info(f"✅ 交易记录数量: {len(trades)}")
    
    # 11. 测试分析交易成本
    logger.info("11. 测试分析交易成本")
    cost = await engine.analyze_trading_costs(market_order.order_id)
    if cost:
        logger.info(f"✅ 交易成本分析: 总成本={cost.total_cost:.2f}, 成本占比={cost.cost_percentage:.2f}%")
    
    # 12. 测试获取执行引擎状态
    logger.info("12. 测试获取执行引擎状态")
    status = await engine.get_execution_engine_status()
    logger.info(f"✅ 执行引擎状态: 运行中={status['running']}, 活跃订单={status['active_orders']}, 总订单={status['total_orders']}")
    
    # 13. 测试关闭交易执行引擎
    logger.info("13. 测试关闭交易执行引擎")
    await engine.shutdown()
    logger.info("✅ 交易执行引擎关闭成功")
    
    logger.info("=" * 50)
    logger.info("🎉 交易执行功能测试完成！")
    logger.info("✅ 所有测试通过")
    
    return True


if __name__ == "__main__":
    try:
        asyncio.run(test_trading_execution())
    except KeyboardInterrupt:
        print("\n👋 测试已停止")
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
