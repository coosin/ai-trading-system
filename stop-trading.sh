#!/bin/bash
# 停止完全独立的加密货币交易系统
#
# 历史说明：此处按端口/进程名（openclaw.*18790）匹配的“独立交易系统实例”，
# 与仓库内推荐的 `scripts/stop-openclaw-trading.sh`（python -m src.main）不一定相同。
# 若你运维的是 ai-trading-system 主链路，请以 scripts 下的脚本为准。

set -e

TRADING_HOME="/home/cool/.openclaw-trading"
TRADING_PORT=18790

echo "🛑 停止加密货币交易系统..."

# 检查是否在运行
if pgrep -f "openclaw.*$TRADING_PORT" > /dev/null; then
    echo "找到运行中的交易系统进程..."
    
    # 优雅停止
    pkill -f "openclaw.*$TRADING_PORT"
    echo "已发送停止信号..."
    
    # 等待进程结束
    for i in {1..10}; do
        if ! pgrep -f "openclaw.*$TRADING_PORT" > /dev/null; then
            echo "✅ 交易系统已停止"
            break
        fi
        echo -n "."
        sleep 1
    done
    
    # 强制停止（如果优雅停止失败）
    if pgrep -f "openclaw.*$TRADING_PORT" > /dev/null; then
        echo "强制停止..."
        pkill -9 -f "openclaw.*$TRADING_PORT"
        echo "✅ 交易系统已强制停止"
    fi
    
    # 清理PID文件
    if [ -f "$TRADING_HOME/trading.pid" ]; then
        rm "$TRADING_HOME/trading.pid"
        echo "已清理PID文件"
    fi
else
    echo "ℹ️ 交易系统未在运行"
fi

# 检查主系统状态（不停止主系统）
if pgrep -f "openclaw.*18789" > /dev/null; then
    echo "✅ 主系统仍在运行（端口 18789）"
else
    echo "ℹ️ 主系统未运行"
fi

echo ""
echo "📊 系统状态:"
echo "交易系统: 已停止"
echo "主系统: 不受影响"
echo "目录结构: 保持独立"