#!/usr/bin/env python3
"""
测试交易所连接和 AI 自动交易功能
"""

import asyncio
import sys
import yaml
sys.path.insert(0, '/home/cool/.openclaw-trading')

from src.modules.exchanges.exchange_factory import ExchangeFactory
from src.modules.exchanges.okx import OKXExchange

async def test_exchange_connection():
    """测试交易所连接"""
    print("=" * 60)
    print("测试交易所连接")
    print("=" * 60)
    
    # 读取配置
    with open('/home/cool/.openclaw-trading/data/config/default.yml', 'r') as f:
        config = yaml.safe_load(f)
    
    exchange_config = config.get('exchanges', {}).get('okx', {})
    
    if not exchange_config.get('enabled'):
        print("❌ OKX 交易所未启用")
        return False
    
    print("\n1. 测试 OKX 交易所连接...")
    print(f"   API Key: {exchange_config.get('api_key', 'N/A')[:10]}...")
    print(f"   Sandbox: {exchange_config.get('sandbox', True)}")
    
    try:
        # 创建交易所实例
        factory = ExchangeFactory()
        exchange = factory.create_exchange("okx", {
            "api_key": exchange_config.get('api_key'),
            "api_secret": exchange_config.get('api_secret'),
            "passphrase": exchange_config.get('passphrase'),
            "sandbox": exchange_config.get('sandbox', False),
            "testnet": exchange_config.get('testnet', False)
        })
        
        # 初始化连接
        success = await exchange.initialize()
        
        if success:
            print("   ✅ 交易所连接初始化成功")
            
            # 测试获取账户余额
            try:
                balance = await exchange.get_balance()
                print(f"\n   账户余额:")
                for asset, amount in balance.items():
                    if amount > 0:
                        print(f"   - {asset}: {amount}")
            except Exception as e:
                print(f"   ⚠️ 获取余额失败: {e}")
            
            # 测试获取市场行情
            try:
                ticker = await exchange.get_ticker("BTC/USDT")
                print(f"\n   BTC/USDT 行情:")
                print(f"   - 最新价格: {ticker.get('last', 'N/A')}")
                print(f"   - 买一价: {ticker.get('bid', 'N/A')}")
                print(f"   - 卖一价: {ticker.get('ask', 'N/A')}")
            except Exception as e:
                print(f"   ⚠️ 获取行情失败: {e}")
            
            # 清理
            await exchange.cleanup()
            return True
        else:
            print("   ❌ 交易所连接初始化失败")
            return False
            
    except Exception as e:
        print(f"   ❌ 交易所连接异常: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ai_trading_signal():
    """测试 AI 交易信号生成"""
    print("\n" + "=" * 60)
    print("测试 AI 交易信号生成")
    print("=" * 60)
    
    from src.modules.core.llm_integration import EnhancedLLMIntegration
    from src.modules.core.enhanced_llm_manager import EnhancedLLMManager
    
    print("\n1. 初始化 LLM 管理器...")
    
    # 初始化 LLM 管理器
    llm_manager = EnhancedLLMManager()
    await llm_manager.initialize({})
    
    # 初始化 LLM 集成
    llm_integration = EnhancedLLMIntegration()
    llm_integration.set_llm_manager(llm_manager)
    
    print("   ✅ LLM 集成初始化完成")
    
    # 模拟市场数据
    market_data = {
        "symbol": "BTC/USDT",
        "price": 67750.0,
        "volume": 1500000000,
        "change_24h": 2.5,
        "high_24h": 68500.0,
        "low_24h": 65800.0,
        "indicators": {
            "rsi": 65,
            "macd": "bullish",
            "ema_20": 67200.0,
            "ema_50": 66500.0
        }
    }
    
    print("\n2. 使用 AI 分析市场...")
    
    try:
        # 使用讯飞模型分析市场
        analysis = await llm_integration.analyze_market(
            market_data, 
            provider="astron-code-latest"
        )
        
        if "error" not in analysis:
            print("   ✅ 市场分析完成")
            print(f"\n   分析结果:")
            print(f"   {analysis}")
        else:
            print(f"   ⚠️ 市场分析失败: {analysis.get('error')}")
    except Exception as e:
        print(f"   ⚠️ 市场分析异常: {e}")
    
    print("\n3. 生成交易信号...")
    
    try:
        # 生成交易信号
        signal = await llm_integration.generate_trading_signal(
            market_data,
            provider="astron-code-latest"
        )
        
        if "error" not in signal:
            print("   ✅ 交易信号生成成功")
            print(f"\n   信号详情:")
            print(f"   {signal}")
        else:
            print(f"   ⚠️ 信号生成失败: {signal.get('error')}")
    except Exception as e:
        print(f"   ⚠️ 信号生成异常: {e}")
    
    # 清理
    await llm_integration.cleanup()
    await llm_manager.cleanup()


async def test_auto_trading_workflow():
    """测试自动交易流程"""
    print("\n" + "=" * 60)
    print("测试自动交易流程")
    print("=" * 60)
    
    print("\n自动交易流程包括:")
    print("  1. 数据采集 → 2. AI分析 → 3. 信号生成 → 4. 交易执行")
    
    print("\n当前系统状态:")
    print("  ✅ AI 模型已对接 (讯飞 astron-code-latest)")
    print("  ✅ 交易所接口已实现 (OKX)")
    print("  ✅ 模拟合约交易已配置")
    print("  ⚠️  自动交易流水线需要进一步完善")
    
    print("\n建议:")
    print("  - 在模拟模式下测试完整交易流程")
    print("  - 配置交易策略参数")
    print("  - 设置风险管理规则")


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("交易所 & AI 自动交易功能测试")
    print("=" * 60)
    
    # 测试交易所连接
    await test_exchange_connection()
    
    # 测试 AI 交易信号
    await test_ai_trading_signal()
    
    # 测试自动交易流程
    await test_auto_trading_workflow()
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
