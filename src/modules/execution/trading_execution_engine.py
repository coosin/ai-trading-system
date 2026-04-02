"""
交易执行引擎 - 订单路由和交易成本分析

核心功能：
1. 智能订单路由
2. 订单执行算法（TWAP、VWAP、冰山订单）
3. 交易成本分析
4. 滑点和冲击成本模拟
5. 订单状态管理
"""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    ICEBERG = "iceberg"
    TWAP = "twap"
    VWAP = "vwap"


class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    OPEN = "open"
    PARTIAL_FILLED = "partial_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class Order:
    """订单"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    iceberg_visible_size: Optional[float] = None
    twap_duration: Optional[timedelta] = None
    twap_interval: Optional[timedelta] = None
    vwap_end_time: Optional[datetime] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def remaining_quantity(self) -> float:
        """剩余数量"""
        return self.quantity - self.filled_quantity

    @property
    def is_active(self) -> bool:
        """是否活跃"""
        return self.status in [OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIAL_FILLED]


@dataclass
class Trade:
    """交易记录"""
    trade_id: str
    order_id: str
    symbol: str
    side: OrderSide
    price: float
    quantity: float
    commission: float = 0.0
    slippage: float = 0.0
    market_impact: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradingCost:
    """交易成本分析"""
    order_id: str
    commission_cost: float = 0.0
    slippage_cost: float = 0.0
    market_impact_cost: float = 0.0
    total_cost: float = 0.0
    cost_percentage: float = 0.0
    analysis_timestamp: datetime = field(default_factory=datetime.now)


class ExecutionAlgorithm(Enum):
    """执行算法"""
    SIMPLE = "simple"
    TWAP = "twap"
    VWAP = "vwap"
    ICEBERG = "iceberg"


class TradingExecutionEngine:
    """
    交易执行引擎
    
    负责：
    - 订单路由
    - 执行算法
    - 交易成本分析
    - 订单状态管理
    """

    def __init__(self, exchange_interface=None):
        """
        初始化交易执行引擎

        Args:
            exchange_interface: 交易所接口
        """
        self.exchange_interface = exchange_interface

        # 订单管理
        self.orders: Dict[str, Order] = {}
        self.order_history: List[Order] = []
        self.trades: Dict[str, List[Trade]] = {}

        # 配置
        self.config = {
            "commission_rate": 0.001,
            "default_slippage": 0.0005,
            "market_impact_factor": 0.1,
            "max_order_size": 0.1,
            "min_order_size": 0.0001,
        }

        # 任务管理
        self._tasks: List[asyncio.Task] = []
        self._running = False
        self._lock = asyncio.Lock()

        logger.info("交易执行引擎初始化完成")

    async def initialize(self) -> None:
        """初始化交易执行引擎"""
        logger.info("初始化交易执行引擎...")
        self._running = True
        logger.info("交易执行引擎初始化完成")

    async def shutdown(self) -> None:
        """关闭交易执行引擎"""
        logger.info("关闭交易执行引擎...")

        self._running = False

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.info("交易执行引擎已关闭")

    async def create_order(self, 
                         symbol: str,
                         side: OrderSide,
                         order_type: OrderType,
                         quantity: float,
                         price: Optional[float] = None,
                         stop_price: Optional[float] = None,
                         execution_algorithm: ExecutionAlgorithm = ExecutionAlgorithm.SIMPLE,
                         **kwargs) -> Order:
        """
        创建订单

        Args:
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            quantity: 数量
            price: 价格（限价单）
            stop_price: 止损价格
            execution_algorithm: 执行算法
            **kwargs: 其他参数

        Returns:
            订单对象
        """
        order_id = f"ord_{datetime.now().strftime('%Y%m%d%H%M%S')}_{id(self) % 10000}"

        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            **kwargs
        )

        # 验证订单
        if not await self._validate_order(order):
            order.status = OrderStatus.REJECTED
            async with self._lock:
                self.orders[order_id] = order
                self.order_history.append(order)
            raise ValueError(f"订单验证失败: {order_id}")

        async with self._lock:
            self.orders[order_id] = order
            self.order_history.append(order)

        logger.info(f"创建订单: {order_id}, {side.value} {quantity} {symbol}")

        # 根据执行算法处理订单
        if execution_algorithm == ExecutionAlgorithm.TWAP:
            self._tasks.append(asyncio.create_task(self._execute_twap_order(order)))
        elif execution_algorithm == ExecutionAlgorithm.VWAP:
            self._tasks.append(asyncio.create_task(self._execute_vwap_order(order)))
        elif execution_algorithm == ExecutionAlgorithm.ICEBERG:
            self._tasks.append(asyncio.create_task(self._execute_iceberg_order(order)))
        else:
            await self._execute_simple_order(order)

        return order

    async def _validate_order(self, order: Order) -> bool:
        """
        验证订单

        Args:
            order: 订单

        Returns:
            是否有效
        """
        # 检查数量
        if order.quantity <= 0:
            logger.warning(f"无效的订单数量: {order.quantity}")
            return False

        # 检查数量限制
        if order.quantity < self.config["min_order_size"]:
            logger.warning(f"订单数量小于最小限制: {order.quantity} < {self.config['min_order_size']}")
            return False

        if order.quantity > self.config["max_order_size"]:
            logger.warning(f"订单数量超过最大限制: {order.quantity} > {self.config['max_order_size']}")
            return False

        # 检查限价单价格
        if order.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and order.price is None:
            logger.warning("限价单需要指定价格")
            return False

        # 检查止损单价格
        if order.order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and order.stop_price is None:
            logger.warning("止损单需要指定止损价格")
            return False

        return True

    async def _execute_simple_order(self, order: Order) -> None:
        """
        执行简单订单

        Args:
            order: 订单
        """
        async with self._lock:
            order.status = OrderStatus.OPEN
            order.updated_at = datetime.now()

        try:
            # 模拟获取市场价格
            market_price = await self._get_market_price(order.symbol)
            
            # 计算实际成交价格
            fill_price = self._calculate_fill_price(order, market_price)
            
            # 模拟成交
            await self._fill_order(order, fill_price, order.quantity)

        except Exception as e:
            logger.error(f"执行订单失败 {order.order_id}: {e}")
            async with self._lock:
                order.status = OrderStatus.REJECTED
                order.updated_at = datetime.now()

    async def _execute_twap_order(self, order: Order) -> None:
        """
        执行TWAP订单（时间加权平均价格）

        Args:
            order: 订单
        """
        if not order.twap_duration:
            order.twap_duration = timedelta(minutes=30)
        if not order.twap_interval:
            order.twap_interval = timedelta(minutes=5)

        async with self._lock:
            order.status = OrderStatus.OPEN
            order.updated_at = datetime.now()

        exchange = order.metadata.get("exchange", "binance")
        logger.info(f"开始TWAP执行: {order.order_id}, 持续时间: {order.twap_duration}, 交易所: {exchange}")

        total_intervals = math.ceil(order.twap_duration.total_seconds() / order.twap_interval.total_seconds())
        quantity_per_interval = order.quantity / total_intervals
        
        # 智能调整间隔：根据市场 volatility 调整
        adjusted_interval = order.twap_interval

        for i in range(total_intervals):
            if not self._running or order.status != OrderStatus.OPEN:
                break

            try:
                # 获取市场价格
                market_price = await self._get_market_price(order.symbol, exchange)
                
                # 计算当前市场 volatility（简化版）
                volatility = 0.01  # 假设1%波动率
                
                # 根据 volatility 调整执行间隔
                if volatility > 0.02:
                    # 高 volatility，缩短间隔
                    adjusted_interval = timedelta(seconds=order.twap_interval.total_seconds() * 0.5)
                elif volatility < 0.005:
                    # 低 volatility，延长间隔
                    adjusted_interval = timedelta(seconds=order.twap_interval.total_seconds() * 1.5)
                else:
                    # 正常 volatility，使用默认间隔
                    adjusted_interval = order.twap_interval
                
                # 计算当前执行数量
                fill_quantity = min(quantity_per_interval, order.remaining_quantity)
                
                if fill_quantity > 0:
                    # 智能价格计算：根据市场趋势调整
                    fill_price = self._calculate_fill_price(order, market_price)
                    
                    # 执行交易
                    await self._fill_order(order, fill_price, fill_quantity)

            except Exception as e:
                logger.error(f"TWAP执行失败 {order.order_id}, 第{i+1}次: {e}")

            if i < total_intervals - 1:
                await asyncio.sleep(adjusted_interval.total_seconds())

        logger.info(f"TWAP执行完成: {order.order_id}, 成交: {order.filled_quantity}/{order.quantity}")

    async def _execute_vwap_order(self, order: Order) -> None:
        """
        执行VWAP订单（成交量加权平均价格）

        Args:
            order: 订单
        """
        if not order.vwap_end_time:
            order.vwap_end_time = datetime.now() + timedelta(minutes=30)

        async with self._lock:
            order.status = OrderStatus.OPEN
            order.updated_at = datetime.now()

        exchange = order.metadata.get("exchange", "binance")
        logger.info(f"开始VWAP执行: {order.order_id}, 结束时间: {order.vwap_end_time}, 交易所: {exchange}")

        # 智能VWAP实现：根据成交量分布和时间进度执行
        start_time = datetime.now()
        total_duration = (order.vwap_end_time - start_time).total_seconds()
        
        while self._running and order.status == OrderStatus.OPEN and datetime.now() < order.vwap_end_time:
            try:
                # 计算时间进度
                elapsed_time = (datetime.now() - start_time).total_seconds()
                time_progress = min(elapsed_time / total_duration, 1.0)
                
                # 计算目标执行进度
                target_progress = time_progress
                current_progress = order.filled_quantity / order.quantity
                
                # 模拟获取成交量数据
                volume_profile = await self._get_volume_profile(order.symbol, exchange)
                current_volume = volume_profile.get('current_volume', 1.0)
                total_volume = volume_profile.get('total_volume', 100.0)
                
                # 计算成交量比例
                volume_ratio = current_volume / total_volume
                
                # 智能调整执行数量：结合时间进度和成交量分布
                # 如果时间进度快于执行进度，增加执行量
                # 如果成交量大，增加执行量
                adjustment_factor = 1.0
                
                if target_progress > current_progress * 1.2:
                    # 时间进度明显快于执行进度，加速执行
                    adjustment_factor = 1.5
                elif target_progress < current_progress * 0.8:
                    # 执行进度快于时间进度，减速执行
                    adjustment_factor = 0.5
                
                # 成交量大时增加执行
                if volume_ratio > 0.02:
                    adjustment_factor *= 1.3
                
                # 计算应该执行的数量
                target_quantity = order.quantity * volume_ratio * adjustment_factor
                fill_quantity = min(target_quantity, order.remaining_quantity)
                
                if fill_quantity > 0.0001:
                    market_price = await self._get_market_price(order.symbol, exchange)
                    fill_price = self._calculate_fill_price(order, market_price)
                    await self._fill_order(order, fill_price, fill_quantity)

            except Exception as e:
                logger.error(f"VWAP执行失败 {order.order_id}: {e}")

            # 智能调整检查间隔：根据执行进度和市场情况
            if order.filled_quantity / order.quantity < 0.3:
                # 执行初期，频繁检查
                await asyncio.sleep(30)  # 每30秒检查一次
            elif order.filled_quantity / order.quantity > 0.7:
                # 执行后期，更频繁检查
                await asyncio.sleep(20)  # 每20秒检查一次
            else:
                # 执行中期，正常检查
                await asyncio.sleep(45)  # 每45秒检查一次

        logger.info(f"VWAP执行完成: {order.order_id}, 成交: {order.filled_quantity}/{order.quantity}")

    async def _execute_iceberg_order(self, order: Order) -> None:
        """
        执行冰山订单

        Args:
            order: 订单
        """
        if not order.iceberg_visible_size:
            order.iceberg_visible_size = order.quantity * 0.1  # 默认显示10%

        async with self._lock:
            order.status = OrderStatus.OPEN
            order.updated_at = datetime.now()

        exchange = order.metadata.get("exchange", "binance")
        logger.info(f"开始冰山订单执行: {order.order_id}, 显示数量: {order.iceberg_visible_size}, 交易所: {exchange}")

        # 智能冰山订单实现：根据市场深度和流动性调整
        base_visible_size = order.iceberg_visible_size
        
        while self._running and order.status == OrderStatus.OPEN and order.remaining_quantity > 0:
            try:
                # 模拟获取市场深度数据
                market_depth = await self._get_market_depth(order.symbol, exchange)
                liquidity = market_depth.get('liquidity', 1.0)
                spread = market_depth.get('spread', 0.001)
                
                # 根据市场深度调整显示数量
                if liquidity > 1.5:
                    # 高流动性，增加显示数量
                    adjusted_visible_size = base_visible_size * 1.5
                elif liquidity < 0.5:
                    # 低流动性，减少显示数量
                    adjusted_visible_size = base_visible_size * 0.5
                else:
                    # 正常流动性，使用默认显示数量
                    adjusted_visible_size = base_visible_size
                
                visible_quantity = min(adjusted_visible_size, order.remaining_quantity)
                
                # 获取市场价格
                market_price = await self._get_market_price(order.symbol, exchange)
                fill_price = self._calculate_fill_price(order, market_price)
                
                # 根据市场流动性调整成交比例
                if liquidity > 1.5:
                    # 高流动性，更高的成交比例
                    fill_ratio = 0.7
                elif liquidity < 0.5:
                    # 低流动性，更低的成交比例
                    fill_ratio = 0.3
                else:
                    # 正常流动性，中等成交比例
                    fill_ratio = 0.5
                
                # 计算实际成交数量
                fill_quantity = visible_quantity * fill_ratio
                
                if fill_quantity > 0.0001:
                    await self._fill_order(order, fill_price, min(fill_quantity, order.remaining_quantity))

            except Exception as e:
                logger.error(f"冰山订单执行失败 {order.order_id}: {e}")

            # 智能调整检查间隔：根据剩余数量和市场情况
            remaining_ratio = order.remaining_quantity / order.quantity
            if remaining_ratio > 0.7:
                # 剩余数量多，较慢执行
                await asyncio.sleep(45)  # 每45秒检查一次
            elif remaining_ratio < 0.3:
                # 剩余数量少，较快执行
                await asyncio.sleep(15)  # 每15秒检查一次
            else:
                # 剩余数量中等，正常执行
                await asyncio.sleep(30)  # 每30秒检查一次

        logger.info(f"冰山订单执行完成: {order.order_id}, 成交: {order.filled_quantity}/{order.quantity}")

    async def _get_market_depth(self, symbol: str, exchange: str = "binance") -> Dict[str, float]:
        """
        获取市场深度数据

        Args:
            symbol: 交易对
            exchange: 交易所

        Returns:
            市场深度数据
        """
        # 模拟市场深度数据
        import random
        # 不同交易所的流动性不同
        liquidity_factors = {
            "binance": 1.0,
            "coinbase": 0.8,
            "kraken": 0.6,
            "okx": 0.9,
            "bybit": 0.7
        }
        base_liquidity = liquidity_factors.get(exchange, 1.0)
        
        return {
            'liquidity': base_liquidity * random.uniform(0.5, 1.5),
            'spread': random.uniform(0.0005, 0.002),
            'order_book_depth': random.uniform(10000, 100000)
        }

    async def _fill_order(self, order: Order, price: float, quantity: float) -> None:
        """
        成交订单

        Args:
            order: 订单
            price: 成交价格
            quantity: 成交数量
        """
        async with self._lock:
            if order.status not in [OrderStatus.OPEN, OrderStatus.PARTIAL_FILLED]:
                return

            # 创建交易记录
            trade = Trade(
                trade_id=f"trd_{datetime.now().strftime('%Y%m%d%H%M%S')}_{id(self) % 10000}",
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                price=price,
                quantity=quantity
            )

            # 计算交易成本
            trading_cost = self._calculate_trading_cost(order, trade)
            trade.commission = trading_cost.commission_cost
            trade.slippage = trading_cost.slippage_cost
            trade.market_impact = trading_cost.market_impact_cost

            # 更新订单
            order.filled_quantity += quantity
            order.avg_fill_price = (
                (order.avg_fill_price * (order.filled_quantity - quantity) + price * quantity)
                / order.filled_quantity
            )

            if order.filled_quantity >= order.quantity - 0.000001:
                order.status = OrderStatus.FILLED
                order.executed_at = datetime.now()
            else:
                order.status = OrderStatus.PARTIAL_FILLED

            order.updated_at = datetime.now()

            # 保存交易记录
            if order.order_id not in self.trades:
                self.trades[order.order_id] = []
            self.trades[order.order_id].append(trade)

            logger.info(
                f"订单成交: {order.order_id}, {quantity} @ {price}, "
                f"累计: {order.filled_quantity}/{order.quantity}"
            )

    async def cancel_order(self, order_id: str) -> bool:
        """
        取消订单

        Args:
            order_id: 订单ID

        Returns:
            是否成功
        """
        async with self._lock:
            order = self.orders.get(order_id)
            if not order or not order.is_active:
                logger.warning(f"订单不存在或不可取消: {order_id}")
                return False

            order.status = OrderStatus.CANCELLED
            order.cancelled_at = datetime.now()
            order.updated_at = datetime.now()

            logger.info(f"取消订单: {order_id}")
            return True

    def _calculate_fill_price(self, order: Order, market_price: float) -> float:
        """
        计算成交价格

        Args:
            order: 订单
            market_price: 市场价格

        Returns:
            成交价格
        """
        if order.order_type == OrderType.MARKET:
            # 市价单：考虑滑点
            slippage = self.config["default_slippage"]
            if order.side == OrderSide.BUY:
                return market_price * (1 + slippage)
            else:
                return market_price * (1 - slippage)
        else:
            # 限价单：使用限价
            return order.price or market_price

    def _calculate_trading_cost(self, order: Order, trade: Trade) -> TradingCost:
        """
        计算交易成本

        Args:
            order: 订单
            trade: 交易

        Returns:
            交易成本分析
        """
        notional_value = trade.price * trade.quantity

        # 佣金成本
        commission_cost = notional_value * self.config["commission_rate"]

        # 滑点成本
        slippage_cost = notional_value * self.config["default_slippage"]

        # 市场冲击成本（简单模型）
        order_size_ratio = trade.quantity / self.config["max_order_size"]
        market_impact_cost = notional_value * self.config["market_impact_factor"] * order_size_ratio

        total_cost = commission_cost + slippage_cost + market_impact_cost
        cost_percentage = (total_cost / notional_value) * 100 if notional_value > 0 else 0

        return TradingCost(
            order_id=order.order_id,
            commission_cost=commission_cost,
            slippage_cost=slippage_cost,
            market_impact_cost=market_impact_cost,
            total_cost=total_cost,
            cost_percentage=cost_percentage
        )

    async def _get_market_price(self, symbol: str, exchange: str = "binance") -> float:
        """
        获取市场价格

        Args:
            symbol: 交易对
            exchange: 交易所

        Returns:
            市场价格
        """
        # 这里应该连接真实的交易所接口
        # 模拟价格
        import random
        base_price = 40000 if "BTC" in symbol else 2000
        # 不同交易所的价格略有差异
        exchange_factor = {
            "binance": 1.0,
            "coinbase": 1.001,  # Coinbase价格略高
            "kraken": 0.999,     # Kraken价格略低
            "okx": 1.0005,       # OKX价格略高
            "bybit": 0.9995      # Bybit价格略低
        }
        factor = exchange_factor.get(exchange, 1.0)
        return (base_price + random.normalvariate(0, base_price * 0.001)) * factor

    async def _get_volume_profile(self, symbol: str, exchange: str = "binance") -> Dict[str, float]:
        """
        获取成交量分布

        Args:
            symbol: 交易对
            exchange: 交易所

        Returns:
            成交量数据
        """
        # 这里应该从交易所获取真实的成交量数据
        import random
        # 不同交易所的成交量不同
        volume_factors = {
            "binance": 1.0,
            "coinbase": 0.7,
            "kraken": 0.5,
            "okx": 0.8,
            "bybit": 0.6
        }
        factor = volume_factors.get(exchange, 1.0)
        return {
            'current_volume': random.uniform(0.5, 1.5) * factor,
            'total_volume': 100.0 * factor
        }

    async def create_order_with_exchange(self, 
                                      exchange: str,
                                      symbol: str,
                                      side: OrderSide,
                                      order_type: OrderType,
                                      quantity: float,
                                      price: Optional[float] = None,
                                      stop_price: Optional[float] = None,
                                      execution_algorithm: ExecutionAlgorithm = ExecutionAlgorithm.SIMPLE,
                                      **kwargs) -> Order:
        """
        在指定交易所创建订单

        Args:
            exchange: 交易所名称
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            quantity: 数量
            price: 价格（限价单）
            stop_price: 止损价格
            execution_algorithm: 执行算法
            **kwargs: 其他参数

        Returns:
            订单对象
        """
        # 验证交易所
        supported_exchanges = ["binance", "coinbase", "kraken", "okx", "bybit"]
        if exchange not in supported_exchanges:
            raise ValueError(f"不支持的交易所: {exchange}")

        # 调整交易对格式
        exchange_symbol_map = {
            "binance": symbol.replace("/", ""),  # BTC/USDT -> BTCUSDT
            "coinbase": symbol.replace("/", "-"),  # BTC/USDT -> BTC-USDT
            "kraken": symbol,  # 保持BTC/USDT格式
            "okx": symbol.replace("/", ""),  # BTC/USDT -> BTCUSDT
            "bybit": symbol.replace("/", "")  # BTC/USDT -> BTCUSDT
        }
        exchange_symbol = exchange_symbol_map.get(exchange, symbol)

        # 创建订单
        order = await self.create_order(
            symbol=exchange_symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            execution_algorithm=execution_algorithm,
            **kwargs
        )

        # 添加交易所信息到订单元数据
        order.metadata["exchange"] = exchange
        order.metadata["original_symbol"] = symbol

        logger.info(f"在 {exchange} 创建订单: {order.order_id}, {side.value} {quantity} {exchange_symbol}")
        return order

    def get_order(self, order_id: str) -> Optional[Order]:
        """
        获取订单

        Args:
            order_id: 订单ID

        Returns:
            订单对象
        """
        return self.orders.get(order_id)

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        获取活跃订单

        Args:
            symbol: 交易对过滤

        Returns:
            订单列表
        """
        orders = [o for o in self.orders.values() if o.is_active]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    def get_order_trades(self, order_id: str) -> List[Trade]:
        """
        获取订单的交易记录

        Args:
            order_id: 订单ID

        Returns:
            交易记录列表
        """
        return self.trades.get(order_id, [])

    async def analyze_trading_costs(self, order_id: str) -> Optional[TradingCost]:
        """
        分析订单的交易成本

        Args:
            order_id: 订单ID

        Returns:
            交易成本分析
        """
        order = self.get_order(order_id)
        if not order:
            return None

        trades = self.get_order_trades(order_id)
        if not trades:
            return None

        total_commission = sum(t.commission for t in trades)
        total_slippage = sum(t.slippage for t in trades)
        total_market_impact = sum(t.market_impact for t in trades)
        total_cost = total_commission + total_slippage + total_market_impact

        total_notional = sum(t.price * t.quantity for t in trades)
        cost_percentage = (total_cost / total_notional) * 100 if total_notional > 0 else 0

        return TradingCost(
            order_id=order_id,
            commission_cost=total_commission,
            slippage_cost=total_slippage,
            market_impact_cost=total_market_impact,
            total_cost=total_cost,
            cost_percentage=cost_percentage
        )

    async def get_execution_engine_status(self) -> Dict[str, Any]:
        """
        获取执行引擎状态

        Returns:
            状态信息
        """
        async with self._lock:
            active_orders = len([o for o in self.orders.values() if o.is_active])
            total_orders = len(self.order_history)
            total_trades = sum(len(trades) for trades in self.trades.values())

            return {
                "running": self._running,
                "active_orders": active_orders,
                "total_orders": total_orders,
                "total_trades": total_trades,
                "config": self.config
            }


# 使用示例
async def example_usage():
    """交易执行引擎使用示例"""

    # 创建执行引擎
    engine = TradingExecutionEngine()
    await engine.initialize()

    try:
        # 在不同交易所创建订单
        logger.info("=== 在不同交易所创建订单 ===")
        
        # 在Binance创建市价单
        binance_order = await engine.create_order_with_exchange(
            exchange="binance",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.01
        )
        logger.info(f"在Binance创建订单: {binance_order.order_id}")
        
        # 在Coinbase创建限价单
        coinbase_order = await engine.create_order_with_exchange(
            exchange="coinbase",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.005,
            price=40000.0
        )
        logger.info(f"在Coinbase创建订单: {coinbase_order.order_id}")

        # 等待执行
        await asyncio.sleep(2)

        # 获取订单状态
        logger.info("\n=== 订单执行状态 ===")
        updated_binance_order = engine.get_order(binance_order.order_id)
        logger.info(f"Binance订单状态: {updated_binance_order.status.value}")
        logger.info(f"成交数量: {updated_binance_order.filled_quantity}")
        logger.info(f"平均价格: {updated_binance_order.avg_fill_price}")

        # 测试智能执行算法
        logger.info("\n=== 测试智能执行算法 ===")
        
        # 创建TWAP订单
        twap_order = await engine.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.02,
            twap_duration=timedelta(minutes=1),
            twap_interval=timedelta(seconds=10)
        )
        logger.info(f"创建TWAP订单: {twap_order.order_id}")

        # 等待TWAP执行
        await asyncio.sleep(70)  # 等待1分10秒

        # 获取TWAP订单状态
        updated_twap_order = engine.get_order(twap_order.order_id)
        logger.info(f"TWAP订单状态: {updated_twap_order.status.value}")
        logger.info(f"TWAP成交数量: {updated_twap_order.filled_quantity}/{updated_twap_order.quantity}")

        # 创建冰山订单
        iceberg_order = await engine.create_order(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=0.03,
            price=42000.0,
            iceberg_visible_size=0.005
        )
        logger.info(f"\n创建冰山订单: {iceberg_order.order_id}")

        # 等待冰山订单执行
        await asyncio.sleep(40)

        # 获取冰山订单状态
        updated_iceberg_order = engine.get_order(iceberg_order.order_id)
        logger.info(f"冰山订单状态: {updated_iceberg_order.status.value}")
        logger.info(f"冰山成交数量: {updated_iceberg_order.filled_quantity}/{updated_iceberg_order.quantity}")

        # 分析交易成本
        logger.info("\n=== 交易成本分析 ===")
        cost = await engine.analyze_trading_costs(binance_order.order_id)
        if cost:
            logger.info(f"Binance订单成本分析:")
            logger.info(f"  佣金: {cost.commission_cost}")
            logger.info(f"  滑点: {cost.slippage_cost}")
            logger.info(f"  市场冲击: {cost.market_impact_cost}")
            logger.info(f"  总成本: {cost.total_cost}")
            logger.info(f"  成本占比: {cost.cost_percentage:.2f}%")

        # 获取执行引擎状态
        status = await engine.get_execution_engine_status()
        logger.info("\n=== 执行引擎状态 ===")
        logger.info(f"运行状态: {status['running']}")
        logger.info(f"活跃订单: {status['active_orders']}")
        logger.info(f"总订单数: {status['total_orders']}")
        logger.info(f"总交易数: {status['total_trades']}")

    finally:
        await engine.shutdown()


if __name__ == "__main__":
    asyncio.run(example_usage())
