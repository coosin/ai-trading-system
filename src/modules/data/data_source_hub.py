"""
统一数据源模块管理中心。

双渠道：
1) 交易执行数据渠道（OKX/Binance 等交易所）
2) 外部情报数据渠道（链上/新闻/舆情）
"""

from __future__ import annotations

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

    def _get_exchange(self) -> Any:
        mc = self.main_controller
        if not mc:
            return None
        engine = getattr(mc, "ai_trading_engine", None)
        return getattr(engine, "exchange", None) if engine else None

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

    async def analyze_market(self, symbol: str) -> Dict[str, Any]:
        mc = self.main_controller
        if mc and hasattr(mc, "data_fusion_analyzer") and mc.data_fusion_analyzer:
            result = await mc.data_fusion_analyzer.analyze_market(symbol)
            return result if isinstance(result, dict) else {"result": result}

        analyzer = self._get_market_analyzer()
        plugin_analysis: Dict[str, Any] = {}
        if analyzer and hasattr(analyzer, "analyze_symbol"):
            try:
                plugin_analysis = self._sanitize(await analyzer.analyze_symbol(symbol))
            except Exception:
                plugin_analysis = {}

        # fallback: hub-level lightweight fusion
        ticker = await self.get_ticker(symbol)
        trend = await self.analyze_trends(symbol)
        signal = await self.get_signals(symbol)
        return {
            "symbol": symbol,
            "overall_sentiment": trend.get("trend", "unknown"),
            "signal_strength": round(float(signal.get("confidence", 0.0)) * 5, 2),
            "recommendation": signal.get("signal", "hold"),
            "confidence": signal.get("confidence", 0.0),
            "market_snapshot": ticker,
            "market_analyzer": plugin_analysis,
            "source": "hub_fallback",
            "timestamp": datetime.now().isoformat(),
        }

    async def get_intel_channel(self, symbol: str) -> Dict[str, Any]:
        """渠道B：链上 + 新闻 + 舆情。"""
        out: Dict[str, Any] = {
            "symbol": symbol,
            "onchain": {},
            "sentiment": {},
            "news": {},
            "health": {"onchain": "missing", "third_party": "missing"},
            "timestamp": datetime.now().isoformat(),
        }

        onchain = self._get_onchain_integrator()
        if onchain:
            try:
                sentiment = await onchain.analyze_onchain_sentiment(symbol)
                flows = await onchain.get_exchange_flows(symbol)
                whales = await onchain.get_whale_activities(symbol, limit=20)
                out["onchain"] = self._sanitize({"sentiment": sentiment, "flows": flows, "whales": whales})
                out["health"]["onchain"] = "ok"
            except Exception as e:
                out["health"]["onchain"] = f"degraded:{e}"

        third = self._get_third_party_integrator()
        if third:
            try:
                cs = await third.get_comprehensive_sentiment(symbol)
                out["sentiment"] = self._sanitize(cs)
                out["health"]["third_party"] = "ok"
            except Exception as e:
                out["health"]["third_party"] = f"degraded:{e}"
            try:
                out["news"] = self._sanitize(await third.get_news_sentiment(symbol))
            except Exception:
                pass
        return out

    async def get_exchange_channel(self, symbol: str) -> Dict[str, Any]:
        """渠道A：交易所实时/账户/执行相关。"""
        ticker = await self.get_ticker(symbol)
        orderbook = await self.get_order_book(symbol, depth=20)
        oi = await self.get_open_interest(symbol)
        fr = await self.get_funding_rate(symbol)
        positions = await self.get_positions()
        orders = await self.get_open_orders(symbol=None)
        liq_proxy = await self.get_liquidation_proxy(symbol)
        return {
            "symbol": symbol,
            "ticker": ticker,
            "order_book": orderbook,
            "open_interest": oi,
            "funding_rate": fr,
            "positions": positions,
            "open_orders": orders,
            "liquidation_proxy": liq_proxy,
            "timestamp": datetime.now().isoformat(),
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
        exchange_channel = await self.get_exchange_channel(symbol)
        intel_channel = await self.get_intel_channel(symbol)
        analysis = await self.analyze_market(symbol)
        whale_summary = {
            "链上大户活跃条数": len(intel_channel.get("onchain", {}).get("whales", []) or []),
            "链上净流入流出样本": len(intel_channel.get("onchain", {}).get("flows", []) or []),
            "盘口大单监控": (
                analysis.get("market_analyzer", {}).get("big_orders", {})
                if isinstance(analysis, dict)
                else {}
            ),
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
            "统一分析判断": analysis,
            "大资金与大户监控": whale_summary,
            "数据质量评估": quality,
            "监控告警": alerts,
            "数据来源状态": {
                "provenance": provenance,
                "说明": "live=主要实时数据, mixed=部分降级, degraded=需谨慎使用",
            },
        }
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
        snapshot["AI智能分析"] = await self.get_ai_analysis(symbol=symbol, snapshot=snapshot)
        return snapshot

    async def get_ai_analysis(self, symbol: str, snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """将统一数据交给 AI 智能分析，生成跨接口可复用结论。"""
        snap = snapshot if isinstance(snapshot, dict) else await self.get_unified_snapshot(symbol)
        llm = self._get_llm_integration()
        if llm and hasattr(llm, "analyze_market"):
            try:
                payload = {
                    "symbol": symbol,
                    "snapshot": snap,
                    "quality": snap.get("数据质量评估", {}),
                    "advisor": snap.get("数据质量与作用评分", {}),
                }
                ai = await llm.analyze_market(payload)
                if isinstance(ai, dict):
                    return {
                        "source": "llm",
                        "summary": ai.get("summary") or ai.get("reasoning") or "AI分析完成",
                        "trend": ai.get("trend"),
                        "sentiment": ai.get("sentiment"),
                        "risk_level": ai.get("risk_level"),
                        "action_bias": ai.get("signal") or ai.get("action") or ai.get("recommendation"),
                        "confidence": ai.get("confidence"),
                        "raw": ai,
                        "timestamp": datetime.now().isoformat(),
                    }
            except Exception:
                pass

        # fallback: rule-based concise AI-style summary
        q = ((snap.get("数据质量评估") or {}).get("score")) if isinstance(snap, dict) else None
        trend = ((snap.get("统一分析判断") or {}).get("overall_sentiment")) if isinstance(snap, dict) else "unknown"
        rec = ((snap.get("统一分析判断") or {}).get("recommendation")) if isinstance(snap, dict) else "hold"
        conf = ((snap.get("数据质量与作用评分") or {}).get("confidence")) if isinstance(snap, dict) else None
        msg = f"基于统一数据快照，当前趋势={trend}，建议倾向={rec}。"
        if q is not None:
            msg += f" 数据质量分={q}。"
        return {
            "source": "hub_fallback",
            "summary": msg,
            "trend": trend,
            "action_bias": rec,
            "confidence": conf,
            "timestamp": datetime.now().isoformat(),
        }

    async def status(self) -> DataSourceHubStatus:
        exchange = self._get_exchange()
        return DataSourceHubStatus(
            healthy=bool(exchange),
            provider="exchange" if exchange else "fallback",
            timestamp=datetime.now().isoformat(),
        )
