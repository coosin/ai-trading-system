"""
OpenClaw HTTP API — 只读路由清单与「数据读取 / 分析」推荐链路。

用途：
- 挂载到 ``GET /api/v1/modules/surface/registry`` 的 ``read_pipeline`` / ``core_http_catalog``；
- 供脚本、巡检与前端对齐「规范入口」，避免散落硬编码路径。

说明：本文件为**文档化清单**，不自动校验运行时是否已注册路由；与 ``module_surface.build_static_route_catalog`` 互补。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

CATALOG_VERSION = "2026.05.13"


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
                "id": "s1_verify",
                "method": "GET",
                "path": "/api/v1/s1/verify",
                "note": "执行脊柱 / ai_core / 单写者等硬门禁",
            },
            {
                "order": 4,
                "id": "system_acceptance",
                "method": "GET",
                "path": "/api/v1/system/acceptance",
                "note": "架构师验收快照（与 prod_stability_check 对齐）",
            },
            {
                "order": 5,
                "id": "exchanges",
                "method": "GET",
                "path": "/api/v1/exchanges",
                "note": "交易所 REST 会话连接态",
            },
            {
                "order": 6,
                "id": "balance_positions",
                "method": "GET",
                "path": "/api/v1/balance 与 /api/v1/positions",
                "note": "账户与持仓（规范 REST；与 commander 诊断互补）",
            },
            {
                "order": 7,
                "id": "market_ticker",
                "method": "GET",
                "path": "/api/v1/market/ticker?symbol=BTC/USDT",
                "note": "单品种行情（交易所直连）",
            },
            {
                "order": 8,
                "id": "data_hub",
                "method": "GET",
                "path": "/api/v1/data-hub/status 与 /api/v1/data-hub/unified-snapshot?symbol=BTC/USDT",
                "note": "统一数据源中心状态 + 融合快照（顶层入口，推荐）",
            },
            {
                "order": 9,
                "id": "modules_unified_snapshot",
                "method": "GET",
                "path": "/api/v1/modules/data/hub/unified-snapshot?symbol=BTC/USDT",
                "note": "与 data-hub 等价能力的 modules 前缀别名（自动化/旧脚本）",
            },
            {
                "order": 10,
                "id": "external_signals",
                "method": "GET",
                "path": "/api/v1/external/signals?symbol=BTC/USDT",
                "note": "外部信号入口（DataSourceHub）",
            },
            {
                "order": 11,
                "id": "trading_diagnosis",
                "method": "GET",
                "path": "/api/v1/modules/commander/trading-diagnosis",
                "note": "交易全链路诊断（ai_core / 门控 / 持仓等）",
            },
            {
                "order": 12,
                "id": "trades_recent_stats",
                "method": "GET",
                "path": "/api/v1/trades/recent 与 /api/v1/trades/statistics",
                "note": "成交明细与汇总统计",
            },
            {
                "order": 13,
                "id": "trades_analytics",
                "method": "GET",
                "path": "/api/v1/trades/analytics/summary",
                "note": "按策略 / regime / 小时等维度的分析摘要",
            },
            {
                "order": 14,
                "id": "trades_reconcile_report",
                "method": "GET",
                "path": "/api/v1/trades/reconcile/report",
                "note": "对账报告（可能较慢，宜异步或长超时）",
            },
            {
                "order": 15,
                "id": "data_integration_health",
                "method": "GET",
                "path": "/api/v1/modules/data/integration/health",
                "note": "Binance/CoinGecko 等 HTTP 源健康（与交易所行情互补）",
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
    return [
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
        _r("GET", "/api/v1/external/analyze-trends", "data", "趋势分析"),
        _r("GET", "/api/v1/external/signals", "data", "外部信号"),
        _r("POST", "/api/v1/external/indicators", "data", "外部指标"),
        _r("GET", "/api/v1/trades", "trades", "成交列表"),
        _r("GET", "/api/v1/trades/recent", "trades", "最近成交"),
        _r("GET", "/api/v1/trades/history", "trades", "历史成交"),
        _r("GET", "/api/v1/trades/statistics", "trades", "成交统计"),
        _r("GET", "/api/v1/trades/analytics/summary", "trades", "分析摘要"),
        _r("GET", "/api/v1/trades/reconcile", "trades", "对账（可能慢）"),
        _r("GET", "/api/v1/trades/reconcile/report", "trades", "对账报告"),
        _r("GET", "/api/v1/executions", "executions", "执行记录"),
        _r("GET", "/api/v1/debug/exchange-binding", "debug", "MainController 绑定探针"),
    ]
