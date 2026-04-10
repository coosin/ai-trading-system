"""
StrategyOptimizer compatibility shim.

The project has moved to UnifiedStrategySystem, but ai_trading_engine still
imports StrategyOptimizer symbols. This lightweight adapter preserves runtime
compatibility and avoids startup failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class StrategyType(str, Enum):
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    ML_BASED = "ml_based"


@dataclass
class StrategyPerformance:
    strategy_id: str
    score: float = 0.0
    metadata: Optional[Dict[str, Any]] = None


class StrategyOptimizer:
    """Backward-compatible no-op optimizer."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def _analyze_all_strategies(self) -> List[StrategyPerformance]:
        return []

    async def _discover_new_patterns(self) -> List[Dict[str, Any]]:
        return []

    async def _process_new_strategy_proposals(self) -> None:
        return None

    async def _save_optimization_results(self) -> None:
        return None
