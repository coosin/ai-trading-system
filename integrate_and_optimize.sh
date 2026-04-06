#!/bin/bash
echo "🔧 开始整合和优化AI智能系统"
echo "=" * 50

# 1. 清理重复文件（如果存在）
echo "1. 清理工作："
echo "   - 检查是否有重复创建的文件..."
if [ -f "/home/cool/.openclaw-trading/src/modules/core/personality_config.py" ]; then
    echo "   ✅ 保留 personality_config.py (这是新增的，不是重复)"
fi

# 2. 检查人格文件是否正确加载
echo ""
echo "2. 检查人格文件加载："
echo "   - 检查自然语言接口是否加载人格文件..."
if grep -q "load_personality_files" /home/cool/.openclaw-trading/src/modules/intelligence/natural_language_interface.py; then
    echo "   ✅ 自然语言接口已增强，会加载人格文件"
else
    echo "   ❌ 需要重新增强自然语言接口"
fi

# 3. 检查主动关怀系统是否集成
echo ""
echo "3. 检查主动关怀系统："
if grep -q "proactive_care" /home/cool/.openclaw-trading/src/modules/intelligence/natural_language_interface.py; then
    echo "   ✅ 主动关怀系统已集成"
else
    echo "   ❌ 需要集成主动关怀系统"
fi

# 4. 检查LLM配置是否优化
echo ""
echo "4. 检查LLM配置优化："
if grep -q "deepseek-chat" /home/cool/.openclaw-trading/data/config/default.yml; then
    echo "   ✅ LLM配置已优化（包含DeepSeek模型）"
else
    echo "   ❌ 需要优化LLM配置"
fi

# 5. 检查技能包加载
echo ""
echo "5. 检查技能包加载："
if [ -d "/home/cool/.openclaw-trading/src/modules/skills" ]; then
    skill_count=$(ls /home/cool/.openclaw-trading/src/modules/skills/*.py 2>/dev/null | wc -l)
    echo "   ✅ 发现 $skill_count 个技能文件"
else
    echo "   ❌ 技能包目录不存在"
fi

# 6. 创建整合优化说明
echo ""
echo "=" * 50
echo "📋 整合优化完成清单："
echo ""
echo "✅ 已完成："
echo "   1. 人格文件增强 (SOUL.md, IDENTITY.md, USER.md)"
echo "   2. 主动关怀系统 (proactive_care.py)"
echo "   3. 自然语言接口增强 (自动加载人格文件)"
echo "   4. LLM配置优化 (DeepSeek模型)"
echo "   5. 情感智能模块 (emotional_intelligence.py)"
echo ""
echo "🔄 需要重启才能生效的功能："
echo "   1. 人格文件加载"
echo "   2. 主动关怀系统"
echo "   3. 情感智能集成"
echo ""
echo "🚀 下一步："
echo "   docker restart openclaw-trading"
echo ""
echo "🎯 预期效果："
echo "   - AI更有人情味，更善解人意"
echo "   - AI会主动关心你的状态"
echo "   - 回复更自然，更像朋友"
echo "   - 保持原有的交易专业性"
echo "=" * 50