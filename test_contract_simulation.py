#!/usr/bin/env python3
"""
测试模拟合约交易功能
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from src.modules.simulation.contract_simulator import ContractSimulator


async def test_contract_simulation():
    """测试模拟合约交易"""
    
    print("=" * 60)
    print("测试模拟合约交易功能")
    print("=" * 60)
    
    # 配置
    config = {
        "initial_capital": 100000,
        "leverage": 10,
        "margin_mode": "cross",
        "contract_type": "perpetual",
        "fee_rate": {"maker": 0.0002, "taker": 0.0005},
        "symbols": ["BTC/USDT", "ETH/USDT"]
    }
    
    # 创建模拟器
    simulator = ContractSimulator(config)
    await simulator.initialize()
    
    try:
        # 设置初始价格
        simulator.update_price("BTC/USDT", 67750.0)
        simulator.update_price("ETH/USDT", 3450.0)
        
        print("\n1. 查看初始账户信息")
        account = simulator.get_account_info()
        print(f"   总权益: {account['total_equity']:.2f} USDT")
        print(f"   可用余额: {account['available_balance']:.2f} USDT")
        print(f"   杠杆: {account['leverage']}x")
        print(f"   保证金模式: {account['margin_mode']}")
        
        print("\n2. 开多仓 BTC/USDT")
        order1 = await simulator.place_order(
            symbol="BTC/USDT",
            side="long",
            size=0.1,
            order_type="market"
        )
        print(f"   订单ID: {order1.order_id}")
        print(f"   状态: {order1.status}")
        print(f"   成交价格: {order1.avg_fill_price:.2f}")
        print(f"   手续费: {order1.fee:.4f} USDT")
        
        # 更新价格
        simulator.update_price("BTC/USDT", 67800.0)
        
        print("\n3. 查看持仓")
        position = simulator.get_position("BTC/USDT")
        if position:
            print(f"   方向: {position.side.value}")
            print(f"   数量: {position.size} BTC")
            print(f"   开仓价格: {position.entry_price:.2f}")
            print(f"   当前价格: 67800.00")
            print(f"   未实现盈亏: {position.unrealized_pnl:.2f} USDT")
            print(f"   盈亏百分比: {position.pnl_percentage:.2f}%")
            print(f"   爆仓价格: {position.liquidation_price:.2f}")
        
        print("\n4. 开空仓 ETH/USDT")
        order2 = await simulator.place_order(
            symbol="ETH/USDT",
            side="short",
            size=1.0,
            order_type="market"
        )
        print(f"   订单ID: {order2.order_id}")
        print(f"   状态: {order2.status}")
        print(f"   成交价格: {order2.avg_fill_price:.2f}")
        
        # 更新价格
        simulator.update_price("ETH/USDT", 3440.0)
        
        print("\n5. 查看所有持仓")
        positions = simulator.get_all_positions()
        for pos in positions:
            print(f"   {pos.symbol}: {pos.side.value}, 数量: {pos.size}, 盈亏: {pos.unrealized_pnl:.2f} USDT")
        
        print("\n6. 查看账户信息")
        account = simulator.get_account_info()
        print(f"   总权益: {account['total_equity']:.2f} USDT")
        print(f"   可用余额: {account['available_balance']:.2f} USDT")
        print(f"   未实现盈亏: {account['unrealized_pnl']:.2f} USDT")
        print(f"   已实现盈亏: {account['realized_pnl']:.2f} USDT")
        print(f"   总手续费: {account['total_fee']:.4f} USDT")
        
        print("\n7. 平仓 BTC/USDT")
        close_order = await simulator.close_position("BTC/USDT")
        if close_order:
            print(f"   平仓订单ID: {close_order.order_id}")
            print(f"   成交价格: {close_order.avg_fill_price:.2f}")
        
        print("\n8. 查看交易统计")
        stats = simulator.get_trading_stats()
        print(f"   总订单数: {stats['total_orders']}")
        print(f"   成交订单数: {stats['filled_orders']}")
        print(f"   做多订单: {stats['long_orders']}")
        print(f"   做空订单: {stats['short_orders']}")
        print(f"   总手续费: {stats['total_fee']:.4f} USDT")
        print(f"   总盈亏: {stats['total_pnl']:.2f} USDT")
        print(f"   收益率: {stats['roi']:.2f}%")
        
        print("\n9. 查看最终账户信息")
        account = simulator.get_account_info()
        print(f"   总权益: {account['total_equity']:.2f} USDT")
        print(f"   可用余额: {account['available_balance']:.2f} USDT")
        print(f"   持仓数量: {account['positions_count']}")
        
        print("\n" + "=" * 60)
        print("✅ 模拟合约交易测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await simulator.cleanup()


if __name__ == "__main__":
    asyncio.run(test_contract_simulation())
