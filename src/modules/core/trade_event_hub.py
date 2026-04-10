"""
Trade domain event hub (Intent/Fill/Position/Exit) built on EnhancedEventSystem.

Goals:
- Single, consistent trade event schema across modules
- In-process fanout to API WebSocket + Telegram (optional)
- Ring buffer for frontend polling / debugging without requiring DB access

This module is additive and should not break existing modules.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.modules.core.event_system import (
    EnhancedEventSystem,
    Event,
    EventPriority,
    EventType,
)

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class TradeIntent:
    trace_id: str
    source: str
    symbol: str
    side: str  # long/short
    action: str  # open/close
    quantity: Optional[float] = None
    leverage: Optional[int] = None
    reason: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "source": self.source,
            "symbol": self.symbol,
            "side": self.side,
            "action": self.action,
            "quantity": self.quantity,
            "leverage": self.leverage,
            "reason": self.reason,
            "context": dict(self.context or {}),
            "created_at": self.created_at,
        }


@dataclass
class TradeFill:
    trace_id: str
    source: str
    symbol: str
    side: str
    action: str  # open/close
    success: bool
    order_id: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[float] = None
    detail: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    filled_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "source": self.source,
            "symbol": self.symbol,
            "side": self.side,
            "action": self.action,
            "success": self.success,
            "order_id": self.order_id,
            "price": self.price,
            "quantity": self.quantity,
            "detail": self.detail,
            "raw": dict(self.raw or {}),
            "filled_at": self.filled_at,
        }


class TradeEventHub:
    """
    A thin adapter around EnhancedEventSystem for trade lifecycle events.
    """

    def __init__(
        self,
        event_system: EnhancedEventSystem,
        *,
        api_server: Any = None,
        telegram_bot: Any = None,
        buffer_size: int = 500,
        tg_enabled: bool = True,
        tg_min_interval_sec: float = 2.0,
    ) -> None:
        self._es = event_system
        self._api = api_server
        self._tg = telegram_bot
        self._buffer_size = int(max(50, buffer_size))
        self._ring: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._tg_enabled = bool(tg_enabled)
        self._tg_min_interval_sec = float(max(0.0, tg_min_interval_sec))
        self._last_tg_at: float = 0.0

    def get_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        lim = int(max(1, min(limit or 100, self._buffer_size)))
        return list(self._ring[-lim:])

    async def _append_ring(self, payload: Dict[str, Any]) -> None:
        async with self._lock:
            self._ring.append(payload)
            if len(self._ring) > self._buffer_size:
                self._ring = self._ring[-self._buffer_size :]

    async def _fanout(self, channel: str, payload: Dict[str, Any]) -> None:
        await self._append_ring(payload)

        if self._api and hasattr(self._api, "broadcast_websocket"):
            try:
                await self._api.broadcast_websocket(channel, payload)
            except Exception as e:
                logger.debug("TradeEventHub websocket fanout failed: %s", e)

        if self._tg_enabled and self._tg and hasattr(self._tg, "send_message"):
            now = time.time()
            if now - self._last_tg_at >= self._tg_min_interval_sec:
                self._last_tg_at = now
                try:
                    # Keep short; full details stay in API ring buffer.
                    msg = payload.get("tg_message")
                    if msg:
                        await self._tg.send_message(str(msg)[:3500])
                except Exception as e:
                    logger.debug("TradeEventHub telegram fanout failed: %s", e)

    async def publish_intent(self, intent: TradeIntent) -> None:
        ev = Event(
            type=EventType.TRADE_SIGNAL,
            source=str(intent.source or "trade"),
            priority=EventPriority.NORMAL,
            data={"kind": "intent", **intent.to_dict()},
            metadata={"trace_id": intent.trace_id},
        )
        await self._es.publish(ev, persist=True)
        await self._fanout(
            "trade.intent",
            {
                "type": "trade.intent",
                **intent.to_dict(),
                "tg_message": f"🧭 意图 {intent.action}\n{intent.symbol} {intent.side}\ntrace_id={intent.trace_id}",
            },
        )

    async def publish_fill(self, fill: TradeFill) -> None:
        ev = Event(
            type=EventType.ORDER_FILLED if fill.success else EventType.ORDER_REJECTED,
            source=str(fill.source or "trade"),
            priority=EventPriority.HIGH if fill.success else EventPriority.NORMAL,
            data={"kind": "fill", **fill.to_dict()},
            metadata={"trace_id": fill.trace_id},
        )
        await self._es.publish(ev, persist=True)
        status = "✅" if fill.success else "❌"
        await self._fanout(
            "trade.fill",
            {
                "type": "trade.fill",
                **fill.to_dict(),
                "tg_message": (
                    f"{status} 成交 {fill.action}\n{fill.symbol} {fill.side}\n"
                    f"qty={fill.quantity} px={fill.price}\ntrace_id={fill.trace_id}"
                ),
            },
        )

    async def publish_position_update(
        self,
        *,
        trace_id: str,
        source: str,
        symbol: str,
        side: str,
        kind: str,
        data: Dict[str, Any],
        priority: EventPriority = EventPriority.NORMAL,
        tg_message: Optional[str] = None,
    ) -> None:
        """
        Publish a generic position/protection update (e.g. SLTP create/modify/trigger).
        """
        payload = {
            "trace_id": trace_id,
            "source": source,
            "symbol": symbol,
            "side": side,
            "kind": kind,
            "data": dict(data or {}),
            "timestamp": _utc_now_iso(),
        }
        ev = Event(
            type=EventType.POSITION_UPDATED,
            source=str(source or "trade"),
            priority=priority,
            data=payload,
            metadata={"trace_id": trace_id, "kind": kind},
        )
        await self._es.publish(ev, persist=True)
        await self._fanout(
            "trade.position",
            {
                "type": "trade.position",
                **payload,
                "tg_message": tg_message,
            },
        )

    async def publish_market_update(
        self,
        *,
        kind: str,
        payload: Dict[str, Any],
        tg_message: Optional[str] = None,
    ) -> None:
        """
        Publish market intelligence updates (state/symbol_view/signals).
        Frontend can subscribe to `market.*` channels.
        """
        data = {
            "kind": str(kind or "market.update"),
            "payload": dict(payload or {}),
            "timestamp": _utc_now_iso(),
        }
        ev = Event(
            type=EventType.DATA_PROCESSED,
            source="market_intelligence",
            priority=EventPriority.LOW,
            data=data,
            metadata={"kind": kind},
        )
        await self._es.publish(ev, persist=True)
        await self._fanout(
            "market.update",
            {
                "type": "market.update",
                **data,
                "tg_message": tg_message,
            },
        )

    @staticmethod
    def new_trace_id() -> str:
        return str(uuid.uuid4())

