"""
数据管道模块 - 全智能量化交易系统的数据核心

功能：
1. 多数据源支持（交易所API、数据库、文件等）
2. 实时数据流处理
3. 数据清洗和标准化
4. 数据质量监控
5. 批处理和流式处理支持
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiohttp
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataSourceType(Enum):
    """数据源类型"""

    EXCHANGE_API = "exchange_api"  # 交易所API
    DATABASE = "database"  # 数据库
    FILE = "file"  # 文件
    WEB_SOCKET = "web_socket"  # WebSocket流
    REST_API = "rest_api"  # REST API


class DataFormat(Enum):
    """数据格式"""

    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"
    PROTOBUF = "protobuf"
    AVRO = "avro"


class DataQuality(Enum):
    """数据质量等级"""

    HIGH = "high"  # 高质量，完整可靠
    MEDIUM = "medium"  # 中等质量，可能有不完整
    LOW = "low"  # 低质量，需要验证
    INVALID = "invalid"  # 无效数据


@dataclass
class DataPoint:
    """数据点"""

    timestamp: datetime
    symbol: str
    data: Dict[str, Any]
    source: str
    quality: DataQuality = DataQuality.HIGH
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataBatch:
    """数据批次"""

    points: List[DataPoint]
    start_time: datetime
    end_time: datetime
    symbol: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dataframe(self) -> pd.DataFrame:
        """转换为Pandas DataFrame"""
        if not self.points:
            return pd.DataFrame()

        data = []
        for point in self.points:
            row = {
                "timestamp": point.timestamp,
                "symbol": point.symbol,
                "source": point.source,
                "quality": point.quality.value,
                **point.data,
                **point.metadata,
            }
            data.append(row)

        return pd.DataFrame(data)

    @property
    def count(self) -> int:
        """数据点数量"""
        return len(self.points)

    @property
    def time_range(self) -> timedelta:
        """时间范围"""
        return self.end_time - self.start_time


class DataPipeline:
    """
    数据管道

    核心功能：
    1. 多数据源管理和调度
    2. 数据清洗和转换
    3. 实时数据流处理
    4. 数据质量监控
    5. 错误处理和重试
    """

    def __init__(self, config_manager=None):
        """
        初始化数据管道

        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager
        self.sources: Dict[str, Dict] = {}
        self.processors: List[Callable] = []
        self.validators: List[Callable] = []
        self.consumers: Dict[str, Callable] = {}
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._stats: Dict[str, Any] = {
            "total_processed": 0,
            "total_errors": 0,
            "last_error": None,
            "start_time": None,
            "sources": {},
        }

        # 默认数据清洗规则
        self.cleaning_rules = {
            "remove_duplicates": True,
            "fill_missing_values": True,
            "normalize_timestamps": True,
            "validate_range": True,
            "remove_outliers": True,
        }

        logger.info("数据管道初始化完成")

    async def initialize(self) -> None:
        """
        初始化数据管道

        加载配置，注册数据源和处理器
        """
        logger.info("初始化数据管道...")

        if self.config_manager:
            # 从配置加载数据源
            pipeline_config = await self.config_manager.get_config("data_pipeline", {})
            self.cleaning_rules.update(pipeline_config.get("cleaning_rules", {}))

        # 注册默认处理器
        self.register_processor(self._default_cleaner)
        self.register_validator(self._default_validator)

        self._stats["start_time"] = datetime.now()
        logger.info("数据管道初始化完成")

    async def cleanup(self) -> None:
        """
        清理数据管道

        停止所有任务，释放资源
        """
        logger.info("清理数据管道...")

        self._running = False

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.info("数据管道清理完成")

    def register_source(
        self, name: str, source_type: DataSourceType, config: Dict[str, Any]
    ) -> None:
        """
        注册数据源

        Args:
            name: 数据源名称
            source_type: 数据源类型
            config: 数据源配置
        """
        self.sources[name] = {
            "type": source_type,
            "config": config,
            "enabled": True,
            "stats": {"total_fetched": 0, "total_errors": 0, "last_fetch": None, "latency_ms": 0},
        }

        self._stats["sources"][name] = self.sources[name]["stats"]
        logger.info(f"注册数据源: {name} ({source_type.value})")

    def register_processor(self, processor: Callable) -> None:
        """
        注册数据处理器

        Args:
            processor: 处理函数，接收DataPoint返回DataPoint
        """
        self.processors.append(processor)
        logger.info(f"注册数据处理器: {processor.__name__}")

    def register_validator(self, validator: Callable) -> None:
        """
        注册数据验证器

        Args:
            validator: 验证函数，接收DataPoint返回bool
        """
        self.validators.append(validator)
        logger.info(f"注册数据验证器: {validator.__name__}")

    def register_consumer(self, name: str, consumer: Callable) -> None:
        """
        注册数据消费者

        Args:
            name: 消费者名称
            consumer: 消费函数，接收DataPoint
        """
        self.consumers[name] = consumer
        logger.info(f"注册数据消费者: {name}")

    async def start(self) -> None:
        """
        启动数据管道

        开始从所有启用的数据源获取数据
        """
        if self._running:
            logger.warning("数据管道已经在运行")
            return

        logger.info("启动数据管道...")
        self._running = True

        # 为每个启用的数据源创建任务
        for name, source in self.sources.items():
            if source["enabled"]:
                task = asyncio.create_task(self._source_worker(name, source))
                self._tasks.append(task)

        logger.info(f"数据管道已启动，{len(self._tasks)}个数据源工作中")

    async def stop(self) -> None:
        """
        停止数据管道
        """
        await self.cleanup()

    async def fetch_batch(
        self, symbol: str, start_time: datetime, end_time: datetime, source: str = None
    ) -> DataBatch:
        """
        获取批量数据

        Args:
            symbol: 交易对
            start_time: 开始时间
            end_time: 结束时间
            source: 指定数据源（None表示使用所有）

        Returns:
            DataBatch: 数据批次
        """
        logger.info(f"获取批量数据: {symbol} ({start_time} - {end_time})")

        points = []
        sources_to_use = [source] if source else list(self.sources.keys())

        for src_name in sources_to_use:
            if src_name in self.sources and self.sources[src_name]["enabled"]:
                try:
                    source_points = await self._fetch_from_source(
                        src_name, symbol, start_time, end_time
                    )
                    points.extend(source_points)

                    # 更新统计
                    self.sources[src_name]["stats"]["total_fetched"] += len(source_points)
                    self.sources[src_name]["stats"]["last_fetch"] = datetime.now()

                except Exception as e:
                    logger.error(f"从数据源 {src_name} 获取数据失败: {e}")
                    self.sources[src_name]["stats"]["total_errors"] += 1

        # 处理数据
        processed_points = []
        for point in points:
            processed_point = await self._process_data_point(point)
            if processed_point:
                processed_points.append(processed_point)

        # 排序
        processed_points.sort(key=lambda x: x.timestamp)

        batch = DataBatch(
            points=processed_points,
            start_time=start_time,
            end_time=end_time,
            symbol=symbol,
            metadata={
                "source_count": len(sources_to_use),
                "processed_count": len(processed_points),
                "original_count": len(points),
            },
        )

        self._stats["total_processed"] += len(processed_points)
        logger.info(f"批量数据获取完成: {symbol}, {len(processed_points)}个数据点")

        return batch

    async def stream_data(self, symbol: str, callback: Callable) -> None:
        """
        流式数据获取

        Args:
            symbol: 交易对
            callback: 回调函数，接收DataPoint
        """
        logger.info(f"开始流式数据: {symbol}")

        # 这里实现流式数据逻辑
        # 实际项目中会连接到WebSocket或轮询API

        # 模拟实现
        async def _stream_worker():
            while self._running:
                try:
                    # 模拟获取实时数据
                    point = DataPoint(
                        timestamp=datetime.now(),
                        symbol=symbol,
                        data={
                            "price": np.random.uniform(100, 200),
                            "volume": np.random.uniform(1, 100),
                            "bid": np.random.uniform(99, 100),
                            "ask": np.random.uniform(101, 102),
                        },
                        source="simulated",
                        quality=DataQuality.HIGH,
                    )

                    processed_point = await self._process_data_point(point)
                    if processed_point:
                        await callback(processed_point)

                    await asyncio.sleep(1)  # 模拟实时更新

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"流式数据错误: {e}")
                    await asyncio.sleep(5)

        task = asyncio.create_task(_stream_worker())
        self._tasks.append(task)

    async def get_stats(self) -> Dict[str, Any]:
        """
        获取统计数据

        Returns:
            统计信息字典
        """
        async with self._lock:
            stats = self._stats.copy()
            stats["uptime"] = (datetime.now() - stats["start_time"]).total_seconds()
            stats["active_tasks"] = len([t for t in self._tasks if not t.done()])
            stats["enabled_sources"] = len([s for s in self.sources.values() if s["enabled"]])
            return stats

    # 私有方法

    async def _source_worker(self, name: str, source: Dict[str, Any]) -> None:
        """
        数据源工作线程

        Args:
            name: 数据源名称
            source: 数据源配置
        """
        source_type = source["type"]
        config = source["config"]

        logger.info(f"启动数据源工作线程: {name} ({source_type.value})")

        try:
            if source_type == DataSourceType.EXCHANGE_API:
                await self._exchange_api_worker(name, config)
            elif source_type == DataSourceType.DATABASE:
                await self._database_worker(name, config)
            elif source_type == DataSourceType.WEB_SOCKET:
                await self._websocket_worker(name, config)
            else:
                logger.warning(f"不支持的数据源类型: {source_type}")

        except asyncio.CancelledError:
            logger.info(f"数据源工作线程取消: {name}")
        except Exception as e:
            logger.error(f"数据源工作线程错误 {name}: {e}")
            self.sources[name]["stats"]["total_errors"] += 1

    async def _exchange_api_worker(self, name: str, config: Dict[str, Any]) -> None:
        """交易所API工作线程"""
        # 实际实现会连接到交易所API
        # 这里提供框架

        interval = config.get("poll_interval", 60)
        symbols = config.get("symbols", ["BTC/USDT", "ETH/USDT"])

        while self._running:
            try:
                start_time = datetime.now()

                for symbol in symbols:
                    # 模拟API调用
                    await asyncio.sleep(0.1)  # 模拟网络延迟

                    point = DataPoint(
                        timestamp=datetime.now(),
                        symbol=symbol,
                        data={
                            "price": np.random.uniform(100, 200),
                            "volume": np.random.uniform(1, 100),
                        },
                        source=name,
                        quality=DataQuality.HIGH,
                    )

                    processed_point = await self._process_data_point(point)
                    if processed_point:
                        await self._distribute_to_consumers(processed_point)

                end_time = datetime.now()
                latency = (end_time - start_time).total_seconds() * 1000
                self.sources[name]["stats"]["latency_ms"] = latency

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"交易所API错误 {name}: {e}")
                await asyncio.sleep(interval * 2)  # 错误时加倍等待

    async def _database_worker(self, name: str, config: Dict[str, Any]) -> None:
        """数据库工作线程"""
        # 实际实现会连接到数据库
        logger.info(f"数据库工作线程启动: {name}")

        while self._running:
            try:
                # 这里可以实现数据库轮询逻辑
                await asyncio.sleep(config.get("poll_interval", 300))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"数据库工作线程错误 {name}: {e}")
                await asyncio.sleep(60)

    async def _websocket_worker(self, name: str, config: Dict[str, Any]) -> None:
        """WebSocket工作线程"""
        # 实际实现会连接到WebSocket
        logger.info(f"WebSocket工作线程启动: {name}")

        while self._running:
            try:
                # 这里可以实现WebSocket连接逻辑
                await asyncio.sleep(1)  # 保持连接

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WebSocket工作线程错误 {name}: {e}")
                await asyncio.sleep(5)

    async def _fetch_from_source(
        self, source_name: str, symbol: str, start_time: datetime, end_time: datetime
    ) -> List[DataPoint]:
        """
        从指定数据源获取数据

        Args:
            source_name: 数据源名称
            symbol: 交易对
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            数据点列表
        """
        # 实际实现会根据数据源类型调用不同的方法
        # 这里提供模拟实现

        source = self.sources[source_name]
        source_type = source["type"]

        points = []

        if source_type == DataSourceType.EXCHANGE_API:
            # 模拟交易所API数据
            current = start_time
            while current < end_time:
                point = DataPoint(
                    timestamp=current,
                    symbol=symbol,
                    data={
                        "open": np.random.uniform(100, 200),
                        "high": np.random.uniform(200, 250),
                        "low": np.random.uniform(50, 100),
                        "close": np.random.uniform(100, 200),
                        "volume": np.random.uniform(1, 1000),
                    },
                    source=source_name,
                    quality=DataQuality.HIGH,
                )
                points.append(point)
                current += timedelta(minutes=1)

        elif source_type == DataSourceType.DATABASE:
            # 模拟数据库数据
            # 实际项目会查询数据库
            pass

        return points

    async def _process_data_point(self, point: DataPoint) -> Optional[DataPoint]:
        """
        处理单个数据点

        Args:
            point: 原始数据点

        Returns:
            处理后的数据点，如果无效则返回None
        """
        if not point:
            return None

        # 验证数据
        is_valid = await self._validate_data_point(point)
        if not is_valid:
            point.quality = DataQuality.INVALID
            logger.warning(f"数据点验证失败: {point.symbol} at {point.timestamp}")
            return None

        # 应用所有处理器
        processed_point = point
        for processor in self.processors:
            try:
                if asyncio.iscoroutinefunction(processor):
                    processed_point = await processor(processed_point)
                else:
                    processed_point = processor(processed_point)

                if processed_point is None:
                    return None

            except Exception as e:
                logger.error(f"数据处理器错误 {processor.__name__}: {e}")
                self._stats["total_errors"] += 1
                return None

        return processed_point

    async def _validate_data_point(self, point: DataPoint) -> bool:
        """
        验证数据点

        Args:
            point: 数据点

        Returns:
            是否有效
        """
        # 基本验证
        if not point.timestamp or not point.symbol or not point.data:
            return False

        # 时间验证（不能是未来时间）
        if point.timestamp > datetime.now() + timedelta(minutes=5):
            logger.warning(f"数据点时间异常（未来时间）: {point.timestamp}")
            return False

        # 应用所有验证器
        for validator in self.validators:
            try:
                if asyncio.iscoroutinefunction(validator):
                    validated_point = await validator(point)
                else:
                    validated_point = validator(point)

                # 检查验证后的数据质量
                if validated_point.quality == DataQuality.INVALID:
                    return False

            except Exception as e:
                logger.error(f"数据验证器错误 {validator.__name__}: {e}")
                return False

        return True

    async def _distribute_to_consumers(self, point: DataPoint) -> None:
        """
        分发数据给所有消费者

        Args:
            point: 数据点
        """
        for name, consumer in self.consumers.items():
            try:
                if asyncio.iscoroutinefunction(consumer):
                    await consumer(point)
                else:
                    consumer(point)
            except Exception as e:
                logger.error(f"数据消费者错误 {name}: {e}")

    # 默认处理器

    async def _default_cleaner(self, point: DataPoint) -> DataPoint:
        """
        默认数据清洗器

        Args:
            point: 数据点

        Returns:
            清洗后的数据点
        """
        if not self.cleaning_rules.get("remove_duplicates", True):
            return point

        # 这里实现数据清洗逻辑
        # 实际项目会有更复杂的清洗规则

        return point

    async def _default_validator(self, point: DataPoint) -> DataPoint:
        """
        默认数据验证器

        Args:
            point: 数据点

        Returns:
            验证后的数据点
        """
        data = point.data

        # 检查价格是否合理
        if "price" in data:
            price = data["price"]
            if price <= 0 or price > 1_000_000:  # 假设价格上限
                logger.warning(f"价格异常: {price}")
                point.quality = DataQuality.INVALID

        # 检查交易量是否合理
        if "volume" in data:
            volume = data["volume"]
            if volume < 0:
                logger.warning(f"交易量异常: {volume}")
                point.quality = DataQuality.INVALID

        return point


# 使用示例
async def example_usage():
    """数据管道使用示例"""

    # 创建数据管道
    pipeline = DataPipeline()
    await pipeline.initialize()

    # 注册数据源
    pipeline.register_source(
        name="binance_api",
        source_type=DataSourceType.EXCHANGE_API,
        config={
            "api_key": "your_api_key",
            "api_secret": "your_api_secret",
            "poll_interval": 60,
            "symbols": ["BTC/USDT", "ETH/USDT"],
        },
    )

    # 注册数据消费者
    def print_consumer(point: DataPoint):
        logger.info(f"收到数据: {point.symbol} @ {point.timestamp}: {point.data}")

    pipeline.register_consumer("print", print_consumer)

    # 启动数据管道
    await pipeline.start()

    try:
        # 运行一段时间
        await asyncio.sleep(10)

        # 获取统计数据
        stats = await pipeline.get_stats()
        logger.info(f"统计数据: {stats}")

    finally:
        # 清理
        await pipeline.cleanup()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
