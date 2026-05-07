"""
多源数据融合模块

整合多个数据源的数据，提供统一的数据访问接口
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class DataSourceType(Enum):
    """数据源类型"""
    EXCHANGE = "exchange"
    MARKET_DATA = "market_data"
    NEWS = "news"
    SOCIAL = "social"
    ONCHAIN = "onchain"
    TECHNICAL = "technical"


@dataclass
class DataPoint:
    """数据点"""
    source: str
    source_type: DataSourceType
    timestamp: datetime
    symbol: Optional[str] = None
    value: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FusedData:
    """融合数据"""
    symbol: str
    timestamp: datetime
    price: Optional[float] = None
    volume: Optional[float] = None
    sentiment: Optional[float] = None
    technical_indicators: Dict[str, float] = field(default_factory=dict)
    onchain_metrics: Dict[str, float] = field(default_factory=dict)
    news_sentiment: Optional[float] = None
    social_sentiment: Optional[float] = None
    confidence: float = 0.0
    sources: List[str] = field(default_factory=list)


class MultiSourceDataFusion:
    """多源数据融合器"""
    
    def __init__(self, data_integration=None, llm_integration=None, config: Optional[Dict] = None):
        self.data_integration = data_integration
        self.llm_integration = llm_integration
        self.config = config or {}
        
        self._sources: Dict[str, Any] = {}
        self._cache: Dict[str, FusedData] = {}
        self._cache_ttl = self.config.get("cache_ttl", 60)
        self._last_source_health: Dict[str, Dict[str, Any]] = {}
        
        self._fusion_weights = {
            "exchange": 0.4,
            "market_data": 0.3,
            "technical": 0.15,
            "sentiment": 0.1,
            "onchain": 0.05
        }

    def set_data_integration(self, data_integration: Any) -> None:
        """在 MainController 完成 DataIntegration 初始化后绑定（引擎早于 DataIntegration 创建）。"""
        self.data_integration = data_integration
    
    async def initialize(self) -> bool:
        """初始化数据融合器"""
        logger.info("多源数据融合器初始化完成")
        return True
    
    def register_source(self, name: str, source: Any, source_type: DataSourceType):
        """注册数据源"""
        self._sources[name] = {
            "source": source,
            "type": source_type
        }
        self._last_source_health.setdefault(name, {
            "status": "unknown",
            "last_ok_at": None,
            "last_error": "",
            "fail_count": 0,
            "quality_score": 0.0,
        })
        logger.info(f"注册数据源: {name} ({source_type.value})")

    def _mark_source_ok(self, name: str) -> None:
        stat = self._last_source_health.setdefault(name, {})
        stat["status"] = "ok"
        stat["last_ok_at"] = datetime.now().isoformat()
        stat["last_error"] = ""
        stat["fail_count"] = 0
        stat["quality_score"] = 1.0

    def _mark_source_fail(self, name: str, error: str) -> None:
        stat = self._last_source_health.setdefault(name, {})
        prev_fail = int(stat.get("fail_count", 0) or 0)
        fail_count = prev_fail + 1
        stat["status"] = "degraded"
        stat["last_error"] = str(error)
        stat["fail_count"] = fail_count
        # 连续失败指数衰减质量分，最低到 0.05，避免直接归零导致全盘无信号。
        stat["quality_score"] = max(0.05, 1.0 / (1.0 + fail_count))
    
    def register_data_source(self, name: str, source: Any, source_type: Optional[str] = None):
        """注册数据源（兼容接口）"""
        type_map = {
            "exchange": DataSourceType.EXCHANGE,
            "market_data": DataSourceType.MARKET_DATA,
            "news": DataSourceType.NEWS,
            "social": DataSourceType.SOCIAL,
            "onchain": DataSourceType.ONCHAIN,
            "technical": DataSourceType.TECHNICAL,
        }
        stype = type_map.get(source_type, DataSourceType.EXCHANGE) if source_type else DataSourceType.EXCHANGE
        self.register_source(name, source, stype)
    
    async def fetch_data(self, symbol: str, sources: Optional[List[str]] = None) -> List[DataPoint]:
        """从多个源获取数据"""
        data_points = []
        
        for name, source_info in self._sources.items():
            if sources and name not in sources:
                continue
            
            try:
                source = source_info["source"]
                if hasattr(source, 'get_market_data'):
                    data = await source.get_market_data(symbol)
                    if data:
                        self._mark_source_ok(name)
                        data_points.append(DataPoint(
                            source=name,
                            source_type=source_info["type"],
                            timestamp=datetime.now(),
                            symbol=symbol,
                            value=data
                        ))
                    else:
                        self._mark_source_fail(name, "empty_data")

                # 可选增强：若数据源支持订单簿/衍生品数据，则并行纳入融合输入
                if hasattr(source, "get_order_book"):
                    try:
                        ob = await source.get_order_book(symbol, depth=10)
                        if ob and getattr(ob, "bids", None) and getattr(ob, "asks", None):
                            best_bid = float(ob.bids[0][0])
                            best_ask = float(ob.asks[0][0])
                            bid_vol = sum(float(x[1]) for x in ob.bids[:5])
                            ask_vol = sum(float(x[1]) for x in ob.asks[:5])
                            spread_bps = ((best_ask - best_bid) / max(1e-9, best_bid)) * 10000.0
                            depth_imbalance = (bid_vol - ask_vol) / max(1e-9, bid_vol + ask_vol)
                            data_points.append(DataPoint(
                                source=f"{name}:orderbook",
                                source_type=source_info["type"],
                                timestamp=datetime.now(),
                                symbol=symbol,
                                value={
                                    "spread_bps": spread_bps,
                                    "depth_imbalance": depth_imbalance,
                                    "bid_volume_top5": bid_vol,
                                    "ask_volume_top5": ask_vol,
                                },
                                metadata={"kind": "orderbook"},
                            ))
                    except Exception as e:
                        logger.debug(f"从 {name} 获取订单簿失败: {e}")

                if hasattr(source, "get_open_interest") or hasattr(source, "get_funding_rate"):
                    try:
                        derivatives: Dict[str, Any] = {}
                        if hasattr(source, "get_open_interest"):
                            oi = await source.get_open_interest(symbol)
                            if isinstance(oi, dict):
                                derivatives.update(oi)
                        if hasattr(source, "get_funding_rate"):
                            fr = await source.get_funding_rate(symbol)
                            if fr is not None:
                                derivatives["funding_rate"] = float(fr)
                        if derivatives:
                            data_points.append(DataPoint(
                                source=f"{name}:derivatives",
                                source_type=source_info["type"],
                                timestamp=datetime.now(),
                                symbol=symbol,
                                value=derivatives,
                                metadata={"kind": "derivatives"},
                            ))
                    except Exception as e:
                        logger.debug(f"从 {name} 获取衍生品数据失败: {e}")
            except Exception as e:
                self._mark_source_fail(name, str(e))
                logger.warning(f"从 {name} 获取数据失败: {e}")
        
        return data_points
    
    async def fuse_data(self, symbol: str, data_points: List[DataPoint]) -> FusedData:
        """融合多个数据源的数据"""
        fused = FusedData(
            symbol=symbol,
            timestamp=datetime.now()
        )
        
        prices = []
        volumes = []
        sentiments = []
        sentiment_weights = []
        
        for dp in data_points:
            fused.sources.append(dp.source)
            
            if dp.value:
                # 兼容两类输入：
                # 1) dict（期望包含 price/volume/sentiment）
                # 2) MarketData dataclass（price/volume/change_24h）
                if isinstance(dp.value, dict):
                    if dp.metadata.get("kind") == "orderbook":
                        if "spread_bps" in dp.value:
                            fused.technical_indicators["spread_bps"] = float(dp.value.get("spread_bps") or 0.0)
                        if "depth_imbalance" in dp.value:
                            fused.technical_indicators["depth_imbalance"] = float(dp.value.get("depth_imbalance") or 0.0)
                        continue
                    if dp.metadata.get("kind") == "derivatives":
                        if "open_interest" in dp.value:
                            fused.onchain_metrics["open_interest"] = float(dp.value.get("open_interest") or 0.0)
                        if "volume_24h" in dp.value:
                            fused.onchain_metrics["oi_volume_24h"] = float(dp.value.get("volume_24h") or 0.0)
                        if "funding_rate" in dp.value:
                            fused.onchain_metrics["funding_rate"] = float(dp.value.get("funding_rate") or 0.0)
                        continue
                    if "price" in dp.value:
                        prices.append(dp.value["price"])
                    if "volume" in dp.value:
                        volumes.append(dp.value["volume"])
                    # Sentiment weighting: prefer explicit sentiment over coarse price-change proxy.
                    src_kind = str(dp.source_type.value if hasattr(dp.source_type, "value") else dp.source_type or "")
                    if "sentiment" in dp.value and dp.value["sentiment"] is not None:
                        try:
                            s = float(dp.value["sentiment"])
                            s = max(-1.0, min(1.0, s))
                            w = 1.0 if src_kind not in ("exchange", "market_data") else 0.8
                            sentiments.append(s)
                            sentiment_weights.append(w)
                        except Exception:
                            pass
                    elif "change_24h" in dp.value and dp.value.get("change_24h") is not None:
                        # 用 24h 变化率粗略映射情绪：正向->正，负向->负
                        try:
                            s = float(dp.value.get("change_24h")) / 5.0
                            s = max(-1.0, min(1.0, s))
                            sentiments.append(s)
                            sentiment_weights.append(0.6)
                        except Exception:
                            pass
                else:
                    price = getattr(dp.value, "price", None)
                    volume = getattr(dp.value, "volume", None)
                    change_24h = getattr(dp.value, "change_24h", None)
                    if price is not None:
                        prices.append(price)
                    if volume is not None:
                        volumes.append(volume)
                    if change_24h is not None:
                        try:
                            # change_24h 通常是百分比（例如 2.3 / -1.1）
                            # 归一化到 [-1, 1] 区间，给 LLM 更稳定的数值范围
                            s = float(change_24h) / 5.0
                            s = max(-1.0, min(1.0, s))
                            sentiments.append(s)
                            sentiment_weights.append(0.6)
                        except Exception:
                            pass
        
        if prices:
            fused.price = sum(prices) / len(prices)
        if volumes:
            fused.volume = sum(volumes) / len(volumes)
        if sentiments:
            if sentiment_weights and len(sentiment_weights) == len(sentiments):
                sw = sum(sentiment_weights) or 1.0
                fused.sentiment = sum(s * w for s, w in zip(sentiments, sentiment_weights)) / sw
            else:
                fused.sentiment = sum(sentiments) / len(sentiments)
        
        # 置信度按“可用数据源数量/已注册数据源数量”归一化，
        # 避免因为写死分母导致即便多源都返回仍长期偏低。
        total_sources = len(self._sources) if self._sources else 1
        base_conf = float(min(1.0, len(data_points) / max(1, total_sources)))
        source_health_scores = []
        for dp in data_points:
            src_base = str(dp.source or "").split(":", 1)[0]
            health = self._last_source_health.get(src_base, {})
            try:
                source_health_scores.append(float(health.get("quality_score", 1.0) or 1.0))
            except Exception:
                source_health_scores.append(1.0)
        health_factor = (sum(source_health_scores) / len(source_health_scores)) if source_health_scores else 1.0
        evidence_bonus = 0.0
        # Evidence bonus should not inflate confidence for a single-source snapshot.
        # Keep 1/N baseline for unit tests and for "only one feed is available" scenarios.
        if len(data_points) >= 2 and fused.sentiment is not None and abs(float(fused.sentiment)) >= 0.12:
            evidence_bonus += 0.08
        if fused.technical_indicators.get("spread_bps") is not None:
            evidence_bonus += 0.05
        if fused.technical_indicators.get("depth_imbalance") is not None:
            evidence_bonus += 0.05
        fused.confidence = float(max(0.0, min(1.0, base_conf * health_factor + evidence_bonus)))
        
        return fused
    
    async def get_fused_data(self, symbol: str) -> Optional[FusedData]:
        """获取融合数据"""
        cache_key = f"{symbol}_{datetime.now().strftime('%Y%m%d%H%M')}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        data_points = await self.fetch_data(symbol)
        if not data_points:
            return None
        
        fused = await self.fuse_data(symbol, data_points)
        self._cache[cache_key] = fused
        
        return fused
    
    async def analyze_correlations(self, symbols: List[str]) -> Dict[str, float]:
        """分析多个资产之间的相关性"""
        correlations = {}
        
        for i, sym1 in enumerate(symbols):
            for sym2 in symbols[i+1:]:
                key = f"{sym1}_{sym2}"
                correlations[key] = 0.0
        
        return correlations
    
    def get_source_status(self) -> Dict[str, Dict[str, Any]]:
        """获取数据源状态"""
        status = {
            name: {
                "type": info["type"].value,
                "status": "active"
            }
            for name, info in self._sources.items()
        }
        for name, health in self._last_source_health.items():
            if name in status:
                status[name]["health"] = dict(health)
        return status
    
    async def analyze_market(self, symbol: str) -> Dict[str, Any]:
        """
        分析市场数据
        
        Args:
            symbol: 交易对符号
        
        Returns:
            市场分析结果
        """
        result = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "price": None,
            "volume": None,
            "sentiment": None,
            "trend": "unknown",
            "volatility": 0.0,
            "confidence": 0.0,
            "sources": [],
            "quality_score": 0.0,
            "degraded_sources": [],
            "source_health": {},
        }
        
        try:
            fused_data = await self.get_fused_data(symbol)
            if fused_data:
                result["price"] = fused_data.price
                result["volume"] = fused_data.volume
                result["sentiment"] = fused_data.sentiment
                result["confidence"] = fused_data.confidence
                result["sources"] = fused_data.sources
                result["source_health"] = self.get_source_status()
                degraded_sources = [
                    n for n, s in result["source_health"].items()
                    if isinstance(s, dict) and isinstance(s.get("health"), dict) and s["health"].get("status") == "degraded"
                ]
                result["degraded_sources"] = degraded_sources
                source_quality = []
                for n in result["sources"]:
                    health = (result["source_health"].get(n) or {}).get("health", {})
                    source_quality.append(float(health.get("quality_score", 1.0) or 1.0))
                quality_score = (sum(source_quality) / len(source_quality)) if source_quality else 0.0
                result["quality_score"] = max(0.0, min(1.0, quality_score))
                
                # 优先用技术指标；若缺失则退化为“情绪+24h动量”方向判定，避免长期 neutral。
                if fused_data.technical_indicators:
                    rsi = fused_data.technical_indicators.get("rsi", 50)
                    if rsi > 70:
                        result["trend"] = "overbought"
                    elif rsi < 30:
                        result["trend"] = "oversold"
                    else:
                        result["trend"] = "neutral"
                    result["volatility"] = fused_data.technical_indicators.get("atr", 0)
                    if "spread_bps" in fused_data.technical_indicators:
                        result["spread_bps"] = fused_data.technical_indicators.get("spread_bps", 0)
                    if "depth_imbalance" in fused_data.technical_indicators:
                        result["depth_imbalance"] = fused_data.technical_indicators.get("depth_imbalance", 0)
                if result.get("trend") in (None, "unknown", "neutral"):
                    sent = result.get("sentiment")
                    try:
                        sf = float(sent) if sent is not None else 0.0
                    except Exception:
                        sf = 0.0
                    if sf >= 0.10:
                        result["trend"] = "bullish"
                    elif sf <= -0.10:
                        result["trend"] = "bearish"
                    else:
                        result["trend"] = "neutral"
                if fused_data.onchain_metrics:
                    result["open_interest"] = fused_data.onchain_metrics.get("open_interest")
                    result["funding_rate"] = fused_data.onchain_metrics.get("funding_rate")
        except Exception as e:
            logger.warning(f"市场分析失败: {e}")
        
        return result
