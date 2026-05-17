from __future__ import annotations

import json

import pytest

from src.modules.core.trade_history_service import TradeHistoryService, TradeRecord


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


@pytest.mark.asyncio
async def test_close_trade_preserves_sltp_trigger_trace_but_links_to_open_trace(tmp_path):
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
            "trade_id": "close-sltp-1",
            "order_id": "order-close-sltp-1",
            "symbol": "BTC/USDT/SWAP",
            "side": "long",
            "action": "close",
            "status": "filled",
            "pnl": 2.5,
            "metadata": {
                "gateway": {
                    "op": "close",
                    "context": {"trace_id": "sltp:btc-long:take_profit"},
                }
            },
        }
    )

    row = next(r for r in await svc.get_trade_history(limit=10) if r["trade_id"] == "close-sltp-1")
    assert row["metadata"]["trace_id"] == "trace-open-1"
    assert row["metadata"]["decision_trace_id"] == "trace-open-1"
    assert row["metadata"]["gateway"]["context"]["trace_id"] == "sltp:btc-long:take_profit"
    assert row["metadata"]["gateway"]["context"]["decision_trace_id"] == "trace-open-1"
    assert row["metadata"]["trigger_trace_id"] == "sltp:btc-long:take_profit"
    assert row["metadata"]["trace_attribution"]["method"] == "linked_from_recent_open_preserving_trigger_trace"


@pytest.mark.asyncio
async def test_backfill_close_trace_attribution_canonicalizes_sltp_trigger_trace(tmp_path):
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
            trade_id="legacy-close-sltp-1",
            order_id="legacy-order-close-sltp-1",
            symbol="ETH/USDT/SWAP",
            side="sell",
            order_type="market",
            quantity=1.0,
            price=100.0,
            pnl=1.0,
            status="filled",
            metadata={"gateway": {"op": "close", "context": {"trace_id": "sltp:eth-short:take_profit"}}},
        )
    )

    dry = await svc.backfill_close_trace_attribution(dry_run=True)
    assert dry["candidates"] == 1
    assert dry["examples"][0]["raw_trace_id"] == "sltp:eth-short:take_profit"

    write = await svc.backfill_close_trace_attribution(dry_run=False)
    assert write["updated"] == 1
    row = next(r for r in await svc.get_trade_history(limit=10) if r["trade_id"] == "legacy-close-sltp-1")
    assert row["metadata"]["trace_id"] == "trace-short-1"
    assert row["metadata"]["gateway"]["context"]["trace_id"] == "sltp:eth-short:take_profit"
    assert row["metadata"]["gateway"]["context"]["decision_trace_id"] == "trace-short-1"
    assert row["metadata"]["trace_attribution"]["method"] == "historical_linked_from_recent_open_preserving_trigger_trace"


@pytest.mark.asyncio
async def test_historical_backfill_reads_beyond_cache_window_and_syncs_cache(tmp_path):
    svc = TradeHistoryService(
        {
            "base_path": str(tmp_path / "trade-history-db-window"),
            "cache_max_size": 2,
        }
    )
    await svc.record_trade_dict(
        {
            "trade_id": "open-old-1",
            "order_id": "order-open-old-1",
            "symbol": "BNB/USDT",
            "side": "long",
            "action": "open",
            "status": "filled",
            "timestamp": "2026-05-08T19:00:00Z",
            "metadata": {"gateway": {"op": "open", "context": {"trace_id": "trace-open-old-1"}}},
        }
    )
    await svc.record_trade_dict(
        {
            "trade_id": "mid-1",
            "order_id": "order-mid-1",
            "symbol": "ETH/USDT",
            "side": "long",
            "action": "open",
            "status": "filled",
            "timestamp": "2026-05-08T19:10:00Z",
            "metadata": {"gateway": {"op": "open", "context": {"trace_id": "trace-mid-1"}}},
        }
    )

    class _FakeDbStorage:
        def __init__(self, rows):
            self.rows = list(rows)

        async def get_trades(self, limit: int = 100):
            return list(self.rows[:limit])

        async def update_trade_metadata_by_order_id(self, order_id: str, *, symbol: str | None = None, metadata_json: str):
            for row in self.rows:
                if str(row.get("order_id") or "") != str(order_id or ""):
                    continue
                if symbol and str(row.get("symbol") or "") != str(symbol):
                    continue
                row["metadata_json"] = metadata_json
                return 1
            return 0

    legacy_close = TradeRecord(
        trade_id="close-old-1",
        order_id="order-close-old-1",
        symbol="BNB/USDT/SWAP",
        side="buy",
        order_type="market",
        quantity=1.0,
        price=90.0,
        pnl=-10.0,
        pnl_percent=-0.1,
        strategy="s1",
        status="filled",
        timestamp="2026-05-08T19:25:23.092780Z",
        metadata={
            "trade_phase": "close",
            "gateway": {"op": "close", "context": {"trace_id": "sltp:legacy-close-old-1"}},
        },
    )
    await svc._backup_to_jsonl(legacy_close)
    await svc._update_cache(legacy_close)
    svc.db_storage = _FakeDbStorage(
        [
            {
                "id": 3,
                "symbol": "BNB/USDT/SWAP",
                "side": "buy",
                "order_type": "market",
                "quantity": 1.0,
                "price": 90.0,
                "timestamp": "2026-05-08T19:25:23.092780Z",
                "order_id": "order-close-old-1",
                "pnl": -10.0,
                "fee": 0.0,
                "reasoning": "",
                "pnl_percent": -0.1,
                "strategy": "s1",
                "stop_loss": None,
                "take_profit": None,
                "leverage": 1,
                "metadata_json": json.dumps(
                    {
                        "trade_phase": "close",
                        "gateway": {"op": "close", "context": {"trace_id": "sltp:legacy-close-old-1"}},
                    },
                    ensure_ascii=False,
                ),
            },
            {
                "id": 2,
                "symbol": "ETH/USDT",
                "side": "buy",
                "order_type": "market",
                "quantity": 1.0,
                "price": 200.0,
                "timestamp": "2026-05-08T19:10:00Z",
                "order_id": "order-mid-1",
                "pnl": 0.0,
                "fee": 0.0,
                "reasoning": "",
                "pnl_percent": 0.0,
                "strategy": "unknown",
                "stop_loss": None,
                "take_profit": None,
                "leverage": 1,
                "metadata_json": json.dumps(
                    {
                        "gateway": {"op": "open", "context": {"trace_id": "trace-mid-1"}},
                        "action": "open",
                        "trade_phase": "open",
                        "strategy_id": "unknown",
                    },
                    ensure_ascii=False,
                ),
            },
            {
                "id": 1,
                "symbol": "BNB/USDT",
                "side": "buy",
                "order_type": "market",
                "quantity": 1.0,
                "price": 100.0,
                "timestamp": "2026-05-08T19:00:00Z",
                "order_id": "order-open-old-1",
                "pnl": 0.0,
                "fee": 0.0,
                "reasoning": "",
                "pnl_percent": 0.0,
                "strategy": "unknown",
                "stop_loss": None,
                "take_profit": None,
                "leverage": 1,
                "metadata_json": json.dumps(
                    {
                        "gateway": {"op": "open", "context": {"trace_id": "trace-open-old-1"}},
                        "action": "open",
                        "trade_phase": "open",
                        "strategy_id": "unknown",
                    },
                    ensure_ascii=False,
                ),
            },
        ]
    )

    assert len(svc._cache) == 2
    assert all(tr.trade_id != "open-old-1" for tr in svc._cache)

    dry = await svc.backfill_close_trace_attribution(limit=10, dry_run=True)
    assert dry["candidates"] == 1

    out = await svc.backfill_close_trace_attribution(limit=10, dry_run=False)
    assert out["updated"] == 1

    rows = await svc.get_trade_history(limit=10)
    close_row = next(r for r in rows if r["trade_id"] == "close-old-1")
    assert close_row["metadata"]["trace_id"] == "trace-open-old-1"
    assert close_row["metadata"]["trace_attribution"]["method"] == "historical_linked_from_recent_open_preserving_trigger_trace"
