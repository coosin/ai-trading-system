"""
交易专用监控模块

功能：
1. 交易执行监控
2. 策略性能监控
3. 市场数据监控
4. 风险指标监控
5. 订单状态监控
6. 交易专用监控面板
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


class TradingStatus(Enum):
    """交易状态"""
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class AlertSeverity(Enum):
    """告警严重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class TradeExecution:
    """交易执行记录"""
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    status: OrderStatus
    timestamp: float
    executed_quantity: float = 0.0
    avg_price: float = 0.0
    fee: float = 0.0


@dataclass
class StrategyPerformance:
    """策略性能指标"""
    strategy_name: str
    total_trades: int
    win_trades: int
    loss_trades: int
    win_rate: float
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: float
    last_update: float
    # 新增细粒度指标
    avg_win: float = 0.0  # 平均盈利
    avg_loss: float = 0.0  # 平均亏损
    profit_factor: float = 0.0  # 盈利因子
    expectancy: float = 0.0  # 预期收益
    drawdown_duration: int = 0  # 回撤持续时间（天）
    current_drawdown: float = 0.0  # 当前回撤
    win_streak: int = 0  # 连续盈利次数
    loss_streak: int = 0  # 连续亏损次数
    best_trade: float = 0.0  # 最佳交易
    worst_trade: float = 0.0  # 最差交易
    avg_holding_period: float = 0.0  # 平均持仓时间（小时）


@dataclass
class MarketDataStatus:
    """市场数据状态"""
    symbol: str
    last_price: float
    volume: float
    bid: float
    ask: float
    spread: float
    last_update: float
    data_age: float  # 数据年龄（秒）
    # 新增市场异常检测指标
    price_change_24h: float = 0.0  # 24小时价格变化百分比
    volume_change_24h: float = 0.0  # 24小时交易量变化百分比
    volatility_24h: float = 0.0  # 24小时波动率
    price_momentum: float = 0.0  # 价格动量
    volume_momentum: float = 0.0  # 交易量动量
    order_book_depth: float = 0.0  # 订单簿深度
    liquidity_score: float = 0.0  # 流动性评分
    market_regime: str = "normal"  # 市场状态：normal, trending, volatile, sideways
    anomaly_score: float = 0.0  # 异常评分


@dataclass
class RiskMetrics:
    """风险指标"""
    portfolio_value: float
    total_exposure: float
    var_95: float  # 95% VaR
    max_position_size: float
    leverage_used: float
    margin_level: float
    last_update: float


@dataclass
class TradingAlert:
    """交易告警"""
    alert_id: str
    timestamp: float
    severity: AlertSeverity
    alert_type: str
    message: str
    details: Dict[str, Any]
    resolved: bool = False


class TradingMonitor:
    """交易专用监控器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化交易监控器"""
        self.config = config
        self.enabled = False
        self.trade_executions: Dict[str, TradeExecution] = {}
        self.strategy_performance: Dict[str, StrategyPerformance] = {}
        self.market_data_status: Dict[str, MarketDataStatus] = {}
        self.risk_metrics: Optional[RiskMetrics] = None
        self.alerts: List[TradingAlert] = []
        self.alert_history: List[TradingAlert] = []
        self.monitoring_interval = config.get("monitoring_interval", 5)  # 秒
        self.max_alert_history = config.get("max_alert_history", 1000)
        self.max_trade_history = config.get("max_trade_history", 1000)
        self.risk_thresholds = config.get("risk_thresholds", {
            "max_drawdown": 10.0,  # 百分比
            "max_leverage": 5.0,
            "min_margin_level": 1.5,
            "max_position_size": 0.3,  # 占总资金的比例
            "max_var": 5.0  # 百分比
        })
        self.market_data_thresholds = config.get("market_data_thresholds", {
            "max_data_age": 30,  # 秒
            "max_spread": 0.5,  # 百分比
            "min_volume": 1000  # USD
        })
        self.order_thresholds = config.get("order_thresholds", {
            "max_pending_time": 300,  # 秒
            "min_fill_rate": 0.8  # 80%
        })
    
    async def initialize(self) -> bool:
        """初始化交易监控器"""
        try:
            # 启动监控循环
            asyncio.create_task(self._monitoring_loop())
            self.enabled = True
            logger.info("TradingMonitor initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize TradingMonitor: {e}")
            return False
    
    async def shutdown(self) -> bool:
        """关闭交易监控器"""
        try:
            self.enabled = False
            self.trade_executions.clear()
            self.alerts.clear()
            logger.info("TradingMonitor shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown TradingMonitor: {e}")
            return False
    
    async def _monitoring_loop(self):
        """监控循环"""
        while self.enabled:
            try:
                # 检查订单状态
                await self._check_orders()
                
                # 检查市场数据状态
                await self._check_market_data()
                
                # 检查风险指标
                await self._check_risk_metrics()
                
                # 检查策略性能
                await self._check_strategy_performance()
            except Exception as e:
                logger.error(f"Error in trading monitoring loop: {e}")
            
            await asyncio.sleep(self.monitoring_interval)
    
    def add_trade_execution(self, trade: TradeExecution):
        """添加交易执行记录"""
        self.trade_executions[trade.order_id] = trade
        
        # 限制交易记录数量
        if len(self.trade_executions) > self.max_trade_history:
            # 删除最早的记录
            oldest_order_id = next(iter(self.trade_executions))
            del self.trade_executions[oldest_order_id]
    
    def update_trade_execution(self, order_id: str, status: OrderStatus, 
                             executed_quantity: float = None, 
                             avg_price: float = None):
        """更新交易执行记录"""
        if order_id in self.trade_executions:
            trade = self.trade_executions[order_id]
            trade.status = status
            if executed_quantity is not None:
                trade.executed_quantity = executed_quantity
            if avg_price is not None:
                trade.avg_price = avg_price
    
    def update_strategy_performance(self, strategy_name: str, performance: StrategyPerformance):
        """更新策略性能"""
        self.strategy_performance[strategy_name] = performance
    
    def update_market_data(self, symbol: str, last_price: float, volume: float, 
                          bid: float, ask: float, price_change_24h: float = 0.0, 
                          volume_change_24h: float = 0.0, volatility_24h: float = 0.0, 
                          price_momentum: float = 0.0, volume_momentum: float = 0.0, 
                          order_book_depth: float = 0.0, liquidity_score: float = 0.0, 
                          market_regime: str = "normal", anomaly_score: float = 0.0):
        """更新市场数据"""
        spread = ((ask - bid) / bid) * 100 if bid > 0 else 0
        self.market_data_status[symbol] = MarketDataStatus(
            symbol=symbol,
            last_price=last_price,
            volume=volume,
            bid=bid,
            ask=ask,
            spread=spread,
            last_update=time.time(),
            data_age=0,
            # 新增市场异常检测指标
            price_change_24h=price_change_24h,
            volume_change_24h=volume_change_24h,
            volatility_24h=volatility_24h,
            price_momentum=price_momentum,
            volume_momentum=volume_momentum,
            order_book_depth=order_book_depth,
            liquidity_score=liquidity_score,
            market_regime=market_regime,
            anomaly_score=anomaly_score
        )
    
    def update_risk_metrics(self, risk_metrics: RiskMetrics):
        """更新风险指标"""
        self.risk_metrics = risk_metrics
    
    async def _check_orders(self):
        """检查订单状态"""
        current_time = time.time()
        
        for order_id, trade in list(self.trade_executions.items()):
            # 检查订单是否长时间处于待处理状态
            if trade.status == OrderStatus.PENDING:
                pending_time = current_time - trade.timestamp
                if pending_time > self.order_thresholds["max_pending_time"]:
                    await self._generate_trading_alert(
                        AlertSeverity.WARNING,
                        "order_pending_timeout",
                        f"Order {order_id} has been pending for {pending_time:.1f} seconds",
                        {
                            "order_id": order_id,
                            "symbol": trade.symbol,
                            "pending_time": pending_time
                        }
                    )
            
            # 检查订单填充率
            if trade.status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED]:
                fill_rate = trade.executed_quantity / trade.quantity
                if fill_rate < self.order_thresholds["min_fill_rate"]:
                    await self._generate_trading_alert(
                        AlertSeverity.INFO,
                        "low_fill_rate",
                        f"Order {order_id} has low fill rate: {fill_rate:.2f}",
                        {
                            "order_id": order_id,
                            "symbol": trade.symbol,
                            "fill_rate": fill_rate
                        }
                    )
    
    async def _check_market_data(self):
        """检查市场数据状态"""
        current_time = time.time()
        
        for symbol, market_data in list(self.market_data_status.items()):
            # 计算数据年龄
            market_data.data_age = current_time - market_data.last_update
            
            # 检查数据是否过期
            if market_data.data_age > self.market_data_thresholds["max_data_age"]:
                await self._generate_trading_alert(
                    AlertSeverity.WARNING,
                    "stale_market_data",
                    f"Market data for {symbol} is stale: {market_data.data_age:.1f} seconds",
                    {
                        "symbol": symbol,
                        "data_age": market_data.data_age
                    }
                )
            
            # 检查点差是否过大
            if market_data.spread > self.market_data_thresholds["max_spread"]:
                await self._generate_trading_alert(
                    AlertSeverity.INFO,
                    "high_spread",
                    f"High spread for {symbol}: {market_data.spread:.2f}%",
                    {
                        "symbol": symbol,
                        "spread": market_data.spread
                    }
                )
            
            # 检查交易量是否过低
            if market_data.volume < self.market_data_thresholds["min_volume"]:
                await self._generate_trading_alert(
                    AlertSeverity.INFO,
                    "low_volume",
                    f"Low volume for {symbol}: {market_data.volume:.2f}",
                    {
                        "symbol": symbol,
                        "volume": market_data.volume
                    }
                )
    
    async def _check_risk_metrics(self):
        """检查风险指标"""
        if not self.risk_metrics:
            return
        
        # 检查最大回撤
        if self.risk_metrics.max_drawdown > self.risk_thresholds["max_drawdown"]:
            await self._generate_trading_alert(
                AlertSeverity.ERROR,
                "high_drawdown",
                f"High drawdown: {self.risk_metrics.max_drawdown:.2f}%",
                {
                    "max_drawdown": self.risk_metrics.max_drawdown
                }
            )
        
        # 检查杠杆使用
        if self.risk_metrics.leverage_used > self.risk_thresholds["max_leverage"]:
            await self._generate_trading_alert(
                AlertSeverity.WARNING,
                "high_leverage",
                f"High leverage: {self.risk_metrics.leverage_used}x",
                {
                    "leverage": self.risk_metrics.leverage_used
                }
            )
        
        # 检查保证金水平
        if self.risk_metrics.margin_level < self.risk_thresholds["min_margin_level"]:
            await self._generate_trading_alert(
                AlertSeverity.CRITICAL,
                "low_margin",
                f"Low margin level: {self.risk_metrics.margin_level}x",
                {
                    "margin_level": self.risk_metrics.margin_level
                }
            )
        
        # 检查仓位大小
        if self.risk_metrics.max_position_size > self.risk_thresholds["max_position_size"]:
            await self._generate_trading_alert(
                AlertSeverity.WARNING,
                "large_position",
                f"Large position size: {self.risk_metrics.max_position_size:.2f}",
                {
                    "position_size": self.risk_metrics.max_position_size
                }
            )
        
        # 检查VaR
        if self.risk_metrics.var_95 > self.risk_thresholds["max_var"]:
            await self._generate_trading_alert(
                AlertSeverity.WARNING,
                "high_var",
                f"High VaR: {self.risk_metrics.var_95:.2f}%",
                {
                    "var_95": self.risk_metrics.var_95
                }
            )
    
    async def _check_strategy_performance(self):
        """检查策略性能"""
        for strategy_name, performance in self.strategy_performance.items():
            # 检查胜率
            if performance.win_rate < 0.4:
                await self._generate_trading_alert(
                    AlertSeverity.INFO,
                    "low_win_rate",
                    f"Low win rate for {strategy_name}: {performance.win_rate:.2f}",
                    {
                        "strategy": strategy_name,
                        "win_rate": performance.win_rate
                    }
                )
            
            # 检查夏普比率
            if performance.sharpe_ratio < 0.5:
                await self._generate_trading_alert(
                    AlertSeverity.INFO,
                    "low_sharpe",
                    f"Low Sharpe ratio for {strategy_name}: {performance.sharpe_ratio:.2f}",
                    {
                        "strategy": strategy_name,
                        "sharpe_ratio": performance.sharpe_ratio
                    }
                )
    
    async def _generate_trading_alert(self, severity: AlertSeverity, alert_type: str, 
                                    message: str, details: Dict[str, Any]):
        """生成交易告警"""
        alert_id = f"alert_{int(time.time())}_{alert_type}"
        alert = TradingAlert(
            alert_id=alert_id,
            timestamp=time.time(),
            severity=severity,
            alert_type=alert_type,
            message=message,
            details=details
        )
        
        self.alerts.append(alert)
        self.alert_history.append(alert)
        
        # 限制告警历史大小
        if len(self.alert_history) > self.max_alert_history:
            self.alert_history = self.alert_history[-self.max_alert_history:]
        
        logger.warning(f"Trading Alert [{severity.value}]: {message}")
    
    def get_active_alerts(self) -> List[TradingAlert]:
        """获取活跃告警"""
        return [alert for alert in self.alerts if not alert.resolved]
    
    def get_alert_history(self, limit: int = 50) -> List[TradingAlert]:
        """获取告警历史"""
        return self.alert_history[-limit:]
    
    def resolve_alert(self, alert_id: str):
        """解决告警"""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                self.alerts.remove(alert)
                break
    
    def get_trade_history(self, limit: int = 50) -> List[TradeExecution]:
        """获取交易历史"""
        trades = list(self.trade_executions.values())
        trades.sort(key=lambda x: x.timestamp, reverse=True)
        return trades[:limit]
    
    def get_strategy_performance(self) -> Dict[str, StrategyPerformance]:
        """获取策略性能"""
        return self.strategy_performance
    
    def get_market_data_status(self) -> Dict[str, MarketDataStatus]:
        """获取市场数据状态"""
        return self.market_data_status
    
    def get_risk_metrics(self) -> Optional[RiskMetrics]:
        """获取风险指标"""
        return self.risk_metrics
    
    def get_monitoring_summary(self) -> Dict[str, Any]:
        """获取监控摘要"""
        active_alerts = self.get_active_alerts()
        alert_counts = {
            "info": 0,
            "warning": 0,
            "error": 0,
            "critical": 0
        }
        
        for alert in active_alerts:
            alert_counts[alert.severity.value] += 1
        
        return {
            "timestamp": time.time(),
            "active_alerts": len(active_alerts),
            "alert_counts": alert_counts,
            "total_trades": len(self.trade_executions),
            "strategies": list(self.strategy_performance.keys()),
            "symbols": list(self.market_data_status.keys()),
            "risk_metrics": self.risk_metrics.__dict__ if self.risk_metrics else None
        }

    async def cleanup(self):
        """清理资源"""
        pass
