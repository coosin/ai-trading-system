#!/usr/bin/env python3
"""
测试风险管理功能
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

# 导入风险管理相关模块
from src.modules.risk.资金管理模块 import MoneyManager, RiskLevel


async def test_risk_management():
    """测试风险管理功能"""
    logger.info("🧪 测试风险管理功能...")
    logger.info("=" * 50)
    
    # 1. 测试初始化资金管理器
    logger.info("1. 初始化资金管理器")
    config = {
        "risk_level": "medium",
        "max_drawdown_limit": 0.1,
        "max_position_size": 0.3,
        "max_leverage": 3.0,
        "risk_per_trade": 0.02,
        "stop_loss_pct": 0.03,
        "take_profit_pct": 0.06,
        "initial_equity": 10000
    }
    money_manager = MoneyManager(config)
    logger.info("✅ 资金管理器初始化成功")
    
    # 2. 测试计算仓位大小
    logger.info("2. 测试计算仓位大小")
    position_size = money_manager.calculate_position_size("BTCUSDT", 50000, 48500)  # 3% stop loss
    logger.info(f"✅ 计算的仓位大小: {position_size:.4f}")
    assert position_size > 0, "仓位大小计算失败"
    
    # 3. 测试添加仓位
    logger.info("3. 测试添加仓位")
    money_manager.add_position("BTCUSDT", "long", position_size, 50000)
    positions = money_manager.get_positions()
    logger.info(f"✅ 已添加仓位: {list(positions.keys())}")
    assert len(positions) == 1, "仓位添加失败"
    
    # 4. 测试更新仓位
    logger.info("4. 测试更新仓位")
    money_manager.update_position("BTCUSDT", 51000)  # 价格上涨
    position = positions["BTCUSDT"]
    logger.info(f"✅ 仓位更新成功，当前价格: {position.current_price}, PnL: {position.pnl:.2f}")
    
    # 5. 测试更新投资组合
    logger.info("5. 测试更新投资组合")
    portfolio = money_manager.get_portfolio_info()
    money_manager.update_portfolio(10200, portfolio.margin_used)
    new_portfolio = money_manager.get_portfolio_info()
    logger.info(f"✅ 投资组合更新成功，总权益: {new_portfolio.total_equity}")
    
    # 6. 测试风险指标计算
    logger.info("6. 测试风险指标计算")
    var = money_manager.calculate_var()
    sharpe = money_manager.calculate_sharpe_ratio()
    risk_metrics = money_manager.get_risk_metrics()
    logger.info(f"✅ 风险指标计算完成: VaR={var:.2f}, Sharpe={sharpe:.2f}")
    
    # 7. 测试风险等级调整
    logger.info("7. 测试风险等级调整")
    money_manager.adjust_risk_level(RiskLevel.HIGH)
    logger.info("✅ 风险等级调整成功")
    
    # 8. 测试风险调整建议
    logger.info("8. 测试风险调整建议")
    recommendations = money_manager.get_risk_adjustment_recommendations()
    logger.info(f"✅ 风险调整建议: {len(recommendations)} 条")
    
    # 9. 测试检查风险是否超过限制
    logger.info("9. 测试检查风险是否超过限制")
    is_risk_exceeded = money_manager.is_risk_exceeded()
    logger.info(f"✅ 风险检查完成: {'风险超过限制' if is_risk_exceeded else '风险在限制范围内'}")
    
    # 10. 测试关闭仓位
    logger.info("10. 测试关闭仓位")
    money_manager.close_position("BTCUSDT")
    positions = money_manager.get_positions()
    logger.info(f"✅ 仓位关闭成功，剩余仓位: {len(positions)}")
    assert len(positions) == 0, "仓位关闭失败"
    
    # 11. 测试资金曲线和回撤曲线
    logger.info("11. 测试资金曲线和回撤曲线")
    equity_curve = money_manager.get_equity_curve()
    drawdown_curve = money_manager.get_drawdown_curve()
    logger.info(f"✅ 资金曲线长度: {len(equity_curve)}, 回撤曲线长度: {len(drawdown_curve)}")
    
    # 12. 测试止盈止损信号
    logger.info("12. 测试止盈止损信号")
    # 添加一个新仓位
    position_size = money_manager.calculate_position_size("ETHUSDT", 3000, 2910)
    money_manager.add_position("ETHUSDT", "long", position_size, 3000)
    
    # 测试止损信号
    money_manager.update_position("ETHUSDT", 2910)  # 达到止损价格
    signal = money_manager.get_adjustment_signal("ETHUSDT")
    logger.info(f"✅ 止损信号: {signal}")
    assert signal is not None, "止损信号生成失败"
    
    # 测试止盈信号
    money_manager.update_position("ETHUSDT", 3180)  # 达到止盈价格
    signal = money_manager.get_adjustment_signal("ETHUSDT")
    logger.info(f"✅ 止盈信号: {signal}")
    assert signal is not None, "止盈信号生成失败"
    
    # 清理
    money_manager.close_position("ETHUSDT")
    
    logger.info("=" * 50)
    logger.info("🎉 风险管理功能测试完成！")
    logger.info("✅ 所有测试通过")
    
    return True


if __name__ == "__main__":
    try:
        asyncio.run(test_risk_management())
    except KeyboardInterrupt:
        print("\n👋 测试已停止")
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
