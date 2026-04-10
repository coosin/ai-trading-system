"""
统一数据源模块管理中心。

双渠道：
1) 交易执行数据渠道（OKX/Binance 等交易所）
2) 外部情报数据渠道（链上/新闻/舆情）
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from src.modules.data.data_quality_advisor import DataQualityAdvisor


@dataclass
class DataSourceHubStatus:
    healthy: bool
    provider: str
    timestamp: str


class DataSourceHub:
    """数据源统一编排入口（轻量 facade）。"""

    def __init__(self, main_controller: Any = None):
        self.main_controller = main_controller
        self.quality_advisor = DataQualityAdvisor(window_size=80)

    async def _cfg(self) -> Dict[str, Any]:
        """
        AI-managed config entrypoint (optional).
        Falls back to safe defaults when config manager is unavailable.
        """
        mc = self.main_controller
        defaults = {
            "enable_legacy_external_analysis": False,
            "fetch_timeout_sec": 2.8,
            "snapshot_timeout_sec": 6.0,
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
                return cfg if isinstance(cfg, dict) else dict(defaults)
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
        mc = self.main_controller
        if not mc:
            return None
        engine = getattr(mc, "ai_trading_engine", None)
        ex = getattr(engine, "exchange", None) if engine else None
        # fallback: some deployments mount exchange directly on main_controller
        return ex or getattr(mc, "okx_exchange", None) or getattr(mc, "exchange", None)

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
        mc = self.main_controller
        plugins = getattr(mc, "data_provider_plugins", None) if mc else None
        return plugins if isinstance(plugins, dict) else {}

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
        if exchange and hasattr(exchange, "get_ticker"):
            try:
                ticker = await exchange.get_ticker(symbol)
                if ticker:
                    last = float(ticker.get("last") or ticker.get("close") or 0.0)
                    return {
                        "symbol": symbol,
                        "last": last,
                        "price": last,
                        "bid": float(ticker.get("bid") or ticker.get("bidPx") or 0.0),
                        "ask": float(ticker.get("ask") or ticker.get("askPx") or 0.0),
                        "high": float(ticker.get("high") or ticker.get("high24h") or 0.0),
                        "low": float(ticker.get("low") or ticker.get("low24h") or 0.0),
                        "volume": float(ticker.get("volume") or ticker.get("quoteVolume") or ticker.get("vol24h") or 0.0),
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
        if exchange and hasattr(exchange, "get_order_book"):
            try:
                ob = await exchange.get_order_book(symbol, depth=depth)
                if ob:
                    bids = ob.bids if hasattr(ob, "bids") else ob.get("bids", [])
                    asks = ob.asks if hasattr(ob, "asks") else ob.get("asks", [])
                    return {
                        "symbol": symbol,
                        "bids": [[float(x[0]), float(x[1])] for x in bids[:depth]],
                        "asks": [[float(x[0]), float(x[1])] for x in asks[:depth]],
                        "timestamp": datetime.now().isoformat(),
                        "source": "exchange",
                    }
            except Exception:
                pass
        return {"symbol": symbol, "bids": [], "asks": [], "timestamp": datetime.now().isoformat(), "source": "fallback"}

    async def get_positions(self) -> List[Dict[str, Any]]:
        exchange = self._get_exchange()
        if exchange and hasattr(exchange, "get_positions"):
            try:
                positions = await exchange.get_positions()
                if isinstance(positions, list):
                    return self._sanitize(positions)
            except Exception:
                pass
        return []

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        exchange = self._get_exchange()
        if exchange and hasattr(exchange, "get_open_orders"):
            try:
                orders = await exchange.get_open_orders(symbol)
                if isinstance(orders, list):
                    return self._sanitize(orders)
            except Exception:
                pass
        return []

    async def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        exchange = self._get_exchange()
        if exchange and hasattr(exchange, "get_open_interest"):
            try:
                oi = await exchange.get_open_interest(symbol)
                if isinstance(oi, dict):
                    return self._sanitize(oi)
            except Exception:
                pass
        return {}

    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        exchange = self._get_exchange()
        if exchange and hasattr(exchange, "get_funding_rate"):
            try:
                fr = await exchange.get_funding_rate(symbol)
                return float(fr) if fr is not None else None
            except Exception:
                pass
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
        return {
            "symbol": symbol,
            "positions_considered": len(matched),
            "high_risk_positions": high_risk,
            "samples": samples[:10],
            "source": "position_proxy",
            "timestamp": datetime.now().isoformat(),
        }

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
            out["health"]["onchain"] = "ok" if sentiment is not None else "degraded"

        third = self._get_third_party_integrator()
        if third and any(k.startswith("third_party.") for k in enabled):
            cs = await self._fetch_safe(
                "third_party.sentiment",
                third.get_comprehensive_sentiment(symbol),
                default={},
                health=health,
                errors=errors,
            )
            out["sentiment"] = self._sanitize(cs or {})
            out["health"]["third_party"] = "ok" if cs else "degraded"
            news = await self._fetch_safe(
                "third_party.news",
                third.get_news_sentiment(symbol),
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

        # collect concurrently; keep best-effort semantics
        ticker, orderbook, oi, fr, positions, orders, liq_proxy = await asyncio.gather(
            self._fetch_safe("exch.ticker", self.get_ticker(symbol), default={}, health=health, errors=errors),
            self._fetch_safe("exch.order_book", self.get_order_book(symbol, depth=20), default={}, health=health, errors=errors),
            self._fetch_safe("exch.open_interest", self.get_open_interest(symbol), default={}, health=health, errors=errors),
            self._fetch_safe("exch.funding_rate", self.get_funding_rate(symbol), default=None, health=health, errors=errors),
            self._fetch_safe("exch.positions", self.get_positions(), default=[], health=health, errors=errors),
            self._fetch_safe("exch.open_orders", self.get_open_orders(symbol=None), default=[], health=health, errors=errors),
            self._fetch_safe("exch.liq_proxy", self.get_liquidation_proxy(symbol), default={}, health=health, errors=errors),
        )

        # Optional: include 1h klines so downstream analyzers (MI/gates) can reuse snapshot.
        klines_1h: List[Dict[str, Any]] = []
        if bool(cfg.get("include_klines_1h", True)) and "klines_1h" in enabled:
            klines_1h = await self._fetch_safe(
                "exch.klines_1h",
                self.get_klines(symbol, interval="1H", limit=int(cfg.get("klines_1h_limit", 64) or 64)),
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
            },
        }

    def _score_quality(self, exchange_channel: Dict[str, Any], intel_channel: Dict[str, Any]) -> Dict[str, Any]:
        score = 0.0
        reasons: List[str] = []
        if float(exchange_channel.get("ticker", {}).get("price") or 0.0) > 0:
            score += 0.35
        else:
            reasons.append("交易所行情缺失")
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
        if intel_channel.get("health", {}).get("onchain", "").startswith("ok"):
            score += 0.15
        else:
            reasons.append("链上通道退化")
        score = round(min(1.0, max(0.0, score)), 4)
        return {"score": score, "grade": "A" if score >= 0.85 else "B" if score >= 0.7 else "C" if score >= 0.5 else "D", "reasons": reasons}

    async def get_unified_snapshot(self, symbol: str) -> Dict[str, Any]:
        """统一快照：供策略/风控/执行/前端共享。"""
        cfg = await self._cfg()
        # bounded overall snapshot budget; per-field timeouts are handled inside collectors
        budget = float(cfg.get("snapshot_timeout_sec", 6.0) or 6.0)
        try:
            exchange_channel, intel_channel = await asyncio.wait_for(
                asyncio.gather(self.get_exchange_channel(symbol), self.get_intel_channel(symbol)),
                timeout=budget,
            )
        except Exception:
            # degraded: return minimal skeleton
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
        # Extra provider plugins (reserved for future add/remove)
        extras: Dict[str, Any] = {}
        plugins = self._get_data_provider_plugins()
        req = set([str(x) for x in (cfg.get("extra_providers") or [])])
        for name, fn in (plugins or {}).items():
            if req and str(name) not in req:
                continue
            if not callable(fn):
                continue
            # plugin signature: async fn(symbol) -> dict
            extras[str(name)] = await self._fetch_safe(
                f"extra.{name}",
                fn(symbol),
                default={},
                health=((exchange_channel.get("collector") or {}).get("health") if isinstance(exchange_channel, dict) else None),
                errors=((exchange_channel.get("collector") or {}).get("errors") if isinstance(exchange_channel, dict) else None),
            )
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
