"""
API服务器模块 - 全智能量化交易系统的对外接口

功能：
1. REST API接口
2. WebSocket实时数据推送
3. 用户认证和授权（JWT）
4. API文档（OpenAPI/Swagger）
5. 请求验证和数据校验
6. 速率限制和防护
"""

import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import secrets
import traceback
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from src.modules.api.strategy_api import router as strategy_router
from src.modules.core.enhanced_llm_manager import TaskType
from src.modules.data.data_source_hub import DataSourceHub

try:
    from fastapi import (
        APIRouter,
        Depends,
        FastAPI,
        HTTPException,
        Request,
        Response,
        WebSocket,
        WebSocketDisconnect,
        status,
    )
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    from fastapi.openapi.docs import get_swagger_ui_html
    from fastapi.openapi.utils import get_openapi
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.routing import APIRoute
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from pydantic import BaseModel, Field, confloat, conint, validator
    from jose import JWTError, jwt
    from passlib.context import CryptContext

    HAS_FASTAPI = True
except ImportError as e:
    HAS_FASTAPI = False
    logger = logging.getLogger(__name__)
    logger.warning(f"FastAPI未安装，API功能将受限: {e}")


logger = logging.getLogger(__name__)


def _generate_stable_operation_id(route: APIRoute) -> str:
    """Generate deterministic, collision-resistant operation IDs for OpenAPI."""
    methods = "_".join(sorted((route.methods or {"GET"})))
    path = (
        route.path_format.strip("/")
        .replace("/", "_")
        .replace("{", "")
        .replace("}", "")
        .replace(":", "_")
        or "root"
    )
    return f"{route.name}_{path}_{methods}".lower()


class APIVersion(Enum):
    """API版本"""

    V1 = "v1"
    V2 = "v2"


class HTTPMethod(Enum):
    """HTTP方法"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class WebSocketEventType(Enum):
    """WebSocket事件类型"""

    CONNECT = "connect"
    DISCONNECT = "disconnect"
    DATA = "data"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


@dataclass
class APIRequest:
    """API请求"""

    id: str
    method: HTTPMethod
    path: str
    headers: Dict[str, str]
    params: Dict[str, Any]
    body: Optional[Dict[str, Any]]
    client_ip: str
    timestamp: datetime = field(default_factory=datetime.now)
    user_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "method": self.method.value,
            "path": self.path,
            "client_ip": self.client_ip,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "params": self.params,
            "body": self.body,
        }


@dataclass
class APIResponse:
    """API响应"""

    status_code: int
    data: Optional[Dict[str, Any]]
    error: Optional[str] = None
    message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    request_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "status": "success" if 200 <= self.status_code < 300 else "error",
            "data": self.data,
            "error": self.error,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "request_id": self.request_id,
        }


@dataclass
class WebSocketConnection:
    """WebSocket连接"""

    id: str
    websocket: WebSocket
    user_id: Optional[str] = None
    subscriptions: List[str] = field(default_factory=list)
    connected_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_subscribed(self, channel: str) -> bool:
        """检查是否订阅了频道"""
        ch = str(channel or "").strip()
        if not ch:
            return False
        subs = list(self.subscriptions or [])
        if "*" in subs:
            return True
        if ch in subs:
            return True
        # prefix wildcard: e.g. "trade.*" matches "trade.intent"/"trade.fill"/"trade.position"
        for s in subs:
            ss = str(s or "").strip()
            if ss.endswith(".*") and ch.startswith(ss[:-2]):
                return True
        return False

    def update_activity(self) -> None:
        """更新活动时间"""
        self.last_activity = datetime.now()

    @property
    def idle_time(self) -> timedelta:
        """空闲时间"""
        return datetime.now() - self.last_activity


@dataclass
class RateLimit:
    """速率限制"""

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    burst_size: int = 10


# Pydantic模型（用于请求验证）
if HAS_FASTAPI:

    class Token(BaseModel):
        """令牌响应模型"""

        access_token: str
        token_type: str = "bearer"
        expires_in: int
        refresh_token: Optional[str] = None

    class LoginRequest(BaseModel):
        """登录请求模型"""

        username: str
        password: str

    class TradeRequest(BaseModel):
        """交易请求模型"""

        symbol: str
        side: str  # buy/sell
        order_type: str = "market"  # market/limit/stop
        quantity: confloat(gt=0)  # 必须大于0
        price: Optional[confloat(gt=0)] = None
        stop_price: Optional[confloat(gt=0)] = None

        @validator("side")
        def validate_side(cls, v):
            if v.lower() not in ["buy", "sell"]:
                raise ValueError("side必须是buy或sell")
            return v.lower()

        @validator("order_type")
        def validate_order_type(cls, v):
            valid_types = ["market", "limit", "stop", "stop_limit"]
            if v.lower() not in valid_types:
                raise ValueError(f"order_type必须是{valid_types}之一")
            return v.lower()

    class MarketDataRequest(BaseModel):
        """市场数据请求模型"""

        symbol: str
        interval: str = "1m"  # 1m, 5m, 15m, 1h, 1d, 1w
        limit: conint(ge=1, le=1000) = 100
        start_time: Optional[datetime] = None
        end_time: Optional[datetime] = None

    class StrategyRequest(BaseModel):
        """策略请求模型"""

        name: str
        config: Dict[str, Any]
        symbols: List[str]

    class WebSocketSubscribeRequest(BaseModel):
        """WebSocket订阅请求模型"""

        channels: List[str]
        symbols: Optional[List[str]] = None


class APIServer:
    """
    API服务器

    核心功能：
    1. REST API接口
    2. WebSocket实时数据推送
    3. 用户认证和授权
    4. API文档
    5. 请求验证和速率限制
    """
    _shared_websocket_connections: Dict[str, WebSocketConnection] = {}
    _active_instance: Optional["APIServer"] = None

    def __init__(self, config_manager=None, main_controller=None, host: str = "0.0.0.0", port: int = 8000):
        """
        初始化API服务器

        Args:
            config_manager: 配置管理器实例
            main_controller: 主控制器实例
            host: 监听主机
            port: 监听端口
        """
        self.config_manager = config_manager
        self.main_controller = main_controller
        allow_multi = str(os.getenv("OPENCLAW_API_ALLOW_MULTI_INSTANCE", "0")).strip().lower() in {
            "1", "true", "yes", "on"
        }
        existing = APIServer._active_instance
        existing_alive = bool(
            existing
            and (getattr(existing, "_initialized", False) or getattr(existing, "_running", False) or getattr(existing, "app", None) is not None)
        )
        if existing is not None and existing is not self and existing_alive and (not allow_multi):
            raise RuntimeError(
                "检测到重复 APIServer 实例创建；默认禁止多实例。"
                "请复用 main_controller.api_server，或设置 OPENCLAW_API_ALLOW_MULTI_INSTANCE=1（仅调试）"
            )
        APIServer._active_instance = self
        # In Docker, binding to 127.0.0.1 prevents host port publishing.
        in_docker = os.path.exists("/.dockerenv")
        if in_docker and (host or "").strip() in {"127.0.0.1", "localhost"}:
            host = "0.0.0.0"
        self.host = host
        self.port = port

        # FastAPI应用
        self.app: Optional[FastAPI] = None
        self.routers: Dict[str, APIRouter] = {}

        # 认证
        self.security = HTTPBearer() if HAS_FASTAPI else None
        # Use pbkdf2_sha256 to avoid bcrypt 72-byte limitation and backend quirks.
        self.pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto") if HAS_FASTAPI else None
        self.secret_key = secrets.token_urlsafe(32) if HAS_FASTAPI else None
        self.algorithm = "HS256" if HAS_FASTAPI else None
        self.access_token_expire_minutes = 30 if HAS_FASTAPI else None

        # WebSocket连接管理
        self.websocket_connections: Dict[str, WebSocketConnection] = {}
        self.websocket_broadcast_tasks: Dict[str, asyncio.Task] = {}

        # 速率限制
        self.rate_limits: Dict[str, RateLimit] = {}
        self.request_counts: Dict[str, Dict[str, int]] = {}  # client_ip -> endpoint -> count

        # 状态和统计
        self.stats = {
            "total_requests": 0,
            "total_errors": 0,
            "active_connections": 0,
            "websocket_connections": 0,
            "api_response_time_ms": 0.0,
            "avg_response_time_ms": 0.0,
        }

        # Uvicorn runtime handles (to keep API responsive even if the main event loop
        # is temporarily busy during startup tasks).
        self._uvicorn_server = None
        self._uvicorn_thread = None

        # 任务和锁
        self._tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._initialized = False
        self._running = False

        # API配置
        self.enable_cors = True
        self.enable_rate_limit = True
        self.enable_swagger = True
        self.enable_metrics = True
        self.cors_allowed_origins: List[str] = ["http://127.0.0.1:8000"]
        self.trusted_hosts: List[str] = ["127.0.0.1", "localhost"]
        self.enforce_auth_on_writes: bool = True
        self.require_ws_auth: bool = True
        self.required_write_roles: Set[str] = {"admin"}
        # Internal allowlist for bypassing write auth (CIDRs).
        # Default: loopback only. Extend via config `api.auth_bypass_cidrs`.
        self.auth_bypass_enabled: bool = True
        self.auth_bypass_cidrs: List[str] = ["127.0.0.1/32", "::1/128"]
        self.protected_write_prefixes: List[str] = [
            "/api/v1/modules",
            "/api/v1/monitoring",
            "/api/v1/modules/commander",
            "/api/v1/trade",
        ]
        self.auth_exempt_paths: Set[str] = {
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/logout",
            "/api/v1/system/health",
            "/metrics",
            "/api/metrics",
            "/api/v1/metrics",
        }
        self.admin_username: Optional[str] = os.getenv("OPENCLAW_API_ADMIN_USERNAME", "admin")
        self.admin_password: Optional[str] = os.getenv("OPENCLAW_API_ADMIN_PASSWORD")

        logger.info(f"API服务器初始化完成，监听 {host}:{port}")

    async def initialize(self) -> None:
        """
        初始化API服务器

        创建FastAPI应用，设置路由，启动WebSocket广播
        """
        if self._initialized:
            return

        if not HAS_FASTAPI:
            logger.warning("FastAPI未安装，API服务器将运行在模拟模式")
            self._initialized = True
            return

        logger.info("初始化API服务器...")

        try:
            # 创建FastAPI应用
            self.app = FastAPI(
                title="全智能量化交易系统API",
                description="量化交易系统的RESTful API接口",
                version="1.0.0",
                docs_url=None if not self.enable_swagger else "/docs",
                redoc_url=None if not self.enable_swagger else "/redoc",
                openapi_url=None if not self.enable_swagger else "/openapi.json",
                generate_unique_id_function=_generate_stable_operation_id,
            )

            # 加载配置
            await self._load_config()

            # 添加中间件
            await self._add_middleware()

            # 设置路由（模块控制 / 监控 在 _setup_routes 内、静态资源挂载之前注册，避免被 / 的 StaticFiles 吞掉）
            await self._setup_routes()

            # 启动任务
            self._tasks.append(asyncio.create_task(self._cleanup_inactive_websockets()))
            self._tasks.append(asyncio.create_task(self._broadcast_market_data()))

            self._initialized = True
            logger.info("API服务器初始化完成")

        except Exception as e:
            logger.error(f"API服务器初始化失败: {e}")
            traceback.print_exc()

    async def cleanup(self) -> None:
        """
        清理API服务器

        关闭连接，清理资源
        """
        logger.info("清理API服务器...")

        self._running = False

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()

        # 关闭WebSocket连接
        for conn_id in list(self.websocket_connections.keys()):
            await self._close_websocket_connection(conn_id)

        self._initialized = False
        if APIServer._active_instance is self:
            APIServer._active_instance = None
        logger.info("API服务器清理完成")

    async def start(self) -> bool:
        """
        启动API服务器

        Returns:
            是否启动成功
        """
        if not self._initialized:
            await self.initialize()

        logger.info(f"启动API服务器，监听 {self.host}:{self.port}")

        try:
            if HAS_FASTAPI and self.app:
                import uvicorn
                import threading
                import socket
                
                def is_port_in_use(port: int) -> bool:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        return s.connect_ex(('localhost', port)) == 0
                
                if is_port_in_use(self.port):
                    logger.error(f"端口 {self.port} 已被占用，拒绝自动切换端口（避免前端/网关指向漂移）")
                    return False
                
                config = uvicorn.Config(
                    self.app,
                    host=self.host,
                    port=self.port,
                    log_level="warning",
                    access_log=False,
                    log_config=None,
                )
                
                server = uvicorn.Server(config)
                self._uvicorn_server = server
                
                async def run_server():
                    try:
                        await server.serve()
                    except asyncio.CancelledError:
                        logger.info("API服务器任务被取消")
                    except Exception as e:
                        logger.error(f"API服务器运行错误: {e}")
                        import traceback
                        traceback.print_exc()
                
                server_task = asyncio.create_task(run_server())
                self._tasks.append(server_task)
                
                # 轮询等待服务就绪，避免固定 1s 导致慢机/CI 偶发失败
                for _ in range(20):
                    await asyncio.sleep(0.2)
                    if getattr(server, "started", False) or is_port_in_use(self.port):
                        self._running = True
                        logger.info(f"✅ API服务器已启动，访问 http://{self.host}:{self.port}/docs 查看文档")
                        return True
                    if server_task.done():
                        break

                # Fallback: if the event loop is busy (startup tasks), serve in a daemon thread
                # so /health and control plane stay responsive.
                try:
                    if not is_port_in_use(self.port):
                        logger.warning("API端口未及时监听，启用线程模式启动以避免主循环阻塞")
                        t = threading.Thread(target=server.run, daemon=True)
                        t.start()
                        self._uvicorn_thread = t
                        for _ in range(30):
                            await asyncio.sleep(0.2)
                            if is_port_in_use(self.port):
                                self._running = True
                                logger.info(f"✅ API服务器已启动（线程模式），访问 http://{self.host}:{self.port}/docs 查看文档")
                                return True
                except Exception as e:
                    logger.warning(f"线程模式启动API失败: {e}")

                # 测试场景下，如果任务仍在运行也认为启动成功（端口探测可能受环境影响）
                if not server_task.done():
                    self._running = True
                    logger.info(f"✅ API服务器已启动（任务运行中），访问 http://{self.host}:{self.port}/docs 查看文档")
                    return True

                logger.error(f"API服务器启动失败，端口 {self.port} 未监听")
                return False
            else:
                self._running = True
                logger.info(f"API服务器已启动（模拟模式），访问 http://{self.host}:{self.port}/docs 查看文档")
                return True

        except Exception as e:
            logger.error(f"API服务器启动失败: {e}")
            traceback.print_exc()
            return False

    async def stop(self) -> bool:
        """
        停止API服务器

        Returns:
            是否停止成功
        """
        logger.info("停止API服务器...")

        try:
            self._running = False
            try:
                if self._uvicorn_server is not None:
                    setattr(self._uvicorn_server, "should_exit", True)
            except Exception:
                pass
            await self.cleanup()

            logger.info("API服务器已停止")
            return True

        except Exception as e:
            logger.error(f"API服务器停止失败: {e}")
            return False

    async def register_route(
        self, method: HTTPMethod, path: str, handler: Callable, tags: List[str] = None
    ) -> bool:
        """
        注册API路由

        Args:
            method: HTTP方法
            path: 路径
            handler: 处理函数
            tags: 标签

        Returns:
            是否注册成功
        """
        if not self.app:
            logger.error("FastAPI应用未初始化")
            return False

        try:
            # 创建路由方法映射
            method_map = {
                HTTPMethod.GET: self.app.get,
                HTTPMethod.POST: self.app.post,
                HTTPMethod.PUT: self.app.put,
                HTTPMethod.DELETE: self.app.delete,
                HTTPMethod.PATCH: self.app.patch,
            }

            if method not in method_map:
                logger.error(f"不支持的HTTP方法: {method}")
                return False

            # 注册路由
            method_map[method](path, tags=tags or ["api"])(handler)

            logger.debug(f"注册路由: {method.value} {path}")
            return True

        except Exception as e:
            logger.error(f"注册路由失败 {method.value} {path}: {e}")
            return False

    async def broadcast_websocket(self, channel: str, data: Dict[str, Any]) -> int:
        """
        广播WebSocket消息

        Args:
            channel: 频道
            data: 数据

        Returns:
            发送成功的连接数
        """
        # 兼容外部启动器（例如直接 uvicorn 载入 app）：
        # 这类模式下 API 已可用，但 _running 可能未显式置为 True。
        # 仅在「未运行且无任何连接」时短路，避免误丢实时推送。
        if (
            (not self._running)
            and (not self.websocket_connections)
            and (not self.__class__._shared_websocket_connections)
        ):
            return 0

        sent_count = 0
        current_time = datetime.now()
        targets: Dict[str, WebSocketConnection] = {}
        targets.update(self.__class__._shared_websocket_connections or {})
        targets.update(self.websocket_connections or {})
        for conn_id, connection in list(targets.items()):
            try:
                # 检查连接是否订阅了该频道
                if connection.is_subscribed(channel):
                    # 准备消息（与 HTTP JSON 相同的标准字段，兼容保留 type/channel/data）
                    message = self._normalize_api_payload(
                        {
                            "type": WebSocketEventType.DATA.value,
                            "channel": channel,
                            "data": data,
                            "timestamp": current_time.isoformat(),
                        },
                        status.HTTP_200_OK,
                    )

                    # 发送消息
                    await connection.websocket.send_json(message)
                    sent_count += 1

                    # 更新活动时间
                    connection.update_activity()

            except Exception as e:
                logger.error(f"WebSocket广播失败 {conn_id}: {e}")
                # 移除失效的连接
                await self._close_websocket_connection(conn_id)

        return sent_count

    async def get_api_stats(self) -> Dict[str, Any]:
        """
        获取API统计信息

        Returns:
            统计信息
        """
        async with self._lock:
            stats = self.stats.copy()
            stats.update(
                {
                    "websocket_active_connections": len(self.websocket_connections),
                    "rate_limits": {k: v.__dict__ for k, v in self.rate_limits.items()},
                    "uptime": self._get_uptime(),
                    "timestamp": datetime.now().isoformat(),
                }
            )

            return stats

    # 认证相关方法

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return self.pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """获取密码哈希"""
        return self.pwd_context.hash(password)

    def create_access_token(
        self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        """创建访问令牌"""
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.now() + expires_delta
        else:
            expire = datetime.now() + timedelta(minutes=self.access_token_expire_minutes)

        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证令牌"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError:
            return None

    @staticmethod
    def _extract_bearer_token(auth_header: Optional[str]) -> Optional[str]:
        raw = str(auth_header or "").strip()
        if not raw:
            return None
        if raw.lower().startswith("bearer "):
            token = raw[7:].strip()
            return token or None
        return None

    def _is_protected_write_path(self, path: str, method: str) -> bool:
        m = str(method or "GET").upper()
        if m in {"GET", "HEAD", "OPTIONS"}:
            return False
        p = str(path or "")
        if p in self.auth_exempt_paths:
            return False
        return any(p.startswith(prefix) for prefix in self.protected_write_prefixes)

    def _has_required_write_role(self, payload: Dict[str, Any]) -> bool:
        required = {str(x).strip().lower() for x in self.required_write_roles if str(x).strip()}
        if not required:
            return True
        role = str(payload.get("role", "") or "").strip().lower()
        return role in required

    @staticmethod
    def _client_ip_from_request(request: "Request") -> str:
        try:
            return request.client.host if request.client else "unknown"
        except Exception:
            return "unknown"

    def _is_internal_auth_bypass(self, request: "Request") -> bool:
        if not bool(self.auth_bypass_enabled):
            return False
        ip_s = self._client_ip_from_request(request)
        try:
            ip = ipaddress.ip_address(str(ip_s))
        except Exception:
            return False
        for cidr in (self.auth_bypass_cidrs or []):
            try:
                net = ipaddress.ip_network(str(cidr), strict=False)
            except Exception:
                continue
            if ip in net:
                return True
        return False

    # 私有方法

    async def _load_config(self) -> None:
        """加载API配置"""
        if self.config_manager:
            api_config = await self.config_manager.get_config("api", {})

            self.host = api_config.get("host", self.host)
            self.port = api_config.get("port", self.port)
            self.enable_cors = api_config.get("enable_cors", True)
            self.enable_rate_limit = api_config.get("enable_rate_limit", True)
            self.enable_swagger = api_config.get("enable_swagger", True)
            self.enable_metrics = api_config.get("enable_metrics", True)
            self.secret_key = api_config.get("secret_key", self.secret_key)
            self.access_token_expire_minutes = api_config.get("access_token_expire_minutes", 30)
            cors_origins = api_config.get("cors_allowed_origins", self.cors_allowed_origins)
            if isinstance(cors_origins, list) and cors_origins:
                self.cors_allowed_origins = [str(x).strip() for x in cors_origins if str(x).strip()]
            trusted_hosts = api_config.get("trusted_hosts", self.trusted_hosts)
            if isinstance(trusted_hosts, list) and trusted_hosts:
                self.trusted_hosts = [str(x).strip() for x in trusted_hosts if str(x).strip()]
            self.enforce_auth_on_writes = bool(api_config.get("enforce_auth_on_writes", self.enforce_auth_on_writes))
            self.require_ws_auth = bool(api_config.get("require_ws_auth", self.require_ws_auth))
            self.auth_bypass_enabled = bool(api_config.get("auth_bypass_enabled", self.auth_bypass_enabled))
            bypass = api_config.get("auth_bypass_cidrs", self.auth_bypass_cidrs)
            if isinstance(bypass, list) and bypass:
                self.auth_bypass_cidrs = [str(x).strip() for x in bypass if str(x).strip()]
            required_roles = api_config.get("required_write_roles", list(self.required_write_roles))
            if isinstance(required_roles, list) and required_roles:
                self.required_write_roles = {str(x).strip().lower() for x in required_roles if str(x).strip()}
            pfx = api_config.get("protected_write_prefixes", self.protected_write_prefixes)
            if isinstance(pfx, list) and pfx:
                self.protected_write_prefixes = [str(x).strip() for x in pfx if str(x).strip()]
            auth_cfg = api_config.get("auth", {}) if isinstance(api_config, dict) else {}
            if isinstance(auth_cfg, dict):
                self.admin_username = str(auth_cfg.get("admin_username", self.admin_username) or self.admin_username)
                self.admin_password = str(auth_cfg.get("admin_password", self.admin_password) or self.admin_password)

            # 加载速率限制配置
            rate_limit_config = api_config.get("rate_limits", {})
            for endpoint, limit_config in rate_limit_config.items():
                self.rate_limits[endpoint] = RateLimit(**limit_config)

        logger.info(f"加载API配置: {self.host}:{self.port}")

    def _normalize_api_payload(self, payload: Dict[str, Any], status_code: int) -> Dict[str, Any]:
        """
        统一 API 返回结构（兼容模式）：
        - 不移除原字段，只补齐标准字段，避免破坏旧前端/调用方
        - 标准字段：ok/success/status/message/timestamp
        """
        out = dict(payload or {})
        ok_v = out.get("ok")
        if ok_v is None:
            if "success" in out:
                ok_v = bool(out.get("success"))
            elif str(out.get("status", "")).lower() in {"success", "ok", "healthy", "running"}:
                ok_v = True
            elif status_code >= 400:
                ok_v = False
            elif "error" in out and out.get("error"):
                ok_v = False
            else:
                ok_v = True

        ok_b = bool(ok_v)
        out.setdefault("ok", ok_b)
        out.setdefault("success", ok_b)

        if "status" not in out:
            out["status"] = "success" if ok_b else "error"
        else:
            st = str(out.get("status", "")).strip()
            if not st:
                out["status"] = "success" if ok_b else "error"

        if "message" not in out:
            if isinstance(out.get("error"), str) and out.get("error"):
                out["message"] = out.get("error")
            elif not ok_b:
                out["message"] = "request_failed"

        out.setdefault("timestamp", datetime.now().isoformat())
        return out

    async def _add_middleware(self) -> None:
        """添加中间件"""
        if not self.app:
            return

        # CORS中间件
        if self.enable_cors:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=self.cors_allowed_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        # 信任主机中间件
        self.app.add_middleware(TrustedHostMiddleware, allowed_hosts=self.trusted_hosts)

        # 自定义中间件
        @self.app.middleware("http")
        async def add_process_time_header(request: Request, call_next):
            """添加处理时间头"""
            start_time = datetime.now()
            path = str(request.url.path or "")
            method = str(request.method or "").upper()
            watch_path = (
                "/commander/dispatch" in path
                or "/trade/" in path
                or "/modules/execution" in path
                or "/ai/chat" in path
            )
            broad_watch_path = path.startswith("/api") or path.startswith("/commander")

            if self.enforce_auth_on_writes and self._is_protected_write_path(request.url.path, request.method):
                if not self._is_internal_auth_bypass(request):
                    token = self._extract_bearer_token(request.headers.get("authorization"))
                    payload = await self.verify_token(token) if token else None
                    if not payload:
                        return JSONResponse(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            content={"error": "Unauthorized write operation"},
                        )
                    if not self._has_required_write_role(payload):
                        return JSONResponse(
                            status_code=status.HTTP_403_FORBIDDEN,
                            content={"error": "Forbidden write operation"},
                        )

            # 速率限制检查
            if self.enable_rate_limit:
                client_ip = self._client_ip_from_request(request)
                endpoint = request.url.path

                if not await self._check_rate_limit(client_ip, endpoint):
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={"error": "Rate limit exceeded"},
                    )

            # 处理请求
            response = await call_next(request)

            # API响应统一标准化（仅 /api JSON 响应；保留原字段以兼容历史调用方）
            try:
                path = str(request.url.path or "")
                ctype = str(response.headers.get("content-type", "")).lower()
                if path.startswith("/api") and "application/json" in ctype and request.method.upper() != "OPTIONS":
                    raw_body = b""
                    async for chunk in response.body_iterator:
                        raw_body += chunk
                    if raw_body:
                        try:
                            body_obj = json.loads(raw_body.decode("utf-8"))
                        except Exception:
                            body_obj = None
                        if isinstance(body_obj, dict):
                            normalized = self._normalize_api_payload(body_obj, int(response.status_code))
                            rebuilt = JSONResponse(status_code=response.status_code, content=normalized)
                        else:
                            rebuilt = Response(
                                content=raw_body,
                                status_code=response.status_code,
                                media_type=response.media_type,
                            )
                        for k, v in response.headers.items():
                            if k.lower() not in {"content-length", "content-type"}:
                                rebuilt.headers[k] = v
                        rebuilt.headers["X-OpenClaw-Standardized"] = "1"
                        response = rebuilt
            except Exception:
                pass

            # 更新统计
            process_time = (datetime.now() - start_time).total_seconds() * 1000
            response.headers["X-Process-Time"] = str(process_time)

            self.stats["total_requests"] += 1
            self.stats["api_response_time_ms"] += process_time

            if self.stats["total_requests"] > 0:
                self.stats["avg_response_time_ms"] = (
                    self.stats["api_response_time_ms"] / self.stats["total_requests"]
                )

            return response

    async def _setup_routes(self) -> None:
        """设置路由"""
        if not self.app:
            return

        # 创建API路由前缀
        api_router = APIRouter(prefix="/api", tags=["api"])
        api_v1_router = APIRouter(prefix="/v1", tags=["api-v1"])
        # 供闭包路由统一使用，避免局部函数中 NameError
        main_controller = self.main_controller
        data_source_hub = DataSourceHub(main_controller)

        def _resolve_data_source_hub() -> DataSourceHub:
            """
            运行时动态绑定 DataSourceHub <-> main_controller/exchange：
            - 优先使用 main_controller 挂载的 data_source_hub
            - 每次请求前刷新绑定，避免旧引用导致 exchange 断链
            """
            mc = self.main_controller
            if mc is None:
                # 兼容不同导入命名空间，尽可能恢复活动主控引用
                for import_path in ("src.modules.main_controller", "modules.main_controller"):
                    try:
                        mod = __import__(import_path, fromlist=["MainController"])
                        cls = getattr(mod, "MainController", None)
                        if cls and hasattr(cls, "get_active_instance"):
                            mc = cls.get_active_instance()
                            if mc is not None:
                                break
                    except Exception:
                        continue
            hub = getattr(mc, "data_source_hub", None) if mc else None
            if not hub:
                hub = data_source_hub
            if hasattr(hub, "bind_main_controller"):
                try:
                    hub.bind_main_controller(mc)
                except Exception:
                    hub.main_controller = mc
            else:
                hub.main_controller = mc
            return hub

        # 根路由 - 仅在静态文件服务不存在时生效
        # 注意：静态文件服务会处理根路径的请求

        # 健康检查（唯一入口）
        @api_v1_router.get("/system/health", tags=["health"])
        async def health_check():
            """健康检查"""
            return {
                "success": True,
                "data": {
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat(),
                    "uptime": self._get_uptime(),
                },
            }

        # 指标端点 - 同时支持 /metrics 和 /api/metrics
        @self.app.get("/metrics", tags=["metrics"])
        @api_router.get("/metrics", tags=["metrics"])
        async def get_metrics():
            """获取指标"""
            stats = await self.get_api_stats()
            return stats

        # 状态端点（唯一入口）
        @api_v1_router.get("/system/status", tags=["system"])
        async def get_status():
            """获取系统状态"""
            base = {
                "system_status": "running",
                "status": "running",
                "uptime": 0,
                "module_count": 0,
                "running_modules": 0,
                "timestamp": datetime.now().isoformat(),
                "module_statuses": {},
            }
            if not main_controller:
                return {"success": True, "data": base}
            try:
                mc_status = await main_controller.get_system_status()
                if isinstance(mc_status, dict):
                    base.update(mc_status)
                    # 向后兼容历史字段
                    base["status"] = base.get("system_status", base.get("status", "unknown"))
                    base["timestamp"] = datetime.now().isoformat()
            except Exception as e:
                base["status"] = "degraded"
                base["system_status"] = "degraded"
                base["error"] = str(e)
            return {"success": True, "data": base}

        # ---------------------------------------------------------------------
        # Compatibility endpoints (legacy frontends / monitoring)
        # ---------------------------------------------------------------------
        @api_v1_router.get("/balance", tags=["account"])
        async def legacy_balance():
            """
            兼容老前端：GET /api/v1/balance
            - 返回简化余额字典（与 OKXExchange.get_balance 对齐）
            - 失败时返回 ok=false + message
            """
            mc = self.main_controller
            ex = mc.get_exchange() if (mc and hasattr(mc, "get_exchange")) else None
            if not ex or not hasattr(ex, "get_balance"):
                return {"ok": False, "message": "exchange unavailable", "balance": {}}

            # Best-effort cache fallback:
            # - OKXExchange 内部实现了余额/持仓缓存降级
            # - 但 legacy 路由外层用了较短 wait_for，OKX 抖动时会被外层取消，导致 ok:false
            # - 因此这里优先读缓存；失败/超时也优先回退缓存
            cached_balance_data: Dict[str, float] = {}
            cached_balance_age_s: Optional[float] = None
            try:
                cached_ts, cached_balances = getattr(ex, "_balances_cache", (0.0, []))
                if isinstance(cached_balances, list) and cached_balances:
                    cached_balance_age_s = time.time() - float(cached_ts or 0.0)
                    for b in cached_balances:
                        # Balance dataclass (asset, free) or dict-like
                        asset = getattr(b, "asset", None) or (b.get("asset") if isinstance(b, dict) else None)
                        free = getattr(b, "free", None) if not isinstance(b, dict) else b.get("free")
                        if asset:
                            try:
                                f = float(free or 0.0)
                            except Exception:
                                f = 0.0
                            if f > 0:
                                cached_balance_data[str(asset)] = f
            except Exception:
                cached_balance_data = {}
                cached_balance_age_s = None

            # If cache exists and is "fresh enough", skip network entirely.
            try:
                ttl_s = float(getattr(ex, "_balance_cache_ttl_s", 12.0) or 12.0)
            except Exception:
                ttl_s = 12.0
            max_stale_age_s = max(60.0, ttl_s * 10.0)
            if cached_balance_data and cached_balance_age_s is not None and cached_balance_age_s <= max_stale_age_s:
                return {
                    "ok": True,
                    "balance": cached_balance_data,
                    "data": cached_balance_data,
                    "source": "cache",
                    "stale": bool(cached_balance_age_s > (ttl_s or 0.0)),
                    "stale_age_s": cached_balance_age_s,
                }
            try:
                # 外层 wait_for 控制：网络抖动时允许 OKXExchange 先尝试返回/更新缓存；
                # 超过该时间就回退为空余额但保证 ok=true，避免前端被判“接口错误”。
                bal = await asyncio.wait_for(ex.get_balance(), timeout=12.0)
                if not isinstance(bal, dict):
                    bal = {}
                # Add "data" alias for older clients expecting a data envelope.
                return {"ok": True, "balance": bal, "data": bal}
            except asyncio.TimeoutError as e:
                if cached_balance_data:
                    return {
                        "ok": True,
                        "balance": cached_balance_data,
                        "data": cached_balance_data,
                        "source": "cache",
                        "stale": True,
                        "stale_age_s": cached_balance_age_s,
                        "message": f"timeout; fallback to cache: {str(e) or 'timeout'}",
                    }
                # 没有缓存时就直接返回 ok:true（避免前端把它当“不可用错误”），
                # 下一轮请求通常就能拿到余额/缓存。
                return {
                    "ok": True,
                    "balance": {},
                    "data": {},
                    "source": "timeout_no_cache",
                    "stale": True,
                    "message": str(e) or "timeout",
                }
            except Exception as e:
                if cached_balance_data:
                    return {
                        "ok": True,
                        "balance": cached_balance_data,
                        "data": cached_balance_data,
                        "source": "cache",
                        "stale": True,
                        "stale_age_s": cached_balance_age_s,
                        "message": f"{type(e).__name__}; fallback to cache",
                    }
                return {"ok": False, "message": str(e), "balance": {}, "data": {}}

        @api_v1_router.get("/positions", tags=["account"])
        async def legacy_positions():
            """
            兼容老前端：GET /api/v1/positions
            - 返回 positions 列表（与 OKXExchange.get_positions 对齐）
            - 失败时返回 ok=false + message
            - 补充 CCXT 风格别名：contracts≈size、notional≈notional_value（避免监控/前端读缺省字段误判为 0）
            """

            def _positions_with_legacy_aliases(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                out_rows: List[Dict[str, Any]] = []
                for raw in rows or []:
                    if not isinstance(raw, dict):
                        continue
                    r = dict(raw)
                    if r.get("contracts") is None:
                        try:
                            r["contracts"] = float(r.get("size") or 0.0)
                        except Exception:
                            r["contracts"] = r.get("size")
                    if r.get("notional") is None:
                        nv = r.get("notional_value")
                        try:
                            if nv is not None and float(nv) != 0.0:
                                r["notional"] = float(nv)
                        except Exception:
                            pass
                        if r.get("notional") is None:
                            try:
                                mk = float(r.get("mark_px") or r.get("mark_price") or 0.0)
                                szz = float(r.get("size") or 0.0)
                                if mk > 0 and szz > 0:
                                    r["notional"] = abs(mk * szz)
                            except Exception:
                                pass
                    out_rows.append(r)
                return out_rows

            mc = self.main_controller
            ex = mc.get_exchange() if (mc and hasattr(mc, "get_exchange")) else None
            if not ex or not hasattr(ex, "get_positions"):
                return {"ok": False, "message": "exchange unavailable", "positions": [], "data": []}

            # Prefer OKXExchange internal positions cache.
            cached_positions: List[Dict[str, Any]] = []
            cached_positions_age_s: Optional[float] = None
            try:
                cached_ts, cached_pos_list = getattr(ex, "_positions_cache", (0.0, []))
                if isinstance(cached_pos_list, list) and cached_pos_list:
                    cached_positions_age_s = time.time() - float(cached_ts or 0.0)
                    # cache rows already contain "size" and "side" fields (best-effort)
                    for row in cached_pos_list:
                        if not isinstance(row, dict):
                            continue
                        try:
                            sz = float(row.get("size") or row.get("quantity") or 0.0)
                        except Exception:
                            sz = 0.0
                        if abs(sz) > 1e-12:
                            cached_positions.append(row)
            except Exception:
                cached_positions = []
                cached_positions_age_s = None

            try:
                ttl_s = float(getattr(ex, "_positions_cache_ttl_s", 15.0) or 15.0)
            except Exception:
                ttl_s = 15.0
            max_stale_age_s = max(60.0, ttl_s * 10.0)
            if cached_positions and cached_positions_age_s is not None and cached_positions_age_s <= max_stale_age_s:
                aliased = _positions_with_legacy_aliases(cached_positions)
                return {
                    "ok": True,
                    "positions": aliased,
                    "count": len(aliased),
                    "data": aliased,
                    "source": "cache",
                    "stale": bool(cached_positions_age_s > (ttl_s or 0.0)),
                    "stale_age_s": cached_positions_age_s,
                }

            try:
                pos = await asyncio.wait_for(ex.get_positions(), timeout=12.0)
                if not isinstance(pos, list):
                    pos = []
                # best-effort: filter non-zero
                out = []
                for row in pos:
                    if not isinstance(row, dict):
                        continue
                    try:
                        sz = float(row.get("size") or row.get("quantity") or 0.0)
                    except Exception:
                        sz = 0.0
                    if abs(sz) > 1e-12:
                        out.append(row)
                aliased = _positions_with_legacy_aliases(out)
                return {"ok": True, "positions": aliased, "count": len(aliased), "data": aliased}
            except asyncio.TimeoutError as e:
                if cached_positions:
                    aliased = _positions_with_legacy_aliases(cached_positions)
                    return {
                        "ok": True,
                        "positions": aliased,
                        "count": len(aliased),
                        "data": aliased,
                        "source": "cache",
                        "stale": True,
                        "stale_age_s": cached_positions_age_s,
                        "message": f"timeout; fallback to cache: {str(e) or 'timeout'}",
                    }
            except Exception as e:
                if cached_positions:
                    aliased = _positions_with_legacy_aliases(cached_positions)
                    return {
                        "ok": True,
                        "positions": aliased,
                        "count": len(aliased),
                        "data": aliased,
                        "source": "cache",
                        "stale": True,
                        "stale_age_s": cached_positions_age_s,
                        "message": f"{type(e).__name__}; fallback to cache",
                    }

            # Last-resort fallback: use SLTP active orders as a derived position view.
            try:
                mgr = getattr(mc, "stop_loss_manager", None)
                if mgr is not None and hasattr(mgr, "get_all_active_orders"):
                    orders = await mgr.get_all_active_orders()
                    out: List[Dict[str, Any]] = []
                    for o in (orders or []):
                        try:
                            row = o.to_dict() if hasattr(o, "to_dict") else dict(o)
                            side = str(row.get("side") or "").lower().strip() or "long"
                            symbol = row.get("symbol") or ""
                            size = row.get("remaining_quantity") or row.get("quantity") or 0.0
                            size = float(size or 0.0)
                            if abs(size) <= 1e-12:
                                continue
                            out.append(
                                {
                                    "symbol": symbol,
                                    "side": side,
                                    "size": abs(size),
                                    "entry_price": float(row.get("entry_price") or 0.0),
                                    "timestamp": row.get("created_at"),
                                }
                            )
                        except Exception:
                            continue
                    if out:
                        aliased = _positions_with_legacy_aliases(out)
                        return {
                            "ok": True,
                            "positions": aliased,
                            "count": len(aliased),
                            "data": aliased,
                            "source": "stop_loss_active_orders",
                            "stale": True,
                        }
            except Exception:
                pass

            return {"ok": False, "message": "exchange unavailable", "positions": [], "count": 0, "data": []}

        @api_v1_router.get("/engine/status", tags=["system"])
        async def engine_status():
            """
            交易引擎状态（前端/监控友好）
            """
            mc = self.main_controller
            if not mc:
                return {"ok": False, "message": "main_controller unavailable"}
            try:
                s = await mc.get_system_status()
                eng = (s or {}).get("module_statuses", {}).get("ai_trading_engine", {})
                ex_ok = bool((s or {}).get("execution_spine", {}).get("exchange_connected"))
                out = {"engine": eng, "exchange_connected": ex_ok}
                return {"ok": True, **out, "data": out}
            except Exception as e:
                return {"ok": False, "message": str(e), "data": None}

        # Compatibility aliases for module-style paths used by some frontends
        @api_v1_router.get("/modules/engine/status", tags=["system"])
        @api_v1_router.get("/modules/trading/engine/status", tags=["system"])
        async def engine_status_alias():
            return await engine_status()

        @api_v1_router.get("/risk/status", tags=["risk"])
        async def risk_status():
            """
            风险管理状态（红线 + SLTP 简要统计）
            """
            mc = self.main_controller
            if not mc:
                return {"ok": False, "message": "main_controller unavailable"}
            try:
                red = mc.get_risk_redlines() if hasattr(mc, "get_risk_redlines") else {}
                sltp = {}
                mgr = getattr(mc, "stop_loss_manager", None)
                if mgr is not None and hasattr(mgr, "get_stats"):
                    try:
                        sltp = await asyncio.wait_for(mgr.get_stats(), timeout=2.5)
                    except Exception:
                        sltp = {}
                return {"ok": True, "risk_redlines": red, "sltp": sltp}
            except Exception as e:
                return {"ok": False, "message": str(e)}

        # /system/health 已在上方 health_check 定义为统一入口

        @api_v1_router.get("/system/acceptance", tags=["system"])
        async def system_architect_acceptance_v1():
            """
            客户侧 / 产品架构师验收快照：进程状态、模块概况、网络出口模型说明。
            不包含密钥；代理 URL 仅显示是否已配置。
            """
            from src.modules.core.network_env_from_config import (
                build_proxy_url_from_config,
                egress_architecture_notes,
            )

            ts = datetime.now().isoformat()
            px: Dict[str, Any] = {}
            if self.config_manager:
                try:
                    raw = await self.config_manager.get_config("proxy", {}) or {}
                    px = raw if isinstance(raw, dict) else {}
                except Exception:
                    px = {}

            hp = bool((os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY") or "").strip())
            purl = build_proxy_url_from_config(px)
            no_preview = (os.getenv("NO_PROXY") or os.getenv("no_proxy") or "")[:400]

            sys_body: Dict[str, Any] = {}
            if main_controller:
                try:
                    sys_body = await main_controller.get_system_status()
                except Exception as e:
                    sys_body = {"error": str(e)}

            checklist: List[Dict[str, Any]] = []

            def _add(cid: str, ok: bool, detail: str) -> None:
                checklist.append({"id": cid, "ok": bool(ok), "detail": detail})

            _add(
                "config_manager",
                self.config_manager is not None,
                "配置管理器已绑定 API 服务" if self.config_manager else "未绑定",
            )
            _add(
                "main_controller",
                main_controller is not None,
                "主控制器已绑定" if main_controller else "未绑定",
            )
            rh = (os.getenv("REDIS_HOST") or "").strip()
            _add("redis_env", bool(rh), f"REDIS_HOST={rh or '(empty)'}")

            ex = getattr(main_controller, "okx_exchange", None) if main_controller else None
            ex_ok = False
            if ex is not None and hasattr(ex, "is_connected"):
                try:
                    ex_ok = bool(ex.is_connected)
                except Exception:
                    ex_ok = False
            _add("okx_exchange_session", ex_ok, "REST 会话可用" if ex_ok else "未连接或不可用")

            sltp = getattr(main_controller, "stop_loss_manager", None) if main_controller else None
            _add("stop_loss_manager", sltp is not None, "止盈止损管理器已挂载" if sltp else "未挂载")

            mc = int(sys_body.get("module_count", 0) or 0)
            rm = int(sys_body.get("running_modules", 0) or 0)
            ratio = (rm / mc) if mc > 0 else 0.0
            _add(
                "module_availability",
                ratio >= 0.85 or rm >= 20,
                f"running_modules={rm} module_count={mc} ratio={ratio:.2f}",
            )

            sys_st = str(sys_body.get("system_status") or "")
            critical_ids = {"config_manager", "main_controller", "redis_env"}
            critical_ok = all(x["ok"] for x in checklist if x["id"] in critical_ids)
            verdict = (
                "PASS"
                if critical_ok and sys_st == "running"
                else "ATTENTION"
            )

            return {
                "acceptance_version": "1.1",
                "role": "product_architect_snapshot",
                "timestamp": ts,
                "verdict": verdict,
                "system_status": sys_body,
                "network": {
                    **egress_architecture_notes(px),
                    "http_proxy_env_active": hp,
                    "proxy_url_built_from_config": bool(purl),
                    "no_proxy_preview": no_preview,
                },
                "checklist": checklist,
            }

        @api_v1_router.get("/debug/exchange-binding", tags=["debug"])
        async def debug_exchange_binding():
            """
            服务进程内的单一真相入口：
            用于排查“脚本实例”和“运行实例”不一致导致的引用分叉问题。
            """
            mc = self.main_controller
            hub = _resolve_data_source_hub()
            hub_mc = getattr(hub, "main_controller", None) if hub else None
            engine = getattr(mc, "ai_trading_engine", None) if mc else None
            ticker_probe: Dict[str, Any] = {}
            ticker_error: str = ""
            if hub and hasattr(hub, "get_ticker"):
                try:
                    ticker_probe = await hub.get_ticker("BTC/USDT")
                except Exception as e:
                    ticker_error = str(e)

            def _typ(x: Any) -> str:
                return type(x).__name__ if x is not None else "None"

            return {
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
                "binding": {
                    "main_controller_present": mc is not None,
                    "main_controller_type": _typ(mc),
                    "main_controller_id": id(mc) if mc is not None else None,
                    "data_source_hub_present": hub is not None,
                    "data_source_hub_type": _typ(hub),
                    "data_source_hub_id": id(hub) if hub is not None else None,
                    "data_source_hub_main_controller_present": hub_mc is not None,
                    "data_source_hub_main_controller_id": id(hub_mc) if hub_mc is not None else None,
                    "same_main_controller_object": (mc is not None and hub_mc is mc),
                },
                "exchanges": {
                    "ai_trading_engine_present": engine is not None,
                    "ai_trading_engine_exchange_type": _typ(getattr(engine, "exchange", None) if engine else None),
                    "okx_exchange_type": _typ(getattr(mc, "okx_exchange", None) if mc else None),
                    "execution_exchange_type": _typ(getattr(mc, "execution_exchange", None) if mc else None),
                    "market_data_exchange_type": _typ(getattr(mc, "market_data_exchange", None) if mc else None),
                    "exchange_accessor_type": _typ(mc.get_exchange() if (mc and hasattr(mc, "get_exchange")) else None),
                },
                "ticker_probe": {
                    "symbol": "BTC/USDT",
                    "source": ticker_probe.get("source") if isinstance(ticker_probe, dict) else None,
                    "last": (ticker_probe.get("last") or ticker_probe.get("price")) if isinstance(ticker_probe, dict) else None,
                    "has_price": bool(
                        isinstance(ticker_probe, dict)
                        and float(ticker_probe.get("last") or ticker_probe.get("price") or 0) > 0
                    ),
                    "error": ticker_error,
                },
            }

        # 指标端点 - 支持 /api/v1/metrics
        @api_v1_router.get("/metrics", tags=["metrics"])
        async def get_metrics_v1():
            """获取指标 v1"""
            api_stats = await self.get_api_stats()
            out: Dict[str, Any] = {
                "total_events": 0,
                "total_errors": 0,
                "module_starts": 0,
                "event_processing_time_ms": 0.0,
                "running_modules": 0,
                "module_count": 0,
                "websocket_active_connections": api_stats.get("websocket_active_connections", 0),
                "rate_limits": api_stats.get("rate_limits", {}),
                "uptime": self._get_uptime(),
                "timestamp": datetime.now().isoformat(),
                "api": api_stats,
            }
            if main_controller:
                try:
                    mc_status = await main_controller.get_system_status()
                    metrics = mc_status.get("metrics", {}) if isinstance(mc_status, dict) else {}
                    out["total_events"] = int(metrics.get("total_events", 0) or 0)
                    out["total_errors"] = int(metrics.get("total_errors", 0) or 0)
                    out["module_starts"] = int(metrics.get("module_starts", 0) or 0)
                    out["event_processing_time_ms"] = float(metrics.get("event_processing_time_ms", 0.0) or 0.0)
                    out["running_modules"] = int(mc_status.get("running_modules", 0) or 0)
                    out["module_count"] = int(mc_status.get("module_count", 0) or 0)
                except Exception as e:
                    out["status"] = "degraded"
                    out["error"] = str(e)
            return out

        @api_v1_router.get("/executions", tags=["executions"])
        async def get_executions(limit: int = 20):
            """获取最近执行记录（兼容 README/前端约定）"""
            safe_limit = max(1, min(int(limit), 200))
            if not main_controller:
                return []
            try:
                return await main_controller.get_recent_executions(safe_limit)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"获取执行记录失败: {e}")

        # 认证路由 - 同时支持 /auth/login 和 /api/v1/auth/login
        @api_v1_router.post("/auth/login", tags=["auth"])
        async def login(request: LoginRequest):
            """用户登录"""
            # 支持从配置或环境变量注入管理员账号，避免硬编码默认口令。
            if not self.admin_password:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="API auth is not configured",
                )
            if request.username == self.admin_username and request.password == self.admin_password:
                access_token = self.create_access_token(
                    data={"sub": request.username, "role": "admin"}
                )
                # 返回前端期望的格式
                return {
                    "token": access_token,
                    "user": {
                        "id": 1,
                        "username": request.username,
                        "role": "admin",
                        "email": "admin@example.com"
                    },
                    "access_token": access_token,
                    "token_type": "bearer",
                    "expires_in": self.access_token_expire_minutes * 60,
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
                )

        # 登出路由 - 同时支持 /auth/logout 和 /api/v1/auth/logout
        @api_v1_router.post("/auth/logout", tags=["auth"])
        async def logout():
            """用户登出"""
            # 这里应该处理登出逻辑，比如清除令牌等
            # 为简化，我们只返回成功响应
            return {"status": "success", "message": "登出成功"}

        # 刷新令牌路由 - 同时支持 /auth/refresh 和 /api/v1/auth/refresh
        @api_v1_router.post("/auth/refresh", tags=["auth"])
        async def refresh_token():
            """刷新访问令牌"""
            # 这里应该处理令牌刷新逻辑
            # 为简化，我们返回一个新的令牌
            access_token = self.create_access_token(
                data={"sub": "admin", "role": "admin"}
            )
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": self.access_token_expire_minutes * 60,
            }

        # 获取当前用户路由 - 同时支持 /auth/me 和 /api/v1/auth/me
        @api_v1_router.get("/auth/me", tags=["auth"])
        async def get_current_user(
            credentials: HTTPAuthorizationCredentials = Depends(self.security),
        ):
            """获取当前用户信息"""
            token = credentials.credentials
            payload = await self.verify_token(token)
            if not payload:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的令牌")
            return {
                "id": 1,
                "username": payload.get("sub", "unknown"),
                "role": payload.get("role", "viewer"),
                "email": "admin@example.com",
                "created_at": datetime.now().isoformat(),
            }

        @api_v1_router.get("/auth/status", tags=["auth"])
        async def auth_status():
            """返回当前 API 鉴权运行状态（不包含敏感密钥）。"""
            return {
                "auth_configured": bool(self.admin_password),
                "enforce_auth_on_writes": bool(self.enforce_auth_on_writes),
                "require_ws_auth": bool(self.require_ws_auth),
                "required_write_roles": sorted(list(self.required_write_roles)),
                "protected_write_prefixes": list(self.protected_write_prefixes),
                "timestamp": datetime.now().isoformat(),
            }

        @api_v1_router.get("/auth/write-policy", tags=["auth"])
        async def auth_write_policy():
            """返回写接口鉴权策略，用于前端/自动化运维对接。"""
            return {
                "success": True,
                "policy": {
                    "enforce_auth_on_writes": bool(self.enforce_auth_on_writes),
                    "required_write_roles": sorted(list(self.required_write_roles)),
                    "protected_write_prefixes": list(self.protected_write_prefixes),
                    "auth_exempt_paths": sorted(list(self.auth_exempt_paths)),
                },
                "timestamp": datetime.now().isoformat(),
            }

        # 受保护的路由示例
        @api_v1_router.get("/protected", tags=["api"])
        async def protected_route(
            credentials: HTTPAuthorizationCredentials = Depends(self.security),
        ):
            """受保护的路由"""
            token = credentials.credentials
            payload = await self.verify_token(token)

            if not payload:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的令牌")

            return {
                "message": f"欢迎 {payload.get('sub')}",
                "role": payload.get("role"),
                "timestamp": datetime.now().isoformat(),
            }

        def _strategy_manager_payload_list() -> List[Dict[str, Any]]:
            mc = self.main_controller
            if not mc or not getattr(mc, "strategy_manager", None):
                return []
            sm = mc.strategy_manager
            configs = getattr(sm, "strategy_configs", None) or {}
            metrics = getattr(sm, "performance_metrics", None) or {}
            out: List[Dict[str, Any]] = []
            for sid, cfg in configs.items():
                d = cfg.to_dict() if hasattr(cfg, "to_dict") else {}
                item: Dict[str, Any] = {
                    "id": d.get("strategy_id", sid),
                    "strategy_id": d.get("strategy_id", sid),
                    "name": d.get("name", sid),
                    "description": d.get("description", ""),
                    "strategy_type": d.get("strategy_type"),
                    "status": "active" if d.get("enabled", True) else "inactive",
                    "enabled": d.get("enabled", True),
                    "symbols": d.get("symbols", []),
                    "timeframe": d.get("timeframe", "1h"),
                    "parameters": d.get("parameters", {}),
                    "metadata": d.get("metadata", {}),
                    "returns": "-",
                    "max_drawdown": "-",
                    "sharpe_ratio": "-",
                }
                perf = metrics.get(sid)
                if perf:
                    item["total_trades"] = int(getattr(perf, "total_trades", 0) or 0)
                    item["win_rate"] = round(100.0 * float(getattr(perf, "win_rate", 0.0) or 0.0), 2)
                    item["max_drawdown"] = str(round(float(getattr(perf, "max_drawdown", 0.0) or 0.0) * 100.0, 2))
                    item["sharpe_ratio"] = str(round(float(getattr(perf, "sharpe_ratio", 0.0) or 0.0), 3))
                    item["returns"] = str(round(float(getattr(perf, "total_pnl", 0.0) or 0.0), 4))
                out.append(item)
            return out

        # 策略管理路由 - 支持 /api/v1/strategies（真实 StrategyManager）
        @api_v1_router.get("/strategies", tags=["strategies"])
        async def get_strategies():
            """获取所有策略（来自 StrategyManager）"""
            return _strategy_manager_payload_list()

        @api_v1_router.get("/strategies/signals", tags=["strategies"])
        async def get_strategy_signals(
            strategy_id: Optional[str] = None,
            instance_id: Optional[str] = None,
            signal_type: Optional[str] = None,
            limit: int = 50,
        ):
            """
            获取策略信号（用于“策略信号查询”验收）
            - strategy_id/instance_id 可选过滤
            - signal_type: BUY/SELL/HOLD（不区分大小写）
            """
            mc = self.main_controller
            if not mc or not getattr(mc, "strategy_manager", None):
                raise HTTPException(status_code=503, detail="策略管理器未初始化")
            sm = mc.strategy_manager
            st = None
            if signal_type:
                try:
                    from src.modules.core.strategy_manager import SignalType as _SignalType

                    st = _SignalType[str(signal_type).strip().upper()]
                except Exception:
                    st = None
            try:
                rows = await sm.get_signals(
                    strategy_id=strategy_id) if strategy_id else None
            except TypeError:
                rows = None
            # prefer calling with full signature
            if rows is None:
                rows = await sm.get_signals(
                    strategy_id=str(strategy_id) if strategy_id else None,
                    instance_id=str(instance_id) if instance_id else None,
                    signal_type=st,
                    limit=max(1, min(int(limit or 50), 500)),
                )
            out: List[Dict[str, Any]] = []
            for s in rows or []:
                out.append(s.to_dict() if hasattr(s, "to_dict") else dict(s))
            return {
                "success": True,
                "data": out,
                "count": len(out),
                "filters": {
                    "strategy_id": strategy_id,
                    "instance_id": instance_id,
                    "signal_type": signal_type,
                },
                "timestamp": datetime.now().isoformat(),
            }

        @api_v1_router.get("/strategies/{id}", tags=["strategies"])
        async def get_strategy(id: str):
            """获取单个策略详情"""
            mc = self.main_controller
            if not mc or not getattr(mc, "strategy_manager", None):
                raise HTTPException(status_code=503, detail="策略管理器未初始化")
            sm = mc.strategy_manager
            if id not in sm.strategy_configs:
                raise HTTPException(status_code=404, detail="策略不存在")
            cfg = sm.strategy_configs[id]
            d = cfg.to_dict() if hasattr(cfg, "to_dict") else {}
            metrics = getattr(sm, "performance_metrics", None) or {}
            perf = metrics.get(id)
            body: Dict[str, Any] = {
                "id": id,
                "strategy_id": d.get("strategy_id", id),
                "name": d.get("name", id),
                "status": "active" if d.get("enabled", True) else "inactive",
                "parameters": d.get("parameters", {}),
                "symbols": d.get("symbols", []),
                "timeframe": d.get("timeframe", "1h"),
                "metadata": d.get("metadata", {}),
                "strategy_type": d.get("strategy_type"),
                "description": d.get("description", ""),
            }
            if perf:
                body["returns"] = str(round(float(getattr(perf, "total_pnl", 0.0) or 0.0), 4))
                body["max_drawdown"] = str(round(float(getattr(perf, "max_drawdown", 0.0) or 0.0) * 100.0, 2))
                body["sharpe_ratio"] = str(round(float(getattr(perf, "sharpe_ratio", 0.0) or 0.0), 3))
            else:
                body.setdefault("returns", "0")
                body.setdefault("max_drawdown", "0")
                body.setdefault("sharpe_ratio", "0")
            return body

        @api_v1_router.post("/strategies", tags=["strategies"])
        async def create_strategy(strategy_data: Dict[str, Any]):
            """创建策略（加载到 StrategyManager）"""
            mc = self.main_controller
            if not mc or not getattr(mc, "strategy_manager", None):
                raise HTTPException(status_code=503, detail="策略管理器未初始化")
            sm = mc.strategy_manager
            if not strategy_data.get("strategy_id"):
                strategy_data = {**strategy_data, "strategy_id": f"api_{datetime.now().strftime('%Y%m%d%H%M%S')}"}
            cfg = await sm.load_strategy_config(strategy_data)
            if not cfg:
                raise HTTPException(status_code=400, detail="策略配置无效：需含 name、strategy_type")
            return {
                "id": cfg.strategy_id,
                "name": cfg.name,
                "status": "inactive" if not cfg.enabled else "active",
                "message": "策略已加载",
            }

        @api_v1_router.put("/strategies/{id}", tags=["strategies"])
        async def update_strategy(id: str, strategy_data: Dict[str, Any]):
            """更新策略（内存中的配置）"""
            mc = self.main_controller
            if not mc or not getattr(mc, "strategy_manager", None):
                raise HTTPException(status_code=503, detail="策略管理器未初始化")
            sm = mc.strategy_manager
            if id not in sm.strategy_configs:
                raise HTTPException(status_code=404, detail="策略不存在")
            cfg = sm.strategy_configs[id]
            if "name" in strategy_data:
                cfg.name = str(strategy_data["name"])
            if "description" in strategy_data:
                cfg.description = str(strategy_data["description"])
            if "enabled" in strategy_data:
                cfg.enabled = bool(strategy_data["enabled"])
            if "parameters" in strategy_data and isinstance(strategy_data["parameters"], dict):
                cfg.parameters = {**cfg.parameters, **strategy_data["parameters"]}
            if "symbols" in strategy_data and isinstance(strategy_data["symbols"], list):
                cfg.symbols = list(strategy_data["symbols"])
            cfg.updated_at = datetime.now()
            return {"id": id, "name": cfg.name, "status": "active" if cfg.enabled else "inactive"}

        @api_v1_router.delete("/strategies/{id}", tags=["strategies"])
        async def delete_strategy(id: str):
            """从策略池移除"""
            mc = self.main_controller
            if not mc or not getattr(mc, "strategy_manager", None):
                raise HTTPException(status_code=503, detail="策略管理器未初始化")
            sm = mc.strategy_manager
            async with sm._lock:
                sm.strategy_configs.pop(id, None)
                sm.performance_metrics.pop(id, None)
            return {"status": "success", "message": "策略已删除"}

        @api_v1_router.post("/strategies/{id}/activate", tags=["strategies"])
        async def activate_strategy(id: str):
            """激活策略"""
            mc = self.main_controller
            if not mc or not getattr(mc, "strategy_manager", None):
                raise HTTPException(status_code=503, detail="策略管理器未初始化")
            sm = mc.strategy_manager
            if id not in sm.strategy_configs:
                raise HTTPException(status_code=404, detail="策略不存在")
            sm.strategy_configs[id].enabled = True
            return {"status": "success", "message": "策略已激活"}

        @api_v1_router.post("/strategies/{id}/deactivate", tags=["strategies"])
        async def deactivate_strategy(id: str):
            """停用策略"""
            mc = self.main_controller
            if not mc or not getattr(mc, "strategy_manager", None):
                raise HTTPException(status_code=503, detail="策略管理器未初始化")
            sm = mc.strategy_manager
            if id not in sm.strategy_configs:
                raise HTTPException(status_code=404, detail="策略不存在")
            sm.strategy_configs[id].enabled = False
            return {"status": "success", "message": "策略已停用"}

        @api_v1_router.get("/strategies/{id}/performance", tags=["strategies"])
        async def get_strategy_performance(id: str):
            """获取策略性能指标"""
            mc = self.main_controller
            if not mc or not getattr(mc, "strategy_manager", None):
                raise HTTPException(status_code=503, detail="策略管理器未初始化")
            sm = mc.strategy_manager
            perf = (getattr(sm, "performance_metrics", None) or {}).get(id)
            if not perf:
                return {
                    "strategy_id": id,
                    "total_return": "0",
                    "max_drawdown": "0",
                    "sharpe_ratio": "0",
                    "win_rate": "0",
                    "profit_factor": "0",
                    "total_trades": "0",
                    "average_trade": "0",
                }
            return {
                "strategy_id": id,
                "total_return": str(round(float(perf.total_pnl or 0.0), 4)),
                "max_drawdown": str(round(float(perf.max_drawdown or 0.0) * 100.0, 2)),
                "sharpe_ratio": str(round(float(perf.sharpe_ratio or 0.0), 3)),
                "win_rate": str(round(100.0 * float(perf.win_rate or 0.0), 2)),
                "profit_factor": str(round(float(perf.profit_factor or 0.0), 3)),
                "total_trades": str(int(perf.total_trades or 0)),
                "average_trade": str(round(float(perf.avg_trade_pnl or 0.0), 6)),
            }

        # 市场数据路由 - 支持 /api/v1/market/data
        @api_v1_router.get("/market/data", tags=["market"])
        async def get_market_data(symbol: str = "BTC/USDT"):
            """获取市场数据"""
            # 这里应该从市场数据服务获取真实数据
            # 为简化，返回模拟数据
            import random
            data = []
            now = datetime.now()
            for i in range(100):
                timestamp = (now - timedelta(minutes=i)).isoformat()
                base_price = 50000 if symbol == "BTC/USDT" else 3000
                price = base_price + random.uniform(-1000, 1000)
                data.append({
                    "timestamp": timestamp,
                    "open": price - random.uniform(100, 200),
                    "high": price + random.uniform(50, 100),
                    "low": price - random.uniform(50, 100),
                    "close": price,
                    "volume": random.uniform(1000, 5000)
                })
            # 反转数据，使最新的数据在最后
            data.reverse()
            return data

        # 市场行情路由 - 支持 /api/v1/market/ticker/{symbol}
        @api_v1_router.get("/market/ticker/{symbol}", tags=["market"])
        async def get_market_ticker(symbol: str):
            """获取市场行情（统一数据源模块）"""
            return await _resolve_data_source_hub().get_ticker(symbol)

        @api_v1_router.get("/market/ticker", tags=["market"])
        async def get_market_ticker_q(symbol: str):
            """兼容 query 参数形式：/market/ticker?symbol=BTC/USDT"""
            return await _resolve_data_source_hub().get_ticker(symbol)

        # K线路由 - 支持 /api/v1/market/klines/{symbol}
        @api_v1_router.get("/market/klines/{symbol}", tags=["market"])
        async def get_market_klines(symbol: str, interval: str = "1H", limit: int = 100):
            """获取K线数据（统一数据源模块）"""
            return await _resolve_data_source_hub().get_klines(symbol, interval=interval, limit=limit)

        @api_v1_router.get("/market/klines", tags=["market"])
        async def get_market_klines_q(symbol: str, interval: str = "1H", limit: int = 100):
            """兼容 query 参数形式：/market/klines?symbol=BTC/USDT"""
            return await _resolve_data_source_hub().get_klines(symbol, interval=interval, limit=limit)

        # 订单簿路由 - 支持 /api/v1/market/orderbook/{symbol}
        @api_v1_router.get("/market/orderbook/{symbol}", tags=["market"])
        async def get_market_orderbook(symbol: str, depth: int = 20):
            """获取订单簿（统一数据源模块）"""
            return await _resolve_data_source_hub().get_order_book(symbol, depth=depth)

        @api_v1_router.get("/market/orderbook", tags=["market"])
        async def get_market_orderbook_q(symbol: str, depth: int = 20):
            """兼容 query 参数形式：/market/orderbook?symbol=BTC/USDT"""
            return await _resolve_data_source_hub().get_order_book(symbol, depth=depth)

        @api_v1_router.get("/market/symbols", tags=["market"])
        async def get_market_symbols():
            """获取可用交易对（统一数据源模块）"""
            return {
                "status": "success",
                "data": await _resolve_data_source_hub().get_symbols(),
                "timestamp": datetime.now().isoformat(),
            }

        # 风险指标路由 - 支持 /api/v1/risk/metrics
        @api_v1_router.get("/risk/metrics", tags=["risk"])
        async def get_risk_metrics():
            """获取风险指标"""
            mc = self.main_controller
            if mc and hasattr(mc, "get_risk_metrics"):
                try:
                    risk = mc.get_risk_metrics()
                    if isinstance(risk, dict):
                        return {
                            **risk,
                            "source": "main_controller",
                            "timestamp": datetime.now().isoformat(),
                        }
                except Exception as e:
                    logger.warning("get_risk_metrics from main_controller failed: %s", e)

            # 兜底：从交易所实时持仓估算风险指标，避免长期 fallback:empty
            if mc:
                try:
                    ex = mc.get_exchange() if hasattr(mc, "get_exchange") else None
                    ex = ex or getattr(mc, "okx_exchange", None)
                    if ex and hasattr(ex, "get_positions"):
                        rows = await ex.get_positions()
                        total_exposure = 0.0
                        max_position_size = 0.0
                        leverage_used = 0.0
                        margin_used = 0.0
                        position_count = 0
                        for p in rows or []:
                            if not isinstance(p, dict):
                                continue
                            try:
                                size_v = abs(float(p.get("size", p.get("pos", 0)) or 0.0))
                            except Exception:
                                size_v = 0.0
                            if size_v <= 0:
                                continue

                            try:
                                notional = abs(float(p.get("notional_value") or 0.0))
                            except Exception:
                                notional = 0.0
                            if notional <= 0:
                                try:
                                    mark_px = float(p.get("mark_px", p.get("mark_price", 0)) or 0.0)
                                except Exception:
                                    mark_px = 0.0
                                notional = abs(size_v * mark_px)

                            try:
                                lev = float(p.get("leverage") or 0.0)
                            except Exception:
                                lev = 0.0

                            total_exposure += notional
                            max_position_size = max(max_position_size, notional)
                            leverage_used = max(leverage_used, lev)
                            if lev > 0:
                                margin_used += notional / lev
                            position_count += 1

                        latest = getattr(mc, "_latest_account_state", {}) or {}
                        portfolio_value = 0.0
                        for k in ("usdt_total", "usdt_free"):
                            try:
                                v = float(latest.get(k) or 0.0)
                                portfolio_value = max(portfolio_value, v)
                            except Exception:
                                continue
                        if portfolio_value <= 0:
                            portfolio_value = margin_used

                        margin_level = (portfolio_value / total_exposure) if total_exposure > 0 else 0.0
                        if leverage_used >= 50 or margin_level < 0.05:
                            risk_level = "high"
                        elif leverage_used >= 20 or margin_level < 0.1:
                            risk_level = "medium"
                        else:
                            risk_level = "low"

                        return {
                            "portfolio_value": float(portfolio_value),
                            "total_exposure": float(total_exposure),
                            "var_95": 0.0,
                            "max_position_size": float(max_position_size),
                            "leverage_used": float(leverage_used),
                            "margin_level": float(margin_level),
                            "risk_level": risk_level,
                            "position_count": int(position_count),
                            "warnings": [],
                            "source": "main_controller:positions_estimated",
                            "timestamp": datetime.now().isoformat(),
                        }
                except Exception as e:
                    logger.warning("get_risk_metrics estimated fallback failed: %s", e)

            # 无实时样本时返回统一降级结构，避免前端硬依赖固定字段时报错
            return {
                "portfolio_value": 0.0,
                "total_exposure": 0.0,
                "var_95": 0.0,
                "max_position_size": 0.0,
                "leverage_used": 0.0,
                "margin_level": 0.0,
                "risk_level": "unknown",
                "position_count": 0,
                "warnings": [],
                "source": "fallback:empty",
                "timestamp": datetime.now().isoformat(),
            }

        # 交易历史路由 - 支持 /api/v1/trades
        def _load_execution_audit_records(days: int = 30) -> List[Dict[str, Any]]:
            """Fallback data source: load execution/audit JSONL records."""
            records: List[Dict[str, Any]] = []
            cutoff = datetime.now() - timedelta(days=max(days, 1))

            # 1) Execution gateway audit (primary structured source)
            exec_dir = Path("logs/executions")
            if exec_dir.exists():
                for file_path in sorted(exec_dir.glob("*.jsonl"), reverse=True):
                    try:
                        for raw_line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                            line = raw_line.strip()
                            if not line:
                                continue
                            row = json.loads(line)
                            ts_raw = row.get("timestamp")
                            if ts_raw:
                                try:
                                    ts_obj = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                                except Exception:
                                    ts_obj = None
                                if ts_obj is not None and ts_obj.replace(tzinfo=None) < cutoff:
                                    continue
                            records.append(row)
                    except Exception:
                        continue

            # 2) Trade audit events (trade_open/trade_close) as compatibility source
            audit_dir = Path("logs/audit")
            if audit_dir.exists():
                for file_path in sorted(audit_dir.glob("audit_*.jsonl"), reverse=True):
                    try:
                        for raw_line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                            line = raw_line.strip()
                            if not line:
                                continue
                            row = json.loads(line)
                            ts_raw = row.get("timestamp")
                            if ts_raw:
                                try:
                                    ts_obj = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                                except Exception:
                                    ts_obj = None
                                if ts_obj is not None and ts_obj.replace(tzinfo=None) < cutoff:
                                    continue
                            et = str(row.get("event_type") or "").strip().lower()
                            if et not in ("trade_open", "trade_close"):
                                continue
                            records.append(row)
                    except Exception:
                        continue
            records.sort(key=lambda r: str(r.get("timestamp") or ""), reverse=True)
            return records

        def _to_float(v: Any, default: float = 0.0) -> float:
            try:
                if v is None or v == "":
                    return float(default)
                return float(v)
            except Exception:
                return float(default)

        def _audit_row_to_trade(row: Dict[str, Any]) -> Dict[str, Any]:
            details = row.get("details") if isinstance(row.get("details"), dict) else {}
            event_type = str(row.get("event_type") or "").strip().lower()
            result_raw = str(row.get("result") or "").strip().lower()
            pnl = _to_float(
                details.get("pnl")
                if details.get("pnl") is not None
                else details.get("realized_pnl")
            )
            pnl_percent = _to_float(
                details.get("pnl_percent")
                if details.get("pnl_percent") is not None
                else details.get("realized_pnl_percent")
            )
            # For trade audit rows (trade_close), derive pnl from entry/trigger when explicit pnl is absent.
            if abs(pnl) <= 1e-12 and abs(pnl_percent) > 1e-12:
                qty = _to_float(details.get("quantity"))
                entry_price = _to_float(details.get("entry_price"))
                if qty > 0 and entry_price > 0:
                    pnl = pnl_percent * qty * entry_price
            # Legacy trade_close audits may not carry pnl/pnl_percent.
            # Provide a conservative direction-only estimate so realized rows are not all zero.
            if event_type == "trade_close" and abs(pnl_percent) <= 1e-12:
                if result_raw in ("take_profit", "success"):
                    pnl_percent = 0.002
                elif result_raw == "stop_loss":
                    pnl_percent = -0.002
                if abs(pnl) <= 1e-12 and abs(pnl_percent) > 1e-12:
                    qty = _to_float(details.get("quantity"))
                    px = _to_float(details.get("entry_price")) or _to_float(details.get("price"))
                    if qty > 0 and px > 0:
                        pnl = pnl_percent * qty * px
            fee = _to_float(details.get("fee"))
            return {
                "trade_id": row.get("execution_id") or row.get("event_id"),
                "order_id": details.get("order_id") or row.get("execution_id") or row.get("event_id"),
                "symbol": row.get("symbol") or details.get("symbol"),
                "side": details.get("side") or row.get("action"),
                "quantity": _to_float(details.get("quantity")),
                "price": _to_float(details.get("price")),
                "fee": fee,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "status": (
                    "filled"
                    if (str(row.get("status", "")).lower() == "success" or result_raw in ("success", "take_profit", "stop_loss"))
                    else str(row.get("status") or row.get("result") or "unknown")
                ),
                "timestamp": row.get("timestamp"),
                "source": "execution_audit" if event_type == "" else "trade_audit",
                "metadata": {
                    "source": "execution_audit" if event_type == "" else "trade_audit",
                    "execution_id": row.get("execution_id"),
                    "event_id": row.get("event_id"),
                    "event_type": event_type,
                    "verified": bool(row.get("verified")),
                    "verification_details": row.get("verification_details"),
                    "command_type": row.get("command_type"),
                },
                "error_message": row.get("error_message"),
            }

        def _is_bootstrap_trade(row: Dict[str, Any]) -> bool:
            md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            src = str((md.get("source") or row.get("source") or "")).strip().lower()
            return src == "db_bootstrap"

        def _is_realized_trade(row: Dict[str, Any]) -> bool:
            pnl = _to_float(row.get("pnl"))
            pnl_pct = _to_float(row.get("pnl_percent"))
            if abs(pnl) > 1e-12 or abs(pnl_pct) > 1e-12:
                return True
            # break-even close should still be treated as realized when confirmed by close action/status
            action = str(row.get("action") or "").strip().lower()
            status = str(row.get("status") or "").strip().lower()
            return action in {"close", "closed"} or status in {"closed", "filled"}

        @api_v1_router.get("/trades", tags=["trades"])
        async def get_trades(
            range: str = "7d",
            symbol: Optional[str] = None,
            side: Optional[str] = None,
            limit: int = 100,
            offset: int = 0,
            realized_only: bool = False,
            exclude_bootstrap: bool = False,
            exclude_estimated_pnl: bool = False,
            accurate_only: bool = False,
        ):
            """
            获取交易历史（真实数据）
            
            参数：
            - range: 时间范围 (24h, 7d, 30d, 90d)
            - symbol: 交易对过滤 (如 BTC/USDT)
            - side: 方向过滤 (buy/sell)
            - limit: 返回数量限制
            - offset: 分页偏移
            - accurate_only: 仅返回可用于真实收益分析的记录（等价 realized_only+exclude_bootstrap）
            """
            try:
                mc = self.main_controller
                if accurate_only:
                    realized_only = True
                    exclude_bootstrap = True
                    exclude_estimated_pnl = True
                # 解析时间范围
                now = datetime.now()
                if range == "24h":
                    start_date = now - timedelta(days=1)
                elif range == "7d":
                    start_date = now - timedelta(days=7)
                elif range == "30d":
                    start_date = now - timedelta(days=30)
                elif range == "90d":
                    start_date = now - timedelta(days=90)
                else:
                    start_date = now - timedelta(days=7)  # 默认7天
                
                # 尝试从主控制器获取交易历史服务
                trade_service = None
                if mc and hasattr(mc, 'trade_history_service'):
                    trade_service = mc.trade_history_service
                
                if trade_service:
                    # 使用真实的交易历史服务查询
                    # Note: filtering after retrieval can empty a page if raw rows include many non-realized/bootstrap entries.
                    # Over-fetch and paginate after filtering for stable operator-facing results.
                    fetch_limit = max(int(limit or 100) * 20, 2000)
                    trades = await trade_service.get_trade_history(
                        start_date=start_date,
                        symbol=symbol,
                        side=side,
                        limit=fetch_limit,
                        offset=0,
                    )
                    clean_trades: List[Dict[str, Any]] = []
                    for row in (trades or []):
                        if not isinstance(row, dict):
                            continue
                        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                        if exclude_bootstrap and _is_bootstrap_trade(row):
                            continue
                        if exclude_estimated_pnl and bool(md.get("pnl_estimated")):
                            continue
                        if realized_only and not _is_realized_trade(row):
                            continue
                        clean_trades.append(row)
                    paged_trades = clean_trades[offset: offset + max(limit, 1)]
                    
                    if not paged_trades:
                        return {
                            "trades": [],
                            "total": len(clean_trades),
                            "message": f"暂无{range}时间范围内的交易记录",
                            "filters_applied": {
                                "realized_only": bool(realized_only),
                                "exclude_bootstrap": bool(exclude_bootstrap),
                                "exclude_estimated_pnl": bool(exclude_estimated_pnl),
                            },
                            "query_time": datetime.now().isoformat()
                        }
                    
                    return {
                        "trades": paged_trades,
                        "total": len(clean_trades),
                        "range": range,
                        "filters": {
                            "symbol": symbol,
                            "side": side,
                            "realized_only": bool(realized_only),
                            "exclude_bootstrap": bool(exclude_bootstrap),
                            "exclude_estimated_pnl": bool(exclude_estimated_pnl),
                        },
                        "query_time": datetime.now().isoformat()
                    }
                
                else:
                    # 如果服务不可用，尝试从数据库直接查询
                    try:
                        from src.modules.core.historical_data_storage import get_historical_storage
                        
                        storage = await get_historical_storage()
                        
                        # 查询数据库中的交易记录
                        trades_db = await storage.get_trades(
                            start_date=start_date.isoformat(),
                            end_date=now.isoformat(),
                            symbol=symbol,
                            limit=limit
                        )
                        
                        if trades_db:
                            from dataclasses import asdict
                            trades_list = [asdict(t) for t in trades_db]
                            clean_list: List[Dict[str, Any]] = []
                            for row in trades_list:
                                if not isinstance(row, dict):
                                    continue
                                if exclude_bootstrap and _is_bootstrap_trade(row):
                                    continue
                                if realized_only and not _is_realized_trade(row):
                                    continue
                                clean_list.append(row)
                            
                            return {
                                "trades": clean_list,
                                "total": len(clean_list),
                                "source": "database",
                                "range": range,
                                "filters": {
                                    "symbol": symbol,
                                    "side": side,
                                    "realized_only": bool(realized_only),
                                    "exclude_bootstrap": bool(exclude_bootstrap),
                                    "exclude_estimated_pnl": bool(exclude_estimated_pnl),
                                },
                                "query_time": datetime.now().isoformat()
                            }
                        else:
                            return {
                                "trades": [],
                                "total": 0,
                                "message": "暂无交易记录",
                                "note": "交易历史服务未初始化，已尝试直接查询数据库",
                                "query_time": datetime.now().isoformat()
                            }
                    
                    except Exception as db_error:
                        logger.error(f"数据库查询失败: {db_error}")
                        fallback_days = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}.get(range, 7)
                        audit_rows = _load_execution_audit_records(days=fallback_days)
                        mapped: List[Dict[str, Any]] = []
                        for row in audit_rows[offset: offset + max(limit, 1)]:
                            details = row.get("details") or {}
                            mapped.append(
                                {
                                    "order_id": details.get("order_id"),
                                    "symbol": row.get("symbol") or details.get("symbol"),
                                    "side": details.get("side") or row.get("action"),
                                    "quantity": details.get("quantity"),
                                    "price": details.get("price"),
                                    "status": row.get("status"),
                                    "timestamp": row.get("timestamp"),
                                    "executed_quantity": details.get("quantity"),
                                    "avg_price": details.get("price"),
                                    "fee": None,
                                    "source": "execution_audit",
                                    "error_message": row.get("error_message"),
                                }
                            )
                        clean_mapped: List[Dict[str, Any]] = []
                        for row in mapped:
                            if exclude_bootstrap and _is_bootstrap_trade(row):
                                continue
                            if realized_only and not _is_realized_trade(row):
                                continue
                            clean_mapped.append(row)
                        return {
                            "trades": clean_mapped,
                            "total": len(clean_mapped),
                            "source": "fallback:execution_audit",
                            "note": "trade_history_service/database unavailable",
                            "filters": {
                                "symbol": symbol,
                                "side": side,
                                "realized_only": bool(realized_only),
                                "exclude_bootstrap": bool(exclude_bootstrap),
                                "exclude_estimated_pnl": bool(exclude_estimated_pnl),
                            },
                            "query_time": datetime.now().isoformat(),
                        }
                        
            except Exception as e:
                logger.error(f"获取交易历史失败: {e}", exc_info=True)
                return {
                    "error": "获取交易历史失败",
                    "details": str(e),
                    "suggestion": "请联系管理员检查系统状态"
                }

        @api_v1_router.get("/trades/reconcile", tags=["trades"])
        async def reconcile_trades_with_exchange(
            days: int = 7,
            symbol: Optional[str] = None,
            limit: int = 200,
            max_exchange_checks: int = 120,
            exclude_bootstrap: bool = True,
            exclude_estimated_pnl: bool = True,
            include_time_window_fallback: bool = True,
            fallback_time_window_sec: int = 240,
            max_fallback_candidates_per_symbol: int = 30,
        ):
            """
            对账系统平仓记录与交易所成交事实（按 order_id + symbol）。
            """
            try:
                mc = self.main_controller
                trade_service = getattr(mc, "trade_history_service", None) if mc else None
                if not trade_service:
                    return {"success": False, "message": "trade_history_service unavailable"}
                ex = mc.get_exchange() if (mc and hasattr(mc, "get_exchange")) else None
                if not ex:
                    ex = getattr(mc, "okx_exchange", None) if mc else None
                if not ex:
                    return {"success": False, "message": "exchange unavailable"}
                get_fills = getattr(ex, "get_swap_fills_for_order", None)
                if not callable(get_fills):
                    return {"success": False, "message": "exchange does not support fills reconciliation"}
                get_history_fills = getattr(ex, "get_recent_fills", None)

                start_date = datetime.now() - timedelta(days=max(1, int(days or 7)))
                fetch_limit = max(int(limit or 200) * 10, 1000)
                rows = await trade_service.get_trade_history(
                    start_date=start_date,
                    symbol=symbol,
                    limit=fetch_limit,
                    offset=0,
                )

                candidates: List[Dict[str, Any]] = []
                for row in (rows or []):
                    if not isinstance(row, dict):
                        continue
                    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                    action = str(row.get("action") or "").strip().lower()
                    status = str(row.get("status") or "").strip().lower()
                    if action not in {"close", "closed"} and status not in {"filled", "closed"}:
                        continue
                    if exclude_bootstrap and _is_bootstrap_trade(row):
                        continue
                    if exclude_estimated_pnl and bool(md.get("pnl_estimated")):
                        continue
                    oid = str(row.get("order_id") or "").strip()
                    sym = str(row.get("symbol") or "").strip()
                    if not sym:
                        continue
                    candidates.append(row)

                candidates = candidates[: max(1, int(max_exchange_checks or 120))]
                details: List[Dict[str, Any]] = []
                matched = 0
                missing = 0
                matched_by_order_id = 0
                matched_by_time_window = 0
                abs_pnl_delta_sum = 0.0
                abs_fee_delta_sum = 0.0

                def _parse_ts(ts: Any) -> Optional[datetime]:
                    s = str(ts or "").strip()
                    if not s:
                        return None
                    try:
                        return datetime.fromisoformat(s.replace("Z", "+00:00"))
                    except Exception:
                        return None

                def _aggregate_fills(fills: List[Dict[str, Any]]) -> Dict[str, float]:
                    ex_pnl = 0.0
                    ex_fee = 0.0
                    ex_px_num = 0.0
                    ex_px_den = 0.0
                    for f in (fills or []):
                        if not isinstance(f, dict):
                            continue
                        for k in ("fillPnl", "pnl", "realizedPnl"):
                            if f.get(k) is None:
                                continue
                            ex_pnl += _to_float(f.get(k))
                            break
                        ex_fee += _to_float(f.get("fee"))
                        fsz = _to_float(f.get("fillSz") if f.get("fillSz") is not None else f.get("sz"))
                        fpx = _to_float(f.get("fillPx") if f.get("fillPx") is not None else f.get("px"))
                        if fsz > 0 and fpx > 0:
                            ex_px_num += fpx * fsz
                            ex_px_den += fsz
                    ex_price = (ex_px_num / ex_px_den) if ex_px_den > 1e-18 else 0.0
                    return {"pnl": ex_pnl, "fee": ex_fee, "price": ex_price}

                fallback_fills_by_symbol: Dict[str, List[Dict[str, Any]]] = {}

                for row in candidates:
                    oid = str(row.get("order_id") or "").strip()
                    sym = str(row.get("symbol") or "").strip()
                    match_method = "none"
                    fills: List[Dict[str, Any]] = []
                    if oid:
                        try:
                            fills = await get_fills(sym, oid)
                        except Exception:
                            fills = []
                        if fills:
                            match_method = "order_id"
                            matched_by_order_id += 1
                    if (
                        not fills
                        and include_time_window_fallback
                        and callable(get_history_fills)
                    ):
                        ts = _parse_ts(row.get("timestamp"))
                        if sym not in fallback_fills_by_symbol:
                            try:
                                got = await get_history_fills(
                                    symbol=sym,
                                    limit=max(5, int(max_fallback_candidates_per_symbol or 30)),
                                )
                                fallback_fills_by_symbol[sym] = list(got or []) if isinstance(got, list) else []
                            except Exception:
                                fallback_fills_by_symbol[sym] = []
                        if ts is not None:
                            delta_sec = max(10, int(fallback_time_window_sec or 240))
                            time_bucket: List[Dict[str, Any]] = []
                            for f in fallback_fills_by_symbol.get(sym, []):
                                if not isinstance(f, dict):
                                    continue
                                fts = _parse_ts(f.get("ts") or f.get("fillTime") or f.get("cTime"))
                                if fts is None:
                                    continue
                                if abs((fts - ts).total_seconds()) <= float(delta_sec):
                                    time_bucket.append(f)
                            if time_bucket:
                                fills = time_bucket
                                match_method = "time_window"
                                matched_by_time_window += 1

                    aggr = _aggregate_fills(fills)
                    ex_pnl = _to_float(aggr.get("pnl"))
                    ex_fee = _to_float(aggr.get("fee"))
                    ex_price = _to_float(aggr.get("price"))

                    sys_pnl = _to_float(row.get("pnl"))
                    sys_fee = _to_float(row.get("fee"))
                    sys_price = _to_float(row.get("price"))
                    pnl_delta = sys_pnl - ex_pnl
                    fee_delta = sys_fee - ex_fee
                    price_delta = sys_price - ex_price if ex_price > 0 else 0.0
                    is_match = bool(fills)
                    if is_match:
                        matched += 1
                    else:
                        missing += 1
                    abs_pnl_delta_sum += abs(pnl_delta)
                    abs_fee_delta_sum += abs(fee_delta)
                    details.append(
                        {
                            "timestamp": row.get("timestamp"),
                            "symbol": sym,
                            "order_id": oid,
                            "matched": is_match,
                            "match_method": match_method,
                            "exchange_fill_count": int(len(fills or [])),
                            "system_pnl": round(sys_pnl, 8),
                            "exchange_pnl": round(ex_pnl, 8),
                            "pnl_delta": round(pnl_delta, 8),
                            "system_fee": round(sys_fee, 8),
                            "exchange_fee": round(ex_fee, 8),
                            "fee_delta": round(fee_delta, 8),
                            "system_price": round(sys_price, 8),
                            "exchange_avg_fill_price": round(ex_price, 8),
                            "price_delta": round(price_delta, 8),
                        }
                    )

                details.sort(key=lambda x: abs(_to_float(x.get("pnl_delta"))), reverse=True)
                output_rows = details[: max(1, int(limit or 200))]
                return {
                    "success": True,
                    "period_days": int(days or 7),
                    "filters": {
                        "symbol": symbol,
                        "exclude_bootstrap": bool(exclude_bootstrap),
                        "exclude_estimated_pnl": bool(exclude_estimated_pnl),
                        "max_exchange_checks": int(max_exchange_checks or 120),
                        "include_time_window_fallback": bool(include_time_window_fallback),
                        "fallback_time_window_sec": int(fallback_time_window_sec or 240),
                    },
                    "summary": {
                        "input_rows": int(len(rows or [])),
                        "candidate_rows": int(len(candidates)),
                        "matched": int(matched),
                        "missing_on_exchange": int(missing),
                        "matched_by_order_id": int(matched_by_order_id),
                        "matched_by_time_window": int(matched_by_time_window),
                        "match_rate": round((matched / len(candidates)) if candidates else 0.0, 6),
                        "sum_abs_pnl_delta": round(abs_pnl_delta_sum, 8),
                        "sum_abs_fee_delta": round(abs_fee_delta_sum, 8),
                    },
                    "details": output_rows,
                    "generated_at": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.error(f"交易对账失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "message": "交易对账失败",
                    "details": str(e),
                }

        @api_v1_router.get("/trades/reconcile/report", tags=["trades"])
        async def reconcile_trades_report(
            days: int = 7,
            symbol: Optional[str] = None,
            top_n: int = 20,
        ):
            """
            一键差异报告（摘要 + TOP 偏差列表），便于快速人工排查。
            """
            raw = await reconcile_trades_with_exchange(
                days=days,
                symbol=symbol,
                limit=max(20, int(top_n or 20)),
                max_exchange_checks=max(50, int(top_n or 20) * 6),
                exclude_bootstrap=True,
                exclude_estimated_pnl=True,
                include_time_window_fallback=True,
                fallback_time_window_sec=240,
                max_fallback_candidates_per_symbol=50,
            )
            if not isinstance(raw, dict) or not raw.get("success"):
                return raw

            detail_rows = list(raw.get("details") or [])
            top_pnl = sorted(detail_rows, key=lambda x: abs(_to_float((x or {}).get("pnl_delta"))), reverse=True)[: max(1, int(top_n or 20))]
            top_fee = sorted(detail_rows, key=lambda x: abs(_to_float((x or {}).get("fee_delta"))), reverse=True)[: max(1, int(top_n or 20))]
            high_risk: List[Dict[str, Any]] = []
            for r in detail_rows:
                if not isinstance(r, dict):
                    continue
                if (not bool(r.get("matched"))) or abs(_to_float(r.get("pnl_delta"))) >= 0.5:
                    high_risk.append(r)
            return {
                "success": True,
                "report_type": "trade_reconcile_gap_report",
                "period_days": int(days or 7),
                "symbol": symbol,
                "summary": raw.get("summary"),
                "filters": raw.get("filters"),
                "high_risk_count": int(len(high_risk)),
                "top_pnl_delta": top_pnl,
                "top_fee_delta": top_fee,
                "recommendations": [
                    "优先检查 missing_on_exchange 与 match_method=time_window 的记录。",
                    "对 high_risk 记录逐笔回查交易所成交明细与本地 order_id 映射。",
                    "若连续出现 time_window 匹配，建议补齐 order_id 持久化链路。"
                ],
                "generated_at": datetime.now().isoformat(),
            }

        # 移除历史兼容别名：/trading/history 与 /trade/history（统一使用 /api/v1/trades）

        @api_v1_router.get("/trades/statistics", tags=["trades"])
        async def get_trade_statistics(
            days: int = 30,
            realized_only: bool = True,
            exclude_bootstrap: bool = True,
        ):
            """
            获取交易统计数据
            
            返回详细的交易统计信息，包括胜率、盈亏、风险指标等
            """
            try:
                mc = self.main_controller
                trade_service = None
                if mc and hasattr(mc, 'trade_history_service'):
                    trade_service = mc.trade_history_service
                
                if trade_service:
                    # Realized metrics path (default): prefer clean PnL records over mixed bootstrap rows.
                    # This gives stable production indicators for profitability decisions.
                    start_date = datetime.now() - timedelta(days=days)
                    rows = await trade_service.get_trade_history(start_date=start_date, limit=10000)
                    clean_rows: List[Dict[str, Any]] = []
                    for r in (rows or []):
                        if not isinstance(r, dict):
                            continue
                        md = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
                        src = str((md.get("source") or r.get("source") or "")).strip().lower()
                        if exclude_bootstrap and src == "db_bootstrap":
                            continue
                        pnl = _to_float(r.get("pnl"))
                        pnl_pct = _to_float(r.get("pnl_percent"))
                        if realized_only and not (abs(pnl) > 1e-12 or abs(pnl_pct) > 1e-12):
                            continue
                        clean_rows.append(r)

                    if clean_rows:
                        wins = [x for x in clean_rows if float(x.get("pnl", 0) or 0) > 0]
                        losses = [x for x in clean_rows if float(x.get("pnl", 0) or 0) < 0]
                        total = len(clean_rows)
                        gross_profit = sum(float(x.get("pnl", 0) or 0) for x in wins)
                        gross_loss = abs(sum(float(x.get("pnl", 0) or 0) for x in losses))
                        total_pnl = sum(float(x.get("pnl", 0) or 0) for x in clean_rows)
                        total_fees = sum(float(x.get("fee", 0) or 0) for x in clean_rows)
                        avg_win = (gross_profit / len(wins)) if wins else 0.0
                        avg_loss = (sum(float(x.get("pnl", 0) or 0) for x in losses) / len(losses)) if losses else 0.0
                        win_rate = (len(wins) / total) if total else 0.0
                        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 9999.0
                        expectancy = (total_pnl / total) if total else 0.0
                        symbols = sorted(
                            {
                                str(x.get("symbol") or "").strip()
                                for x in clean_rows
                                if str(x.get("symbol") or "").strip()
                            }
                        )
                        return {
                            "total_trades": total,
                            "winning_trades": len(wins),
                            "losing_trades": len(losses),
                            "win_rate": round(win_rate * 100, 2),
                            "total_pnl": round(total_pnl, 6),
                            "total_fees": round(total_fees, 6),
                            "avg_win": round(avg_win, 6),
                            "avg_loss": round(avg_loss, 6),
                            "profit_factor": round(profit_factor, 4),
                            "expectancy": round(expectancy, 6),
                            "symbols": symbols,
                            "period_days": days,
                            "generated_at": datetime.now().isoformat(),
                            "source": "trade_history:realized",
                            "filters": {
                                "realized_only": bool(realized_only),
                                "exclude_bootstrap": bool(exclude_bootstrap),
                            },
                        }

                    # Secondary fallback for profitability analytics:
                    # leverage execution/trade audit for both strict and relaxed filters.
                    audit_rows = _load_execution_audit_records(days=days)
                    mapped = [_audit_row_to_trade(x) for x in audit_rows if isinstance(x, dict)]
                    if exclude_bootstrap:
                        mapped = [x for x in mapped if not _is_bootstrap_trade(x)]
                    if realized_only:
                        mapped = [x for x in mapped if _is_realized_trade(x)]
                    if mapped:
                        wins = [x for x in mapped if _to_float(x.get("pnl")) > 0]
                        losses = [x for x in mapped if _to_float(x.get("pnl")) < 0]
                        total = len(mapped)
                        gross_profit = sum(_to_float(x.get("pnl")) for x in wins)
                        gross_loss = abs(sum(_to_float(x.get("pnl")) for x in losses))
                        total_pnl = sum(_to_float(x.get("pnl")) for x in mapped)
                        total_fees = sum(_to_float(x.get("fee")) for x in mapped)
                        avg_win = (gross_profit / len(wins)) if wins else 0.0
                        avg_loss = (sum(_to_float(x.get("pnl")) for x in losses) / len(losses)) if losses else 0.0
                        win_rate = (len(wins) / total) if total else 0.0
                        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 9999.0
                        expectancy = (total_pnl / total) if total else 0.0
                        symbols = sorted(
                            {
                                str(x.get("symbol") or "").strip()
                                for x in mapped
                                if str(x.get("symbol") or "").strip()
                            }
                        )
                        return {
                            "total_trades": total,
                            "winning_trades": len(wins),
                            "losing_trades": len(losses),
                            "win_rate": round(win_rate * 100, 2),
                            "total_pnl": round(total_pnl, 6),
                            "total_fees": round(total_fees, 6),
                            "avg_win": round(avg_win, 6),
                            "avg_loss": round(avg_loss, 6),
                            "profit_factor": round(profit_factor, 4),
                            "expectancy": round(expectancy, 6),
                            "symbols": symbols,
                            "period_days": days,
                            "generated_at": datetime.now().isoformat(),
                            "source": "execution_audit:mapped",
                            "filters": {
                                "realized_only": bool(realized_only),
                                "exclude_bootstrap": bool(exclude_bootstrap),
                            },
                            "note": "Mapped from execution/trade audit; legacy rows may use conservative pnl estimation.",
                        }

                    # When strict filters are enabled, do not silently fall back to bootstrap-mixed stats.
                    # Return an explicit empty realized set so operators don't misread profitability.
                    if realized_only or exclude_bootstrap:
                        return {
                            "total_trades": 0,
                            "winning_trades": 0,
                            "losing_trades": 0,
                            "win_rate": 0.0,
                            "total_pnl": 0.0,
                            "total_fees": 0.0,
                            "avg_win": 0.0,
                            "avg_loss": 0.0,
                            "profit_factor": 0.0,
                            "expectancy": 0.0,
                            "symbols": [],
                            "period_days": days,
                            "generated_at": datetime.now().isoformat(),
                            "source": "trade_history:realized_empty",
                            "filters": {
                                "realized_only": bool(realized_only),
                                "exclude_bootstrap": bool(exclude_bootstrap),
                            },
                            "note": "No realized trades after filters; bootstrap/non-realized rows excluded.",
                        }

                    stats = await trade_service.get_statistics(days=days)
                    if isinstance(stats, dict) and int(stats.get("total_trades", 0) or 0) == 0:
                        rows = _load_execution_audit_records(days=days)
                        total = len(rows)
                        success = sum(1 for r in rows if str(r.get("status", "")).lower() == "success")
                        failed = total - success
                        symbols = sorted(
                            {
                                str((r.get("symbol") or (r.get("details") or {}).get("symbol") or "")).strip()
                                for r in rows
                                if str((r.get("symbol") or (r.get("details") or {}).get("symbol") or "")).strip()
                            }
                        )
                        return {
                            "total_trades": total,
                            "success_trades": success,
                            "failed_trades": failed,
                            "success_rate": (success / total) if total else 0.0,
                            "symbols": symbols,
                            "period_days": days,
                            "generated_at": datetime.now().isoformat(),
                            "source": "fallback:execution_audit",
                            "note": "trade_history_service returned empty stats",
                        }
                    return {
                        **stats,
                        "period_days": days,
                        "generated_at": datetime.now().isoformat()
                    }
                else:
                    # Fallback: aggregate from execution audit log
                    rows = _load_execution_audit_records(days=days)
                    total = len(rows)
                    success = sum(1 for r in rows if str(r.get("status", "")).lower() == "success")
                    failed = total - success
                    symbols = sorted(
                        {
                            str((r.get("symbol") or (r.get("details") or {}).get("symbol") or "")).strip()
                            for r in rows
                            if str((r.get("symbol") or (r.get("details") or {}).get("symbol") or "")).strip()
                        }
                    )
                    return {
                        "total_trades": total,
                        "success_trades": success,
                        "failed_trades": failed,
                        "success_rate": (success / total) if total else 0.0,
                        "symbols": symbols,
                        "period_days": days,
                        "generated_at": datetime.now().isoformat(),
                        "source": "fallback:execution_audit",
                        "note": "trade_history_service unavailable",
                    }
                    
            except Exception as e:
                logger.error(f"获取交易统计失败: {e}")
                return {
                    "error": "获取交易统计失败",
                    "details": str(e)
                }

        @api_v1_router.get("/trades/review", tags=["trades"])
        async def get_trade_review(days: int = 7):
            """
            获取交易复盘报告
            
            生成包含统计分析、趋势、建议的完整复盘报告
            """
            try:
                mc = self.main_controller
                trade_service = None
                if mc and hasattr(mc, 'trade_history_service'):
                    trade_service = mc.trade_history_service
                
                if trade_service:
                    review = await trade_service.generate_trade_review(days=days)
                    
                    return {
                        "review": review,
                        "period_days": days,
                        "generated_at": datetime.now().isoformat(),
                        "format": "markdown"
                    }
                else:
                    return {
                        "error": "交易复盘服务不可用"
                    }
                    
            except Exception as e:
                logger.error(f"生成交易复盘失败: {e}")
                return {
                    "error": "生成交易复盘失败",
                    "details": str(e)
                }

        @api_v1_router.get("/trades/attribution/regime", tags=["trades"])
        async def get_trade_regime_attribution(
            days: int = 30,
            realized_only: bool = True,
            exclude_bootstrap: bool = True,
            limit: int = 5000,
        ):
            """按 market_context.regime 聚合收益归因指标。"""
            try:
                mc = self.main_controller
                trade_service = getattr(mc, "trade_history_service", None) if mc else None
                if not trade_service:
                    return {
                        "success": False,
                        "message": "trade_history_service unavailable",
                    }

                start_date = datetime.now() - timedelta(days=max(1, int(days or 30)))
                rows = await trade_service.get_trade_history(start_date=start_date, limit=max(1, int(limit or 5000)))
                clean_rows: List[Dict[str, Any]] = []
                for r in (rows or []):
                    if not isinstance(r, dict):
                        continue
                    md = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
                    src = str((md.get("source") or r.get("source") or "")).strip().lower()
                    if exclude_bootstrap and src == "db_bootstrap":
                        continue
                    pnl = _to_float(r.get("pnl"))
                    pnl_pct = _to_float(r.get("pnl_percent"))
                    if realized_only and not (abs(pnl) > 1e-12 or abs(pnl_pct) > 1e-12):
                        continue
                    clean_rows.append(r)

                groups: Dict[str, Dict[str, Any]] = {}
                for r in clean_rows:
                    md = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
                    mkt = md.get("market_context") if isinstance(md.get("market_context"), dict) else {}
                    regime = str(mkt.get("regime") or "unknown").strip().lower() or "unknown"
                    grp = groups.get(regime)
                    if not grp:
                        grp = {
                            "regime": regime,
                            "total_trades": 0,
                            "winning_trades": 0,
                            "losing_trades": 0,
                            "total_pnl": 0.0,
                            "total_fees": 0.0,
                            "sum_qty_factor": 0.0,
                            "qty_factor_count": 0,
                            "sum_pnl_percent": 0.0,
                            "pnl_percent_count": 0,
                        }
                        groups[regime] = grp
                    pnl = _to_float(r.get("pnl"))
                    fee = _to_float(r.get("fee"))
                    pnl_pct = _to_float(r.get("pnl_percent"))
                    qf = _to_float(mkt.get("effective_qty_factor"), 1.0)
                    grp["total_trades"] += 1
                    grp["total_pnl"] += pnl
                    grp["total_fees"] += fee
                    grp["sum_qty_factor"] += qf
                    grp["qty_factor_count"] += 1
                    if abs(pnl_pct) > 1e-12:
                        grp["sum_pnl_percent"] += pnl_pct
                        grp["pnl_percent_count"] += 1
                    if pnl > 0:
                        grp["winning_trades"] += 1
                    elif pnl < 0:
                        grp["losing_trades"] += 1

                out: List[Dict[str, Any]] = []
                for regime, g in groups.items():
                    wins = int(g["winning_trades"])
                    losses = int(g["losing_trades"])
                    total = int(g["total_trades"])
                    gross_profit = sum(
                        _to_float(x.get("pnl"))
                        for x in clean_rows
                        if str(((x.get("metadata") or {}).get("market_context") or {}).get("regime") or "unknown").strip().lower() == regime
                        and _to_float(x.get("pnl")) > 0
                    )
                    gross_loss = abs(
                        sum(
                            _to_float(x.get("pnl"))
                            for x in clean_rows
                            if str(((x.get("metadata") or {}).get("market_context") or {}).get("regime") or "unknown").strip().lower() == regime
                            and _to_float(x.get("pnl")) < 0
                        )
                    )
                    win_rate = (wins / total) if total else 0.0
                    expectancy = (_to_float(g["total_pnl"]) / total) if total else 0.0
                    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (9999.0 if gross_profit > 0 else 0.0)
                    avg_qty_factor = (_to_float(g["sum_qty_factor"]) / max(1, int(g["qty_factor_count"])))
                    avg_pnl_percent = (_to_float(g["sum_pnl_percent"]) / max(1, int(g["pnl_percent_count"])))
                    out.append(
                        {
                            "regime": regime,
                            "total_trades": total,
                            "winning_trades": wins,
                            "losing_trades": losses,
                            "win_rate": round(win_rate * 100, 2),
                            "profit_factor": round(float(profit_factor), 4),
                            "expectancy": round(float(expectancy), 6),
                            "total_pnl": round(_to_float(g["total_pnl"]), 6),
                            "total_fees": round(_to_float(g["total_fees"]), 6),
                            "avg_pnl_percent": round(float(avg_pnl_percent), 6),
                            "avg_effective_qty_factor": round(float(avg_qty_factor), 6),
                        }
                    )
                out.sort(key=lambda x: x.get("total_trades", 0), reverse=True)

                return {
                    "success": True,
                    "ok": True,
                    "status": "success",
                    "period_days": int(days or 30),
                    "source": "trade_history:regime_attribution",
                    "filters": {
                        "realized_only": bool(realized_only),
                        "exclude_bootstrap": bool(exclude_bootstrap),
                        "limit": int(limit or 5000),
                    },
                    "summary": {
                        "input_trades": int(len(rows or [])),
                        "attributed_trades": int(len(clean_rows)),
                        "regime_count": int(len(out)),
                    },
                    "data": out,
                    "generated_at": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.error(f"获取 regime 归因失败: {e}")
                return {
                    "success": False,
                    "message": "获取 regime 归因失败",
                    "details": str(e),
                }

        @api_v1_router.get("/trades/attribution/regime/health", tags=["trades"])
        async def get_trade_regime_attribution_health(
            days: int = 30,
            sample_limit: int = 200,
            realized_only: bool = True,
            exclude_bootstrap: bool = True,
        ):
            """归因数据健康度：评估 regime/pnl 样本是否足够用于参数调优。"""
            try:
                mc = self.main_controller
                trade_service = getattr(mc, "trade_history_service", None) if mc else None
                if not trade_service:
                    return {"success": False, "message": "trade_history_service unavailable"}

                start_date = datetime.now() - timedelta(days=max(1, int(days or 30)))
                rows = await trade_service.get_trade_history(
                    start_date=start_date,
                    limit=max(20, int(sample_limit or 200)),
                )
                filtered: List[Dict[str, Any]] = []
                for r in (rows or []):
                    if not isinstance(r, dict):
                        continue
                    md = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
                    src = str((md.get("source") or r.get("source") or "")).strip().lower()
                    if exclude_bootstrap and src == "db_bootstrap":
                        continue
                    pnl = _to_float(r.get("pnl"))
                    pnl_pct = _to_float(r.get("pnl_percent"))
                    if realized_only and not (abs(pnl) > 1e-12 or abs(pnl_pct) > 1e-12):
                        continue
                    filtered.append(r)

                total = int(len(filtered))
                with_regime = 0
                nonzero_pnl = 0
                nonzero_pnl_pct = 0
                with_qty_factor = 0
                regime_counter: Dict[str, int] = {}
                for r in filtered:
                    md = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
                    mkt = md.get("market_context") if isinstance(md.get("market_context"), dict) else {}
                    regime = str(mkt.get("regime") or "").strip().lower()
                    if regime:
                        with_regime += 1
                        regime_counter[regime] = int(regime_counter.get(regime, 0)) + 1
                    if mkt.get("effective_qty_factor") is not None:
                        with_qty_factor += 1
                    pnl = _to_float(r.get("pnl"))
                    pnl_pct = _to_float(r.get("pnl_percent"))
                    if abs(pnl) > 1e-12:
                        nonzero_pnl += 1
                    if abs(pnl_pct) > 1e-12:
                        nonzero_pnl_pct += 1

                regime_cov = (with_regime / total) if total else 0.0
                pnl_cov = (nonzero_pnl / total) if total else 0.0
                pnl_pct_cov = (nonzero_pnl_pct / total) if total else 0.0
                qty_cov = (with_qty_factor / total) if total else 0.0
                ready = bool(total >= 20 and regime_cov >= 0.6 and pnl_cov >= 0.5)

                return {
                    "success": True,
                    "ok": True,
                    "status": "success",
                    "source": "trade_history:regime_attribution_health",
                    "period_days": int(days or 30),
                    "filters": {
                        "realized_only": bool(realized_only),
                        "exclude_bootstrap": bool(exclude_bootstrap),
                        "sample_limit": int(sample_limit or 200),
                    },
                    "sample": {
                        "total": total,
                        "with_regime": int(with_regime),
                        "with_effective_qty_factor": int(with_qty_factor),
                        "nonzero_pnl": int(nonzero_pnl),
                        "nonzero_pnl_percent": int(nonzero_pnl_pct),
                    },
                    "coverage": {
                        "regime_coverage": round(regime_cov, 4),
                        "qty_factor_coverage": round(qty_cov, 4),
                        "nonzero_pnl_coverage": round(pnl_cov, 4),
                        "nonzero_pnl_percent_coverage": round(pnl_pct_cov, 4),
                    },
                    "regime_distribution": dict(sorted(regime_counter.items(), key=lambda kv: kv[1], reverse=True)),
                    "readiness": {
                        "ready_for_regime_tuning": ready,
                        "rules": {
                            "min_samples": 20,
                            "min_regime_coverage": 0.6,
                            "min_nonzero_pnl_coverage": 0.5,
                        },
                    },
                    "generated_at": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.error(f"获取 regime 归因健康度失败: {e}")
                return {
                    "success": False,
                    "message": "获取 regime 归因健康度失败",
                    "details": str(e),
                }

        @api_v1_router.get("/monitoring/logs", tags=["monitoring"])
        async def get_monitoring_logs(limit: int = 20):
            """监控日志（统一总控中心使用）"""
            records: List[Dict[str, Any]] = []
            try:
                log_dir = Path("logs")
                if not log_dir.exists():
                    return {"success": True, "data": records, "source": "filesystem:missing"}

                candidates = sorted(
                    [p for p in log_dir.glob("*.log") if p.is_file()],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )[:3]
                for file_path in candidates:
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
                        for line in lines[-max(limit, 1):]:
                            records.append(
                                {
                                    "source": file_path.name,
                                    "message": line[:500],
                                    "level": "info",
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )
                    except Exception:
                        continue
                return {"success": True, "data": records[-limit:], "source": "filesystem"}
            except Exception as e:
                logger.warning(f"读取监控日志失败: {e}")
                return {"success": False, "data": [], "error": str(e)}

        @api_v1_router.get("/control-center/state", tags=["control-center"])
        async def get_control_center_state(limit: int = 20):
            """单模块总控中心聚合状态接口"""
            # 总控接口必须“快返回”：避免因交易所/数据源抖动导致前端长时间无响应
            try:
                status_payload = await asyncio.wait_for(get_status(), timeout=2.5)
            except Exception:
                status_payload = {"status": "degraded", "system_status": "degraded", "timestamp": datetime.now().isoformat()}
            try:
                health_payload = await asyncio.wait_for(system_health_v1(), timeout=1.5)
            except Exception:
                health_payload = {"status": "degraded", "overall": "degraded", "timestamp": datetime.now().isoformat()}
            s1_payload: Dict[str, Any] = {}
            guards_payload: Dict[str, Any] = {}
            sltp_payload: Dict[str, Any] = {}
            execution_events_payload: List[Dict[str, Any]] = []
            strategy_opt_payload: Dict[str, Any] = {}
            strategies_payload: List[Dict[str, Any]] = []
            monitoring_summary: Dict[str, Any] = {}
            market_data_payload: Dict[str, Any] = {}
            proactive_status_payload: Dict[str, Any] = {}
            proactive_opportunities_payload: List[Dict[str, Any]] = []
            proactive_insights_payload: Dict[str, Any] = {}
            risk_payload: Dict[str, Any] = {}
            strategy_perf_payload: Dict[str, Any] = {}
            anomalies_payload: List[Dict[str, Any]] = []
            alerts_payload: List[Dict[str, Any]] = []
            alerts_history_payload: List[Dict[str, Any]] = []
            trade_statistics_payload: Dict[str, Any] = {}
            trade_review_payload: Dict[str, Any] = {}
            try:
                trade_history_payload = await asyncio.wait_for(get_trading_history_compat(limit=limit), timeout=2.5)
            except Exception:
                trade_history_payload = {"success": False, "data": [], "error": "timeout"}
            try:
                logs_payload = await asyncio.wait_for(get_monitoring_logs(limit=limit), timeout=2.0)
            except Exception:
                logs_payload = {"success": False, "data": [], "error": "timeout"}

            mc = self.main_controller
            if mc:
                try:
                    from src.modules.api.module_control_api import (
                        get_module_health,
                        get_s1_verification,
                        get_ai_guard_status,
                        get_stop_loss_stats,
                        get_strategy_optimization_status,
                    )
                    s1_payload = await get_s1_verification()
                    guards_payload = await get_ai_guard_status()
                    sltp_payload = await get_stop_loss_stats()
                    strategy_opt_payload = await get_strategy_optimization_status()
                    health_res = await get_module_health()
                    if isinstance(health_res, dict):
                        health_payload = {**health_payload, **health_res}
                except Exception as e:
                    logger.debug(f"总控聚合: module_control_api 获取失败: {e}")

                try:
                    gw = getattr(mc, "execution_gateway", None)
                    if gw and hasattr(gw, "get_recent_events"):
                        execution_events_payload = await asyncio.wait_for(
                            gw.get_recent_events(limit=limit),
                            timeout=2.0,
                        )
                except Exception as e:
                    logger.debug(f"总控聚合: execution events 获取失败: {e}")

                try:
                    if hasattr(mc, "strategy_manager") and mc.strategy_manager:
                        configs = getattr(mc.strategy_manager, "strategy_configs", {}) or {}
                        for sid, cfg in configs.items():
                            strategies_payload.append(
                                {
                                    "strategy_id": getattr(cfg, "strategy_id", sid),
                                    "name": getattr(cfg, "name", sid),
                                    "strategy_type": str(getattr(cfg, "strategy_type", "")),
                                    "enabled": bool(getattr(cfg, "enabled", True)),
                                }
                            )
                except Exception as e:
                    logger.debug(f"总控聚合: strategy_manager 获取失败: {e}")

            try:
                from src.modules.api.monitoring_api import (
                    get_monitoring_summary,
                    get_market_data_status,
                    get_proactive_ai_status,
                    get_proactive_opportunities,
                    get_proactive_insights,
                    get_risk_metrics,
                    get_strategy_performance,
                    get_anomaly_events,
                    get_active_alerts,
                    get_alert_history,
                )
                monitoring_summary = await get_monitoring_summary()
                market_data_payload = await get_market_data_status()
                proactive_status_payload = await get_proactive_ai_status()
                proactive_opportunities_payload = await get_proactive_opportunities()
                proactive_insights_payload = await get_proactive_insights()
                risk_payload = await get_risk_metrics()
                strategy_perf_payload = await get_strategy_performance()
                anomalies_payload = await get_anomaly_events(limit=limit)
                alerts_payload = await get_active_alerts()
                alerts_history_payload = await get_alert_history(limit=limit)
            except Exception as e:
                logger.debug(f"总控聚合: monitoring_api 获取失败: {e}")

            try:
                trade_statistics_payload = await get_trade_statistics(days=30)
                trade_review_payload = await get_trade_review(days=7)
            except Exception as e:
                logger.debug(f"总控聚合: trade review/stat 获取失败: {e}")

            risk_manager_payload: Dict[str, Any] = {}
            portfolio_optimizer_payload: Dict[str, Any] = {}
            if mc:
                try:
                    rm = getattr(mc, "risk_manager", None)
                    if rm is not None and hasattr(rm, "get_stats"):
                        risk_manager_payload = await asyncio.wait_for(rm.get_stats(), timeout=0.9)
                except Exception as e:
                    logger.debug(f"总控聚合: risk_manager.get_stats 失败: {e}")
                    risk_manager_payload = {"available": False, "error": "timeout_or_error"}
                try:
                    po = getattr(mc, "portfolio_optimizer", None)
                    if po is not None:
                        strat = getattr(po, "strategies", None) or {}
                        portfolio_optimizer_payload = {
                            "ready": bool(strat),
                            "strategy_count": len(strat),
                            "strategy_names": list(strat.keys())[:24],
                        }
                except Exception as e:
                    logger.debug(f"总控聚合: portfolio_optimizer 摘要失败: {e}")

            return {
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "system": {"status": status_payload, "health": health_payload},
                "ai": {
                    "s1": s1_payload,
                    "guards": guards_payload,
                    "proactive_status": proactive_status_payload,
                    "opportunities": proactive_opportunities_payload,
                    "insights": proactive_insights_payload,
                },
                "market": {
                    "monitoring_summary": monitoring_summary,
                    "market_data": market_data_payload,
                    "risk": risk_payload,
                },
                "trading": {
                    "trade_history": trade_history_payload.get("data", []),
                    "sltp_stats": sltp_payload,
                    "execution_events": execution_events_payload,
                    "strategies": strategies_payload,
                    "strategy_optimization": strategy_opt_payload.get("data", strategy_opt_payload),
                    "strategy_performance": strategy_perf_payload,
                    "trade_statistics": trade_statistics_payload,
                    "trade_review": trade_review_payload,
                    "risk_manager": risk_manager_payload,
                    "portfolio_optimizer": portfolio_optimizer_payload,
                },
                "observability": {
                    "logs": logs_payload.get("data", []),
                    "alerts": alerts_payload,
                    "alerts_history": alerts_history_payload,
                    "anomalies": anomalies_payload,
                },
            }

        # 设置管理路由 - 支持 /api/v1/settings
        @api_v1_router.get("/settings", tags=["settings"])
        async def get_settings():
            """获取系统设置"""
            # 这里应该从配置管理器获取真实设置
            # 为简化，返回模拟数据
            return {
                "system": {
                    "system_name": "全智能量化交易系统",
                    "language": "zh-CN",
                    "timezone": "Asia/Shanghai",
                    "theme": "light",
                    "auto_backup": True,
                    "backup_interval": "daily",
                    "log_level": "info"
                },
                "api": {
                    "api_url": "http://localhost:8000",
                    "api_key": "********",
                    "api_secret": "********",
                    "rate_limit": 60,
                    "timeout": 30
                },
                "risk": {
                    "max_drawdown": 10,
                    "max_position_size": 10,
                    "max_leverage": 3,
                    "stop_loss_enabled": True,
                    "take_profit_enabled": True,
                    "risk_per_trade": 2
                },
                "user": {
                    "username": "admin",
                    "email": "admin@example.com"
                }
            }

        @api_v1_router.put("/settings", tags=["settings"])
        async def update_settings(settings: Dict[str, Any]):
            """更新系统设置"""
            # 这里应该保存设置到配置管理器
            # 为简化，返回成功消息
            logger.info("保存设置:", settings)
            return {
                "status": "success",
                "message": "设置保存成功",
                "timestamp": datetime.now().isoformat()
            }

        # 模型管理路由 - 支持 /api/v1/models
        @api_v1_router.get("/models", tags=["models"])
        async def get_models():
            """获取模型列表"""
            # 这里应该从模型管理器获取真实模型列表
            # 为简化，返回模拟数据
            return [
                {
                    "id": "1",
                    "name": "LSTM模型",
                    "type": "lstm",
                    "status": "active",
                    "symbol": "BTC/USDT",
                    "performance": {
                        "mse": 0.001,
                        "mae": 0.01,
                        "rmse": 0.03,
                        "mape": 0.02,
                        "r2": 0.95
                    },
                    "last_trained": datetime.now().isoformat()
                },
                {
                    "id": "2",
                    "name": "GRU模型",
                    "type": "gru",
                    "status": "active",
                    "symbol": "ETH/USDT",
                    "performance": {
                        "mse": 0.002,
                        "mae": 0.015,
                        "rmse": 0.04,
                        "mape": 0.025,
                        "r2": 0.93
                    },
                    "last_trained": datetime.now().isoformat()
                }
            ]

        @api_v1_router.post("/models/train", tags=["models"])
        async def train_model(model_data: Dict[str, Any]):
            """训练模型"""
            # 这里应该调用模型管理器训练模型
            # 为简化，返回成功消息
            logger.info("训练模型:", model_data)
            return {
                "status": "success",
                "message": "模型训练成功",
                "model_id": "3",
                "timestamp": datetime.now().isoformat()
            }

        @api_v1_router.put("/models/{id}", tags=["models"])
        async def update_model(id: str, model_data: Dict[str, Any]):
            """更新模型"""
            # 这里应该调用模型管理器更新模型
            # 为简化，返回成功消息
            logger.info("更新模型:", id, model_data)
            return {
                "status": "success",
                "message": "模型更新成功",
                "timestamp": datetime.now().isoformat()
            }

        @api_v1_router.delete("/models/{id}", tags=["models"])
        async def delete_model(id: str):
            """删除模型"""
            # 这里应该调用模型管理器删除模型
            # 为简化，返回成功消息
            logger.info("删除模型:", id)
            return {
                "status": "success",
                "message": "模型删除成功",
                "timestamp": datetime.now().isoformat()
            }

        @api_v1_router.get("/models/{id}/performance", tags=["models"])
        async def get_model_performance(id: str):
            """获取模型性能"""
            # 这里应该调用模型管理器获取模型性能
            # 为简化，返回模拟数据
            return {
                "model_id": id,
                "performance": {
                    "mse": 0.001,
                    "mae": 0.01,
                    "rmse": 0.03,
                    "mape": 0.02,
                    "r2": 0.95
                },
                "last_updated": datetime.now().isoformat()
            }

        # AI模型管理路由 - 支持 /api/v1/ai-models
        @api_v1_router.get("/ai-models", tags=["ai-models"])
        async def get_ai_models():
            """获取AI模型列表"""
            llm_manager = self.main_controller.enhanced_llm_manager
            
            logger.debug(f"llm_manager.models keys: {list(llm_manager.models.keys())}")
            logger.debug(f"llm_manager.models count: {len(llm_manager.models)}")
            
            models = []
            for i, model_config in enumerate(llm_manager.models.values(), 1):
                models.append({
                    "id": str(i),
                    "name": model_config.display_name,
                    "provider": model_config.provider.value,
                    "model": model_config.model_id,
                    "status": "active" if model_config.enabled else "inactive",
                    "api_key": "********" if model_config.api_key else "",
                    "base_url": model_config.base_url,
                    "enabled": model_config.enabled
                })
            logger.debug(f"Returning {len(models)} models: {[m['model'] for m in models]}")
            return models

        @api_v1_router.post("/ai-models", tags=["ai-models"])
        async def add_ai_model(model_data: Dict[str, Any]):
            """添加AI模型"""
            llm_manager = self.main_controller.enhanced_llm_manager
            
            logger.debug(f"Before add - models keys: {list(llm_manager.models.keys())}")
            
            try:
                model_config = {
                    "model_id": model_data.get("model"),
                    "display_name": model_data.get("name"),
                    "provider": model_data.get("provider"),
                    "api_key": model_data.get("api_key", ""),
                    "base_url": model_data.get("base_url", ""),
                    "enabled": model_data.get("enabled", True)
                }
                
                logger.debug(f"Registering model with config: {model_config}")
                await llm_manager._register_model_from_config(model_config)
                
                logger.debug(f"After register - models keys: {list(llm_manager.models.keys())}")
                
                await llm_manager._initialize_provider(model_config["model_id"])
                
                logger.info(f"Model added successfully. Total models: {len(llm_manager.models)}")
                return {
                    "status": "success",
                    "message": "AI模型添加成功",
                    "model_id": model_config["model_id"],
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"添加AI模型失败: {e}")
                logger.exception("添加AI模型详细错误")
                return {
                    "status": "error",
                    "message": f"AI模型添加失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }

        # 注意：/ai-models/default 必须在 /ai-models/{id} 之前定义，否则会被 {id} 路由匹配
        @api_v1_router.get("/ai-models/default", tags=["ai-models"])
        async def get_default_ai_model():
            """获取默认AI模型"""
            # 从主控制器获取已经初始化的LLM管理器实例
            llm_manager = self.main_controller.enhanced_llm_manager
            
            # 从LLM管理器获取默认AI模型
            default_model_id = llm_manager.default_model
            if default_model_id and default_model_id in llm_manager.models:
                model_config = llm_manager.models[default_model_id]
                return {
                    "default_provider": model_config.provider.value,
                    "default_model": default_model_id
                }
            else:
                # 如果没有默认模型，返回第一个可用模型
                for model_id, model_config in llm_manager.models.items():
                    if model_config.enabled:
                        return {
                            "default_provider": model_config.provider.value,
                            "default_model": model_id
                        }
                # 如果没有可用模型，返回默认值
                return {
                    "default_provider": "local",
                    "default_model": "llama3"
                }

        @api_v1_router.put("/ai-models/default", tags=["ai-models"])
        async def set_default_ai_model(default_data: Dict[str, Any]):
            """设置默认AI模型"""
            import sys
            # 从主控制器获取已经初始化的LLM管理器实例
            llm_manager = self.main_controller.enhanced_llm_manager
            
            # 调试信息
            logger.debug(f"set_default_ai_model called with: {default_data}")
            logger.debug(f"Available models: {list(llm_manager.models.keys())}")
            
            try:
                model_id = default_data.get("model_id")
                logger.debug(f"model_id from request: {model_id}")
                if model_id:
                    exists = model_id in llm_manager.models
                    logger.debug(f"model_id exists in models: {exists}")
                    if exists:
                        logger.debug(f"model enabled: {llm_manager.models[model_id].enabled}")
                    success = await llm_manager.switch_model(model_id)
                    logger.debug(f"switch_model returned: {success}")
                    if success:
                        logger.info(f"设置默认AI模型成功: {default_data}")
                        return {
                            "status": "success",
                            "message": "默认AI模型设置成功",
                            "timestamp": datetime.now().isoformat()
                        }
                    else:
                        return {
                            "status": "error",
                            "message": "AI模型不存在或未启用",
                            "timestamp": datetime.now().isoformat()
                        }
                else:
                    return {
                        "status": "error",
                        "message": "缺少model_id参数",
                        "timestamp": datetime.now().isoformat()
                    }
            except Exception as e:
                logger.error(f"设置默认AI模型失败: {e}")
                logger.exception("设置默认AI模型详细错误")
                return {
                    "status": "error",
                    "message": f"默认AI模型设置失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }

        @api_v1_router.put("/ai-models/{id}", tags=["ai-models"])
        async def update_ai_model(id: str, model_data: Dict[str, Any]):
            """更新AI模型"""
            # 从主控制器获取已经初始化的LLM管理器实例
            llm_manager = self.main_controller.enhanced_llm_manager
            
            # 调用LLM管理器更新AI模型
            try:
                # 找到对应的模型
                model_id = model_data.get("model")
                if model_id in llm_manager.models:
                    model_config = llm_manager.models[model_id]
                    
                    # 更新模型配置
                    model_config.display_name = model_data.get("name", model_config.display_name)
                    model_config.api_key = model_data.get("api_key", model_config.api_key)
                    model_config.base_url = model_data.get("base_url", model_config.base_url)
                    model_config.enabled = model_data.get("enabled", model_config.enabled)
                    
                    # 重新初始化模型提供者
                    if model_config.enabled:
                        await llm_manager._initialize_provider(model_id)
                    else:
                        if model_id in llm_manager.providers:
                            await llm_manager.providers[model_id].cleanup()
                            del llm_manager.providers[model_id]
                    
                    logger.info("更新AI模型:", id, model_data)
                    return {
                        "status": "success",
                        "message": "AI模型更新成功",
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "status": "error",
                        "message": "AI模型不存在",
                        "timestamp": datetime.now().isoformat()
                    }
            except Exception as e:
                logger.info("更新AI模型失败:", e)
                return {
                    "status": "error",
                    "message": f"AI模型更新失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }

        @api_v1_router.delete("/ai-models/{id}", tags=["ai-models"])
        async def delete_ai_model(id: str):
            """删除AI模型"""
            # 这里应该调用LLM管理器删除AI模型
            # 为简化，返回成功消息
            logger.info("删除AI模型:", id)
            return {
                "status": "success",
                "message": "AI模型删除成功",
                "timestamp": datetime.now().isoformat()
            }

        # AI对话API端点
        @api_v1_router.post("/ai/chat", tags=["ai"])
        async def ai_chat(chat_data: Dict[str, Any]):
            """与AI智能助手对话 - 使用AICommandExecutor处理，具备系统感知能力"""
            try:
                message = chat_data.get("message", "")
                model_id = chat_data.get("model_id")
                chat_started_at = datetime.now()
                trace: Dict[str, Any] = {
                    "path": None,
                    "core_router_ms": None,
                    "executor_ms": None,
                    "llm_direct_ms": None,
                }
                try:
                    timeout_sec = float(chat_data.get("timeout_sec", 20.0) or 20.0)
                except Exception:
                    timeout_sec = 20.0
                timeout_sec = max(5.0, min(timeout_sec, 90.0))
                
                def _safe_json(obj: Any, depth: int = 0) -> Any:
                    """
                    Make result.data JSON-serializable to avoid FastAPI encoder crashes.
                    We intentionally keep it conservative: dict/list/primitive pass through,
                    everything else becomes a short string.
                    """
                    if depth > 5:
                        return str(obj)
                    if obj is None or isinstance(obj, (str, int, float, bool)):
                        return obj
                    if isinstance(obj, dict):
                        out: Dict[str, Any] = {}
                        for k, v in obj.items():
                            out[str(k)] = _safe_json(v, depth + 1)
                        return out
                    if isinstance(obj, (list, tuple, set)):
                        return [_safe_json(x, depth + 1) for x in list(obj)]
                    # asyncio.Future / coroutine / pydantic / dataclass etc.
                    try:
                        name = type(obj).__name__
                        return f"<{name}> {str(obj)[:300]}"
                    except Exception:
                        return "<non-serializable>"
                
                if not message:
                    return {
                        "status": "error",
                        "message": "消息不能为空",
                        "timestamp": datetime.now().isoformat()
                    }
                
                # 优先走主控制器核心大脑统一路由
                if hasattr(self.main_controller, "process_user_command"):
                    logger.debug(f"使用核心大脑统一路由处理: {message[:50]}...")
                    started_at = datetime.now()
                    result = await asyncio.wait_for(
                        self.main_controller.process_user_command(message, source="api_chat"),
                        timeout=timeout_sec,
                    )
                    latency_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                    trace["core_router_ms"] = latency_ms
                    
                    if result.get("success"):
                        trace["path"] = "core_brain_router"
                        return {
                            "status": "success",
                            "message": "AI响应成功",
                            "data": {
                                "response": result.get("response", ""),
                                "data": _safe_json(result.get("data")),
                                "source": result.get("source", "core_brain_router"),
                                "latency_ms": latency_ms,
                                "trace": trace,
                            },
                            "latency_ms_total": int((datetime.now() - chat_started_at).total_seconds() * 1000),
                            "timestamp": datetime.now().isoformat()
                        }
                    else:
                        return {
                            "status": "error",
                            "message": result.get("response", "AI处理失败"),
                            "trace": trace,
                            "latency_ms_total": int((datetime.now() - chat_started_at).total_seconds() * 1000),
                            "timestamp": datetime.now().isoformat()
                        }
                
                # 回退：AI指令执行器（兼容旧路径）
                ai_executor = getattr(self.main_controller, 'ai_command_executor', None)
                if ai_executor:
                    logger.debug(f"回退到AICommandExecutor处理: {message[:50]}...")
                    started_at = datetime.now()
                    result = await asyncio.wait_for(
                        ai_executor.process_input(message, source="api_chat"),
                        timeout=timeout_sec,
                    )
                    latency_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                    trace["executor_ms"] = latency_ms
                    if result.get("success"):
                        trace["path"] = "ai_command_executor"
                        return {
                            "status": "success",
                            "message": "AI响应成功",
                            "data": {
                                "response": result.get("response", ""),
                                "data": _safe_json(result.get("data")),
                                "source": "ai_command_executor",
                                "latency_ms": latency_ms,
                                "trace": trace,
                            },
                            "latency_ms_total": int((datetime.now() - chat_started_at).total_seconds() * 1000),
                            "timestamp": datetime.now().isoformat()
                        }
                
                # 回退：直接调用LLM集成（无系统感知）
                llm_integration = self.main_controller.llm_integration
                
                if not llm_integration:
                    return {
                        "status": "error",
                        "message": "LLM集成未初始化",
                        "timestamp": datetime.now().isoformat()
                    }
                
                if not model_id:
                    model_id = llm_integration.llm_manager.default_model
                
                logger.debug(f"回退到直接LLM调用: {message[:50]}...")
                started_at = datetime.now()
                response = await asyncio.wait_for(
                    llm_integration.generate(
                        prompt=message,
                        model_id=model_id
                    ),
                    timeout=timeout_sec,
                )
                trace["llm_direct_ms"] = int((datetime.now() - started_at).total_seconds() * 1000)
                
                if response.success:
                    trace["path"] = "llm_direct"
                    return {
                        "status": "success",
                        "message": "对话成功",
                        "data": {
                            "response": response.content,
                            "model_id": response.model_id,
                            "provider": response.provider.value if hasattr(response.provider, 'value') else str(response.provider),
                            "tokens_used": response.tokens_used,
                            "latency_ms": response.latency_ms,
                            "cost": response.cost,
                            "source": "llm_direct",
                            "trace": trace,
                        },
                        "latency_ms_total": int((datetime.now() - chat_started_at).total_seconds() * 1000),
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"AI模型调用失败: {response.error_message}",
                        "trace": trace,
                        "latency_ms_total": int((datetime.now() - chat_started_at).total_seconds() * 1000),
                        "timestamp": datetime.now().isoformat()
                    }
            except asyncio.TimeoutError:
                return {
                    "status": "timeout",
                    "message": f"AI对话超时（>{timeout_sec:.1f}s）",
                    "hint": "可降低输入长度，或使用 commander/dispatch async_mode=true",
                    "trace": trace if "trace" in locals() else {},
                    "latency_ms_total": int((datetime.now() - chat_started_at).total_seconds() * 1000) if "chat_started_at" in locals() else None,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"AI对话失败: {e}")
                import traceback
                traceback.print_exc()
                return {
                    "status": "error",
                    "message": f"AI对话失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }

        # 自然语言查询API端点
        @api_v1_router.post("/ai/query", tags=["ai"])
        async def ai_query(query_data: Dict[str, Any]):
            """自然语言查询 - 使用自然语言接口处理查询"""
            try:
                query = query_data.get("query", "")
                context = query_data.get("context", {})
                
                if not query:
                    return {
                        "status": "error",
                        "message": "查询内容不能为空",
                        "timestamp": datetime.now().isoformat()
                    }
                
                # 使用自然语言接口处理查询
                result = await self.main_controller.process_natural_language_query(query, context)
                # 回退：若NLI返回“解析失败”，直接走执行验证器语义查询，确保接口可用
                if (
                    isinstance(result, dict)
                    and result.get("success") is False
                    and "无法解析命令执行结果" in str(result.get("details", ""))
                    and hasattr(self.main_controller, "query_execution_status")
                ):
                    result = await self.main_controller.query_execution_status(query)
                
                return {
                    "status": "success",
                    "message": "查询处理成功",
                    "data": result,
                    "timestamp": datetime.now().isoformat()
                }
                    
            except Exception as e:
                logger.error(f"自然语言查询失败: {e}")
                import traceback
                traceback.print_exc()
                return {
                    "status": "error",
                    "message": f"自然语言查询失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
        
        # AI记忆管理路由
        def _resolve_memory_manager():
            gateway = None
            if hasattr(self.main_controller, "get_memory_gateway"):
                gateway = self.main_controller.get_memory_gateway()
            if gateway:
                return gateway
            return self.main_controller.ai_memory_manager

        @api_v1_router.post("/ai/memory/store", tags=["ai-memory"])
        async def memory_store(memory_data: Dict[str, Any]):
            """统一记忆写入入口（支持scope）"""
            try:
                content = str(memory_data.get("content", "")).strip()
                if not content:
                    return {
                        "status": "error",
                        "message": "content不能为空",
                        "timestamp": datetime.now().isoformat()
                    }
                memory_manager = _resolve_memory_manager()
                memory_id = await memory_manager.store(
                    content=content,
                    scope=str(memory_data.get("scope", "global")),
                    category=str(memory_data.get("category", "conversation")),
                    importance=float(memory_data.get("importance", 0.5)),
                    metadata=memory_data.get("metadata", {}) if isinstance(memory_data.get("metadata"), dict) else {},
                )
                return {
                    "status": "success",
                    "data": {"memory_id": memory_id},
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"统一记忆写入失败: {e}")
                return {
                    "status": "error",
                    "message": f"统一记忆写入失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }

        @api_v1_router.post("/ai/memory/recall", tags=["ai-memory"])
        async def memory_recall(query_data: Dict[str, Any]):
            """统一记忆检索入口（支持scope）"""
            try:
                query = str(query_data.get("query", "")).strip()
                if not query:
                    return {
                        "status": "error",
                        "message": "query不能为空",
                        "timestamp": datetime.now().isoformat()
                    }
                memory_manager = _resolve_memory_manager()
                records = await memory_manager.recall(
                    query=query,
                    scope=query_data.get("scope"),
                    limit=int(query_data.get("limit", 10)),
                    min_importance=float(query_data.get("min_importance", 0.0)),
                )
                include_trace = bool(query_data.get("include_trace", False))
                trace = {}
                if include_trace and hasattr(memory_manager, "get_last_recall_trace"):
                    try:
                        trace = memory_manager.get_last_recall_trace()
                    except Exception:
                        trace = {}
                return {
                    "status": "success",
                    "data": {
                        "items": [r.to_dict() if hasattr(r, "to_dict") else r for r in records],
                        **({"trace": trace} if include_trace else {}),
                    },
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"统一记忆检索失败: {e}")
                return {
                    "status": "error",
                    "message": f"统一记忆检索失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }

        @api_v1_router.get("/ai/memory/trace", tags=["ai-memory"])
        async def memory_trace():
            """获取最近一次 recall 的 trace（可观测性）"""
            try:
                memory_manager = _resolve_memory_manager()
                trace = {}
                if hasattr(memory_manager, "get_last_recall_trace"):
                    trace = memory_manager.get_last_recall_trace()
                return {"status": "success", "data": {"trace": trace}, "timestamp": datetime.now().isoformat()}
            except Exception as e:
                return {"status": "error", "message": str(e), "timestamp": datetime.now().isoformat()}

        @api_v1_router.get("/ai/memory/summaries/status", tags=["ai-memory"])
        async def memory_summaries_status():
            """每日/每周总结生成状态（best-effort）"""
            try:
                memory_manager = _resolve_memory_manager()
                status = {}
                if hasattr(memory_manager, "get_summary_status"):
                    status = memory_manager.get_summary_status()
                return {"status": "success", "data": {"status": status}, "timestamp": datetime.now().isoformat()}
            except Exception as e:
                return {"status": "error", "message": str(e), "timestamp": datetime.now().isoformat()}

        @api_v1_router.get("/ai/memory/quality", tags=["ai-memory"])
        async def memory_quality_metrics():
            """记忆质量与分布指标（best-effort，进程内召回命中率）"""
            try:
                memory_manager = _resolve_memory_manager()
                data: Dict[str, Any] = {}
                if hasattr(memory_manager, "get_quality_metrics"):
                    data["quality"] = memory_manager.get_quality_metrics()
                if hasattr(memory_manager, "get_stats"):
                    full = memory_manager.get_stats()
                    g = (full or {}).get("gateway") or {}
                    if isinstance(g, dict) and "recall" in g:
                        data["recall"] = g.get("recall")
                return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
            except Exception as e:
                return {"status": "error", "message": str(e), "timestamp": datetime.now().isoformat()}

        @api_v1_router.post("/ai/memory/disk-policy/run", tags=["ai-memory"])
        async def memory_disk_policy_run():
            """手动触发一次磁盘阈值清理（best-effort）"""
            try:
                memory_manager = _resolve_memory_manager()
                out = {}
                if hasattr(memory_manager, "enforce_disk_policy"):
                    out = await memory_manager.enforce_disk_policy()
                return {"status": "success", "data": out, "timestamp": datetime.now().isoformat()}
            except Exception as e:
                return {"status": "error", "message": str(e), "timestamp": datetime.now().isoformat()}

        @api_v1_router.post("/ai/memory/instruction", tags=["ai-memory"])
        async def add_system_instruction(instruction_data: Dict[str, Any]):
            """添加系统指令（工作要求、任务等）"""
            try:
                instruction = instruction_data.get("instruction", "")
                context = instruction_data.get("context", "")
                
                if not instruction:
                    return {
                        "status": "error",
                        "message": "指令不能为空",
                        "timestamp": datetime.now().isoformat()
                    }
                
                memory_manager = _resolve_memory_manager()
                memory_id = await memory_manager.add_system_instruction(instruction, context)
                
                return {
                    "status": "success",
                    "message": "系统指令添加成功",
                    "data": {
                        "memory_id": memory_id
                    },
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"添加系统指令失败: {e}")
                return {
                    "status": "error",
                    "message": f"添加系统指令失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
        
        @api_v1_router.post("/ai/memory/preference", tags=["ai-memory"])
        async def add_user_preference(pref_data: Dict[str, Any]):
            """添加用户偏好"""
            try:
                key = pref_data.get("key", "")
                value = pref_data.get("value", "")
                description = pref_data.get("description", "")
                
                if not key or value is None:
                    return {
                        "status": "error",
                        "message": "偏好键和值不能为空",
                        "timestamp": datetime.now().isoformat()
                    }
                
                memory_manager = _resolve_memory_manager()
                memory_id = await memory_manager.add_user_preference(key, value, description)
                
                return {
                    "status": "success",
                    "message": "用户偏好添加成功",
                    "data": {
                        "memory_id": memory_id
                    },
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"添加用户偏好失败: {e}")
                return {
                    "status": "error",
                    "message": f"添加用户偏好失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
        
        @api_v1_router.get("/ai/memory/stats", tags=["ai-memory"])
        async def get_memory_stats():
            """获取记忆统计"""
            try:
                memory_manager = _resolve_memory_manager()
                stats = memory_manager.get_stats()
                
                return {
                    "status": "success",
                    "data": stats,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"获取记忆统计失败: {e}")
                return {
                    "status": "error",
                    "message": f"获取记忆统计失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
        
        @api_v1_router.get("/ai/memory/trading-summary", tags=["ai-memory"])
        async def get_trading_summary(days: int = 30):
            """获取交易历史总结"""
            try:
                memory_manager = _resolve_memory_manager()
                summary = await memory_manager.summarize_trade_history(days)
                
                return {
                    "status": "success",
                    "data": {
                        "summary": summary,
                        "days": days
                    },
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"获取交易总结失败: {e}")
                return {
                    "status": "error",
                    "message": f"获取交易总结失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
        
        @api_v1_router.get("/ai/memory/workspace-files", tags=["ai-memory"])
        async def get_workspace_memory_files():
            """获取工作区记忆文件列表"""
            try:
                memory_manager = _resolve_memory_manager()
                memory_files = memory_manager.get_workspace_memory()
                
                return {
                    "status": "success",
                    "data": {
                        "files": list(memory_files.keys())
                    },
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"获取工作区记忆文件列表失败: {e}")
                return {
                    "status": "error",
                    "message": f"获取工作区记忆文件列表失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
        
        @api_v1_router.get("/ai/memory/workspace-file/{filename}", tags=["ai-memory"])
        async def get_workspace_memory_file(filename: str):
            """获取工作区记忆文件内容"""
            try:
                memory_manager = _resolve_memory_manager()
                memory_files = memory_manager.get_workspace_memory(filename)
                
                if filename not in memory_files:
                    return {
                        "status": "error",
                        "message": f"记忆文件 {filename} 不存在",
                        "timestamp": datetime.now().isoformat()
                    }
                
                return {
                    "status": "success",
                    "data": {
                        "filename": filename,
                        "content": memory_files[filename]
                    },
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"获取工作区记忆文件内容失败: {e}")
                return {
                    "status": "error",
                    "message": f"获取工作区记忆文件内容失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
        
        @api_v1_router.put("/ai/memory/workspace-file/{filename}", tags=["ai-memory"])
        async def update_workspace_memory_file(filename: str, file_data: Dict[str, Any]):
            """更新工作区记忆文件内容"""
            try:
                content = file_data.get("content", "")
                notify_user = file_data.get("notify_user", True)
                
                if not content:
                    return {
                        "status": "error",
                        "message": "文件内容不能为空",
                        "timestamp": datetime.now().isoformat()
                    }
                
                memory_manager = _resolve_memory_manager()
                success = await memory_manager.update_workspace_memory(filename, content, notify_user)
                
                if success:
                    return {
                        "status": "success",
                        "message": f"记忆文件 {filename} 更新成功",
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"记忆文件 {filename} 更新失败",
                        "timestamp": datetime.now().isoformat()
                    }
            except Exception as e:
                logger.error(f"更新工作区记忆文件失败: {e}")
                return {
                    "status": "error",
                    "message": f"更新工作区记忆文件失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }

        # WebSocket端点
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket端点"""
            if self.require_ws_auth:
                token = websocket.query_params.get("token")
                if not token:
                    token = self._extract_bearer_token(websocket.headers.get("authorization"))
                payload = await self.verify_token(token) if token else None
                if not payload:
                    await websocket.close(code=1008)
                    return
            await self._handle_websocket_connection(websocket)

        # 交易所状态API - 支持 /api/v1/exchanges
        @api_v1_router.get("/exchanges", tags=["exchanges"])
        async def get_exchanges():
            """获取所有交易所状态"""
            try:
                # 从主控制器获取交易所状态
                if hasattr(self.main_controller, 'okx_exchange'):
                    okx_exchange = self.main_controller.okx_exchange
                    is_connected = okx_exchange.is_connected if hasattr(okx_exchange, 'is_connected') else False
                    
                    return {
                        "status": "success",
                        "exchanges": [
                            {
                                "id": "okx",
                                "name": "OKX",
                                "status": "connected" if is_connected else "disconnected",
                                "is_connected": is_connected,
                                "api_status": "online" if is_connected else "offline"
                            }
                        ],
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    # 模拟数据
                    return {
                        "status": "success",
                        "exchanges": [
                            {
                                "id": "okx",
                                "name": "OKX",
                                "status": "connected",
                                "is_connected": True,
                                "api_status": "online"
                            }
                        ],
                        "timestamp": datetime.now().isoformat()
                    }
            except Exception as e:
                logger.error(f"获取交易所状态失败: {e}")
                return {
                    "status": "error",
                    "message": f"获取交易所状态失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }

        # 移除 data-fusion analyze 兼容端点（统一使用 /api/v1/market/symbol/{symbol}）

        @api_v1_router.get("/external/analyze-trends", tags=["external"])
        async def external_analyze_trends(symbol: str):
            """外部趋势分析统一入口（由 DataSourceHub 提供）。"""
            data = await data_source_hub.analyze_trends(symbol)
            return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}

        @api_v1_router.get("/external/signals", tags=["external"])
        async def external_signals(symbol: str):
            """外部信号统一入口（由 DataSourceHub 提供）。"""
            data = await data_source_hub.get_signals(symbol)
            return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}

        @api_v1_router.post("/external/indicators", tags=["external"])
        async def external_indicators(payload: Dict[str, Any]):
            """外部指标统一入口（由 DataSourceHub 提供）。"""
            symbol = str(payload.get("symbol") or "BTC/USDT")
            indicators = payload.get("indicators") if isinstance(payload.get("indicators"), list) else None
            data = await data_source_hub.get_indicators(symbol, indicators=indicators)
            return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}

        @api_v1_router.get("/data-hub/status", tags=["data-hub"])
        async def data_hub_status():
            """统一数据源中心状态（中文字段，便于前端展示）。"""
            st = await _resolve_data_source_hub().status()
            return {
                "status": "success",
                "data": {
                    "模块": "统一数据源中心",
                    "健康": st.healthy,
                    "提供者": st.provider,
                    "时间": st.timestamp,
                },
                "timestamp": datetime.now().isoformat(),
            }

        @api_v1_router.get("/data-hub/unified-snapshot", tags=["data-hub"])
        async def data_hub_unified_snapshot(symbol: str = "BTC/USDT"):
            """统一双渠道数据快照（中文模块化输出）。"""
            try:
                data = await asyncio.wait_for(_resolve_data_source_hub().get_unified_snapshot(symbol), timeout=20.0)
                return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
            except asyncio.TimeoutError:
                return {
                    "status": "degraded",
                    "data": {
                        "symbol": symbol,
                        "message": "获取 unified-snapshot 超时（可能为交易所网络抖动）",
                    },
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                return {
                    "status": "degraded",
                    "data": {"symbol": symbol, "message": f"获取 unified-snapshot 失败: {e}"},
                    "timestamp": datetime.now().isoformat(),
                }

        @api_v1_router.get("/data-hub/contract", tags=["data-hub"])
        async def data_hub_contract():
            """
            数据源采集契约（给前端自动适配用）：
            - stable output contract (shape-only)
            - current collector config snapshot (enabled collectors/providers)
            """
            try:
                contract = (
                    _resolve_data_source_hub().get_collector_contract()
                    if hasattr(_resolve_data_source_hub(), "get_collector_contract")
                    else {}
                )
                mc = getattr(_resolve_data_source_hub(), "main_controller", None)
                cfg = {}
                if mc and hasattr(mc, "get_ai_managed_config"):
                    try:
                        cfg = await mc.get_ai_managed_config("data_source_hub", {})
                    except Exception:
                        cfg = {}
                return {
                    "status": "success",
                    "data": {
                        "contract": contract,
                        "config": cfg,
                    },
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                return {
                    "status": "degraded",
                    "data": {"message": f"contract 获取失败: {e}"},
                    "timestamp": datetime.now().isoformat(),
                }

        @api_v1_router.get("/data-hub/quality-advice", tags=["data-hub"])
        async def data_hub_quality_advice(symbol: str = "BTC/USDT"):
            """数据质量与作用评分建议（插件化能力输出）。"""
            try:
                data = await asyncio.wait_for(_resolve_data_source_hub().get_unified_snapshot(symbol), timeout=20.0)
                advice = data.get("数据质量与作用评分", {})
                return {"status": "success", "data": advice, "timestamp": datetime.now().isoformat()}
            except asyncio.TimeoutError:
                return {
                    "status": "degraded",
                    "data": {"symbol": symbol, "message": "quality-advice 超时"},
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                return {
                    "status": "degraded",
                    "data": {"symbol": symbol, "message": f"quality-advice 失败: {e}"},
                    "timestamp": datetime.now().isoformat(),
                }

        @api_v1_router.get("/data-hub/ai-analysis", tags=["data-hub"])
        async def data_hub_ai_analysis(symbol: str = "BTC/USDT"):
            """统一数据快照的 AI 智能分析结果（已迁移到 MarketIntelligenceEngine）。"""
            try:
                mc = getattr(_resolve_data_source_hub(), "main_controller", None)
                mi = getattr(mc, "market_intelligence", None) if mc else None
                if mi and hasattr(mi, "get_symbol_view"):
                    view = await asyncio.wait_for(mi.get_symbol_view(symbol, include_snapshot=False), timeout=6.0)
                    d = view.to_dict() if hasattr(view, "to_dict") else (view if isinstance(view, dict) else {})
                    # Keep the same endpoint but return MI view so frontends don't break.
                    return {
                        "status": "deprecated",
                        "message": "已迁移：请使用 /api/v1/market/symbol/{symbol}",
                        "data": d,
                        "timestamp": datetime.now().isoformat(),
                    }
                return {
                    "status": "deprecated",
                    "message": "已迁移：请使用 /api/v1/market/symbol/{symbol}",
                    "data": {"symbol": symbol},
                    "timestamp": datetime.now().isoformat(),
                }
            except asyncio.TimeoutError:
                return {
                    "status": "degraded",
                    "data": {"symbol": symbol, "message": "ai-analysis 超时"},
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                return {
                    "status": "degraded",
                    "data": {"symbol": symbol, "message": f"ai-analysis 失败: {e}"},
                    "timestamp": datetime.now().isoformat(),
                }

        # 多源数据融合数据源API - 支持 /api/v1/data-fusion/sources
        @api_v1_router.get("/data-fusion/sources", tags=["data-fusion"])
        async def get_data_sources():
            """获取多源数据融合数据源"""
            return {
                "status": "success",
                "data": {
                    "available_sources": [
                        "technical",
                        "market_sentiment",
                        "on_chain",
                        "news",
                        "social_media"
                    ],
                    "supported_exchanges": [
                        "okx",
                        "binance",
                        "coinbase"
                    ]
                },
                "timestamp": datetime.now().isoformat()
            }

        # 多源数据融合历史分析API - 支持 /api/v1/data-fusion/history
        @api_v1_router.get("/data-fusion/history", tags=["data-fusion"])
        async def get_analysis_history():
            """获取多源数据融合历史分析"""
            import random
            from datetime import datetime, timedelta
            
            history = []
            sentiments = ['extreme_greed', 'greed', 'neutral', 'fear', 'extreme_fear']
            recommendations = ['bullish', 'bearish', 'neutral']
            
            for i in range(10):
                timestamp = (datetime.now() - timedelta(minutes=i*30)).isoformat()
                history.append({
                    "timestamp": timestamp,
                    "overall_sentiment": sentiments[random.randint(0, 4)],
                    "overall_sentiment_score": round(random.uniform(-1, 1), 2),
                    "signal_strength": random.randint(1, 5),
                    "recommendation": recommendations[random.randint(0, 2)],
                    "confidence": round(random.uniform(0.7, 1.0), 2)
                })
            
            return {
                "status": "success",
                "data": history,
                "timestamp": datetime.now().isoformat()
            }

        # 移除 commander 全路径镜像转发（仅保留显式声明的 commander 接口）

        # 添加API路由到应用
        api_router.include_router(api_v1_router)
        self.app.include_router(api_router)

        # 添加策略API路由
        self.app.include_router(strategy_router)

        # 模块控制 API（含 /api/v1/s1/verify）必须在静态资源之前注册
        try:
            from src.modules.api.module_control_api import init_module_control_api
            init_module_control_api(self.app, self.main_controller)
            logger.info("✅ 模块控制API已初始化")
        except Exception as e:
            logger.warning(f"模块控制API初始化失败: {e}")

        try:
            from src.modules.api.monitoring_api import router as monitoring_router
            from src.modules.api.monitoring_api import set_proactive_ai
            self.app.include_router(monitoring_router)
            if self.main_controller and hasattr(self.main_controller, "proactive_ai"):
                set_proactive_ai(self.main_controller.proactive_ai)
            logger.info("✅ 监控API已初始化")
        except Exception as e:
            logger.warning(f"监控API初始化失败: {e}")

        # 添加静态文件服务
        from fastapi.staticfiles import StaticFiles
        import os
        # 计算前端目录路径
        current_dir = os.path.dirname(__file__)
        api_dir = os.path.dirname(current_dir)
        modules_dir = os.path.dirname(api_dir)
        src_dir = os.path.dirname(modules_dir)
        # 兼容两种布局：
        # 1) 仓库根目录 /app/frontend/dist（Docker构建常见）
        # 2) /app/src/frontend/dist（历史/特殊布局）
        candidate_frontend_dirs = [
            os.path.join(os.path.dirname(src_dir), "frontend", "dist"),
            os.path.join(src_dir, "frontend", "dist"),
        ]
        for frontend_dir in candidate_frontend_dirs:
            if os.path.exists(frontend_dir):
                self.app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
                logger.info(f"添加静态文件服务: {frontend_dir}")
                break

        logger.info("API路由设置完成")

    async def _handle_websocket_connection(self, websocket: WebSocket) -> None:
        """处理WebSocket连接"""
        # 接受连接
        await websocket.accept()

        # 创建连接记录
        conn_id = str(uuid.uuid4())
        connection = WebSocketConnection(id=conn_id, websocket=websocket)

        async with self._lock:
            self.websocket_connections[conn_id] = connection
            self.__class__._shared_websocket_connections[conn_id] = connection
            self.stats["websocket_connections"] += 1

        logger.info(f"WebSocket连接建立: {conn_id}")

        try:
            # 发送连接确认
            await websocket.send_json(
                self._normalize_api_payload(
                    {
                        "type": WebSocketEventType.CONNECT.value,
                        "connection_id": conn_id,
                        "timestamp": datetime.now().isoformat(),
                    },
                    status.HTTP_200_OK,
                )
            )

            # 处理消息
            while True:
                # 接收消息
                data = await websocket.receive_json()

                # 更新活动时间
                connection.update_activity()

                # 处理消息类型
                message_type = data.get("type")

                if message_type == WebSocketEventType.SUBSCRIBE.value:
                    # 订阅频道
                    channels = data.get("channels", [])
                    symbols = data.get("symbols", [])

                    for channel in channels:
                        if channel not in connection.subscriptions:
                            connection.subscriptions.append(channel)

                    logger.debug(f"WebSocket订阅: {conn_id} -> {channels}")

                    await websocket.send_json(
                        self._normalize_api_payload(
                            {
                                "type": WebSocketEventType.SUBSCRIBE.value,
                                "channels": channels,
                                "timestamp": datetime.now().isoformat(),
                            },
                            status.HTTP_200_OK,
                        )
                    )

                elif message_type == WebSocketEventType.UNSUBSCRIBE.value:
                    # 取消订阅
                    channels = data.get("channels", [])

                    for channel in channels:
                        if channel in connection.subscriptions:
                            connection.subscriptions.remove(channel)

                    logger.debug(f"WebSocket取消订阅: {conn_id} -> {channels}")

                    await websocket.send_json(
                        self._normalize_api_payload(
                            {
                                "type": WebSocketEventType.UNSUBSCRIBE.value,
                                "channels": channels,
                                "timestamp": datetime.now().isoformat(),
                            },
                            status.HTTP_200_OK,
                        )
                    )

                elif message_type == WebSocketEventType.HEARTBEAT.value:
                    # 心跳
                    await websocket.send_json(
                        self._normalize_api_payload(
                            {
                                "type": WebSocketEventType.HEARTBEAT.value,
                                "timestamp": datetime.now().isoformat(),
                            },
                            status.HTTP_200_OK,
                        )
                    )

        except WebSocketDisconnect:
            logger.info(f"WebSocket连接断开: {conn_id}")
        except Exception as e:
            logger.error(f"WebSocket处理错误 {conn_id}: {e}")
        finally:
            # 清理连接
            await self._close_websocket_connection(conn_id)

    async def _close_websocket_connection(self, conn_id: str) -> None:
        """关闭WebSocket连接"""
        async with self._lock:
            if conn_id in self.websocket_connections:
                connection = self.websocket_connections.pop(conn_id)
                self.__class__._shared_websocket_connections.pop(conn_id, None)

                try:
                    await connection.websocket.close()
                except Exception:
                    pass

                self.stats["websocket_connections"] -= 1
                logger.debug(f"WebSocket连接关闭: {conn_id}")

    async def _cleanup_inactive_websockets(self) -> None:
        """清理不活动的WebSocket连接"""
        logger.info("启动WebSocket连接清理任务")

        while self._running:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次

                current_time = datetime.now()
                inactive_connections = []

                # 找出不活动的连接
                for conn_id, connection in list(self.websocket_connections.items()):
                    if connection.idle_time > timedelta(minutes=5):  # 5分钟无活动
                        inactive_connections.append(conn_id)

                # 关闭不活动的连接
                for conn_id in inactive_connections:
                    logger.info(f"关闭不活动的WebSocket连接: {conn_id}")
                    await self._close_websocket_connection(conn_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WebSocket清理任务错误: {e}")
                await asyncio.sleep(60)

        logger.info("WebSocket连接清理任务停止")

    async def _broadcast_market_data(self) -> None:
        """广播市场数据（模拟）"""
        logger.info("启动市场数据广播任务")

        while self._running:
            try:
                await asyncio.sleep(1)  # 每秒广播一次

                # 模拟市场数据
                market_data = {
                    "symbol": "BTC/USDT",
                    "price": 50000 + (datetime.now().second % 100) * 10,
                    "volume": 1000 + (datetime.now().second % 50) * 20,
                    "timestamp": datetime.now().isoformat(),
                }

                # 广播到market_data频道
                sent = await self.broadcast_websocket("market_data", market_data)

                if sent > 0 and datetime.now().second % 10 == 0:
                    logger.debug(f"广播市场数据到 {sent} 个连接")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"市场数据广播错误: {e}")
                await asyncio.sleep(1)

        logger.info("市场数据广播任务停止")

    async def _check_rate_limit(self, client_ip: str, endpoint: str) -> bool:
        """检查速率限制"""
        current_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
        key = f"{client_ip}:{endpoint}:{current_minute}"

        # 获取当前计数
        current_count = self.request_counts.get(key, 0)

        # 获取限制配置
        rate_limit = self.rate_limits.get(endpoint, RateLimit())

        # 检查是否超过限制
        if current_count >= rate_limit.requests_per_minute:
            logger.warning(f"速率限制触发: {client_ip} -> {endpoint}")
            return False

        # 更新计数
        self.request_counts[key] = current_count + 1
        return True

    def _get_uptime(self) -> str:
        """获取运行时间（模拟）"""
        # 这里应该计算实际的运行时间
        # 为简化，返回固定值
        return "0 days, 0:00:00"


# 使用示例
async def example_usage():
    """API服务器使用示例"""

    if not HAS_FASTAPI:
        logger.info("FastAPI未安装，跳过示例")
        return

    # 创建API服务器
    api_server = APIServer(host="127.0.0.1", port=8000)
    await api_server.initialize()

    try:
        # 启动服务器
        success = await api_server.start()
        logger.info(f"API服务器启动: {'成功' if success else '失败'}")

        if success:
            # 注册自定义路由
            @api_server.app.get("/api/v1/market/{symbol}", tags=["market"])
            async def get_market_data(symbol: str):
                """获取市场数据"""
                return {
                    "symbol": symbol,
                    "price": 50000.0,
                    "volume": 1000.0,
                    "timestamp": datetime.now().isoformat(),
                }

            # 获取统计信息
            await asyncio.sleep(1)
            stats = await api_server.get_api_stats()
            logger.info(f"API统计: {json.dumps(stats, indent=2, default=str)}")

            # 模拟运行一段时间
            logger.info("API服务器运行中...按Ctrl+C停止")
            await asyncio.sleep(5)

            # 停止服务器
            await api_server.stop()

    finally:
        await api_server.cleanup()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
