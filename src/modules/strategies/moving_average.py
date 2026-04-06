"""
移动平均线交叉策略

当短期均线上穿长期均线时买入，下穿时卖出
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional

from .strategy_base import Strategy

logger = logging.getLogger(__name__)

STOP_LOSS_LONG_RATIO = 0.97
STOP_LOSS_SHORT_RATIO = 1.03
TAKE_PROFIT_LONG_RATIO = 1.06
TAKE_PROFIT_SHORT_RATIO = 0.94


class MovingAverageStrategy(Strategy):
    """移动平均线交叉策略"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化策略
        
        Args:
            config: 策略配置
        """
        super().__init__(config)
        self.short_window = config.get("short_window", 20)
        self.long_window = config.get("long_window", 50)
        self.symbol = config.get("symbol", "BTC/USDT")
        self.history = []
        self.trades = []
        self.position = None
    
    def generate_signal(self, market_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """生成交易信号
        
        Args:
            market_data: 市场数据
            
        Returns:
            交易信号
        """
        if self.symbol not in market_data:
            return None
        
        # 获取最新价格
        price = market_data[self.symbol]["close"]
        timestamp = market_data[self.symbol]["timestamp"]
        
        # 更新历史数据
        self.history.append({"timestamp": timestamp, "price": price})
        
        # 只保留最近的数据点
        if len(self.history) > self.long_window * 2:
            self.history = self.history[-self.long_window * 2:]
        
        # 数据不足，无法生成信号
        if len(self.history) < self.long_window:
            return None
        
        # 计算移动平均线
        prices = [h["price"] for h in self.history]
        short_ma = np.mean(prices[-self.short_window:])
        long_ma = np.mean(prices[-self.long_window:])
        
        # 生成信号
        signal = None
        
        # 金叉：短期均线上穿长期均线
        if short_ma > long_ma and self.position != "long":
            signal = {
                "symbol": self.symbol,
                "side": "long",
                "type": "market",
                "quantity": 0.1,  # 固定数量，实际应该根据资金管理计算
                "price": price,
                "stop_loss": price * STOP_LOSS_LONG_RATIO,
                "take_profit": price * TAKE_PROFIT_LONG_RATIO
            }
            self.position = "long"
            logger.info(f"金叉信号: {self.symbol}, 价格: {price}, 短期MA: {short_ma}, 长期MA: {long_ma}")
        
        # 死叉：短期均线下穿长期均线
        elif short_ma < long_ma and self.position == "long":
            signal = {
                "symbol": self.symbol,
                "side": "short",
                "type": "market",
                "quantity": 0.1,  # 固定数量
                "price": price,
                "stop_loss": price * STOP_LOSS_SHORT_RATIO,
                "take_profit": price * TAKE_PROFIT_SHORT_RATIO
            }
            self.position = "short"
            logger.info(f"死叉信号: {self.symbol}, 价格: {price}, 短期MA: {short_ma}, 长期MA: {long_ma}")
        
        if signal:
            self.trades.append({
                "timestamp": timestamp,
                "signal": signal,
                "short_ma": short_ma,
                "long_ma": long_ma
            })
        
        return signal
    
    def update_parameters(self, params: Dict[str, Any]):
        """更新策略参数
        
        Args:
            params: 新的参数
        """
        if "short_window" in params:
            self.short_window = params["short_window"]
        if "long_window" in params:
            self.long_window = params["long_window"]
        if "symbol" in params:
            self.symbol = params["symbol"]
        logger.info(f"更新策略参数: short_window={self.short_window}, long_window={self.long_window}, symbol={self.symbol}")
    
    def get_performance(self) -> Dict[str, Any]:
        """获取策略性能指标
        
        Returns:
            性能指标
        """
        if not self.trades:
            return {
                "total_pnl": 0,
                "win_rate": 0,
                "sharpe_ratio": 0,
                "max_drawdown": 0
            }
        
        # 计算盈亏
        pnls = []
        for i in range(1, len(self.trades)):
            entry_trade = self.trades[i-1]
            exit_trade = self.trades[i]
            
            if entry_trade["signal"]["side"] == "long" and exit_trade["signal"]["side"] == "short":
                pnl = (exit_trade["signal"]["price"] - entry_trade["signal"]["price"]) * entry_trade["signal"]["quantity"]
                pnls.append(pnl)
            elif entry_trade["signal"]["side"] == "short" and exit_trade["signal"]["side"] == "long":
                pnl = (entry_trade["signal"]["price"] - exit_trade["signal"]["price"]) * entry_trade["signal"]["quantity"]
                pnls.append(pnl)
        
        if not pnls:
            return {
                "total_pnl": 0,
                "win_rate": 0,
                "sharpe_ratio": 0,
                "max_drawdown": 0
            }
        
        # 计算总盈亏
        total_pnl = sum(pnls)
        
        # 计算胜率
        win_trades = [p for p in pnls if p > 0]
        win_rate = len(win_trades) / len(pnls) if pnls else 0
        
        # 计算夏普比率（简化版）
        if len(pnls) > 1:
            returns = np.array(pnls) / 1000  # 假设每笔交易的本金为1000
            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            sharpe_ratio = 0
        
        # 计算最大回撤（简化版）
        cumulative_pnl = []
        current_pnl = 0
        for p in pnls:
            current_pnl += p
            cumulative_pnl.append(current_pnl)
        
        if cumulative_pnl:
            max_pnl = max(cumulative_pnl)
            drawdowns = [(max_pnl - p) / max_pnl if max_pnl > 0 else 0 for p in cumulative_pnl]
            max_drawdown = max(drawdowns) if drawdowns else 0
        else:
            max_drawdown = 0
        
        return {
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "trade_count": len(pnls)
        }