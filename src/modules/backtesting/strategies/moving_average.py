"""
移动平均线策略

当短期均线上穿长期均线时买入，下穿时卖出
"""

import logging
from typing import Dict, Any, Optional

import pandas as pd

from ..backtest_engine import StrategyBase

logger = logging.getLogger(__name__)


class MovingAverageStrategy(StrategyBase):
    """移动平均线策略"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.short_window = config.get("short_window", 20)
        self.long_window = config.get("long_window", 50)
        self.last_signal = None
    
    def initialize(self, data: pd.DataFrame):
        """初始化策略"""
        logger.info(f"初始化移动平均线策略: 短期均线={self.short_window}, 长期均线={self.long_window}")
    
    def on_data(self, data: pd.DataFrame, index: int) -> Optional[Dict[str, Any]]:
        """处理数据并生成信号"""
        # 确保数据足够计算均线
        if len(data) < self.long_window:
            return None
        
        # 计算移动平均线
        data['short_ma'] = data['close'].rolling(window=self.short_window).mean()
        data['long_ma'] = data['close'].rolling(window=self.long_window).mean()
        
        # 获取当前和前一期的均线值
        current_short_ma = data['short_ma'].iloc[-1]
        current_long_ma = data['long_ma'].iloc[-1]
        prev_short_ma = data['short_ma'].iloc[-2]
        prev_long_ma = data['long_ma'].iloc[-2]
        
        # 生成信号
        signal = None
        
        # 金叉：短期均线上穿长期均线
        if prev_short_ma <= prev_long_ma and current_short_ma > current_long_ma:
            if self.last_signal != "buy":
                signal = {
                    "side": "buy",
                    "quantity": 0.1  # 固定购买数量
                }
                self.last_signal = "buy"
                logger.info(f"金叉信号: {data.index[-1]}, 短期MA={current_short_ma:.2f}, 长期MA={current_long_ma:.2f}")
        
        # 死叉：短期均线下穿长期均线
        elif prev_short_ma >= prev_long_ma and current_short_ma < current_long_ma:
            if self.last_signal != "sell":
                signal = {
                    "side": "sell",
                    "quantity": 0.1  # 固定卖出数量
                }
                self.last_signal = "sell"
                logger.info(f"死叉信号: {data.index[-1]}, 短期MA={current_short_ma:.2f}, 长期MA={current_long_ma:.2f}")
        
        return signal
    
    def on_finish(self):
        """回测完成时调用"""
        logger.info("移动平均线策略回测完成")