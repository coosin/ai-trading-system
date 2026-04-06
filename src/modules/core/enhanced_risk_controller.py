"""
增强风险控制系统

为无人化AI交易系统提供全面的风险控制和熔断机制
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CircuitBreakerStatus(str, Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常
    OPEN = "open"          # 熔断
    HALF_OPEN = "half_open"  # 半开


@dataclass
class RiskLimit:
    """风险限制"""
    max_daily_trades: int = 20
    max_hourly_trades: int = 5
    max_consecutive_losses: int = 3
    max_drawdown_percent: float = 0.15
    max_position_risk: float = 0.02
    max_leverage: float = 3.0
    min_time_between_trades: int = 300  # 秒
    max_position_hold_time: int = 86400  # 秒


@dataclass
class TradingState:
    """交易状态"""
    daily_trade_count: int = 0
    hourly_trade_count: int = 0
    consecutive_losses: int = 0
    current_drawdown: float = 0.0
    total_pnl: float = 0.0
    daily_pnl: float = 0.0
    last_trade_time: Optional[datetime] = None
    positions: Dict[str, Any] = field(default_factory=dict)


class EnhancedRiskController:
    """增强风险控制器"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.risk_limits = RiskLimit()
        
        # 交易状态
        self.trading_state = TradingState()
        
        # 熔断器
        self.circuit_breaker = {
            "status": CircuitBreakerStatus.CLOSED,
            "trigger_reason": None,
            "trigger_time": None,
            "auto_resume_time": None,
        }
        
        # 风险历史
        self.risk_history: List[Dict] = []
        
        # 告警回调
        self.alert_callbacks: List[callable] = []
        
        # 统计
        self.stats = {
            "total_checks": 0,
            "violations": 0,
            "circuit_breaker_triggers": 0,
        }
    
    async def initialize(self) -> bool:
        """初始化模块"""
        logger.info("初始化增强风险控制器...")
        return True
    
    async def cleanup(self):
        """清理资源"""
        logger.info("清理增强风险控制器...")
        pass
    
    async def initialize(self) -> bool:
        """初始化模块"""
        logger.info("初始化增强风险控制器...")
        return True
    
    async def cleanup(self):
        """清理资源"""
        logger.info("清理增强风险控制器...")
        pass
    
    async def check_pre_trade_risk(
        self,
        symbol: str,
        action: str,
        quantity: float,
        price: float
    ) -> Dict[str, Any]:
        """交易前风险检查"""
        
        self.stats["total_checks"] += 1
        
        result = {
            "allowed": True,
            "risk_level": RiskLevel.LOW,
            "violations": [],
            "warnings": [],
            "recommendations": []
        }
        
        if not await self._check_circuit_breaker():
            result["warnings"].append("熔断器已触发，AI自主评估是否继续")
            result["risk_level"] = RiskLevel.CRITICAL
        
        if not await self._check_trade_frequency():
            result["warnings"].append("交易频率较高")
        
        if not await self._check_consecutive_losses():
            result["warnings"].append(f"连续亏损{self.trading_state.consecutive_losses}次，AI自主评估")
        
        if not await self._check_drawdown():
            result["warnings"].append(f"当前回撤{self.trading_state.current_drawdown:.2%}，AI自主评估")
        
        position_risk = await self._calculate_position_risk(symbol, quantity, price)
        if position_risk > self.risk_limits.max_position_risk:
            result["warnings"].append(f"仓位风险{position_risk:.2%}，AI自主评估")
        
        if not await self._check_trade_interval():
            result["warnings"].append("交易间隔较短")
        
        if result["warnings"]:
            result["risk_level"] = RiskLevel.MEDIUM
            logger.info(f"📊 风险提示: {result['warnings']}，AI自主决策")
        
        result["allowed"] = True
        logger.info(f"✅ AI自主风险检查通过")
        
        await self._record_risk_check(result)
        
        return result
    
    async def _check_circuit_breaker(self) -> bool:
        """检查熔断器"""
        
        if self.circuit_breaker["status"] == CircuitBreakerStatus.CLOSED:
            return True
        
        if self.circuit_breaker["status"] == CircuitBreakerStatus.OPEN:
            # 检查是否可以进入半开状态
            if datetime.now() >= self.circuit_breaker["auto_resume_time"]:
                self.circuit_breaker["status"] = CircuitBreakerStatus.HALF_OPEN
                logger.info("熔断器进入半开状态")
                return True
            return False
        
        # 半开状态允许有限交易
        return True
    
    async def _check_trade_frequency(self) -> bool:
        """检查交易频率"""
        
        now = datetime.now()
        
        # 检查日内交易次数
        if self.trading_state.daily_trade_count >= self.risk_limits.max_daily_trades:
            logger.warning(f"日内交易次数超限: {self.trading_state.daily_trade_count}")
            return False
        
        # 检查小时交易次数
        if self.trading_state.hourly_trade_count >= self.risk_limits.max_hourly_trades:
            logger.warning(f"小时交易次数超限: {self.trading_state.hourly_trade_count}")
            return False
        
        return True
    
    async def _check_consecutive_losses(self) -> bool:
        """检查连续亏损"""
        
        if self.trading_state.consecutive_losses >= self.risk_limits.max_consecutive_losses:
            logger.warning(f"连续亏损次数: {self.trading_state.consecutive_losses}")
            await self._trigger_circuit_breaker("连续亏损超限")
            return False
        
        return True
    
    async def _check_drawdown(self) -> bool:
        """检查回撤"""
        
        if self.trading_state.current_drawdown >= self.risk_limits.max_drawdown_percent:
            logger.warning(f"当前回撤: {self.trading_state.current_drawdown:.2%}")
            await self._trigger_circuit_breaker("回撤超限")
            return False
        
        return True
    
    async def _check_trade_interval(self) -> bool:
        """检查交易间隔"""
        
        if self.trading_state.last_trade_time:
            elapsed = (datetime.now() - self.trading_state.last_trade_time).total_seconds()
            
            if elapsed < self.risk_limits.min_time_between_trades:
                logger.warning(f"交易间隔过短: {elapsed:.0f}秒")
                return False
        
        return True
    
    async def _calculate_position_risk(
        self,
        symbol: str,
        quantity: float,
        price: float
    ) -> float:
        """计算仓位风险"""
        
        # 简化计算：仓位价值 / 账户总资金
        position_value = quantity * price
        
        # 这里应该从账户获取总资金
        total_capital = 10000.0  # 示例值
        
        return position_value / total_capital
    
    async def _trigger_circuit_breaker(self, reason: str):
        """触发熔断器"""
        
        self.circuit_breaker["status"] = CircuitBreakerStatus.OPEN
        self.circuit_breaker["trigger_reason"] = reason
        self.circuit_breaker["trigger_time"] = datetime.now()
        self.circuit_breaker["auto_resume_time"] = datetime.now() + timedelta(minutes=30)
        
        self.stats["circuit_breaker_triggers"] += 1
        
        logger.critical(f"🚨 熔断器触发: {reason}")
        
        # 发送告警
        for callback in self.alert_callbacks:
            try:
                await callback(
                    level="critical",
                    type="circuit_breaker",
                    message=f"熔断器触发: {reason}"
                )
            except Exception as e:
                logger.error(f"告警回调失败: {e}")
    
    async def update_trade_result(self, trade_result: Dict[str, Any]):
        """更新交易结果"""
        
        # 更新交易计数
        self.trading_state.daily_trade_count += 1
        self.trading_state.hourly_trade_count += 1
        self.trading_state.last_trade_time = datetime.now()
        
        # 更新盈亏
        pnl = trade_result.get("pnl", 0)
        self.trading_state.total_pnl += pnl
        self.trading_state.daily_pnl += pnl
        
        # 更新连续亏损
        if pnl < 0:
            self.trading_state.consecutive_losses += 1
        else:
            self.trading_state.consecutive_losses = 0
        
        # 更新回撤
        await self._update_drawdown()
        
        logger.info(
            f"交易结果更新 - 日内交易: {self.trading_state.daily_trade_count}, "
            f"连续亏损: {self.trading_state.consecutive_losses}, "
            f"日盈亏: {self.trading_state.daily_pnl:.2f}"
        )
    
    async def _update_drawdown(self):
        """更新回撤"""
        
        # 简化计算
        # 实际应该基于权益曲线计算
        if self.trading_state.daily_pnl < 0:
            self.trading_state.current_drawdown = abs(self.trading_state.daily_pnl) / 10000.0
    
    async def _record_risk_check(self, result: Dict):
        """记录风险检查"""
        
        record = {
            "timestamp": datetime.now().isoformat(),
            "result": result,
            "state": {
                "daily_trades": self.trading_state.daily_trade_count,
                "consecutive_losses": self.trading_state.consecutive_losses,
                "drawdown": self.trading_state.current_drawdown,
            }
        }
        
        self.risk_history.append(record)
        
        # 保持最近1000条记录
        if len(self.risk_history) > 1000:
            self.risk_history.pop(0)
    
    def add_alert_callback(self, callback: callable):
        """添加告警回调"""
        self.alert_callbacks.append(callback)
    
    async def reset_daily_counters(self):
        """重置日内计数器"""
        
        self.trading_state.daily_trade_count = 0
        self.trading_state.daily_pnl = 0.0
        
        logger.info("日内计数器已重置")
    
    async def reset_hourly_counters(self):
        """重置小时计数器"""
        
        self.trading_state.hourly_trade_count = 0
        
        logger.info("小时计数器已重置")
    
    def get_risk_status(self) -> Dict[str, Any]:
        """获取风险状态"""
        
        return {
            "circuit_breaker": {
                "status": self.circuit_breaker["status"].value,
                "trigger_reason": self.circuit_breaker["trigger_reason"],
                "trigger_time": self.circuit_breaker["trigger_time"].isoformat() if self.circuit_breaker["trigger_time"] else None,
            },
            "trading_state": {
                "daily_trades": self.trading_state.daily_trade_count,
                "hourly_trades": self.trading_state.hourly_trade_count,
                "consecutive_losses": self.trading_state.consecutive_losses,
                "current_drawdown": f"{self.trading_state.current_drawdown:.2%}",
                "daily_pnl": self.trading_state.daily_pnl,
            },
            "risk_limits": {
                "max_daily_trades": self.risk_limits.max_daily_trades,
                "max_hourly_trades": self.risk_limits.max_hourly_trades,
                "max_consecutive_losses": self.risk_limits.max_consecutive_losses,
                "max_drawdown": f"{self.risk_limits.max_drawdown_percent:.2%}",
            },
            "stats": self.stats,
        }
    
    async def manual_reset_circuit_breaker(self):
        """手动重置熔断器"""
        
        self.circuit_breaker["status"] = CircuitBreakerStatus.CLOSED
        self.circuit_breaker["trigger_reason"] = None
        self.circuit_breaker["trigger_time"] = None
        self.circuit_breaker["auto_resume_time"] = None
        
        logger.info("熔断器已手动重置")

    async def check_position_risk(self, positions: Dict[str, Any], exchange=None) -> Dict[str, Any]:
        """
        检查持仓风险并返回需要采取的行动
        
        Args:
            positions: 当前持仓字典
            exchange: 交易所实例（用于执行平仓）
        
        Returns:
            风险检查结果和需要采取的行动
        """
        result = {
            "risk_level": RiskLevel.LOW,
            "positions_at_risk": [],
            "actions_required": [],
            "total_unrealized_pnl": 0.0,
            "total_margin_ratio": 0.0,
        }
        
        if not positions:
            return result
        
        total_pnl = 0.0
        critical_positions = []
        high_risk_positions = []
        
        for symbol, pos in positions.items():
            pnl_percent = pos.get("unrealized_pnl_percent", 0)
            margin_ratio = pos.get("margin_ratio", 0)
            liquidation_price = pos.get("liquidation_price", 0)
            current_price = pos.get("current_price", 0)
            
            total_pnl += pos.get("unrealized_pnl", 0)
            
            if margin_ratio > 0:
                result["total_margin_ratio"] = max(result["total_margin_ratio"], margin_ratio)
            
            if pnl_percent < -0.10 or margin_ratio > 0.8:
                critical_positions.append({
                    "symbol": symbol,
                    "pnl_percent": pnl_percent,
                    "margin_ratio": margin_ratio,
                    "action": "emergency_close",
                    "reason": f"严重风险: 亏损{pnl_percent*100:.1f}%, 保证金率{margin_ratio*100:.1f}%"
                })
            elif pnl_percent < -0.05 or margin_ratio > 0.6:
                high_risk_positions.append({
                    "symbol": symbol,
                    "pnl_percent": pnl_percent,
                    "margin_ratio": margin_ratio,
                    "action": "reduce_position",
                    "reason": f"高风险: 亏损{pnl_percent*100:.1f}%, 保证金率{margin_ratio*100:.1f}%"
                })
        
        result["total_unrealized_pnl"] = total_pnl
        result["positions_at_risk"] = critical_positions + high_risk_positions
        
        if critical_positions:
            result["risk_level"] = RiskLevel.CRITICAL
            result["actions_required"].append({
                "type": "emergency_close",
                "positions": [p["symbol"] for p in critical_positions],
                "reason": "存在严重风险持仓，需要立即平仓"
            })
        elif high_risk_positions:
            result["risk_level"] = RiskLevel.HIGH
            result["actions_required"].append({
                "type": "reduce_position",
                "positions": high_risk_positions,
                "reason": "存在高风险持仓，建议减仓"
            })
        
        if result["risk_level"] in [RiskLevel.CRITICAL, RiskLevel.HIGH]:
            logger.warning(f"⚠️ 持仓风险检查: {result['risk_level'].value} - {len(result['positions_at_risk'])}个持仓需要关注")
        
        return result

    async def auto_reduce_positions(
        self, 
        positions: List[Dict], 
        exchange,
        reduce_ratio: float = 0.5
    ) -> Dict[str, Any]:
        """
        自动减仓
        
        Args:
            positions: 需要减仓的持仓列表
            exchange: 交易所实例
            reduce_ratio: 减仓比例
        
        Returns:
            减仓结果
        """
        results = []
        
        for pos in positions:
            symbol = pos.get("symbol")
            try:
                current_qty = pos.get("quantity", 0)
                reduce_qty = current_qty * reduce_ratio
                
                if reduce_qty > 0:
                    side = "sell" if pos.get("side") == "long" else "buy"
                    
                    logger.warning(f"🔄 自动减仓: {symbol} {side} {reduce_qty}")
                    
                    if exchange and hasattr(exchange, 'place_order'):
                        order = await exchange.place_order(
                            symbol=symbol,
                            side=side,
                            order_type="market",
                            quantity=reduce_qty,
                            reduce_only=True
                        )
                        results.append({
                            "symbol": symbol,
                            "success": True,
                            "order": order
                        })
                    else:
                        results.append({
                            "symbol": symbol,
                            "success": False,
                            "error": "交易所不可用"
                        })
            except Exception as e:
                logger.error(f"减仓失败 {symbol}: {e}")
                results.append({
                    "symbol": symbol,
                    "success": False,
                    "error": str(e)
                })
        
        return {
            "action": "auto_reduce",
            "timestamp": datetime.now().isoformat(),
            "results": results
        }

    async def emergency_close_all(
        self, 
        positions: Dict[str, Any], 
        exchange,
        reason: str = "风险控制"
    ) -> Dict[str, Any]:
        """
        紧急平仓所有持仓
        
        Args:
            positions: 所有持仓
            exchange: 交易所实例
            reason: 平仓原因
        
        Returns:
            平仓结果
        """
        logger.critical(f"🚨 紧急平仓触发: {reason}")
        
        results = []
        
        for symbol, pos in positions.items():
            try:
                quantity = pos.get("quantity", 0)
                side = "sell" if pos.get("side") == "long" else "buy"
                
                if quantity > 0 and exchange and hasattr(exchange, 'place_order'):
                    order = await exchange.place_order(
                        symbol=symbol,
                        side=side,
                        order_type="market",
                        quantity=quantity,
                        reduce_only=True
                    )
                    results.append({
                        "symbol": symbol,
                        "success": True,
                        "order": order
                    })
                    logger.info(f"✅ 紧急平仓成功: {symbol}")
            except Exception as e:
                logger.error(f"紧急平仓失败 {symbol}: {e}")
                results.append({
                    "symbol": symbol,
                    "success": False,
                    "error": str(e)
                })
        
        await self._trigger_circuit_breaker(f"紧急平仓: {reason}")
        
        return {
            "action": "emergency_close_all",
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "results": results
        }

    async def get_risk_report(self) -> Dict[str, Any]:
        """获取详细风险报告"""
        return {
            "timestamp": datetime.now().isoformat(),
            "circuit_breaker": {
                "status": self.circuit_breaker["status"].value,
                "trigger_reason": self.circuit_breaker["trigger_reason"],
                "trigger_time": self.circuit_breaker["trigger_time"].isoformat() if self.circuit_breaker["trigger_time"] else None,
                "auto_resume_time": self.circuit_breaker["auto_resume_time"].isoformat() if self.circuit_breaker["auto_resume_time"] else None,
            },
            "trading_state": {
                "daily_trades": self.trading_state.daily_trade_count,
                "hourly_trades": self.trading_state.hourly_trade_count,
                "consecutive_losses": self.trading_state.consecutive_losses,
                "current_drawdown": f"{self.trading_state.current_drawdown:.2%}",
                "daily_pnl": self.trading_state.daily_pnl,
                "total_pnl": self.trading_state.total_pnl,
            },
            "risk_limits": {
                "max_daily_trades": self.risk_limits.max_daily_trades,
                "max_hourly_trades": self.risk_limits.max_hourly_trades,
                "max_consecutive_losses": self.risk_limits.max_consecutive_losses,
                "max_drawdown": f"{self.risk_limits.max_drawdown_percent:.2%}",
                "max_leverage": self.risk_limits.max_leverage,
            },
            "stats": self.stats,
            "recent_risk_events": self.risk_history[-10:] if self.risk_history else [],
        }
