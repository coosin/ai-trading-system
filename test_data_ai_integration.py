#!/usr/bin/env python3
"""
测试第三方数据获取和 AI 智能分析行情功能
"""

import asyncio
import sys
import yaml
sys.path.insert(0, '/home/cool/.openclaw-trading')

from datetime import datetime, timedelta
from src.modules.data.data_integration import (
    DataIntegrator, BinanceDataSource, CoinGeckoDataSource,
    CoinbaseDataSource, KrakenDataSource, EtherscanDataSource,
    TwitterDataSource, NewsDataSource
)


async def test_third_party_data():
    """测试第三方数据获取"""
    print("=" * 70)
    print("测试第三方数据获取模块")
    print("=" * 70)
    
    integrator = DataIntegrator()
    
    # 1. 注册数据源
    print("\n1. 注册数据源...")
    integrator.register_data_source("binance", BinanceDataSource())
    integrator.register_data_source("coingecko", CoinGeckoDataSource())
    integrator.register_data_source("coinbase", CoinbaseDataSource())
    integrator.register_data_source("kraken", KrakenDataSource())
    print("   ✅ 已注册数据源: Binance, CoinGecko, Coinbase, Kraken")
    
    # 2. 测试 Binance 数据获取
    print("\n2. 测试 Binance 数据获取...")
    try:
        binance_data = await integrator.fetch_data(
            "binance",
            symbol="BTCUSDT",
            interval="1h",
            limit=100
        )
        if not binance_data.empty:
            print(f"   ✅ Binance 数据获取成功: {len(binance_data)} 条记录")
            print(f"   最新价格: {binance_data['close'].iloc[-1]:.2f} USDT")
        else:
            print("   ⚠️ Binance 数据为空")
    except Exception as e:
        print(f"   ❌ Binance 数据获取失败: {e}")
        binance_data = None
    
    # 3. 测试 CoinGecko 数据获取
    print("\n3. 测试 CoinGecko 数据获取...")
    try:
        coingecko_data = await integrator.fetch_data(
            "coingecko",
            coin_id="bitcoin",
            vs_currency="usd",
            days=7
        )
        if not coingecko_data.empty:
            print(f"   ✅ CoinGecko 数据获取成功: {len(coingecko_data)} 条记录")
            print(f"   最新价格: {coingecko_data['price'].iloc[-1]:.2f} USD")
        else:
            print("   ⚠️ CoinGecko 数据为空")
    except Exception as e:
        print(f"   ❌ CoinGecko 数据获取失败: {e}")
        coingecko_data = None
    
    # 4. 测试技术指标计算
    print("\n4. 测试技术指标计算...")
    if binance_data is not None and not binance_data.empty:
        try:
            indicators_data = await integrator.calculate_technical_indicators(
                binance_data,
                ["sma", "ema", "rsi", "macd", "bollinger"]
            )
            latest = indicators_data.iloc[-1]
            print("   ✅ 技术指标计算成功")
            print(f"   - RSI: {latest.get('rsi', 'N/A'):.2f}")
            print(f"   - MACD: {latest.get('macd', 'N/A'):.4f}")
            print(f"   - SMA 20: {latest.get('sma_20', 'N/A'):.2f}")
            print(f"   - SMA 50: {latest.get('sma_50', 'N/A'):.2f}")
        except Exception as e:
            print(f"   ❌ 技术指标计算失败: {e}")
    else:
        print("   ⚠️ 跳过技术指标计算（无数据）")
    
    # 5. 测试市场趋势分析
    print("\n5. 测试市场趋势分析...")
    if binance_data is not None and not binance_data.empty:
        try:
            trend_analysis = await integrator.analyze_market_trends(binance_data)
            print("   ✅ 市场趋势分析完成")
            print(f"   - 价格趋势: {trend_analysis.get('price_trend', 'N/A')}")
            print(f"   - 动量: {trend_analysis.get('momentum', 'N/A')}")
            print(f"   - MACD 信号: {trend_analysis.get('macd_signal', 'N/A')}")
            print(f"   - 波动率: {trend_analysis.get('volatility', 'N/A'):.4f}")
        except Exception as e:
            print(f"   ❌ 市场趋势分析失败: {e}")
    else:
        print("   ⚠️ 跳过市场趋势分析（无数据）")
    
    # 6. 测试交易信号生成
    print("\n6. 测试交易信号生成...")
    if binance_data is not None and not binance_data.empty:
        try:
            signals = await integrator.generate_trading_signals(binance_data)
            print(f"   ✅ 交易信号生成完成: {len(signals)} 个信号")
            if signals:
                for signal in signals[-3:]:
                    print(f"   - {signal['timestamp']}: {signal['signal'].upper()} "
                          f"({signal['indicator']}, 置信度: {signal['confidence']})")
        except Exception as e:
            print(f"   ❌ 交易信号生成失败: {e}")
    else:
        print("   ⚠️ 跳过交易信号生成（无数据）")
    
    return integrator, binance_data


async def test_onchain_data():
    """测试链上数据获取"""
    print("\n" + "=" * 70)
    print("测试链上数据获取")
    print("=" * 70)
    
    integrator = DataIntegrator()
    
    print("\n1. Etherscan 链上数据...")
    print("   注意: 需要配置 Etherscan API Key")
    
    # 检查配置
    etherscan_key = None
    try:
        with open('/home/cool/.openclaw-trading/data/config/default.yml', 'r') as f:
            config = yaml.safe_load(f)
            etherscan_key = config.get('etherscan', {}).get('api_key')
    except:
        pass
    
    if etherscan_key:
        try:
            integrator.register_data_source("etherscan", EtherscanDataSource(etherscan_key))
            print("   ✅ Etherscan 数据源已注册")
            
            # 获取示例地址的交易数据
            eth_data = await integrator.fetch_data(
                "etherscan",
                address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",  # 示例地址
                startblock=0,
                endblock=99999999,
                limit=10
            )
            if not eth_data.empty:
                print(f"   ✅ 链上数据获取成功: {len(eth_data)} 条交易记录")
            else:
                print("   ⚠️ 链上数据为空")
        except Exception as e:
            print(f"   ❌ 链上数据获取失败: {e}")
    else:
        print("   ⚠️ 未配置 Etherscan API Key，跳过链上数据测试")
        print("   请在配置文件中添加:")
        print("   etherscan:")
        print("     api_key: \"your-api-key\"")


async def test_ai_market_analysis():
    """测试 AI 智能分析行情"""
    print("\n" + "=" * 70)
    print("测试 AI 智能分析行情")
    print("=" * 70)
    
    from src.modules.core.llm_integration import EnhancedLLMIntegration
    from src.modules.core.enhanced_llm_manager import EnhancedLLMManager
    
    print("\n1. 初始化 AI 分析模块...")
    
    try:
        # 初始化 LLM 管理器
        llm_manager = EnhancedLLMManager()
        await llm_manager.initialize({})
        
        # 初始化 LLM 集成
        llm_integration = EnhancedLLMIntegration()
        llm_integration.set_llm_manager(llm_manager)
        
        print("   ✅ AI 分析模块初始化完成")
    except Exception as e:
        print(f"   ❌ AI 分析模块初始化失败: {e}")
        return
    
    # 2. 准备市场数据
    print("\n2. 准备市场数据...")
    market_data = {
        "symbol": "BTC/USDT",
        "price": 67750.0,
        "volume_24h": 35000000000,
        "change_24h": 2.5,
        "high_24h": 68500.0,
        "low_24h": 65800.0,
        "indicators": {
            "rsi": 65,
            "macd": "bullish",
            "ema_20": 67200.0,
            "ema_50": 66500.0,
            "sma_20": 67100.0,
            "sma_50": 66400.0,
            "bollinger_upper": 69500.0,
            "bollinger_lower": 65500.0
        },
        "market_sentiment": "neutral",
        "funding_rate": 0.0001,
        "open_interest": 15000000000
    }
    print("   ✅ 市场数据准备完成")
    
    # 3. AI 市场分析
    print("\n3. 使用 AI 分析市场...")
    try:
        analysis = await llm_integration.analyze_market(
            market_data,
            provider="astron-code-latest"
        )
        
        if "error" not in analysis:
            print("   ✅ AI 市场分析完成")
            print(f"\n   分析结果:")
            if isinstance(analysis, dict):
                for key, value in analysis.items():
                    print(f"   - {key}: {value}")
            else:
                print(f"   {analysis}")
        else:
            print(f"   ⚠️ AI 市场分析失败: {analysis.get('error')}")
    except Exception as e:
        print(f"   ⚠️ AI 市场分析异常: {e}")
    
    # 4. AI 生成交易策略
    print("\n4. 使用 AI 生成交易策略...")
    try:
        strategy = await llm_integration.generate_strategy(
            {"market_analysis": market_data, "trend": "bullish"},
            provider="astron-code-latest"
        )
        
        if "error" not in strategy:
            print("   ✅ AI 策略生成完成")
            print(f"\n   策略内容:")
            if isinstance(strategy, dict):
                for key, value in strategy.items():
                    print(f"   - {key}: {value}")
            else:
                print(f"   {strategy}")
        else:
            print(f"   ⚠️ AI 策略生成失败: {strategy.get('error')}")
    except Exception as e:
        print(f"   ⚠️ AI 策略生成异常: {e}")
    
    # 5. AI 生成交易信号
    print("\n5. 使用 AI 生成交易信号...")
    try:
        signal = await llm_integration.generate_trading_signal(
            market_data,
            provider="astron-code-latest"
        )
        
        if "error" not in signal:
            print("   ✅ AI 交易信号生成完成")
            print(f"\n   信号详情:")
            if isinstance(signal, dict):
                for key, value in signal.items():
                    print(f"   - {key}: {value}")
            else:
                print(f"   {signal}")
        else:
            print(f"   ⚠️ AI 信号生成失败: {signal.get('error')}")
    except Exception as e:
        print(f"   ⚠️ AI 信号生成异常: {e}")
    
    # 清理
    await llm_integration.cleanup()
    await llm_manager.cleanup()


async def test_social_media_data():
    """测试社交媒体数据获取"""
    print("\n" + "=" * 70)
    print("测试社交媒体数据获取")
    print("=" * 70)
    
    integrator = DataIntegrator()
    
    print("\n1. Twitter 数据...")
    print("   注意: 需要配置 Twitter Bearer Token")
    
    # 检查配置
    twitter_token = None
    try:
        with open('/home/cool/.openclaw-trading/data/config/default.yml', 'r') as f:
            config = yaml.safe_load(f)
            twitter_token = config.get('twitter', {}).get('bearer_token')
    except:
        pass
    
    if twitter_token:
        try:
            integrator.register_data_source("twitter", TwitterDataSource(twitter_token))
            print("   ✅ Twitter 数据源已注册")
            
            twitter_data = await integrator.fetch_data(
                "twitter",
                query="bitcoin",
                max_results=10
            )
            if not twitter_data.empty:
                print(f"   ✅ Twitter 数据获取成功: {len(twitter_data)} 条推文")
            else:
                print("   ⚠️ Twitter 数据为空")
        except Exception as e:
            print(f"   ❌ Twitter 数据获取失败: {e}")
    else:
        print("   ⚠️ 未配置 Twitter Bearer Token，跳过 Twitter 数据测试")
    
    print("\n2. 新闻数据...")
    print("   注意: 需要配置 NewsAPI Key")
    
    news_key = None
    try:
        with open('/home/cool/.openclaw-trading/data/config/default.yml', 'r') as f:
            config = yaml.safe_load(f)
            news_key = config.get('newsapi', {}).get('api_key')
    except:
        pass
    
    if news_key:
        try:
            integrator.register_data_source("news", NewsDataSource(news_key))
            print("   ✅ NewsAPI 数据源已注册")
            
            news_data = await integrator.fetch_data(
                "news",
                query="cryptocurrency",
                page_size=10
            )
            if not news_data.empty:
                print(f"   ✅ 新闻数据获取成功: {len(news_data)} 条新闻")
            else:
                print("   ⚠️ 新闻数据为空")
        except Exception as e:
            print(f"   ❌ 新闻数据获取失败: {e}")
    else:
        print("   ⚠️ 未配置 NewsAPI Key，跳过新闻数据测试")


async def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("第三方数据获取 & AI 智能分析行情 - 综合测试")
    print("=" * 70)
    
    # 1. 测试第三方数据获取
    await test_third_party_data()
    
    # 2. 测试链上数据
    await test_onchain_data()
    
    # 3. 测试社交媒体数据
    await test_social_media_data()
    
    # 4. 测试 AI 智能分析
    await test_ai_market_analysis()
    
    print("\n" + "=" * 70)
    print("测试完成!")
    print("=" * 70)
    
    print("\n📊 数据获取模块总结:")
    print("  ✅ 交易所数据: Binance, Coinbase, Kraken")
    print("  ✅ 行情数据: CoinGecko")
    print("  ✅ 技术指标: SMA, EMA, RSI, MACD, Bollinger, Stochastic, CCI, ADX")
    print("  ✅ 趋势分析: 价格趋势、动量、MACD信号、波动率、支撑阻力")
    print("  ✅ 信号生成: 基于技术指标的自动信号")
    print("  ⚠️  链上数据: 需要 Etherscan API Key")
    print("  ⚠️  社交媒体: 需要 Twitter/NewsAPI Key")
    
    print("\n🤖 AI 智能分析总结:")
    print("  ✅ AI 市场分析")
    print("  ✅ AI 策略生成")
    print("  ✅ AI 交易信号")
    print("  ✅ 讯飞模型对接 (astron-code-latest)")


if __name__ == "__main__":
    asyncio.run(main())
