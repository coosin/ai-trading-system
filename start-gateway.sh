#!/bin/bash
# 启动交易系统独立网关

set -e

echo "🚀 启动交易系统独立网关..."

# 检查端口是否被占用
if ss -tlnp | grep -q ":18790 "; then
    echo "⚠️  端口18790已被占用，请先停止其他服务"
    exit 1
fi

# 检查配置文件
if [ ! -f "/home/cool/.openclaw-trading/openclaw-trading.json" ]; then
    echo "❌ 配置文件不存在: /home/cool/.openclaw-trading/openclaw-trading.json"
    exit 1
fi

# 检查服务文件
if [ ! -f "/home/cool/.config/systemd/user/openclaw-trading-gateway.service" ]; then
    echo "❌ 服务文件不存在，请先创建"
    exit 1
fi

# 重新加载systemd配置
echo "🔄 重新加载systemd配置..."
systemctl --user daemon-reload

# 启用服务
echo "✅ 启用交易系统网关服务..."
systemctl --user enable openclaw-trading-gateway.service

# 启动服务
echo "🚀 启动交易系统网关..."
systemctl --user start openclaw-trading-gateway.service

# 等待启动
echo "⏳ 等待服务启动..."
sleep 3

# 检查状态
if systemctl --user is-active --quiet openclaw-trading-gateway.service; then
    echo "✅ 交易系统网关启动成功！"
    echo "📊 服务状态:"
    systemctl --user status openclaw-trading-gateway.service --no-pager
    
    echo ""
    echo "🌐 网络端口:"
    echo "   API端口: 18790"
    echo "   控制UI: http://localhost:18791"
    
    echo ""
    echo "📋 检查端口监听:"
    if ss -tlnp | grep -q ":18790 "; then
        echo "   ✅ 端口18790监听正常"
    else
        echo "   ⚠️  端口18790未监听"
    fi
    
    echo ""
    echo "📁 独立配置:"
    echo "   配置目录: /home/cool/.openclaw-trading/"
    echo "   配置文件: openclaw-trading.json"
    echo "   工作空间: /home/cool/.openclaw-trading/workspace"
    
    echo ""
    echo "🔧 常用命令:"
    echo "   查看状态: systemctl --user status openclaw-trading-gateway.service"
    echo "   查看日志: journalctl --user -u openclaw-trading-gateway.service -f"
    echo "   停止服务: systemctl --user stop openclaw-trading-gateway.service"
    echo "   重启服务: systemctl --user restart openclaw-trading-gateway.service"
else
    echo "❌ 交易系统网关启动失败"
    echo "📋 查看日志: journalctl --user -u openclaw-trading-gateway.service --no-pager -n 50"
    exit 1
fi