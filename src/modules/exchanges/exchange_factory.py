"""
交易所工厂类

用于创建和管理不同交易所的实例
"""

import logging
from typing import Dict, Any

from .binance import BinanceExchange
from .okx import OKXExchange
from .exchange_base import ExchangeBase

logger = logging.getLogger(__name__)


class ExchangeFactory:
    """交易所工厂类"""
    
    _exchange_classes = {
        "binance": BinanceExchange,
        "okx": OKXExchange,
        # 可以添加更多交易所实现
        # "bybit": BybitExchange,
        # "huobi": HuobiExchange
    }
    
    def __init__(self):
        self._exchanges: Dict[str, ExchangeBase] = {}
    
    def create_exchange(self, exchange_id: str, config: Dict[str, Any]) -> ExchangeBase:
        """创建交易所实例"""
        if exchange_id not in self._exchange_classes:
            raise ValueError(f"不支持的交易所: {exchange_id}")
        
        # 检查是否已存在该交易所的实例
        if exchange_id in self._exchanges:
            logger.info(f"使用已存在的{exchange_id}交易所实例")
            return self._exchanges[exchange_id]
        
        # 创建新实例
        exchange_class = self._exchange_classes[exchange_id]
        exchange = exchange_class(config)
        self._exchanges[exchange_id] = exchange
        logger.info(f"创建{exchange_id}交易所实例")
        return exchange
    
    def get_exchange(self, exchange_id: str) -> ExchangeBase:
        """获取交易所实例"""
        if exchange_id not in self._exchanges:
            raise ValueError(f"交易所{exchange_id}未初始化")
        return self._exchanges[exchange_id]
    
    def list_exchanges(self) -> list:
        """列出所有可用的交易所"""
        return list(self._exchange_classes.keys())
    
    def list_active_exchanges(self) -> list:
        """列出所有已激活的交易所"""
        return list(self._exchanges.keys())
    
    async def initialize_all(self) -> Dict[str, bool]:
        """初始化所有交易所"""
        results = {}
        for exchange_id, exchange in self._exchanges.items():
            results[exchange_id] = await exchange.initialize()
        return results
    
    async def cleanup_all(self) -> None:
        """清理所有交易所"""
        for exchange_id, exchange in self._exchanges.items():
            try:
                await exchange.cleanup()
                logger.info(f"清理{exchange_id}交易所实例")
            except Exception as e:
                logger.error(f"清理{exchange_id}交易所实例失败: {e}")
        self._exchanges.clear()
    
    def register_exchange(self, exchange_id: str, exchange_class: type) -> None:
        """注册新的交易所实现"""
        if not issubclass(exchange_class, ExchangeBase):
            raise TypeError("交易所类必须继承自ExchangeBase")
        
        self._exchange_classes[exchange_id] = exchange_class
        logger.info(f"注册新的交易所实现: {exchange_id}")
    
    def unregister_exchange(self, exchange_id: str) -> None:
        """注销交易所实现"""
        if exchange_id in self._exchange_classes:
            del self._exchange_classes[exchange_id]
            logger.info(f"注销交易所实现: {exchange_id}")
        
        if exchange_id in self._exchanges:
            del self._exchanges[exchange_id]
            logger.info(f"移除{exchange_id}交易所实例")