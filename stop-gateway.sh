#!/bin/bash
# 停止交易系统独立网关

set -e

echo "🛑 停止交易系统独立网关..."

# 检查服务状态
if systemctl --user is-active --quiet openclaw-trading-gateway.service; then
    echo "服务运行中，正在停止..."
    
    # 停止服务
    systemctl --user stop openclaw-trading-gateway.service
    
    # 等待停止
    sleep 2
    
    if systemctl --user is-active --quiet openclaw-trading-gateway.service; then
        echo "⚠️ 正常停止失败，尝试强制停止..."
        systemctl --user kill openclaw-trading-gateway.service
        sleep 2
    fi
    
    if ! systemctl --user is-active --quiet openclaw-trading-gateway.service; then
        echo "✅ 交易系统网关已停止"
        
        # 可选：禁用服务（如果不常使用）
        # systemctl --user disable openclaw-trading-gateway.service
        
        # 检查端口是否释放
        if ss -tlnp | grep -q ":18790 "; then
            echo "⚠️ 端口18790仍被占用"
        else
            echo "✅ 端口18790已释放"
        fi
    else
        echo "❌ 停止失败"
        exit 1
    fi
else
    echo "ℹ️ 交易系统网关未在运行"
fi

echo ""
echo "📊 主系统网关状态:"
if systemctl --user is-active --quiet openclaw-gateway.service; then
    echo "   ✅ 主系统网关仍在运行 (端口: 18789)"
else
    echo "   ⚠️  主系统网关未运行"
fi

echo ""
echo "🔧 交易系统已停止，主系统不受影响"