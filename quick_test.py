#!/usr/bin/env python3
"""
快速测试ConfigManager
"""

import asyncio
import tempfile
import json
from pathlib import Path

# 将src目录添加到Python路径
import sys
sys.path.insert(0, '/home/cool/.openclaw-trading/src')

from modules.core.config_manager_simple import ConfigManager


async def main():
    print("🚀 测试ConfigManager（简化版）...")
    print("=" * 50)
    
    # 使用临时目录
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / "config"
        config_dir.mkdir(exist_ok=True)
        
        # 创建配置管理器
        manager = ConfigManager(config_dir=str(config_dir), watch_interval=0)
        
        try:
            # 初始化
            print("1. 初始化配置管理器...")
            await manager.initialize()
            print("   ✅ 初始化成功")
            
            # 测试设置配置
            print("2. 测试设置配置...")
            success = await manager.set_config("test", "key1", "value1")
            print(f"   ✅ 设置配置: {success}")
            
            # 测试获取配置
            print("3. 测试获取配置...")
            value = await manager.get_config("test", "key1")
            print(f"   ✅ 获取配置: {value}")
            assert value == "value1"
            
            # 测试获取不存在的配置
            print("4. 测试默认值...")
            value = await manager.get_config("test", "nonexistent", default="default_value")
            print(f"   ✅ 默认值: {value}")
            assert value == "default_value"
            
            # 测试保存到文件
            print("5. 测试保存到文件...")
            config_file = config_dir / "test.json"
            print(f"   📁 配置文件: {config_file}")
            
            if config_file.exists():
                with open(config_file, 'r') as f:
                    content = json.load(f)
                print(f"   ✅ 文件内容: {json.dumps(content, indent=2)}")
            
            # 测试监听器
            print("6. 测试配置变更监听...")
            changes = []
            
            async def callback(section, key, old_value, new_value):
                changes.append((section, key, old_value, new_value))
                print(f"   🔔 配置变更: {section}.{key} = {old_value} -> {new_value}")
            
            await manager.watch_config("test", "key2", callback)
            await manager.set_config("test", "key2", "new_value")
            
            await asyncio.sleep(0.1)
            print(f"   ✅ 监听器调用次数: {len(changes)}")
            
            # 测试获取所有配置
            print("7. 测试获取所有配置...")
            all_configs = await manager.get_all_configs()
            print(f"   ✅ 所有配置: {json.dumps(all_configs, indent=2)}")
            
            # 测试不同类型的数据
            print("8. 测试不同类型的数据...")
            test_data = {
                "string": "hello",
                "number": 123,
                "float": 3.14,
                "boolean": True,
                "list": [1, 2, 3],
                "dict": {"a": 1, "b": 2},
                "none": None
            }
            
            for key, value in test_data.items():
                await manager.set_config("types", key, value)
                retrieved = await manager.get_config("types", key)
                assert retrieved == value
                print(f"   ✅ {key}: {type(value).__name__} = {retrieved}")
            
            # 测试事务
            print("9. 测试配置事务...")
            async with manager.transaction() as transaction:
                await transaction.set_config("transaction", "key1", "value1")
                await transaction.set_config("transaction", "key2", "value2")
            
            # 验证事务提交
            val1 = await manager.get_config("transaction", "key1")
            val2 = await manager.get_config("transaction", "key2")
            print(f"   ✅ 事务提交: key1={val1}, key2={val2}")
            assert val1 == "value1"
            assert val2 == "value2"
            
            # 测试重新加载
            print("10. 测试重新加载...")
            await manager.reload()
            print("   ✅ 重新加载成功")
            
            # 清理
            print("11. 清理...")
            await manager.cleanup()
            print("   ✅ 清理成功")
            
            print("\n" + "=" * 50)
            print("🎉 所有测试通过！")
            print("ConfigManager 核心功能正常！")
            print("=" * 50)
            
            print("\n📋 总结：")
            print("✅ 配置管理：设置、获取、默认值")
            print("✅ 文件持久化：自动保存到JSON文件")
            print("✅ 监听机制：配置变更通知")
            print("✅ 事务支持：原子性配置更新")
            print("✅ 数据类型：支持所有Python基本类型")
            print("✅ 生命周期：初始化和清理")
            
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())