#!/usr/bin/env python3
"""
完整模块集成检查工具

检查所有功能模块是否正确集成到主控制器
"""

import sys
import asyncio
from pathlib import Path
from typing import Dict, List, Tuple

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 加载环境变量
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from src.modules.core.config_manager import get_config_manager
from src.modules.main_controller import MainController


async def check_all_modules():
    """检查所有模块集成状态"""
    
    print("=" * 80)
    print("🔍 完整模块集成检查")
    print("=" * 80)
    print()
    
    # 定义所有应该存在的模块
    all_expected_modules = {
        "核心系统模块": {
            "event_system": "增强事件系统",
            "data_quality_system": "数据质量监控系统",
            "fault_tolerance": "容错机制系统",
            "enhanced_llm_manager": "增强大模型管理器",
            "ai_memory_manager": "AI记忆管理器",
            "memory_optimizer": "内存优化器",
            "config_manager": "配置管理器",
            "database_manager": "数据库管理器",
            "cache_manager": "缓存管理器",
            "log_manager": "日志管理器",
            "system_monitor": "系统监控器",
            "event_system": "事件系统",
        },
        
        "AI决策模块": {
            "llm_integration": "大模型集成系统",
            "ai_trading_engine": "全智能AI交易引擎",
            "ai_core": "AI核心决策引擎",
            "ai_command_executor": "AI指令执行器",
            "ai_learning_engine": "AI学习引擎",
            "active_trader": "主动交易器",
        },
        
        "智能系统组件": {
            "hierarchical_memory": "层次化记忆管理器",
            "skill_manager": "技能管理器",
            "heartbeat_monitor": "心跳监控器",
            "smart_notification": "智能通知系统",
            "unified_intelligent_memory": "统一智能记忆",
        },
        
        "信息收集分析": {
            "unified_info_collector": "统一信息收集分析管理器",
            "realtime_data_collector": "实时数据采集器",
            "market_analyzer": "市场分析器",
            "sentiment_analyzer": "情感分析器",
            "onchain_integrator": "链上数据集成器",
        },
        
        "交易相关模块": {
            "trading_monitor": "交易监控器",
            "strategy_manager": "多策略管理器",
            "anomaly_detector": "异常检测器",
            "portfolio_optimizer": "策略组合优化器",
            "parameter_optimizer": "参数优化器",
            "strategy_evaluator": "策略评估器",
            "trade_engine": "交易引擎",
            "risk_manager": "风险管理器",
        },
        
        "数据和存储模块": {
            "data_storage": "增强数据存储系统",
            "backup_manager": "数据备份管理器",
            "historical_data_storage": "历史数据存储",
            "data_pipeline": "数据管道",
            "data_fusion": "数据融合",
        },
        
        "通信和通知模块": {
            "telegram_bot": "Telegram机器人",
            "natural_language_interface": "自然语言接口",
            "notification_manager": "通知管理器",
        },
        
        "模拟和测试模块": {
            "simulated_market": "模拟交易市场",
            "contract_simulator": "合约模拟器",
            "automated_testing": "自动化测试系统",
        },
        
        "业务和管理模块": {
            "business_process_manager": "业务流程管理器",
            "plugin_manager": "插件管理器",
            "domain_manager": "域名管理器",
            "automation_rules": "自动化规则系统",
        },
        
        "安全和风控模块": {
            "emergency_stop": "紧急停止系统",
            "intelligent_monitoring": "智能监控系统",
            "security_manager": "安全管理器",
            "fund_manager": "智能资金管理器",
            "api_key_manager": "API密钥管理器",
        },
        
        "交易所连接": {
            "okx_exchange": "OKX交易所",
            "exchange_connector": "交易所连接器",
            "exchange_factory": "交易所工厂",
            "risk_monitor": "风险监控",
        },
        
        "执行模块": {
            "trading_execution_engine": "交易执行引擎",
            "smart_order_router": "智能订单路由器",
        },
        
        "API模块": {
            "api_server": "API服务器",
            "monitoring_api": "监控API",
            "strategy_api": "策略API",
            "risk_api": "风险API",
            "backtest_api": "回测API",
        },
        
        "回测模块": {
            "backtest_engine": "回测引擎",
        },
        
        "AI模块": {
            "deep_learning_integrator": "深度学习集成器",
            "reinforcement_learning_optimizer": "强化学习优化器",
            "model_training_system": "模型训练系统",
            "model_auto_updater": "模型自动更新器",
        },
        
        "审计模块": {
            "operation_audit": "操作审计系统",
        },
    }
    
    # 初始化配置管理器
    config_manager = await get_config_manager()
    
    # 创建主控制器
    controller = MainController(config_manager)
    await controller.initialize()
    
    # 检查结果统计
    total_modules = 0
    connected_modules = 0
    missing_modules_by_category: Dict[str, List[Tuple[str, str]]] = {}
    
    # 遍历所有模块类别
    for category, modules in all_expected_modules.items():
        category_missing = []
        
        print(f"\n📋 {category}")
        print("-" * 80)
        
        for attr_name, display_name in modules.items():
            total_modules += 1
            
            # 检查模块是否存在
            module = getattr(controller, attr_name, None)
            
            if module is not None:
                connected_modules += 1
                print(f"  ✅ {display_name:30s} [{attr_name}]")
            else:
                category_missing.append((display_name, attr_name))
                print(f"  ❌ {display_name:30s} [{attr_name}] - 未连接")
        
        if category_missing:
            missing_modules_by_category[category] = category_missing
    
    # 打印统计信息
    print("\n" + "=" * 80)
    print("📊 连接状态统计")
    print("=" * 80)
    print(f"总模块数: {total_modules}")
    print(f"已连接: {connected_modules}")
    print(f"未连接: {total_modules - connected_modules}")
    print(f"连接率: {connected_modules / total_modules * 100:.1f}%")
    
    # 如果有未连接的模块，列出详细信息
    if missing_modules_by_category:
        print("\n" + "=" * 80)
        print("⚠️ 未连接的模块详情")
        print("=" * 80)
        for category, missing_list in missing_modules_by_category.items():
            print(f"\n[{category}]")
            for display_name, attr_name in missing_list:
                print(f"  ❌ {display_name} ({attr_name})")
    
    # 生成建议
    print("\n" + "=" * 80)
    print("💡 集成建议")
    print("=" * 80)
    
    critical_missing = []
    for category in ["核心系统模块", "AI决策模块", "交易相关模块", "信息收集分析"]:
        if category in missing_modules_by_category:
            critical_missing.extend(missing_modules_by_category[category])
    
    if critical_missing:
        print("\n🔴 关键模块缺失（需要优先处理）:")
        for display_name, attr_name in critical_missing[:10]:
            print(f"  - {display_name} ({attr_name})")
    
    # 清理
    await controller.cleanup()
    
    print("\n" + "=" * 80)
    print("✅ 模块集成检查完成")
    print("=" * 80)
    
    return connected_modules == total_modules


if __name__ == "__main__":
    try:
        result = asyncio.run(check_all_modules())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ 检查被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
