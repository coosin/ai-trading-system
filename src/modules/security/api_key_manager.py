"""
API密钥管理器 - 企业级API认证和授权

功能：
1. API密钥生成和管理
2. 基于角色的访问控制 (RBAC)
3. HMAC-SHA256签名验证
4. API调用审计日志
5. 密钥权限管理
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import sqlite3
import time
import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class UserRole(Enum):
    """用户角色"""
    ADMIN = "admin"           # 管理员 - 所有权限
    TRADER = "trader"         # 交易员 - 交易权限
    ANALYST = "analyst"       # 分析师 - 查看权限
    VIEWER = "viewer"         # 观察者 - 只读权限
    API = "api"               # API用户 - 程序化访问


class Permission(Enum):
    """权限列表"""
    # 系统权限
    SYSTEM_READ = "system:read"
    SYSTEM_WRITE = "system:write"
    SYSTEM_ADMIN = "system:admin"
    
    # 交易权限
    TRADE_READ = "trade:read"
    TRADE_EXECUTE = "trade:execute"
    TRADE_CANCEL = "trade:cancel"
    
    # 策略权限
    STRATEGY_READ = "strategy:read"
    STRATEGY_CREATE = "strategy:create"
    STRATEGY_MODIFY = "strategy:modify"
    STRATEGY_DELETE = "strategy:delete"
    
    # 资金权限
    FUNDS_READ = "funds:read"
    FUNDS_TRANSFER = "funds:transfer"
    FUNDS_WITHDRAW = "funds:withdraw"
    
    # 数据权限
    DATA_READ = "data:read"
    DATA_EXPORT = "data:export"
    
    # 用户管理权限
    USER_READ = "user:read"
    USER_CREATE = "user:create"
    USER_MODIFY = "user:modify"
    USER_DELETE = "user:delete"


# 角色权限映射
ROLE_PERMISSIONS = {
    UserRole.ADMIN: [p for p in Permission],  # 所有权限
    UserRole.TRADER: [
        Permission.SYSTEM_READ,
        Permission.TRADE_READ, Permission.TRADE_EXECUTE, Permission.TRADE_CANCEL,
        Permission.STRATEGY_READ, Permission.STRATEGY_CREATE, Permission.STRATEGY_MODIFY,
        Permission.FUNDS_READ,
        Permission.DATA_READ, Permission.DATA_EXPORT,
    ],
    UserRole.ANALYST: [
        Permission.SYSTEM_READ,
        Permission.TRADE_READ,
        Permission.STRATEGY_READ,
        Permission.FUNDS_READ,
        Permission.DATA_READ, Permission.DATA_EXPORT,
    ],
    UserRole.VIEWER: [
        Permission.SYSTEM_READ,
        Permission.TRADE_READ,
        Permission.STRATEGY_READ,
        Permission.DATA_READ,
    ],
    UserRole.API: [
        Permission.TRADE_READ, Permission.TRADE_EXECUTE, Permission.TRADE_CANCEL,
        Permission.STRATEGY_READ,
        Permission.FUNDS_READ,
        Permission.DATA_READ,
    ],
}


@dataclass
class APIKey:
    """API密钥"""
    key_id: str
    api_key: str
    api_secret: str
    salt: str
    user_id: str
    role: UserRole
    permissions: List[Permission]
    name: str
    description: str
    enabled: bool
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    usage_count: int
    ip_whitelist: List[str]
    rate_limit: int  # 每分钟请求数
    allowed_endpoints: List[str]


@dataclass
class APIAuditLog:
    """API审计日志"""
    log_id: str
    api_key: str
    user_id: str
    timestamp: datetime
    method: str
    path: str
    ip_address: str
    user_agent: str
    request_body: Optional[str]
    response_status: int
    response_time_ms: int
    error_message: Optional[str]


class APIKeyManager:
    """
    API密钥管理器
    
    功能：
    1. API密钥生成和管理
    2. 权限验证
    3. 签名验证
    4. 审计日志
    """
    
    def __init__(self, db_path: str = "data/api_keys.db"):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._initialized = False
        
        # 缓存
        self._key_cache: Dict[str, APIKey] = {}
        self._cache_ttl = 300  # 5分钟
        self._cache_timestamps: Dict[str, float] = {}
    
    async def initialize(self):
        """初始化"""
        logger.info("初始化API密钥管理器...")
        await self._init_database()
        self._initialized = True
        logger.info("API密钥管理器初始化完成")
    
    async def _init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # API密钥表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id TEXT PRIMARY KEY,
                api_key TEXT UNIQUE NOT NULL,
                api_secret_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                permissions TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                last_used_at TEXT,
                usage_count INTEGER DEFAULT 0,
                ip_whitelist TEXT,
                rate_limit INTEGER DEFAULT 60,
                allowed_endpoints TEXT
            )
        ''')
        
        # 审计日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_audit_logs (
                log_id TEXT PRIMARY KEY,
                api_key TEXT NOT NULL,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                user_agent TEXT,
                request_body TEXT,
                response_status INTEGER,
                response_time_ms INTEGER,
                error_message TEXT
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys(api_key)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON api_audit_logs(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_api_key ON api_audit_logs(api_key)')
        
        conn.commit()
        conn.close()
        logger.info("API密钥数据库初始化完成")
    
    async def generate_api_key(
        self,
        user_id: str,
        role: UserRole,
        name: str,
        description: str = "",
        expires_days: Optional[int] = None,
        ip_whitelist: List[str] = None,
        rate_limit: int = 60,
        custom_permissions: List[Permission] = None,
        allowed_endpoints: List[str] = None
    ) -> Dict[str, str]:
        """
        生成API密钥
        
        Returns:
            {
                "key_id": "...",
                "api_key": "...",
                "api_secret": "...",  # 只返回一次
                "role": "...",
                "permissions": [...],
                "allowed_endpoints": [...]
            }
        """
        async with self._lock:
            key_id = str(uuid4())
            api_key = f"ak_{secrets.token_urlsafe(32)}"
            api_secret = secrets.token_urlsafe(64)
            
            # 生成盐和哈希
            salt = secrets.token_bytes(32)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
                backend=default_backend()
            )
            api_secret_hash = base64.b64encode(kdf.derive(api_secret.encode())).decode()
            salt_encoded = base64.b64encode(salt).decode()
            
            # 确定权限
            if custom_permissions:
                permissions = custom_permissions
            else:
                permissions = ROLE_PERMISSIONS.get(role, [])
            
            # 计算过期时间
            expires_at = None
            if expires_days:
                expires_at = datetime.now() + timedelta(days=expires_days)
            
            # 存储到数据库
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO api_keys 
                (key_id, api_key, api_secret_hash, salt, user_id, role, permissions, name, description,
                 enabled, created_at, expires_at, ip_whitelist, rate_limit, allowed_endpoints)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                key_id,
                api_key,
                api_secret_hash,
                salt_encoded,
                user_id,
                role.value,
                json.dumps([p.value for p in permissions]),
                name,
                description,
                1,
                datetime.now().isoformat(),
                expires_at.isoformat() if expires_at else None,
                json.dumps(ip_whitelist or []),
                rate_limit,
                json.dumps(allowed_endpoints or [])
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"生成API密钥: {key_id} 用户: {user_id} 角色: {role.value}")
            
            return {
                "key_id": key_id,
                "api_key": api_key,
                "api_secret": api_secret,  # 只返回一次，请妥善保存
                "role": role.value,
                "permissions": [p.value for p in permissions],
                "allowed_endpoints": allowed_endpoints or []
            }
    
    async def verify_api_key(
        self,
        api_key: str,
        signature: str,
        timestamp: str,
        method: str,
        path: str,
        body: str = "",
        ip_address: str = None,
        user_agent: str = None
    ) -> Optional[APIKey]:
        """
        验证API密钥和签名
        
        Args:
            api_key: API密钥
            signature: HMAC-SHA256签名
            timestamp: 时间戳（毫秒）
            method: HTTP方法
            path: 请求路径
            body: 请求体
            ip_address: IP地址
            user_agent: 用户代理
        
        Returns:
            APIKey对象或None
        """
        # 检查时间戳（防止重放攻击，5分钟有效期）
        try:
            ts = int(timestamp)
            now = int(time.time() * 1000)
            if abs(now - ts) > 300000:  # 5分钟
                logger.warning(f"API请求时间戳过期: {api_key}")
                return None
        except ValueError:
            logger.warning(f"无效的时间戳: {timestamp}")
            return None
        
        # 获取API密钥信息
        key_info = await self._get_api_key_info(api_key)
        if not key_info:
            logger.warning(f"API密钥不存在: {api_key}")
            return None
        
        # 检查是否启用
        if not key_info.enabled:
            logger.warning(f"API密钥已禁用: {api_key}")
            return None
        
        # 检查是否过期
        if key_info.expires_at and datetime.now() > key_info.expires_at:
            logger.warning(f"API密钥已过期: {api_key}")
            return None
        
        # 检查IP白名单
        if key_info.ip_whitelist and ip_address:
            if ip_address not in key_info.ip_whitelist:
                logger.warning(f"IP地址不在白名单中: {ip_address}")
                return None
        
        # 检查允许的端点
        if key_info.allowed_endpoints:
            endpoint = path.split('?')[0]  # 去掉查询参数
            if endpoint not in key_info.allowed_endpoints:
                logger.warning(f"端点未被允许: {endpoint}")
                return None
        
        # 验证签名
        message = f"{timestamp}{method.upper()}{path}{body}"
        expected_signature = hmac.new(
            key_info.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            logger.warning(f"API签名验证失败: {api_key}")
            return None
        
        # 更新最后使用时间
        await self._update_last_used(api_key)
        
        return key_info
    
    async def _get_api_key_info(self, api_key: str) -> Optional[APIKey]:
        """获取API密钥信息（带缓存）"""
        # 检查缓存
        now = time.time()
        if api_key in self._key_cache:
            if now - self._cache_timestamps.get(api_key, 0) < self._cache_ttl:
                return self._key_cache[api_key]
        
        # 从数据库获取
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM api_keys WHERE api_key = ?",
            (api_key,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        key_info = APIKey(
            key_id=row[0],
            api_key=row[1],
            api_secret=row[2],  # 存储的是hash，实际验证时需要重新输入
            salt=row[3],
            user_id=row[4],
            role=UserRole(row[5]),
            permissions=[Permission(p) for p in json.loads(row[6])],
            name=row[7],
            description=row[8] or "",
            enabled=bool(row[9]),
            created_at=datetime.fromisoformat(row[10]),
            expires_at=datetime.fromisoformat(row[11]) if row[11] else None,
            last_used_at=datetime.fromisoformat(row[12]) if row[12] else None,
            usage_count=row[13],
            ip_whitelist=json.loads(row[14]) if row[14] else [],
            rate_limit=row[15],
            allowed_endpoints=json.loads(row[16]) if row[16] else []
        )
        
        # 更新缓存
        self._key_cache[api_key] = key_info
        self._cache_timestamps[api_key] = now
        
        return key_info
    
    async def _update_last_used(self, api_key: str):
        """更新最后使用时间"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE api_keys 
            SET last_used_at = ?, usage_count = usage_count + 1
            WHERE api_key = ?
        ''', (datetime.now().isoformat(), api_key))
        
        conn.commit()
        conn.close()
    
    async def check_permission(self, api_key: str, required_permission: Permission) -> bool:
        """检查权限"""
        key_info = await self._get_api_key_info(api_key)
        if not key_info:
            return False
        
        return required_permission in key_info.permissions
    
    async def revoke_api_key(self, key_id: str) -> bool:
        """吊销API密钥"""
        async with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE api_keys SET enabled = 0 WHERE key_id = ?",
                (key_id,)
            )
            
            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            
            if success:
                # 清除缓存
                for key, info in list(self._key_cache.items()):
                    if info.key_id == key_id:
                        del self._key_cache[key]
                        del self._cache_timestamps[key]
                
                logger.info(f"吊销API密钥: {key_id}")
            
            return success
    
    async def delete_api_key(self, key_id: str) -> bool:
        """删除API密钥"""
        async with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "DELETE FROM api_keys WHERE key_id = ?",
                (key_id,)
            )
            
            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            
            if success:
                # 清除缓存
                for key, info in list(self._key_cache.items()):
                    if info.key_id == key_id:
                        del self._key_cache[key]
                        del self._cache_timestamps[key]
                
                logger.info(f"删除API密钥: {key_id}")
            
            return success
    
    async def get_user_api_keys(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的所有API密钥"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT key_id, api_key, role, name, description, enabled, created_at, expires_at, last_used_at, usage_count FROM api_keys WHERE user_id = ?",
            (user_id,)
        )
        
        keys = []
        for row in cursor.fetchall():
            keys.append({
                "key_id": row[0],
                "api_key": row[1][:20] + "...",  # 部分隐藏
                "role": row[2],
                "name": row[3],
                "description": row[4],
                "enabled": bool(row[5]),
                "created_at": row[6],
                "expires_at": row[7],
                "last_used_at": row[8],
                "usage_count": row[9]
            })
        
        conn.close()
        return keys
    
    async def log_api_call(
        self,
        api_key: str,
        user_id: str,
        method: str,
        path: str,
        ip_address: str,
        user_agent: str,
        request_body: Optional[str],
        response_status: int,
        response_time_ms: int,
        error_message: Optional[str] = None
    ):
        """记录API调用日志"""
        log_id = str(uuid4())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO api_audit_logs 
            (log_id, api_key, user_id, timestamp, method, path, ip_address, user_agent,
             request_body, response_status, response_time_ms, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            log_id,
            api_key,
            user_id,
            datetime.now().isoformat(),
            method,
            path,
            ip_address,
            user_agent,
            request_body,
            response_status,
            response_time_ms,
            error_message
        ))
        
        conn.commit()
        conn.close()
    
    async def get_audit_logs(
        self,
        api_key: Optional[str] = None,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取审计日志"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM api_audit_logs WHERE 1=1"
        params = []
        
        if api_key:
            query += " AND api_key = ?"
            params.append(api_key)
        
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        
        logs = []
        for row in cursor.fetchall():
            logs.append({
                "log_id": row[0],
                "api_key": row[1][:20] + "...",
                "user_id": row[2],
                "timestamp": row[3],
                "method": row[4],
                "path": row[5],
                "ip_address": row[6],
                "user_agent": row[7],
                "response_status": row[9],
                "response_time_ms": row[10],
                "error_message": row[11]
            })
        
        conn.close()
        return logs
    
    async def cleanup_old_logs(self, days: int = 30) -> int:
        """清理旧日志"""
        cutoff = datetime.now() - timedelta(days=days)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "DELETE FROM api_audit_logs WHERE timestamp < ?",
            (cutoff.isoformat(),)
        )
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        logger.info(f"清理了 {deleted} 条旧审计日志")
        return deleted


# 全局API密钥管理器
_api_key_manager: Optional[APIKeyManager] = None


async def get_api_key_manager() -> APIKeyManager:
    """获取API密钥管理器实例"""
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager()
        await _api_key_manager.initialize()
    return _api_key_manager
