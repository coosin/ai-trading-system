#!/bin/bash

# 全智能量化交易系统 - 环境设置脚本
# 在 Ubuntu 24.04 上安装必要的开发工具（裸机运行；不再安装 Docker）。

set -e  # 出错时退出

echo "🚀 开始设置全智能量化交易系统开发环境..."
echo "=" * 60

# 1. 更新系统
echo "1. 更新系统包..."
sudo apt update
sudo apt upgrade -y

# 2. 安装Python开发工具
echo "2. 安装Python 3.11和相关工具..."
sudo apt install -y python3.11 python3.11-dev python3.11-venv python3.11-distutils
sudo apt install -y python3-pip python3-virtualenv python3-wheel

# 3. 安装PostgreSQL和Redis客户端
echo "3. 安装数据库客户端..."
sudo apt install -y postgresql-client redis-tools

# 4. 安装开发工具
echo "4. 安装其他开发工具..."
sudo apt install -y git curl wget tree htop net-tools jq make

# 5. 创建Python虚拟环境
echo "5. 创建Python虚拟环境..."
cd /home/cool/.openclaw-trading
python3.11 -m venv venv
source venv/bin/activate

# 6. 安装Python依赖
echo "6. 安装Python依赖..."
pip install --upgrade pip
pip install wheel setuptools

# 基础依赖
pip install pydantic fastapi uvicorn sqlalchemy alembic psycopg2-binary redis aioredis

# 数据分析
pip install pandas numpy scipy scikit-learn matplotlib seaborn

# 异步和网络
pip install aiohttp httpx websockets

# 开发工具
pip install black isort flake8 mypy bandit safety pytest pytest-asyncio pytest-cov

# 7. 验证安装
echo "7. 验证安装..."
echo -n "Python: " && python --version
echo -n "pip: " && pip --version
echo -n "Git: " && git --version

# 8. 初始化项目
echo "8. 初始化项目..."
cd /home/cool/.openclaw-trading

# 创建必要的目录
mkdir -p logs data/backup

# 复制环境变量模板
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  已创建 .env 文件，请编辑配置"
fi

# 9. 运行第一个测试
echo "9. 运行第一个测试..."
if python -m pytest tests/unit/test_config_manager.py::TestConfigManager::test_initialization -xvs; then
    echo "  ✅ 测试通过！"
else
    echo "  ⚠️ 测试失败，需要安装更多依赖"
    pip install pyyaml
fi

echo ""
echo "=" * 60
echo "🎉 环境设置完成！"
echo ""
echo "📋 下一步："
echo "1. 编辑 .env 文件配置环境变量"
echo "2. 运行 'source venv/bin/activate' 激活虚拟环境"
echo "3. 运行 'make test' 运行所有测试"
echo "4. 运行 'make run' 启动开发服务器"
echo ""
echo "💡 提示："
echo "- 查看 '快速开始指南.md' 获取详细步骤"
echo "- 查看 '开发任务清单.md' 了解开发计划"
echo ""
echo "🔧 快速命令："
echo "  cd /home/cool/.openclaw-trading"
echo "  source venv/bin/activate"
echo "  make help  # 查看所有可用命令"
echo ""
echo "🚀 开始开发吧！"