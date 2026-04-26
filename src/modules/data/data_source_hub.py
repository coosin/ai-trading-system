"""
统一数据源模块管理中心。

双渠道：
1) 交易执行数据渠道（OKX/Binance 等交易所）
2) 外部情报数据渠道（链上/新闻/舆情）
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from src.modules.data.data_quality_advisor import DataQualityAdvisor
from src.modules.data.binance_public_provider import get_binance_public_provider

logger = logging.getLogger(__name__)


@dataclass
class DataSourceHubStatus:
    healthy: bool
    provider: str
    timestamp: str


class DataSourceHub:
    """数据源统一编排入口（轻量 facade）。"""

    def __init__(self, main_controller: Any = None):
        self.main_controller = main_controller or self._resolve_main_controller()
        self.quality_advisor = DataQualityAdvisor(window_size=80)
        self._collector_cache: Dict[str, Dict[str, Any]] = {}
        self._collector_cache_ts: Dict[str, float] = {}
        self._exchange_override: Any = None
        if self.main_controller is not None:
            self.bind_main_controller(self.main_controller)

    def _resolve_main_controller(self) -> Any:
        """
        Best-effort resolve active MainController across import namespaces.
        Some runtimes may load `src.modules.*` and `modules.*` separately.
        """
        # Prefer already-loaded modules first (no extra import side effects).
        for mod_name in ("src.modules.main_controller", "modules.main_controller"):
            mod = sys.modules.get(mod_name)
            cls = getattr(mod, "MainController", None) if mod else None
            if cls and hasattr(cls, "get_active_instance"):
                try:
                    mc = cls.get_active_instance()
                    if mc is not None:
                        return mc
                except Exception:
                    pass
        # Fallback imports if module not loaded yet.
        for import_path in ("src.modules.main_controller", "modules.main_controller"):
            try:
                mod = __import__(import_path, fromlist=["MainController"])
                cls = getattr(mod, "MainController", None)
                if cls and hasattr(cls, "get_active_instance"):
                    mc = cls.get_active_instance()
                    if mc is not None:
                        return mc
            except Exception:
                continue
        return None

    def bind_main_controller(self, main_controller: Any) -> None:
        """
        显式绑定主控制器与交易所引用，避免初始化窗口/重建后的引用漂移。
        """
        self.main_controller = main_controller
        self._exchange_override = None
        mc = main_controller
        if not mc:
            return
        engine = getattr(mc, "ai_trading_engine", None)
        self._exchange_override = (
            (getattr(engine, "exchange", None) if engine else None)
            or getattr(mc, "execution_exchange", None)
            or getattr(mc, "market_data_exchange", None)
            or getattr(mc, "okx_exchange", None)
            or getattr(mc, "exchange", None)
        )

    def _collector_timeout(self, name: str, cfg: Dict[str, Any]) -> float:
        """采集项分级超时，避免单一 timeout 造成全链路误降级。"""
        base = float(cfg.get("fetch_timeout_sec", 8.0) or 8.0)
        hard_defaults = {
            # 实盘网络抖动/代理链路下，ticker 与 order_book 常出现 6-8s 边界超时；
            # 适度抬高默认预算，避免统一快照误判为 fallback。
            "exch.ticker": 10.0,
            "exch.order_book": 12.0,
            "exch.open_interest": 8.0,
            "exch.funding_rate": 8.0,
            "exch.positions": 14.0,
            "exch.open_orders": 14.0,
            "exch.liq_proxy": 12.0,
            "exch.klines_1h": 10.0,
            "third_party.sentiment": 8.0,
            "third_party.news": 8.0,
        }
        env_key = f"OPENCLAW_DATA_HUB_TIMEOUT_{name.upper().replace('.', '_')}"
        env_v = os.getenv(env_key)
        if env_v:
            try:
                return max(1.5, float(env_v))
            except Exception:
                pass
        return max(base, hard_defaults.get(name, base))

    def _cache_get(self, key: str, ttl_sec: float) -> Any:
        ts = float(self._collector_cache_ts.get(key, 0.0))
        if ts <= 0:
            return None
        if (datetime.now().timestamp() - ts) > max(1.0, float(ttl_sec)):
            return None
        return self._collector_cache.get(key)

    def _cache_set(self, key: str, value: Any) -> None:
        self._collector_cache[key] = value
        self._collector_cache_ts[key] = datetime.now().timestamp()

    async def _cfg(self) -> Dict[str, Any]:
        """
        AI-managed config entrypoint (optional).
        Falls back to safe defaults when config manager is unavailable.
        """
        mc = self.main_controller
        _ft = float(os.getenv("OPENCLAW_DATA_HUB_FETCH_TIMEOUT_SEC", "22") or "22")
        _st = float(os.getenv("OPENCLAW_DATA_HUB_SNAPSHOT_TIMEOUT_SEC", "55") or "55")
        defaults = {
            "enable_legacy_external_analysis": False,
            # 经 HTTP 代理访问 OKX 时 2.8s 过短，会导致 exch.* 全 timeout → ticker fallback
            "fetch_timeout_sec": max(2.8, _ft),
            "snapshot_timeout_sec": max(6.0, _st),
            "include_klines_1h": True,
            "klines_1h_limit": 64,
            "exchange_collectors": [
                "ticker",
                "order_book",
                "klines_1h",
                "open_interest",
                "funding_rate",
                "positions",
                "open_orders",
                "liquidation_proxy",
            ],
            "intel_collectors": [
                "onchain.sentiment",
                "onchain.flows",
                "onchain.whales",
                "third_party.sentiment",
                "third_party.news",
            ],
            "extra_providers": [],
        }
        if mc and hasattr(mc, "get_ai_managed_config"):
            try:
                cfg = await mc.get_ai_managed_config("data_source_hub", defaults)
                out = cfg if isinstance(cfg, dict) else dict(defaults)
                out["fetch_timeout_sec"] = max(6.0, float(out.get("fetch_timeout_sec", defaults["fetch_timeout_sec"]) or defaults["fetch_timeout_sec"]))
                out["snapshot_timeout_sec"] = max(20.0, float(out.get("snapshot_timeout_sec", defaults["snapshot_timeout_sec"]) or defaults["snapshot_timeout_sec"]))
                return out
            except Exception:
                return dict(defaults)
        return dict(defaults)

    async def _legacy_enabled(self) -> bool:
        try:
            cfg = await self._cfg()
            return bool(cfg.get("enable_legacy_external_analysis", False))
        except Exception:
            return False

    async def _fetch_safe(
        self,
        name: str,
        coro,
        *,
        timeout_sec: Optional[float] = None,
        default: Any = None,
        health: Optional[Dict[str, Any]] = None,
        errors: Optional[List[str]] = None,
    ) -> Any:
        """
        Best-effort data collection wrapper.
        - Never raises to callers
        - Records health + error tags for downstream quality/provenance
        """
        t0 = datetime.now()
        cfg = await self._cfg()
        to = float(timeout_sec if timeout_sec is not None else cfg.get("fetch_timeout_sec", 2.8) or 2.8)
        try:
            out = await asyncio.wait_for(coro, timeout=to)
            if health is not None:
                health[name] = {"status": "ok", "latency_ms": int((datetime.now() - t0).total_seconds() * 1000)}
            return out
        except asyncio.TimeoutError:
            if health is not None:
                health[name] = {"status": "timeout", "latency_ms": int((datetime.now() - t0).total_seconds() * 1000)}
            if errors is not None:
                errors.append(f"{name}:timeout")
            return default
        except Exception as e:
            if health is not None:
                health[name] = {
                    "status": "error",
                    "error": type(e).__name__,
                    "latency_ms": int((datetime.now() - t0).total_seconds() * 1000),
                }
            if errors is not None:
                errors.append(f"{name}:{type(e).__name__}")
            return default

    def _get_exchange(self) -> Any:
        if self._exchange_override is not None:
            return self._exchange_override
        mc = self.main_controller
        if mc is None:
            mc = self._resolve_main_controller()
            if mc is not None:
                self.bind_main_controller(mc)
        if not mc:
            return None
        engine = getattr(mc, "ai_trading_engine", None)
        ex = getattr(engine, "exchange", None) if engine else None
        # fallback: deployment/runtime 差异下，交易所实例可能挂在不同引用点
        return (
            ex
            or getattr(mc, "execution_exchange", None)
            or getattr(mc, "market_data_exchange", None)
            or getattr(mc, "okx_exchange", None)
            or getattr(mc, "exchange", None)
        )

    def _get_onchain_integrator(self) -> Any:
        mc = self.main_controller
        if not mc:
            return None
        integ = getattr(mc, "onchain_integrator", None)
        if integ is not None:
            return integ
        engine = getattr(mc, "ai_trading_engine", None)
        return getattr(engine, "onchain_data", None) if engine else None

    def _get_third_party_integrator(self) -> Any:
        mc = self.main_controller
        if not mc:
            return None
        integ = getattr(mc, "third_party_data_integrator", None)
        if integ is not None:
            return integ
        engine = getattr(mc, "ai_trading_engine", None)
        return getattr(engine, "third_party_data", None) if engine else None

    def _get_market_analyzer(self) -> Any:
        mc = self.main_controller
        if not mc:
            return None
        analyzer = getattr(mc, "market_analyzer", None)
        if analyzer is not None:
            return analyzer
        collector = getattr(mc, "unified_info_collector", None)
        return getattr(collector, "market_analyzer", None) if collector else None

    def _get_llm_integration(self) -> Any:
        mc = self.main_controller
        if not mc:
            return None
        llm = getattr(mc, "llm_integration", None)
        if llm is not None:
            return llm
        engine = getattr(mc, "ai_trading_engine", None)
        return getattr(engine, "llm_integration", None) if engine else None

    def _get_data_provider_plugins(self) -> Dict[str, Any]:
        """
        Reserved hook for future data providers.
        main_controller can expose:
          - data_provider_plugins: Dict[str, Callable[[str], Awaitable[Dict]]]
        """
        out: Dict[str, Any] = {}
        # Built-in plugins (enabled via config `data_source_hub.extra_providers`)
        try:
            from src.modules.data.coinglass_provider import fetch_coinglass_snapshot

            out["coinglass"] = fetch_coinglass_snapshot
        except Exception:
            pass
        try:
            from src.modules.data.aicoin_provider import fetch_aicoin_snapshot

            out["aicoin"] = fetch_aicoin_snapshot
        except Exception:
            pass

        # External plugins injected by MainController (highest priority)
        mc = self.main_controller
        plugins = getattr(mc, "data_provider_plugins", None) if mc else None
        if isinstance(plugins, dict) and plugins:
            out.update(plugins)
        return out

    def get_collector_contract(self) -> Dict[str, Any]:
        """
        Stable contract for analysis modules (shape-only; values depend on providers).
        """
        return {
            "channels": {
                "渠道A_交易所实时执行数据": {
                    "ticker": "dict",
                    "order_book": "dict",
                    "klines_1h": "list[dict] (optional)",
                    "open_interest": "dict",
                    "funding_rate": "float|None",
                    "positions": "list[dict]",
                    "open_orders": "list[dict]",
                    "liquidation_proxy": "dict",
                    "collector": {"partial": "bool", "errors": "list[str]", "health": "dict"},
                },
                "渠道B_链上新闻舆情数据": {
                    "onchain": "dict",
                    "sentiment": "dict",
                    "news": "dict",
                    "collector": {"partial": "bool", "errors": "list[str]", "health": "dict"},
                },
            },
            "reserved": {
                "扩展数据": "dict[str, dict] (extra providers)",
            },
        }

    def _iso(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def _sanitize(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            return {str(k): self._sanitize(v) for k, v in payload.items()}
        if isinstance(payload, list):
            return [self._sanitize(v) for v in payload]
        if isinstance(payload, tuple):
            return [self._sanitize(v) for v in payload]
        if hasattr(payload, "__dataclass_fields__"):
            return self._sanitize(asdict(payload))
        return self._iso(payload)

    async def get_symbols(self) -> List[str]:
        exchange = self._get_exchange()
        if exchange and hasattr(exchange, "symbols"):
            symbols = getattr(exchange, "symbols", None)
            if isinstance(symbols, list) and symbols:
                return [str(s) for s in symbols]
        return ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT"]

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        exchange = self._get_exchange()
        if not exchange:
            logger.warning(
                "DataSourceHub.get_ticker(%s): main_controller 上无可用 exchange（检查 ai_trading_engine/execution_exchange/market_data_exchange/okx_exchange）",
                symbol,
            )
        if exchange and hasattr(exchange, "get_ticker"):
            try:
                raw = await exchange.get_ticker(symbol)
                if isinstance(raw, dict) and raw:
                    last = float(
                        raw.get("last")
                        or raw.get("close")
                        or raw.get("lastPx")
                        or raw.get("idxPx")
                        or 0.0
                    )
                    bid = float(raw.get("bid") or raw.get("bidPx") or 0.0)
                    ask = float(raw.get("ask") or raw.get("askPx") or 0.0)
                    if last <= 0.0 and bid > 0.0 and ask > 0.0:
                        last = (bid + ask) / 2.0
                    if last > 0.0 or bid > 0.0 or ask > 0.0:
                        chg_24h = float(
                            raw.get("change_24h")
                            or raw.get("change24h")
                            or raw.get("change")
                            or raw.get("chgUtc")
                            or 0.0
                        )
                        return {
                            "symbol": symbol,
                            "last": last,
                            "price": last,
                            "bid": bid,
                            "ask": ask,
                            "high": float(raw.get("high") or raw.get("high24h") or 0.0),
                            "low": float(raw.get("low") or raw.get("low24h") or 0.0),
                            # Provide both snake_case + legacy keys for downstream consumers.
                            "change_24h": chg_24h,
                            "change24h": chg_24h,
                            "change": chg_24h,
                            "volume": float(
                                raw.get("volume")
                                or raw.get("quoteVolume")
                                or raw.get("vol24h")
                                or 0.0
                            ),
                            "timestamp": datetime.now().isoformat(),
                            "source": "exchange",
                        }
            except Exception:
                pass
        return {"symbol": symbol, "timestamp": datetime.now().isoformat(), "source": "fallback"}

    async def get_klines(self, symbol: str, interval: str = "1H", limit: int = 100) -> List[Dict[str, Any]]:
        exchange = self._get_exchange()
        if exchange and hasattr(exchange, "get_klines"):
            try:
                klines = await exchange.get_klines(symbol, interval, limit=limit)
                if isinstance(klines, list):
                    return self._sanitize(klines)
            except Exception:
                pass
        return []

    async def get_order_book(self, symbol: str, depth: int = 20) -> Dict[str, Any]:
        exchange = self._get_exchange()
        cache_key = f"order_book:{symbol}:{depth}"
        if exchange and hasattr(exchange, "get_order_book"):
            try:
                ob = await exchange.get_order_book(symbol, depth=depth)
                if ob:
                    bids = ob.bids if hasattr(ob, "bids") else ob.get("bids", [])
                    asks = ob.asks if hasattr(ob, "asks") else ob.get("asks", [])
                    out = {
                        "symbol": symbol,
                        "bids": [[float(x[0]), float(x[1])] for x in bids[:depth]],
                        "asks": [[float(x[0]), float(x[1])] for x in asks[:depth]],
                        "timestamp": datetime.now().isoformat(),
                        "source": "exchange",
                    }
                    if out["bids"] or out["asks"]:
                        self._cache_set(cache_key, out)
                    return out
            except Exception:
                pass
        cached = self._cache_get(cache_key, ttl_sec=float(os.getenv("OPENCLAW_DATA_HUB_ORDERBOOK_CACHE_TTL", "12") or "12"))
        if isinstance(cached, dict):
            out = dict(cached)
            out["source"] = "cache"
            return out
        return {"symbol": symbol, "bids": [], "asks": [], "timestamp": datetime.now().isoformat(), "source": "fallback"}

    async def get_positions(self) -> List[Dict[str, Any]]:
        exchange = self._get_exchange()
        cache_key = "positions"
        if exchange and hasattr(exchange, "get_positions"):
            try:
                positions = await exchange.get_positions()
                if isinstance(positions, list):
                    self._cache_set(cache_key, positions)
                    return self._sanitize(positions)
            except Exception:
                pass
        cached = self._cache_get(cache_key, ttl_sec=float(os.getenv("OPENCLAW_DATA_HUB_POSITIONS_CACHE_TTL", "20") or "20"))
        if isinstance(cached, list):
            return self._sanitize(cached)
        return []

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        exchange = self._get_exchange()
        cache_key = f"open_orders:{symbol or '*'}"
        if exchange and hasattr(exchange, "get_open_orders"):
            try:
                orders = await exchange.get_open_orders(symbol)
                if isinstance(orders, list):
                    self._cache_set(cache_key, orders)
                    return self._sanitize(orders)
            except Exception:
                pass
        cached = self._cache_get(cache_key, ttl_sec=float(os.getenv("OPENCLAW_DATA_HUB_OPEN_ORDERS_CACHE_TTL", "20") or "20"))
        if isinstance(cached, list):
            return self._sanitize(cached)
        return []

    async def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        exchange = self._get_exchange()
        cache_key = f"open_interest:{symbol}"
        if exchange and hasattr(exchange, "get_open_interest"):
            try:
                oi = await exchange.get_open_interest(symbol)
                if isinstance(oi, dict):
                    self._cache_set(cache_key, oi)
                    return self._sanitize(oi)
            except Exception:
                pass
        # Public fallback (no key): Binance Futures OI
        if str(os.getenv("OPENCLAW_DATA_HUB_BINANCE_PUBLIC_FALLBACK", "1") or "1").strip().lower() not in ("0", "false", "no", "off"):
            try:
                prov = await get_binance_public_provider()
                oi2, meta = await prov.get_open_interest_current(symbol)
                if isinstance(oi2, dict) and oi2.get("openInterest") is not None:
                    out = dict(oi2)
                    out["fallback_meta"] = meta
                    self._cache_set(cache_key, out)
                    return self._sanitize(out)
            except Exception:
                pass
        cached = self._cache_get(cache_key, ttl_sec=float(os.getenv("OPENCLAW_DATA_HUB_OI_CACHE_TTL", "20") or "20"))
        if isinstance(cached, dict):
            return self._sanitize(cached)
        return {}

    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        exchange = self._get_exchange()
        cache_key = f"funding_rate:{symbol}"
        if exchange and hasattr(exchange, "get_funding_rate"):
            try:
                fr = await exchange.get_funding_rate(symbol)
                out = float(fr) if fr is not None else None
                if out is not None:
                    self._cache_set(cache_key, out)
                return out
            except Exception:
                pass
        # Public fallback (no key): Binance Futures funding rate
        if str(os.getenv("OPENCLAW_DATA_HUB_BINANCE_PUBLIC_FALLBACK", "1") or "1").strip().lower() not in ("0", "false", "no", "off"):
            try:
                prov = await get_binance_public_provider()
                fr2, _meta = await prov.get_funding_rate_current(symbol)
                if fr2 is not None:
                    self._cache_set(cache_key, float(fr2))
                    return float(fr2)
            except Exception:
                pass
        cached = self._cache_get(cache_key, ttl_sec=float(os.getenv("OPENCLAW_DATA_HUB_FUNDING_CACHE_TTL", "20") or "20"))
        if isinstance(cached, (int, float)):
            return float(cached)
        return None

    async def get_liquidation_proxy(self, symbol: str) -> Dict[str, Any]:
        """无统一交易所爆仓接口时，用持仓+清算价构造风险代理指标。"""
        positions = await self.get_positions()
        matched = []
        key = symbol.replace("/", "-").upper()
        for p in positions:
            p_symbol = str(p.get("instId") or p.get("symbol") or "").upper()
            if key.split("-")[0] in p_symbol:
                matched.append(p)
        high_risk = 0
        samples = []
        for p in matched:
            liq_px = float(p.get("liqPx") or p.get("liquidation_price") or 0.0)
            mark_px = float(p.get("markPx") or p.get("mark_price") or p.get("last") or 0.0)
            if liq_px > 0 and mark_px > 0:
                dist = abs(mark_px - liq_px) / max(mark_px, 1e-9)
                if dist < 0.05:
                    high_risk += 1
                samples.append({"mark_price": mark_px, "liquidation_price": liq_px, "distance_pct": dist * 100.0})
        out = {
            "symbol": symbol,
            "positions_considered": len(matched),
            "high_risk_positions": high_risk,
            "samples": samples[:10],
            "source": "position_proxy",
            "timestamp": datetime.now().isoformat(),
        }
        # If no positions matched (common in read-only/boot windows), provide a derived risk proxy
        # from funding/extreme volatility/spread so upstream MI/gates can still behave conservatively.
        if len(matched) <= 0:
            try:
                ticker = await self.get_ticker(symbol)
                last = float((ticker or {}).get("last") or (ticker or {}).get("price") or 0.0)
            except Exception:
                last = 0.0
            try:
                fr = await self.get_funding_rate(symbol)
            except Exception:
                fr = None
            try:
                ob = await self.get_order_book(symbol, depth=10)
            except Exception:
                ob = {}
            spread_bps = None
            try:
                bids = (ob or {}).get("bids") or []
                asks = (ob or {}).get("asks") or []
                if bids and asks:
                    bb = float(bids[0][0])
                    ba = float(asks[0][0])
                    mid = 0.5 * (bb + ba)
                    if mid > 0 and ba >= bb:
                        spread_bps = ((ba - bb) / mid) * 10000.0
            except Exception:
                spread_bps = None
            # crude risk score: higher funding abs and wider spread imply more liquidation-prone regime
            risk = 0.0
            try:
                if fr is not None:
                    risk += min(1.0, abs(float(fr)) / 0.0010) * 0.6
                if spread_bps is not None:
                    risk += min(1.0, float(spread_bps) / 80.0) * 0.4
            except Exception:
                risk = 0.0
            out["derived_risk_proxy"] = {
                "risk_score_0_1": float(round(max(0.0, min(1.0, risk)), 4)),
                "funding_rate": float(fr) if fr is not None else None,
                "spread_bps": float(spread_bps) if spread_bps is not None else None,
                "last": float(last) if last > 0 else None,
                "source": "derived_funding_spread",
            }
            out["source"] = "derived_or_position_proxy"
        return out

    async def analyze_trends(self, symbol: str) -> Dict[str, Any]:
        if not await self._legacy_enabled():
            return {
                "symbol": symbol,
                "enabled": False,
                "deprecated": True,
                "message": "legacy_trend_analysis_disabled",
                "trend": "unknown",
                "strength": 0.0,
                "source": "disabled",
                "timestamp": datetime.now().isoformat(),
            }
        klines = await self.get_klines(symbol, interval="1H", limit=48)
        closes = [float(k.get("close", 0.0)) for k in klines if float(k.get("close", 0.0)) > 0]
        if len(closes) < 10:
            return {"symbol": symbol, "trend": "unknown", "strength": 0.0, "source": "insufficient_data"}
        ma_short = sum(closes[-6:]) / 6.0
        ma_long = sum(closes[-24:]) / 24.0
        diff = (ma_short - ma_long) / max(1e-9, ma_long)
        trend = "bullish" if diff > 0.005 else "bearish" if diff < -0.005 else "sideways"
        return {"symbol": symbol, "trend": trend, "strength": round(abs(diff), 6), "source": "hub"}

    async def get_signals(self, symbol: str) -> Dict[str, Any]:
        if not await self._legacy_enabled():
            return {
                "symbol": symbol,
                "enabled": False,
                "deprecated": True,
                "message": "legacy_signal_endpoint_disabled",
                "signal": "hold",
                "confidence": 0.0,
                "source": "disabled",
                "timestamp": datetime.now().isoformat(),
            }
        ticker = await self.get_ticker(symbol)
        trend = await self.analyze_trends(symbol)
        bias = "hold"
        if trend.get("trend") == "bullish":
            bias = "buy"
        elif trend.get("trend") == "bearish":
            bias = "sell"
        return {
            "symbol": symbol,
            "signal": bias,
            "price": ticker.get("last") or ticker.get("price"),
            "trend": trend.get("trend"),
            "confidence": min(1.0, float(trend.get("strength", 0.0)) * 20.0),
            "source": "hub",
        }

    async def get_indicators(self, symbol: str, indicators: Optional[List[str]] = None) -> Dict[str, Any]:
        if not await self._legacy_enabled():
            return {
                "symbol": symbol,
                "enabled": False,
                "deprecated": True,
                "message": "legacy_indicators_endpoint_disabled",
                "source": "disabled",
                "timestamp": datetime.now().isoformat(),
            }
        indicators = indicators or ["ma_short", "ma_long"]
        klines = await self.get_klines(symbol, interval="1H", limit=64)
        closes = [float(k.get("close", 0.0)) for k in klines if float(k.get("close", 0.0)) > 0]
        out: Dict[str, Any] = {"symbol": symbol, "source": "hub"}
        if not closes:
            return out
        if "ma_short" in indicators:
            out["ma_short"] = sum(closes[-6:]) / min(6, len(closes))
        if "ma_long" in indicators:
            out["ma_long"] = sum(closes[-24:]) / min(24, len(closes))
        if "volatility" in indicators and len(closes) > 2:
            rets: List[float] = []
            for i in range(1, len(closes)):
                prev = closes[i - 1]
                if prev > 0:
                    rets.append((closes[i] - prev) / prev)
            if rets:
                mean = sum(rets) / len(rets)
                var = sum((r - mean) ** 2 for r in rets) / len(rets)
                out["volatility"] = var**0.5
        return out

    # NOTE:
    # 彻底规范：DataSourceHub 只负责数据采集，不负责市场判断/信号/AI分析。
    # 相关分析能力已迁移到 MarketIntelligenceEngine / ai_core。

    async def get_intel_channel(self, symbol: str) -> Dict[str, Any]:
        """渠道B：链上 + 新闻 + 舆情。"""
        cfg = await self._cfg()
        enabled = set([str(x) for x in (cfg.get("intel_collectors") or [])])
        errors: List[str] = []
        health: Dict[str, Any] = {}
        out: Dict[str, Any] = {
            "symbol": symbol,
            "onchain": {},
            "sentiment": {},
            "news": {},
            "health": {"onchain": "missing", "third_party": "missing"},
            "timestamp": datetime.now().isoformat(),
        }

        onchain = self._get_onchain_integrator()
        if onchain and any(k.startswith("onchain.") for k in enabled):
            # Detect mock-only onchain provider to avoid "fake health ok" that misleads quality scoring.
            try:
                provs = getattr(onchain, "providers", None)
                if isinstance(provs, list) and provs:
                    real_cnt = 0
                    mock_cnt = 0
                    for p in provs:
                        name = type(p).__name__ if p is not None else ""
                        if name == "MockOnChainProvider":
                            mock_cnt += 1
                        else:
                            real_cnt += 1
                    if real_cnt <= 0 and mock_cnt > 0:
                        out["health"]["onchain"] = "mock"
            except Exception:
                pass
            sentiment = await self._fetch_safe(
                "onchain.sentiment",
                onchain.analyze_onchain_sentiment(symbol),
                default=None,
                health=health,
                errors=errors,
            )
            flows = await self._fetch_safe(
                "onchain.flows",
                onchain.get_exchange_flows(symbol),
                default=[],
                health=health,
                errors=errors,
            )
            whales = await self._fetch_safe(
                "onchain.whales",
                onchain.get_whale_activities(symbol, limit=20),
                default=[],
                health=health,
                errors=errors,
            )
            if "onchain.sentiment" not in enabled:
                sentiment = None
            if "onchain.flows" not in enabled:
                flows = []
            if "onchain.whales" not in enabled:
                whales = []
            out["onchain"] = self._sanitize({"sentiment": sentiment or {}, "flows": flows or [], "whales": whales or []})
            # If already marked as mock, keep it; otherwise set ok/degraded.
            if out["health"].get("onchain") != "mock":
                out["health"]["onchain"] = "ok" if sentiment is not None else "degraded"

        third = self._get_third_party_integrator()
        if third and any(k.startswith("third_party.") for k in enabled):
            sentiment_key = f"third_party_sentiment:{symbol}"
            cs = await self._fetch_safe(
                "third_party.sentiment",
                third.get_comprehensive_sentiment(symbol),
                timeout_sec=self._collector_timeout("third_party.sentiment", cfg),
                default={},
                health=health,
                errors=errors,
            )
            if isinstance(cs, dict) and cs:
                self._cache_set(sentiment_key, cs)
            else:
                cached_cs = self._cache_get(
                    sentiment_key,
                    ttl_sec=float(os.getenv("OPENCLAW_DATA_HUB_THIRD_PARTY_SENTIMENT_CACHE_TTL", "900") or "900"),
                )
                if isinstance(cached_cs, dict) and cached_cs:
                    cs = dict(cached_cs)
                    if isinstance(health.get("third_party.sentiment"), dict):
                        health["third_party.sentiment"]["status"] = "cache"
                    try:
                        errors.remove("third_party.sentiment:timeout")
                    except ValueError:
                        pass
            out["sentiment"] = self._sanitize(cs or {})
            out["health"]["third_party"] = "ok" if cs else "degraded"
            news = await self._fetch_safe(
                "third_party.news",
                third.get_news_sentiment(symbol),
                timeout_sec=self._collector_timeout("third_party.news", cfg),
                default={},
                health=health,
                errors=errors,
            )
            out["news"] = self._sanitize(news or {})
            if "third_party.sentiment" not in enabled:
                out["sentiment"] = {}
            if "third_party.news" not in enabled:
                out["news"] = {}
        out["collector"] = {
            "partial": bool(errors),
            "errors": errors[:30],
            "health": health,
            "enabled": sorted(enabled),
        }
        return out

    async def get_exchange_channel(self, symbol: str) -> Dict[str, Any]:
        """渠道A：交易所实时/账户/执行相关。"""
        cfg = await self._cfg()
        enabled = set([str(x) for x in (cfg.get("exchange_collectors") or [])])
        errors: List[str] = []
        health: Dict[str, Any] = {}
        # 关键修复：不能让慢接口拖垮整条 exchange channel。
        # 使用分任务并发 + 总预算收敛，优先保住 ticker/order_book 等核心实时字段。
        defaults: Dict[str, Any] = {
            "ticker": {},
            "order_book": {},
            "open_interest": {},
            "funding_rate": None,
            "positions": [],
            "open_orders": [],
            "liquidation_proxy": {},
        }
        # 只为 enabled collector 创建任务，避免“已禁用的重接口”仍然被调用拖慢整包。
        task_specs: Dict[str, asyncio.Task] = {}
        if "ticker" in enabled:
            task_specs["ticker"] = asyncio.create_task(
                self._fetch_safe(
                    "exch.ticker",
                    self.get_ticker(symbol),
                    timeout_sec=self._collector_timeout("exch.ticker", cfg),
                    default={},
                    health=health,
                    errors=errors,
                )
            )
        if "order_book" in enabled:
            task_specs["order_book"] = asyncio.create_task(
                self._fetch_safe(
                    "exch.order_book",
                    self.get_order_book(symbol, depth=20),
                    timeout_sec=self._collector_timeout("exch.order_book", cfg),
                    default={},
                    health=health,
                    errors=errors,
                )
            )
        if "open_interest" in enabled:
            task_specs["open_interest"] = asyncio.create_task(
                self._fetch_safe(
                    "exch.open_interest",
                    self.get_open_interest(symbol),
                    timeout_sec=self._collector_timeout("exch.open_interest", cfg),
                    default={},
                    health=health,
                    errors=errors,
                )
            )
        if "funding_rate" in enabled:
            task_specs["funding_rate"] = asyncio.create_task(
                self._fetch_safe(
                    "exch.funding_rate",
                    self.get_funding_rate(symbol),
                    timeout_sec=self._collector_timeout("exch.funding_rate", cfg),
                    default=None,
                    health=health,
                    errors=errors,
                )
            )
        if "positions" in enabled:
            task_specs["positions"] = asyncio.create_task(
                self._fetch_safe(
                    "exch.positions",
                    self.get_positions(),
                    timeout_sec=self._collector_timeout("exch.positions", cfg),
                    default=[],
                    health=health,
                    errors=errors,
                )
            )
        if "open_orders" in enabled:
            task_specs["open_orders"] = asyncio.create_task(
                self._fetch_safe(
                    "exch.open_orders",
                    self.get_open_orders(symbol=None),
                    timeout_sec=self._collector_timeout("exch.open_orders", cfg),
                    default=[],
                    health=health,
                    errors=errors,
                )
            )
        if "liquidation_proxy" in enabled:
            task_specs["liquidation_proxy"] = asyncio.create_task(
                self._fetch_safe(
                    "exch.liq_proxy",
                    self.get_liquidation_proxy(symbol),
                    timeout_sec=self._collector_timeout("exch.liq_proxy", cfg),
                    default={},
                    health=health,
                    errors=errors,
                )
            )
        budget_sec = float(os.getenv("OPENCLAW_DATA_HUB_EXCHANGE_BUDGET_SEC", "12") or "12")
        budget_sec = max(4.0, min(budget_sec, 20.0))
        done, pending = await asyncio.wait(set(task_specs.values()), timeout=budget_sec) if task_specs else (set(), set())
        results: Dict[str, Any] = dict(defaults)
        for name, task in task_specs.items():
            if task in done:
                try:
                    results[name] = task.result()
                except Exception:
                    results[name] = defaults[name]
            else:
                task.cancel()
                errors.append(f"exch.{name}:budget_timeout")
                if isinstance(health.get(f"exch.{name}"), dict):
                    health[f"exch.{name}"]["status"] = "budget_timeout"
                else:
                    health[f"exch.{name}"] = {"status": "budget_timeout", "latency_ms": int(budget_sec * 1000)}
        ticker = results["ticker"]
        orderbook = results["order_book"]
        oi = results["open_interest"]
        fr = results["funding_rate"]
        positions = results["positions"]
        orders = results["open_orders"]
        liq_proxy = results["liquidation_proxy"]

        # Optional: include 1h klines so downstream analyzers (MI/gates) can reuse snapshot.
        klines_1h: List[Dict[str, Any]] = []
        if bool(cfg.get("include_klines_1h", True)) and "klines_1h" in enabled:
            klines_1h = await self._fetch_safe(
                "exch.klines_1h",
                self.get_klines(symbol, interval="1H", limit=int(cfg.get("klines_1h_limit", 64) or 64)),
                timeout_sec=self._collector_timeout("exch.klines_1h", cfg),
                default=[],
                health=health,
                errors=errors,
            )
        # Apply enabled filtering (keeps stable keys, but can drop heavy payloads)
        if "ticker" not in enabled:
            ticker = {}
        if "order_book" not in enabled:
            orderbook = {}
        if "open_interest" not in enabled:
            oi = {}
        if "funding_rate" not in enabled:
            fr = None
        if "positions" not in enabled:
            positions = []
        if "open_orders" not in enabled:
            orders = []
        if "liquidation_proxy" not in enabled:
            liq_proxy = {}
        # 当 ticker 短暂超时但 order_book 可用时，用盘口中间价兜底，避免整包质量被误判为“无价格”。
        if (not isinstance(ticker, dict) or not ticker.get("last")) and isinstance(orderbook, dict):
            bids = orderbook.get("bids") or []
            asks = orderbook.get("asks") or []
            if bids and asks:
                try:
                    best_bid = float(bids[0][0])
                    best_ask = float(asks[0][0])
                    mid = (best_bid + best_ask) / 2.0 if best_bid > 0 and best_ask > 0 else 0.0
                    if mid > 0:
                        ticker = {
                            "symbol": symbol,
                            "last": mid,
                            "price": mid,
                            "bid": best_bid,
                            "ask": best_ask,
                            "high": 0.0,
                            "low": 0.0,
                            "volume": 0.0,
                            "timestamp": datetime.now().isoformat(),
                            "source": "derived_order_book",
                        }
                except Exception:
                    pass
        ticker_quality_notes = self._exchange_ticker_quality_notes(symbol, ticker)
        return {
            "symbol": symbol,
            "ticker": ticker,
            "order_book": orderbook,
            "klines_1h": klines_1h,
            "open_interest": oi,
            "funding_rate": fr,
            "positions": positions,
            "open_orders": orders,
            "liquidation_proxy": liq_proxy,
            "timestamp": datetime.now().isoformat(),
            "collector": {
                "partial": bool(errors),
                "errors": errors[:30],
                "health": health,
                "enabled": sorted(enabled),
                "ticker_quality_notes": ticker_quality_notes,
            },
        }

    def _exchange_ticker_quality_notes(self, symbol: str, ticker: Dict[str, Any]) -> List[str]:
        """对 ETH 等主品种做轻量一致性检查，便于总控/质量分解释。"""
        notes: List[str] = []
        if not isinstance(ticker, dict):
            return notes
        sym_u = str(symbol or "").upper()
        last = float(ticker.get("last") or ticker.get("price") or 0.0)
        bid = float(ticker.get("bid") or 0.0)
        ask = float(ticker.get("ask") or 0.0)
        src = str(ticker.get("source") or "")
        if "ETH" in sym_u:
            if last > 0 and bid > 0 and ask > 0:
                spread = (ask - bid) / last
                if spread > 0.003:
                    notes.append(f"ETH 买卖价差偏大 relative_spread={spread:.5f}")
            if last > 0 and last < 50.0:
                notes.append("ETH 现价异常偏低，请核对 instId 与字段映射")
            if src == "fallback":
                notes.append("ETH 行情来源为 fallback，实盘决策前建议以 REST/交易所核对")
        return notes

    def _score_quality(self, exchange_channel: Dict[str, Any], intel_channel: Dict[str, Any]) -> Dict[str, Any]:
        score = 0.0
        reasons: List[str] = []
        enabled = set()
        try:
            enabled = set([str(x) for x in ((exchange_channel.get("collector") or {}).get("enabled") or [])])
        except Exception:
            enabled = set()
        t = exchange_channel.get("ticker") or {}
        px = float(t.get("price") or t.get("last") or 0.0)
        if px > 0:
            score += 0.35
        else:
            if (not enabled) or ("ticker" in enabled):
                reasons.append("交易所行情缺失")
        ex_col = exchange_channel.get("collector") or {}
        for note in ex_col.get("ticker_quality_notes") or []:
            if isinstance(note, str) and note:
                reasons.append(note)
        # 订单簿深度：只有在 collector 启用时才作为扣分项，避免在“禁用重接口保活”时被误判为低质量
        if (not enabled) or ("order_book" in enabled):
            if exchange_channel.get("order_book", {}).get("bids"):
                score += 0.2
            else:
                reasons.append("订单簿深度不足")
        if exchange_channel.get("positions") is not None:
            score += 0.15
        if intel_channel.get("health", {}).get("third_party", "").startswith("ok"):
            score += 0.15
        else:
            reasons.append("舆情/新闻通道退化")
        on_h = str((intel_channel.get("health", {}) or {}).get("onchain", "") or "")
        if on_h == "mock":
            reasons.append("链上通道为 mock（未配置真实链上 API）")
        elif on_h.startswith("ok"):
            score += 0.15
        else:
            reasons.append("链上通道退化")
        score = round(min(1.0, max(0.0, score)), 4)
        return {"score": score, "grade": "A" if score >= 0.85 else "B" if score >= 0.7 else "C" if score >= 0.5 else "D", "reasons": reasons}

    async def get_unified_snapshot(self, symbol: str) -> Dict[str, Any]:
        """统一快照：供策略/风控/执行/前端共享。"""
        cfg = await self._cfg()
        # bounded overall snapshot budget; per-field timeouts are handled inside collectors
        # NOTE: this is a control-plane API dependency (MarketIntelligenceEngine).
        # Keep it responsive by default; heavy collectors are already protected by per-collector timeouts.
        budget = float(cfg.get("snapshot_timeout_sec", 2.5) or 2.5)
        budget_cap = float(os.getenv("OPENCLAW_DATA_HUB_SNAPSHOT_BUDGET_CAP", "6") or "6")
        budget = max(1.5, min(budget, budget_cap))
        try:
            # 全局 budget 仅作为保护上限，不阻断已完成子通道结果。
            # 具体超时在各 collector 内部按字段分级处理，避免一次整体 timeout 导致整包清空。
            exchange_task = asyncio.create_task(self.get_exchange_channel(symbol))
            intel_task = asyncio.create_task(self.get_intel_channel(symbol))
            done, pending = await asyncio.wait({exchange_task, intel_task}, timeout=budget)
            exchange_channel = exchange_task.result() if exchange_task in done else {}
            intel_channel = intel_task.result() if intel_task in done else {}
            for task in pending:
                task.cancel()
        except Exception as e:
            logger.warning("DataSourceHub unified snapshot degraded: %s", e)
            exchange_channel, intel_channel = {}, {}
        whale_summary = {
            "链上大户活跃条数": len(intel_channel.get("onchain", {}).get("whales", []) or []),
            "链上净流入流出样本": len(intel_channel.get("onchain", {}).get("flows", []) or []),
            "盘口大单监控": {},
        }
        quality = self._score_quality(exchange_channel, intel_channel)
        provenance = "live"
        if quality["score"] < 0.85:
            provenance = "mixed"
        if quality["score"] < 0.5:
            provenance = "degraded"
        alerts: List[Dict[str, Any]] = []
        if quality["score"] < 0.5:
            alerts.append(
                {
                    "级别": "warning",
                    "标题": "数据质量偏低",
                    "消息": f"{symbol} 数据质量分 {quality['score']:.2f}，建议谨慎交易并关注多渠道确认。",
                    "建议渠道": ["前端总控", "Telegram", "消息推送"],
                }
            )
        snapshot = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "渠道A_交易所实时执行数据": exchange_channel,
            "渠道B_链上新闻舆情数据": intel_channel,
            "大资金与大户监控": whale_summary,
            "数据质量评估": quality,
            "监控告警": alerts,
            "数据来源状态": {
                "provenance": provenance,
                "说明": "live=主要实时数据, mixed=部分降级, degraded=需谨慎使用",
            },
        }
        # Extra provider plugins: run in parallel and use cache fallback.
        # Goal: external providers should enrich snapshot, never drag the control-plane latency.
        extras: Dict[str, Any] = {}
        plugins = self._get_data_provider_plugins()
        req = set([str(x) for x in (cfg.get("extra_providers") or [])])
        extra_health = ((exchange_channel.get("collector") or {}).get("health") if isinstance(exchange_channel, dict) else None)
        extra_errors = ((exchange_channel.get("collector") or {}).get("errors") if isinstance(exchange_channel, dict) else None)
        tasks: Dict[str, asyncio.Task] = {}
        for name, fn in (plugins or {}).items():
            if req and str(name) not in req:
                continue
            if not callable(fn):
                continue
            # plugin signature: async fn(symbol) -> dict
            tasks[str(name)] = asyncio.create_task(
                self._fetch_safe(
                    f"extra.{name}",
                    fn(symbol),
                    default={},
                    health=extra_health,
                    errors=extra_errors,
                )
            )
        if tasks:
            extra_budget = float(os.getenv("OPENCLAW_DATA_HUB_EXTRA_BUDGET_SEC", "4.0") or "4.0")
            extra_budget = max(1.0, min(extra_budget, 8.0))
            done, pending = await asyncio.wait(set(tasks.values()), timeout=extra_budget)
            for name, task in tasks.items():
                cache_key = f"extra:{name}:{symbol}"
                value: Dict[str, Any] = {}
                if task in done:
                    try:
                        raw = task.result()
                        if isinstance(raw, dict):
                            value = raw
                    except Exception:
                        value = {}
                else:
                    task.cancel()
                    if isinstance(extra_errors, list):
                        extra_errors.append(f"extra.{name}:budget_timeout")
                # cache only non-empty payloads
                if isinstance(value, dict) and value:
                    self._cache_set(cache_key, value)
                else:
                    cached = self._cache_get(
                        cache_key,
                        ttl_sec=float(os.getenv("OPENCLAW_DATA_HUB_EXTRA_CACHE_TTL_SEC", "900") or "900"),
                    )
                    if isinstance(cached, dict) and cached:
                        value = dict(cached)
                        value.setdefault("cache_fallback", True)
                extras[name] = value if isinstance(value, dict) else {}
        if extras:
            snapshot["扩展数据"] = self._sanitize(extras)

        # Promote provider health summary for frontends/analysis modules
        try:
            prov = snapshot.get("数据来源状态") if isinstance(snapshot, dict) else None
            if isinstance(prov, dict):
                prov["providers"] = {
                    "exchange": (exchange_channel.get("collector") if isinstance(exchange_channel, dict) else {}),
                    "intel": (intel_channel.get("collector") if isinstance(intel_channel, dict) else {}),
                    "extra": list(extras.keys()),
                }
        except Exception:
            pass
        try:
            advice = self.quality_advisor.evaluate(symbol=symbol, snapshot=snapshot)
            snapshot["数据质量与作用评分"] = advice.to_dict()
        except Exception:
            snapshot["数据质量与作用评分"] = {
                "symbol": symbol,
                "timestamp": datetime.now().isoformat(),
                "grade": "N/A",
                "suggestions": ["评分顾问暂不可用，建议检查数据质量顾问模块日志。"],
            }
        return snapshot

    async def status(self) -> DataSourceHubStatus:
        exchange = self._get_exchange()
        return DataSourceHubStatus(
            healthy=bool(exchange),
            provider="exchange" if exchange else "fallback",
            timestamp=datetime.now().isoformat(),
        )
