from __future__ import annotations

import asyncio
import logging
import time
import queue
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Union, Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """数据源"""
    MARKET = "market"
    ON_CHAIN = "on_chain"
    SOCIAL = "social"
    NEWS = "news"
    MACRO = "macro"


@dataclass
class RealTimeData:
    """实时数据"""
    symbol: str
    source: DataSource
    timestamp: float
    data: Dict[str, Any]
    latency: float


@dataclass
class DecisionResult:
    """决策结果"""
    timestamp: float
    symbol: str
    action: str  # buy, sell, hold
    price: float
    size: float
    leverage: float
    confidence: float
    latency: float


class RealTimeProcessor:
    """实时数据处理器"""

    def __init__(self, config: Dict[str, Any]):
        """初始化实时数据处理器

        Args:
            config: 配置信息
        """
        self.config = config
        self.data_queue = queue.Queue(maxsize=10000)
        self.result_queue = queue.Queue(maxsize=10000)
        self.processing_thread = None
        self.enabled = False
        self.processing_rate = config.get("processing_rate", 100)  # 每秒处理次数
        self.max_latency = config.get("max_latency", 100)  # 最大延迟(ms)
        self.data_handlers = {}
        self.decision_handlers = []

    def initialize(self) -> bool:
        """初始化实时数据处理器

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 启动处理线程
            self.enabled = True
            self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
            self.processing_thread.start()
            logger.info("RealTimeProcessor initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize RealTimeProcessor: {e}")
            return False

    def shutdown(self) -> bool:
        """关闭实时数据处理器

        Returns:
            bool: 关闭是否成功
        """
        try:
            self.enabled = False
            if self.processing_thread:
                self.processing_thread.join(timeout=5)
            self.data_queue.queue.clear()
            self.result_queue.queue.clear()
            logger.info("RealTimeProcessor shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown RealTimeProcessor: {e}")
            return False

    def _processing_loop(self):
        """处理循环"""
        while self.enabled:
            try:
                # 计算处理间隔
                interval = 1.0 / self.processing_rate
                start_time = time.time()
                
                # 处理队列中的数据
                processed_count = 0
                while not self.data_queue.empty() and processed_count < self.processing_rate:
                    data = self.data_queue.get(block=False)
                    if data:
                        self._process_data(data)
                    processed_count += 1
                
                # 控制处理频率
                elapsed = time.time() - start_time
                if elapsed < interval:
                    time.sleep(interval - elapsed)
            except queue.Empty:
                time.sleep(0.001)
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                time.sleep(0.01)

    def _process_data(self, data: RealTimeData):
        """处理数据

        Args:
            data: 实时数据
        """
        try:
            # 检查延迟
            current_time = time.time()
            data.latency = (current_time - data.timestamp) * 1000  # 转换为毫秒
            
            if data.latency > self.max_latency:
                logger.warning(f"Data latency too high: {data.latency:.2f}ms")
                return
            
            # 调用对应的数据源处理器
            if data.source in self.data_handlers:
                handler = self.data_handlers[data.source]
                handler(data)
            
            # 执行决策
            decision = self._make_decision(data)
            if decision:
                self.result_queue.put(decision)
        except Exception as e:
            logger.error(f"Error processing data: {e}")

    def _make_decision(self, data: RealTimeData) -> Optional[DecisionResult]:
        """做出决策

        Args:
            data: 实时数据

        Returns:
            Optional[DecisionResult]: 决策结果
        """
        try:
            start_time = time.time()
            
            # 这里应该实现具体的决策逻辑
            # 暂时返回一个模拟决策
            decision = DecisionResult(
                timestamp=time.time(),
                symbol=data.symbol,
                action="hold",
                price=data.data.get("price", 0),
                size=0,
                leverage=1.0,
                confidence=0.5,
                latency=(time.time() - start_time) * 1000
            )
            
            # 调用决策处理器
            for handler in self.decision_handlers:
                handler(decision)
            
            return decision
        except Exception as e:
            logger.error(f"Error making decision: {e}")
            return None

    def add_data(self, data: RealTimeData):
        """添加数据

        Args:
            data: 实时数据
        """
        try:
            self.data_queue.put(data, block=False)
        except queue.Full:
            logger.warning("Data queue full, dropping data")

    def get_result(self, block: bool = False, timeout: Optional[float] = None) -> Optional[DecisionResult]:
        """获取结果

        Args:
            block: 是否阻塞
            timeout: 超时时间

        Returns:
            Optional[DecisionResult]: 决策结果
        """
        try:
            return self.result_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def register_data_handler(self, source: DataSource, handler: Callable[[RealTimeData], None]):
        """注册数据处理器

        Args:
            source: 数据源
            handler: 处理函数
        """
        self.data_handlers[source] = handler

    def register_decision_handler(self, handler: Callable[[DecisionResult], None]):
        """注册决策处理器

        Args:
            handler: 处理函数
        """
        self.decision_handlers.append(handler)

    def get_queue_size(self) -> Tuple[int, int]:
        """获取队列大小

        Returns:
            Tuple[int, int]: (数据队列大小, 结果队列大小)
        """
        return (self.data_queue.qsize(), self.result_queue.qsize())

    def is_healthy(self) -> bool:
        """检查实时数据处理器健康状态

        Returns:
            bool: 健康状态
        """
        if not self.enabled:
            return False
        
        # 检查队列大小
        data_queue_size, result_queue_size = self.get_queue_size()
        if data_queue_size > self.data_queue.maxsize * 0.8:
            logger.warning(f"Data queue near capacity: {data_queue_size}/{self.data_queue.maxsize}")
            return False
        
        if result_queue_size > self.result_queue.maxsize * 0.8:
            logger.warning(f"Result queue near capacity: {result_queue_size}/{self.result_queue.maxsize}")
            return False
        
        return True


class LowLatencyDecisionEngine:
    """低延迟决策引擎"""

    def __init__(self, config: Dict[str, Any]):
        """初始化低延迟决策引擎

        Args:
            config: 配置信息
        """
        self.config = config
        self.real_time_processor = RealTimeProcessor(config)
        self.enabled = False
        self.decision_cache = {}
        self.max_cache_size = config.get("max_cache_size", 1000)

    async def initialize(self) -> bool:
        """初始化低延迟决策引擎

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 初始化实时数据处理器
            if not self.real_time_processor.initialize():
                return False
            
            # 注册默认处理器
            self._register_default_handlers()
            
            self.enabled = True
            logger.info("LowLatencyDecisionEngine initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize LowLatencyDecisionEngine: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭低延迟决策引擎

        Returns:
            bool: 关闭是否成功
        """
        try:
            if not self.real_time_processor.shutdown():
                return False
            
            self.enabled = False
            self.decision_cache.clear()
            logger.info("LowLatencyDecisionEngine shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown LowLatencyDecisionEngine: {e}")
            return False

    def _register_default_handlers(self):
        """注册默认处理器"""
        # 注册市场数据处理器
        def market_data_handler(data: RealTimeData):
            # 处理市场数据
            logger.debug(f"Processing market data for {data.symbol}")
        
        self.real_time_processor.register_data_handler(DataSource.MARKET, market_data_handler)
        
        # 注册决策处理器
        def decision_handler(decision: DecisionResult):
            # 处理决策结果
            logger.debug(f"Processing decision for {decision.symbol}: {decision.action}")
            # 缓存决策结果
            self._cache_decision(decision)
        
        self.real_time_processor.register_decision_handler(decision_handler)

    def _cache_decision(self, decision: DecisionResult):
        """缓存决策结果

        Args:
            decision: 决策结果
        """
        try:
            if decision.symbol not in self.decision_cache:
                self.decision_cache[decision.symbol] = []
            
            # 添加到缓存
            self.decision_cache[decision.symbol].append(decision)
            
            # 限制缓存大小
            if len(self.decision_cache[decision.symbol]) > self.max_cache_size:
                self.decision_cache[decision.symbol] = self.decision_cache[decision.symbol][-self.max_cache_size:]
        except Exception as e:
            logger.error(f"Error caching decision: {e}")

    def add_data(self, data: RealTimeData):
        """添加数据

        Args:
            data: 实时数据
        """
        if self.enabled:
            self.real_time_processor.add_data(data)
        else:
            logger.warning("LowLatencyDecisionEngine is not enabled")

    def get_decision(self, symbol: str) -> Optional[DecisionResult]:
        """获取最新决策

        Args:
            symbol: 交易对

        Returns:
            Optional[DecisionResult]: 最新决策
        """
        try:
            if symbol in self.decision_cache and self.decision_cache[symbol]:
                return self.decision_cache[symbol][-1]
            return None
        except Exception as e:
            logger.error(f"Error getting decision: {e}")
            return None

    def get_cache_size(self) -> Dict[str, int]:
        """获取缓存大小

        Returns:
            Dict[str, int]: 每个交易对的缓存大小
        """
        return {symbol: len(decisions) for symbol, decisions in self.decision_cache.items()}

    def is_healthy(self) -> bool:
        """检查低延迟决策引擎健康状态

        Returns:
            bool: 健康状态
        """
        return self.enabled and self.real_time_processor.is_healthy()
