#!/bin/bash

# 全智能量化交易系统 - 快速启动脚本
# 一键启动后端和前端服务

set -e  # 出错时退出

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Color

# 项目目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo -e "${BLUE}项目目录: $PROJECT_DIR${NC}"

# 端口配置
BACKEND_PORT=8000
FRONTEND_PORT=3001

# 日志目录
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

# 检查Python虚拟环境
check_venv() {
    if [ ! -d "$PROJECT_DIR/venv" ]; then
        echo -e "${YELLOW}⚠️  未找到虚拟环境，正在创建...${NC}"
        python3 -m venv "$PROJECT_DIR/venv"
        echo -e "${GREEN}✅ 虚拟环境创建成功${NC}"
    fi
    source "$PROJECT_DIR/venv/bin/activate"
}

# 安装Python依赖
install_python_deps() {
    echo -e "${BLUE}📦 检查并安装Python依赖...${NC}"
    pip install --upgrade pip -q
    pip install -r "$PROJECT_DIR/requirements.txt" -q
    echo -e "${GREEN}✅ Python依赖安装完成${NC}"
}

# 安装前端依赖
install_frontend_deps() {
    echo -e "${BLUE}📦 检查并安装前端依赖...${NC}"
    cd "$PROJECT_DIR/frontend"
    if [ ! -d "node_modules" ]; then
        npm install
    fi
    cd "$PROJECT_DIR"
    echo -e "${GREEN}✅ 前端依赖安装完成${NC}"
}

# 检查端口是否被占用
check_port() {
    local port=$1
    local service=$2
    if lsof -i :$port > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  端口 $port ($service) 已被占用${NC}"
        return 1
    fi
    return 0
}

# 启动后端服务
start_backend() {
    echo -e "${BLUE}🚀 启动后端服务...${NC}"
    
    if check_port $BACKEND_PORT "后端API"; then
        cd "$PROJECT_DIR"
        nohup python -m src.main > "$LOG_DIR/backend.log" 2>&1 &
        BACKEND_PID=$!
        echo $BACKEND_PID > "$LOG_DIR/backend.pid"
        echo -e "${GREEN}✅ 后端服务已启动 (PID: $BACKEND_PID)${NC}"
        echo -e "${GREEN}   日志文件: $LOG_DIR/backend.log${NC}"
        
        # 等待后端启动
        echo -e "${YELLOW}⏳ 等待后端服务启动...${NC}"
        sleep 5
    fi
}

# 启动前端服务
start_frontend() {
    echo -e "${BLUE}🚀 启动前端服务...${NC}"
    
    if check_port $FRONTEND_PORT "前端UI"; then
        cd "$PROJECT_DIR/frontend"
        nohup npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
        FRONTEND_PID=$!
        echo $FRONTEND_PID > "$LOG_DIR/frontend.pid"
        echo -e "${GREEN}✅ 前端服务已启动 (PID: $FRONTEND_PID)${NC}"
        echo -e "${GREEN}   日志文件: $LOG_DIR/frontend.log${NC}"
    fi
}

# 停止服务
stop_services() {
    echo -e "${RED}🛑 停止所有服务...${NC}"
    
    # 停止后端
    if [ -f "$LOG_DIR/backend.pid" ]; then
        BACKEND_PID=$(cat "$LOG_DIR/backend.pid" 2>/dev/null || true)
        if [ -n "$BACKEND_PID" ] && kill -0 $BACKEND_PID 2>/dev/null; then
            kill $BACKEND_PID 2>/dev/null || true
            echo -e "${GREEN}✅ 后端服务已停止${NC}"
        fi
        rm -f "$LOG_DIR/backend.pid"
    fi
    
    # 停止前端
    if [ -f "$LOG_DIR/frontend.pid" ]; then
        FRONTEND_PID=$(cat "$LOG_DIR/frontend.pid" 2>/dev/null || true)
        if [ -n "$FRONTEND_PID" ] && kill -0 $FRONTEND_PID 2>/dev/null; then
            kill $FRONTEND_PID 2>/dev/null || true
            echo -e "${GREEN}✅ 前端服务已停止${NC}"
        fi
        rm -f "$LOG_DIR/frontend.pid"
    fi
    
    # 清理可能残留的进程
    pkill -f "python.*src.main" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
}

# 查看状态
show_status() {
    echo -e "${BLUE}📊 服务状态${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # 后端状态
    if lsof -i :$BACKEND_PORT > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 后端API服务运行中 (端口 $BACKEND_PORT)${NC}"
        echo -e "${GREEN}   访问: http://localhost:$BACKEND_PORT/docs${NC}"
    else
        echo -e "${RED}❌ 后端API服务未运行${NC}"
    fi
    
    # 前端状态
    if lsof -i :$FRONTEND_PORT > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 前端UI服务运行中 (端口 $FRONTEND_PORT)${NC}"
        echo -e "${GREEN}   访问: http://localhost:$FRONTEND_PORT${NC}"
    else
        echo -e "${RED}❌ 前端UI服务未运行${NC}"
    fi
    
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 查看日志
show_logs() {
    local service=$1
    case $service in
        backend)
            if [ -f "$LOG_DIR/backend.log" ]; then
                tail -f "$LOG_DIR/backend.log"
            else
                echo -e "${RED}❌ 后端日志文件不存在${NC}"
            fi
            ;;
        frontend)
            if [ -f "$LOG_DIR/frontend.log" ]; then
                tail -f "$LOG_DIR/frontend.log"
            else
                echo -e "${RED}❌ 前端日志文件不存在${NC}"
            fi
            ;;
        *)
            echo -e "${YELLOW}用法: $0 logs [backend|frontend]${NC}"
            ;;
    esac
}

# 显示帮助
show_help() {
    echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     全智能量化交易系统 - 快速启动脚本                   ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${GREEN}用法:${NC} $0 [命令]"
    echo ""
    echo -e "${BLUE}命令:${NC}"
    echo -e "  ${GREEN}start${NC}      - 启动后端和前端服务"
    echo -e "  ${GREEN}stop${NC}       - 停止所有服务"
    echo -e "  ${GREEN}restart${NC}    - 重启所有服务"
    echo -e "  ${GREEN}status${NC}     - 查看服务状态"
    echo -e "  ${GREEN}logs${NC}       - 查看日志 (backend|frontend)"
    echo -e "  ${GREEN}help${NC}       - 显示帮助信息"
    echo ""
    echo -e "${BLUE}示例:${NC}"
    echo -e "  $0 start"
    echo -e "  $0 logs backend"
    echo -e "  $0 status"
    echo ""
}

# 主函数
main() {
    local command=${1:-help}
    
    case $command in
        start)
            echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
            echo -e "${BLUE}║    启动全智能量化交易系统                ║${NC}"
            echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
            
            check_venv
            install_python_deps
            install_frontend_deps
            start_backend
            start_frontend
            
            echo ""
            show_status
            echo ""
            echo -e "${GREEN}🎉 系统启动完成！${NC}"
            echo -e "${BLUE}📖 API文档: http://localhost:$BACKEND_PORT/docs${NC}"
            echo -e "${BLUE}🌐 前端界面: http://localhost:$FRONTEND_PORT${NC}"
            echo ""
            ;;
            
        stop)
            stop_services
            ;;
            
        restart)
            stop_services
            sleep 2
            check_venv
            start_backend
            start_frontend
            show_status
            ;;
            
        status)
            show_status
            ;;
            
        logs)
            show_logs $2
            ;;
            
        help)
            show_help
            ;;
            
        *)
            echo -e "${RED}❌ 未知命令: $command${NC}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
