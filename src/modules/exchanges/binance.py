"""
Binance交易所实现

基于ExchangeBase抽象类实现Binance API调用
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

import aiohttp

from .exchange_base import ExchangeBase, MarketData, OrderBook, Order, Balance, ExchangeInfo

logger = logging.getLogger(__name__)


class BinanceExchange(ExchangeBase):
    """Binance交易所实现"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_url = "https://api.binance.com" if not self.testnet else "https://testnet.binance.vision"
        self.ws_url = "wss://stream.binance.com:9443" if not self.testnet else "wss://testnet.binance.vision"
        self._session = None
        self._ws_connections = {}
    
    async def initialize(self) -> bool:
        """初始化交易所连接"""
        try:
            self._session = aiohttp.ClientSession()
            # 测试连接
            await self.get_exchange_info()
            self._running = True
            logger.info(f"Binance交易所初始化成功")
            return True
        except Exception as e:
            logger.error(f"Binance交易所初始化失败: {e}")
            return False
    
    async def cleanup(self) -> None:
        """清理资源"""
        try:
            if self._session:
                await self._session.close()
            # 关闭所有WebSocket连接
            for conn in self._ws_connections.values():
                if not conn.closed:
                    await conn.close()
            self._running = False
            logger.info(f"Binance交易所清理完成")
        except Exception as e:
            logger.error(f"Binance交易所清理失败: {e}")
    
    async def get_market_data(self, symbol: str, interval: str = "1m") -> MarketData:
        """获取市场数据"""
        endpoint = "/api/v3/klines"
        params = {
            "symbol": symbol.replace("/", ""),
            "interval": interval,
            "limit": 1
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data:
                kline = data[0]
                return MarketData(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(kline[0] / 1000),
                    open=float(kline[1]),
                    high=float(kline[2]),
                    low=float(kline[3]),
                    close=float(kline[4]),
                    volume=float(kline[5]),
                    quote_volume=float(kline[7])
                )
        except Exception as e:
            logger.error(f"获取Binance市场数据失败: {e}")
        return None
    
    async def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook:
        """获取订单簿"""
        endpoint = "/api/v3/depth"
        params = {
            "symbol": symbol.replace("/", ""),
            "limit": depth
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data:
                asks = [(float(price), float(quantity)) for price, quantity in data["asks"]]
                bids = [(float(price), float(quantity)) for price, quantity in data["bids"]]
                return OrderBook(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(data.get("E", time.time() * 1000) / 1000),
                    asks=asks,
                    bids=bids
                )
        except Exception as e:
            logger.error(f"获取Binance订单簿失败: {e}")
        return None
    
    async def place_order(self, order: Order) -> Dict[str, Any]:
        """下单"""
        endpoint = "/api/v3/order"
        params = {
            "symbol": order.symbol.replace("/", ""),
            "side": order.side.upper(),
            "type": order.order_type.upper(),
            "quantity": order.quantity
        }
        
        if order.order_type == "limit":
            params["price"] = order.price
        
        if order.client_order_id:
            params["newClientOrderId"] = order.client_order_id
        
        try:
            data = await self._make_request("POST", endpoint, params)
            return {
                "order_id": data["orderId"],
                "client_order_id": data.get("clientOrderId"),
                "status": data["status"].lower()
            }
        except Exception as e:
            logger.error(f"Binance下单失败: {e}")
            return {"error": str(e)}
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        endpoint = "/api/v3/order"
        params = {
            "symbol": symbol.replace("/", ""),
            "orderId": order_id
        }
        
        try:
            await self._make_request("DELETE", endpoint, params)
            return True
        except Exception as e:
            logger.error(f"Binance取消订单失败: {e}")
            return False
    
    async def get_order(self, order_id: str, symbol: str) -> Order:
        """获取订单信息"""
        endpoint = "/api/v3/order"
        params = {
            "symbol": symbol.replace("/", ""),
            "orderId": order_id
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            return Order(
                order_id=str(data["orderId"]),
                symbol=symbol,
                side=data["side"].lower(),
                order_type=data["type"].lower(),
                quantity=float(data["origQty"]),
                price=float(data.get("price", 0)),
                status=data["status"].lower(),
                executed_quantity=float(data["executedQty"]),
                avg_price=float(data.get("avgPrice", 0)),
                timestamp=datetime.fromtimestamp(data["time"] / 1000),
                client_order_id=data.get("clientOrderId")
            )
        except Exception as e:
            logger.error(f"获取Binance订单信息失败: {e}")
            return None
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """获取未成交订单"""
        endpoint = "/api/v3/openOrders"
        params = {}
        
        if symbol:
            params["symbol"] = symbol.replace("/", "")
        
        try:
            data = await self._make_request("GET", endpoint, params)
            orders = []
            for order_data in data:
                symbol = f"{order_data['symbol'][:3]}/{order_data['symbol'][3:]}"  # 假设格式为BTCUSDT
                orders.append(Order(
                    order_id=str(order_data["orderId"]),
                    symbol=symbol,
                    side=order_data["side"].lower(),
                    order_type=order_data["type"].lower(),
                    quantity=float(order_data["origQty"]),
                    price=float(order_data.get("price", 0)),
                    status=order_data["status"].lower(),
                    executed_quantity=float(order_data["executedQty"]),
                    avg_price=float(order_data.get("avgPrice", 0)),
                    timestamp=datetime.fromtimestamp(order_data["time"] / 1000),
                    client_order_id=order_data.get("clientOrderId")
                ))
            return orders
        except Exception as e:
            logger.error(f"获取Binance未成交订单失败: {e}")
            return []
    
    async def get_balances(self) -> List[Balance]:
        """获取资产余额"""
        endpoint = "/api/v3/account"
        
        try:
            data = await self._make_request("GET", endpoint, {})
            balances = []
            for asset_data in data["balances"]:
                free = float(asset_data["free"])
                locked = float(asset_data["locked"])
                total = free + locked
                if total > 0:
                    balances.append(Balance(
                        asset=asset_data["asset"],
                        free=free,
                        locked=locked,
                        total=total
                    ))
            return balances
        except Exception as e:
            logger.error(f"获取Binance资产余额失败: {e}")
            return []
    
    async def get_exchange_info(self) -> ExchangeInfo:
        """获取交易所信息"""
        endpoint = "/api/v3/exchangeInfo"
        
        try:
            data = await self._make_request("GET", endpoint, {})
            symbols = [f"{s['baseAsset']}/{s['quoteAsset']}" for s in data["symbols"]]
            return ExchangeInfo(
                exchange_id="binance",
                name="Binance",
                api_url=self.api_url,
                ws_url=self.ws_url,
                rate_limit=data.get("rateLimits", []),
                supported_symbols=symbols,
                fee_structure={"maker": 0.001, "taker": 0.001}
            )
        except Exception as e:
            logger.error(f"获取Binance交易所信息失败: {e}")
            return None
    
    async def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """获取交易对信息"""
        endpoint = "/api/v3/exchangeInfo"
        params = {"symbol": symbol.replace("/", "")}
        
        try:
            data = await self._make_request("GET", endpoint, params)
            for s in data["symbols"]:
                if s["symbol"] == symbol.replace("/", ""):
                    return s
        except Exception as e:
            logger.error(f"获取Binance交易对信息失败: {e}")
        return {}
    
    async def subscribe_market_data(self, symbol: str, callback: callable) -> bool:
        """订阅市场数据"""
        try:
            symbol = symbol.replace("/", "").lower()
            ws_url = f"{self.ws_url}/ws/{symbol}@kline_1m"
            
            async def on_message(msg):
                data = json.loads(msg.data)
                if "k" in data:
                    kline = data["k"]
                    market_data = MarketData(
                        symbol=symbol.upper(),
                        timestamp=datetime.fromtimestamp(kline["t"] / 1000),
                        open=float(kline["o"]),
                        high=float(kline["h"]),
                        low=float(kline["l"]),
                        close=float(kline["c"]),
                        volume=float(kline["v"]),
                        quote_volume=float(kline["q"])
                    )
                    await callback(market_data)
            
            conn = await self._session.ws_connect(ws_url)
            self._ws_connections[symbol] = conn
            
            asyncio.create_task(self._handle_ws_connection(conn, on_message))
            return True
        except Exception as e:
            logger.error(f"Binance订阅市场数据失败: {e}")
            return False
    
    async def unsubscribe_market_data(self, symbol: str) -> bool:
        """取消订阅市场数据"""
        try:
            symbol = symbol.replace("/", "").lower()
            if symbol in self._ws_connections:
                conn = self._ws_connections[symbol]
                if not conn.closed:
                    await conn.close()
                del self._ws_connections[symbol]
                return True
        except Exception as e:
            logger.error(f"Binance取消订阅市场数据失败: {e}")
        return False
    
    def _sign_request(self, method: str, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """签名请求"""
        if not self.api_key or not self.api_secret:
            return params
        
        # 添加时间戳
        params["timestamp"] = int(time.time() * 1000)
        
        # 生成签名
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        signature = hmac.new(
            self.api_secret.encode(),
            query_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        params["signature"] = signature
        return params
    
    async def _make_request(self, method: str, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求"""
        url = f"{self.api_url}{endpoint}"
        headers = {}
        
        # 添加API密钥
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        
        # 签名请求
        if self.api_secret and endpoint.startswith("/api/v3/"):
            params = self._sign_request(method, endpoint, params)
        
        try:
            if method == "GET":
                async with self._session.get(url, params=params, headers=headers) as response:
                    data = await response.json()
                    if "error" in data:
                        raise Exception(f"API错误: {data['error']}")
                    return data
            elif method == "POST":
                async with self._session.post(url, data=params, headers=headers) as response:
                    data = await response.json()
                    if "error" in data:
                        raise Exception(f"API错误: {data['error']}")
                    return data
            elif method == "DELETE":
                async with self._session.delete(url, params=params, headers=headers) as response:
                    data = await response.json()
                    if "error" in data:
                        raise Exception(f"API错误: {data['error']}")
                    return data
        except Exception as e:
            logger.error(f"Binance API请求失败: {e}")
            raise
    
    async def _handle_ws_connection(self, conn, callback):
        """处理WebSocket连接"""
        try:
            async for msg in conn:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await callback(msg)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket错误: {msg.data}")
                    break
        except Exception as e:
            logger.error(f"WebSocket处理失败: {e}")
        finally:
            if not conn.closed:
                await conn.close()