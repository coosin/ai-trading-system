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
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.binance.com"
    
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
                async with session.get(self.base_url + endpoint, params=params) as response:
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
    
    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
    
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
                async with session.get(self.base_url + endpoint, params=params) as response:
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
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.etherscan.io/api"
    
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
                async with session.get(self.base_url, params=params) as response:
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
    
    def __init__(self, bearer_token: str):
        self.bearer_token = bearer_token
        self.base_url = "https://api.twitter.com/2"
    
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
                                    headers=headers, params=params) as response:
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
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://newsapi.org/v2"
    
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
                async with session.get(self.base_url + endpoint, params=params) as response:
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

class DataIntegrator:
    """数据集成器"""
    
    def __init__(self):
        self.data_sources: Dict[str, DataSource] = {}
    
    def register_data_source(self, name: str, data_source: DataSource):
        """注册数据源"""
        self.data_sources[name] = data_source
        logger.info(f"注册数据源: {name}")
    
    async def fetch_data(self, source_name: str, **kwargs) -> pd.DataFrame:
        """从指定数据源获取数据"""
        if source_name not in self.data_sources:
            logger.error(f"数据源不存在: {source_name}")
            return pd.DataFrame()
        
        try:
            data_source = self.data_sources[source_name]
            data = await data_source.fetch_data(**kwargs)
            logger.info(f"从 {source_name} 获取数据成功: {len(data)} 条记录")
            return data
        except Exception as e:
            logger.error(f"从 {source_name} 获取数据失败: {e}")
            return pd.DataFrame()
    
    async def get_data_source_metadata(self, source_name: str) -> Dict[str, Any]:
        """获取数据源元数据"""
        if source_name not in self.data_sources:
            logger.error(f"数据源不存在: {source_name}")
            return {}
        
        try:
            data_source = self.data_sources[source_name]
            return await data_source.get_metadata()
        except Exception as e:
            logger.error(f"获取数据源元数据失败: {e}")
            return {}
    
    async def get_all_data_sources(self) -> List[str]:
        """获取所有注册的数据源"""
        return list(self.data_sources.keys())
    
    async def integrate_data(self, sources: List[Tuple[str, Dict[str, Any]]]) -> Dict[str, pd.DataFrame]:
        """集成多个数据源的数据"""
        results = {}
        
        async def fetch_from_source(source_info):
            source_name, params = source_info
            data = await self.fetch_data(source_name, **params)
            return source_name, data
        
        tasks = [fetch_from_source(source) for source in sources]
        results_list = await asyncio.gather(*tasks)
        
        for source_name, data in results_list:
            results[source_name] = data
        
        return results
    
    async def merge_data(self, data_dict: Dict[str, pd.DataFrame], 
                       join_key: str = "timestamp") -> pd.DataFrame:
        """合并多个数据源的数据"""
        if not data_dict:
            return pd.DataFrame()
        
        try:
            # 选择第一个数据源作为基础
            first_source = list(data_dict.keys())[0]
            merged_data = data_dict[first_source].copy()
            
            # 合并其他数据源
            for source_name, data in data_dict.items():
                if source_name != first_source:
                    if join_key in data.index and join_key in merged_data.index:
                        merged_data = merged_data.join(data, how="outer", rsuffix=f"_{source_name}")
                    else:
                        logger.warning(f"数据源 {source_name} 没有 {join_key} 索引，跳过合并")
            
            return merged_data
        except Exception as e:
            logger.error(f"合并数据失败: {e}")
            return pd.DataFrame()

# 使用示例
if __name__ == "__main__":
    async def main():
        # 创建数据集成器
        integrator = DataIntegrator()
        
        # 注册数据源
        integrator.register_data_source("binance", BinanceDataSource())
        integrator.register_data_source("coingecko", CoinGeckoDataSource())
        
        # 获取Binance数据
        binance_data = await integrator.fetch_data(
            "binance",
            symbol="BTCUSDT",
            interval="1h",
            limit=24
        )
        print(f"Binance数据: {len(binance_data)} 条记录")
        print(binance_data.head())
        
        # 获取CoinGecko数据
        coingecko_data = await integrator.fetch_data(
            "coingecko",
            coin_id="bitcoin",
            days=1
        )
        print(f"\nCoinGecko数据: {len(coingecko_data)} 条记录")
        print(coingecko_data.head())
        
        # 集成多个数据源
        sources = [
            ("binance", {"symbol": "BTCUSDT", "interval": "1h", "limit": 24}),
            ("coingecko", {"coin_id": "bitcoin", "days": 1})
        ]
        integrated_data = await integrator.integrate_data(sources)
        print(f"\n集成数据: {len(integrated_data)} 个数据源")
        
        # 合并数据
        merged_data = await integrator.merge_data(integrated_data)
        print(f"\n合并数据: {len(merged_data)} 条记录")
        print(merged_data.head())
    
    asyncio.run(main())
