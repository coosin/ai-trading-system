"""
Single narrow exit for live swap orders (S1 execution spine).

- Records last intent/outcome for observability
- Enforces single-write-owner policy for discretionary trading sources
- Risk/auxiliary sources (e.g. SL/TP) may always submit closes
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
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
    last_order_success: Optional[bool] = None
    last_order_detail: Optional[str] = None
    exchange_connected: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "single_write_owner": self.single_write_owner,
            "last_tick_at": self.last_tick_at,
            "last_tick_source": self.last_tick_source,
            "last_order_at": self.last_order_at,
            "last_order_source": self.last_order_source,
            "last_order_op": self.last_order_op,
            "last_order_success": self.last_order_success,
            "last_order_detail": self.last_order_detail,
            "exchange_connected": self.exchange_connected,
            "notes": list(self.notes),
        }


class ExecutionGateway:
    """Central gate for OKX-style swap closes/opens with policy + metrics."""

    def __init__(self, main_controller: Any) -> None:
        self._mc = main_controller
        self._locks: Dict[str, asyncio.Lock] = {}
        self._snapshot = ExecutionGatewaySnapshot()
        self._idempotent_recent: Dict[str, float] = {}
        self._idempotent_ttl_sec = 8.0

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
                },
            )
        return {"single_write_owner": "ai_core", "primary_controller": "ai_core"}

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
        if src in ("execution_verifier", "manual", "system"):
            return True
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
    ) -> Dict[str, Any]:
        """
        Close a perpetual swap position. SL/TP and risk paths set force=False but
        pass source in _AUXILIARY_WRITE_SOURCES so policy always allows them.
        """
        swo = await self.single_write_owner()
        self._snapshot.single_write_owner = swo

        if not force and not self._allow_discretionary(source, swo):
            msg = f"policy_denied source={source} swo={swo}"
            logger.error("ExecutionGateway.close_swap: %s", msg)
            self._record_order(source, "close", False, msg)
            return {"success": False, "error": msg}

        ex = self._exchange()
        self._snapshot.exchange_connected = ex is not None
        if not ex:
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
                self._record_order(source, "close", ok, detail or "ok")
                if ok:
                    logger.info(
                        "ExecutionGateway: close_swap ok symbol=%s side=%s source=%s reason=%s",
                        symbol,
                        side,
                        source,
                        reason,
                    )
                else:
                    logger.error(
                        "ExecutionGateway: close_swap failed symbol=%s source=%s err=%s",
                        symbol,
                        source,
                        detail,
                    )
                return res if isinstance(res, dict) else {"success": ok, "raw": res}
            except Exception as e:
                self._record_order(source, "close", False, str(e))
                logger.exception("ExecutionGateway.close_swap: %s", e)
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
    ) -> Dict[str, Any]:
        """开永续仓位（经策略校验后的唯一入口之一）。"""
        swo = await self.single_write_owner()
        self._snapshot.single_write_owner = swo

        if not self._allow_open(source, swo):
            msg = f"open_policy_denied source={source} swo={swo}"
            logger.error("ExecutionGateway.open_swap: %s", msg)
            self._record_order(source, "open", False, msg)
            return {"success": False, "error": msg}

        ex = self._exchange()
        self._snapshot.exchange_connected = ex is not None
        if not ex:
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
                            err = f"preflight_denied size>{max_sz} (requested={size} adjusted={adj})"
                            self._record_order(source, "open", False, err)
                            return {"success": False, "error": err}

                        if adj <= 0:
                            err = f"preflight_denied invalid_size (requested={size} adjusted={adj})"
                            self._record_order(source, "open", False, err)
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
                    err = "exchange has no open_swap_position"
                    self._record_order(source, "open", False, err)
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
                self._record_order(source, "open", ok, detail or "ok")
                if ok:
                    logger.info(
                        "ExecutionGateway: open_swap ok symbol=%s side=%s source=%s reason=%s",
                        symbol,
                        side,
                        source,
                        reason,
                    )
                else:
                    logger.error(
                        "ExecutionGateway: open_swap failed symbol=%s source=%s err=%s",
                        symbol,
                        source,
                        detail,
                    )
                return res if isinstance(res, dict) else {"success": ok, "raw": res}
            except Exception as e:
                self._record_order(source, "open", False, str(e))
                logger.exception("ExecutionGateway.open_swap: %s", e)
                return {"success": False, "error": str(e)}

    def _record_order(self, source: str, op: str, success: bool, detail: str) -> None:
        self._snapshot.last_order_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._snapshot.last_order_source = source
        self._snapshot.last_order_op = op
        self._snapshot.last_order_success = success
        self._snapshot.last_order_detail = detail[:800] if detail else None

    async def get_snapshot(self) -> Dict[str, Any]:
        swo = await self.single_write_owner()
        self._snapshot.single_write_owner = swo
        ex = self._exchange()
        self._snapshot.exchange_connected = ex is not None
        return self._snapshot.to_dict()
