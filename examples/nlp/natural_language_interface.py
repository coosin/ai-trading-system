#!/usr/bin/env python3
"""
自然语言接口使用示例

本示例展示如何使用系统的自然语言接口来与交易系统进行交互。
"""

import asyncio
from src.modules.main_controller import MainController

async def main():
    # 初始化主控制器
    controller = MainController()
    await controller.initialize()
    
    print("=== 自然语言接口使用示例 ===")
    
    # 1. 基本查询
    print("\n1. 基本查询示例")
    
    queries = [
        "系统现在的运行状态如何？",
        "分析一下比特币的市场趋势",
        "生成一个基于MACD的交易策略",
        "评估当前策略的性能",
        "获取最近的告警信息"
    ]
    
    for query in queries:
        print(f"\n查询: {query}")
        response = await controller.respond_to_natural_language_query(query)
        print(f"响应: {response}")
    
    # 2. 带上下文的查询
    print("\n2. 带上下文的查询示例")
    
    context = {
        "user_id": "trader123",
        "preferences": {
            "timezone": "Asia/Shanghai",
            "preferred_strategies": ["trend_following", "mean_reversion"],
            "risk_level": "medium"
        },
        "recent_queries": [
            "比特币的价格是多少？",
            "以太坊的趋势如何？"
        ]
    }
    
    context_query = "我关注的加密货币有什么投资机会？"
    print(f"\n查询: {context_query}")
    response = await controller.respond_to_natural_language_query(context_query, context)
    print(f"响应: {response}")
    
    # 3. 命令执行
    print("\n3. 命令执行示例")
    
    command_queries = [
        "获取BTC/USDT的1小时K线数据",
        "运行策略回测",
        "优化策略参数",
        "分析投资组合风险"
    ]
    
    for query in command_queries:
        print(f"\n命令: {query}")
        result = await controller.process_natural_language_query(query)
        print(f"执行结果: {result}")
    
    # 4. 自定义命令
    print("\n4. 自定义命令示例")
    
    # 添加自定义命令
    success = controller.add_natural_language_command(
        "get_crypto_news",
        "获取加密货币相关新闻",
        ["加密货币新闻", "数字货币新闻", "币圈新闻"],
        "get_crypto_news"
    )
    
    if success:
        print("成功添加自定义命令: get_crypto_news")
        
        # 使用自定义命令
        news_query = "最近有什么重要的加密货币新闻？"
        print(f"\n查询: {news_query}")
        response = await controller.respond_to_natural_language_query(news_query)
        print(f"响应: {response}")
    
    # 5. 获取可用命令
    print("\n5. 获取可用命令")
    commands = controller.get_available_commands()
    print("可用的自然语言命令:")
    for command_name, info in commands.items():
        print(f"- {command_name}: {info['description']}")
    
    # 6. 清理
    print("\n6. 清理资源")
    await controller.cleanup()
    
    print("自然语言接口使用示例完成！")

if __name__ == "__main__":
    asyncio.run(main())