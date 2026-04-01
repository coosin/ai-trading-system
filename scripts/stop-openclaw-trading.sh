#!/bin/bash
# OpenClaw Trading System - Stop Script

APP_NAME="openclaw-trading"
APP_DIR="/home/cool/.openclaw-trading"
PID_FILE="/tmp/${APP_NAME}.pid"
LOCK_FILE="/tmp/${APP_NAME}.lock"

echo "Stopping OpenClaw Trading System..."

# Try graceful stop first
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$PID" ]; then
        echo "Sending SIGTERM to process $PID..."
        kill -TERM "$PID" 2>/dev/null
        sleep 3
        
        # Check if still running
        if pgrep -f "python3 -m src.main" > /dev/null; then
            echo "Process not responding, force killing..."
            kill -9 "$PID" 2>/dev/null
            sleep 1
        fi
        echo "SUCCESS: OpenClaw Trading System stopped"
    else
        echo "PID file is empty"
    fi
else
    echo "PID file does not exist"
fi

# Kill all related processes
pkill -f "python3 -m src.main" 2>/dev/null

# Clean up lock and PID files
rm -f "$PID_FILE" "$LOCK_FILE" 2>/dev/null
echo "Lock files cleaned"

echo "Cleanup complete"
