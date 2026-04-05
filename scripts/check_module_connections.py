#!/usr/bin/env python3
"""
模块连接状态检查工具

检查所有功能模块是否正常对接到主控制器
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 加载环境变量
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ 已加载环境变量文件: {env_path}")
except ImportError:
    print("⚠️ python-dotenv未安装，跳过.env文件加载")

from src.modules.core.config_manager import get_config_manager
from src.modules.main_controller import MainController


async def check_module_connections():
    """检查所有模块连接状态"""
    
    print("=" * 80)
    print("🔍 开始检查所有功能模块连接状态")
    print("=" * 80)
    print()
    
    # 初始化配置管理器
    config_manager = await get_config_manager()
    
    # 创建主控制器
    controller = MainController(config_manager)
    await controller.initialize()
    
    # 定义所有需要检查的模块
    modules_to_check = {
        "核心系统模块": {
            "event_system": "增强事件系统",
            "data_quality_system": "数据质量监控系统",
            "fault_tolerance": "容错机制系统",
            "enhanced_llm_manager": "增强大模型管理器",
            "ai_memory_manager": "AI记忆管理器",
            "memory_optimizer": "内存优化器",
        },
        "AI决策模块": {
            "llm_integration": "大模型集成系统",
            "ai_trading_engine": "全智能AI交易引擎",
            "ai_core": "AI核心决策引擎",
            "ai_command_executor": "AI指令执行器",
            "ai_learning_engine": "AI学习引擎",
        },
        "智能系统组件": {
            "hierarchical_memory": "层次化记忆管理器",
            "skill_manager": "技能管理器",
            "heartbeat_monitor": "心跳监控器",
            "smart_notification": "智能通知系统",
        },
        "交易相关模块": {
            "trading_monitor": "交易监控器",
            "strategy_manager": "多策略管理器",
            "anomaly_detector": "异常检测器",
            "portfolio_optimizer": "策略组合优化器",
            "parameter_optimizer": "参数优化器",
        },
        "数据和存储模块": {
            "data_storage": "增强数据存储系统",
            "backup_manager": "数据备份管理器",
            "database_manager": "数据库管理器",
            "enhanced_backtester": "增强回测系统",
        },
        "通信和通知模块": {
            "telegram_bot": "Telegram机器人",
            "natural_language_interface": "自然语言接口",
        },
        "模拟和测试模块": {
            "simulated_market": "模拟交易市场",
            "contract_simulator": "合约模拟器",
        },
        "业务和管理模块": {
            "business_process_manager": "业务流程管理器",
            "plugin_manager": "插件管理器",
            "strategy_evaluator": "策略评估器",
        },
        "安全和风控模块": {
            "emergency_stop": "紧急停止系统",
            "intelligent_monitoring": "智能监控系统",
            "security_manager": "安全管理器",
            "fund_manager": "智能资金管理器",
        },
        "交易所连接": {
            "okx_exchange": "OKX交易所",
            "risk_monitor": "风险监控",
        }
    }
    
    # 检查结果统计
    total_modules = 0
    connected_modules = 0
    failed_modules = []
    
    # 遍历所有模块类别
    for category, modules in modules_to_check.items():
        print(f"\n📋 {category}")
        print("-" * 80)
        
        for attr_name, display_name in modules.items():
            total_modules += 1
            
            # 检查模块是否存在
            module = getattr(controller, attr_name, None)
            
            if module is not None:
                connected_modules += 1
                status = "✅ 已连接"
                
                # 尝试获取模块状态
                try:
                    if hasattr(module, 'is_running'):
                        is_running = module.is_running if isinstance(module.is_running, bool) else getattr(module, '_running', False)
                        status += f" (运行: {'是' if is_running else '否'})"
                    elif hasattr(module, '_running'):
                        status += f" (运行: {'是' if module._running else '否'})"
                    elif hasattr(module, '_initialized'):
                        status += f" (已初始化: {'是' if module._initialized else '否'})"
                except:
                    pass
                
                print(f"  ✅ {display_name:30s} [{attr_name}]")
            else:
                failed_modules.append((category, display_name, attr_name))
                print(f"  ❌ {display_name:30s} [{attr_name}] - 未连接")
    
    # 打印统计信息
    print("\n" + "=" * 80)
    print("📊 连接状态统计")
    print("=" * 80)
    print(f"总模块数: {total_modules}")
    print(f"已连接: {connected_modules}")
    print(f"未连接: {total_modules - connected_modules}")
    print(f"连接率: {connected_modules / total_modules * 100:.1f}%")
    
    # 如果有未连接的模块，列出详细信息
    if failed_modules:
        print("\n" + "=" * 80)
        print("⚠️ 未连接的模块详情")
        print("=" * 80)
        for category, display_name, attr_name in failed_modules:
            print(f"  ❌ [{category}] {display_name} ({attr_name})")
    
    # 检查模块间的依赖关系
    print("\n" + "=" * 80)
    print("🔗 关键依赖关系检查")
    print("=" * 80)
    
    dependencies = [
        ("ai_core", "llm_integration", "AI核心需要LLM集成"),
        ("ai_core", "ai_trading_engine", "AI核心需要交易引擎"),
        ("ai_trading_engine", "okx_exchange", "交易引擎需要交易所"),
        ("llm_integration", "enhanced_llm_manager", "LLM集成需要LLM管理器"),
        ("telegram_bot", "llm_integration", "Telegram需要LLM集成"),
        ("ai_command_executor", "ai_core", "AI指令执行器需要AI核心"),
    ]
    
    for source, target, description in dependencies:
        source_module = getattr(controller, source, None)
        target_module = getattr(controller, target, None) if source_module else None
        
        if source_module and target_module:
            print(f"  ✅ {description}")
        else:
            print(f"  ❌ {description} - 依赖缺失")
    
    # 清理
    await controller.cleanup()
    
    print("\n" + "=" * 80)
    print("✅ 模块连接状态检查完成")
    print("=" * 80)
    
    return connected_modules == total_modules


if __name__ == "__main__":
    try:
        result = asyncio.run(check_module_connections())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ 检查被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
