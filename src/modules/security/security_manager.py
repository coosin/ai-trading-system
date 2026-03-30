"""
认证和安全系统 - JWT认证、RBAC和API密钥管理

核心功能：
1. JWT令牌认证
2. 基于角色的访问控制（RBAC）
3. API密钥管理
4. 用户会话管理
5. 权限验证
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


try:
    import jwt
    HAS_JWT = True
except ImportError:
    HAS_JWT = False
    logger.warning("PyJWT未安装，JWT功能将受限")


class UserRole(Enum):
    """用户角色"""
    ADMIN = "admin"
    TRADER = "trader"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Permission(Enum):
    """权限"""
    READ_SYSTEM = "read_system"
    WRITE_SYSTEM = "write_system"
    READ_TRADING = "read_trading"
    WRITE_TRADING = "write_trading"
    READ_STRATEGY = "read_strategy"
    WRITE_STRATEGY = "write_strategy"
    READ_RISK = "read_risk"
    WRITE_RISK = "write_risk"
    READ_DATA = "read_data"
    WRITE_DATA = "write_data"
    MANAGE_USERS = "manage_users"
    MANAGE_API_KEYS = "manage_api_keys"


# 角色权限映射
ROLE_PERMISSIONS = {
    UserRole.ADMIN: set(Permission),
    UserRole.TRADER: {
        Permission.READ_SYSTEM,
        Permission.READ_TRADING,
        Permission.WRITE_TRADING,
        Permission.READ_STRATEGY,
        Permission.READ_RISK,
        Permission.READ_DATA
    },
    UserRole.ANALYST: {
        Permission.READ_SYSTEM,
        Permission.READ_TRADING,
        Permission.READ_STRATEGY,
        Permission.WRITE_STRATEGY,
        Permission.READ_RISK,
        Permission.READ_DATA
    },
    UserRole.VIEWER: {
        Permission.READ_SYSTEM,
        Permission.READ_TRADING,
        Permission.READ_STRATEGY,
        Permission.READ_RISK,
        Permission.READ_DATA
    }
}


@dataclass
class User:
    """用户"""
    user_id: str
    username: str
    email: str
    role: UserRole
    password_hash: str
    salt: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: Permission) -> bool:
        """检查是否具有权限"""
        if self.role not in ROLE_PERMISSIONS:
            return False
        return permission in ROLE_PERMISSIONS[self.role]


@dataclass
class ApiKey:
    """API密钥"""
    key_id: str
    user_id: str
    key_name: str
    api_key: str
    api_secret_hash: str
    permissions: Set[Permission]
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: Permission) -> bool:
        """检查是否具有权限"""
        return permission in self.permissions


@dataclass
class Session:
    """用户会话"""
    session_id: str
    user_id: str
    token: str
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(hours=24))
    last_activity: datetime = field(default_factory=datetime.now)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """是否过期"""
        return datetime.now() > self.expires_at


class SecurityManager:
    """
    安全管理器
    
    负责：
    - 用户认证
    - JWT令牌管理
    - API密钥管理
    - 权限验证
    - 会话管理
    """

    def __init__(self, secret_key: str = None):
        """
        初始化安全管理器

        Args:
            secret_key: JWT签名密钥
        """
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 60
        self.refresh_token_expire_days = 7

        # 存储（实际应用中应使用数据库）
        self.users: Dict[str, User] = {}
        self.api_keys: Dict[str, ApiKey] = {}
        self.sessions: Dict[str, Session] = {}
        self.username_to_id: Dict[str, str] = {}

        # 锁
        self._lock = asyncio.Lock()
        self._initialized = False

        logger.info("安全管理器初始化完成")

    async def initialize(self) -> None:
        """初始化安全管理器"""
        if self._initialized:
            return

        logger.info("初始化安全管理器...")
        
        # 创建默认管理员用户
        await self._create_default_admin()
        
        self._initialized = True
        logger.info("安全管理器初始化完成")

    async def shutdown(self) -> None:
        """关闭安全管理器"""
        logger.info("关闭安全管理器...")
        
        # 清理过期会话
        await self._cleanup_expired_sessions()
        
        logger.info("安全管理器已关闭")

    async def _create_default_admin(self) -> None:
        """创建默认管理员用户"""
        admin_id = "admin_001"
        
        if admin_id in self.users:
            return

        # 创建默认管理员（密码：admin123）
        password = "admin123"
        salt = secrets.token_hex(16)
        password_hash = self._hash_password(password, salt)

        admin = User(
            user_id=admin_id,
            username="admin",
            email="admin@example.com",
            role=UserRole.ADMIN,
            password_hash=password_hash,
            salt=salt
        )

        async with self._lock:
            self.users[admin_id] = admin
            self.username_to_id[admin.username] = admin_id

        logger.info("创建默认管理员用户: admin / admin123")

    def _hash_password(self, password: str, salt: str) -> str:
        """
        哈希密码

        Args:
            password: 密码
            salt: 盐值

        Returns:
            哈希值
        """
        return hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()

    def _verify_password(self, password: str, password_hash: str, salt: str) -> bool:
        """
        验证密码

        Args:
            password: 密码
            password_hash: 密码哈希
            salt: 盐值

        Returns:
            是否验证成功
        """
        computed_hash = self._hash_password(password, salt)
        return hmac.compare_digest(computed_hash, password_hash)

    def _create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """
        创建访问令牌

        Args:
            data: 数据
            expires_delta: 过期时间

        Returns:
            JWT令牌
        """
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        
        to_encode.update({"exp": expire})
        
        if HAS_JWT:
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            return encoded_jwt
        else:
            # 回退：简单令牌
            return f"token_{secrets.token_urlsafe(32)}"

    def _decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        解码令牌

        Args:
            token: JWT令牌

        Returns:
            解码后的数据
        """
        if HAS_JWT:
            try:
                payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
                return payload
            except jwt.ExpiredSignatureError:
                logger.warning("令牌已过期")
                return None
            except jwt.InvalidTokenError:
                logger.warning("无效的令牌")
                return None
        else:
            # 回退：简单验证
            if token.startswith("token_"):
                return {"sub": "user", "exp": time.time() + 3600}
            return None

    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        认证用户

        Args:
            username: 用户名
            password: 密码

        Returns:
            用户对象或None
        """
        async with self._lock:
            user_id = self.username_to_id.get(username)
            if not user_id:
                return None

            user = self.users.get(user_id)
            if not user or not user.is_active:
                return None

            if not self._verify_password(password, user.password_hash, user.salt):
                return None

            return user

    async def create_session(self, user: User, ip_address: str = None, user_agent: str = None) -> Session:
        """
        创建用户会话

        Args:
            user: 用户
            ip_address: IP地址
            user_agent: 用户代理

        Returns:
            会话对象
        """
        session_id = secrets.token_urlsafe(32)
        
        # 创建JWT令牌
        token_data = {
            "sub": user.user_id,
            "username": user.username,
            "role": user.role.value
        }
        token = self._create_access_token(token_data)

        session = Session(
            session_id=session_id,
            user_id=user.user_id,
            token=token,
            ip_address=ip_address,
            user_agent=user_agent
        )

        async with self._lock:
            self.sessions[session_id] = session

        logger.info(f"创建会话: {user.username}")
        return session

    async def validate_session(self, token: str) -> Optional[Session]:
        """
        验证会话

        Args:
            token: 令牌

        Returns:
            会话对象或None
        """
        payload = self._decode_token(token)
        if not payload:
            return None

        # 查找会话
        async with self._lock:
            for session in self.sessions.values():
                if session.token == token and not session.is_expired:
                    session.last_activity = datetime.now()
                    return session

        return None

    async def get_user_from_token(self, token: str) -> Optional[User]:
        """
        从令牌获取用户

        Args:
            token: 令牌

        Returns:
            用户对象或None
        """
        session = await self.validate_session(token)
        if not session:
            return None

        async with self._lock:
            return self.users.get(session.user_id)

    async def invalidate_session(self, token: str) -> bool:
        """
        使会话失效

        Args:
            token: 令牌

        Returns:
            是否成功
        """
        async with self._lock:
            for session_id, session in list(self.sessions.items()):
                if session.token == token:
                    del self.sessions[session_id]
                    logger.info(f"会话失效: {session.user_id}")
                    return True

        return False

    async def create_user(self, username: str, email: str, password: str, role: UserRole) -> Optional[User]:
        """
        创建用户

        Args:
            username: 用户名
            email: 邮箱
            password: 密码
            role: 角色

        Returns:
            用户对象或None
        """
        async with self._lock:
            if username in self.username_to_id:
                logger.warning(f"用户名已存在: {username}")
                return None

            user_id = f"user_{secrets.token_hex(8)}"
            salt = secrets.token_hex(16)
            password_hash = self._hash_password(password, salt)

            user = User(
                user_id=user_id,
                username=username,
                email=email,
                role=role,
                password_hash=password_hash,
                salt=salt
            )

            self.users[user_id] = user
            self.username_to_id[username] = user_id

            logger.info(f"创建用户: {username}")
            return user

    async def create_api_key(self, user_id: str, key_name: str, permissions: List[Permission], 
                           expires_days: int = 30) -> Optional[ApiKey]:
        """
        创建API密钥

        Args:
            user_id: 用户ID
            key_name: 密钥名称
            permissions: 权限列表
            expires_days: 过期天数

        Returns:
            API密钥对象或None
        """
        async with self._lock:
            if user_id not in self.users:
                logger.warning(f"用户不存在: {user_id}")
                return None

            key_id = f"key_{secrets.token_hex(8)}"
            api_key = f"ak_{secrets.token_urlsafe(32)}"
            api_secret = secrets.token_urlsafe(32)
            api_secret_hash = hashlib.sha256(api_secret.encode()).hex()

            expires_at = None
            if expires_days > 0:
                expires_at = datetime.now() + timedelta(days=expires_days)

            api_key_obj = ApiKey(
                key_id=key_id,
                user_id=user_id,
                key_name=key_name,
                api_key=api_key,
                api_secret_hash=api_secret_hash,
                permissions=set(permissions),
                expires_at=expires_at
            )

            self.api_keys[key_id] = api_key_obj

            logger.info(f"创建API密钥: {key_name} for {user_id}")
            
            # 返回包含明文密钥的对象（仅在创建时）
            api_key_obj.metadata["plain_secret"] = api_secret
            return api_key_obj

    async def validate_api_key(self, api_key: str, api_secret: str) -> Optional[ApiKey]:
        """
        验证API密钥

        Args:
            api_key: API密钥
            api_secret: API密钥密码

        Returns:
            API密钥对象或None
        """
        async with self._lock:
            for key_obj in self.api_keys.values():
                if key_obj.api_key == api_key and key_obj.is_active:
                    if key_obj.expires_at and datetime.now() > key_obj.expires_at:
                        logger.warning("API密钥已过期")
                        return None

                    secret_hash = hashlib.sha256(api_secret.encode()).hex()
                    if hmac.compare_digest(secret_hash, key_obj.api_secret_hash):
                        key_obj.last_used_at = datetime.now()
                        return key_obj

        return None

    async def check_permission(self, user_or_key: Any, permission: Permission) -> bool:
        """
        检查权限

        Args:
            user_or_key: 用户或API密钥对象
            permission: 权限

        Returns:
            是否具有权限
        """
        if isinstance(user_or_key, User):
            return user_or_key.has_permission(permission)
        elif isinstance(user_or_key, ApiKey):
            return user_or_key.has_permission(permission)
        return False

    async def _cleanup_expired_sessions(self) -> None:
        """清理过期会话"""
        now = datetime.now()
        expired_ids = []

        async with self._lock:
            for session_id, session in self.sessions.items():
                if session.is_expired:
                    expired_ids.append(session_id)

            for session_id in expired_ids:
                del self.sessions[session_id]

        if expired_ids:
            logger.info(f"清理过期会话: {len(expired_ids)}")

    async def get_security_status(self) -> Dict[str, Any]:
        """
        获取安全状态

        Returns:
            状态信息
        """
        async with self._lock:
            return {
                "users": len(self.users),
                "api_keys": len(self.api_keys),
                "active_sessions": len(self.sessions),
                "jwt_enabled": HAS_JWT
            }


# 使用示例
async def example_usage():
    """安全管理器使用示例"""

    # 创建安全管理器
    security = SecurityManager()
    await security.initialize()

    try:
        # 认证用户
        user = await security.authenticate_user("admin", "admin123")
        if user:
            print(f"认证成功: {user.username}")

            # 创建会话
            session = await security.create_session(user)
            print(f"会话令牌: {session.token[:50]}...")

            # 验证会话
            validated_session = await security.validate_session(session.token)
            if validated_session:
                print(f"会话验证成功")

            # 检查权限
            has_perm = await security.check_permission(user, Permission.MANAGE_USERS)
            print(f"具有管理用户权限: {has_perm}")

            # 创建API密钥
            api_key = await security.create_api_key(
                user.user_id,
                "Trading API",
                [Permission.READ_TRADING, Permission.WRITE_TRADING]
            )
            if api_key:
                print(f"API密钥创建: {api_key.api_key}")
                print(f"API密钥密码: {api_key.metadata.get('plain_secret')}")

    finally:
        await security.shutdown()


if __name__ == "__main__":
    asyncio.run(example_usage())
