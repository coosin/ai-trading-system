#!/bin/bash
# OpenClaw Trading System - Start Script

APP_NAME="openclaw-trading"
APP_DIR="/home/cool/.openclaw-trading"
LOG_DIR="$APP_DIR/logs"
PID_FILE="/tmp/${APP_NAME}.pid"

cd $APP_DIR

mkdir -p $LOG_DIR

if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "进程 $OLD_PID 已停止"
        rm -f "$PID_FILE"
    fi
fi

echo "启动 OpenClaw Trading System..."
source /home/cool/.bashrc 2>/dev/null 2>&1

nohup python3 -m src.main >> "$LOG_DIR/app.log" 2>&1 &

sleep 3

if pgrep -f "python3 -m src.main" > /dev/null; then
    echo "✅ OpenClaw Trading System 启动成功"
    exit 0
else
    echo "❌ OpenClaw Trading System 启动失败"
    exit 1
