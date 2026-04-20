"""
MarketIntelligenceEngine

Purpose:
- Read-only aggregation layer on top of DataSourceHub / unified collectors
- Produces a normalized, structured "symbol view" and "market state"
- Publishes updates for frontend/TG consumption (via TradeEventHub + EnhancedEventSystem)

Non-goals:
- Do NOT place orders
- Do NOT replace ai_core; instead provide consistent evidence + bias to decision layer
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        if math.isfinite(x):
            return x
    except Exception:
        pass
    return float(default)


def _spread_bps(ticker: Dict[str, Any]) -> Optional[float]:
    last = _safe_float(ticker.get("last") or ticker.get("price") or 0)
    bid = _safe_float(ticker.get("bid") or 0)
    ask = _safe_float(ticker.get("ask") or 0)
    if last <= 0 or bid <= 0 or ask <= 0 or ask < bid:
        return None
    mid = 0.5 * (bid + ask)
    if mid <= 0:
        return None
    return ((ask - bid) / mid) * 10000.0


def _atr_pct_from_klines(klines: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    if not klines or len(klines) < period + 1:
        return None
    highs = [_safe_float(k.get("high"), 0) for k in klines]
    lows = [_safe_float(k.get("low"), 0) for k in klines]
    closes = [_safe_float(k.get("close"), 0) for k in klines]
    if min(closes[-period - 1 :]) <= 0:
        return None
    trs: List[float] = []
    for i in range(-period, 0):
        h, l, c_prev = highs[i], lows[i], closes[i - 1]
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        trs.append(tr)
    atr = sum(trs) / max(1, len(trs))
    last = closes[-1]
    if last <= 0:
        return None
    return atr / last


@dataclass
class SymbolView:
    symbol: str
    timestamp: str
    quality_score: Optional[float] = None
    provenance: str = "unknown"
    schema_version: int = 1
    partial: bool = False
    errors: List[str] = field(default_factory=list)

    price: Optional[float] = None
    spread_bps: Optional[float] = None
    atr_pct_1h: Optional[float] = None
    change_24h: Optional[float] = None

    trend: str = "unknown"  # bullish/bearish/sideways/unknown
    # 仅供参考的“倾向”（由 MarketIntelligenceEngine 基于证据推导/可选 LLM 加强）；
    # 不应被任何模块当作直接下单指令
    action_bias: str = "hold"  # buy/sell/hold
    confidence: Optional[float] = None
    summary: str = ""
    conflicts: List[str] = field(default_factory=list)

    # 供执行/风控/SLTP/前端复用的结构化支撑信息（只读）
    exchange_support: Dict[str, Any] = field(default_factory=dict)
    intel_support: Dict[str, Any] = field(default_factory=dict)
    risk_support: Dict[str, Any] = field(default_factory=dict)
    execution_support: Dict[str, Any] = field(default_factory=dict)

    snapshot: Dict[str, Any] = field(default_factory=dict)
    # optional UI-friendly fields (Chinese display, diff changeset) — additive only
    display_cn: Dict[str, Any] = field(default_factory=dict)
    changeset: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "quality_score": self.quality_score,
            "provenance": self.provenance,
            "schema_version": self.schema_version,
            "partial": self.partial,
            "errors": list(self.errors or []),
            "price": self.price,
            "spread_bps": self.spread_bps,
            "atr_pct_1h": self.atr_pct_1h,
            "change_24h": self.change_24h,
            "trend": self.trend,
            "action_bias": self.action_bias,
            "confidence": self.confidence,
            "summary": self.summary,
            "conflicts": list(self.conflicts),
            "exchange_support": dict(self.exchange_support or {}),
            "intel_support": dict(self.intel_support or {}),
            "risk_support": dict(self.risk_support or {}),
            "execution_support": dict(self.execution_support or {}),
            "display_cn": dict(self.display_cn or {}),
            "changeset": dict(self.changeset or {}),
        }


class MarketIntelligenceEngine:
    def __init__(self, main_controller: Any, config: Optional[Dict[str, Any]] = None) -> None:
        self._mc = main_controller
        self._cfg = dict(config or {})
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ts: Dict[str, float] = {}
        self._rolling: Dict[str, Dict[str, float]] = {}
        self._contract_cache: Dict[str, Dict[str, Any]] = {}
        self._contract_cache_ts: Dict[str, float] = {}
        self._last_emitted: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl_sec = float(self._cfg.get("cache_ttl_sec", 20) or 20)
        self._push_interval_sec = float(self._cfg.get("push_interval_sec", 15) or 15)
        self._watch_symbols: List[str] = list(self._cfg.get("watch_symbols") or [])
        self._contract_cache_ttl_sec = float(self._cfg.get("contract_cache_ttl_sec", 3600) or 3600)
        # market state aggregation stability/perf guards
        self._market_state_cache: Dict[str, Any] = {}
        self._market_state_cache_ts: float = 0.0
        self._market_state_cache_ttl_sec: float = float(self._cfg.get("market_state_cache_ttl_sec", 2.0) or 2.0)
        self._market_state_concurrency: int = int(self._cfg.get("market_state_concurrency", 4) or 4)
        # Per-symbol timeout for get_market_state fan-out.
        # 1.6s is often too tight when unified_snapshot has its own ~2.5s budget (plus scheduling overhead),
        # which causes systemic timeouts and "snapshot_timeout" degradations.
        self._market_state_symbol_timeout_s: float = float(self._cfg.get("market_state_symbol_timeout_s", 3.0) or 3.0)
        self._market_state_fetch_limit: int = int(self._cfg.get("market_state_fetch_limit", 4) or 4)
        self._market_state_debug_perf: bool = bool(self._cfg.get("market_state_debug_perf", True))
        # upstream fetch timeouts (avoid control-plane hangs)
        self._snapshot_timeout_s: float = float(self._cfg.get("snapshot_timeout_s", 2.2) or 2.2)
        self._klines_timeout_s: float = float(self._cfg.get("klines_timeout_s", 1.2) or 1.2)
        self._snapshot_timeout_min_s: float = float(self._cfg.get("snapshot_timeout_min_s", 1.6) or 1.6)
        self._snapshot_timeout_max_s: float = float(self._cfg.get("snapshot_timeout_max_s", 4.2) or 4.2)
        self._klines_timeout_min_s: float = float(self._cfg.get("klines_timeout_min_s", 0.8) or 0.8)
        self._klines_timeout_max_s: float = float(self._cfg.get("klines_timeout_max_s", 2.6) or 2.6)
        self._snapshot_timeout_dynamic_s: float = float(self._snapshot_timeout_s)
        self._klines_timeout_dynamic_s: float = float(self._klines_timeout_s)
        self._timeout_stats: Dict[str, Dict[str, float]] = {
            "snapshot": {"ok_streak": 0.0, "timeout_streak": 0.0},
            "klines": {"ok_streak": 0.0, "timeout_streak": 0.0},
        }

        # fee model (defaults align with backtest/research defaults in repo)
        self._fee_rate_taker = float(self._cfg.get("fee_rate_taker", 0.0005) or 0.0005)
        self._fee_rate_maker = float(self._cfg.get("fee_rate_maker", 0.0002) or 0.0002)
        self._schema_version = int(self._cfg.get("schema_version", 1) or 1)

    def _fmt(self, v: Any, *, nd: int = 4) -> Optional[str]:
        try:
            if v is None:
                return None
            x = float(v)
            if not math.isfinite(x):
                return None
            return f"{x:.{int(max(0, nd))}f}"
        except Exception:
            return None

    def _compute_changeset(self, key: str, curr: Dict[str, Any]) -> Dict[str, Any]:
        """
        Best-effort shallow diff for UI/notifications. Keeps payload small and stable.
        """
        prev = self._last_emitted.get(key) or {}
        added: List[str] = []
        removed: List[str] = []
        changed: List[str] = []
        for k in curr.keys():
            if k not in prev:
                added.append(k)
        for k in prev.keys():
            if k not in curr:
                removed.append(k)
        # only track a curated set of high-signal keys to avoid noisy diffs
        watch = [
            "price",
            "spread_bps",
            "atr_pct_1h",
            "change_24h",
            "trend",
            "action_bias",
            "confidence",
            "quality_score",
            "partial",
        ]
        for k in watch:
            if k in prev and k in curr and prev.get(k) != curr.get(k):
                changed.append(k)
        # nested key checks (bounded)
        try:
            pc = ((prev.get("execution_support") or {}).get("costs") or {}) if isinstance(prev, dict) else {}
            cc = ((curr.get("execution_support") or {}).get("costs") or {}) if isinstance(curr, dict) else {}
            for nk in ("estimated_cost_bps_small_market_order", "funding_rate"):
                if nk in pc and nk in cc and pc.get(nk) != cc.get(nk):
                    changed.append(f"execution_support.costs.{nk}")
        except Exception:
            pass
        out = {
            "added": sorted(set(added)),
            "removed": sorted(set(removed)),
            "changed": sorted(set(changed)),
        }
        self._last_emitted[key] = dict(curr)
        return out

    def _build_display_cn(self, d: Dict[str, Any]) -> Dict[str, Any]:
        ex = d.get("exchange_support") or {}
        ob = (ex.get("order_book") or {}) if isinstance(ex, dict) else {}
        contract = (ex.get("contract") or {}) if isinstance(ex, dict) else {}
        es = d.get("execution_support") or {}
        costs = (es.get("costs") or {}) if isinstance(es, dict) else {}
        anomalies = es.get("anomalies") or []
        warnings = es.get("warnings") or []

        px = d.get("price")
        sp = d.get("spread_bps")
        cost_bps = costs.get("estimated_cost_bps_small_market_order")
        fr = costs.get("funding_rate")
        fr_cost = costs.get("funding_cost_usdt_per_10k_notional_per_period")

        # succinct lines for TG / notifications
        lines: List[str] = []
        lines.append(f"标的: {d.get('symbol')}")
        if px is not None:
            lines.append(f"价格: {self._fmt(px, nd=6)}")
        lines.append(f"趋势: {d.get('trend')}")
        lines.append(f"倾向: {d.get('action_bias')} 置信: {self._fmt(d.get('confidence'), nd=2)}")
        lines.append(f"质量: {self._fmt(d.get('quality_score'), nd=2)} 点差(bps): {self._fmt(sp, nd=1)}")
        if cost_bps is not None:
            lines.append(f"预估执行成本(bps): {self._fmt(cost_bps, nd=2)}")
        if fr is not None:
            lines.append(f"资金费率: {self._fmt(fr, nd=6)} 费成本($10k/周期): {self._fmt(fr_cost, nd=4)}")
        if anomalies:
            lines.append(f"异常: {', '.join([str(x) for x in anomalies][:4])}")
        if warnings:
            lines.append(f"提示: {', '.join([str(x) for x in warnings][:4])}")

        # contract sizing hints (if available)
        cs = {}
        for k in ("minSz", "lotSz", "ctVal", "ctValCcy", "maxSz"):
            if k in contract and contract.get(k) not in (None, "", 0, 0.0):
                cs[k] = contract.get(k)

        return {
            "title": f"统一行情情报: {d.get('symbol')}",
            "lines": lines,
            "contract_hints": cs,
            "bid": ob.get("best_bid"),
            "ask": ob.get("best_ask"),
        }

    def _hub(self) -> Any:
        return getattr(self._mc, "data_source_hub", None) if self._mc else None

    def _exchange(self) -> Any:
        mc = self._mc
        if not mc:
            return None
        return getattr(mc, "okx_exchange", None) or getattr(mc, "exchange", None)

    def _llm(self) -> Any:
        mc = self._mc
        if not mc:
            return None
        return getattr(mc, "llm_integration", None) or getattr(mc, "large_model_interface", None)

    def _trade_hub(self) -> Any:
        return getattr(self._mc, "trade_event_hub", None) if self._mc else None

    def _now(self) -> float:
        return time.time()

    def _record_timeout_result(self, kind: str, timeout_hit: bool) -> None:
        try:
            stats = self._timeout_stats.get(kind)
            if not stats:
                return
            if timeout_hit:
                stats["timeout_streak"] = float(stats.get("timeout_streak", 0.0)) + 1.0
                stats["ok_streak"] = 0.0
            else:
                stats["ok_streak"] = float(stats.get("ok_streak", 0.0)) + 1.0
                stats["timeout_streak"] = 0.0

            if kind == "snapshot":
                cur = float(self._snapshot_timeout_dynamic_s)
                min_s = float(self._snapshot_timeout_min_s)
                max_s = float(self._snapshot_timeout_max_s)
            else:
                cur = float(self._klines_timeout_dynamic_s)
                min_s = float(self._klines_timeout_min_s)
                max_s = float(self._klines_timeout_max_s)

            if timeout_hit:
                # 快速扩容，优先保证可用性
                cur = min(max_s, cur * 1.2 + 0.05)
            elif stats.get("ok_streak", 0.0) >= 3:
                # 连续稳定后缓慢回落，避免抖动
                cur = max(min_s, cur * 0.92)

            if kind == "snapshot":
                self._snapshot_timeout_dynamic_s = float(cur)
            else:
                self._klines_timeout_dynamic_s = float(cur)
        except Exception:
            return

    async def initialize(self) -> bool:
        return True

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._push_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
        self._task = None

    async def _push_loop(self) -> None:
        while self._running:
            try:
                syms = list(self._watch_symbols)
                if not syms:
                    hub = self._hub()
                    if hub and hasattr(hub, "get_symbols"):
                        try:
                            syms = (await hub.get_symbols())[:6]
                        except Exception:
                            syms = ["BTC/USDT", "ETH/USDT"]
                    else:
                        syms = ["BTC/USDT", "ETH/USDT"]

                for s in syms:
                    try:
                        view = await self.get_symbol_view(s, include_snapshot=False)
                        await self._publish_symbol_view(view)
                    except Exception:
                        continue
                await asyncio.sleep(self._push_interval_sec)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("MarketIntelligence push loop error: %s", e)
                await asyncio.sleep(3)

    async def _publish_symbol_view(self, view: SymbolView) -> None:
        th = self._trade_hub()
        if not th:
            return
        if hasattr(th, "publish_market_update"):
            # Build a concise CN message, but keep full payload in ring buffer.
            tg = None
            try:
                dc = view.display_cn or {}
                lines = dc.get("lines") if isinstance(dc, dict) else None
                if isinstance(lines, list) and lines:
                    tg = "🧠 " + "\n".join([str(x) for x in lines[:8]])
            except Exception:
                tg = None
            await th.publish_market_update(
                kind="market.symbol_view",
                payload=view.to_dict(),
                tg_message=tg
                or f"🧠 行情汇总 {view.symbol}\n趋势={view.trend} 倾向={view.action_bias} 置信={view.confidence}\n质量={view.quality_score} spread={view.spread_bps}\n{view.summary[:160]}",
            )

    async def ingest_scanner_opportunity(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        接收「机会扫描」初筛后的机会提示，做二次分析/补充证据，然后：
        - 发布到 market.update（前端/TG 可见）
        - 转发给 ai_core 作为决策提示（不等于下单指令）
        """
        raw = dict(payload or {})
        sym = str(raw.get("symbol") or "").strip()
        if not sym:
            return {"ok": False, "message": "missing_symbol"}

        # 二次分析：复用 MI 的统一行情视图，补充质量分/趋势/倾向/执行 guard 等
        view = None
        try:
            view = await self.get_symbol_view(sym, include_snapshot=False)
        except Exception:
            view = None

        mi_block: Dict[str, Any] = {}
        if view:
            vd = view.to_dict()
            mi_block = {
                "mi_timestamp": vd.get("timestamp"),
                "mi_quality_score": vd.get("quality_score"),
                "mi_trend": vd.get("trend"),
                "mi_action_bias": vd.get("action_bias"),
                "mi_confidence": vd.get("confidence"),
                "mi_summary": vd.get("summary"),
                "mi_execution_guards": (vd.get("execution_support") or {}).get("guards") if isinstance(vd.get("execution_support"), dict) else {},
            }

        enriched = {
            **raw,
            "enriched_at": _utc_iso(),
            "analysis_layer": "market_intelligence",
            **mi_block,
        }

        # 对外推送（前端/电报）
        try:
            th = self._trade_hub()
            if th and hasattr(th, "publish_market_update"):
                direction = str(enriched.get("direction") or "")
                opp_t = str(enriched.get("opportunity_type") or "")
                q = enriched.get("mi_quality_score")
                trend = enriched.get("mi_trend")
                tg = (
                    f"📡 扫描机会（二次分析后）\n"
                    f"{sym} 方向={direction} 类型={opp_t}\n"
                    f"趋势={trend} 质量={q}\n"
                    f"{str(enriched.get('mi_summary') or '')[:160]}"
                )
                await th.publish_market_update(kind="scanner.opportunity", payload=enriched, tg_message=tg)
        except Exception:
            pass

        # 转发给 ai_core（只做提示，不开仓）
        try:
            core = getattr(self._mc, "ai_core", None) if self._mc else None
            if core and hasattr(core, "ingest_scanner_opportunity"):
                core.ingest_scanner_opportunity(enriched)
        except Exception:
            pass

        return {"ok": True, "symbol": sym, "enriched": enriched}

    async def get_market_state(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        聚合市场状态（多 symbol 汇总）。用于前端面板/风控开关/日报。
        """
        started_at = time.time()
        syms = symbols or list(self._watch_symbols)
        if not syms:
            hub = self._hub()
            if hub and hasattr(hub, "get_symbols"):
                try:
                    syms = (await hub.get_symbols())[:10]
                except Exception:
                    syms = ["BTC/USDT", "ETH/USDT"]
            else:
                syms = ["BTC/USDT", "ETH/USDT"]

        # quick cache to prevent aggregation storms
        try:
            now = self._now()
            if self._market_state_cache and (now - float(self._market_state_cache_ts or 0.0)) < self._market_state_cache_ttl_sec:
                out = dict(self._market_state_cache)
                out["cached"] = True
                return out
        except Exception:
            pass

        # Prefer cached symbol views to keep control-plane stable/fast.
        views: List[Dict[str, Any]] = []
        cached_by_symbol: Dict[str, Dict[str, Any]] = {}
        try:
            for s in [str(x) for x in (syms or []) if x][:20]:
                cached = self.get_cached_symbol_view(s)
                if cached:
                    views.append(cached)
                    key = str(cached.get("symbol") or s).upper()
                    cached_by_symbol[key] = cached
        except Exception:
            pass
        bull = bear = side = unknown = 0
        avg_q = []
        max_spread = 0.0
        high_risk = 0

        sem = asyncio.Semaphore(max(1, int(self._market_state_concurrency)))
        perf_rows: List[Dict[str, Any]] = []

        async def _one(sym: str) -> Optional[Dict[str, Any]]:
            t0 = time.time()
            try:
                cached = cached_by_symbol.get(str(sym).upper())
                if cached:
                    perf_rows.append(
                        {"symbol": sym, "ok": True, "ms": int((time.time() - t0) * 1000), "source": "cache"}
                    )
                    return cached
                async with sem:
                    v = await asyncio.wait_for(
                        self.get_symbol_view(sym, include_snapshot=False, prefer_fast_only=True),
                        timeout=max(0.5, min(float(self._market_state_symbol_timeout_s), 3.2)),
                    )
                d = v.to_dict()
                return d
            except asyncio.TimeoutError:
                perf_rows.append({"symbol": sym, "ok": False, "error": "timeout", "ms": int((time.time() - t0) * 1000)})
                # Return a minimal degraded row so market_state is still informative.
                return {
                    "symbol": sym,
                    "timestamp": _utc_iso(),
                    "quality_score": 0.0,
                    "provenance": "degraded",
                    "schema_version": self._schema_version,
                    "partial": True,
                    "errors": ["snapshot_timeout"],
                    "price": None,
                    "spread_bps": None,
                    "atr_pct_1h": None,
                    "change_24h": 0.0,
                    "trend": "unknown",
                    "action_bias": "hold",
                    "confidence": None,
                    "summary": "",
                    "conflicts": [],
                    "exchange_support": {},
                    "intel_support": {},
                    "risk_support": {},
                    "execution_support": {},
                    "display_cn": {},
                    "changeset": {},
                }
            except Exception as e:
                perf_rows.append(
                    {"symbol": sym, "ok": False, "error": type(e).__name__, "ms": int((time.time() - t0) * 1000)}
                )
                return {
                    "symbol": sym,
                    "timestamp": _utc_iso(),
                    "quality_score": 0.0,
                    "provenance": "degraded",
                    "schema_version": self._schema_version,
                    "partial": True,
                    "errors": [f"symbol_view_failed:{type(e).__name__}"],
                    "price": None,
                    "spread_bps": None,
                    "atr_pct_1h": None,
                    "change_24h": 0.0,
                    "trend": "unknown",
                    "action_bias": "hold",
                    "confidence": None,
                    "summary": "",
                    "conflicts": [],
                    "exchange_support": {},
                    "intel_support": {},
                    "risk_support": {},
                    "execution_support": {},
                    "display_cn": {},
                    "changeset": {},
                }
            finally:
                # only record success timing if no error row exists
                if not any(r.get("symbol") == sym for r in perf_rows):
                    perf_rows.append({"symbol": sym, "ok": True, "ms": int((time.time() - t0) * 1000)})

        # Only fetch symbols that are not already cached, and keep this bounded.
        syms_all = [str(s) for s in (syms or []) if s][:20]
        syms_missing = [s for s in syms_all if str(s).upper() not in cached_by_symbol]
        syms_use = syms_missing[: max(1, min(int(self._market_state_fetch_limit), 8))]
        results = await asyncio.gather(*[_one(s) for s in syms_use], return_exceptions=False)
        # Merge fetched (prefer) + cached (fallback).
        merged: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for d in results:
            if not isinstance(d, dict):
                continue
            k = str(d.get("symbol") or "").upper()
            if k:
                seen.add(k)
            merged.append(d)
        for d in views:
            if not isinstance(d, dict):
                continue
            k = str(d.get("symbol") or "").upper()
            if k and k in seen:
                continue
            merged.append(d)
        views = merged

        for d in views:
            tr = str(d.get("trend") or "unknown")
            if tr == "bullish":
                bull += 1
            elif tr == "bearish":
                bear += 1
            elif tr == "sideways":
                side += 1
            else:
                unknown += 1
            q = d.get("quality_score")
            if q is not None:
                try:
                    avg_q.append(float(q))
                except Exception:
                    pass
            sp = d.get("spread_bps")
            if sp is not None:
                try:
                    max_spread = max(max_spread, float(sp))
                except Exception:
                    pass
            try:
                lp = (d.get("risk_support") or {}).get("liquidation_proxy") or {}
                high_risk += int(lp.get("high_risk_positions") or 0)
            except Exception:
                pass

        attempted = len(syms_use) + len(cached_by_symbol)
        trend = "mixed"
        total = max(1, len(views))
        if bull > total * 0.6:
            trend = "bullish"
        elif bear > total * 0.6:
            trend = "bearish"
        elif side > total * 0.6:
            trend = "sideways"
        out = {
            "timestamp": _utc_iso(),
            "symbols_considered": len(views),
            "symbols_attempted": attempted,
            "symbols_failed": max(0, attempted - len(views)),
            "trend": trend,
            "counts": {"bullish": bull, "bearish": bear, "sideways": side, "unknown": unknown},
            "avg_quality_score": (sum(avg_q) / len(avg_q)) if avg_q else None,
            "max_spread_bps": max_spread if max_spread > 0 else None,
            "high_risk_positions": high_risk,
            "symbol_views": views,
            "cached": False,
        }
        if self._market_state_debug_perf:
            out["perf"] = {
                "total_ms": int((time.time() - started_at) * 1000),
                "concurrency": int(self._market_state_concurrency),
                "symbol_timeout_s": float(self._market_state_symbol_timeout_s),
                "per_symbol_top": sorted(perf_rows, key=lambda r: int(r.get("ms") or 0), reverse=True)[:8],
            }

        try:
            self._market_state_cache = dict(out)
            self._market_state_cache_ts = float(self._now())
        except Exception:
            pass
        return out

    def get_cached_market_state(self) -> Dict[str, Any]:
        return dict(self._market_state_cache or {})

    async def get_symbol_view(
        self,
        symbol: str,
        *,
        include_snapshot: bool = True,
        prefer_fast_only: bool = False,
    ) -> SymbolView:
        sym = str(symbol or "").strip()
        ts = _utc_iso()
        cache_key = sym.upper()
        now = self._now()
        if cache_key in self._cache and (now - self._cache_ts.get(cache_key, 0)) < self._cache_ttl_sec:
            cached = self._cache[cache_key]
            view = SymbolView(**cached["view"])
            if include_snapshot:
                view.snapshot = cached.get("snapshot", {})
            else:
                view.snapshot = {}
            return view

        hub = self._hub()
        snapshot: Dict[str, Any] = {}
        errors: List[str] = []
        partial = False

        # Fast path (control-plane friendly):
        # When include_snapshot=False (used by /market/state fan-out and default /market/symbol view),
        # avoid blocking on unified_snapshot which can be near its budget under proxy/collector load.
        # Prefer exchange.get_ticker() (WS fast-path in OKXExchange) to keep endpoints responsive.
        if not bool(include_snapshot):
            ex = self._exchange()
            if ex is not None and hasattr(ex, "get_ticker"):
                try:
                    t = await asyncio.wait_for(ex.get_ticker(sym), timeout=0.9)
                    if isinstance(t, dict) and float(t.get("last") or t.get("price") or 0.0) > 0:
                        snapshot = {
                            "symbol": sym,
                            "timestamp": datetime.now().isoformat(),
                            "渠道A_交易所实时执行数据": {
                                "ticker": {
                                    "last": float(t.get("last") or t.get("price") or 0.0),
                                    "bid": float(t.get("bid") or 0.0),
                                    "ask": float(t.get("ask") or 0.0),
                                    "high_24h": float(t.get("high") or t.get("high_24h") or 0.0),
                                    "low_24h": float(t.get("low") or t.get("low_24h") or 0.0),
                                    "volume_24h": float(t.get("volume") or t.get("volume_24h") or 0.0),
                                    "change_24h": float(t.get("change_24h") or t.get("change") or 0.0),
                                },
                                "collector": {
                                    "enabled": ["ticker"],
                                    "health": {"ticker": "ok"},
                                    "errors": [],
                                    "snapshot_timeout_sec": None,
                                },
                            },
                            "数据来源状态": {"provenance": "fastpath"},
                        }
                        errors.append("fastpath_ticker_only")
                        partial = True
                except Exception as e:
                    errors.append(f"fastpath_ticker_failed:{type(e).__name__}")
                    partial = True
        providers = list(self._cfg.get("providers") or ["unified_snapshot"])
        if bool(prefer_fast_only) and snapshot:
            # Control-plane fast mode: market/state fan-out prefers bounded ticker-only data
            # over potentially slow unified snapshot fetches.
            providers = []
        if "unified_snapshot" in providers and hub and hasattr(hub, "get_unified_snapshot"):
            try:
                # DataSourceHub.get_unified_snapshot uses its own overall budget (default 2.5s).
                # If we set a smaller outer timeout here, we will prematurely cancel the snapshot and
                # consistently degrade to snapshot_timeout. Add a small slack for scheduling/JSON work.
                snap_timeout = max(0.8, min(6.0, float(self._snapshot_timeout_dynamic_s) + 0.8))
                if not snapshot:
                    snapshot = await asyncio.wait_for(hub.get_unified_snapshot(sym), timeout=snap_timeout)
                    self._record_timeout_result("snapshot", timeout_hit=False)
            except Exception as e:
                errors.append(f"snapshot_fetch_failed:{type(e).__name__}")
                if not snapshot:
                    snapshot = {}
                partial = True
                self._record_timeout_result("snapshot", timeout_hit=isinstance(e, asyncio.TimeoutError))
        else:
            if bool(prefer_fast_only):
                errors.append("snapshot_skipped_fast_mode")
                partial = True
            else:
                errors.append("snapshot_provider_missing")
                partial = True

        # Pull core fields (统一快照字段)
        exch = (snapshot.get("渠道A_交易所实时执行数据") or {}) if isinstance(snapshot, dict) else {}
        intel = (snapshot.get("渠道B_链上新闻舆情数据") or {}) if isinstance(snapshot, dict) else {}
        ticker = (exch.get("ticker") or {}) if isinstance(exch, dict) else {}
        order_book = (exch.get("order_book") or {}) if isinstance(exch, dict) else {}
        positions = (exch.get("positions") or []) if isinstance(exch, dict) else []
        open_orders = (exch.get("open_orders") or []) if isinstance(exch, dict) else []
        funding_rate = exch.get("funding_rate") if isinstance(exch, dict) else None
        open_interest = (exch.get("open_interest") or {}) if isinstance(exch, dict) else {}
        liq_proxy = (exch.get("liquidation_proxy") or {}) if isinstance(exch, dict) else {}
        intel_ai = {}
        analysis = {}
        q = (snapshot.get("数据质量评估") or {}) if isinstance(snapshot, dict) else {}
        qa = (snapshot.get("数据质量与作用评分") or {}) if isinstance(snapshot, dict) else {}
        alerts = snapshot.get("监控告警") if isinstance(snapshot, dict) else None
        prov = (snapshot.get("数据来源状态") or {}) if isinstance(snapshot, dict) else {}

        quality_score: Optional[float] = None
        if isinstance(q, dict) and q.get("score") is not None:
            quality_score = _safe_float(q.get("score"), default=0.0)

        price = _safe_float(ticker.get("price") or ticker.get("last") or ticker.get("close") or 0, 0.0)
        sp = _spread_bps(ticker) if isinstance(ticker, dict) else None
        change_24h = _safe_float(ticker.get("change24h") or ticker.get("change") or 0, 0.0)
        # 1h ATR proxy from hub klines if present
        kl = (exch.get("klines_1h") or []) if isinstance(exch, dict) else []
        # NOTE:
        # Do NOT block symbol_view on an extra klines call when unified_snapshot already consumed most of
        # the control-plane budget (module_control_api puts a 3s upper bound on the whole call).
        # If klines are missing from snapshot, we degrade gracefully (atr_pct_1h=None) instead of timing out.
        if not kl:
            if hub and hasattr(hub, "get_klines"):
                errors.append("klines_missing_in_snapshot")
            partial = True
        atrp = _atr_pct_from_klines(kl, 14)

        # Normalize trend/bias/confidence
        # Normalize trend/bias/confidence from evidence (collector-only snapshot).
        # Prefer third_party sentiment -> onchain sentiment -> fall back to unknown.
        tp_sent = (intel.get("sentiment") or {}) if isinstance(intel, dict) else {}
        tp_trend = tp_sent.get("trend") if isinstance(tp_sent, dict) else None
        oc_sent = ((intel.get("onchain") or {}).get("sentiment")) if isinstance(intel, dict) else None
        oc_trend = (oc_sent.get("sentiment") or oc_sent.get("trend")) if isinstance(oc_sent, dict) else None
        trend = str(tp_trend or oc_trend or "unknown").lower()
        if trend in ("bull", "bullish", "up"):
            trend_n = "bullish"
        elif trend in ("bear", "bearish", "down"):
            trend_n = "bearish"
        elif trend in ("sideways", "range", "neutral"):
            trend_n = "sideways"
        else:
            trend_n = "unknown"

        conf = None
        try:
            if isinstance(tp_sent, dict) and tp_sent.get("confidence") is not None:
                conf = tp_sent.get("confidence")
            elif isinstance(oc_sent, dict) and oc_sent.get("strength") is not None:
                conf = oc_sent.get("strength")
        except Exception:
            conf = None
        conf_f = _safe_float(conf, default=0.0) if conf is not None else None

        # Derive bias from trend + confidence (never treated as an order signal).
        action_bias = "hold"
        try:
            c0 = float(conf_f) if conf_f is not None else 0.0
            if trend_n == "bullish" and c0 >= 0.55:
                action_bias = "buy"
            elif trend_n == "bearish" and c0 >= 0.55:
                action_bias = "sell"
        except Exception:
            action_bias = "hold"
        if action_bias in ("buy", "long"):
            action_bias = "buy"
        elif action_bias in ("sell", "short"):
            action_bias = "sell"
        else:
            action_bias = "hold"

        conflicts: List[str] = []
        # simple conflict detection: trend vs bias mismatch
        if trend_n == "bullish" and action_bias == "sell":
            conflicts.append("trend_bullish_but_bias_sell")
        if trend_n == "bearish" and action_bias == "buy":
            conflicts.append("trend_bearish_but_bias_buy")

        # Exchange support (execution-relevant microstructure)
        ob_bids = []
        ob_asks = []
        try:
            ob_bids = order_book.get("bids") if isinstance(order_book, dict) else []
            ob_asks = order_book.get("asks") if isinstance(order_book, dict) else []
        except Exception:
            ob_bids, ob_asks = [], []
        best_bid = _safe_float(ob_bids[0][0], 0.0) if ob_bids else 0.0
        best_ask = _safe_float(ob_asks[0][0], 0.0) if ob_asks else 0.0
        bid_vol_5 = sum(_safe_float(x[1], 0.0) for x in (ob_bids[:5] if isinstance(ob_bids, list) else []))
        ask_vol_5 = sum(_safe_float(x[1], 0.0) for x in (ob_asks[:5] if isinstance(ob_asks, list) else []))
        depth_imb = None
        if (bid_vol_5 + ask_vol_5) > 1e-12:
            depth_imb = (bid_vol_5 - ask_vol_5) / (bid_vol_5 + ask_vol_5)

        exchange_support = {
            "ticker": {
                "last": price if price > 0 else None,
                "bid": _safe_float(ticker.get("bid") or 0, 0.0) if isinstance(ticker, dict) else None,
                "ask": _safe_float(ticker.get("ask") or 0, 0.0) if isinstance(ticker, dict) else None,
                "high_24h": _safe_float(ticker.get("high") or 0, 0.0) if isinstance(ticker, dict) else None,
                "low_24h": _safe_float(ticker.get("low") or 0, 0.0) if isinstance(ticker, dict) else None,
                "volume_24h": _safe_float(ticker.get("volume") or 0, 0.0) if isinstance(ticker, dict) else None,
                "change_24h": float(change_24h),
            },
            "order_book": {
                "best_bid": best_bid if best_bid > 0 else None,
                "best_ask": best_ask if best_ask > 0 else None,
                "spread_bps": float(sp) if sp is not None else None,
                "bid_volume_top5": float(bid_vol_5),
                "ask_volume_top5": float(ask_vol_5),
                "depth_imbalance_top5": float(depth_imb) if depth_imb is not None else None,
            },
            "funding_rate": _safe_float(funding_rate, default=0.0) if funding_rate is not None else None,
            "open_interest": open_interest if isinstance(open_interest, dict) else {},
            "positions_count": len(positions) if isinstance(positions, list) else None,
            "open_orders_count": len(open_orders) if isinstance(open_orders, list) else None,
        }

        # Contract specs (minSz/lotSz/ctVal...) for execution sizing alignment
        contract: Dict[str, Any] = {}
        try:
            ex = self._exchange()
            if ex and hasattr(ex, "get_swap_symbol_info"):
                ck = cache_key
                now2 = now
                if (
                    ck in self._contract_cache
                    and (now2 - self._contract_cache_ts.get(ck, 0)) < self._contract_cache_ttl_sec
                ):
                    contract = dict(self._contract_cache.get(ck) or {})
                else:
                    info = await ex.get_swap_symbol_info(sym)
                    if isinstance(info, dict) and info:
                        contract = dict(info)
                        self._contract_cache[ck] = dict(contract)
                        self._contract_cache_ts[ck] = now2
        except Exception:
            contract = {}
            errors.append("contract_info_failed")
        exchange_support["contract"] = contract

        # Position/open-order match for this symbol (more execution/S1/SLTP friendly)
        base = sym.split("/")[0].upper() if "/" in sym else sym.upper()
        matched_pos: List[Dict[str, Any]] = []
        matched_orders: List[Dict[str, Any]] = []
        try:
            for p in (positions or []):
                if not isinstance(p, dict):
                    continue
                iid = str(p.get("instId") or p.get("symbol") or "").upper()
                if base and base in iid:
                    matched_pos.append(p)
        except Exception:
            matched_pos = []
        try:
            for o in (open_orders or []):
                if not isinstance(o, dict):
                    continue
                osym = str(o.get("instId") or o.get("symbol") or "").upper()
                if base and base in osym:
                    matched_orders.append(o)
        except Exception:
            matched_orders = []

        # Summarize net exposure + liquidation distance proxy
        pos_summary: Dict[str, Any] = {"positions": [], "net": {"long": 0.0, "short": 0.0}}
        for p in matched_pos[:6]:
            try:
                side = str(p.get("side") or "").lower()
                sz = _safe_float(p.get("size") or p.get("pos") or 0.0, 0.0)
                entry_px = _safe_float(p.get("entry_price") or p.get("avgPx") or p.get("avgPx") or 0.0, 0.0)
                mark_px = _safe_float(p.get("mark_price") or p.get("markPx") or p.get("mark_px") or 0.0, 0.0)
                liq_px = _safe_float(p.get("liquidation_price") or p.get("liqPx") or 0.0, 0.0)
                dist_pct = None
                if liq_px > 0 and mark_px > 0:
                    dist_pct = abs(mark_px - liq_px) / max(mark_px, 1e-9)
                pos_summary["positions"].append(
                    {
                        "instId": p.get("instId"),
                        "symbol": p.get("symbol"),
                        "side": side,
                        "size": abs(float(sz)),
                        "entry_price": entry_px if entry_px > 0 else None,
                        "mark_price": mark_px if mark_px > 0 else None,
                        "liquidation_price": liq_px if liq_px > 0 else None,
                        "liq_distance_pct": float(dist_pct) if dist_pct is not None else None,
                        "unrealized_pnl": p.get("unrealized_pnl"),
                        "unrealized_pnl_ratio": p.get("unrealized_pnl_ratio"),
                        "notional_value": p.get("notional_value"),
                        "leverage": p.get("leverage"),
                    }
                )
                if side == "long":
                    pos_summary["net"]["long"] += abs(float(sz))
                elif side == "short":
                    pos_summary["net"]["short"] += abs(float(sz))
            except Exception:
                continue

        order_summary: Dict[str, Any] = {"open_orders": []}
        for o in matched_orders[:8]:
            try:
                order_summary["open_orders"].append(
                    {
                        "id": o.get("id") or o.get("ordId"),
                        "instId": o.get("instId") or o.get("symbol"),
                        "side": o.get("side"),
                        "type": o.get("type") or o.get("ordType"),
                        "price": o.get("price") or o.get("px"),
                        "amount": o.get("amount") or o.get("sz"),
                        "status": o.get("status") or o.get("state"),
                        "timestamp": o.get("timestamp") or o.get("cTime"),
                    }
                )
            except Exception:
                continue

        exchange_support["position_summary"] = pos_summary
        exchange_support["open_order_summary"] = order_summary

        # Intel support (onchain/news/sentiment summaries)
        intel_support = {
            "health": (intel.get("health") or {}) if isinstance(intel, dict) else {},
            "onchain": {
                "sentiment": ((intel.get("onchain") or {}).get("sentiment")) if isinstance(intel, dict) else None,
                "flows_samples": len(((intel.get("onchain") or {}).get("flows")) or []) if isinstance(intel, dict) else None,
                "whales_samples": len(((intel.get("onchain") or {}).get("whales")) or []) if isinstance(intel, dict) else None,
            },
            "sentiment": (intel.get("sentiment") or {}) if isinstance(intel, dict) else {},
            "news": (intel.get("news") or {}) if isinstance(intel, dict) else {},
        }

        # Risk support (liquidation proxy + quality gates)
        risk_support = {
            "liquidation_proxy": liq_proxy if isinstance(liq_proxy, dict) else {},
            "quality": q if isinstance(q, dict) else {},
            "quality_advisor": qa if isinstance(qa, dict) else {},
            "alerts": alerts if isinstance(alerts, list) else [],
        }

        provenance = str(prov.get("provenance") or "unknown") if isinstance(prov, dict) else "unknown"
        summary = ""
        try:
            if isinstance(tp_sent, dict):
                summary = str(tp_sent.get("summary") or tp_sent.get("details", {}).get("summary") or "")
        except Exception:
            summary = ""
        if not summary:
            try:
                if isinstance(oc_sent, dict):
                    summary = str(oc_sent.get("report") or oc_sent.get("summary") or "")
            except Exception:
                summary = ""

        # Execution/SLTP support suggestions (read-only)
        # Suggest tighter guards when quality degraded or spread wide.
        max_spread_bps = 35.0
        if sp is not None:
            if sp > 80:
                max_spread_bps = 25.0
            elif sp > 45:
                max_spread_bps = 30.0
        min_rr = 1.15
        if atrp is not None and atrp > 0:
            # higher vol: allow slightly lower RR, but not too low
            if atrp >= 0.02:
                min_rr = 1.05
            elif atrp <= 0.005:
                min_rr = 1.25
        min_quality = 0.55
        if quality_score is not None and quality_score < 0.5:
            min_quality = 0.70

        # Cost estimates / warnings (execution-facing)
        costs: Dict[str, Any] = {}
        if sp is not None:
            costs["spread_bps"] = float(sp)
            costs["expected_slippage_bps_small_market_order"] = float(sp) / 2.0
        if depth_imb is not None:
            costs["depth_imbalance_top5"] = float(depth_imb)
        # crude liquidity score: more top5 volume -> better
        liq_score = None
        try:
            liq_score = math.log10(max(1e-9, bid_vol_5 + ask_vol_5))
        except Exception:
            liq_score = None
        costs["liquidity_score_top5"] = float(liq_score) if liq_score is not None else None

        # Fee model + cost in bps (per side independent, assumes taker for market execution)
        fee_taker = float(self._fee_rate_taker)
        fee_maker = float(self._fee_rate_maker)
        costs["fee_rate_taker"] = fee_taker
        costs["fee_rate_maker"] = fee_maker
        # Convert fee rate to bps
        costs["fee_bps_taker"] = fee_taker * 10000.0
        costs["fee_bps_maker"] = fee_maker * 10000.0
        # Estimated execution cost bps for small market order: fee + half spread + slippage proxy
        est = float(costs["fee_bps_taker"])
        if sp is not None:
            est += float(sp) / 2.0
            est += float(costs.get("expected_slippage_bps_small_market_order") or 0.0) * float(
                self._cfg.get("slippage_spread_multiplier", 1.0) or 1.0
            )
        costs["estimated_cost_bps_small_market_order"] = float(round(est, 3))
        # Provide $10k notional estimates for frontend readability
        costs["estimated_cost_usdt_per_10k_notional"] = float(round(est / 10000.0 * 10000.0, 4))

        # Funding/OI anomaly flags (read-only)
        anomalies: List[str] = []
        fr = exchange_support.get("funding_rate")
        if fr is not None:
            fr_abs = abs(float(fr))
            # thresholds: 5bp/8h ~ 0.0005 as "high"
            if fr_abs >= float(self._cfg.get("funding_rate_extreme_abs", 0.0010) or 0.0010):
                anomalies.append(f"funding_rate_extreme_abs:{fr_abs:.6f}")
            elif fr_abs >= float(self._cfg.get("funding_rate_high_abs", 0.0005) or 0.0005):
                anomalies.append(f"funding_rate_high_abs:{fr_abs:.6f}")
        if isinstance(open_interest, dict):
            oi_val = open_interest.get("openInterest") or open_interest.get("oi") or open_interest.get("value")
            if oi_val is not None:
                try:
                    oif = float(oi_val)
                    if oif > 0 and oif >= float(self._cfg.get("open_interest_high", 0) or 0) and float(self._cfg.get("open_interest_high", 0) or 0) > 0:
                        anomalies.append("open_interest_high")
                except Exception:
                    pass

        # Funding conflict hint vs reference bias (not a directive)
        warnings: List[str] = []
        if fr is not None and action_bias in ("buy", "sell"):
            # positive funding: longs pay -> long bias costlier
            if float(fr) > 0 and action_bias == "buy":
                warnings.append("funding_positive_long_pays")
            if float(fr) < 0 and action_bias == "sell":
                warnings.append("funding_negative_short_pays")

        # Funding cost estimate (per 8h, per $10k notional). OKX funding is periodic; we keep generic.
        if fr is not None:
            try:
                fr_f = float(fr)
                costs["funding_rate"] = fr_f
                costs["funding_cost_usdt_per_10k_notional_per_period"] = float(round(fr_f * 10000.0, 6))
            except Exception:
                pass

        # Short-term anomaly detection (rolling compare): spread spike / depth drop
        try:
            prev = self._rolling.get(cache_key, {})
            prev_sp = float(prev.get("spread_bps") or 0.0)
            prev_depth = float(prev.get("depth_top5") or 0.0)
            cur_sp = float(sp) if sp is not None else 0.0
            cur_depth = float(bid_vol_5 + ask_vol_5)
            if prev_sp > 0 and cur_sp > 0:
                if (cur_sp / prev_sp) >= 1.8 and (cur_sp - prev_sp) >= 10:
                    anomalies.append(f"spread_spike:{prev_sp:.1f}->{cur_sp:.1f}")
            if prev_depth > 0 and cur_depth > 0:
                if (cur_depth / prev_depth) <= 0.45:
                    anomalies.append("depth_drop_top5")
            self._rolling[cache_key] = {"spread_bps": cur_sp, "depth_top5": cur_depth}
        except Exception:
            pass

        # SLTP suggestions based on ATR% + spread
        risk_pct_s = None
        tp_pct_s = None
        trailing_offset_s = None
        if atrp is not None and atrp > 0:
            risk_pct_s = min(0.08, max(0.006, atrp * 2.0))
            tp_pct_s = min(0.20, max(0.010, risk_pct_s * min_rr))
            # trailing offset anchored by spread and volatility
            base = max(0.008, min(0.03, (float(sp or 35.0) / 10000.0) * 2.0))
            trailing_offset_s = max(0.006, min(0.03, base))

        llm_block: Dict[str, Any] = {}
        execution_support = {
            "guards": {
                "min_quality_score_to_trade": float(min_quality),
                "max_spread_bps_to_trade": float(max_spread_bps),
                "min_rr_to_trade": float(min_rr),
                "depth_imbalance_top5": float(depth_imb) if depth_imb is not None else None,
            },
            "costs": costs,
            "anomalies": anomalies,
            "warnings": warnings,
            "llm_analysis": llm_block,
            "sltp_suggestions": {
                "risk_pct": float(risk_pct_s) if risk_pct_s is not None else None,
                "take_profit_pct": float(tp_pct_s) if tp_pct_s is not None else None,
                "trailing_offset": float(trailing_offset_s) if trailing_offset_s is not None else None,
                "basis": {
                    "atr_pct_1h": float(atrp) if atrp is not None else None,
                    "spread_bps": float(sp) if sp is not None else None,
                    "min_rr": float(min_rr),
                },
            },
            "notes": [
                "本模块只负责数据汇总与判断支撑，不产生下单指令。",
                "执行/开平仓由 ai_core 决策 + ExecutionGateway 执行；SLTP 仅消费建议参数。",
            ],
        }

        # Optional LLM deep analysis (analysis module responsibility, bounded by quality+timeout).
        # Mutate llm_block in place so execution_support["llm_analysis"] stays consistent.
        try:
            if bool(self._cfg.get("enable_llm_analysis", False)):
                minq = float(self._cfg.get("min_quality_score_for_llm", 0.55) or 0.55)
                qscore = float(quality_score) if quality_score is not None else 0.0
                if qscore >= minq:
                    llm = self._llm()
                    if llm and hasattr(llm, "analyze_market"):
                        payload = {
                            "symbol": sym,
                            "snapshot": snapshot,
                            "exchange_support": exchange_support,
                            "intel_support": intel_support,
                            "risk_support": risk_support,
                            "execution_support": execution_support,
                            "quality": {"score": qscore, "provenance": provenance},
                        }
                        to = float(self._cfg.get("llm_timeout_sec", 3.5) or 3.5)
                        ai = await asyncio.wait_for(llm.analyze_market(payload), timeout=to)
                        if isinstance(ai, dict) and ai:
                            llm_block.clear()
                            llm_block.update(
                                {
                                    "source": "llm",
                                    "summary": ai.get("summary") or ai.get("reasoning") or "",
                                    "trend": ai.get("trend"),
                                    "action_bias": ai.get("signal") or ai.get("action") or ai.get("recommendation"),
                                    "confidence": ai.get("confidence"),
                                    "risk_level": ai.get("risk_level"),
                                    "raw": ai,
                                }
                            )
        except Exception:
            llm_block.clear()

        view = SymbolView(
            symbol=sym,
            timestamp=ts,
            quality_score=quality_score,
            provenance=provenance,
            schema_version=self._schema_version,
            partial=bool(partial),
            errors=errors,
            price=price if price > 0 else None,
            spread_bps=float(sp) if sp is not None else None,
            atr_pct_1h=float(atrp) if atrp is not None else None,
            change_24h=float(change_24h),
            trend=trend_n,
            action_bias=action_bias,
            confidence=conf_f,
            summary=summary[:1200],
            conflicts=conflicts,
            exchange_support=exchange_support,
            intel_support=intel_support,
            risk_support=risk_support,
            execution_support=execution_support,
            snapshot=snapshot if include_snapshot else {},
        )

        # Add UI-oriented helpers (Chinese display + bounded diff)
        try:
            d = view.to_dict()
            view.changeset = self._compute_changeset(cache_key, d)
            view.display_cn = self._build_display_cn(d)
        except Exception:
            pass

        self._cache[cache_key] = {"view": view.__dict__, "snapshot": snapshot}
        self._cache_ts[cache_key] = now
        return view

    def get_cached_symbol_view(self, symbol: str) -> Dict[str, Any]:
        """
        Fast-path for control-plane (Commander fast snapshot).
        Returns cached symbol view if fresh; otherwise returns {} without fetching any data.
        """
        try:
            sym = str(symbol or "").strip()
            if not sym:
                return {}
            cache_key = sym.upper()
            now = self._now()
            if cache_key in self._cache and (now - self._cache_ts.get(cache_key, 0)) < self._cache_ttl_sec:
                cached = self._cache.get(cache_key) or {}
                view = cached.get("view") or {}
                # Never include the heavy snapshot in this fast-path.
                out = dict(view) if isinstance(view, dict) else {}
                out.pop("snapshot", None)
                out.setdefault("cached_only", True)
                out.setdefault("cache_age_sec", round(now - float(self._cache_ts.get(cache_key, 0) or 0), 3))
                return out
        except Exception:
            return {}
        return {}

