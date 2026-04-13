"""
simulation_exchange 兼容层。

为旧代码中常见的 `simulation_exchange` / `mock_exchange` / `virtual_exchange`
导入路径提供统一实现，并将订单路由到现有模拟模块。
"""

from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.simulation.contract_simulator import ContractSimulator
    from src.modules.simulation.simulated_market import SimulatedMarket


class SimulationExchange:
    """统一模拟交易所接口，兼容不同历史调用方式。"""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        market: Optional["SimulatedMarket"] = None,
        contract_simulator: Optional["ContractSimulator"] = None,
    ):
        self.config = config or {}
        if market is None:
            from src.modules.simulation.simulated_market import SimulatedMarket

            self.market = SimulatedMarket(self.config.get("market", {}))
        else:
            self.market = market
        self.contract_simulator = contract_simulator

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        s = str(symbol or "").strip().upper()
        if "-" in s and "/" not in s:
            s = s.replace("-", "/")
        return s

    @staticmethod
    def _normalize_interval(interval: str) -> str:
        raw = str(interval or "1h").strip().lower()
        mapping = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
        }
        return mapping.get(raw, "1h")

    async def initialize(self) -> bool:
        return True

    async def cleanup(self) -> None:
        return None

    @staticmethod
    def _normalize_open_side(side: str) -> str:
        s = str(side or "").strip().lower()
        if s in ("buy", "long", "l"):
            return "long"
        if s in ("sell", "short", "s"):
            return "short"
        return "long"

    async def execute_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        统一执行入口：
        - 有 contract_simulator 时优先走合约模拟
        - 否则退化到现货模拟市场执行
        """
        side = str(side).lower()
        normalized_side = "buy" if side in ("buy", "long") else "sell"

        if self.contract_simulator:
            contract_side = "long" if normalized_side == "buy" else "short"
            order = await self.contract_simulator.place_order(
                symbol=symbol,
                side=contract_side,
                size=float(size),
                order_type="market",
                price=price,
            )
            return {
                "status": order.status,
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": normalized_side,
                "size": order.filled_size or size,
                "price": order.avg_fill_price or price,
                "filled_size": order.filled_size,
            }

        market_execution = self.market.execute_order(
            symbol=symbol,
            side=normalized_side,
            size=float(size),
            price=price,
        )
        return {
            "status": market_execution.get("status", "filled"),
            "symbol": symbol,
            "side": normalized_side,
            "size": size,
            "price": market_execution.get("price", price),
            "filled_size": market_execution.get("filled_size", size),
        }

    async def open_swap_position(
        self,
        symbol: str,
        side: str,
        size: float,
        leverage: int = 20,
        price: Optional[float] = None,
        margin_mode: str = "cross",
    ) -> Dict[str, Any]:
        """适配 ExecutionGateway.open_swap 所需接口。"""
        symbol = self._normalize_symbol(symbol)
        side = self._normalize_open_side(side)
        qty = float(size or 0.0)
        if qty <= 0:
            return {"success": False, "error": "invalid_size"}

        if self.contract_simulator:
            order = await self.contract_simulator.place_order(
                symbol=symbol,
                side=side,
                size=qty,
                order_type="market",
                price=price,
                leverage=float(leverage or 20),
            )
            ok = str(getattr(order, "status", "")) == "filled"
            return {
                "success": ok,
                "order_id": getattr(order, "order_id", None),
                "symbol": symbol,
                "side": side,
                "size": float(getattr(order, "filled_size", qty) or qty),
                "price": float(getattr(order, "avg_fill_price", price) or (price or 0.0)),
                "margin_mode": margin_mode,
                "error": None if ok else f"order_status={getattr(order, 'status', 'unknown')}",
            }

        # 无合约模拟器时，退化为现货买卖模拟
        market_side = "buy" if side == "long" else "sell"
        filled = self.market.execute_order(symbol=symbol, side=market_side, size=qty, price=price)
        status = str((filled or {}).get("status", "filled")).lower()
        ok = status in ("filled", "success", "ok")
        return {
            "success": ok,
            "order_id": (filled or {}).get("order_id"),
            "symbol": symbol,
            "side": side,
            "size": float((filled or {}).get("filled_size", qty) or qty),
            "price": float((filled or {}).get("price", price or 0.0) or 0.0),
            "margin_mode": margin_mode,
            "error": None if ok else f"order_status={status}",
        }

    async def close_swap_position(self, symbol: str, side: str, size: Optional[float] = None) -> Dict[str, Any]:
        """适配 ExecutionGateway.close_swap 所需接口。"""
        symbol = self._normalize_symbol(symbol)
        qty = float(size) if size is not None else None

        if self.contract_simulator:
            order = await self.contract_simulator.close_position(symbol=symbol, size=qty)
            if order is None:
                return {"success": False, "error": "position_not_found", "symbol": symbol}
            ok = str(getattr(order, "status", "")) == "filled"
            return {
                "success": ok,
                "order_id": getattr(order, "order_id", None),
                "symbol": symbol,
                "side": str(side or "").lower(),
                "size": float(getattr(order, "filled_size", qty or 0.0) or 0.0),
                "price": float(getattr(order, "avg_fill_price", 0.0) or 0.0),
                "error": None if ok else f"order_status={getattr(order, 'status', 'unknown')}",
            }

        market_side = "sell" if str(side or "").lower() in ("long", "buy") else "buy"
        close_size = float(qty or 0.0)
        if close_size <= 0:
            return {"success": False, "error": "invalid_size", "symbol": symbol}
        filled = self.market.execute_order(symbol=symbol, side=market_side, size=close_size, price=None)
        status = str((filled or {}).get("status", "filled")).lower()
        ok = status in ("filled", "success", "ok")
        return {
            "success": ok,
            "order_id": (filled or {}).get("order_id"),
            "symbol": symbol,
            "side": str(side or "").lower(),
            "size": float((filled or {}).get("filled_size", close_size) or close_size),
            "price": float((filled or {}).get("price", 0.0) or 0.0),
            "error": None if ok else f"order_status={status}",
        }

    async def close_position(self, symbol: str, side: str, size: Optional[float] = None) -> Dict[str, Any]:
        """兼容部分调用方使用 close_position 命名。"""
        return await self.close_swap_position(symbol=symbol, side=side, size=size)

    async def get_balance(self) -> Dict[str, Any]:
        initial = float(
            self.config.get("initial_capital")
            or self.config.get("initial_balance")
            or 10000.0
        )
        if self.contract_simulator:
            info = self.contract_simulator.get_account_info()
            available = float(info.get("available_balance", 0.0) or 0.0)
            total = float(info.get("total_equity", available) or available)
            locked = max(total - available, 0.0)
            return {"USDT": {"free": available, "total": total, "locked": locked}}
        return {"USDT": {"free": initial, "total": initial, "locked": 0.0}}

    async def get_positions(self) -> list:
        if not self.contract_simulator:
            return []
        positions = []
        for p in self.contract_simulator.get_all_positions():
            current = float(self.market.get_price(p.symbol) or p.entry_price or 0.0)
            positions.append(
                {
                    "symbol": p.symbol,
                    "side": p.side.value,
                    "size": float(p.size),
                    "entry_price": float(p.entry_price),
                    "mark_price": current,
                    "unrealized_pnl": float(p.unrealized_pnl),
                }
            )
        return positions

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        symbol = self._normalize_symbol(symbol)
        price = float(self.market.get_price(symbol) or 0.0)
        return {"symbol": symbol, "last": price, "close": price}

    async def get_klines(
        self, symbol: str, interval: str = "1h", limit: int = 100
    ) -> List[Dict[str, Any]]:
        symbol = self._normalize_symbol(symbol)
        tf = self._normalize_interval(interval)
        df = self.market.get_historical_data(symbol, timeframe=tf, limit=max(int(limit or 1), 1))
        if df is None or getattr(df, "empty", True):
            return []

        out: List[Dict[str, Any]] = []
        for ts, row in df.tail(limit).iterrows():
            # 与 OKXExchange.get_klines 结构对齐
            out.append(
                {
                    "timestamp": int(ts.timestamp() * 1000),
                    "open": float(row.get("open", 0.0) or 0.0),
                    "high": float(row.get("high", 0.0) or 0.0),
                    "low": float(row.get("low", 0.0) or 0.0),
                    "close": float(row.get("close", 0.0) or 0.0),
                    "volume": float(row.get("volume", 0.0) or 0.0),
                    "quote_volume": 0.0,
                }
            )
        return out

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> List[List[float]]:
        klines = await self.get_klines(symbol, timeframe, limit=limit)
        return [
            [
                float(k.get("timestamp", 0)),
                float(k.get("open", 0)),
                float(k.get("high", 0)),
                float(k.get("low", 0)),
                float(k.get("close", 0)),
                float(k.get("volume", 0)),
            ]
            for k in klines
        ]

    async def get_order_book(self, symbol: str, depth: int = 10) -> Dict[str, Any]:
        symbol = self._normalize_symbol(symbol)
        ob = self.market.get_order_book(symbol)
        bids = ob.get("bids", [])[: max(int(depth or 1), 1)]
        asks = ob.get("asks", [])[: max(int(depth or 1), 1)]
        return {"symbol": symbol, "bids": bids, "asks": asks, "timestamp": None}

