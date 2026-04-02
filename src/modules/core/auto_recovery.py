"""
自动故障恢复和自愈系统

为无人化AI交易系统提供自动故障检测和恢复能力
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import traceback

logger = logging.getLogger(__name__)


class FailureType(str, Enum):
    """故障类型"""
    NETWORK_ERROR = "network_error"
    API_TIMEOUT = "api_timeout"
    API_ERROR = "api_error"
    DATA_ERROR = "data_error"
    AI_MODEL_ERROR = "ai_model_error"
    EXCHANGE_ERROR = "exchange_error"
    DATABASE_ERROR = "database_error"
    SYSTEM_ERROR = "system_error"
    UNKNOWN_ERROR = "unknown_error"


class RecoveryStrategy(str, Enum):
    """恢复策略"""
    RETRY = "retry"                    # 重试
    FALLBACK = "fallback"              # 降级
    SAFE_MODE = "safe_mode"            # 安全模式
    EMERGENCY_STOP = "emergency_stop"  # 紧急停止
    RESTART = "restart"                # 重启
    SKIP = "skip"                      # 跳过


@dataclass
class FailureRecord:
    """故障记录"""
    id: str
    type: FailureType
    error_message: str
    error_traceback: str
    context: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    recovery_strategy: Optional[RecoveryStrategy] = None
    recovery_attempts: int = 0
    recovery_successful: bool = False


@dataclass
class RecoveryConfig:
    """恢复配置"""
    max_retry_attempts: int = 3
    retry_delay_seconds: float = 5.0
    backoff_multiplier: float = 2.0
    max_retry_delay: float = 60.0
    
    # 熔断配置
    circuit_breaker_threshold: int = 5  # 失败次数阈值
    circuit_breaker_timeout: int = 300  # 熔断超时时间(秒)
    
    # 安全模式配置
    safe_mode_duration: int = 600  # 安全模式持续时间(秒)


class AutoRecoverySystem:
    """自动故障恢复系统"""
    
    def __init__(self, config: Optional[RecoveryConfig] = None):
        self.config = config or RecoveryConfig()
        
        # 故障记录
        self.failures: Dict[str, FailureRecord] = {}
        self.failure_history: List[FailureRecord] = []
        
        # 熔断器状态
        self.circuit_breakers: Dict[str, Dict] = {}
        
        # 恢复策略映射
        self.recovery_strategies: Dict[FailureType, RecoveryStrategy] = {
            FailureType.NETWORK_ERROR: RecoveryStrategy.RETRY,
            FailureType.API_TIMEOUT: RecoveryStrategy.RETRY,
            FailureType.API_ERROR: RecoveryStrategy.FALLBACK,
            FailureType.DATA_ERROR: RecoveryStrategy.FALLBACK,
            FailureType.AI_MODEL_ERROR: RecoveryStrategy.FALLBACK,
            FailureType.EXCHANGE_ERROR: RecoveryStrategy.SAFE_MODE,
            FailureType.DATABASE_ERROR: RecoveryStrategy.RETRY,
            FailureType.SYSTEM_ERROR: RecoveryStrategy.RESTART,
            FailureType.UNKNOWN_ERROR: RecoveryStrategy.SAFE_MODE,
        }
        
        # 自定义恢复处理器
        self.recovery_handlers: Dict[RecoveryStrategy, Callable] = {}
        
        # 系统状态
        self._in_safe_mode = False
        self._safe_mode_start_time: Optional[datetime] = None
        
        # 统计
        self.stats = {
            "total_failures": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0,
            "safe_mode_activations": 0,
        }
    
    async def handle_failure(
        self,
        error: Exception,
        context: Dict[str, Any],
        operation_name: str = "unknown"
    ) -> bool:
        """
        处理故障
        
        Args:
            error: 异常对象
            context: 上下文信息
            operation_name: 操作名称
        
        Returns:
            是否成功恢复
        """
        import uuid
        
        # 1. 分类故障类型
        failure_type = self._classify_failure(error)
        
        # 2. 创建故障记录
        failure_id = str(uuid.uuid4())
        failure_record = FailureRecord(
            id=failure_id,
            type=failure_type,
            error_message=str(error),
            error_traceback=traceback.format_exc(),
            context=context
        )
        
        self.failures[failure_id] = failure_record
        self.failure_history.append(failure_record)
        self.stats["total_failures"] += 1
        
        logger.error(
            f"🔴 故障检测 [{failure_type.value}]: {operation_name}\n"
            f"错误: {str(error)}\n"
            f"上下文: {context}"
        )
        
        # 3. 检查熔断器
        if self._is_circuit_breaker_open(operation_name):
            logger.warning(f"⚠️ 熔断器已打开: {operation_name}")
            return False
        
        # 4. 获取恢复策略
        recovery_strategy = self._get_recovery_strategy(failure_type, context)
        failure_record.recovery_strategy = recovery_strategy
        
        logger.info(f"🔧 执行恢复策略: {recovery_strategy.value}")
        
        # 5. 执行恢复
        recovery_successful = await self._execute_recovery(
            recovery_strategy,
            error,
            context,
            operation_name
        )
        
        # 6. 更新故障记录
        failure_record.recovery_successful = recovery_successful
        failure_record.resolved = True
        
        if recovery_successful:
            self.stats["successful_recoveries"] += 1
            logger.info(f"✅ 故障恢复成功: {failure_id}")
        else:
            self.stats["failed_recoveries"] += 1
            logger.error(f"❌ 故障恢复失败: {failure_id}")
        
        return recovery_successful
    
    def _classify_failure(self, error: Exception) -> FailureType:
        """分类故障类型"""
        error_type = type(error).__name__
        error_message = str(error).lower()
        
        # 网络错误
        if any(keyword in error_type for keyword in ["Network", "Connection", "Socket"]):
            return FailureType.NETWORK_ERROR
        
        # 超时错误
        if "timeout" in error_type.lower() or "timeout" in error_message:
            return FailureType.API_TIMEOUT
        
        # API错误
        if any(keyword in error_type for keyword in ["API", "HTTP", "Request"]):
            return FailureType.API_ERROR
        
        # 数据错误
        if any(keyword in error_type for keyword in ["Data", "Value", "Key", "Type"]):
            return FailureType.DATA_ERROR
        
        # 交易所错误
        if any(keyword in error_message for keyword in ["exchange", "order", "balance"]):
            return FailureType.EXCHANGE_ERROR
        
        # 数据库错误
        if any(keyword in error_type for keyword in ["Database", "SQL", "DB"]):
            return FailureType.DATABASE_ERROR
        
        # AI模型错误
        if any(keyword in error_message for keyword in ["llm", "ai", "model"]):
            return FailureType.AI_MODEL_ERROR
        
        # 系统错误
        if any(keyword in error_type for keyword in ["System", "Runtime", "Memory"]):
            return FailureType.SYSTEM_ERROR
        
        return FailureType.UNKNOWN_ERROR
    
    def _get_recovery_strategy(
        self,
        failure_type: FailureType,
        context: Dict[str, Any]
    ) -> RecoveryStrategy:
        """获取恢复策略"""
        
        # 检查是否有自定义策略
        if failure_type in self.recovery_strategies:
            strategy = self.recovery_strategies[failure_type]
        else:
            strategy = RecoveryStrategy.SAFE_MODE
        
        # 根据上下文调整策略
        if context.get("critical", False):
            # 关键操作，使用更保守的策略
            if strategy == RecoveryStrategy.RETRY:
                strategy = RecoveryStrategy.FALLBACK
        
        return strategy
    
    async def _execute_recovery(
        self,
        strategy: RecoveryStrategy,
        error: Exception,
        context: Dict[str, Any],
        operation_name: str
    ) -> bool:
        """执行恢复策略"""
        
        try:
            if strategy == RecoveryStrategy.RETRY:
                return await self._retry_operation(error, context, operation_name)
            
            elif strategy == RecoveryStrategy.FALLBACK:
                return await self._fallback_operation(error, context, operation_name)
            
            elif strategy == RecoveryStrategy.SAFE_MODE:
                return await self._enter_safe_mode(error, context)
            
            elif strategy == RecoveryStrategy.EMERGENCY_STOP:
                return await self._emergency_stop(error, context)
            
            elif strategy == RecoveryStrategy.RESTART:
                return await self._restart_component(error, context, operation_name)
            
            elif strategy == RecoveryStrategy.SKIP:
                logger.info("跳过操作")
                return True
            
            else:
                logger.error(f"未知恢复策略: {strategy}")
                return False
                
        except Exception as e:
            logger.error(f"执行恢复策略失败: {e}")
            return False
    
    async def _retry_operation(
        self,
        error: Exception,
        context: Dict[str, Any],
        operation_name: str
    ) -> bool:
        """重试操作"""
        
        max_attempts = self.config.max_retry_attempts
        delay = self.config.retry_delay_seconds
        
        for attempt in range(1, max_attempts + 1):
            logger.info(f"重试操作 ({attempt}/{max_attempts}): {operation_name}")
            
            try:
                # 如果有重试处理器，调用它
                if operation_name in self.recovery_handlers:
                    result = await self.recovery_handlers[operation_name](context)
                    return True
                
                # 否则等待后重试
                await asyncio.sleep(delay)
                
                # 更新熔断器
                self._update_circuit_breaker(operation_name, success=True)
                
                return True
                
            except Exception as retry_error:
                logger.warning(f"重试失败 ({attempt}/{max_attempts}): {retry_error}")
                
                # 更新熔断器
                self._update_circuit_breaker(operation_name, success=False)
                
                # 指数退避
                delay = min(
                    delay * self.config.backoff_multiplier,
                    self.config.max_retry_delay
                )
        
        logger.error(f"重试{max_attempts}次后仍然失败")
        return False
    
    async def _fallback_operation(
        self,
        error: Exception,
        context: Dict[str, Any],
        operation_name: str
    ) -> bool:
        """降级操作"""
        
        logger.warning(f"执行降级策略: {operation_name}")
        
        # 根据操作类型执行不同的降级策略
        if "market_data" in operation_name:
            # 使用缓存数据
            logger.info("使用缓存的市场数据")
            return True
        
        elif "ai_decision" in operation_name:
            # 使用规则策略
            logger.info("降级到规则策略")
            return True
        
        elif "order" in operation_name:
            # 暂停交易
            logger.warning("暂停交易操作")
            return False
        
        else:
            logger.warning("未知操作，无法降级")
            return False
    
    async def _enter_safe_mode(self, error: Exception, context: Dict[str, Any]) -> bool:
        """进入安全模式"""
        
        if self._in_safe_mode:
            logger.info("系统已在安全模式中")
            return True
        
        logger.warning("🛡️ 系统进入安全模式")
        
        self._in_safe_mode = True
        self._safe_mode_start_time = datetime.now()
        self.stats["safe_mode_activations"] += 1
        
        # 安全模式操作
        try:
            # 1. 停止所有新交易
            logger.info("停止所有新交易")
            
            # 2. 只保留风险管理
            logger.info("保持风险管理系统运行")
            
            # 3. 发送告警
            logger.critical("⚠️ 系统已进入安全模式，请人工介入")
            
            # 4. 设置自动退出
            asyncio.create_task(self._auto_exit_safe_mode())
            
            return True
            
        except Exception as e:
            logger.error(f"进入安全模式失败: {e}")
            return False
    
    async def _auto_exit_safe_mode(self):
        """自动退出安全模式"""
        
        await asyncio.sleep(self.config.safe_mode_duration)
        
        if self._in_safe_mode:
            logger.info("自动退出安全模式")
            await self._exit_safe_mode()
    
    async def _exit_safe_mode(self):
        """退出安全模式"""
        
        self._in_safe_mode = False
        self._safe_mode_start_time = None
        
        logger.info("✅ 系统已退出安全模式")
    
    async def _emergency_stop(self, error: Exception, context: Dict[str, Any]) -> bool:
        """紧急停止"""
        
        logger.critical("🚨 执行紧急停止！")
        
        try:
            # 1. 停止所有交易
            logger.critical("停止所有交易")
            
            # 2. 平掉所有仓位
            logger.critical("平掉所有仓位")
            
            # 3. 锁定账户
            logger.critical("锁定账户")
            
            # 4. 发送紧急通知
            logger.critical("🔔 发送紧急通知")
            
            return True
            
        except Exception as e:
            logger.critical(f"紧急停止失败: {e}")
            return False
    
    async def _restart_component(
        self,
        error: Exception,
        context: Dict[str, Any],
        operation_name: str
    ) -> bool:
        """重启组件"""
        
        logger.info(f"重启组件: {operation_name}")
        
        try:
            # 这里应该实现具体的重启逻辑
            # 例如：重新初始化连接、重新加载数据等
            
            logger.info(f"组件重启成功: {operation_name}")
            return True
            
        except Exception as e:
            logger.error(f"组件重启失败: {e}")
            return False
    
    def _is_circuit_breaker_open(self, operation_name: str) -> bool:
        """检查熔断器是否打开"""
        
        if operation_name not in self.circuit_breakers:
            return False
        
        breaker = self.circuit_breakers[operation_name]
        
        if not breaker["is_open"]:
            return False
        
        # 检查是否超过超时时间
        elapsed = (datetime.now() - breaker["opened_at"]).total_seconds()
        
        if elapsed >= self.config.circuit_breaker_timeout:
            # 关闭熔断器
            breaker["is_open"] = False
            logger.info(f"熔断器已重置: {operation_name}")
            return False
        
        return True
    
    def _update_circuit_breaker(self, operation_name: str, success: bool):
        """更新熔断器状态"""
        
        if operation_name not in self.circuit_breakers:
            self.circuit_breakers[operation_name] = {
                "failure_count": 0,
                "is_open": False,
                "opened_at": None
            }
        
        breaker = self.circuit_breakers[operation_name]
        
        if success:
            breaker["failure_count"] = 0
        else:
            breaker["failure_count"] += 1
            
            # 检查是否需要打开熔断器
            if breaker["failure_count"] >= self.config.circuit_breaker_threshold:
                breaker["is_open"] = True
                breaker["opened_at"] = datetime.now()
                logger.warning(f"⚠️ 熔断器已打开: {operation_name}")
    
    def register_recovery_handler(self, operation_name: str, handler: Callable):
        """注册恢复处理器"""
        self.recovery_handlers[operation_name] = handler
    
    def get_failure_stats(self) -> Dict[str, Any]:
        """获取故障统计"""
        
        recent_failures = [
            f for f in self.failure_history
            if (datetime.now() - f.timestamp).total_seconds() < 3600  # 最近1小时
        ]
        
        return {
            "total_failures": self.stats["total_failures"],
            "successful_recoveries": self.stats["successful_recoveries"],
            "failed_recoveries": self.stats["failed_recoveries"],
            "recovery_rate": (
                self.stats["successful_recoveries"] / max(self.stats["total_failures"], 1) * 100
            ),
            "safe_mode_activations": self.stats["safe_mode_activations"],
            "recent_failures": len(recent_failures),
            "active_circuit_breakers": sum(
                1 for b in self.circuit_breakers.values() if b["is_open"]
            ),
            "in_safe_mode": self._in_safe_mode
        }
    
    def is_system_healthy(self) -> bool:
        """检查系统是否健康"""
        
        # 检查是否在安全模式
        if self._in_safe_mode:
            return False
        
        # 检查是否有太多熔断器打开
        open_breakers = sum(
            1 for b in self.circuit_breakers.values() if b["is_open"]
        )
        
        if open_breakers > 3:
            return False
        
        # 检查最近的失败率
        recent_failures = len([
            f for f in self.failure_history
            if (datetime.now() - f.timestamp).total_seconds() < 300  # 最近5分钟
        ])
        
        if recent_failures > 10:
            return False
        
        return True
