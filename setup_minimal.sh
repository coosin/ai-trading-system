#!/bin/bash

# 最小化安装脚本
# 只安装最必要的依赖
#
# 仅 Docker 部署时无需本脚本；见 DEVELOPMENT.md「仅 Docker 运行」。

set -e

echo "📦 最小化环境安装..."
echo "=" * 40

# 1. 安装Python 3.11和venv
echo "1. 安装Python 3.11..."
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# 2. 安装pip
echo "2. 安装pip..."
sudo apt install -y python3-pip

# 3. 创建虚拟环境
echo "3. 创建虚拟环境..."
cd /home/cool/.openclaw-trading
python3.11 -m venv venv
source venv/bin/activate

# 4. 安装基础Python包
echo "4. 安装Python包..."
pip install --upgrade pip
pip install pydantic pytest pytest-asyncio pyyaml

# 5. 验证
echo "5. 验证安装..."
python --version
pip list | grep -E "(pydantic|pytest|pyyaml)"

echo ""
echo "✅ 最小化安装完成！"
echo ""
echo "运行测试："
echo "  cd /home/cool/.openclaw-trading"
echo "  source venv/bin/activate"
echo "  python -m pytest tests/unit/test_config_manager.py -v"