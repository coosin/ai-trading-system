from __future__ import annotations

from typing import Any, Dict, List


class AccountService:
    def __init__(self, main_controller: Any) -> None:
        self.mc = main_controller

    async def snapshot(self) -> Dict[str, Any]:
        mc = self.mc
        exchange = None
        try:
            exchange = mc.get_exchange() if mc and hasattr(mc, "get_exchange") else getattr(mc, "okx_exchange", None)
        except Exception:
            exchange = None
        balances: Dict[str, Any] = {}
        positions: List[Dict[str, Any]] = []
        if exchange:
            try:
                if hasattr(exchange, "get_balance"):
                    balances = await exchange.get_balance()
                elif hasattr(exchange, "fetch_balance"):
                    balances = await exchange.fetch_balance()
            except Exception as exc:
                balances = {"error": str(exc)}
            try:
                if hasattr(exchange, "get_positions"):
                    positions = await exchange.get_positions()
                elif hasattr(exchange, "fetch_positions"):
                    positions = await exchange.fetch_positions()
            except Exception:
                positions = []
        return {"exchange_bound": exchange is not None, "balances": balances or {}, "positions": positions or [], "position_count": len(positions or [])}

