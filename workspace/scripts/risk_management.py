#!/usr/bin/env python3
"""
风险管理模块
计算和管理交易风险
"""

import os
import json
import math
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum

class RiskLevel(Enum):
    """风险等级"""
    LOW = "低风险"
    MEDIUM = "中风险"
    HIGH = "高风险"
    CRITICAL = "极高风险"

@dataclass
class Position:
    """持仓信息"""
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    entry_time: datetime
    
    @property
    def market_value(self) -> float:
        """当前市值"""
        return self.quantity * self.current_price
    
    @property
    def entry_value(self) -> float:
        """入场市值"""
        return self.quantity * self.entry_price
    
    @property
    def pnl(self) -> float:
        """盈亏金额"""
        return self.market_value - self.entry_value
    
    @property
    def pnl_percent(self) -> float:
        """盈亏百分比"""
        if self.entry_value == 0:
            return 0.0
        return (self.pnl / self.entry_value) * 100
    
    @property
    def unrealized_pnl(self) -> float:
        """未实现盈亏（同pnl）"""
        return self.pnl

class RiskManager:
    """风险管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'crypto-config', 'risk_config.json'
        )
        self.config = self.load_config()
        self.positions: Dict[str, Position] = {}
        self.trading_history: List[Dict] = []
        
    def load_config(self) -> Dict:
        """加载风险配置文件"""
        default_config = {
            "risk_limits": {
                "max_daily_loss_percent": 2.0,
                "max_position_percent": 30.0,
                "max_single_trade_percent": 10.0,
                "stop_loss_percent": 5.0,
                "take_profit_percent": 15.0,
                "max_leverage": 3.0,
                "max_correlation": 0.7
            },
            "portfolio": {
                "total_capital": 10000.0,  # 默认总资金
                "base_currency": "USDT"
            },
            "risk_factors": {
                "volatility_weight": 0.4,
                "correlation_weight": 0.3,
                "liquidity_weight": 0.2,
                "market_cap_weight": 0.1
            }
        }
        
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"风险配置文件加载失败，使用默认配置: {e}")
        
        return default_config
    
    def add_position(self, position: Position):
        """添加持仓"""
        self.positions[position.symbol] = position
        self.trading_history.append({
            "action": "ADD_POSITION",
            "symbol": position.symbol,
            "quantity": position.quantity,
            "entry_price": position.entry_price,
            "timestamp": datetime.now().isoformat()
        })
    
    def update_position_price(self, symbol: str, current_price: float):
        """更新持仓价格"""
        if symbol in self.positions:
            self.positions[symbol].current_price = current_price
    
    def calculate_portfolio_value(self) -> float:
        """计算投资组合总价值"""
        return sum(pos.market_value for pos in self.positions.values())
    
    def calculate_total_pnl(self) -> Tuple[float, float]:
        """计算总盈亏（金额和百分比）"""
        total_entry = sum(pos.entry_value for pos in self.positions.values())
        total_current = sum(pos.market_value for pos in self.positions.values())
        
        pnl_amount = total_current - total_entry
        pnl_percent = (pnl_amount / total_entry * 100) if total_entry > 0 else 0.0
        
        return pnl_amount, pnl_percent
    
    def check_position_size(self, symbol: str, quantity: float, price: float) -> RiskLevel:
        """检查持仓大小是否符合风险限制"""
        trade_value = quantity * price
        total_capital = self.config["portfolio"]["total_capital"]
        position_percent = (trade_value / total_capital) * 100
        
        max_position = self.config["risk_limits"]["max_position_percent"]
        
        if position_percent > max_position:
            return RiskLevel.CRITICAL
        elif position_percent > max_position * 0.8:
            return RiskLevel.HIGH
        elif position_percent > max_position * 0.5:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def check_stop_loss(self, position: Position) -> bool:
        """检查是否触发止损"""
        loss_percent = abs(position.pnl_percent) if position.pnl < 0 else 0
        stop_loss_percent = self.config["risk_limits"]["stop_loss_percent"]
        
        if loss_percent >= stop_loss_percent:
            return True
        return False
    
    def check_take_profit(self, position: Position) -> bool:
        """检查是否触发止盈"""
        profit_percent = position.pnl_percent if position.pnl > 0 else 0
        take_profit_percent = self.config["risk_limits"]["take_profit_percent"]
        
        if profit_percent >= take_profit_percent:
            return True
        return False
    
    def calculate_var(self, confidence_level: float = 0.95, horizon_days: int = 1) -> float:
        """
        计算在险价值 (Value at Risk)
        confidence_level: 置信水平 (0.95 = 95%)
        horizon_days: 时间范围 (天数)
        """
        # 简化的VaR计算（实际需要历史数据）
        portfolio_value = self.calculate_portfolio_value()
        
        # 假设年化波动率为30%，转换为日波动率
        annual_volatility = 0.30
        daily_volatility = annual_volatility / math.sqrt(252)
        
        # Z-score对应置信水平（正态分布）
        z_scores = {0.95: 1.645, 0.99: 2.326, 0.999: 3.090}
        z_score = z_scores.get(confidence_level, 1.645)
        
        # 计算VaR
        var = portfolio_value * z_score * daily_volatility * math.sqrt(horizon_days)
        
        return var
    
    def calculate_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """计算夏普比率"""
        # 简化的夏普比率计算（实际需要历史收益率数据）
        portfolio_value = self.calculate_portfolio_value()
        total_capital = self.config["portfolio"]["total_capital"]
        
        # 计算收益率
        if total_capital > 0:
            returns = (portfolio_value - total_capital) / total_capital
        
        # 年化收益率（假设持有期1年）
        annual_return = returns * 252 if 'returns' in locals() else 0
        
        # 假设年化波动率
        annual_volatility = 0.30
        
        # 计算夏普比率
        if annual_volatility > 0:
            sharpe = (annual_return - risk_free_rate) / annual_volatility
        else:
            sharpe = 0
        
        return sharpe
    
    def generate_risk_report(self) -> str:
        """生成风险报告"""
        portfolio_value = self.calculate_portfolio_value()
        total_capital = self.config["portfolio"]["total_capital"]
        pnl_amount, pnl_percent = self.calculate_total_pnl()
        
        # 计算各项风险指标
        var_95 = self.calculate_var(confidence_level=0.95)
        var_99 = self.calculate_var(confidence_level=0.99)
        sharpe_ratio = self.calculate_sharpe_ratio()
        
        # 检查各个持仓的风险
        position_risks = []
        for symbol, position in self.positions.items():
            position_risk = self.check_position_size(
                symbol, position.quantity, position.current_price
            )
            stop_loss_triggered = self.check_stop_loss(position)
            take_profit_triggered = self.check_take_profit(position)
            
            position_risks.append({
                "symbol": symbol,
                "risk_level": position_risk.value,
                "pnl_percent": position.pnl_percent,
                "stop_loss": stop_loss_triggered,
                "take_profit": take_profit_triggered
            })
        
        # 生成报告
        report_lines = ["🔐 风险管理报告"]
        report_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("=" * 50)
        
        report_lines.append(f"总资金: ${total_capital:.2f}")
        report_lines.append(f"组合价值: ${portfolio_value:.2f}")
        report_lines.append(f"总盈亏: ${pnl_amount:.2f} ({pnl_percent:.2f}%)")
        report_lines.append(f"夏普比率: {sharpe_ratio:.2f}")
        report_lines.append(f"95%置信度1日VaR: ${var_95:.2f}")
        report_lines.append(f"99%置信度1日VaR: ${var_99:.2f}")
        report_lines.append("=" * 50)
        
        report_lines.append("📊 持仓风险分析:")
        for risk in position_risks:
            status_icons = []
            if risk["stop_loss"]:
                status_icons.append("🛑止损")
            if risk["take_profit"]:
                status_icons.append("🎯止盈")
            
            status_str = " | ".join(status_icons) if status_icons else "正常"
            
            report_lines.append(
                f"{risk['symbol']}: {risk['risk_level']} | "
                f"盈亏: {risk['pnl_percent']:.2f}% | "
                f"状态: {status_str}"
            )
        
        report_lines.append("=" * 50)
        
        # 总体风险评估
        critical_count = sum(1 for r in position_risks if r["risk_level"] == RiskLevel.CRITICAL.value)
        if critical_count > 0:
            report_lines.append(f"⚠️ 警告: {critical_count}个持仓处于极高风险水平")
        
        # 检查是否超过每日亏损限额
        if pnl_percent < -self.config["risk_limits"]["max_daily_loss_percent"]:
            report_lines.append(f"🚨 紧急: 已达到每日亏损限额 ({self.config['risk_limits']['max_daily_loss_percent']}%)")
        
        return "\n".join(report_lines)
    
    def save_report(self, report: str):
        """保存风险报告"""
        report_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(report_dir, exist_ok=True)
        
        report_file = os.path.join(
            report_dir, f'risk_report_{datetime.now().strftime("%Y%m%d_%H%M")}.txt'
        )
        
        with open(report_file, 'w') as f:
            f.write(report)
        
        return report_file

def main():
    """主函数 - 示例用法"""
    manager = RiskManager()
    
    # 示例：添加一些持仓
    positions = [
        Position("BTCUSDT", 0.1, 45000.0, 45500.0, datetime.now()),
        Position("ETHUSDT", 1.5, 2500.0, 2450.0, datetime.now()),
        Position("SOLUSDT", 10.0, 100.0, 105.0, datetime.now())
    ]
    
    for pos in positions:
        manager.add_position(pos)
    
    # 生成风险报告
    report = manager.generate_risk_report()
    print(report)
    
    # 保存报告
    saved_file = manager.save_report(report)
    print(f"\n报告已保存至: {saved_file}")

if __name__ == "__main__":
    main()