"""
模拟合约交易管理器

支持功能：
1. 模拟合约交易（永续合约）
2. 支持全仓/逐仓模式
3. 支持杠杆交易
4. 模拟手续费
5. 模拟资金费率
6. 持仓管理
7. 盈亏计算
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class MarginMode(Enum):
    """保证金模式"""
    CROSS = "cross"      # 全仓
    ISOLATED = "isolated"  # 逐仓


class ContractType(Enum):
    """合约类型"""
    PERPETUAL = "perpetual"  # 永续合约
    FUTURES = "futures"      # 交割合约


class PositionSide(Enum):
    """持仓方向"""
    LONG = "long"    # 做多
    SHORT = "short"  # 做空


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    side: PositionSide
    size: float           # 持仓数量
    entry_price: float    # 开仓价格
    leverage: float       # 杠杆倍数
    margin_mode: MarginMode
    margin: float         # 保证金
    unrealized_pnl: float = 0.0  # 未实现盈亏
    realized_pnl: float = 0.0    # 已实现盈亏
    funding_fee: float = 0.0     # 资金费
    open_time: datetime = field(default_factory=datetime.now)
    
    def update_pnl(self, current_price: float):
        """更新未实现盈亏"""
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (current_price - self.entry_price) * self.size
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * self.size
    
    @property
    def liquidation_price(self) -> float:
        """计算爆仓价格"""
        if self.margin_mode == MarginMode.ISOLATED:
            # 逐仓模式
            if self.side == PositionSide.LONG:
                return self.entry_price * (1 - 1 / self.leverage + 0.005)
            else:
                return self.entry_price * (1 + 1 / self.leverage - 0.005)
        else:
            # 全仓模式需要账户总权益，这里简化计算
            if self.side == PositionSide.LONG:
                return self.entry_price * (1 - 0.9 / self.leverage)
            else:
                return self.entry_price * (1 + 0.9 / self.leverage)
    
    @property
    def pnl_percentage(self) -> float:
        """盈亏百分比"""
        if self.margin > 0:
            return (self.unrealized_pnl / self.margin) * 100
        return 0.0


@dataclass
class Order:
    """订单信息"""
    order_id: str
    symbol: str
    side: PositionSide
    order_type: str       # market, limit
    size: float
    price: Optional[float] = None
    leverage: float = 10.0
    margin_mode: MarginMode = MarginMode.CROSS
    status: str = "pending"
    filled_size: float = 0.0
    avg_fill_price: float = 0.0
    fee: float = 0.0
    create_time: datetime = field(default_factory=datetime.now)
    fill_time: Optional[datetime] = None


@dataclass
class Account:
    """账户信息"""
    total_equity: float = 0.0      # 总权益
    available_balance: float = 0.0  # 可用余额
    margin_balance: float = 0.0     # 保证金余额
    unrealized_pnl: float = 0.0     # 未实现盈亏
    realized_pnl: float = 0.0       # 已实现盈亏
    total_fee: float = 0.0          # 总手续费
    
    @property
    def total_margin_used(self) -> float:
        """总占用保证金"""
        return self.margin_balance - self.available_balance


class ContractSimulator:
    """模拟合约交易管理器"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化模拟合约交易管理器
        
        Args:
            config: 配置参数
        """
        self.config = config or {}
        
        # 交易配置
        self.initial_capital = self.config.get("initial_capital", 100000)
        self.leverage = self.config.get("leverage", 10)
        self.margin_mode = MarginMode(self.config.get("margin_mode", "cross"))
        self.contract_type = ContractType(self.config.get("contract_type", "perpetual"))
        self.fee_rate = self.config.get("fee_rate", {"maker": 0.0002, "taker": 0.0005})
        self.symbols = self.config.get("symbols", ["BTC/USDT", "ETH/USDT"])
        
        # 账户状态
        self.account = Account(
            total_equity=self.initial_capital,
            available_balance=self.initial_capital,
            margin_balance=self.initial_capital
        )
        
        # 持仓和订单
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        self.orders: Dict[str, Order] = {}        # order_id -> Order
        self.order_history: List[Order] = []
        
        # 价格数据
        self.current_prices: Dict[str, float] = {}
        
        # 运行状态
        self.running = False
        self._task = None
        
        logger.info(f"模拟合约交易管理器初始化完成")
        logger.info(f"初始资金: {self.initial_capital} USDT, 杠杆: {self.leverage}x")
    
    async def initialize(self):
        """初始化"""
        logger.info("初始化模拟合约交易环境...")
        self.running = True
        
        # 启动资金费率计算任务
        self._task = asyncio.create_task(self._funding_fee_worker())
        
        logger.info("模拟合约交易环境初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        logger.info("清理模拟合约交易环境...")
        self.running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("模拟合约交易环境清理完成")
    
    async def _funding_fee_worker(self):
        """资金费率计算任务（每8小时）"""
        while self.running:
            try:
                await asyncio.sleep(8 * 3600)  # 8小时
                await self._apply_funding_fee()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"资金费率计算出错: {e}")
    
    async def _apply_funding_fee(self):
        """应用资金费"""
        funding_rate = 0.0001  # 0.01% 资金费率
        
        for position in self.positions.values():
            fee = position.size * position.entry_price * funding_rate
            if position.side == PositionSide.LONG:
                position.funding_fee -= fee
                self.account.realized_pnl -= fee
            else:
                position.funding_fee += fee
                self.account.realized_pnl += fee
        
        logger.info(f"已应用资金费率: {funding_rate}")
    
    def update_price(self, symbol: str, price: float):
        """更新价格"""
        self.current_prices[symbol] = price
        
        # 更新持仓盈亏
        if symbol in self.positions:
            self.positions[symbol].update_pnl(price)
            self._update_account_pnl()
    
    def _update_account_pnl(self):
        """更新账户盈亏"""
        total_unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        self.account.unrealized_pnl = total_unrealized
        self.account.total_equity = self.initial_capital + self.account.realized_pnl + total_unrealized
    
    async def place_order(self, symbol: str, side: str, size: float, 
                         order_type: str = "market", price: Optional[float] = None,
                         leverage: Optional[float] = None) -> Order:
        """
        下单
        
        Args:
            symbol: 交易对
            side: 方向 (long/short)
            size: 数量
            order_type: 订单类型
            price: 价格（限价单）
            leverage: 杠杆倍数
        
        Returns:
            Order: 订单对象
        """
        order_id = f"sim_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        leverage = leverage or self.leverage
        
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=PositionSide(side),
            order_type=order_type,
            size=size,
            price=price,
            leverage=leverage,
            margin_mode=self.margin_mode
        )
        
        # 获取当前价格
        current_price = self.current_prices.get(symbol, price or 50000)
        
        # 计算所需保证金
        required_margin = (size * current_price) / leverage
        
        # 检查可用余额
        if required_margin > self.account.available_balance:
            order.status = "rejected"
            logger.warning(f"订单被拒绝: 保证金不足")
            return order
        
        # 模拟成交
        fill_price = price if price else current_price
        fee_rate = self.fee_rate["maker"] if order_type == "limit" else self.fee_rate["taker"]
        fee = size * fill_price * fee_rate
        
        order.filled_size = size
        order.avg_fill_price = fill_price
        order.fee = fee
        order.status = "filled"
        order.fill_time = datetime.now()
        
        # 更新账户
        self.account.available_balance -= required_margin
        self.account.margin_balance -= fee
        self.account.total_fee += fee
        self.account.realized_pnl -= fee
        
        # 更新或创建持仓
        await self._update_position(symbol, PositionSide(side), size, fill_price, leverage, required_margin)
        
        # 保存订单
        self.orders[order_id] = order
        self.order_history.append(order)
        
        logger.info(f"订单成交: {order_id}, {symbol}, {side}, 数量: {size}, 价格: {fill_price}")
        
        return order
    
    async def _update_position(self, symbol: str, side: PositionSide, size: float, 
                              price: float, leverage: float, margin: float):
        """更新持仓"""
        if symbol in self.positions:
            position = self.positions[symbol]
            
            if position.side == side:
                # 加仓
                total_size = position.size + size
                position.entry_price = (position.entry_price * position.size + price * size) / total_size
                position.size = total_size
                position.margin += margin
            else:
                # 减仓或反向
                if position.size > size:
                    # 部分平仓
                    pnl = (price - position.entry_price) * size if side == PositionSide.SHORT else (position.entry_price - price) * size
                    position.size -= size
                    self.account.realized_pnl += pnl
                    self.account.available_balance += margin + pnl
                elif position.size == size:
                    # 完全平仓
                    pnl = (price - position.entry_price) * size if side == PositionSide.SHORT else (position.entry_price - price) * size
                    self.account.realized_pnl += pnl
                    self.account.available_balance += margin + pnl
                    del self.positions[symbol]
                else:
                    # 反向开仓
                    pnl = (price - position.entry_price) * position.size if side == PositionSide.SHORT else (position.entry_price - price) * position.size
                    remaining_size = size - position.size
                    self.account.realized_pnl += pnl
                    self.account.available_balance += position.margin + pnl
                    
                    # 创建新持仓
                    self.positions[symbol] = Position(
                        symbol=symbol,
                        side=side,
                        size=remaining_size,
                        entry_price=price,
                        leverage=leverage,
                        margin_mode=self.margin_mode,
                        margin=margin
                    )
        else:
            # 新开仓
            self.positions[symbol] = Position(
                symbol=symbol,
                side=side,
                size=size,
                entry_price=price,
                leverage=leverage,
                margin_mode=self.margin_mode,
                margin=margin
            )
        
        self._update_account_pnl()
    
    async def close_position(self, symbol: str, size: Optional[float] = None) -> Optional[Order]:
        """平仓"""
        if symbol not in self.positions:
            logger.warning(f"没有持仓: {symbol}")
            return None
        
        position = self.positions[symbol]
        close_size = size or position.size
        current_price = self.current_prices.get(symbol, position.entry_price)
        
        # 创建反向订单
        opposite_side = PositionSide.SHORT if position.side == PositionSide.LONG else PositionSide.LONG
        
        order = await self.place_order(
            symbol=symbol,
            side=opposite_side.value,
            size=close_size,
            order_type="market"
        )
        
        return order
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        return list(self.positions.values())
    
    def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息"""
        return {
            "total_equity": self.account.total_equity,
            "available_balance": self.account.available_balance,
            "margin_balance": self.account.margin_balance,
            "unrealized_pnl": self.account.unrealized_pnl,
            "realized_pnl": self.account.realized_pnl,
            "total_fee": self.account.total_fee,
            "total_margin_used": self.account.total_margin_used,
            "positions_count": len(self.positions),
            "leverage": self.leverage,
            "margin_mode": self.margin_mode.value
        }
    
    def get_trading_stats(self) -> Dict[str, Any]:
        """获取交易统计"""
        filled_orders = [o for o in self.order_history if o.status == "filled"]
        
        long_orders = [o for o in filled_orders if o.side == PositionSide.LONG]
        short_orders = [o for o in filled_orders if o.side == PositionSide.SHORT]
        
        return {
            "total_orders": len(self.order_history),
            "filled_orders": len(filled_orders),
            "long_orders": len(long_orders),
            "short_orders": len(short_orders),
            "total_fee": self.account.total_fee,
            "realized_pnl": self.account.realized_pnl,
            "unrealized_pnl": self.account.unrealized_pnl,
            "total_pnl": self.account.realized_pnl + self.account.unrealized_pnl,
            "roi": ((self.account.total_equity - self.initial_capital) / self.initial_capital) * 100
        }
