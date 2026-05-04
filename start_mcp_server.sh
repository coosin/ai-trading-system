#!/bin/bash
# OpenClaw MCP 服务器启动脚本
# 非侵入式集成方案

set -e

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENCLAW_DIR="/home/cool/ai-trading-system"
MCP_ADAPTER_DIR="${OPENCLAW_DIR}/mcp_adapter"
LOG_DIR="${OPENCLAW_DIR}/logs/collaboration"
PIDFILE="${LOG_DIR}/mcp_server.pid"

# 创建目录
mkdir -p "${MCP_ADAPTER_DIR}" "${LOG_DIR}"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

# 检查依赖
check_dependency() {
    python3 -c "import $1" 2>/dev/null || {
        echo "Installing $1..."
        pip3 install "$1" --quiet
    }
}

echo "Checking dependencies..."
check_dependency aiohttp
check_dependency requests

# 可选的 MCP SDK
if python3 -c "import mcp" 2>/dev/null; then
    echo "MCP SDK available"
    MCP_AVAILABLE=1
else
    echo "MCP SDK not available, will use HTTP fallback mode"
    MCP_AVAILABLE=0
fi

# 复制适配器脚本到目标位置 (如果不存在)
if [ ! -f "${MCP_ADAPTER_DIR}/openclaw_mcp_server.py" ]; then
    echo "Installing MCP adapter..."
    # 从工作区复制
    if [ -f "${SCRIPT_DIR}/mcp_adapter/openclaw_mcp_server.py" ]; then
        cp "${SCRIPT_DIR}/mcp_adapter/openclaw_mcp_server.py" "${MCP_ADAPTER_DIR}/"
    else
        echo "Error: MCP adapter script not found"
        exit 1
    fi
fi

# 检查 OpenClaw 是否运行
check_openclaw() {
    if curl -s http://localhost:18789/api/v1/status > /dev/null 2>&1; then
        echo "OpenClaw is running"
        return 0
    else
        echo "Warning: OpenClaw not responding on port 18789"
        return 1
    fi
}

# 启动 HTTP 模式 (备用)
start_http_mode() {
    echo "Starting OpenClaw MCP server in HTTP mode on port 18888..."
    nohup python3 "${MCP_ADAPTER_DIR}/openclaw_mcp_server.py" \
        --mode http \
        --port 18888 \
        >> "${LOG_DIR}/mcp_server.log" 2>&1 &

    echo $! > "${PIDFILE}"
    echo "MCP server started with PID $(cat ${PIDFILE})"

    # 等待启动
    sleep 2
    if curl -s http://localhost:18888/health > /dev/null 2>&1; then
        echo "MCP server is healthy"
    else
        echo "Warning: MCP server health check failed"
    fi
}

# 停止
stop_server() {
    if [ -f "${PIDFILE}" ]; then
        PID=$(cat "${PIDFILE}")
        if kill -0 "${PID}" 2>/dev/null; then
            echo "Stopping MCP server (PID ${PID})..."
            kill "${PID}"
            rm -f "${PIDFILE}"
            echo "Stopped"
        else
            echo "MCP server not running"
            rm -f "${PIDFILE}"
        fi
    else
        echo "PID file not found"
    fi
}

# 状态
status() {
    if [ -f "${PIDFILE}" ]; then
        PID=$(cat "${PIDFILE}")
        if kill -0 "${PID}" 2>/dev/null; then
            echo "MCP server is running (PID ${PID})"
            curl -s http://localhost:18888/health 2>/dev/null || echo "Health check failed"
        else
            echo "MCP server not running (stale PID file)"
        fi
    else
        echo "MCP server not running"
    fi
}

# 主逻辑
case "${1:-start}" in
    start)
        check_openclaw || true
        start_http_mode
        ;;
    stop)
        stop_server
        ;;
    restart)
        stop_server
        sleep 1
        check_openclaw || true
        start_http_mode
        ;;
    status)
        status
        ;;
    install)
        echo "Installing MCP adapter files..."
        mkdir -p "${MCP_ADAPTER_DIR}"
        if [ -f "${SCRIPT_DIR}/mcp_adapter/openclaw_mcp_server.py" ]; then
            cp "${SCRIPT_DIR}/mcp_adapter/openclaw_mcp_server.py" "${MCP_ADAPTER_DIR}/"
            echo "Installed to ${MCP_ADAPTER_DIR}"
        fi
        mkdir -p "${LOG_DIR}"
        echo "Installation complete"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|install}"
        exit 1
        ;;
esac
