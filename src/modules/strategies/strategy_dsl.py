"""
Strategy DSL (Domain Specific Language)

Goal:
- Let AI generate strategies as structured JSON/YAML-like configs
- Enable deterministic validation, backtest, walk-forward evaluation
- Provide safe, composable primitives that can "invent" new entry/exit combos
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple


PrimitiveType = Literal[
    "ma_crossover",
    "bollinger_reversion",
    "breakout_channel",
    "volatility_breakout",
    "scalp_reversion",
    "pinbar_reversal",
]


@dataclass
class StrategyDSL:
    """
    Minimal DSL schema.

    Example:
    {
      "name": "MA20x50 + breakout filter",
      "version": "1.0.0",
      "symbol": "BTC/USDT",
      "timeframe": "1h",
      "entry": [{"type":"ma_crossover","params":{"fast":20,"slow":50}}],
      "filters": [{"type":"breakout_channel","params":{"lookback":20,"mode":"confirm"}}],
      "exit": [{"type":"bollinger_reversion","params":{"window":20,"std":2}}],
      "risk": {"stop_loss_pct":0.02,"take_profit_pct":0.04,"max_holding_bars":72}
    }
    """

    name: str
    version: str = "1.0.0"
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    entry: List[Dict[str, Any]] = field(default_factory=list)
    filters: List[Dict[str, Any]] = field(default_factory=list)
    exit: List[Dict[str, Any]] = field(default_factory=list)
    risk: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "entry": self.entry,
            "filters": self.filters,
            "exit": self.exit,
            "risk": self.risk,
            "tags": self.tags,
            "metadata": self.metadata,
        }


class StrategyDSLValidationError(ValueError):
    pass


def validate_dsl(dsl: Dict[str, Any]) -> None:
    if not isinstance(dsl, dict):
        raise StrategyDSLValidationError("dsl must be a dict")
    if not dsl.get("name"):
        raise StrategyDSLValidationError("dsl.name is required")
    for section in ("entry", "filters", "exit"):
        ops = dsl.get(section, [])
        if ops is None:
            continue
        if not isinstance(ops, list):
            raise StrategyDSLValidationError(f"dsl.{section} must be a list")
        for op in ops:
            if not isinstance(op, dict):
                raise StrategyDSLValidationError(f"dsl.{section} items must be dicts")
            if op.get("type") not in {
                "ma_crossover",
                "bollinger_reversion",
                "breakout_channel",
                "volatility_breakout",
                "scalp_reversion",
                "pinbar_reversal",
            }:
                raise StrategyDSLValidationError(f"unsupported primitive type: {op.get('type')}")
            params = op.get("params", {})
            if params is not None and not isinstance(params, dict):
                raise StrategyDSLValidationError("primitive params must be dict")

    risk = dsl.get("risk", {}) or {}
    if not isinstance(risk, dict):
        raise StrategyDSLValidationError("dsl.risk must be dict")

    sl = risk.get("stop_loss_pct")
    tp = risk.get("take_profit_pct")
    if sl is not None and (not isinstance(sl, (int, float)) or sl <= 0 or sl >= 0.5):
        raise StrategyDSLValidationError("risk.stop_loss_pct must be (0, 0.5)")
    if tp is not None and (not isinstance(tp, (int, float)) or tp <= 0 or tp >= 2.0):
        raise StrategyDSLValidationError("risk.take_profit_pct must be (0, 2.0)")


def bump_version(version: str) -> str:
    """Semver patch bump for simple versioning."""
    parts = (version or "1.0.0").split(".")
    while len(parts) < 3:
        parts.append("0")
    major, minor, patch = parts[:3]
    try:
        patch_i = int(patch)
    except Exception:
        patch_i = 0
    return f"{major}.{minor}.{patch_i+1}"


def normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip() or "BTC/USDT"

