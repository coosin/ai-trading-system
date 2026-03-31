"""
交易所抽象基类

定义统一的交易所接口，所有具体交易所实现都需要继承此类
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union, Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class MarketData:
    """市场数据"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float


@dataclass
class OrderBook:
    """订单簿"""
    symbol: str
    timestamp: datetime
    asks: List[Tuple[float, float]]  # (价格, 数量)
    bids: List[Tuple[float, float]]  # (价格, 数量)


@dataclass
class Order:
    """订单"""
    order_id: str
    symbol: str
    side: str  # buy, sell
    order_type: str  # market, limit, etc.
    quantity: float
    price: Optional[float] = None
    status: str = "pending"
    executed_quantity: float = 0.0
    avg_price: float = 0.0
    timestamp: datetime = None
    client_order_id: Optional[str] = None


@dataclass
class Balance:
    """资产余额"""
    asset: str
    free: float
    locked: float
    total: float


@dataclass
class ExchangeInfo:
    """交易所信息"""
    exchange_id: str
    name: str
    api_url: str
    ws_url: str
    rate_limit: int
    supported_symbols: List[str]
    fee_structure: Dict[str, float]


class ExchangeBase(ABC):
    """交易所抽象基类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.exchange_id = config.get("exchange_id")
        self.api_key = config.get("api_key")
        self.api_secret = config.get("api_secret")
        self.api_passphrase = config.get("api_passphrase")
        self.testnet = config.get("testnet", False)
        self._session = None
        self._ws_connection = None
        self._running = False
    
    @abstractmethod
    async def initialize(self) -> bool:
        """初始化交易所连接"""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """清理资源"""
        pass
    
    @abstractmethod
    async def get_market_data(self, symbol: str, interval: str = "1m") -> MarketData:
        """获取市场数据"""
        pass
    
    @abstractmethod
    async def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook:
        """获取订单簿"""
        pass
    
    @abstractmethod
    async def place_order(self, order: Order) -> Dict[str, Any]:
        """下单"""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        pass
    
    @abstractmethod
    async def get_order(self, order_id: str, symbol: str) -> Order:
        """获取订单信息"""
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """获取未成交订单"""
        pass
    
    @abstractmethod
    async def get_balances(self) -> List[Balance]:
        """获取资产余额"""
        pass
    
    @abstractmethod
    async def get_exchange_info(self) -> ExchangeInfo:
        """获取交易所信息"""
        pass
    
    @abstractmethod
    async def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """获取交易对信息"""
        pass
    
    @abstractmethod
    async def subscribe_market_data(self, symbol: str, callback: Callable) -> bool:
        """订阅市场数据"""
        pass
    
    @abstractmethod
    async def unsubscribe_market_data(self, symbol: str) -> bool:
        """取消订阅市场数据"""
        pass
    
    @property
    def running(self) -> bool:
        """是否运行中"""
        return self._running
    
    def _sign_request(self, method: str, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """签名请求（子类实现）"""
        raise NotImplementedError
    
    async def _make_request(self, method: str, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求（子类实现）"""
        raise NotImplementedError