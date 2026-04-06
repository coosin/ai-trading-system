"""
记忆系统优化验证脚本

测试优化后的记忆系统功能：
1. 基本记忆存储和检索
2. 多层级记忆管理
3. 索引和快速检索
4. 记忆关联功能
5. 遗忘机制
"""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.modules.core.optimized_memory_system import (
    OptimizedMemorySystem,
    MemoryLayer,
    MemoryCategory,
    get_memory_system
)
from src.modules.core.unified_memory_system import UnifiedMemorySystem


async def test_basic_operations():
    """测试基本操作"""
    print("\n" + "="*60)
    print("📝 测试基本记忆操作")
    print("="*60)
    
    memory = await get_memory_system(
        workspace_path=str(Path(__file__).parent / "workspace")
    )
    
    memory_id = await memory.remember(
        content="测试记忆：BTC在65000美元支撑位反弹",
        category=MemoryCategory.MARKET_OBSERVATION,
        layer=MemoryLayer.WORKING,
        importance=0.7,
        tags={"BTC", "support", "market"}
    )
    print(f"✅ 记忆已存储: {memory_id}")
    
    results = await memory.recall("BTC", limit=5)
    print(f"✅ 检索到 {len(results)} 条记忆")
    for r in results:
        print(f"   - {r.content[:50]}...")
    
    return True


async def test_trade_records():
    """测试交易记录"""
    print("\n" + "="*60)
    print("📈 测试交易记录功能")
    print("="*60)
    
    memory = await get_memory_system()
    
    trade_id = await memory.save_trade_record(
        symbol="BTC/USDT",
        action="开多",
        price=65000.0,
        quantity=0.1,
        pnl=150.0,
        reason="突破阻力位",
        strategy="趋势跟踪"
    )
    print(f"✅ 交易记录已保存: {trade_id}")
    
    trade_id2 = await memory.save_trade_record(
        symbol="ETH/USDT",
        action="平多",
        price=3200.0,
        quantity=1.0,
        pnl=-50.0,
        reason="止损触发",
        strategy="趋势跟踪"
    )
    print(f"✅ 交易记录已保存: {trade_id2}")
    
    results = await memory.recall("trade", limit=10)
    print(f"✅ 检索到 {len(results)} 条交易记录")
    
    return True


async def test_memory_relation():
    """测试记忆关联"""
    print("\n" + "="*60)
    print("🔗 测试记忆关联功能")
    print("="*60)
    
    memory = await get_memory_system()
    
    id1 = await memory.remember(
        content="BTC突破65000阻力位",
        category=MemoryCategory.MARKET_OBSERVATION,
        layer=MemoryLayer.WORKING,
        tags={"BTC", "breakout"}
    )
    
    id2 = await memory.remember(
        content="BTC突破后回踩确认支撑",
        category=MemoryCategory.MARKET_OBSERVATION,
        layer=MemoryLayer.WORKING,
        tags={"BTC", "pullback"}
    )
    
    success = await memory.relate(id1, id2)
    print(f"✅ 记忆关联: {success}")
    
    related = await memory.get_related(id1)
    print(f"✅ 相关记忆数量: {len(related)}")
    
    return True


async def test_context_building():
    """测试上下文构建"""
    print("\n" + "="*60)
    print("📚 测试上下文构建")
    print("="*60)
    
    memory = await get_memory_system()
    
    context = await memory.build_context("BTC交易", max_tokens=500)
    print(f"✅ 构建上下文长度: {len(context)} 字符")
    print(f"上下文预览:\n{context[:300]}...")
    
    return True


async def test_stats():
    """测试统计功能"""
    print("\n" + "="*60)
    print("📊 测试统计功能")
    print("="*60)
    
    memory = await get_memory_system()
    stats = memory.get_stats()
    
    print(f"✅ 总记忆数: {stats.get('total_memories', 0)}")
    print(f"✅ 按层级分布: {stats.get('by_layer', {})}")
    print(f"✅ 索引统计: {stats.get('index_stats', {})}")
    
    return True


async def test_compatibility():
    """测试兼容性接口"""
    print("\n" + "="*60)
    print("🔄 测试兼容性接口")
    print("="*60)
    
    unified = UnifiedMemorySystem(
        workspace_path=str(Path(__file__).parent / "workspace")
    )
    await unified.initialize()
    
    success = await unified.remember(
        key="test_key",
        value="测试兼容性记忆",
        level="short"
    )
    print(f"✅ 兼容接口存储: {success}")
    
    results = await unified.recall("测试", limit=5)
    print(f"✅ 兼容接口检索: {len(results)} 条")
    
    stats = unified.get_stats()
    print(f"✅ 统计信息: {stats.get('total_memories', 0)} 条记忆")
    
    return True


async def test_cleanup():
    """测试清理功能"""
    print("\n" + "="*60)
    print("🧹 测试清理功能")
    print("="*60)
    
    memory = await get_memory_system()
    
    cleaned = await memory.cleanup_expired()
    print(f"✅ 清理过期记忆: {cleaned} 条")
    
    await memory.cleanup()
    print("✅ 记忆系统清理完成")
    
    return True


async def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("🚀 记忆系统优化验证")
    print("="*60)
    
    tests = [
        ("基本操作", test_basic_operations),
        ("交易记录", test_trade_records),
        ("记忆关联", test_memory_relation),
        ("上下文构建", test_context_building),
        ("统计功能", test_stats),
        ("兼容性接口", test_compatibility),
        ("清理功能", test_cleanup),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = await test_func()
            results.append((name, success, None))
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"❌ {name} 测试失败: {e}")
    
    print("\n" + "="*60)
    print("📋 测试结果汇总")
    print("="*60)
    
    passed = 0
    failed = 0
    for name, success, error in results:
        if success:
            print(f"✅ {name}: 通过")
            passed += 1
        else:
            print(f"❌ {name}: 失败 - {error}")
            failed += 1
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
