#!/bin/bash
# OpenClaw Trading System - 生产环境启动脚本
# 用法: ./start_production.sh [选项]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 项目根目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# 默认配置
MODE="${1:-simulation}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
API_PORT="${API_PORT:-8000}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  OpenClaw Trading System${NC}"
echo -e "${GREEN}  生产环境启动${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查Python版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓${NC} Python版本: $PYTHON_VERSION"

# 检查.env文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}!${NC} .env文件不存在，从模板创建..."
    cp .env.example .env
    echo -e "${YELLOW}!${NC} 请编辑 .env 文件配置您的API密钥"
fi

# 检查必要目录
for dir in data logs workspace config; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo -e "${GREEN}✓${NC} 创建目录: $dir"
    fi
done

# 检查代理设置
if [ -n "$HTTP_PROXY" ] || [ -n "$HTTPS_PROXY" ]; then
    echo -e "${GREEN}✓${NC} 代理已配置: ${HTTP_PROXY:-$HTTPS_PROXY}"
else
    echo -e "${YELLOW}!${NC} 未配置代理，如需访问外网请配置 HTTP_PROXY"
fi

# 检查Clash代理
if nc -z 127.0.0.1 7890 2>/dev/null; then
    echo -e "${GREEN}✓${NC} 检测到Clash代理 (端口 7890)"
    export HTTP_PROXY="http://127.0.0.1:7890"
    export HTTPS_PROXY="http://127.0.0.1:7890"
fi

# 检查依赖
echo ""
echo -e "${GREEN}检查依赖...${NC}"
MISSING_DEPS=""
for dep in numpy pandas aiohttp yaml redis sqlalchemy psutil dotenv sklearn; do
    if ! python3 -c "import $dep" 2>/dev/null; then
        MISSING_DEPS="$MISSING_DEPS $dep"
    fi
done

if [ -n "$MISSING_DEPS" ]; then
    echo -e "${RED}✗${NC} 缺少依赖:$MISSING_DEPS"
    echo -e "${YELLOW}!${NC} 请运行: pip install -r requirements.txt"
    exit 1
fi
echo -e "${GREEN}✓${NC} 所有核心依赖已安装"

# 显示配置
echo ""
echo -e "${GREEN}启动配置:${NC}"
echo "  模式: $MODE"
echo "  日志级别: $LOG_LEVEL"
echo "  API端口: $API_PORT"
echo ""

# 设置环境变量
export MODE
export LOG_LEVEL
export API_PORT
export PYTHONPATH="$PROJECT_DIR"

# 启动系统
echo -e "${GREEN}启动交易系统...${NC}"
case "$MODE" in
    simulation|paper_trading|live_trading)
        python3 src/main.py --mode "$MODE" --port "$API_PORT"
        ;;
    backtest)
        python3 src/main.py --mode backtest "${@:2}"
        ;;
    *)
        echo -e "${RED}✗${NC} 未知模式: $MODE"
        echo "可用模式: simulation, paper_trading, live_trading, backtest"
        exit 1
        ;;
esac
