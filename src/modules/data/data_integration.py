"""
数据集成模块

提供多个数据源的统一接口
"""

import logging
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


@dataclass
class MarketData:
    """市场数据"""
    symbol: str
    price: float
    volume: float = 0.0
    change_24h: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""


class DataSourceBase(ABC):
    """数据源基类"""
    
    def __init__(self, proxy_url: Optional[str] = None):
        self.proxy_url = proxy_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._initialized = False
    
    async def initialize(self) -> bool:
        """初始化数据源"""
        if self._initialized:
            return True
        
        connector = None
        if self.proxy_url:
            connector = aiohttp.TCPConnector(ssl=False)
        
        self._session = aiohttp.ClientSession(connector=connector)
        self._initialized = True
        logger.info(f"{self.__class__.__name__} 初始化完成")
        return True
    
    async def close(self):
        """关闭连接"""
        if self._session:
            await self._session.close()
            self._session = None
        self._initialized = False
    
    @abstractmethod
    async def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """获取市场数据"""
        pass
    
    @abstractmethod
    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> List[Dict]:
        """获取K线数据"""
        pass


class BinanceDataSource(DataSourceBase):
    """Binance数据源"""
    
    def __init__(self, proxy_url: Optional[str] = None, api_key: Optional[str] = None):
        super().__init__(proxy_url)
        self.api_url = "https://api.binance.com"
        self.api_key = api_key
    
    async def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """获取市场数据"""
        if not self._initialized:
            await self.initialize()
        
        try:
            url = f"{self.api_url}/api/v3/ticker/24hr"
            params = {"symbol": symbol.replace("/", "")}
            
            proxy = self.proxy_url if self.proxy_url else None
            async with self._session.get(url, params=params, proxy=proxy, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return MarketData(
                        symbol=symbol,
                        price=float(data.get("lastPrice", 0)),
                        volume=float(data.get("volume", 0)),
                        change_24h=float(data.get("priceChangePercent", 0)),
                        high_24h=float(data.get("highPrice", 0)),
                        low_24h=float(data.get("lowPrice", 0)),
                        source="binance"
                    )
        except Exception as e:
            logger.warning(f"Binance获取市场数据失败: {e}")
        
        return None
    
    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> List[Dict]:
        """获取K线数据"""
        if not self._initialized:
            await self.initialize()
        
        try:
            url = f"{self.api_url}/api/v3/klines"
            params = {
                "symbol": symbol.replace("/", ""),
                "interval": interval,
                "limit": limit
            }
            
            proxy = self.proxy_url if self.proxy_url else None
            async with self._session.get(url, params=params, proxy=proxy, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [
                        {
                            "timestamp": k[0],
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5])
                        }
                        for k in data
                    ]
        except Exception as e:
            logger.warning(f"Binance获取K线数据失败: {e}")
        
        return []


class CoinGeckoDataSource(DataSourceBase):
    """CoinGecko数据源"""
    
    def __init__(self, proxy_url: Optional[str] = None, api_key: Optional[str] = None):
        super().__init__(proxy_url)
        self.api_url = "https://api.coingecko.com/api/v3"
        self.api_key = api_key
    
    def _get_coin_id(self, symbol: str) -> str:
        """获取CoinGecko币种ID"""
        symbol_map = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            "BNB": "binancecoin",
            "XRP": "ripple",
            "ADA": "cardano",
            "DOGE": "dogecoin",
            "DOT": "polkadot",
            "MATIC": "matic-network",
            "LINK": "chainlink"
        }
        base = symbol.split("/")[0] if "/" in symbol else symbol
        return symbol_map.get(base.upper(), base.lower())
    
    async def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """获取市场数据"""
        if not self._initialized:
            await self.initialize()
        
        try:
            coin_id = self._get_coin_id(symbol)
            url = f"{self.api_url}/simple/price"
            params = {
                "ids": coin_id,
                "vs_currencies": "usd",
                "include_24hr_vol": "true",
                "include_24hr_change": "true"
            }
            
            proxy = self.proxy_url if self.proxy_url else None
            async with self._session.get(url, params=params, proxy=proxy, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if coin_id in data:
                        coin_data = data[coin_id]
                        return MarketData(
                            symbol=symbol,
                            price=coin_data.get("usd", 0),
                            volume=coin_data.get("usd_24h_vol", 0),
                            change_24h=coin_data.get("usd_24h_change", 0),
                            source="coingecko"
                        )
        except Exception as e:
            logger.warning(f"CoinGecko获取市场数据失败: {e}")
        
        return None
    
    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> List[Dict]:
        """获取K线数据（CoinGecko不支持K线，返回模拟数据）"""
        return []


class DataIntegration:
    """数据集成器"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self._sources: Dict[str, DataSourceBase] = {}
        self._source_health: Dict[str, Dict[str, Any]] = {}
    
    def register_source(self, name: str, source: DataSourceBase):
        """注册数据源"""
        self._sources[name] = source
        self._source_health.setdefault(name, {
            "ok_count": 0,
            "fail_count": 0,
            "last_ok_at": None,
            "last_error": "",
            "degraded": False,
        })
        logger.info(f"注册数据源: {name}")

    def _mark_source_ok(self, name: str):
        stat = self._source_health.setdefault(name, {
            "ok_count": 0,
            "fail_count": 0,
            "last_ok_at": None,
            "last_error": "",
            "degraded": False,
        })
        stat["ok_count"] += 1
        stat["last_ok_at"] = datetime.now().isoformat()
        stat["last_error"] = ""
        # 连续成功后恢复健康标记
        if stat["ok_count"] >= max(1, stat["fail_count"]):
            stat["degraded"] = False

    def _mark_source_fail(self, name: str, error: str):
        stat = self._source_health.setdefault(name, {
            "ok_count": 0,
            "fail_count": 0,
            "last_ok_at": None,
            "last_error": "",
            "degraded": False,
        })
        stat["fail_count"] += 1
        stat["last_error"] = str(error)
        # 任意失败先标记退化，供上层可观测
        stat["degraded"] = True
    
    async def initialize_all(self) -> bool:
        """初始化所有数据源"""
        for name, source in self._sources.items():
            try:
                await source.initialize()
            except Exception as e:
                logger.warning(f"数据源 {name} 初始化失败: {e}")
        return True
    
    async def get_best_price(self, symbol: str) -> Optional[MarketData]:
        """获取最佳价格（从多个源获取并验证）"""
        results = []
        
        for name, source in self._sources.items():
            try:
                data = await source.get_market_data(symbol)
                if data:
                    results.append(data)
                    self._mark_source_ok(name)
                else:
                    self._mark_source_fail(name, "no_data")
            except Exception as e:
                self._mark_source_fail(name, str(e))
                logger.debug(f"从 {name} 获取价格失败: {e}")
        
        if not results:
            return None
        
        results.sort(key=lambda x: x.timestamp, reverse=True)
        return results[0]

    def get_source_health_report(self) -> Dict[str, Any]:
        degraded = [name for name, s in self._source_health.items() if s.get("degraded")]
        return {
            "total_sources": len(self._sources),
            "degraded_sources": degraded,
            "degraded_count": len(degraded),
            "healthy": len(degraded) == 0,
            "sources": self._source_health,
        }
    
    async def close_all(self):
        """关闭所有数据源"""
        for source in self._sources.values():
            try:
                await source.close()
            except Exception as e:
                logger.warning(f"关闭数据源失败: {e}")
