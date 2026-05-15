from src.modules.agents import AgentOrchestrator


def test_agent_orchestrator_returns_four_advisory_verdicts():
    orch = AgentOrchestrator()
    out = orch.evaluate_advisory_snapshot(
        symbol="BTC/USDT",
        market_snapshot={
            "trend": "bullish",
            "confidence": 0.8,
            "spread_bps": 6,
            "funding_rate": 0.0004,
            "open_interest": 500000,
        },
        semantic_context={
            "risk_posture": "balanced",
            "liquidity_state": "healthy",
            "strategy_stage": "limited_live",
            "execution_recommendation": "normal",
        },
        governance={
            "strategy_id": "s1",
            "stage": "limited_live",
            "oos_status": "passed",
            "live_drift_status": "healthy",
            "market_structure_overlay": {"status": "normal"},
        },
        research_profile={
            "strategy_id": "s1",
            "hypothesis": "trend continuation",
            "experiment_card": {"cost_model": {"fee_bps": 8}},
            "review_completion_status": "completed",
            "peer_review_answers": {
                "what_edge": "trend persistence",
                "why_not_immediately_gone": "liquidity fragmentation",
                "net_after_cost": "positive",
                "failure_shape": "range chop",
                "kill_signal": "drift",
            },
        },
        decision_confidence=0.78,
        trace_id="trace-1",
    )
    assert out["mode"] == "advisory_only"
    assert out["workflow"][-1] == "ExecutionGateway"
    verdicts = out["verdicts"]
    assert len(verdicts) == 4
    assert {v["agent_name"] for v in verdicts} == {
        "market_structure_agent",
        "research_agent",
        "risk_governor_agent",
        "execution_coach_agent",
    }
    risk = next(v for v in verdicts if v["agent_name"] == "risk_governor_agent")
    assert risk["structured_verdict"]["risk_verdict"] == "allow"


def test_agent_orchestrator_risk_governor_blocks_degraded_strategy():
    orch = AgentOrchestrator()
    out = orch.evaluate_advisory_snapshot(
        symbol="BTC/USDT",
        market_snapshot={"trend": "bullish", "confidence": 0.9, "spread_bps": 5},
        semantic_context={
            "risk_posture": "balanced",
            "liquidity_state": "healthy",
            "execution_quality_state": "degraded",
            "exchange_reachability_status": "degraded",
        },
        governance={
            "strategy_id": "s1",
            "stage": "limited_live",
            "oos_status": "failed",
            "live_drift_status": "degraded",
            "market_structure_overlay": {"status": "observe"},
        },
        research_profile={
            "strategy_id": "s1",
            "review_completion_status": "missing",
        },
        decision_confidence=0.7,
        trace_id="trace-2",
    )
    risk = next(v for v in out["verdicts"] if v["agent_name"] == "risk_governor_agent")
    assert risk["structured_verdict"]["risk_verdict"] == "deny"
    assert "oos_not_ready" in risk["blocking_flags"]
    assert "live_drift_degraded" in risk["blocking_flags"]
