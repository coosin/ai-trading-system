#!/usr/bin/env python3
"""
测试OKX交易所连接
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from src.modules.exchanges.okx import OKXExchange

async def test_okx():
    """测试OKX交易所"""
    # OKX配置
    config = {
        "exchange_id": "okx",
        "api_key": "bf73ac3f-6552-48b0-99dd-f279bf47b336",
        "api_secret": "8A550FDA562D66523D175599D8166BE1",
        "api_passphrase": "Cool+095136",
        "testnet": False
    }
    
    print("=" * 60)
    print("测试OKX交易所连接")
    print("=" * 60)
    
    # 创建交易所实例
    exchange = OKXExchange(config)
    
    try:
        # 初始化
        print("\n1. 初始化交易所...")
        success = await exchange.initialize()
        if not success:
            print("❌ 初始化失败")
            return
        print("✅ 初始化成功")
        
        # 获取交易所信息
        print("\n2. 获取交易所信息...")
        exchange_info = await exchange.get_exchange_info()
        print(f"✅ 交易所: {exchange_info.name}")
        print(f"   支持的交易对数量: {len(exchange_info.supported_symbols)}")
        if len(exchange_info.supported_symbols) > 0:
            print(f"   前5个交易对: {exchange_info.supported_symbols[:5]}")
        
        # 获取BTC/USDT市场数据
        print("\n3. 获取BTC/USDT市场数据...")
        market_data = await exchange.get_market_data("BTC/USDT", "1m")
        if market_data:
            print(f"✅ 时间: {market_data.timestamp}")
            print(f"   开盘: {market_data.open}")
            print(f"   最高: {market_data.high}")
            print(f"   最低: {market_data.low}")
            print(f"   收盘: {market_data.close}")
            print(f"   成交量: {market_data.volume}")
        else:
            print("❌ 获取市场数据失败")
        
        # 获取订单簿
        print("\n4. 获取BTC/USDT订单簿...")
        order_book = await exchange.get_order_book("BTC/USDT", 5)
        if order_book:
            print(f"✅ 时间: {order_book.timestamp}")
            print(f"   卖单（前3个）:")
            for i, (price, qty) in enumerate(order_book.asks[:3]):
                print(f"     {i+1}. 价格: {price}, 数量: {qty}")
            print(f"   买单（前3个）:")
            for i, (price, qty) in enumerate(order_book.bids[:3]):
                print(f"     {i+1}. 价格: {price}, 数量: {qty}")
        else:
            print("❌ 获取订单簿失败")
        
        # 获取资产余额
        print("\n5. 获取资产余额...")
        balances = await exchange.get_balances()
        if balances:
            print(f"✅ 找到 {len(balances)} 个资产:")
            for balance in balances[:10]:  # 只显示前10个
                if balance.total > 0:
                    print(f"   {balance.asset}: 可用 {balance.free}, 冻结 {balance.locked}, 总计 {balance.total}")
        else:
            print("ℹ️  没有找到资产余额")
        
        # 获取交易对信息
        print("\n6. 获取BTC/USDT交易对信息...")
        symbol_info = await exchange.get_symbol_info("BTC/USDT")
        if symbol_info:
            print(f"✅ 交易对: {symbol_info['symbol']}")
            print(f"   基础货币: {symbol_info['base_currency']}")
            print(f"   计价货币: {symbol_info['quote_currency']}")
            print(f"   最小订单量: {symbol_info['min_order_size']}")
            print(f"   最大订单量: {symbol_info['max_order_size']}")
            print(f"   价格精度: {symbol_info['price_precision']}")
        else:
            print("❌ 获取交易对信息失败")
        
        print("\n" + "=" * 60)
        print("✅ 所有测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理
        print("\n清理资源...")
        await exchange.cleanup()
        print("✅ 清理完成")

if __name__ == "__main__":
    asyncio.run(test_okx())
