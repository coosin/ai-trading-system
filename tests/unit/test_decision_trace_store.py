from src.modules.core.decision_trace_store import DecisionTraceStore


def test_decision_trace_store_collects_semantic_context():
    store = DecisionTraceStore(max_items=20, persist_path="")
    store.record_intent(
        trace_id="t1",
        symbol="BTC/USDT",
        side="buy",
        action="open",
        source="ai_core",
        confidence=0.81,
        strategy_used="trend_follow",
        reasoning="test",
        extras={
            "regime_label": "trend_up",
            "risk_posture": "balanced",
            "strategy_stage": "limited_live",
            "memory_refs": ["m1"],
            "workflow_mode": "advisory_only",
            "workflow_path": ["market_structure", "risk_governor", "execution_gateway"],
        },
    )
    store.record_guard_result(
        trace_id="t1",
        status="rejected",
        reason="risk_gate",
        stage="decision",
        extras={"risk_verdict": "deny", "lesson_summary": "risk too high"},
    )
    store.record_learning_feedback(
        trace_id="t1",
        lesson_summary="avoid weak liquidity entries",
        mistake_tags=["fragile_liquidity"],
        tuning_suggestion={"section": "ai_core_runtime", "key": "ai_core_min_confidence_to_open"},
        self_review_score=0.66,
    )

    row = store.get_by_trace_id("t1")
    assert row is not None
    assert row["market_context"]["regime_label"] == "trend_up"
    assert row["market_context"]["strategy_stage"] == "limited_live"
    assert row["workflow"]["mode"] == "advisory_only"
    assert row["workflow"]["current_stage"] == "guard:decision"
    assert row["workflow"]["status"] == "blocked"
    assert row["agent_outputs"] == {}
    assert row["semantic_signals"]["guard"]["risk_verdict"] == "deny"
    stages = [item["stage"] for item in row["stage_history"]]
    assert "intent" in stages
    assert "guard:decision" in stages
    assert stages.index("intent") < stages.index("guard:decision")
    assert row["learning"]["mistake_tags"] == ["fragile_liquidity"]

    analysis = store.analyze_recent(limit=10)
    top_regimes = analysis["top_regimes"]
    top_risk_verdicts = analysis["top_risk_verdicts"]
    top_workflow_statuses = analysis["top_workflow_statuses"]
    assert top_regimes and top_regimes[0]["key"] == "trend_up"
    assert top_risk_verdicts and top_risk_verdicts[0]["key"] == "deny"
    assert any(item["key"] == "blocked" for item in top_workflow_statuses)


def test_decision_trace_store_advances_execution_workflow():
    store = DecisionTraceStore(max_items=20, persist_path="")
    store.record_intent(
        trace_id="t2",
        symbol="ETH/USDT",
        side="sell",
        action="open",
        source="ai_core",
        extras={"workflow_mode": "advisory_only"},
    )
    store.record_guard_result(
        trace_id="t2",
        status="passed",
        reason="ready",
        stage="execution_preflight",
    )
    store.record_execution_result(
        trace_id="t2",
        status="success",
        detail="opened",
        source="execution_gateway",
        op="open_swap",
    )

    row = store.get_by_trace_id("t2")
    assert row is not None
    assert row["workflow"]["current_stage"] == "execution:open_swap"
    assert row["workflow"]["status"] == "completed"
    stages = [x["stage"] for x in row["stage_history"]]
    assert "intent" in stages
    assert "guard:execution_preflight" in stages
    assert "execution:open_swap" in stages
    assert stages.index("intent") < stages.index("guard:execution_preflight") < stages.index("execution:open_swap")
