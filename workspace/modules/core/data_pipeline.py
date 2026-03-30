#!/usr/bin/env python3
"""
数据管道模块
统一管理市场数据流
"""

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import aiohttp
import numpy as np
import pandas as pd
import websockets


@dataclass
class MarketData:
    """市场数据结构"""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    exchange: str
    timeframe: str


@dataclass
class OrderBookSnapshot:
    """订单簿快照"""

    symbol: str
    timestamp: datetime
    bids: List[tuple[float, float]]  # (价格, 数量)
    asks: List[tuple[float, float]]
    exchange: str


@dataclass
class TradeTick:
    """交易tick数据"""

    symbol: str
    timestamp: datetime
    price: float
    quantity: float
    side: str  # buy/sell
    exchange: str


class DataPipeline:
    """数据管道管理器"""

    def __init__(self, config_manager):
        self.config = config_manager
        self.data_storage = {}
        self.data_subscribers = {}
        self.websocket_connections = {}
        self.rate_limiter = {}

        # 数据源配置
        self.data_sources = {
            "binance": {
                "rest": "https://api.binance.com/api/v3",
                "websocket": "wss://stream.binance.com:9443/ws",
                "rate_limit": 1200,  # 每分钟请求限制
            },
            "okx": {
                "rest": "https://www.okx.com/api/v5",
                "websocket": "wss://ws.okx.com:8443/ws/v5/public",
                "rate_limit": 300,
            },
            "coingecko": {"rest": "https://api.coingecko.com/api/v3", "rate_limit": 50},
        }

    async def fetch_historical_data(
        self, symbol: str, timeframe: str, limit: int = 1000, exchange: str = "binance"
    ) -> List[MarketData]:
        """获取历史K线数据"""

        endpoint = f"{self.data_sources[exchange]['rest']}/klines"
        params = {"symbol": symbol, "interval": timeframe, "limit": limit}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        market_data_list = []
                        for candle in data:
                            market_data = MarketData(
                                symbol=symbol,
                                timestamp=datetime.fromtimestamp(candle[0] / 1000),
                                open=float(candle[1]),
                                high=float(candle[2]),
                                low=float(candle[3]),
                                close=float(candle[4]),
                                volume=float(candle[5]),
                                exchange=exchange,
                                timeframe=timeframe,
                            )
                            market_data_list.append(market_data)

                        # 存储到内存
                        key = f"{symbol}_{timeframe}_{exchange}"
                        self.data_storage[key] = market_data_list

                        return market_data_list
                    else:
                        print(f"获取历史数据失败: {response.status}")
                        return []

        except Exception as e:
            print(f"获取历史数据异常: {e}")
            return []

    async def fetch_real_time_price(
        self, symbol: str, exchange: str = "binance"
    ) -> Optional[float]:
        """获取实时价格"""

        endpoint = f"{self.data_sources[exchange]['rest']}/ticker/price"
        params = {"symbol": symbol}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return float(data["price"])
                    else:
                        return None

        except Exception as e:
            print(f"获取实时价格异常: {e}")
            return None

    async def fetch_order_book(
        self, symbol: str, exchange: str = "binance", depth: int = 20
    ) -> Optional[OrderBookSnapshot]:
        """获取订单簿数据"""

        endpoint = f"{self.data_sources[exchange]['rest']}/depth"
        params = {"symbol": symbol, "limit": depth}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        bids = [(float(price), float(qty)) for price, qty in data["bids"][:depth]]
                        asks = [(float(price), float(qty)) for price, qty in data["asks"][:depth]]

                        return OrderBookSnapshot(
                            symbol=symbol,
                            timestamp=datetime.now(),
                            bids=bids,
                            asks=asks,
                            exchange=exchange,
                        )
                    else:
                        return None

        except Exception as e:
            print(f"获取订单簿异常: {e}")
            return None

    async def start_websocket_stream(self, symbols: List[str], exchange: str = "binance"):
        """启动WebSocket数据流"""

        if exchange not in self.data_sources:
            print(f"不支持的数据源: {exchange}")
            return

        ws_url = self.data_sources[exchange]["websocket"]

        # 构建订阅消息 (不同交易所格式不同)
        if exchange == "binance":
            streams = [f"{symbol.lower()}@ticker" for symbol in symbols]
            subscribe_msg = {"method": "SUBSCRIBE", "params": streams, "id": 1}
        elif exchange == "okx":
            subscribe_msg = {
                "op": "subscribe",
                "args": [{"channel": "tickers", "instId": symbol} for symbol in symbols],
            }

        try:
            async with websockets.connect(ws_url) as websocket:
                await websocket.send(json.dumps(subscribe_msg))

                self.websocket_connections[exchange] = websocket
                print(f"WebSocket连接已建立: {exchange}")

                # 持续接收数据
                async for message in websocket:
                    data = json.loads(message)
                    await self.process_websocket_data(data, exchange)

        except Exception as e:
            print(f"WebSocket连接异常: {e}")
        finally:
            if exchange in self.websocket_connections:
                del self.websocket_connections[exchange]

    async def process_websocket_data(self, data: Dict, exchange: str):
        """处理WebSocket数据"""

        if exchange == "binance":
            if "e" in data:  # 事件类型
                event_type = data["e"]

                if event_type == "24hrTicker":
                    ticker_data = {
                        "symbol": data["s"],
                        "price": float(data["c"]),
                        "volume": float(data["v"]),
                        "timestamp": datetime.fromtimestamp(data["E"] / 1000),
                        "exchange": exchange,
                    }
                    await self.notify_subscribers("ticker", ticker_data)

                elif event_type == "trade":
                    trade_data = {
                        "symbol": data["s"],
                        "price": float(data["p"]),
                        "quantity": float(data["q"]),
                        "side": "buy" if data["m"] else "sell",
                        "timestamp": datetime.fromtimestamp(data["T"] / 1000),
                        "exchange": exchange,
                    }
                    await self.notify_subscribers("trade", trade_data)

        elif exchange == "okx":
            if "data" in data:
                for ticker in data["data"]:
                    ticker_data = {
                        "symbol": ticker["instId"],
                        "price": float(ticker["last"]),
                        "volume": float(ticker["vol24h"]),
                        "timestamp": datetime.fromtimestamp(int(ticker["ts"]) / 1000),
                        "exchange": exchange,
                    }
                    await self.notify_subscribers("ticker", ticker_data)

    def subscribe(self, data_type: str, callback: Callable):
        """订阅数据更新"""
        if data_type not in self.data_subscribers:
            self.data_subscribers[data_type] = []

        self.data_subscribers[data_type].append(callback)
        print(f"新增订阅: {data_type}, 订阅者总数: {len(self.data_subscribers[data_type])}")

    def unsubscribe(self, data_type: str, callback: Callable):
        """取消订阅"""
        if data_type in self.data_subscribers and callback in self.data_subscribers[data_type]:
            self.data_subscribers[data_type].remove(callback)

    async def notify_subscribers(self, data_type: str, data: Dict):
        """通知订阅者"""
        if data_type in self.data_subscribers:
            for callback in self.data_subscribers[data_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    print(f"通知订阅者失败: {e}")

    def calculate_technical_indicators(self, market_data: List[MarketData]) -> Dict[str, Any]:
        """计算技术指标"""

        if not market_data:
            return {}

        closes = np.array([data.close for data in market_data])
        highs = np.array([data.high for data in market_data])
        lows = np.array([data.low for data in market_data])
        volumes = np.array([data.volume for data in market_data])

        indicators = {}

        # SMA
        indicators["sma_20"] = np.mean(closes[-20:]) if len(closes) >= 20 else None
        indicators["sma_50"] = np.mean(closes[-50:]) if len(closes) >= 50 else None
        indicators["sma_200"] = np.mean(closes[-200:]) if len(closes) >= 200 else None

        # EMA
        def calculate_ema(prices, period):
            if len(prices) < period:
                return None
            return pd.Series(prices).ewm(span=period, adjust=False).mean().iloc[-1]

        indicators["ema_12"] = calculate_ema(closes, 12)
        indicators["ema_26"] = calculate_ema(closes, 26)

        # RSI
        if len(closes) >= 14:
            delta = np.diff(closes)
            gain = (delta[delta > 0]).sum() / 14
            loss = (-delta[delta < 0]).sum() / 14
            if loss != 0:
                rs = gain / loss
                indicators["rsi"] = 100 - (100 / (1 + rs))
            else:
                indicators["rsi"] = 100
        else:
            indicators["rsi"] = None

        # MACD
        if indicators["ema_12"] and indicators["ema_26"]:
            indicators["macd"] = indicators["ema_12"] - indicators["ema_26"]
        else:
            indicators["macd"] = None

        # Bollinger Bands
        if len(closes) >= 20:
            sma_20 = indicators["sma_20"]
            std_20 = np.std(closes[-20:])
            indicators["bb_upper"] = sma_20 + (2 * std_20)
            indicators["bb_lower"] = sma_20 - (2 * std_20)
            indicators["bb_middle"] = sma_20
        else:
            indicators["bb_upper"] = indicators["bb_lower"] = indicators["bb_middle"] = None

        # Volume指标
        indicators["volume_avg"] = np.mean(volumes[-20:]) if len(volumes) >= 20 else None
        indicators["volume_ratio"] = (
            volumes[-1] / indicators["volume_avg"] if indicators["volume_avg"] else None
        )

        return indicators

    def get_cached_data(
        self, symbol: str, timeframe: str, exchange: str = "binance"
    ) -> List[MarketData]:
        """获取缓存数据"""
        key = f"{symbol}_{timeframe}_{exchange}"
        return self.data_storage.get(key, [])

    def clear_cache(self, symbol: str = None):
        """清理缓存"""
        if symbol:
            keys_to_delete = [key for key in self.data_storage.keys() if key.startswith(symbol)]
            for key in keys_to_delete:
                del self.data_storage[key]
        else:
            self.data_storage.clear()


# 单例实例
_data_pipeline = None


def get_data_pipeline(config_manager=None) -> DataPipeline:
    """获取数据管道单例"""
    global _data_pipeline
    if _data_pipeline is None:
        from .config_manager import get_config_manager

        config = config_manager or get_config_manager()
        _data_pipeline = DataPipeline(config)
    return _data_pipeline
