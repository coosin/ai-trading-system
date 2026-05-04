#!/bin/bash
# OpenClaw Trading System - Stop Script

set -euo pipefail

APP_NAME="openclaw-trading"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${APP_DIR}/runtime"
HOME_RUNTIME=""
if [[ -n "${HOME:-}" ]]; then
  HOME_RUNTIME="${HOME}/.openclaw-trading/runtime"
fi
PID_BASENAME="${APP_NAME}.pid"
PID_FILE="/tmp/${PID_BASENAME}"
LOCK_FILE="/tmp/${APP_NAME}.lock"
REPO_PID_FILE="${RUNTIME_DIR}/${PID_BASENAME}"
HOME_PID_FILE=""
if [[ -n "${HOME_RUNTIME}" ]]; then
  HOME_PID_FILE="${HOME_RUNTIME}/${PID_BASENAME}"
fi

echo "Stopping OpenClaw Trading System..."

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "${PID:-}" ]; then
        echo "Sending SIGTERM to process $PID..."
        kill -TERM "$PID" 2>/dev/null || true
        sleep 3

        if pgrep -f "src.main" >/dev/null 2>&1; then
            echo "Process not responding, force killing..."
            kill -9 "$PID" 2>/dev/null || true
            sleep 1
        fi
        echo "SUCCESS: OpenClaw Trading System stopped"
    else
        echo "PID file is empty"
    fi
else
    echo "PID file does not exist"
fi

pkill -f "src.main" 2>/dev/null || true

rm -f "$PID_FILE" "$LOCK_FILE" "$REPO_PID_FILE" 2>/dev/null || true
if [[ -n "${HOME_PID_FILE:-}" ]]; then
  rm -f "$HOME_PID_FILE" 2>/dev/null || true
fi
echo "Lock files cleaned"

echo "Cleanup complete"
