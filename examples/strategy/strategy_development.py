#!/usr/bin/env python3
"""
策略开发示例

本示例展示如何使用系统的策略模板和参数优化功能来开发和优化交易策略。
"""

import asyncio
import pandas as pd
from src.modules.main_controller import MainController
from src.modules.strategies.macd_strategy import MACDStrategy
from src.modules.strategies.bb_strategy import BBStrategy

async def main():
    # 初始化主控制器
    controller = MainController()
    await controller.initialize()
    
    print("=== 策略开发示例 ===")
    
    # 1. 创建策略实例
    print("\n1. 创建策略实例")
    macd_strategy = MACDStrategy({
        "symbol": "BTC/USDT",
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9
    })
    
    bb_strategy = BBStrategy({
        "symbol": "ETH/USDT",
        "period": 20,
        "std_dev": 2.0
    })
    
    # 添加策略到策略管理器
    await controller.add_strategy(macd_strategy)
    await controller.add_strategy(bb_strategy)
    
    print(f"已添加策略: MACD, Bollinger Bands")
    
    # 2. 模拟市场数据
    print("\n2. 生成模拟市场数据")
    # 启动模拟市场
    await controller.start_simulated_market()
    
    # 等待市场数据生成
    await asyncio.sleep(5)
    
    # 获取模拟市场数据
    btc_data = controller.get_simulated_market_data("BTC/USDT", "1m", 100)
    eth_data = controller.get_simulated_market_data("ETH/USDT", "1m", 100)
    
    print(f"获取BTC数据: {len(btc_data)}条")
    print(f"获取ETH数据: {len(eth_data)}条")
    
    # 3. 策略参数优化
    print("\n3. 策略参数优化")
    
    # 定义参数空间
    param_space = {
        "fast_period": [10, 12, 14],
        "slow_period": [20, 26, 30],
        "signal_period": [8, 9, 10]
    }
    
    # 运行参数优化
    optimization_result = await controller.optimize_strategy_parameters(
        "macd",
        "grid_search",
        param_space,
        btc_data
    )
    
    print("参数优化结果:")
    print(f"最佳参数: {optimization_result.get('best_params')}")
    print(f"最佳性能: {optimization_result.get('best_score')}")
    
    # 4. 策略评估
    print("\n4. 策略评估")
    
    # 模拟策略交易
    macd_signals = macd_strategy.generate_signals({"BTC/USDT": btc_data})
    bb_signals = bb_strategy.generate_signals({"ETH/USDT": eth_data})
    
    # 模拟交易执行
    trades = []
    for signal in macd_signals:
        if signal['signal'] != 0:
            side = "buy" if signal['signal'] == 1 else "sell"
            execution = controller.execute_simulated_order(
                "BTC/USDT",
                side,
                0.01
            )
            trades.append(execution)
    
    # 评估策略性能
    returns = [trade['price'] * trade['size'] for trade in trades]
    evaluation = await controller.evaluate_strategy("macd", returns, trades)
    
    print("策略评估报告:")
    print(f"总收益: {evaluation.get('total_return'):.2f}")
    print(f"年化收益: {evaluation.get('annual_return'):.2f}")
    print(f"夏普比率: {evaluation.get('sharpe_ratio'):.2f}")
    print(f"最大回撤: {evaluation.get('max_drawdown'):.2f}")
    print(f"胜率: {evaluation.get('win_rate'):.2f}")
    
    # 5. 策略组合
    print("\n5. 策略组合优化")
    
    # 准备策略数据
    strategies_data = {
        "macd": {
            "returns": returns,
            "volatility": 0.02,
            "correlation": 0.5
        },
        "bb": {
            "returns": [trade['price'] * trade['size'] for trade in trades],
            "volatility": 0.015,
            "correlation": 0.5
        }
    }
    
    # 运行风险平价优化
    risk_parity_weights = await controller.optimize_portfolio("risk_parity", strategies_data)
    print("风险平价优化权重:")
    print(risk_parity_weights)
    
    # 运行均值方差优化
    mean_variance_weights = await controller.optimize_portfolio("mean_variance", strategies_data)
    print("均值方差优化权重:")
    print(mean_variance_weights)
    
    # 6. 清理
    print("\n6. 清理资源")
    await controller.stop_simulated_market()
    await controller.cleanup()
    
    print("策略开发示例完成！")

if __name__ == "__main__":
    asyncio.run(main())