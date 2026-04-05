#!/bin/bash
# OpenClaw Trading System - Health Check Script
# Run frequency: hourly
# 
# 重要：此脚本只监控系统状态，不直接启动进程
# 所有进程管理通过 systemd 进行

APP_NAME="openclaw-trading"
APP_DIR="/home/cool/.openclaw-trading"
LOG_FILE="$APP_DIR/logs/health_check.log"
ALERT_FILE="$APP_DIR/logs/alerts.log"
SERVICE_NAME="openclaw-trading.service"

# Telegram configuration
TELEGRAM_BOT_TOKEN="8792055007:AAHpk8zwcsCXYh3bKqwDgxb4UVLZ3Qlik60"
TELEGRAM_CHAT_ID="6716232147"

mkdir -p "$(dirname "$LOG_FILE")"

send_telegram() {
    local message="$1"
    if [ -n "$TELEGRAM_CHAT_ID" ]; then
        curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
            -d chat_id="$TELEGRAM_CHAT_ID" \
            -d text="$message" \
            -d parse_mode="Markdown" > /dev/null 2>&1
    fi
}

echo "=== $(date) Health Check ===" >> "$LOG_FILE"

ALERTS=""
CRITICAL=false

# Check systemd service status (preferred method)
SERVICE_STATUS=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null)

if [ "$SERVICE_STATUS" != "active" ]; then
    ALERTS="${ALERTS}WARNING: Service not active (status: $SERVICE_STATUS)\n"
    echo "[CRITICAL] Service not active!" | tee -a "$ALERT_FILE"
    
    # Try to restart via systemctl (not direct process start)
    sudo systemctl restart "$SERVICE_NAME" 2>/dev/null
    sleep 5
    
    NEW_STATUS=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null)
    if [ "$NEW_STATUS" = "active" ]; then
        ALERTS="${ALERTS}SUCCESS: Service restarted via systemctl\n"
        echo "[INFO] Service restarted via systemctl" >> "$LOG_FILE"
    else
        ALERTS="${ALERTS}ERROR: Service restart failed!\n"
        echo "[EMERGENCY] Service restart failed!" | tee -a "$ALERT_FILE"
        CRITICAL=true
    fi
fi

# Check for multiple instances (should never happen)
PROCESS_COUNT=$(pgrep -f "python.*src.main" 2>/dev/null | wc -l)
if [ "$PROCESS_COUNT" -gt 1 ]; then
    ALERTS="${ALERTS}WARNING: Multiple instances detected ($PROCESS_COUNT)\n"
    echo "[WARNING] Multiple instances detected!" | tee -a "$ALERT_FILE"
    
    # Kill all but the systemd service
    SYSTEMD_PID=$(systemctl show --property MainPID "$SERVICE_NAME" 2>/dev/null | cut -d= -f2)
    
    for PID in $(pgrep -f "python.*src.main" 2>/dev/null); do
        if [ "$PID" != "$SYSTEMD_PID" ] && [ "$PID" -gt 1 ]; then
            kill -9 "$PID" 2>/dev/null
            ALERTS="${ALERTS}Killed extra process: $PID\n"
            echo "[INFO] Killed extra process: $PID" >> "$LOG_FILE"
        fi
    done
fi

# Check API
if ! curl -s http://localhost:8000/api/v1/health > /dev/null 2>&1; then
    ALERTS="${ALERTS}WARNING: API service not responding\n"
    echo "[WARNING] API service not responding" >> "$ALERT_FILE"
fi

# Check memory
MEM_USED=$(free | grep Mem | awk '{print int($3/$2 * 100)}')
if [ "$MEM_USED" -gt 90 ]; then
    ALERTS="${ALERTS}WARNING: High memory usage: ${MEM_USED}%\n"
    echo "[WARNING] High memory usage: ${MEM_USED}%" | tee -a "$ALERT_FILE"
    CRITICAL=true
elif [ "$MEM_USED" -gt 80 ]; then
    ALERTS="${ALERTS}INFO: Memory usage: ${MEM_USED}%\n"
fi

# Check disk
DISK_USED=$(df -h /home | grep -v Filesystem | awk '{print $5}' | tr -d '%')
if [ "$DISK_USED" -gt 90 ]; then
    ALERTS="${ALERTS}WARNING: Low disk space: ${DISK_USED}%\n"
    echo "[WARNING] Low disk space: ${DISK_USED}%" | tee -a "$ALERT_FILE"
    CRITICAL=true
fi

# Check error logs
ERROR_COUNT=$(grep -c "ERROR" "$APP_DIR/logs/app.log" 2>/dev/null || echo "0")
if [ "$ERROR_COUNT" -gt 20 ]; then
    ALERTS="${ALERTS}WARNING: Too many errors in log: ${ERROR_COUNT}\n"
    echo "[WARNING] Too many errors: ${ERROR_COUNT}" >> "$ALERT_FILE"
fi

# Send Telegram notification
if [ -n "$ALERTS" ]; then
    if [ "$CRITICAL" = true ]; then
        MESSAGE="*OpenClaw System Alert*\n\n$(echo -e "$ALERTS")\nTime: $(date '+%Y-%m-%d %H:%M:%S')\nPlease check immediately!"
    else
        MESSAGE="*OpenClaw System Notice*\n\n$(echo -e "$ALERTS")\nTime: $(date '+%Y-%m-%d %H:%M:%S')"
    fi
    send_telegram "$MESSAGE"
fi

echo "Health check complete" >> "$LOG_FILE"
