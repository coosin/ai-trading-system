from src.modules.core.feature_store_lite import FeatureStoreLite


def test_feature_store_lite_tracks_decision_and_execution_funnel(tmp_path):
    fs = FeatureStoreLite(max_items_per_table=10, persist_path=str(tmp_path / "feature_store_lite.json"))
    fs.append_decision_context(
        "trace-1",
        {"decision_action": "open_long", "symbol": "BTC/USDT", "regime_label": "trend_up"},
    )
    fs.append_execution_outcome(
        "trace-1",
        {"status": "success", "op": "open_swap", "symbol": "BTC/USDT"},
    )
    fs.append_research_label(
        "s1",
        {"stage": "published", "oos_status": "passed"},
    )
    summary = fs.get_summary()
    assert summary["decision_funnel"]["by_action"]["open_long"] == 1
    assert summary["execution_status"]["by_value"]["success"] == 1
    assert summary["research_stage"]["by_value"]["published"] == 1


def test_feature_store_lite_persists_and_recovers_rows(tmp_path):
    persist_path = tmp_path / "feature_store_lite.json"
    fs = FeatureStoreLite(max_items_per_table=10, persist_path=str(persist_path))
    fs.append_raw_market_event("BTC/USDT", {"spread_bps": 5.0})
    fs.append_derived_features("BTC/USDT", {"regime_label": "trend_up"})

    restored = FeatureStoreLite(max_items_per_table=10, persist_path=str(persist_path))
    raw = restored.get_recent("raw_market_events", 1)
    derived = restored.get_recent("derived_features", 1)

    assert raw and raw[0]["symbol"] == "BTC/USDT"
    assert derived and derived[0]["regime_label"] == "trend_up"
