"""
日志管理模块 - 全智能量化交易系统的诊断和审计核心

功能：
1. 结构化日志（JSON格式，统一字段）
2. 多输出目标（控制台、文件、数据库、远程服务）
3. 日志分级（DEBUG、INFO、WARNING、ERROR、CRITICAL）
4. 日志轮转（按大小或时间自动轮转）
5. 日志查询（灵活的日志搜索和过滤）
6. 审计跟踪（用户操作和系统事件记录）
"""

import asyncio
import gzip
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class LogLevel(Enum):
    """日志级别"""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogSource(Enum):
    """日志来源"""

    SYSTEM = "system"
    TRADING = "trading"
    API = "api"
    DATABASE = "database"
    STRATEGY = "strategy"
    RISK = "risk"
    MONITOR = "monitor"
    AUDIT = "audit"
    CUSTOM = "custom"


class LogOutput(Enum):
    """日志输出"""

    CONSOLE = "console"
    FILE = "file"
    DATABASE = "database"
    SYSLOG = "syslog"
    REMOTE = "remote"


@dataclass
class LogEntry:
    """日志条目"""

    log_id: str
    timestamp: datetime
    level: LogLevel
    source: LogSource
    message: str
    module: Optional[str] = None
    function: Optional[str] = None
    line_no: Optional[int] = None
    correlation_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    duration_ms: Optional[float] = None
    data: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "log_id": self.log_id,
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "source": self.source.value,
            "message": self.message,
            "module": self.module,
            "function": self.function,
            "line_no": self.line_no,
            "correlation_id": self.correlation_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "duration_ms": self.duration_ms,
            "data": self.data,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogEntry":
        """从字典创建"""
        return cls(
            log_id=data.get("log_id", f"log_{uuid.uuid4().hex[:8]}"),
            timestamp=(
                datetime.fromisoformat(data["timestamp"])
                if isinstance(data.get("timestamp"), str)
                else data.get("timestamp", datetime.now())
            ),
            level=(
                LogLevel(data["level"])
                if isinstance(data.get("level"), str)
                else data.get("level", LogLevel.INFO)
            ),
            source=(
                LogSource(data["source"])
                if isinstance(data.get("source"), str)
                else data.get("source", LogSource.SYSTEM)
            ),
            message=data["message"],
            module=data.get("module"),
            function=data.get("function"),
            line_no=data.get("line_no"),
            correlation_id=data.get("correlation_id"),
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
            request_id=data.get("request_id"),
            duration_ms=data.get("duration_ms"),
            data=data.get("data", {}),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class LogConfig:
    """日志配置"""

    outputs: List[LogOutput] = field(default_factory=lambda: [LogOutput.CONSOLE, LogOutput.FILE])
    log_level: LogLevel = LogLevel.INFO
    log_dir: str = "./logs"
    max_file_size_mb: int = 100  # 单个日志文件最大大小（MB）
    max_backup_count: int = 10  # 最大备份文件数量
    rotation_interval: str = "daily"  # 轮转间隔：daily, hourly, weekly
    compress_backups: bool = True  # 是否压缩备份文件
    json_format: bool = True  # 是否使用JSON格式
    include_traceback: bool = True  # 是否包含堆栈跟踪
    buffer_size: int = 1000  # 内存缓冲区大小
    flush_interval_seconds: int = 5  # 刷新间隔（秒）


@dataclass
class LogQuery:
    """日志查询"""

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    level: Optional[LogLevel] = None
    source: Optional[LogSource] = None
    module: Optional[str] = None
    correlation_id: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    tags: Optional[List[str]] = None
    message_pattern: Optional[str] = None
    data_filter: Optional[Dict[str, Any]] = None
    limit: int = 1000
    offset: int = 0
    order_by: str = "timestamp"  # timestamp, level
    order_desc: bool = True  # 是否降序

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "level": self.level.value if self.level else None,
            "source": self.source.value if self.source else None,
            "module": self.module,
            "correlation_id": self.correlation_id,
            "user_id": self.user_id,
            "request_id": self.request_id,
            "tags": self.tags,
            "message_pattern": self.message_pattern,
            "data_filter": self.data_filter,
            "limit": self.limit,
            "offset": self.offset,
            "order_by": self.order_by,
            "order_desc": self.order_desc,
        }
        return {k: v for k, v in result.items() if v is not None}


@dataclass
class LogStatistics:
    """日志统计"""

    total_logs: int = 0
    logs_by_level: Dict[str, int] = field(default_factory=dict)
    logs_by_source: Dict[str, int] = field(default_factory=dict)
    logs_by_module: Dict[str, int] = field(default_factory=dict)
    error_rate: float = 0.0
    avg_logs_per_minute: float = 0.0
    peak_hour: Optional[datetime] = None
    peak_logs_per_hour: int = 0
    time_period_start: Optional[datetime] = None
    time_period_end: Optional[datetime] = None


class LogHandler:
    """日志处理器基类"""

    def __init__(self, config: LogConfig):
        self.config = config
        self._initialized = False

    async def initialize(self) -> None:
        """初始化"""
        if self._initialized:
            return

        try:
            await self._setup()
            self._initialized = True

        except Exception as e:
            logger.error(f"日志处理器初始化失败: {e}")
            raise

    async def cleanup(self) -> None:
        """清理"""
        if not self._initialized:
            return

        try:
            await self._cleanup()
            self._initialized = False

        except Exception as e:
            logger.error(f"日志处理器清理失败: {e}")

    async def write(self, entry: LogEntry) -> None:
        """写入日志"""
        if not self._initialized:
            return

        try:
            await self._write(entry)

        except Exception as e:
            logger.error(f"写入日志失败: {e}")

    async def _setup(self) -> None:
        """设置（子类实现）"""
        raise NotImplementedError

    async def _cleanup(self) -> None:
        """清理（子类实现）"""
        pass

    async def _write(self, entry: LogEntry) -> None:
        """写入日志（子类实现）"""
        raise NotImplementedError


class ConsoleHandler(LogHandler):
    """控制台处理器"""

    async def _setup(self) -> None:
        """设置控制台处理器"""
        # 使用Python标准logging
        self.logger = logging.getLogger("trading_system")
        self.logger.setLevel(logging.DEBUG)

        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)

        # 设置格式
        if self.config.json_format:
            console_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
        else:
            console_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )

        self.logger.addHandler(console_handler)

    async def _write(self, entry: LogEntry) -> None:
        """写入到控制台"""
        log_method = getattr(self.logger, entry.level.value, self.logger.info)

        # 构建消息
        message = f"[{entry.source.value}] {entry.message}"
        if entry.data:
            message += f" | data={json.dumps(entry.data, default=str)}"
        if entry.tags:
            message += f" | tags={entry.tags}"

        extra = {
            "module": entry.module,
            "function": entry.function,
            "correlation_id": entry.correlation_id,
            "user_id": entry.user_id,
        }

        log_method(message, extra=extra)


class FileHandler(LogHandler):
    """文件处理器"""

    def __init__(self, config: LogConfig):
        super().__init__(config)
        self._current_file = None
        self._file_handle = None
        self._bytes_written = 0
        self._last_rotation_check = datetime.now()
        self._lock = threading.RLock()

    async def _setup(self) -> None:
        """设置文件处理器"""
        # 创建日志目录
        log_dir = Path(self.config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        # 打开当前日志文件
        await self._open_current_file()

    async def _cleanup(self) -> None:
        """清理文件处理器"""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None

    async def _write(self, entry: LogEntry) -> None:
        """写入到文件"""
        with self._lock:
            # 检查是否需要轮转
            await self._check_rotation()

            # 写入日志
            log_line = entry.to_json() + "\n"

            try:
                self._file_handle.write(log_line)
                self._file_handle.flush()

                self._bytes_written += len(log_line.encode("utf-8"))

            except Exception as e:
                logger.error(f"写入日志文件失败: {e}")
                # 尝试重新打开文件
                await self._open_current_file()

    async def _open_current_file(self) -> None:
        """打开当前日志文件"""
        try:
            # 关闭现有文件
            if self._file_handle:
                self._file_handle.close()

            # 确定文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._current_file = Path(self.config.log_dir) / f"trading_system_{timestamp}.log"

            # 打开文件
            self._file_handle = open(self._current_file, "a", encoding="utf-8")
            self._bytes_written = 0

            # 写入文件头
            header = (
                json.dumps(
                    {
                        "type": "log_file_header",
                        "created_at": datetime.now().isoformat(),
                        "config": asdict(self.config),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

            self._file_handle.write(header)
            self._file_handle.flush()
            self._bytes_written += len(header.encode("utf-8"))

        except Exception as e:
            logger.error(f"打开日志文件失败: {e}")
            raise

    async def _check_rotation(self) -> None:
        """检查是否需要轮转"""
        now = datetime.now()

        # 检查文件大小
        size_mb = self._bytes_written / (1024 * 1024)
        if size_mb >= self.config.max_file_size_mb:
            logger.info(f"日志文件达到大小限制 {size_mb:.1f}MB，开始轮转")
            await self._rotate_file()
            return

        # 检查时间间隔
        if self.config.rotation_interval == "daily":
            if now.date() != self._last_rotation_check.date():
                logger.info("新的一天，开始日志轮转")
                await self._rotate_file()

        elif self.config.rotation_interval == "hourly":
            if now.hour != self._last_rotation_check.hour:
                logger.info("新的一小时，开始日志轮转")
                await self._rotate_file()

        self._last_rotation_check = now

    async def _rotate_file(self) -> None:
        """轮转日志文件"""
        try:
            # 关闭当前文件
            if self._file_handle:
                self._file_handle.close()
                self._file_handle = None

            # 压缩备份文件
            if self.config.compress_backups and self._current_file:
                await self._compress_backup(self._current_file)

            # 清理旧备份文件
            await self._cleanup_old_backups()

            # 打开新文件
            await self._open_current_file()

        except Exception as e:
            logger.error(f"日志轮转失败: {e}")

    async def _compress_backup(self, file_path: Path) -> None:
        """压缩备份文件"""
        try:
            compressed_path = file_path.with_suffix(file_path.suffix + ".gz")

            with open(file_path, "rb") as f_in:
                with gzip.open(compressed_path, "wb") as f_out:
                    f_out.writelines(f_in)

            # 删除原始文件
            file_path.unlink()

            logger.debug(f"压缩备份文件: {compressed_path}")

        except Exception as e:
            logger.error(f"压缩备份文件失败 {file_path}: {e}")

    async def _cleanup_old_backups(self) -> None:
        """清理旧备份文件"""
        try:
            log_dir = Path(self.config.log_dir)

            # 获取所有日志文件
            log_files = []
            for pattern in ["*.log", "*.log.gz"]:
                log_files.extend(log_dir.glob(pattern))

            # 按修改时间排序（最新的在前面）
            log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

            # 删除超出限制的文件
            for i, log_file in enumerate(
                log_files[self.config.max_backup_count :], self.config.max_backup_count
            ):
                try:
                    log_file.unlink()
                    logger.debug(f"删除旧备份文件: {log_file}")
                except Exception as e:
                    logger.error(f"删除旧备份文件失败 {log_file}: {e}")

        except Exception as e:
            logger.error(f"清理旧备份文件失败: {e}")


class MemoryBufferHandler(LogHandler):
    """内存缓冲区处理器"""

    def __init__(self, config: LogConfig):
        super().__init__(config)
        self.buffer: List[LogEntry] = []
        self._lock = threading.RLock()

    async def _setup(self) -> None:
        """设置内存缓冲区"""
        self.buffer = []

    async def _write(self, entry: LogEntry) -> None:
        """写入到内存缓冲区"""
        with self._lock:
            self.buffer.append(entry)

            # 限制缓冲区大小
            if len(self.buffer) > self.config.buffer_size:
                self.buffer = self.buffer[-self.config.buffer_size :]

    async def get_buffer(self) -> List[LogEntry]:
        """获取缓冲区内容"""
        with self._lock:
            return self.buffer.copy()

    async def clear_buffer(self) -> None:
        """清空缓冲区"""
        with self._lock:
            self.buffer.clear()


class LogManager:
    """
    日志管理器

    核心功能：
    1. 结构化日志管理
    2. 多输出目标支持
    3. 日志分级和过滤
    4. 日志轮转管理
    5. 日志查询和分析
    6. 审计跟踪
    """

    def __init__(self, config_manager=None):
        """
        初始化日志管理器

        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager

        # 配置
        self.config = LogConfig()

        # 日志处理器
        self.handlers: Dict[LogOutput, LogHandler] = {}
        self.memory_handler: Optional[MemoryBufferHandler] = None

        # 日志存储
        self.log_storage: List[LogEntry] = []  # 内存存储（用于查询）
        self.max_storage_size = 100000  # 最大存储数量

        # 统计
        self.stats = {
            "total_logs": 0,
            "logs_by_level": {level.value: 0 for level in LogLevel},
            "logs_by_source": {source.value: 0 for source in LogSource},
            "last_log_time": None,
        }

        # 任务和锁
        self._tasks: List[asyncio.Task] = []
        self._lock = threading.RLock()
        self._initialized = False
        self._running = False

        logger.info("日志管理器初始化完成")

    async def initialize(self) -> None:
        """
        初始化日志管理器

        加载配置，设置处理器
        """
        if self._initialized:
            return

        logger.info("初始化日志管理器...")

        try:
            # 加载配置
            await self._load_config()

            # 设置日志处理器
            await self._setup_handlers()

            # 启动清理任务
            self._tasks.append(asyncio.create_task(self._cleanup_worker()))

            self._initialized = True
            logger.info("日志管理器初始化完成")

        except Exception as e:
            logger.error(f"日志管理器初始化失败: {e}")
            traceback.print_exc()

    async def cleanup(self) -> None:
        """
        清理日志管理器

        刷新日志，清理资源
        """
        logger.info("清理日志管理器...")

        self._running = False

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()

        # 清理所有处理器
        for handler in self.handlers.values():
            await handler.cleanup()

        self.handlers.clear()

        self._initialized = False
        logger.info("日志管理器清理完成")

    async def log(
        self,
        level: LogLevel,
        source: LogSource,
        message: str,
        module: Optional[str] = None,
        function: Optional[str] = None,
        line_no: Optional[int] = None,
        correlation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
        data: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        include_traceback: Optional[bool] = None,
    ) -> str:
        """
        记录日志

        Args:
            level: 日志级别
            source: 日志来源
            message: 日志消息
            module: 模块名
            function: 函数名
            line_no: 行号
            correlation_id: 关联ID
            user_id: 用户ID
            session_id: 会话ID
            request_id: 请求ID
            duration_ms: 持续时间（毫秒）
            data: 附加数据
            tags: 标签
            metadata: 元数据
            include_traceback: 是否包含堆栈跟踪

        Returns:
            日志ID
        """
        if not self._initialized:
            logger.warning("日志管理器未初始化，跳过日志记录")
            return ""

        # 检查日志级别是否启用
        if not await self._is_level_enabled(level):
            return ""

        # 获取调用信息
        if not module or not function:
            try:
                frame = traceback.extract_stack()[-3]
                module = module or frame.filename
                function = function or frame.name
                line_no = line_no or frame.lineno
            except:
                pass

        # 创建日志条目
        log_id = f"log_{uuid.uuid4().hex[:8]}"
        entry = LogEntry(
            log_id=log_id,
            timestamp=datetime.now(),
            level=level,
            source=source,
            message=message,
            module=module,
            function=function,
            line_no=line_no,
            correlation_id=correlation_id,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            duration_ms=duration_ms,
            data=data or {},
            tags=tags or [],
            metadata=metadata or {},
        )

        # 添加堆栈跟踪
        if (
            include_traceback or (include_traceback is None and self.config.include_traceback)
        ) and level in [LogLevel.ERROR, LogLevel.CRITICAL]:
            try:
                tb = traceback.format_exc()
                if tb and "NoneType: None" not in tb:
                    entry.data["traceback"] = tb
            except:
                pass

        # 写入到所有处理器
        await self._write_to_handlers(entry)

        # 更新统计
        await self._update_stats(entry)

        return log_id

    async def debug(self, source: LogSource, message: str, **kwargs) -> str:
        """
        记录DEBUG级别日志

        Args:
            source: 日志来源
            message: 日志消息
            **kwargs: 其他参数

        Returns:
            日志ID
        """
        return await self.log(LogLevel.DEBUG, source, message, **kwargs)

    async def info(self, source: LogSource, message: str, **kwargs) -> str:
        """
        记录INFO级别日志

        Args:
            source: 日志来源
            message: 日志消息
            **kwargs: 其他参数

        Returns:
            日志ID
        """
        return await self.log(LogLevel.INFO, source, message, **kwargs)

    async def warning(self, source: LogSource, message: str, **kwargs) -> str:
        """
        记录WARNING级别日志

        Args:
            source: 日志来源
            message: 日志消息
            **kwargs: 其他参数

        Returns:
            日志ID
        """
        return await self.log(LogLevel.WARNING, source, message, **kwargs)

    async def error(self, source: LogSource, message: str, **kwargs) -> str:
        """
        记录ERROR级别日志

        Args:
            source: 日志来源
            message: 日志消息
            **kwargs: 其他参数

        Returns:
            日志ID
        """
        return await self.log(LogLevel.ERROR, source, message, **kwargs)

    async def critical(self, source: LogSource, message: str, **kwargs) -> str:
        """
        记录CRITICAL级别日志

        Args:
            source: 日志来源
            message: 日志消息
            **kwargs: 其他参数

        Returns:
            日志ID
        """
        return await self.log(LogLevel.CRITICAL, source, message, **kwargs)

    async def audit(
        self,
        user_id: str,
        action: str,
        resource: str,
        status: str,
        details: Dict[str, Any] = None,
        **kwargs,
    ) -> str:
        """
        记录审计日志

        Args:
            user_id: 用户ID
            action: 操作
            resource: 资源
            status: 状态
            details: 详情
            **kwargs: 其他参数

        Returns:
            日志ID
        """
        message = f"审计: {action} {resource} ({status})"

        data = details or {}
        data.update({"audit_action": action, "audit_resource": resource, "audit_status": status})

        tags = kwargs.get("tags", [])
        if "audit" not in tags:
            tags = tags + ["audit"]

        return await self.log(
            LogLevel.INFO, LogSource.AUDIT, message, user_id=user_id, data=data, tags=tags, **kwargs
        )

    async def query_logs(self, query: LogQuery) -> List[LogEntry]:
        """
        查询日志

        Args:
            query: 查询条件

        Returns:
            日志条目列表
        """
        with self._lock:
            # 获取所有日志
            logs = self.log_storage.copy()

            # 应用过滤器
            filtered_logs = []
            for log in logs:
                if not await self._matches_query(log, query):
                    continue
                filtered_logs.append(log)

            # 排序
            if query.order_by == "timestamp":
                filtered_logs.sort(key=lambda x: x.timestamp, reverse=query.order_desc)
            elif query.order_by == "level":
                # 按级别排序（CRITICAL > ERROR > WARNING > INFO > DEBUG）
                level_order = {
                    LogLevel.CRITICAL: 5,
                    LogLevel.ERROR: 4,
                    LogLevel.WARNING: 3,
                    LogLevel.INFO: 2,
                    LogLevel.DEBUG: 1,
                }
                filtered_logs.sort(
                    key=lambda x: level_order.get(x.level, 0), reverse=query.order_desc
                )

            # 分页
            start_idx = query.offset
            end_idx = query.offset + query.limit
            return filtered_logs[start_idx:end_idx]

    async def get_log_by_id(self, log_id: str) -> Optional[LogEntry]:
        """
        根据ID获取日志

        Args:
            log_id: 日志ID

        Returns:
            日志条目或None
        """
        with self._lock:
            for log in self.log_storage:
                if log.log_id == log_id:
                    return log
            return None

    async def get_recent_logs(self, limit: int = 100) -> List[LogEntry]:
        """
        获取最近日志

        Args:
            limit: 限制数量

        Returns:
            最近日志列表
        """
        query = LogQuery(limit=limit, order_by="timestamp", order_desc=True)
        return await self.query_logs(query)

    async def get_log_statistics(
        self, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None
    ) -> LogStatistics:
        """
        获取日志统计

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            日志统计
        """
        with self._lock:
            # 过滤时间范围
            logs = self.log_storage.copy()
            if start_time:
                logs = [log for log in logs if log.timestamp >= start_time]
            if end_time:
                logs = [log for log in logs if log.timestamp <= end_time]

            if not logs:
                return LogStatistics()

            # 计算统计
            stats = LogStatistics(
                total_logs=len(logs),
                logs_by_level={},
                logs_by_source={},
                logs_by_module={},
                time_period_start=min(log.timestamp for log in logs),
                time_period_end=max(log.timestamp for log in logs),
            )

            # 按级别统计
            for log in logs:
                level_key = log.level.value
                stats.logs_by_level[level_key] = stats.logs_by_level.get(level_key, 0) + 1

            # 按来源统计
            for log in logs:
                source_key = log.source.value
                stats.logs_by_source[source_key] = stats.logs_by_source.get(source_key, 0) + 1

            # 按模块统计
            for log in logs:
                if log.module:
                    module_key = log.module
                    stats.logs_by_module[module_key] = stats.logs_by_module.get(module_key, 0) + 1

            # 计算错误率
            error_count = stats.logs_by_level.get(
                LogLevel.ERROR.value, 0
            ) + stats.logs_by_level.get(LogLevel.CRITICAL.value, 0)
            stats.error_rate = error_count / stats.total_logs if stats.total_logs > 0 else 0.0

            # 计算每分钟平均日志数
            time_span = (stats.time_period_end - stats.time_period_start).total_seconds()
            if time_span > 0:
                stats.avg_logs_per_minute = stats.total_logs / (time_span / 60)

            # 找出峰值小时
            hourly_counts: Dict[int, int] = {}
            for log in logs:
                hour_key = log.timestamp.replace(minute=0, second=0, microsecond=0)
                hour_timestamp = int(hour_key.timestamp())
                hourly_counts[hour_timestamp] = hourly_counts.get(hour_timestamp, 0) + 1

            if hourly_counts:
                peak_timestamp = max(hourly_counts.items(), key=lambda x: x[1])[0]
                stats.peak_hour = datetime.fromtimestamp(peak_timestamp)
                stats.peak_logs_per_hour = hourly_counts[peak_timestamp]

            return stats

    async def get_memory_buffer(self) -> List[LogEntry]:
        """
        获取内存缓冲区内容

        Returns:
            内存缓冲区内容
        """
        if self.memory_handler:
            return await self.memory_handler.get_buffer()
        return []

    async def clear_memory_buffer(self) -> None:
        """
        清空内存缓冲区
        """
        if self.memory_handler:
            await self.memory_handler.clear_buffer()

    async def get_config(self) -> LogConfig:
        """
        获取日志配置

        Returns:
            日志配置
        """
        return self.config

    async def update_config(self, new_config: Dict[str, Any]) -> bool:
        """
        更新日志配置

        Args:
            new_config: 新配置

        Returns:
            是否更新成功
        """
        try:
            # 更新配置
            for key, value in new_config.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)

            # 重新设置处理器
            await self._setup_handlers()

            logger.info("更新日志配置")
            return True

        except Exception as e:
            logger.error(f"更新日志配置失败: {e}")
            return False

    async def export_logs(self, query: LogQuery, format: str = "json") -> Optional[str]:
        """
        导出日志

        Args:
            query: 查询条件
            format: 格式（json, csv）

        Returns:
            导出的日志字符串或None
        """
        logs = await self.query_logs(query)

        if not logs:
            return None

        try:
            if format == "json":
                log_dicts = [log.to_dict() for log in logs]
                return json.dumps(log_dicts, indent=2, ensure_ascii=False, default=str)

            elif format == "csv":
                import csv
                import io

                # 收集所有字段
                all_fields = set()
                for log in logs:
                    all_fields.update(log.to_dict().keys())

                # 写入CSV
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=sorted(all_fields))
                writer.writeheader()

                for log in logs:
                    writer.writerow(log.to_dict())

                return output.getvalue()

            else:
                logger.error(f"不支持的导出格式: {format}")
                return None

        except Exception as e:
            logger.error(f"导出日志失败: {e}")
            return None

    async def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计信息
        """
        with self._lock:
            stats = self.stats.copy()
            stats.update(
                {
                    "storage_size": len(self.log_storage),
                    "max_storage_size": self.max_storage_size,
                    "active_handlers": len(self.handlers),
                    "config": asdict(self.config),
                }
            )
            return stats

    # 私有方法

    async def _load_config(self) -> None:
        """加载日志配置"""
        if self.config_manager:
            log_config = await self.config_manager.get_config("logging", {})

            # 更新配置
            if log_config:
                # 输出目标
                if "outputs" in log_config:
                    self.config.outputs = [LogOutput(output) for output in log_config["outputs"]]

                # 日志级别
                if "log_level" in log_config:
                    self.config.log_level = LogLevel(log_config["log_level"])

                # 其他配置
                config_fields = [
                    "log_dir",
                    "max_file_size_mb",
                    "max_backup_count",
                    "rotation_interval",
                    "compress_backups",
                    "json_format",
                    "include_traceback",
                    "buffer_size",
                    "flush_interval_seconds",
                ]

                for field in config_fields:
                    if field in log_config:
                        setattr(self.config, field, log_config[field])

        logger.info(
            f"加载日志配置: 级别={self.config.log_level.value}, 输出={[o.value for o in self.config.outputs]}"
        )

    async def _setup_handlers(self) -> None:
        """设置日志处理器"""
        # 清理现有处理器
        for handler in self.handlers.values():
            await handler.cleanup()

        self.handlers.clear()

        # 创建新处理器
        for output in self.config.outputs:
            try:
                if output == LogOutput.CONSOLE:
                    handler = ConsoleHandler(self.config)
                elif output == LogOutput.FILE:
                    handler = FileHandler(self.config)
                else:
                    logger.warning(f"不支持的日志输出: {output.value}")
                    continue

                await handler.initialize()
                self.handlers[output] = handler

                logger.info(f"设置日志处理器: {output.value}")

            except Exception as e:
                logger.error(f"设置日志处理器失败 {output.value}: {e}")

        # 总是创建内存缓冲区处理器（用于查询）
        self.memory_handler = MemoryBufferHandler(self.config)
        await self.memory_handler.initialize()

    async def _is_level_enabled(self, level: LogLevel) -> bool:
        """检查日志级别是否启用"""
        level_order = {
            LogLevel.DEBUG: 1,
            LogLevel.INFO: 2,
            LogLevel.WARNING: 3,
            LogLevel.ERROR: 4,
            LogLevel.CRITICAL: 5,
        }
        config_order = level_order.get(self.config.log_level, 2)  # 默认INFO

        return level_order.get(level, 1) >= config_order

    async def _write_to_handlers(self, entry: LogEntry) -> None:
        """写入到所有处理器"""
        # 写入到输出处理器
        for handler in self.handlers.values():
            await handler.write(entry)

        # 写入到内存缓冲区处理器
        if self.memory_handler:
            await self.memory_handler.write(entry)

        # 存储到内存（用于查询）
        await self._store_log(entry)

    async def _store_log(self, entry: LogEntry) -> None:
        """存储日志到内存"""
        with self._lock:
            self.log_storage.append(entry)

            # 限制存储大小
            if len(self.log_storage) > self.max_storage_size:
                self.log_storage = self.log_storage[-self.max_storage_size :]

    async def _update_stats(self, entry: LogEntry) -> None:
        """更新统计"""
        with self._lock:
            self.stats["total_logs"] += 1
            self.stats["logs_by_level"][entry.level.value] = (
                self.stats["logs_by_level"].get(entry.level.value, 0) + 1
            )
            self.stats["logs_by_source"][entry.source.value] = (
                self.stats["logs_by_source"].get(entry.source.value, 0) + 1
            )
            self.stats["last_log_time"] = entry.timestamp.isoformat()

    async def _matches_query(self, log: LogEntry, query: LogQuery) -> bool:
        """检查日志是否匹配查询条件"""
        # 时间过滤
        if query.start_time and log.timestamp < query.start_time:
            return False
        if query.end_time and log.timestamp > query.end_time:
            return False

        # 级别过滤
        if query.level and log.level != query.level:
            return False

        # 来源过滤
        if query.source and log.source != query.source:
            return False

        # 模块过滤
        if query.module and log.module != query.module:
            return False

        # 关联ID过滤
        if query.correlation_id and log.correlation_id != query.correlation_id:
            return False

        # 用户ID过滤
        if query.user_id and log.user_id != query.user_id:
            return False

        # 请求ID过滤
        if query.request_id and log.request_id != query.request_id:
            return False

        # 标签过滤
        if query.tags:
            if not all(tag in log.tags for tag in query.tags):
                return False

        # 消息模式过滤
        if query.message_pattern:
            try:
                if not re.search(query.message_pattern, log.message, re.IGNORECASE):
                    return False
            except re.error:
                # 如果正则表达式无效，使用简单字符串匹配
                if query.message_pattern.lower() not in log.message.lower():
                    return False

        # 数据过滤
        if query.data_filter:
            for key, value in query.data_filter.items():
                if key not in log.data or log.data[key] != value:
                    return False

        return True

    async def _cleanup_worker(self) -> None:
        """清理工作线程"""
        logger.info("启动日志清理线程")

        while self._initialized:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次

                # 清理旧日志（保留最近7天）
                cutoff_time = datetime.now() - timedelta(days=7)

                with self._lock:
                    # 保留最近7天的日志
                    self.log_storage = [
                        log for log in self.log_storage if log.timestamp > cutoff_time
                    ]

                logger.debug(f"清理日志存储，当前大小: {len(self.log_storage)}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"日志清理线程错误: {e}")
                await asyncio.sleep(60)

        logger.info("日志清理线程停止")


# 使用示例
async def example_usage():
    """日志管理器使用示例"""

    # 创建日志管理器
    log_manager = LogManager()
    await log_manager.initialize()

    try:
        # 记录不同级别的日志
        await log_manager.info(
            source=LogSource.SYSTEM,
            message="系统启动完成",
            module="system",
            function="initialize",
            tags=["startup", "system"],
        )

        await log_manager.debug(
            source=LogSource.TRADING,
            message="交易引擎初始化",
            module="trade_engine",
            function="initialize",
            data={"initial_capital": 100000.0},
        )

        await log_manager.warning(
            source=LogSource.RISK,
            message="风险检查警告",
            module="risk_manager",
            function="check_order",
            data={"order_value": 15000.0, "limit": 10000.0},
        )

        await log_manager.error(
            source=LogSource.API,
            message="API请求失败",
            module="api_server",
            function="handle_request",
            request_id="req_123",
            data={"endpoint": "/api/v1/trades", "status_code": 500},
            include_traceback=True,
        )

        # 审计日志
        await log_manager.audit(
            user_id="user123",
            action="login",
            resource="system",
            status="success",
            details={"ip": "192.168.1.100", "user_agent": "Mozilla/5.0"},
        )

        # 获取最近日志
        recent_logs = await log_manager.get_recent_logs(limit=5)
        logger.info(f"最近 {len(recent_logs)} 条日志:")
        for log in recent_logs:
            logger.info(
                f"  [{log.timestamp.strftime('%H:%M:%S')}] {log.level.value.upper()}: {log.message}"
            )

        # 查询特定日志
        query = LogQuery(level=LogLevel.ERROR, source=LogSource.API, limit=10)

        error_logs = await log_manager.query_logs(query)
        logger.info(f"API错误日志: {len(error_logs)} 条")

        # 获取统计
        stats = await log_manager.get_log_statistics()
        logger.info(f"日志统计: 总数={stats.total_logs}, 错误率={stats.error_rate*100:.1f}%")

        # 获取内存缓冲区
        buffer = await log_manager.get_memory_buffer()
        logger.info(f"内存缓冲区大小: {len(buffer)}")

        # 获取配置
        config = await log_manager.get_config()
        logger.info(f"日志配置: 级别={config.log_level.value}, 输出={[o.value for o in config.outputs]}")

        # 获取管理器统计
        mgr_stats = await log_manager.get_statistics()
        logger.info(f"管理器统计: {mgr_stats}")

    finally:
        await log_manager.cleanup()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
