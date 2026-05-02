"""
数据集成模块

提供多个数据源的统一接口
"""

import logging
import asyncio
import os
import ssl
import time
import aiohttp
import certifi
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


def _datasource_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _datasource_timeout() -> aiohttp.ClientTimeout:
    total = float(os.getenv("OPENCLAW_DATASOURCE_HTTP_TIMEOUT", "28") or "28")
    conn = min(18.0, max(5.0, total * 0.45))
    return aiohttp.ClientTimeout(total=total, connect=conn, sock_read=total)


def _datasource_max_retries() -> int:
    return max(1, int(os.getenv("OPENCLAW_DATASOURCE_MAX_RETRIES", "3") or "3"))


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

    async def _open_session(self) -> None:
        """创建会话：HTTPS 目标必须校验 TLS；禁用 trust_env 避免与显式 proxy= 叠加。"""
        if self._session and not self._session.closed:
            return
        connector = aiohttp.TCPConnector(
            ssl=_datasource_ssl_context(),
            enable_cleanup_closed=True,
            ttl_dns_cache=max(10, int(os.getenv("OPENCLAW_DATASOURCE_DNS_TTL", "300") or "300")),
            limit=max(8, int(os.getenv("OPENCLAW_DATASOURCE_CONNECTOR_LIMIT", "32") or "32")),
        )
        self._session = aiohttp.ClientSession(connector=connector, trust_env=False)
    
    async def initialize(self) -> bool:
        """初始化数据源"""
        if self._initialized:
            return True
        
        await self._open_session()
        self._initialized = True
        logger.info(f"{self.__class__.__name__} 初始化完成")
        return True

    async def _recycle_session(self) -> None:
        old = self._session
        self._session = None
        if old and not old.closed:
            try:
                await old.close()
            except Exception:
                pass
        await self._open_session()
    
    async def _http_get_json(
        self, url: str, params: Optional[Dict[str, Any]] = None, log_label: str = "source"
    ) -> Tuple[bool, Any]:
        """GET JSON，带短重试；代理隧道半开时重建会话。"""
        proxy = self.proxy_url if self.proxy_url else None
        retries = _datasource_max_retries()
        timeout = _datasource_timeout()
        last_err: Optional[str] = None
        for attempt in range(retries):
            try:
                if not self._initialized:
                    await self.initialize()
                if self._session is None:
                    await self._open_session()
                async with self._session.get(url, params=params, proxy=proxy, timeout=timeout) as resp:
                    if resp.status == 200:
                        return True, await resp.json()
                    last_err = f"HTTP {resp.status}"
                    if resp.status >= 500 and attempt < retries - 1:
                        logger.debug("%s ServerError (attempt %s/%s): %s", log_label, attempt + 1, retries, last_err)
                        await asyncio.sleep(0.25 * (attempt + 1))
                        continue
            except aiohttp.ClientError as e:
                last_err = f"{type(e).__name__}: {e}"
                if attempt < retries - 1:
                    logger.debug("%s ClientError (attempt %s/%s): %s", log_label, attempt + 1, retries, last_err)
                    await self._recycle_session()
                    await asyncio.sleep(0.25 * (attempt + 1))
            except asyncio.TimeoutError:
                last_err = "ConnectionTimeoutError: datasource timeout"
                if attempt < retries - 1:
                    logger.debug("%s Timeout (attempt %s/%s)", log_label, attempt + 1, retries)
                    await self._recycle_session()
                    await asyncio.sleep(0.3 * (attempt + 1))
            except Exception as e:
                last_err = str(e)
                break
        return False, last_err
    
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
        url = f"{self.api_url}/api/v3/ticker/24hr"
        params = {"symbol": symbol.replace("/", "")}
        ok, data = await self._http_get_json(url, params, log_label="Binance")
        if ok and isinstance(data, dict):
            return MarketData(
                symbol=symbol,
                price=float(data.get("lastPrice", 0)),
                volume=float(data.get("volume", 0)),
                change_24h=float(data.get("priceChangePercent", 0)),
                high_24h=float(data.get("highPrice", 0)),
                low_24h=float(data.get("lowPrice", 0)),
                source="binance",
            )
        logger.warning("Binance获取市场数据失败: %s", data if not ok else "bad payload")
        return None
    
    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> List[Dict]:
        """获取K线数据"""
        url = f"{self.api_url}/api/v3/klines"
        params = {
            "symbol": symbol.replace("/", ""),
            "interval": interval,
            "limit": limit,
        }
        ok, data = await self._http_get_json(url, params, log_label="Binance.klines")
        if ok and isinstance(data, list):
            return [
                {
                    "timestamp": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                }
                for k in data
            ]
        logger.warning("Binance获取K线数据失败: %s", data if not ok else "bad payload")
        return []


def _coin_gecko_log_fail(source: Any, err: Any) -> None:
    """CoinGecko 失败去重日志（限流/网络差时避免刷屏）"""
    try:
        now = time.time()
        last = float(getattr(source, "_warn_last_ts", 0.0) or 0.0)
        if now - last >= 900.0:
            source._warn_last_ts = now
            logger.warning("CoinGecko获取市场数据失败(去重15m): %s", err)
        else:
            logger.debug("CoinGecko获取市场数据失败(去重): %s", err)
    except Exception:
        logger.warning("CoinGecko获取市场数据失败: %s", err)


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
        coin_id = self._get_coin_id(symbol)
        url = f"{self.api_url}/simple/price"
        params = {
            "ids": coin_id,
            "vs_currencies": "usd",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        }
        ok, data = await self._http_get_json(url, params, log_label="CoinGecko")
        if ok and isinstance(data, dict) and coin_id in data:
            coin_data = data[coin_id]
            return MarketData(
                symbol=symbol,
                price=coin_data.get("usd", 0),
                volume=coin_data.get("usd_24h_vol", 0),
                change_24h=coin_data.get("usd_24h_change", 0),
                source="coingecko",
            )
        _coin_gecko_log_fail(self, data if not ok else "missing coin_id in response")
        return None
    
    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> List[Dict]:
        """获取K线数据（CoinGecko不支持K线，返回模拟数据）"""
        return []


class DataIntegration:
    """数据集成器"""
    
    def __init__(self, config: Optional[Dict] = None, third_party_integrator: Any = None):
        self.config = config or {}
        self._sources: Dict[str, DataSourceBase] = {}
        self._source_health: Dict[str, Dict[str, Any]] = {}
        # Optional bridge to ThirdPartyDataIntegrator for “news” style data.
        self._third_party_integrator = third_party_integrator
    
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

    async def get_crypto_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Compatibility API for ProactiveAIOrchestrator.
        Returns a simplified list of news items (best-effort).
        """
        items: List[Dict[str, Any]] = []
        tpi = self._third_party_integrator
        if not tpi:
            return items
        # Try using NEWS provider directly to obtain articles.
        try:
            prov = getattr(tpi, "providers", {}) or {}
            news_provider = None
            # avoid importing DataSource Enum here; locate by value string
            for k, v in prov.items():
                if str(getattr(k, "value", k)).lower() in {"news", "cryptocompare", "cointelegraph"}:
                    news_provider = v
                    break
            if not news_provider:
                # fallback: tpi.get_news_sentiment exists but returns aggregated dict
                if hasattr(tpi, "get_news_sentiment"):
                    agg = await tpi.get_news_sentiment("BTC", hours=24)
                    return [{"title": "news_sentiment", "data": agg}]
                return items
            data = await news_provider.fetch_data("BTC", limit=max(1, int(limit or 10)))
            arts = (data or {}).get("articles") if isinstance(data, dict) else None
            for a in (arts or [])[: max(1, int(limit or 10))]:
                try:
                    items.append(
                        {
                            "title": getattr(a, "title", "") or "",
                            "source": getattr(a, "source", "") or "",
                            "url": getattr(a, "url", "") or "",
                            "timestamp": str(getattr(a, "timestamp", "") or ""),
                            "sentiment": float(getattr(a, "sentiment", 0.0) or 0.0),
                            "relevance": float(getattr(a, "relevance", 0.0) or 0.0),
                        }
                    )
                except Exception:
                    continue
            return items
        except Exception:
            return items
    
    async def close_all(self):
        """关闭所有数据源"""
        for source in self._sources.values():
            try:
                await source.close()
            except Exception as e:
                logger.warning(f"关闭数据源失败: {e}")
