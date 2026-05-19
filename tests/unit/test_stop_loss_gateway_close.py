"""Stop-loss trigger submits close via ExecutionGateway when main_controller is set."""
import time

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


@pytest.mark.asyncio
async def test_stop_loss_trigger_repairs_missing_trace_before_gateway_close(tmp_path):
    cfg = StopLossTakeProfitConfig(
        persist_file=str(tmp_path / "sl-repair.json"),
        check_interval=60,
        execute_exchange_on_trigger=True,
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()

    await mgr.create_order(
        symbol="BTC/USDT",
        side="long",
        entry_price=100.0,
        quantity=1.0,
        stop_loss_config=StopLossConfig(stop_value=0.01),
        take_profit_config=TakeProfitConfig(tp_value=0.9),
        metadata={"source": "exchange_sync"},
    )
    active = await mgr.get_all_active_orders()
    assert len(active) == 1
    active[0].metadata = {"source": "exchange_sync"}

    gw = MagicMock()
    gw.close_swap = AsyncMock(return_value={"success": True})
    trade_history = MagicMock()
    trade_history.get_trade_history = AsyncMock(
        return_value=[
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "strategy": "s1_ai_autonomy_override",
                "metadata": {"gateway": {"op": "open", "context": {"trace_id": "open-trace-2"}}},
            }
        ]
    )

    mc = MagicMock()
    mc.trade_history_service = trade_history
    mc.get_exchange = MagicMock(return_value=None)
    mc.execution_gateway = gw

    mgr.set_main_controller(mc)
    mgr.set_exchange(MagicMock())

    await mgr._check_stop_loss_take_profit(active[0], 90.0)

    gw.close_swap.assert_awaited()
    kwargs = gw.close_swap.call_args.kwargs
    assert kwargs["context"]["trace_id"] == "open-trace-2"
    assert kwargs["context"]["strategy_id"] == "s1_ai_autonomy_override"
    assert active[0].metadata["trace_id"] == "open-trace-2"
    assert active[0].metadata["strategy_id"] == "s1_ai_autonomy_override"
    assert active[0].metadata["trace_attribution"]["method"] == "sltp_close_inferred_from_recent_open"


@pytest.mark.asyncio
async def test_partial_close_quantize_zero_sets_block_marker(tmp_path):
    cfg = StopLossTakeProfitConfig(
        persist_file=str(tmp_path / "sl-quantize-zero.json"),
        check_interval=60,
        execute_exchange_on_trigger=True,
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()

    ex = MagicMock()
    ex.get_positions = AsyncMock(
        return_value=[
            {
                "side": "long",
                "instId": "BTC-USDT-SWAP",
                "symbol": "BTC/USDT/SWAP",
                "size": 1.0,
            }
        ]
    )
    ex.get_swap_symbol_info = AsyncMock(return_value={"lotSz": 1.0, "minSz": 1.0})
    mgr.set_exchange(ex)

    order = await mgr.create_order(
        symbol="BTC/USDT",
        side="long",
        entry_price=100.0,
        quantity=1.0,
        stop_loss_config=StopLossConfig(stop_value=0.01),
        take_profit_config=TakeProfitConfig(tp_value=0.9),
    )

    ok = await mgr._execute_exchange_close_on_trigger(
        order,
        reason="partial_take_profit_3",
        close_size=0.3,
    )

    assert ok is False
    meta = order.metadata or {}
    blocked = meta["partial_close_quantize_zero"]["partial_take_profit_3"]
    assert blocked["desired_close_size"] == pytest.approx(0.3)
    assert blocked["remaining_quantity"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_layered_partial_skips_repeated_quantize_zero_block(tmp_path):
    cfg = StopLossTakeProfitConfig(
        persist_file=str(tmp_path / "sl-layered-skip.json"),
        check_interval=60,
        execute_exchange_on_trigger=True,
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()

    order = await mgr.create_order(
        symbol="BTC/USDT",
        side="long",
        entry_price=100.0,
        quantity=1.0,
        stop_loss_config=StopLossConfig(stop_value=0.01),
        take_profit_config=TakeProfitConfig(tp_value=0.9),
    )
    mgr._remember_quantize_zero_partial_block(order, "partial_take_profit_3", 0.3, 1.0)
    mgr._execute_exchange_close_on_trigger = AsyncMock(return_value=False)

    await mgr._check_layered_partial_take_profit(order, 103.5)

    mgr._execute_exchange_close_on_trigger.assert_not_awaited()


@pytest.mark.asyncio
async def test_quantize_zero_block_tolerates_tiny_float_drift(tmp_path):
    cfg = StopLossTakeProfitConfig(
        persist_file=str(tmp_path / "sl-quantize-zero-tol.json"),
        check_interval=60,
        execute_exchange_on_trigger=True,
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()

    order = await mgr.create_order(
        symbol="BTC/USDT",
        side="long",
        entry_price=100.0,
        quantity=1.0,
        stop_loss_config=StopLossConfig(stop_value=0.01),
        take_profit_config=TakeProfitConfig(tp_value=0.9),
    )
    mgr._remember_quantize_zero_partial_block(order, "partial_take_profit_3", 0.3, 1.0)

    blocked = mgr._is_quantize_zero_partial_blocked(order, "partial_take_profit_3", 0.3000001)

    assert blocked is True
    meta = order.metadata or {}
    assert meta["partial_close_quantize_zero"]["partial_take_profit_3"]["skip_count"] == 1


@pytest.mark.asyncio
async def test_layered_partial_uses_effective_closed_size_for_remaining_quantity(tmp_path):
    cfg = StopLossTakeProfitConfig(
        persist_file=str(tmp_path / "sl-layered-effective-size.json"),
        check_interval=60,
        execute_exchange_on_trigger=True,
        layered_partial_tp_levels=[(0.03, 0.30), (0.06, 0.40)],
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()

    order = await mgr.create_order(
        symbol="ATOM/USDT/SWAP",
        side="long",
        entry_price=100.0,
        quantity=3.0,
        stop_loss_config=StopLossConfig(stop_value=0.01),
        take_profit_config=TakeProfitConfig(tp_value=0.9),
    )

    async def _fake_close(*args, **kwargs):
        mgr._record_last_close_execution_snapshot(
            order,
            reason="partial_take_profit_6",
            requested_size=1.2,
            effective_size=1.0,
            live_remaining=2.0,
        )
        return True

    mgr._execute_exchange_close_on_trigger = AsyncMock(side_effect=_fake_close)

    await mgr._check_layered_partial_take_profit(order, 106.5)

    assert order.remaining_quantity == pytest.approx(2.0)
    assert order.partial_tp_executed[-1] == pytest.approx((0.06, 1.0))


@pytest.mark.asyncio
async def test_create_order_replaces_existing_active_order_by_coord(tmp_path):
    cfg = StopLossTakeProfitConfig(
        persist_file=str(tmp_path / "sl-dedupe-coord.json"),
        check_interval=60,
        execute_exchange_on_trigger=True,
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()

    first = await mgr.create_order(
        symbol="ATOM/USDT/SWAP",
        side="long",
        entry_price=100.0,
        quantity=1.0,
        stop_loss_config=StopLossConfig(stop_value=0.01),
        take_profit_config=TakeProfitConfig(tp_value=0.9),
    )
    assert first.status.value == "active"

    second = await mgr.create_order(
        symbol="ATOM/USDT",
        side="long",
        entry_price=101.0,
        quantity=1.0,
        stop_loss_config=StopLossConfig(stop_value=0.01),
        take_profit_config=TakeProfitConfig(tp_value=0.9),
    )

    assert second.order_id != first.order_id
    assert mgr.orders[first.order_id].status.value == "cancelled"
    active = await mgr.get_all_active_orders()
    assert [o.order_id for o in active] == [second.order_id]


@pytest.mark.asyncio
async def test_resolve_monitor_price_prefers_position_mark_when_ticker_diverges(tmp_path):
    cfg = StopLossTakeProfitConfig(
        persist_file=str(tmp_path / "sl-monitor-price-guard.json"),
        check_interval=60,
        execute_exchange_on_trigger=True,
        monitor_price_guard_max_deviation=0.02,
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()

    order = await mgr.create_order(
        symbol="ATOM/USDT/SWAP",
        side="long",
        entry_price=2.001,
        quantity=3.0,
        stop_loss_config=StopLossConfig(stop_value=0.01),
        take_profit_config=TakeProfitConfig(tp_value=0.9),
    )

    ticker = {
        "last": 2.122,
        "timestamp": int(time.time() * 1000),
    }
    position_row = {
        "instId": "ATOM-USDT-SWAP",
        "symbol": "ATOM/USDT/SWAP",
        "side": "long",
        "size": 3.0,
        "mark_price": 1.934,
    }

    resolved_price, source = mgr._resolve_monitor_price(order, ticker, position_row)

    assert resolved_price == pytest.approx(1.934)
    assert source == "position_mark_guard"
    assert mgr._stats["monitor_price_guard_hits"] == 1
    meta = order.metadata["last_monitor_price"]
    assert meta["source"] == "position_mark_guard"
    assert meta["ticker_price"] == pytest.approx(2.122)
    assert meta["mark_price"] == pytest.approx(1.934)
    assert meta["deviation_ratio"] > 0.09


@pytest.mark.asyncio
async def test_resolve_monitor_price_falls_back_to_mark_when_ticker_is_stale(tmp_path):
    cfg = StopLossTakeProfitConfig(
        persist_file=str(tmp_path / "sl-monitor-price-stale.json"),
        check_interval=60,
        execute_exchange_on_trigger=True,
        monitor_price_max_ticker_age_ms=1000.0,
    )
    mgr = StopLossTakeProfitManager(cfg)
    await mgr.initialize()

    order = await mgr.create_order(
        symbol="BTC/USDT/SWAP",
        side="long",
        entry_price=100.0,
        quantity=1.0,
        stop_loss_config=StopLossConfig(stop_value=0.01),
        take_profit_config=TakeProfitConfig(tp_value=0.9),
    )

    ticker = {
        "last": 103.0,
        "timestamp": int((time.time() - 10.0) * 1000),
    }
    position_row = {
        "instId": "BTC-USDT-SWAP",
        "symbol": "BTC/USDT/SWAP",
        "side": "long",
        "size": 1.0,
        "mark_price": 101.0,
    }

    resolved_price, source = mgr._resolve_monitor_price(order, ticker, position_row)

    assert resolved_price == pytest.approx(101.0)
    assert source == "position_mark_stale_ticker_fallback"
    assert mgr._stats["monitor_price_mark_fallback_hits"] == 1
    meta = order.metadata["last_monitor_price"]
    assert meta["source"] == "position_mark_stale_ticker_fallback"
    assert meta["ticker_age_ms"] >= 9000.0
