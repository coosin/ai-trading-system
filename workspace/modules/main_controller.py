#!/usr/bin/env python3
"""
主控制器
协调所有模块，实现全智能自主交易
"""

import asyncio
import time
import json
import signal
import sys
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import numpy as np

from .core.config_manager import get_config_manager, SystemConfig, TradingConfig, RiskConfig
from .core.data_pipeline import get_data_pipeline, MarketData, OrderBookSnapshot
from .intelligence.decision_engine.multi_model import (
    get_decision_engine, MultiModelDecisionEngine, TradingSignal, Decision
)
from .execution.order_manager.smart_order import (
    get_order_manager, SmartOrderManager, Order, OrderStatus, OrderType
)

@dataclass
class SystemState:
    """系统状态"""
    running: bool = False
    mode: str = "paper_trading"  # paper_trading, live_trading, backtesting
    start_time: datetime = None
    uptime: float = 0.0
    total_trades: int = 0
    total_pnl: float = 0.0
    current_risk_level: str = "low"
    last_error: str = None
    
    def __post_init__(self):
        if self.start_time is None:
            self.start_time = datetime.now()
    
    def update_uptime(self):
        """更新运行时间"""
        if self.running:
            self.uptime = (datetime.now() - self.start_time).total_seconds()
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'running': self.running,
            'mode': self.mode,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'uptime': self.uptime,
            'total_trades': self.total_trades,
            'total_pnl': self.total_pnl,
            'current_risk_level': self.current_risk_level,
            'last_error': self.last_error
        }

@dataclass
class Portfolio:
    """投资组合"""
    total_capital: float = 10000.0
    available_capital: float = 10000.0
    positions: Dict[str, Dict] = None  # symbol -> position_info
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    
    def __post_init__(self):
        if self.positions is None:
            self.positions = {}
    
    def update_position(self, symbol: str, quantity: float, avg_price: float):
        """更新仓位"""
        if quantity == 0:
            if symbol in self.positions:
                del self.positions[symbol]
        else:
            self.positions[symbol] = {
                'quantity': quantity,
                'avg_price': avg_price,
                'entry_time': datetime.now()
            }
    
    def calculate_unrealized_pnl(self, current_prices: Dict[str, float]) -> float:
        """计算未实现盈亏"""
        total_unrealized = 0.0
        
        for symbol, position in self.positions.items():
            if symbol in current_prices:
                current_price = current_prices[symbol]
                position_value = position['quantity'] * current_price
                entry_value = position['quantity'] * position['avg_price']
                unrealized = position_value - entry_value
                total_unrealized += unrealized
        
        self.unrealized_pnl = total_unrealized
        return total_unrealized
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'total_capital': self.total_capital,
            'available_capital': self.available_capital,
            'positions': self.positions,
            'unrealized_pnl': self.unrealized_pnl,
            'realized_pnl': self.realized_pnl,
            'max_drawdown': self.max_drawdown,
            'sharpe_ratio': self.sharpe_ratio
        }

class MainController:
    """主控制器"""
    
    def __init__(self):
        # 初始化所有模块
        self.config_manager = get_config_manager()
        self.data_pipeline = get_data_pipeline(self.config_manager)
        self.decision_engine = get_decision_engine()
        self.order_manager = get_order_manager(None, self.config_manager)  # 需要实际的exchange_adapter
        
        # 系统状态
        self.state = SystemState()
        self.portfolio = Portfolio()
        
        # 监控的币种
        self.monitored_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        
        # 任务列表
        self.tasks = []
        self.should_stop = False
        
        # 事件回调
        self.event_callbacks = {
            'system_started': [],
            'system_stopped': [],
            'signal_generated': [],
            'order_created': [],
            'order_filled': [],
            'error_occurred': []
        }
    
    def register_callback(self, event_type: str, callback):
        """注册事件回调"""
        if event_type in self.event_callbacks:
            self.event_callbacks[event_type].append(callback)
    
    async def start(self, mode: str = "paper_trading"):
        """启动系统"""
        
        print("=" * 60)
        print("🚀 启动全智能量化交易系统")
        print("=" * 60)
        
        try:
            # 设置运行模式
            self.state.mode = mode
            self.state.running = True
            self.state.start_time = datetime.now()
            
            # 触发系统启动事件
            await self._trigger_event('system_started', {
                'mode': mode,
                'timestamp': datetime.now().isoformat()
            })
            
            # 启动核心任务
            self.tasks = [
                asyncio.create_task(self._market_data_task()),
                asyncio.create_task(self._decision_making_task()),
                asyncio.create_task(self._portfolio_monitor_task()),
                asyncio.create_task(self._system_health_task())
            ]
            
            print("✅ 系统启动完成")
            print(f"📊 监控币种: {', '.join(self.monitored_symbols)}")
            print(f"🎯 运行模式: {mode}")
            print(f"💰 初始资金: ${self.portfolio.total_capital:,.2f}")
            
            # 等待所有任务完成
            await asyncio.gather(*self.tasks)
            
        except Exception as e:
            self.state.last_error = str(e)
            print(f"❌ 系统启动失败: {e}")
            await self.stop()
    
    async def stop(self):
        """停止系统"""
        
        print("\n" + "=" * 60)
        print("🛑 停止全智能量化交易系统")
        print("=" * 60)
        
        self.should_stop = True
        self.state.running = False
        
        # 取消所有任务
        for task in self.tasks:
            task.cancel()
        
        # 等待任务取消完成
        await asyncio.sleep(1)
        
        # 取消所有活跃订单
        await self._cancel_all_orders()
        
        # 触发系统停止事件
        await self._trigger_event('system_stopped', {
            'uptime': self.state.uptime,
            'total_trades': self.state.total_trades,
            'total_pnl': self.state.total_pnl,
            'timestamp': datetime.now().isoformat()
        })
        
        print(f"📊 运行统计:")
        print(f"   运行时间: {self.state.uptime:.1f} 秒")
        print(f"   总交易数: {self.state.total_trades}")
        print(f"   总盈亏: ${self.state.total_pnl:,.2f}")
        print(f"   夏普比率: {self.portfolio.sharpe_ratio:.2f}")
        print(f"   最大回撤: {self.portfolio.max_drawdown:.2%}")
        print("✅ 系统停止完成")
    
    async def _market_data_task(self):
        """市场数据任务"""
        
        print("📈 启动市场数据任务...")
        
        while not self.should_stop:
            try:
                # 获取所有监控币种的数据
                for symbol in self.monitored_symbols:
                    # 获取实时价格
                    price = await self.data_pipeline.fetch_real_time_price(symbol)
                    
                    if price:
                        # 获取K线数据
                        klines = await self.data_pipeline.fetch_historical_data(
                            symbol, '1h', limit=100
                        )
                        
                        # 计算技术指标
                        indicators = self.data_pipeline.calculate_technical_indicators(klines)
                        
                        # 构建市场数据包
                        market_data = {
                            'symbol': symbol,
                            'price': price,
                            'timestamp': datetime.now(),
                            'indicators': indicators,
                            'klines': [{
                                'time': k.timestamp.isoformat(),
                                'open': k.open,
                                'high': k.high,
                                'low': k.low,
                                'close': k.close,
                                'volume': k.volume
                            } for k in klines[-20:]]  # 最近20根K线
                        }
                        
                        # 存储到数据管道缓存
                        self.data_pipeline.data_storage[f"current_{symbol}"] = market_data
                
                # 每10秒更新一次
                await asyncio.sleep(10)
                
            except Exception as e:
                print(f"市场数据任务出错: {e}")
                await asyncio.sleep(30)
    
    async def _decision_making_task(self):
        """决策生成任务"""
        
        print("🧠 启动智能决策任务...")
        
        decision_interval = 60  # 每60秒做一次决策
        
        while not self.should_stop:
            try:
                # 对每个监控币种生成决策
                for symbol in self.monitored_symbols:
                    # 获取当前市场数据
                    market_data_key = f"current_{symbol}"
                    if market_data_key not in self.data_pipeline.data_storage:
                        continue
                    
                    market_data = self.data_pipeline.data_storage[market_data_key]
                    
                    # 获取当前仓位信息
                    position_info = self.portfolio.positions.get(symbol, {})
                    
                    # 使用多模型决策引擎分析
                    model_outputs = await self.decision_engine.analyze_market(
                        symbol, market_data, self.portfolio.to_dict()
                    )
                    
                    # 融合决策
                    signal = self.decision_engine.fuse_decisions(model_outputs)
                    signal.symbol = symbol  # 确保symbol正确
                    
                    # 触发信号生成事件
                    await self._trigger_event('signal_generated', {
                        'symbol': symbol,
                        'signal': asdict(signal),
                        'model_outputs': {
                            name: {
                                'decision': output.decision.value,
                                'confidence': output.confidence,
                                'reasoning': output.reasoning
                            }
                            for name, output in model_outputs.items()
                        },
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    # 如果信号不是HOLD，执行交易
                    if signal.decision != Decision.HOLD and signal.confidence > 0.6:
                        await self._execute_trade_signal(signal)
                
                # 等待下一个决策周期
                await asyncio.sleep(decision_interval)
                
            except Exception as e:
                print(f"决策任务出错: {e}")
                await self._trigger_event('error_occurred', {
                    'task': 'decision_making',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
                await asyncio.sleep(30)
    
    async def _execute_trade_signal(self, signal: TradingSignal):
        """执行交易信号"""
        
        try:
            # 构建交易指令
            trade_instruction = {
                'symbol': signal.symbol,
                'side': 'BUY' if signal.decision in [Decision.BUY, Decision.STRONG_BUY] else 'SELL',
                'quantity': self._calculate_position_size(signal),
                'order_type': 'LIMIT',
                'strategy_id': 'ai_trader_v1',
                'urgency': 'normal',
                'max_slippage': 0.005,  # 最大滑点0.5%
                'reason': signal.reasoning
            }
            
            # 设置目标价格
            current_price = self._get_current_price(signal.symbol)
            if trade_instruction['side'] == 'BUY':
                trade_instruction['price'] = current_price * 0.995  # 低于市价0.5%
            else:
                trade_instruction['price'] = current_price * 1.005  # 高于市价0.5%
            
            # 设置止损止盈
            if signal.stop_loss:
                trade_instruction['stop_price'] = signal.stop_loss
            if signal.take_profit:
                trade_instruction['take_profit'] = signal.take_profit
            
            # 创建订单
            order = await self.order_manager.create_order(trade_instruction, self.portfolio.to_dict())
            
            if order:
                # 触发订单创建事件
                await self._trigger_event('order_created', {
                    'order_id': order.order_id,
                    'symbol': order.symbol,
                    'side': order.side,
                    'quantity': order.quantity,
                    'price': order.price,
                    'status': order.status.value,
                    'timestamp': datetime.now().isoformat()
                })
                
                print(f"📝 创建订单: {order.order_id} {order.side} {order.quantity} {order.symbol} @ {order.price}")
            
        except Exception as e:
            print(f"执行交易信号失败: {e}")
            await self._trigger_event('error_occurred', {
                'task': 'execute_trade',
                'error': str(e),
                'symbol': signal.symbol,
                'timestamp': datetime.now().isoformat()
            })
    
    def _calculate_position_size(self, signal: TradingSignal) -> float:
        """计算仓位大小"""
        
        # 基础仓位比例
        base_position_percent = 0.05  # 5%
        
        # 根据信号强度调整
        if signal.decision == Decision.STRONG_BUY or signal.decision == Decision.STRONG_SELL:
            position_multiplier = 2.0
        elif signal.decision == Decision.BUY or signal.decision == Decision.SELL:
            position_multiplier = 1.0
        else:
            position_multiplier = 0.0
        
        # 根据置信度调整
        confidence_multiplier = signal.confidence
        
        # 根据风险等级调整
        risk_multiplier = 1.0
        if self.state.current_risk_level == "high":
            risk_multiplier = 0.5
        elif self.state.current_risk_level == "medium":
            risk_multiplier = 0.8
        
        # 计算最终仓位比例
        position_percent = base_position_percent * position_multiplier * confidence_multiplier * risk_multiplier
        
        # 转换为具体数量
        current_price = self._get_current_price(signal.symbol)
        if not current_price:
            return 0.0
        
        position_value = self.portfolio.total_capital * position_percent
        position_size = position_value / current_price
        
        # 最小交易单位检查
        min_size = 0.001  # 假设最小交易单位
        if position_size < min_size:
            return 0.0
        
        return round(position_size, 6)  # 保留6位小数
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """获取当前价格"""
        market_data_key = f"current_{symbol}"
        if market_data_key in self.data_pipeline.data_storage:
            return self.data_pipeline.data_storage[market_data_key].get('price')
        return None
    
    async def _portfolio_monitor_task(self):
        """投资组合监控任务"""
        
        print("💰 启动投资组合监控任务...")
        
        while not self.should_stop:
            try:
                # 获取当前价格
                current_prices = {}
                for symbol in self.monitored_symbols:
                    price = self._get_current_price(symbol)
                    if price:
                        current_prices[symbol] = price
                
                # 更新未实现盈亏
                unrealized_pnl = self.portfolio.calculate_unrealized_pnl(current_prices)
                
                # 更新夏普比率（简化计算）
                if self.state.total_trades > 0:
                    avg_return = self.state.total_pnl / self.state.total_trades
                    return_std = abs(avg_return) * 0.5  # 简化假设
                    if return_std > 0:
                        self.portfolio.sharpe_ratio = avg_return / return_std
                
                # 更新最大回撤
                total_value = self.portfolio.total_capital + unrealized_pnl
                peak_value = max(self.portfolio.total_capital * 1.1, total_value)  # 简化处理
                drawdown = (peak_value - total_value) / peak_value
                self.portfolio.max_drawdown = max(self.portfolio.max_drawdown, drawdown)
                
                # 更新风险等级
                self._update_risk_level()
                
                # 每30秒更新一次
                await asyncio.sleep(30)
                
            except Exception as e:
                print(f"投资组合监控任务出错: {e}")
                await asyncio.sleep(60)
    
    def _update_risk_level(self):
        """更新风险等级"""
        
        # 根据回撤和波动性判断风险等级
        if self.portfolio.max_drawdown > 0.15:  # 回撤超过15%
            self.state.current_risk_level = "high"
        elif self.portfolio.max_drawdown > 0.08:  # 回撤超过8%
            self.state.current_risk_level = "medium"
        else:
            self.state.current_risk_level = "low"
    
    async def _system_health_task(self):
        """系统健康检查任务"""
        
        print("🏥 启动系统健康检查任务...")
        
        while not self.should_stop:
            try:
                # 更新运行时间
                self.state.update_uptime()
                
                # 检查模块健康状态
                health_status = {
                    'data_pipeline': len(self.data_pipeline.data_storage) > 0,
                    'decision_engine': len(self.decision_engine.decision_history) > 0,
                    'order_manager': len(self.order_manager.active_orders) >= 0,
                    'uptime': self.state.uptime,
                    'memory_usage': self._get_memory_usage(),
                    'cpu_usage': self._get_cpu_usage()
                }
                
                # 如果有严重问题，记录错误
                if not all(health_status.values()):
                    self.state.last_error = "系统健康检查失败"
                
                # 每60秒检查一次
                await asyncio.sleep(60)
                
            except Exception as e:
                print(f"系统健康检查任务出错: {e}")
                await asyncio.sleep(60)
    
    def _get_memory_usage(self) -> float:
        """获取内存使用率"""
        # 简化实现，实际应该使用psutil
        return 0.0
    
    def _get_cpu_usage(self) -> float:
        """获取CPU使用率"""
        # 简化实现，实际应该使用psutil
        return 0.0
    
    async def _cancel_all_orders(self):
        """取消所有活跃订单"""
        
        try:
            active_orders = self.order_manager.get_active_orders()
            for order in active_orders:
                await self.order_manager.cancel_order(order.order_id)
            
            print(f"✅ 已取消 {len(active_orders)} 个活跃订单")
            
        except Exception as e:
            print(f"取消订单失败: {e}")
    
    async def _trigger_event(self, event_type: str, data: Dict):
        """触发事件"""
        
        if event_type in self.event_callbacks:
            for callback in self.event_callbacks[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event_type, data)
                    else:
                        callback(event_type, data)
                except Exception as e:
                    print(f"事件回调执行失败: {e}")
    
    def get_system_status(self) -> Dict:
        """获取系统状态"""
        
        return {
            'state': self.state.to_dict(),
            'portfolio': self.portfolio.to_dict(),
            'monitored_symbols': self.monitored_symbols,
            'active_orders': [
                {
                    'order_id': order.order_id,
                    'symbol': order.symbol,
                    'side': order.side,
                    'quantity': order.quantity,
                    'filled_quantity': order.filled_quantity,
                    'price': order.price,
                    'status': order.status.value
                }
                for order in self.order_manager.get_active_orders()
            ],
            'decision_stats': self.decision_engine.get_performance_stats(),
            'execution_stats': self.order_manager.get_execution_stats()
        }
    
    async def manual_override(self, action: str, params: Dict) -> Dict:
        """手动控制"""
        
        result = {'success': False, 'message': ''}
        
        try:
            if action == 'create_order':
                # 手动创建订单
                order = await self.order_manager.create_order(params, self.portfolio.to_dict())
                if order:
                    result['success'] = True
                    result['message'] = f"订单创建成功: {order.order_id}"
                    result['order_id'] = order.order_id
                else:
                    result['message'] = "订单创建失败"
            
            elif action == 'cancel_order':
                # 手动取消订单
                success = await self.order_manager.cancel_order(params['order_id'])
                result['success'] = success
                result['message'] = "订单取消成功" if success else "订单取消失败"
            
            elif action == 'update_config':
                # 更新配置
                config_type = params.get('config_type')
                updates = params.get('updates', {})
                
                if config_type and updates:
                    self.config_manager.update_config(config_type, updates)
                    result['success'] = True
                    result['message'] = f"配置 {config_type} 更新成功"
                else:
                    result['message'] = "配置更新参数错误"
            
            elif action == 'emergency_stop':
                # 紧急停止
                await self.stop()
                result['success'] = True
                result['message'] = "系统已紧急停止"
            
            else:
                result['message'] = f"未知的操作: {action}"
                
        except Exception as e:
            result['message'] = f"操作失败: {str(e)}"
        
        return result

# 全局实例
_controller = None

def get_controller() -> MainController:
    """获取主控制器单例"""
    global _controller
    if _controller is None:
        _controller = MainController()
    return _controller

async def main():
    """主函数"""
    
    # 创建主控制器
    controller = get_controller()
    
    # 设置信号处理
    def signal_handler(signum, frame):
        print(f"\n收到信号 {signum}，正在停止系统...")
        asyncio.create_task(controller.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 启动系统
        await controller.start(mode="paper_trading")
        
    except KeyboardInterrupt:
        print("\n用户中断，正在停止系统...")
        await controller.stop()
    
    except Exception as e:
        print(f"系统运行出错: {e}")
        await controller.stop()

if __name__ == "__main__":
    asyncio.run(main())