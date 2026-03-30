"""
资金管理模块

功能：
1. 基于风险的资金分配
2. 动态仓位调整
3. 风险评估和控制
4. 资金曲线分析
5. 回撤控制
"""

import logging
import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"      # 低风险
    MEDIUM = "medium"  # 中风险
    HIGH = "high"     # 高风险
    AGGRESSIVE = "aggressive"  # 激进风险


@dataclass
class PortfolioInfo:
    """投资组合信息"""
    total_equity: float          # 总权益
    available_balance: float     # 可用余额
    margin_used: float           # 已用保证金
    margin_level: float          # 保证金水平
    total_exposure: float        # 总敞口
    leverage: float              # 杠杆


@dataclass
class PositionInfo:
    """仓位信息"""
    symbol: str                  # 交易对
    side: str                    # 方向 (long/short)
    quantity: float              # 数量
    entry_price: float           # 入场价格
    current_price: float         # 当前价格
    pnl: float                   # 盈亏
    margin: float                # 占用保证金
    leverage: float              # 杠杆


@dataclass
class RiskMetrics:
    """风险指标"""
    var_95: float              # 95% VaR
    max_drawdown: float         # 最大回撤
    sharpe_ratio: float         # 夏普比率
    sortino_ratio: float        # 索提诺比率
    win_rate: float             # 胜率
    average_win_loss_ratio: float  # 平均盈亏比


class MoneyManager:
    """资金管理类"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化资金管理器
        
        Args:
            config: 配置信息
        """
        self.config = config
        self.risk_level = RiskLevel(config.get("risk_level", "medium"))
        self.max_drawdown_limit = config.get("max_drawdown_limit", 0.1)  # 10%
        self.max_position_size = config.get("max_position_size", 0.3)  # 30% of equity
        self.max_leverage = config.get("max_leverage", 3.0)
        self.risk_per_trade = config.get("risk_per_trade", 0.02)  # 2% per trade
        self.stop_loss_pct = config.get("stop_loss_pct", 0.03)  # 3% stop loss
        self.take_profit_pct = config.get("take_profit_pct", 0.06)  # 6% take profit
        
        # 资金曲线历史
        self.equity_history = []
        self.drawdown_history = []
        
        # 当前投资组合信息
        self.portfolio = PortfolioInfo(
            total_equity=config.get("initial_equity", 10000),
            available_balance=config.get("initial_equity", 10000),
            margin_used=0,
            margin_level=float('inf'),
            total_exposure=0,
            leverage=1.0
        )
        
        # 当前仓位
        self.positions: Dict[str, PositionInfo] = {}
        
        # 风险指标
        self.risk_metrics = RiskMetrics(
            var_95=0,
            max_drawdown=0,
            sharpe_ratio=0,
            sortino_ratio=0,
            win_rate=0,
            average_win_loss_ratio=0
        )
        
        logger.info(f"资金管理器初始化完成，风险等级: {self.risk_level.value}")
    
    def calculate_position_size(self, symbol: str, entry_price: float, stop_loss_price: float) -> float:
        """计算仓位大小
        
        Args:
            symbol: 交易对
            entry_price: 入场价格
            stop_loss_price: 止损价格
            
        Returns:
            仓位大小
        """
        # 计算每单位风险
        risk_amount = self.portfolio.total_equity * self.risk_per_trade
        
        # 计算每单位损失
        if entry_price > stop_loss_price:
            # 多头
            risk_per_unit = entry_price - stop_loss_price
        else:
            # 空头
            risk_per_unit = stop_loss_price - entry_price
        
        if risk_per_unit <= 0:
            return 0
        
        # 计算仓位大小
        position_size = risk_amount / risk_per_unit
        
        # 检查是否超过最大仓位限制
        max_position_value = self.portfolio.total_equity * self.max_position_size
        max_position_size = max_position_value / entry_price
        
        position_size = min(position_size, max_position_size)
        
        # 检查保证金是否足够
        margin_required = position_size * entry_price / self.max_leverage
        if margin_required > self.portfolio.available_balance:
            position_size = (self.portfolio.available_balance * self.max_leverage) / entry_price
        
        return position_size
    
    def update_portfolio(self, equity: float, margin_used: float):
        """更新投资组合信息
        
        Args:
            equity: 总权益
            margin_used: 已用保证金
        """
        self.portfolio.total_equity = equity
        self.portfolio.available_balance = equity - margin_used
        self.portfolio.margin_used = margin_used
        self.portfolio.margin_level = equity / margin_used if margin_used > 0 else float('inf')
        
        # 计算总敞口和杠杆
        total_exposure = 0
        for pos in self.positions.values():
            total_exposure += abs(pos.quantity * pos.current_price)
        
        self.portfolio.total_exposure = total_exposure
        self.portfolio.leverage = total_exposure / equity if equity > 0 else 0
        
        # 记录资金曲线
        self.equity_history.append((time.time(), equity))
        
        # 计算回撤
        if self.equity_history:
            max_equity = max([e[1] for e in self.equity_history])
            drawdown = (max_equity - equity) / max_equity
            self.drawdown_history.append((time.time(), drawdown))
            self.risk_metrics.max_drawdown = max([d[1] for d in self.drawdown_history])
    
    def add_position(self, symbol: str, side: str, quantity: float, entry_price: float):
        """添加仓位
        
        Args:
            symbol: 交易对
            side: 方向
            quantity: 数量
            entry_price: 入场价格
        """
        position = PositionInfo(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,
            pnl=0,
            margin=quantity * entry_price / self.max_leverage,
            leverage=self.max_leverage
        )
        
        self.positions[symbol] = position
        
        # 更新可用余额
        self.portfolio.available_balance -= position.margin
        self.portfolio.margin_used += position.margin
        
        logger.info(f"添加仓位: {symbol}, {side}, {quantity}, {entry_price}")
    
    def update_position(self, symbol: str, current_price: float):
        """更新仓位信息
        
        Args:
            symbol: 交易对
            current_price: 当前价格
        """
        if symbol in self.positions:
            position = self.positions[symbol]
            position.current_price = current_price
            
            # 计算盈亏
            if position.side == "long":
                position.pnl = (current_price - position.entry_price) * position.quantity
            else:
                position.pnl = (position.entry_price - current_price) * position.quantity
    
    def close_position(self, symbol: str):
        """关闭仓位
        
        Args:
            symbol: 交易对
        """
        if symbol in self.positions:
            position = self.positions[symbol]
            
            # 释放保证金
            self.portfolio.available_balance += position.margin
            self.portfolio.margin_used -= position.margin
            
            logger.info(f"关闭仓位: {symbol}, PnL: {position.pnl}")
            del self.positions[symbol]
    
    def should_adjust_position(self, symbol: str) -> bool:
        """判断是否需要调整仓位
        
        Args:
            symbol: 交易对
            
        Returns:
            是否需要调整
        """
        if symbol not in self.positions:
            return False
        
        position = self.positions[symbol]
        
        # 检查是否达到止盈止损
        if position.side == "long":
            if position.current_price >= position.entry_price * (1 + self.take_profit_pct):
                return True
            if position.current_price <= position.entry_price * (1 - self.stop_loss_pct):
                return True
        else:
            if position.current_price <= position.entry_price * (1 - self.take_profit_pct):
                return True
            if position.current_price >= position.entry_price * (1 + self.stop_loss_pct):
                return True
        
        # 检查是否超过风险限制
        position_value = abs(position.quantity * position.current_price)
        if position_value > self.portfolio.total_equity * self.max_position_size:
            return True
        
        return False
    
    def get_adjustment_signal(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取调整信号
        
        Args:
            symbol: 交易对
            
        Returns:
            调整信号
        """
        if not self.should_adjust_position(symbol):
            return None
        
        position = self.positions[symbol]
        
        # 检查是否达到止盈止损
        if position.side == "long":
            if position.current_price >= position.entry_price * (1 + self.take_profit_pct):
                return {
                    "action": "close",
                    "reason": "take_profit",
                    "symbol": symbol,
                    "quantity": position.quantity
                }
            if position.current_price <= position.entry_price * (1 - self.stop_loss_pct):
                return {
                    "action": "close",
                    "reason": "stop_loss",
                    "symbol": symbol,
                    "quantity": position.quantity
                }
        else:
            if position.current_price <= position.entry_price * (1 - self.take_profit_pct):
                return {
                    "action": "close",
                    "reason": "take_profit",
                    "symbol": symbol,
                    "quantity": position.quantity
                }
            if position.current_price >= position.entry_price * (1 + self.stop_loss_pct):
                return {
                    "action": "close",
                    "reason": "stop_loss",
                    "symbol": symbol,
                    "quantity": position.quantity
                }
        
        # 检查是否超过风险限制
        position_value = abs(position.quantity * position.current_price)
        if position_value > self.portfolio.total_equity * self.max_position_size:
            max_position_value = self.portfolio.total_equity * self.max_position_size
            new_quantity = max_position_value / position.current_price
            adjustment = new_quantity - position.quantity
            
            return {
                "action": "adjust",
                "reason": "position_size",
                "symbol": symbol,
                "quantity": adjustment
            }
        
        return None
    
    def calculate_var(self, days: int = 1, confidence: float = 0.95) -> float:
        """计算VaR (Value at Risk)
        
        Args:
            days: 天数
            confidence: 置信度
            
        Returns:
            VaR值
        """
        if len(self.equity_history) < 2:
            return 0
        
        # 计算日收益率
        returns = []
        for i in range(1, len(self.equity_history)):
            prev_equity = self.equity_history[i-1][1]
            current_equity = self.equity_history[i][1]
            returns.append((current_equity - prev_equity) / prev_equity)
        
        if not returns:
            return 0
        
        # 计算VaR
        returns.sort()
        index = int(len(returns) * (1 - confidence))
        var = abs(returns[index]) * self.portfolio.total_equity
        
        # 调整到指定天数
        var *= math.sqrt(days)
        
        self.risk_metrics.var_95 = var
        return var
    
    def calculate_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """计算夏普比率
        
        Args:
            risk_free_rate: 无风险利率
            
        Returns:
            夏普比率
        """
        if len(self.equity_history) < 2:
            return 0
        
        # 计算日收益率
        returns = []
        for i in range(1, len(self.equity_history)):
            prev_equity = self.equity_history[i-1][1]
            current_equity = self.equity_history[i][1]
            returns.append((current_equity - prev_equity) / prev_equity)
        
        if not returns:
            return 0
        
        # 计算年化收益率
        avg_return = np.mean(returns) * 365
        std_return = np.std(returns) * math.sqrt(365)
        
        if std_return == 0:
            return 0
        
        sharpe = (avg_return - risk_free_rate) / std_return
        self.risk_metrics.sharpe_ratio = sharpe
        return sharpe
    
    def get_risk_metrics(self) -> RiskMetrics:
        """获取风险指标
        
        Returns:
            风险指标
        """
        # 更新VaR
        self.calculate_var()
        
        # 更新夏普比率
        self.calculate_sharpe_ratio()
        
        return self.risk_metrics
    
    def get_portfolio_info(self) -> PortfolioInfo:
        """获取投资组合信息
        
        Returns:
            投资组合信息
        """
        return self.portfolio
    
    def get_positions(self) -> Dict[str, PositionInfo]:
        """获取当前仓位
        
        Returns:
            仓位信息
        """
        return self.positions
    
    def get_equity_curve(self) -> List[Tuple[float, float]]:
        """获取资金曲线
        
        Returns:
            资金曲线
        """
        return self.equity_history
    
    def get_drawdown_curve(self) -> List[Tuple[float, float]]:
        """获取回撤曲线
        
        Returns:
            回撤曲线
        """
        return self.drawdown_history
    
    def adjust_risk_level(self, new_risk_level: RiskLevel):
        """调整风险等级
        
        Args:
            new_risk_level: 新的风险等级
        """
        self.risk_level = new_risk_level
        
        # 根据风险等级调整参数
        if new_risk_level == RiskLevel.LOW:
            self.risk_per_trade = 0.01  # 1%
            self.max_position_size = 0.2  # 20%
            self.max_leverage = 2.0
        elif new_risk_level == RiskLevel.MEDIUM:
            self.risk_per_trade = 0.02  # 2%
            self.max_position_size = 0.3  # 30%
            self.max_leverage = 3.0
        elif new_risk_level == RiskLevel.HIGH:
            self.risk_per_trade = 0.03  # 3%
            self.max_position_size = 0.4  # 40%
            self.max_leverage = 5.0
        elif new_risk_level == RiskLevel.AGGRESSIVE:
            self.risk_per_trade = 0.05  # 5%
            self.max_position_size = 0.5  # 50%
            self.max_leverage = 10.0
        
        logger.info(f"风险等级调整为: {new_risk_level.value}")
    
    def is_risk_exceeded(self) -> bool:
        """检查是否超过风险限制
        
        Returns:
            是否超过风险限制
        """
        # 检查最大回撤
        if self.risk_metrics.max_drawdown > self.max_drawdown_limit:
            logger.warning(f"最大回撤超过限制: {self.risk_metrics.max_drawdown:.2f} > {self.max_drawdown_limit:.2f}")
            return True
        
        # 检查杠杆
        if self.portfolio.leverage > self.max_leverage:
            logger.warning(f"杠杆超过限制: {self.portfolio.leverage:.2f} > {self.max_leverage:.2f}")
            return True
        
        # 检查保证金水平
        if self.portfolio.margin_level < 1.5:
            logger.warning(f"保证金水平过低: {self.portfolio.margin_level:.2f} < 1.5")
            return True
        
        return False
    
    def get_risk_adjustment_recommendations(self) -> List[Dict[str, Any]]:
        """获取风险调整建议
        
        Returns:
            调整建议
        """
        recommendations = []
        
        # 检查每个仓位
        for symbol in list(self.positions.keys()):
            signal = self.get_adjustment_signal(symbol)
            if signal:
                recommendations.append(signal)
        
        # 检查整体风险
        if self.is_risk_exceeded():
            recommendations.append({
                "action": "reduce_exposure",
                "reason": "risk_exceeded",
                "message": "整体风险超过限制，建议减少敞口"
            })
        
        return recommendations