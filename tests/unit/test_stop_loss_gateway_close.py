"""Stop-loss trigger submits close via ExecutionGateway when main_controller is set."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.modules.core.stop_loss_take_profit import (
    StopLossTakeProfitManager,
    StopLossTakeProfitConfig,
    StopLossConfig,
    TakeProfitConfig,
)


@pytest.mark.asyncio
async def test_stop_loss_trigger_invokes_gateway_close(tmp_path):
    cfg = StopLossTakeProfitConfig(
        persist_file=str(tmp_path / "sl.json"),
        check_interval=60,
        execute_exchange_on_trigger=True,
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()

    gw = MagicMock()
    gw.close_swap = AsyncMock(return_value={"success": True})

    mc = MagicMock()
    mc.get_exchange = MagicMock(return_value=None)
    mc.execution_gateway = gw

    mgr.set_main_controller(mc)
    mgr.set_exchange(MagicMock())

    await mgr.create_order(
        symbol="BTC/USDT",
        side="long",
        entry_price=100.0,
        quantity=1.0,
        stop_loss_config=StopLossConfig(stop_value=0.01),
        take_profit_config=TakeProfitConfig(tp_value=0.9),
    )
    active = await mgr.get_all_active_orders()
    assert len(active) == 1

    await mgr._check_stop_loss_take_profit(active[0], 90.0)

    gw.close_swap.assert_awaited()
    kwargs = gw.close_swap.call_args.kwargs
    assert kwargs.get("source") == "stop_loss_take_profit"
    assert kwargs.get("reason") == "stop_loss"


@pytest.mark.asyncio
async def test_sltp_create_infers_trace_id_from_recent_open_trade(tmp_path):
    cfg = StopLossTakeProfitConfig(
        persist_file=str(tmp_path / "sl-trace.json"),
        check_interval=60,
        execute_exchange_on_trigger=True,
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()

    trade_history = MagicMock()
    trade_history.get_trade_history = AsyncMock(
        return_value=[
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "strategy": "s1_ai_autonomy_override",
                "metadata": {"gateway": {"op": "open", "context": {"trace_id": "open-trace-1"}}},
            }
        ]
    )
    mc = MagicMock()
    mc.trade_history_service = trade_history
    mgr.set_main_controller(mc)

    order = await mgr.create_order(
        symbol="BTC/USDT",
        side="long",
        entry_price=100.0,
        quantity=1.0,
        stop_loss_config=StopLossConfig(stop_value=0.01),
        take_profit_config=TakeProfitConfig(tp_value=0.9),
        metadata={"source": "exchange_sync"},
    )

    assert order.metadata["trace_id"] == "open-trace-1"
    assert order.metadata["trace_attribution"]["method"] == "sltp_create_inferred_from_recent_open"
