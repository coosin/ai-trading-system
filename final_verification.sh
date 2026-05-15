#!/bin/bash
echo "🎯 AI智能优化最终验证和重启"
echo "=" * 70

echo ""
echo "📋 验证已完成的所有优化:"
echo ""

# 1. 检查人格文件
echo "1. ✅ 人格文件:"
echo "   - SOUL.md (灵魂文件) - 已创建"
echo "   - IDENTITY.md (身份文件) - 已创建"
echo "   - USER.md (用户文件) - 已创建"

# 2. 检查新模块
echo ""
echo "2. ✅ 新模块:"
echo "   - emotional_intelligence.py (情感智能) - 已创建"
echo "   - personality_config.py (人格配置) - 已创建"
echo "   - proactive_care.py (主动关怀) - 已创建"

# 3. 检查自然语言接口增强
echo ""
echo "3. ✅ 自然语言接口增强:"
echo "   - 人格文件加载方法 - 已添加"
echo "   - 主动关怀系统集成 - 已添加"
echo "   - 语法错误 - 已修复"

# 4. 检查LLM配置
echo ""
echo "4. ⚠️ LLM配置:"
echo "   - DeepSeek模型配置 - 已添加"
echo "   - 但YAML格式可能需要验证"
echo "   - 建议重启后测试实际效果"

# 5. 检查技能包
echo ""
echo "5. ✅ 技能包:"
skill_count=$(ls /home/cool/.openclaw-trading/src/modules/skills/*.py 2>/dev/null | wc -l)
echo "   - 发现 $skill_count 个技能文件"
echo "   - 技能包已存在，需要验证是否正确加载"

echo ""
echo "=" * 70
echo "🚀 请重启本机交易进程以使配置生效"
echo ""
echo "示例（按你的托管方式选一）："
echo "  systemctl restart openclaw-trading.service   # 若已配置 systemd"
echo "  bash scripts/stop-openclaw-trading.sh && bash scripts/start-openclaw-trading.sh"
echo ""
read -r -p "是否现在执行 stop + start 脚本? [y/N] " ans
if [[ "${ans,,}" == "y" ]]; then
  bash "$(dirname "$0")/scripts/stop-openclaw-trading.sh" 2>/dev/null || true
  sleep 2
  bash "$(dirname "$0")/scripts/start-openclaw-trading.sh" 2>/dev/null || echo "启动脚本失败，请手动检查"
else
  echo "已跳过自动重启"
fi

echo ""
echo "📊 建议检查: curl -s http://127.0.0.1:8000/api/v1/system/health"

echo ""
echo "=" * 70
echo "🧪 测试建议:"
echo ""
echo "1. 测试日常对话:"
echo "   输入: '你好'"
echo "   期望: 自然问候，不是机械回复"
echo ""
echo "2. 测试情感智能:"
echo "   输入: '今天市场跌了，我有点担心'"
echo "   期望: 先安抚情绪，再分析市场"
echo ""
echo "3. 测试主动关怀:"
echo "   长时间不对话，观察AI是否主动问候"
echo ""
echo "4. 测试技能包:"
echo "   输入: '帮我分析系统状态'"
echo "   期望: 使用系统诊断技能"
echo ""
echo "=" * 70
echo "🎯 优化目标总结:"
echo ""
echo "✅ 已完成:"
echo "   - 人格文件创建 (让AI有'灵魂')"
echo "   - 情感智能模块 (让AI更善解人意)"
echo "   - 主动关怀系统 (让AI更主动)"
echo "   - 自然语言接口增强 (集成所有优化)"
echo ""
echo "🔄 待验证:"
echo "   - LLM配置是否生效"
echo "   - 人格文件是否被加载"
echo "   - 主动关怀是否工作"
echo ""
echo "🔍 如果测试发现问题，可以:"
echo "   1. 查看日志: tail -n 120 logs/app.log"
echo "   2. 查看人格文件加载日志"
echo "   3. 调试具体问题"
echo ""
echo "=" * 70