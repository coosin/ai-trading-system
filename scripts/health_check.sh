#!/bin/bash
# 健康检查脚本

APP_NAME="openclaw-trading"
APP_DIR="/home/cool/.openclaw-trading"
LOG_FILE="$APP_DIR/logs/health_check.log"
ALERT_FILE="$APP_DIR/logs/alerts.log"

mkdir -p "$(dirname "$LOG_FILE")"

echo "=== $(date) 健康检查 ===" >> "$LOG_FILE"

# 检查进程
if ! pgrep -f "python3 -m src.main" > /dev/null; then
    echo "[CRITICAL] 进程未运行！尝试重启..." | tee -a "$ALERT_FILE"
    cd "$APP_DIR" && rm -f /tmp/${APP_NAME}.*.lock /tmp/${APP_NAME}.*.pid 2>/dev/null
    nohup python3 -m src.main >> "$APP_DIR/logs/app.log" 2>&1 &
    sleep 5
    if pgrep -f "python3 -m src.main" > /dev/null; then
        echo "[INFO] 服务已自动重启" >> "$LOG_FILE"
    else
        echo "[EMERGENCY] 服务重启失败！" | tee -a "$ALERT_FILE"
    fi
fi

# 检查 API
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "[WARNING] API 服务无响应" >> "$ALERT_FILE"
fi

# 检查内存
MEM_USED=$(free | grep Mem | awk '{print int($3/$2 * 100)}')
if [ "$MEM_USED" -gt 90 ]; then
    echo "[WARNING] 内存使用过高: ${MEM_USED}%" | tee -a "$ALERT_FILE"
fi

# 检查错误日志
ERROR_COUNT=$(grep -c "ERROR" "$APP_DIR/logs/app.log" 2>/dev/null || echo "0")
if [ "$ERROR_COUNT" -gt 10 ]; then
    echo "[WARNING] 错误日志过多: ${ERROR_COUNT} 条" >> "$ALERT_FILE"
fi

echo "健康检查完成" >> "$LOG_FILE"
