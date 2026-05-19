from src.modules.api.module_control_api import (
    _build_platform_alerts,
    _build_humanized_platform_oversight,
    _build_humanized_agent_effectiveness_summary,
    _build_humanized_closed_loop_summary,
    _build_humanized_memory_stats_summary,
    _build_humanized_profit_ops_overview,
    _build_humanized_snapshot_summary,
    _build_humanized_system_mastery_summary,
)
from src.modules.api.monitoring_api import _build_humanized_monitoring_summary


def test_humanized_snapshot_summary_is_frontend_ready():
    out = _build_humanized_snapshot_summary(
        {
            "system": {"system_status": "running", "module_count": 12},
            "account": {"positions": [{"symbol": "BTC/USDT"}], "synced_at": "2026-05-16T12:00:00"},
            "execution": {"reconciliation": {"healthy": True}, "policy_metrics": {"success_ratio": 0.93}},
            "risk": {"position_recommendations": {"BTC/USDT": {"ok": True}}},
            "alerts": [],
        }
    )
    assert "系统当前状态 running" in out["headline"]
    assert out["display_preferences"]["frontend_ready"] is True
    assert len(out["focus_cards"]) == 3


def test_humanized_system_mastery_summary_handles_negative_pnl():
    out = _build_humanized_system_mastery_summary(
        {
            "overview": {
                "loop_verdict": "WARN",
                "risk_level": "medium",
                "position_count": 2,
                "active_orders": 1,
                "recent_net_pnl_plus_fees": -20.5,
                "recent_win_rate": 0.4,
            },
            "learning_and_optimization": {"learning_status": {"ok": True}, "optimization_hints": [{"recommendation": "tighten regime filters"}]},
            "coverage_gaps": [{"message": "trace 覆盖不足"}],
        }
    )
    assert "最近净收益 -20.50" in out["headline"]
    assert out["next_actions"][0] == "trace 覆盖不足"


def test_humanized_monitoring_summary_mentions_alerts_and_trades():
    out = _build_humanized_monitoring_summary(
        {"status": "ok", "active_alerts": 2, "total_trades": 15, "symbols": ["BTC/USDT"], "strategies": ["s1", "s2"]}
    )
    assert "活跃告警 2 条" in out["headline"]
    assert out["next_actions"]


def test_humanized_agent_effectiveness_flags_missing_realized_linkage():
    out = _build_humanized_agent_effectiveness_summary(
        {
            "summary": {
                "trace_sample_size": 20,
                "agent_trace_coverage_ratio": 0.35,
                "executed_trace_count": 4,
                "realized_trade_linked_trace_count": 0,
                "full_stack_trace_count": 2,
                "blocked_trace_count": 8,
            },
            "top_issues": [{"recommendation": "继续打通 trace_id 回写"}],
            "attribution_diagnostics": {"diagnosis": "realized_trace_namespace_mismatch"},
        }
    )
    assert "闭环归因不足" in out["verdict"]
    assert out["next_actions"][0] == "继续打通 trace_id 回写"


def test_humanized_closed_loop_summary_surfaces_reconciliation_block():
    out = _build_humanized_closed_loop_summary(
        {
            "loop_health": {"verdict": "WARN", "risk_level": "medium", "position_count": 1, "active_orders": 2, "equity": 1234, "active_alerts": 1, "running_modules": 5},
            "signal_and_guard": {"top_reject_reasons": [{"reason": "spread_rejected", "count": 3}]},
            "exit_and_profitability": {
                "realized_performance": {"best_regime": {"regime": "trend"}, "worst_regime": {"regime": "volatile"}},
                "opportunity_blocks": {"reconciliation_blocked": 2, "guard_rejected": 5, "tp_net_edge_suppressed": 0},
            },
            "optimization_hints": [{"recommendation": "先修持仓漂移"}],
        }
    )
    assert "主要阻塞点在对账保护" in out["verdict"]
    assert out["next_actions"][0] == "先修持仓漂移"


def test_humanized_memory_stats_summary_handles_zero_trade_records():
    out = _build_humanized_memory_stats_summary(
        {"short_term_count": 4, "long_term_count": 9, "trade_records": 0, "risk_events": 0}
    )
    assert "短期记忆 4 条" in out["headline"]
    assert "trade_close" in out["next_actions"][0]


def test_humanized_profit_ops_overview_mentions_readiness():
    out = _build_humanized_profit_ops_overview(
        {
            "profit_attribution": {
                "regime": [{"regime": "trend", "total_pnl": 20}, {"regime": "volatile", "total_pnl": -10}],
                "health": {
                    "sample": {"total": 12},
                    "coverage": {"regime_coverage": 0.5},
                    "readiness": {"ready_for_regime_tuning": False},
                },
            },
            "profit_protect_debug": {"active_count": 3},
        }
    )
    assert "还不建议直接按 regime 自动调参" in out["verdict"]
    assert out["focus_cards"][2]["summary"] == "活跃保护订单 3 个。"


def test_humanized_platform_oversight_surfaces_component_and_route_counts():
    payload = {
        "component_inventory": [{"available": True}, {"available": False, "component": "execution_gateway", "responsibility": "执行脊柱"}, {"available": True}],
        "route_inventory": {"summary": {"total_routes": 88}},
        "order_tracking": {"positions_summary": {"position_count": 2}, "active_orders_summary": {"active_sltp_orders": 4}},
        "closed_loop_summary": {"loop_health": {"active_alerts": 1}, "humanized": {"headline": "闭环正常", "next_actions": ["先处理活跃告警"]}},
        "agent_effectiveness": {"summary": {"realized_trade_linked_trace_count": 0, "agent_trace_coverage_ratio": 0.2}, "humanized": {"next_actions": ["继续打通收益归因"]}},
        "profit_ops_overview": {"humanized": {"next_actions": ["检查盈利保护参数"]}, "profit_attribution": {"health": {"readiness": {"ready_for_regime_tuning": False}}}},
        "memory_stats": {"trade_records": 0},
        "route_catalog_alignment": {"static_catalog_routes": 90, "runtime_static_overlap": 10},
    }
    payload["priority_alerts"] = _build_platform_alerts(payload)
    out = _build_humanized_platform_oversight(payload)
    assert "88 条运行时路由" in out["headline"]
    assert out["verdict"] == "当前存在需要立即处理的关键风险项。"
    assert out["next_actions"][0] == "先处理活跃告警"


def test_platform_alerts_prioritize_critical_component_gaps():
    alerts = _build_platform_alerts(
        {
            "component_inventory": [{"available": False, "component": "ai_core", "responsibility": "AI 决策"}],
            "closed_loop_summary": {"loop_health": {"active_alerts": 2}, "execution_and_reconciliation": {"reconciliation_summary": {"drift_total": 1}}},
            "agent_effectiveness": {"summary": {"realized_trade_linked_trace_count": 0, "agent_trace_coverage_ratio": 0.1}},
            "profit_ops_overview": {"profit_attribution": {"health": {"readiness": {"ready_for_regime_tuning": False}}}},
            "memory_stats": {"trade_records": 0},
            "route_catalog_alignment": {"static_catalog_routes": 5, "runtime_static_overlap": 0},
            "order_tracking": {"positions_summary": {"position_count": 1}, "active_orders_summary": {"active_sltp_orders": 0}},
        }
    )
    assert alerts[0]["severity"] == "critical"
    assert "核心组件缺失" in alerts[0]["title"] or "持仓存在漂移" not in alerts[0]["title"]
    assert any(x["area"] == "position_protection" for x in alerts)
