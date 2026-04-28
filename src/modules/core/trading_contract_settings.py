"""
交易合约与持仓上限：以 ``trading.contract`` 为主配置源，合并到引擎与 AI 核心。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _as_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def apply_trading_contract_unified(
    trading_section: Any,
    *,
    contract_config: Dict[str, Any],
    ai_config: Dict[str, Any],
    ai_core_config: Optional[Dict[str, Any]] = None,
) -> None:
    """
    将 ``trading.contract`` 合并到 ``contract_config`` / ``ai_config`` / ``ai_core_config``。

    - 杠杆、网格、永续类型、保证金模式来自主配置
    - 单向最大同向持仓与总仓上限、双向对冲上限分别映射到 ai_config
    """
    if not isinstance(trading_section, dict):
        return
    tc = trading_section.get("contract")
    if not isinstance(tc, dict):
        return

    for key in (
        "enabled",
        "trade_type",
        "margin_mode",
        "position_mode",
        "leverage_curve",
        "grid_trading",
        "grid_levels",
        "grid_spacing",
        "products",
    ):
        if key in tc:
            contract_config[key] = tc[key]

    if "leverage_min" in tc:
        contract_config["leverage_min"] = _as_int(tc["leverage_min"], int(contract_config.get("leverage_min") or 20))
    if "leverage_max" in tc:
        contract_config["leverage_max"] = _as_int(tc["leverage_max"], int(contract_config.get("leverage_max") or 100))
    if "default_leverage" in tc:
        contract_config["default_leverage"] = _as_int(
            tc["default_leverage"], int(contract_config.get("default_leverage") or 30)
        )

    oneway = _as_int(tc.get("max_positions_oneway"), 5)
    hedge = _as_int(tc.get("max_positions_hedge"), 8)

    if "max_positions_oneway" in tc:
        ai_config["max_same_direction_positions"] = oneway
        ai_config["max_positions"] = oneway
    if "max_positions_hedge" in tc:
        ai_config["max_hedged_positions"] = hedge

    if ai_core_config is not None:
        if "leverage_min" in tc:
            ai_core_config["leverage_min"] = int(contract_config.get("leverage_min", 20))
        if "leverage_max" in tc:
            ai_core_config["leverage_max"] = int(contract_config.get("leverage_max", 100))
        if "default_leverage" in tc:
            ai_core_config["default_leverage"] = int(contract_config.get("default_leverage", 30))
        if "max_positions_oneway" in tc:
            ai_core_config["max_positions"] = oneway

    logger.info(
        "已应用 trading.contract: lev=%s-%s default=%s oneway_cap=%s hedge_cap=%s grid=%s",
        contract_config.get("leverage_min"),
        contract_config.get("leverage_max"),
        contract_config.get("default_leverage"),
        ai_config.get("max_positions"),
        ai_config.get("max_hedged_positions"),
        contract_config.get("grid_trading"),
    )
