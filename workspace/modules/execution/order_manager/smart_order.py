#!/usr/bin/env python3
"""
智能订单管理系统
AI驱动的订单执行和风险管理
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class OrderType(Enum):
    """订单类型"""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LIMIT = "STOP_LIMIT"
    ICEBERG = "ICEBERG"  # 冰山订单
    TWAP = "TWAP"  # 时间加权平均价
    VWAP = "VWAP"  # 成交量加权平均价


class OrderStatus(Enum):
    """订单状态"""

    PENDING = "PENDING"  # 等待执行
    PARTIAL_FILLED = "PARTIAL_FILLED"  # 部分成交
    FILLED = "FILLED"  # 完全成交
    CANCELLED = "CANCELLED"  # 已取消
    REJECTED = "REJECTED"  # 被拒绝
    EXPIRED = "EXPIRED"  # 已过期


@dataclass
class Order:
    """订单信息"""

    order_id: str
    symbol: str
    order_type: OrderType
    side: str  # BUY/SELL
    quantity: float
    price: Optional[float] = None  # 限价单价格
    stop_price: Optional[float] = None  # 止损/止盈触发价
    time_in_force: str = "GTC"  # GTC, IOC, FOK
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = None
    updated_at: datetime = None
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    commission: float = 0.0
    client_order_id: str = None
    strategy_id: str = None  # 关联的策略ID
    parent_order_id: str = None  # 父订单ID（用于冰山订单等）

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = self.created_at

    @property
    def remaining_quantity(self) -> float:
        """剩余数量"""
        return self.quantity - self.filled_quantity

    @property
    def is_active(self) -> bool:
        """是否活跃"""
        return self.status in [OrderStatus.PENDING, OrderStatus.PARTIAL_FILLED]

    @property
    def is_completed(self) -> bool:
        """是否完成"""
        return self.status in [
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        ]


@dataclass
class ExecutionResult:
    """执行结果"""

    order_id: str
    status: OrderStatus
    filled_quantity: float
    avg_fill_price: float
    commission: float
    execution_time: datetime
    slippage: float = 0.0  # 滑点
    market_impact: float = 0.0  # 市场影响
    execution_quality: float = 1.0  # 执行质量评分


class SmartOrderManager:
    """智能订单管理器"""

    def __init__(self, exchange_adapter, config_manager):
        self.exchange = exchange_adapter
        self.config = config_manager
        self.active_orders: Dict[str, Order] = {}
        self.order_history: List[Order] = []
        self.execution_stats = {}

        # 智能执行参数
        self.execution_strategies = {
            "aggressive": self._execute_aggressive,
            "passive": self._execute_passive,
            "adaptive": self._execute_adaptive,
            "stealth": self._execute_stealth,  # 隐蔽执行
        }

        # 监控任务
        self.monitoring_task = None

    def generate_order_id(self, prefix: str = "ORD") -> str:
        """生成订单ID"""
        timestamp = int(time.time() * 1000)
        random_str = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        return f"{prefix}_{timestamp}_{random_str}"

    async def create_order(self, signal: Dict, portfolio: Dict = None) -> Optional[Order]:
        """创建智能订单"""

        try:
            # 验证信号
            if not self._validate_signal(signal):
                print("信号验证失败")
                return None

            # 计算订单参数
            order_params = self._calculate_order_parameters(signal, portfolio)

            # 选择执行策略
            execution_strategy = self._select_execution_strategy(order_params, signal)

            # 创建订单对象
            order = Order(
                order_id=self.generate_order_id(),
                symbol=order_params["symbol"],
                order_type=self._select_order_type(order_params, signal),
                side=order_params["side"],
                quantity=order_params["quantity"],
                price=order_params.get("price"),
                stop_price=order_params.get("stop_price"),
                time_in_force=order_params.get("time_in_force", "GTC"),
                strategy_id=signal.get("strategy_id", "default"),
                client_order_id=signal.get("client_order_id"),
            )

            # 添加到活跃订单
            self.active_orders[order.order_id] = order

            # 异步执行订单
            asyncio.create_task(self._execute_order(order, execution_strategy, signal))

            return order

        except Exception as e:
            print(f"创建订单失败: {e}")
            return None

    def _validate_signal(self, signal: Dict) -> bool:
        """验证交易信号"""

        required_fields = ["symbol", "side", "quantity"]
        for field in required_fields:
            if field not in signal:
                print(f"信号缺少必要字段: {field}")
                return False

        # 验证数量
        if signal["quantity"] <= 0:
            print("订单数量必须大于0")
            return False

        # 验证价格（如果提供）
        if "price" in signal and signal["price"] <= 0:
            print("订单价格必须大于0")
            return False

        return True

    def _calculate_order_parameters(self, signal: Dict, portfolio: Dict = None) -> Dict:
        """计算订单参数"""

        symbol = signal["symbol"]
        side = signal["side"]
        base_quantity = signal["quantity"]

        # 获取当前市场数据
        current_price = self._get_current_price(symbol)
        order_book = self._get_order_book(symbol)

        # 计算智能订单数量（考虑市场深度）
        smart_quantity = self._calculate_smart_quantity(
            base_quantity, side, order_book, current_price
        )

        # 计算智能价格
        smart_price = self._calculate_smart_price(side, current_price, order_book, smart_quantity)

        # 风险管理检查
        risk_params = self._apply_risk_management(smart_quantity, smart_price, portfolio)

        # 构建订单参数
        order_params = {
            "symbol": symbol,
            "side": side,
            "quantity": risk_params["approved_quantity"],
            "price": smart_price if signal.get("order_type") == "LIMIT" else None,
            "stop_price": signal.get("stop_price"),
            "time_in_force": signal.get("time_in_force", "GTC"),
            "max_slippage": signal.get("max_slippage", 0.01),
            "urgency": signal.get("urgency", "normal"),  # urgent, normal, patient
        }

        return order_params

    def _get_current_price(self, symbol: str) -> float:
        """获取当前价格"""
        # 这里应该调用数据模块
        # 暂时返回模拟数据
        return 50000.0  # 模拟BTC价格

    def _get_order_book(self, symbol: str, depth: int = 20) -> Dict:
        """获取订单簿"""
        # 这里应该调用数据模块
        # 暂时返回模拟数据
        return {
            "bids": [(49999, 1.5), (49998, 2.0), (49997, 3.0)],
            "asks": [(50001, 1.2), (50002, 1.8), (50003, 2.5)],
        }

    def _calculate_smart_quantity(
        self, base_quantity: float, side: str, order_book: Dict, current_price: float
    ) -> float:
        """计算智能订单数量"""

        if side == "BUY":
            depth_data = order_book["asks"]
        else:  # SELL
            depth_data = order_book["bids"]

        # 计算市场深度能承受的数量
        available_quantity = 0
        for price, quantity in depth_data[:10]:  # 前10档
            available_quantity += quantity

        # 智能调整：不超过市场深度的30%
        smart_quantity = min(base_quantity, available_quantity * 0.3)

        # 最小化市场影响
        market_impact = smart_quantity / available_quantity
        if market_impact > 0.1:  # 市场影响超过10%
            smart_quantity *= 0.5  # 减半执行

        return smart_quantity

    def _calculate_smart_price(
        self, side: str, current_price: float, order_book: Dict, quantity: float
    ) -> Optional[float]:
        """计算智能订单价格"""

        if side == "BUY":
            # 买单：尽量低价买入
            target_price = current_price * 0.995  # 低于市价0.5%

            # 检查订单簿深度
            for price, qty in order_book["bids"]:
                if price >= target_price and qty >= quantity * 0.5:
                    # 有足够流动性，可以更激进
                    target_price = price * 1.001  # 略高于最佳买价
                    break
        else:  # SELL
            # 卖单：尽量高价卖出
            target_price = current_price * 1.005  # 高于市价0.5%

            # 检查订单簿深度
            for price, qty in order_book["asks"]:
                if price <= target_price and qty >= quantity * 0.5:
                    # 有足够流动性，可以更激进
                    target_price = price * 0.999  # 略低于最佳卖价
                    break

        return target_price

    def _apply_risk_management(self, quantity: float, price: float, portfolio: Dict = None) -> Dict:
        """应用风险管理"""

        if not portfolio:
            portfolio = {
                "total_capital": 10000,
                "current_positions": {},
                "max_position_percent": 0.3,
            }

        # 计算订单价值
        order_value = quantity * price

        # 检查是否超过最大仓位
        max_position_value = portfolio["total_capital"] * portfolio["max_position_percent"]

        # 计算当前仓位价值
        current_position_value = sum(
            pos["quantity"] * pos["avg_price"] for pos in portfolio["current_positions"].values()
        )

        # 检查新订单是否会超过限制
        if current_position_value + order_value > max_position_value:
            # 调整订单数量
            allowed_additional = max_position_value - current_position_value
            if allowed_additional <= 0:
                approved_quantity = 0
            else:
                approved_quantity = min(quantity, allowed_additional / price)
        else:
            approved_quantity = quantity

        return {
            "approved_quantity": approved_quantity,
            "original_quantity": quantity,
            "adjustment_reason": "risk_management" if approved_quantity < quantity else None,
        }

    def _select_order_type(self, order_params: Dict, signal: Dict) -> OrderType:
        """选择订单类型"""

        urgency = order_params.get("urgency", "normal")

        if urgency == "urgent":
            return OrderType.MARKET
        elif "stop_price" in order_params:
            if order_params.get("price"):
                return OrderType.STOP_LIMIT
            else:
                return OrderType.STOP_LOSS
        elif signal.get("iceberg", False):
            return OrderType.ICEBERG
        elif signal.get("twap", False):
            return OrderType.TWAP
        else:
            return OrderType.LIMIT

    def _select_execution_strategy(self, order_params: Dict, signal: Dict):
        """选择执行策略"""

        urgency = order_params.get("urgency", "normal")
        quantity = order_params["quantity"]

        # 根据订单大小和紧急程度选择策略
        if urgency == "urgent":
            return self.execution_strategies["aggressive"]
        elif quantity > 10:  # 大单
            return self.execution_strategies["stealth"]
        elif quantity < 1:  # 小单
            return self.execution_strategies["passive"]
        else:
            return self.execution_strategies["adaptive"]

    async def _execute_order(self, order: Order, execution_strategy, signal: Dict):
        """执行订单"""

        try:
            # 记录开始时间
            start_time = time.time()

            # 调用执行策略
            execution_result = await execution_strategy(order, signal)

            # 更新订单状态
            order.status = execution_result.status
            order.filled_quantity = execution_result.filled_quantity
            order.avg_fill_price = execution_result.avg_fill_price
            order.commission = execution_result.commission
            order.updated_at = datetime.now()

            # 计算执行质量
            execution_time = time.time() - start_time
            execution_quality = self._calculate_execution_quality(
                execution_result, execution_time, signal
            )

            # 记录执行统计
            self._record_execution_stats(order, execution_result, execution_quality)

            # 如果订单完成，从活跃订单移除
            if order.is_completed:
                self.active_orders.pop(order.order_id, None)
                self.order_history.append(order)

            # 触发执行完成事件
            await self._on_order_executed(order, execution_result, execution_quality)

        except Exception as e:
            print(f"订单执行失败: {e}")
            order.status = OrderStatus.REJECTED
            order.updated_at = datetime.now()

    async def _execute_aggressive(self, order: Order, signal: Dict) -> ExecutionResult:
        """激进执行策略"""

        # 立即以市价执行
        try:
            # 调用交易所API
            exchange_result = await self.exchange.create_market_order(
                symbol=order.symbol, side=order.side, quantity=order.quantity
            )

            return ExecutionResult(
                order_id=order.order_id,
                status=OrderStatus.FILLED,
                filled_quantity=exchange_result["filled_qty"],
                avg_fill_price=exchange_result["avg_price"],
                commission=exchange_result.get("commission", 0.0),
                execution_time=datetime.now(),
                slippage=exchange_result.get("slippage", 0.0),
            )

        except Exception as e:
            print(f"激进执行失败: {e}")
            return ExecutionResult(
                order_id=order.order_id,
                status=OrderStatus.REJECTED,
                filled_quantity=0.0,
                avg_fill_price=0.0,
                commission=0.0,
                execution_time=datetime.now(),
            )

    async def _execute_passive(self, order: Order, signal: Dict) -> ExecutionResult:
        """被动执行策略"""

        # 挂限价单等待成交
        try:
            # 调用交易所API
            exchange_result = await self.exchange.create_limit_order(
                symbol=order.symbol, side=order.side, quantity=order.quantity, price=order.price
            )

            # 启动监控任务
            asyncio.create_task(
                self._monitor_passive_order(order.order_id, exchange_result["order_id"])
            )

            return ExecutionResult(
                order_id=order.order_id,
                status=OrderStatus.PENDING,
                filled_quantity=0.0,
                avg_fill_price=0.0,
                commission=0.0,
                execution_time=datetime.now(),
            )

        except Exception as e:
            print(f"被动执行失败: {e}")
            return ExecutionResult(
                order_id=order.order_id,
                status=OrderStatus.REJECTED,
                filled_quantity=0.0,
                avg_fill_price=0.0,
                commission=0.0,
                execution_time=datetime.now(),
            )

    async def _execute_adaptive(self, order: Order, signal: Dict) -> ExecutionResult:
        """自适应执行策略"""

        # 根据市场情况动态调整
        market_conditions = await self._analyze_market_conditions(order.symbol)

        if market_conditions["volatility"] > 0.05:
            # 高波动市场，使用激进策略
            return await self._execute_aggressive(order, signal)
        elif market_conditions["liquidity"] < order.quantity * 10:
            # 流动性不足，使用被动策略
            return await self._execute_passive(order, signal)
        else:
            # 正常市场，使用TWAP策略
            return await self._execute_twap(order, signal)

    async def _execute_stealth(self, order: Order, signal: Dict) -> ExecutionResult:
        """隐蔽执行策略（冰山订单）"""

        # 将大单拆分成多个小单
        chunk_size = self._calculate_chunk_size(order.quantity, order.symbol)
        num_chunks = int(np.ceil(order.quantity / chunk_size))

        # 创建父订单记录
        parent_order = order
        parent_order.order_type = OrderType.ICEBERG

        # 分批执行
        for i in range(num_chunks):
            chunk_qty = min(chunk_size, parent_order.remaining_quantity)

            if chunk_qty <= 0:
                break

            # 创建子订单
            child_order = Order(
                order_id=self.generate_order_id(f"ICE_{i}"),
                symbol=parent_order.symbol,
                order_type=OrderType.LIMIT,
                side=parent_order.side,
                quantity=chunk_qty,
                price=parent_order.price,
                parent_order_id=parent_order.order_id,
                strategy_id=parent_order.strategy_id,
            )

            # 执行子订单
            await self._execute_passive(child_order, signal)

            # 等待一段时间再执行下一单
            await asyncio.sleep(np.random.uniform(5, 15))  # 随机间隔

        return ExecutionResult(
            order_id=parent_order.order_id,
            status=OrderStatus.PARTIAL_FILLED,
            filled_quantity=0.0,  # 实际成交在子订单中
            avg_fill_price=0.0,
            commission=0.0,
            execution_time=datetime.now(),
        )

    async def _execute_twap(self, order: Order, signal: Dict) -> ExecutionResult:
        """TWAP执行策略"""

        # 在指定时间窗口内均匀执行
        time_window = signal.get("twap_window", 300)  # 默认5分钟
        num_slices = signal.get("twap_slices", 10)

        slice_quantity = order.quantity / num_slices
        slice_interval = time_window / num_slices

        # 创建父订单记录
        parent_order = order
        parent_order.order_type = OrderType.TWAP

        # 分片执行
        for i in range(num_slices):
            # 创建子订单
            child_order = Order(
                order_id=self.generate_order_id(f"TWAP_{i}"),
                symbol=parent_order.symbol,
                order_type=OrderType.MARKET,  # TWAP通常用市价单
                side=parent_order.side,
                quantity=slice_quantity,
                parent_order_id=parent_order.order_id,
                strategy_id=parent_order.strategy_id,
            )

            # 执行子订单
            await self._execute_aggressive(child_order, signal)

            # 等待下一个时间片
            if i < num_slices - 1:
                await asyncio.sleep(slice_interval)

        return ExecutionResult(
            order_id=parent_order.order_id,
            status=OrderStatus.FILLED,
            filled_quantity=order.quantity,
            avg_fill_price=0.0,  # 实际平均价在子订单中计算
            commission=0.0,
            execution_time=datetime.now(),
        )

    def _calculate_chunk_size(self, total_quantity: float, symbol: str) -> float:
        """计算冰山订单的块大小"""

        # 根据市场深度和订单大小计算
        order_book = self._get_order_book(symbol)
        avg_depth = np.mean([qty for _, qty in order_book["bids"][:5] + order_book["asks"][:5]])

        # 块大小不超过平均深度的20%
        chunk_size = avg_depth * 0.2

        # 确保至少分成3块
        max_chunk_size = total_quantity / 3

        return min(chunk_size, max_chunk_size)

    async def _analyze_market_conditions(self, symbol: str) -> Dict:
        """分析市场条件"""

        # 这里应该调用数据模块进行详细分析
        # 暂时返回模拟数据
        return {
            "volatility": np.random.uniform(0.01, 0.1),
            "liquidity": np.random.uniform(100, 1000),
            "spread": np.random.uniform(0.0001, 0.001),
            "momentum": np.random.uniform(-0.1, 0.1),
        }

    async def _monitor_passive_order(self, internal_order_id: str, exchange_order_id: str):
        """监控被动订单"""

        while True:
            try:
                # 查询订单状态
                order_status = await self.exchange.get_order_status(exchange_order_id)

                if order_status["status"] in ["filled", "canceled", "expired"]:
                    # 订单完成，更新本地订单
                    if internal_order_id in self.active_orders:
                        order = self.active_orders[internal_order_id]
                        order.status = (
                            OrderStatus.FILLED
                            if order_status["status"] == "filled"
                            else OrderStatus.CANCELLED
                        )
                        order.filled_quantity = order_status["filled_qty"]
                        order.avg_fill_price = order_status["avg_price"]
                        order.updated_at = datetime.now()

                    break

                # 等待一段时间再检查
                await asyncio.sleep(5)

            except Exception as e:
                print(f"订单监控失败: {e}")
                await asyncio.sleep(10)

    def _calculate_execution_quality(
        self, execution_result: ExecutionResult, execution_time: float, signal: Dict
    ) -> float:
        """计算执行质量"""

        quality_score = 1.0

        # 滑点惩罚
        max_slippage = signal.get("max_slippage", 0.01)
        if execution_result.slippage > max_slippage:
            penalty = (execution_result.slippage - max_slippage) / max_slippage
            quality_score -= min(0.5, penalty * 0.5)

        # 执行时间惩罚（如果提供了时间要求）
        if "max_execution_time" in signal:
            if execution_time > signal["max_execution_time"]:
                penalty = (execution_time - signal["max_execution_time"]) / signal[
                    "max_execution_time"
                ]
                quality_score -= min(0.3, penalty * 0.3)

        # 市场影响惩罚
        if execution_result.market_impact > 0.1:
            penalty = execution_result.market_impact * 2
            quality_score -= min(0.4, penalty)

        return max(0.0, min(1.0, quality_score))

    def _record_execution_stats(
        self, order: Order, execution_result: ExecutionResult, execution_quality: float
    ):
        """记录执行统计"""

        symbol = order.symbol
        if symbol not in self.execution_stats:
            self.execution_stats[symbol] = {
                "total_orders": 0,
                "filled_orders": 0,
                "total_quantity": 0.0,
                "avg_slippage": 0.0,
                "avg_execution_time": 0.0,
                "avg_execution_quality": 0.0,
            }

        stats = self.execution_stats[symbol]
        stats["total_orders"] += 1

        if execution_result.status == OrderStatus.FILLED:
            stats["filled_orders"] += 1
            stats["total_quantity"] += execution_result.filled_quantity

        # 更新滑动平均值
        n = stats["filled_orders"]
        if n > 0:
            stats["avg_slippage"] = (
                stats["avg_slippage"] * (n - 1) + execution_result.slippage
            ) / n
            stats["avg_execution_quality"] = (
                stats["avg_execution_quality"] * (n - 1) + execution_quality
            ) / n

    async def _on_order_executed(
        self, order: Order, execution_result: ExecutionResult, execution_quality: float
    ):
        """订单执行完成事件"""

        # 这里可以触发各种回调，比如：
        # 1. 通知监控系统
        # 2. 更新学习模型
        # 3. 发送通知
        # 4. 记录到数据库

        print(f"订单执行完成: {order.order_id}, 质量: {execution_quality:.2f}")

    async def cancel_order(self, order_id: str) -> bool:
        """取消订单"""

        if order_id not in self.active_orders:
            print(f"订单不存在: {order_id}")
            return False

        order = self.active_orders[order_id]

        try:
            # 调用交易所API取消订单
            await self.exchange.cancel_order(order.symbol, order.client_order_id)

            # 更新订单状态
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.now()

            # 从活跃订单移除
            self.active_orders.pop(order_id)
            self.order_history.append(order)

            return True

        except Exception as e:
            print(f"取消订单失败: {e}")
            return False

    def get_order_status(self, order_id: str) -> Optional[Order]:
        """获取订单状态"""
        return self.active_orders.get(order_id)

    def get_active_orders(self, symbol: str = None) -> List[Order]:
        """获取活跃订单"""
        if symbol:
            return [
                order
                for order in self.active_orders.values()
                if order.symbol == symbol and order.is_active
            ]
        else:
            return [order for order in self.active_orders.values() if order.is_active]

    def get_order_history(self, symbol: str = None, limit: int = 100) -> List[Order]:
        """获取订单历史"""
        if symbol:
            filtered = [order for order in self.order_history if order.symbol == symbol]
        else:
            filtered = self.order_history

        return filtered[-limit:]  # 返回最近的订单

    def get_execution_stats(self, symbol: str = None) -> Dict:
        """获取执行统计"""
        if symbol:
            return self.execution_stats.get(symbol, {})
        else:
            return self.execution_stats


# 单例实例
_order_manager = None


def get_order_manager(exchange_adapter=None, config_manager=None) -> SmartOrderManager:
    """获取订单管理器单例"""
    global _order_manager
    if _order_manager is None:
        # 这里需要传入实际的exchange_adapter和config_manager
        from ...core.config_manager import get_config_manager

        config = config_manager or get_config_manager()
        _order_manager = SmartOrderManager(exchange_adapter, config)
    return _order_manager
