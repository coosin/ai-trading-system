"""
单元测试框架

提供测试基础设施和工具
"""

import asyncio
import pytest
import logging
from typing import Any, Dict, Optional
from unittest.mock import Mock, AsyncMock, patch
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TestConfig:
    """测试配置"""
    use_mock_data: bool = True
    mock_exchange: bool = True
    mock_llm: bool = True
    test_timeout: float = 30.0


class BaseTestCase:
    """测试基类"""
    
    @pytest.fixture(autouse=True)
    def setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    @pytest.fixture
    def event_loop(self):
        """创建事件循环"""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()
    
    @pytest.fixture
    def mock_config(self) -> Dict[str, Any]:
        """模拟配置"""
        return {
            "system": {
                "name": "Test System",
                "version": "1.0.0",
                "mode": "test"
            },
            "trading": {
                "symbols": ["BTC/USDT"],
                "max_positions": 3,
                "risk_per_trade": 0.02
            },
            "ai": {
                "default_model": "test-model",
                "temperature": 0.7,
                "max_tokens": 1000
            }
        }
    
    @pytest.fixture
    def mock_exchange(self) -> Mock:
        """模拟交易所"""
        exchange = Mock()
        exchange.get_ticker = AsyncMock(return_value={
            "symbol": "BTC/USDT",
            "last": 50000.0,
            "bid": 49999.0,
            "ask": 50001.0,
            "volume": 1000.0
        })
        exchange.get_balance = AsyncMock(return_value={
            "USDT": 10000.0,
            "BTC": 0.1
        })
        exchange.get_positions = AsyncMock(return_value=[])
        exchange.create_order = AsyncMock(return_value={
            "id": "test-order-123",
            "symbol": "BTC/USDT",
            "side": "buy",
            "amount": 0.001,
            "price": 50000.0,
            "status": "open"
        })
        return exchange
    
    @pytest.fixture
    def mock_llm_manager(self) -> Mock:
        """模拟LLM管理器"""
        manager = Mock()
        manager.generate = AsyncMock(return_value={
            "content": "Test response",
            "model": "test-model",
            "usage": {"total_tokens": 100}
        })
        manager.analyze_market = AsyncMock(return_value={
            "trend": "bullish",
            "confidence": 0.8,
            "signal": "buy"
        })
        return manager


class AsyncTestCase(BaseTestCase):
    """异步测试基类"""
    
    @pytest.mark.asyncio
    async def async_setup(self):
        """异步设置"""
        pass
    
    @pytest.mark.asyncio
    async def async_teardown(self):
        """异步清理"""
        pass


def create_mock_market_data(symbol: str = "BTC/USDT") -> Dict[str, Any]:
    """创建模拟市场数据"""
    return {
        "symbol": symbol,
        "multi_timeframe_klines": {
            "1m": [[50000.0, 50100.0, 49900.0, 50050.0, 100.0]],
            "5m": [[50000.0, 50200.0, 49800.0, 50100.0, 500.0]],
            "1h": [[50000.0, 50500.0, 49500.0, 50200.0, 2000.0]]
        },
        "ticker": {
            "symbol": symbol,
            "last": 50000.0,
            "bid": 49999.0,
            "ask": 50001.0,
            "volume": 1000.0
        },
        "order_book": {
            "bids": [[49999.0, 1.0], [49998.0, 2.0]],
            "asks": [[50001.0, 1.0], [50002.0, 2.0]]
        },
        "balance": {
            "USDT": 10000.0,
            "BTC": 0.1
        },
        "positions": [],
        "timestamp": "2026-04-02T00:00:00"
    }


def create_mock_position(symbol: str = "BTC/USDT") -> Dict[str, Any]:
    """创建模拟持仓"""
    return {
        "symbol": symbol,
        "side": "long",
        "entry_price": 50000.0,
        "quantity": 0.1,
        "current_price": 50500.0,
        "unrealized_pnl": 50.0,
        "unrealized_pnl_percent": 0.01,
        "stop_loss": 49000.0,
        "take_profit": 52000.0,
        "opened_at": "2026-04-02T00:00:00"
    }


def create_mock_trade(symbol: str = "BTC/USDT") -> Dict[str, Any]:
    """创建模拟交易"""
    return {
        "id": "test-trade-123",
        "symbol": symbol,
        "side": "buy",
        "amount": 0.1,
        "price": 50000.0,
        "cost": 5000.0,
        "fee": 5.0,
        "timestamp": "2026-04-02T00:00:00",
        "status": "closed"
    }


# 测试工具函数
def assert_valid_signal(signal: Dict[str, Any]):
    """验证交易信号"""
    assert "action" in signal
    assert "symbol" in signal
    assert "confidence" in signal
    assert 0 <= signal["confidence"] <= 1


def assert_valid_position(position: Dict[str, Any]):
    """验证持仓"""
    assert "symbol" in position
    assert "side" in position
    assert "quantity" in position
    assert position["quantity"] > 0


def assert_valid_order(order: Dict[str, Any]):
    """验证订单"""
    assert "id" in order
    assert "symbol" in order
    assert "side" in order
    assert "amount" in order
    assert "status" in order
