"""
Single narrow exit for live swap orders (S1 execution spine).

- Records last intent/outcome for observability
- Enforces single-write-owner policy for discretionary trading sources
- Auxiliary close sources are limited to SLTP + user manual; main lane closes with write_source=SWO.

来源约定（强制平仓仅三入口：主策略 SWO / 止盈止损 / 用户 manual）：
- 主策略：single_write_owner（默认 ai_core）经 AICoreDecisionEngine/ExecutionVerifier，平仓须 write_source=SWO
- 止盈止损：stop_loss_take_profit
- 用户：manual（API 或确认后的指令）
- 辅环：open 仍可用 source=system（见 _allow_open）；不得直连强制平仓
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

from src.modules.core.execution_reconciler import ExecutionReconciler
from src.modules.core.decision_trace_store import DecisionTraceStore
from src.modules.core.reconciliation_protection_manager import ReconciliationProtectionManager
from src.modules.core.trading_limits import resolve_position_limits
from src.modules.core.decision_contract import normalize_strategy_field
from src.modules.core.exchange_sync_ledger import append_exchange_truth

logger = logging.getLogger(__name__)

# Closes when source != SWO: only SLTP and explicit user manual (main lane uses write_source=SWO).
_AUXILIARY_WRITE_SOURCES: Set[str] = {
    "stop_loss_take_profit",
    "manual",
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
        if self._mc is not None and getattr(self._mc, "decision_trace_store", None) is None:
            try:
                self._mc.decision_trace_store = DecisionTraceStore()
            except Exception:
                pass
        self._reconciler = ExecutionReconciler(main_controller)
        self._reconciliation_protection = ReconciliationProtectionManager()
        self._locks: Dict[str, asyncio.Lock] = {}
        self._snapshot = ExecutionGatewaySnapshot()
        self._idempotent_recent: Dict[str, float] = {}
        self._idempotent_ttl_sec = 8.0
        self._recent_events_limit = 30
        self._open_retry_attempts = 2
        self._open_retry_base_delay_sec = 0.8
        self._open_retry_cap_delay_sec = 3.5
        self._open_symbol_cooldown_sec = 90.0
        self._open_symbol_cooldown_until: Dict[str, float] = {}
        self._open_symbol_fail_count: Dict[str, int] = {}
        self._open_retry_count: int = 0
        self._open_cooldown_denied_count: int = 0
        self._open_last_retry_error: Optional[str] = None
        self._open_last_retry_at: Optional[str] = None
        self._policy_metrics: Dict[str, int] = {
            "open_policy_denied": 0,
            "close_policy_denied": 0,
            "close_skipped": 0,
            "open_ok": 0,
            "open_fail": 0,
            "close_ok": 0,
            "close_fail": 0,
        }

    def _metric_inc(self, key: str) -> None:
        self._policy_metrics[key] = int(self._policy_metrics.get(key, 0)) + 1

    def get_policy_metrics(self) -> Dict[str, int]:
        return dict(self._policy_metrics)

    def get_reconciliation_protection_snapshot(self) -> Dict[str, Any]:
        return self._reconciliation_protection.get_snapshot()

    def _decision_trace_store(self) -> Optional[DecisionTraceStore]:
        try:
            return getattr(self._mc, "decision_trace_store", None)
        except Exception:
            return None

    def _push_recent_event(self, event: Dict[str, Any]) -> None:
        try:
            # Normalize event into a stable schema for downstream aggregation.
            e = dict(event or {})
            ctx = e.get("context") if isinstance(e.get("context"), dict) else {}
            op = str(e.get("op") or "").strip().lower()
            success = bool(e.get("success"))
            detail = str(e.get("detail") or "")

            if "event_id" not in e:
                e["event_id"] = str(uuid.uuid4())
            if "ts" not in e:
                e["ts"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            if "trace_id" not in e:
                e["trace_id"] = self._trace_id_from_context(ctx) or ""
            if "phase" not in e:
                e["phase"] = str(ctx.get("phase") or ("exchange" if op in {"open", "close"} else "unknown"))
            if "endpoint" not in e:
                e["endpoint"] = str(ctx.get("endpoint") or ctx.get("api") or ctx.get("url") or "")
            if "idempotency_key" not in e:
                e["idempotency_key"] = str(ctx.get("idempotency_key") or ctx.get("idempotent_key") or "")

            if "retriable" not in e:
                e["retriable"] = bool(ctx.get("retriable")) if "retriable" in ctx else self._is_retryable_open_error(detail)
            if "error_code" not in e:
                e["error_code"] = self._classify_error_code(op=op, success=success, detail=detail, ctx=ctx)

            # Trim context to avoid bloating snapshots.
            try:
                e["context"] = dict(ctx) if isinstance(ctx, dict) else {}
            except Exception:
                e["context"] = {"raw": str(ctx)[:800]}

            self._snapshot.recent_events.append(e)
            self._snapshot.recent_events = self._snapshot.recent_events[-self._recent_events_limit :]
        except Exception:
            pass

    @staticmethod
    def _classify_error_code(op: str, success: bool, detail: str, ctx: Optional[Dict[str, Any]] = None) -> str:
        """
        Convert a raw detail string into a stable, low-cardinality error_code for aggregation.
        """
        if success:
            return "OK"
        d = (detail or "").lower()
        c = ctx or {}

        # Policy / guards
        if "policy_denied" in d or "open_policy_denied" in d:
            return "POLICY_DENIED"
        if "semi_auto" in d or "半自动" in detail or "托管模式拦截" in detail:
            return "HOSTING_MODE_DENIED"
        if "open_cooldown_active" in d:
            return "OPEN_COOLDOWN_ACTIVE"
        if "风控" in detail or "redline" in d or "红线" in detail:
            return "RISK_REDLINE_DENIED"

        # Connectivity / exchange availability
        if "no_exchange" in d:
            return "NO_EXCHANGE"
        if "timeout" in d or "timed out" in d:
            return "TIMEOUT"
        if "connection" in d and ("reset" in d or "refused" in d or "closed" in d):
            return "CONNECTION_ERROR"
        if "network" in d or "dns" in d:
            return "NETWORK_ERROR"

        # Common exchange-side failures
        if (
            "scode=51169" in d
            or "51169" in d
            or "don't have any positions in this direction" in d
            or "no positions in this direction" in d
        ):
            return "ALREADY_CLOSED_NO_POSITION"
        if "all operations failed" in d:
            return "EXCHANGE_ALL_OPERATIONS_FAILED"
        if "insufficient" in d and ("margin" in d or "balance" in d):
            return "INSUFFICIENT_MARGIN"
        if "insufficient" in d and ("funds" in d or "balance" in d):
            return "INSUFFICIENT_FUNDS"
        if "size" in d and ("too small" in d or "min" in d or "minsz" in d):
            return "SIZE_TOO_SMALL"
        if "instrument" in d or "instid" in d:
            return "INSTRUMENT_INVALID"
        if "reduceonly" in d:
            return "REDUCE_ONLY_REJECTED"

        # Post-check anomalies
        if isinstance(c, dict):
            pc = c.get("post_close_check")
            if isinstance(pc, dict) and pc.get("status") in {"position_unchanged", "check_failed"}:
                return "POST_CHECK_ANOMALY"

        return "EXCHANGE_ERROR"

    async def _notify_telegram(self, text: str) -> None:
        try:
            if self._mc and hasattr(self._mc, "_send_notification_handler"):
                await self._mc._send_notification_handler("交易执行", str(text), priority="medium")
        except Exception:
            pass

    def _exchange(self) -> Any:
        ex = (
            getattr(self._mc, "execution_exchange", None)
            or getattr(self._mc, "okx_exchange", None)
            or getattr(self._mc, "exchange", None)
        )
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

    def _hosting_mode(self) -> str:
        mc = self._mc
        if mc and hasattr(mc, "get_hosting_mode"):
            try:
                m = str(mc.get_hosting_mode() or "full_auto").strip().lower()
                if m in {"full_auto", "semi_auto"}:
                    return m
            except Exception:
                pass
        return "full_auto"

    def _automation_profile(self) -> str:
        mc = self._mc
        if mc and hasattr(mc, "get_automation_profile"):
            try:
                p = str(mc.get_automation_profile() or "semi_auto").strip().lower()
                if p in {"conservative", "semi_auto", "full_auto"}:
                    return p
            except Exception:
                pass
        return "semi_auto"

    def _risk_redlines(self) -> Dict[str, Any]:
        mc = self._mc
        if mc and hasattr(mc, "get_risk_redlines"):
            try:
                out = mc.get_risk_redlines()
                if isinstance(out, dict):
                    return out
            except Exception:
                pass
        return {}

    @staticmethod
    def _is_manual_approved(source: str, context: Optional[Dict[str, Any]]) -> bool:
        src = str(source or "").strip().lower()
        if src in {"manual", "user", "api_chat"}:
            return True
        if context and isinstance(context, dict):
            return bool(context.get("manual_approved", False))
        return False

    async def _open_blocked_by_redlines(
        self,
        symbol: str,
        size: float,
        source: str,
        context: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        red = self._risk_redlines()
        if not red:
            return None
        # 保守模式：仅允许人工确认开仓
        if self._automation_profile() == "conservative" and not self._is_manual_approved(source, context):
            return "保守模式拦截：仅允许人工确认开仓"

        ex = self._exchange()
        if not ex:
            return None
        try:
            max_positions = int(red.get("max_positions", 0) or 0)
            if max_positions > 0 and hasattr(ex, "get_positions"):
                ps = await ex.get_positions()
                non_zero = 0
                for p in ps or []:
                    if not isinstance(p, dict):
                        continue
                    try:
                        v = float(p.get("size", p.get("pos", 0)) or 0)
                    except Exception:
                        v = 0.0
                    if abs(v) > 1e-12:
                        non_zero += 1
                if non_zero >= max_positions:
                    return f"风控红线拦截：持仓数 {non_zero} 已达到上限 {max_positions}"
        except Exception:
            pass
        return None

    def _allow_discretionary(self, source: str, swo: str) -> bool:
        src = (source or "").strip().lower()
        if src in _AUXILIARY_WRITE_SOURCES:
            return True
        return src == swo

    def _allow_open(self, source: str, swo: str) -> bool:
        """开仓仅允许 SWO 或 manual；强制单链路，杜绝旁路开仓。"""
        src = (source or "").strip().lower()
        # manual：人工显式触发允许开仓（用于运维/人工测试）
        if src == "manual":
            return True
        # 禁止任何系统旁路来源（system/proactive/secondary 等）直接开仓。
        # 若未来需要切换主控，只需切换 single_write_owner，不需要开放多来源。
        return src == swo

    @staticmethod
    def _is_retryable_open_error(detail: str) -> bool:
        d = str(detail or "").lower()
        if not d:
            return False
        retryable_markers = (
            "all operations failed",
            "connector is closed",
            "connection",
            "timeout",
            "temporarily",
            "system error",
            "rate limit",
        )
        return any(m in d for m in retryable_markers)

    def _is_symbol_open_cooling_down(self, symbol: str) -> bool:
        now = time.time()
        key = str(symbol or "").upper()
        until = float(self._open_symbol_cooldown_until.get(key, 0.0) or 0.0)
        if until <= now:
            self._open_symbol_cooldown_until.pop(key, None)
            return False
        return True

    def _mark_symbol_open_failure(self, symbol: str, detail: str) -> None:
        key = str(symbol or "").upper()
        cnt = int(self._open_symbol_fail_count.get(key, 0) or 0) + 1
        self._open_symbol_fail_count[key] = cnt
        # cooldown after repeated failures on the same symbol to reduce thrashing
        if cnt >= 2:
            self._open_symbol_cooldown_until[key] = time.time() + float(self._open_symbol_cooldown_sec)

    def _mark_symbol_open_success(self, symbol: str) -> None:
        key = str(symbol or "").upper()
        self._open_symbol_fail_count.pop(key, None)
        self._open_symbol_cooldown_until.pop(key, None)

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

    def _idempotent_key(self, symbol: str, side: str, op: str, extra: str = "") -> str:
        extra = str(extra or "").strip()
        if extra:
            return f"{op}:{symbol}:{side}:{extra}"
        return f"{op}:{symbol}:{side}"

    @staticmethod
    def _fmt_size_for_key(size: Optional[float]) -> str:
        if size is None:
            return "all"
        try:
            v = float(size)
        except Exception:
            return "all"
        # 保守去抖：避免浮点噪声造成 key 爆炸
        return f"{v:.8f}".rstrip("0").rstrip(".") or "0"

    @staticmethod
    def _trace_id_from_context(context: Optional[Dict[str, Any]]) -> str:
        if not context or not isinstance(context, dict):
            return ""
        tid = context.get("trace_id") or context.get("TraceId") or context.get("traceId")
        return str(tid or "").strip()

    @staticmethod
    def _extract_market_context(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Normalize regime/qty factor from gateway context for trade_history attribution."""
        ctx = context if isinstance(context, dict) else {}
        gp = ctx.get("guard_profile") if isinstance(ctx.get("guard_profile"), dict) else {}
        regime = (
            ctx.get("regime")
            or gp.get("regime")
            or gp.get("profile")
            or "unknown"
        )
        try:
            qty_factor = float(
                ctx.get("effective_qty_factor")
                if ctx.get("effective_qty_factor") is not None
                else gp.get("effective_qty_factor", 1.0)
            )
        except Exception:
            qty_factor = 1.0
        return {
            "regime": str(regime or "unknown"),
            "effective_qty_factor": float(qty_factor),
        }

    @staticmethod
    def _extract_strategy_id(context: Optional[Dict[str, Any]], default: str = "") -> str:
        ctx = context if isinstance(context, dict) else {}
        return normalize_strategy_field(ctx, metadata=ctx, default=default)

    def _close_idempotent_key(self, symbol: str, side: str, size: Optional[float], context: Optional[Dict[str, Any]]) -> str:
        """
        close 幂等粒度：
        - close_all (size=None) 维持粗粒度，避免多次 close_all 重入
        - partial close 带 size（规避“部分平仓被粗 key 吃掉”）
        - 若有 trace_id，则纳入 key（允许同 symbol/side 的不同链路并行）
        """
        tid = self._trace_id_from_context(context)
        sz = self._fmt_size_for_key(size)
        extra = f"{tid}:{sz}" if tid else sz
        return self._idempotent_key(symbol, side, "close", extra=extra)

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

    async def _enrich_close_result_with_exchange_fills(
        self, ex: Any, symbol: str, res: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        平仓回报里往往只有 ordId；用交易所 fills 回填 realizedPnl / fee / 均价，供入账与 accurate_only。
        """
        if not isinstance(res, dict) or not res.get("success"):
            return res
        oid = res.get("orderId") or res.get("order_id") or res.get("id")
        getter = getattr(ex, "get_swap_fills_for_order", None)
        if not oid or not callable(getter):
            return res
        fills: List[Dict[str, Any]] = []
        for attempt in range(4):
            try:
                fills = await getter(symbol, str(oid))
            except Exception:
                fills = []
            if fills:
                break
            await asyncio.sleep(0.2 * float(attempt + 1))
        if not fills:
            return res
        out = dict(res)
        total_pnl = 0.0
        total_fee = 0.0
        px_num = 0.0
        px_den = 0.0
        notional = 0.0
        ct_val = 0.0
        ct_is_base = False
        try:
            get_swap_info = getattr(ex, "get_swap_symbol_info", None)
            if callable(get_swap_info):
                info = await get_swap_info(symbol)
                if isinstance(info, dict):
                    ct_val = float(info.get("ctVal", 0) or 0)
                    ct_ccy = str(info.get("ctValCcy") or "").upper()
                    base_ccy = str(symbol).split("/")[0].upper()
                    ct_is_base = bool(ct_val > 0 and ct_ccy and base_ccy and ct_ccy == base_ccy)
        except Exception:
            ct_val = 0.0
            ct_is_base = False
        for f in fills:
            if not isinstance(f, dict):
                continue
            for k in ("fillPnl", "pnl", "realizedPnl"):
                if f.get(k) is None:
                    continue
                try:
                    total_pnl += float(f.get(k) or 0)
                    break
                except Exception:
                    continue
            try:
                total_fee += float(f.get("fee") or 0)
            except Exception:
                pass
            try:
                fsz = float(f.get("fillSz") or f.get("sz") or 0)
                fpx = float(f.get("fillPx") or f.get("px") or 0)
            except Exception:
                fsz, fpx = 0.0, 0.0
            if fsz > 0 and fpx > 0:
                px_num += fpx * fsz
                px_den += fsz
                if ct_val > 0:
                    # For SWAP: ctVal can be base-coin or USDT; normalize into an approximate USDT notional.
                    if ct_is_base:
                        notional += fsz * ct_val * fpx
                    else:
                        notional += fsz * ct_val
                else:
                    notional += fsz * fpx
        out["realizedPnl"] = total_pnl
        out["pnl"] = total_pnl
        out["fee"] = total_fee
        if px_den > 1e-18:
            out["average"] = px_num / px_den
            out["price"] = out["average"]
        out["fills_enriched"] = True
        out["fill_count"] = len(fills)
        out["notional_usdt_est"] = float(notional) if notional > 0 else None
        try:
            out["fee_rate_est"] = (abs(float(total_fee)) / float(notional)) if notional > 1e-18 else None
        except Exception:
            out["fee_rate_est"] = None
        return out

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
        Close a perpetual swap position. Non-SWO sources must be in
        _AUXILIARY_WRITE_SOURCES (SLTP, manual) or match single_write_owner unless force=True.
        """
        swo = await self.single_write_owner()
        self._snapshot.single_write_owner = swo

        if force and str(source or "").strip().lower() != "manual":
            self._metric_inc("close_policy_denied")
            msg = f"force_close_denied_non_manual source={source}"
            logger.error("ExecutionGateway.close_swap: %s", msg)
            self._record_order(source, "close", False, msg, symbol=symbol, side=side, size=size, leverage=None, reason=reason, context=context)
            return {"success": False, "error": msg}

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

        key = self._close_idempotent_key(symbol, side, size, context)
        if self._should_skip_idempotent(key):
            logger.info("ExecutionGateway: skip duplicate close %s", key)
            self._metric_inc("close_skipped")
            # best-effort fill event so front-end/ops can see the skip
            try:
                hub = getattr(self._mc, "trade_event_hub", None) if self._mc else None
                trace_id = self._trace_id_from_context(context) or str(uuid.uuid4())
                if hub and hasattr(hub, "publish_fill"):
                    from src.modules.core.trade_event_hub import TradeFill

                    await hub.publish_fill(
                        TradeFill(
                            trace_id=str(trace_id),
                            source=str(source or "gateway"),
                            symbol=str(symbol),
                            side=str(side),
                            action="close",
                            success=True,
                            order_id=None,
                            price=None,
                            quantity=float(size) if size is not None else None,
                            detail="idempotent_skip",
                            raw={"skipped": True, "reason": "idempotent", "idempotent_key": key},
                        )
                    )
            except Exception:
                pass
            return {"success": True, "skipped": True, "reason": "idempotent", "idempotent_key": key, "trace_id": self._trace_id_from_context(context)}

        async with self._symbol_lock(symbol):
            try:
                before_size: Optional[float] = None
                normalized_symbol = str(symbol or "").replace("-SWAP", "/USDT/SWAP")
                try:
                    get_positions = getattr(ex, "get_positions", None)
                    if callable(get_positions):
                        rows = await get_positions()
                        want_leg = str(side or "").strip().lower()
                        for p in rows or []:
                            ps = str(p.get("symbol") or p.get("instId") or "")
                            if normalized_symbol.split("/USDT")[0] not in ps:
                                continue
                            leg = str(p.get("side") or "").strip().lower()
                            if want_leg and leg and leg != want_leg:
                                continue
                            before_size = float(p.get("size") or 0.0)
                            break
                except Exception:
                    before_size = None

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
                    post_check: Dict[str, Any] = {"status": "not_checked"}
                    try:
                        get_positions = getattr(ex, "get_positions", None)
                        if callable(get_positions):
                            # 给交易所状态一个极短传播窗口，降低“刚成交但仓位快照未刷新”的误报。
                            await asyncio.sleep(0.35)
                            rows = await get_positions()
                            after_size = 0.0
                            found = False
                            want_leg2 = str(side or "").strip().lower()
                            for p in rows or []:
                                ps = str(p.get("symbol") or p.get("instId") or "")
                                if normalized_symbol.split("/USDT")[0] not in ps:
                                    continue
                                leg2 = str(p.get("side") or "").strip().lower()
                                if want_leg2 and leg2 and leg2 != want_leg2:
                                    continue
                                after_size = float(p.get("size") or 0.0)
                                found = True
                                break
                            if not found:
                                post_check = {
                                    "status": "position_closed",
                                    "before_size": before_size,
                                    "after_size": 0.0,
                                }
                            elif before_size is None:
                                post_check = {
                                    "status": "position_observed",
                                    "before_size": None,
                                    "after_size": after_size,
                                }
                            elif after_size < max(0.0, before_size - 1e-9):
                                post_check = {
                                    "status": "position_reduced",
                                    "before_size": before_size,
                                    "after_size": after_size,
                                }
                            elif after_size <= 1e-9:
                                post_check = {
                                    "status": "position_closed",
                                    "before_size": before_size,
                                    "after_size": after_size,
                                }
                            else:
                                post_check = {
                                    "status": "position_unchanged",
                                    "before_size": before_size,
                                    "after_size": after_size,
                                }
                    except Exception as chk_e:
                        post_check = {"status": "check_failed", "error": str(chk_e)[:240]}

                    if isinstance(res, dict):
                        res["post_close_check"] = post_check
                    post_status = str(post_check.get("status") or "")
                    if post_status in {"position_unchanged", "check_failed"}:
                        ok = False
                        self._metric_inc("close_fail")
                        detail = f"post_close_check_failed:{post_status}"
                        if isinstance(res, dict):
                            res["success"] = False
                            res["error"] = detail
                        self._record_order(
                            source,
                            "close",
                            False,
                            detail,
                            symbol=symbol,
                            side=side,
                            size=size,
                            leverage=None,
                            reason=reason,
                            context=context,
                        )
                        logger.error(
                            "ExecutionGateway: close verification failed symbol=%s side=%s source=%s status=%s before=%s after=%s",
                            symbol,
                            side,
                            source,
                            post_status,
                            post_check.get("before_size"),
                            post_check.get("after_size"),
                        )
                        return {"success": False, "error": detail, "post_close_check": post_check, "raw": res}
                    self._metric_inc("close_ok")
                    logger.info(
                        "ExecutionGateway: close_swap ok symbol=%s side=%s source=%s reason=%s",
                        symbol,
                        side,
                        source,
                        reason,
                    )
                    try:
                        res = await self._enrich_close_result_with_exchange_fills(ex, symbol, res)
                    except Exception:
                        pass
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
                # trade history persistence (best-effort)
                if ok:
                    try:
                        ths = getattr(self._mc, "trade_history_service", None) if self._mc else None
                        if ths and hasattr(ths, "record_trade_dict"):
                            ctx = context if isinstance(context, dict) else {}
                            mkt = self._extract_market_context(ctx)
                            price_val: float = 0.0
                            try:
                                if isinstance(res, dict) and (res.get("average") or res.get("price")):
                                    price_val = float(res.get("average") or res.get("price") or 0)
                                elif ctx.get("trigger_price") is not None:
                                    price_val = float(ctx.get("trigger_price") or 0)
                                elif ctx.get("mark_price") is not None:
                                    price_val = float(ctx.get("mark_price") or 0)
                            except Exception:
                                price_val = 0.0

                            fee_val: float = 0.0
                            try:
                                if isinstance(res, dict):
                                    fee_val = float(
                                        res.get("fee")
                                        or res.get("fillFee")
                                        or (res.get("data") or {}).get("fee", 0)
                                        or 0
                                    )
                            except Exception:
                                fee_val = 0.0

                            pnl_val: float = 0.0
                            pnl_pct_val: float = 0.0
                            pnl_estimated: bool = True
                            try:
                                realized_candidates = []
                                if isinstance(res, dict):
                                    realized_candidates.extend(
                                        [
                                            res.get("pnl"),
                                            res.get("realized_pnl"),
                                            res.get("realizedPnl"),
                                            res.get("fillPnl"),
                                            (res.get("data") or {}).get("pnl") if isinstance(res.get("data"), dict) else None,
                                            (res.get("data") or {}).get("realizedPnl") if isinstance(res.get("data"), dict) else None,
                                        ]
                                    )
                                if ctx.get("realized_pnl") is not None:
                                    realized_candidates.append(ctx.get("realized_pnl"))
                                for cand in realized_candidates:
                                    try:
                                        if cand is None or cand == "":
                                            continue
                                        pnl_val = float(cand)
                                        pnl_estimated = False
                                        break
                                    except Exception:
                                        continue

                                # 优先使用上游已计算的触发收益率（例如 SLTP 触发上下文），
                                # 可避免由于价格/名义缺失导致的 pnl 长期为 0。
                                if ctx.get("trigger_pnl_percent") is not None:
                                    pnl_pct_val = float(ctx.get("trigger_pnl_percent") or 0.0)
                                elif ctx.get("entry_price") is not None and price_val > 0:
                                    ep = float(ctx.get("entry_price") or 0)
                                    if ep > 0:
                                        sd = str(side or "").strip().lower()
                                        # close_swap 的 side 入参是 long/short（策略内部约定）；trade_history_service 会归一为 buy/sell
                                        if sd == "long":
                                            pnl_pct_val = (price_val - ep) / ep
                                        elif sd == "short":
                                            pnl_pct_val = (ep - price_val) / ep
                                if pnl_estimated:
                                    # 名义金额兜底：position_notional -> 合约 ctVal 估算 -> 数量*价格
                                    position_notional = float(ctx.get("position_notional") or 0.0)
                                    try:
                                        qty = float(size or 0.0) if size is not None else float(ctx.get("quantity") or 0.0)
                                    except Exception:
                                        qty = 0.0
                                    try:
                                        ep = float(ctx.get("entry_price") or 0.0)
                                    except Exception:
                                        ep = 0.0
                                    ref_px = ep if ep > 0 else price_val
                                    if position_notional <= 0 and qty > 0:
                                        ct_val = 0.0
                                        ct_is_base = False
                                        try:
                                            get_swap_info = getattr(ex, "get_swap_symbol_info", None)
                                            if callable(get_swap_info):
                                                info = await get_swap_info(sym)
                                                if isinstance(info, dict):
                                                    ct_val = float(info.get("ctVal", 0) or 0)
                                                    ct_ccy = str(info.get("ctValCcy") or "").upper()
                                                    base_ccy = str(sym).split("/")[0].upper()
                                                    ct_is_base = bool(ct_val > 0 and ct_ccy and base_ccy and ct_ccy == base_ccy)
                                        except Exception:
                                            ct_val = 0.0
                                            ct_is_base = False
                                        if ct_val > 0:
                                            if ct_is_base and ref_px > 0:
                                                position_notional = qty * ct_val * ref_px
                                            else:
                                                position_notional = qty * ct_val
                                        elif ref_px > 0:
                                            position_notional = qty * ref_px
                                    pnl_val = float(pnl_pct_val) * max(1e-12, float(position_notional or 0.0))
                            except Exception:
                                pnl_val = 0.0
                                pnl_pct_val = 0.0
                                pnl_estimated = True

                            _sid = self._extract_strategy_id(ctx, default=str(source or "gateway"))
                            await ths.record_trade_dict(
                                {
                                    "timestamp": self._snapshot.last_order_at,
                                    "symbol": str(symbol),
                                    "side": str(side),
                                    "action": "close",
                                    "source": str(source or "gateway"),
                                    "reason": str(reason or ""),
                                    "status": "filled",
                                    "strategy": _sid,
                                    "order_id": (res.get("orderId") or res.get("order_id") or res.get("id")) if isinstance(res, dict) else None,
                                    "price": float(price_val),
                                    "quantity": float(size) if size is not None else None,
                                    "fee": float(fee_val),
                                    "pnl": float(pnl_val),
                                    "pnl_percent": float(pnl_pct_val),
                                    "metadata": {
                                        "market_context": {
                                            "regime": mkt.get("regime"),
                                            "effective_qty_factor": float(mkt.get("effective_qty_factor", 1.0)),
                                        },
                                        "gateway": {
                                            "op": "close",
                                            "source": str(source or "gateway"),
                                            "reason": str(reason or ""),
                                            "context": dict(ctx) if isinstance(ctx, dict) else {},
                                        },
                                        "pnl_estimated": bool(pnl_estimated),
                                        "raw": dict(res) if isinstance(res, dict) else {"raw": str(res)},
                                    },
                                }
                            )
                            try:
                                await append_exchange_truth(
                                    {
                                        "event": "trade_close_recorded",
                                        "symbol": str(symbol),
                                        "side": str(side),
                                        "order_id": (res.get("orderId") or res.get("order_id") or res.get("id")) if isinstance(res, dict) else None,
                                        "price": float(price_val),
                                        "quantity": float(size) if size is not None else None,
                                        "pnl": float(pnl_val),
                                        "fee": float(fee_val),
                                        "notional_usdt_est": (res.get("notional_usdt_est") if isinstance(res, dict) else None),
                                        "fee_rate_est": (res.get("fee_rate_est") if isinstance(res, dict) else None),
                                        "pnl_estimated": bool(pnl_estimated),
                                        "fills_enriched": bool((res or {}).get("fills_enriched")) if isinstance(res, dict) else False,
                                        "source": str(source or "gateway"),
                                    }
                                )
                            except Exception:
                                pass
                    except Exception:
                        pass
                    # memory persistence (best-effort): feed AILearningEngine (trade_close memories)
                    try:
                        mc = self._mc
                        mg = getattr(mc, "memory_gateway", None) if mc else None
                        if mg and hasattr(mg, "add_memory"):
                            ctx = context if isinstance(context, dict) else {}
                            await mg.add_memory(
                                memory_type="trade_record",
                                content=f"trade_close {symbol} {side} pnl={pnl_val:+.4f} pnl_pct={pnl_pct_val:+.4%} price={price_val} qty={size}",
                                metadata={
                                    "kind": "trade_close",
                                    "symbol": str(symbol),
                                    "side": str(side),
                                    "pnl": float(pnl_val),
                                    "pnl_percent": float(pnl_pct_val),
                                    "price": float(price_val),
                                    "quantity": float(size) if size is not None else None,
                                    "order_id": (res.get("orderId") or res.get("order_id") or res.get("id")) if isinstance(res, dict) else None,
                                    "trace_id": (ctx.get("trace_id") if isinstance(ctx, dict) else None),
                                    "source": str(source or "gateway"),
                                    "reason": str(reason or ""),
                                },
                                source_module="execution_gateway",
                                importance=0.75,
                                tags=["trade_close", "learning_feed"],
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

        # 托管模式门控：
        # - full_auto: 按原有策略放行
        # - semi_auto: 策略自动开仓默认拒绝，需人工确认（manual source 或 manual_approved）
        if self._hosting_mode() == "semi_auto" and not self._is_manual_approved(source, context):
            self._metric_inc("open_policy_denied")
            msg = "托管模式拦截：当前为半自动，需人工确认后才允许开仓"
            logger.warning("ExecutionGateway.open_swap: %s source=%s", msg, source)
            self._record_order(
                source,
                "open",
                False,
                msg,
                symbol=symbol,
                side=side,
                size=size,
                leverage=leverage,
                reason=reason,
                context=context,
            )
            return {"success": False, "error": msg}

        redline_err = await self._open_blocked_by_redlines(symbol=symbol, size=size, source=source, context=context)
        if redline_err:
            self._metric_inc("open_policy_denied")
            self._record_order(
                source,
                "open",
                False,
                redline_err,
                symbol=symbol,
                side=side,
                size=size,
                leverage=leverage,
                reason=reason,
                context=context,
            )
            return {"success": False, "error": redline_err}

        if not self._allow_open(source, swo):
            self._metric_inc("open_policy_denied")
            msg = f"open_policy_denied source={source} swo={swo}"
            logger.error("ExecutionGateway.open_swap: %s", msg)
            self._record_order(source, "open", False, msg, symbol=symbol, side=side, size=size, leverage=leverage, reason=reason, context=context)
            # trade event fanout (best-effort)
            try:
                hub = getattr(self._mc, "trade_event_hub", None) if self._mc else None
                trace_id = self._trace_id_from_context(context) or str(uuid.uuid4())
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
                            order_id=None,
                            price=None,
                            quantity=float(size) if size is not None else None,
                            detail=msg,
                            raw={"error": msg, "reason": reason, "context": context or {}},
                        )
                    )
            except Exception:
                pass
            return {"success": False, "error": msg}

        if self._is_symbol_open_cooling_down(symbol):
            self._metric_inc("open_policy_denied")
            self._open_cooldown_denied_count += 1
            left = int(max(1.0, self._open_symbol_cooldown_until.get(str(symbol).upper(), 0.0) - time.time()))
            msg = f"open_cooldown_active:{left}s"
            logger.warning("ExecutionGateway.open_swap: cooldown deny symbol=%s source=%s left=%ss", symbol, source, left)
            self._record_order(source, "open", False, msg, symbol=symbol, side=side, size=size, leverage=leverage, reason=reason, context=context)
            return {"success": False, "error": msg}

        try:
            rec = await self._reconciler.build_snapshot(recent_events=list(self._snapshot.recent_events))
            self._reconciliation_protection.ingest_reconciliation(rec)
            protect_err = self._reconciliation_protection.allow_open(symbol)
            if protect_err:
                dts = self._decision_trace_store()
                if dts:
                    dts.record_reconciliation_result(
                        trace_id=self._trace_id_from_context(context) or "",
                        status="blocked",
                        detail=protect_err,
                        extras={"symbol": symbol},
                    )
                self._metric_inc("open_policy_denied")
                logger.warning("ExecutionGateway.open_swap: reconciliation protection deny symbol=%s err=%s", symbol, protect_err)
                self._record_order(
                    source,
                    "open",
                    False,
                    protect_err,
                    symbol=symbol,
                    side=side,
                    size=size,
                    leverage=leverage,
                    reason=reason,
                    context=context,
                )
                return {"success": False, "error": protect_err}
        except Exception as e:
            logger.debug("ExecutionGateway.open_swap: reconciliation protection skipped: %s", e)

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

                        # Unified per-symbol margin hard cap for ALL sources.
                        # Prevents route differences (ai_core vs ai_trading_engine/proactive) from bypassing 20% rule.
                        try:
                            bal = await ex.get_balance() if hasattr(ex, "get_balance") else {}
                            usdt = bal.get("USDT", 0) if isinstance(bal, dict) else 0
                            available = float(usdt.get("free", usdt.get("available", 0)) if isinstance(usdt, dict) else usdt or 0)
                            available = max(0.0, available)

                            limits = await resolve_position_limits(
                                config_manager=(self._mc.config_manager if self._mc else None),
                                ai_config=None,
                                trading_config=None,
                            )
                            sym_cap = max(0.01, min(0.92, float(limits.symbol_max_margin_ratio)))
                            cap_margin = available * sym_cap

                            ticker = await ex.get_ticker(sym) if hasattr(ex, "get_ticker") else {}
                            px = float((ticker or {}).get("last") or (ticker or {}).get("price") or 0.0)
                            lev_f = max(1.0, float(lev))
                            ct_val = float(info.get("ctVal", 0) or 0)
                            ct_ccy = str(info.get("ctValCcy") or "").upper()
                            base = str(sym).split("/")[0].upper()
                            ct_is_base = bool(ct_val > 0 and ct_ccy and base and ct_ccy == base)

                            def _notional(q: float) -> float:
                                q = max(0.0, float(q or 0))
                                if q <= 0 or px <= 0:
                                    return 0.0
                                if ct_val > 0:
                                    return q * ct_val * px if ct_is_base else q * ct_val
                                return q * px

                            projected_notional = _notional(size)
                            required_margin = projected_notional / lev_f
                            # Include existing same-symbol exposure in cap check (not just single order),
                            # so scale-in cannot push total symbol margin above cap.
                            existing_margin = 0.0
                            try:
                                get_positions = getattr(ex, "get_positions", None)
                                if callable(get_positions):
                                    rows = await get_positions()
                                    norm = str(sym).upper().replace("-", "/")
                                    base = norm.split("/USDT")[0]
                                    for p in rows or []:
                                        ps = str(p.get("symbol") or p.get("instId") or "").upper()
                                        if base not in ps:
                                            continue
                                        sz = float(p.get("size") or 0.0)
                                        if sz <= 0:
                                            continue
                                        # notional_value from adapter is preferred
                                        n0 = float(p.get("notional_value") or 0.0)
                                        if n0 <= 0:
                                            mark = float(p.get("mark_px") or p.get("mark_price") or px or 0.0)
                                            if mark > 0:
                                                if ct_val > 0:
                                                    n0 = sz * ct_val * mark if ct_is_base else sz * ct_val
                                                else:
                                                    n0 = sz * mark
                                        existing_margin += max(0.0, n0 / lev_f)
                            except Exception:
                                existing_margin = max(0.0, existing_margin)
                            total_margin_after = existing_margin + required_margin
                            if cap_margin > 0 and required_margin > cap_margin:
                                capped_notional = cap_margin * lev_f
                                if ct_val > 0:
                                    per_contract_notional = (ct_val * px) if ct_is_base else ct_val
                                    new_size = max(1.0, math.floor(capped_notional / max(1e-12, per_contract_notional)))
                                else:
                                    new_size = max(1.0, math.floor(capped_notional / max(1e-12, px)))
                                if lot_sz > 0:
                                    new_size = math.floor(new_size / lot_sz) * lot_sz
                                if min_sz > 0 and new_size < min_sz:
                                    err = (
                                        f"margin_cap_denied req={required_margin:.2f} cap={cap_margin:.2f} "
                                        f"symbol={sym} size={size}"
                                    )
                                    self._metric_inc("open_fail")
                                    self._record_order(
                                        source, "open", False, err, symbol=sym, side=side, size=size, leverage=lev, reason=reason, context=context
                                    )
                                    return {"success": False, "error": err}
                                logger.warning(
                                    "ExecutionGateway: margin hard-cap resize symbol=%s source=%s size=%s->%s req=%.2f cap=%.2f ctVal=%s",
                                    sym,
                                    source,
                                    size,
                                    new_size,
                                    required_margin,
                                    cap_margin,
                                    ct_val if ct_val > 0 else "n/a",
                                )
                                size = float(new_size)
                                projected_notional = _notional(size)
                                required_margin = projected_notional / lev_f
                                total_margin_after = existing_margin + required_margin
                            if cap_margin > 0 and total_margin_after > cap_margin * 1.0001:
                                err = (
                                    f"symbol_margin_total_cap_denied existing={existing_margin:.2f} "
                                    f"new={required_margin:.2f} cap={cap_margin:.2f} symbol={sym}"
                                )
                                self._metric_inc("open_fail")
                                self._record_order(
                                    source, "open", False, err, symbol=sym, side=side, size=size, leverage=lev, reason=reason, context=context
                                )
                                return {"success": False, "error": err}
                        except Exception as e:
                            logger.debug("ExecutionGateway: margin hard-cap check skipped: %s", e)
                except Exception as e:
                    logger.debug("ExecutionGateway: preflight check skipped: %s", e)
                # 杠杆设置职责：默认交由交易所适配器（例如 OKX 的 open_swap_position 内已设置杠杆），避免重复调用。
                # 如需在 S1 统一设置，可在 ai_brain.policy.gateway_sets_leverage=true 显式开启。
                try:
                    pol = {}
                    if self._mc and hasattr(self._mc, "config_manager") and self._mc.config_manager:
                        pol = self._mc.config_manager.get_config_sync("ai_brain", {}) or {}
                    gateway_sets = False
                    if isinstance(pol, dict):
                        if isinstance(pol.get("policy"), dict):
                            gateway_sets = bool(pol.get("policy", {}).get("gateway_sets_leverage", False))
                        else:
                            gateway_sets = bool(pol.get("gateway_sets_leverage", False))
                    if gateway_sets:
                        set_lv = getattr(ex, "set_leverage", None)
                        if callable(set_lv):
                            await set_lv(sym, lev, margin_mode)
                except Exception:
                    pass

                opn = getattr(ex, "open_swap_position", None)
                if not callable(opn):
                    self._metric_inc("open_fail")
                    err = "exchange has no open_swap_position"
                    self._record_order(source, "open", False, err, symbol=sym, side=side, size=size, leverage=lev, reason=reason, context=context)
                    return {"success": False, "error": err}

                res: Any = None
                detail = ""
                max_attempts = max(1, int(self._open_retry_attempts or 1))
                for attempt in range(1, max_attempts + 1):
                    res = await opn(
                        sym,
                        side,
                        float(size),
                        lev,
                        price,
                        margin_mode,
                    )
                    ok_attempt = bool(isinstance(res, dict) and res.get("success"))
                    detail = str(res.get("error") if isinstance(res, dict) else res)[:500]
                    if ok_attempt:
                        break
                    if attempt >= max_attempts or not self._is_retryable_open_error(detail):
                        break
                    self._open_retry_count += 1
                    self._open_last_retry_error = detail[:500]
                    self._open_last_retry_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    # best-effort connection refresh before retry
                    try:
                        rebuild = getattr(ex, "_rebuild_session", None)
                        if callable(rebuild):
                            await rebuild("gateway open retry")
                    except Exception:
                        pass
                    delay = min(
                        float(self._open_retry_cap_delay_sec),
                        float(self._open_retry_base_delay_sec) * (2 ** (attempt - 1)),
                    )
                    await asyncio.sleep(max(0.0, delay))
                ok = bool(isinstance(res, dict) and res.get("success"))
                detail = str(res.get("error") if isinstance(res, dict) else res)[:500]
                self._record_order(source, "open", ok, detail or "ok", symbol=symbol, side=side, size=size, leverage=lev, reason=reason, context=context)
                if ok:
                    self._mark_symbol_open_success(symbol)
                    self._metric_inc("open_ok")
                    logger.info(
                        "ExecutionGateway: open_swap ok symbol=%s side=%s source=%s reason=%s",
                        symbol,
                        side,
                        source,
                        reason,
                    )
                    extra = ""
                    if context and isinstance(context, dict):
                        r = str(context.get("decision_reasoning") or context.get("reasoning") or "")[:160]
                        st = str(self._extract_strategy_id(context, default=""))[:80]
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
                    self._mark_symbol_open_failure(symbol, detail)
                    self._metric_inc("open_fail")
                    logger.error(
                        "ExecutionGateway: open_swap failed symbol=%s source=%s err=%s",
                        symbol,
                        source,
                        detail,
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
                # trade history persistence (best-effort)
                if ok:
                    try:
                        ths = getattr(self._mc, "trade_history_service", None) if self._mc else None
                        if ths and hasattr(ths, "record_trade_dict"):
                            ctx = context if isinstance(context, dict) else {}
                            mkt = self._extract_market_context(ctx)
                            price_val: float = 0.0
                            try:
                                if isinstance(res, dict) and (res.get("average") or res.get("price")):
                                    price_val = float(res.get("average") or res.get("price") or 0)
                                elif ctx.get("mark_price") is not None:
                                    price_val = float(ctx.get("mark_price") or 0)
                            except Exception:
                                price_val = 0.0

                            fee_val: float = 0.0
                            try:
                                if isinstance(res, dict):
                                    fee_val = float(
                                        res.get("fee")
                                        or res.get("fillFee")
                                        or (res.get("data") or {}).get("fee", 0)
                                        or 0
                                    )
                            except Exception:
                                fee_val = 0.0

                            _sid = self._extract_strategy_id(ctx, default=str(source or "gateway"))
                            await ths.record_trade_dict(
                                {
                                    "timestamp": self._snapshot.last_order_at,
                                    "symbol": str(symbol),
                                    "side": str(side),
                                    "action": "open",
                                    "source": str(source or "gateway"),
                                    "reason": str(reason or ""),
                                    "status": "filled",
                                    "strategy": _sid,
                                    "order_id": (res.get("orderId") or res.get("order_id") or res.get("id")) if isinstance(res, dict) else None,
                                    "price": float(price_val),
                                    "quantity": float(size) if size is not None else None,
                                    "leverage": int(lev) if lev is not None else None,
                                    "fee": float(fee_val),
                                    "metadata": {
                                        "market_context": {
                                            "regime": mkt.get("regime"),
                                            "effective_qty_factor": float(mkt.get("effective_qty_factor", 1.0)),
                                        },
                                        "gateway": {
                                            "op": "open",
                                            "source": str(source or "gateway"),
                                            "reason": str(reason or ""),
                                            "context": dict(ctx) if isinstance(ctx, dict) else {},
                                        },
                                        "raw": dict(res) if isinstance(res, dict) else {"raw": str(res)},
                                    },
                                }
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

        # Always emit a normalized recent_event for aggregation/diagnosis.
        try:
            ev_ctx: Dict[str, Any] = {}
            if isinstance(context, dict):
                ev_ctx.update(context)
            trace_id = self._trace_id_from_context(ev_ctx)
            self._push_recent_event(
                {
                    "ts": self._snapshot.last_order_at,
                    "op": str(op or "").strip().lower(),
                    "symbol": symbol,
                    "side": side,
                    "size": size,
                    "leverage": leverage,
                    "source": source,
                    "reason": reason,
                    "success": bool(success),
                    "detail": str(detail or "")[:800],
                    "context": ev_ctx,
                }
            )
            dts = self._decision_trace_store()
            if dts and trace_id:
                dts.record_execution_result(
                    trace_id=trace_id,
                    status="success" if bool(success) else "failed",
                    detail=str(detail or "")[:500],
                    source=source,
                    op=op,
                    extras={
                        "symbol": symbol,
                        "side": side,
                        "size": size,
                        "leverage": leverage,
                        "reason": reason,
                    },
                )
        except Exception:
            pass

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
        now = time.time()
        cooldown_symbols: Dict[str, int] = {}
        for sym, until in list(self._open_symbol_cooldown_until.items()):
            left = int(float(until) - now)
            if left > 0:
                cooldown_symbols[str(sym)] = left
            else:
                self._open_symbol_cooldown_until.pop(sym, None)
        out["execution_resilience"] = {
            "open_retry_attempts_config": int(self._open_retry_attempts),
            "open_retry_count": int(self._open_retry_count),
            "open_last_retry_error": self._open_last_retry_error,
            "open_last_retry_at": self._open_last_retry_at,
            "open_cooldown_seconds_config": int(self._open_symbol_cooldown_sec),
            "open_cooldown_denied_count": int(self._open_cooldown_denied_count),
            "open_cooldown_symbols": cooldown_symbols,
            "open_symbol_fail_count": dict(self._open_symbol_fail_count),
        }
        try:
            rec = await self._reconciler.build_snapshot(
                recent_events=list(self._snapshot.recent_events)
            )
            self._reconciliation_protection.ingest_reconciliation(rec)
            out["reconciliation"] = rec
            out["reconciliation_protection"] = self._reconciliation_protection.get_snapshot()
        except Exception as e:
            out["reconciliation"] = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "healthy": False,
                "severity": "warning",
                "error": f"reconciliation_error:{type(e).__name__}",
            }
            out["reconciliation_protection"] = self._reconciliation_protection.get_snapshot()
        dts = self._decision_trace_store()
        out["decision_traces"] = dts.get_recent(limit=20) if dts else []
        return out
