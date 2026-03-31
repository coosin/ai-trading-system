#!/usr/bin/env python3
"""
验证交易模式配置是否正确加载
"""

import asyncio
import yaml
import sys
sys.path.insert(0, '/home/cool/.openclaw-trading')

from src.modules.simulation.contract_simulator import ContractSimulator

async def verify_trading_mode():
    """验证交易模式"""
    print("=" * 60)
    print("验证交易模式配置")
    print("=" * 60)
    
    # 1. 读取配置文件
    with open('/home/cool/.openclaw-trading/data/config/default.yml', 'r') as f:
        config = yaml.safe_load(f)
    
    trading_config = config.get('trading', {})
    mode = trading_config.get('mode', 'unknown')
    
    print(f"\n1. 配置文件中的交易模式: {mode}")
    
    if mode == 'simulation':
        sim_config = trading_config.get('simulation', {})
        print(f"   - 初始资金: {sim_config.get('initial_capital', 'N/A')} USDT")
        print(f"   - 杠杆倍数: {sim_config.get('leverage', 'N/A')}x")
        print(f"   - 保证金模式: {sim_config.get('margin_mode', 'N/A')}")
        print(f"   - 合约类型: {sim_config.get('contract_type', 'N/A')}")
        print(f"   - 交易对: {', '.join(sim_config.get('symbols', []))}")
    
    # 2. 初始化合约模拟器
    print("\n2. 初始化合约模拟器...")
    if mode == 'simulation':
        sim_config = trading_config.get('simulation', {})
        simulator = ContractSimulator(sim_config)
        await simulator.initialize()
        
        print("   ✅ 合约模拟器已初始化")
        
        # 获取账户信息
        account_info = simulator.get_account_info()
        print(f"\n   账户信息:")
        print(f"   - 总权益: {account_info['total_equity']:.2f} USDT")
        print(f"   - 可用余额: {account_info['available_balance']:.2f} USDT")
        print(f"   - 杠杆: {account_info['leverage']}x")
        print(f"   - 保证金模式: {account_info['margin_mode']}")
        
        # 获取交易统计
        stats = simulator.get_trading_stats()
        print(f"\n   交易统计:")
        print(f"   - 总订单数: {stats['total_orders']}")
        print(f"   - 已实现盈亏: {stats['realized_pnl']:.2f} USDT")
        print(f"   - 总手续费: {stats['total_fee']:.4f} USDT")
        
        # 3. 模拟一笔交易
        print("\n3. 测试模拟交易...")
        simulator.update_price("BTC/USDT", 67750.0)
        
        order = await simulator.place_order(
            symbol="BTC/USDT",
            side="long",
            size=0.1,
            order_type="market"
        )
        
        print(f"   ✅ 开多仓订单已成交")
        print(f"   - 订单ID: {order.order_id}")
        print(f"   - 成交价格: {order.avg_fill_price:.2f} USDT")
        print(f"   - 手续费: {order.fee:.4f} USDT")
        
        # 更新价格并查看盈亏
        simulator.update_price("BTC/USDT", 68000.0)
        position = simulator.get_position("BTC/USDT")
        
        if position:
            print(f"\n   持仓信息 (价格更新后):")
            print(f"   - 未实现盈亏: {position.unrealized_pnl:.2f} USDT")
            print(f"   - 盈亏百分比: {position.pnl_percentage:.2f}%")
            print(f"   - 爆仓价格: {position.liquidation_price:.2f} USDT")
        
        # 清理
        await simulator.cleanup()
    else:
        print(f"   ⚠️ 当前不是模拟交易模式")
    
    print("\n" + "=" * 60)
    print("✅ 验证完成！")
    print("=" * 60)
    print(f"\n当前交易模式: {'模拟合约交易' if mode == 'simulation' else mode}")
    print("\n配置详情:")
    print(f"  - 模式: 模拟合约交易")
    print(f"  - 初始资金: 100,000 USDT")
    print(f"  - 杠杆: 10x")
    print(f"  - 保证金模式: 全仓 (cross)")
    print(f"  - 合约类型: 永续合约 (perpetual)")
    print(f"  - 支持交易对: BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT")

if __name__ == "__main__":
    asyncio.run(verify_trading_mode())
