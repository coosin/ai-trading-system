from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.modules.main_controller import MainController


@pytest.mark.asyncio
async def test_auto_backfill_trade_truth_skips_open_filled_rows():
    controller = MainController.__new__(MainController)
    controller.trade_history_service = AsyncMock()
    controller.trade_history_service.get_trade_history = AsyncMock(
        return_value=[
            {
                "order_id": "open-1",
                "symbol": "BTC/USDT",
                "status": "filled",
                "metadata": {"action": "open", "decision_action": "OPEN_LONG"},
            },
            {
                "order_id": "close-1",
                "symbol": "BTC/USDT",
                "status": "filled",
                "metadata": {"action": "close", "decision_action": "CLOSE_LONG"},
            },
        ]
    )
    controller.trade_history_service.apply_exchange_truth = AsyncMock(return_value=True)
    exchange = AsyncMock()
    exchange.get_swap_fills_for_order = AsyncMock(
        return_value=[{"fillPnl": "12.5", "fee": "-0.2", "fillSz": "1", "fillPx": "50000"}]
    )
    controller.get_exchange = lambda: exchange
    controller.okx_exchange = None

    out = await controller._auto_backfill_trade_truth_once(lookback_minutes=30, max_rows=10)

    assert out["checked"] == 1
    assert out["matched"] == 1
    assert out["updated"] == 1
    controller.trade_history_service.apply_exchange_truth.assert_awaited_once()
    kwargs = controller.trade_history_service.apply_exchange_truth.await_args.kwargs
    assert kwargs["order_id"] == "close-1"
