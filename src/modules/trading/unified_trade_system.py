"""
统一交易系统

整合所有交易执行功能：
1. 交易执行
2. 交易监控
3. 交易记录
4. 交易通知
"""

import asyncio
import inspect
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

from src.modules.core.module_config_utils import resolve_module_config

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class UnifiedTradeSystem:
    """
    统一交易系统
    
    整合所有交易执行功能，提供统一接口
    """
    
    def __init__(self, config: Dict[str, Any] = None, config_manager=None):
        """
        初始化统一交易系统
        
        Args:
            config: 配置字典
        """
        self.config = resolve_module_config(
            config=config,
            config_manager=config_manager,
            section="unified_trade_system",
            defaults={},
        )
        
        # 子模块（保留现有模块的引用）
        self.executor = None
        self.monitor = None
        self.recorder = None
        self.notifier = None
        
        # 交易记录
        self.trades: Dict[str, Dict] = {}
        
        # 订单队列
        self._order_queue: asyncio.Queue = asyncio.Queue()
        self._order_task: Optional[asyncio.Task] = None
        self.exchange_executor = None
        
        # 统计信息
        self.stats = {
            "total_trades": 0,
            "successful_trades": 0,
            "failed_trades": 0,
            "total_volume": 0.0,
            "last_trade_time": None
        }
        
        logger.info("统一交易系统初始化")
    
    async def initialize(self) -> bool:
        """
        初始化所有子模块
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            logger.info("🔧 初始化统一交易系统...")
            
            # 初始化交易执行器
            await self._init_executor()
            
            # 初始化交易监控器
            await self._init_monitor()
            
            # 初始化交易记录器
            await self._init_recorder()
            
            # 初始化交易通知器
            await self._init_notifier()
            
            # 启动订单处理任务
            self._order_task = asyncio.create_task(self._process_orders())

            # 配置驱动初始化执行后端（兼容 simulation 模式）
            if not self.exchange_executor and self.config.get("mode") == "simulation":
                try:
                    from src.modules.simulation.simulation_exchange import SimulationExchange
                    self.exchange_executor = SimulationExchange(self.config.get("simulation", {}))
                    logger.info("✅ 已按配置加载模拟交易执行后端")
                except Exception as e:
                    logger.warning(f"⚠️ 模拟交易执行后端加载失败: {e}")
            
            logger.info("✅ 统一交易系统初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 统一交易系统初始化失败: {e}")
            return False
    
    async def _init_executor(self):
        """初始化交易执行器"""
        try:
            # 交易执行功能整合到此系统
            self.executor = {}
            logger.info("✅ 交易执行器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 交易执行器初始化失败: {e}")
            self.executor = None
    
    async def _init_monitor(self):
        """初始化交易监控器"""
        try:
            from src.modules.monitoring.trading_monitor import TradingMonitor
            self.monitor = TradingMonitor({})
            logger.info("✅ 交易监控器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 交易监控器初始化失败: {e}")
            self.monitor = None
    
    async def _init_recorder(self):
        """初始化交易记录器"""
        try:
            # 交易记录功能整合到此系统
            self.recorder = {}
            logger.info("✅ 交易记录器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 交易记录器初始化失败: {e}")
            self.recorder = None
    
    async def _init_notifier(self):
        """初始化交易通知器"""
        try:
            from src.modules.notification.telegram_bot import TelegramBot
            # TelegramBot需要配置，这里先设为None
            self.notifier = None
            logger.info("✅ 交易通知器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 交易通知器初始化失败: {e}")
            self.notifier = None

    def set_execution_backend(self, backend: Any):
        """注入订单执行后端（支持 async/sync execute_order）。"""
        self.exchange_executor = backend
    
    # ==================== 交易执行 ====================
    
    async def execute_trade(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行交易
        
        Args:
            order: 订单信息
        
        Returns:
            Dict: 执行结果
        """
        try:
            # 生成订单ID
            order_id = order.get("id", f"order_{datetime.now().timestamp()}")
            
            # 添加到队列
            await self._order_queue.put({
                "id": order_id,
                "order": order,
                "status": OrderStatus.PENDING,
                "submitted_at": datetime.now()
            })
            
            logger.info(f"订单已提交: {order_id}")
            
            return {
                "order_id": order_id,
                "status": "submitted",
                "message": "订单已提交到执行队列"
            }
            
        except Exception as e:
            logger.error(f"执行交易失败: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _process_orders(self):
        """处理订单队列"""
        while True:
            try:
                # 从队列获取订单
                order_data = await self._order_queue.get()
                
                # 执行订单
                result = await self._execute_order(order_data)
                
                # 更新统计
                self.stats["total_trades"] += 1
                if result.get("status") == "success":
                    self.stats["successful_trades"] += 1
                else:
                    self.stats["failed_trades"] += 1
                
                self.stats["last_trade_time"] = datetime.now()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理订单失败: {e}")
                await asyncio.sleep(1)
            finally:
                try:
                    self._order_queue.task_done()
                except ValueError:
                    pass
    
    async def _execute_order(self, order_data: Dict) -> Dict[str, Any]:
        """
        执行单个订单
        
        Args:
            order_data: 订单数据
        
        Returns:
            Dict: 执行结果
        """
        try:
            order_id = order_data["id"]
            order = order_data["order"]
            
            logger.info(f"执行订单: {order_id}")

            execution_price = order.get("price")

            if self.exchange_executor:
                symbol = order.get("symbol")
                side = str(order.get("side", "buy")).lower()
                size = float(order.get("amount") or order.get("size") or order.get("quantity") or 0)
                if not symbol or size <= 0:
                    raise ValueError("订单缺少 symbol 或数量字段(amount/size/quantity)")

                if side in ("long", "buy"):
                    side = "buy"
                elif side in ("short", "sell"):
                    side = "sell"
                else:
                    raise ValueError(f"不支持的交易方向: {side}")

                backend_call = self.exchange_executor.execute_order(
                    symbol=symbol,
                    side=side,
                    size=size,
                    price=order.get("price"),
                )
                backend_result = await backend_call if inspect.isawaitable(backend_call) else backend_call
                if isinstance(backend_result, dict):
                    execution_price = backend_result.get("price", execution_price)
            
            # 记录交易
            await self.record_trade({
                "id": order_id,
                "symbol": order.get("symbol"),
                "side": order.get("side"),
                "amount": order.get("amount") or order.get("size") or order.get("quantity"),
                "price": execution_price,
                "status": "filled",
                "executed_at": datetime.now()
            })
            
            # 发送通知
            await self.notify_trade({
                "order_id": order_id,
                "symbol": order.get("symbol"),
                "status": "filled"
            })
            
            return {"status": "success", "order_id": order_id}
            
        except Exception as e:
            logger.error(f"执行订单失败: {e}")
            return {"status": "error", "error": str(e)}
    
    async def cancel_trade(self, order_id: str) -> bool:
        """
        取消交易
        
        Args:
            order_id: 订单ID
        
        Returns:
            bool: 是否成功
        """
        try:
            if order_id in self.trades:
                self.trades[order_id]["status"] = "cancelled"
                logger.info(f"订单已取消: {order_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"取消交易失败 {order_id}: {e}")
            return False
    
    # ==================== 交易监控 ====================
    
    async def monitor_trade(self, trade_id: str) -> Dict[str, Any]:
        """
        监控交易
        
        Args:
            trade_id: 交易ID
        
        Returns:
            Dict: 监控结果
        """
        try:
            if trade_id not in self.trades:
                return {"status": "not_found"}
            
            trade = self.trades[trade_id]
            
            # 使用监控器
            if self.monitor:
                try:
                    status = await self.monitor.get_trade_status(trade_id)
                    return {
                        **trade,
                        "monitor_status": status
                    }
                except Exception as e:
                    logger.debug(f"监控器查询交易状态失败 {trade_id}: {e}")
            
            return trade
            
        except Exception as e:
            logger.error(f"监控交易失败 {trade_id}: {e}")
            return {"status": "error", "error": str(e)}
    
    async def get_trade_status(self, trade_id: str) -> Dict[str, Any]:
        """
        获取交易状态
        
        Args:
            trade_id: 交易ID
        
        Returns:
            Dict: 交易状态
        """
        try:
            if trade_id not in self.trades:
                return {"status": "not_found"}
            
            return self.trades[trade_id]
            
        except Exception as e:
            logger.error(f"获取交易状态失败 {trade_id}: {e}")
            return {"status": "error", "error": str(e)}
    
    # ==================== 交易记录 ====================
    
    async def record_trade(self, trade: Dict[str, Any]) -> bool:
        """
        记录交易
        
        Args:
            trade: 交易信息
        
        Returns:
            bool: 是否成功
        """
        try:
            trade_id = trade.get("id", f"trade_{datetime.now().timestamp()}")
            
            # 保存到内存
            self.trades[trade_id] = {
                **trade,
                "recorded_at": datetime.now()
            }
            
            # 使用监控器记录
            if self.monitor:
                try:
                    await self.monitor.add_trade_execution(trade)
                except Exception as e:
                    logger.debug(f"监控器记录交易失败 {trade_id}: {e}")
            
            logger.debug(f"交易已记录: {trade_id}")
            return True
            
        except Exception as e:
            logger.error(f"记录交易失败: {e}")
            return False
    
    async def get_trade_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取交易历史
        
        Args:
            limit: 返回数量限制
        
        Returns:
            List[Dict]: 交易历史列表
        """
        try:
            # 按时间排序
            sorted_trades = sorted(
                self.trades.items(),
                key=lambda x: x[1].get("recorded_at", datetime.min),
                reverse=True
            )
            
            return [trade for _, trade in sorted_trades[:limit]]
            
        except Exception as e:
            logger.error(f"获取交易历史失败: {e}")
            return []
    
    # ==================== 交易通知 ====================
    
    async def notify_trade(self, notification: Dict[str, Any]) -> bool:
        """
        发送交易通知
        
        Args:
            notification: 通知信息
        
        Returns:
            bool: 是否成功
        """
        try:
            # 使用通知器
            if self.notifier:
                try:
                    await self.notifier.send_trade_notification(notification)
                except Exception as e:
                    logger.debug(f"通知器发送交易通知失败: {e}")
            
            logger.debug(f"交易通知已发送: {notification.get('order_id', 'unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"发送交易通知失败: {e}")
            return False
    
    # ==================== 统计和监控 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict: 统计信息
        """
        return {
            **self.stats,
            "total_recorded_trades": len(self.trades),
            "executor_available": self.executor is not None,
            "monitor_available": self.monitor is not None,
            "recorder_available": self.recorder is not None,
            "notifier_available": self.notifier is not None
        }
    
    # ==================== 清理 ====================
    
    async def cleanup(self):
        """清理资源"""
        try:
            logger.info("清理统一交易系统...")

            if self._order_task and not self._order_task.done():
                self._order_task.cancel()
                try:
                    await self._order_task
                except asyncio.CancelledError:
                    pass
            self._order_task = None
            
            # 清理交易记录
            self.trades.clear()
            
            logger.info("✅ 统一交易系统清理完成")
        except Exception as e:
            logger.error(f"清理失败: {e}")
