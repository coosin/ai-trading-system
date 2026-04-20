#!/bin/bash
# OpenClaw Trading System - Start Script

APP_NAME="openclaw-trading"
APP_DIR="/home/cool/ai-trading-system"
LOG_DIR="$APP_DIR/logs"
PID_FILE="/tmp/${APP_NAME}.pid"
LOCK_FILE="/tmp/${APP_NAME}.lock"
PY="${APP_DIR}/.venv/bin/python"

cd "$APP_DIR"

if [ ! -x "$PY" ]; then
    echo "ERROR: venv missing at $PY — run: cd $APP_DIR && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

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

nohup "$PY" -m src.main >> "$LOG_DIR/app.log" 2>&1 &

sleep 3

if pgrep -f "src.main" > /dev/null; then
    NEW_PID=$(pgrep -f "src.main" | head -1)
    echo "$NEW_PID" > "$PID_FILE"
    echo "SUCCESS: OpenClaw Trading System started (PID: $NEW_PID)"
    echo "Log file: $LOG_DIR/app.log"
    echo "API docs: http://localhost:8000/docs"
    exit 0
else
    echo "FAILED: OpenClaw Trading System did not start"
    echo "Check logs: tail -50 $LOG_DIR/app.log"
    exit 1
fi
