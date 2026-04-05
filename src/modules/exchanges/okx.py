"""
OKX交易所实现

基于ExchangeBase抽象类实现OKX API调用
"""

import asyncio
import base64
import hmac
import json
import logging
import ssl
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from functools import wraps

import aiohttp

from .exchange_base import ExchangeBase, MarketData, OrderBook, Order, Balance, ExchangeInfo

logger = logging.getLogger(__name__)


def retry_on_error(max_retries=3, delay=1.0, backoff=2.0, allowed_exceptions=(Exception,)):
    """
    重试装饰器
    
    Args:
        max_retries: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟时间的增长因子
        allowed_exceptions: 允许重试的异常类型
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except allowed_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"⚠️ {func.__name__} 失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                        logger.info(f"⏳ 等待 {current_delay:.1f} 秒后重试...")
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"❌ {func.__name__} 失败，已达到最大重试次数")
                        raise
            
            raise last_exception
        return wrapper
    return decorator


class OKXExchange(ExchangeBase):
    """OKX交易所实现"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_url = "https://www.okx.com" if not self.testnet else "https://www.okx.com"
        self.ws_url = "wss://ws.okx.com:8443" if not self.testnet else "wss://wspap.okx.com:8443"
        self._session = None
        self._ws_connections = {}
        self._request_semaphore = asyncio.Semaphore(10)  # 限制并发请求数
        self._last_request_time = 0
        self._min_request_interval = 0.1  # 最小请求间隔（秒）
    
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
    
    async def _make_request(self, method: str, endpoint: str, params: Dict[str, Any] = None, body: Dict[str, Any] = None) -> Any:
        """发送请求到OKX API - 带重试和限流机制"""
        async with self._request_semaphore:
            current_time = time.time()
            time_since_last = current_time - self._last_request_time
            if time_since_last < self._min_request_interval:
                await asyncio.sleep(self._min_request_interval - time_since_last)
            
            self._last_request_time = time.time()
            
            url = self.api_url + endpoint
            body_str = json.dumps(body, separators=(',', ':')) if body else ""
            
            headers = self._get_headers(method, endpoint, body_str)
            
            logger.debug(f"📤 OKX请求: {method} {endpoint}")
            logger.debug(f"📤 Body: {body_str}")
            logger.debug(f"📤 Headers: OK-ACCESS-KEY={headers.get('OK-ACCESS-KEY')[:8]}..., TIMESTAMP={headers.get('OK-ACCESS-TIMESTAMP')}")
            
            max_retries = 3
            retry_delay = 1.0
            
            proxy = getattr(self, '_proxy_url', None)
            if proxy:
                logger.debug(f"📤 使用代理: {proxy}")
            
            for attempt in range(max_retries + 1):
                try:
                    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
                    
                    if method == "GET":
                        async with self._session.get(url, headers=headers, params=params, timeout=timeout, proxy=proxy, ssl=False) as response:
                            if response.status == 429:  # Rate limit
                                logger.warning(f"⚠️ OKX API 限流，等待 {retry_delay} 秒后重试...")
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                            
                            data = await response.json()
                            if data.get("code") == "0":
                                return data.get("data", [])
                            else:
                                error_code = data.get('code', '')
                                error_msg = data.get('msg', '') or error_code or 'unknown'
                                if error_code == "51001":
                                    logger.debug(f"OKX API交易对不存在: {method} {endpoint} - {error_msg}")
                                else:
                                    logger.error(f"OKX API返回错误: {method} {endpoint} - code={error_code}, msg={error_msg}")
                                raise Exception(f"OKX API错误: {error_msg}")
                                
                    elif method == "POST":
                        async with self._session.post(url, headers=headers, data=body_str, timeout=timeout, proxy=proxy, ssl=False) as response:
                            if response.status == 429:  # Rate limit
                                logger.warning(f"⚠️ OKX API 限流，等待 {retry_delay} 秒后重试...")
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                            
                            data = await response.json()
                            logger.debug(f"📥 OKX响应: {data}")
                            if data.get("code") == "0":
                                return data.get("data", [])
                            else:
                                error_msg = data.get('msg', '') or data.get('code', 'unknown')
                                logger.error(f"OKX API返回错误: {method} {endpoint} - code={data.get('code')}, msg={data.get('msg')}")
                                raise Exception(f"OKX API错误: {error_msg}")
                                
                    elif method == "DELETE":
                        async with self._session.delete(url, headers=headers, json=body, timeout=timeout, proxy=proxy, ssl=False) as response:
                            if response.status == 429:  # Rate limit
                                logger.warning(f"⚠️ OKX API 限流，等待 {retry_delay} 秒后重试...")
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                            
                            data = await response.json()
                            if data.get("code") == "0":
                                return data.get("data", [])
                            else:
                                error_code = data.get('code', '')
                                error_msg = data.get('msg', '') or error_code or 'unknown'
                                if error_code == "51001":
                                    logger.debug(f"OKX API交易对不存在: {method} {endpoint}")
                                else:
                                    logger.error(f"OKX API返回错误: {method} {endpoint} - code={error_code}, msg={error_msg}")
                                raise Exception(f"OKX API错误: {error_msg}")
                                
                except asyncio.TimeoutError as e:
                    if attempt < max_retries:
                        logger.warning(f"⚠️ OKX API 超时 (尝试 {attempt + 1}/{max_retries + 1}): {method} {endpoint}")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 1.5
                        continue
                    else:
                        logger.error(f"❌ OKX API 超时，已达到最大重试次数: {method} {endpoint}")
                        raise
                        
                except aiohttp.ClientConnectorError as e:
                    if attempt < max_retries:
                        logger.warning(f"⚠️ OKX API 连接失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        logger.error(f"❌ OKX API 连接失败，已达到最大重试次数: {e}")
                        raise
                        
                except aiohttp.ClientError as e:
                    if attempt < max_retries and "SSL" in str(e):
                        logger.warning(f"⚠️ OKX API SSL错误 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        logger.error(f"OKX API网络错误: {method} {endpoint} - {type(e).__name__}: {e}")
                        raise
                        
                except Exception as e:
                    error_str = str(e)
                    if "51001" in error_str or "doesn't exist" in error_str:
                        logger.debug(f"OKX API交易对不存在: {method} {endpoint}")
                    else:
                        logger.error(f"OKX API请求失败: {method} {endpoint} - {type(e).__name__}: {e}")
                    raise
    
    async def initialize(self) -> bool:
        """初始化交易所连接"""
        try:
            connector = None
            ssl_context = None
            
            try:
                from src.modules.core.proxy_manager import get_proxy_manager
                proxy_manager = await get_proxy_manager()
                
                if not proxy_manager._running:
                    if hasattr(self, '_config_manager') and self._config_manager:
                        config_manager = self._config_manager
                    else:
                        from src.modules.core.config_manager import get_config_manager
                        config_manager = await get_config_manager()
                    
                    proxy_config = await config_manager.get_config("proxy", {})
                    logger.info(f"📋 加载代理配置: {proxy_config}")
                    await proxy_manager.initialize(proxy_config)
                else:
                    logger.info(f"📋 proxy_manager已初始化, global_proxy={proxy_manager.global_proxy}, use_global_proxy={proxy_manager.use_global_proxy}")
                
                proxy = await proxy_manager.get_proxy("www.okx.com")
                
                if proxy:
                    logger.info(f"✅ 使用代理: {proxy.url}")
                    if proxy.proxy_type.value in ["socks5", "socks4"]:
                        from aiohttp_socks import ProxyConnector
                        connector = ProxyConnector.from_url(proxy.url, ssl=False)
                    else:
                        ssl_context = ssl.create_default_context()
                        ssl_context.check_hostname = False
                        ssl_context.verify_mode = ssl.CERT_NONE
                        connector = aiohttp.TCPConnector(ssl=ssl_context)
                        self._proxy_url = proxy.url
                        logger.info(f"✅ 已配置HTTPS代理SSL上下文 (忽略证书验证)")
                else:
                    logger.warning("⚠️ 未找到可用代理，使用直连")
                    ssl_context = ssl.create_default_context()
                    connector = aiohttp.TCPConnector(ssl=ssl_context)
            except Exception as proxy_error:
                logger.warning(f"⚠️ 加载代理配置失败: {proxy_error}，使用直连")
                import traceback
                traceback.print_exc()
                ssl_context = ssl.create_default_context()
                connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            self._session = aiohttp.ClientSession(connector=connector, connector_owner=True)
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
        
        if "/SWAP" in symbol or symbol.endswith("SWAP"):
            okx_symbol = symbol.replace("/SWAP", "").replace("/", "-")
            if not okx_symbol.endswith("-SWAP"):
                okx_symbol = okx_symbol + "-SWAP"
        else:
            okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
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
            logger.debug(f"获取OKX市场数据失败: {symbol} -> {okx_symbol}: {e}")
        return None
    
    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> List[Dict[str, any]]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对，如 BTC/USDT
            interval: 时间周期，支持 1m, 5m, 15m, 1h, 4h, 1d
            limit: 返回数量，最大300
            
        Returns:
            K线数据列表
        """
        # OKX的时间间隔格式转换
        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D"
        }
        okx_interval = interval_map.get(interval, "1H")
        
        endpoint = "/api/v5/market/candles"
        
        if "/SWAP" in symbol or symbol.endswith("SWAP"):
            okx_symbol = symbol.replace("/SWAP", "").replace("/", "-")
            if not okx_symbol.endswith("-SWAP"):
                okx_symbol = okx_symbol + "-SWAP"
        else:
            okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
        params = {
            "instId": okx_symbol,
            "bar": okx_interval,
            "limit": min(limit, 300)
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data:
                klines = []
                for candle in data:
                    klines.append({
                        "timestamp": int(candle[0]),
                        "open": float(candle[1]),
                        "high": float(candle[2]),
                        "low": float(candle[3]),
                        "close": float(candle[4]),
                        "volume": float(candle[5]),
                        "quote_volume": float(candle[7])
                    })
                return klines
        except Exception as e:
            logger.debug(f"获取OKX K线数据失败: {symbol} -> {okx_symbol}: {e}")
        return []
    
    async def get_multi_timeframe_klines(self, symbol: str, timeframes: List[str] = None) -> Dict[str, List[Dict]]:
        """
        获取多时间周期K线数据
        
        Args:
            symbol: 交易对
            timeframes: 时间周期列表，默认 ["1m", "5m", "15m", "1h", "4h", "1d"]
            
        Returns:
            字典，key为时间周期，value为K线数据列表
        """
        if timeframes is None:
            timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        
        result = {}
        
        for tf in timeframes:
            try:
                klines = await self.get_klines(symbol, tf, limit=100)
                if klines:
                    result[tf] = klines
                    logger.info(f"获取 {symbol} {tf} K线数据成功，共 {len(klines)} 条")
            except Exception as e:
                logger.error(f"获取 {symbol} {tf} K线数据失败: {e}")
                result[tf] = []
        
        return result
    
    async def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook:
        """获取订单簿"""
        endpoint = "/api/v5/market/books"
        
        if "/SWAP" in symbol or symbol.endswith("SWAP"):
            okx_symbol = symbol.replace("/SWAP", "").replace("/", "-")
            if not okx_symbol.endswith("-SWAP"):
                okx_symbol = okx_symbol + "-SWAP"
        else:
            okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
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
            logger.debug(f"获取OKX订单簿失败: {symbol} -> {okx_symbol}: {e}")
        return None
    
    async def place_order(self, order: Order) -> Dict[str, Any]:
        """下单
        
        支持永续合约交易：
        - symbol格式: BTC/USDT/SWAP 或 BTC/USDT
        - 自动转换为OKX格式: BTC-USDT-SWAP
        """
        endpoint = "/api/v5/trade/order"
        
        # 交易对格式转换
        symbol = order.symbol
        if "/SWAP" in symbol or symbol.endswith("SWAP"):
            okx_symbol = symbol.replace("/SWAP", "").replace("/", "-")
            if not okx_symbol.endswith("-SWAP"):
                okx_symbol = okx_symbol + "-SWAP"
        else:
            # 默认使用永续合约
            okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
        # 判断是开仓还是平仓
        is_close = hasattr(order, 'metadata') and order.metadata and order.metadata.get('is_close', False)
        
        # OKX的订单方向转换
        # 对于永续合约：
        # - 开多: side=buy, posSide=long
        # - 开空: side=sell, posSide=short
        # - 平多: side=sell, posSide=long
        # - 平空: side=buy, posSide=short
        side_map = {"buy": "buy", "sell": "sell"}
        ord_type_map = {"market": "market", "limit": "limit"}
        
        body = {
            "instId": okx_symbol,
            "tdMode": "cross",  # 全仓模式
            "side": side_map.get(order.side, "buy"),
            "ordType": ord_type_map.get(order.order_type, "market"),
            "sz": str(order.quantity)
        }
        
        # 永续合约需要指定posSide
        if "-SWAP" in okx_symbol:
            if hasattr(order, 'metadata') and order.metadata:
                pos_side = order.metadata.get('posSide', 'net')
                if pos_side in ['long', 'short']:
                    body["posSide"] = pos_side
            elif is_close:
                # 平仓时根据side推断posSide
                if order.side == "buy":
                    body["posSide"] = "short"  # 平空
                else:
                    body["posSide"] = "long"   # 平多
        
        if order.order_type == "limit" and order.price:
            body["px"] = str(order.price)
        
        if order.client_order_id:
            body["clOrdId"] = order.client_order_id
        
        logger.info(f"📤 OKX下单请求: {body}")
        
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
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """获取持仓信息"""
        endpoint = "/api/v5/account/positions"
        
        try:
            data = await self._make_request("GET", endpoint)
            positions = []
            
            for pos_data in data:
                positions.append({
                    "symbol": pos_data.get("instId", "").replace("-", "/"),
                    "side": "long" if pos_data.get("posSide") == "long" else "short",
                    "size": float(pos_data.get("pos", 0) or 0),
                    "entry_price": float(pos_data.get("avgPx", 0) or 0),
                    "unrealized_pnl": float(pos_data.get("upl", 0) or 0),
                    "leverage": float(pos_data.get("lever", 1) or 1),
                    "margin": float(pos_data.get("margin", 0) or 0),
                    "liquidation_price": float(pos_data.get("liqPx", 0) or 0),
                    "timestamp": int(pos_data.get("cTime", 0) or 0)
                })
            
            return positions
        except Exception as e:
            logger.error(f"获取OKX持仓信息失败: {e}")
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
        """获取行情数据（便捷方法）
        
        自动识别现货和永续合约：
        - 现货: BTC/USDT -> BTC-USDT (需要指定 instType=SP)
        - 永续合约: BTC/USDT/SWAP 或 BTC/USDT -> BTC-USDT-SWAP (默认)
        """
        endpoint = "/api/v5/market/ticker"
        
        if "/SWAP" in symbol or symbol.endswith("SWAP"):
            okx_symbol = symbol.replace("/SWAP", "").replace("/", "-")
            if not okx_symbol.endswith("-SWAP"):
                okx_symbol = okx_symbol + "-SWAP"
        else:
            okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
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
            error_str = str(e)
            if "51001" in error_str or "doesn't exist" in error_str:
                logger.debug(f"交易对 {okx_symbol} 不存在，尝试现货...")
                try:
                    spot_symbol = symbol.replace("/SWAP", "").replace("/", "-")
                    params["instId"] = spot_symbol
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
                except Exception as e2:
                    logger.debug(f"交易对 {symbol} 行情获取失败: {e2}")
            else:
                logger.debug(f"获取OKX行情失败: {e}")
        return {}
    
    async def set_leverage(self, symbol: str, leverage: int, margin_mode: str = "cross") -> Dict[str, Any]:
        """设置杠杆倍数
        
        Args:
            symbol: 交易对，如 BTC/USDT
            leverage: 杠杆倍数
            margin_mode: 保证金模式 cross(全仓) 或 isolated(逐仓)
        """
        endpoint = "/api/v5/account/set-leverage"
        okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
        body = {
            "instId": okx_symbol,
            "lever": str(leverage),
            "mgnMode": margin_mode
        }
        
        try:
            data = await self._make_request("POST", endpoint, body=body)
            logger.info(f"✅ 设置杠杆成功: {symbol} {leverage}x ({margin_mode})")
            return {
                "success": True,
                "symbol": symbol,
                "leverage": leverage,
                "margin_mode": margin_mode,
                "data": data
            }
        except Exception as e:
            logger.error(f"设置杠杆失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def open_swap_position(self, symbol: str, side: str, size: float, 
                                  leverage: int = 20, price: float = None,
                                  margin_mode: str = "cross") -> Dict[str, Any]:
        """开永续合约仓位
        
        Args:
            symbol: 交易对，如 BTC/USDT
            side: 方向 long/short
            size: 仓位大小（张数或币数）
            leverage: 杠杆倍数
            price: 限价单价格，None为市价单
            margin_mode: 保证金模式 cross/isolated
        """
        okx_symbol = symbol.replace("/", "-") + "-SWAP"
        if "--" in okx_symbol:
            okx_symbol = okx_symbol.replace("--", "-")
        
        await self.set_leverage(symbol, leverage, margin_mode)
        
        order_type = "market" if price is None else "limit"
        
        pos_side = await self._get_position_side(side)
        
        body = {
            "instId": okx_symbol,
            "tdMode": margin_mode,
            "side": "buy" if side == "long" else "sell",
            "posSide": pos_side,
            "ordType": order_type,
            "sz": str(size)
        }
        
        if price:
            body["px"] = str(price)
        
        endpoint = "/api/v5/trade/order"
        
        logger.info(f"📤 发送订单请求: {body}")
        
        try:
            data = await self._make_request("POST", endpoint, body=body)
            order_data = data[0] if isinstance(data, list) and len(data) > 0 else data
            logger.info(f"✅ 开仓成功: {symbol} {side} {size} @ {leverage}x")
            return {
                "success": True,
                "orderId": order_data.get("ordId"),
                "symbol": symbol,
                "side": side,
                "size": size,
                "leverage": leverage,
                "data": data
            }
        except Exception as e:
            logger.error(f"开仓失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _get_position_side(self, side: str) -> str:
        """获取持仓方向 - 适配单向/双向持仓模式"""
        try:
            account_config = await self._get_account_config()
            pos_mode = account_config.get("posMode", "long_short_mode")
            
            if pos_mode == "net_mode":
                return "net"
            else:
                return side
        except Exception as e:
            logger.warning(f"获取持仓模式失败，使用默认: {e}")
            return side
    
    async def _get_account_config(self) -> Dict[str, Any]:
        """获取账户配置"""
        endpoint = "/api/v5/account/config"
        try:
            data = await self._make_request("GET", endpoint)
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error(f"获取账户配置失败: {e}")
            return {}
    
    async def close_swap_position(self, symbol: str, side: str, size: float = None) -> Dict[str, Any]:
        """平永续合约仓位
        
        Args:
            symbol: 交易对
            side: 方向 long/short
            size: 平仓数量，None为全部平仓
        """
        okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
        if size is None:
            positions = await self.get_positions()
            for pos in positions:
                if pos["symbol"].replace("/USDT", "") == symbol.replace("/USDT", ""):
                    size = abs(float(pos["size"]))
                    break
        
        if size is None or size <= 0:
            return {"success": False, "error": "未找到持仓或数量为0"}
        
        pos_side = await self._get_position_side(side)
        
        body = {
            "instId": okx_symbol,
            "tdMode": "cross",
            "side": "sell" if side == "long" else "buy",
            "posSide": pos_side,
            "ordType": "market",
            "sz": str(size)
        }
        
        endpoint = "/api/v5/trade/order"
        
        try:
            data = await self._make_request("POST", endpoint, body=body)
            logger.info(f"✅ 平仓成功: {symbol} {side} {size}")
            return {
                "success": True,
                "orderId": data.get("ordId") if isinstance(data, dict) else data[0].get("ordId") if isinstance(data, list) else None,
                "symbol": symbol,
                "side": side,
                "size": size,
                "data": data
            }
        except Exception as e:
            logger.error(f"平仓失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_swap_ticker(self, symbol: str) -> Dict[str, Any]:
        """获取永续合约行情"""
        endpoint = "/api/v5/market/ticker"
        okx_symbol = symbol.replace("/", "-") + "-SWAP"
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
                    "funding_rate": float(ticker.get("fundingRate", 0)),
                    "timestamp": int(ticker.get("ts", 0))
                }
        except Exception as e:
            logger.error(f"获取永续合约行情失败: {e}")
        return {}
    
    async def get_swap_klines(self, symbol: str, interval: str = "1H", limit: int = 100) -> List[Dict[str, Any]]:
        """获取永续合约K线数据"""
        endpoint = "/api/v5/market/candles"
        okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
        interval_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1H": "1H", "4H": "4H", "1D": "1D", "1W": "1W"
        }
        bar = interval_map.get(interval, "1H")
        
        params = {
            "instId": okx_symbol,
            "bar": bar,
            "limit": str(limit)
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            klines = []
            
            for candle in data:
                klines.append({
                    "timestamp": int(candle[0]),
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5])
                })
            
            return list(reversed(klines))
        except Exception as e:
            logger.error(f"获取永续合约K线失败: {e}")
            return []
    
    async def create_grid_order(self, symbol: str, grid_levels: int = 10, 
                                 grid_spacing: float = 0.01, total_size: float = 1.0,
                                 leverage: int = 20, side: str = "long") -> Dict[str, Any]:
        """创建网格交易订单
        
        Args:
            symbol: 交易对
            grid_levels: 网格层数
            grid_spacing: 网格间距（百分比）
            total_size: 总仓位大小
            leverage: 杠杆倍数
            side: 方向 long/short
        """
        ticker = await self.get_swap_ticker(symbol)
        if not ticker:
            return {"success": False, "error": "无法获取行情"}
        
        current_price = ticker["last"]
        size_per_grid = total_size / grid_levels
        
        orders = []
        
        for i in range(1, grid_levels + 1):
            if side == "long":
                price = current_price * (1 - grid_spacing * i)
            else:
                price = current_price * (1 + grid_spacing * i)
            
            result = await self.open_swap_position(
                symbol=symbol,
                side=side,
                size=size_per_grid,
                leverage=leverage,
                price=round(price, 2),
                margin_mode="cross"
            )
            
            orders.append({
                "level": i,
                "price": price,
                "size": size_per_grid,
                "result": result
            })
        
        logger.info(f"✅ 创建网格订单: {symbol} {grid_levels}层 间距{grid_spacing*100}%")
        return {
            "success": True,
            "symbol": symbol,
            "current_price": current_price,
            "grid_levels": grid_levels,
            "grid_spacing": grid_spacing,
            "orders": orders
        }
    
    async def get_open_interest(self, symbol: str) -> Optional[Dict[str, float]]:
        """获取持仓量"""
        endpoint = "/api/v5/public/open-interest"
        okx_symbol = symbol.replace("/", "-") + "-SWAP"
        params = {"instId": okx_symbol}
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data:
                oi = float(data.get("oi", 0))
                vol24h = float(data.get("vol24h", 0))
                return {
                    "open_interest": oi,
                    "volume_24h": vol24h
                }
            return None
        except Exception as e:
            logger.error(f"获取持仓量失败: {e}")
        return None
    
    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        """获取资金费率"""
        endpoint = "/api/v5/public/funding-rate"
        okx_symbol = symbol.replace("/", "-") + "-SWAP"
        params = {"instId": okx_symbol}
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data:
                return float(data.get("fundingRate", 0))
            return None
        except Exception as e:
            logger.error(f"获取资金费率失败: {e}")
        return None
    
    async def get_long_short_ratio(self, symbol: str) -> Optional[Dict[str, float]]:
        """获取多空比 - 使用订单簿数据计算"""
        try:
            okx_symbol = symbol.replace("/", "-") + "-SWAP"
            order_book = await self.get_order_book(okx_symbol, depth=20)
            
            if not order_book:
                return None
            
            bids = order_book.bids if hasattr(order_book, 'bids') else []
            asks = order_book.asks if hasattr(order_book, 'asks') else []
            
            if not bids or not asks:
                return None
            
            bid_volume = sum(float(b[1]) if len(b) > 1 else 0 for b in bids)
            ask_volume = sum(float(a[1]) if len(a) > 1 else 0 for a in asks)
            
            total = bid_volume + ask_volume
            if total == 0:
                return None
            
            long_ratio = bid_volume / total
            short_ratio = ask_volume / total
            
            return {
                "long": long_ratio,
                "short": short_ratio,
                "long_short_ratio": long_ratio / short_ratio if short_ratio > 0 else 1,
                "source": "order_book"
            }
        except Exception as e:
            logger.debug(f"获取多空比失败: {e}")
        return None
