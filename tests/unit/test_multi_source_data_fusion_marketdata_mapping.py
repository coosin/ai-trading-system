import pytest

from src.modules.data.multi_source_data_fusion import (
    MultiSourceDataFusion,
    DataPoint,
    DataSourceType,
)
from src.modules.data.data_integration import MarketData


@pytest.mark.asyncio
async def test_fuse_data_handles_marketdata_dataclass():
    fusion = MultiSourceDataFusion()
    # Confidence 计算依赖已注册数据源数量；这里手动设置为 2 个。
    fusion._sources = {"binance": object(), "coingecko": object()}

    dp = DataPoint(
        source="binance",
        source_type=DataSourceType.MARKET_DATA,
        timestamp=__import__("datetime").datetime.now(),
        symbol="BTC/USDT",
        value=MarketData(
            symbol="BTC/USDT",
            price=100.0,
            volume=10.0,
            change_24h=2.5,
            high_24h=0.0,
            low_24h=0.0,
        ),
    )

    fused = await fusion.fuse_data("BTC/USDT", [dp])
    assert fused.price == 100.0
    assert fused.volume == 10.0
    # sentiment mapped from change_24h / 5.0 => 2.5/5=0.5
    assert abs(fused.sentiment - 0.5) < 1e-6
    # confidence = len(data_points)/total_sources => 1/2 = 0.5
    assert fused.confidence == 0.5

