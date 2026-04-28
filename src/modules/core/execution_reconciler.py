from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _norm_symbol(symbol: Any) -> str:
    s = str(symbol or "").strip()
    if not s:
        return ""
    s = s.replace("-", "/")
    if s.endswith("/SWAP"):
        s = s[: -len("/SWAP")]
    if s.endswith("/USDT/SWAP"):
        s = s.replace("/USDT/SWAP", "/USDT")
    return s


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        if x != x:
            return default
        return x
    except Exception:
        return default


class ExecutionReconciler:
    """
    Lightweight runtime reconciliation between exchange truth and local AI views.

    Goals:
    - detect drift between exchange positions and local in-process positions
    - surface suspicious open orders that may require manual inspection
    - refresh local AI position views before comparison to reduce stale-state decisions
    """

    def __init__(self, main_controller: Any) -> None:
        self._mc = main_controller
        self._last_snapshot: Dict[str, Any] = {}
        self._last_run_ts: float = 0.0
        self._min_interval_sec: float = 8.0

    async def _refresh_local_views(self) -> Dict[str, bool]:
        out = {
            "ai_trading_engine_positions_refreshed": False,
            "ai_core_positions_refreshed": False,
        }
        mc = self._mc
        if not mc:
            return out

        eng = getattr(mc, "ai_trading_engine", None)
        if eng and hasattr(eng, "_update_positions"):
            try:
                await asyncio.wait_for(eng._update_positions(), timeout=4.5)
                out["ai_trading_engine_positions_refreshed"] = True
            except Exception:
                pass

        core = getattr(mc, "ai_core", None)
        if core and hasattr(core, "_get_current_positions"):
            try:
                rows = await asyncio.wait_for(core._get_current_positions(), timeout=4.5)
                if isinstance(rows, list):
                    core._current_positions = {
                        _norm_symbol(p.get("symbol")): p
                        for p in rows
                        if isinstance(p, dict) and _norm_symbol(p.get("symbol"))
                    }
                out["ai_core_positions_refreshed"] = True
            except Exception:
                pass
        return out

    async def _exchange_positions(self, ex: Any) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
        try:
            rows = await asyncio.wait_for(ex.get_positions(), timeout=6.0)
        except Exception as e:
            return {}, type(e).__name__
        out: Dict[str, Dict[str, Any]] = {}
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            sym = _norm_symbol(row.get("symbol") or row.get("instId"))
            if not sym:
                continue
            size = abs(_safe_float(row.get("size", row.get("pos", 0.0)), 0.0))
            if size <= 1e-12:
                continue
            side = str(row.get("side") or "").lower()
            if side not in {"long", "short"}:
                raw = str(row.get("posSide_raw") or row.get("posSide") or "").lower()
                side = raw if raw in {"long", "short"} else "long"
            out[sym] = {
                "symbol": sym,
                "side": side,
                "size": size,
                "entry_price": _safe_float(row.get("entry_price", row.get("avgPx", 0.0)), 0.0),
                "mark_price": _safe_float(
                    row.get("mark_price", row.get("mark_px", row.get("markPx", 0.0))),
                    0.0,
                ),
                "source": "exchange",
            }
        return out, None

    async def _exchange_open_orders(self, ex: Any) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        try:
            rows = await asyncio.wait_for(ex.get_open_orders(), timeout=6.0)
        except Exception as e:
            return [], type(e).__name__
        out: List[Dict[str, Any]] = []
        for row in rows or []:
            sym = _norm_symbol(getattr(row, "symbol", None))
            if not sym:
                continue
            ts = getattr(row, "timestamp", None)
            age_sec = None
            if isinstance(ts, datetime):
                try:
                    age_sec = max(0, int((datetime.now() - ts).total_seconds()))
                except Exception:
                    age_sec = None
            out.append(
                {
                    "order_id": getattr(row, "order_id", None),
                    "symbol": sym,
                    "side": str(getattr(row, "side", "") or ""),
                    "order_type": str(getattr(row, "order_type", "") or ""),
                    "status": str(getattr(row, "status", "") or ""),
                    "quantity": _safe_float(getattr(row, "quantity", 0.0), 0.0),
                    "executed_quantity": _safe_float(getattr(row, "executed_quantity", 0.0), 0.0),
                    "price": _safe_float(getattr(row, "price", 0.0), 0.0),
                    "age_sec": age_sec,
                }
            )
        return out, None

    def _local_positions_from_ai_engine(self) -> Dict[str, Dict[str, Any]]:
        eng = getattr(self._mc, "ai_trading_engine", None)
        positions = getattr(eng, "positions", {}) if eng else {}
        out: Dict[str, Dict[str, Any]] = {}
        if not isinstance(positions, dict):
            return out
        for symbol, pos in positions.items():
            sym = _norm_symbol(symbol)
            if not sym:
                continue
            qty = abs(_safe_float(getattr(pos, "quantity", 0.0), 0.0))
            if qty <= 1e-12:
                continue
            out[sym] = {
                "symbol": sym,
                "side": str(getattr(pos, "side", "") or "").lower(),
                "size": qty,
                "entry_price": _safe_float(getattr(pos, "entry_price", 0.0), 0.0),
                "mark_price": _safe_float(getattr(pos, "current_price", 0.0), 0.0),
                "source": "ai_trading_engine",
            }
        return out

    def _local_positions_from_ai_core(self) -> Dict[str, Dict[str, Any]]:
        core = getattr(self._mc, "ai_core", None)
        rows = getattr(core, "_current_positions", {}) if core else {}
        out: Dict[str, Dict[str, Any]] = {}
        if not isinstance(rows, dict):
            return out
        for symbol, row in rows.items():
            if not isinstance(row, dict):
                continue
            sym = _norm_symbol(symbol)
            if not sym:
                continue
            qty = abs(_safe_float(row.get("size", row.get("pos", 0.0)), 0.0))
            if qty <= 1e-12:
                continue
            side = str(row.get("side") or "").lower()
            if side not in {"long", "short"}:
                side = "long"
            out[sym] = {
                "symbol": sym,
                "side": side,
                "size": qty,
                "entry_price": _safe_float(row.get("entry_price", row.get("avgPx", 0.0)), 0.0),
                "mark_price": _safe_float(
                    row.get("mark_price", row.get("mark_px", row.get("markPx", 0.0))),
                    0.0,
                ),
                "source": "ai_core",
            }
        return out

    @staticmethod
    def _size_delta(a: Dict[str, Any], b: Dict[str, Any]) -> float:
        xa = abs(_safe_float(a.get("size", 0.0), 0.0))
        xb = abs(_safe_float(b.get("size", 0.0), 0.0))
        base = max(xa, xb, 1e-9)
        return abs(xa - xb) / base

    def _build_position_drifts(
        self,
        exchange_positions: Dict[str, Dict[str, Any]],
        ai_engine_positions: Dict[str, Dict[str, Any]],
        ai_core_positions: Dict[str, Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        exchange_syms = set(exchange_positions.keys())
        ai_engine_syms = set(ai_engine_positions.keys())
        ai_core_syms = set(ai_core_positions.keys())
        tracked_local_syms = ai_engine_syms | ai_core_syms

        exchange_only = [
            exchange_positions[s]
            for s in sorted(exchange_syms - tracked_local_syms)
        ]
        local_only = []
        for s in sorted(tracked_local_syms - exchange_syms):
            row = ai_engine_positions.get(s) or ai_core_positions.get(s)
            if row:
                local_only.append(row)

        side_mismatch: List[Dict[str, Any]] = []
        size_mismatch: List[Dict[str, Any]] = []

        for sym in sorted(exchange_syms & tracked_local_syms):
            ex = exchange_positions.get(sym) or {}
            ai = ai_engine_positions.get(sym) or ai_core_positions.get(sym) or {}
            ex_side = str(ex.get("side") or "")
            ai_side = str(ai.get("side") or "")
            if ex_side and ai_side and ex_side != ai_side:
                side_mismatch.append(
                    {
                        "symbol": sym,
                        "exchange_side": ex_side,
                        "local_side": ai_side,
                        "local_source": ai.get("source"),
                    }
                )
            delta = self._size_delta(ex, ai)
            if delta >= 0.18:
                size_mismatch.append(
                    {
                        "symbol": sym,
                        "exchange_size": round(_safe_float(ex.get("size", 0.0), 0.0), 8),
                        "local_size": round(_safe_float(ai.get("size", 0.0), 0.0), 8),
                        "relative_delta": round(float(delta), 4),
                        "local_source": ai.get("source"),
                    }
                )

        return {
            "exchange_only_positions": exchange_only,
            "local_only_positions": local_only,
            "side_mismatch_positions": side_mismatch,
            "size_mismatch_positions": size_mismatch,
        }

    def _build_order_signals(
        self,
        open_orders: List[Dict[str, Any]],
        exchange_positions: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        stale = []
        no_position_symbol = []
        pos_syms = set(exchange_positions.keys())
        for row in open_orders:
            age_sec = row.get("age_sec")
            sym = str(row.get("symbol") or "")
            if age_sec is not None and int(age_sec) >= 300:
                stale.append(row)
            if sym and sym not in pos_syms:
                no_position_symbol.append(row)
        return {
            "open_orders_total": len(open_orders),
            "stale_open_orders": stale[:12],
            "open_orders_without_position": no_position_symbol[:12],
        }

    def _build_repair_hints(
        self,
        drifts: Dict[str, List[Dict[str, Any]]],
        order_signals: Dict[str, Any],
    ) -> List[str]:
        hints: List[str] = []
        if drifts.get("exchange_only_positions"):
            hints.append("发现 exchange_only_positions：建议优先刷新本地持仓视图，并检查是否存在未接管的真实持仓。")
        if drifts.get("local_only_positions"):
            hints.append("发现 local_only_positions：本地仍认为有仓位，但交易所已无对应持仓，建议检查平仓回写/状态清理。")
        if drifts.get("side_mismatch_positions"):
            hints.append("发现 side_mismatch_positions：本地方向与交易所方向不一致，建议暂停该 symbol 新开仓并人工复核。")
        if drifts.get("size_mismatch_positions"):
            hints.append("发现 size_mismatch_positions：本地仓位数量与交易所偏差较大，建议触发持仓重同步。")
        if order_signals.get("stale_open_orders"):
            hints.append("发现 stale_open_orders：存在长时间未完成订单，建议检查是否需要撤单/重提或加入超时保护。")
        if order_signals.get("open_orders_without_position"):
            hints.append("发现 open_orders_without_position：无持仓但仍存在挂单，需确认是否为预期开仓单或孤儿订单。")
        return hints

    async def build_snapshot(self, recent_events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        now = asyncio.get_running_loop().time()
        if self._last_snapshot and (now - float(self._last_run_ts or 0.0)) < self._min_interval_sec:
            return dict(self._last_snapshot)

        out: Dict[str, Any] = {
            "timestamp": _utc_now(),
            "healthy": True,
            "severity": "ok",
            "refresh_actions": {},
            "exchange_errors": {},
        }
        out["refresh_actions"] = await self._refresh_local_views()

        mc = self._mc
        ex = getattr(mc, "execution_exchange", None) or getattr(mc, "okx_exchange", None) or getattr(mc, "exchange", None)
        if not ex:
            out["healthy"] = False
            out["severity"] = "warning"
            out["error"] = "exchange_unavailable"
            self._last_snapshot = dict(out)
            self._last_run_ts = now
            return out

        exchange_positions, pos_err = await self._exchange_positions(ex)
        open_orders, ord_err = await self._exchange_open_orders(ex)
        if pos_err:
            out["exchange_errors"]["positions"] = pos_err
        if ord_err:
            out["exchange_errors"]["open_orders"] = ord_err

        ai_engine_positions = self._local_positions_from_ai_engine()
        ai_core_positions = self._local_positions_from_ai_core()
        drifts = self._build_position_drifts(exchange_positions, ai_engine_positions, ai_core_positions)
        order_signals = self._build_order_signals(open_orders, exchange_positions)
        repair_hints = self._build_repair_hints(drifts, order_signals)

        recent_failures = []
        for e in (recent_events or [])[-12:]:
            if isinstance(e, dict) and e.get("success") is False:
                recent_failures.append(
                    {
                        "ts": e.get("ts"),
                        "op": e.get("op"),
                        "symbol": e.get("symbol"),
                        "error_code": e.get("error_code"),
                        "detail": str(e.get("detail") or "")[:160],
                    }
                )

        drift_count = (
            len(drifts.get("exchange_only_positions", []))
            + len(drifts.get("local_only_positions", []))
            + len(drifts.get("side_mismatch_positions", []))
            + len(drifts.get("size_mismatch_positions", []))
        )
        severe = bool(drifts.get("side_mismatch_positions")) or bool(drifts.get("local_only_positions"))
        if severe:
            out["healthy"] = False
            out["severity"] = "critical"
        elif drift_count or order_signals.get("stale_open_orders"):
            out["healthy"] = False
            out["severity"] = "warning"

        out["summary"] = {
            "exchange_positions": len(exchange_positions),
            "ai_trading_engine_positions": len(ai_engine_positions),
            "ai_core_positions": len(ai_core_positions),
            "drift_total": int(drift_count),
            "recent_failure_events": len(recent_failures),
            "stale_open_orders": len(order_signals.get("stale_open_orders", [])),
        }
        out["position_drifts"] = drifts
        out["order_signals"] = order_signals
        out["repair_hints"] = repair_hints
        out["safe_recovery"] = {
            "automatic_actions_attempted": [
                {
                    "type": "refresh_ai_trading_engine_positions",
                    "status": "applied" if bool(out["refresh_actions"].get("ai_trading_engine_positions_refreshed")) else "skipped",
                },
                {
                    "type": "refresh_ai_core_positions",
                    "status": "applied" if bool(out["refresh_actions"].get("ai_core_positions_refreshed")) else "skipped",
                },
            ],
            "manual_actions_required": [
                {
                    "type": "review_side_mismatch",
                    "symbols": [r.get("symbol") for r in drifts.get("side_mismatch_positions", []) if isinstance(r, dict)][:12],
                },
                {
                    "type": "review_open_orders_without_position",
                    "symbols": [r.get("symbol") for r in order_signals.get("open_orders_without_position", []) if isinstance(r, dict)][:12],
                },
            ],
            "policy": "safe_only_no_cancel_no_force_close",
        }
        out["recent_failure_samples"] = recent_failures[:8]
        out["local_views"] = {
            "exchange_symbols": sorted(exchange_positions.keys())[:32],
            "ai_trading_engine_symbols": sorted(ai_engine_positions.keys())[:32],
            "ai_core_symbols": sorted(ai_core_positions.keys())[:32],
        }

        self._last_snapshot = dict(out)
        self._last_run_ts = now
        return out
