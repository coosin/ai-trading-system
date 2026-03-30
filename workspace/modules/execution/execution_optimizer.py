#!/usr/bin/env python3
"""
执行优化器
智能订单拆分、执行时机选择、成本优化
"""

import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
import math
from collections import deque
import warnings
warnings.filterwarnings('ignore')

@dataclass
class MarketState:
    """市场状态"""
    timestamp: datetime
    symbol: str
    bid_price: float
    ask_price: float
    bid_size: float
    ask_size: float
    spread: float
    mid_price: float
    volume_24h: float
    volatility: float
    order_book_depth: Dict[str, float]  # 不同价格深度的挂单量
    
    def __post_init__(self):
        self.spread = self.ask_price - self.bid_price
        self.mid_price = (self.bid_price + self.ask_price) / 2

@dataclass
class ExecutionPlan:
    """执行计划"""
    plan_id: str
    symbol: str
    total_quantity: float
    order_type: str  # 'MARKET', 'LIMIT', 'TWAP', 'VWAP', 'ICEBERG', 'PEGGED'
    
    # 拆分详情
    child_orders: List[Dict] = field(default_factory=list)
    estimated_cost: float = 0.0
    estimated_slippage: float = 0.0
    estimated_completion_time: datetime = None
    confidence_score: float = 0.0
    
    # 风险指标
    market_impact: float = 0.0
    liquidity_risk: float = 0.0
    timing_risk: float = 0.0
    
    def add_child_order(self, order: Dict):
        """添加子订单"""
        self.child_orders.append(order)
    
    def calculate_metrics(self, market_state: MarketState):
        """计算执行指标"""
        
        if not self.child_orders:
            return
        
        # 估算执行成本
        total_cost = 0.0
        total_slippage = 0.0
        
        for order in self.child_orders:
            if order['order_type'] == 'MARKET':
                # 市价单的成本估算
                if order['side'] == 'BUY':
                    # 以卖一价成交
                    execution_price = market_state.ask_price
                    slippage = (execution_price - market_state.mid_price) / market_state.mid_price
                else:
                    # 以买一价成交
                    execution_price = market_state.bid_price
                    slippage = (market_state.mid_price - execution_price) / market_state.mid_price
                
                order['estimated_price'] = execution_price
                order['estimated_slippage'] = slippage
                
                total_slippage += slippage * order['quantity'] * execution_price
                
            elif order['order_type'] == 'LIMIT':
                # 限价单的成本估算
                if order['side'] == 'BUY' and order['price'] >= market_state.ask_price:
                    # 可以立即成交
                    execution_price = order['price']
                    slippage = (execution_price - market_state.mid_price) / market_state.mid_price
                elif order['side'] == 'SELL' and order['price'] <= market_state.bid_price:
                    # 可以立即成交
                    execution_price = order['price']
                    slippage = (market_state.mid_price - execution_price) / market_state.mid_price
                else:
                    # 挂单等待
                    execution_price = order['price']
                    slippage = 0.0
                
                order['estimated_price'] = execution_price
                order['estimated_slippage'] = slippage
            
            # 计算市场冲击
            order_size_ratio = order['quantity'] / market_state.volume_24h
            market_impact_factor = min(0.1, order_size_ratio * 10)  # 简化模型
            order['market_impact'] = market_impact_factor
        
        # 汇总指标
        self.estimated_slippage = total_slippage / (self.total_quantity * market_state.mid_price) if self.total_quantity > 0 else 0.0
        self.market_impact = sum(order.get('market_impact', 0) for order in self.child_orders) / len(self.child_orders) if self.child_orders else 0.0

@dataclass
class ExecutionResult:
    """执行结果"""
    plan_id: str
    symbol: str
    start_time: datetime
    end_time: datetime
    total_quantity: float
    executed_quantity: float
    average_price: float
    total_cost: float
    total_slippage: float
    actual_market_impact: float
    completion_rate: float
    execution_quality_score: float
    
    # 详细结果
    order_results: List[Dict] = field(default_factory=list)
    
    def calculate_quality_score(self) -> float:
        """计算执行质量分数"""
        
        # 完成率权重
        completion_score = self.completion_rate * 100
        
        # 成本效率（越低越好）
        if self.total_cost > 0:
            cost_score = max(0, 100 - (self.total_cost / self.total_quantity / self.average_price * 10000))
        else:
            cost_score = 100
        
        # 滑点效率
        if self.total_slippage > 0:
            slippage_score = max(0, 100 - (abs(self.total_slippage) * 100))
        else:
            slippage_score = 100
        
        # 执行速度（越快越好）
        execution_time = (self.end_time - self.start_time).total_seconds()
        if execution_time > 0:
            speed_score = max(0, 100 - (execution_time / 3600 * 10))  # 每小时减10分
        else:
            speed_score = 100
        
        # 综合分数
        weights = {
            'completion': 0.3,
            'cost': 0.3,
            'slippage': 0.2,
            'speed': 0.2
        }
        
        self.execution_quality_score = (
            completion_score * weights['completion'] +
            cost_score * weights['cost'] +
            slippage_score * weights['slippage'] +
            speed_score * weights['speed']
        )
        
        return self.execution_quality_score

class ExecutionOptimizer:
    """执行优化器"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        
        # 市场状态历史
        self.market_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # 执行历史
        self.execution_history: List[ExecutionResult] = []
        
        # 优化算法
        self.optimization_algorithms = {
            'twap': self._optimize_twap,
            'vwap': self._optimize_vwap,
            'iceberg': self._optimize_iceberg,
            'adaptive': self._optimize_adaptive,
            'stealth': self._optimize_stealth
        }
        
        # 配置
        self.config = {
            'min_order_size': 0.001,  # 最小订单大小
            'max_order_size': 100.0,  # 最大订单大小
            'max_slippage_percent': 1.0,
            'max_market_impact_percent': 5.0,
            'default_time_horizon_minutes': 60,
            'volume_participation_rate': 0.1,  # 成交量参与率
            'aggressiveness_level': 'medium',  # low, medium, high
            'enable_learning': True
        }
        
        # 学习模型
        self.learning_model = ExecutionLearningModel()
        
        # 加载配置
        if config_manager:
            self._load_config()
    
    def _load_config(self):
        """加载配置"""
        
        execution_config = self.config_manager.get_config('execution', 'optimization', {})
        
        if execution_config:
            self.config.update({
                'min_order_size': execution_config.get('min_order_size', 0.001),
                'max_order_size': execution_config.get('max_order_size', 100.0),
                'max_slippage_percent': execution_config.get('max_slippage_percent', 1.0),
                'max_market_impact_percent': execution_config.get('max_market_impact_percent', 5.0),
                'default_time_horizon_minutes': execution_config.get('default_time_horizon_minutes', 60),
                'volume_participation_rate': execution_config.get('volume_participation_rate', 0.1),
                'aggressiveness_level': execution_config.get('aggressiveness_level', 'medium'),
                'enable_learning': execution_config.get('enable_learning', True)
            })
    
    def update_market_state(self, market_state: MarketState):
        """更新市场状态"""
        
        self.market_history[market_state.symbol].append(market_state)
    
    async def create_execution_plan(self, order_request: Dict) -> ExecutionPlan:
        """创建执行计划"""
        
        symbol = order_request.get('symbol', 'BTCUSDT')
        side = order_request.get('side', 'BUY')
        quantity = order_request.get('quantity', 0.0)
        order_type = order_request.get('order_type', 'ADAPTIVE')
        urgency = order_request.get('urgency', 'normal')  # low, normal, high, urgent
        
        if quantity <= 0:
            raise ValueError("订单数量必须大于0")
        
        print(f"📋 创建执行计划: {symbol} {side} {quantity:.4f} {order_type}")
        
        # 获取当前市场状态
        current_market = self._get_current_market_state(symbol)
        if not current_market:
            raise ValueError(f"无法获取 {symbol} 的市场状态")
        
        # 选择合适的优化算法
        optimization_algorithm = self._select_optimization_algorithm(
            order_type, urgency, quantity, current_market
        )
        
        # 创建执行计划
        plan_id = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{symbol}"
        
        plan = ExecutionPlan(
            plan_id=plan_id,
            symbol=symbol,
            total_quantity=quantity,
            order_type=optimization_algorithm
        )
        
        # 执行优化
        if optimization_algorithm in self.optimization_algorithms:
            optimizer = self.optimization_algorithms[optimization_algorithm]
            child_orders = await optimizer(symbol, side, quantity, current_market, urgency)
            
            for order in child_orders:
                plan.add_child_order(order)
        else:
            # 默认使用自适应执行
            child_orders = await self._optimize_adaptive(symbol, side, quantity, current_market, urgency)
            for order in child_orders:
                plan.add_child_order(order)
        
        # 计算执行指标
        plan.calculate_metrics(current_market)
        
        # 应用学习模型建议
        if self.config['enable_learning']:
            plan = await self._apply_learning_suggestions(plan, current_market)
        
        # 计算置信度分数
        plan.confidence_score = self._calculate_confidence_score(plan, current_market)
        
        print(f"✅ 执行计划创建完成: {plan.plan_id}")
        print(f"   拆分订单: {len(plan.child_orders)} 个")
        print(f"   预估滑点: {plan.estimated_slippage:.4%}")
        print(f"   市场冲击: {plan.market_impact:.4%}")
        print(f"   置信度: {plan.confidence_score:.2%}")
        
        return plan
    
    def _get_current_market_state(self, symbol: str) -> Optional[MarketState]:
        """获取当前市场状态"""
        
        if symbol in self.market_history and self.market_history[symbol]:
            return self.market_history[symbol][-1]
        
        # 如果没有历史数据，创建模拟数据
        return self._create_mock_market_state(symbol)
    
    def _create_mock_market_state(self, symbol: str) -> MarketState:
        """创建模拟市场状态"""
        
        # 模拟价格
        base_price = 50000.0 if 'BTC' in symbol else 3000.0
        
        return MarketState(
            timestamp=datetime.now(),
            symbol=symbol,
            bid_price=base_price * 0.999,
            ask_price=base_price * 1.001,
            bid_size=10.0,
            ask_size=10.0,
            spread=base_price * 0.002,
            mid_price=base_price,
            volume_24h=1000000.0,
            volatility=0.02,
            order_book_depth={
                'bid_0.1%': 5.0,
                'bid_0.5%': 20.0,
                'bid_1.0%': 50.0,
                'ask_0.1%': 5.0,
                'ask_0.5%': 20.0,
                'ask_1.0%': 50.0
            }
        )
    
    def _select_optimization_algorithm(self, order_type: str, urgency: str, 
                                      quantity: float, market_state: MarketState) -> str:
        """选择优化算法"""
        
        if order_type != 'ADAPTIVE':
            return order_type.lower()
        
        # 根据紧急程度和数量选择算法
        order_size_ratio = quantity / market_state.volume_24h
        
        if urgency == 'urgent':
            return 'adaptive'  # 最激进的执行
        
        elif urgency == 'high':
            if order_size_ratio > 0.01:  # 大于1%的日成交量
                return 'iceberg'  # 冰山订单
            else:
                return 'adaptive'
        
        elif urgency == 'normal':
            if order_size_ratio > 0.001:  # 大于0.1%的日成交量
                return 'twap'  # 时间加权
            else:
                return 'vwap'  # 成交量加权
        
        elif urgency == 'low':
            if order_size_ratio > 0.0001:  # 大于0.01%的日成交量
                return 'stealth'  # 隐蔽执行
            else:
                return 'limit'  # 限价单
        
        return 'adaptive'  # 默认
    
    async def _optimize_twap(self, symbol: str, side: str, quantity: float,
                           market_state: MarketState, urgency: str) -> List[Dict]:
        """TWAP（时间加权平均价格）优化"""
        
        print(f"   🕐 使用TWAP算法优化执行")
        
        # 确定时间窗口
        time_horizon_minutes = self._get_time_horizon(urgency)
        
        # 确定拆分数
        n_orders = self._calculate_order_count(quantity, market_state, urgency)
        
        # 创建子订单
        orders = []
        order_quantity = quantity / n_orders
        
        for i in range(n_orders):
            # 计算执行时间
            execute_after_minutes = (i * time_horizon_minutes) / n_orders
            
            order = {
                'order_id': f"{symbol}_twap_{i+1}_{n_orders}",
                'symbol': symbol,
                'side': side,
                'quantity': order_quantity,
                'order_type': 'LIMIT',
                'time_in_force': 'GTC',
                'execute_after_minutes': execute_after_minutes,
                'strategy': 'TWAP',
                'notes': f"TWAP订单 {i+1}/{n_orders}"
            }
            
            # 确定限价
            if side == 'BUY':
                # 买单价略低于当前买一价
                order['price'] = market_state.bid_price * (1 - 0.0005)  # 0.05%折扣
            else:
                # 卖单价略高于当前卖一价
                order['price'] = market_state.ask_price * (1 + 0.0005)  # 0.05%溢价
            
            orders.append(order)
        
        return orders
    
    async def _optimize_vwap(self, symbol: str, side: str, quantity: float,
                           market_state: MarketState, urgency: str) -> List[Dict]:
        """VWAP（成交量加权平均价格）优化"""
        
        print(f"   📊 使用VWAP算法优化执行")
        
        # 获取历史成交量模式
        volume_pattern = self._get_volume_pattern(symbol)
        
        # 确定时间窗口
        time_horizon_minutes = self._get_time_horizon(urgency)
        
        # 根据成交量模式分配订单
        orders = []
        remaining_quantity = quantity
        
        # 将时间窗口分成若干时段
        time_slots = 12  # 每5分钟一个时段
        time_slot_minutes = time_horizon_minutes / time_slots
        
        for slot in range(time_slots):
            # 计算该时段的成交量比例
            volume_ratio = volume_pattern.get(slot, 1.0 / time_slots)
            
            # 分配数量
            slot_quantity = quantity * volume_ratio
            
            if slot_quantity < self.config['min_order_size']:
                continue
            
            order = {
                'order_id': f"{symbol}_vwap_slot_{slot+1}",
                'symbol': symbol,
                'side': side,
                'quantity': slot_quantity,
                'order_type': 'LIMIT',
                'time_in_force': 'GTC',
                'execute_after_minutes': slot * time_slot_minutes,
                'strategy': 'VWAP',
                'notes': f"VWAP时段 {slot+1}/{time_slots}, 成交量比例: {volume_ratio:.2%}"
            }
            
            # 确定限价（根据市场状态动态调整）
            if side == 'BUY':
                order['price'] = market_state.bid_price * (1 - 0.001 * slot / time_slots)
            else:
                order['price'] = market_state.ask_price * (1 + 0.001 * slot / time_slots)
            
            orders.append(order)
            remaining_quantity -= slot_quantity
        
        # 如果有剩余数量，添加到最后一个订单
        if remaining_quantity > self.config['min_order_size'] and orders:
            orders[-1]['quantity'] += remaining_quantity
        
        return orders
    
    async def _optimize_iceberg(self, symbol: str, side: str, quantity: float,
                              market_state: MarketState, urgency: str) -> List[Dict]:
        """冰山订单优化"""
        
        print(f"   🧊 使用冰山订单算法优化执行")
        
        # 确定冰山参数
        tip_size_percent = self._get_iceberg_tip_size(urgency)
        tip_quantity = quantity * tip_size_percent
        hidden_quantity = quantity - tip_quantity
        
        # 创建冰山订单
        orders = []
        
        # 显示部分（冰山顶部）
        tip_order = {
            'order_id': f"{symbol}_iceberg_tip",
            'symbol': symbol,
            'side': side,
            'quantity': tip_quantity,
            'order_type': 'LIMIT',
            'time_in_force': 'GTC',
            'execute_immediately': True,
            'strategy': 'ICEBERG_TIP',
            'notes': f"冰山订单显示部分 ({tip_size_percent:.1%})"
        }
        
        if side == 'BUY':
            tip_order['price'] = market_state.ask_price  # 主动吃单
        else:
            tip_order['price'] = market_state.bid_price
        
        orders.append(tip_order)
        
        # 隐藏部分（冰山水下）
        n_hidden_orders = max(3, int(hidden_quantity / (tip_quantity * 2)))
        hidden_order_quantity = hidden_quantity / n_hidden_orders
        
        for i in range(n_hidden_orders):
            hidden_order = {
                'order_id': f"{symbol}_iceberg_hidden_{i+1}",
                'symbol': symbol,
                'side': side,
                'quantity': hidden_order_quantity,
                'order_type': 'LIMIT',
                'time_in_force': 'GTC',
                'execute_after_minutes': (i + 1) * 5,  # 每5分钟下一个隐藏订单
                'visible': False,  # 隐藏订单
                'strategy': 'ICEBERG_HIDDEN',
                'notes': f"冰山订单隐藏部分 {i+1}/{n_hidden_orders}"
            }
            
            # 隐藏订单的价格更保守
            if side == 'BUY':
                hidden_order['price'] = market_state.bid_price * (1 - 0.002 * (i + 1))
            else:
                hidden_order['price'] = market_state.ask_price * (1 + 0.002 * (i + 1))
            
            orders.append(hidden_order)
        
        return orders
    
    async def _optimize_adaptive(self, symbol: str, side: str, quantity: float,
                               market_state: MarketState, urgency: str) -> List[Dict]:
        """自适应执行优化"""
        
        print(f"   🔄 使用自适应算法优化执行")
        
        # 评估市场条件
        market_condition = self._evaluate_market_condition(market_state)
        
        # 根据市场条件选择策略
        if market_condition == 'high_volatility':
            # 高波动市场，使用小订单快速执行
            return await self._optimize_high_volatility(symbol, side, quantity, market_state, urgency)
        elif market_condition == 'low_liquidity':
            # 低流动性市场，使用更保守的策略
            return await self._optimize_low_liquidity(symbol, side, quantity, market_state, urgency)
        elif market_condition == 'trending':
            # 趋势市场，顺势执行
            return await self._optimize_trending(symbol, side, quantity, market_state, urgency)
        else:
            # 正常市场，混合策略
            return await self._optimize_normal(symbol, side, quantity, market_state, urgency)
    
    async def _optimize_stealth(self, symbol: str, side: str, quantity: float,
                              market_state: MarketState, urgency: str) -> List[Dict]:
        """隐蔽执行优化"""
        
        print(f"   🕵️ 使用隐蔽执行算法")
        
        # 使用非常小的订单和随机时间间隔
        orders = []
        remaining_quantity = quantity
        
        # 确定最小订单大小
        min_order_size = max(self.config['min_order_size'], quantity * 0.001)
        
        # 创建多个小订单
        order_count = 0
        max_orders = min(50, int(quantity / min_order_size))
        
        while remaining_quantity > min_order_size and order_count < max_orders:
            # 随机确定订单大小（在一定范围内）
            max_order_ratio = min(0.05, remaining_quantity / quantity)
            order_ratio = np.random.uniform(0.001, max_order_ratio)
            order_quantity = quantity * order_ratio
            
            if order_quantity < min_order_size:
                order_quantity = min_order_size
            
            # 随机确定执行时间
            if order_count == 0:
                execute_after = 0  # 第一个立即执行
            else:
                execute_after = np.random.exponential(5)  # 平均5分钟间隔
            
            order = {
                'order_id': f"{symbol}_stealth_{order_count+1}",
                'symbol': symbol,
                'side': side,
                'quantity': order_quantity,
                'order_type': 'LIMIT',
                'time_in_force': 'GTC',
                'execute_after_minutes': execute_after,
                'visible': False,  # 隐藏订单
                'strategy': 'STEALTH',
                'notes': f"隐蔽订单 {order_count+1}"
            }
            
            # 随机确定价格（在一定范围内）
            price_range = market_state.spread * np.random.uniform(0.5, 2.0)
            
            if side == 'BUY':
                order['price'] = market_state.bid_price - price_range * np.random.uniform(0.1, 0.5)
            else:
                order['price'] = market_state.ask_price + price_range * np.random.uniform(0.1, 0.5)
            
            orders.append(order)
            remaining_quantity -= order_quantity
            order_count += 1
        
        # 如果有剩余，添加到最后一个订单
        if remaining_quantity > 0 and orders:
            orders[-1]['quantity'] += remaining_quantity
        
        return orders
    
    async def _optimize_high_volatility(self, symbol: str, side: str, quantity: float,
                                      market_state: MarketState, urgency: str) -> List[Dict]:
        """高波动市场优化"""
        
        # 使用更激进的执行，减少时间风险
        orders = []
        
        # 拆分成更少的订单，但每个订单更大
        n_orders = max(2, int(np.sqrt(quantity / market_state.volume_24h * 100)))
        order_quantity = quantity / n_orders
        
        for i in range(n_orders):
            order = {
                'order_id': f"{symbol}_highvol_{i+1}",
                'symbol': symbol,
                'side': side,
                'quantity': order_quantity,
                'order_type': 'MARKET',  # 高波动市场使用市价单
                'time_in_force': 'IOC',  # 立即成交或取消
                'execute_after_minutes': i * 2,  # 快速执行
                'strategy': 'HIGH_VOLATILITY',
                'notes': f"高波动市场订单 {i+1}/{n_orders}"
            }
            
            orders.append(order)
        
        return orders
    
    async def _optimize_low_liquidity(self, symbol: str, side: str, quantity: float,
                                    market_state: MarketState, urgency: str) -> List[Dict]:
        """低流动性市场优化"""
        
        # 使用更保守的执行，避免市场冲击
        orders = []
        
        # 拆分成很多小订单
        n_orders = min(20, int(quantity / (market_state.volume_24h * 0.0001)))
        order_quantity = quantity / n_orders
        
        for i in range(n_orders):
            order = {
                'order_id': f"{symbol}_lowliq_{i+1}",
                'symbol': symbol,
                'side': side,
                'quantity': order_quantity,
                'order_type': 'LIMIT',
                'time_in_force': 'GTC',
                'execute_after_minutes': i * 10,  # 慢速执行
                'strategy': 'LOW_LIQUIDITY',
                'notes': f"低流动性市场订单 {i+1}/{n_orders}"
            }
            
            # 更保守的价格
            if side == 'BUY':
                order['price'] = market_state.bid_price * (1 - 0.001 * (i + 1))
            else:
                order['price'] = market_state.ask_price * (1 + 0.001 * (i + 1))
            
            orders.append(order)
        
        return orders
    
    async def _optimize_trending(self, symbol: str, side: str, quantity: float,
                               market_state: MarketState, urgency: str) -> List[Dict]:
        """趋势市场优化"""
        
        # 判断趋势方向
        trend_direction = self._detect_trend_direction(symbol)
        
        orders = []
        
        if (side == 'BUY' and trend_direction == 'up') or (side == 'SELL' and trend_direction == 'down'):
            # 顺势交易，可以更积极
            print(f"   📈 顺势交易，使用积极执行")
            
            n_orders = 3  # 少量大订单
            order_quantity = quantity / n_orders
            
            for i in range(n_orders):
                order = {
                    'order_id': f"{symbol}_trend_{i+1}",
                    'symbol': symbol,
                    'side': side,
                    'quantity': order_quantity,
                    'order_type': 'LIMIT',
                    'time_in_force': 'GTC',
                    'execute_after_minutes': i * 5,
                    'strategy': 'TRENDING_WITH_TREND',
                    'notes': f"顺势订单 {i+1}/{n_orders}"
                }
                
                if side == 'BUY':
                    # 上涨趋势中，买单价可以更高
                    order['price'] = market_state.ask_price * (1 + 0.0005 * i)
                else:
                    # 下跌趋势中，卖单价可以更低
                    order['price'] = market_state.bid_price * (1 - 0.0005 * i)
                
                orders.append(order)
        else:
            # 逆势交易，需要更保守
            print(f"   📉 逆势交易，使用保守执行")
            
            return await self._optimize_stealth(symbol, side, quantity, market_state, urgency)
        
        return orders
    
    async def _optimize_normal(self, symbol: str, side: str, quantity: float,
                             market_state: MarketState, urgency: str) -> List[Dict]:
        """正常市场优化"""
        
        # 混合策略：部分TWAP，部分VWAP
        twap_ratio = 0.6
        vwap_ratio = 0.4
        
        orders = []
        
        # TWAP部分
        if twap_ratio > 0:
            twap_quantity = quantity * twap_ratio
            twap_orders = await self._optimize_twap(symbol, side, twap_quantity, market_state, urgency)
            for order in twap_orders:
                order['notes'] += " (混合策略-TWAP部分)"
            orders.extend(twap_orders)
        
        # VWAP部分
        if vwap_ratio > 0:
            vwap_quantity = quantity * vwap_ratio
            vwap_orders = await self._optimize_vwap(symbol, side, vwap_quantity, market_state, urgency)
            for order in vwap_orders:
                order['notes'] += " (混合策略-VWAP部分)"
            orders.extend(vwap_orders)
        
        return orders
    
    def _get_time_horizon(self, urgency: str) -> float:
        """获取执行时间窗口"""
        
        time_horizons = {
            'urgent': 5,    # 5分钟
            'high': 15,     # 15分钟
            'normal': 60,   # 1小时
            'low': 180      # 3小时
        }
        
        return time_horizons.get(urgency, self.config['default_time_horizon_minutes'])
    
    def _calculate_order_count(self, quantity: float, market_state: MarketState, urgency: str) -> int:
        """计算订单拆分数"""
        
        # 基于订单大小和市场流动性的启发式算法
        order_size_ratio = quantity / market_state.volume_24h
        
        base_count = {
            'urgent': 3,
            'high': 5,
            'normal': 10,
            'low': 20
        }.get(urgency, 10)
        
        # 根据订单大小调整
        if order_size_ratio > 0.01:  # 大于1%
            multiplier = 2
        elif order_size_ratio > 0.001:  # 大于0.1%
            multiplier = 1.5
        elif order_size_ratio > 0.0001:  # 大于0.01%
            multiplier = 1.2
        else:
            multiplier = 1.0
        
        return int(base_count * multiplier)
    
    def _get_volume_pattern(self, symbol: str) -> Dict[int, float]:
        """获取成交量模式"""
        
        # 这里应该从历史数据中分析成交量模式
        # 简化实现：返回均匀分布
        
        pattern = {}
        time_slots = 12
        
        for slot in range(time_slots):
            # 亚洲时段（0-3）和欧美时段（8-11）成交量较高
            if 0 <= slot <= 3 or 8 <= slot <= 11:
                pattern[slot] = 0.12  # 12%
            else:
                pattern[slot] = 0.08  # 8%
        
        # 归一化
        total = sum(pattern.values())
        for slot in pattern:
            pattern[slot] /= total
        
        return pattern
    
    def _get_iceberg_tip_size(self, urgency: str) -> float:
        """获取冰山订单显示部分比例"""
        
        tip_sizes = {
            'urgent': 0.3,   # 30%
            'high': 0.2,     # 20%
            'normal': 0.1,   # 10%
            'low': 0.05      # 5%
        }
        
        return tip_sizes.get(urgency, 0.1)
    
    def _evaluate_market_condition(self, market_state: MarketState) -> str:
        """评估市场条件"""
        
        # 基于波动性
        if market_state.volatility > 0.03:
            return 'high_volatility'
        
        # 基于流动性
        if market_state.volume_24h < 100000:  # 低成交量
            return 'low_liquidity'
        
        # 基于价差
        spread_ratio = market_state.spread / market_state.mid_price
        if spread_ratio > 0.002:  # 价差大于0.2%
            return 'low_liquidity'
        
        # 检测趋势
        if len(self.market_history[market_state.symbol]) > 10:
            trend = self._detect_trend_direction(market_state.symbol)
            if trend != 'neutral':
                return 'trending'
        
        return 'normal'
    
    def _detect_trend_direction(self, symbol: str) -> str:
        """检测趋势方向"""
        
        if symbol not in self.market_history or len(self.market_history[symbol]) < 20:
            return 'neutral'
        
        prices = [state.mid_price for state in list(self.market_history[symbol])[-20:]]
        
        if len(prices) < 10:
            return 'neutral'
        
        # 简单趋势检测
        first_half = np.mean(prices[:10])
        second_half = np.mean(prices[10:])
        
        change_percent = (second_half - first_half) / first_half
        
        if change_percent > 0.01:  # 上涨1%
            return 'up'
        elif change_percent < -0.01:  # 下跌1%
            return 'down'
        else:
            return 'neutral'
    
    async def _apply_learning_suggestions(self, plan: ExecutionPlan, market_state: MarketState) -> ExecutionPlan:
        """应用学习模型建议"""
        
        if not self.learning_model.is_trained:
            return plan
        
        suggestions = self.learning_model.get_suggestions(
            plan.symbol,
            plan.total_quantity,
            market_state,
            plan.order_type
        )
        
        if suggestions:
            # 调整订单大小
            if 'order_size_adjustment' in suggestions:
                adjustment = suggestions['order_size_adjustment']
                for order in plan.child_orders:
                    if 'quantity' in order:
                        order['quantity'] *= adjustment
            
            # 调整执行时间
            if 'time_adjustment' in suggestions:
                adjustment = suggestions['time_adjustment']
                for order in plan.child_orders:
                    if 'execute_after_minutes' in order:
                        order['execute_after_minutes'] *= adjustment
            
            # 调整价格
            if 'price_adjustment' in suggestions:
                adjustment = suggestions['price_adjustment']
                for order in plan.child_orders:
                    if 'price' in order:
                        order['price'] *= adjustment
        
        return plan
    
    def _calculate_confidence_score(self, plan: ExecutionPlan, market_state: MarketState) -> float:
        """计算置信度分数"""
        
        # 基于市场条件
        market_condition = self._evaluate_market_condition(market_state)
        condition_scores = {
            'normal': 0.9,
            'trending': 0.8,
            'high_volatility': 0.6,
            'low_liquidity': 0.5
        }
        condition_score = condition_scores.get(market_condition, 0.7)
        
        # 基于订单大小
        order_size_ratio = plan.total_quantity / market_state.volume_24h
        if order_size_ratio < 0.0001:  # 小于0.01%
            size_score = 1.0
        elif order_size_ratio < 0.001:  # 小于0.1%
            size_score = 0.9
        elif order_size_ratio < 0.01:   # 小于1%
            size_score = 0.8
        else:
            size_score = 0.6
        
        # 基于策略适用性
        strategy_scores = {
            'twap': 0.9,
            'vwap': 0.85,
            'adaptive': 0.8,
            'iceberg': 0.75,
            'stealth': 0.7,
            'market': 0.6
        }
        strategy_score = strategy_scores.get(plan.order_type, 0.7)
        
        # 基于历史表现
        if self.execution_history:
            recent_results = self.execution_history[-10:]
            if recent_results:
                avg_quality = np.mean([r.execution_quality_score for r in recent_results])
                history_score = avg_quality / 100
            else:
                history_score = 0.7
        else:
            history_score = 0.7
        
        # 综合分数
        weights = {
            'condition': 0.3,
            'size': 0.25,
            'strategy': 0.25,
            'history': 0.2
        }
        
        confidence = (
            condition_score * weights['condition'] +
            size_score * weights['size'] +
            strategy_score * weights['strategy'] +
            history_score * weights['history']
        )
        
        return confidence
    
    def record_execution_result(self, result: ExecutionResult):
        """记录执行结果"""
        
        self.execution_history.append(result)
        
        # 保持历史记录长度
        if len(self.execution_history) > 1000:
            self.execution_history = self.execution_history[-1000:]
        
        # 更新学习模型
        if self.config['enable_learning']:
            self.learning_model.add_training_data(result)
    
    def get_performance_report(self, symbol: str = None, days: int = 30) -> Dict[str, Any]:
        """获取性能报告"""
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        if symbol:
            filtered_results = [
                r for r in self.execution_history
                if r.symbol == symbol and r.end_time > cutoff_date
            ]
        else:
            filtered_results = [
                r for r in self.execution_history
                if r.end_time > cutoff_date
            ]
        
        if not filtered_results:
            return {
                'total_executions': 0,
                'message': '无执行记录'
            }
        
        # 计算统计信息
        total_executions = len(filtered_results)
        total_quantity = sum(r.executed_quantity for r in filtered_results)
        avg_completion_rate = np.mean([r.completion_rate for r in filtered_results])
        avg_quality_score = np.mean([r.execution_quality_score for r in filtered_results])
        avg_slippage = np.mean([abs(r.total_slippage) for r in filtered_results])
        
        # 按策略分组
        strategies = {}
        for result in filtered_results:
            # 从订单备注中提取策略
            strategy = 'UNKNOWN'
            if result.order_results:
                for order in result.order_results:
                    if 'strategy' in order:
                        strategy = order['strategy']
                        break
            
            if strategy not in strategies:
                strategies[strategy] = {
                    'count': 0,
                    'total_quantity': 0.0,
                    'avg_quality': 0.0,
                    'avg_slippage': 0.0
                }
            
            strategies[strategy]['count'] += 1
            strategies[strategy]['total_quantity'] += result.executed_quantity
            strategies[strategy]['avg_quality'] += result.execution_quality_score
            strategies[strategy]['avg_slippage'] += abs(result.total_slippage)
        
        # 计算平均值
        for strategy in strategies:
            count = strategies[strategy]['count']
            strategies[strategy]['avg_quality'] /= count
            strategies[strategy]['avg_slippage'] /= count
        
        report = {
            'period_days': days,
            'total_executions': total_executions,
            'total_quantity': total_quantity,
            'avg_completion_rate': avg_completion_rate,
            'avg_quality_score': avg_quality_score,
            'avg_slippage': avg_slippage,
            'strategies': strategies,
            'top_performing_strategies': sorted(
                strategies.items(),
                key=lambda x: x[1]['avg_quality'],
                reverse=True
            )[:3]
        }
        
        return report

class ExecutionLearningModel:
    """执行学习模型"""
    
    def __init__(self):
        self.training_data = []
        self.is_trained = False
        
    def add_training_data(self, execution_result: ExecutionResult):
        """添加训练数据"""
        
        self.training_data.append(execution_result)
        
        # 简单训练：当有足够数据时
        if len(self.training_data) >= 100:
            self._train_simple_model()
    
    def _train_simple_model(self):
        """训练简单模型"""
        
        print("🧠 训练执行学习模型...")
        
        # 这里应该实现机器学习模型
        # 简化实现：基于规则的模型
        
        self.is_trained = True
        print("✅ 执行学习模型训练完成")
    
    def get_suggestions(self, symbol: str, quantity: float, 
                       market_state: MarketState, strategy: str) -> Dict[str, float]:
        """获取优化建议"""
        
        if not self.is_trained:
            return {}
        
        # 基于历史数据的简单建议
        suggestions = {}
        
        # 根据市场波动性调整
        if market_state.volatility > 0.03:
            suggestions['order_size_adjustment'] = 0.8  # 减小订单大小
            suggestions['time_adjustment'] = 0.7  # 加快执行
        
        # 根据流动性调整
        if market_state.volume_24h < 100000:
            suggestions['order_size_adjustment'] = 0.5  # 大幅减小订单大小
            suggestions['price_adjustment'] = 0.99 if strategy in ['BUY', 'buy'] else 1.01
        
        return suggestions

# 单例实例
_execution_optimizer = None

def get_execution_optimizer(config_manager=None) -> ExecutionOptimizer:
    """获取执行优化器单例"""
    global _execution_optimizer
    if _execution_optimizer is None:
        _execution_optimizer = ExecutionOptimizer(config_manager)
    return _execution_optimizer

async def test_execution_optimizer():
    """测试执行优化器"""
    
    optimizer = get_execution_optimizer()
    
    # 创建模拟市场状态
    market_state = MarketState(
        timestamp=datetime.now(),
        symbol='BTCUSDT',
        bid_price=50000.0,
        ask_price=50010.0,
        bid_size=5.0,
        ask_size=5.0,
        spread=10.0,
        mid_price=50005.0,
        volume_24h=1000000.0,
        volatility=0.02,
        order_book_depth={
            'bid_0.1%': 10.0,
            'bid_0.5%': 50.0,
            'ask_0.1%': 10.0,
            'ask_0.5%': 50.0
        }
    )
    
    optimizer.update_market_state(market_state)
    
    # 创建执行计划
    order_request = {
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'quantity': 1.0,  # 1个BTC
        'order_type': 'ADAPTIVE',
        'urgency': 'normal'
    }
    
    plan = await optimizer.create_execution_plan(order_request)
    
    print(f"\n📋 执行计划详情:")
    print(f"   计划ID: {plan.plan_id}")
    print(f"   策略: {plan.order_type}")
    print(f"   子订单数: {len(plan.child_orders)}")
    
    for i, order in enumerate(plan.child_orders[:3]):  # 只显示前3个
        print(f"   订单{i+1}: {order.get('quantity', 0):.4f} {order.get('order_type', 'N/A')} "
              f"@{order.get('price', 0):.2f}")
    
    if len(plan.child_orders) > 3:
        print(f"   ... 还有 {len(plan.child_orders) - 3} 个订单")
    
    print(f"\n📊 执行指标:")
    print(f"   预估滑点: {plan.estimated_slippage:.4%}")
    print(f"   市场冲击: {plan.market_impact:.4%}")
    print(f"   置信度: {plan.confidence_score:.2%}")
    
    # 模拟执行结果
    result = ExecutionResult(
        plan_id=plan.plan_id,
        symbol=plan.symbol,
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(minutes=30),
        total_quantity=plan.total_quantity,
        executed_quantity=plan.total_quantity * 0.95,  # 95%成交
        average_price=50020.0,
        total_cost=plan.total_quantity * 50020.0,
        total_slippage=0.001,  # 0.1%滑点
        actual_market_impact=plan.market_impact * 1.2,
        completion_rate=0.95,
        execution_quality_score=0.0
    )
    
    result.calculate_quality_score()
    optimizer.record_execution_result(result)
    
    print(f"\n📈 执行结果:")
    print(f"   完成率: {result.completion_rate:.2%}")
    print(f"   平均价格: {result.average_price:.2f}")
    print(f"   实际滑点: {result.total_slippage:.4%}")
    print(f"   质量分数: {result.execution_quality_score:.1f}/100")
    
    # 获取性能报告
    report = optimizer.get_performance_report()
    print(f"\n📊 性能报告:")
    print(f"   总执行次数: {report.get('total_executions', 0)}")
    print(f"   平均质量分数: {report.get('avg_quality_score', 0):.1f}")

if __name__ == "__main__":
    asyncio.run(test_execution_optimizer())