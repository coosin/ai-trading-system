#!/bin/bash
# OpenClaw Trading System - Start Script

APP_NAME="openclaw-trading"
APP_DIR="/home/cool/.openclaw-trading"
LOG_DIR="$APP_DIR/logs"
PID_FILE="/tmp/${APP_NAME}.pid"
LOCK_FILE="/tmp/${APP_NAME}.lock"

cd $APP_DIR

mkdir -p $LOG_DIR

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "ERROR: Already running (PID: $OLD_PID)"
        echo "To restart, run: ./scripts/stop-openclaw-trading.sh first"
        exit 1
    else
        echo "Cleaning stale PID file..."
        rm -f "$PID_FILE" "$LOCK_FILE"
    fi
fi

# Check lock file
if [ -f "$LOCK_FILE" ]; then
    echo "Found stale lock file, cleaning..."
    rm -f "$LOCK_FILE"
fi

echo "Starting OpenClaw Trading System..."
source /home/cool/.bashrc 2>/dev/null 2>&1

nohup python3 -m src.main >> "$LOG_DIR/app.log" 2>&1 &

sleep 3

if pgrep -f "python3 -m src.main" > /dev/null; then
    NEW_PID=$(pgrep -f "python3 -m src.main" | head -1)
    echo "SUCCESS: OpenClaw Trading System started (PID: $NEW_PID)"
    echo "Log file: $LOG_DIR/app.log"
    echo "API docs: http://localhost:8000/docs"
    exit 0
else
    echo "FAILED: OpenClaw Trading System did not start"
    echo "Check logs: tail -50 $LOG_DIR/app.log"
    exit 1
fi
