"""
RSI策略

当RSI低于30时买入，高于70时卖出
"""

import logging
import numpy as np
from typing import Dict, Any, Optional

from .strategy_base import Strategy

logger = logging.getLogger(__name__)

STOP_LOSS_LONG_RATIO = 0.97
STOP_LOSS_SHORT_RATIO = 1.03
TAKE_PROFIT_LONG_RATIO = 1.06
TAKE_PROFIT_SHORT_RATIO = 0.94


class RSIStrategy(Strategy):
    """RSI策略"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化策略
        
        Args:
            config: 策略配置
        """
        super().__init__(config)
        self.rsi_period = config.get("rsi_period", 14)
        self.symbol = config.get("symbol", "BTC/USDT")
        self.history = []
        self.trades = []
        self.position = None
        self.buy_threshold = config.get("buy_threshold", 30)
        self.sell_threshold = config.get("sell_threshold", 70)
    
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
        if len(self.history) > self.rsi_period * 2:
            self.history = self.history[-self.rsi_period * 2:]
        
        # 数据不足，无法生成信号
        if len(self.history) < self.rsi_period + 1:
            return None
        
        # 计算RSI
        rsi = self._calculate_rsi()
        
        # 生成信号
        signal = None
        
        # RSI低于买入阈值，且当前没有多头仓位
        if rsi < self.buy_threshold and self.position != "long":
            signal = {
                "symbol": self.symbol,
                "side": "long",
                "type": "market",
                "quantity": 0.1,  # 固定数量
                "price": price,
                "stop_loss": price * STOP_LOSS_LONG_RATIO,
                "take_profit": price * TAKE_PROFIT_LONG_RATIO
            }
            self.position = "long"
            logger.info(f"RSI买入信号: {self.symbol}, 价格: {price}, RSI: {rsi}")
        
        # RSI高于卖出阈值，且当前有多头仓位
        elif rsi > self.sell_threshold and self.position == "long":
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
            logger.info(f"RSI卖出信号: {self.symbol}, 价格: {price}, RSI: {rsi}")
        
        if signal:
            self.trades.append({
                "timestamp": timestamp,
                "signal": signal,
                "rsi": rsi
            })
        
        return signal
    
    def _calculate_rsi(self) -> float:
        """计算RSI
        
        Returns:
            RSI值
        """
        prices = [h["price"] for h in self.history]
        deltas = np.diff(prices)
        
        # 计算上涨和下跌
        gain = deltas[deltas > 0].sum() / self.rsi_period
        loss = -deltas[deltas < 0].sum() / self.rsi_period
        
        if loss == 0:
            return 100
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def update_parameters(self, params: Dict[str, Any]):
        """更新策略参数
        
        Args:
            params: 新的参数
        """
        if "rsi_period" in params:
            self.rsi_period = params["rsi_period"]
        if "symbol" in params:
            self.symbol = params["symbol"]
        if "buy_threshold" in params:
            self.buy_threshold = params["buy_threshold"]
        if "sell_threshold" in params:
            self.sell_threshold = params["sell_threshold"]
        logger.info(f"更新策略参数: rsi_period={self.rsi_period}, buy_threshold={self.buy_threshold}, sell_threshold={self.sell_threshold}")
    
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