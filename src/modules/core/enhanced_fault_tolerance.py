"""
增强的容错和故障恢复机制

功能：
1. 断路器模式 - 防止级联故障
2. 重试机制 - 指数退避重试
3. 故障隔离 - 隔离故障组件
4. 自动恢复 - 自动检测和恢复
5. 健康检查 - 全面的健康状态监控
"""

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union
from functools import wraps

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """断路器状态"""
    CLOSED = "closed"       # 正常状态，允许请求
    OPEN = "open"          # 断开状态，拒绝请求
    HALF_OPEN = "half_open"  # 半开状态，测试请求


class FaultType(Enum):
    """故障类型"""
    TRANSIENT = "transient"    # 瞬时故障
    PERSISTENT = "persistent"  # 持久故障
    CRITICAL = "critical"      # 关键故障
    TIMEOUT = "timeout"        # 超时


@dataclass
class FaultEvent:
    """故障事件"""
    component: str
    fault_type: FaultType
    error_message: str
    timestamp: datetime = field(default_factory=datetime.now)
    recovery_attempts: int = 0
    resolved: bool = False


@dataclass
class RetryPolicy:
    """重试策略"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    retryable_exceptions: Set[Type[Exception]] = field(default_factory=set)
    
    def calculate_delay(self, attempt: int) -> float:
        """计算重试延迟"""
        delay = self.base_delay * (self.exponential_base ** attempt)
        # 添加随机抖动
        jitter = random.uniform(0, delay * 0.1)
        return min(delay + jitter, self.max_delay)


class CircuitBreaker:
    """断路器 - 防止级联故障"""
    
    def __init__(self, 
                 name: str,
                 failure_threshold: int = 5,
                 recovery_timeout: float = 60.0,
                 half_open_max_calls: int = 3):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0
        self._lock = asyncio.Lock()
        self._stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "rejected_calls": 0
        }
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """执行带断路器保护的调用"""
        async with self._lock:
            self._stats["total_calls"] += 1
            
            # 检查断路器状态
            if self.state == CircuitState.OPEN:
                # 检查是否可以进入半开状态
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    logger.info(f"断路器 {self.name} 进入半开状态")
                else:
                    self._stats["rejected_calls"] += 1
                    raise CircuitBreakerOpen(f"断路器 {self.name} 处于断开状态")
            
            elif self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.half_open_max_calls:
                    self._stats["rejected_calls"] += 1
                    raise CircuitBreakerOpen(f"断路器 {self.name} 半开状态调用过多")
                self.half_open_calls += 1
        
        # 执行调用
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        """处理成功调用"""
        async with self._lock:
            self._stats["successful_calls"] += 1
            
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                # 连续成功足够次数后关闭断路器
                if self.success_count >= self.half_open_max_calls:
                    self._reset()
                    logger.info(f"断路器 {self.name} 已关闭")
            else:
                self.failure_count = 0
    
    async def _on_failure(self):
        """处理失败调用"""
        async with self._lock:
            self._stats["failed_calls"] += 1
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.state == CircuitState.HALF_OPEN:
                # 半开状态失败，重新断开
                self.state = CircuitState.OPEN
                logger.warning(f"断路器 {self.name} 半开状态失败，重新断开")
            elif self.failure_count >= self.failure_threshold:
                # 达到失败阈值，断开断路器
                self.state = CircuitState.OPEN
                logger.warning(f"断路器 {self.name} 已断开，失败次数: {self.failure_count}")
    
    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试重置"""
        if self.last_failure_time is None:
            return True
        return datetime.now() - self.last_failure_time >= timedelta(seconds=self.recovery_timeout)
    
    def _reset(self):
        """重置断路器"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_calls = 0
        self.last_failure_time = None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "state": self.state.value,
            "failure_count": self.failure_count
        }


class CircuitBreakerOpen(Exception):
    """断路器断开异常"""
    pass


class RetryHandler:
    """重试处理器"""
    
    def __init__(self, policy: Optional[RetryPolicy] = None):
        self.policy = policy or RetryPolicy()
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """执行带重试的调用"""
        last_exception = None
        
        for attempt in range(self.policy.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
                    
            except Exception as e:
                last_exception = e
                
                # 检查是否应该重试
                if attempt < self.policy.max_retries:
                    if self._should_retry(e):
                        delay = self.policy.calculate_delay(attempt)
                        logger.warning(f"调用失败，{delay:.2f}秒后重试 ({attempt + 1}/{self.policy.max_retries}): {e}")
                        await asyncio.sleep(delay)
                    else:
                        raise
                else:
                    break
        
        raise last_exception
    
    def _should_retry(self, exception: Exception) -> bool:
        """检查是否应该重试"""
        if not self.policy.retryable_exceptions:
            return True
        return type(exception) in self.policy.retryable_exceptions


def with_retry(policy: Optional[RetryPolicy] = None):
    """重试装饰器"""
    def decorator(func: Callable):
        handler = RetryHandler(policy)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await handler.execute(func, *args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 同步函数不支持异步重试
            return func(*args, **kwargs)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def with_circuit_breaker(breaker: CircuitBreaker):
    """断路器装饰器"""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 同步函数不支持异步断路器
            return func(*args, **kwargs)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


class FaultIsolation:
    """故障隔离管理器"""
    
    def __init__(self):
        self.isolated_components: Set[str] = set()
        self.fault_history: List[FaultEvent] = []
        self._lock = asyncio.Lock()
    
    async def isolate(self, component: str, fault_type: FaultType, error_message: str):
        """隔离故障组件"""
        async with self._lock:
            if component not in self.isolated_components:
                self.isolated_components.add(component)
                
                fault = FaultEvent(
                    component=component,
                    fault_type=fault_type,
                    error_message=error_message
                )
                self.fault_history.append(fault)
                
                logger.warning(f"组件 {component} 已被隔离，故障类型: {fault_type.value}")
    
    async def recover(self, component: str) -> bool:
        """恢复组件"""
        async with self._lock:
            if component in self.isolated_components:
                self.isolated_components.discard(component)
                
                # 更新故障记录
                for fault in reversed(self.fault_history):
                    if fault.component == component and not fault.resolved:
                        fault.resolved = True
                        break
                
                logger.info(f"组件 {component} 已恢复")
                return True
            return False
    
    def is_isolated(self, component: str) -> bool:
        """检查组件是否被隔离"""
        return component in self.isolated_components
    
    def get_isolated_components(self) -> Set[str]:
        """获取被隔离的组件列表"""
        return self.isolated_components.copy()
    
    def get_fault_history(self, component: Optional[str] = None) -> List[FaultEvent]:
        """获取故障历史"""
        if component:
            return [f for f in self.fault_history if f.component == component]
        return self.fault_history.copy()


class AutoRecovery:
    """自动恢复管理器"""
    
    def __init__(self, check_interval: float = 30.0):
        self.check_interval = check_interval
        self.isolation = FaultIsolation()
        self.recovery_handlers: Dict[str, Callable] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._stats = {
            "recovery_attempts": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0,
            "recovery_time": {},  # 记录每个组件的恢复时间
            "recovery_history": []  # 恢复历史记录
        }
        # 恢复策略配置
        self.recovery_strategies = {
            "exponential_backoff": True,  # 指数退避恢复
            "parallel_recovery": True,  # 并行恢复多个组件
            "priority_based": True,  # 基于优先级的恢复
            "graceful_degradation": True  # 优雅降级
        }
        # 组件优先级
        self.component_priorities = {
            "database": 10,
            "redis": 9,
            "exchange_api": 8,
            "strategy": 7,
            "execution": 6,
            "monitoring": 5,
            "api_server": 4
        }
    
    async def initialize(self):
        """初始化自动恢复"""
        self._running = True
        self._task = asyncio.create_task(self._recovery_loop())
        logger.info("自动恢复管理器初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("自动恢复管理器清理完成")
    
    def register_recovery_handler(self, component: str, handler: Callable[[], bool]):
        """注册恢复处理器"""
        self.recovery_handlers[component] = handler
    
    async def _recovery_loop(self):
        """恢复检查循环"""
        while self._running:
            try:
                await self._attempt_recovery()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"恢复循环错误: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _attempt_recovery(self):
        """尝试恢复被隔离的组件"""
        isolated = self.isolation.get_isolated_components()
        
        if not isolated:
            return
        
        # 按优先级排序组件
        if self.recovery_strategies["priority_based"]:
            sorted_components = sorted(
                isolated,
                key=lambda c: self.component_priorities.get(c, 5),
                reverse=True
            )
        else:
            sorted_components = list(isolated)
        
        # 并行恢复多个组件
        if self.recovery_strategies["parallel_recovery"]:
            recovery_tasks = []
            for component in sorted_components:
                if component in self.recovery_handlers:
                    recovery_tasks.append(self._recover_component(component))
            
            if recovery_tasks:
                await asyncio.gather(*recovery_tasks, return_exceptions=True)
        else:
            # 串行恢复
            for component in sorted_components:
                if component in self.recovery_handlers:
                    await self._recover_component(component)
    
    async def _recover_component(self, component: str):
        """恢复单个组件"""
        # 检查是否需要指数退避
        if self.recovery_strategies["exponential_backoff"]:
            last_recovery_time = self._stats["recovery_time"].get(component, 0)
            current_time = time.time()
            
            # 计算退避时间
            failure_count = len([f for f in self.isolation.get_fault_history(component) if not f.resolved])
            base_delay = 10  # 基础延迟10秒
            max_delay = 300  # 最大延迟5分钟
            delay = min(base_delay * (2 ** (failure_count - 1)), max_delay)
            
            if current_time - last_recovery_time < delay:
                logger.debug(f"组件 {component} 处于退避期，跳过本次恢复尝试")
                return
        
        self._stats["recovery_attempts"] += 1
        start_time = time.time()
        
        try:
            handler = self.recovery_handlers[component]
            
            if asyncio.iscoroutinefunction(handler):
                success = await handler()
            else:
                success = handler()
            
            if success:
                await self.isolation.recover(component)
                self._stats["successful_recoveries"] += 1
                recovery_duration = time.time() - start_time
                self._stats["recovery_time"][component] = time.time()
                
                # 记录恢复历史
                self._stats["recovery_history"].append({
                    "component": component,
                    "timestamp": time.time(),
                    "duration": recovery_duration,
                    "success": True
                })
                
                logger.info(f"组件 {component} 自动恢复成功，耗时 {recovery_duration:.2f}秒")
            else:
                self._stats["failed_recoveries"] += 1
                self._stats["recovery_time"][component] = time.time()
                
                # 记录恢复历史
                self._stats["recovery_history"].append({
                    "component": component,
                    "timestamp": time.time(),
                    "duration": time.time() - start_time,
                    "success": False
                })
                
                logger.warning(f"组件 {component} 自动恢复失败")
                
        except Exception as e:
            self._stats["failed_recoveries"] += 1
            self._stats["recovery_time"][component] = time.time()
            
            # 记录恢复历史
            self._stats["recovery_history"].append({
                "component": component,
                "timestamp": time.time(),
                "duration": time.time() - start_time,
                "success": False,
                "error": str(e)
            })
            
            logger.error(f"组件 {component} 恢复过程出错: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        # 限制恢复历史记录的大小
        recovery_history = self._stats["recovery_history"][-50:]  # 只返回最近50条记录
        
        return {
            **self._stats,
            "recovery_history": recovery_history,
            "isolated_components": len(self.isolation.get_isolated_components()),
            "recovery_strategies": self.recovery_strategies,
            "component_priorities": self.component_priorities
        }


class EnhancedFaultTolerance:
    """增强的容错管理器"""
    
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.isolation = FaultIsolation()
        self.auto_recovery = AutoRecovery()
        self.retry_policies: Dict[str, RetryPolicy] = {}
        self._initialized = False
    
    async def initialize(self):
        """初始化容错管理器"""
        await self.auto_recovery.initialize()
        self._initialized = True
        logger.info("容错管理器初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        await self.auto_recovery.cleanup()
        self._initialized = False
        logger.info("容错管理器清理完成")
    
    def get_circuit_breaker(self, name: str, 
                           failure_threshold: int = 5,
                           recovery_timeout: float = 60.0) -> CircuitBreaker:
        """获取或创建断路器"""
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout
            )
        return self.circuit_breakers[name]
    
    def get_retry_policy(self, name: str) -> RetryPolicy:
        """获取或创建重试策略"""
        if name not in self.retry_policies:
            self.retry_policies[name] = RetryPolicy()
        return self.retry_policies[name]
    
    async def execute_with_protection(self,
                                     func: Callable,
                                     component: str,
                                     *args,
                                     use_circuit_breaker: bool = True,
                                     use_retry: bool = True,
                                     **kwargs) -> Any:
        """执行受保护的调用"""
        if not self._initialized:
            raise RuntimeError("容错管理器未初始化")
        
        # 检查组件是否被隔离
        if self.isolation.is_isolated(component):
            raise ComponentIsolated(f"组件 {component} 已被隔离")
        
        try:
            # 构建调用链
            if use_circuit_breaker and use_retry:
                breaker = self.get_circuit_breaker(component)
                policy = self.get_retry_policy(component)
                handler = RetryHandler(policy)
                
                async def wrapped_func():
                    return await handler.execute(func, *args, **kwargs)
                
                return await breaker.call(wrapped_func)
            
            elif use_circuit_breaker:
                breaker = self.get_circuit_breaker(component)
                return await breaker.call(func, *args, **kwargs)
            
            elif use_retry:
                policy = self.get_retry_policy(component)
                handler = RetryHandler(policy)
                return await handler.execute(func, *args, **kwargs)
            
            else:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
                    
        except Exception as e:
            # 记录故障
            fault_type = self._classify_fault(e)
            await self.isolation.isolate(component, fault_type, str(e))
            raise
    
    def _classify_fault(self, exception: Exception) -> FaultType:
        """分类故障类型"""
        if isinstance(exception, asyncio.TimeoutError):
            return FaultType.TIMEOUT
        elif isinstance(exception, CircuitBreakerOpen):
            return FaultType.PERSISTENT
        elif isinstance(exception, ComponentIsolated):
            return FaultType.CRITICAL
        else:
            return FaultType.TRANSIENT
    
    def register_recovery_handler(self, component: str, handler: Callable[[], bool]):
        """注册恢复处理器"""
        self.auto_recovery.register_recovery_handler(component, handler)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "circuit_breakers": {
                name: cb.get_stats() 
                for name, cb in self.circuit_breakers.items()
            },
            "isolated_components": list(self.isolation.get_isolated_components()),
            "auto_recovery": self.auto_recovery.get_stats()
        }


class ComponentIsolated(Exception):
    """组件被隔离异常"""
    pass


# 使用示例
async def example_usage():
    """使用示例"""
    # 创建容错管理器
    ft = EnhancedFaultTolerance()
    await ft.initialize()
    
    try:
        # 模拟一个可能失败的函数
        call_count = 0
        
        async def unreliable_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError(f"模拟连接错误 #{call_count}")
            return "成功!"
        
        # 使用断路器和重试执行
        result = await ft.execute_with_protection(
            unreliable_function,
            "test_component",
            use_circuit_breaker=True,
            use_retry=True
        )
        logger.info(f"执行结果: {result}")
        
        # 获取统计
        stats = ft.get_stats()
        logger.info(f"容错统计: {stats}")
        
    finally:
        await ft.cleanup()


if __name__ == "__main__":
    asyncio.run(example_usage())
