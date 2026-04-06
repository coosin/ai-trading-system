"""
MACD策略

当MACD线金叉信号线时买入，死叉时卖出
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


class MACDStrategy(Strategy):
    """MACD策略"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化策略
        
        Args:
            config: 策略配置
        """
        super().__init__(config)
        self.fast_period = config.get("fast_period", 12)
        self.slow_period = config.get("slow_period", 26)
        self.signal_period = config.get("signal_period", 9)
        self.symbol = config.get("symbol", "BTC/USDT")
        self.history = []
        self.trades = []
        self.position = None
        self.macd_line = []
        self.signal_line = []
    
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
        max_period = max(self.fast_period, self.slow_period, self.signal_period)
        if len(self.history) > max_period * 3:
            self.history = self.history[-max_period * 3:]
        
        # 数据不足，无法生成信号
        if len(self.history) < self.slow_period:
            return None
        
        # 计算MACD
        macd, signal, hist = self._calculate_macd()
        
        # 生成信号
        signal = None
        
        # 金叉：MACD线上穿信号线
        if len(self.macd_line) > 1 and len(self.signal_line) > 1:
            prev_macd = self.macd_line[-2]
            current_macd = self.macd_line[-1]
            prev_signal = self.signal_line[-2]
            current_signal = self.signal_line[-1]
            
            # 金叉
            if prev_macd <= prev_signal and current_macd > current_signal and self.position != "long":
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
                logger.info(f"MACD金叉信号: {self.symbol}, 价格: {price}, MACD: {current_macd:.4f}, 信号: {current_signal:.4f}")
            
            # 死叉
            elif prev_macd >= prev_signal and current_macd < current_signal and self.position == "long":
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
                logger.info(f"MACD死叉信号: {self.symbol}, 价格: {price}, MACD: {current_macd:.4f}, 信号: {current_signal:.4f}")
        
        if signal:
            self.trades.append({
                "timestamp": timestamp,
                "signal": signal,
                "macd": macd,
                "signal_line": signal,
                "histogram": hist
            })
        
        return signal
    
    def _calculate_macd(self):
        """计算MACD指标
        
        Returns:
            macd, signal, histogram
        """
        prices = [h["price"] for h in self.history]
        
        # 计算EMA
        fast_ema = self._calculate_ema(prices, self.fast_period)
        slow_ema = self._calculate_ema(prices, self.slow_period)
        
        # 计算MACD线
        macd_line = [fast - slow for fast, slow in zip(fast_ema, slow_ema)]
        
        # 计算信号线
        signal_line = self._calculate_ema(macd_line, self.signal_period)
        
        # 计算柱状图
        histogram = [macd - sig for macd, sig in zip(macd_line, signal_line)]
        
        # 更新历史数据
        if macd_line:
            self.macd_line = macd_line
        if signal_line:
            self.signal_line = signal_line
        
        # 返回最新值
        return macd_line[-1], signal_line[-1], histogram[-1] if histogram else 0
    
    def _calculate_ema(self, prices, period):
        """计算EMA
        
        Args:
            prices: 价格列表
            period: 周期
            
        Returns:
            EMA列表
        """
        ema = []
        if len(prices) < period:
            return ema
        
        # 初始EMA为简单平均值
        initial_ema = np.mean(prices[:period])
        ema.append(initial_ema)
        
        # 计算后续EMA
        multiplier = 2 / (period + 1)
        for price in prices[period:]:
            current_ema = price * multiplier + ema[-1] * (1 - multiplier)
            ema.append(current_ema)
        
        return ema
    
    def update_parameters(self, params: Dict[str, Any]):
        """更新策略参数
        
        Args:
            params: 新的参数
        """
        if "fast_period" in params:
            self.fast_period = params["fast_period"]
        if "slow_period" in params:
            self.slow_period = params["slow_period"]
        if "signal_period" in params:
            self.signal_period = params["signal_period"]
        if "symbol" in params:
            self.symbol = params["symbol"]
        # 重置历史数据
        self.history = []
        self.macd_line = []
        self.signal_line = []
        logger.info(f"更新策略参数: fast_period={self.fast_period}, slow_period={self.slow_period}, signal_period={self.signal_period}, symbol={self.symbol}")
    
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