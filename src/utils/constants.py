"""
系统常量配置

定义系统中使用的所有常量
"""

from enum import Enum
from typing import Final


# 系统信息
SYSTEM_NAME: Final[str] = "OpenClaw Trading"
SYSTEM_VERSION: Final[str] = "1.0.1"


# 交易相关常量
class TradingConstants:
    """交易常量"""
    
    # 最小置信度阈值
    MIN_CONFIDENCE: Final[float] = 0.65
    
    # 最大持仓数
    MAX_POSITIONS: Final[int] = 3
    
    # 单笔交易风险比例
    RISK_PER_TRADE: Final[float] = 0.02
    
    # 最大杠杆
    MAX_LEVERAGE: Final[float] = 3.0
    
    # 止损比例
    DEFAULT_STOP_LOSS: Final[float] = 0.03
    
    # 止盈比例
    DEFAULT_TAKE_PROFIT: Final[float] = 0.06
    
    # 最大回撤
    MAX_DRAWDOWN: Final[float] = 0.15
    
    # 交易对列表
    DEFAULT_SYMBOLS: Final[list] = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
    
    # 时间框架
    TIMEFRAMES: Final[list] = ["1m", "5m", "15m", "1h", "4h", "1d"]


# AI相关常量
class AIConstants:
    """AI常量"""
    
    # 默认模型（与 config/config.yaml llm.default_model 对齐）
    DEFAULT_MODEL: Final[str] = "trading-fast"
    
    # 最大Token数
    MAX_TOKENS: Final[int] = 2000
    
    # 温度参数
    DEFAULT_TEMPERATURE: Final[float] = 0.7
    
    # 最大重试次数
    MAX_RETRIES: Final[int] = 3
    
    # 请求超时
    REQUEST_TIMEOUT: Final[float] = 60.0
    
    # 分析间隔
    ANALYSIS_INTERVAL: Final[int] = 60


# 风险管理常量
class RiskConstants:
    """风险常量"""
    
    # 风险等级
    class RiskLevel(str, Enum):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        CRITICAL = "critical"
    
    # 最大仓位占比
    MAX_POSITION_SIZE_PERCENT: Final[float] = 0.2
    
    # 日损失限制
    DAILY_LOSS_LIMIT: Final[float] = 0.05
    
    # 周损失限制
    WEEKLY_LOSS_LIMIT: Final[float] = 0.10
    
    # 月损失限制
    MONTHLY_LOSS_LIMIT: Final[float] = 0.15
    
    # 风险监控间隔
    MONITORING_INTERVAL: Final[int] = 10


# 数据相关常量
class DataConstants:
    """数据常量"""
    
    # 历史数据最大天数
    MAX_HISTORICAL_DAYS: Final[int] = 365
    
    # 缓存过期时间
    CACHE_TTL: Final[int] = 300
    
    # 最大缓存数量
    MAX_CACHE_SIZE: Final[int] = 1000
    
    # 数据库连接池大小
    DB_POOL_SIZE: Final[int] = 10
    
    # 数据库最大溢出
    DB_MAX_OVERFLOW: Final[int] = 20


# API相关常量
class APIConstants:
    """API常量"""
    
    # 默认主机
    DEFAULT_HOST: Final[str] = "0.0.0.0"
    
    # 默认端口
    DEFAULT_PORT: Final[int] = 8000
    
    # API版本
    API_VERSION: Final[str] = "v1"
    
    # 请求速率限制
    RATE_LIMIT: Final[int] = 100
    
    # 请求超时
    REQUEST_TIMEOUT: Final[int] = 30


# 日志相关常量
class LogConstants:
    """日志常量"""
    
    # 默认日志级别
    DEFAULT_LOG_LEVEL: Final[str] = "INFO"
    
    # 日志文件最大大小
    MAX_LOG_SIZE: Final[str] = "10MB"
    
    # 日志备份数量
    BACKUP_COUNT: Final[int] = 5
    
    # 日志格式
    LOG_FORMAT: Final[str] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


# 通知相关常量
class NotificationConstants:
    """通知常量"""
    
    # 通知类型
    class NotificationType(str, Enum):
        TRADE = "trade"
        RISK = "risk"
        SYSTEM = "system"
        ERROR = "error"
    
    # 通知优先级
    class Priority(str, Enum):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        URGENT = "urgent"


# 监控相关常量
class MonitoringConstants:
    """监控常量"""
    
    # 健康检查间隔
    HEALTH_CHECK_INTERVAL: Final[int] = 60
    
    # 性能监控间隔
    PERFORMANCE_MONITOR_INTERVAL: Final[int] = 60
    
    # 最大CPU使用率
    MAX_CPU_USAGE: Final[float] = 80.0
    
    # 最大内存使用率
    MAX_MEMORY_USAGE: Final[float] = 80.0
    
    # 最大磁盘使用率
    MAX_DISK_USAGE: Final[float] = 90.0


# 文件路径常量
class PathConstants:
    """路径常量"""
    
    # 配置目录
    CONFIG_DIR: Final[str] = "config"
    
    # 数据目录
    DATA_DIR: Final[str] = "data"
    
    # 日志目录
    LOGS_DIR: Final[str] = "logs"
    
    # 备份目录
    BACKUP_DIR: Final[str] = "backups"
    
    # 插件目录
    PLUGIN_DIR: Final[str] = "plugins"
    
    # 工作区目录
    WORKSPACE_DIR: Final[str] = "workspace"


# 错误消息常量
class ErrorMessages:
    """错误消息"""
    
    # 通用错误
    UNKNOWN_ERROR: Final[str] = "未知错误"
    TIMEOUT_ERROR: Final[str] = "操作超时"
    NETWORK_ERROR: Final[str] = "网络错误"
    
    # 交易错误
    INSUFFICIENT_BALANCE: Final[str] = "余额不足"
    INVALID_SYMBOL: Final[str] = "无效的交易对"
    ORDER_FAILED: Final[str] = "订单失败"
    
    # AI错误
    LLM_ERROR: Final[str] = "AI模型调用失败"
    PARSE_ERROR: Final[str] = "解析错误"
    
    # 配置错误
    CONFIG_ERROR: Final[str] = "配置错误"
    API_KEY_MISSING: Final[str] = "API密钥缺失"


# 成功消息常量
class SuccessMessages:
    """成功消息"""
    
    # 通用成功
    OPERATION_SUCCESS: Final[str] = "操作成功"
    SYSTEM_STARTED: Final[str] = "系统启动成功"
    SYSTEM_STOPPED: Final[str] = "系统停止成功"
    
    # 交易成功
    ORDER_PLACED: Final[str] = "订单已提交"
    ORDER_FILLED: Final[str] = "订单已成交"
    POSITION_OPENED: Final[str] = "仓位已开启"
    POSITION_CLOSED: Final[str] = "仓位已关闭"
    
    # AI成功
    ANALYSIS_COMPLETE: Final[str] = "分析完成"
    DECISION_MADE: Final[str] = "决策完成"
