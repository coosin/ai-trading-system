"""Tests for stop_loss_take_profit YAML / dict mapping."""
from src.modules.core.stop_loss_take_profit import (
    StopLossTakeProfitConfig,
    stop_loss_take_profit_config_from_mapping,
)


def test_from_mapping_partial_override():
    cfg = stop_loss_take_profit_config_from_mapping(
        {"initial_trailing_offset": 0.05, "check_interval": 12}
    )
    assert cfg.initial_trailing_offset == 0.05
    assert cfg.check_interval == 12
    assert cfg.trailing_only_mode is True


def test_from_mapping_unknown_keys_ignored():
    cfg = stop_loss_take_profit_config_from_mapping({"nosuch_key": 99, "max_orders": 50})
    assert cfg.max_orders == 50


def test_legacy_strategy_risk_management_fill():
    cfg = stop_loss_take_profit_config_from_mapping(
        {"check_interval": 7},
        strategy_section={"risk_management": {"stop_loss": 0.04, "take_profit": 0.08}},
    )
    assert cfg.check_interval == 7
    assert cfg.default_stop_loss_percent == 0.04
    assert cfg.default_take_profit_percent == 0.08


def test_explicit_sltp_wins_over_legacy():
    cfg = stop_loss_take_profit_config_from_mapping(
        {
            "default_stop_loss_percent": 0.02,
            "default_take_profit_percent": 0.0,
        },
        strategy_section={"risk_management": {"stop_loss": 0.99, "take_profit": 0.99}},
    )
    assert cfg.default_stop_loss_percent == 0.02
    assert cfg.default_take_profit_percent == 0.0


def test_bool_coercion():
    cfg = stop_loss_take_profit_config_from_mapping(
        {"trailing_only_mode": "false", "execute_exchange_on_trigger": "on"}
    )
    assert cfg.trailing_only_mode is False
    assert cfg.execute_exchange_on_trigger is True


def test_matches_builtin_defaults_shape():
    base = StopLossTakeProfitConfig()
    cfg = stop_loss_take_profit_config_from_mapping({})
    assert cfg.trailing_only_mode == base.trailing_only_mode
    assert cfg.persist_file == base.persist_file
    assert cfg.layered_partial_tp_levels == [(0.015, 0.25), (0.03, 0.35), (0.05, 0.40)]
    assert cfg.sr_partial_tp_trigger_pnl == 0.0075
    assert cfg.sr_partial_close_ratio == 0.33


def test_trailing_only_coerce_inputs_mapping():
    cfg = stop_loss_take_profit_config_from_mapping(
        {"trailing_only_coerce_inputs": "false"}
    )
    assert cfg.trailing_only_coerce_inputs is False
