from src.modules.market_structure import MarketStructureEngine


def test_market_structure_engine_classifies_liquidity_stress():
    engine = MarketStructureEngine()
    snap = engine.analyze_symbol(
        "BTC/USDT",
        {
            "trend": "bullish",
            "confidence": 0.72,
            "spread_bps": 22.0,
            "funding_rate": 0.0005,
            "open_interest": 800000.0,
            "quality_score": 0.38,
            "volatility": 0.015,
        },
    )
    assert snap.regime_label == "liquidity_stress"
    assert snap.risk_posture == "capital_preservation"
    assert snap.avoid_symbols == ["BTC/USDT"]


def test_market_structure_engine_exposes_preferred_setups():
    engine = MarketStructureEngine()
    snap = engine.analyze_symbol(
        "ETH/USDT",
        {
            "trend": "bullish",
            "confidence": 0.81,
            "spread_bps": 4.0,
            "funding_rate": 0.0004,
            "open_interest": 900000.0,
            "quality_score": 0.82,
            "volatility": 0.01,
            "stablecoin_supply_change": 0.9,
        },
    )
    assert snap.regime_label == "trend_up"
    assert "trend_continuation_long" in snap.preferred_setups
