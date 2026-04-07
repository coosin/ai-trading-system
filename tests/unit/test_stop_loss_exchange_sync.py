"""Tests for syncing exchange positions into StopLossTakeProfitManager."""
import pytest

from src.modules.core.stop_loss_take_profit import (
    StopLossTakeProfitManager,
    StopLossTakeProfitConfig,
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
