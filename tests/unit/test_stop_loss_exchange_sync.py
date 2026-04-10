"""Tests for syncing exchange positions into StopLossTakeProfitManager."""
import pytest

from datetime import datetime

from src.modules.core.stop_loss_take_profit import (
    StopLossTakeProfitManager,
    StopLossTakeProfitConfig,
    StopLossTakeProfitOrder,
    StopLossTakeProfitStatus,
)


class _FakeEx:
    def __init__(self, positions):
        self._positions = positions

    async def get_positions(self):
        return self._positions

    async def get_ticker(self, symbol: str):
        return {"last": 100.0, "symbol": symbol}


@pytest.mark.asyncio
async def test_sync_registers_positions_with_index_key(tmp_path):
    cfg = StopLossTakeProfitConfig(
        sync_exchange_positions_on_startup=True,
        persist_file=str(tmp_path / "sltp.json"),
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()
    mgr.set_exchange(
        _FakeEx(
            [
                {
                    "symbol": "BTC/USDT/SWAP",
                    "side": "long",
                    "size": 1.0,
                    "entry_price": 99000.0,
                }
            ]
        )
    )
    res = await mgr.sync_open_positions_from_exchange()
    assert res["synced"] == 1
    assert res["skipped"] == 0
    active = await mgr.get_all_active_orders()
    assert len(active) == 1
    assert active[0].metadata.get("index_key") == "BTC/USDT/SWAP|long"
    assert active[0].metadata.get("source") == "exchange_sync"


@pytest.mark.asyncio
async def test_sync_skips_when_already_active(tmp_path):
    cfg = StopLossTakeProfitConfig(
        sync_exchange_positions_on_startup=True,
        persist_file=str(tmp_path / "sltp2.json"),
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()
    ex = _FakeEx(
        [
            {
                "symbol": "ETH/USDT/SWAP",
                "side": "short",
                "size": 2.0,
                "entry_price": 3000.0,
            }
        ]
    )
    mgr.set_exchange(ex)
    r1 = await mgr.sync_open_positions_from_exchange()
    assert r1["synced"] == 1
    r2 = await mgr.sync_open_positions_from_exchange()
    assert r2["skipped"] == 1
    assert r2["synced"] == 0
    assert r2.get("refreshed") == 0


@pytest.mark.asyncio
async def test_sync_not_blocked_by_archived_orders(tmp_path):
    """历史 triggered 单不应占用 max_orders，否则无法为当前持仓登记跟踪。"""
    cfg = StopLossTakeProfitConfig(
        sync_exchange_positions_on_startup=True,
        persist_file=str(tmp_path / "sltp3.json"),
        max_orders=5,
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()
    # 模拟长期运行后积压的大量已触发记录（仍留在 self.orders）
    for i in range(120):
        oid = f"hist_{i}"
        mgr.orders[oid] = StopLossTakeProfitOrder(
            order_id=oid,
            symbol="X/USDT/SWAP",
            side="long",
            entry_price=1.0,
            quantity=1.0,
            remaining_quantity=0.0,
            status=StopLossTakeProfitStatus.TRIGGERED,
            created_at=datetime.now(),
            triggered_at=datetime.now(),
        )
    mgr.set_exchange(
        _FakeEx(
            [
                {
                    "symbol": "BTC/USDT/SWAP",
                    "side": "long",
                    "size": 0.1,
                    "entry_price": 50000.0,
                }
            ]
        )
    )
    res = await mgr.sync_open_positions_from_exchange()
    assert res["synced"] == 1
    active = await mgr.get_all_active_orders()
    assert len(active) == 1


@pytest.mark.asyncio
async def test_sync_refreshes_existing_active_quantity(tmp_path):
    """已存在 ACTIVE 跟踪时，交易所仓位变化应对齐数量（接管持续有效）。"""
    cfg = StopLossTakeProfitConfig(
        sync_exchange_positions_on_startup=True,
        persist_file=str(tmp_path / "sltp4.json"),
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()
    pos_row = {
        "symbol": "BTC/USDT/SWAP",
        "side": "long",
        "size": 1.0,
        "entry_price": 100.0,
    }
    ex = _FakeEx([pos_row])
    mgr.set_exchange(ex)
    r1 = await mgr.sync_open_positions_from_exchange()
    assert r1["synced"] == 1
    a1 = await mgr.get_all_active_orders()
    assert a1[0].quantity == 1.0

    pos_row["size"] = 2.0
    r2 = await mgr.sync_open_positions_from_exchange()
    assert r2["synced"] == 0
    assert r2["skipped"] == 1
    assert r2.get("refreshed") == 1
    a2 = await mgr.get_all_active_orders()
    assert a2[0].quantity == 2.0
    assert a2[0].remaining_quantity == 2.0
