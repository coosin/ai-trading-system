#!/usr/bin/env python3
"""
OpenClaw MCP 服务器适配器
为 Hermes 提供标准化的 MCP 接口，非侵入式集成
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, AsyncGenerator
from contextlib import asynccontextmanager

# 配置
OPENCLAW_API_URL = os.getenv("OPENCLAW_API_URL", "http://localhost:18789")
COLLAB_LOG_PATH = Path(os.getenv("COLLAB_LOG_PATH", "/home/cool/ai-trading-system/logs/collaboration/events.log"))
MCP_SERVER_NAME = "openclaw-mcp-server"
MCP_VERSION = "1.0.0"

# 日志设置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/cool/ai-trading-system/logs/collaboration/mcp_server.log'),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)


class OpenClawClient:
    """OpenClaw API 客户端"""

    def __init__(self, base_url: str = OPENCLAW_API_URL):
        self.base_url = base_url.rstrip('/')
        self.session: Optional[Any] = None
        try:
            import aiohttp
            self.aiohttp = aiohttp
        except ImportError:
            logger.warning("aiohttp not available, using sync requests")
            self.aiohttp = None
            import requests
            self.requests = requests

    async def __aenter__(self):
        if self.aiohttp:
            self.session = self.aiohttp.ClientSession(timeout=self.aiohttp.ClientTimeout(total=30))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session and self.aiohttp:
            await self.session.close()

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """通用 API 请求"""
        url = f"{self.base_url}{endpoint}"
        try:
            if self.aiohttp and self.session:
                async with self.session.request(method, url, **kwargs) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        text = await response.text()
                        logger.error(f"API error {response.status}: {text}")
                        return {"error": f"HTTP {response.status}", "message": text}
            else:
                # 同步回退
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None, lambda: self.requests.request(method, url, timeout=30, **kwargs)
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"error": f"HTTP {response.status_code}", "message": response.text}
        except asyncio.TimeoutError:
            return {"error": "timeout", "message": "Request timeout"}
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return {"error": "request_failed", "message": str(e)}

    async def get_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return await self._request("GET", "/api/v1/status")

    async def get_positions(self) -> Dict[str, Any]:
        """获取持仓信息"""
        return await self._request("GET", "/api/v1/positions")

    async def get_account(self) -> Dict[str, Any]:
        """获取账户信息"""
        return await self._request("GET", "/api/v1/account")

    async def get_modules(self) -> Dict[str, Any]:
        """获取模块状态"""
        return await self._request("GET", "/api/v1/modules")

    async def reload_config(self) -> Dict[str, Any]:
        """重载配置"""
        return await self._request("POST", "/api/v1/config/reload")


class CollaborationLogger:
    """协作日志记录器 - 用于记忆同步"""

    def __init__(self, log_path: Path = COLLAB_LOG_PATH):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._buffer: List[Dict] = []
        self._flush_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def log_event(self, event_type: str, source: str, data: Dict[str, Any]):
        """记录事件到协作日志"""
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_id": f"{source}_{datetime.utcnow().timestamp()}",
            "source": source,
            "type": event_type,
            "data": data
        }
        async with self._lock:
            self._buffer.append(event)

        # 延迟批量写入
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._delayed_flush())

    async def _delayed_flush(self, delay: float = 0.5):
        """延迟批量写入"""
        await asyncio.sleep(delay)
        await self._flush()

    async def _flush(self):
        """批量写入日志"""
        async with self._lock:
            if not self._buffer:
                return

            events_to_write = self._buffer.copy()
            self._buffer.clear()

        try:
            with open(self.log_path, 'a') as f:
                for event in events_to_write:
                    f.write(json.dumps(event, ensure_ascii=False) + '\n')
                    f.flush()
        except Exception as e:
            logger.error(f"Failed to write collaboration log: {e}")
            # 恢复缓冲区
            async with self._lock:
                self._buffer = events_to_write + self._buffer

    async def tail_events(self, last_n: int = 100) -> List[Dict[str, Any]]:
        """读取最近的事件"""
        events = []
        if not self.log_path.exists():
            return events

        try:
            with open(self.log_path, 'r') as f:
                lines = f.readlines()
                for line in lines[-last_n:]:
                    try:
                        events.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Failed to read collaboration log: {e}")

        return events


# MCP 协议支持检测
MCP_AVAILABLE = False
Server = None
stdio_server = None
Tool = None
TextContent = None
InitializationOptions = None

try:
    from mcp.server import Server as MCPServer
    from mcp.server.stdio import stdio_server as mcp_stdio_server
    from mcp.types import TextContent as MCPTextContent, Tool as MCPTool
    from mcp.server.models import InitializationOptions as MCPInitOptions
    Server = MCPServer
    stdio_server = mcp_stdio_server
    TextContent = MCPTextContent
    Tool = MCPTool
    InitializationOptions = MCPInitOptions
    MCP_AVAILABLE = True
    logger.info("MCP SDK loaded successfully")
except ImportError:
    logger.warning("MCP SDK not available, running in HTTP fallback mode")


# 工具定义
TOOLS_SCHEMA = [
    {
        "name": "get_openclaw_status",
        "description": "获取 OpenClaw 交易系统整体状态，包括模块健康度、策略状态等",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_positions",
        "description": "获取当前持仓信息，包括各交易对的仓位、方向、盈亏等",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_account_summary",
        "description": "获取账户摘要信息，包括余额、保证金、风险等级等",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_module_health",
        "description": "获取各模块健康状态",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "reload_configuration",
        "description": "重载 OpenClaw 配置文件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "confirm": {"type": "boolean", "description": "确认重载操作"}
            },
            "required": ["confirm"]
        }
    },
    {
        "name": "get_recent_events",
        "description": "获取最近的协作事件日志，用于记忆同步",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "返回事件数量", "default": 50}
            }
        }
    },
    {
        "name": "publish_event",
        "description": "发布事件到协作日志，供其他智能体订阅",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_type": {"type": "string", "description": "事件类型: decision, observation, action, alert"},
                "data": {"type": "object", "description": "事件数据"}
            },
            "required": ["event_type", "data"]
        }
    }
]


class OpenClawMCPServer:
    """OpenClaw MCP 服务器"""

    def __init__(self):
        self.client = OpenClawClient()
        self.logger = CollaborationLogger()
        self.server = None
        if MCP_AVAILABLE:
            self.server = Server(MCP_SERVER_NAME)
            self._setup_handlers()

    def _setup_handlers(self):
        """设置 MCP 处理器"""
        if not self.server:
            return

        @self.server.list_tools()
        async def list_tools():
            return [Tool(**t) for t in TOOLS_SCHEMA]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]):
            """处理工具调用"""
            logger.info(f"Tool called: {name} with args: {arguments}")
            result_text = await self._handle_tool(name, arguments)
            return [TextContent(type="text", text=result_text)]

    async def _handle_tool(self, name: str, arguments: Dict) -> str:
        """处理工具调用并返回文本结果"""
        async with self.client as client:
            if name == "get_openclaw_status":
                result = await client.get_status()
                return json.dumps(result, indent=2, ensure_ascii=False)

            elif name == "get_positions":
                result = await client.get_positions()
                return json.dumps(result, indent=2, ensure_ascii=False)

            elif name == "get_account_summary":
                result = await client.get_account()
                return json.dumps(result, indent=2, ensure_ascii=False)

            elif name == "get_module_health":
                result = await client.get_modules()
                return json.dumps(result, indent=2, ensure_ascii=False)

            elif name == "reload_configuration":
                if not arguments.get("confirm"):
                    return json.dumps({"error": "confirm=true required"})
                result = await client.reload_config()
                await self.logger.log_event("config_reloaded", "openclaw", result)
                return json.dumps(result, indent=2, ensure_ascii=False)

            elif name == "get_recent_events":
                limit = arguments.get("limit", 50)
                events = await self.logger.tail_events(limit)
                return json.dumps(events, indent=2, ensure_ascii=False)

            elif name == "publish_event":
                event_type = arguments.get("event_type")
                data = arguments.get("data", {})
                await self.logger.log_event(event_type, "hermes", data)
                return json.dumps({"status": "published", "event_type": event_type})

            else:
                return json.dumps({"error": f"Unknown tool: {name}"})

    async def run_stdio(self):
        """运行 stdio 模式 (MCP 标准)"""
        if not MCP_AVAILABLE or not self.server:
            logger.error("MCP SDK not available, cannot run stdio mode")
            return

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=MCP_SERVER_NAME,
                    server_version=MCP_VERSION,
                    capabilities=self.server.get_capabilities()
                )
            )

    async def run_http(self, host: str = "localhost", port: int = 18888):
        """运行 HTTP 模式 (备用)"""
        try:
            from aiohttp import web
        except ImportError:
            logger.error("aiohttp not available for HTTP mode")
            return

        app = web.Application()

        async def handle_tools(request):
            return web.json_response(TOOLS_SCHEMA)

        async def handle_call(request):
            data = await request.json()
            name = data.get("name")
            arguments = data.get("arguments", {})
            result_text = await self._handle_tool(name, arguments)
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                result = {"text": result_text}
            return web.json_response(result)

        async def handle_health(request):
            return web.json_response({"status": "ok", "server": MCP_SERVER_NAME})

        app.router.add_get('/tools', handle_tools)
        app.router.add_post('/call', handle_call)
        app.router.add_get('/health', handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        logger.info(f"HTTP MCP server listening on {host}:{port}")
        await site.start()

        # 保持运行
        while True:
            await asyncio.sleep(3600)


async def main():
    """主入口"""
    import argparse
    parser = argparse.ArgumentParser(description="OpenClaw MCP Server")
    parser.add_argument("--mode", choices=["stdio", "http"], default="stdio",
                       help="Server mode: stdio (default) or http")
    parser.add_argument("--port", type=int, default=18888, help="HTTP port")
    parser.add_argument("--openclaw-url", default="http://localhost:18789",
                       help="OpenClaw API URL")
    args = parser.parse_args()

    # 设置环境变量
    os.environ["OPENCLAW_API_URL"] = args.openclaw_url

    server = OpenClawMCPServer()

    if args.mode == "stdio":
        await server.run_stdio()
    else:
        await server.run_http(port=args.port)


if __name__ == "__main__":
    asyncio.run(main())
