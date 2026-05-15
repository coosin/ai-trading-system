from __future__ import annotations

import pytest

from src.modules.core.trade_history_service import TradeHistoryService


@pytest.mark.asyncio
async def test_close_trade_inherits_trace_id_from_recent_open_without_overwriting_explicit_trace(tmp_path):
    svc = TradeHistoryService({"base_path": str(tmp_path)})

    await svc.record_trade_dict(
        {
            "trade_id": "open-1",
            "order_id": "order-open-1",
            "symbol": "BTC/USDT",
            "side": "long",
            "action": "open",
            "status": "filled",
            "metadata": {"gateway": {"op": "open", "context": {"trace_id": "trace-open-1"}}},
        }
    )
    await svc.record_trade_dict(
        {
            "trade_id": "close-1",
            "order_id": "order-close-1",
            "symbol": "BTC/USDT",
            "side": "long",
            "action": "close",
            "status": "filled",
            "pnl": 3.0,
            "metadata": {"gateway": {"op": "close", "context": {}}},
        }
    )
    await svc.record_trade_dict(
        {
            "trade_id": "close-2",
            "order_id": "order-close-2",
            "symbol": "BTC/USDT",
            "side": "long",
            "action": "close",
            "status": "filled",
            "pnl": 4.0,
            "metadata": {"gateway": {"op": "close", "context": {"trace_id": "explicit-close-trace"}}},
        }
    )

    rows = await svc.get_trade_history(limit=10, descending=False)
    close_1 = next(row for row in rows if row["trade_id"] == "close-1")
    close_2 = next(row for row in rows if row["trade_id"] == "close-2")

    assert close_1["metadata"]["gateway"]["context"]["trace_id"] == "trace-open-1"
    assert close_1["metadata"]["trace_id"] == "trace-open-1"
    assert close_1["metadata"]["trace_attribution"]["method"] == "inherited_from_recent_open"
    assert close_1["metadata"]["trace_attribution"]["source_trade_id"] == "open-1"
    assert close_2["metadata"]["gateway"]["context"]["trace_id"] == "explicit-close-trace"
    assert "trace_attribution" not in close_2["metadata"]


@pytest.mark.asyncio
async def test_backfill_close_trace_attribution_updates_existing_close_rows(tmp_path):
    svc = TradeHistoryService({"base_path": str(tmp_path)})

    await svc.record_trade_dict(
        {
            "trade_id": "open-1",
            "order_id": "order-open-1",
            "symbol": "ETH/USDT",
            "side": "short",
            "action": "open",
            "status": "filled",
            "metadata": {"gateway": {"op": "open", "context": {"trace_id": "trace-short-1"}}},
        }
    )
    svc._cache.append(
        svc._cache[-1].__class__(
            trade_id="legacy-close-1",
            order_id="legacy-order-close-1",
            symbol="ETH/USDT",
            side="sell",
            order_type="market",
            quantity=1.0,
            price=100.0,
            pnl=-2.0,
            status="filled",
            metadata={"gateway": {"op": "close", "context": {}}},
        )
    )

    dry = await svc.backfill_close_trace_attribution(dry_run=True)
    assert dry["candidates"] == 1
    assert dry["updated"] == 0

    write = await svc.backfill_close_trace_attribution(dry_run=False)
    assert write["updated"] == 1
    row = next(r for r in await svc.get_trade_history(limit=10) if r["trade_id"] == "legacy-close-1")
    assert row["metadata"]["gateway"]["context"]["trace_id"] == "trace-short-1"
    assert row["metadata"]["trace_attribution"]["method"] == "historical_backfill_from_recent_open"
