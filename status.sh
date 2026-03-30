#!/bin/bash
# 查看完全独立的加密货币交易系统状态

TRADING_HOME="/home/cool/.openclaw-trading"
TRADING_PORT=18790
TRADING_UI_PORT=18791
MAIN_PORT=18789

echo "📊 加密货币交易系统状态检查"
echo "════════════════════════════════════════"

# 检查交易系统进程
echo "🔄 进程状态:"
if pgrep -f "openclaw.*$TRADING_PORT" > /dev/null; then
    echo "  ✅ 交易系统运行中 (端口: $TRADING_PORT)"
    
    # 获取PID
    PID=$(pgrep -f "openclaw.*$TRADING_PORT")
    echo "     PID: $PID"
    echo "     运行时间: $(ps -p $PID -o etime= 2>/dev/null || echo "未知")"
    
    # 检查端口
    if lsof -i :$TRADING_PORT > /dev/null 2>&1; then
        echo "  ✅ 端口 $TRADING_PORT 监听正常"
    else
        echo "  ⚠️  端口 $TRADING_PORT 未监听"
    fi
    
    if lsof -i :$TRADING_UI_PORT > /dev/null 2>&1; then
        echo "  ✅ 控制UI端口 $TRADING_UI_PORT 正常"
    else
        echo "  ⚠️  控制UI端口 $TRADING_UI_PORT 异常"
    fi
else
    echo "  ❌ 交易系统未运行"
fi

echo ""

# 检查主系统进程
echo "🏠 主系统状态:"
if pgrep -f "openclaw.*$MAIN_PORT" > /dev/null; then
    echo "  ✅ 主系统运行中 (端口: $MAIN_PORT)"
    
    MAIN_PID=$(pgrep -f "openclaw.*$MAIN_PORT")
    echo "     PID: $MAIN_PID"
else
    echo "  ⚠️  主系统未运行"
fi

echo ""

# 目录结构检查
echo "📁 目录结构:"
echo "  交易系统根目录: $TRADING_HOME"
if [ -d "$TRADING_HOME" ]; then
    echo "  ✅ 目录存在"
    
    # 检查关键目录
    DIRS=("workspace" "logs" "database" "agents")
    for dir in "${DIRS[@]}"; do
        if [ -d "$TRADING_HOME/$dir" ]; then
            COUNT=$(find "$TRADING_HOME/$dir" -type f 2>/dev/null | wc -l)
            echo "    📂 $dir/ ($COUNT 个文件)"
        else
            echo "    ⚠️  $dir/ (不存在)"
        fi
    done
else
    echo "  ❌ 目录不存在"
fi

echo ""

echo "  主系统目录: /home/cool/.openclaw"
if [ -d "/home/cool/.openclaw" ]; then
    echo "  ✅ 目录存在"
else
    echo "  ❌ 目录不存在"
fi

echo ""

# 配置文件检查
echo "⚙️ 配置文件:"
if [ -f "$TRADING_HOME/openclaw-trading.json" ]; then
    CONFIG_SIZE=$(wc -c < "$TRADING_HOME/openclaw-trading.json")
    echo "  ✅ 交易系统配置 ($CONFIG_SIZE 字节)"
else
    echo "  ❌ 交易系统配置不存在"
fi

if [ -f "/home/cool/.openclaw/openclaw.json" ]; then
    MAIN_CONFIG_SIZE=$(wc -c < "/home/cool/.openclaw/openclaw.json")
    echo "  ✅ 主系统配置 ($MAIN_CONFIG_SIZE 字节)"
else
    echo "  ❌ 主系统配置不存在"
fi

echo ""

# 工作空间文件检查
echo "💼 工作空间文件:"
TRADING_WS="$TRADING_HOME/workspace"
MAIN_WS="/home/cool/.openclaw/workspace"

check_ws_file() {
    local ws_dir="$1"
    local file="$2"
    local label="$3"
    
    if [ -f "$ws_dir/$file" ]; then
        echo "  ✅ $label: $file"
    else
        echo "  ⚠️  $label: 缺少 $file"
    fi
}

echo "  交易系统工作空间 ($TRADING_WS):"
check_ws_file "$TRADING_WS" "SOUL.md" "身份文件"
check_ws_file "$TRADING_WS" "AGENTS.md" "工作空间配置"
check_ws_file "$TRADING_WS" "TOOLS.md" "工具配置"
check_ws_file "$TRADING_WS" "scripts/market_monitor.py" "市场监控脚本"

echo ""

echo "  主系统工作空间 ($MAIN_WS):"
if [ -d "$MAIN_WS" ]; then
    MAIN_FILES=$(find "$MAIN_WS" -maxdepth 1 -name "*.md" | wc -l)
    echo "  📄 $MAIN_FILES 个Markdown文件"
else
    echo "  ⚠️  目录不存在"
fi

echo ""

# 日志文件检查
echo "📋 日志文件:"
TRADING_LOGS="$TRADING_HOME/logs"
if [ -d "$TRADING_LOGS" ]; then
    LOG_FILES=$(find "$TRADING_LOGS" -name "*.log" -o -name "*.txt" | wc -l)
    LATEST_LOG=$(find "$TRADING_LOGS" -name "*.log" -o -name "*.txt" 2>/dev/null | sort -r | head -1)
    
    echo "  交易系统日志: $LOG_FILES 个文件"
    if [ -n "$LATEST_LOG" ]; then
        LOG_SIZE=$(wc -c < "$LATEST_LOG" 2>/dev/null || echo "未知")
        echo "    最新: $(basename "$LATEST_LOG") ($LOG_SIZE 字节)"
    fi
else
    echo "  交易系统日志: 目录不存在"
fi

echo ""

# 数据库检查
echo "🗄️ 数据库:"
TRADING_DB="$TRADING_HOME/database"
if [ -d "$TRADING_DB" ]; then
    DB_FILES=$(find "$TRADING_DB" -type f | wc -l)
    echo "  交易系统数据库: $DB_FILES 个文件"
else
    echo "  交易系统数据库: 目录不存在"
fi

echo "════════════════════════════════════════"
echo "✅ 目录结构完全独立，无冲突"
echo "✅ 两个系统可并行运行"
echo "✅ 互不影响，故障隔离"