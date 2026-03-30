"""
TradeEngine单元测试
"""

import asyncio
import pytest
from datetime import datetime
from src.modules.core.trade_engine import (
    TradeEngine, Order, Position, Trade, PortfolioStats,
    OrderSide, OrderType, OrderStatus, PositionSide
)


class TestTradeEngine:
    """TradeEngine测试类"""
    
    @pytest.fixture
    async def trade_engine(self):
        """创建测试用的交易引擎"""
        engine = TradeEngine(initial_capital=100000.0)
        await engine.initialize()
        yield engine
        await engine.cleanup()
    
    @pytest.mark.asyncio
    async def test_initialization(self, trade_engine):
        """测试初始化"""
        assert trade_engine is not None
        assert trade_engine.initial_capital == 100000.0
        assert trade_engine.cash_balance == 100000.0
        assert trade_engine.reserved_cash == 0.0
        assert len(trade_engine.orders) == 0
        assert len(trade_engine.positions) == 0
        assert len(trade_engine.trades) == 0
    
    @pytest.mark.asyncio
    async def test_create_market_buy_order(self, trade_engine):
        """测试创建市价买单"""
        # 创建市价买单
        order = await trade_engine.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.5
        )
        
        assert order is not None
        assert order.symbol == "BTC/USDT"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == 0.5
        assert order.status == OrderStatus.PENDING
        assert order.id in trade_engine.orders
        
        # 检查保留资金
        assert trade_engine.reserved_cash > 0
    
    @pytest.mark.asyncio
    async def test_create_limit_sell_order(self, trade_engine):
        """测试创建限价卖单"""
        # 创建限价卖单
        order = await trade_engine.create_order(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=0.3,
            price=51000.0,
            strategy_id="test_strategy"
        )
        
        assert order is not None
        assert order.symbol == "BTC/USDT"
        assert order.side == OrderSide.SELL
        assert order.order_type == OrderType.LIMIT
        assert order.quantity == 0.3
        assert order.price == 51000.0
        assert order.strategy_id == "test_strategy"
        assert order.status == OrderStatus.PENDING
        assert order.id in trade_engine.orders
    
    @pytest.mark.asyncio
    async def test_create_order_insufficient_funds(self, trade_engine):
        """测试资金不足的订单创建"""
        # 尝试创建超大订单（应该失败）
        order = await trade_engine.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1000.0  # 非常大的数量
        )
        
        assert order is None
    
    @pytest.mark.asyncio
    async def test_get_order(self, trade_engine):
        """测试获取订单"""
        # 创建订单
        created_order = await trade_engine.create_order(
            symbol="ETH/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0
        )
        
        assert created_order is not None
        
        # 获取订单
        retrieved_order = await trade_engine.get_order(created_order.id)
        
        assert retrieved_order is not None
        assert retrieved_order.id == created_order.id
        assert retrieved_order.symbol == "ETH/USDT"
        assert retrieved_order.quantity == 1.0
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_order(self, trade_engine):
        """测试获取不存在的订单"""
        order = await trade_engine.get_order("nonexistent_id")
        assert order is None
    
    @pytest.mark.asyncio
    async def test_get_orders_with_filters(self, trade_engine):
        """测试带过滤器的订单获取"""
        # 创建多个订单
        order1 = await trade_engine.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.5
        )
        
        order2 = await trade_engine.create_order(
            symbol="ETH/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=2.0,
            price=3100.0
        )
        
        # 获取所有订单
        all_orders = await trade_engine.get_orders()
        assert len(all_orders) >= 2
        
        # 按交易对过滤
        btc_orders = await trade_engine.get_orders(symbol="BTC/USDT")
        assert len(btc_orders) >= 1
        assert all(o.symbol == "BTC/USDT" for o in btc_orders)
        
        # 按状态过滤
        pending_orders = await trade_engine.get_orders(status=OrderStatus.PENDING)
        assert len(pending_orders) >= 2
        assert all(o.status == OrderStatus.PENDING for o in pending_orders)
    
    @pytest.mark.asyncio
    async def test_cancel_order(self, trade_engine):
        """测试取消订单"""
        # 创建订单
        order = await trade_engine.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.5
        )
        
        assert order is not None
        
        # 取消订单
        success = await trade_engine.cancel_order(order.id)
        assert success is True
        
        # 检查订单状态
        cancelled_order = await trade_engine.get_order(order.id)
        assert cancelled_order.status == OrderStatus.CANCELLED
        assert cancelled_order.cancelled_at is not None
    
    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order(self, trade_engine):
        """测试取消不存在的订单"""
        success = await trade_engine.cancel_order("nonexistent_id")
        assert success is False
    
    @pytest.mark.asyncio
    async def test_update_market_price(self, trade_engine):
        """测试更新市场价格"""
        # 创建仓位
        order = await trade_engine.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.5
        )
        
        # 执行订单（模拟）
        if order:
            # 手动更新价格
            await trade_engine.update_market_price("BTC/USDT", 51000.0)
            
            # 检查仓位更新
            position = await trade_engine.get_position("BTC/USDT")
            if position:
                assert position.current_price == 51000.0
    
    @pytest.mark.asyncio
    async def test_get_position(self, trade_engine):
        """测试获取仓位"""
        # 创建订单建立仓位
        order = await trade_engine.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.5
        )
        
        # 检查仓位
        position = await trade_engine.get_position("BTC/USDT")
        # 仓位可能不存在（如果订单未执行）
        assert position is None or isinstance(position, Position)
    
    @pytest.mark.asyncio
    async def test_get_positions(self, trade_engine):
        """测试获取所有仓位"""
        positions = await trade_engine.get_positions()
        assert isinstance(positions, list)
        assert all(isinstance(p, Position) for p in positions)
    
    @pytest.mark.asyncio
    async def test_get_portfolio_stats(self, trade_engine):
        """测试获取投资组合统计"""
        stats = await trade_engine.get_portfolio_stats()
        
        assert isinstance(stats, PortfolioStats)
        assert stats.total_value == 100000.0  # 初始资金
        assert stats.cash_balance == 100000.0
        assert stats.position_value == 0.0
        assert stats.total_pnl == 0.0
        assert stats.total_trades == 0
        assert stats.timestamp is not None
    
    @pytest.mark.asyncio
    async def test_order_properties(self):
        """测试订单属性"""
        # 创建订单
        order = Order(
            id="test_order",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            price=50000.0
        )
        
        # 检查属性
        assert order.id == "test_order"
        assert order.symbol == "BTC/USDT"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == 1.0
        assert order.price == 50000.0
        assert order.status == OrderStatus.PENDING
        assert order.filled_quantity == 0.0
        assert order.avg_fill_price == 0.0
        assert order.commission == 0.0
        assert order.created_at is not None
        assert order.updated_at is not None
        
        # 检查计算属性
        assert order.remaining_quantity == 1.0
        assert order.is_filled is False
        assert order.is_active is True
        assert order.value == 50000.0
        
        # 测试部分成交
        order.update_fill(0.5, 51000.0, 10.0)
        assert order.filled_quantity == 0.5
        assert order.avg_fill_price == 51000.0
        assert order.commission == 10.0
        assert order.status == OrderStatus.PARTIAL_FILL
        assert order.remaining_quantity == 0.5
        
        # 测试完全成交
        order.update_fill(0.5, 52000.0, 10.0)
        assert order.filled_quantity == 1.0
        assert order.avg_fill_price == 51500.0  # (51000*0.5 + 52000*0.5) / 1.0
        assert order.commission == 20.0
        assert order.status == OrderStatus.FILLED
        assert order.remaining_quantity == 0.0
        assert order.is_filled is True
        assert order.filled_at is not None
    
    @pytest.mark.asyncio
    async def test_position_properties(self):
        """测试仓位属性"""
        # 创建仓位
        position = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            quantity=1.0,
            avg_entry_price=50000.0,
            current_price=51000.0
        )
        
        # 检查属性
        assert position.symbol == "BTC/USDT"
        assert position.side == PositionSide.LONG
        assert position.quantity == 1.0
        assert position.avg_entry_price == 50000.0
        assert position.current_price == 51000.0
        assert position.unrealized_pnl == 0.0  # 需要调用计算方法
        assert position.realized_pnl == 0.0
        assert position.total_commission == 0.0
        assert position.created_at is not None
        assert position.updated_at is not None
        
        # 计算属性
        assert position.market_value == 51000.0  # 1.0 * 51000.0
        assert position.cost_basis == 50000.0    # 1.0 * 50000.0
        assert position.total_pnl == 0.0         # unrealized + realized
        assert position.pnl_percentage == 0.0    # 需要计算
        
        # 更新价格并计算盈亏
        position.update_price(52000.0)
        assert position.current_price == 52000.0
        assert position.unrealized_pnl == 2000.0  # (52000 - 50000) * 1.0
        assert position.total_pnl == 2000.0
        assert position.pnl_percentage == 4.0     # (2000 / 50000) * 100
        
        # 测试仓位更新（买入）
        position.update_position(OrderSide.BUY, 0.5, 53000.0, 5.0)
        assert position.quantity == 1.5
        assert abs(position.avg_entry_price - 51000.0) < 0.01  # (50000*1.0 + 53000*0.5) / 1.5
        assert position.total_commission == 5.0
        assert position.side == PositionSide.LONG
        
        # 测试仓位更新（卖出）
        position.update_position(OrderSide.SELL, 1.0, 54000.0, 5.0)
        assert position.quantity == 0.5
        assert position.total_commission == 10.0
        assert position.realized_pnl > 0.0  # 应该有已实现盈亏
        
        # 测试平仓
        position.update_position(OrderSide.SELL, 0.5, 55000.0, 5.0)
        assert abs(position.quantity) < 0.001
        assert position.side == PositionSide.FLAT
    
    @pytest.mark.asyncio
    async def test_trade_properties(self):
        """测试交易属性"""
        # 创建交易
        trade = Trade(
            id="test_trade",
            order_id="test_order",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            quantity=1.0,
            price=50000.0,
            commission=10.0,
            strategy_id="test_strategy"
        )
        
        # 检查属性
        assert trade.id == "test_trade"
        assert trade.order_id == "test_order"
        assert trade.symbol == "BTC/USDT"
        assert trade.side == OrderSide.BUY
        assert trade.quantity == 1.0
        assert trade.price == 50000.0
        assert trade.commission == 10.0
        assert trade.strategy_id == "test_strategy"
        assert trade.timestamp is not None
    
    @pytest.mark.asyncio
    async def test_portfolio_stats_properties(self):
        """测试投资组合统计属性"""
        # 创建统计
        stats = PortfolioStats(
            total_value=150000.0,
            cash_balance=50000.0,
            position_value=100000.0,
            total_pnl=50000.0,
            daily_pnl=1000.0,
            win_rate=0.65,
            sharpe_ratio=1.5,
            max_drawdown=0.1,
            total_trades=100,
            winning_trades=65,
            losing_trades=35
        )
        
        # 检查属性
        assert stats.total_value == 150000.0
        assert stats.cash_balance == 50000.0
        assert stats.position_value == 100000.0
        assert stats.total_pnl == 50000.0
        assert stats.daily_pnl == 1000.0
        assert stats.win_rate == 0.65
        assert stats.sharpe_ratio == 1.5
        assert stats.max_drawdown == 0.1
        assert stats.total_trades == 100
        assert stats.winning_trades == 65
        assert stats.losing_trades == 35
        assert stats.timestamp is not None
    
    @pytest.mark.asyncio
    async def test_enum_values(self):
        """测试枚举值"""
        # 订单方向
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"
        
        # 订单类型
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP.value == "stop"
        assert OrderType.STOP_LIMIT.value == "stop_limit"
        
        # 订单状态
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.SUBMITTED.value == "submitted"
        assert OrderStatus.PARTIAL_FILL.value == "partial"
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.CANCELLED.value == "cancelled"
        assert OrderStatus.REJECTED.value == "rejected"
        assert OrderStatus.EXPIRED.value == "expired"
        
        # 仓位方向
        assert PositionSide.LONG.value == "long"
        assert PositionSide.SHORT.value == "short"
        assert PositionSide.FLAT.value == "flat"
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, trade_engine):
        """测试并发操作"""
        # 并发创建订单
        async def create_order_task(i):
            return await trade_engine.create_order(
                symbol=f"SYM{i % 3}",  # 3个不同的交易对
                side=OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=0.1 * (i + 1)
            )
        
        # 创建多个订单任务
        tasks = [create_order_task(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        # 检查结果
        successful_orders = [r for r in results if r is not None]
        assert len(successful_orders) > 0
        
        # 检查订单数量
        all_orders = await trade_engine.get_orders()
        assert len(all_orders) == len(successful_orders)
    
    @pytest.mark.asyncio
    async def test_error_handling(self, trade_engine):
        """测试错误处理"""
        # 测试无效订单（负数量）
        order = await trade_engine.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=-1.0  # 无效数量
        )
        
        assert order is None
        
        # 测试无效订单（缺少价格）
        order = await trade_engine.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0
            # 缺少price参数
        )
        
        assert order is None


if __name__ == "__main__":
    """运行测试"""
    import sys
    import pytest
    
    # 添加src目录到Python路径
    sys.path.insert(0, "/home/cool/.openclaw-trading/src")
    
    # 运行测试
    pytest.main([__file__, "-v"])