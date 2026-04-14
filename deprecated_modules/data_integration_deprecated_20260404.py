import os
import json
import logging
import asyncio
import aiohttp
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

DEFAULT_PROXY_URL = "http://127.0.0.1:7890"

class DataSource(ABC):
    """数据源抽象基类"""
    
    @abstractmethod
    async def fetch_data(self, **kwargs) -> pd.DataFrame:
        """获取数据"""
        pass
    
    @abstractmethod
    async def get_metadata(self) -> Dict[str, Any]:
        """获取数据源元数据"""
        pass

class BinanceDataSource(DataSource):
    """Binance数据源"""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, proxy_url: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.binance.com"
        self.proxy_url = proxy_url or DEFAULT_PROXY_URL
    
    async def fetch_data(self, symbol: str = "BTCUSDT", interval: str = "1m", 
                        start_time: Optional[datetime] = None, 
                        end_time: Optional[datetime] = None, 
                        limit: int = 1000) -> pd.DataFrame:
        """获取K线数据"""
        try:
            endpoint = "/api/v3/klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
            
            if start_time:
                params["startTime"] = int(start_time.timestamp() * 1000)
            if end_time:
                params["endTime"] = int(end_time.timestamp() * 1000)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url + endpoint, params=params, proxy=self.proxy_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        df = pd.DataFrame(data, columns=[
                            "timestamp", "open", "high", "low", "close", "volume",
                            "close_time", "quote_asset_volume", "number_of_trades",
                            "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
                        ])
                        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                        df.set_index("timestamp", inplace=True)
                        df = df.astype({
                            "open": float, "high": float, "low": float, "close": float, "volume": float
                        })
                        return df
                    else:
                        logger.error(f"Binance API错误: {response.status}")
                        return pd.DataFrame()
        except Exception as e:
            logger.error(f"获取Binance数据失败: {e}")
            return pd.DataFrame()
    
    async def get_metadata(self) -> Dict[str, Any]:
        """获取数据源元数据"""
        return {
            "name": "Binance",
            "type": "cryptocurrency",
            "supported_intervals": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"],
            "rate_limit": "1200 requests per minute"
        }

class CoinGeckoDataSource(DataSource):
    """CoinGecko数据源"""
    
    def __init__(self, proxy_url: Optional[str] = None):
        self.base_url = "https://api.coingecko.com/api/v3"
        self.proxy_url = proxy_url or DEFAULT_PROXY_URL
    
    async def fetch_data(self, coin_id: str = "bitcoin", vs_currency: str = "usd", 
                        days: int = 7) -> pd.DataFrame:
        """获取价格数据"""
        try:
            endpoint = f"/coins/{coin_id}/market_chart"
            params = {
                "vs_currency": vs_currency,
                "days": days
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url + endpoint, params=params, proxy=self.proxy_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        prices = data.get("prices", [])
                        df = pd.DataFrame(prices, columns=["timestamp", "price"])
                        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                        df.set_index("timestamp", inplace=True)
                        return df
                    else:
                        logger.error(f"CoinGecko API错误: {response.status}")
                        return pd.DataFrame()
        except Exception as e:
            logger.error(f"获取CoinGecko数据失败: {e}")
            return pd.DataFrame()
    
    async def get_metadata(self) -> Dict[str, Any]:
        """获取数据源元数据"""
        return {
            "name": "CoinGecko",
            "type": "cryptocurrency",
            "rate_limit": "50 requests per minute"
        }

class EtherscanDataSource(DataSource):
    """Etherscan数据源"""
    
    def __init__(self, api_key: str, proxy_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://api.etherscan.io/api"
        self.proxy_url = proxy_url or DEFAULT_PROXY_URL
    
    async def fetch_data(self, address: str, startblock: int = 0, 
                        endblock: int = 99999999, 
                        sort: str = "asc") -> pd.DataFrame:
        """获取以太坊地址交易记录"""
        try:
            params = {
                "module": "account",
                "action": "txlist",
                "address": address,
                "startblock": startblock,
                "endblock": endblock,
                "sort": sort,
                "apikey": self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params, proxy=self.proxy_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "1":
                            txs = data.get("result", [])
                            df = pd.DataFrame(txs)
                            if not df.empty:
                                df["timeStamp"] = pd.to_datetime(df["timeStamp"], unit="s")
                                df.set_index("timeStamp", inplace=True)
                                df = df.astype({
                                    "value": float, "gas": float, "gasPrice": float
                                })
                            return df
                    else:
                        logger.error(f"Etherscan API错误: {response.status}")
                        return pd.DataFrame()
        except Exception as e:
            logger.error(f"获取Etherscan数据失败: {e}")
            return pd.DataFrame()
    
    async def get_metadata(self) -> Dict[str, Any]:
        """获取数据源元数据"""
        return {
            "name": "Etherscan",
            "type": "blockchain",
            "rate_limit": "5 calls per second"
        }

class TwitterDataSource(DataSource):
    """Twitter数据源"""
    
    def __init__(self, bearer_token: str, proxy_url: Optional[str] = None):
        self.bearer_token = bearer_token
        self.base_url = "https://api.twitter.com/2"
        self.proxy_url = proxy_url or DEFAULT_PROXY_URL
    
    async def fetch_data(self, query: str = "bitcoin", 
                        max_results: int = 100, 
                        start_time: Optional[datetime] = None) -> pd.DataFrame:
        """获取Twitter推文"""
        try:
            endpoint = "/tweets/search/recent"
            headers = {
                "Authorization": f"Bearer {self.bearer_token}"
            }
            params = {
                "query": query,
                "max_results": max_results,
                "tweet.fields": "created_at,public_metrics"
            }
            
            if start_time:
                params["start_time"] = start_time.isoformat() + "Z"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url + endpoint, 
                                    headers=headers, params=params, proxy=self.proxy_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        tweets = data.get("data", [])
                        df = pd.DataFrame(tweets)
                        if not df.empty:
                            df["created_at"] = pd.to_datetime(df["created_at"])
                            df.set_index("created_at", inplace=True)
                        return df
                    else:
                        logger.error(f"Twitter API错误: {response.status}")
                        return pd.DataFrame()
        except Exception as e:
            logger.error(f"获取Twitter数据失败: {e}")
            return pd.DataFrame()
    
    async def get_metadata(self) -> Dict[str, Any]:
        """获取数据源元数据"""
        return {
            "name": "Twitter",
            "type": "social_media",
            "rate_limit": "450 requests per 15-minute window"
        }

class NewsDataSource(DataSource):
    """新闻数据源"""
    
    def __init__(self, api_key: str, proxy_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://newsapi.org/v2"
        self.proxy_url = proxy_url or DEFAULT_PROXY_URL
    
    async def fetch_data(self, query: str = "cryptocurrency", 
                        from_date: Optional[datetime] = None, 
                        to_date: Optional[datetime] = None, 
                        language: str = "en", 
                        page_size: int = 100) -> pd.DataFrame:
        """获取新闻文章"""
        try:
            endpoint = "/everything"
            params = {
                "q": query,
                "language": language,
                "pageSize": page_size,
                "apiKey": self.api_key
            }
            
            if from_date:
                params["from"] = from_date.strftime("%Y-%m-%d")
            if to_date:
                params["to"] = to_date.strftime("%Y-%m-%d")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url + endpoint, params=params, proxy=self.proxy_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        articles = data.get("articles", [])
                        df = pd.DataFrame(articles)
                        if not df.empty:
                            df["publishedAt"] = pd.to_datetime(df["publishedAt"])
                            df.set_index("publishedAt", inplace=True)
                        return df
                    else:
                        logger.error(f"News API错误: {response.status}")
                        return pd.DataFrame()
        except Exception as e:
            logger.error(f"获取新闻数据失败: {e}")
            return pd.DataFrame()
    
    async def get_metadata(self) -> Dict[str, Any]:
        """获取数据源元数据"""
        return {
            "name": "NewsAPI",
            "type": "news",
            "rate_limit": "100 requests per day"
        }

class CoinbaseDataSource(DataSource):
    """Coinbase数据源"""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, proxy_url: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.coinbase.com"
        self.proxy_url = proxy_url or DEFAULT_PROXY_URL
    
    async def fetch_data(self, symbol: str = "BTC-USD", 
                        interval: str = "60", 
                        limit: int = 300) -> pd.DataFrame:
        """获取K线数据"""
        try:
            symbol = symbol.replace("/", "-")
            endpoint = f"/api/v2/prices/{symbol}/historic"
            params = {
                "granularity": interval
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url + endpoint, params=params, proxy=self.proxy_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        prices = data.get("data", {}).get("prices", [])
                        df = pd.DataFrame(prices)
                        if not df.empty:
                            df["time"] = pd.to_datetime(df["time"])
                            df.set_index("time", inplace=True)
                            df = df.rename(columns={
                                "price": "close"
                            })
                        return df
                    else:
                        logger.error(f"Coinbase API错误: {response.status}")
                        return pd.DataFrame()
        except Exception as e:
            logger.error(f"获取Coinbase数据失败: {e}")
            return pd.DataFrame()
    
    async def get_metadata(self) -> Dict[str, Any]:
        """获取数据源元数据"""
        return {
            "name": "Coinbase",
            "type": "cryptocurrency",
            "supported_intervals": ["60", "300", "900", "3600", "21600", "86400"],
            "rate_limit": "10 requests per second"
        }

class KrakenDataSource(DataSource):
    """Kraken数据源"""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, proxy_url: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.kraken.com"
        self.proxy_url = proxy_url or DEFAULT_PROXY_URL
    
    async def fetch_data(self, symbol: str = "XXBTZUSD", 
                        interval: int = 60, 
                        limit: int = 720) -> pd.DataFrame:
        """获取K线数据"""
        try:
            endpoint = "/0/public/OHLC"
            params = {
                "pair": symbol,
                "interval": interval
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url + endpoint, params=params, proxy=self.proxy_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data.get("result", {})
                        ohlc_data = result.get(symbol, [])
                        df = pd.DataFrame(ohlc_data, columns=[
                            "time", "open", "high", "low", "close", "vwap", "volume", "count"
                        ])
                        if not df.empty:
                            df["time"] = pd.to_datetime(df["time"], unit="s")
                            df.set_index("time", inplace=True)
                            df = df.astype({
                                "open": float, "high": float, "low": float, "close": float,
                                "vwap": float, "volume": float, "count": int
                            })
                        return df
                    else:
                        logger.error(f"Kraken API错误: {response.status}")
                        return pd.DataFrame()
        except Exception as e:
            logger.error(f"获取Kraken数据失败: {e}")
            return pd.DataFrame()
    
    async def get_metadata(self) -> Dict[str, Any]:
        """获取数据源元数据"""
        return {
            "name": "Kraken",
            "type": "cryptocurrency",
            "supported_intervals": [1, 5, 15, 30, 60, 240, 1440, 10080, 21600],
            "rate_limit": "1 request per second"
        }
