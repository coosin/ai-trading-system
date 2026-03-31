#!/bin/bash

# 部署脚本 - OpenClaw Trading

set -e

echo "=== OpenClaw Trading 部署脚本 ==="

# 配置变量
PROJECT_DIR="$(dirname "$0")"
VENV_DIR="$PROJECT_DIR/venv"
REQUIREMENTS_FILE="$PROJECT_DIR/requirements.txt"
MAIN_SCRIPT="$PROJECT_DIR/src/main.py"

# 函数定义
function setup_venv() {
    echo "创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
    echo "激活虚拟环境..."
    source "$VENV_DIR/bin/activate"
    echo "升级 pip..."
    pip install --upgrade pip
    if [ -f "$REQUIREMENTS_FILE" ]; then
        echo "安装依赖..."
        pip install -r "$REQUIREMENTS_FILE"
    else
        echo "警告: 未找到 requirements.txt 文件"
    fi
}

function start_service() {
    echo "启动服务..."
    if [ -f "/etc/systemd/system/openclaw-trading-gateway.service" ]; then
        sudo systemctl start openclaw-trading-gateway.service
        echo "服务已启动"
    else
        echo "启动应用..."
        source "$VENV_DIR/bin/activate"
        python "$MAIN_SCRIPT" &
        echo "应用已在后台启动"
    fi
}

function stop_service() {
    echo "停止服务..."
    if [ -f "/etc/systemd/system/openclaw-trading-gateway.service" ]; then
        sudo systemctl stop openclaw-trading-gateway.service
        echo "服务已停止"
    else
        echo "查找并停止应用进程..."
        pkill -f "python.*main.py"
        echo "应用已停止"
    fi
}

function restart_service() {
    echo "重启服务..."
    if [ -f "/etc/systemd/system/openclaw-trading-gateway.service" ]; then
        sudo systemctl restart openclaw-trading-gateway.service
        echo "服务已重启"
    else
        stop_service
        start_service
    fi
}

function check_status() {
    echo "检查服务状态..."
    if [ -f "/etc/systemd/system/openclaw-trading-gateway.service" ]; then
        sudo systemctl status openclaw-trading-gateway.service
    else
        echo "检查应用进程..."
        ps aux | grep "python.*main.py" | grep -v grep
    fi
}

function deploy() {
    echo "开始部署..."
    setup_venv
    stop_service
    start_service
    check_status
    echo "部署完成!"
}

# 主菜单
function main_menu() {
    echo "\n请选择操作:"
    echo "1. 部署项目"
    echo "2. 启动服务"
    echo "3. 停止服务"
    echo "4. 重启服务"
    echo "5. 检查状态"
    echo "6. 设置虚拟环境"
    echo "7. 退出"
    read -p "输入选项: " choice
    
    case $choice in
        1) deploy ;;
        2) start_service ;;
        3) stop_service ;;
        4) restart_service ;;
        5) check_status ;;
        6) setup_venv ;;
        7) exit 0 ;;
        *) echo "无效选项" ;;
    esac
    
    main_menu
}

# 执行主菜单
main_menu
