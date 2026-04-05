"""
实时数据采集模块 - WebSocket连接和数据清洗管道

核心功能：
1. WebSocket连接管理
2. 多数据源实时数据采集
3. 数据清洗和标准化
4. 数据质量监控
5. 数据缓冲和推送
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class DataSourceType(Enum):
    """数据源类型"""
    EXCHANGE = "exchange"
    WEBSOCKET = "websocket"
    REST_API = "rest_api"
    CUSTOM = "custom"


class ConnectionStatus(Enum):
    """连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class DataBuffer:
    """数据缓冲区"""
    symbol: str
    data: List[Dict[str, Any]] = field(default_factory=list)
    max_size: int = 1000
    last_update: Optional[datetime] = None

    def add(self, data_point: Dict[str, Any]) -> None:
        """添加数据点"""
        self.data.append(data_point)
        self.last_update = datetime.now()
        
        # 限制缓冲区大小
        if len(self.data) > self.max_size:
            self.data = self.data[-self.max_size:]

    def to_dataframe(self) -> pd.DataFrame:
        """转换为DataFrame"""
        if not self.data:
            return pd.DataFrame()
        return pd.DataFrame(self.data)

    def clear(self) -> None:
        """清空缓冲区"""
        self.data.clear()
        self.last_update = None


@dataclass
class DataSourceConfig:
    """数据源配置"""
    name: str
    source_type: DataSourceType
    enabled: bool = True
    symbol: str = ""
    websocket_url: str = ""
    rest_api_url: str = ""
    update_interval: float = 1.0  # 秒
    max_reconnect_attempts: int = 5
    reconnect_delay: float = 5.0  # 秒


class RealTimeDataCollector:
    """
    实时数据采集器
    
    负责管理多个数据源的连接和数据采集
    """

    def __init__(self, business_process_manager=None):
        """
        初始化实时数据采集器

        Args:
            business_process_manager: 业务流程管理器实例
        """
        self.business_process_manager = business_process_manager

        # 数据源配置
        self.data_sources: Dict[str, DataSourceConfig] = {}

        # 连接管理
        self.connections: Dict[str, Any] = {}
        self.connection_status: Dict[str, ConnectionStatus] = {}

        # 数据缓冲
        self.data_buffers: Dict[str, DataBuffer] = {}

        # 数据回调
        self.data_callbacks: List[Callable] = []

        # 任务管理
        self._tasks: List[asyncio.Task] = []
        self._running = False
        self._lock = asyncio.Lock()

        logger.info("实时数据采集器初始化完成")

    async def initialize(self) -> None:
        """初始化实时数据采集器"""
        logger.info("初始化实时数据采集器...")
        self._running = True
        logger.info("实时数据采集器初始化完成")

    async def shutdown(self) -> None:
        """关闭实时数据采集器"""
        logger.info("关闭实时数据采集器...")

        self._running = False

        # 断开所有连接
        for source_name in list(self.data_sources.keys()):
            await self.disconnect_source(source_name)

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.info("实时数据采集器已关闭")

    def register_data_source(self, config: DataSourceConfig) -> bool:
        """
        注册数据源

        Args:
            config: 数据源配置

        Returns:
            是否注册成功
        """
        if config.name in self.data_sources:
            logger.warning(f"数据源已存在: {config.name}")
            return False

        self.data_sources[config.name] = config
        self.connection_status[config.name] = ConnectionStatus.DISCONNECTED
        self.data_buffers[config.name] = DataBuffer(symbol=config.symbol)
        
        logger.info(f"注册数据源: {config.name}")
        return True
    
    def add_data_source(self, name: str, source: Any = None, 
                        source_type: str = "custom", symbol: str = "",
                        websocket_url: str = "", rest_api_url: str = "") -> bool:
        """添加数据源（兼容接口）"""
        type_map = {
            "exchange": DataSourceType.EXCHANGE,
            "websocket": DataSourceType.WEBSOCKET,
            "rest_api": DataSourceType.REST_API,
            "custom": DataSourceType.CUSTOM,
        }
        stype = type_map.get(source_type, DataSourceType.CUSTOM)
        
        config = DataSourceConfig(
            name=name,
            source_type=stype,
            symbol=symbol,
            websocket_url=websocket_url,
            rest_api_url=rest_api_url
        )
        return self.register_data_source(config)

    def unregister_data_source(self, source_name: str) -> bool:
        """
        注销数据源

        Args:
            source_name: 数据源名称

        Returns:
            是否注销成功
        """
        if source_name not in self.data_sources:
            logger.warning(f"数据源不存在: {source_name}")
            return False

        # 先断开连接
        asyncio.create_task(self.disconnect_source(source_name))

        del self.data_sources[source_name]
        if source_name in self.connection_status:
            del self.connection_status[source_name]
        if source_name in self.data_buffers:
            del self.data_buffers[source_name]

        logger.info(f"注销数据源: {source_name}")
        return True

    async def connect_source(self, source_name: str) -> bool:
        """
        连接数据源

        Args:
            source_name: 数据源名称

        Returns:
            是否连接成功
        """
        if source_name not in self.data_sources:
            logger.error(f"数据源不存在: {source_name}")
            return False

        config = self.data_sources[source_name]
        if not config.enabled:
            logger.warning(f"数据源已禁用: {source_name}")
            return False

        async with self._lock:
            if self.connection_status.get(source_name) == ConnectionStatus.CONNECTED:
                logger.warning(f"数据源已连接: {source_name}")
                return True

            self.connection_status[source_name] = ConnectionStatus.CONNECTING

        try:
            if config.source_type == DataSourceType.WEBSOCKET:
                await self._connect_websocket(source_name, config)
            elif config.source_type == DataSourceType.REST_API:
                await self._connect_rest_api(source_name, config)
            elif config.source_type == DataSourceType.EXCHANGE:
                await self._connect_exchange(source_name, config)

            async with self._lock:
                self.connection_status[source_name] = ConnectionStatus.CONNECTED

            logger.info(f"数据源连接成功: {source_name}")
            return True

        except Exception as e:
            async with self._lock:
                self.connection_status[source_name] = ConnectionStatus.ERROR

            logger.error(f"数据源连接失败 {source_name}: {e}")
            return False

    async def disconnect_source(self, source_name: str) -> bool:
        """
        断开数据源

        Args:
            source_name: 数据源名称

        Returns:
            是否断开成功
        """
        if source_name not in self.data_sources:
            logger.warning(f"数据源不存在: {source_name}")
            return False

        async with self._lock:
            if self.connection_status.get(source_name) == ConnectionStatus.DISCONNECTED:
                return True

            self.connection_status[source_name] = ConnectionStatus.DISCONNECTED

        # 关闭连接
        if source_name in self.connections:
            try:
                conn = self.connections[source_name]
                if hasattr(conn, 'close'):
                    if asyncio.iscoroutinefunction(conn.close):
                        await conn.close()
                    else:
                        conn.close()
                del self.connections[source_name]
            except Exception as e:
                logger.error(f"关闭连接失败 {source_name}: {e}")

        logger.info(f"数据源断开: {source_name}")
        return True

    async def _connect_websocket(self, source_name: str, config: DataSourceConfig) -> None:
        """连接WebSocket数据源"""
        logger.info(f"连接WebSocket: {source_name}")
        
        # 这里可以集成具体的WebSocket连接
        # 例如使用websockets库
        # self.connections[source_name] = await websockets.connect(config.websocket_url)
        
        # 启动数据接收任务
        self._tasks.append(asyncio.create_task(self._websocket_worker(source_name, config)))

    async def _connect_rest_api(self, source_name: str, config: DataSourceConfig) -> None:
        """连接REST API数据源"""
        logger.info(f"连接REST API: {source_name}")
        
        # 启动轮询任务
        self._tasks.append(asyncio.create_task(self._rest_api_worker(source_name, config)))

    async def _connect_exchange(self, source_name: str, config: DataSourceConfig) -> None:
        """连接交易所数据源"""
        logger.info(f"连接交易所: {source_name}")
        
        # 这里可以集成ccxt库连接交易所
        # import ccxt
        # exchange = ccxt.binance()
        # self.connections[source_name] = exchange
        
        # 启动数据获取任务
        self._tasks.append(asyncio.create_task(self._exchange_worker(source_name, config)))

    async def _websocket_worker(self, source_name: str, config: DataSourceConfig) -> None:
        """WebSocket工作任务"""
        logger.info(f"启动WebSocket工作任务: {source_name}")
        
        reconnect_attempts = 0
        
        while self._running and source_name in self.data_sources:
            try:
                # 模拟WebSocket数据接收
                await asyncio.sleep(config.update_interval)
                
                # 生成模拟数据
                mock_data = self._generate_mock_data(config.symbol)
                await self._process_data(source_name, mock_data)
                
                reconnect_attempts = 0
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WebSocket工作任务错误 {source_name}: {e}")
                
                reconnect_attempts += 1
                if reconnect_attempts > config.max_reconnect_attempts:
                    logger.error(f"重连次数超限，停止: {source_name}")
                    break
                
                await asyncio.sleep(config.reconnect_delay)
        
        logger.info(f"WebSocket工作任务停止: {source_name}")

    async def _rest_api_worker(self, source_name: str, config: DataSourceConfig) -> None:
        """REST API工作任务"""
        logger.info(f"启动REST API工作任务: {source_name}")
        
        while self._running and source_name in self.data_sources:
            try:
                # 模拟REST API数据获取
                await asyncio.sleep(config.update_interval)
                
                mock_data = self._generate_mock_data(config.symbol)
                await self._process_data(source_name, mock_data)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"REST API工作任务错误 {source_name}: {e}")
                await asyncio.sleep(config.reconnect_delay)
        
        logger.info(f"REST API工作任务停止: {source_name}")

    async def _exchange_worker(self, source_name: str, config: DataSourceConfig) -> None:
        """交易所工作任务"""
        logger.info(f"启动交易所工作任务: {source_name}")
        
        while self._running and source_name in self.data_sources:
            try:
                # 模拟交易所数据获取
                await asyncio.sleep(config.update_interval)
                
                mock_data = self._generate_mock_data(config.symbol)
                await self._process_data(source_name, mock_data)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"交易所工作任务错误 {source_name}: {e}")
                await asyncio.sleep(config.reconnect_delay)
        
        logger.info(f"交易所工作任务停止: {source_name}")

    def _generate_mock_data(self, symbol: str) -> Dict[str, Any]:
        """生成模拟数据"""
        import random
        import numpy as np
        
        base_price = 40000 if symbol == "BTC/USDT" else 2000
        
        return {
            "symbol": symbol,
            "timestamp": datetime.now(),
            "open": base_price + random.normalvariate(0, 100),
            "high": base_price + random.normalvariate(50, 100),
            "low": base_price - random.normalvariate(50, 100),
            "close": base_price + random.normalvariate(0, 100),
            "volume": abs(random.normalvariate(1000, 200))
        }

    async def _process_data(self, source_name: str, raw_data: Dict[str, Any]) -> None:
        """
        处理原始数据

        Args:
            source_name: 数据源名称
            raw_data: 原始数据
        """
        # 数据清洗
        cleaned_data = await self._clean_data(raw_data)
        
        if not cleaned_data:
            return

        # 添加到缓冲区
        if source_name in self.data_buffers:
            self.data_buffers[source_name].add(cleaned_data)

        # 推送到业务流程管理器
        if self.business_process_manager:
            symbol = cleaned_data.get("symbol", "")
            df = pd.DataFrame([cleaned_data])
            await self.business_process_manager.process_market_data(symbol, df)

        # 调用数据回调
        for callback in self.data_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(source_name, cleaned_data)
                else:
                    callback(source_name, cleaned_data)
            except Exception as e:
                logger.error(f"数据回调错误: {e}")

    async def _clean_data(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        清洗数据

        Args:
            raw_data: 原始数据

        Returns:
            清洗后的数据
        """
        cleaned = raw_data.copy()

        # 检查必需字段
        required_fields = ["symbol", "timestamp", "open", "high", "low", "close", "volume"]
        for field in required_fields:
            if field not in cleaned:
                logger.warning(f"缺少必需字段: {field}")
                return None

        # 验证价格合理性
        price_fields = ["open", "high", "low", "close"]
        for field in price_fields:
            if cleaned[field] <= 0:
                logger.warning(f"无效的价格值: {field}={cleaned[field]}")
                return None

        # 验证成交量
        if cleaned["volume"] < 0:
            logger.warning(f"无效的成交量: {cleaned['volume']}")
            return None

        # 验证价格关系
        if cleaned["high"] < cleaned["low"]:
            logger.warning("最高价低于最低价")
            return None

        return cleaned

    def register_data_callback(self, callback: Callable) -> None:
        """
        注册数据回调

        Args:
            callback: 回调函数
        """
        self.data_callbacks.append(callback)
        logger.info(f"注册数据回调: {callback.__name__}")

    def unregister_data_callback(self, callback: Callable) -> None:
        """
        注销数据回调

        Args:
            callback: 回调函数
        """
        if callback in self.data_callbacks:
            self.data_callbacks.remove(callback)
            logger.info(f"注销数据回调: {callback.__name__}")

    def get_buffer_data(self, source_name: str) -> pd.DataFrame:
        """
        获取缓冲区数据

        Args:
            source_name: 数据源名称

        Returns:
            数据DataFrame
        """
        if source_name in self.data_buffers:
            return self.data_buffers[source_name].to_dataframe()
        return pd.DataFrame()

    def get_connection_status(self, source_name: str) -> Optional[ConnectionStatus]:
        """
        获取连接状态

        Args:
            source_name: 数据源名称

        Returns:
            连接状态
        """
        return self.connection_status.get(source_name)

    async def get_collector_status(self) -> Dict[str, Any]:
        """
        获取采集器状态

        Returns:
            状态信息
        """
        async with self._lock:
            return {
                "running": self._running,
                "data_sources": {
                    name: {
                        "enabled": config.enabled,
                        "type": config.source_type.value,
                        "status": self.connection_status.get(name, ConnectionStatus.DISCONNECTED).value,
                        "buffer_size": len(self.data_buffers[name].data) if name in self.data_buffers else 0
                    }
                    for name, config in self.data_sources.items()
                }
            }


# 使用示例
async def example_usage():
    """实时数据采集器使用示例"""

    # 创建采集器
    collector = RealTimeDataCollector()
    await collector.initialize()

    try:
        # 注册数据源
        config = DataSourceConfig(
            name="binance_btc",
            source_type=DataSourceType.EXCHANGE,
            enabled=True,
            symbol="BTC/USDT",
            update_interval=1.0
        )
        collector.register_data_source(config)

        # 连接数据源
        await collector.connect_source("binance_btc")

        # 注册数据回调
        def callback(source, data):
            logger.info(f"收到数据: {source} - {data['close']}")

        collector.register_data_callback(callback)

        # 运行一段时间
        await asyncio.sleep(10)

        # 获取状态
        status = await collector.get_collector_status()
        logger.info(f"采集器状态: {status}")

    finally:
        await collector.shutdown()


if __name__ == "__main__":
    asyncio.run(example_usage())
