"""Unit tests for ExecutionGateway (S1 policy + narrow exit)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.modules.core.execution_gateway import ExecutionGateway


def _mc_with_exchange(ex, swo="ai_core"):
    mc = MagicMock()
    # Important: ExecutionGateway._exchange() prefers execution_exchange first.
    # MagicMock would otherwise fabricate a truthy attribute and break awaits.
    mc.execution_exchange = None
    mc.exchange = None
    mc.okx_exchange = ex
    mc.get_ai_managed_config = AsyncMock(
        return_value={"single_write_owner": swo, "primary_controller": swo}
    )
    return mc


def _mc_with_exchange_and_policy(ex, swo="ai_core", hosting_mode="full_auto", automation_profile="semi_auto", redlines=None):
    mc = _mc_with_exchange(ex, swo=swo)
    mc.get_hosting_mode = MagicMock(return_value=hosting_mode)
    mc.get_automation_profile = MagicMock(return_value=automation_profile)
    mc.get_risk_redlines = MagicMock(return_value=(redlines or {}))
    return mc


@pytest.mark.asyncio
async def test_close_denied_when_source_not_swo():
    ex = MagicMock()
    ex.close_swap_position = AsyncMock(return_value={"success": True})
    gw = ExecutionGateway(_mc_with_exchange(ex))
    res = await gw.close_swap("BTC/USDT", "long", None, "ai_trading_engine", "t")
    assert res["success"] is False
    assert "policy_denied" in res.get("error", "")
    ex.close_swap_position.assert_not_called()


@pytest.mark.asyncio
async def test_close_allowed_for_stop_loss_take_profit():
    ex = MagicMock()
    ex.close_swap_position = AsyncMock(return_value={"success": True, "orderId": "1"})
    gw = ExecutionGateway(_mc_with_exchange(ex))
    res = await gw.close_swap("BTC/USDT", "long", 1.0, "stop_loss_take_profit", "sl")
    assert res["success"] is True
    ex.close_swap_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_allowed_for_manual():
    ex = MagicMock()
    ex.close_swap_position = AsyncMock(return_value={"success": True, "orderId": "m1"})
    gw = ExecutionGateway(_mc_with_exchange(ex, swo="ai_core"))
    res = await gw.close_swap("BTC/USDT", "short", None, "manual", "user_api")
    assert res["success"] is True
    ex.close_swap_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_open_denied_when_source_not_swo():
    ex = MagicMock()
    ex.set_leverage = AsyncMock(return_value={"success": True})
    ex.open_swap_position = AsyncMock(return_value={"success": True})
    gw = ExecutionGateway(_mc_with_exchange(ex))
    res = await gw.open_swap("BTC/USDT", "long", 1.0, 20, "ai_trading_engine", "t")
    assert res["success"] is False
    assert "open_policy_denied" in res.get("error", "")
    ex.open_swap_position.assert_not_called()


@pytest.mark.asyncio
async def test_open_denied_for_legacy_execution_verifier_tag():
    """write_source 必须显式为 SWO（如 ai_core），不再放行裸 execution_verifier。"""
    ex = MagicMock()
    ex.set_leverage = AsyncMock(return_value={"success": True})
    ex.open_swap_position = AsyncMock(return_value={"success": True})
    gw = ExecutionGateway(_mc_with_exchange(ex, swo="ai_core"))
    res = await gw.open_swap("BTC/USDT", "long", 1.0, 20, "execution_verifier", "t")
    assert res["success"] is False
    assert "open_policy_denied" in res.get("error", "")
    ex.open_swap_position.assert_not_called()


@pytest.mark.asyncio
async def test_open_allowed_for_ai_core():
    ex = MagicMock()
    ex.set_leverage = AsyncMock(return_value={"success": True})
    ex.open_swap_position = AsyncMock(return_value={"success": True, "orderId": "x"})
    gw = ExecutionGateway(_mc_with_exchange(ex, swo="ai_core"))
    res = await gw.open_swap("BTC/USDT", "long", 1.0, 20, "ai_core", "decision")
    assert res["success"] is True
    ex.open_swap_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_idempotent_within_ttl():
    ex = MagicMock()
    ex.close_swap_position = AsyncMock(return_value={"success": True})
    gw = ExecutionGateway(_mc_with_exchange(ex))
    r1 = await gw.close_swap("ETH/USDT", "short", 2.0, "stop_loss_take_profit", "a")
    r2 = await gw.close_swap("ETH/USDT", "short", 2.0, "stop_loss_take_profit", "b")
    assert r1.get("success") is True
    assert r2.get("skipped") is True
    ex.close_swap_position.assert_awaited_once()

@pytest.mark.asyncio
async def test_close_denied_for_system_source():
    ex = MagicMock()
    ex.close_swap_position = AsyncMock(return_value={"success": True})
    gw = ExecutionGateway(_mc_with_exchange(ex, swo="ai_core"))
    res = await gw.close_swap("BTC/USDT", "long", None, "system", "proactive")
    assert res["success"] is False
    assert "policy_denied" in res.get("error", "")
    ex.close_swap_position.assert_not_called()


@pytest.mark.asyncio
async def test_open_denied_in_semi_auto_without_manual_approval():
    ex = MagicMock()
    ex.open_swap_position = AsyncMock(return_value={"success": True, "orderId": "x"})
    mc = _mc_with_exchange_and_policy(ex, swo="ai_core", hosting_mode="semi_auto")
    gw = ExecutionGateway(mc)
    res = await gw.open_swap("BTC/USDT", "long", 1.0, 20, "ai_core", "decision")
    assert res["success"] is False
    assert "半自动" in res.get("error", "") or "semi" in res.get("error", "")
    ex.open_swap_position.assert_not_called()


@pytest.mark.asyncio
async def test_open_allowed_in_semi_auto_with_manual_approval():
    ex = MagicMock()
    ex.open_swap_position = AsyncMock(return_value={"success": True, "orderId": "x"})
    mc = _mc_with_exchange_and_policy(ex, swo="ai_core", hosting_mode="semi_auto")
    gw = ExecutionGateway(mc)
    res = await gw.open_swap(
        "BTC/USDT",
        "long",
        1.0,
        20,
        "ai_core",
        "decision",
        context={"manual_approved": True},
    )
    assert res["success"] is True
    ex.open_swap_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_open_denied_by_risk_redlines_max_positions():
    ex = MagicMock()
    ex.get_positions = AsyncMock(return_value=[{"symbol": "ETH/USDT", "size": 1.0, "side": "long"}])
    ex.open_swap_position = AsyncMock(return_value={"success": True, "orderId": "x"})
    mc = _mc_with_exchange_and_policy(ex, swo="ai_core", redlines={"max_positions": 1})
    gw = ExecutionGateway(mc)
    res = await gw.open_swap("BTC/USDT", "long", 1.0, 20, "ai_core", "decision")
    assert res["success"] is False
    assert "风控红线" in res.get("error", "") or "max_positions" in res.get("error", "")
    ex.open_swap_position.assert_not_called()

