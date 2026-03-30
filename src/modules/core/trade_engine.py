"""
交易引擎模块 - 全智能量化交易系统的核心业务逻辑

功能：
1. 订单管理（创建、修改、取消）
2. 仓位管理（计算持仓和盈亏）
3. 执行逻辑（订单路由和成交处理）
4. 费用计算（手续费和滑点）
5. 业绩统计（PnL计算和报告）
"""

import asyncio
import logging
import math
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    """订单方向"""

    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """订单类型"""

    MARKET = "market"  # 市价单
    LIMIT = "limit"  # 限价单
    STOP = "stop"  # 止损单
    STOP_LIMIT = "stop_limit"  # 止损限价单


class OrderStatus(Enum):
    """订单状态"""

    PENDING = "pending"  # 待处理
    SUBMITTED = "submitted"  # 已提交
    PARTIAL_FILL = "partial"  # 部分成交
    FILLED = "filled"  # 完全成交
    CANCELLED = "cancelled"  # 已取消
    REJECTED = "rejected"  # 已拒绝
    EXPIRED = "expired"  # 已过期


class PositionSide(Enum):
    """仓位方向"""

    LONG = "long"  # 多头
    SHORT = "short"  # 空头
    FLAT = "flat"  # 平仓


@dataclass
class Order:
    """订单"""

    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    commission: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    strategy_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def remaining_quantity(self) -> float:
        """剩余数量"""
        return self.quantity - self.filled_quantity

    @property
    def is_filled(self) -> bool:
        """是否完全成交"""
        return self.status == OrderStatus.FILLED

    @property
    def is_active(self) -> bool:
        """是否活跃（可成交）"""
        active_statuses = [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILL]
        return self.status in active_statuses

    @property
    def value(self) -> float:
        """订单价值"""
        if self.price:
            return self.quantity * self.price
        return 0.0

    def update_fill(self, fill_quantity: float, fill_price: float, commission: float = 0.0) -> None:
        """更新成交"""
        self.filled_quantity += fill_quantity
        self.avg_fill_price = (
            self.avg_fill_price * (self.filled_quantity - fill_quantity)
            + fill_price * fill_quantity
        ) / self.filled_quantity
        self.commission += commission

        if abs(self.filled_quantity - self.quantity) < 1e-8:  # 浮点数容差
            self.status = OrderStatus.FILLED
            self.filled_at = datetime.now()
        else:
            self.status = OrderStatus.PARTIAL_FILL

        self.updated_at = datetime.now()


@dataclass
class Position:
    """仓位"""

    symbol: str
    side: PositionSide
    quantity: float = 0.0
    avg_entry_price: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_commission: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def market_value(self) -> float:
        """市值"""
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        """成本基础"""
        return self.quantity * self.avg_entry_price

    @property
    def total_pnl(self) -> float:
        """总盈亏"""
        return self.unrealized_pnl + self.realized_pnl

    @property
    def pnl_percentage(self) -> float:
        """盈亏百分比"""
        if self.cost_basis > 0:
            return (self.total_pnl / self.cost_basis) * 100
        return 0.0

    def update_price(self, price: float) -> None:
        """更新价格"""
        self.current_price = price
        self._calculate_unrealized_pnl()
        self.updated_at = datetime.now()

    def update_position(
        self, side: OrderSide, quantity: float, price: float, commission: float
    ) -> None:
        """更新仓位"""
        old_quantity = self.quantity
        old_avg_price = self.avg_entry_price

        if side == OrderSide.BUY:
            # 买入
            new_quantity = old_quantity + quantity
            if new_quantity > 0:
                self.avg_entry_price = (
                    old_quantity * old_avg_price + quantity * price
                ) / new_quantity
            self.quantity = new_quantity

            # 如果是空头平仓，计算已实现盈亏
            if self.side == PositionSide.SHORT and old_quantity < 0:
                realized_pnl = (old_avg_price - price) * min(abs(old_quantity), quantity)
                self.realized_pnl += realized_pnl

        elif side == OrderSide.SELL:
            # 卖出
            new_quantity = old_quantity - quantity
            if abs(new_quantity) > 0:
                # 保持平均价格不变（对于减少的仓位）
                self.avg_entry_price = old_avg_price
            self.quantity = new_quantity

            # 如果是多头平仓，计算已实现盈亏
            if self.side == PositionSide.LONG and old_quantity > 0:
                realized_pnl = (price - old_avg_price) * min(old_quantity, quantity)
                self.realized_pnl += realized_pnl

        # 更新手续费
        self.total_commission += commission

        # 更新方向
        if abs(self.quantity) < 1e-8:
            self.side = PositionSide.FLAT
        elif self.quantity > 0:
            self.side = PositionSide.LONG
        else:
            self.side = PositionSide.SHORT

        # 计算未实现盈亏
        self._calculate_unrealized_pnl()
        self.updated_at = datetime.now()

    def _calculate_unrealized_pnl(self) -> None:
        """计算未实现盈亏"""
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (self.current_price - self.avg_entry_price) * self.quantity
        elif self.side == PositionSide.SHORT:
            self.unrealized_pnl = (self.avg_entry_price - self.current_price) * abs(self.quantity)
        else:
            self.unrealized_pnl = 0.0


@dataclass
class Trade:
    """交易记录"""

    id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float
    timestamp: datetime = field(default_factory=datetime.now)
    strategy_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PortfolioStats:
    """投资组合统计"""

    total_value: float = 0.0
    cash_balance: float = 0.0
    position_value: float = 0.0
    total_pnl: float = 0.0
    daily_pnl: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


class TradeEngine:
    """
    交易引擎

    核心功能：
    1. 订单管理
    2. 仓位管理
    3. 执行逻辑
    4. 费用计算
    5. 业绩统计
    """

    def __init__(self, config_manager=None, initial_capital: float = 100000.0):
        """
        初始化交易引擎

        Args:
            config_manager: 配置管理器实例
            initial_capital: 初始资金
        """
        self.config_manager = config_manager

        # 订单管理
        self.orders: Dict[str, Order] = {}
        self.order_history: List[Order] = []

        # 仓位管理
        self.positions: Dict[str, Position] = {}
        self.position_history: List[Dict[str, Any]] = []

        # 交易记录
        self.trades: List[Trade] = []

        # 资金管理
        self.cash_balance: float = initial_capital
        self.initial_capital: float = initial_capital
        self.reserved_cash: float = 0.0  # 为未完成订单保留的资金

        # 费用配置
        self.commission_rate: float = 0.001  # 0.1%
        self.slippage_rate: float = 0.0005  # 0.05%
        self.min_commission: float = 0.01

        # 风险管理
        self.max_position_size: float = 0.1  # 单仓位最大比例（10%）
        self.max_daily_loss: float = 0.02  # 单日最大损失（2%）
        self.max_position_count: int = 10  # 最大持仓数量

        # 统计
        self.portfolio_stats = PortfolioStats()
        self.daily_pnl_history: List[Dict[str, Any]] = []

        # 执行器
        self.execution_handlers: List[Callable] = []

        # 锁和状态
        self._lock = asyncio.Lock()
        self._initialized = False
        self._running = False

        logger.info(f"交易引擎初始化完成，初始资金: ${initial_capital:,.2f}")

    async def initialize(self) -> None:
        """
        初始化交易引擎

        加载配置，设置执行器
        """
        if self._initialized:
            return

        logger.info("初始化交易引擎...")

        try:
            # 加载配置
            await self._load_config()

            # 设置默认执行器
            self._setup_default_executors()

            # 初始化投资组合统计
            await self._update_portfolio_stats()

            self._initialized = True
            logger.info("交易引擎初始化完成")

        except Exception as e:
            logger.error(f"交易引擎初始化失败: {e}")
            traceback.print_exc()

    async def cleanup(self) -> None:
        """
        清理交易引擎

        保存状态，清理资源
        """
        logger.info("清理交易引擎...")

        # 保存最终状态
        await self._save_state()

        # 清理资源
        self.orders.clear()
        self.positions.clear()
        self.trades.clear()

        self._initialized = False
        logger.info("交易引擎清理完成")

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        strategy_id: Optional[str] = None,
    ) -> Optional[Order]:
        """
        创建订单

        Args:
            symbol: 交易对
            side: 方向（买/卖）
            order_type: 类型（市价/限价等）
            quantity: 数量
            price: 价格（限价单需要）
            stop_price: 止损价格（止损单需要）
            strategy_id: 策略ID

        Returns:
            创建的订单或None
        """
        async with self._lock:
            try:
                # 验证订单
                validation_error = await self._validate_order(
                    symbol, side, order_type, quantity, price, stop_price
                )

                if validation_error:
                    logger.error(f"订单验证失败: {validation_error}")
                    return None

                # 创建订单
                order_id = f"order_{uuid.uuid4().hex[:8]}"
                order = Order(
                    id=order_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    quantity=quantity,
                    price=price,
                    stop_price=stop_price,
                    strategy_id=strategy_id,
                )

                # 保留资金（对于买单）
                if side == OrderSide.BUY:
                    order_value = quantity * (
                        price if price else await self._get_current_price(symbol)
                    )
                    required_cash = order_value * (1 + self.commission_rate)

                    if self.cash_balance - self.reserved_cash >= required_cash:
                        self.reserved_cash += required_cash
                    else:
                        logger.error(
                            f"资金不足: 需要${required_cash:,.2f}, 可用${self.cash_balance - self.reserved_cash:,.2f}"
                        )
                        return None

                # 保存订单
                self.orders[order_id] = order
                self.order_history.append(order)

                logger.info(
                    f"创建订单: {order_id} {side.value} {quantity} {symbol} "
                    f"@{price if price else 'MARKET'}"
                )

                # 执行订单
                asyncio.create_task(self._execute_order(order_id))

                return order

            except Exception as e:
                logger.error(f"创建订单失败: {e}")
                traceback.print_exc()
                return None

    async def cancel_order(self, order_id: str) -> bool:
        """
        取消订单

        Args:
            order_id: 订单ID

        Returns:
            是否取消成功
        """
        async with self._lock:
            if order_id not in self.orders:
                logger.error(f"订单不存在: {order_id}")
                return False

            order = self.orders[order_id]

            # 只能取消活跃订单
            if not order.is_active:
                logger.warning(f"订单不可取消: {order_id} 状态={order.status.value}")
                return False

            # 更新订单状态
            order.status = OrderStatus.CANCELLED
            order.cancelled_at = datetime.now()
            order.updated_at = datetime.now()

            # 释放保留资金（对于买单）
            if order.side == OrderSide.BUY and order.status == OrderStatus.PENDING:
                order_value = order.quantity * (
                    order.price if order.price else await self._get_current_price(order.symbol)
                )
                required_cash = order_value * (1 + self.commission_rate)
                self.reserved_cash = max(0, self.reserved_cash - required_cash)

            logger.info(f"取消订单: {order_id}")
            return True

    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        获取订单

        Args:
            order_id: 订单ID

        Returns:
            订单或None
        """
        return self.orders.get(order_id)

    async def get_orders(
        self, symbol: Optional[str] = None, status: Optional[OrderStatus] = None
    ) -> List[Order]:
        """
        获取订单列表

        Args:
            symbol: 过滤交易对
            status: 过滤状态

        Returns:
            订单列表
        """
        orders = list(self.orders.values())

        if symbol:
            orders = [o for o in orders if o.symbol == symbol]

        if status:
            orders = [o for o in orders if o.status == status]

        return orders

    async def get_position(self, symbol: str) -> Optional[Position]:
        """
        获取仓位

        Args:
            symbol: 交易对

        Returns:
            仓位或None
        """
        return self.positions.get(symbol)

    async def get_positions(self) -> List[Position]:
        """
        获取所有仓位

        Returns:
            仓位列表
        """
        return list(self.positions.values())

    async def update_market_price(self, symbol: str, price: float) -> None:
        """
        更新市场价格

        Args:
            symbol: 交易对
            price: 价格
        """
        async with self._lock:
            # 更新仓位价格
            if symbol in self.positions:
                self.positions[symbol].update_price(price)

            # 检查止损单
            await self._check_stop_orders(symbol, price)

            # 更新投资组合统计
            await self._update_portfolio_stats()

    async def get_portfolio_stats(self) -> PortfolioStats:
        """
        获取投资组合统计

        Returns:
            投资组合统计
        """
        async with self._lock:
            return self.portfolio_stats

    async def get_trade_history(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Trade]:
        """
        获取交易历史

        Args:
            symbol: 过滤交易对
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            交易历史
        """
        trades = self.trades.copy()

        if symbol:
            trades = [t for t in trades if t.symbol == symbol]

        if start_time:
            trades = [t for t in trades if t.timestamp >= start_time]

        if end_time:
            trades = [t for t in trades if t.timestamp <= end_time]

        trades.sort(key=lambda t: t.timestamp, reverse=True)
        return trades

    async def calculate_pnl(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, float]:
        """
        计算盈亏

        Args:
            symbol: 过滤交易对
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            盈亏统计
        """
        trades = await self.get_trade_history(symbol, start_time, end_time)

        total_pnl = 0.0
        total_commission = 0.0
        win_count = 0
        loss_count = 0

        # 按交易计算盈亏
        position_map: Dict[str, List[Trade]] = {}
        for trade in trades:
            if trade.symbol not in position_map:
                position_map[trade.symbol] = []
            position_map[trade.symbol].append(trade)

        # 计算每个交易对的盈亏
        for symbol_trades in position_map.values():
            # 按时间排序
            symbol_trades.sort(key=lambda t: t.timestamp)

            # 模拟计算（简化版）
            # 在实际系统中，应该根据实际持仓计算
            for trade in symbol_trades:
                total_commission += trade.commission

                # 简单示例：假设所有卖出都是盈利的
                if trade.side == OrderSide.SELL:
                    total_pnl += trade.quantity * trade.price * 0.01  # 假设1%利润
                    win_count += 1
                else:
                    loss_count += 1

        return {
            "total_pnl": total_pnl,
            "total_commission": total_commission,
            "net_pnl": total_pnl - total_commission,
            "win_rate": win_count / len(trades) if trades else 0.0,
            "total_trades": len(trades),
            "winning_trades": win_count,
            "losing_trades": loss_count,
        }

    # 私有方法

    async def _load_config(self) -> None:
        """加载交易配置"""
        if self.config_manager:
            trade_config = await self.config_manager.get_config("trading", {})

            self.commission_rate = trade_config.get("commission_rate", self.commission_rate)
            self.slippage_rate = trade_config.get("slippage_rate", self.slippage_rate)
            self.min_commission = trade_config.get("min_commission", self.min_commission)
            self.max_position_size = trade_config.get("max_position_size", self.max_position_size)
            self.max_daily_loss = trade_config.get("max_daily_loss", self.max_daily_loss)
            self.max_position_count = trade_config.get(
                "max_position_count", self.max_position_count
            )

        logger.info(
            f"加载交易配置: 手续费率={self.commission_rate*100:.2f}%, "
            f"滑点={self.slippage_rate*100:.2f}%"
        )

    def _setup_default_executors(self) -> None:
        """设置默认执行器"""

        async def market_order_executor(order: Order, current_price: float) -> bool:
            """市价单执行器"""
            # 应用滑点
            if order.side == OrderSide.BUY:
                execution_price = current_price * (1 + self.slippage_rate)
            else:  # SELL
                execution_price = current_price * (1 - self.slippage_rate)

            # 计算手续费
            commission = max(
                order.quantity * execution_price * self.commission_rate, self.min_commission
            )

            # 执行成交
            await self._execute_fill(order, order.quantity, execution_price, commission)
            return True

        async def limit_order_executor(order: Order, current_price: float) -> bool:
            """限价单执行器"""
            if order.price is None:
                logger.error(f"限价单缺少价格: {order.id}")
                return False

            # 检查价格条件
            if (order.side == OrderSide.BUY and current_price <= order.price) or (
                order.side == OrderSide.SELL and current_price >= order.price
            ):

                # 计算手续费
                commission = max(
                    order.quantity * order.price * self.commission_rate, self.min_commission
                )

                # 执行成交
                await self._execute_fill(order, order.quantity, order.price, commission)
                return True

            return False

        # 注册执行器
        self.execution_handlers = [market_order_executor, limit_order_executor]

    async def _validate_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float],
        stop_price: Optional[float],
    ) -> Optional[str]:
        """验证订单"""
        # 检查数量
        if quantity <= 0:
            return "数量必须大于0"

        # 检查价格
        if order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and price is None:
            return "限价单需要价格"

        if order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and stop_price is None:
            return "止损单需要止损价格"

        # 检查资金（对于买单）
        if side == OrderSide.BUY:
            order_value = quantity * (price if price else await self._get_current_price(symbol))
            required_cash = order_value * (1 + self.commission_rate)

            if self.cash_balance - self.reserved_cash < required_cash:
                return f"资金不足: 需要${required_cash:,.2f}, 可用${self.cash_balance - self.reserved_cash:,.2f}"

        # 检查仓位限制
        if symbol in self.positions:
            position = self.positions[symbol]
            if side == OrderSide.BUY and position.side == PositionSide.SHORT:
                # 空头平仓买入
                pass
            elif side == OrderSide.SELL and position.side == PositionSide.LONG:
                # 多头平仓卖出
                pass
            else:
                # 开新仓位或加仓
                portfolio_value = await self._get_portfolio_value()
                max_position_value = portfolio_value * self.max_position_size

                if (
                    position.market_value
                    + quantity * (price or await self._get_current_price(symbol))
                    > max_position_value
                ):
                    return f"超过单仓位限制: 最大${max_position_value:,.2f}"

        # 检查持仓数量限制
        active_positions = sum(1 for p in self.positions.values() if abs(p.quantity) > 1e-8)
        if (
            symbol not in self.positions
            or abs(self.positions.get(symbol, Position(symbol, PositionSide.FLAT)).quantity) < 1e-8
        ):
            if active_positions >= self.max_position_count:
                return f"超过最大持仓数量: {self.max_position_count}"

        return None

    async def _execute_order(self, order_id: str) -> None:
        """执行订单"""
        async with self._lock:
            if order_id not in self.orders:
                return

            order = self.orders[order_id]

            # 更新订单状态
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now()
            order.updated_at = datetime.now()

            logger.info(f"提交订单执行: {order_id}")

        try:
            # 获取当前价格
            current_price = await self._get_current_price(order.symbol)

            # 根据订单类型选择执行器
            success = False
            for handler in self.execution_handlers:
                if await handler(order, current_price):
                    success = True
                    break

            if not success and order.is_active:
                # 如果订单仍然活跃但没有执行，保持待处理状态
                logger.debug(f"订单未执行: {order_id}")

        except Exception as e:
            logger.error(f"订单执行失败 {order_id}: {e}")
            traceback.print_exc()

            async with self._lock:
                order.status = OrderStatus.REJECTED
                order.updated_at = datetime.now()

    async def _execute_fill(
        self, order: Order, fill_quantity: float, fill_price: float, commission: float
    ) -> None:
        """执行成交"""
        async with self._lock:
            # 更新订单
            order.update_fill(fill_quantity, fill_price, commission)

            # 更新资金
            if order.side == OrderSide.BUY:
                # 买入：减少现金
                cost = fill_quantity * fill_price + commission
                self.cash_balance -= cost
                self.reserved_cash = max(0, self.reserved_cash - cost)
            else:  # SELL
                # 卖出：增加现金
                revenue = fill_quantity * fill_price - commission
                self.cash_balance += revenue

            # 更新仓位
            symbol = order.symbol
            if symbol not in self.positions:
                # 创建新仓位
                side = PositionSide.LONG if order.side == OrderSide.BUY else PositionSide.SHORT
                self.positions[symbol] = Position(
                    symbol=symbol, side=side, current_price=fill_price
                )

            # 更新仓位数量
            self.positions[symbol].update_position(
                order.side, fill_quantity, fill_price, commission
            )

            # 创建交易记录
            trade = Trade(
                id=f"trade_{uuid.uuid4().hex[:8]}",
                order_id=order.id,
                symbol=order.symbol,
                side=order.side,
                quantity=fill_quantity,
                price=fill_price,
                commission=commission,
                strategy_id=order.strategy_id,
            )
            self.trades.append(trade)

            logger.info(
                f"订单成交: {order.id} {order.side.value} {fill_quantity} {order.symbol} "
                f"@{fill_price:.4f}, 手续费${commission:.4f}"
            )

    async def _check_stop_orders(self, symbol: str, current_price: float) -> None:
        """检查止损单"""
        for order_id, order in list(self.orders.items()):
            if (
                order.symbol == symbol
                and order.is_active
                and order.order_type in [OrderType.STOP, OrderType.STOP_LIMIT]
                and order.stop_price is not None
            ):

                # 检查止损条件
                trigger = False
                if order.side == OrderSide.BUY and current_price >= order.stop_price:
                    # 买入止损：价格高于止损价时触发
                    trigger = True
                elif order.side == OrderSide.SELL and current_price <= order.stop_price:
                    # 卖出止损：价格低于止损价时触发
                    trigger = True

                if trigger:
                    logger.info(
                        f"止损单触发: {order_id} {order.side.value} {order.symbol} "
                        f"@{current_price:.4f} (止损价: {order.stop_price:.4f})"
                    )

                    # 转换为市价单或限价单执行
                    if order.order_type == OrderType.STOP:
                        # 止损市价单
                        await self._execute_fill(
                            order,
                            order.remaining_quantity,
                            current_price,
                            max(
                                order.quantity * current_price * self.commission_rate,
                                self.min_commission,
                            ),
                        )
                    elif order.order_type == OrderType.STOP_LIMIT and order.price is not None:
                        # 止损限价单：检查限价条件
                        if (order.side == OrderSide.BUY and current_price <= order.price) or (
                            order.side == OrderSide.SELL and current_price >= order.price
                        ):

                            await self._execute_fill(
                                order,
                                order.remaining_quantity,
                                order.price,
                                max(
                                    order.quantity * order.price * self.commission_rate,
                                    self.min_commission,
                                ),
                            )

    async def _update_portfolio_stats(self) -> None:
        """更新投资组合统计"""
        # 计算仓位总价值
        position_value = 0.0
        for position in self.positions.values():
            position_value += position.market_value

        # 计算总投资组合价值
        total_value = self.cash_balance + position_value

        # 计算总盈亏
        total_pnl = total_value - self.initial_capital

        # 更新统计
        self.portfolio_stats = PortfolioStats(
            total_value=total_value,
            cash_balance=self.cash_balance,
            position_value=position_value,
            total_pnl=total_pnl,
            daily_pnl=0.0,  # 需要按日计算
            total_trades=len(self.trades),
            timestamp=datetime.now(),
        )

    async def _get_current_price(self, symbol: str) -> float:
        """获取当前价格（模拟）"""
        # 在实际系统中，这里应该从市场数据模块获取
        # 为简化，返回模拟价格
        base_prices = {
            "BTC/USDT": 50000.0,
            "ETH/USDT": 3000.0,
            "BNB/USDT": 400.0,
        }
        return base_prices.get(symbol, 100.0)

    async def _get_portfolio_value(self) -> float:
        """获取投资组合价值"""
        position_value = sum(p.market_value for p in self.positions.values())
        return self.cash_balance + position_value

    async def _save_state(self) -> None:
        """保存状态"""
        # 在实际系统中，这里应该保存到数据库
        logger.info("保存交易引擎状态")


# 使用示例
async def example_usage():
    """交易引擎使用示例"""

    # 创建交易引擎
    engine = TradeEngine(initial_capital=100000.0)
    await engine.initialize()

    try:
        # 创建市价买单
        buy_order = await engine.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.5,  # 0.5 BTC
            strategy_id="moving_average",
        )

        if buy_order:
            print(f"创建买单: {buy_order.id} {buy_order.quantity} BTC @ 市价")

        # 等待执行
        await asyncio.sleep(1)

        # 获取订单状态
        if buy_order:
            order_status = await engine.get_order(buy_order.id)
            print(f"订单状态: {order_status.status.value if order_status else 'N/A'}")

        # 获取仓位
        positions = await engine.get_positions()
        print(f"仓位数量: {len(positions)}")

        for position in positions:
            print(
                f"  {position.symbol}: {position.quantity} @ {position.avg_entry_price:.2f}, "
                f"当前价: {position.current_price:.2f}, PnL: ${position.total_pnl:.2f}"
            )

        # 获取投资组合统计
        stats = await engine.get_portfolio_stats()
        print(f"投资组合价值: ${stats.total_value:,.2f}")
        print(f"现金余额: ${stats.cash_balance:,.2f}")
        print(f"总盈亏: ${stats.total_pnl:,.2f}")

        # 创建限价卖单
        sell_order = await engine.create_order(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=0.3,
            price=51000.0,
            strategy_id="profit_taking",
        )

        if sell_order:
            print(f"创建卖单: {sell_order.id} {sell_order.quantity} BTC @ {sell_order.price:.2f}")

        # 计算盈亏
        pnl_stats = await engine.calculate_pnl()
        print(f"盈亏统计: {pnl_stats}")

    finally:
        await engine.cleanup()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
