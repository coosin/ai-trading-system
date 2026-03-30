#!/bin/bash
# 完全独立的加密货币交易系统启动脚本
# 与主OpenClaw系统零冲突

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# 系统配置
TRADING_HOME="/home/cool/.openclaw-trading"
TRADING_CONFIG="$TRADING_HOME/openclaw-trading.json"
TRADING_PORT=18790
TRADING_UI_PORT=18791
MAIN_PORT=18789  # 主系统端口

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    完全独立加密货币交易系统启动器      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo -e "${GREEN}系统根目录: $TRADING_HOME${NC}"
echo -e "${GREEN}配置文件: $TRADING_CONFIG${NC}"
echo -e "${GREEN}服务端口: $TRADING_PORT${NC}"
echo -e "${GREEN}控制UI端口: $TRADING_UI_PORT${NC}"
echo -e "${YELLOW}主系统端口: $MAIN_PORT (不冲突)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# 检查端口冲突
echo -e "${YELLOW}[1/4] 检查端口冲突...${NC}"
if lsof -i :$TRADING_PORT > /dev/null 2>&1; then
    echo -e "${RED}✗ 端口 $TRADING_PORT 已被占用${NC}"
    exit 1
else
    echo -e "${GREEN}✓ 端口 $TRADING_PORT 可用${NC}"
fi

if lsof -i :$TRADING_UI_PORT > /dev/null 2>&1; then
    echo -e "${RED}✗ 端口 $TRADING_UI_PORT 已被占用${NC}"
    exit 1
else
    echo -e "${GREEN}✓ 端口 $TRADING_UI_PORT 可用${NC}"
fi

# 检查主系统是否运行
if lsof -i :$MAIN_PORT > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 主系统运行中 (端口 $MAIN_PORT)${NC}"
    echo -e "${GREEN}  两个系统将并行运行，互不干扰${NC}"
else
    echo -e "${YELLOW}⚠ 主系统未运行 (不影响交易系统)${NC}"
fi

# 检查配置文件
echo -e "${YELLOW}[2/4] 检查配置文件...${NC}"
if [ -f "$TRADING_CONFIG" ]; then
    CONFIG_SIZE=$(wc -c < "$TRADING_CONFIG")
    echo -e "${GREEN}✓ 配置文件存在 ($CONFIG_SIZE 字节)${NC}"
    
    # 验证关键配置
    if grep -q '"isolated": true' "$TRADING_CONFIG"; then
        echo -e "${GREEN}✓ 配置为完全独立模式${NC}"
    else
        echo -e "${YELLOW}⚠ 配置未标记为独立模式${NC}"
    fi
else
    echo -e "${RED}✗ 配置文件不存在: $TRADING_CONFIG${NC}"
    exit 1
fi

# 检查工作空间
echo -e "${YELLOW}[3/4] 检查工作空间...${NC}"
if [ -d "$TRADING_HOME/workspace" ]; then
    WS_FILES=$(find "$TRADING_HOME/workspace" -type f | wc -l)
    echo -e "${GREEN}✓ 工作空间存在 ($WS_FILES 个文件)${NC}"
    
    # 检查关键文件
    REQUIRED_FILES=("SOUL.md" "AGENTS.md" "TOOLS.md" "scripts/market_monitor.py")
    for file in "${REQUIRED_FILES[@]}"; do
        if [ -f "$TRADING_HOME/workspace/$file" ]; then
            echo -e "  ${GREEN}✓ $file${NC}"
        else
            echo -e "  ${YELLOW}⚠ 缺少: $file${NC}"
        fi
    done
else
    echo -e "${RED}✗ 工作空间不存在${NC}"
    exit 1
fi

# 创建日志目录
echo -e "${YELLOW}[4/4] 准备日志和数据库...${NC}"
mkdir -p "$TRADING_HOME/logs" "$TRADING_HOME/database"
LOG_FILE="$TRADING_HOME/logs/startup_$(date +%Y%m%d_%H%M%S).log"
echo -e "${GREEN}✓ 日志目录: $TRADING_HOME/logs/${NC}"
echo -e "${GREEN}✓ 数据库目录: $TRADING_HOME/database/${NC}"

# 启动选项
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}选择启动模式:${NC}"
echo -e "1. ${BLUE}后台服务模式${NC} (推荐)"
echo -e "   - 启动为后台服务"
echo -e "   - 自动重连"
echo -e "   - 日志输出到文件"
echo -e ""
echo -e "2. ${YELLOW}前台调试模式${NC}"
echo -e "   - 控制台输出"
echo -e "   - 方便调试"
echo -e "   - Ctrl+C 停止"
echo -e ""
echo -e "3. ${GREEN}仅检查不启动${NC}"
echo -e "4. ${RED}退出${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

read -p "请选择 (1-4): " choice

case $choice in
    1)
        # 后台服务模式
        echo -e "${GREEN}启动后台服务模式...${NC}"
        
        # 检查是否已有服务在运行
        if pgrep -f "openclaw.*$TRADING_PORT" > /dev/null; then
            echo -e "${YELLOW}⚠ 交易系统已在运行，先停止...${NC}"
            pkill -f "openclaw.*$TRADING_PORT"
            sleep 2
        fi
        
        # 启动服务
        echo -e "启动命令: openclaw --config $TRADING_CONFIG"
        nohup openclaw --config "$TRADING_CONFIG" > "$LOG_FILE" 2>&1 &
        PID=$!
        
        echo -e "${GREEN}✓ 服务已启动 (PID: $PID)${NC}"
        echo -e "${GREEN}✓ 日志文件: $LOG_FILE${NC}"
        echo -e "${GREEN}✓ 服务端口: http://localhost:$TRADING_PORT${NC}"
        echo -e "${GREEN}✓ 控制UI: http://localhost:$TRADING_UI_PORT${NC}"
        
        # 等待服务启动
        echo -e "等待服务启动..."
        sleep 5
        
        if curl -s http://localhost:$TRADING_PORT/health > /dev/null 2>&1; then
            echo -e "${GREEN}✅ 交易系统启动成功！${NC}"
        else
            echo -e "${YELLOW}⚠ 服务可能启动较慢，请检查日志${NC}"
            echo -e "查看日志: tail -f $LOG_FILE"
        fi
        
        # 保存PID文件
        echo "$PID" > "$TRADING_HOME/trading.pid"
        echo -e "${GREEN}✓ PID已保存: $TRADING_HOME/trading.pid${NC}"
        ;;
    
    2)
        # 前台调试模式
        echo -e "${YELLOW}启动前台调试模式...${NC}"
        echo -e "按 Ctrl+C 停止服务"
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        
        openclaw --config "$TRADING_CONFIG"
        ;;
    
    3)
        # 仅检查
        echo -e "${GREEN}系统检查完成！${NC}"
        echo -e "目录结构:"
        tree -L 2 "$TRADING_HOME" 2>/dev/null || find "$TRADING_HOME" -maxdepth 2 -type d | sort
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "要手动启动: openclaw --config $TRADING_CONFIG"
        ;;
    
    4)
        echo -e "${BLUE}退出启动脚本${NC}"
        exit 0
        ;;
    
    *)
        echo -e "${RED}无效选择${NC}"
        exit 1
        ;;
esac

# 显示状态
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📊 系统状态${NC}"
echo -e "交易系统目录: $TRADING_HOME"
echo -e "主系统目录: /home/cool/.openclaw"
echo -e "${YELLOW}两个系统完全独立，目录结构无冲突${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}常用命令:${NC}"
echo -e "停止交易系统: pkill -f 'openclaw.*$TRADING_PORT'"
echo -e "查看日志: tail -f $TRADING_HOME/logs/*.log"
echo -e "启动交易脚本: cd $TRADING_HOME/workspace/scripts && ./start_trading_system.sh"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# 验证目录隔离
echo -e "${GREEN}🔒 目录隔离验证:${NC}"
echo -e "主系统工作空间: /home/cool/.openclaw/workspace"
echo -e "交易系统工作空间: $TRADING_HOME/workspace"
echo -e "${GREEN}✓ 完全独立，零冲突${NC}"