from src.modules.agents import AgentOrchestrator


def test_agent_orchestrator_returns_execution_governed_verdicts_and_plan():
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
    assert out["mode"] == "execution_governed"
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
    research = next(v for v in verdicts if v["agent_name"] == "research_agent")
    assert risk["structured_verdict"]["risk_verdict"] == "allow"
    assert research["next_action"] != "hold_for_review"
    assert out["execution_plan"]["should_block"] is False
    assert out["execution_plan"]["execution_recommendation"] == "slice"
    assert out["execution_plan"]["size_scale"] == 0.6


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
    assert out["execution_plan"]["should_block"] is True
    assert out["execution_plan"]["block_reason"] == "risk_governor_deny"


def test_agent_orchestrator_execution_coach_softens_bad_microstructure():
    orch = AgentOrchestrator()
    out = orch.evaluate_advisory_snapshot(
        symbol="BTC/USDT",
        market_snapshot={"trend": "bullish", "confidence": 0.82, "spread_bps": 11},
        semantic_context={
            "risk_posture": "balanced",
            "liquidity_state": "healthy",
            "execution_quality_state": "degraded",
            "execution_recommendation": "normal",
            "signal_conflict_score": 0.52,
            "depth_imbalance": 0.51,
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
            "review_completion_status": "completed",
            "experiment_card": {"cost_model": {"fee_bps": 8}},
            "peer_review_answers": {
                "what_edge": "trend persistence",
                "why_not_immediately_gone": "liquidity fragmentation",
                "net_after_cost": "positive",
                "failure_shape": "range chop",
                "kill_signal": "drift",
            },
        },
        decision_confidence=0.82,
        trace_id="trace-3",
    )
    exec_v = next(v for v in out["verdicts"] if v["agent_name"] == "execution_coach_agent")
    assert exec_v["structured_verdict"]["execution_recommendation"] == "wait_or_slice"
    assert "elevated_spread" in exec_v["blocking_flags"]
    assert exec_v["structured_verdict"]["depth_imbalance"] == 0.51
    assert exec_v["structured_verdict"]["signal_conflict_score"] == 0.52
    assert out["execution_plan"]["should_block"] is False
    assert out["execution_plan"]["size_scale"] < 1.0
    assert out["execution_plan"]["leverage_scale"] < 1.0
