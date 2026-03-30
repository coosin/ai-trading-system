"""
增强型风险管理器 - 实时风险监控和预警

功能：
1. 实时风险指标计算（VaR、CVaR、夏普比率等）
2. 多维度风险监控（市场、信用、操作、流动性）
3. 风险预警和自动风控
4. 压力测试和情景分析
5. 风险报告生成
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Callable
from collections import deque

logger = logging.getLogger(__name__)


class RiskType(Enum):
    """风险类型"""
    MARKET = "market"           # 市场风险
    CREDIT = "credit"           # 信用风险
    OPERATIONAL = "operational" # 操作风险
    LIQUIDITY = "liquidity"     # 流动性风险
    CONCENTRATION = "concentration"  # 集中度风险


class RiskLevel(Enum):
    """风险等级"""
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


class RiskAction(Enum):
    """风控动作"""
    NOTIFY = "notify"           # 通知
    WARN = "warn"               # 警告
    REDUCE_POSITION = "reduce"  # 减仓
    LIQUIDATE = "liquidate"     # 平仓
    BLOCK_TRADING = "block"     # 禁止交易


@dataclass
class RiskThreshold:
    """风险阈值配置"""
    risk_type: RiskType
    warning_level: float        # 警告阈值
    danger_level: float         # 危险阈值
    critical_level: float       # 临界阈值
    action: RiskAction          # 触发动作
    auto_execute: bool = False  # 是否自动执行


@dataclass
class RiskMetric:
    """风险指标"""
    name: str
    value: float
    risk_type: RiskType
    level: RiskLevel
    threshold: float
    timestamp: datetime
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskAlert:
    """风险告警"""
    alert_id: str
    risk_type: RiskType
    level: RiskLevel
    message: str
    metrics: List[RiskMetric]
    timestamp: datetime
    acknowledged: bool = False
    resolved: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class PositionRisk:
    """持仓风险"""
    symbol: str
    quantity: float
    avg_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    var_95: float              # 95% VaR
    var_99: float              # 99% VaR
    beta: float                # Beta系数
    correlation: float         # 相关性
    concentration_pct: float   # 集中度百分比


@dataclass
class PortfolioRisk:
    """组合风险"""
    total_value: float
    total_exposure: float
    net_exposure: float
    gross_exposure: float
    var_95: float
    var_99: float
    cvar_95: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    beta: float
    correlation_matrix: pd.DataFrame
    position_risks: List[PositionRisk]
    timestamp: datetime


class EnhancedRiskManager:
    """
    增强型风险管理器
    
    功能：
    1. 实时风险计算和监控
    2. 多维度风险评估
    3. 自动风控措施
    4. 风险报告生成
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # 风险阈值配置
        self.thresholds: Dict[RiskType, RiskThreshold] = {}
        self._init_default_thresholds()
        
        # 风险数据缓存
        self.price_history: Dict[str, deque] = {}
        self.returns_history: Dict[str, deque] = {}
        self.position_risks: Dict[str, PositionRisk] = {}
        self.portfolio_risk: Optional[PortfolioRisk] = None
        
        # 告警管理
        self.active_alerts: Dict[str, RiskAlert] = {}
        self.alert_history: List[RiskAlert] = []
        self._alert_callbacks: List[Callable] = []
        
        # 风控状态
        self.trading_blocked: bool = False
        self.block_reason: Optional[str] = None
        self.risk_reduction_active: bool = False
        
        # 统计
        self.risk_metrics_history: deque = deque(maxlen=1000)
        
        self._initialized = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False
    
    def _init_default_thresholds(self):
        """初始化默认阈值"""
        self.thresholds[RiskType.MARKET] = RiskThreshold(
            risk_type=RiskType.MARKET,
            warning_level=0.02,      # 2%日回撤
            danger_level=0.05,       # 5%日回撤
            critical_level=0.10,     # 10%日回撤
            action=RiskAction.REDUCE_POSITION,
            auto_execute=False
        )
        
        self.thresholds[RiskType.CONCENTRATION] = RiskThreshold(
            risk_type=RiskType.CONCENTRATION,
            warning_level=0.20,      # 20%单品种
            danger_level=0.30,       # 30%单品种
            critical_level=0.50,     # 50%单品种
            action=RiskAction.REDUCE_POSITION,
            auto_execute=True
        )
        
        self.thresholds[RiskType.LIQUIDITY] = RiskThreshold(
            risk_type=RiskType.LIQUIDITY,
            warning_level=0.10,      # 10%日成交量
            danger_level=0.20,       # 20%日成交量
            critical_level=0.30,     # 30%日成交量
            action=RiskAction.WARN,
            auto_execute=False
        )
    
    async def initialize(self):
        """初始化风险管理器"""
        logger.info("初始化增强型风险管理器...")
        self._running = True
        self._initialized = True
        
        # 启动风险监控任务
        self._monitoring_task = asyncio.create_task(self._risk_monitoring_loop())
        
        logger.info("增强型风险管理器初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        logger.info("清理风险管理器...")
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("风险管理器清理完成")
    
    async def _risk_monitoring_loop(self):
        """风险监控循环"""
        logger.info("启动风险监控循环")
        
        while self._running:
            try:
                # 每5秒检查一次风险
                await asyncio.sleep(5)
                
                # 计算组合风险
                await self._calculate_portfolio_risk()
                
                # 检查风险阈值
                await self._check_risk_thresholds()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"风险监控循环出错: {e}")
    
    async def update_price(self, symbol: str, price: float, timestamp: datetime = None):
        """更新价格数据"""
        if timestamp is None:
            timestamp = datetime.now()
        
        # 初始化历史数据
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=252)  # 保留1年数据
            self.returns_history[symbol] = deque(maxlen=251)
        
        # 计算收益率
        if len(self.price_history[symbol]) > 0:
            last_price = self.price_history[symbol][-1]
            returns = (price - last_price) / last_price
            self.returns_history[symbol].append(returns)
        
        self.price_history[symbol].append(price)
    
    async def update_position(self, symbol: str, quantity: float, avg_price: float, current_price: float):
        """更新持仓信息"""
        market_value = quantity * current_price
        unrealized_pnl = quantity * (current_price - avg_price)
        unrealized_pnl_pct = (current_price - avg_price) / avg_price if avg_price > 0 else 0
        
        # 计算VaR
        var_95 = await self._calculate_var(symbol, 0.95)
        var_99 = await self._calculate_var(symbol, 0.99)
        
        # 计算Beta（简化计算）
        beta = await self._calculate_beta(symbol)
        
        position_risk = PositionRisk(
            symbol=symbol,
            quantity=quantity,
            avg_price=avg_price,
            current_price=current_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            var_95=var_95,
            var_99=var_99,
            beta=beta,
            correlation=0.0,  # 稍后计算
            concentration_pct=0.0  # 稍后计算
        )
        
        self.position_risks[symbol] = position_risk
    
    async def _calculate_var(self, symbol: str, confidence: float = 0.95) -> float:
        """计算VaR（风险价值）"""
        if symbol not in self.returns_history or len(self.returns_history[symbol]) < 30:
            return 0.0
        
        returns = np.array(self.returns_history[symbol])
        var = np.percentile(returns, (1 - confidence) * 100)
        
        # 转换为金额
        if symbol in self.position_risks:
            market_value = self.position_risks[symbol].market_value
            return abs(var * market_value)
        
        return abs(var)
    
    async def _calculate_cvar(self, symbol: str, confidence: float = 0.95) -> float:
        """计算CVaR（条件风险价值）"""
        if symbol not in self.returns_history or len(self.returns_history[symbol]) < 30:
            return 0.0
        
        returns = np.array(self.returns_history[symbol])
        var = np.percentile(returns, (1 - confidence) * 100)
        cvar = returns[returns <= var].mean()
        
        if symbol in self.position_risks:
            market_value = self.position_risks[symbol].market_value
            return abs(cvar * market_value)
        
        return abs(cvar)
    
    async def _calculate_beta(self, symbol: str) -> float:
        """计算Beta系数（简化）"""
        if symbol not in self.returns_history or len(self.returns_history[symbol]) < 30:
            return 1.0
        
        # 简化：假设市场收益率为所有品种的平均
        symbol_returns = np.array(self.returns_history[symbol])
        
        # 这里简化处理，实际应该使用市场指数
        return 1.0
    
    async def _calculate_portfolio_risk(self):
        """计算组合风险"""
        if not self.position_risks:
            return
        
        total_value = sum(p.market_value for p in self.position_risks.values())
        total_exposure = sum(abs(p.market_value) for p in self.position_risks.values())
        net_exposure = sum(p.market_value for p in self.position_risks.values())
        
        # 计算组合VaR（简化：假设独立）
        var_95 = sum(p.var_95 for p in self.position_risks.values())
        var_99 = sum(p.var_99 for p in self.position_risks.values())
        
        # 计算CVaR
        cvar_95 = sum(await self._calculate_cvar(p.symbol, 0.95) for p in self.position_risks.values())
        
        # 更新集中度
        for symbol, position in self.position_risks.items():
            position.concentration_pct = position.market_value / total_value if total_value > 0 else 0
        
        # 创建组合风险对象
        self.portfolio_risk = PortfolioRisk(
            total_value=total_value,
            total_exposure=total_exposure,
            net_exposure=net_exposure,
            gross_exposure=total_exposure,
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            sharpe_ratio=0.0,  # 需要历史数据
            sortino_ratio=0.0,
            max_drawdown=0.0,
            beta=1.0,
            correlation_matrix=pd.DataFrame(),
            position_risks=list(self.position_risks.values()),
            timestamp=datetime.now()
        )
        
        # 保存历史
        self.risk_metrics_history.append({
            'timestamp': datetime.now(),
            'total_value': total_value,
            'var_95': var_95,
            'var_99': var_99
        })
    
    async def _check_risk_thresholds(self):
        """检查风险阈值"""
        if not self.portfolio_risk:
            return
        
        # 检查市场风险（回撤）
        for position in self.portfolio_risk.position_risks:
            if position.unrealized_pnl_pct < -self.thresholds[RiskType.MARKET].warning_level:
                await self._create_alert(
                    RiskType.MARKET,
                    RiskLevel.HIGH if position.unrealized_pnl_pct < -self.thresholds[RiskType.MARKET].danger_level else RiskLevel.MEDIUM,
                    f"品种 {position.symbol} 回撤 {position.unrealized_pnl_pct:.2%}",
                    []
                )
        
        # 检查集中度风险
        for position in self.portfolio_risk.position_risks:
            threshold = self.thresholds[RiskType.CONCENTRATION]
            if position.concentration_pct > threshold.warning_level:
                level = RiskLevel.MEDIUM
                if position.concentration_pct > threshold.critical_level:
                    level = RiskLevel.CRITICAL
                elif position.concentration_pct > threshold.danger_level:
                    level = RiskLevel.HIGH
                
                await self._create_alert(
                    RiskType.CONCENTRATION,
                    level,
                    f"品种 {position.symbol} 集中度 {position.concentration_pct:.2%}",
                    []
                )
                
                # 自动执行风控
                if threshold.auto_execute and level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                    await self._execute_risk_control(threshold.action, position.symbol)
    
    async def _create_alert(self, risk_type: RiskType, level: RiskLevel, message: str, metrics: List[RiskMetric]):
        """创建风险告警"""
        alert_id = f"alert_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.active_alerts)}"
        
        alert = RiskAlert(
            alert_id=alert_id,
            risk_type=risk_type,
            level=level,
            message=message,
            metrics=metrics,
            timestamp=datetime.now()
        )
        
        self.active_alerts[alert_id] = alert
        self.alert_history.append(alert)
        
        logger.warning(f"风险告警 [{level.name}]: {message}")
        
        # 触发回调
        for callback in self._alert_callbacks:
            try:
                await callback(alert)
            except Exception as e:
                logger.error(f"告警回调出错: {e}")
    
    async def _execute_risk_control(self, action: RiskAction, symbol: Optional[str] = None):
        """执行风控措施"""
        if action == RiskAction.BLOCK_TRADING:
            self.trading_blocked = True
            self.block_reason = f"风险过高，自动禁止交易"
            logger.critical(f"执行风控: 禁止交易 - {self.block_reason}")
        
        elif action == RiskAction.REDUCE_POSITION:
            self.risk_reduction_active = True
            logger.warning(f"执行风控: 减仓 - 品种: {symbol}")
        
        elif action == RiskAction.LIQUIDATE:
            logger.critical(f"执行风控: 平仓 - 品种: {symbol}")
    
    def register_alert_callback(self, callback: Callable):
        """注册告警回调"""
        self._alert_callbacks.append(callback)
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """确认告警"""
        if alert_id in self.active_alerts:
            self.active_alerts[alert_id].acknowledged = True
            return True
        return False
    
    async def resolve_alert(self, alert_id: str) -> bool:
        """解决告警"""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.resolved = True
            alert.resolved_at = datetime.now()
            del self.active_alerts[alert_id]
            return True
        return False
    
    def get_portfolio_risk(self) -> Optional[PortfolioRisk]:
        """获取组合风险"""
        return self.portfolio_risk
    
    def get_position_risk(self, symbol: str) -> Optional[PositionRisk]:
        """获取持仓风险"""
        return self.position_risks.get(symbol)
    
    def get_active_alerts(self, risk_type: RiskType = None, level: RiskLevel = None) -> List[RiskAlert]:
        """获取活跃告警"""
        alerts = list(self.active_alerts.values())
        
        if risk_type:
            alerts = [a for a in alerts if a.risk_type == risk_type]
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        return sorted(alerts, key=lambda x: x.timestamp, reverse=True)
    
    def get_risk_report(self) -> Dict[str, Any]:
        """生成风险报告"""
        return {
            "timestamp": datetime.now().isoformat(),
            "portfolio_risk": {
                "total_value": self.portfolio_risk.total_value if self.portfolio_risk else 0,
                "var_95": self.portfolio_risk.var_95 if self.portfolio_risk else 0,
                "var_99": self.portfolio_risk.var_99 if self.portfolio_risk else 0,
                "gross_exposure": self.portfolio_risk.gross_exposure if self.portfolio_risk else 0,
            },
            "position_count": len(self.position_risks),
            "active_alerts": len(self.active_alerts),
            "trading_blocked": self.trading_blocked,
            "block_reason": self.block_reason
        }
    
    async def stress_test(self, scenarios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """压力测试"""
        results = []
        
        for scenario in scenarios:
            name = scenario.get("name", "Unknown")
            price_changes = scenario.get("price_changes", {})
            
            # 计算情景下的组合价值
            portfolio_value = 0
            for symbol, position in self.position_risks.items():
                change = price_changes.get(symbol, 0)
                new_price = position.current_price * (1 + change)
                portfolio_value += position.quantity * new_price
            
            results.append({
                "scenario": name,
                "portfolio_value": portfolio_value,
                "pnl": portfolio_value - (self.portfolio_risk.total_value if self.portfolio_risk else 0),
                "pnl_pct": (portfolio_value / (self.portfolio_risk.total_value if self.portfolio_risk else 1) - 1)
            })
        
        return results
    
    def unblock_trading(self):
        """解除交易禁止"""
        if self.trading_blocked:
            self.trading_blocked = False
            self.block_reason = None
            logger.info("解除交易禁止")


# 全局风险管理器
_risk_manager: Optional[EnhancedRiskManager] = None


async def get_enhanced_risk_manager() -> EnhancedRiskManager:
    """获取风险管理器实例"""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = EnhancedRiskManager()
        await _risk_manager.initialize()
    return _risk_manager
