"""
掃描機會實時數據預檢（初篩）

在將機會上報 ai_core 或自動開倉前，用交易所行情/K 線等做一輪可配置門檻校驗。
未通過則不報 AI，由掃描器日誌記錄原因。
"""

from __future__ import annotations

import logging
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ScannerGateResult:
    passed: bool
    reason: str
    metrics: Dict[str, Any] = field(default_factory=dict)


def _risk_reward_ratio(opp: Any) -> float:
    entry = float(getattr(opp, "entry_price", 0) or 0)
    sl = float(getattr(opp, "stop_loss", 0) or 0)
    tp = float(getattr(opp, "take_profit", 0) or 0)
    d = str(getattr(opp, "direction", "")).lower()
    if entry <= 0:
        return 0.0
    if d == "long":
        risk = max(entry - sl, 1e-12)
        reward = max(tp - entry, 0.0)
    elif d == "short":
        risk = max(sl - entry, 1e-12)
        reward = max(entry - tp, 0.0)
    else:
        return 0.0
    return reward / risk if risk > 0 else 0.0


def _extract_kline_series(klines: List[Any], field: str) -> List[float]:
    idx = {"open": 1, "high": 2, "low": 3, "close": 4, "volume": 5}
    keys = {
        "high": ("high", "h"),
        "low": ("low", "l"),
        "close": ("close", "c"),
        "volume": ("volume", "v"),
    }
    fi = idx.get(field, 4)
    out: List[float] = []
    for k in klines or []:
        raw = None
        if isinstance(k, dict):
            for kk in keys.get(field, ("close",)):
                if kk in k:
                    raw = k.get(kk)
                    break
        elif isinstance(k, (list, tuple)) and len(k) > fi:
            raw = k[fi]
        try:
            if raw is not None:
                out.append(float(raw))
        except (TypeError, ValueError):
            continue
    return out


def _simple_atr_pct(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1 or len(highs) < period + 1 or len(lows) < period + 1:
        return 0.0
    trs: List[float] = []
    for i in range(-period, 0):
        h, l, c_prev = highs[i], lows[i], closes[i - 1]
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        trs.append(tr)
    atr = sum(trs) / max(1, len(trs))
    last = closes[-1]
    return (atr / last) if last > 0 else 0.0


class ScannerOpportunityGate:
    """基於實時行情與 K 線的掃描機會初篩。"""

    def __init__(
        self,
        exchange: Any,
        config: Optional[Dict[str, Any]] = None,
        *,
        main_controller: Any = None,
    ) -> None:
        self.exchange = exchange
        self.config = dict(config or {})
        self.main_controller = main_controller

    def _c(self, key: str, default: Any) -> Any:
        return self.config.get(key, default)

    async def _fetch_ticker_resilient(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch ticker with symbol variants and lightweight retries."""
        if not self.exchange or not hasattr(self.exchange, "get_ticker"):
            return None
        variants = [symbol]
        sym_dash = symbol.replace("/", "-")
        if sym_dash not in variants:
            variants.append(sym_dash)
        retries = max(1, int(self._c("ticker_retry_count", 2) or 2))
        backoff = max(0.0, float(self._c("ticker_retry_backoff_sec", 0.2) or 0.2))
        for attempt in range(retries):
            for sym in variants:
                try:
                    ticker = await self.exchange.get_ticker(sym)
                    if ticker:
                        return ticker
                except Exception:
                    continue
            if attempt < retries - 1:
                await asyncio.sleep(backoff * float(attempt + 1))
        return None

    async def evaluate(self, opportunity: Any, insight: Any = None) -> ScannerGateResult:
        if not self._c("enabled", True):
            return ScannerGateResult(True, "gate_disabled", {})

        if not self.exchange or not hasattr(self.exchange, "get_ticker"):
            return ScannerGateResult(False, "no_exchange", {})

        sym = str(getattr(opportunity, "symbol", "") or "").strip()
        if not sym:
            return ScannerGateResult(False, "empty_symbol", {})

        metrics: Dict[str, Any] = {"symbol": sym}
        mi_view_bid = None
        mi_view_ask = None
        mi_view_price = None

        # 优先使用统一行情情报引擎的门控建议（单一真源）
        try:
            mi = getattr(self.main_controller, "market_intelligence", None) if self.main_controller else None
            if mi and hasattr(mi, "get_symbol_view"):
                view = await mi.get_symbol_view(sym, include_snapshot=False)
                es = getattr(view, "execution_support", None)
                guards = (es.get("guards") or {}) if isinstance(es, dict) else {}
                q = getattr(view, "quality_score", None)
                # When MI can provide a usable price/bid/ask, we can avoid hard dependency
                # on exchange ticker endpoint (which is the #1 false-negative source).
                try:
                    mi_view_price = float(getattr(view, "price", None) or 0.0)
                except Exception:
                    mi_view_price = None
                try:
                    mi_view_bid = float(getattr(view, "best_bid", None) or 0.0)
                except Exception:
                    mi_view_bid = None
                try:
                    mi_view_ask = float(getattr(view, "best_ask", None) or 0.0)
                except Exception:
                    mi_view_ask = None
                # unknown/partial 数据更保守：对点差/RR 门槛做收紧，避免“信息不全也照样开仓”
                try:
                    partial = bool(getattr(view, "partial", False))
                except Exception:
                    partial = False
                prov = str(getattr(view, "provenance", "") or "").strip().lower() or "unknown"
                metrics["mi_partial"] = partial
                metrics["mi_provenance"] = prov
                if mi_view_price and mi_view_price > 0:
                    metrics["mi_price"] = mi_view_price
                if mi_view_bid and mi_view_bid > 0:
                    metrics["mi_best_bid"] = mi_view_bid
                if mi_view_ask and mi_view_ask > 0:
                    metrics["mi_best_ask"] = mi_view_ask
                if partial or prov == "unknown":
                    # 只在 gate 未显式配置得更严格时才覆写（尊重用户配置）
                    try:
                        cur_spread = float(self._c("max_spread_bps", 45.0) or 45.0)
                    except Exception:
                        cur_spread = 45.0
                    try:
                        cur_rr = float(self._c("min_risk_reward", 1.05) or 1.05)
                    except Exception:
                        cur_rr = 1.05
                    tightened_spread = min(cur_spread, float(self._c("partial_max_spread_bps", 35.0) or 35.0))
                    tightened_rr = max(cur_rr, float(self._c("partial_min_risk_reward", 1.15) or 1.15))
                    self.config["max_spread_bps"] = tightened_spread
                    self.config["min_risk_reward"] = tightened_rr
                    metrics["gate_tightened_for_partial"] = True
                    metrics["tightened_max_spread_bps"] = tightened_spread
                    metrics["tightened_min_risk_reward"] = tightened_rr
                if q is not None:
                    try:
                        metrics["mi_quality_score"] = float(q)
                    except Exception:
                        pass
                if guards:
                    metrics["mi_guards"] = dict(guards)
                    # 若 gate 本身未显式配置，采用 MI 建议值
                    if "max_spread_bps" not in self.config:
                        self.config["max_spread_bps"] = guards.get("max_spread_bps_to_trade", self._c("max_spread_bps", 45.0))
                    if "min_risk_reward" not in self.config:
                        self.config["min_risk_reward"] = guards.get("min_rr_to_trade", self._c("min_risk_reward", 1.05))
                    # 数据质量门槛（若 MI 给出了质量分与阈值建议）
                    try:
                        min_q = float(guards.get("min_quality_score_to_trade", 0) or 0)
                        qv = float(metrics.get("mi_quality_score")) if metrics.get("mi_quality_score") is not None else None
                        # IMPORTANT: treat qv<=0 as "unknown / missing", not hard-fail.
                        # We only hard-fail when MI produced a meaningful quality score.
                        if qv is not None and qv <= 0:
                            metrics["mi_quality_missing_or_zero"] = True
                            qv = None
                        if min_q > 0 and qv is not None and qv < min_q:
                            return ScannerGateResult(False, f"mi_quality_low:{qv:.3f}<{min_q}", metrics)
                    except Exception:
                        pass
        except Exception:
            pass

        # If MI already gave a tradable price, accept it as ticker fallback.
        # Bid/ask can be missing on transient collector degradation; in that
        # case spread checks will be skipped naturally and other guards still apply.
        ticker = None
        try:
            if mi_view_price and float(mi_view_price or 0) > 0:
                ticker = {
                    "last": float(mi_view_price),
                    "bid": float(mi_view_bid or 0) if mi_view_bid else 0,
                    "ask": float(mi_view_ask or 0) if mi_view_ask else 0,
                }
                metrics["ticker_from_mi_view"] = True
        except Exception:
            ticker = None

        if ticker is None:
            ticker = await self._fetch_ticker_resilient(sym)

        if not ticker:
            # Fallback to MI cached symbol view to reduce false negatives when
            # exchange ticker endpoint has transient timeout/empty payload.
            try:
                mi = getattr(self.main_controller, "market_intelligence", None) if self.main_controller else None
                if mi and hasattr(mi, "get_cached_symbol_view"):
                    cv = mi.get_cached_symbol_view(sym) or {}
                    px = float(cv.get("price") or 0.0)
                    bb = cv.get("best_bid")
                    ba = cv.get("best_ask")
                    ticker = {"last": px, "bid": bb, "ask": ba, "change24h": cv.get("change_24h")}
                    metrics["ticker_from_cached_symbol_view"] = True
            except Exception:
                ticker = None
            # Last-resort fallback: use opportunity entry_price as tradable last.
            # This avoids dropping otherwise valid opportunities on transient
            # ticker outages; downstream RR/slippage/risk guards still apply.
            if (not ticker) or float(ticker.get("last") or ticker.get("close") or 0.0) <= 0:
                try:
                    ep = float(getattr(opportunity, "entry_price", 0) or 0)
                except Exception:
                    ep = 0.0
                if ep > 0:
                    ticker = {"last": ep, "bid": 0.0, "ask": 0.0}
                    metrics["ticker_from_opportunity_entry"] = True
            if not ticker or float(ticker.get("last") or ticker.get("close") or 0.0) <= 0:
                return ScannerGateResult(False, "ticker_empty", metrics)

        last = float(ticker.get("last") or ticker.get("close") or 0)
        bid = float(ticker.get("bid") or 0)
        ask = float(ticker.get("ask") or 0)
        chg = float(ticker.get("change24h") or ticker.get("change") or 0)
        metrics["last"] = last
        metrics["spread_bps"] = None
        metrics["change_24h"] = chg

        max_spread = float(self._c("max_spread_bps", 45.0) or 0)
        if max_spread > 0 and last > 0 and bid > 0 and ask > 0 and ask >= bid:
            mid = 0.5 * (bid + ask)
            spread_bps = ((ask - bid) / mid) * 10000.0 if mid > 0 else 9999.0
            metrics["spread_bps"] = round(spread_bps, 3)
            if spread_bps > max_spread:
                return ScannerGateResult(
                    False,
                    f"spread_too_wide:{spread_bps:.1f}>{max_spread}",
                    metrics,
                )

        min_chg = float(self._c("min_abs_change_24h", 0.0) or 0.0)
        if min_chg > 0 and abs(chg) < min_chg:
            return ScannerGateResult(
                False,
                f"change_24h_too_small:{abs(chg):.4f}<{min_chg}",
                metrics,
            )

        # 默认允许 5% 的 entry vs last 偏差：突破/均值回归机会的 entry_price 可能取自 K线收盘或关键价位，
        # 在波动期与实时 last 存在偏差属正常；过严会导致机会全部被门控拦截而无法进入决策/执行链路。
        slip_max = float(self._c("max_entry_vs_last_slippage_pct", 0.05) or 0)
        entry = float(getattr(opportunity, "entry_price", 0) or 0)
        if slip_max > 0 and last > 0 and entry > 0:
            slip = abs(entry - last) / last
            metrics["entry_vs_last_slippage_pct"] = round(slip, 6)
            if slip > slip_max:
                return ScannerGateResult(
                    False,
                    f"entry_slippage:{slip:.4f}>{slip_max}",
                    metrics,
                )

        min_rr = float(self._c("min_risk_reward", 1.05) or 0)
        if min_rr > 0:
            rr = _risk_reward_ratio(opportunity)
            metrics["risk_reward"] = round(rr, 4)
            if rr < min_rr:
                return ScannerGateResult(
                    False,
                    f"risk_reward_low:{rr:.3f}<{min_rr}",
                    metrics,
                )

        if bool(self._c("require_insight_trend_alignment", True)) and insight is not None:
            tr = str(getattr(insight, "trend", "") or "").lower()
            ts = float(getattr(insight, "trend_strength", 0.0) or 0.0)
            d = str(getattr(opportunity, "direction", "") or "").lower()
            metrics["insight_trend"] = tr
            metrics["insight_trend_strength"] = ts
            if ts > 0.05:
                if d == "long" and tr == "bearish":
                    return ScannerGateResult(False, "insight_conflict_long_vs_bearish", metrics)
                if d == "short" and tr == "bullish":
                    return ScannerGateResult(False, "insight_conflict_short_vs_bullish", metrics)

        vol_ratio_min = float(self._c("min_volume_vs_avg_ratio", 0.0) or 0.0)
        lb = int(self._c("volume_avg_lookback_bars", 12) or 12)
        min_atr = float(self._c("min_atr_pct_1h", 0.0) or 0.0)
        max_atr = float(self._c("max_atr_pct_1h", 0.0) or 0.0)

        need_klines = vol_ratio_min > 0 or min_atr > 0 or max_atr > 0
        if need_klines and hasattr(self.exchange, "get_klines"):
            try:
                kl = await self.exchange.get_klines(sym.replace("/", "-"), "1h", limit=max(48, lb + 5))
            except Exception as e:
                logger.debug("ScannerGate klines failed %s: %s", sym, e)
                return ScannerGateResult(False, f"klines_error:{e}", metrics)

            if not kl or len(kl) < lb + 2:
                return ScannerGateResult(False, "klines_short", metrics)

            vols = _extract_kline_series(kl, "volume")
            closes = _extract_kline_series(kl, "close")
            highs = _extract_kline_series(kl, "high")
            lows = _extract_kline_series(kl, "low")

            if vol_ratio_min > 0 and len(vols) >= lb + 1:
                last_v = float(vols[-1] or 0)
                prev = [float(vols[i] or 0) for i in range(-lb - 1, -1)]
                avg_v = sum(prev) / max(1, len(prev))
                metrics["volume_last"] = last_v
                metrics["volume_avg_prev"] = round(avg_v, 6)
                ratio_v = (last_v / avg_v) if avg_v > 1e-12 else 0.0
                metrics["volume_vs_avg_ratio"] = round(ratio_v, 4)
                if ratio_v < vol_ratio_min:
                    return ScannerGateResult(
                        False,
                        f"volume_ratio_low:{ratio_v:.3f}<{vol_ratio_min}",
                        metrics,
                    )

            if (min_atr > 0 or max_atr > 0) and len(highs) >= 16 and len(lows) >= 16 and len(closes) >= 16:
                atrp = _simple_atr_pct(highs, lows, closes, period=14)
                metrics["atr_pct_1h"] = round(atrp, 6)
                if min_atr > 0 and atrp < min_atr:
                    return ScannerGateResult(
                        False,
                        f"atr_too_low:{atrp:.5f}<{min_atr}",
                        metrics,
                    )
                if max_atr > 0 and atrp > max_atr:
                    return ScannerGateResult(
                        False,
                        f"atr_too_high:{atrp:.5f}>{max_atr}",
                        metrics,
                    )

        metrics["passed"] = True
        return ScannerGateResult(True, "all_checks_ok", metrics)
