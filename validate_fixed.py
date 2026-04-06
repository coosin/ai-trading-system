#!/usr/bin/env python3
"""
修复后的验证工具
"""

import os
import yaml

def check_llm_config():
    """检查LLM配置优化"""
    config_path = "/home/cool/.openclaw-trading/data/config/default.yml"
    
    print("📋 LLM配置检查:")
    print("-" * 40)
    
    if not os.path.exists(config_path):
        print("❌ LLM配置文件不存在")
        return False
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 检查是否有deepseek-chat模型（数组格式）
        models = config.get('models', [])
        deepseek_found = False
        deepseek_config = None
        
        for model in models:
            if isinstance(model, dict) and model.get('model_id') == 'deepseek-chat':
                deepseek_found = True
                deepseek_config = model
                break
        
        if deepseek_found:
            print("✅ 已添加DeepSeek模型")
            
            # 检查参数
            temp = deepseek_config.get('temperature', 1.0)
            if temp == 0.8:
                print("✅ 温度参数: 0.8 (优化成功)")
            else:
                print(f"⚠️ 温度参数: {temp} (期望0.8)")
                
            max_tokens = deepseek_config.get('max_tokens', 0)
            if max_tokens == 4000:
                print("✅ 回复长度: 4000 tokens (优化成功)")
            else:
                print(f"⚠️ 回复长度: {max_tokens} (期望4000)")
                
            context = deepseek_config.get('context_window', 0)
            if context == 128000:
                print("✅ 上下文窗口: 128K (优化成功)")
            else:
                print(f"⚠️ 上下文窗口: {context} (期望128000)")
        else:
            print("❌ 未找到DeepSeek模型")
            return False
        
        # 检查任务映射
        task_mapping = config.get('task_model_mapping', {})
        if 'natural_language' in task_mapping:
            nl_models = task_mapping['natural_language']
            if 'deepseek-chat' in nl_models:
                print("✅ natural_language任务映射到deepseek-chat")
            else:
                print(f"❌ natural_language未映射到deepseek-chat: {nl_models}")
                return False
        else:
            print("❌ 找不到natural_language任务映射")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ 读取LLM配置失败: {e}")
        return False

def check_personality_files():
    """检查人格文件"""
    print("\n📋 人格文件检查:")
    print("-" * 40)
    
    personality_files = [
        ("SOUL.md", "灵魂文件"),
        ("IDENTITY.md", "身份文件"),
        ("USER.md", "用户文件")
    ]
    
    base_path = "/home/cool/.openclaw-trading/workspace"
    all_exist = True
    
    for filename, description in personality_files:
        filepath = os.path.join(base_path, filename)
        if os.path.exists(filepath):
            size_kb = os.path.getsize(filepath) / 1024
            print(f"✅ {description}: {filename} ({size_kb:.1f} KB)")
        else:
            print(f"❌ {description}: 文件不存在")
            all_exist = False
    
    return all_exist

def main():
    """主验证函数"""
    print("🎯 AI智能优化验证工具（修复版）")
    print("=" * 60)
    
    results = []
    
    # 检查LLM配置
    results.append(("LLM配置优化", check_llm_config()))
    
    # 检查人格文件
    results.append(("人格文件", check_personality_files()))
    
    print("\n" + "=" * 60)
    print("📊 验证结果汇总:")
    
    total_passed = 0
    total_items = len(results)
    
    for item, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {item}: {status}")
        if passed:
            total_passed += 1
    
    print(f"\n🎯 总体通过率: {total_passed}/{total_items}")
    
    if total_passed == total_items:
        print("\n✅ 所有优化验证通过！")
        print("🚀 可以重启容器测试效果")
        return True
    else:
        print(f"\n⚠️ 发现{total_items - total_passed}个问题需要修复")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)