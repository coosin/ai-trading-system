from src.modules.api.module_control_api import _build_humanized_workflow_summary


def test_humanized_trading_workflow_summary_builds_frontend_ready_copy():
    report = {
        "health": {
            "exchange_connected": True,
            "reconciliation": {"healthy": True},
        },
        "current_exposure": {
            "position_count": 2,
            "active_sltp_count": 3,
        },
        "decision_and_guard": {
            "summary": {"guard_pass_rate": 0.18},
            "top_reject_reasons": [{"reason": "risk_reward_low"}],
        },
        "exits_and_pnl": {
            "trade_summary": {"sample_size": 48, "win_rate": 0.61, "net_pnl_plus_fees": 128.36},
        },
        "optimization_read_model": {
            "kpi_scorecard": {
                "data_quality": {"score": 0.91, "status": "ok"},
                "decision_selectivity": {"status": "ok"},
                "execution_quality": {"success_ratio": 0.96, "status": "ok"},
                "exit_quality": {"tp_suppressed": 12, "status": "ok"},
            },
            "optimization_readiness": {
                "ready_for_auto_apply": False,
                "blocking_gaps": [{"message": "成交样本不足 300，不建议自动应用参数。"}],
            },
            "parameter_recommendations": [{"guardrail": "执行/对账不健康时，禁止调策略阈值。"}],
        },
        "workflow_actions": [{"reason": "volatile regime has negative expectancy"}],
    }

    out = _build_humanized_workflow_summary(report)

    assert out["display_preferences"]["frontend_ready"] is True
    assert "当前系统共持有 2 个仓位" in out["headline"]
    assert out["focus_cards"][0]["title"] == "系统状态"
    assert out["metrics"][0]["label"] == "数据质量"
    assert out["next_actions"]


def test_humanized_trading_workflow_summary_handles_sparse_report():
    out = _build_humanized_workflow_summary({})

    assert out["display_preferences"]["api_readable"] is True
    assert "当前系统共持有 0 个仓位" in out["headline"]
    assert isinstance(out["focus_cards"], list)
    assert isinstance(out["next_actions"], list)
