#!/bin/bash
# OpenClaw Trading System - 每日备份脚本
# 执行时间: 北京时间 11:00 (UTC 03:00)
# 保留份数: 3份

APP_NAME="openclaw-trading"
APP_DIR="/home/cool/.openclaw-trading"
BACKUP_DIR="$APP_DIR/backups"
LOG_FILE="$APP_DIR/logs/backup.log"
MAX_BACKUPS=3

# Telegram 配置
# Use explicit proxy to avoid network timeouts in restricted networks.
TELEGRAM_PROXY="http://127.0.0.1:7890"
TELEGRAM_BOT_TOKEN="8792055007:AAHpk8zwcsCXYh3bKqwDgxb4UVLZ3Qlik60"
TELEGRAM_CHAT_ID=""

mkdir -p "$BACKUP_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/daily_backup_$DATE.tar.gz"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

send_telegram() {
    local message="$1"
    if [ -n "$TELEGRAM_CHAT_ID" ]; then
        curl -s -x "$TELEGRAM_PROXY" -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
            -d chat_id="$TELEGRAM_CHAT_ID" \
            -d text="$message" \
            -d parse_mode="Markdown" > /dev/null 2>&1
    fi
}

log "========================================"
log "开始每日备份任务"

ERROR_MSG=""
SUCCESS=true

# 创建备份
log "创建备份文件: $BACKUP_FILE"

if tar -czf "$BACKUP_FILE" \
    -C "$APP_DIR/data" . \
    -C "$APP_DIR/workspace" . \
    --exclude='*.log' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='historical_data/*.parquet' 2>> "$LOG_FILE"; then
    
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log "✅ 备份创建成功: $BACKUP_FILE ($BACKUP_SIZE)"
else
    ERROR_MSG="备份创建失败"
    log "❌ 备份创建失败"
    SUCCESS=false
fi

# 清理旧备份，只保留最近3份
if [ "$SUCCESS" = true ]; then
    log "清理旧备份文件（保留最近 $MAX_BACKUPS 份）"
    
    BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/daily_backup_*.tar.gz 2>/dev/null | wc -l)
    
    if [ "$BACKUP_COUNT" -gt "$MAX_BACKUPS" ]; then
        DELETE_COUNT=$((BACKUP_COUNT - MAX_BACKUPS))
        ls -1t "$BACKUP_DIR"/daily_backup_*.tar.gz | tail -n "$DELETE_COUNT" | while read file; do
            log "删除旧备份: $file"
            rm -f "$file"
        done
        log "已删除 $DELETE_COUNT 个旧备份文件"
    fi
fi

# 检查磁盘空间
DISK_USAGE=$(df -h /home | grep -v Filesystem | awk '{print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 80 ]; then
    log "⚠️ 磁盘使用率较高: ${DISK_USAGE}%"
    ERROR_MSG="磁盘使用率: ${DISK_USAGE}%"
fi

# 检查系统状态
PROCESS_COUNT=$(pgrep -c -f "python3 -m src.main" 2>/dev/null || echo "0")
MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100}')

# 发送 Telegram 通知
if [ "$SUCCESS" = true ]; then
    MESSAGE="✅ *OpenClaw 备份完成*

📅 时间: $(date '+%Y-%m-%d %H:%M:%S')
📦 文件: \`$(basename "$BACKUP_FILE")\`
📊 大小: $BACKUP_SIZE
💾 备份数: $(ls -1 "$BACKUP_DIR"/daily_backup_*.tar.gz 2>/dev/null | wc -l)/$MAX_BACKUPS

🖥 系统状态:
• 进程: $PROCESS_COUNT 个运行中
• 内存: ${MEMORY_USAGE}%
• 磁盘: ${DISK_USAGE}%"
else
    MESSAGE="❌ *OpenClaw 备份失败*

📅 时间: $(date '+%Y-%m-%d %H:%M:%S')
⚠️ 错误: $ERROR_MSG

请检查日志: \`$LOG_FILE\`"
fi

send_telegram "$MESSAGE"

log "备份任务完成"
log "========================================"

exit 0
