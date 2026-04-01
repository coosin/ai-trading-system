#!/bin/bash
# OpenClaw Trading System - Stop Script

APP_NAME="openclaw-trading"
APP_DIR="/home/cool/.openclaw-trading"
PID_FILE="/tmp/${APP_NAME}.pid"

echo "停止 OpenClaw Trading System..."

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$PID" ]; then
        kill -TERM "$PID" 2>/dev/null
        sleep 2
        if pgrep -f "python3 -m src.main" > /dev/null; then
            kill -9 "$PID" 2>/dev/null
        fi
        rm -f "$PID_FILE"
        echo "✅ OpenClaw Trading System 已停止"
    else
        echo "PID 文件为空"
        rm -f "$PID_FILE"
    fi
else
    echo "PID 文件不存在"
fi

pkill -f "python3 -m src.main" 2>/dev/null

echo "清理完成"
