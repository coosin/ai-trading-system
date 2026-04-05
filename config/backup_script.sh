#!/bin/bash

# 交易系统备份脚本
# 每天凌晨2点执行

set -e

# 配置
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup-$DATE.tar.gz"
RETENTION_DAYS=30

# 日志函数
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# 检查目录
check_directories() {
    log "检查备份目录..."
    
    if [ ! -d "$BACKUP_DIR" ]; then
        log "创建备份目录: $BACKUP_DIR"
        mkdir -p "$BACKUP_DIR"
    fi
    
    # 创建子目录
    mkdir -p "$BACKUP_DIR/daily"
    mkdir -p "$BACKUP_DIR/weekly"
    mkdir -p "$BACKUP_DIR/monthly"
    mkdir -p "$BACKUP_DIR/logs"
}

# 备份数据库
backup_database() {
    log "备份PostgreSQL数据库..."
    
    local DB_BACKUP_DIR="$BACKUP_DIR/database"
    mkdir -p "$DB_BACKUP_DIR"
    
    # 备份所有数据库
    pg_dumpall -h postgres -U trader | gzip > "$DB_BACKUP_DIR/postgres-full-$DATE.sql.gz"
    
    # 备份单个数据库
    pg_dump -h postgres -U trader trading_db | gzip > "$DB_BACKUP_DIR/trading_db-$DATE.sql.gz"
    
    log "数据库备份完成"
}

# 备份Redis
backup_redis() {
    log "备份Redis数据..."
    
    local REDIS_BACKUP_DIR="$BACKUP_DIR/redis"
    mkdir -p "$REDIS_BACKUP_DIR"
    
    # 使用redis-cli备份
    redis-cli -h redis SAVE
    cp /source/redis/dump.rdb "$REDIS_BACKUP_DIR/dump-$DATE.rdb"
    
    log "Redis备份完成"
}

# 备份配置文件
backup_configs() {
    log "备份配置文件..."
    
    local CONFIG_BACKUP_DIR="$BACKUP_DIR/config"
    mkdir -p "$CONFIG_BACKUP_DIR"
    
    # 备份应用配置
    cp -r /app/config "$CONFIG_BACKUP_DIR/config-$DATE"
    
    # 备份Docker配置
    cp /app/docker-compose.yml "$CONFIG_BACKUP_DIR/docker-compose-$DATE.yml"
    cp /app/Dockerfile "$CONFIG_BACKUP_DIR/Dockerfile-$DATE"
    cp /app/requirements.txt "$CONFIG_BACKUP_DIR/requirements-$DATE.txt"
    
    log "配置文件备份完成"
}

# 备份数据文件
backup_data() {
    log "备份数据文件..."
    
    local DATA_BACKUP_DIR="$BACKUP_DIR/data"
    mkdir -p "$DATA_BACKUP_DIR"
    
    # 备份工作区
    tar -czf "$DATA_BACKUP_DIR/workspace-$DATE.tar.gz" -C /app workspace
    
    # 备份日志
    tar -czf "$DATA_BACKUP_DIR/logs-$DATE.tar.gz" -C /app logs
    
    # 备份缓存
    tar -czf "$DATA_BACKUP_DIR/cache-$DATE.tar.gz" -C /app cache
    
    log "数据文件备份完成"
}

# 备份监控数据
backup_monitoring() {
    log "备份监控数据..."
    
    local MONITORING_BACKUP_DIR="$BACKUP_DIR/monitoring"
    mkdir -p "$MONITORING_BACKUP_DIR"
    
    # 备份Prometheus数据
    tar -czf "$MONITORING_BACKUP_DIR/prometheus-$DATE.tar.gz" -C /source prometheus
    
    # 备份Grafana数据
    tar -czf "$MONITORING_BACKUP_DIR/grafana-$DATE.tar.gz" -C /source grafana
    
    # 备份Elasticsearch数据
    tar -czf "$MONITORING_BACKUP_DIR/elasticsearch-$DATE.tar.gz" -C /source elasticsearch
    
    log "监控数据备份完成"
}

# 创建完整备份
create_full_backup() {
    log "创建完整备份..."
    
    # 临时目录
    local TEMP_DIR="/tmp/backup-$DATE"
    mkdir -p "$TEMP_DIR"
    
    # 复制所有备份到临时目录
    cp -r "$BACKUP_DIR/database" "$TEMP_DIR/"
    cp -r "$BACKUP_DIR/redis" "$TEMP_DIR/"
    cp -r "$BACKUP_DIR/config" "$TEMP_DIR/"
    cp -r "$BACKUP_DIR/data" "$TEMP_DIR/"
    cp -r "$BACKUP_DIR/monitoring" "$TEMP_DIR/"
    
    # 创建备份清单
    cat > "$TEMP_DIR/backup-manifest.json" << EOF
{
    "backup_date": "$(date -Iseconds)",
    "backup_type": "full",
    "components": [
        "postgresql",
        "redis",
        "configurations",
        "workspace_data",
        "logs",
        "cache",
        "monitoring_data"
    ],
    "system_info": {
        "hostname": "$(hostname)",
        "timestamp": "$(date +%s)"
    }
}
EOF
    
    # 压缩完整备份
    tar -czf "$BACKUP_FILE" -C "$TEMP_DIR" .
    
    # 清理临时目录
    rm -rf "$TEMP_DIR"
    
    log "完整备份创建完成: $BACKUP_FILE"
    log "备份大小: $(du -h "$BACKUP_FILE" | cut -f1)"
}

# 清理旧备份
cleanup_old_backups() {
    log "清理旧备份..."
    
    # 清理每日备份（保留30天）
    find "$BACKUP_DIR" -name "backup-*.tar.gz" -mtime +$RETENTION_DAYS -delete
    
    # 清理数据库备份（保留7天）
    find "$BACKUP_DIR/database" -name "*.sql.gz" -mtime +7 -delete
    
    # 清理Redis备份（保留7天）
    find "$BACKUP_DIR/redis" -name "*.rdb" -mtime +7 -delete
    
    # 清理配置备份（保留30天）
    find "$BACKUP_DIR/config" -type d -name "config-*" -mtime +30 -exec rm -rf {} \;
    find "$BACKUP_DIR/config" -name "*.yml" -mtime +30 -delete
    find "$BACKUP_DIR/config" -name "Dockerfile-*" -mtime +30 -delete
    find "$BACKUP_DIR/config" -name "requirements-*" -mtime +30 -delete
    
    # 清理数据备份（保留14天）
    find "$BACKUP_DIR/data" -name "*.tar.gz" -mtime +14 -delete
    
    # 清理监控备份（保留30天）
    find "$BACKUP_DIR/monitoring" -name "*.tar.gz" -mtime +30 -delete
    
    log "旧备份清理完成"
}

# 验证备份
verify_backup() {
    log "验证备份..."
    
    # 检查备份文件是否存在
    if [ ! -f "$BACKUP_FILE" ]; then
        log "错误: 备份文件不存在"
        return 1
    fi
    
    # 检查备份文件大小
    local BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE")
    if [ "$BACKUP_SIZE" -lt 1000 ]; then
        log "警告: 备份文件过小 ($BACKUP_SIZE 字节)"
    fi
    
    # 检查备份文件完整性
    if ! tar -tzf "$BACKUP_FILE" > /dev/null 2>&1; then
        log "错误: 备份文件损坏"
        return 1
    fi
    
    log "备份验证通过"
    return 0
}

# 发送备份通知
send_notification() {
    log "发送备份通知..."
    
    local BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    local STATUS=$1
    
    # 这里可以集成邮件、Slack、Telegram等通知
    cat > "$BACKUP_DIR/logs/backup-report-$DATE.txt" << EOF
备份报告 - $(date)
====================
状态: $STATUS
时间: $(date)
备份文件: $BACKUP_FILE
备份大小: $BACKUP_SIZE
组件: 数据库, Redis, 配置, 数据, 监控
保留策略: $RETENTION_DAYS 天
EOF
    
    log "备份报告已保存: $BACKUP_DIR/logs/backup-report-$DATE.txt"
}

# 主函数
main() {
    log "开始备份流程..."
    
    # 检查目录
    check_directories
    
    # 执行备份
    backup_database
    backup_redis
    backup_configs
    backup_data
    backup_monitoring
    
    # 创建完整备份
    create_full_backup
    
    # 验证备份
    if verify_backup; then
        # 清理旧备份
        cleanup_old_backups
        
        # 发送成功通知
        send_notification "SUCCESS"
        
        log "备份流程完成"
    else
        # 发送失败通知
        send_notification "FAILED"
        
        log "备份流程失败"
        exit 1
    fi
}

# 执行主函数
main "$@"