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
import logging
import traceback
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import json
import hashlib
import secrets


try:
    from fastapi import (
        FastAPI, APIRouter, Depends, HTTPException, status,
        WebSocket, WebSocketDisconnect, Request, Response
    )
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from fastapi.responses import JSONResponse, HTMLResponse
    from fastapi.openapi.docs import get_swagger_ui_html
    from fastapi.openapi.utils import get_openapi
    from pydantic import BaseModel, Field, validator, confloat, conint
    from jose import JWTError, jwt
    from passlib.context import CryptContext
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
            "body": self.body
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
            "request_id": self.request_id
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
        
        @validator('side')
        def validate_side(cls, v):
            if v.lower() not in ['buy', 'sell']:
                raise ValueError('side必须是buy或sell')
            return v.lower()
        
        @validator('order_type')
        def validate_order_type(cls, v):
            valid_types = ['market', 'limit', 'stop', 'stop_limit']
            if v.lower() not in valid_types:
                raise ValueError(f'order_type必须是{valid_types}之一')
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
    
    def __init__(self, config_manager=None, host: str = "0.0.0.0", port: int = 8000):
        """
        初始化API服务器
        
        Args:
            config_manager: 配置管理器实例
            host: 监听主机
            port: 监听端口
        """
        self.config_manager = config_manager
        self.host = host
        self.port = port
        
        # FastAPI应用
        self.app: Optional[FastAPI] = None
        self.routers: Dict[str, APIRouter] = {}
        
        # 认证
        self.security = HTTPBearer()
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.secret_key = secrets.token_urlsafe(32)
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 30
        
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
            "avg_response_time_ms": 0.0
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
                openapi_url=None if not self.enable_swagger else "/openapi.json"
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
            # 这里实际应该启动uvicorn服务器
            # 但在这个模拟版本中，我们只标记为运行状态
            self._running = True
            
            logger.info(f"API服务器已启动，访问 http://{self.host}:{self.port}/docs 查看文档")
            return True
            
        except Exception as e:
            logger.error(f"API服务器启动失败: {e}")
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
    
    async def register_route(self, method: HTTPMethod, path: str, 
                           handler: Callable, tags: List[str] = None) -> bool:
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
                HTTPMethod.PATCH: self.app.patch
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
                        "timestamp": current_time.isoformat()
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
            stats.update({
                "websocket_active_connections": len(self.websocket_connections),
                "rate_limits": {k: v.__dict__ for k, v in self.rate_limits.items()},
                "uptime": self._get_uptime(),
                "timestamp": datetime.now().isoformat()
            })
            
            return stats
    
    # 认证相关方法
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """获取密码哈希"""
        return self.pwd_context.hash(password)
    
    def create_access_token(self, data: Dict[str, Any], 
                          expires_delta: Optional[timedelta] = None) -> str:
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
        self.app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*"]  # 生产环境应该限制
        )
        
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
                        content={"error": "Rate limit exceeded"}
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
        
        # 根路由
        @self.app.get("/", tags=["root"])
        async def root():
            """根端点"""
            return {
                "name": "全智能量化交易系统API",
                "version": "1.0.0",
                "status": "running",
                "timestamp": datetime.now().isoformat()
            }
        
        # 健康检查
        @self.app.get("/health", tags=["health"])
        async def health_check():
            """健康检查"""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "uptime": self._get_uptime()
            }
        
        # 指标端点
        @self.app.get("/metrics", tags=["metrics"])
        async def get_metrics():
            """获取指标"""
            stats = await self.get_api_stats()
            return stats
        
        # 认证路由
        @self.app.post("/auth/login", response_model=Token, tags=["auth"])
        async def login(request: LoginRequest):
            """用户登录"""
            # 这里应该从数据库验证用户
            # 为简化，我们使用模拟验证
            if request.username == "admin" and request.password == "admin123":
                access_token = self.create_access_token(
                    data={"sub": request.username, "role": "admin"}
                )
                return {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "expires_in": self.access_token_expire_minutes * 60
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="用户名或密码错误"
                )
        
        # 受保护的路由示例
        @self.app.get("/api/v1/protected", tags=["api"])
        async def protected_route(credentials: HTTPAuthorizationCredentials = Depends(self.security)):
            """受保护的路由"""
            token = credentials.credentials
            payload = await self.verify_token(token)
            
            if not payload:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="无效的令牌"
                )
            
            return {
                "message": f"欢迎 {payload.get('sub')}",
                "role": payload.get('role'),
                "timestamp": datetime.now().isoformat()
            }
        
        # WebSocket端点
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket端点"""
            await self._handle_websocket_connection(websocket)
        
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
            await websocket.send_json({
                "type": WebSocketEventType.CONNECT.value,
                "connection_id": conn_id,
                "timestamp": datetime.now().isoformat()
            })
            
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
                    
                    await websocket.send_json({
                        "type": WebSocketEventType.SUBSCRIBE.value,
                        "channels": channels,
                        "timestamp": datetime.now().isoformat()
                    })
                
                elif message_type == WebSocketEventType.UNSUBSCRIBE.value:
                    # 取消订阅
                    channels = data.get("channels", [])
                    
                    for channel in channels:
                        if channel in connection.subscriptions:
                            connection.subscriptions.remove(channel)
                    
                    logger.debug(f"WebSocket取消订阅: {conn_id} -> {channels}")
                    
                    await websocket.send_json({
                        "type": WebSocketEventType.UNSUBSCRIBE.value,
                        "channels": channels,
                        "timestamp": datetime.now().isoformat()
                    })
                
                elif message_type == WebSocketEventType.HEARTBEAT.value:
                    # 心跳
                    await websocket.send_json({
                        "type": WebSocketEventType.HEARTBEAT.value,
                        "timestamp": datetime.now().isoformat()
                    })
                
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
                    "timestamp": datetime.now().isoformat()
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
                    "timestamp": datetime.now().isoformat()
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