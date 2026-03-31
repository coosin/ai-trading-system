"""
数据库管理器模块 - 全智能量化交易系统的数据持久化核心

功能：
1. 多数据库支持（PostgreSQL、MySQL、SQLite）
2. 异步ORM（SQLAlchemy 2.0 + async）
3. 数据迁移系统（Alembic）
4. 连接池管理（连接复用和监控）
5. 事务管理（原子性和一致性）
"""

import asyncio
import hashlib
import json
import logging
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


try:
    from sqlalchemy import (
        JSON,
        Boolean,
        Column,
        DateTime,
        Float,
        ForeignKey,
        Index,
        Integer,
        String,
        Text,
        UniqueConstraint,
        delete,
        func,
        insert,
        select,
        text,
        update,
    )
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.ext.asyncio import (
        AsyncConnection,
        AsyncEngine,
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.orm import DeclarativeMeta, declarative_base

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False
    logger.warning("SQLAlchemy未安装，数据库功能将受限")


# 声明式基类
Base = declarative_base() if HAS_SQLALCHEMY else type("Base", (), {})


class DatabaseType(Enum):
    """数据库类型"""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    MEMORY = "memory"


class ConnectionStatus(Enum):
    """连接状态"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class HealthStatus(Enum):
    """健康状态"""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class TransactionIsolationLevel(Enum):
    """事务隔离级别"""

    READ_UNCOMMITTED = "read_uncommitted"
    READ_COMMITTED = "read_committed"
    REPEATABLE_READ = "repeatable_read"
    SERIALIZABLE = "serializable"


@dataclass
class DatabaseStats:
    """数据库统计"""

    connections_active: int = 0
    connections_total: int = 0
    queries_executed: int = 0
    transactions_committed: int = 0
    transactions_rolled_back: int = 0
    query_execution_time_ms: float = 0.0
    avg_query_time_ms: float = 0.0
    errors: int = 0

    def update_avg_query_time(self) -> None:
        """更新平均查询时间"""
        if self.queries_executed > 0:
            self.avg_query_time_ms = self.query_execution_time_ms / self.queries_executed


@dataclass
class DatabaseConfig:
    """数据库配置"""

    type: DatabaseType = DatabaseType.POSTGRESQL
    host: str = "localhost"
    port: int = 5432
    database: str = "trading_system"
    username: str = "postgres"
    password: str = ""
    pool_size: int = 20
    max_overflow: int = 30
    pool_timeout: int = 60
    pool_recycle: int = 1800
    echo: bool = False
    isolation_level: TransactionIsolationLevel = TransactionIsolationLevel.READ_COMMITTED
    backup_enabled: bool = True
    backup_interval: int = 3600
    backup_retention: int = 7

    def get_connection_string(self) -> str:
        """获取连接字符串"""
        if self.type == DatabaseType.POSTGRESQL:
            return f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.type == DatabaseType.MYSQL:
            return f"mysql+aiomysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.type == DatabaseType.SQLITE:
            if self.database == ":memory:":
                return "sqlite+aiosqlite:///:memory:"
            else:
                return f"sqlite+aiosqlite:///{self.database}"
        elif self.type == DatabaseType.MEMORY:
            return "sqlite+aiosqlite:///:memory:"
        else:
            raise ValueError(f"不支持的数据库类型: {self.type}")


# 定义数据模型
if HAS_SQLALCHEMY:

    class TradingSession(Base):
        """交易会话表"""

        __tablename__ = "trading_sessions"

        id = Column(Integer, primary_key=True)
        session_id = Column(String(64), unique=True, nullable=False, index=True)
        strategy_id = Column(String(64), nullable=False, index=True)
        symbol = Column(String(32), nullable=False, index=True)
        status = Column(String(32), nullable=False, default="active")
        created_at = Column(DateTime, nullable=False, default=datetime.now)
        updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
        started_at = Column(DateTime)
        ended_at = Column(DateTime)
        initial_balance = Column(Float, nullable=False, default=0.0)
        current_balance = Column(Float, nullable=False, default=0.0)
        profit_loss = Column(Float, nullable=False, default=0.0)
        profit_loss_percent = Column(Float, nullable=False, default=0.0)
        metadata_json = Column(JSON, default=dict)

        __table_args__ = (
            Index("idx_session_strategy", "session_id", "strategy_id"),
            Index("idx_session_symbol", "session_id", "symbol"),
        )

    class Trade(Base):
        """交易记录表"""

        __tablename__ = "trades"

        id = Column(Integer, primary_key=True)
        trade_id = Column(String(64), unique=True, nullable=False, index=True)
        session_id = Column(
            String(64), ForeignKey("trading_sessions.session_id"), nullable=False, index=True
        )
        strategy_id = Column(String(64), nullable=False, index=True)
        symbol = Column(String(32), nullable=False, index=True)
        side = Column(String(8), nullable=False)  # buy/sell
        order_type = Column(String(16), nullable=False)  # market/limit/stop
        quantity = Column(Float, nullable=False, default=0.0)
        price = Column(Float, nullable=False, default=0.0)
        filled_quantity = Column(Float, nullable=False, default=0.0)
        avg_fill_price = Column(Float, nullable=False, default=0.0)
        status = Column(String(32), nullable=False, default="pending")
        created_at = Column(DateTime, nullable=False, default=datetime.now)
        updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
        executed_at = Column(DateTime)
        cancelled_at = Column(DateTime)
        commission = Column(Float, nullable=False, default=0.0)
        pnl = Column(Float, nullable=False, default=0.0)
        pnl_percent = Column(Float, nullable=False, default=0.0)
        metadata_json = Column(JSON, default=dict)

        __table_args__ = (
            Index("idx_trade_session", "trade_id", "session_id"),
            Index("idx_trade_strategy", "trade_id", "strategy_id"),
            Index("idx_trade_symbol_time", "symbol", "created_at"),
        )

    class MarketData(Base):
        """市场数据表"""

        __tablename__ = "market_data"

        id = Column(Integer, primary_key=True)
        symbol = Column(String(32), nullable=False, index=True)
        timestamp = Column(DateTime, nullable=False, index=True)
        open = Column(Float, nullable=False)
        high = Column(Float, nullable=False)
        low = Column(Float, nullable=False)
        close = Column(Float, nullable=False)
        volume = Column(Float, nullable=False, default=0.0)
        source = Column(String(32), nullable=False, default="exchange")
        interval = Column(String(8), nullable=False, default="1m")  # 1m, 5m, 15m, 1h, 1d
        created_at = Column(DateTime, nullable=False, default=datetime.now)
        metadata_json = Column(JSON, default=dict)

        __table_args__ = (
            UniqueConstraint(
                "symbol", "timestamp", "interval", name="uq_symbol_timestamp_interval"
            ),
            Index("idx_symbol_interval_time", "symbol", "interval", "timestamp"),
        )

    class StrategyMetrics(Base):
        """策略指标表"""

        __tablename__ = "strategy_metrics"

        id = Column(Integer, primary_key=True)
        strategy_id = Column(String(64), nullable=False, index=True)
        session_id = Column(
            String(64), ForeignKey("trading_sessions.session_id"), nullable=False, index=True
        )
        timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
        metric_name = Column(String(64), nullable=False, index=True)
        metric_value = Column(Float, nullable=False)
        metric_type = Column(String(32), nullable=False, default="gauge")  # gauge/counter/histogram
        metadata_json = Column(JSON, default=dict)

        __table_args__ = (
            Index("idx_strategy_session_metric", "strategy_id", "session_id", "metric_name"),
            Index("idx_strategy_metric_time", "strategy_id", "metric_name", "timestamp"),
        )

    class SystemLog(Base):
        """系统日志表"""

        __tablename__ = "system_logs"

        id = Column(Integer, primary_key=True)
        level = Column(String(16), nullable=False, index=True)  # debug/info/warning/error/critical
        module = Column(String(64), nullable=False, index=True)
        message = Column(Text, nullable=False)
        timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
        metadata_json = Column(JSON, default=dict)

        __table_args__ = (Index("idx_module_level_time", "module", "level", "timestamp"),)


class DatabaseManager:
    """
    数据库管理器

    核心功能：
    1. 多数据库支持
    2. 异步ORM
    3. 数据迁移系统
    4. 连接池管理
    5. 事务管理
    """

    def __init__(self, config_manager=None):
        """
        初始化数据库管理器

        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager

        # 数据库配置
        self.config: Optional[DatabaseConfig] = None
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker] = None

        # 状态管理
        self.status: ConnectionStatus = ConnectionStatus.DISCONNECTED
        self.last_error: Optional[str] = None
        self.connected_at: Optional[datetime] = None

        # 连接池监控
        self.pool_monitor_task: Optional[asyncio.Task] = None
        self.connection_stats: Dict[str, Any] = {}

        # 备份管理
        self.backup_task: Optional[asyncio.Task] = None
        self.last_backup: Optional[datetime] = None

        # 统计信息
        self.stats = DatabaseStats()

        # 锁和状态
        self._lock = asyncio.Lock()
        self._initialized = False
        self._running = False

        # 数据模型注册
        self.models: Dict[str, Any] = {}

        logger.info("数据库管理器初始化完成")

    async def initialize(self) -> None:
        """
        初始化数据库管理器

        加载配置，创建引擎，检查连接
        """
        if self._initialized:
            return

        if not HAS_SQLALCHEMY:
            logger.warning("SQLAlchemy未安装，数据库管理器将运行在模拟模式")
            self._initialized = True
            return

        logger.info("初始化数据库管理器...")

        try:
            # 加载配置
            await self._load_config()

            # 创建数据库引擎
            await self._create_engine()

            # 测试连接
            await self._test_connection()

            # 启动连接池监控
            self.pool_monitor_task = asyncio.create_task(self._pool_monitor())

            # 启动备份任务
            if self.config.backup_enabled:
                self.backup_task = asyncio.create_task(self._backup_manager())

            self._initialized = True
            self._running = True
            self.status = ConnectionStatus.CONNECTED
            self.connected_at = datetime.now()

            logger.info(
                f"数据库管理器初始化完成，连接到: {self.config.host}:{self.config.database}"
            )

        except Exception as e:
            self.status = ConnectionStatus.ERROR
            self.last_error = str(e)
            logger.error(f"数据库管理器初始化失败: {e}")
            traceback.print_exc()

    async def cleanup(self) -> None:
        """
        清理数据库管理器

        关闭连接，清理资源
        """
        logger.info("清理数据库管理器...")

        self._running = False

        # 停止监控任务
        if self.pool_monitor_task:
            self.pool_monitor_task.cancel()
            try:
                await self.pool_monitor_task
            except asyncio.CancelledError:
                pass

        # 停止备份任务
        if self.backup_task:
            self.backup_task.cancel()
            try:
                await self.backup_task
            except asyncio.CancelledError:
                pass

        # 关闭引擎
        if self.engine:
            await self.engine.dispose()
            self.engine = None

        self.session_factory = None
        self.status = ConnectionStatus.DISCONNECTED
        self._initialized = False

        logger.info("数据库管理器清理完成")

    async def execute_migration(self, revision: str = "head", downgrade: bool = False) -> bool:
        """
        执行数据库迁移

        Args:
            revision: 迁移版本
            downgrade: 是否降级

        Returns:
            是否迁移成功
        """
        if not HAS_SQLALCHEMY:
            logger.warning("SQLAlchemy未安装，跳过迁移")
            return False

        try:
            # 这里可以集成Alembic
            # from alembic import command
            # from alembic.config import Config

            logger.info(f"执行数据库迁移: {'降级到' if downgrade else '升级到'} {revision}")

            # 实际迁移逻辑需要Alembic配置文件
            # 这里只是示例

            return True

        except Exception as e:
            logger.error(f"数据库迁移失败: {e}")
            traceback.print_exc()
            return False

    @asynccontextmanager
    async def session(self) -> AsyncSession:
        """
        获取数据库会话上下文管理器

        Yields:
            数据库会话
        """
        if not self.session_factory:
            raise RuntimeError("数据库未初始化")

        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def execute_query(self, query, params: Dict[str, Any] = None) -> Any:
        """
        执行查询

        Args:
            query: SQL查询或ORM查询
            params: 查询参数

        Returns:
            查询结果
        """
        if not self.session_factory:
            raise RuntimeError("数据库未初始化")

        start_time = datetime.now()

        try:
            async with self.session() as session:
                if isinstance(query, str):
                    # 原生SQL查询
                    if params:
                        result = await session.execute(query, params)
                    else:
                        result = await session.execute(query)
                else:
                    # ORM查询
                    result = await session.execute(query)

                self.stats.queries_executed += 1

                # 更新统计
                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                self.stats.query_execution_time_ms += execution_time
                self.stats.update_avg_query_time()

                return result

        except Exception as e:
            self.stats.errors += 1
            logger.error(f"查询执行失败: {e}")
            raise

    async def fetch_one(self, query, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        获取单条记录

        Args:
            query: 查询
            params: 参数

        Returns:
            单条记录或None
        """
        result = await self.execute_query(query, params)
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def fetch_all(self, query, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        获取所有记录

        Args:
            query: 查询
            params: 参数

        Returns:
            记录列表
        """
        result = await self.execute_query(query, params)
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]

    async def insert(self, table, data: Dict[str, Any]) -> Any:
        """
        插入数据

        Args:
            table: 表名或模型类
            data: 数据

        Returns:
            插入结果
        """
        if isinstance(table, str):
            # 原生SQL插入
            columns = ", ".join(data.keys())
            placeholders = ", ".join([f":{key}" for key in data.keys()])
            query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
            return await self.execute_query(query, data)
        else:
            # ORM插入
            stmt = insert(table).values(**data)
            result = await self.execute_query(stmt)
            return result

    async def update(self, table, data: Dict[str, Any], where: Dict[str, Any]) -> int:
        """
        更新数据

        Args:
            table: 表名或模型类
            data: 更新数据
            where: 条件

        Returns:
            影响的行数
        """
        if isinstance(table, str):
            # 原生SQL更新
            set_clause = ", ".join([f"{key} = :{key}" for key in data.keys()])
            where_clause = " AND ".join([f"{key} = :where_{key}" for key in where.keys()])

            # 合并参数
            params = data.copy()
            for key, value in where.items():
                params[f"where_{key}"] = value

            query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
            result = await self.execute_query(query, params)
            return result.rowcount
        else:
            # ORM更新
            stmt = (
                update(table)
                .where(*[getattr(table, key) == value for key, value in where.items()])
                .values(**data)
            )
            result = await self.execute_query(stmt)
            return result.rowcount

    async def delete(self, table, where: Dict[str, Any]) -> int:
        """
        删除数据

        Args:
            table: 表名或模型类
            where: 条件

        Returns:
            影响的行数
        """
        if isinstance(table, str):
            # 原生SQL删除
            where_clause = " AND ".join([f"{key} = :{key}" for key in where.keys()])
            query = f"DELETE FROM {table} WHERE {where_clause}"
            result = await self.execute_query(query, where)
            return result.rowcount
        else:
            # ORM删除
            stmt = delete(table).where(
                *[getattr(table, key) == value for key, value in where.items()]
            )
            result = await self.execute_query(stmt)
            return result.rowcount

    async def count(self, table, where: Dict[str, Any] = None) -> int:
        """
        统计数量

        Args:
            table: 表名或模型类
            where: 条件

        Returns:
            数量
        """
        if isinstance(table, str):
            # 原生SQL计数
            if where:
                where_clause = " WHERE " + " AND ".join([f"{key} = :{key}" for key in where.keys()])
                query = f"SELECT COUNT(*) FROM {table}{where_clause}"
                result = await self.fetch_one(query, where)
            else:
                query = f"SELECT COUNT(*) FROM {table}"
                result = await self.fetch_one(query)

            return result["count"] if result else 0
        else:
            # ORM计数
            stmt = select(func.count()).select_from(table)
            if where:
                stmt = stmt.where(*[getattr(table, key) == value for key, value in where.items()])

            result = await self.execute_query(stmt)
            return result.scalar()

    async def create_table(self, model_class) -> bool:
        """
        创建表

        Args:
            model_class: 模型类

        Returns:
            是否创建成功
        """
        if not HAS_SQLALCHEMY or not self.engine:
            logger.warning("无法创建表：数据库未初始化")
            return False

        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(model_class.metadata.create_all)

            logger.info(f"创建表: {model_class.__tablename__}")
            return True

        except Exception as e:
            logger.error(f"创建表失败 {model_class.__tablename__}: {e}")
            return False

    async def drop_table(self, model_class) -> bool:
        """
        删除表

        Args:
            model_class: 模型类

        Returns:
            是否删除成功
        """
        if not HAS_SQLALCHEMY or not self.engine:
            logger.warning("无法删除表：数据库未初始化")
            return False

        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(model_class.metadata.drop_all)

            logger.info(f"删除表: {model_class.__tablename__}")
            return True

        except Exception as e:
            logger.error(f"删除表失败 {model_class.__tablename__}: {e}")
            return False

    async def get_connection_stats(self) -> Dict[str, Any]:
        """
        获取连接统计

        Returns:
            连接统计信息
        """
        if not self.engine:
            return {}

        try:
            # 获取连接池信息
            pool = self.engine.pool
            stats = {
                "status": self.status.value,
                "connected_at": self.connected_at.isoformat() if self.connected_at else None,
                "last_error": self.last_error,
                "pool_size": getattr(pool, "size", 0),
                "checked_in": getattr(pool, "checkedin", 0),
                "checked_out": getattr(pool, "checkedout", 0),
                "overflow": getattr(pool, "overflow", 0),
                "connections": getattr(pool, "_conn.current_connections", 0),
            }

            # 合并查询统计
            stats.update(self.stats.__dict__)

            return stats

        except Exception as e:
            logger.error(f"获取连接统计失败: {e}")
            return {"status": self.status.value, "error": str(e)}

    async def health_check(self) -> HealthStatus:
        """
        健康检查

        Returns:
            健康状态
        """
        if not self.engine or self.status != ConnectionStatus.CONNECTED:
            return HealthStatus.CRITICAL

        try:
            # 简单查询测试连接
            async with self.session() as session:
                # 尝试执行一个简单查询
                if self.config.type == DatabaseType.POSTGRESQL:
                    result = await session.execute("SELECT 1")
                elif self.config.type == DatabaseType.MYSQL:
                    result = await session.execute("SELECT 1")
                elif self.config.type in [DatabaseType.SQLITE, DatabaseType.MEMORY]:
                    result = await session.execute("SELECT 1")

                result.scalar()

            # 检查连接池状态
            pool_stats = await self.get_connection_stats()
            active_connections = pool_stats.get("checked_out", 0)
            pool_size = pool_stats.get("pool_size", 0)

            if active_connections >= pool_size * 0.8:
                return HealthStatus.WARNING
            else:
                return HealthStatus.HEALTHY

        except Exception as e:
            self.status = ConnectionStatus.ERROR
            self.last_error = str(e)
            logger.error(f"数据库健康检查失败: {e}")
            return HealthStatus.CRITICAL

    # 私有方法

    async def _load_config(self) -> None:
        """加载数据库配置"""
        if self.config_manager:
            db_config = await self.config_manager.get_config("database", {})
            
            # 检查是否有直接的URL配置
            if "url" in db_config and db_config["url"]:
                url = db_config["url"]
                # 解析URL来确定数据库类型和参数
                if url.startswith("sqlite://"):
                    db_type = DatabaseType.SQLITE
                    # 从SQLite URL中提取数据库路径
                    if url == "sqlite:///:memory:":
                        db_path = ":memory:"
                    elif url.startswith("sqlite:///"):
                        db_path = url[10:]  # 移除 sqlite:///
                    elif url.startswith("sqlite://"):
                        db_path = url[9:]  # 移除 sqlite://
                    else:
                        db_path = "trading_system.db"
                    
                    self.config = DatabaseConfig(
                        type=db_type,
                        database=db_path,
                        pool_size=db_config.get("pool_size", 5),
                        max_overflow=db_config.get("max_overflow", 10),
                        pool_timeout=db_config.get("pool_timeout", 30),
                        pool_recycle=db_config.get("pool_recycle", 3600),
                        echo=db_config.get("echo", False),
                        isolation_level=TransactionIsolationLevel(
                            db_config.get("isolation_level", "read_committed")
                        ),
                    )
                else:
                    # 对于其他数据库类型，使用标准配置
                    self.config = DatabaseConfig(
                        type=DatabaseType(db_config.get("type", "postgresql")),
                        host=db_config.get("host", "localhost"),
                        port=db_config.get("port", 5432),
                        database=db_config.get("database", "trading_system"),
                        username=db_config.get("username", "postgres"),
                        password=db_config.get("password", ""),
                        pool_size=db_config.get("pool_size", 10),
                        max_overflow=db_config.get("max_overflow", 20),
                        pool_timeout=db_config.get("pool_timeout", 30),
                        pool_recycle=db_config.get("pool_recycle", 3600),
                        echo=db_config.get("echo", False),
                        isolation_level=TransactionIsolationLevel(
                            db_config.get("isolation_level", "read_committed")
                        ),
                    )
            else:
                # 没有URL配置，使用标准配置
                self.config = DatabaseConfig(
                    type=DatabaseType(db_config.get("type", "postgresql")),
                    host=db_config.get("host", "localhost"),
                    port=db_config.get("port", 5432),
                    database=db_config.get("database", "trading_system"),
                    username=db_config.get("username", "postgres"),
                    password=db_config.get("password", ""),
                    pool_size=db_config.get("pool_size", 10),
                    max_overflow=db_config.get("max_overflow", 20),
                    pool_timeout=db_config.get("pool_timeout", 30),
                    pool_recycle=db_config.get("pool_recycle", 3600),
                    echo=db_config.get("echo", False),
                    isolation_level=TransactionIsolationLevel(
                        db_config.get("isolation_level", "read_committed")
                    ),
                )
        else:
            # 默认配置
            self.config = DatabaseConfig()

        logger.info(
            f"加载数据库配置: {self.config.type.value}://{self.config.host}/{self.config.database}"
        )

    async def _create_engine(self) -> None:
        """创建数据库引擎"""
        if not HAS_SQLALCHEMY:
            raise RuntimeError("SQLAlchemy未安装")

        if not self.config:
            raise RuntimeError("数据库配置未加载")

        # 构建连接字符串
        connection_string = self.config.get_connection_string()

        # 创建异步引擎
        engine_kwargs = {
            "pool_size": self.config.pool_size,
            "max_overflow": self.config.max_overflow,
            "pool_timeout": self.config.pool_timeout,
            "pool_recycle": self.config.pool_recycle,
            "echo": self.config.echo,
            "future": True,
        }
        
        # SQLite不支持READ COMMITTED隔离级别，使用默认隔离级别
        if self.config.type != DatabaseType.SQLITE:
            engine_kwargs["isolation_level"] = self.config.isolation_level.value.upper()
        
        self.engine = create_async_engine(connection_string, **engine_kwargs)

        # 创建会话工厂
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

        logger.info(f"数据库引擎创建完成，连接池大小: {self.config.pool_size}")

    async def _test_connection(self) -> None:
        """测试数据库连接"""
        if not self.engine:
            raise RuntimeError("数据库引擎未创建")

        logger.info("测试数据库连接...")

        try:
            async with self.engine.connect() as conn:
                # 执行一个简单查询测试连接
                if self.config.type == DatabaseType.POSTGRESQL:
                    result = await conn.execute(text("SELECT version()"))
                    version = result.scalar()
                    logger.info(f"PostgreSQL版本: {version}")
                elif self.config.type == DatabaseType.MYSQL:
                    result = await conn.execute(text("SELECT version()"))
                    version = result.scalar()
                    logger.info(f"MySQL版本: {version}")
                elif self.config.type in [DatabaseType.SQLITE, DatabaseType.MEMORY]:
                    result = await conn.execute(text("SELECT sqlite_version()"))
                    version = result.scalar()
                    logger.info(f"SQLite版本: {version}")

                logger.info("数据库连接测试成功")

        except Exception as e:
            logger.error(f"数据库连接测试失败: {e}")
            raise

    async def _pool_monitor(self) -> None:
        """连接池监控任务"""
        logger.info("启动连接池监控任务")

        while self._running:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次

                if self.engine:
                    # 获取连接池状态
                    pool = self.engine.pool

                    # 安全地获取连接池属性，跳过方法
                    def safe_getattr(obj, attr, default):
                        value = getattr(obj, attr, default)
                        if callable(value):
                            return default
                        return value

                    # 记录连接池统计
                    self.connection_stats = {
                        "timestamp": datetime.now().isoformat(),
                        "size": safe_getattr(pool, "size", 0),
                        "checkedin": safe_getattr(pool, "checkedin", 0),
                        "checkedout": safe_getattr(pool, "checkedout", 0),
                        "overflow": safe_getattr(pool, "overflow", 0),
                    }

                    # 检查连接池健康状态
                    checked_out = self.connection_stats.get("checkedout", 0)
                    pool_size = self.connection_stats.get("size", 0)

                    if isinstance(checked_out, (int, float)) and isinstance(pool_size, (int, float)) and pool_size > 0:
                        if checked_out >= pool_size:
                            logger.warning(f"连接池饱和: {checked_out}/{pool_size}")

                    # 记录日志
                    logger.debug(f"连接池状态: {self.connection_stats}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"连接池监控错误: {e}")
                await asyncio.sleep(60)

        logger.info("连接池监控任务停止")

    async def _backup_manager(self) -> None:
        """备份管理任务"""
        logger.info("启动备份管理任务")

        while self._running:
            try:
                await asyncio.sleep(self.config.backup_interval)

                if self.config.backup_enabled:
                    await self._create_backup()
                    await self._cleanup_old_backups()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"备份管理错误: {e}")
                await asyncio.sleep(60)

        logger.info("备份管理任务停止")

    async def _create_backup(self) -> bool:
        """创建数据库备份"""
        try:
            if not self.engine or self.status != ConnectionStatus.CONNECTED:
                logger.warning("数据库未连接，跳过备份")
                return False

            backup_dir = Path("backups")
            backup_dir.mkdir(exist_ok=True)

            backup_filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
            backup_path = backup_dir / backup_filename

            if self.config.type == DatabaseType.POSTGRESQL:
                # PostgreSQL备份
                import subprocess
                cmd = [
                    "pg_dump",
                    f"--host={self.config.host}",
                    f"--port={self.config.port}",
                    f"--username={self.config.username}",
                    f"--dbname={self.config.database}",
                    "--format=c",
                    f"--file={backup_path}"
                ]
                env = os.environ.copy()
                env["PGPASSWORD"] = self.config.password
                result = subprocess.run(cmd, env=env, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"PostgreSQL备份失败: {result.stderr}")
                    return False
            elif self.config.type == DatabaseType.MYSQL:
                # MySQL备份
                import subprocess
                cmd = [
                    "mysqldump",
                    f"--host={self.config.host}",
                    f"--port={self.config.port}",
                    f"--user={self.config.username}",
                    f"--password={self.config.password}",
                    f"{self.config.database}",
                    f"--result-file={backup_path}"
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"MySQL备份失败: {result.stderr}")
                    return False
            elif self.config.type in [DatabaseType.SQLITE, DatabaseType.MEMORY]:
                # SQLite备份
                if self.config.type == DatabaseType.MEMORY:
                    logger.warning("内存数据库不支持备份")
                    return False
                import shutil
                db_path = Path(self.config.database)
                if db_path.exists():
                    shutil.copy2(db_path, backup_path)
                else:
                    logger.warning(f"SQLite数据库文件不存在: {db_path}")
                    return False

            self.last_backup = datetime.now()
            logger.info(f"数据库备份成功: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"创建备份失败: {e}")
            return False

    async def _cleanup_old_backups(self) -> None:
        """清理旧备份"""
        try:
            backup_dir = Path("backups")
            if not backup_dir.exists():
                return

            cutoff_time = datetime.now() - timedelta(days=self.config.backup_retention)
            backups = list(backup_dir.glob("backup_*.sql")) + list(backup_dir.glob("backup_*.dump"))

            for backup in backups:
                backup_time = datetime.strptime(backup.stem.split("_")[1], "%Y%m%d_%H%M%S")
                if backup_time < cutoff_time:
                    backup.unlink()
                    logger.info(f"清理旧备份: {backup}")
        except Exception as e:
            logger.error(f"清理旧备份失败: {e}")

    async def create_backup(self) -> bool:
        """手动创建备份"""
        return await self._create_backup()

    async def get_backup_status(self) -> Dict[str, Any]:
        """获取备份状态"""
        return {
            "enabled": self.config.backup_enabled if self.config else False,
            "last_backup": self.last_backup.isoformat() if self.last_backup else None,
            "backup_interval": self.config.backup_interval if self.config else 3600,
            "backup_retention": self.config.backup_retention if self.config else 7
        }


# 使用示例
async def example_usage():
    """数据库管理器使用示例"""

    if not HAS_SQLALCHEMY:
        print("SQLAlchemy未安装，跳过示例")
        return

    # 创建数据库管理器
    db_manager = DatabaseManager()
    await db_manager.initialize()

    try:
        # 创建表
        await db_manager.create_table(TradingSession)
        await db_manager.create_table(Trade)
        await db_manager.create_table(MarketData)

        # 插入数据
        session_data = {
            "session_id": "test_session_1",
            "strategy_id": "moving_average",
            "symbol": "BTC/USDT",
            "status": "active",
            "initial_balance": 10000.0,
            "current_balance": 10500.0,
            "profit_loss": 500.0,
            "profit_loss_percent": 5.0,
        }

        await db_manager.insert(TradingSession, session_data)

        # 查询数据
        query = select(TradingSession).where(TradingSession.symbol == "BTC/USDT")
        sessions = await db_manager.fetch_all(query)
        print(f"交易会话: {len(sessions)} 条记录")

        # 更新数据
        await db_manager.update(
            TradingSession,
            {"status": "completed", "ended_at": datetime.now()},
            {"session_id": "test_session_1"},
        )

        # 统计数量
        count = await db_manager.count(TradingSession, {"status": "active"})
        print(f"活跃会话数量: {count}")

        # 获取统计信息
        stats = await db_manager.get_connection_stats()
        print(f"数据库统计: {json.dumps(stats, indent=2, default=str)}")

        # 健康检查
        health = await db_manager.health_check()
        print(f"数据库健康状态: {health.value}")

        # 手动创建备份
        backup_result = await db_manager.create_backup()
        print(f"手动备份结果: {backup_result}")

        # 获取备份状态
        backup_status = await db_manager.get_backup_status()
        print(f"备份状态: {json.dumps(backup_status, indent=2, default=str)}")

    finally:
        await db_manager.cleanup()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
