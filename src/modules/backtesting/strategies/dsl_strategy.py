"""
DSL-backed strategy for BacktestEngine.

Implements deterministic signal generation from StrategyDSL primitives.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd

from ..backtest_engine import StrategyBase
from ...strategies.strategy_dsl import validate_dsl

logger = logging.getLogger(__name__)


class DSLStrategy(StrategyBase):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.dsl = config.get("dsl", {}) or {}
        validate_dsl(self.dsl)
        self.last_signal = None

    def initialize(self, data: pd.DataFrame):
        logger.info(f"初始化 DSLStrategy: {self.dsl.get('name')} v{self.dsl.get('version','1.0.0')}")

    def on_data(self, data: pd.DataFrame, index: int) -> Optional[Dict[str, Any]]:
        if len(data) < 30:
            return None

        close = float(data["close"].iloc[-1])

        side = self._compute_entry_side(data)
        if not side:
            side = self._compute_exit_side(data)
        if not side:
            return None

        if side == self.last_signal:
            return None
        self.last_signal = side
        return {"side": side, "quantity": 0.1, "price": close}

    def on_finish(self):
        logger.info("DSLStrategy 回测完成")

    def _compute_entry_side(self, data: pd.DataFrame) -> Optional[str]:
        for op in self.dsl.get("entry", []) or []:
            t = op.get("type")
            params = op.get("params", {}) or {}
            if t == "ma_crossover":
                fast = int(params.get("fast", 20))
                slow = int(params.get("slow", 50))
                if len(data) < slow + 2:
                    return None
                fast_ma = data["close"].rolling(window=fast).mean()
                slow_ma = data["close"].rolling(window=slow).mean()
                if fast_ma.iloc[-2] <= slow_ma.iloc[-2] and fast_ma.iloc[-1] > slow_ma.iloc[-1]:
                    return "buy"
                if fast_ma.iloc[-2] >= slow_ma.iloc[-2] and fast_ma.iloc[-1] < slow_ma.iloc[-1]:
                    return "sell"
            if t == "breakout_channel":
                lookback = int(params.get("lookback", 20))
                if len(data) < lookback + 2:
                    return None
                hh = data["high"].rolling(window=lookback).max().iloc[-2]
                ll = data["low"].rolling(window=lookback).min().iloc[-2]
                close = float(data["close"].iloc[-1])
                if close > float(hh):
                    return "buy"
                if close < float(ll):
                    return "sell"
        return None

    def _compute_exit_side(self, data: pd.DataFrame) -> Optional[str]:
        for op in self.dsl.get("exit", []) or []:
            t = op.get("type")
            params = op.get("params", {}) or {}
            if t == "bollinger_reversion":
                window = int(params.get("window", 20))
                std_n = float(params.get("std", 2.0))
                if len(data) < window + 2:
                    return None
                ma = data["close"].rolling(window=window).mean()
                std = data["close"].rolling(window=window).std()
                upper = ma + std_n * std
                lower = ma - std_n * std
                close = float(data["close"].iloc[-1])
                if close < float(lower.iloc[-1]):
                    return "buy"
                if close > float(upper.iloc[-1]):
                    return "sell"
        return None

