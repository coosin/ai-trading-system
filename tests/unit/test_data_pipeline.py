"""
DataPipeline单元测试
"""

import asyncio
from datetime import datetime, timedelta

import pytest

try:
    from src.modules.core.data_pipeline import (  # type: ignore
        DataBatch,
        DataPipeline,
        DataPoint,
        DataQuality,
        DataSourceType,
    )
except ModuleNotFoundError:
    pytest.skip("data_pipeline 模块已迁移/移除：跳过旧测试", allow_module_level=True)


class TestDataPipeline:
    """DataPipeline测试类"""

    @pytest.fixture
    async def pipeline(self):
        """创建测试用的数据管道"""
        pipeline = DataPipeline()
        await pipeline.initialize()
        yield pipeline
        await pipeline.cleanup()

    @pytest.mark.asyncio
    async def test_initialization(self, pipeline):
        """测试初始化"""
        assert pipeline is not None
        assert len(pipeline.processors) > 0
        assert len(pipeline.validators) > 0

    @pytest.mark.asyncio
    async def test_register_source(self, pipeline):
        """测试注册数据源"""
        # 注册数据源
        pipeline.register_source(
            name="test_source",
            source_type=DataSourceType.EXCHANGE_API,
            config={"poll_interval": 60},
        )

        # 验证注册成功
        assert "test_source" in pipeline.sources
        assert pipeline.sources["test_source"]["type"] == DataSourceType.EXCHANGE_API
        assert pipeline.sources["test_source"]["enabled"] is True

    @pytest.mark.asyncio
    async def test_register_processor(self, pipeline):
        """测试注册处理器"""

        def test_processor(point):
            point.data["processed"] = True
            return point

        pipeline.register_processor(test_processor)

        assert len(pipeline.processors) > 1
        assert test_processor in pipeline.processors

    @pytest.mark.asyncio
    async def test_register_consumer(self, pipeline):
        """测试注册消费者"""
        consumed_points = []

        def test_consumer(point):
            consumed_points.append(point)

        pipeline.register_consumer("test_consumer", test_consumer)

        assert "test_consumer" in pipeline.consumers
        assert pipeline.consumers["test_consumer"] == test_consumer

    @pytest.mark.asyncio
    async def test_process_data_point(self, pipeline):
        """测试处理数据点"""
        # 创建测试数据点
        point = DataPoint(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            data={"price": 50000, "volume": 100},
            source="test",
            quality=DataQuality.HIGH,
        )

        # 处理数据点
        processed = await pipeline._process_data_point(point)

        # 验证处理成功
        assert processed is not None
        assert processed.symbol == "BTC/USDT"
        assert "price" in processed.data

    @pytest.mark.asyncio
    async def test_validate_data_point(self, pipeline):
        """测试数据点验证"""
        # 有效数据点
        valid_point = DataPoint(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            data={"price": 50000, "volume": 100},
            source="test",
            quality=DataQuality.HIGH,
        )

        is_valid = await pipeline._validate_data_point(valid_point)
        assert is_valid is True

        # 无效数据点（负价格）
        invalid_point = DataPoint(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            data={"price": -100, "volume": 100},
            source="test",
            quality=DataQuality.HIGH,
        )

        is_valid = await pipeline._validate_data_point(invalid_point)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_fetch_batch(self, pipeline):
        """测试批量数据获取"""
        # 注册模拟数据源
        pipeline.register_source(
            name="mock_source",
            source_type=DataSourceType.EXCHANGE_API,
            config={"poll_interval": 60},
        )

        # 启用数据源
        pipeline.sources["mock_source"]["enabled"] = True

        # 获取批量数据
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        batch = await pipeline.fetch_batch(
            symbol="BTC/USDT", start_time=start_time, end_time=end_time, source="mock_source"
        )

        # 验证结果
        assert isinstance(batch, DataBatch)
        assert batch.symbol == "BTC/USDT"
        assert batch.start_time == start_time
        assert batch.end_time == end_time
        assert batch.count > 0

    @pytest.mark.asyncio
    async def test_data_batch_to_dataframe(self, pipeline):
        """测试数据批次转换为DataFrame"""
        # 创建测试数据点
        points = [
            DataPoint(
                timestamp=datetime.now() - timedelta(minutes=i),
                symbol="BTC/USDT",
                data={"price": 50000 + i, "volume": 100 + i},
                source="test",
                quality=DataQuality.HIGH,
            )
            for i in range(5)
        ]

        # 创建数据批次
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=10)

        batch = DataBatch(
            points=points, start_time=start_time, end_time=end_time, symbol="BTC/USDT"
        )

        # 转换为DataFrame
        df = batch.to_dataframe()

        # 验证DataFrame
        assert len(df) == 5
        assert "timestamp" in df.columns
        assert "symbol" in df.columns
        assert "price" in df.columns
        assert "volume" in df.columns

    @pytest.mark.asyncio
    async def test_get_stats(self, pipeline):
        """测试获取统计数据"""
        stats = await pipeline.get_stats()

        # 验证统计信息
        assert "total_processed" in stats
        assert "total_errors" in stats
        assert "start_time" in stats
        assert "sources" in stats

        assert isinstance(stats["total_processed"], int)
        assert isinstance(stats["total_errors"], int)
        assert stats["start_time"] is not None

    @pytest.mark.asyncio
    async def test_cleanup(self, pipeline):
        """测试清理"""
        # 启动一些任务
        pipeline._running = True
        task = asyncio.create_task(asyncio.sleep(10))
        pipeline._tasks.append(task)

        # 清理
        await pipeline.cleanup()

        # 验证清理完成
        assert pipeline._running is False
        assert len(pipeline._tasks) == 0

    @pytest.mark.asyncio
    async def test_data_point_quality(self):
        """测试数据点质量"""
        # 创建不同质量的数据点
        high_quality = DataPoint(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            data={"price": 50000},
            source="test",
            quality=DataQuality.HIGH,
        )

        low_quality = DataPoint(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            data={"price": 50000},
            source="test",
            quality=DataQuality.LOW,
        )

        invalid_quality = DataPoint(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            data={"price": 50000},
            source="test",
            quality=DataQuality.INVALID,
        )

        assert high_quality.quality == DataQuality.HIGH
        assert low_quality.quality == DataQuality.LOW
        assert invalid_quality.quality == DataQuality.INVALID

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, pipeline):
        """测试并发操作"""
        # 注册多个数据源
        for i in range(3):
            pipeline.register_source(
                name=f"source_{i}",
                source_type=DataSourceType.EXCHANGE_API,
                config={"poll_interval": 60},
            )
            pipeline.sources[f"source_{i}"]["enabled"] = True

        # 并发获取数据
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=30)

        tasks = []
        for i in range(3):
            task = asyncio.create_task(
                pipeline.fetch_batch(symbol=f"SYM{i}/USD", start_time=start_time, end_time=end_time)
            )
            tasks.append(task)

        # 等待所有任务完成
        batches = await asyncio.gather(*tasks)

        # 验证所有任务都成功
        assert len(batches) == 3
        for batch in batches:
            assert isinstance(batch, DataBatch)


if __name__ == "__main__":
    """运行测试"""
    import sys

    import pytest

    # 添加src目录到Python路径
    sys.path.insert(0, "/home/cool/.openclaw-trading/src")

    # 运行测试
    pytest.main([__file__, "-v"])
