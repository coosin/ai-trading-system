from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI

from src.modules.api.standard_domains import CapabilityRoute, STANDARD_DOMAINS, assert_unique_capabilities


def canonical_routes() -> List[CapabilityRoute]:
    routes: List[CapabilityRoute] = [
        CapabilityRoute("system.health", "system", "GET", "/api/v1/system/health", "系统健康"),
        CapabilityRoute("system.status", "system", "GET", "/api/v1/system/status", "系统状态"),
        CapabilityRoute("account.snapshot", "account", "GET", "/api/v1/account/snapshot", "账户余额与持仓"),
        CapabilityRoute("market.snapshot", "market", "GET", "/api/v1/market/snapshot", "单品种行情快照"),
        CapabilityRoute("data.snapshot", "data", "GET", "/api/v1/data/snapshot", "多源数据快照"),
        CapabilityRoute("strategy.overview", "strategy", "GET", "/api/v1/strategy/overview", "策略运行、评分与筛选总览"),
        CapabilityRoute("strategy.list", "strategy", "GET", "/api/v1/strategy/list", "策略列表"),
        CapabilityRoute("strategy.create", "strategy", "POST", "/api/v1/strategy", "创建策略"),
        CapabilityRoute("strategy.update", "strategy", "PUT", "/api/v1/strategy/{strategy_id}", "更新策略"),
        CapabilityRoute("strategy.delete", "strategy", "DELETE", "/api/v1/strategy/{strategy_id}", "删除策略"),
        CapabilityRoute("strategy.approve", "strategy", "POST", "/api/v1/strategy/{strategy_id}/approve", "审批策略"),
        CapabilityRoute("strategy.activate", "strategy", "POST", "/api/v1/strategy/{strategy_id}/activate", "启用策略"),
        CapabilityRoute("strategy.deactivate", "strategy", "POST", "/api/v1/strategy/{strategy_id}/deactivate", "停用策略"),
        CapabilityRoute("risk.status", "risk", "GET", "/api/v1/risk/status", "风控状态"),
        CapabilityRoute("execution.spine", "execution", "GET", "/api/v1/execution/spine", "执行脊柱状态"),
        CapabilityRoute("trades.lifecycle", "trades", "GET", "/api/v1/trades/lifecycle", "开平仓与拒单后验"),
        CapabilityRoute("trades.backfill_trace_attribution", "trades", "POST", "/api/v1/trades/backfill-trace-attribution", "回填平仓记录 trace 归因"),
        CapabilityRoute("memory.overview", "memory", "GET", "/api/v1/memory/overview", "记忆与知识层状态"),
        CapabilityRoute("learning.overview", "learning", "GET", "/api/v1/learning/overview", "学习复盘与调优状态"),
        CapabilityRoute("learning.backfill_lessons", "learning", "POST", "/api/v1/learning/backfill-lessons", "将后验复盘候选写入学习层"),
        CapabilityRoute("agents.effectiveness", "agents", "GET", "/api/v1/agents/effectiveness", "智能体有效性"),
        CapabilityRoute("agents.advisory", "agents", "POST", "/api/v1/agents/advisory-snapshot", "智能体当前判定"),
        CapabilityRoute("commander.system_mastery", "commander", "GET", "/api/v1/commander/system-mastery", "全系统单接口总览"),
        CapabilityRoute("commander.closed_loop", "commander", "GET", "/api/v1/commander/closed-loop", "司令闭环状态"),
        CapabilityRoute("commander.trading_workflow", "commander", "GET", "/api/v1/commander/trading-workflow", "交易全链路工作流、原因与优化动作"),
        CapabilityRoute("plugins.registry", "plugins", "GET", "/api/v1/plugins/registry", "插件与技能注册表"),
        CapabilityRoute("surface.registry", "system", "GET", "/api/v1/surface/registry", "标准接口发现入口"),
    ]
    assert_unique_capabilities(routes)
    return routes


def build_standard_surface() -> Dict[str, Any]:
    routes = canonical_routes()
    by_domain: Dict[str, List[Dict[str, Any]]] = {domain: [] for domain in STANDARD_DOMAINS}
    for route in routes:
        by_domain.setdefault(route.domain, []).append(route.to_dict())
    return {
        "api_style": "/api/v1/{domain}/...",
        "domains": list(STANDARD_DOMAINS),
        "routes": [r.to_dict() for r in routes],
        "by_domain": by_domain,
    }


def attach_standard_domain_apis(app: FastAPI, main_controller: Any) -> None:
    if bool(getattr(getattr(app, "state", None), "openclaw_standard_domain_apis_attached", False)):
        return
    from src.modules.account.api import build_router as account_router
    from src.modules.agents.api import build_router as agents_router
    from src.modules.commander.api import build_router as commander_router
    from src.modules.data.api import build_router as data_router
    from src.modules.execution.api import build_router as execution_router
    from src.modules.learning.api import build_router as learning_router
    from src.modules.market.api import build_router as market_router
    from src.modules.memory.api import build_router as memory_router
    from src.modules.plugins.api import build_router as plugins_router
    from src.modules.risk.api import build_router as risk_router
    from src.modules.strategy.api import build_router as strategy_router
    from src.modules.system.api import build_router as system_router
    from src.modules.trades.api import build_router as trades_router

    for factory in (
        system_router,
        account_router,
        market_router,
        data_router,
        strategy_router,
        risk_router,
        execution_router,
        trades_router,
        memory_router,
        learning_router,
        agents_router,
        commander_router,
        plugins_router,
    ):
        app.include_router(factory(main_controller))
    app.state.openclaw_standard_domain_apis_attached = True
