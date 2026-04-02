"""
异步超时处理工具

提供统一的超时处理机制
"""

import asyncio
import logging
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, ParamSpec

logger = logging.getLogger(__name__)

P = ParamSpec('P')
T = TypeVar('T')


def with_timeout(timeout_seconds: float):
    """
    超时装饰器
    
    Args:
        timeout_seconds: 超时秒数
    
    Example:
        @with_timeout(30)
        async def slow_operation():
            await asyncio.sleep(60)
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                async with asyncio.timeout(timeout_seconds):
                    return await func(*args, **kwargs)
            except asyncio.TimeoutError:
                logger.error(f"{func.__name__} 执行超时 ({timeout_seconds}秒)")
                raise TimeoutError(f"{func.__name__} 执行超时 ({timeout_seconds}秒)")
            except Exception as e:
                logger.error(f"{func.__name__} 执行失败: {e}")
                raise
        return wrapper
    return decorator


async def run_with_timeout(
    coro: Any,
    timeout_seconds: float,
    default_value: Optional[T] = None,
    raise_on_timeout: bool = False
) -> Optional[T]:
    """
    带超时执行协程
    
    Args:
        coro: 协程对象
        timeout_seconds: 超时秒数
        default_value: 超时时返回的默认值
        raise_on_timeout: 是否在超时时抛出异常
    
    Returns:
        协程返回值或默认值
    
    Example:
        result = await run_with_timeout(
            fetch_data(),
            timeout_seconds=30,
            default_value=None
        )
    """
    try:
        async with asyncio.timeout(timeout_seconds):
            return await coro
    except asyncio.TimeoutError:
        logger.warning(f"操作超时 ({timeout_seconds}秒)")
        if raise_on_timeout:
            raise TimeoutError(f"操作超时 ({timeout_seconds}秒)")
        return default_value
    except Exception as e:
        logger.error(f"操作失败: {e}")
        raise


class TimeoutContext:
    """超时上下文管理器"""
    
    def __init__(self, timeout_seconds: float, operation_name: str = "操作"):
        self.timeout_seconds = timeout_seconds
        self.operation_name = operation_name
        self._timeout_handle = None
    
    async def __aenter__(self):
        self._timeout_handle = asyncio.timeout(self.timeout_seconds)
        return await self._timeout_handle.__aenter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is asyncio.TimeoutError:
            logger.error(f"{self.operation_name} 超时 ({self.timeout_seconds}秒)")
        return await self._timeout_handle.__aexit__(exc_type, exc_val, exc_tb)


# 预定义的超时常量
class Timeouts:
    """超时常量配置"""
    
    # 数据采集超时
    MARKET_DATA_FETCH = 30.0
    ORDERBOOK_FETCH = 10.0
    ACCOUNT_INFO_FETCH = 15.0
    
    # AI操作超时
    LLM_GENERATE = 60.0
    MARKET_ANALYSIS = 90.0
    DECISION_MAKING = 45.0
    
    # 交易操作超时
    ORDER_PLACEMENT = 10.0
    ORDER_CANCELLATION = 10.0
    POSITION_UPDATE = 15.0
    
    # 数据存储超时
    DATABASE_WRITE = 10.0
    FILE_WRITE = 15.0
    CACHE_UPDATE = 5.0
    
    # 网络请求超时
    HTTP_REQUEST = 30.0
    WEBSOCKET_CONNECT = 15.0
    API_CALL = 60.0
    
    # 监控超时
    HEALTH_CHECK = 10.0
    RISK_ASSESSMENT = 20.0
