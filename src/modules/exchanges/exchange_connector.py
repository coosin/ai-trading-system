"""
交易所连接器 - 统一的交易接口

功能：
1. 支持多个交易所（Binance、Coinbase、OKX等）
2. WebSocket实时数据连接
3. REST API交易操作
4. 自动重连和故障转移
5. 订单管理和状态同步
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import aiohttp
import websockets

logger = logging.getLogger(__name__)


class ExchangeType(Enum):
    """交易所类型"""
    BINANCE = "binance"
    COINBASE = "coinbase"
    OKX = "okx"
    BYBIT = "bybit"
    KRAKEN = "kraken"


class ConnectionStatus(Enum):
    """连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class ExchangeConfig:
    """交易所配置"""
    exchange_type: ExchangeType
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None  # 用于OKX等
    sandbox: bool = True
    testnet: bool = False
    
    # 连接配置
    ws_reconnect_interval: int = 5
    ws_reconnect_attempts: int = 10
    rest_timeout: int = 30
    
    # 限流配置
    rate_limit_enabled: bool = True
    rate_limit_requests_per_second: int = 10


@dataclass
class MarketData:
    """市场数据"""
    symbol: str
    timestamp: datetime
    price: float
    volume: float
    bid: float
    ask: float
    bid_volume: float
    ask_volume: float
    data_type: str = "ticker"  # ticker, trade, orderbook
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderUpdate:
    """订单更新"""
    order_id: str
    client_order_id: str
    symbol: str
    status: str
    side: str
    order_type: str
    price: float
    quantity: float
    filled_quantity: float
    remaining_quantity: float
    avg_fill_price: float
    commission: float
    timestamp: datetime
    raw_data: Dict[str, Any] = field(default_factory=dict)


class BaseExchangeConnector(ABC):
    """交易所连接器基类"""
    
    def __init__(self, config: ExchangeConfig):
        self.config = config
        self.status = ConnectionStatus.DISCONNECTED
        self.ws_connection = None
        self.session = None
        self._reconnect_attempts = 0
        self._running = False
        
        # 回调函数
        self.on_market_data: Optional[Callable[[MarketData], None]] = None
        self.on_order_update: Optional[Callable[[OrderUpdate], None]] = None
        self.on_trade_update: Optional[Callable[[Dict], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None
        
        # 订阅管理
        self._subscribed_symbols: set = set()
        self._lock = asyncio.Lock()
    
    @property
    @abstractmethod
    def name(self) -> str:
        """交易所名称"""
        pass
    
    @property
    @abstractmethod
    def ws_url(self) -> str:
        """WebSocket URL"""
        pass
    
    @property
    @abstractmethod
    def rest_url(self) -> str:
        """REST API URL"""
        pass
    
    async def initialize(self):
        """初始化连接器"""
        logger.info(f"初始化 {self.name} 连接器...")
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.rest_timeout)
        )
        self._running = True
        logger.info(f"{self.name} 连接器初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        logger.info(f"清理 {self.name} 连接器...")
        self._running = False
        
        if self.ws_connection:
            await self.ws_connection.close()
        
        if self.session:
            await self.session.close()
        
        logger.info(f"{self.name} 连接器清理完成")
    
    async def connect(self):
        """建立WebSocket连接"""
        async with self._lock:
            if self.status == ConnectionStatus.CONNECTED:
                return
            
            self.status = ConnectionStatus.CONNECTING
            
            try:
                logger.info(f"连接 {self.name} WebSocket...")
                self.ws_connection = await websockets.connect(self.ws_url)
                self.status = ConnectionStatus.CONNECTED
                self._reconnect_attempts = 0
                logger.info(f"{self.name} WebSocket 连接成功")
                
                # 重新订阅之前的频道
                if self._subscribed_symbols:
                    await self._resubscribe()
                
                # 启动消息处理循环
                asyncio.create_task(self._message_loop())
                
            except Exception as e:
                logger.error(f"{self.name} WebSocket 连接失败: {e}")
                self.status = ConnectionStatus.ERROR
                await self._handle_reconnect()
    
    async def disconnect(self):
        """断开连接"""
        async with self._lock:
            if self.ws_connection:
                await self.ws_connection.close()
                self.ws_connection = None
            self.status = ConnectionStatus.DISCONNECTED
            logger.info(f"{self.name} WebSocket 已断开")
    
    async def _handle_reconnect(self):
        """处理重连"""
        if self._reconnect_attempts >= self.config.ws_reconnect_attempts:
            logger.error(f"{self.name} 重连次数超过限制，停止重连")
            self.status = ConnectionStatus.ERROR
            return
        
        self._reconnect_attempts += 1
        self.status = ConnectionStatus.RECONNECTING
        
        logger.info(f"{self.name} 将在 {self.config.ws_reconnect_interval} 秒后重连 (尝试 {self._reconnect_attempts}/{self.config.ws_reconnect_attempts})")
        await asyncio.sleep(self.config.ws_reconnect_interval)
        
        if self._running:
            await self.connect()
    
    async def _message_loop(self):
        """消息处理循环"""
        try:
            async for message in self.ws_connection:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError:
                    logger.warning(f"收到无效的JSON消息: {message}")
                except Exception as e:
                    logger.error(f"处理消息时出错: {e}")
                    if self.on_error:
                        await self.on_error(e)
        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"{self.name} WebSocket 连接关闭")
            if self._running:
                await self._handle_reconnect()
        except Exception as e:
            logger.error(f"{self.name} 消息循环出错: {e}")
            if self._running:
                await self._handle_reconnect()
    
    @abstractmethod
    async def _handle_message(self, data: Dict[str, Any]):
        """处理WebSocket消息"""
        pass
    
    @abstractmethod
    async def _resubscribe(self):
        """重新订阅频道"""
        pass
    
    @abstractmethod
    async def subscribe_ticker(self, symbols: List[str]):
        """订阅行情数据"""
        pass
    
    @abstractmethod
    async def subscribe_orderbook(self, symbols: List[str], depth: int = 10):
        """订阅订单簿数据"""
        pass
    
    @abstractmethod
    async def subscribe_trades(self, symbols: List[str]):
        """订阅成交数据"""
        pass
    
    @abstractmethod
    async def subscribe_orders(self):
        """订阅订单更新"""
        pass
    
    @abstractmethod
    async def place_order(self, symbol: str, side: str, order_type: str,
                         quantity: float, price: Optional[float] = None,
                         client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """下单"""
        pass
    
    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """撤单"""
        pass
    
    @abstractmethod
    async def get_order_status(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """查询订单状态"""
        pass
    
    @abstractmethod
    async def get_account_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """获取持仓信息"""
        pass
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """生成签名"""
        query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
        signature = hmac.new(
            self.config.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature


class BinanceConnector(BaseExchangeConnector):
    """币安交易所连接器"""
    
    @property
    def name(self) -> str:
        return "Binance"
    
    @property
    def ws_url(self) -> str:
        if self.config.testnet:
            return "wss://testnet.binance.vision/ws"
        return "wss://stream.binance.com:9443/ws"
    
    @property
    def rest_url(self) -> str:
        if self.config.testnet:
            return "https://testnet.binance.vision"
        return "https://api.binance.com"
    
    async def _handle_message(self, data: Dict[str, Any]):
        """处理币安WebSocket消息"""
        if 'e' in data:
            event_type = data['e']
            
            if event_type == '24hrTicker':
                # 行情数据
                market_data = MarketData(
                    symbol=data['s'],
                    timestamp=datetime.fromtimestamp(data['E'] / 1000),
                    price=float(data['c']),
                    volume=float(data['v']),
                    bid=float(data['b']),
                    ask=float(data['a']),
                    bid_volume=float(data['B']),
                    ask_volume=float(data['A']),
                    data_type='ticker',
                    raw_data=data
                )
                if self.on_market_data:
                    await self.on_market_data(market_data)
            
            elif event_type == 'executionReport':
                # 订单更新
                order_update = OrderUpdate(
                    order_id=data['i'],
                    client_order_id=data['c'],
                    symbol=data['s'],
                    status=data['X'],
                    side=data['S'],
                    order_type=data['o'],
                    price=float(data['p']),
                    quantity=float(data['q']),
                    filled_quantity=float(data['z']),
                    remaining_quantity=float(data['q']) - float(data['z']),
                    avg_fill_price=float(data['L']) if data['L'] else 0,
                    commission=float(data['n']) if data['n'] else 0,
                    timestamp=datetime.fromtimestamp(data['E'] / 1000),
                    raw_data=data
                )
                if self.on_order_update:
                    await self.on_order_update(order_update)
    
    async def _resubscribe(self):
        """重新订阅"""
        if self._subscribed_symbols:
            await self.subscribe_ticker(list(self._subscribed_symbols))
    
    async def subscribe_ticker(self, symbols: List[str]):
        """订阅行情"""
        streams = [f"{s.lower()}@ticker" for s in symbols]
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": int(time.time())
        }
        await self.ws_connection.send(json.dumps(subscribe_msg))
        self._subscribed_symbols.update(symbols)
        logger.info(f"订阅行情: {symbols}")
    
    async def subscribe_orderbook(self, symbols: List[str], depth: int = 10):
        """订阅订单簿"""
        streams = [f"{s.lower()}@depth{depth}" for s in symbols]
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": int(time.time())
        }
        await self.ws_connection.send(json.dumps(subscribe_msg))
        logger.info(f"订阅订单簿: {symbols}")
    
    async def subscribe_trades(self, symbols: List[str]):
        """订阅成交"""
        streams = [f"{s.lower()}@trade" for s in symbols]
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": int(time.time())
        }
        await self.ws_connection.send(json.dumps(subscribe_msg))
        logger.info(f"订阅成交: {symbols}")
    
    async def subscribe_orders(self):
        """订阅订单更新（需要认证）"""
        listen_key = await self._get_listen_key()
        # 连接到用户数据流
        user_ws_url = f"{self.ws_url}/{listen_key}"
        # 这里需要单独连接用户数据流
        logger.info("订阅订单更新")
    
    async def _get_listen_key(self) -> str:
        """获取监听密钥"""
        url = f"{self.rest_url}/api/v3/userDataStream"
        headers = {'X-MBX-APIKEY': self.config.api_key}
        
        async with self.session.post(url, headers=headers) as response:
            data = await response.json()
            return data['listenKey']
    
    async def place_order(self, symbol: str, side: str, order_type: str,
                         quantity: float, price: Optional[float] = None,
                         client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """下单"""
        url = f"{self.rest_url}/api/v3/order"
        
        params = {
            'symbol': symbol,
            'side': side.upper(),
            'type': order_type.upper(),
            'quantity': quantity,
            'timestamp': int(time.time() * 1000)
        }
        
        if price:
            params['price'] = price
        
        if client_order_id:
            params['newClientOrderId'] = client_order_id
        
        # 添加签名
        params['signature'] = self._generate_signature(params)
        
        headers = {'X-MBX-APIKEY': self.config.api_key}
        
        async with self.session.post(url, params=params, headers=headers) as response:
            return await response.json()
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """撤单"""
        url = f"{self.rest_url}/api/v3/order"
        
        params = {
            'symbol': symbol,
            'orderId': order_id,
            'timestamp': int(time.time() * 1000)
        }
        
        params['signature'] = self._generate_signature(params)
        headers = {'X-MBX-APIKEY': self.config.api_key}
        
        async with self.session.delete(url, params=params, headers=headers) as response:
            data = await response.json()
            return 'status' in data
    
    async def get_order_status(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """查询订单状态"""
        url = f"{self.rest_url}/api/v3/order"
        
        params = {
            'symbol': symbol,
            'orderId': order_id,
            'timestamp': int(time.time() * 1000)
        }
        
        params['signature'] = self._generate_signature(params)
        headers = {'X-MBX-APIKEY': self.config.api_key}
        
        async with self.session.get(url, params=params, headers=headers) as response:
            return await response.json()
    
    async def get_account_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        url = f"{self.rest_url}/api/v3/account"
        
        params = {
            'timestamp': int(time.time() * 1000)
        }
        
        params['signature'] = self._generate_signature(params)
        headers = {'X-MBX-APIKEY': self.config.api_key}
        
        async with self.session.get(url, params=params, headers=headers) as response:
            return await response.json()
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """获取持仓（币安使用账户余额）"""
        account = await self.get_account_balance()
        positions = []
        
        for balance in account.get('balances', []):
            free = float(balance['free'])
            locked = float(balance['locked'])
            if free > 0 or locked > 0:
                positions.append({
                    'symbol': balance['asset'],
                    'quantity': free + locked,
                    'available': free,
                    'locked': locked
                })
        
        return positions


class ExchangeManager:
    """交易所管理器"""
    
    def __init__(self):
        self.connectors: Dict[ExchangeType, BaseExchangeConnector] = {}
        self._lock = asyncio.Lock()
    
    async def add_exchange(self, config: ExchangeConfig) -> BaseExchangeConnector:
        """添加交易所"""
        async with self._lock:
            if config.exchange_type == ExchangeType.BINANCE:
                connector = BinanceConnector(config)
            else:
                raise ValueError(f"不支持的交易所类型: {config.exchange_type}")
            
            await connector.initialize()
            self.connectors[config.exchange_type] = connector
            
            logger.info(f"添加交易所: {config.exchange_type.value}")
            return connector
    
    async def remove_exchange(self, exchange_type: ExchangeType):
        """移除交易所"""
        async with self._lock:
            if exchange_type in self.connectors:
                await self.connectors[exchange_type].cleanup()
                del self.connectors[exchange_type]
                logger.info(f"移除交易所: {exchange_type.value}")
    
    async def get_connector(self, exchange_type: ExchangeType) -> Optional[BaseExchangeConnector]:
        """获取连接器"""
        return self.connectors.get(exchange_type)
    
    async def connect_all(self):
        """连接所有交易所"""
        for connector in self.connectors.values():
            await connector.connect()
    
    async def disconnect_all(self):
        """断开所有交易所"""
        for connector in self.connectors.values():
            await connector.disconnect()
    
    async def cleanup(self):
        """清理所有资源"""
        for connector in self.connectors.values():
            await connector.cleanup()
        self.connectors.clear()


# 全局交易所管理器
_exchange_manager: Optional[ExchangeManager] = None


async def get_exchange_manager() -> ExchangeManager:
    """获取交易所管理器实例"""
    global _exchange_manager
    if _exchange_manager is None:
        _exchange_manager = ExchangeManager()
    return _exchange_manager
