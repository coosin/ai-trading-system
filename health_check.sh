#!/bin/bash
# OpenClaw Trading System - 健康检查脚本

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================"
echo "  OpenClaw Trading System 健康检查"
echo "========================================"
echo ""

ERRORS=0
WARNINGS=0

# 1. 检查Python环境
echo -e "${GREEN}[1/10]${NC} 检查Python环境..."
PYTHON_VERSION=$(python3 --version 2>&1)
if [ $? -eq 0 ]; then
    echo "  ✓ $PYTHON_VERSION"
else
    echo -e "  ${RED}✗ Python未安装${NC}"
    ERRORS=$((ERRORS + 1))
fi

# 2. 检查核心依赖
echo -e "${GREEN}[2/10]${NC} 检查核心依赖..."
MISSING=""
for dep in numpy pandas aiohttp yaml redis sqlalchemy psutil dotenv sklearn; do
    if ! python3 -c "import $dep" 2>/dev/null; then
        MISSING="$MISSING $dep"
    fi
done
if [ -z "$MISSING" ]; then
    echo "  ✓ 所有核心依赖已安装"
else
    echo -e "  ${RED}✗ 缺少依赖:$MISSING${NC}"
    ERRORS=$((ERRORS + 1))
fi

# 3. 检查配置文件
echo -e "${GREEN}[3/10]${NC} 检查配置文件..."
if [ -f "config/config.yaml" ]; then
    echo "  ✓ config/config.yaml 存在"
else
    echo -e "  ${RED}✗ config/config.yaml 不存在${NC}"
    ERRORS=$((ERRORS + 1))
fi

if [ -f ".env" ]; then
    echo "  ✓ .env 存在"
else
    echo -e "  ${YELLOW}! .env 不存在，请从 .env.example 复制${NC}"
    WARNINGS=$((WARNINGS + 1))
fi

# 4. 检查数据目录
echo -e "${GREEN}[4/10]${NC} 检查数据目录..."
for dir in data logs workspace; do
    if [ -d "$dir" ]; then
        SIZE=$(du -sh "$dir" 2>/dev/null | awk '{print $1}')
        echo "  ✓ $dir/ ($SIZE)"
    else
        echo -e "  ${YELLOW}! $dir/ 不存在${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
done

# 5. 检查代理配置
echo -e "${GREEN}[5/10]${NC} 检查代理配置..."
if nc -z 127.0.0.1 7890 2>/dev/null; then
    echo "  ✓ Clash代理可用 (127.0.0.1:7890)"
elif [ -n "$HTTP_PROXY" ] || [ -n "$HTTPS_PROXY" ]; then
    echo "  ✓ 环境变量代理已配置"
else
    echo -e "  ${YELLOW}! 未检测到代理配置${NC}"
    WARNINGS=$((WARNINGS + 1))
fi

# 6. 检查API密钥
echo -e "${GREEN}[6/10]${NC} 检查API密钥配置..."
if [ -f ".env" ]; then
    # 检查讯飞API
    if grep -q "XUNFEI_API_KEY=your_" .env 2>/dev/null || ! grep -q "XUNFEI_API_KEY" .env 2>/dev/null; then
        echo -e "  ${YELLOW}! 讯飞API密钥未配置${NC}"
        WARNINGS=$((WARNINGS + 1))
    else
        echo "  ✓ 讯飞API密钥已配置"
    fi
    
    # 检查Telegram
    if grep -q "TELEGRAM_BOT_TOKEN=your_" .env 2>/dev/null || ! grep -q "TELEGRAM_BOT_TOKEN" .env 2>/dev/null; then
        echo -e "  ${YELLOW}! Telegram未配置${NC}"
    else
        echo "  ✓ Telegram已配置"
    fi
    
    # 检查交易所
    if grep -q "OKX_API_KEY=your_" .env 2>/dev/null || ! grep -q "OKX_API_KEY" .env 2>/dev/null; then
        echo -e "  ${YELLOW}! 交易所API未配置 (模拟模式可忽略)${NC}"
    else
        echo "  ✓ 交易所API已配置"
    fi
else
    echo -e "  ${RED}✗ .env文件不存在${NC}"
    ERRORS=$((ERRORS + 1))
fi

# 7. 检查模块导入
echo -e "${GREEN}[7/10]${NC} 检查核心模块..."
MODULES_OK=true
for module in unified_intelligent_memory user_intent_recognizer proxy_manager; do
    if python3 -c "from src.modules.core import $module" 2>/dev/null; then
        echo "  ✓ $module"
    else
        echo -e "  ${RED}✗ $module 导入失败${NC}"
        MODULES_OK=false
        ERRORS=$((ERRORS + 1))
    fi
done

# 8. 检查数据库
echo -e "${GREEN}[8/10]${NC} 检查数据库..."
if [ -f "data/trading.db" ]; then
    SIZE=$(du -sh data/trading.db 2>/dev/null | awk '{print $1}')
    echo "  ✓ trading.db ($SIZE)"
else
    echo -e "  ${YELLOW}! trading.db 不存在 (首次运行会自动创建)${NC}"
fi

# 9. 检查内存使用
echo -e "${GREEN}[9/10]${NC} 检查系统资源..."
MEMORY_USAGE=$(free | awk '/Mem:/ {printf "%.1f", $3/$2 * 100}')
DISK_USAGE=$(df -h . | awk 'NR==2 {print $5}' | tr -d '%')
echo "  内存使用: ${MEMORY_USAGE}%"
echo "  磁盘使用: ${DISK_USAGE}%"
if [ "${DISK_USAGE%.*}" -gt 90 ]; then
    echo -e "  ${RED}✗ 磁盘空间不足${NC}"
    ERRORS=$((ERRORS + 1))
fi

# 10. 检查端口
echo -e "${GREEN}[10/10]${NC} 检查端口..."
if nc -z 127.0.0.1 8000 2>/dev/null; then
    echo -e "  ${YELLOW}! 端口 8000 已被占用${NC}"
    WARNINGS=$((WARNINGS + 1))
else
    echo "  ✓ 端口 8000 可用"
fi

# 汇总
echo ""
echo "========================================"
echo "  检查结果汇总"
echo "========================================"
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ 系统健康，可以启动${NC}"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ 系统基本健康，但有 $WARNINGS 个警告${NC}"
    echo "  建议检查警告项后启动"
    exit 0
else
    echo -e "${RED}✗ 发现 $ERRORS 个错误, $WARNINGS 个警告${NC}"
    echo "  请修复错误后再启动"
    exit 1
fi
