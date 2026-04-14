import pytest

from src.modules.data.unified_info_collector import UnifiedInfoCollector, InfoCollectorConfig


class _FakeCollector:
    def __init__(self, business_process_manager=None):
        self.business_process_manager = business_process_manager
        self.calls = []

    def add_data_source(self, name, source=None, source_type="custom", symbol="", websocket_url="", rest_api_url=""):
        self.calls.append(
            {
                "name": name,
                "source_type": source_type,
                "symbol": symbol,
            }
        )
        return True


@pytest.mark.asyncio
async def test_unified_info_realtime_collector_init_uses_named_args(monkeypatch):
    import src.modules.data.realtime_data_collector as rtc_module

    monkeypatch.setattr(rtc_module, "RealTimeDataCollector", _FakeCollector)

    cfg = InfoCollectorConfig(symbols=["BTC/USDT", "ETH/USDT"], enable_market_analysis=False, enable_sentiment_analysis=False, enable_onchain_analysis=False)
    collector = UnifiedInfoCollector(main_controller=None, config=cfg)

    await collector._init_realtime_collector()

    assert collector.realtime_collector is not None
    assert len(collector.realtime_collector.calls) == 2
    assert collector.realtime_collector.calls[0]["name"] == "BTC/USDT_ws"
    assert collector.realtime_collector.calls[0]["source_type"] == "websocket"
