"""
性能监控模块

提供函数执行时间跟踪和性能指标收集功能
"""

import asyncio
import logging
import time
import functools
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


class PerformanceLevel(str, Enum):
    """性能等级"""
    EXCELLENT = "excellent"
    GOOD = "good"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class PerformanceMetric:
    """性能指标"""
    name: str
    call_count: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    avg_time: float = 0.0
    error_count: int = 0
    last_called: Optional[datetime] = None
    last_execution_time: Optional[float] = None


@dataclass
class AlertRule:
    """告警规则"""
    name: str
    metric_name: str
    threshold_ms: float
    condition: str  # "gt" | "lt" | "eq"
    level: str  # "warning" | "critical"


class PerformanceMonitor:
    """
    性能监控器
    
    功能：
    1. 函数执行时间跟踪
    2. 性能指标统计
    3. 性能告警
    4. 性能报告生成
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self._metrics: Dict[str, PerformanceMetric] = {}
        self._alert_rules: List[AlertRule] = []
        self._alert_callbacks: List[Callable] = []
        self._enabled = self.config.get("enabled", True)
        self._slow_threshold_ms = self.config.get("slow_threshold_ms", 1000)
        
        self._setup_default_alerts()
    
    def _setup_default_alerts(self):
        """设置默认告警规则"""
        self._alert_rules = [
            AlertRule("slow_api", "api_call", 5000, "gt", "warning"),
            AlertRule("very_slow_api", "api_call", 10000, "gt", "critical"),
            AlertRule("slow_database", "database_query", 1000, "gt", "warning"),
            AlertRule("slow_llm", "llm_request", 30000, "gt", "warning"),
            AlertRule("slow_trading", "trade_execution", 5000, "gt", "warning"),
        ]
    
    def track(self, metric_name: str = None):
        """
        装饰器：跟踪函数执行时间
        
        用法:
        @performance_monitor.track("my_function")
        async def my_function():
            ...
        """
        def decorator(func: Callable) -> Callable:
            name = metric_name or f"{func.__module__}.{func.__name__}"
            
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                if not self._enabled:
                    return await func(*args, **kwargs)
                
                start_time = time.time()
                error = None
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    error = e
                    raise
                finally:
                    execution_time = (time.time() - start_time) * 1000
                    self._record_execution(name, execution_time, error)
            
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                if not self._enabled:
                    return func(*args, **kwargs)
                
                start_time = time.time()
                error = None
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    error = e
                    raise
                finally:
                    execution_time = (time.time() - start_time) * 1000
                    self._record_execution(name, execution_time, error)
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        
        return decorator
    
    def _record_execution(self, name: str, execution_time_ms: float, error: Optional[Exception]):
        """记录执行时间"""
        if name not in self._metrics:
            self._metrics[name] = PerformanceMetric(name=name)
        
        metric = self._metrics[name]
        metric.call_count += 1
        metric.total_time += execution_time_ms
        metric.avg_time = metric.total_time / metric.call_count
        metric.min_time = min(metric.min_time, execution_time_ms)
        metric.max_time = max(metric.max_time, execution_time_ms)
        metric.last_called = datetime.now()
        metric.last_execution_time = execution_time_ms
        
        if error:
            metric.error_count += 1
        
        if execution_time_ms > self._slow_threshold_ms:
            logger.warning(f"慢执行: {name} 耗时 {execution_time_ms:.2f}ms")
            self._check_alerts(name, execution_time_ms)
    
    def _check_alerts(self, metric_name: str, value: float):
        """检查告警规则"""
        for rule in self._alert_rules:
            if rule.metric_name not in metric_name:
                continue
            
            triggered = False
            if rule.condition == "gt" and value > rule.threshold_ms:
                triggered = True
            elif rule.condition == "lt" and value < rule.threshold_ms:
                triggered = True
            
            if triggered:
                alert = {
                    "type": "performance",
                    "level": rule.level,
                    "metric": metric_name,
                    "value": value,
                    "threshold": rule.threshold_ms,
                    "message": f"性能{rule.level}: {metric_name} 耗时 {value:.2f}ms (阈值: {rule.threshold_ms}ms)",
                    "timestamp": datetime.now().isoformat()
                }
                self._trigger_alert(alert)
    
    def _trigger_alert(self, alert: Dict):
        """触发告警"""
        logger.warning(f"性能告警: {alert['message']}")
        
        for callback in self._alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(alert))
                else:
                    callback(alert)
            except Exception as e:
                logger.error(f"告警回调失败: {e}")
    
    def add_alert_callback(self, callback: Callable):
        """添加告警回调"""
        self._alert_callbacks.append(callback)
    
    def get_metric(self, name: str) -> Optional[PerformanceMetric]:
        """获取指定指标"""
        return self._metrics.get(name)
    
    def get_all_metrics(self) -> Dict[str, PerformanceMetric]:
        """获取所有指标"""
        return self._metrics.copy()
    
    def get_slowest(self, limit: int = 10) -> List[PerformanceMetric]:
        """获取最慢的指标"""
        sorted_metrics = sorted(
            self._metrics.values(),
            key=lambda m: m.avg_time,
            reverse=True
        )
        return sorted_metrics[:limit]
    
    def get_most_called(self, limit: int = 10) -> List[PerformanceMetric]:
        """获取调用次数最多的指标"""
        sorted_metrics = sorted(
            self._metrics.values(),
            key=lambda m: m.call_count,
            reverse=True
        )
        return sorted_metrics[:limit]
    
    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        if not self._metrics:
            return {"status": "no_data"}
        
        total_calls = sum(m.call_count for m in self._metrics.values())
        total_time = sum(m.total_time for m in self._metrics.values())
        
        slowest = self.get_slowest(5)
        most_called = self.get_most_called(5)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "total_calls": total_calls,
            "total_time_ms": total_time,
            "avg_time_ms": total_time / total_calls if total_calls > 0 else 0,
            "slowest": [
                {
                    "name": m.name,
                    "avg_time_ms": m.avg_time,
                    "max_time_ms": m.max_time,
                    "call_count": m.call_count
                }
                for m in slowest
            ],
            "most_called": [
                {
                    "name": m.name,
                    "call_count": m.call_count,
                    "avg_time_ms": m.avg_time
                }
                for m in most_called
            ],
            "error_count": sum(m.error_count for m in self._metrics.values())
        }
    
    def reset(self):
        """重置所有指标"""
        self._metrics.clear()
        logger.info("性能指标已重置")
    
    def set_enabled(self, enabled: bool):
        """设置启用状态"""
        self._enabled = enabled
        logger.info(f"性能监控已{'启用' if enabled else '禁用'}")


performance_monitor = PerformanceMonitor()
