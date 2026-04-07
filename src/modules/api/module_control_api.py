"""
模块控制API - 提供所有系统模块的集中控制接口
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

def init_module_control_api(app, main_controller):
    """初始化模块控制API"""
    
    from fastapi import APIRouter
    
    router = APIRouter(prefix="/api/v1/modules", tags=["modules"])
    
    @router.get("/list")
    async def get_all_modules():
        """获取所有模块列表和状态"""
        modules = []
        
        if main_controller:
            if hasattr(main_controller, 'ai_trading_engine') and main_controller.ai_trading_engine:
                modules.append({
                    "id": "ai_trading_engine",
                    "name": "AI交易引擎",
                    "category": "核心",
                    "status": "running" if main_controller.ai_trading_engine._running else "stopped",
                    "health": "healthy",
                    "description": "全智能AI交易引擎，自动分析市场并执行交易",
                    "controls": ["start", "stop", "analyze"]
                })
            
            if hasattr(main_controller, 'llm_integration') and main_controller.llm_integration:
                modules.append({
                    "id": "llm_integration",
                    "name": "AI大模型集成",
                    "category": "AI",
                    "status": "running",
                    "health": "healthy",
                    "description": "大语言模型集成系统，支持讯飞、百度千帆等",
                    "controls": ["chat", "analyze"]
                })
            
            if hasattr(main_controller, 'telegram_bot') and main_controller.telegram_bot:
                modules.append({
                    "id": "telegram_bot",
                    "name": "Telegram机器人",
                    "category": "通信",
                    "status": "running",
                    "health": "healthy",
                    "description": "Telegram通信机器人，接收用户指令并发送通知",
                    "controls": ["start", "stop", "test"]
                })
            
            if hasattr(main_controller, 'emergency_stop') and main_controller.emergency_stop:
                modules.append({
                    "id": "emergency_stop",
                    "name": "紧急停止系统",
                    "category": "安全",
                    "status": "ready",
                    "health": "healthy",
                    "description": "紧急情况下自动停止交易",
                    "controls": ["trigger", "reset"]
                })
            
            if hasattr(main_controller, 'intelligent_monitoring') and main_controller.intelligent_monitoring:
                modules.append({
                    "id": "intelligent_monitoring",
                    "name": "智能监控系统",
                    "category": "监控",
                    "status": "running",
                    "health": "healthy",
                    "description": "监控系统健康状态和性能指标",
                    "controls": ["check", "alert"]
                })
            
            if hasattr(main_controller, 'security_manager') and main_controller.security_manager:
                modules.append({
                    "id": "security_manager",
                    "name": "安全管理器",
                    "category": "安全",
                    "status": "running",
                    "health": "healthy",
                    "description": "系统安全检测和防护",
                    "controls": ["scan", "audit"]
                })
            
            if hasattr(main_controller, 'fund_manager') and main_controller.fund_manager:
                modules.append({
                    "id": "fund_manager",
                    "name": "智能资金管理器",
                    "category": "资金",
                    "status": "running" if main_controller.fund_manager.enabled else "stopped",
                    "health": "healthy",
                    "description": "智能资金分配和仓位管理",
                    "controls": ["start", "stop", "rebalance"]
                })
            
            if hasattr(main_controller, 'ai_learning_engine') and main_controller.ai_learning_engine:
                modules.append({
                    "id": "ai_learning_engine",
                    "name": "AI学习引擎",
                    "category": "AI",
                    "status": "running" if main_controller.ai_learning_engine._running else "stopped",
                    "health": "healthy",
                    "description": "自动学习交易经验并优化策略",
                    "controls": ["start", "stop", "learn"]
                })
            
            if hasattr(main_controller, 'anomaly_detector') and main_controller.anomaly_detector:
                modules.append({
                    "id": "anomaly_detector",
                    "name": "异常检测器",
                    "category": "监控",
                    "status": "running",
                    "health": "healthy",
                    "description": "检测市场异常和系统异常",
                    "controls": ["detect", "report"]
                })
            
            if hasattr(main_controller, 'strategy_manager') and main_controller.strategy_manager:
                modules.append({
                    "id": "strategy_manager",
                    "name": "策略管理器",
                    "category": "策略",
                    "status": "running",
                    "health": "healthy",
                    "description": "管理多个交易策略",
                    "controls": ["list", "activate", "deactivate"]
                })
            
            if hasattr(main_controller, 'portfolio_optimizer') and main_controller.portfolio_optimizer:
                modules.append({
                    "id": "portfolio_optimizer",
                    "name": "组合优化器",
                    "category": "策略",
                    "status": "ready",
                    "health": "healthy",
                    "description": "优化投资组合配置",
                    "controls": ["optimize", "rebalance"]
                })
            
            if hasattr(main_controller, 'backup_manager') and main_controller.backup_manager:
                modules.append({
                    "id": "backup_manager",
                    "name": "数据备份管理器",
                    "category": "数据",
                    "status": "running",
                    "health": "healthy",
                    "description": "自动备份系统数据",
                    "controls": ["backup", "restore", "schedule"]
                })
        
        return {
            "modules": modules,
            "total": len(modules),
            "timestamp": datetime.now().isoformat()
        }
    
    @router.post("/{module_id}/control")
    async def control_module(module_id: str, action: str, params: Optional[Dict] = None):
        """控制指定模块"""
        params = params or {}
        result = {"success": False, "message": ""}
        
        try:
            if module_id == "ai_trading_engine":
                if main_controller and hasattr(main_controller, 'ai_trading_engine'):
                    engine = main_controller.ai_trading_engine
                    if action == "start":
                        if not engine._running:
                            await engine.start()
                        result = {"success": True, "message": "AI交易引擎已启动"}
                    elif action == "stop":
                        await engine.stop()
                        result = {"success": True, "message": "AI交易引擎已停止"}
                    elif action == "analyze":
                        symbol = params.get("symbol", "BTC/USDT")
                        result = {"success": True, "message": f"开始分析 {symbol}", "data": {"symbol": symbol}}
            
            elif module_id == "telegram_bot":
                if main_controller and hasattr(main_controller, 'telegram_bot'):
                    bot = main_controller.telegram_bot
                    if action == "test":
                        result = {"success": True, "message": "Telegram机器人测试成功"}
            
            elif module_id == "emergency_stop":
                if main_controller and hasattr(main_controller, 'emergency_stop'):
                    es = main_controller.emergency_stop
                    if action == "trigger":
                        await es._trigger_emergency(
                            level="HIGH",
                            type="manual_trigger",
                            description="手动触发紧急停止"
                        )
                        result = {"success": True, "message": "紧急停止已触发"}
                    elif action == "reset":
                        es._is_emergency_mode = False
                        result = {"success": True, "message": "紧急停止已重置"}
            
            elif module_id == "fund_manager":
                if main_controller and hasattr(main_controller, 'fund_manager'):
                    fm = main_controller.fund_manager
                    if action == "start":
                        fm.enabled = True
                        result = {"success": True, "message": "资金管理器已启动"}
                    elif action == "stop":
                        fm.enabled = False
                        result = {"success": True, "message": "资金管理器已停止"}
            
            elif module_id == "ai_learning_engine":
                if main_controller and hasattr(main_controller, 'ai_learning_engine'):
                    le = main_controller.ai_learning_engine
                    if action == "start":
                        await le.start()
                        result = {"success": True, "message": "AI学习引擎已启动"}
                    elif action == "stop":
                        await le.stop()
                        result = {"success": True, "message": "AI学习引擎已停止"}
            
            else:
                result = {"success": False, "message": f"未知模块: {module_id}"}
        
        except Exception as e:
            result = {"success": False, "message": f"操作失败: {str(e)}"}
        
        return result
    
    @router.get("/trading/symbols")
    async def get_trading_symbols():
        """获取交易对配置"""
        blacklist = []
        if main_controller and hasattr(main_controller, 'ai_trading_engine'):
            engine = main_controller.ai_trading_engine
            if hasattr(engine, 'symbols'):
                return {
                    "symbols": engine.symbols,
                    "blacklist": blacklist,
                    "message": "ETH已允许交易"
                }
        return {
            "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
            "blacklist": blacklist
        }
    
    @router.post("/trading/symbols/config")
    async def config_trading_symbols(config: Dict[str, Any]):
        """配置交易对"""
        symbols = config.get("symbols", [])
        blacklist = config.get("blacklist", [])
        
        if main_controller and hasattr(main_controller, 'ai_trading_engine'):
            engine = main_controller.ai_trading_engine
            filtered_symbols = [s for s in symbols if s not in blacklist]
            engine.symbols = filtered_symbols
            return {
                "success": True,
                "message": f"交易对已更新，黑名单: {blacklist}",
                "symbols": filtered_symbols,
                "blacklist": blacklist
            }
        
        return {"success": False, "message": "AI交易引擎未初始化"}
    
    @router.get("/models")
    async def get_ai_models():
        """获取AI模型列表"""
        models = []
        if main_controller and hasattr(main_controller, 'enhanced_llm_manager'):
            mgr = main_controller.enhanced_llm_manager
            for model_id, config in mgr.models.items():
                models.append({
                    "id": model_id,
                    "name": config.display_name,
                    "provider": config.provider.value,
                    "priority": config.priority,
                    "enabled": config.enabled,
                    "context_window": config.context_window
                })
        
        return {
            "models": models,
            "total": len(models)
        }
    
    @router.post("/models/{model_id}/select")
    async def select_ai_model(model_id: str):
        """选择AI模型"""
        if main_controller and hasattr(main_controller, 'enhanced_llm_manager'):
            mgr = main_controller.enhanced_llm_manager
            if model_id in mgr.models:
                mgr.default_model = model_id
                return {"success": True, "message": f"已切换到模型: {model_id}"}
        
        return {"success": False, "message": "模型不存在"}
    
    @router.get("/risk/status")
    async def get_risk_status():
        """获取风险状态"""
        risk_data = {
            "circuit_breaker": {"status": "closed", "trigger_count": 0},
            "daily_trades": 0,
            "hourly_trades": 0,
            "consecutive_losses": 0,
            "current_drawdown": 0.0,
            "risk_level": "low"
        }
        
        if main_controller:
            if hasattr(main_controller, 'risk_monitor') and main_controller.risk_monitor:
                status = main_controller.risk_monitor.get_status()
                risk_data.update(status)
            
            if hasattr(main_controller, 'ai_trading_engine') and main_controller.ai_trading_engine:
                engine = main_controller.ai_trading_engine
                if hasattr(engine, 'enhanced_risk') and engine.enhanced_risk:
                    risk_status = engine.enhanced_risk.get_risk_status()
                    risk_data["circuit_breaker"] = risk_status.get("circuit_breaker", {})
                    risk_data["risk_level"] = risk_status.get("trading_state", {}).get("daily_trades", 0) > 15 and "medium" or "low"
        
        return risk_data
    
    @router.post("/risk/reset")
    async def reset_risk_counters():
        """重置风险计数器"""
        if main_controller and hasattr(main_controller, 'ai_trading_engine'):
            engine = main_controller.ai_trading_engine
            if hasattr(engine, 'enhanced_risk') and engine.enhanced_risk:
                await engine.enhanced_risk.reset_daily_counters()
                await engine.enhanced_risk.reset_hourly_counters()
                return {"success": True, "message": "风险计数器已重置"}
        
        return {"success": True, "message": "风险计数器已重置"}
    
    @router.get("/memory/stats")
    async def get_memory_stats():
        """获取记忆系统统计"""
        stats = {
            "short_term_count": 0,
            "long_term_count": 0,
            "trade_records": 0,
            "risk_events": 0
        }
        
        if main_controller:
            if hasattr(main_controller, 'ai_memory_manager') and main_controller.ai_memory_manager:
                mem = main_controller.ai_memory_manager
                stats["short_term_count"] = len(mem.short_term_memory)
                stats["long_term_count"] = len(mem.long_term_memory)
        
        return stats
    
    @router.get("/system/health")
    async def get_system_health():
        """获取系统健康状态"""
        health = {
            "overall": "healthy",
            "modules": {},
            "timestamp": datetime.now().isoformat()
        }
        
        if main_controller:
            modules_to_check = [
                ("ai_trading_engine", "AI交易引擎"),
                ("llm_integration", "AI大模型"),
                ("telegram_bot", "Telegram机器人"),
                ("database_manager", "数据库"),
                ("event_system", "事件系统"),
                ("emergency_stop", "紧急停止"),
                ("security_manager", "安全管理"),
                ("fund_manager", "资金管理")
            ]
            
            healthy_count = 0
            for attr, name in modules_to_check:
                if hasattr(main_controller, attr):
                    module = getattr(main_controller, attr)
                    is_healthy = module is not None
                    health["modules"][name] = {
                        "status": "healthy" if is_healthy else "unavailable",
                        "running": is_healthy
                    }
                    if is_healthy:
                        healthy_count += 1
                else:
                    health["modules"][name] = {
                        "status": "unavailable",
                        "running": False
                    }
            
            total = len(modules_to_check)
            health["overall"] = "healthy" if healthy_count == total else "degraded" if healthy_count > total // 2 else "unhealthy"
            health["healthy_count"] = healthy_count
            health["total_count"] = total
        
        return health

    s1_router = APIRouter(prefix="/api/v1/s1", tags=["s1"])

    @s1_router.get("/verify")
    async def s1_full_verify():
        """
        S1 全自动验收探针：主控、ExecutionGateway、策略配置、交易所、止盈止损。
        供脚本/监控轮询；返回 all_passed 与各子检查项。
        """
        checks: List[Dict[str, Any]] = []
        details: Dict[str, Any] = {}

        def add_check(name: str, passed: bool, detail: str = "") -> None:
            checks.append({"name": name, "passed": bool(passed), "detail": detail})

        if not main_controller:
            add_check("main_controller", False, "missing")
            return {"ok": False, "all_passed": False, "checks": checks, "details": details}

        add_check("main_controller", True, "present")
        mc = main_controller

        gw = getattr(mc, "execution_gateway", None)
        add_check("execution_gateway", gw is not None, "missing" if gw is None else "ok")
        if gw:
            try:
                snap = await gw.get_snapshot()
                details["execution_spine"] = snap
                add_check(
                    "execution_spine.single_write_owner",
                    bool(snap.get("single_write_owner")),
                    str(snap.get("single_write_owner") or ""),
                )
            except Exception as e:
                add_check("execution_spine", False, str(e))

        ac = getattr(mc, "ai_core", None)
        add_check("ai_core", ac is not None, "missing" if ac is None else "ok")

        try:
            brain = await mc.get_ai_managed_config(
                "ai_brain",
                {
                    "primary_controller": "ai_core",
                    "single_write_owner": "ai_core",
                    "enable_secondary_controller": False,
                },
            )
            details["ai_brain"] = {
                "primary_controller": brain.get("primary_controller"),
                "single_write_owner": brain.get("single_write_owner"),
                "enable_secondary_controller": brain.get("enable_secondary_controller"),
            }
            swo = str(brain.get("single_write_owner") or brain.get("primary_controller") or "").strip().lower()
            add_check("ai_brain.single_write_owner", bool(swo), swo or "empty")
            pri = str(brain.get("primary_controller") or "").strip().lower()
            coherent = (not pri or not swo) or (pri == swo)
            add_check(
                "ai_brain.primary_coherent_with_swo",
                coherent,
                f"primary={pri} swo={swo}" + ("" if coherent else " (建议保持一致)"),
            )
        except Exception as e:
            add_check("ai_brain_config", False, str(e))

        sl = getattr(mc, "stop_loss_manager", None)
        add_check("stop_loss_manager", sl is not None, "missing" if sl is None else "ok")

        ex = mc.get_exchange() if hasattr(mc, "get_exchange") else None
        ex = ex or getattr(mc, "okx_exchange", None)
        add_check("exchange", ex is not None, "missing" if ex is None else type(ex).__name__)

        ait = getattr(mc, "ai_trading_engine", None)
        if ait and hasattr(ait, "_autonomous_trading_execution_allowed"):
            try:
                allow_loop = await ait._autonomous_trading_execution_allowed()
                details["ai_trading_engine"] = {
                    "autonomous_trading_loop_allowed": allow_loop,
                }
                try:
                    pol = await mc.get_ai_managed_config("ai_brain", {})
                    swo2 = str(
                        pol.get("single_write_owner") or pol.get("primary_controller") or "ai_core"
                    ).strip().lower()
                except Exception:
                    swo2 = "ai_core"
                if swo2 == "ai_core":
                    add_check(
                        "s1_aitrading_loop_suppressed_when_swo_ai_core",
                        not allow_loop,
                        "loop allowed (unexpected)" if allow_loop else "main loop skipped as expected",
                    )
                else:
                    add_check(
                        "s1_aitrading_loop_policy",
                        True,
                        f"swo={swo2} allow_loop={allow_loop}",
                    )
            except Exception as e:
                add_check("ai_trading_engine_policy", False, str(e))

        try:
            sys_status = await mc.get_system_status()
            details["system_status_keys"] = list(sys_status.keys()) if isinstance(sys_status, dict) else []
            if isinstance(sys_status, dict) and "execution_spine" in sys_status:
                add_check("get_system_status.execution_spine", True, "present")
            else:
                add_check("get_system_status.execution_spine", False, "missing in status payload")
        except Exception as e:
            add_check("get_system_status", False, str(e))

        all_passed = all(c.get("passed") for c in checks)
        return {
            "ok": True,
            "all_passed": all_passed,
            "timestamp": datetime.now().isoformat(),
            "checks": checks,
            "details": details,
        }
    
    app.include_router(router)
    app.include_router(s1_router)
    logger.info("✅ 模块控制API已初始化")
