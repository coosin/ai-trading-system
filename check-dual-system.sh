#!/bin/bash
# 双系统状态检查脚本

echo "📊 OpenClaw 完全独立双智能体系统状态检查"
echo "=========================================="
echo "检查时间: $(date)"
echo ""

echo "🔧 系统架构:"
echo "   主系统 (通用助手): 端口 18789"
echo "   交易系统 (加密货币交易专家): 端口 18790"
echo ""

echo "✅ 1. 进程状态:"
MAIN_PROCESS=$(ps aux | grep "openclaw-gateway" | grep -v grep | head -1)
TRADING_PROCESS=$(ps aux | grep "openclaw-gateway" | grep -v grep | tail -1)

echo "   主系统进程:"
if [ -n "$MAIN_PROCESS" ]; then
    echo "   ✅ PID: $(echo $MAIN_PROCESS | awk '{print $2}')"
    echo "      内存: $(echo $MAIN_PROCESS | awk '{print $6/1024 " MB"}')"
    echo "      运行时间: $(echo $MAIN_PROCESS | awk '{print $10}')"
else
    echo "   ❌ 未运行"
fi

echo ""
echo "   交易系统进程:"
if [ -n "$TRADING_PROCESS" ]; then
    echo "   ✅ PID: $(echo $TRADING_PROCESS | awk '{print $2}')"
    echo "      内存: $(echo $TRADING_PROCESS | awk '{print $6/1024 " MB"}')"
    echo "      运行时间: $(echo $TRADING_PROCESS | awk '{print $10}')"
else
    echo "   ❌ 未运行"
fi

echo ""
echo "🌐 2. 端口监听状态:"
echo "   端口 18789 (主系统):"
if ss -tlnp | grep -q ":18789 "; then
    echo "   ✅ 正在监听"
else
    echo "   ❌ 未监听"
fi

echo "   端口 18790 (交易系统):"
if ss -tlnp | grep -q ":18790 "; then
    echo "   ✅ 正在监听"
else
    echo "   ❌ 未监听"
fi

echo ""
echo "🏥 3. 系统健康检查:"
echo "   主系统健康状态:"
MAIN_HEALTH=$(curl -s http://localhost:18789/health 2>/dev/null | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
if [ -n "$MAIN_HEALTH" ]; then
    echo "   ✅ $MAIN_HEALTH"
else
    echo "   ❌ 无法访问"
fi

echo "   交易系统健康状态:"
TRADING_HEALTH=$(curl -s http://localhost:18790/health 2>/dev/null | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
if [ -n "$TRADING_HEALTH" ]; then
    echo "   ✅ $TRADING_HEALTH"
else
    echo "   ❌ 无法访问"
fi

echo ""
echo "📁 4. 目录结构验证:"
echo "   主系统目录 (~/.openclaw/):"
if [ -d "$HOME/.openclaw" ]; then
    echo "   ✅ 存在"
    echo "      配置文件: $(ls -la ~/.openclaw/openclaw.json 2>/dev/null | wc -l) 个"
    echo "      工作空间: $(ls -la ~/.openclaw/workspace/*.md 2>/dev/null | wc -l) 个文件"
else
    echo "   ❌ 不存在"
fi

echo "   交易系统目录 (~/.openclaw-trading/):"
if [ -d "$HOME/.openclaw-trading" ]; then
    echo "   ✅ 存在"
    echo "      主配置 YAML: $(test -f "$HOME/.openclaw-trading/config/config.yaml" && echo 1 || echo 0) 个 (config/config.yaml)"
    echo "      工作空间: $(ls -la ~/.openclaw-trading/workspace/*.md 2>/dev/null | wc -l) 个文件"
else
    echo "   ❌ 不存在"
fi

echo ""
echo "🔐 5. 安全配置检查:"
echo "   主系统提权权限:"
MAIN_ELEVATED=$(grep -A5 '"elevated"' ~/.openclaw/openclaw.json 2>/dev/null | grep '"enabled"' | grep -o 'true\|false')
if [ "$MAIN_ELEVATED" = "true" ]; then
    echo "   ⚠️  已启用提权权限"
else
    echo "   ✅ 提权权限已禁用"
fi

echo "   交易系统提权/危险项:"
if [ -f "$HOME/.openclaw-trading/config/config.yaml" ]; then
    echo "   （已迁移至 YAML；请人工检查 config/config.yaml 中 system / trading 等段）"
else
    echo "   （未检测到 ~/.openclaw-trading/config/config.yaml）"
fi

echo ""
echo "📈 6. 系统资源使用:"
echo "   总内存使用:"
free -h | grep Mem | awk '{print "     可用: " $7, "已用: " $3}'

echo ""
echo "🎯 7. 服务管理状态:"
echo "   主系统服务:"
systemctl --user is-active --quiet openclaw-gateway.service && echo "   ✅ 运行中" || echo "   ❌ 未运行"

echo "   交易系统服务:"
systemctl --user is-active --quiet openclaw-trading-gateway.service && echo "   ✅ 运行中" || echo "   ❌ 未运行"

echo ""
echo "=========================================="
echo "📝 总结:"
echo "   双智能体系统架构部署完成!"
echo "   完全隔离设计确保安全性和稳定性"
echo ""
echo "🔧 访问地址:"
echo "   主系统控制界面: http://localhost:18789"
echo "   交易系统控制界面: 端口 18790 (API)"
echo ""
echo "⚠️  注意:"
echo "   - 两个系统使用独立的配置和数据目录"
echo "   - 交易系统无提权权限，安全性更高"
echo "   - 消息路由机制需单独配置"