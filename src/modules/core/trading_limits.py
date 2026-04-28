from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PositionLimits:
    """
    Canonical position/size limits snapshot.

    All open/scale-in paths should rely on this snapshot rather than reading
    scattered keys across trading/contract/ai_config/ai_core_runtime.
    """

    symbol_max_margin_ratio: float  # per-symbol max margin usage as fraction of available
    max_same_direction_positions: int  # per-direction cap (long count / short count)
    max_positions_oneway: int  # total cap in oneway mode
    max_positions_hedge: int  # total cap when both directions exist
    hard_max_positions: int  # absolute cap regardless of oneway/hedge
    scale_in_min_confidence_2: float  # confidence floor for 2nd same-side open
    scale_in_min_confidence_3: float  # confidence floor for 3rd same-side open
    scale_in_min_confidence_4: float  # confidence floor for 4th+ same-side open
    source: Dict[str, str]  # field -> config key that produced it

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol_max_margin_ratio": float(self.symbol_max_margin_ratio),
            "max_same_direction_positions": int(self.max_same_direction_positions),
            "max_positions_oneway": int(self.max_positions_oneway),
            "max_positions_hedge": int(self.max_positions_hedge),
            "hard_max_positions": int(self.hard_max_positions),
            "scale_in_min_confidence_2": float(self.scale_in_min_confidence_2),
            "scale_in_min_confidence_3": float(self.scale_in_min_confidence_3),
            "scale_in_min_confidence_4": float(self.scale_in_min_confidence_4),
            "source": dict(self.source or {}),
        }


def _as_float(v: Any, default: float) -> float:
    try:
        x = float(v)
        if x != x:  # NaN
            return default
        return x
    except Exception:
        return default


def _as_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _pick_first(
    *candidates: Tuple[str, Any],
    cast: str,
    default: Any,
) -> Tuple[Any, str]:
    """
    Pick first non-None candidate; return (value, source_key).
    """
    for key, val in candidates:
        if val is None:
            continue
        if cast == "int":
            return _as_int(val, int(default)), key
        if cast == "float":
            return _as_float(val, float(default)), key
        return val, key
    return default, "default"


async def resolve_position_limits(
    *,
    config_manager: Any = None,
    trading_config: Optional[Dict[str, Any]] = None,
    ai_config: Optional[Dict[str, Any]] = None,
) -> PositionLimits:
    """
    Resolve canonical position limits from config.

    Priority:
    1) trading.position_limits.* (new canonical entry)
    2) legacy trading.contract.max_positions_oneway/max_positions_hedge
    3) legacy trading.max_positions
    4) legacy ai_config keys (max_same_direction_positions/max_hedged_positions/hard_max_positions)
    5) defaults (0.2 / 5 / 5 / 8 / 8)
    """
    tr: Dict[str, Any] = {}
    if isinstance(trading_config, dict):
        tr = dict(trading_config)
    elif config_manager and hasattr(config_manager, "get_config"):
        try:
            raw = await config_manager.get_config("trading", {}) or {}
            if isinstance(raw, dict):
                tr = dict(raw)
        except Exception:
            tr = {}

    ai: Dict[str, Any] = dict(ai_config) if isinstance(ai_config, dict) else {}

    pl = tr.get("position_limits") if isinstance(tr.get("position_limits"), dict) else {}
    tc = tr.get("contract") if isinstance(tr.get("contract"), dict) else {}

    source: Dict[str, str] = {}

    symbol_max_margin_ratio, source["symbol_max_margin_ratio"] = _pick_first(
        ("trading.position_limits.symbol_max_margin_ratio", pl.get("symbol_max_margin_ratio") if isinstance(pl, dict) else None),
        ("risk.max_position_size_percent", None),  # reserved: intentionally not coupling risk.* semantics
        cast="float",
        default=0.2,
    )
    # Clamp to sane bounds: never allow > 0.92 and never below 0.01.
    symbol_max_margin_ratio = max(0.01, min(0.92, float(symbol_max_margin_ratio)))

    max_same, source["max_same_direction_positions"] = _pick_first(
        ("trading.position_limits.max_same_direction_positions", pl.get("max_same_direction_positions") if isinstance(pl, dict) else None),
        ("trading.contract.max_positions_oneway", tc.get("max_positions_oneway") if isinstance(tc, dict) else None),
        ("ai_config.max_same_direction_positions", ai.get("max_same_direction_positions") if isinstance(ai, dict) else None),
        cast="int",
        default=5,
    )
    max_same = max(1, int(max_same))

    max_oneway, source["max_positions_oneway"] = _pick_first(
        ("trading.position_limits.max_positions_oneway", pl.get("max_positions_oneway") if isinstance(pl, dict) else None),
        ("trading.max_positions", tr.get("max_positions")),
        ("trading.contract.max_positions_oneway", tc.get("max_positions_oneway") if isinstance(tc, dict) else None),
        ("ai_config.max_positions", ai.get("max_positions") if isinstance(ai, dict) else None),
        cast="int",
        default=max_same,
    )
    max_oneway = max(1, int(max_oneway))

    max_hedge, source["max_positions_hedge"] = _pick_first(
        ("trading.position_limits.max_positions_hedge", pl.get("max_positions_hedge") if isinstance(pl, dict) else None),
        ("trading.contract.max_positions_hedge", tc.get("max_positions_hedge") if isinstance(tc, dict) else None),
        ("ai_config.max_hedged_positions", ai.get("max_hedged_positions") if isinstance(ai, dict) else None),
        cast="int",
        default=8,
    )
    max_hedge = max(1, int(max_hedge))

    hard_max, source["hard_max_positions"] = _pick_first(
        ("trading.position_limits.hard_max_positions", pl.get("hard_max_positions") if isinstance(pl, dict) else None),
        ("ai_config.hard_max_positions", ai.get("hard_max_positions") if isinstance(ai, dict) else None),
        cast="int",
        default=max(max_oneway, max_hedge),
    )
    hard_max = max(1, int(hard_max))

    c2, source["scale_in_min_confidence_2"] = _pick_first(
        ("trading.position_limits.scale_in_min_confidence_2", pl.get("scale_in_min_confidence_2") if isinstance(pl, dict) else None),
        cast="float",
        default=0.77,
    )
    c3, source["scale_in_min_confidence_3"] = _pick_first(
        ("trading.position_limits.scale_in_min_confidence_3", pl.get("scale_in_min_confidence_3") if isinstance(pl, dict) else None),
        cast="float",
        default=0.82,
    )
    c4, source["scale_in_min_confidence_4"] = _pick_first(
        ("trading.position_limits.scale_in_min_confidence_4", pl.get("scale_in_min_confidence_4") if isinstance(pl, dict) else None),
        cast="float",
        default=0.87,
    )
    c2 = max(0.0, min(1.0, float(c2)))
    c3 = max(c2, min(1.0, float(c3)))
    c4 = max(c3, min(1.0, float(c4)))

    # Ensure internal consistency: hedge cap should not be below oneway cap, and hard cap >= both.
    if max_hedge < max_oneway:
        max_hedge = max_oneway
        source["max_positions_hedge"] = "normalized(max_positions_oneway)"
    if hard_max < max(max_oneway, max_hedge):
        hard_max = max(max_oneway, max_hedge)
        source["hard_max_positions"] = "normalized(max(max_positions_oneway,max_positions_hedge))"

    # Emit a single compact log line when canonical block is missing (legacy fallback path).
    if not isinstance(pl, dict) or not pl:
        logger.info(
            "position_limits using legacy fallback: symbol_max_margin_ratio=%.3f max_same=%s oneway=%s hedge=%s hard=%s",
            symbol_max_margin_ratio,
            max_same,
            max_oneway,
            max_hedge,
            hard_max,
        )

    return PositionLimits(
        symbol_max_margin_ratio=float(symbol_max_margin_ratio),
        max_same_direction_positions=int(max_same),
        max_positions_oneway=int(max_oneway),
        max_positions_hedge=int(max_hedge),
        hard_max_positions=int(hard_max),
        scale_in_min_confidence_2=float(c2),
        scale_in_min_confidence_3=float(c3),
        scale_in_min_confidence_4=float(c4),
        source=source,
    )

