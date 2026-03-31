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
import json
import logging
import secrets
import traceback
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.modules.api.strategy_api import router as strategy_router
from src.modules.core.enhanced_llm_manager import TaskType

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
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from jose import JWTError, jwt
    from passlib.context import CryptContext
    from pydantic import BaseModel, Field, confloat, conint, validator

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    logger = logging.getLogger(__name__)
    logger.warning("FastAPI未安装，API功能将受限")


logger = logging.getLogger(__name__)


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
        return channel in self.subscriptions

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
        self.host = host
        self.port = port

        # FastAPI应用
        self.app: Optional[FastAPI] = None
        self.routers: Dict[str, APIRouter] = {}

        # 认证
        self.security = HTTPBearer() if HAS_FASTAPI else None
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") if HAS_FASTAPI else None
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
            )

            # 加载配置
            await self._load_config()

            # 添加中间件
            await self._add_middleware()

            # 设置路由
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
                # 导入uvicorn
                import uvicorn
                from fastapi.staticfiles import StaticFiles
                
                # 创建uvicorn配置
                config = uvicorn.Config(
                    self.app,
                    host=self.host,
                    port=self.port,
                    log_level="info",
                    access_log=True
                )
                
                # 创建服务器
                server = uvicorn.Server(config)
                
                # 在异步任务中启动服务器
                async def run_server():
                    try:
                        await server.serve()
                    except asyncio.CancelledError:
                        logger.info("API服务器任务被取消")
                    except Exception as e:
                        logger.error(f"API服务器运行错误: {e}")
                
                # 启动服务器任务
                server_task = asyncio.create_task(run_server())
                self._tasks.append(server_task)
                
                self._running = True
                logger.info(f"API服务器已启动，访问 http://{self.host}:{self.port}/docs 查看文档")
                return True
            else:
                # 模拟模式
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
        if not self._running:
            return 0

        sent_count = 0
        current_time = datetime.now()

        for conn_id, connection in list(self.websocket_connections.items()):
            try:
                # 检查连接是否订阅了该频道
                if connection.is_subscribed(channel):
                    # 准备消息
                    message = {
                        "type": WebSocketEventType.DATA.value,
                        "channel": channel,
                        "data": data,
                        "timestamp": current_time.isoformat(),
                    }

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

            # 加载速率限制配置
            rate_limit_config = api_config.get("rate_limits", {})
            for endpoint, limit_config in rate_limit_config.items():
                self.rate_limits[endpoint] = RateLimit(**limit_config)

        logger.info(f"加载API配置: {self.host}:{self.port}")

    async def _add_middleware(self) -> None:
        """添加中间件"""
        if not self.app:
            return

        # CORS中间件
        if self.enable_cors:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],  # 生产环境应该限制
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        # 信任主机中间件
        self.app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])  # 生产环境应该限制

        # 自定义中间件
        @self.app.middleware("http")
        async def add_process_time_header(request: Request, call_next):
            """添加处理时间头"""
            start_time = datetime.now()

            # 速率限制检查
            if self.enable_rate_limit:
                client_ip = request.client.host if request.client else "unknown"
                endpoint = request.url.path

                if not await self._check_rate_limit(client_ip, endpoint):
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={"error": "Rate limit exceeded"},
                    )

            # 处理请求
            response = await call_next(request)

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

        # 根路由 - 仅在静态文件服务不存在时生效
        # 注意：静态文件服务会处理根路径的请求

        # 健康检查 - 同时支持 /health 和 /api/health
        @self.app.get("/health", tags=["health"])
        @api_router.get("/health", tags=["health"])
        async def health_check():
            """健康检查"""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "uptime": self._get_uptime(),
            }

        # 指标端点 - 同时支持 /metrics 和 /api/metrics
        @self.app.get("/metrics", tags=["metrics"])
        @api_router.get("/metrics", tags=["metrics"])
        async def get_metrics():
            """获取指标"""
            stats = await self.get_api_stats()
            return stats

        # 状态端点 - 支持 /api/status 和 /api/v1/status 和 /api/v1/system/status
        @api_router.get("/status", tags=["system"])
        @api_v1_router.get("/status", tags=["system"])
        @api_v1_router.get("/system/status", tags=["system"])
        async def get_status():
            """获取系统状态"""
            return {
                "system_status": "running",
                "status": "running",
                "uptime": 0,
                "module_count": 7,
                "running_modules": 7,
                "timestamp": datetime.now().isoformat(),
                "module_statuses": {
                    "主控制器": {"status": "running", "health": "healthy", "uptime": 0, "error_count": 0},
                    "API服务器": {"status": "running", "health": "healthy", "uptime": 0, "error_count": 0},
                    "数据库管理器": {"status": "running", "health": "healthy", "uptime": 0, "error_count": 0},
                    "事件系统": {"status": "running", "health": "healthy", "uptime": 0, "error_count": 0},
                    "策略管理器": {"status": "running", "health": "healthy", "uptime": 0, "error_count": 0},
                    "风险管理": {"status": "running", "health": "healthy", "uptime": 0, "error_count": 0},
                    "市场数据": {"status": "running", "health": "healthy", "uptime": 0, "error_count": 0},
                }
            }

        # 健康检查 - 支持 /api/v1/health
        @api_v1_router.get("/health", tags=["health"])
        async def health_check_v1():
            """健康检查 v1"""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "uptime": self._get_uptime(),
            }

        # 指标端点 - 支持 /api/v1/metrics
        @api_v1_router.get("/metrics", tags=["metrics"])
        async def get_metrics_v1():
            """获取指标 v1"""
            # 这里应该从系统获取真实的指标数据
            # 为简化，返回模拟数据，与前端期望的格式一致
            return {
                "total_events": 1234,
                "total_errors": 5,
                "module_starts": 7,
                "event_processing_time_ms": 1.23,
                "running_modules": 7,
                "module_count": 7,
                "websocket_active_connections": 0,
                "rate_limits": {},
                "uptime": "0 days, 0:00:00",
                "timestamp": datetime.now().isoformat()
            }

        # 认证路由 - 同时支持 /auth/login 和 /api/v1/auth/login
        @self.app.post("/auth/login", tags=["auth"])
        @api_v1_router.post("/auth/login", tags=["auth"])
        async def login(request: LoginRequest):
            """用户登录"""
            # 这里应该从数据库验证用户
            # 为简化，我们使用模拟验证
            if request.username == "admin" and request.password == "admin123":
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
        @self.app.post("/auth/logout", tags=["auth"])
        @api_v1_router.post("/auth/logout", tags=["auth"])
        async def logout():
            """用户登出"""
            # 这里应该处理登出逻辑，比如清除令牌等
            # 为简化，我们只返回成功响应
            return {"status": "success", "message": "登出成功"}

        # 刷新令牌路由 - 同时支持 /auth/refresh 和 /api/v1/auth/refresh
        @self.app.post("/auth/refresh", tags=["auth"])
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
        @self.app.get("/auth/me", tags=["auth"])
        @api_v1_router.get("/auth/me", tags=["auth"])
        async def get_current_user():
            """获取当前用户信息"""
            # 这里应该从令牌中获取用户信息
            # 为简化，我们返回模拟用户数据
            return {
                "id": 1,
                "username": "admin",
                "role": "admin",
                "email": "admin@example.com",
                "created_at": datetime.now().isoformat(),
            }

        # 受保护的路由示例
        @self.app.get("/api/v1/protected", tags=["api"])
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

        # 策略管理路由 - 支持 /api/v1/strategies
        @api_v1_router.get("/strategies", tags=["strategies"])
        async def get_strategies():
            """获取所有策略"""
            # 这里应该从策略管理器获取策略列表
            # 为简化，返回模拟数据
            return [
                {
                    "id": "1",
                    "name": "移动平均趋势跟踪",
                    "status": "active",
                    "returns": "15.2",
                    "max_drawdown": "8.3",
                    "sharpe_ratio": "1.2"
                },
                {
                    "id": "2",
                    "name": "布林带均值回归",
                    "status": "inactive",
                    "returns": "10.5",
                    "max_drawdown": "6.7",
                    "sharpe_ratio": "0.9"
                },
                {
                    "id": "3",
                    "name": "机器学习策略",
                    "status": "active",
                    "returns": "22.8",
                    "max_drawdown": "12.1",
                    "sharpe_ratio": "1.5"
                }
            ]

        @api_v1_router.get("/strategies/{id}", tags=["strategies"])
        async def get_strategy(id: str):
            """获取单个策略"""
            # 这里应该从策略管理器获取策略详情
            # 为简化，返回模拟数据
            return {
                "id": id,
                "name": "移动平均趋势跟踪",
                "status": "active",
                "returns": "15.2",
                "max_drawdown": "8.3",
                "sharpe_ratio": "1.2",
                "parameters": {
                    "fast_ma_period": 10,
                    "slow_ma_period": 30,
                    "stop_loss_pct": 0.05,
                    "take_profit_pct": 0.1
                },
                "symbols": ["BTC/USDT", "ETH/USDT"],
                "timeframe": "1h"
            }

        @api_v1_router.post("/strategies", tags=["strategies"])
        async def create_strategy(strategy_data: Dict[str, Any]):
            """创建策略"""
            # 这里应该创建新策略
            # 为简化，返回模拟数据
            return {
                "id": "4",
                "name": strategy_data.get("name", "新策略"),
                "status": "inactive",
                "returns": "0.0",
                "max_drawdown": "0.0",
                "sharpe_ratio": "0.0"
            }

        @api_v1_router.put("/strategies/{id}", tags=["strategies"])
        async def update_strategy(id: str, strategy_data: Dict[str, Any]):
            """更新策略"""
            # 这里应该更新策略
            # 为简化，返回模拟数据
            return {
                "id": id,
                "name": strategy_data.get("name", "策略"),
                "status": "inactive",
                "returns": "0.0",
                "max_drawdown": "0.0",
                "sharpe_ratio": "0.0"
            }

        @api_v1_router.delete("/strategies/{id}", tags=["strategies"])
        async def delete_strategy(id: str):
            """删除策略"""
            # 这里应该删除策略
            # 为简化，返回成功消息
            return {"status": "success", "message": "策略已删除"}

        @api_v1_router.post("/strategies/{id}/activate", tags=["strategies"])
        async def activate_strategy(id: str):
            """激活策略"""
            # 这里应该激活策略
            # 为简化，返回成功消息
            return {"status": "success", "message": "策略已激活"}

        @api_v1_router.post("/strategies/{id}/deactivate", tags=["strategies"])
        async def deactivate_strategy(id: str):
            """停用策略"""
            # 这里应该停用策略
            # 为简化，返回成功消息
            return {"status": "success", "message": "策略已停用"}

        @api_v1_router.get("/strategies/{id}/performance", tags=["strategies"])
        async def get_strategy_performance(id: str):
            """获取策略性能"""
            # 这里应该获取策略性能
            # 为简化，返回模拟数据
            return {
                "strategy_id": id,
                "total_return": "15.2",
                "max_drawdown": "8.3",
                "sharpe_ratio": "1.2",
                "win_rate": "65.3",
                "profit_factor": "1.8",
                "total_trades": "124",
                "average_trade": "0.12"
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
            """获取市场行情"""
            import random
            base_price = 50000 if symbol == "BTC/USDT" else 3000 if symbol == "ETH/USDT" else 100
            price = base_price + random.uniform(-1000, 1000)
            return {
                "symbol": symbol,
                "price": round(price, 2),
                "bid": round(price - random.uniform(1, 10), 2),
                "ask": round(price + random.uniform(1, 10), 2),
                "high": round(price + random.uniform(50, 100), 2),
                "low": round(price - random.uniform(50, 100), 2),
                "volume": round(random.uniform(1000, 5000), 2),
                "change": round(random.uniform(-5, 5), 2),
                "timestamp": datetime.now().isoformat()
            }

        # 风险指标路由 - 支持 /api/v1/risk/metrics
        @api_v1_router.get("/risk/metrics", tags=["risk"])
        async def get_risk_metrics():
            """获取风险指标"""
            # 这里应该从风险管理服务获取真实数据
            # 为简化，返回模拟数据
            return {
                "max_drawdown": 8.2,
                "sharpe_ratio": 2.3,
                "var": 2.5,
                "risk_exposure": 42,
                "position_data": [
                    { "name": "BTC/USDT", "value": 45 },
                    { "name": "ETH/USDT", "value": 25 },
                    { "name": "BNB/USDT", "value": 15 },
                    { "name": "SOL/USDT", "value": 10 },
                    { "name": "ADA/USDT", "value": 5 }
                ],
                "risk_alerts": [
                    { "level": "low", "message": "市场波动率正常，无异常情况" },
                    { "level": "low", "message": "资产配置符合风险控制要求" },
                    { "level": "medium", "message": "BTC价格波动较大，建议关注" }
                ]
            }

        # 交易历史路由 - 支持 /api/v1/trades
        @api_v1_router.get("/trades", tags=["trades"])
        async def get_trades(range: str = "7d"):
            """获取交易历史"""
            # 这里应该从交易记录服务获取真实数据
            # 为简化，返回模拟数据
            import random
            trades = []
            now = datetime.now()
            days = 7 if range == "7d" else 1 if range == "24h" else 30 if range == "30d" else 90
            
            for i in range(100):
                timestamp = (now - timedelta(days=random.randint(0, days), hours=random.randint(0, 23), minutes=random.randint(0, 59))).isoformat()
                symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "ADA/USDT"]
                symbol = random.choice(symbols)
                side = random.choice(["buy", "sell"])
                price = random.uniform(3000, 50000) if symbol == "BTC/USDT" else random.uniform(100, 3000)
                amount = random.uniform(0.001, 1) if symbol == "BTC/USDT" else random.uniform(0.1, 10)
                status = "filled"
                
                trades.append({
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "side": side,
                    "price": round(price, 2),
                    "amount": round(amount, 4),
                    "status": status
                })
            
            # 按时间排序，最新的交易在前面
            trades.sort(key=lambda x: x["timestamp"], reverse=True)
            return trades

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
            print("保存设置:", settings)
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
            print("训练模型:", model_data)
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
            print("更新模型:", id, model_data)
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
            print("删除模型:", id)
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
            # 从主控制器获取已经初始化的LLM管理器实例
            llm_manager = self.main_controller.enhanced_llm_manager
            
            # 调试信息：打印真实的模型列表
            print(f"[DEBUG] llm_manager.models keys: {list(llm_manager.models.keys())}")
            print(f"[DEBUG] llm_manager.models count: {len(llm_manager.models)}")
            
            # 从LLM管理器获取真实AI模型配置
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
            print(f"[DEBUG] Returning {len(models)} models: {[m['model'] for m in models]}")
            return models

        @api_v1_router.post("/ai-models", tags=["ai-models"])
        async def add_ai_model(model_data: Dict[str, Any]):
            """添加AI模型"""
            # 从主控制器获取已经初始化的LLM管理器实例
            llm_manager = self.main_controller.enhanced_llm_manager
            
            # 调试信息：打印添加前的模型列表
            print(f"[DEBUG] Before add - models keys: {list(llm_manager.models.keys())}")
            
            # 调用LLM管理器添加AI模型
            try:
                model_config = {
                    "model_id": model_data.get("model"),
                    "display_name": model_data.get("name"),
                    "provider": model_data.get("provider"),
                    "api_key": model_data.get("api_key", ""),
                    "base_url": model_data.get("base_url", ""),
                    "enabled": model_data.get("enabled", True)
                }
                
                print(f"[DEBUG] Registering model with config: {model_config}")
                await llm_manager._register_model_from_config(model_config)
                
                # 调试信息：打印添加后的模型列表
                print(f"[DEBUG] After register - models keys: {list(llm_manager.models.keys())}")
                
                # 初始化模型提供者
                await llm_manager._initialize_provider(model_config["model_id"])
                
                print(f"[DEBUG] Model added successfully. Total models: {len(llm_manager.models)}")
                return {
                    "status": "success",
                    "message": "AI模型添加成功",
                    "model_id": model_config["model_id"],
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                print(f"[DEBUG] 添加AI模型失败: {e}")
                import traceback
                traceback.print_exc()
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
            print(f"[DEBUG] set_default_ai_model called with: {default_data}", flush=True)
            print(f"[DEBUG] Available models: {list(llm_manager.models.keys())}", flush=True)
            sys.stdout.flush()
            
            # 调用LLM管理器设置默认AI模型
            try:
                model_id = default_data.get("model_id")
                print(f"[DEBUG] model_id from request: {model_id}", flush=True)
                if model_id:
                    exists = model_id in llm_manager.models
                    print(f"[DEBUG] model_id exists in models: {exists}", flush=True)
                    if exists:
                        print(f"[DEBUG] model enabled: {llm_manager.models[model_id].enabled}", flush=True)
                    success = await llm_manager.switch_model(model_id)
                    print(f"[DEBUG] switch_model returned: {success}", flush=True)
                    if success:
                        print("[DEBUG] 设置默认AI模型成功:", default_data, flush=True)
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
                print("[DEBUG] 设置默认AI模型失败:", e, flush=True)
                import traceback
                traceback.print_exc()
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
                    
                    print("更新AI模型:", id, model_data)
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
                print("更新AI模型失败:", e)
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
            print("删除AI模型:", id)
            return {
                "status": "success",
                "message": "AI模型删除成功",
                "timestamp": datetime.now().isoformat()
            }

        # AI对话API端点
        @api_v1_router.post("/ai/chat", tags=["ai"])
        async def ai_chat(chat_data: Dict[str, Any]):
            """与AI模型对话"""
            try:
                message = chat_data.get("message", "")
                model_id = chat_data.get("model_id")  # 可选，如果不提供则使用默认模型
                
                if not message:
                    return {
                        "status": "error",
                        "message": "消息不能为空",
                        "timestamp": datetime.now().isoformat()
                    }
                
                # 获取LLM管理器
                llm_manager = self.main_controller.enhanced_llm_manager
                
                # 如果没有指定模型，使用默认模型
                if not model_id:
                    model_id = llm_manager.default_model
                
                if not model_id:
                    return {
                        "status": "error",
                        "message": "没有可用的AI模型",
                        "timestamp": datetime.now().isoformat()
                    }
                
                # 检查模型是否存在
                if model_id not in llm_manager.models:
                    return {
                        "status": "error",
                        "message": f"AI模型不存在: {model_id}",
                        "timestamp": datetime.now().isoformat()
                    }
                
                # 检查模型是否启用
                if not llm_manager.models[model_id].enabled:
                    return {
                        "status": "error",
                        "message": f"AI模型未启用: {model_id}",
                        "timestamp": datetime.now().isoformat()
                    }
                
                # 调用AI模型生成回复
                print(f"[DEBUG] Calling AI model {model_id} with message: {message[:50]}...")
                response = await llm_manager.generate(
                    prompt=message,
                    model_id=model_id,
                    task_type=TaskType.GENERAL
                )
                
                if response.success:
                    return {
                        "status": "success",
                        "message": "对话成功",
                        "data": {
                            "response": response.content,
                            "model_id": response.model_id,
                            "provider": response.provider.value,
                            "tokens_used": response.tokens_used,
                            "latency_ms": response.latency_ms,
                            "cost": response.cost
                        },
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"AI模型调用失败: {response.error_message}",
                        "timestamp": datetime.now().isoformat()
                    }
                    
            except Exception as e:
                print(f"[ERROR] AI对话失败: {e}")
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
                
                return {
                    "status": "success",
                    "message": "查询处理成功",
                    "data": result,
                    "timestamp": datetime.now().isoformat()
                }
                    
            except Exception as e:
                print(f"[ERROR] 自然语言查询失败: {e}")
                import traceback
                traceback.print_exc()
                return {
                    "status": "error",
                    "message": f"自然语言查询失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
        
        # AI记忆管理路由
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
                
                memory_manager = self.main_controller.ai_memory_manager
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
                
                memory_manager = self.main_controller.ai_memory_manager
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
                memory_manager = self.main_controller.ai_memory_manager
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
                memory_manager = self.main_controller.ai_memory_manager
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

        # WebSocket端点
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket端点"""
            await self._handle_websocket_connection(websocket)

        # 添加API路由到应用
        api_router.include_router(api_v1_router)
        self.app.include_router(api_router)

        # 添加策略API路由
        self.app.include_router(strategy_router)

        # 添加静态文件服务
        from fastapi.staticfiles import StaticFiles
        import os
        # 计算前端目录路径
        current_dir = os.path.dirname(__file__)
        api_dir = os.path.dirname(current_dir)
        modules_dir = os.path.dirname(api_dir)
        src_dir = os.path.dirname(modules_dir)
        frontend_dir = os.path.join(src_dir, "frontend", "dist")
        if os.path.exists(frontend_dir):
            self.app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
            logger.info(f"添加静态文件服务: {frontend_dir}")

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
            self.stats["websocket_connections"] += 1

        logger.info(f"WebSocket连接建立: {conn_id}")

        try:
            # 发送连接确认
            await websocket.send_json(
                {
                    "type": WebSocketEventType.CONNECT.value,
                    "connection_id": conn_id,
                    "timestamp": datetime.now().isoformat(),
                }
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
                        {
                            "type": WebSocketEventType.SUBSCRIBE.value,
                            "channels": channels,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                elif message_type == WebSocketEventType.UNSUBSCRIBE.value:
                    # 取消订阅
                    channels = data.get("channels", [])

                    for channel in channels:
                        if channel in connection.subscriptions:
                            connection.subscriptions.remove(channel)

                    logger.debug(f"WebSocket取消订阅: {conn_id} -> {channels}")

                    await websocket.send_json(
                        {
                            "type": WebSocketEventType.UNSUBSCRIBE.value,
                            "channels": channels,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                elif message_type == WebSocketEventType.HEARTBEAT.value:
                    # 心跳
                    await websocket.send_json(
                        {
                            "type": WebSocketEventType.HEARTBEAT.value,
                            "timestamp": datetime.now().isoformat(),
                        }
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
        print("FastAPI未安装，跳过示例")
        return

    # 创建API服务器
    api_server = APIServer(host="127.0.0.1", port=8000)
    await api_server.initialize()

    try:
        # 启动服务器
        success = await api_server.start()
        print(f"API服务器启动: {'成功' if success else '失败'}")

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
            print(f"API统计: {json.dumps(stats, indent=2, default=str)}")

            # 模拟运行一段时间
            print("API服务器运行中...按Ctrl+C停止")
            await asyncio.sleep(5)

            # 停止服务器
            await api_server.stop()

    finally:
        await api_server.cleanup()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
