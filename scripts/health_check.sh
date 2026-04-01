#!/bin/bash
# OpenClaw Trading System - Health Check Script
# Run frequency: hourly

APP_NAME="openclaw-trading"
APP_DIR="/home/cool/.openclaw-trading"
LOG_FILE="$APP_DIR/logs/health_check.log"
ALERT_FILE="$APP_DIR/logs/alerts.log"

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

# Check process
if ! pgrep -f "python3 -m src.main" > /dev/null; then
    ALERTS="${ALERTS}WARNING: Process not running!\n"
    echo "[CRITICAL] Process not running!" | tee -a "$ALERT_FILE"
    
    # Clean lock files
    rm -f /tmp/${APP_NAME}.lock /tmp/${APP_NAME}.pid 2>/dev/null
    
    # Try to restart
    cd "$APP_DIR" && nohup python3 -m src.main >> "$APP_DIR/logs/app.log" 2>&1 &
    sleep 5
    
    if pgrep -f "python3 -m src.main" > /dev/null; then
        ALERTS="${ALERTS}SUCCESS: Service auto-restarted\n"
        echo "[INFO] Service auto-restarted" >> "$LOG_FILE"
    else
        ALERTS="${ALERTS}ERROR: Service restart failed!\n"
        echo "[EMERGENCY] Service restart failed!" | tee -a "$ALERT_FILE"
        CRITICAL=true
    fi
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
