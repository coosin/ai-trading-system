#!/bin/bash

# 推送代码到GitHub

set -e

echo "🚀 推送代码到GitHub..."
echo "仓库: https://github.com/coosin/ai-trading-system.git"
echo ""

cd /home/cool/.openclaw-trading

# 检查Git状态
echo "📊 检查Git状态..."
git status --short

# 添加所有更改
echo "📦 添加文件..."
git add .

# 提交
echo "💾 提交更改..."
git commit -m "更新: $(date '+%Y-%m-%d %H:%M:%S')" || echo "没有更改可提交"

# 尝试推送
echo "🔄 推送到GitHub..."
echo "注意：第一次推送可能需要输入GitHub用户名和密码"
echo "（如果使用token，用token作为密码）"
echo ""

# 使用HTTPS推送
git push https://github.com/coosin/ai-trading-system.git master --force

echo ""
echo "✅ 完成！"
echo ""
echo "📋 如果推送失败："
echo "1. 检查GitHub仓库是否存在"
echo "2. 确保有推送权限"
echo "3. 可能需要使用GitHub token作为密码"
echo ""
echo "🔗 仓库地址：https://github.com/coosin/ai-trading-system"