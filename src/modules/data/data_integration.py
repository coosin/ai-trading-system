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

class CoinbaseDataSource(DataSource):
    """Coinbase数据源"""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.coinbase.com/v2"
    
    async def fetch_data(self, product_id: str = "BTC-USD", 
                        granularity: int = 3600,  # 1小时
                        start: Optional[datetime] = None, 
                        end: Optional[datetime] = None) -> pd.DataFrame:
        """获取K线数据"""
        try:
            endpoint = f"/products/{product_id}/candles"
            params = {
                "granularity": granularity
            }
            
            if start:
                params["start"] = start.isoformat()
            if end:
                params["end"] = end.isoformat()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url + endpoint, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        df = pd.DataFrame(data, columns=[
                            "timestamp", "low", "high", "open", "close", "volume"
                        ])
                        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
                        df.set_index("timestamp", inplace=True)
                        df = df.astype({
                            "open": float, "high": float, "low": float, "close": float, "volume": float
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
            "supported_granularities": [60, 300, 900, 3600, 21600, 86400],
            "rate_limit": "10 requests per second"
        }

class KrakenDataSource(DataSource):
    """Kraken数据源"""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.kraken.com/0"
    
    async def fetch_data(self, pair: str = "BTC/USD", 
                        interval: int = 1,  # 1分钟
                        since: Optional[int] = None) -> pd.DataFrame:
        """获取K线数据"""
        try:
            endpoint = "/public/OHLC"
            params = {
                "pair": pair.replace("/", ""),
                "interval": interval
            }
            
            if since:
                params["since"] = since
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url + endpoint, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data.get("result", {})
                        pair_key = list(result.keys())[0] if result else None
                        
                        if pair_key:
                            ohlc_data = result[pair_key]
                            df = pd.DataFrame(ohlc_data, columns=[
                                "timestamp", "open", "high", "low", "close", "vwap", "volume", "count"
                            ])
                            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
                            df.set_index("timestamp", inplace=True)
                            df = df.astype({
                                "open": float, "high": float, "low": float, "close": float, 
                                "vwap": float, "volume": float, "count": int
                            })
                            return df
                        return pd.DataFrame()
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
            "rate_limit": "15 requests per second"
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

    async def calculate_technical_indicators(self, data: pd.DataFrame, indicators: List[str]) -> pd.DataFrame:
        """
        计算技术指标

        Args:
            data: 包含价格数据的DataFrame，需要有close列
            indicators: 要计算的指标列表

        Returns:
            添加了技术指标的DataFrame
        """
        try:
            result = data.copy()
            
            for indicator in indicators:
                if indicator == "sma":
                    # 简单移动平均线
                    result["sma_20"] = result["close"].rolling(window=20).mean()
                    result["sma_50"] = result["close"].rolling(window=50).mean()
                elif indicator == "ema":
                    # 指数移动平均线
                    result["ema_20"] = result["close"].ewm(span=20, adjust=False).mean()
                    result["ema_50"] = result["close"].ewm(span=50, adjust=False).mean()
                elif indicator == "rsi":
                    # 相对强弱指标
                    delta = result["close"].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    result["rsi"] = 100 - (100 / (1 + rs))
                elif indicator == "macd":
                    # MACD指标
                    result["ema_12"] = result["close"].ewm(span=12, adjust=False).mean()
                    result["ema_26"] = result["close"].ewm(span=26, adjust=False).mean()
                    result["macd"] = result["ema_12"] - result["ema_26"]
                    result["macd_signal"] = result["macd"].ewm(span=9, adjust=False).mean()
                    result["macd_hist"] = result["macd"] - result["macd_signal"]
                elif indicator == "bollinger":
                    # 布林带
                    result["bb_middle"] = result["close"].rolling(window=20).mean()
                    result["bb_std"] = result["close"].rolling(window=20).std()
                    result["bb_upper"] = result["bb_middle"] + (result["bb_std"] * 2)
                    result["bb_lower"] = result["bb_middle"] - (result["bb_std"] * 2)
                elif indicator == "stochastic":
                    # 随机指标
                    result["low_14"] = result["low"].rolling(window=14).min()
                    result["high_14"] = result["high"].rolling(window=14).max()
                    result["stochastic_k"] = 100 * ((result["close"] - result["low_14"]) / (result["high_14"] - result["low_14"]))
                    result["stochastic_d"] = result["stochastic_k"].rolling(window=3).mean()
                elif indicator == "cci":
                    # 商品通道指数
                    typical_price = (result["high"] + result["low"] + result["close"]) / 3
                    sma_typical = typical_price.rolling(window=20).mean()
                    mean_deviation = abs(typical_price - sma_typical).rolling(window=20).mean()
                    result["cci"] = (typical_price - sma_typical) / (0.015 * mean_deviation)
                elif indicator == "adx":
                    # 平均趋向指数
                    result["tr"] = pd.concat([
                        result["high"] - result["low"],
                        abs(result["high"] - result["close"].shift()),
                        abs(result["low"] - result["close"].shift())
                    ], axis=1).max(axis=1)
                    result["+dm"] = (result["high"] - result["high"].shift()).where(
                        (result["high"] - result["high"].shift()) > (result["low"].shift() - result["low"]), 0
                    )
                    result["-dm"] = (result["low"].shift() - result["low"]).where(
                        (result["low"].shift() - result["low"]) > (result["high"] - result["high"].shift()), 0
                    )
                    result["+di"] = 100 * (result["+dm"].rolling(window=14).mean() / result["tr"].rolling(window=14).mean())
                    result["-di"] = 100 * (result["-dm"].rolling(window=14).mean() / result["tr"].rolling(window=14).mean())
                    result["dx"] = 100 * abs(result["+di"] - result["-di"]) / (result["+di"] + result["-di"])
                    result["adx"] = result["dx"].rolling(window=14).mean()
            
            return result
        except Exception as e:
            logger.error(f"计算技术指标失败: {e}")
            return data

    async def analyze_market_trends(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        分析市场趋势

        Args:
            data: 包含价格数据的DataFrame

        Returns:
            市场趋势分析结果
        """
        try:
            analysis = {}
            
            # 计算基本指标
            data_with_indicators = await self.calculate_technical_indicators(data, ["sma", "ema", "rsi", "macd"])
            
            # 趋势分析
            latest_data = data_with_indicators.iloc[-1]
            
            # 价格趋势
            if latest_data["close"] > latest_data["sma_50"]:
                analysis["price_trend"] = "bullish"
            else:
                analysis["price_trend"] = "bearish"
            
            # 动量分析
            if latest_data["rsi"] > 70:
                analysis["momentum"] = "overbought"
            elif latest_data["rsi"] < 30:
                analysis["momentum"] = "oversold"
            else:
                analysis["momentum"] = "neutral"
            
            # MACD分析
            if latest_data["macd"] > latest_data["macd_signal"]:
                analysis["macd_signal"] = "bullish"
            else:
                analysis["macd_signal"] = "bearish"
            
            # 波动率分析
            analysis["volatility"] = data["close"].pct_change().std() * (252 ** 0.5)  # 年化波动率
            
            # 支撑和阻力位
            analysis["support"] = data["low"].tail(20).min()
            analysis["resistance"] = data["high"].tail(20).max()
            
            # 趋势强度
            price_change = (latest_data["close"] - data["close"].iloc[0]) / data["close"].iloc[0]
            analysis["trend_strength"] = "strong" if abs(price_change) > 0.1 else "weak"
            
            return analysis
        except Exception as e:
            logger.error(f"分析市场趋势失败: {e}")
            return {}

    async def generate_trading_signals(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        生成交易信号

        Args:
            data: 包含价格数据的DataFrame

        Returns:
            交易信号列表
        """
        try:
            signals = []
            data_with_indicators = await self.calculate_technical_indicators(data, ["sma", "rsi", "macd", "bollinger"])
            
            # 遍历数据，生成信号
            for i in range(1, len(data_with_indicators)):
                current = data_with_indicators.iloc[i]
                previous = data_with_indicators.iloc[i-1]
                
                # 移动平均线金叉/死叉
                if previous["sma_20"] < previous["sma_50"] and current["sma_20"] > current["sma_50"]:
                    signals.append({
                        "timestamp": current.name,
                        "signal": "buy",
                        "indicator": "sma_crossover",
                        "price": current["close"],
                        "confidence": 0.7
                    })
                elif previous["sma_20"] > previous["sma_50"] and current["sma_20"] < current["sma_50"]:
                    signals.append({
                        "timestamp": current.name,
                        "signal": "sell",
                        "indicator": "sma_crossover",
                        "price": current["close"],
                        "confidence": 0.7
                    })
                
                # RSI超买/超卖
                if current["rsi"] < 30 and previous["rsi"] >= 30:
                    signals.append({
                        "timestamp": current.name,
                        "signal": "buy",
                        "indicator": "rsi_oversold",
                        "price": current["close"],
                        "confidence": 0.6
                    })
                elif current["rsi"] > 70 and previous["rsi"] <= 70:
                    signals.append({
                        "timestamp": current.name,
                        "signal": "sell",
                        "indicator": "rsi_overbought",
                        "price": current["close"],
                        "confidence": 0.6
                    })
                
                # 布林带突破
                if current["close"] > current["bb_upper"] and previous["close"] <= previous["bb_upper"]:
                    signals.append({
                        "timestamp": current.name,
                        "signal": "buy",
                        "indicator": "bollinger_breakout",
                        "price": current["close"],
                        "confidence": 0.65
                    })
                elif current["close"] < current["bb_lower"] and previous["close"] >= previous["bb_lower"]:
                    signals.append({
                        "timestamp": current.name,
                        "signal": "sell",
                        "indicator": "bollinger_breakdown",
                        "price": current["close"],
                        "confidence": 0.65
                    })
            
            return signals
        except Exception as e:
            logger.error(f"生成交易信号失败: {e}")
            return []

# 使用示例
if __name__ == "__main__":
    async def main():
        # 创建数据集成器
        integrator = DataIntegrator()
        
        # 注册数据源
        integrator.register_data_source("binance", BinanceDataSource())
        integrator.register_data_source("coingecko", CoinGeckoDataSource())
        integrator.register_data_source("coinbase", CoinbaseDataSource())
        integrator.register_data_source("kraken", KrakenDataSource())
        
        # 获取Binance数据
        binance_data = await integrator.fetch_data(
            "binance",
            symbol="BTCUSDT",
            interval="1h",
            limit=100
        )
        print(f"Binance数据: {len(binance_data)} 条记录")
        print(binance_data.head())
        
        # 获取Coinbase数据
        coinbase_data = await integrator.fetch_data(
            "coinbase",
            product_id="BTC-USD",
            granularity=3600,  # 1小时
            start=datetime.now() - timedelta(days=5)
        )
        print(f"\nCoinbase数据: {len(coinbase_data)} 条记录")
        print(coinbase_data.head())
        
        # 计算技术指标
        if not binance_data.empty:
            indicators_data = await integrator.calculate_technical_indicators(
                binance_data, 
                ["sma", "rsi", "macd", "bollinger"]
            )
            print(f"\n技术指标数据: {len(indicators_data)} 条记录")
            print(indicators_data[["close", "sma_20", "sma_50", "rsi", "macd"]].tail())
        
        # 分析市场趋势
        if not binance_data.empty:
            trend_analysis = await integrator.analyze_market_trends(binance_data)
            print("\n市场趋势分析:")
            for key, value in trend_analysis.items():
                print(f"  {key}: {value}")
        
        # 生成交易信号
        if not binance_data.empty:
            signals = await integrator.generate_trading_signals(binance_data)
            print(f"\n生成交易信号: {len(signals)} 个")
            for signal in signals[-5:]:  # 显示最后5个信号
                print(f"  {signal['timestamp']}: {signal['signal']} - {signal['indicator']} (置信度: {signal['confidence']})")
        
        # 集成多个数据源
        sources = [
            ("binance", {"symbol": "BTCUSDT", "interval": "1h", "limit": 24}),
            ("coinbase", {"product_id": "BTC-USD", "granularity": 3600, "start": datetime.now() - timedelta(days=1)})
        ]
        integrated_data = await integrator.integrate_data(sources)
        print(f"\n集成数据: {len(integrated_data)} 个数据源")
        
        # 合并数据
        merged_data = await integrator.merge_data(integrated_data)
        print(f"\n合并数据: {len(merged_data)} 条记录")
        print(merged_data.head())
    
    asyncio.run(main())
