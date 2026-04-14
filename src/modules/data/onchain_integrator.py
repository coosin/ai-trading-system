"""
链上数据集成系统

为AI交易系统提供链上数据分析能力
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import aiohttp
import json

logger = logging.getLogger(__name__)


class OnChainMetric(str, Enum):
    """链上指标类型"""
    ACTIVE_ADDRESSES = "active_addresses"
    TRANSACTION_VOLUME = "transaction_volume"
    HOLDER_DISTRIBUTION = "holder_distribution"
    EXCHANGE_FLOWS = "exchange_flows"
    MINER_ACTIVITY = "miner_activity"
    WHALE_ACTIVITY = "whale_activity"
    NETWORK_HASHRATE = "network_hashrate"
    DIFFICULTY = "difficulty"
    FEE_RATE = "fee_rate"
    MEMPOOL_SIZE = "mempool_size"


@dataclass
class OnChainData:
    """链上数据"""
    symbol: str
    metric: OnChainMetric
    value: float
    change_24h: float
    change_7d: float
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExchangeFlow:
    """交易所资金流向"""
    exchange: str
    inflow: float
    outflow: float
    net_flow: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class WhaleActivity:
    """巨鲸活动"""
    address: str
    amount: float
    direction: str  # in, out
    usd_value: float
    timestamp: datetime = field(default_factory=datetime.now)


class OnChainDataProvider:
    """链上数据提供者基类"""
    
    def __init__(self, proxy_url: Optional[str] = None):
        self._proxy_url = proxy_url
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_proxy(self) -> Optional[str]:
        """获取代理URL"""
        if self._proxy_url:
            return self._proxy_url
        try:
            from src.utils.proxy_utils import get_proxy_url
            self._proxy_url = await get_proxy_url()
            return self._proxy_url
        except Exception as e:
            logger.debug(f"获取代理失败: {e}")
            return None
    
    async def get_metric(self, symbol: str, metric: OnChainMetric) -> Optional[OnChainData]:
        """获取链上指标"""
        raise NotImplementedError


class GlassnodeProvider(OnChainDataProvider):
    """Glassnode数据提供者"""
    
    def __init__(self, api_key: str, proxy_url: Optional[str] = None):
        super().__init__(proxy_url)
        self.api_key = api_key
        self.base_url = "https://api.glassnode.com/v1/metrics"
    
    async def get_metric(self, symbol: str, metric: OnChainMetric) -> Optional[OnChainData]:
        """获取链上指标"""
        try:
            metric_map = {
                OnChainMetric.ACTIVE_ADDRESSES: "addresses/active_count",
                OnChainMetric.TRANSACTION_VOLUME: "transactions/transfers_volume_sum",
                OnChainMetric.EXCHANGE_FLOWS: "transactions/transfers_volume_to_exchanges_sum",
            }
            
            if metric not in metric_map:
                return None
            
            endpoint = metric_map[metric]
            url = f"{self.base_url}/{endpoint}"
            
            params = {
                "api_key": self.api_key,
                "a": symbol.lower(),
                "i": "24h"
            }
            
            proxy = await self._get_proxy()
            
            if not self._session:
                self._session = aiohttp.ClientSession()
            
            async with self._session.get(url, params=params, proxy=proxy, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data and len(data) > 0:
                        latest = data[-1]
                        
                        return OnChainData(
                            symbol=symbol,
                            metric=metric,
                            value=float(latest.get("v", 0)),
                            change_24h=0.0,
                            change_7d=0.0,
                            timestamp=datetime.fromtimestamp(latest.get("t", 0) / 1000)
                        )
            
            return None
            
        except Exception as e:
            logger.error(f"Glassnode API调用失败: {e}")
            return None


class CryptoQuantProvider(OnChainDataProvider):
    """CryptoQuant数据提供者"""
    
    def __init__(self, api_key: str, proxy_url: Optional[str] = None):
        super().__init__(proxy_url)
        self.api_key = api_key
        self.base_url = "https://api.cryptoquant.com/v1"
    
    async def get_metric(self, symbol: str, metric: OnChainMetric) -> Optional[OnChainData]:
        """获取链上指标"""
        try:
            metric_map = {
                OnChainMetric.EXCHANGE_FLOWS: "exchange-flows/netflow",
                OnChainMetric.MINER_ACTIVITY: "miner/outflow",
                OnChainMetric.WHALE_ACTIVITY: "transactions/whale-activity",
            }
            
            if metric not in metric_map:
                return None
            
            endpoint = metric_map[metric]
            url = f"{self.base_url}/{endpoint}"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }
            
            params = {
                "symbol": symbol.upper(),
                "window": "day"
            }
            
            proxy = await self._get_proxy()
            
            if not self._session:
                self._session = aiohttp.ClientSession()
            
            async with self._session.get(url, headers=headers, params=params, proxy=proxy, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data and "result" in data and len(data["result"]) > 0:
                        latest = data["result"][-1]
                        
                        return OnChainData(
                            symbol=symbol,
                            metric=metric,
                            value=float(latest.get("value", 0)),
                            change_24h=0.0,
                            change_7d=0.0,
                            timestamp=datetime.now()
                        )
            
            return None
            
        except Exception as e:
            logger.error(f"CryptoQuant API调用失败: {e}")
            return None


class MockOnChainProvider(OnChainDataProvider):
    """模拟链上数据提供者（用于测试）"""
    
    async def get_metric(self, symbol: str, metric: OnChainMetric) -> Optional[OnChainData]:
        """获取模拟链上指标"""
        
        # 模拟数据
        mock_values = {
            OnChainMetric.ACTIVE_ADDRESSES: 850000,
            OnChainMetric.TRANSACTION_VOLUME: 25000000000,
            OnChainMetric.EXCHANGE_FLOWS: -150000000,
            OnChainMetric.MINER_ACTIVITY: 1200000000,
            OnChainMetric.WHALE_ACTIVITY: 500000000,
            OnChainMetric.NETWORK_HASHRATE: 350000000000000,
        }
        
        value = mock_values.get(metric, 0)
        
        return OnChainData(
            symbol=symbol,
            metric=metric,
            value=value,
            change_24h=2.5,
            change_7d=-1.2,
            timestamp=datetime.now()
        )


class OnChainDataIntegrator:
    """链上数据集成器"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # 初始化数据提供者
        self.providers: List[OnChainDataProvider] = []
        
        # 添加模拟提供者（默认）
        self.providers.append(MockOnChainProvider())
        
        # 如果有API密钥，添加真实提供者
        glassnode_key = self.config.get("glassnode_api_key")
        if glassnode_key:
            self.providers.append(GlassnodeProvider(glassnode_key))
        
        cryptoquant_key = self.config.get("cryptoquant_api_key")
        if cryptoquant_key:
            self.providers.append(CryptoQuantProvider(cryptoquant_key))
        
        # 缓存
        self._cache: Dict[str, OnChainData] = {}
        self._cache_ttl = 300  # 5分钟缓存
    
    async def get_onchain_metrics(self, symbol: str) -> Dict[str, OnChainData]:
        """获取所有链上指标"""
        
        metrics = {}
        
        # 获取所有指标
        for metric in OnChainMetric:
            data = await self._get_metric_with_cache(symbol, metric)
            if data:
                metrics[metric.value] = data
        
        return metrics
    
    async def _get_metric_with_cache(
        self,
        symbol: str,
        metric: OnChainMetric
    ) -> Optional[OnChainData]:
        """带缓存的获取指标"""
        
        cache_key = f"{symbol}_{metric.value}"
        
        # 检查缓存
        if cache_key in self._cache:
            cached_data = self._cache[cache_key]
            age = (datetime.now() - cached_data.timestamp).total_seconds()
            
            if age < self._cache_ttl:
                return cached_data
        
        # 从提供者获取
        for provider in self.providers:
            try:
                data = await provider.get_metric(symbol, metric)
                if data:
                    self._cache[cache_key] = data
                    return data
            except Exception as e:
                logger.error(f"获取链上数据失败 {symbol} {metric.value}: {e}")
                continue
        
        return None
    
    async def analyze_onchain_sentiment(self, symbol: str) -> Dict[str, Any]:
        """分析链上情绪"""
        
        metrics = await self.get_onchain_metrics(symbol)
        
        if not metrics:
            return {"sentiment": "neutral", "confidence": 0.0}
        
        # 计算情绪分数
        score = 0.0
        
        # 活跃地址增加 = 看涨
        if "active_addresses" in metrics:
            change = metrics["active_addresses"].change_24h
            score += min(max(change / 10, -1), 1)
        
        # 交易所净流出 = 看涨
        if "exchange_flows" in metrics:
            net_flow = metrics["exchange_flows"].value
            if net_flow < 0:  # 流出
                score += 0.5
            else:  # 流入
                score -= 0.5
        
        # 巨鲸活动
        if "whale_activity" in metrics:
            change = metrics["whale_activity"].change_24h
            score += min(max(change / 20, -1), 1)
        
        # 矿工活动
        if "miner_activity" in metrics:
            change = metrics["miner_activity"].change_24h
            if change < 0:  # 矿工卖出减少
                score += 0.3
            else:  # 矿工卖出增加
                score -= 0.3
        
        # 确定情绪
        if score > 0.5:
            sentiment = "bullish"
        elif score < -0.5:
            sentiment = "bearish"
        else:
            sentiment = "neutral"
        
        return {
            "sentiment": sentiment,
            "score": score,
            "confidence": min(abs(score), 1.0),
            "metrics_analyzed": len(metrics)
        }
    
    async def get_exchange_flows(self, symbol: str) -> List[ExchangeFlow]:
        """获取交易所资金流向"""
        
        # 模拟数据
        exchanges = ["Binance", "OKX", "Coinbase", "Kraken"]
        flows = []
        
        for exchange in exchanges:
            import random
            
            inflow = random.uniform(100, 1000)
            outflow = random.uniform(100, 1000)
            
            flows.append(ExchangeFlow(
                exchange=exchange,
                inflow=inflow,
                outflow=outflow,
                net_flow=outflow - inflow
            ))
        
        return flows
    
    async def get_whale_activities(
        self,
        symbol: str,
        min_amount: float = 1000000,
        limit: int = 5,
    ) -> List[WhaleActivity]:
        """获取巨鲸活动"""
        
        # 模拟数据
        activities = []
        
        count = max(1, int(limit or 5))
        for i in range(count):
            import random
            
            amount = random.uniform(min_amount, min_amount * 10)
            direction = random.choice(["in", "out"])
            
            activities.append(WhaleActivity(
                address=f"0x{''.join(random.choices('0123456789abcdef', k=40))}",
                amount=amount,
                direction=direction,
                usd_value=amount * 50000  # 假设BTC价格
            ))
        
        return activities
    
    async def generate_onchain_report(self, symbol: str) -> Dict[str, Any]:
        """生成链上数据报告"""
        
        metrics = await self.get_onchain_metrics(symbol)
        sentiment = await self.analyze_onchain_sentiment(symbol)
        flows = await self.get_exchange_flows(symbol)
        whales = await self.get_whale_activities(symbol)
        
        return {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "metrics": {
                metric: {
                    "value": data.value,
                    "change_24h": data.change_24h,
                    "change_7d": data.change_7d
                }
                for metric, data in metrics.items()
            },
            "sentiment": sentiment,
            "exchange_flows": [
                {
                    "exchange": flow.exchange,
                    "net_flow": flow.net_flow
                }
                for flow in flows
            ],
            "whale_activities": len(whales),
            "summary": self._generate_summary(metrics, sentiment, flows, whales)
        }
    
    def _generate_summary(
        self,
        metrics: Dict,
        sentiment: Dict,
        flows: List,
        whales: List
    ) -> str:
        """生成摘要"""
        
        summary_parts = []
        
        # 情绪
        summary_parts.append(
            f"链上情绪: {sentiment['sentiment']} (置信度: {sentiment['confidence']:.2f})"
        )
        
        # 交易所流向
        total_net_flow = sum(flow.net_flow for flow in flows)
        if total_net_flow > 0:
            summary_parts.append("交易所净流入，可能面临抛压")
        else:
            summary_parts.append("交易所净流出，看涨信号")
        
        # 巨鲸活动
        if len(whales) > 3:
            summary_parts.append("巨鲸活动频繁，需密切关注")
        
        return " | ".join(summary_parts)
