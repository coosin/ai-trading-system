#!/usr/bin/env python3
"""
模拟交易环境使用示例

本示例展示如何使用系统的模拟交易环境进行策略测试和回测。
"""

import asyncio
import pandas as pd
from src.modules.main_controller import MainController
from src.modules.strategies.macd_strategy import MACDStrategy

async def main():
    # 初始化主控制器
    controller = MainController()
    await controller.initialize()
    
    print("=== 模拟交易环境使用示例 ===")
    
    # 1. 启动模拟市场
    print("\n1. 启动模拟市场")
    await controller.start_simulated_market()
    
    # 等待市场初始化
    await asyncio.sleep(2)
    
    # 2. 查看市场状态
    print("\n2. 查看市场状态")
    market_state = controller.get_simulated_market_state()
    print("市场状态:")
    print(f"交易对: {market_state.get('symbols')}")
    print(f"当前价格: {market_state.get('current_prices')}")
    print(f"市场运行时间: {market_state.get('uptime'):.2f}秒")
    
    # 3. 获取历史数据
    print("\n3. 获取历史数据")
    btc_data = controller.get_simulated_market_data("BTC/USDT", "1m", 100)
    eth_data = controller.get_simulated_market_data("ETH/USDT", "5m", 50)
    
    print(f"BTC/USDT 1分钟数据: {len(btc_data)}条")
    print(f"ETH/USDT 5分钟数据: {len(eth_data)}条")
    
    # 4. 测试策略
    print("\n4. 测试策略")
    
    # 创建策略实例
    macd_strategy = MACDStrategy({
        "symbol": "BTC/USDT",
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9
    })
    
    # 生成交易信号
    signals = macd_strategy.generate_signals({"BTC/USDT": btc_data})
    print(f"生成信号数量: {len(signals)}")
    
    # 5. 执行模拟交易
    print("\n5. 执行模拟交易")
    
    trades = []
    for i, signal in enumerate(signals):
        if signal['signal'] != 0:
            side = "buy" if signal['signal'] == 1 else "sell"
            execution = controller.execute_simulated_order(
                "BTC/USDT",
                side,
                0.01
            )
            trades.append(execution)
            print(f"交易 {i+1}: {side} 0.01 BTC/USDT at {execution['price']:.2f}")
    
    print(f"执行交易数量: {len(trades)}")
    
    # 6. 调整市场参数
    print("\n6. 调整市场参数")
    
    # 增加波动率
    controller.set_simulated_market_parameters(volatility=0.05)
    print("已将市场波动率设置为 0.05")
    
    # 等待市场反应
    await asyncio.sleep(3)
    
    # 查看调整后的价格
    new_price = controller.get_simulated_market().get_price("BTC/USDT")
    print(f"调整后BTC价格: {new_price:.2f}")
    
    # 7. 回测策略
    print("\n7. 回测策略")
    
    # 重置市场
    controller.reset_simulated_market()
    print("已重置模拟市场")
    
    # 生成新的历史数据
    await asyncio.sleep(5)
    backtest_data = controller.get_simulated_market_data("BTC/USDT", "1m", 200)
    
    # 运行回测
    backtest_result = await controller.run_multi_strategy_backtest(
        {
            "macd": macd_strategy
        },
        {
            "BTC/USDT": backtest_data
        }
    )
    
    print("回测结果:")
    print(f"总收益: {backtest_result.get('total_return'):.2f}")
    print(f"夏普比率: {backtest_result.get('sharpe_ratio'):.2f}")
    print(f"最大回撤: {backtest_result.get('max_drawdown'):.2f}")
    print(f"胜率: {backtest_result.get('win_rate'):.2f}")
    print(f"总交易次数: {backtest_result.get('total_trades')}")
    
    # 8. 停止模拟市场
    print("\n8. 停止模拟市场")
    await controller.stop_simulated_market()
    
    # 9. 清理
    print("\n9. 清理资源")
    await controller.cleanup()
    
    print("模拟交易环境使用示例完成！")

if __name__ == "__main__":
    asyncio.run(main())