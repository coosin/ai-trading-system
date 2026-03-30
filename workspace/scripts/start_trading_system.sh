#!/bin/bash
# 加密货币交易系统启动脚本

set -e  # 遇到错误时退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 工作空间目录
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$WORKSPACE_DIR/scripts"
LOG_DIR="$WORKSPACE_DIR/logs"
CONFIG_DIR="$WORKSPACE_DIR/crypto-config"

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}  加密货币交易系统启动脚本${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "工作空间: $WORKSPACE_DIR"
echo -e "日志目录: $LOG_DIR"
echo -e "配置目录: $CONFIG_DIR"
echo -e "${BLUE}========================================${NC}"

# 创建必要目录
echo -e "${YELLOW}[1/5] 创建目录结构...${NC}"
mkdir -p "$LOG_DIR" "$CONFIG_DIR" "$WORKSPACE_DIR/database"
echo -e "${GREEN}✓ 目录创建完成${NC}"

# 检查Python环境
echo -e "${YELLOW}[2/5] 检查Python环境...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    echo -e "${GREEN}✓ Python $PYTHON_VERSION 已安装${NC}"
    
    # 检查必需的Python包
    echo -e "检查Python依赖包..."
    REQUIRED_PACKAGES=("aiohttp" "pandas" "numpy" "ccxt")
    for package in "${REQUIRED_PACKAGES[@]}"; do
        if python3 -c "import $package" &> /dev/null; then
            echo -e "  ${GREEN}✓ $package${NC}"
        else
            echo -e "  ${RED}✗ $package 未安装${NC}"
            echo -e "  安装命令: pip3 install $package"
        fi
    done
else
    echo -e "${RED}✗ Python3 未安装${NC}"
    echo -e "请先安装Python3: sudo apt install python3 python3-pip"
    exit 1
fi

# 检查配置文件
echo -e "${YELLOW}[3/5] 检查配置文件...${NC}"
if [ -f "$CONFIG_DIR/api_keys.json" ]; then
    echo -e "${GREEN}✓ API密钥配置文件存在${NC}"
else
    echo -e "${YELLOW}⚠ API密钥配置文件不存在${NC}"
    echo -e "创建示例配置文件..."
    
    cat > "$CONFIG_DIR/api_keys.json.example" << EOF
{
  "exchanges": {
    "binance": {
      "api_key": "YOUR_BINANCE_API_KEY",
      "api_secret": "YOUR_BINANCE_SECRET_KEY",
      "enable": true,
      "testnet": false
    },
    "okx": {
      "api_key": "YOUR_OKX_API_KEY",
      "api_secret": "YOUR_OKX_SECRET_KEY",
      "passphrase": "YOUR_OKX_PASSPHRASE",
      "enable": true
    },
    "coinbase": {
      "api_key": "YOUR_COINBASE_API_KEY",
      "api_secret": "YOUR_COINBASE_SECRET_KEY",
      "enable": false
    }
  },
  "warning": "⚠️ 重要提示: 不要提交此文件到版本控制！"
}
EOF
    echo -e "${GREEN}✓ 示例配置文件已创建: $CONFIG_DIR/api_keys.json.example${NC}"
    echo -e "请复制为 api_keys.json 并填入真实的API密钥"
fi

# 设置环境变量
echo -e "${YELLOW}[4/5] 设置环境变量...${NC}"
export TRADING_WORKSPACE="$WORKSPACE_DIR"
export TRADING_LOGS="$LOG_DIR"
export PYTHONPATH="$PYTHONPATH:$WORKSPACE_DIR"

# 创建环境变量文件
ENV_FILE="$WORKSPACE_DIR/.trading_env"
cat > "$ENV_FILE" << EOF
# 交易系统环境变量
export TRADING_WORKSPACE="$WORKSPACE_DIR"
export TRADING_LOGS="$LOG_DIR"
export PYTHONPATH="\$PYTHONPATH:$WORKSPACE_DIR"

# 交易所API密钥（从配置文件读取，不要硬编码）
# export BINANCE_API_KEY=""
# export BINANCE_SECRET_KEY=""
# export OKX_API_KEY=""
# export OKX_SECRET_KEY=""
# export OKX_PASSPHRASE=""

# 交易参数
export MAX_DAILY_LOSS_PERCENT=2.0
export MAX_POSITION_PERCENT=30.0
export STOP_LOSS_PERCENT=5.0
export TAKE_PROFIT_PERCENT=15.0

# 日志级别
export LOG_LEVEL="INFO"
EOF

echo -e "${GREEN}✓ 环境变量文件已创建: $ENV_FILE${NC}"
echo -e "要使用这些变量，请执行: source $ENV_FILE"

# 启动选项
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}[5/5] 选择启动模式:${NC}"
echo -e "1. 市场监控模式"
echo -e "2. 风险管理模式"
echo -e "3. 完整交易系统"
echo -e "4. 系统测试模式"
echo -e "5. 退出"
echo -e "${BLUE}========================================${NC}"

read -p "请选择 (1-5): " choice

case $choice in
    1)
        echo -e "${GREEN}启动市场监控模式...${NC}"
        cd "$SCRIPT_DIR"
        python3 market_monitor.py
        ;;
    2)
        echo -e "${GREEN}启动风险管理模式...${NC}"
        cd "$SCRIPT_DIR"
        python3 risk_management.py
        ;;
    3)
        echo -e "${GREEN}启动完整交易系统...${NC}"
        echo -e "${YELLOW}此功能正在开发中...${NC}"
        echo -e "请稍后使用: python3 trading_bot.py"
        ;;
    4)
        echo -e "${GREEN}启动系统测试...${NC}"
        # 运行测试
        cd "$SCRIPT_DIR"
        echo -e "测试市场监控..."
        python3 -c "import market_monitor; print('市场监控模块导入成功')"
        echo -e "测试风险管理..."
        python3 -c "import risk_management; print('风险管理模块导入成功')"
        echo -e "${GREEN}✓ 所有测试通过${NC}"
        ;;
    5)
        echo -e "${BLUE}退出启动脚本${NC}"
        exit 0
        ;;
    *)
        echo -e "${RED}无效的选择${NC}"
        exit 1
        ;;
esac

# 记录启动日志
LOG_FILE="$LOG_DIR/system_start_$(date +%Y%m%d_%H%M%S).log"
{
    echo "=== 交易系统启动日志 ==="
    echo "时间: $(date)"
    echo "工作空间: $WORKSPACE_DIR"
    echo "Python版本: $PYTHON_VERSION"
    echo "选择的模式: $choice"
    echo "启动用户: $(whoami)"
    echo "主机名: $(hostname)"
} > "$LOG_FILE"

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}启动完成！${NC}"
echo -e "日志文件: $LOG_FILE"
echo -e "系统状态: 运行中"
echo -e "${BLUE}========================================${NC}"

# 显示快速帮助
echo -e "${YELLOW}快速命令:${NC}"
echo -e "查看日志: tail -f $LOG_DIR/*.log"
echo -e "停止系统: pkill -f 'python3.*trading'"
echo -e "重启系统: $0"
echo -e "${BLUE}========================================${NC}"