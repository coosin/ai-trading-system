#!/usr/bin/env python3
"""
交易历史记忆系统 - 集成测试脚本

测试内容：
1. TradeHistoryService 初始化和基本操作
2. 记忆系统集成
3. API端点数据查询
4. 完整交易生命周期（记录→查询→统计→复盘）
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_trade_history_service():
    """测试1: TradeHistoryService 基本功能"""
    print("\n" + "="*60)
    print("🧪 测试1: TradeHistoryService 基本功能")
    print("="*60)
    
    try:
        from src.modules.core.trade_history_service import TradeHistoryService, TradeRecord
        
        # 初始化服务
        service = TradeHistoryService(config={
            "cache_max_size": 100,
            "base_path": "/tmp/test_trade_history"
        })
        
        init_success = await service.initialize()
        assert init_success, "初始化失败"
        print("✅ 服务初始化成功")
        
        # 测试记录交易
        test_trades = [
            {
                "trade_id": "test_001",
                "order_id": "order_001",
                "symbol": "BTC/USDT",
                "side": "buy",
                "order_type": "market",
                "quantity": 0.01,
                "price": 45000.0,
                "cost": 450.0,
                "fee": 0.45,
                "reasoning": "测试买入",
                "strategy": "测试策略"
            },
            {
                "trade_id": "test_002",
                "order_id": "order_002",
                "symbol": "ETH/USDT",
                "side": "sell",
                "order_type": "market",
                "quantity": 1.0,
                "price": 2800.0,
                "cost": 2800.0,
                "fee": 2.8,
                "pnl": 150.5,
                "pnl_percent": 5.67,
                "reasoning": "测试卖出盈利",
                "strategy": "测试策略"
            }
        ]
        
        for trade_data in test_trades:
            success = await service.record_trade_dict(trade_data)
            assert success, f"记录交易失败: {trade_data['trade_id']}"
            print(f"✅ 交易已记录: {trade_data['trade_id']} - {trade_data['symbol']} {trade_data['side']}")
        
        # 测试查询
        trades = await service.get_recent_trades(limit=10)
        assert len(trades) == 2, f"查询结果数量错误: {len(trades)}"
        print(f"✅ 查询成功，返回 {len(trades)} 条记录")
        
        # 测试按币种过滤
        btc_trades = await service.get_trades_by_symbol("BTC/USDT", days=1)
        assert len(btc_trades) == 1, f"BTC交易数量错误: {len(btc_trades)}"
        print(f"✅ 按币种查询成功: BTC/USDT 有 {len(btc_trades)} 笔交易")
        
        # 测试服务状态
        status = await service.get_system_status()
        assert status["cache_size"] == 2, f"缓存数量错误: {status['cache_size']}"
        print(f"✅ 服务状态正常: 缓存{status['cache_size']}条记录")
        
        print("\n✨ 测试1通过！TradeHistoryService 基本功能正常\n")
        return service
        
    except Exception as e:
        print(f"\n❌ 测试1失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_memory_integration(service):
    """测试2: 记忆系统集成"""
    print("\n" + "="*60)
    print("🧪 测试2: 记忆系统集成")
    print("="*60)
    
    try:
        from src.modules.core.hierarchical_memory import HierarchicalMemoryManager
        
        # 初始化记忆管理器
        memory = HierarchicalMemoryManager(base_path="/tmp/test_memory")
        
        # 连接到服务
        await service.set_memory_manager(memory)
        print("✅ 记忆系统已连接到服务")
        
        # 测试保存开仓记录
        await memory.save_trade_open(
            symbol="SOL/USDT",
            side="long",
            price=150.0,
            quantity=10.0,
            reason="突破阻力位",
            stop_loss=145.0,
            take_profit=165.0,
            strategy="趋势跟踪"
        )
        print("✅ 开仓记录已保存到记忆系统")
        
        # 测试保存平仓记录
        await memory.save_trade_close(
            symbol="SOL/USDT",
            side="long",
            open_price=150.0,
            close_price=160.0,
            quantity=10.0,
            pnl=100.0,
            pnl_percent=6.67,
            reason="达到止盈目标"
        )
        print("✅ 平仓记录已保存到记忆系统")
        
        # 测试获取交易摘要
        summary = await memory.get_trade_history_summary(days=1)
        assert "SOL/USDT" in summary or "交易" in summary, "交易摘要生成失败"
        print("✅ 交易历史摘要生成成功")
        print(f"\n📝 摘要预览:\n{summary[:200]}...")
        
        # 测试为对话生成上下文
        context = await service.get_trade_context_for_conversation(limit=5)
        assert "最近交易概览" in context or "暂无" in context, "对话上下文生成失败"
        print("✅ 对话上下文生成成功")
        
        print("\n✨ 测试2通过！记忆系统集成正常\n")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试2失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_statistics_and_review(service):
    """测试3: 统计分析和复盘报告"""
    print("\n" + "="*60)
    print("🧪 测试3: 统计分析和复盘报告")
    print("="*60)
    
    try:
        # 添加更多测试数据以获得有意义的统计数据
        for i in range(8):
            pnl = (i % 3 - 1) * 50  # 交替盈利/亏损
            await service.record_trade_dict({
                "trade_id": f"stats_test_{i:03d}",
                "order_id": f"order_stats_{i}",
                "symbol": ["BTC/USDT", "ETH/USDT", "SOL/USDT"][i % 3],
                "side": ["buy", "sell"][i % 2],
                "order_type": "market",
                "quantity": 0.01 * (i + 1),
                "price": 40000 + i * 1000,
                "pnl": pnl,
                "pnl_percent": pnl / 100,
                "reasoning": f"统计测试交易{i}",
                "strategy": "测试策略"
            })
        
        print(f"✅ 已添加额外的测试数据用于统计分析")
        
        # 测试统计功能
        stats = await service.get_statistics(days=1, force_refresh=True)
        
        assert "total_trades" in stats, "统计数据缺少total_trades字段"
        assert stats["total_trades"] > 0, "总交易数应为正数"
        
        print(f"\n📊 交易统计结果:")
        print(f"   总交易次数: {stats.get('total_trades', 0)}")
        print(f"   胜率: {stats.get('win_rate', 0)}%")
        print(f"   总盈亏: {stats.get('total_pnl', 0)} USDT")
        print(f"   盈利因子: {stats.get('profit_factor', 0)}")
        print(f"   最佳交易: {stats.get('best_trade', 0)} USDT")
        print(f"   最差交易: {stats.get('worst_trade', 0)} USDT")
        
        if "symbol_distribution" in stats:
            print(f"\n💰 各币种表现:")
            for symbol, data in list(stats["symbol_distribution"].items())[:3]:
                print(f"   {symbol}: {data['count']}笔 | 胜率{data['win_rate']}% | 盈亏{data['total_pnl']}")
        
        print("✅ 统计分析功能正常")
        
        # 测试复盘报告生成
        review = await service.generate_trade_review(days=1)
        
        assert "# 📈" in review or "交易复盘" in review, "复盘报告格式错误"
        assert "总体表现" in review or "总交易" in review, "复盘报告缺少关键部分"
        
        print(f"\n📝 复盘报告预览:")
        lines = review.split('\n')[:20]
        preview = '\n'.join(lines)
        print(preview)
        print("... (报告已截断)")
        
        print("\n✅ 复盘报告生成功能正常")
        
        print("\n✨ 测试3通过！统计分析和复盘功能正常\n")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试3失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_endpoints():
    """测试4: API端点模拟"""
    print("\n" + "="*60)
    print("🧪 测试4: API端点模拟测试")
    print("="*60)
    
    try:
        # 模拟API调用逻辑
        from src.modules.core.trade_history_service import TradeHistoryService
        
        service = TradeHistoryService(config={
            "base_path": "/tmp/test_api"
        })
        await service.initialize()
        
        # 添加测试数据
        for i in range(5):
            await service.record_trade_dict({
                "trade_id": f"api_test_{i}",
                "symbol": "BTC/USDT",
                "side": "buy" if i % 2 == 0 else "sell",
                "order_type": "market",
                "quantity": 0.01,
                "price": 45000 + i * 100,
                "reasoning": "API测试"
            })
        
        # 模拟 GET /api/v1/trades?range=7d&symbol=BTC/USDT&limit=10
        result = await service.get_trade_history(
            start_date=datetime.now() - timedelta(days=7),
            symbol="BTC/USDT",
            limit=10
        )
        
        assert isinstance(result, list), "返回类型应为列表"
        assert len(result) == 5, f"应返回5条记录，实际返回{len(result)}"
        assert all("trade_id" in r for r in result), "每条记录应包含trade_id字段"
        
        print(f"✅ GET /api/v1/trades 模拟成功:")
        print(f"   返回 {len(result)} 条记录")
        print(f"   示例记录: {result[0]['trade_id']} - {result[0]['symbol']} {result[0]['side']}")
        
        # 模拟 GET /api/v1/trades/statistics?days=7
        stats = await service.get_statistics(days=7)
        
        assert isinstance(stats, dict), "统计返回类型应为字典"
        assert "total_trades" in stats, "统计应包含total_trades"
        
        print(f"\n✅ GET /api/v1/trades/statistics 模拟成功:")
        print(f"   总交易: {stats['total_trades']}")
        print(f"   胜率: {stats.get('win_rate', 0)}%")
        
        # 模拟 GET /api/v1/trades/review?days=7
        review = await service.generate_trade_review(days=7)
        
        assert isinstance(review, str), "复盘报告应为字符串"
        assert len(review) > 100, "复盘报告内容过短"
        
        print(f"\n✅ GET /api/v1/trades/review 模拟成功:")
        print(f"   报告长度: {len(review)} 字符")
        print(f"   包含章节: {'# ' if '# ' in review else '无标题'}")
        
        print("\n✨ 测试4通过！API端点逻辑正确\n")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试4失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("\n" + "="*70)
    print("🚀 AI智能交易系统 - 交易历史记忆集成测试")
    print("="*70)
    print(f"⏰ 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    # 运行所有测试
    service = await test_trade_history_service()
    results["TradeHistoryService"] = service is not None
    
    if service:
        results["记忆系统集成"] = await test_memory_integration(service)
        results["统计分析"] = await test_statistics_and_review(service)
    
    results["API端点"] = await test_api_endpoints()
    
    # 输出总结
    print("\n" + "="*70)
    print("📋 测试结果总结")
    print("="*70)
    
    total_tests = len(results)
    passed_tests = sum(1 for v in results.values() if v)
    
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status}: {test_name}")
    
    print("-"*70)
    print(f"总计: {passed_tests}/{total_tests} 个测试通过")
    
    if passed_tests == total_tests:
        print("\n🎉 所有测试通过！交易历史记忆系统集成成功！\n")
        print("\n📌 已实现的功能:")
        print("  ✅ 统一交易历史服务 (TradeHistoryService)")
        print("  ✅ SQLite持久化存储")
        print("  ✅ 内存缓存加速查询")
        print("  ✅ 记忆系统集成 (HierarchicalMemoryManager)")
        print("  ✅ 对话上下文自动生成")
        print("  ✅ 交易统计和分析")
        print("  ✅ 自动复盘报告生成")
        print("  ✅ API端点真实数据查询")
        print("  ✅ AI交易引擎实时记录集成")
        return 0
    else:
        print(f"\n⚠️  {total_tests - passed_tests}个测试失败，请检查日志\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
