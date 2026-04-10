"""
Single narrow exit for live swap orders (S1 execution spine).

- Records last intent/outcome for observability
- Enforces single-write-owner policy for discretionary trading sources
- Risk/auxiliary sources (e.g. SL/TP) may always submit closes

来源约定（避免多链路冲突）：
- 主动策略开平：single_write_owner（默认 ai_core）经 AICoreDecisionEngine/ExecutionVerifier
- 系统/扫描/NL 辅助入口：open 用 source=system（_allow_open 放行）
- 账户风控强平：account_risk_monitor
- 止盈止损触发平仓：stop_loss_take_profit（StopLossTakeProfitManager 独占）
- 人工/验证：manual / execution_verifier（须带 write_source）
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Sources that may submit protective / reconciled closes even when SWO is ai_core
_AUXILIARY_WRITE_SOURCES: Set[str] = {
    "stop_loss_take_profit",
    "account_risk_monitor",
    "execution_verifier",
    "manual",
    "system",
}


@dataclass
class ExecutionGatewaySnapshot:
    single_write_owner: str = "ai_core"
    last_tick_at: Optional[str] = None
    last_tick_source: Optional[str] = None
    last_order_at: Optional[str] = None
    last_order_source: Optional[str] = None
    last_order_op: Optional[str] = None
    last_order_symbol: Optional[str] = None
    last_order_side: Optional[str] = None
    last_order_size: Optional[float] = None
    last_order_leverage: Optional[int] = None
    last_order_reason: Optional[str] = None
    last_order_context: Optional[Dict[str, Any]] = None
    last_order_success: Optional[bool] = None
    last_order_detail: Optional[str] = None
    exchange_connected: bool = False
    notes: List[str] = field(default_factory=list)
    recent_events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "single_write_owner": self.single_write_owner,
            "last_tick_at": self.last_tick_at,
            "last_tick_source": self.last_tick_source,
            "last_order_at": self.last_order_at,
            "last_order_source": self.last_order_source,
            "last_order_op": self.last_order_op,
            "last_order_symbol": self.last_order_symbol,
            "last_order_side": self.last_order_side,
            "last_order_size": self.last_order_size,
            "last_order_leverage": self.last_order_leverage,
            "last_order_reason": self.last_order_reason,
            "last_order_context": self.last_order_context,
            "last_order_success": self.last_order_success,
            "last_order_detail": self.last_order_detail,
            "exchange_connected": self.exchange_connected,
            "notes": list(self.notes),
            "recent_events": list(self.recent_events),
        }


class ExecutionGateway:
    """Central gate for OKX-style swap closes/opens with policy + metrics."""

    def __init__(self, main_controller: Any) -> None:
        self._mc = main_controller
        self._locks: Dict[str, asyncio.Lock] = {}
        self._snapshot = ExecutionGatewaySnapshot()
        self._idempotent_recent: Dict[str, float] = {}
        self._idempotent_ttl_sec = 8.0
        self._recent_events_limit = 30
        self._policy_metrics: Dict[str, int] = {
            "open_policy_denied": 0,
            "close_policy_denied": 0,
            "open_ok": 0,
            "open_fail": 0,
            "close_ok": 0,
            "close_fail": 0,
        }

    def _metric_inc(self, key: str) -> None:
        self._policy_metrics[key] = int(self._policy_metrics.get(key, 0)) + 1

    def get_policy_metrics(self) -> Dict[str, int]:
        return dict(self._policy_metrics)

    def _push_recent_event(self, event: Dict[str, Any]) -> None:
        try:
            self._snapshot.recent_events.append(event)
            self._snapshot.recent_events = self._snapshot.recent_events[-self._recent_events_limit :]
        except Exception:
            pass

    async def _notify_telegram(self, text: str) -> None:
        bot = getattr(self._mc, "telegram_bot", None) if self._mc else None
        if not bot or not hasattr(bot, "send_message"):
            return
        try:
            await bot.send_message(text)
        except Exception:
            pass

    def _exchange(self) -> Any:
        ex = getattr(self._mc, "okx_exchange", None) or getattr(self._mc, "exchange", None)
        return ex

    async def _policy(self) -> Dict[str, Any]:
        if self._mc and hasattr(self._mc, "get_ai_managed_config"):
            return await self._mc.get_ai_managed_config(
                "ai_brain",
                {
                    "primary_controller": "ai_core",
                    "single_write_owner": "ai_core",
                    "enable_secondary_controller": False,
                },
            )
        return {"single_write_owner": "ai_core", "primary_controller": "ai_core", "enable_secondary_controller": False}

    async def single_write_owner(self) -> str:
        p = await self._policy()
        swo = str(p.get("single_write_owner") or p.get("primary_controller") or "ai_core").strip().lower()
        return swo

    def _allow_discretionary(self, source: str, swo: str) -> bool:
        src = (source or "").strip().lower()
        if src in _AUXILIARY_WRITE_SOURCES:
            return True
        return src == swo

    def _allow_open(self, source: str, swo: str) -> bool:
        """开仓仅允许 SWO 或显式人工/指令执行链路，防止辅环误开仓。"""
        src = (source or "").strip().lower()
        # manual/system：运维/系统指令；实盘策略须带真实 write_source（如 ai_core），不再放行匿名 execution_verifier
        if src in ("manual", "system"):
            return True
        # 用户显式开启双控时，允许 ai_core 与 ai_trading_engine 并行开仓。
        # 这是一个受配置开关控制的特例，默认关闭。
        try:
            pol = {}
            if self._mc and hasattr(self._mc, "config_manager") and self._mc.config_manager:
                pol = self._mc.config_manager.get_config_sync("ai_brain", {}) or {}
            if isinstance(pol, dict) and bool(pol.get("enable_secondary_controller", False)) and src in {"ai_core", "ai_trading_engine"}:
                return True
        except Exception:
            pass
        return src == swo

    def record_tick(self, source: str, note: str = "") -> None:
        self._snapshot.last_tick_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._snapshot.last_tick_source = source
        if note:
            self._snapshot.notes.append(note)
            self._snapshot.notes = self._snapshot.notes[-12:]

    async def assert_live_write_allowed(self, source: str) -> bool:
        swo = await self.single_write_owner()
        ok = self._allow_discretionary(source, swo)
        if not ok:
            logger.warning(
                "ExecutionGateway: write denied source=%s single_write_owner=%s",
                source,
                swo,
            )
        return ok

    def _symbol_lock(self, symbol: str) -> asyncio.Lock:
        key = symbol.replace("/", "-")
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _idempotent_key(self, symbol: str, side: str, op: str) -> str:
        return f"{op}:{symbol}:{side}"

    def _should_skip_idempotent(self, key: str) -> bool:
        now = time.time()
        if key in self._idempotent_recent:
            if now - self._idempotent_recent[key] < self._idempotent_ttl_sec:
                return True
        self._idempotent_recent[key] = now
        for k in list(self._idempotent_recent.keys()):
            if now - self._idempotent_recent[k] > 60.0:
                del self._idempotent_recent[k]
        return False

    async def close_swap(
        self,
        symbol: str,
        side: str,
        size: Optional[float],
        source: str,
        reason: str,
        *,
        force: bool = False,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Close a perpetual swap position. SL/TP and risk paths set force=False but
        pass source in _AUXILIARY_WRITE_SOURCES so policy always allows them.
        """
        swo = await self.single_write_owner()
        self._snapshot.single_write_owner = swo

        if not force and not self._allow_discretionary(source, swo):
            self._metric_inc("close_policy_denied")
            msg = f"policy_denied source={source} swo={swo}"
            logger.error("ExecutionGateway.close_swap: %s", msg)
            self._record_order(source, "close", False, msg, symbol=symbol, side=side, size=size, leverage=None, reason=reason, context=context)
            return {"success": False, "error": msg}

        ex = self._exchange()
        self._snapshot.exchange_connected = ex is not None
        if not ex:
            # trade event fanout (best-effort)
            try:
                hub = getattr(self._mc, "trade_event_hub", None) if self._mc else None
                trace_id = None
                if context and isinstance(context, dict):
                    trace_id = context.get("trace_id")
                if not trace_id:
                    trace_id = str(uuid.uuid4())
                if hub and hasattr(hub, "publish_fill"):
                    from src.modules.core.trade_event_hub import TradeFill

                    await hub.publish_fill(
                        TradeFill(
                            trace_id=str(trace_id),
                            source=str(source or "gateway"),
                            symbol=str(symbol),
                            side=str(side),
                            action="close",
                            success=False,
                            order_id=None,
                            price=None,
                            quantity=float(size) if size is not None else None,
                            detail="no_exchange",
                            raw={"error": "no_exchange"},
                        )
                    )
            except Exception:
                pass
            self._record_order(source, "close", False, "no_exchange")
            return {"success": False, "error": "no_exchange"}

        key = self._idempotent_key(symbol, side, "close")
        if self._should_skip_idempotent(key):
            logger.info("ExecutionGateway: skip duplicate close %s", key)
            return {"success": True, "skipped": True, "reason": "idempotent"}

        async with self._symbol_lock(symbol):
            try:
                close_swap = getattr(ex, "close_swap_position", None)
                if callable(close_swap):
                    res = await close_swap(symbol, side, size)
                else:
                    close_pos = getattr(ex, "close_position", None)
                    if callable(close_pos):
                        res = await close_pos(symbol, side, size)
                    else:
                        err = "exchange has no close_swap_position/close_position"
                        self._record_order(source, "close", False, err)
                        return {"success": False, "error": err}

                ok = bool(isinstance(res, dict) and res.get("success"))
                detail = str(res.get("error") if isinstance(res, dict) else res)[:500]
                self._record_order(source, "close", ok, detail or "ok", symbol=symbol, side=side, size=size, leverage=None, reason=reason, context=context)
                if ok:
                    self._metric_inc("close_ok")
                    logger.info(
                        "ExecutionGateway: close_swap ok symbol=%s side=%s source=%s reason=%s",
                        symbol,
                        side,
                        source,
                        reason,
                    )
                    self._push_recent_event(
                        {
                            "ts": self._snapshot.last_order_at,
                            "op": "close",
                            "symbol": symbol,
                            "side": side,
                            "size": size,
                            "leverage": None,
                            "source": source,
                            "reason": reason,
                            "success": True,
                            "detail": detail or "ok",
                            "context": context or {},
                        }
                    )
                    await self._notify_telegram(
                        f"✅ 平仓\n交易对: {symbol}\n方向: {side}\n来源: {source}\n原因: {reason}"
                    )
                else:
                    self._metric_inc("close_fail")
                    logger.error(
                        "ExecutionGateway: close_swap failed symbol=%s source=%s err=%s",
                        symbol,
                        source,
                        detail,
                    )
                    self._push_recent_event(
                        {
                            "ts": self._snapshot.last_order_at,
                            "op": "close",
                            "symbol": symbol,
                            "side": side,
                            "size": size,
                            "leverage": None,
                            "source": source,
                            "reason": reason,
                            "success": False,
                            "detail": detail,
                            "context": context or {},
                        }
                    )
                # trade event fanout (best-effort)
                try:
                    hub = getattr(self._mc, "trade_event_hub", None) if self._mc else None
                    trace_id = None
                    if context and isinstance(context, dict):
                        trace_id = context.get("trace_id")
                    if not trace_id:
                        trace_id = str(uuid.uuid4())
                    if hub and hasattr(hub, "publish_fill"):
                        from src.modules.core.trade_event_hub import TradeFill

                        await hub.publish_fill(
                            TradeFill(
                                trace_id=str(trace_id),
                                source=str(source or "gateway"),
                                symbol=str(symbol),
                                side=str(side),
                                action="close",
                                success=bool(ok),
                                order_id=(res.get("orderId") or res.get("order_id") or res.get("id")) if isinstance(res, dict) else None,
                                price=float(res.get("average") or res.get("price") or 0) if isinstance(res, dict) and (res.get("average") or res.get("price")) else None,
                                quantity=float(size) if size is not None else None,
                                detail=detail,
                                raw=dict(res) if isinstance(res, dict) else {"raw": str(res)},
                            )
                        )
                except Exception:
                    pass
                return res if isinstance(res, dict) else {"success": ok, "raw": res}
            except Exception as e:
                self._metric_inc("close_fail")
                self._record_order(source, "close", False, str(e), symbol=symbol, side=side, size=size, leverage=None, reason=reason, context=context)
                logger.exception("ExecutionGateway.close_swap: %s", e)
                try:
                    hub = getattr(self._mc, "trade_event_hub", None) if self._mc else None
                    trace_id = None
                    if context and isinstance(context, dict):
                        trace_id = context.get("trace_id")
                    if not trace_id:
                        trace_id = str(uuid.uuid4())
                    if hub and hasattr(hub, "publish_fill"):
                        from src.modules.core.trade_event_hub import TradeFill

                        await hub.publish_fill(
                            TradeFill(
                                trace_id=str(trace_id),
                                source=str(source or "gateway"),
                                symbol=str(symbol),
                                side=str(side),
                                action="close",
                                success=False,
                                quantity=float(size) if size is not None else None,
                                detail=str(e)[:500],
                                raw={"error": str(e)},
                            )
                        )
                except Exception:
                    pass
                return {"success": False, "error": str(e)}

    async def open_swap(
        self,
        symbol: str,
        side: str,
        size: float,
        leverage: int,
        source: str,
        reason: str,
        margin_mode: str = "cross",
        price: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """开永续仓位（经策略校验后的唯一入口之一）。"""
        swo = await self.single_write_owner()
        self._snapshot.single_write_owner = swo

        if not self._allow_open(source, swo):
            self._metric_inc("open_policy_denied")
            msg = f"open_policy_denied source={source} swo={swo}"
            logger.error("ExecutionGateway.open_swap: %s", msg)
            self._record_order(source, "open", False, msg, symbol=symbol, side=side, size=size, leverage=leverage, reason=reason, context=context)
            return {"success": False, "error": msg}

        ex = self._exchange()
        self._snapshot.exchange_connected = ex is not None
        if not ex:
            try:
                hub = getattr(self._mc, "trade_event_hub", None) if self._mc else None
                trace_id = None
                if context and isinstance(context, dict):
                    trace_id = context.get("trace_id")
                if not trace_id:
                    trace_id = str(uuid.uuid4())
                if hub and hasattr(hub, "publish_fill"):
                    from src.modules.core.trade_event_hub import TradeFill

                    await hub.publish_fill(
                        TradeFill(
                            trace_id=str(trace_id),
                            source=str(source or "gateway"),
                            symbol=str(symbol),
                            side=str(side),
                            action="open",
                            success=False,
                            quantity=float(size) if size is not None else None,
                            detail="no_exchange",
                            raw={"error": "no_exchange"},
                        )
                    )
            except Exception:
                pass
            self._metric_inc("open_fail")
            self._record_order(source, "open", False, "no_exchange")
            return {"success": False, "error": "no_exchange"}

        lev = int(leverage) if leverage else 20
        async with self._symbol_lock(symbol):
            try:
                sym = symbol
                if "/" not in sym and "-" in sym and "-SWAP" not in sym:
                    pass

                # 预检：合约最小张数/步进对齐（若交易所实现了 SWAP instruments 查询）
                # 目的：减少必失败单（例如 size < minSz 或非 lotSz 整数倍）导致的反复下单失败。
                try:
                    get_swap_info = getattr(ex, "get_swap_symbol_info", None)
                    if callable(get_swap_info):
                        info = await get_swap_info(sym)
                        min_sz = float(info.get("minSz", 0) or 0)
                        max_sz = float(info.get("maxSz", 0) or 0)
                        lot_sz = float(info.get("lotSz", 0) or 0)

                        adj = float(size)
                        if min_sz > 0 and adj < min_sz:
                            adj = min_sz
                        if lot_sz > 0:
                            adj = math.ceil(adj / lot_sz) * lot_sz
                        if max_sz > 0 and adj > max_sz:
                            self._metric_inc("open_fail")
                            err = f"preflight_denied size>{max_sz} (requested={size} adjusted={adj})"
                            self._record_order(source, "open", False, err, symbol=sym, side=side, size=size, leverage=lev, reason=reason, context=context)
                            return {"success": False, "error": err}

                        if adj <= 0:
                            self._metric_inc("open_fail")
                            err = f"preflight_denied invalid_size (requested={size} adjusted={adj})"
                            self._record_order(source, "open", False, err, symbol=sym, side=side, size=size, leverage=lev, reason=reason, context=context)
                            return {"success": False, "error": err}

                        if float(adj) != float(size):
                            logger.info(
                                "ExecutionGateway: adjust size symbol=%s requested=%s adjusted=%s minSz=%s lotSz=%s",
                                sym,
                                size,
                                adj,
                                min_sz,
                                lot_sz,
                            )
                        size = float(adj)
                except Exception as e:
                    logger.debug("ExecutionGateway: preflight check skipped: %s", e)
                set_lv = getattr(ex, "set_leverage", None)
                if callable(set_lv):
                    await set_lv(sym, lev, margin_mode)

                opn = getattr(ex, "open_swap_position", None)
                if not callable(opn):
                    self._metric_inc("open_fail")
                    err = "exchange has no open_swap_position"
                    self._record_order(source, "open", False, err, symbol=sym, side=side, size=size, leverage=lev, reason=reason, context=context)
                    return {"success": False, "error": err}

                res = await opn(
                    sym,
                    side,
                    float(size),
                    lev,
                    price,
                    margin_mode,
                )
                ok = bool(isinstance(res, dict) and res.get("success"))
                detail = str(res.get("error") if isinstance(res, dict) else res)[:500]
                self._record_order(source, "open", ok, detail or "ok", symbol=symbol, side=side, size=size, leverage=lev, reason=reason, context=context)
                if ok:
                    self._metric_inc("open_ok")
                    logger.info(
                        "ExecutionGateway: open_swap ok symbol=%s side=%s source=%s reason=%s",
                        symbol,
                        side,
                        source,
                        reason,
                    )
                    self._push_recent_event(
                        {
                            "ts": self._snapshot.last_order_at,
                            "op": "open",
                            "symbol": symbol,
                            "side": side,
                            "size": size,
                            "leverage": lev,
                            "source": source,
                            "reason": reason,
                            "success": True,
                            "detail": detail or "ok",
                            "context": context or {},
                        }
                    )
                    extra = ""
                    if context and isinstance(context, dict):
                        r = str(context.get("decision_reasoning") or context.get("reasoning") or "")[:160]
                        st = str(context.get("strategy") or context.get("strategy_used") or "")[:80]
                        parts = []
                        if st:
                            parts.append(f"策略: {st}")
                        if r:
                            parts.append(f"逻辑: {r}")
                        if parts:
                            extra = "\n" + "\n".join(parts)
                    await self._notify_telegram(
                        f"✅ 开仓\n交易对: {symbol}\n方向: {side}\n数量: {size}\n杠杆: {lev}x\n来源: {source}\n原因: {reason}{extra}"
                    )
                else:
                    self._metric_inc("open_fail")
                    logger.error(
                        "ExecutionGateway: open_swap failed symbol=%s source=%s err=%s",
                        symbol,
                        source,
                        detail,
                    )
                    self._push_recent_event(
                        {
                            "ts": self._snapshot.last_order_at,
                            "op": "open",
                            "symbol": symbol,
                            "side": side,
                            "size": size,
                            "leverage": lev,
                            "source": source,
                            "reason": reason,
                            "success": False,
                            "detail": detail,
                            "context": context or {},
                        }
                    )
                # trade event fanout (best-effort)
                try:
                    hub = getattr(self._mc, "trade_event_hub", None) if self._mc else None
                    trace_id = None
                    if context and isinstance(context, dict):
                        trace_id = context.get("trace_id")
                    if not trace_id:
                        trace_id = str(uuid.uuid4())
                    if hub and hasattr(hub, "publish_fill"):
                        from src.modules.core.trade_event_hub import TradeFill

                        await hub.publish_fill(
                            TradeFill(
                                trace_id=str(trace_id),
                                source=str(source or "gateway"),
                                symbol=str(symbol),
                                side=str(side),
                                action="open",
                                success=bool(ok),
                                order_id=(res.get("orderId") or res.get("order_id") or res.get("id")) if isinstance(res, dict) else None,
                                price=float(res.get("average") or res.get("price") or 0) if isinstance(res, dict) and (res.get("average") or res.get("price")) else None,
                                quantity=float(size) if size is not None else None,
                                detail=detail,
                                raw=dict(res) if isinstance(res, dict) else {"raw": str(res)},
                            )
                        )
                except Exception:
                    pass
                return res if isinstance(res, dict) else {"success": ok, "raw": res}
            except Exception as e:
                self._metric_inc("open_fail")
                self._record_order(source, "open", False, str(e), symbol=symbol, side=side, size=size, leverage=lev, reason=reason, context=context)
                logger.exception("ExecutionGateway.open_swap: %s", e)
                try:
                    hub = getattr(self._mc, "trade_event_hub", None) if self._mc else None
                    trace_id = None
                    if context and isinstance(context, dict):
                        trace_id = context.get("trace_id")
                    if not trace_id:
                        trace_id = str(uuid.uuid4())
                    if hub and hasattr(hub, "publish_fill"):
                        from src.modules.core.trade_event_hub import TradeFill

                        await hub.publish_fill(
                            TradeFill(
                                trace_id=str(trace_id),
                                source=str(source or "gateway"),
                                symbol=str(symbol),
                                side=str(side),
                                action="open",
                                success=False,
                                quantity=float(size) if size is not None else None,
                                detail=str(e)[:500],
                                raw={"error": str(e)},
                            )
                        )
                except Exception:
                    pass
                return {"success": False, "error": str(e)}

    def _record_order(
        self,
        source: str,
        op: str,
        success: bool,
        detail: str,
        *,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        size: Optional[float] = None,
        leverage: Optional[int] = None,
        reason: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._snapshot.last_order_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._snapshot.last_order_source = source
        self._snapshot.last_order_op = op
        self._snapshot.last_order_success = success
        self._snapshot.last_order_detail = detail[:800] if detail else None
        self._snapshot.last_order_symbol = symbol
        self._snapshot.last_order_side = side
        try:
            self._snapshot.last_order_size = float(size) if size is not None else None
        except Exception:
            self._snapshot.last_order_size = None
        try:
            self._snapshot.last_order_leverage = int(leverage) if leverage is not None else None
        except Exception:
            self._snapshot.last_order_leverage = None
        self._snapshot.last_order_reason = reason
        if context is None:
            self._snapshot.last_order_context = None
        else:
            try:
                self._snapshot.last_order_context = dict(context)
            except Exception:
                self._snapshot.last_order_context = {"raw": str(context)[:800]}

    async def get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        lim = max(1, min(int(limit or 20), self._recent_events_limit))
        return list(self._snapshot.recent_events[-lim:])

    async def get_snapshot(self) -> Dict[str, Any]:
        swo = await self.single_write_owner()
        self._snapshot.single_write_owner = swo
        ex = self._exchange()
        self._snapshot.exchange_connected = ex is not None
        out = self._snapshot.to_dict()
        out["policy_metrics"] = dict(self._policy_metrics)
        return out
