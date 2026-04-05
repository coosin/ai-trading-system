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
        
        self._fusion_weights = {
            "exchange": 0.4,
            "market_data": 0.3,
            "technical": 0.15,
            "sentiment": 0.1,
            "onchain": 0.05
        }
    
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
        logger.info(f"注册数据源: {name} ({source_type.value})")
    
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
                        data_points.append(DataPoint(
                            source=name,
                            source_type=source_info["type"],
                            timestamp=datetime.now(),
                            symbol=symbol,
                            value=data
                        ))
            except Exception as e:
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
        
        for dp in data_points:
            fused.sources.append(dp.source)
            
            if dp.value:
                if isinstance(dp.value, dict):
                    if "price" in dp.value:
                        prices.append(dp.value["price"])
                    if "volume" in dp.value:
                        volumes.append(dp.value["volume"])
                    if "sentiment" in dp.value:
                        sentiments.append(dp.value["sentiment"])
        
        if prices:
            fused.price = sum(prices) / len(prices)
        if volumes:
            fused.volume = sum(volumes) / len(volumes)
        if sentiments:
            fused.sentiment = sum(sentiments) / len(sentiments)
        
        fused.confidence = min(1.0, len(data_points) / 5.0)
        
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
        return {
            name: {
                "type": info["type"].value,
                "status": "active"
            }
            for name, info in self._sources.items()
        }
    
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
            "sources": []
        }
        
        try:
            fused_data = await self.get_fused_data(symbol)
            if fused_data:
                result["price"] = fused_data.price
                result["volume"] = fused_data.volume
                result["sentiment"] = fused_data.sentiment
                result["confidence"] = fused_data.confidence
                result["sources"] = fused_data.sources
                
                if fused_data.price and fused_data.technical_indicators:
                    rsi = fused_data.technical_indicators.get("rsi", 50)
                    if rsi > 70:
                        result["trend"] = "overbought"
                    elif rsi < 30:
                        result["trend"] = "oversold"
                    else:
                        result["trend"] = "neutral"
                    
                    result["volatility"] = fused_data.technical_indicators.get("atr", 0)
        except Exception as e:
            logger.warning(f"市场分析失败: {e}")
        
        return result
