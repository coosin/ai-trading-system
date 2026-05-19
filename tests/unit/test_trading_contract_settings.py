from src.modules.core.trading_contract_settings import apply_trading_contract_unified


def test_apply_trading_contract_merges_leverage_and_caps():
    cc = {
        "leverage_min": 1,
        "leverage_max": 50,
        "default_leverage": 10,
        "leverage_curve": [{"atr_gte": 0.05, "leverage": 20}],
        "grid_trading": False,
    }
    ai = {"max_positions": 3, "max_hedged_positions": 4, "max_same_direction_positions": 3}
    ac = {"leverage_max": 50, "max_positions": 3, "default_leverage": 10}
    tr = {
        "contract": {
            "leverage_min": 10,
            "leverage_max": 100,
            "default_leverage": 20,
            "leverage_curve": [{"atr_gte": 0.04, "leverage": 36}, {"atr_gte": 0.0, "leverage": 90}],
            "max_positions_oneway": 5,
            "max_positions_hedge": 8,
            "grid_trading": True,
            "trade_type": "swap",
        }
    }
    apply_trading_contract_unified(
        tr, contract_config=cc, ai_config=ai, ai_core_config=ac
    )
    assert cc["leverage_max"] == 100
    assert cc["grid_trading"] is True
    assert cc["leverage_curve"] == [{"atr_gte": 0.04, "leverage": 36}, {"atr_gte": 0.0, "leverage": 90}]
    assert ai["max_positions"] == 5
    assert ai["max_hedged_positions"] == 8
    assert ac["leverage_max"] == 100
    assert ac["max_positions"] == 5
