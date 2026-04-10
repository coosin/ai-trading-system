import pytest

from src.modules.core.event_system import EnhancedEventSystem
from src.modules.core.trade_event_hub import TradeEventHub, TradeFill, TradeIntent


@pytest.mark.asyncio
async def test_trade_event_hub_ring_buffer_records_events(tmp_path):
    es = EnhancedEventSystem(str(tmp_path / "events.db"))
    await es.initialize()
    hub = TradeEventHub(es, api_server=None, telegram_bot=None, buffer_size=10, tg_enabled=False)

    await hub.publish_intent(
        TradeIntent(
            trace_id="t1",
            source="unit",
            symbol="BTC/USDT",
            side="long",
            action="open",
            quantity=1.0,
            leverage=20,
            reason="test",
        )
    )
    await hub.publish_fill(
        TradeFill(
            trace_id="t1",
            source="unit",
            symbol="BTC/USDT",
            side="long",
            action="open",
            success=True,
            order_id="o1",
            price=100.0,
            quantity=1.0,
        )
    )

    events = hub.get_recent(10)
    assert len(events) == 2
    assert events[0]["type"] == "trade.intent"
    assert events[1]["type"] == "trade.fill"

    await es.cleanup()

