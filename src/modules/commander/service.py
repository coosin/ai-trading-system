from __future__ import annotations

from typing import Any, Dict

from src.modules.api.module_control_api import (
    _build_closed_loop_summary_data,
    _build_system_mastery_snapshot,
    _build_trading_workflow_report,
)


class CommanderDomainService:
    def __init__(self, main_controller: Any) -> None:
        self.mc = main_controller

    async def system_mastery(
        self,
        symbol: str = "BTC/USDT",
        trace_limit: int = 120,
        trade_limit: int = 300,
        recent_trades_limit: int = 20,
    ) -> Dict[str, Any]:
        return await _build_system_mastery_snapshot(
            self.mc,
            symbol=symbol,
            trace_limit=int(trace_limit or 120),
            trade_limit=int(trade_limit or 300),
            recent_trades_limit=int(recent_trades_limit or 20),
        )

    async def closed_loop(self, trace_limit: int = 120) -> Dict[str, Any]:
        return await _build_closed_loop_summary_data(self.mc, trace_limit=int(trace_limit or 120))

    async def trading_workflow(
        self,
        symbol: str = "BTC/USDT",
        trace_limit: int = 200,
        trade_limit: int = 1000,
        recent_trades_limit: int = 40,
        recent_order_hours: float = 4.0,
    ) -> Dict[str, Any]:
        return await _build_trading_workflow_report(
            self.mc,
            symbol=symbol,
            trace_limit=int(trace_limit or 200),
            trade_limit=int(trade_limit or 1000),
            recent_trades_limit=int(recent_trades_limit or 40),
            recent_order_hours=float(recent_order_hours or 4.0),
        )
