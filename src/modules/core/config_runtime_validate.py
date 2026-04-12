"""
合并后配置的运行时校验（类型与基本约束）。

由 ConfigManager 在文件与环境变量合并完成后调用；失败抛出 ConfigRuntimeValidateError。
"""

from __future__ import annotations

import numbers
from typing import Any, Dict, List, Tuple


class ConfigRuntimeValidateError(Exception):
    """配置合并结果未通过运行时校验。"""


def _bad(section: str, key: str, expected: str, got: Any) -> None:
    raise ConfigRuntimeValidateError(
        f"配置校验失败: {section}.{key} 应为 {expected}，实际为 {type(got).__name__}: {got!r}"
    )


def validate_merged_runtime_config(cfg: Dict[str, Any]) -> None:
    """校验关键段类型与简单数值关系；必要时就地规范化常见 YAML 类型偏差。"""
    trading = cfg.get("trading")
    if trading is not None and not isinstance(trading, dict):
        _bad("root", "trading", "dict", trading)

    if isinstance(trading, dict) and "paper_trading" in trading:
        pt = trading["paper_trading"]
        if not isinstance(pt, bool):
            _bad("trading", "paper_trading", "bool", pt)

    sltp = cfg.get("stop_loss_take_profit")
    if sltp is not None:
        if not isinstance(sltp, dict):
            _bad("root", "stop_loss_take_profit", "dict", sltp)
        else:
            _check_sltp(sltp)

    brain = cfg.get("ai_brain")
    if brain is not None and not isinstance(brain, dict):
        _bad("root", "ai_brain", "dict", brain)

    api = cfg.get("api")
    if api is not None:
        if not isinstance(api, dict):
            _bad("root", "api", "dict", api)
        elif "port" in api:
            v = api["port"]
            if isinstance(v, bool):
                _bad("api", "port", "int", v)
            if isinstance(v, numbers.Integral):
                api["port"] = int(v)
            elif isinstance(v, str) and v.strip().isdigit():
                api["port"] = int(v.strip())
            elif isinstance(v, float) and v == int(v):
                api["port"] = int(v)
            else:
                _bad("api", "port", "int", v)


def _check_sltp(sltp: Dict[str, Any]) -> None:
    int_keys: Tuple[str, ...] = ("check_interval", "max_orders", "exchange_resync_interval_sec")
    for k in int_keys:
        if k not in sltp:
            continue
        v = sltp[k]
        if isinstance(v, bool):
            _bad("stop_loss_take_profit", k, "int", v)
        if isinstance(v, numbers.Integral):
            sltp[k] = int(v)
            continue
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            sltp[k] = int(v.strip())
            continue
        if isinstance(v, float) and v == int(v):
            sltp[k] = int(v)
            continue
        _bad("stop_loss_take_profit", k, "int", v)

    float_keys: Tuple[str, ...] = (
        "default_stop_loss_percent",
        "default_take_profit_percent",
        "initial_trailing_offset",
        "profit_tier2_pnl_threshold",
        "tier2_trailing_offset",
        "trailing_stop_offset",
        "trailing_stop_trigger",
        "breakeven_trigger",
        "min_trailing_offset",
        "max_trailing_offset",
        "open_rr_synthetic_reward_multiple",
    )
    for k in float_keys:
        if k not in sltp:
            continue
        v = sltp[k]
        if isinstance(v, bool):
            _bad("stop_loss_take_profit", k, "float", v)
        if isinstance(v, numbers.Real) and not isinstance(v, bool):
            sltp[k] = float(v)
            continue
        if isinstance(v, str):
            try:
                sltp[k] = float(v.strip())
            except ValueError:
                _bad("stop_loss_take_profit", k, "float", v)
            continue
        _bad("stop_loss_take_profit", k, "float", v)

    bool_keys: Tuple[str, ...] = (
        "trailing_only_mode",
        "trailing_only_coerce_inputs",
        "trailing_active_on_open",
        "enable_trailing_stop",
        "trailing_momentum_adjust_enable",
        "enable_breakeven",
        "enable_partial_tp",
        "execute_exchange_on_trigger",
        "sync_exchange_positions_on_startup",
        "enable_dynamic_market_adjustment",
    )
    for k in bool_keys:
        if k not in sltp:
            continue
        v = sltp[k]
        if isinstance(v, bool):
            continue
        if isinstance(v, str):
            sltp[k] = str(v).strip().lower() in ("1", "true", "yes", "on")
            continue
        _bad("stop_loss_take_profit", k, "bool", v)

    errs: List[str] = []
    mto = sltp.get("min_trailing_offset")
    mxo = sltp.get("max_trailing_offset")
    if isinstance(mto, numbers.Real) and isinstance(mxo, numbers.Real) and float(mto) > float(mxo):
        errs.append("min_trailing_offset 不可大于 max_trailing_offset")
    if errs:
        raise ConfigRuntimeValidateError("; ".join(errs))
