"""
账户风险监控模块

提供实时账户权益监控、持仓风险预警、强平价格计算等功能
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PositionRisk:
    """持仓风险信息"""
    symbol: str
    side: str
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    liquidation_price: float
    margin: float
    leverage: float
    
    risk_level: RiskLevel = RiskLevel.LOW
    distance_to_liquidation: float = 0.0
    margin_ratio: float = 0.0
    
    warnings: List[str] = field(default_factory=list)


@dataclass
class AccountRisk:
    """账户风险信息"""
    total_equity: float
    available_balance: float
    margin_used: float
    unrealized_pnl: float
    
    margin_ratio: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    
    position_risks: List[PositionRisk] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class AccountRiskMonitor:
    """
    账户风险监控器
    
    功能：
    1. 实时监控账户权益变化
    2. 监控持仓盈亏和风险
    3. 计算强平价格
    4. 风险预警和通知
    """
    
    def __init__(self, exchange=None, data_storage=None):
        self.exchange = exchange
        self.data_storage = data_storage
        
        self._running = False
        self._monitor_task = None
        
        self.risk_config = {
            "margin_ratio_warning": 0.5,
            "margin_ratio_critical": 0.8,
            "unrealized_loss_warning": -0.05,
            "unrealized_loss_critical": -0.10,
            "liquidation_distance_warning": 0.10,
            "liquidation_distance_critical": 0.05,
            "monitor_interval": 10
        }
        
        self._callbacks: List[callable] = []
        self._last_account_risk: Optional[AccountRisk] = None
        
        logger.info("账户风险监控器初始化完成")
    
    async def start(self) -> None:
        """启动监控"""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("✅ 账户风险监控已启动")
    
    async def stop(self) -> None:
        """停止监控"""
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("账户风险监控已停止")
    
    def add_callback(self, callback: callable) -> None:
        """添加风险预警回调"""
        self._callbacks.append(callback)
    
    async def _monitor_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                account_risk = await self.check_account_risk()
                
                if account_risk:
                    self._last_account_risk = account_risk
                    
                    if account_risk.warnings:
                        await self._notify_warnings(account_risk)
                
                await asyncio.sleep(self.risk_config["monitor_interval"])
                
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(5)
    
    async def check_account_risk(self) -> Optional[AccountRisk]:
        """检查账户风险"""
        try:
            if not self.exchange:
                return None
            
            balance = await self.exchange.get_balance()
            positions = await self.exchange.get_positions()
            
            total_equity = balance.get("USDT", {}).get("total", 0) if isinstance(balance.get("USDT"), dict) else balance.get("USDT", 0)
            available_balance = balance.get("USDT", {}).get("free", 0) if isinstance(balance.get("USDT"), dict) else balance.get("USDT", 0)
            
            margin_used = 0
            unrealized_pnl = 0
            position_risks = []
            
            for pos in positions:
                pos_risk = await self._calculate_position_risk(pos)
                if pos_risk:
                    position_risks.append(pos_risk)
                    margin_used += pos_risk.margin
                    unrealized_pnl += pos_risk.unrealized_pnl
            
            margin_ratio = margin_used / total_equity if total_equity > 0 else 0
            
            account_risk = AccountRisk(
                total_equity=total_equity,
                available_balance=available_balance,
                margin_used=margin_used,
                unrealized_pnl=unrealized_pnl,
                margin_ratio=margin_ratio,
                position_risks=position_risks
            )
            
            account_risk.risk_level = self._evaluate_account_risk_level(account_risk)
            account_risk.warnings = self._generate_account_warnings(account_risk)
            
            return account_risk
            
        except Exception as e:
            logger.error(f"检查账户风险失败: {e}")
            return None
    
    async def _calculate_position_risk(self, pos: Dict) -> Optional[PositionRisk]:
        """计算持仓风险"""
        try:
            symbol = pos.get("symbol", "")
            side = pos.get("side", "long")
            size = float(pos.get("size", 0) or 0)
            
            if size == 0:
                return None
            
            entry_price = float(pos.get("entry_price", 0) or 0)
            current_price = float(pos.get("mark_price", entry_price) or entry_price)
            unrealized_pnl = float(pos.get("unrealized_pnl", 0) or 0)
            leverage = float(pos.get("leverage", 1) or 1)
            margin = float(pos.get("margin", 0) or 0)
            liquidation_price = float(pos.get("liquidation_price", 0) or 0)
            
            unrealized_pnl_percent = (unrealized_pnl / (entry_price * size)) * 100 if entry_price > 0 and size > 0 else 0
            
            distance_to_liquidation = 0
            if liquidation_price > 0 and current_price > 0:
                if side == "long":
                    distance_to_liquidation = (current_price - liquidation_price) / current_price
                else:
                    distance_to_liquidation = (liquidation_price - current_price) / current_price
            
            margin_ratio = margin / (entry_price * size / leverage) if entry_price > 0 and size > 0 else 0
            
            position_risk = PositionRisk(
                symbol=symbol,
                side=side,
                size=size,
                entry_price=entry_price,
                current_price=current_price,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_percent=unrealized_pnl_percent,
                liquidation_price=liquidation_price,
                margin=margin,
                leverage=leverage,
                distance_to_liquidation=distance_to_liquidation,
                margin_ratio=margin_ratio
            )
            
            position_risk.risk_level = self._evaluate_position_risk_level(position_risk)
            position_risk.warnings = self._generate_position_warnings(position_risk)
            
            return position_risk
            
        except Exception as e:
            logger.error(f"计算持仓风险失败: {e}")
            return None
    
    def _evaluate_account_risk_level(self, account: AccountRisk) -> RiskLevel:
        """评估账户风险等级"""
        if account.margin_ratio >= self.risk_config["margin_ratio_critical"]:
            return RiskLevel.CRITICAL
        
        if account.margin_ratio >= self.risk_config["margin_ratio_warning"]:
            return RiskLevel.HIGH
        
        if account.unrealized_pnl / account.total_equity <= self.risk_config["unrealized_loss_critical"]:
            return RiskLevel.CRITICAL
        
        if account.unrealized_pnl / account.total_equity <= self.risk_config["unrealized_loss_warning"]:
            return RiskLevel.HIGH
        
        for pos_risk in account.position_risks:
            if pos_risk.risk_level == RiskLevel.CRITICAL:
                return RiskLevel.CRITICAL
            if pos_risk.risk_level == RiskLevel.HIGH:
                return RiskLevel.HIGH
        
        return RiskLevel.LOW
    
    def _evaluate_position_risk_level(self, pos: PositionRisk) -> RiskLevel:
        """评估持仓风险等级"""
        if pos.distance_to_liquidation <= self.risk_config["liquidation_distance_critical"]:
            return RiskLevel.CRITICAL
        
        if pos.distance_to_liquidation <= self.risk_config["liquidation_distance_warning"]:
            return RiskLevel.HIGH
        
        if pos.unrealized_pnl_percent <= self.risk_config["unrealized_loss_critical"] * 100:
            return RiskLevel.CRITICAL
        
        if pos.unrealized_pnl_percent <= self.risk_config["unrealized_loss_warning"] * 100:
            return RiskLevel.HIGH
        
        return RiskLevel.LOW
    
    def _generate_account_warnings(self, account: AccountRisk) -> List[str]:
        """生成账户预警信息"""
        warnings = []
        
        if account.margin_ratio >= self.risk_config["margin_ratio_critical"]:
            warnings.append(f"🚨 保证金占用率过高: {account.margin_ratio:.1%}")
        elif account.margin_ratio >= self.risk_config["margin_ratio_warning"]:
            warnings.append(f"⚠️ 保证金占用率较高: {account.margin_ratio:.1%}")
        
        pnl_ratio = account.unrealized_pnl / account.total_equity if account.total_equity > 0 else 0
        if pnl_ratio <= self.risk_config["unrealized_loss_critical"]:
            warnings.append(f"🚨 账户浮亏严重: {pnl_ratio:.1%}")
        elif pnl_ratio <= self.risk_config["unrealized_loss_warning"]:
            warnings.append(f"⚠️ 账户浮亏较大: {pnl_ratio:.1%}")
        
        for pos_risk in account.position_risks:
            warnings.extend(pos_risk.warnings)
        
        return warnings
    
    def _generate_position_warnings(self, pos: PositionRisk) -> List[str]:
        """生成持仓预警信息"""
        warnings = []
        
        if pos.distance_to_liquidation <= self.risk_config["liquidation_distance_critical"]:
            warnings.append(f"🚨 {pos.symbol} 接近强平价格! 距离: {pos.distance_to_liquidation:.1%}")
        elif pos.distance_to_liquidation <= self.risk_config["liquidation_distance_warning"]:
            warnings.append(f"⚠️ {pos.symbol} 距离强平价格较近: {pos.distance_to_liquidation:.1%}")
        
        if pos.unrealized_pnl_percent <= self.risk_config["unrealized_loss_critical"] * 100:
            warnings.append(f"🚨 {pos.symbol} 浮亏严重: {pos.unrealized_pnl_percent:.1f}%")
        elif pos.unrealized_pnl_percent <= self.risk_config["unrealized_loss_warning"] * 100:
            warnings.append(f"⚠️ {pos.symbol} 浮亏较大: {pos.unrealized_pnl_percent:.1f}%")
        
        return warnings
    
    async def _notify_warnings(self, account_risk: AccountRisk) -> None:
        """通知预警"""
        for warning in account_risk.warnings:
            logger.warning(warning)
        
        for callback in self._callbacks:
            try:
                await callback(account_risk)
            except Exception as e:
                logger.error(f"风险回调执行失败: {e}")
    
    def get_status(self) -> Dict:
        """获取监控状态"""
        status = {
            "running": self._running,
            "config": self.risk_config
        }
        
        if self._last_account_risk:
            status["last_check"] = {
                "total_equity": self._last_account_risk.total_equity,
                "margin_ratio": self._last_account_risk.margin_ratio,
                "risk_level": self._last_account_risk.risk_level.value,
                "position_count": len(self._last_account_risk.position_risks),
                "warnings": self._last_account_risk.warnings
            }
        
        return status
    
    def calculate_liquidation_price(
        self,
        entry_price: float,
        size: float,
        leverage: float,
        side: str,
        maintenance_margin_rate: float = 0.004
    ) -> float:
        """
        计算强平价格
        
        Args:
            entry_price: 入场价格
            size: 持仓数量
            leverage: 杠杆倍数
            side: 方向 (long/short)
            maintenance_margin_rate: 维持保证金率
            
        Returns:
            强平价格
        """
        if side == "long":
            liquidation_price = entry_price * (1 - 1/leverage + maintenance_margin_rate)
        else:
            liquidation_price = entry_price * (1 + 1/leverage - maintenance_margin_rate)
        
        return liquidation_price
    
    def calculate_position_value(
        self,
        size: float,
        price: float,
        leverage: float = 1
    ) -> Dict[str, float]:
        """
        计算仓位价值
        
        Returns:
            包含名义价值、保证金、风险价值的字典
        """
        notional_value = size * price
        margin = notional_value / leverage
        
        return {
            "notional_value": notional_value,
            "margin": margin,
            "leverage": leverage
        }
    
    def calculate_risk_reward_ratio(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        side: str
    ) -> Dict[str, float]:
        """
        计算风险收益比
        
        Returns:
            包含风险、收益、风险收益比的字典
        """
        if side == "long":
            risk = abs(entry_price - stop_loss) / entry_price
            reward = abs(take_profit - entry_price) / entry_price
        else:
            risk = abs(stop_loss - entry_price) / entry_price
            reward = abs(entry_price - take_profit) / entry_price
        
        ratio = reward / risk if risk > 0 else 0
        
        return {
            "risk": risk,
            "reward": reward,
            "risk_reward_ratio": ratio
        }
