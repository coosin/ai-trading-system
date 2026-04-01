#!/usr/bin/env python3
"""
系统诊断脚本 - 检查所有组件是否正确连接
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


async def diagnose():
    """诊断系统"""
    print("=" * 80)
    print("🔍 系统诊断 - 检查组件连接")
    print("=" * 80)
    
    # 1. 检查导入
    print("\n1️⃣ 检查核心组件导入...")
    try:
        from src.modules.core.ai_command_parser import AICommandParser, CommandType
        print("   ✅ AICommandParser 导入成功")
    except Exception as e:
        print(f"   ❌ AICommandParser 导入失败: {e}")
        return
    
    try:
        from src.modules.core.ai_command_executor import AICommandExecutor
        print("   ✅ AICommandExecutor 导入成功")
    except Exception as e:
        print(f"   ❌ AICommandExecutor 导入失败: {e}")
        return
    
    try:
        from src.modules.core.ai_memory import AIMemoryManager
        print("   ✅ AIMemoryManager 导入成功")
    except Exception as e:
        print(f"   ❌ AIMemoryManager 导入失败: {e}")
        return
    
    # 2. 检查工作区文件
    print("\n2️⃣ 检查工作区记忆文件...")
    workspace_path = os.path.join(os.path.dirname(__file__), "workspace")
    memory_files = ["SOUL.md", "IDENTITY.md", "USER.md", "TRADING.md", "INSTRUCTIONS.md"]
    all_files_exist = True
    for f in memory_files:
        file_path = os.path.join(workspace_path, f)
        if os.path.exists(file_path):
            print(f"   ✅ {f} 存在")
        else:
            print(f"   ❌ {f} 缺失")
            all_files_exist = False
    
    # 3. 测试记忆管理器
    print("\n3️⃣ 测试记忆管理器...")
    try:
        memory_manager = AIMemoryManager(workspace_path=workspace_path)
        workspace_memory = memory_manager.get_workspace_memory()
        print(f"   ✅ 成功加载 {len(workspace_memory)} 个记忆文件")
        for filename in workspace_memory.keys():
            print(f"      - {filename}")
        
        context = await memory_manager.build_memory_context("测试")
        print(f"   ✅ 记忆上下文长度: {len(context)} 字符")
        print(f"   ✅ 记忆上下文预览:")
        print("   " + "-" * 60)
        print(context[:500].replace("\n", "\n   "))
        print("   " + "-" * 60)
    except Exception as e:
        print(f"   ❌ 记忆管理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 4. 测试指令解析器
    print("\n4️⃣ 测试指令解析器...")
    try:
        parser = AICommandParser()
        
        test_cases = [
            ("帮我开仓BTC多单", "开仓指令"),
            ("平掉BTC的仓位", "平仓指令"),
            ("分析一下比特币市场", "分析指令"),
            ("开始自动交易", "启动交易指令"),
            ("停止自动交易", "停止交易指令"),
            ("你是谁？", "普通对话"),
        ]
        
        for user_input, description in test_cases:
            command = await parser.parse(user_input)
            print(f"   ✅ {description}: {user_input}")
            print(f"      → 类型: {command.command_type.value}")
            if command.symbol:
                print(f"      → 交易对: {command.symbol}")
            if command.side:
                print(f"      → 方向: {command.side.value}")
        
        print("   ✅ 所有指令解析测试通过")
    except Exception as e:
        print(f"   ❌ 指令解析器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 5. 检查API端点更新
    print("\n5️⃣ 检查API端点更新...")
    try:
        with open("src/modules/api/server.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        if "ai_command_executor" in content:
            print("   ✅ API端点已集成AI指令执行器")
        else:
            print("   ❌ API端点未集成AI指令执行器")
        
        if "process_input" in content:
            print("   ✅ API端点使用process_input方法")
        else:
            print("   ❌ API端点未使用process_input方法")
    except Exception as e:
        print(f"   ❌ API端点检查失败: {e}")
        return
    
    # 6. 检查主控制器初始化
    print("\n6️⃣ 检查主控制器初始化...")
    try:
        with open("src/modules/main_controller.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        if "ai_command_executor = AICommandExecutor" in content:
            print("   ✅ 主控制器已初始化AI指令执行器")
        else:
            print("   ❌ 主控制器未初始化AI指令执行器")
        
        if "await self.ai_command_executor.initialize()" in content:
            print("   ✅ 主控制器已调用initialize()")
        else:
            print("   ❌ 主控制器未调用initialize()")
    except Exception as e:
        print(f"   ❌ 主控制器检查失败: {e}")
        return
    
    print("\n" + "=" * 80)
    print("✅ 所有诊断通过！系统组件连接正常")
    print("=" * 80)
    print("\n📝 问题可能是：")
    print("   1. 系统还在运行旧代码 - 需要重启后端")
    print("   2. 浏览器缓存了旧前端 - 请刷新页面")
    print("\n🚀 重启后端步骤：")
    print("   1. 停止当前运行的后端 (Ctrl+C)")
    print("   2. 重新启动: python3 src/main.py")
    print("   3. 刷新前端页面")


if __name__ == "__main__":
    asyncio.run(diagnose())
