"""
统一模块 API 表面（Surface Registry）

供前端、Bot、运维一次性发现：已实现路由、预留路由、实时通道约定、契约版本。
与司令部主智能体 + 子专家（服务化）架构对齐；不包含业务逻辑，仅注册与薄委托。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body

CONTRACT_VERSION = "2026.04.10"
MODULES_PREFIX = "/api/v1/modules"
TRADE_PREFIX = "/api/v1/trade"
MARKET_PREFIX = "/api/v1/market"
S1_PREFIX = "/api/v1/s1"


def _reserved(domain: str, path_hint: str) -> Dict[str, Any]:
    return {
        "success": True,
        "implemented": False,
        "reserved": True,
        "contract_version": CONTRACT_VERSION,
        "domain": domain,
        "path_hint": path_hint,
        "message": "预留接口：后续版本将实现；请勿依赖当前行为。",
        "timestamp": datetime.now().isoformat(),
    }


def build_static_route_catalog() -> List[Dict[str, Any]]:
    """文档化全站模块 API（含已实现与预留）。"""
    impl = "implemented"
    res = "reserved"

    def r(method: str, path: str, status: str, domain: str, note: str = "") -> Dict[str, Any]:
        return {"method": method, "path": path, "status": status, "domain": domain, "note": note}

    rows: List[Dict[str, Any]] = []

    # Commander / 编排
    for method, path, note in [
        ("GET", f"{MODULES_PREFIX}/commander/snapshot", "司令部快照"),
        ("GET", f"{MODULES_PREFIX}/commander/capabilities", "能力 + 子专家清单"),
        ("POST", f"{MODULES_PREFIX}/commander/dispatch", "统一对话/指令，source 区分渠道"),
        ("POST", f"{MODULES_PREFIX}/commander/chores", "日常任务"),
        ("GET", f"{MODULES_PREFIX}/commander/audit", "链路审查"),
        ("GET", f"{MODULES_PREFIX}/commander/memory/status", "记忆自检"),
        ("GET", f"{MODULES_PREFIX}/commander/memory/workspace", "workspace 记忆文件"),
        ("GET", f"{MODULES_PREFIX}/commander/memory/persona-preview", "人格注入预览"),
        ("GET", f"{MODULES_PREFIX}/commander/account-diagnostics", "账户诊断"),
        ("POST", f"{MODULES_PREFIX}/commander/account-sync/run", "强制同步账户"),
    ]:
        rows.append(r(method, path, impl, "commander", note))

    # 模块控制（节选）
    for method, path, note in [
        ("GET", f"{MODULES_PREFIX}/list", "模块列表"),
        ("POST", f"{MODULES_PREFIX}/{{module_id}}/control", "启停控制"),
        ("GET", f"{MODULES_PREFIX}/system/health", "系统健康"),
        ("GET", f"{MODULES_PREFIX}/memory/stats", "记忆统计"),
        ("GET", f"{MODULES_PREFIX}/risk/status", "风控状态"),
        ("GET", f"{MODULES_PREFIX}/strategy/optimization-status", "策略优化状态"),
        ("POST", f"{MODULES_PREFIX}/strategy/research-run", "策略研究任务"),
        ("GET", f"{MODULES_PREFIX}/strategy/research-jobs", "研究任务列表"),
        ("GET", f"{MODULES_PREFIX}/execution/production-audit", "生产执行审计"),
    ]:
        rows.append(r(method, path, impl, "modules", note))

    # 交易域 / 行情域（独立 router 前缀）
    for method, path, note in [
        ("GET", f"{TRADE_PREFIX}/events", "交易事件流查询（前端轮询/WS 配合）"),
        ("GET", f"{TRADE_PREFIX}/execution_spine", "执行脊柱快照"),
        ("GET", f"{MARKET_PREFIX}/symbol/{{symbol}}", "单品种 MI 视图"),
        ("GET", f"{MARKET_PREFIX}/state", "市场聚合状态"),
    ]:
        rows.append(r(method, path, impl, "market_execution", note))

    # S1
    rows.append(r("GET", f"{S1_PREFIX}/verify", impl, "s1", "全自动验收探针"))

    # 预留：数据 / 执行 / 智能 / 技能 / 插件（薄扩展位）
    reserved_paths = [
        ("GET", f"{MODULES_PREFIX}/data/integration/health", "data", "数据源集成健康度"),
        ("GET", f"{MODULES_PREFIX}/data/onchain/status", "data", "链上集成状态"),
        ("POST", f"{MODULES_PREFIX}/intelligence/batch-analyze", "intelligence", "批量分析任务"),
        ("POST", f"{MODULES_PREFIX}/execution/simulate-order", "execution", "模拟下单（纸交易）"),
        ("GET", f"{MODULES_PREFIX}/plugins/status", "plugins", "插件状态"),
    ]
    for method, path, domain, note in reserved_paths:
        rows.append(r(method, path, res, domain, note))

    # 已实现：技能目录与调用（委托 SkillManager）
    rows.append(r("GET", f"{MODULES_PREFIX}/skills/catalog", impl, "skills", "已注册技能名"))
    rows.append(r("POST", f"{MODULES_PREFIX}/skills/invoke", impl, "skills", "按 skill_name 调用"))
    rows.append(r("GET", f"{MODULES_PREFIX}/data/hub/unified-snapshot", impl, "data", "统一数据源快照"))
    rows.append(r("GET", f"{MODULES_PREFIX}/surface/registry", impl, "surface", "API 总注册表"))
    rows.append(r("GET", f"{MODULES_PREFIX}/surface/channels", impl, "surface", "渠道契约"))

    return rows


def build_channel_contract() -> Dict[str, Any]:
    """前端与实时通道对接约定（HTTP + WS 摘要）。"""
    return {
        "contract_version": CONTRACT_VERSION,
        "http": {
            "commander_inbox": {
                "method": "POST",
                "path": f"{MODULES_PREFIX}/commander/dispatch",
                "body": {"message": "string", "source": "control_hub | telegram | api_chat | ..."},
            },
            "registry": {"method": "GET", "path": f"{MODULES_PREFIX}/surface/registry"},
        },
        "websocket": {
            "note": "APIServer 内置 WebSocket 广播；订阅语义见服务端 WebSocketSubscribeRequest / channel 前缀。",
            "trade_events_channel_hint": "trade.* 可与 GET /api/v1/trade/events 对照",
        },
        "telegram": {
            "note": "Bot 长轮询/ webhook 由 TelegramBot 接入；业务语义应与 commander dispatch 一致（同一 process_user_command 链）。",
        },
    }


def attach_module_surface_routes(router: APIRouter, main_controller: Any) -> None:
    """向已有 /api/v1/modules 路由挂载 surface 与薄委托接口。"""

    @router.get("/surface/registry")
    async def surface_registry() -> Dict[str, Any]:
        catalog = build_static_route_catalog()
        cap: Dict[str, Any] = {}
        if main_controller and hasattr(main_controller, "get_commander_capabilities"):
            try:
                cap = main_controller.get_commander_capabilities()
            except Exception as e:
                cap = {"error": str(e)}
        return {
            "success": True,
            "contract_version": CONTRACT_VERSION,
            "catalog": catalog,
            "commander_capabilities": cap,
            "channels": build_channel_contract(),
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/surface/channels")
    async def surface_channels() -> Dict[str, Any]:
        return {"success": True, "data": build_channel_contract(), "timestamp": datetime.now().isoformat()}

    @router.get("/data/hub/unified-snapshot")
    async def data_hub_unified_snapshot(symbol: str = "BTC/USDT") -> Dict[str, Any]:
        mc = main_controller
        hub = getattr(mc, "data_source_hub", None) if mc else None
        if not hub or not hasattr(hub, "get_unified_snapshot"):
            return _reserved("data", "/modules/data/hub/unified-snapshot")
        try:
            snap = await asyncio.wait_for(hub.get_unified_snapshot(symbol), timeout=8.0)
            return {
                "success": True,
                "implemented": True,
                "symbol": symbol,
                "data": snap,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/reserved/{domain}/ping")
    async def reserved_domain_ping(domain: str) -> Dict[str, Any]:
        return _reserved(domain, f"/modules/reserved/{domain}/ping")

    @router.post("/skills/invoke")
    async def skills_invoke_reserved(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
        """预留：按技能名执行；实现时将委托 SkillManager。"""
        mc = main_controller
        sm = getattr(mc, "skill_manager", None) if mc else None
        name = str((payload or {}).get("skill_name") or "").strip()
        ctx = (payload or {}).get("context") if isinstance((payload or {}).get("context"), dict) else {}
        if not sm or not name or not hasattr(sm, "execute_skill"):
            out = _reserved("skills", "/modules/skills/invoke")
            out["hint"] = {"skill_name": name or None, "context_keys": list(ctx.keys())}
            return out
        try:
            result = await sm.execute_skill(name, ctx)
            if result is not None and hasattr(result, "to_dict"):
                out = result.to_dict()
            elif result is not None:
                out = {"raw": str(result)}
            else:
                out = None
            return {
                "success": True,
                "implemented": True,
                "skill_name": name,
                "result": out,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/skills/catalog")
    async def skills_catalog() -> Dict[str, Any]:
        mc = main_controller
        sm = getattr(mc, "skill_manager", None) if mc else None
        if not sm or not getattr(sm, "skills", None):
            return _reserved("skills", "/modules/skills/catalog")
        names = sorted(list(sm.skills.keys()))
        return {
            "success": True,
            "implemented": True,
            "skills": names,
            "count": len(names),
            "timestamp": datetime.now().isoformat(),
        }
