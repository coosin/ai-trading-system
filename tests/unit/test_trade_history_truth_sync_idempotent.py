from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.modules.core.trade_history_service import TradeHistoryService, TradeRecord


@pytest.mark.asyncio
async def test_apply_exchange_truth_is_idempotent_for_same_values(tmp_path):
    svc = TradeHistoryService({"base_path": str(tmp_path)})
    svc._rewrite_backup_jsonl = AsyncMock(return_value=None)
    svc.db_storage = SimpleNamespace(
        update_trade_truth_by_order_id=AsyncMock(return_value=1)
    )
    svc._cache = [
        TradeRecord(
            trade_id="t-1",
            order_id="ord-1",
            symbol="BTC/USDT",
            side="sell",
            order_type="market",
            quantity=1.0,
            price=100.0,
            pnl=5.0,
            fee=0.2,
            metadata={"gateway": {"op": "close"}},
        )
    ]

    first = await svc.apply_exchange_truth(
        order_id="ord-1",
        symbol="BTC/USDT",
        exchange_pnl=5.0,
        exchange_fee=0.2,
        exchange_price=100.0,
        source="auto_exchange_sync",
    )
    second = await svc.apply_exchange_truth(
        order_id="ord-1",
        symbol="BTC/USDT",
        exchange_pnl=5.0,
        exchange_fee=0.2,
        exchange_price=100.0,
        source="auto_exchange_sync",
    )

    assert first is True
    assert second is False
    assert svc._cache[0].metadata["truth_synced"] is True
    assert svc.db_storage.update_trade_truth_by_order_id.await_count == 1
