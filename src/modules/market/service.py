from __future__ import annotations

from typing import Any, Dict


class MarketService:
    def __init__(self, main_controller: Any) -> None:
        self.mc = main_controller

    async def snapshot(self, symbol: str = "BTC/USDT") -> Dict[str, Any]:
        mc = self.mc
        exchange = None
        try:
            exchange = mc.get_exchange() if mc and hasattr(mc, "get_exchange") else getattr(mc, "okx_exchange", None)
        except Exception:
            exchange = None
        ticker: Dict[str, Any] = {}
        order_book: Dict[str, Any] = {}
        if exchange:
            for name in ("get_ticker", "fetch_ticker"):
                fn = getattr(exchange, name, None)
                if callable(fn):
                    try:
                        ticker = await fn(symbol)
                        break
                    except Exception as exc:
                        ticker = {"error": str(exc)}
            for name in ("get_order_book", "fetch_order_book"):
                fn = getattr(exchange, name, None)
                if callable(fn):
                    try:
                        order_book = await fn(symbol)
                        break
                    except Exception:
                        order_book = {}
        return {"symbol": symbol, "exchange_bound": exchange is not None, "ticker": ticker or {}, "order_book": order_book or {}}

