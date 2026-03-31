"""
OKX交易所实现

基于ExchangeBase抽象类实现OKX API调用
"""

import asyncio
import base64
import hmac
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

import aiohttp

from .exchange_base import ExchangeBase, MarketData, OrderBook, Order, Balance, ExchangeInfo

logger = logging.getLogger(__name__)


class OKXExchange(ExchangeBase):
    """OKX交易所实现"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_url = "https://www.okx.com" if not self.testnet else "https://www.okx.com"
        self.ws_url = "wss://ws.okx.com:8443" if not self.testnet else "wss://wspap.okx.com:8443"
        self._session = None
        self._ws_connections = {}
    
    def _generate_signature(self, timestamp: str, method: str, endpoint: str, body: str = "") -> str:
        """生成OKX API签名"""
        message = timestamp + method.upper() + endpoint + body
        mac = hmac.new(self.api_secret.encode('utf-8'), message.encode('utf-8'), digestmod='sha256')
        return base64.b64encode(mac.digest()).decode('utf-8')
    
    def _get_headers(self, method: str, endpoint: str, body: str = "") -> Dict[str, str]:
        """获取请求头"""
        # 使用 UTC 时间戳（ISO 8601 格式）
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        signature = self._generate_signature(timestamp, method, endpoint, body)
        
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.api_passphrase or "",
            "Content-Type": "application/json"
        }
        return headers
    
    async def _make_request(self, method: str, endpoint: str, params: Dict[str, Any] = None, body: Dict[str, Any] = None) -> Dict[str, Any]:
        """发送请求到OKX API"""
        url = self.api_url + endpoint
        body_str = json.dumps(body) if body else ""
        
        headers = self._get_headers(method, endpoint, body_str)
        
        try:
            timeout = aiohttp.ClientTimeout(total=60, connect=30)
            
            # 准备代理参数
            proxy = getattr(self, '_proxy_url', None)
            
            if method == "GET":
                async with self._session.get(url, headers=headers, params=params, timeout=timeout, proxy=proxy) as response:
                    data = await response.json()
                    if data.get("code") == "0":
                        return data.get("data", {})
                    else:
                        raise Exception(f"OKX API错误: {data.get('msg')}")
            elif method == "POST":
                async with self._session.post(url, headers=headers, json=body, timeout=timeout, proxy=proxy) as response:
                    data = await response.json()
                    if data.get("code") == "0":
                        return data.get("data", {})
                    else:
                        raise Exception(f"OKX API错误: {data.get('msg')}")
            elif method == "DELETE":
                async with self._session.delete(url, headers=headers, json=body, timeout=timeout, proxy=proxy) as response:
                    data = await response.json()
                    if data.get("code") == "0":
                        return data.get("data", {})
                    else:
                        raise Exception(f"OKX API错误: {data.get('msg')}")
        except Exception as e:
            logger.error(f"OKX API请求失败: {method} {endpoint} - {e}")
            raise
    
    async def initialize(self) -> bool:
        """初始化交易所连接"""
        try:
            # 尝试加载代理配置
            connector = None
            try:
                from src.modules.core.proxy_manager import get_proxy_manager
                proxy_manager = await get_proxy_manager()
                proxy = await proxy_manager.get_proxy("www.okx.com")
                
                if proxy:
                    logger.info(f"使用代理: {proxy.url}")
                    if proxy.proxy_type.value in ["socks5", "socks4"]:
                        # 使用 SOCKS 代理
                        from aiohttp_socks import ProxyConnector
                        connector = ProxyConnector.from_url(proxy.url)
                    else:
                        # HTTP/HTTPS 代理
                        connector = aiohttp.TCPConnector()
                        self._proxy_url = proxy.url
                else:
                    connector = aiohttp.TCPConnector()
            except Exception as proxy_error:
                logger.warning(f"加载代理配置失败: {proxy_error}")
                connector = aiohttp.TCPConnector()
            
            self._session = aiohttp.ClientSession(connector=connector)
            # 测试连接
            await self.get_exchange_info()
            self._running = True
            logger.info(f"OKX交易所初始化成功")
            return True
        except Exception as e:
            logger.error(f"OKX交易所初始化失败: {e}")
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
            logger.info(f"OKX交易所清理完成")
        except Exception as e:
            logger.error(f"OKX交易所清理失败: {e}")
    
    async def get_market_data(self, symbol: str, interval: str = "1m") -> MarketData:
        """获取市场数据"""
        # OKX的时间间隔格式转换
        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D"
        }
        okx_interval = interval_map.get(interval, "1m")
        
        endpoint = "/api/v5/market/candles"
        okx_symbol = symbol.replace("/", "-")
        params = {
            "instId": okx_symbol,
            "bar": okx_interval,
            "limit": 1
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data and len(data) > 0:
                candle = data[0]
                return MarketData(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(int(candle[0]) / 1000),
                    open=float(candle[1]),
                    high=float(candle[2]),
                    low=float(candle[3]),
                    close=float(candle[4]),
                    volume=float(candle[5]),
                    quote_volume=float(candle[7])
                )
        except Exception as e:
            logger.error(f"获取OKX市场数据失败: {e}")
        return None
    
    async def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook:
        """获取订单簿"""
        endpoint = "/api/v5/market/books"
        okx_symbol = symbol.replace("/", "-")
        params = {
            "instId": okx_symbol,
            "sz": depth
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data and len(data) > 0:
                order_book = data[0]
                asks = [(float(price), float(quantity)) for price, quantity, _, _ in order_book.get("asks", [])]
                bids = [(float(price), float(quantity)) for price, quantity, _, _ in order_book.get("bids", [])]
                return OrderBook(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(int(order_book["ts"]) / 1000),
                    asks=asks,
                    bids=bids
                )
        except Exception as e:
            logger.error(f"获取OKX订单簿失败: {e}")
        return None
    
    async def place_order(self, order: Order) -> Dict[str, Any]:
        """下单"""
        endpoint = "/api/v5/trade/order"
        okx_symbol = order.symbol.replace("/", "-")
        
        # OKX的订单方向转换
        side_map = {"buy": "buy", "sell": "sell"}
        ord_type_map = {"market": "market", "limit": "limit"}
        
        body = {
            "instId": okx_symbol,
            "tdMode": "cross",  # 全仓模式
            "side": side_map.get(order.side, "buy"),
            "ordType": ord_type_map.get(order.order_type, "limit"),
            "sz": str(order.quantity)
        }
        
        if order.order_type == "limit" and order.price:
            body["px"] = str(order.price)
        
        if order.client_order_id:
            body["clOrdId"] = order.client_order_id
        
        try:
            data = await self._make_request("POST", endpoint, body=body)
            if data and len(data) > 0:
                result = data[0]
                return {
                    "order_id": result.get("ordId"),
                    "client_order_id": result.get("clOrdId"),
                    "status": "success",
                    "result": result
                }
        except Exception as e:
            logger.error(f"OKX下单失败: {e}")
            return {"status": "error", "message": str(e)}
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        endpoint = "/api/v5/trade/cancel-order"
        okx_symbol = symbol.replace("/", "-")
        
        body = {
            "instId": okx_symbol,
            "ordId": order_id
        }
        
        try:
            await self._make_request("POST", endpoint, body=body)
            return True
        except Exception as e:
            logger.error(f"OKX取消订单失败: {e}")
            return False
    
    async def get_order(self, order_id: str, symbol: str) -> Order:
        """获取订单信息"""
        endpoint = "/api/v5/trade/order"
        okx_symbol = symbol.replace("/", "-")
        
        params = {
            "instId": okx_symbol,
            "ordId": order_id
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data and len(data) > 0:
                order_data = data[0]
                
                # 状态映射
                status_map = {
                    "live": "open",
                    "partially_filled": "partial",
                    "filled": "closed",
                    "cancelled": "cancelled"
                }
                
                return Order(
                    order_id=order_data["ordId"],
                    symbol=symbol,
                    side=order_data["side"],
                    order_type=order_data["ordType"],
                    quantity=float(order_data["sz"]),
                    price=float(order_data["px"]) if order_data.get("px") else None,
                    status=status_map.get(order_data["state"], "unknown"),
                    executed_quantity=float(order_data["accFillSz"]),
                    avg_price=float(order_data["avgPx"]) if order_data.get("avgPx") else 0.0,
                    timestamp=datetime.fromtimestamp(int(order_data["cTime"]) / 1000),
                    client_order_id=order_data.get("clOrdId")
                )
        except Exception as e:
            logger.error(f"获取OKX订单信息失败: {e}")
        return None
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """获取未成交订单"""
        endpoint = "/api/v5/trade/orders-pending"
        
        params = {"instType": "SPOT"}
        if symbol:
            okx_symbol = symbol.replace("/", "-")
            params["instId"] = okx_symbol
        
        try:
            data = await self._make_request("GET", endpoint, params)
            orders = []
            
            for order_data in data:
                status_map = {
                    "live": "open",
                    "partially_filled": "partial",
                    "filled": "closed",
                    "cancelled": "cancelled"
                }
                
                orders.append(Order(
                    order_id=order_data["ordId"],
                    symbol=order_data["instId"].replace("-", "/"),
                    side=order_data["side"],
                    order_type=order_data["ordType"],
                    quantity=float(order_data["sz"]),
                    price=float(order_data["px"]) if order_data.get("px") else None,
                    status=status_map.get(order_data["state"], "unknown"),
                    executed_quantity=float(order_data["accFillSz"]),
                    avg_price=float(order_data["avgPx"]) if order_data.get("avgPx") else 0.0,
                    timestamp=datetime.fromtimestamp(int(order_data["cTime"]) / 1000),
                    client_order_id=order_data.get("clOrdId")
                ))
            
            return orders
        except Exception as e:
            logger.error(f"获取OKX未成交订单失败: {e}")
            return []
    
    async def get_balances(self) -> List[Balance]:
        """获取资产余额"""
        endpoint = "/api/v5/account/balance"
        
        try:
            data = await self._make_request("GET", endpoint)
            balances = []
            
            if data and len(data) > 0:
                for balance_data in data[0].get("details", []):
                    balances.append(Balance(
                        asset=balance_data["ccy"],
                        free=float(balance_data["availEq"]),
                        locked=float(balance_data["frozenBal"]),
                        total=float(balance_data["eq"])
                    ))
            
            return balances
        except Exception as e:
            logger.error(f"获取OKX资产余额失败: {e}")
            return []
    
    async def get_exchange_info(self) -> ExchangeInfo:
        """获取交易所信息"""
        endpoint = "/api/v5/public/instruments"
        params = {"instType": "SPOT"}
        
        try:
            data = await self._make_request("GET", endpoint, params)
            
            supported_symbols = []
            for inst in data:
                supported_symbols.append(inst["instId"].replace("-", "/"))
            
            return ExchangeInfo(
                exchange_id="okx",
                name="OKX",
                api_url=self.api_url,
                ws_url=self.ws_url,
                rate_limit=20,
                supported_symbols=supported_symbols,
                fee_structure={
                    "maker": 0.001,
                    "taker": 0.0015
                }
            )
        except Exception as e:
            logger.error(f"获取OKX交易所信息失败: {e}")
            # 返回默认信息
            return ExchangeInfo(
                exchange_id="okx",
                name="OKX",
                api_url=self.api_url,
                ws_url=self.ws_url,
                rate_limit=20,
                supported_symbols=[],
                fee_structure={}
            )
    
    async def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """获取交易对信息"""
        endpoint = "/api/v5/public/instruments"
        okx_symbol = symbol.replace("/", "-")
        params = {
            "instType": "SPOT",
            "instId": okx_symbol
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data and len(data) > 0:
                inst = data[0]
                return {
                    "symbol": symbol,
                    "base_currency": inst.get("baseCcy", ""),
                    "quote_currency": inst.get("quoteCcy", ""),
                    "min_order_size": float(inst.get("minSz", 0)),
                    "max_order_size": float(inst.get("maxSz", 0)),
                    "tick_size": float(inst.get("tickSz", 0)),
                    "price_precision": len(inst.get("tickSz", "0").split(".")[1]) if "." in inst.get("tickSz", "") else 0
                }
        except Exception as e:
            logger.error(f"获取OKX交易对信息失败: {e}")
        return {}
    
    async def subscribe_market_data(self, symbol: str, callback: Any) -> bool:
        """订阅市场数据"""
        # 暂时使用轮询方式，WebSocket实现可以后续添加
        logger.info(f"OKX订阅市场数据: {symbol}")
        return True
    
    async def unsubscribe_market_data(self, symbol: str) -> bool:
        """取消订阅市场数据"""
        logger.info(f"OKX取消订阅市场数据: {symbol}")
        return True
    
    async def get_balance(self) -> Dict[str, float]:
        """获取账户余额（便捷方法）"""
        balances = await self.get_balances()
        return {b.asset: b.free for b in balances if b.free > 0}
    
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """获取行情数据（便捷方法）"""
        endpoint = "/api/v5/market/ticker"
        okx_symbol = symbol.replace("/", "-")
        params = {"instId": okx_symbol}
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data and len(data) > 0:
                ticker = data[0]
                return {
                    "symbol": symbol,
                    "last": float(ticker.get("last", 0)),
                    "bid": float(ticker.get("bidPx", 0)),
                    "ask": float(ticker.get("askPx", 0)),
                    "high": float(ticker.get("high24h", 0)),
                    "low": float(ticker.get("low24h", 0)),
                    "volume": float(ticker.get("vol24h", 0)),
                    "change": float(ticker.get("change24h", 0)),
                    "timestamp": int(ticker.get("ts", 0))
                }
        except Exception as e:
            logger.error(f"获取OKX行情失败: {e}")
        return {}
