"""
智能订单路由系统 - 最优订单执行策略

功能：
1. 智能交易所选择
2. TWAP/VWAP/冰山订单等高级执行算法
3. 实时流动性分析和最优路径选择
4. 订单拆分和智能调度
5. 执行成本优化
"""

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    TWAP = "twap"           # 时间加权平均价格
    VWAP = "vwap"           # 成交量加权平均价格
    ICEBERG = "iceberg"     # 冰山订单
    SMART = "smart"         # 智能路由


class ExecutionStatus(Enum):
    """执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class ExchangeMetrics:
    """交易所指标"""
    exchange_id: str
    latency_ms: float
    fee_rate: float
    liquidity_score: float
    reliability_score: float
    last_updated: datetime = field(default_factory=datetime.now)
    
    @property
    def composite_score(self) -> float:
        """综合评分"""
        # 延迟越低越好，流动性越高越好，费用越低越好，可靠性越高越好
        latency_score = max(0, 100 - self.latency_ms)
        fee_score = max(0, 100 - self.fee_rate * 10000)
        return (latency_score * 0.3 + 
                self.liquidity_score * 0.3 + 
                fee_score * 0.2 + 
                self.reliability_score * 0.2)


@dataclass
class OrderSlice:
    """订单切片"""
    id: str
    parent_order_id: str
    exchange_id: str
    symbol: str
    side: str
    quantity: float
    price: Optional[float]
    order_type: OrderType
    scheduled_time: datetime
    status: ExecutionStatus = ExecutionStatus.PENDING
    executed_quantity: float = 0.0
    avg_price: float = 0.0


@dataclass
class ExecutionResult:
    """执行结果"""
    order_id: str
    success: bool
    executed_quantity: float
    avg_price: float
    total_fee: float
    execution_time_ms: float
    slices: List[OrderSlice] = field(default_factory=list)
    error_message: Optional[str] = None


class ExecutionAlgorithm(ABC):
    """执行算法基类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._running = False
    
    @abstractmethod
    async def execute(self, order: Dict[str, Any], 
                     exchanges: List[ExchangeMetrics]) -> ExecutionResult:
        """执行订单"""
        pass
    
    @abstractmethod
    def split_order(self, order: Dict[str, Any], 
                   exchanges: List[ExchangeMetrics]) -> List[OrderSlice]:
        """拆分订单"""
        pass


class TWAPAlgorithm(ExecutionAlgorithm):
    """TWAP算法 - 时间加权平均价格"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.num_slices = config.get("num_slices", 10)
        self.interval_seconds = config.get("interval_seconds", 60)
    
    def split_order(self, order: Dict[str, Any], 
                   exchanges: List[ExchangeMetrics]) -> List[OrderSlice]:
        """将订单拆分为时间切片"""
        total_quantity = order["quantity"]
        symbol = order["symbol"]
        side = order["side"]
        price = order.get("price")
        
        # 选择最佳交易所
        best_exchange = max(exchanges, key=lambda e: e.composite_score)
        
        # 计算每个切片的数量
        base_quantity = total_quantity / self.num_slices
        slices = []
        
        for i in range(self.num_slices):
            # 最后一个切片处理余数
            if i == self.num_slices - 1:
                quantity = total_quantity - sum(s.quantity for s in slices)
            else:
                quantity = base_quantity
            
            slice_order = OrderSlice(
                id=f"{order['id']}_slice_{i}",
                parent_order_id=order["id"],
                exchange_id=best_exchange.exchange_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                order_type=OrderType.TWAP,
                scheduled_time=datetime.now() + timedelta(seconds=i * self.interval_seconds)
            )
            slices.append(slice_order)
        
        return slices
    
    async def execute(self, order: Dict[str, Any], 
                     exchanges: List[ExchangeMetrics]) -> ExecutionResult:
        """执行TWAP订单"""
        start_time = time.time()
        slices = self.split_order(order, exchanges)
        
        total_executed = 0.0
        total_value = 0.0
        total_fee = 0.0
        
        for slice_order in slices:
            # 等待到预定时间
            wait_seconds = (slice_order.scheduled_time - datetime.now()).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            
            # 执行切片
            try:
                # 模拟执行（实际应调用交易所API）
                executed_qty = slice_order.quantity
                avg_price = slice_order.price or self._get_market_price(slice_order.symbol)
                fee = executed_qty * avg_price * 0.001  # 0.1% 手续费
                
                slice_order.executed_quantity = executed_qty
                slice_order.avg_price = avg_price
                slice_order.status = ExecutionStatus.COMPLETED
                
                total_executed += executed_qty
                total_value += executed_qty * avg_price
                total_fee += fee
                
            except Exception as e:
                logger.error(f"TWAP切片执行失败: {slice_order.id}, {e}")
                slice_order.status = ExecutionStatus.FAILED
        
        execution_time = (time.time() - start_time) * 1000
        avg_price = total_value / total_executed if total_executed > 0 else 0
        
        return ExecutionResult(
            order_id=order["id"],
            success=total_executed >= order["quantity"] * 0.95,  # 95%以上成交算成功
            executed_quantity=total_executed,
            avg_price=avg_price,
            total_fee=total_fee,
            execution_time_ms=execution_time,
            slices=slices
        )
    
    def _get_market_price(self, symbol: str) -> float:
        """获取市场价格（模拟）"""
        # 实际应从市场数据获取
        base_prices = {"BTC/USDT": 50000, "ETH/USDT": 3000}
        return base_prices.get(symbol, 100)


class VWAPAlgorithm(ExecutionAlgorithm):
    """VWAP算法 - 成交量加权平均价格"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.volume_profile = config.get("volume_profile", {})
        self.participation_rate = config.get("participation_rate", 0.1)  # 10%市场成交量
    
    def split_order(self, order: Dict[str, Any], 
                   exchanges: List[ExchangeMetrics]) -> List[OrderSlice]:
        """根据成交量分布拆分订单"""
        symbol = order["symbol"]
        total_quantity = order["quantity"]
        
        # 获取该交易对的成交量分布（按小时）
        profile = self.volume_profile.get(symbol, [1.0/24] * 24)
        
        slices = []
        best_exchange = max(exchanges, key=lambda e: e.composite_score)
        
        for hour, volume_ratio in enumerate(profile):
            if volume_ratio > 0.01:  # 只处理成交量占比>1%的时间段
                quantity = total_quantity * volume_ratio
                
                slice_order = OrderSlice(
                    id=f"{order['id']}_slice_{hour}",
                    parent_order_id=order["id"],
                    exchange_id=best_exchange.exchange_id,
                    symbol=symbol,
                    side=order["side"],
                    quantity=quantity,
                    price=order.get("price"),
                    order_type=OrderType.VWAP,
                    scheduled_time=datetime.now() + timedelta(hours=hour)
                )
                slices.append(slice_order)
        
        return slices
    
    async def execute(self, order: Dict[str, Any], 
                     exchanges: List[ExchangeMetrics]) -> ExecutionResult:
        """执行VWAP订单"""
        start_time = time.time()
        slices = self.split_order(order, exchanges)
        
        total_executed = 0.0
        total_value = 0.0
        total_fee = 0.0
        
        for slice_order in slices:
            # 等待到预定时间
            wait_seconds = (slice_order.scheduled_time - datetime.now()).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            
            # 执行切片
            try:
                executed_qty = slice_order.quantity
                avg_price = slice_order.price or self._get_market_price(slice_order.symbol)
                fee = executed_qty * avg_price * 0.001
                
                slice_order.executed_quantity = executed_qty
                slice_order.avg_price = avg_price
                slice_order.status = ExecutionStatus.COMPLETED
                
                total_executed += executed_qty
                total_value += executed_qty * avg_price
                total_fee += fee
                
            except Exception as e:
                logger.error(f"VWAP切片执行失败: {slice_order.id}, {e}")
                slice_order.status = ExecutionStatus.FAILED
        
        execution_time = (time.time() - start_time) * 1000
        avg_price = total_value / total_executed if total_executed > 0 else 0
        
        return ExecutionResult(
            order_id=order["id"],
            success=total_executed >= order["quantity"] * 0.95,
            executed_quantity=total_executed,
            avg_price=avg_price,
            total_fee=total_fee,
            execution_time_ms=execution_time,
            slices=slices
        )
    
    def _get_market_price(self, symbol: str) -> float:
        """获取市场价格"""
        base_prices = {"BTC/USDT": 50000, "ETH/USDT": 3000}
        return base_prices.get(symbol, 100)


class IcebergAlgorithm(ExecutionAlgorithm):
    """冰山订单算法"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.display_size = config.get("display_size", 0.1)  # 显示数量占比
        self.variance = config.get("variance", 0.2)  # 数量随机变化范围
    
    def split_order(self, order: Dict[str, Any], 
                   exchanges: List[ExchangeMetrics]) -> List[OrderSlice]:
        """将大单拆分为多个小单"""
        total_quantity = order["quantity"]
        symbol = order["symbol"]
        
        # 基础显示数量
        base_display = total_quantity * self.display_size
        
        slices = []
        remaining = total_quantity
        best_exchange = max(exchanges, key=lambda e: e.composite_score)
        
        slice_idx = 0
        while remaining > 0:
            # 添加随机变化
            variance = random.uniform(-self.variance, self.variance)
            display_qty = base_display * (1 + variance)
            
            # 确保不超过剩余数量
            quantity = min(display_qty, remaining)
            
            slice_order = OrderSlice(
                id=f"{order['id']}_iceberg_{slice_idx}",
                parent_order_id=order["id"],
                exchange_id=best_exchange.exchange_id,
                symbol=symbol,
                side=order["side"],
                quantity=quantity,
                price=order.get("price"),
                order_type=OrderType.ICEBERG,
                scheduled_time=datetime.now() + timedelta(seconds=slice_idx * 5)
            )
            slices.append(slice_order)
            
            remaining -= quantity
            slice_idx += 1
        
        return slices
    
    async def execute(self, order: Dict[str, Any], 
                     exchanges: List[ExchangeMetrics]) -> ExecutionResult:
        """执行冰山订单"""
        start_time = time.time()
        slices = self.split_order(order, exchanges)
        
        total_executed = 0.0
        total_value = 0.0
        total_fee = 0.0
        
        for slice_order in slices:
            # 冰山订单之间间隔较短
            wait_seconds = (slice_order.scheduled_time - datetime.now()).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            
            try:
                executed_qty = slice_order.quantity
                avg_price = slice_order.price or self._get_market_price(slice_order.symbol)
                fee = executed_qty * avg_price * 0.001
                
                slice_order.executed_quantity = executed_qty
                slice_order.avg_price = avg_price
                slice_order.status = ExecutionStatus.COMPLETED
                
                total_executed += executed_qty
                total_value += executed_qty * avg_price
                total_fee += fee
                
                # 模拟等待成交
                await asyncio.sleep(random.uniform(1, 3))
                
            except Exception as e:
                logger.error(f"冰山订单切片执行失败: {slice_order.id}, {e}")
                slice_order.status = ExecutionStatus.FAILED
        
        execution_time = (time.time() - start_time) * 1000
        avg_price = total_value / total_executed if total_executed > 0 else 0
        
        return ExecutionResult(
            order_id=order["id"],
            success=total_executed >= order["quantity"] * 0.95,
            executed_quantity=total_executed,
            avg_price=avg_price,
            total_fee=total_fee,
            execution_time_ms=execution_time,
            slices=slices
        )
    
    def _get_market_price(self, symbol: str) -> float:
        """获取市场价格"""
        base_prices = {"BTC/USDT": 50000, "ETH/USDT": 3000}
        return base_prices.get(symbol, 100)


class SmartOrderRouter:
    """智能订单路由器"""
    
    def __init__(self):
        self.exchanges: Dict[str, ExchangeMetrics] = {}
        self.algorithms: Dict[OrderType, ExecutionAlgorithm] = {}
        self._running = False
        self._initialized = False
        
        # 初始化默认算法
        self._init_default_algorithms()
    
    def _init_default_algorithms(self):
        """初始化默认算法"""
        self.algorithms[OrderType.TWAP] = TWAPAlgorithm({
            "num_slices": 10,
            "interval_seconds": 60
        })
        self.algorithms[OrderType.VWAP] = VWAPAlgorithm({
            "participation_rate": 0.1
        })
        self.algorithms[OrderType.ICEBERG] = IcebergAlgorithm({
            "display_size": 0.1,
            "variance": 0.2
        })
    
    async def initialize(self):
        """初始化路由器"""
        if self._initialized:
            return
        
        # 初始化交易所连接
        await self._init_exchanges()
        
        self._running = True
        self._initialized = True
        logger.info("智能订单路由器初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        self._running = False
        self._initialized = False
        logger.info("智能订单路由器清理完成")
    
    async def _init_exchanges(self):
        """初始化交易所连接"""
        # 模拟交易所数据
        self.exchanges = {
            "binance": ExchangeMetrics(
                exchange_id="binance",
                latency_ms=50,
                fee_rate=0.001,
                liquidity_score=95,
                reliability_score=98
            ),
            "okx": ExchangeMetrics(
                exchange_id="okx",
                latency_ms=80,
                fee_rate=0.0008,
                liquidity_score=88,
                reliability_score=95
            ),
            "bybit": ExchangeMetrics(
                exchange_id="bybit",
                latency_ms=60,
                fee_rate=0.001,
                liquidity_score=85,
                reliability_score=92
            )
        }
    
    def register_exchange(self, exchange_id: str, metrics: ExchangeMetrics):
        """注册交易所"""
        self.exchanges[exchange_id] = metrics
        logger.info(f"注册交易所: {exchange_id}")
    
    def register_algorithm(self, order_type: OrderType, algorithm: ExecutionAlgorithm):
        """注册执行算法"""
        self.algorithms[order_type] = algorithm
        logger.info(f"注册算法: {order_type.value}")
    
    async def route_order(self, order: Dict[str, Any]) -> ExecutionResult:
        """路由订单"""
        if not self._initialized:
            raise RuntimeError("路由器未初始化")
        
        order_type = OrderType(order.get("order_type", "market"))
        
        # 获取交易所列表
        exchanges = list(self.exchanges.values())
        
        if not exchanges:
            return ExecutionResult(
                order_id=order["id"],
                success=False,
                executed_quantity=0,
                avg_price=0,
                total_fee=0,
                execution_time_ms=0,
                error_message="没有可用的交易所"
            )
        
        # 选择执行算法
        if order_type in self.algorithms:
            algorithm = self.algorithms[order_type]
            return await algorithm.execute(order, exchanges)
        else:
            # 默认使用TWAP
            return await self.algorithms[OrderType.TWAP].execute(order, exchanges)
    
    def select_best_exchange(self, symbol: str, 
                            order_size: float) -> Optional[ExchangeMetrics]:
        """选择最佳交易所"""
        if not self.exchanges:
            return None
        
        # 根据综合评分选择
        best = max(self.exchanges.values(), key=lambda e: e.composite_score)
        return best
    
    def get_exchange_metrics(self, exchange_id: str) -> Optional[ExchangeMetrics]:
        """获取交易所指标"""
        return self.exchanges.get(exchange_id)
    
    def update_exchange_metrics(self, exchange_id: str, 
                               metrics: ExchangeMetrics):
        """更新交易所指标"""
        self.exchanges[exchange_id] = metrics
    
    async def get_optimal_path(self, order: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取最优执行路径"""
        symbol = order["symbol"]
        quantity = order["quantity"]
        
        # 选择最佳交易所
        best_exchange = self.select_best_exchange(symbol, quantity)
        
        if not best_exchange:
            return []
        
        # 返回最优路径
        return [{
            "exchange_id": best_exchange.exchange_id,
            "quantity": quantity,
            "expected_price": self._get_market_price(symbol),
            "expected_fee": quantity * self._get_market_price(symbol) * best_exchange.fee_rate
        }]
    
    def _get_market_price(self, symbol: str) -> float:
        """获取市场价格"""
        base_prices = {"BTC/USDT": 50000, "ETH/USDT": 3000}
        return base_prices.get(symbol, 100)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "exchanges": len(self.exchanges),
            "algorithms": len(self.algorithms),
            "exchange_scores": {
                eid: e.composite_score 
                for eid, e in self.exchanges.items()
            }
        }


# 使用示例
async def example_usage():
    """使用示例"""
    # 创建路由器
    router = SmartOrderRouter()
    await router.initialize()
    
    try:
        # 创建TWAP订单
        twap_order = {
            "id": "order_001",
            "symbol": "BTC/USDT",
            "side": "buy",
            "quantity": 1.0,
            "price": 50000,
            "order_type": "twap"
        }
        
        # 执行订单
        result = await router.route_order(twap_order)
        print(f"TWAP订单执行结果:")
        print(f"  成功: {result.success}")
        print(f"  成交数量: {result.executed_quantity}")
        print(f"  平均价格: {result.avg_price}")
        print(f"  手续费: {result.total_fee}")
        print(f"  切片数量: {len(result.slices)}")
        
        # 创建VWAP订单
        vwap_order = {
            "id": "order_002",
            "symbol": "ETH/USDT",
            "side": "sell",
            "quantity": 10.0,
            "order_type": "vwap"
        }
        
        result = await router.route_order(vwap_order)
        print(f"\nVWAP订单执行结果:")
        print(f"  成功: {result.success}")
        print(f"  成交数量: {result.executed_quantity}")
        
        # 创建冰山订单
        iceberg_order = {
            "id": "order_003",
            "symbol": "BTC/USDT",
            "side": "buy",
            "quantity": 5.0,
            "order_type": "iceberg"
        }
        
        result = await router.route_order(iceberg_order)
        print(f"\n冰山订单执行结果:")
        print(f"  成功: {result.success}")
        print(f"  切片数量: {len(result.slices)}")
        
        # 获取统计
        stats = router.get_stats()
        print(f"\n路由器统计: {stats}")
        
    finally:
        await router.cleanup()


if __name__ == "__main__":
    asyncio.run(example_usage())
