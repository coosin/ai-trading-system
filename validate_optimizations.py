#!/usr/bin/env python3
"""
优化验证工具 - 验证所有修改是否生效
"""

import os
import json
import yaml
import sys

def check_file_exists(filepath, description):
    """检查文件是否存在"""
    if os.path.exists(filepath):
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ {description}: 文件不存在")
        return False

def check_llm_config():
    """检查LLM配置优化"""
    config_path = "/home/cool/.openclaw-trading/data/config/default.yml"
    
    if not os.path.exists(config_path):
        print("❌ LLM配置文件不存在")
        return False
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 检查是否有deepseek-chat模型
        models = config.get('models', {})
        if 'deepseek-chat' in models:
            print("✅ LLM配置: 已添加DeepSeek模型")
            
            # 检查参数
            deepseek_config = models['deepseek-chat']
            if deepseek_config.get('temperature', 1.0) == 0.8:
                print("✅ 温度参数: 0.8 (优化成功)")
            else:
                print("⚠️ 温度参数: 不是0.8")
                
            if deepseek_config.get('max_tokens', 0) == 4000:
                print("✅ 回复长度: 4000 tokens (优化成功)")
            else:
                print("⚠️ 回复长度: 不是4000")
        else:
            print("❌ LLM配置: 未找到DeepSeek模型")
            return False
            
        # 检查任务映射
        task_mapping = config.get('task_model_mapping', {})
        if 'natural_language' in task_mapping:
            models_for_nl = task_mapping['natural_language']
            if 'deepseek-chat' in models_for_nl:
                print("✅ 任务映射: 对话任务使用DeepSeek模型")
            else:
                print("❌ 任务映射: 对话任务未使用DeepSeek模型")
                
        return True
        
    except Exception as e:
        print(f"❌ 读取LLM配置失败: {e}")
        return False

def check_personality_files():
    """检查人格文件"""
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
            # 检查文件内容
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    size_kb = len(content) / 1024
                    
                print(f"✅ {description}: {filename} ({size_kb:.1f} KB)")
                
                # 检查关键内容
                if filename == "SOUL.md" and "交易助手小智" in content:
                    print("   ✅ 包含正确身份: 交易助手小智")
                elif filename == "IDENTITY.md" and "主动积极" in content:
                    print("   ✅ 包含主动积极特质")
                elif filename == "USER.md" and "主动关心" in content:
                    print("   ✅ 包含主动关心要求")
                    
            except Exception as e:
                print(f"⚠️ {description}: 读取失败 - {e}")
                all_exist = False
        else:
            print(f"❌ {description}: 文件不存在")
            all_exist = False
    
    return all_exist

def check_new_modules():
    """检查新创建的模块"""
    new_modules = [
        ("emotional_intelligence.py", "情感智能模块"),
        ("personality_config.py", "人格配置文件"),
        ("proactive_care.py", "主动关怀系统")
    ]
    
    base_path = "/home/cool/.openclaw-trading/src/modules/core"
    all_exist = True
    
    for filename, description in new_modules:
        filepath = os.path.join(base_path, filename)
        if os.path.exists(filepath):
            size_kb = os.path.getsize(filepath) / 1024
            print(f"✅ {description}: {filename} ({size_kb:.1f} KB)")
        else:
            print(f"❌ {description}: 文件不存在")
            all_exist = False
    
    return all_exist

def check_nli_enhancements():
    """检查自然语言接口增强"""
    nli_path = "/home/cool/.openclaw-trading/src/modules/intelligence/natural_language_interface.py"
    
    if not os.path.exists(nli_path):
        print("❌ 自然语言接口文件不存在")
        return False
    
    try:
        with open(nli_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        enhancements = [
            ("_load_personality_files", "人格文件加载方法"),
            ("_get_personality_prompt", "人格提示词方法"),
            ("proactive_care", "主动关怀系统"),
            ("load_personality_files", "加载人格文件调用")
        ]
        
        all_found = True
        for method, description in enhancements:
            if method in content:
                print(f"✅ 自然语言接口: 包含{description}")
            else:
                print(f"❌ 自然语言接口: 缺少{description}")
                all_found = False
        
        return all_found
        
    except Exception as e:
        print(f"❌ 读取自然语言接口失败: {e}")
        return False

def main():
    """主验证函数"""
    print("🎯 AI智能优化验证工具")
    print("验证所有优化是否已正确实施")
    print("=" * 70)
    
    results = []
    
    # 1. 检查LLM配置优化
    print("\n📋 1. LLM配置优化检查")
    results.append(("LLM配置优化", check_llm_config()))
    
    # 2. 检查人格文件
    print("\n📋 2. 人格文件检查")
    results.append(("人格文件", check_personality_files()))
    
    # 3. 检查新模块
    print("\n📋 3. 新模块检查")
    results.append(("新模块创建", check_new_modules()))
    
    # 4. 检查自然语言接口增强
    print("\n📋 4. 自然语言接口增强检查")
    results.append(("NLI增强", check_nli_enhancements()))
    
    # 汇总结果
    print("\n" + "=" * 70)
    print("📊 验证结果汇总:")
    
    total_passed = 0
    total_items = len(results)
    
    for item, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {item}: {status}")
        if passed:
            total_passed += 1
    
    print(f"\n🎯 总体通过率: {total_passed}/{total_items} ({total_passed/total_items*100:.0f}%)")
    
    if total_passed == total_items:
        print("\n✅ 所有优化验证通过！")
        print("🚀 可以重启容器测试效果")
        return True
    else:
        print(f"\n⚠️ 发现{total_items - total_passed}个问题需要修复")
        print("🎯 建议修复后再重启容器")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)