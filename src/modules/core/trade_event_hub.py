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


def _side_zh(side: Optional[str]) -> str:
    s = str(side or "").lower()
    if s == "long":
        return "做多"
    if s == "short":
        return "做空"
    if s in ("buy", "bid"):
        return "买入"
    if s in ("sell", "ask"):
        return "卖出"
    if s in ("neutral", "hold"):
        return "观望"
    return s or "未知"


def _action_zh(action: Optional[str]) -> str:
    a = str(action or "").lower()
    if a == "open":
        return "开仓"
    if a == "close":
        return "平仓"
    if a in ("modify", "update"):
        return "修改"
    if a in ("cancel", "cancel_order"):
        return "撤单"
    return a or "未知"


def _type_zh(event_type: Optional[str]) -> str:
    t = str(event_type or "")
    return {
        "trade.intent": "交易意图",
        "trade.fill": "交易成交/拒绝",
        "trade.position": "持仓/保护更新",
        "market.update": "行情/分析更新",
    }.get(t, t or "未知事件")


def _translate_detail_zh(detail: Optional[str]) -> Optional[str]:
    if detail is None:
        return None
    d = str(detail)
    if not d:
        return d

    # common gate/policy reasons
    if d.startswith("risk_reward_low:"):
        return d.replace("risk_reward_low:", "风险回报比不足：", 1)
    if d.startswith("cooldown_symbol:"):
        return d.replace("cooldown_symbol:", "冷却中（同品种冷却）：", 1)
    if d.startswith("mi_quality_low:"):
        return d.replace("mi_quality_low:", "数据质量过低：", 1)
    if d.startswith("spread_too_wide:"):
        return d.replace("spread_too_wide:", "点差过大：", 1)
    if d.startswith("slippage_too_high:"):
        return d.replace("slippage_too_high:", "滑点过大：", 1)
    if d.startswith("open_policy_denied"):
        return "开仓策略拒绝（写权限/所有权策略）： " + d
    if d.startswith("execute_exception:"):
        return "执行异常： " + d
    if d.startswith("no_engine"):
        return "执行失败：交易引擎不可用"
    return d


def _enrich_zh(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add Chinese-friendly aliases without breaking existing keys.
    """
    out = dict(payload or {})
    try:
        out.setdefault("type_zh", _type_zh(out.get("type")))
        if "action" in out:
            out.setdefault("action_zh", _action_zh(out.get("action")))
        if "side" in out:
            out.setdefault("side_zh", _side_zh(out.get("side")))
        if "detail" in out:
            out.setdefault("detail_zh", _translate_detail_zh(out.get("detail")))
        if "reason" in out:
            # reason is often already Chinese; still provide alias for UI
            out.setdefault("reason_zh", str(out.get("reason") or ""))
    except Exception:
        return out
    return out


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
        notify_fn: Any = None,
        buffer_size: int = 500,
        tg_enabled: bool = True,
        tg_min_interval_sec: float = 2.0,
    ) -> None:
        self._es = event_system
        self._api = api_server
        self._tg = telegram_bot
        self._notify_fn = notify_fn
        self._buffer_size = int(max(50, buffer_size))
        self._ring: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._seq: int = 0
        self._tg_enabled = bool(tg_enabled)
        self._tg_min_interval_sec = float(max(0.0, tg_min_interval_sec))
        self._last_tg_at: float = 0.0

    def get_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        lim = int(max(1, min(limit or 100, self._buffer_size)))
        return list(self._ring[-lim:])

    def query_recent(
        self,
        *,
        limit: int = 200,
        cursor: Optional[int] = None,
        event_type: Optional[str] = None,
        symbol: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query ring buffer with lightweight filtering + cursor pagination.

        - cursor: return events with seq < cursor (exclusive). None means "latest".
        - event_type: matches payload["type"] (e.g. trade.fill / market.update)
        """
        lim = int(max(1, min(limit or 200, self._buffer_size)))
        et = str(event_type).strip() if event_type else None
        sym = str(symbol).strip() if symbol else None
        tid = str(trace_id).strip() if trace_id else None

        rows = list(self._ring)
        if cursor is not None:
            try:
                cur = int(cursor)
                rows = [r for r in rows if int(r.get("seq", 0) or 0) < cur]
            except Exception:
                pass
        if et:
            rows = [r for r in rows if str(r.get("type") or "") == et]
        if sym:
            rows = [r for r in rows if str(r.get("symbol") or "") == sym]
        if tid:
            rows = [r for r in rows if str(r.get("trace_id") or "") == tid]

        out = rows[-lim:]
        next_cursor = int(out[0].get("seq")) if out else (int(cursor) if cursor is not None else None)
        return {"events": out, "next_cursor": next_cursor, "count": len(out)}

    async def _publish_event(self, ev: Event, *, persist: bool = True) -> None:
        """
        Compatible publish adapter:
        - Some codepaths use EventBus.publish(event, persist)
        - EnhancedEventSystem exposes emit(...) instead of publish(event,...)
        """
        if hasattr(self._es, "publish"):
            await self._es.publish(ev, persist=persist)  # type: ignore[attr-defined]
            return
        bus = getattr(self._es, "event_bus", None)
        if bus and hasattr(bus, "publish"):
            await bus.publish(ev, persist)  # type: ignore[attr-defined]
            return
        # last resort: do nothing (ring buffer still records)

    async def _append_ring(self, payload: Dict[str, Any]) -> None:
        async with self._lock:
            self._seq += 1
            if "seq" not in payload:
                payload["seq"] = int(self._seq)
            self._ring.append(payload)
            if len(self._ring) > self._buffer_size:
                self._ring = self._ring[-self._buffer_size :]

    async def _fanout(self, channel: str, payload: Dict[str, Any]) -> None:
        payload = _enrich_zh(payload)
        await self._append_ring(payload)

        if self._api and hasattr(self._api, "broadcast_websocket"):
            try:
                await self._api.broadcast_websocket(channel, payload)
            except Exception as e:
                logger.debug("TradeEventHub websocket fanout failed: %s", e)

        # 即时消息渠道统一走“司令部”（notify_fn），避免各模块直接发 TG 造成多头与节流不一致
        if self._notify_fn and callable(self._notify_fn):
            now = time.time()
            if now - self._last_tg_at >= self._tg_min_interval_sec:
                self._last_tg_at = now
                try:
                    msg = payload.get("tg_message")
                    if msg:
                        await self._notify_fn(
                            f"即时消息({channel})",
                            str(msg)[:3500],
                            priority="medium",
                        )
                except Exception as e:
                    logger.debug("TradeEventHub commander fanout failed: %s", e)
            return

        # Backward-compatible direct TG (legacy)
        if self._tg_enabled and self._tg and hasattr(self._tg, "send_message"):
            now = time.time()
            if now - self._last_tg_at >= self._tg_min_interval_sec:
                self._last_tg_at = now
                try:
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
        await self._publish_event(ev, persist=True)
        await self._fanout(
            "trade.intent",
            {
                "type": "trade.intent",
                **intent.to_dict(),
                "timestamp": intent.created_at,
                "tg_message": (
                    f"🧭 交易意图 {_action_zh(intent.action)}\n"
                    f"{intent.symbol} {_side_zh(intent.side)}\ntrace_id={intent.trace_id}"
                ),
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
        await self._publish_event(ev, persist=True)
        status = "✅" if fill.success else "❌"
        await self._fanout(
            "trade.fill",
            {
                "type": "trade.fill",
                **fill.to_dict(),
                "timestamp": fill.filled_at,
                "tg_message": (
                    f"{status} {_action_zh(fill.action)}\n{fill.symbol} {_side_zh(fill.side)}\n"
                    f"数量={fill.quantity} 价格={fill.price}\ntrace_id={fill.trace_id}"
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
        await self._publish_event(ev, persist=True)
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
        await self._publish_event(ev, persist=True)
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

