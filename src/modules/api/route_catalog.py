"""
OpenClaw HTTP API — 标准域只读路由清单与「数据读取 / 分析」推荐链路。

用途：
- 挂载到 ``GET /api/v1/surface/registry`` 的 ``read_pipeline`` / ``core_http_catalog``；
- 供脚本、巡检与前端对齐「规范入口」，避免散落硬编码路径。

说明：本文件为**文档化清单**，不自动校验运行时是否已注册路由；与 ``module_surface.build_static_route_catalog`` 互补。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from src.modules.api.standard_registry import canonical_routes

CATALOG_VERSION = "2026.05.15"


def read_pipeline_spec() -> Dict[str, Any]:
    """
    推荐的只读巡检 / 分析顺序（由监控脚本与人工排障复用）。

    原则：先系统与脊柱验收 → 交易所与账户 → 行情与融合 → 成交与对账。
    """
    return {
        "version": CATALOG_VERSION,
        "generated_at": datetime.now().isoformat(),
        "steps": [
            {
                "order": 1,
                "id": "system_health",
                "method": "GET",
                "path": "/api/v1/system/health",
                "note": "进程存活 + 交易所公网探针",
            },
            {
                "order": 2,
                "id": "system_status",
                "method": "GET",
                "path": "/api/v1/system/status",
                "note": "模块连接态与运行摘要",
            },
            {
                "order": 3,
                "id": "commander_system_mastery",
                "method": "GET",
                "path": "/api/v1/commander/system-mastery?symbol=BTC/USDT",
                "note": "单接口全局总览：系统、行情、账户、决策、执行、收益、学习、优化建议",
            },
            {
                "order": 4,
                "id": "s1_verify",
                "method": "GET",
                "path": "/api/v1/s1/verify",
                "note": "执行脊柱 / ai_core / 单写者等硬门禁",
            },
            {
                "order": 5,
                "id": "system_acceptance",
                "method": "GET",
                "path": "/api/v1/system/acceptance",
                "note": "架构师验收快照（与 prod_stability_check 对齐）",
            },
            {
                "order": 6,
                "id": "exchanges",
                "method": "GET",
                "path": "/api/v1/exchanges",
                "note": "交易所 REST 会话连接态",
            },
            {
                "order": 7,
                "id": "balance_positions",
                "method": "GET",
                "path": "/api/v1/account/snapshot",
                "note": "账户与持仓标准域快照；旧 /api/v1/balance 与 /api/v1/positions 仅作兼容",
            },
            {
                "order": 8,
                "id": "market_ticker",
                "method": "GET",
                "path": "/api/v1/market/snapshot?symbol=BTC/USDT",
                "note": "单品种行情标准域快照；旧 ticker 路径仅作兼容",
            },
            {
                "order": 9,
                "id": "data_hub",
                "method": "GET",
                "path": "/api/v1/data/snapshot?symbol=BTC/USDT",
                "note": "统一数据源中心状态 + 融合快照（顶层入口，推荐）",
            },
            {
                "order": 10,
                "id": "strategy_overview",
                "method": "GET",
                "path": "/api/v1/strategy/overview",
                "note": "策略运行、评分、筛选、审批与收益表现",
            },
            {
                "order": 11,
                "id": "trade_lifecycle",
                "method": "GET",
                "path": "/api/v1/trades/lifecycle",
                "note": "开仓、平仓、SLTP、拒单后验、收益归因",
            },
            {
                "order": 12,
                "id": "agent_effectiveness",
                "method": "GET",
                "path": "/api/v1/agents/effectiveness",
                "note": "智能体覆盖率、verdict 分布与收益闭环关联",
            },
            {
                "order": 13,
                "id": "trading_workflow",
                "method": "GET",
                "path": "/api/v1/commander/trading-workflow?symbol=BTC/USDT",
                "note": "交易全链路工作流：数据、行情、持仓、拒单、开平仓理由、收益与优化动作",
            },
            {
                "order": 14,
                "id": "trades_recent_stats",
                "method": "GET",
                "path": "/api/v1/commander/closed-loop",
                "note": "成交明细与汇总统计",
            },
            {
                "order": 15,
                "id": "execution_spine",
                "method": "GET",
                "path": "/api/v1/execution/spine",
                "note": "ExecutionGateway 单写者、开仓门控、执行状态",
            },
            {
                "order": 16,
                "id": "plugins_registry",
                "method": "GET",
                "path": "/api/v1/plugins/registry",
                "note": "插件与技能注册表",
            },
            {
                "order": 17,
                "id": "surface_registry",
                "method": "GET",
                "path": "/api/v1/surface/registry",
                "note": "标准接口发现入口与核心 HTTP catalog",
            },
        ],
    }


def _r(method: str, path: str, domain: str, note: str = "") -> Dict[str, Any]:
    return {
        "method": method,
        "path": path,
        "status": "implemented",
        "domain": domain,
        "note": note,
        "catalog": "core_http",
    }


def extended_core_routes() -> List[Dict[str, Any]]:
    """顶层 /api/v1 下常用只读路由（补充 module_surface 静态表）。"""
    standard = [
        _r(r.method, r.path, r.domain, r.summary) for r in canonical_routes()
    ]
    legacy = [
        _r("GET", "/api/v1/system/health", "system", "系统健康"),
        _r("GET", "/api/v1/system/status", "system", "模块状态"),
        _r("GET", "/api/v1/system/acceptance", "system", "验收快照"),
        _r("GET", "/api/v1/s1/verify", "s1", "脊柱自检"),
        _r("GET", "/api/v1/exchanges", "exchange", "交易所连接"),
        _r("GET", "/api/v1/balance", "account", "余额"),
        _r("GET", "/api/v1/positions", "account", "持仓"),
        _r("GET", "/api/v1/market/ticker", "market", "行情 ticker（query: symbol）"),
        _r("GET", "/api/v1/market/ticker/{symbol}", "market", "行情 ticker（path）"),
        _r("GET", "/api/v1/market/klines", "market", "K 线"),
        _r("GET", "/api/v1/market/symbol/{symbol}", "market", "单品种 MI 视图"),
        _r("GET", "/api/v1/data-hub/status", "data", "数据源中心状态"),
        _r("GET", "/api/v1/data-hub/unified-snapshot", "data", "融合快照（推荐顶层）"),
        _r("GET", "/api/v1/data-hub/contract", "data", "采集契约"),
        _r("GET", "/api/v1/data-hub/quality-advice", "data", "质量建议"),
        _r("GET", "/api/v1/data-hub/ai-analysis", "data", "AI 分析摘要"),
        _r("GET", "/api/v1/commander/trading-workflow", "commander", "交易全链路工作流"),
        _r("GET", "/api/v1/commander/closed-loop", "commander", "闭环摘要"),
        _r("GET", "/api/v1/strategy/list", "strategy", "策略列表"),
        _r("POST", "/api/v1/strategy", "strategy", "创建策略"),
        _r("PUT", "/api/v1/strategy/{strategy_id}", "strategy", "更新策略"),
        _r("DELETE", "/api/v1/strategy/{strategy_id}", "strategy", "删除策略"),
        _r("POST", "/api/v1/strategy/{strategy_id}/approve", "strategy", "审批策略"),
        _r("POST", "/api/v1/strategy/{strategy_id}/activate", "strategy", "启用策略"),
        _r("POST", "/api/v1/strategy/{strategy_id}/deactivate", "strategy", "停用策略"),
    ]
    seen = {(r["method"], r["path"]) for r in standard}
    for row in legacy:
        key = (row["method"], row["path"])
        if key not in seen:
            row["status"] = "legacy"
            standard.append(row)
            seen.add(key)
    return standard
