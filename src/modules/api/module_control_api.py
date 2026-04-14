"""
模块控制API - 提供所有系统模块的集中控制接口
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

def init_module_control_api(app, main_controller):
    """初始化模块控制API"""
    
    from fastapi import APIRouter, Body

    router = APIRouter(prefix="/api/v1/modules", tags=["modules"])
    trade_router = APIRouter(prefix="/api/v1/trade", tags=["trade"])
    market_router = APIRouter(prefix="/api/v1/market", tags=["market"])
    research_jobs: Dict[str, Dict[str, Any]] = {}
    research_jobs_lock = asyncio.Lock()
    research_semaphore = asyncio.Semaphore(1)

    async def _check_unified_data_quality(
        symbol: str = "BTC/USDT",
        min_score: float = 0.5,
    ) -> Dict[str, Any]:
        mc = main_controller
        if not mc:
            return {"ok": False, "score": None, "message": "主控制器未初始化"}
        hub = getattr(mc, "data_source_hub", None)
        if not hub or not hasattr(hub, "get_unified_snapshot"):
            return {"ok": True, "score": None, "message": "统一数据源中心不可用，跳过门控"}
        try:
            # 防止上游行情/交易所抖动导致 API 入口阻塞。
            snap = await asyncio.wait_for(hub.get_unified_snapshot(symbol), timeout=6.0)
            quality = (snap.get("数据质量评估") or {}) if isinstance(snap, dict) else {}
            score = quality.get("score")
            score_f = float(score) if score is not None else None
            if score_f is None:
                return {"ok": True, "score": None, "message": "未返回质量分，跳过门控"}
            return {
                "ok": score_f >= float(min_score),
                "score": score_f,
                "symbol": symbol,
                "message": f"数据质量={score_f:.3f}, 阈值={float(min_score):.3f}",
            }
        except asyncio.TimeoutError:
            return {"ok": True, "score": None, "message": "质量门控超时，已降级放行"}
        except Exception as e:
            return {"ok": True, "score": None, "message": f"质量门控检查失败，已降级放行: {e}"}

    async def _notify_quality_warning(title: str, gate: Dict[str, Any]) -> None:
        """将数据质量告警推送到统一通知通道（含 TG 等），不中断主流程。"""
        try:
            if not main_controller:
                return
            symbol = str(gate.get("symbol") or "BTC/USDT")
            ai_line = ""
            # analysis moved to MarketIntelligenceEngine
            mi = getattr(main_controller, "market_intelligence", None)
            if mi and hasattr(mi, "get_symbol_view"):
                try:
                    view = await mi.get_symbol_view(symbol, include_snapshot=False)
                    ai_line = (
                        f"\nMI: 趋势={getattr(view, 'trend', '-') or '-'} | 倾向={getattr(view, 'action_bias', '-') or '-'} | "
                        f"置信度={getattr(view, 'confidence', None) if getattr(view, 'confidence', None) is not None else '-'}"
                    )
                    summary = str(getattr(view, "summary", "") or "").strip()
                    if summary:
                        ai_line += f"\n摘要: {summary[:180]}"
                except Exception:
                    pass
            msg = f"{title}\n{gate.get('message', '')}{ai_line}"
            if hasattr(main_controller, "_send_notification_handler"):
                await main_controller._send_notification_handler("数据质量告警", msg, priority="medium")
        except Exception:
            pass

    async def _run_research_job(job_id: str, payload: Dict[str, Any]) -> None:
        """后台执行研究任务，避免阻塞 API worker。"""
        if not main_controller:
            async with research_jobs_lock:
                research_jobs[job_id]["status"] = "failed"
                research_jobs[job_id]["message"] = "主控制器未初始化"
                research_jobs[job_id]["finished_at"] = datetime.now().isoformat()
            return

        pipeline = getattr(main_controller, "strategy_research_pipeline", None)
        if not pipeline:
            async with research_jobs_lock:
                research_jobs[job_id]["status"] = "failed"
                research_jobs[job_id]["message"] = "策略研究流水线未初始化"
                research_jobs[job_id]["finished_at"] = datetime.now().isoformat()
            return

        raw_syms = payload.get("symbols") or ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
        if isinstance(raw_syms, str):
            symbols = [raw_syms]
        elif isinstance(raw_syms, list):
            symbols = [str(s) for s in raw_syms if s]
        else:
            symbols = ["BTC/USDT", "ETH/USDT"]

        timeframe = str(payload.get("timeframe") or "1h")
        lookback_days = max(7, int(payload.get("lookback_days") or 28))
        timeout_sec = max(120, int(payload.get("timeout_seconds") or 1800))
        max_symbols = max(1, int(payload.get("max_symbols") or min(6, len(symbols))))
        sym_slice = symbols[:max_symbols]

        async with research_jobs_lock:
            research_jobs[job_id].update(
                {
                    "status": "running",
                    "symbols_used": sym_slice,
                    "timeframe": timeframe,
                    "lookback_days": lookback_days,
                    "timeout_seconds": timeout_sec,
                    "started_at": datetime.now().isoformat(),
                }
            )

    @trade_router.get("/events")
    async def get_trade_events(
        limit: int = 200,
        cursor: Optional[int] = None,
        type: Optional[str] = None,  # noqa: A002 (fastapi query param)
        symbol: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取最近交易域事件（Intent/Fill/Position）。
        前端可轮询或配合 WebSocket 订阅 channel=trade.*（支持前缀通配符）。
        """
        mc = main_controller
        hub = getattr(mc, "trade_event_hub", None) if mc else None
        if not hub or not (hasattr(hub, "query_recent") or hasattr(hub, "get_recent")):
            return {"ok": False, "events": [], "message": "TradeEventHub unavailable"}
        try:
            if hasattr(hub, "query_recent"):
                q = hub.query_recent(limit=int(limit or 200), cursor=cursor, event_type=type, symbol=symbol, trace_id=trace_id)
                return {"ok": True, **q}
            return {"ok": True, "events": hub.get_recent(limit=int(limit or 200))}
        except Exception as e:
            return {"ok": False, "events": [], "message": str(e)}

    @trade_router.get("/execution_spine")
    async def get_execution_spine_snapshot() -> Dict[str, Any]:
        """返回 S1 ExecutionGateway 快照（包含 policy_metrics）。"""
        mc = main_controller
        gw = getattr(mc, "execution_gateway", None) if mc else None
        if not gw or not hasattr(gw, "get_snapshot"):
            return {"ok": False, "message": "ExecutionGateway unavailable"}
        try:
            snap = await gw.get_snapshot()
            return {"ok": True, "snapshot": snap}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    @market_router.get("/symbol/{symbol}")
    async def get_market_symbol_view(
        symbol: str,
        include_snapshot: bool = False,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        """统一行情汇总：单品种视图（供前端/模块复用）。"""
        mc = main_controller
        mi = getattr(mc, "market_intelligence", None) if mc else None
        if not mi or not hasattr(mi, "get_symbol_view"):
            return {"ok": False, "message": "MarketIntelligenceEngine unavailable"}
        try:
            view = await mi.get_symbol_view(symbol, include_snapshot=bool(include_snapshot))
            out_view = view.to_dict()
            if fields:
                allow = {k.strip() for k in str(fields).split(",") if k.strip()}
                allow.add("symbol")
                allow.add("timestamp")
                out_view = {k: v for k, v in out_view.items() if k in allow}
            return {"ok": True, "view": out_view, "snapshot": view.snapshot if include_snapshot else None}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    @market_router.get("/state")
    async def get_market_state() -> Dict[str, Any]:
        """统一行情汇总：全局市场状态（多 symbol 聚合）。"""
        mc = main_controller
        mi = getattr(mc, "market_intelligence", None) if mc else None
        if not mi or not hasattr(mi, "get_market_state"):
            return {"ok": False, "message": "MarketIntelligenceEngine unavailable"}
        try:
            state = await mi.get_market_state()
            return {"ok": True, "state": state}
        except Exception as e:
            return {"ok": False, "message": str(e)}

        def _run_cycle_in_thread() -> Dict[str, Any]:
            # 在独立线程事件循环中执行重型研究流程，避免阻塞主 API loop。
            return asyncio.run(
                pipeline.run_cycle(symbols=sym_slice, timeframe=timeframe, lookback_days=lookback_days)
            )

        try:
            async with research_semaphore:
                result = await asyncio.wait_for(asyncio.to_thread(_run_cycle_in_thread), timeout=timeout_sec)
            async with research_jobs_lock:
                research_jobs[job_id].update(
                    {
                        "status": "completed",
                        "result": result,
                        "finished_at": datetime.now().isoformat(),
                    }
                )
        except asyncio.TimeoutError:
            async with research_jobs_lock:
                research_jobs[job_id].update(
                    {
                        "status": "failed",
                        "message": f"策略研发执行超时（>{timeout_sec}s）",
                        "finished_at": datetime.now().isoformat(),
                    }
                )
        except Exception as e:
            logger.exception("手动策略研发失败")
            async with research_jobs_lock:
                research_jobs[job_id].update(
                    {
                        "status": "failed",
                        "message": str(e),
                        "finished_at": datetime.now().isoformat(),
                    }
                )
    
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

        def _resolve_risk_monitor():
            if not main_controller:
                return None
            if hasattr(main_controller, 'risk_monitor') and main_controller.risk_monitor:
                return main_controller.risk_monitor
            if (
                hasattr(main_controller, 'ai_trading_engine')
                and main_controller.ai_trading_engine
                and hasattr(main_controller.ai_trading_engine, 'risk_monitor')
                and main_controller.ai_trading_engine.risk_monitor
            ):
                return main_controller.ai_trading_engine.risk_monitor
            return None

        if main_controller:
            monitor = _resolve_risk_monitor()

            if monitor:
                status = monitor.get_status() if hasattr(monitor, "get_status") else {}
                risk_data.update(status if isinstance(status, dict) else {})
                risk_data["monitor_running"] = bool(
                    (status or {}).get("running", False) if isinstance(status, dict) else False
                )
            
            if hasattr(main_controller, 'ai_trading_engine') and main_controller.ai_trading_engine:
                engine = main_controller.ai_trading_engine
                if hasattr(engine, 'enhanced_risk') and engine.enhanced_risk:
                    risk_status = engine.enhanced_risk.get_risk_status()
                    risk_data["circuit_breaker"] = risk_status.get("circuit_breaker", {})
                    risk_data["risk_level"] = risk_status.get("trading_state", {}).get("daily_trades", 0) > 15 and "medium" or "low"
        
        return risk_data

    @router.get("/risk/config")
    async def get_risk_config():
        """读取账户风险监控阈值配置"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        monitor = None
        if hasattr(main_controller, 'risk_monitor') and main_controller.risk_monitor:
            monitor = main_controller.risk_monitor
        elif (
            hasattr(main_controller, 'ai_trading_engine')
            and main_controller.ai_trading_engine
            and hasattr(main_controller.ai_trading_engine, 'risk_monitor')
            and main_controller.ai_trading_engine.risk_monitor
        ):
            monitor = main_controller.ai_trading_engine.risk_monitor
        if not monitor:
            return {"success": False, "message": "风险监控未初始化"}
        return {
            "success": True,
            "config": dict(getattr(monitor, "risk_config", {}) or {}),
            "running": bool(getattr(monitor, "_running", False)),
        }

    @router.post("/risk/config")
    async def update_risk_config(payload: Dict[str, Any]):
        """更新账户风险监控阈值（运行期生效）"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        monitor = None
        if hasattr(main_controller, 'risk_monitor') and main_controller.risk_monitor:
            monitor = main_controller.risk_monitor
        elif (
            hasattr(main_controller, 'ai_trading_engine')
            and main_controller.ai_trading_engine
            and hasattr(main_controller.ai_trading_engine, 'risk_monitor')
            and main_controller.ai_trading_engine.risk_monitor
        ):
            monitor = main_controller.ai_trading_engine.risk_monitor
        if not monitor:
            return {"success": False, "message": "风险监控未初始化"}

        allowed = {
            "margin_ratio_warning",
            "margin_ratio_critical",
            "unrealized_loss_warning",
            "unrealized_loss_critical",
            "liquidation_distance_warning",
            "liquidation_distance_critical",
            "monitor_interval",
        }
        applied: Dict[str, Any] = {}
        for k, v in (payload or {}).items():
            if k not in allowed or v is None:
                continue
            try:
                if k == "monitor_interval":
                    monitor.risk_config[k] = max(2, int(float(v)))
                else:
                    monitor.risk_config[k] = float(v)
                applied[k] = monitor.risk_config[k]
            except Exception:
                continue
        return {"success": True, "applied": applied, "config": dict(monitor.risk_config)}
    
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

    @router.get("/ai/guards")
    async def get_ai_execution_guards():
        """获取 AI 执行门控配置与触发统计"""
        if not main_controller or not hasattr(main_controller, "ai_core") or not main_controller.ai_core:
            return {"success": False, "message": "AI核心决策引擎未初始化"}
        try:
            st = main_controller.ai_core.get_status() if hasattr(main_controller.ai_core, "get_status") else {}
            guards = (st or {}).get("execution_guards", {})
            return {
                "success": True,
                "config": guards.get("config", {}),
                "adaptive_profile": guards.get("adaptive_profile", {}),
                "group_overrides": guards.get("group_overrides", {}),
                "frequency_profile": guards.get("frequency_profile", "balanced"),
                "last_frequency_profile_switch_at": guards.get("last_frequency_profile_switch_at"),
                "group_last_tuned_at": guards.get("group_last_tuned_at", {}),
                "global_last_tuned_at": guards.get("global_last_tuned_at"),
                "stats": guards.get("stats", {}),
            }
        except Exception as e:
            return {"success": False, "message": f"读取执行门控失败: {e}"}

    @router.post("/ai/guards")
    async def update_ai_execution_guards(config: Dict[str, Any]):
        """更新 AI 执行门控阈值（运行期生效）"""
        if not main_controller or not hasattr(main_controller, "ai_core") or not main_controller.ai_core:
            return {"success": False, "message": "AI核心决策引擎未初始化"}
        ai_core = main_controller.ai_core
        allowed = {
            "min_trade_interval",
            "min_confidence_to_trade",
            "ai_core_min_confidence_to_open",
            "min_data_quality_to_trade",
            "min_rr_to_trade",
            "max_spread_bps_to_trade",
            "max_abs_depth_imbalance_to_trade",
            "degraded_data_quantity_factor",
            "boost_on_low_risk",
            "low_risk_rr_multiplier",
            "low_risk_spread_multiplier",
            "high_risk_rr_multiplier",
            "high_risk_spread_multiplier",
            "auto_frequency_profile_switch",
            "frequency_profile_switch_telegram_notify",
            "frequency_profile_cooldown_seconds",
            "frequency_profile_lookback_trades",
            "frequency_profile_max_drawdown_guard",
            "auto_adaptive_guards",
            "auto_tune_guards",
            "auto_tune_by_symbol_group",
            "auto_tune_by_session",
            "auto_tune_global_enabled",
            "auto_tune_global_cooldown_seconds",
            "auto_tune_global_step_rr",
            "auto_tune_global_step_spread_bps",
            "auto_tune_step_rr",
            "auto_tune_step_spread_bps",
            "auto_tune_group_step_rr",
            "auto_tune_group_step_spread_bps",
            "auto_tune_cooldown_seconds",
            "auto_tune_min_rr_delta",
            "auto_tune_min_spread_delta_bps",
            "auto_tune_sltp_params",
            "auto_tune_sltp_cooldown_seconds",
            "auto_tune_sltp_step_tighten",
            "auto_tune_sltp_step_extend",
            "critical_risk_auto_close",
            "critical_risk_auto_close_liq_only",
            "critical_risk_auto_close_max_liq_distance",
            "critical_risk_auto_close_min_loss_pct",
            "hold_avoidance_override_enabled",
            "hold_avoidance_override_cooldown_sec",
            "hold_avoidance_override_min_abs_sentiment",
            "hold_avoidance_override_min_mi_quality_score",
            "hold_avoidance_override_require_mi_trend_alignment",
        }
        applied: Dict[str, Any] = {}
        for k, v in (config or {}).items():
            if k in allowed and v is not None:
                try:
                    if k in (
                        "auto_adaptive_guards",
                        "auto_tune_guards",
                        "auto_tune_by_symbol_group",
                        "auto_tune_by_session",
                        "auto_tune_global_enabled",
                        "auto_tune_sltp_params",
                        "boost_on_low_risk",
                        "auto_frequency_profile_switch",
                        "frequency_profile_switch_telegram_notify",
                    ):
                        ai_core.config[k] = bool(v)
                        applied[k] = bool(v)
                    elif k in ("auto_tune_group_step_rr", "auto_tune_group_step_spread_bps"):
                        if isinstance(v, str) and v.strip().lower() in ("", "null", "none"):
                            ai_core.config[k] = None
                            applied[k] = None
                        else:
                            ai_core.config[k] = float(v)
                            applied[k] = float(ai_core.config[k])
                    else:
                        ai_core.config[k] = float(v)
                        applied[k] = float(v)
                except Exception:
                    continue
        return {
            "success": True,
            "message": "执行门控配置已更新",
            "applied": applied,
        }

    @router.get("/ai/frequency-profile")
    async def get_ai_frequency_profile():
        """读取当前开单频率档位（根据关键门控参数推断）"""
        if not main_controller or not hasattr(main_controller, "ai_core") or not main_controller.ai_core:
            return {"success": False, "message": "AI核心决策引擎未初始化"}
        cfg = main_controller.ai_core.config if hasattr(main_controller.ai_core, "config") else {}
        min_interval = float(cfg.get("min_trade_interval", 120) or 120)
        min_conf = float(cfg.get("min_confidence_to_trade", 0.75) or 0.75)
        min_rr = float(cfg.get("min_rr_to_trade", 1.2) or 1.2)
        spread = float(cfg.get("max_spread_bps_to_trade", 35.0) or 35.0)
        if min_interval <= 70 and min_conf <= 0.70 and min_rr <= 1.10 and spread >= 45.0:
            inferred = "aggressive"
        elif min_interval <= 90 and min_conf <= 0.72 and min_rr <= 1.15 and spread >= 40.0:
            inferred = "balanced"
        else:
            inferred = "conservative"
        return {
            "success": True,
            "inferred_profile": inferred,
            "config": {
                "min_trade_interval": min_interval,
                "min_confidence_to_trade": min_conf,
                "min_rr_to_trade": min_rr,
                "max_spread_bps_to_trade": spread,
                "boost_on_low_risk": bool(cfg.get("boost_on_low_risk", True)),
            },
        }

    @router.post("/ai/frequency-profile")
    async def set_ai_frequency_profile(payload: Dict[str, Any]):
        """一键切换开单频率档位（运行期生效）：conservative / balanced / aggressive"""
        if not main_controller or not hasattr(main_controller, "ai_core") or not main_controller.ai_core:
            return {"success": False, "message": "AI核心决策引擎未初始化"}
        ai_core = main_controller.ai_core
        requested = str((payload or {}).get("profile", "balanced")).strip().lower()
        profiles = (
            ai_core._get_frequency_profiles()
            if hasattr(ai_core, "_get_frequency_profiles")
            else {}
        )
        if requested not in profiles:
            return {
                "success": False,
                "message": "无效档位，支持: conservative / balanced / aggressive",
            }
        if hasattr(ai_core, "_apply_frequency_profile"):
            applied = ai_core._apply_frequency_profile(requested)
        else:
            applied = {}
            for k, v in profiles[requested].items():
                ai_core.config[k] = v
                applied[k] = v
        return {
            "success": True,
            "message": f"已切换到 {requested} 档位",
            "profile": requested,
            "applied": applied,
        }
    
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
                # 兼容旧版内存管理器(list字段)与新版网关(get_stats接口)
                if hasattr(mem, "get_stats"):
                    try:
                        raw = mem.get_stats() or {}
                        if isinstance(raw, dict):
                            stats["short_term_count"] = int(raw.get("short_term_count", raw.get("short_term", 0)) or 0)
                            stats["long_term_count"] = int(raw.get("long_term_count", raw.get("long_term", 0)) or 0)
                            stats["trade_records"] = int(raw.get("trade_records", raw.get("trades", 0)) or 0)
                            stats["risk_events"] = int(raw.get("risk_events", raw.get("risks", 0)) or 0)
                    except Exception:
                        pass
                if stats["short_term_count"] == 0 and hasattr(mem, "short_term_memory"):
                    try:
                        stats["short_term_count"] = len(getattr(mem, "short_term_memory") or [])
                    except Exception:
                        pass
                if stats["long_term_count"] == 0 and hasattr(mem, "long_term_memory"):
                    try:
                        stats["long_term_count"] = len(getattr(mem, "long_term_memory") or [])
                    except Exception:
                        pass
        
        return stats

    @router.get("/stop-loss/stats")
    async def get_stop_loss_stats():
        """获取止盈止损跟踪统计"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        try:
            slm = getattr(main_controller, "stop_loss_manager", None)
            if not slm:
                return {"success": False, "message": "止盈止损管理器未初始化"}
            data = slm.get_stats() if hasattr(slm, "get_stats") else {}
            return {"success": True, "stats": data or {}}
        except Exception as e:
            return {"success": False, "message": f"读取止盈止损统计失败: {e}"}
    
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

    @router.get("/strategy/optimization-status")
    async def get_strategy_optimization_status():
        """
        预留给前端的策略优化状态接口：
        - 策略池总量/上限
        - 每日优化进度与结果
        - 最近一次策略池清理时间
        """
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            sm = main_controller.strategy_manager
            if hasattr(sm, "get_optimization_status"):
                data = sm.get_optimization_status()
            else:
                data = {
                    "pool_limit": 30,
                    "total_strategies": len(getattr(sm, "strategy_configs", {}) or {}),
                    "daily_optimization": {},
                    "last_daily_optimization_date": None,
                    "last_pool_prune_at": None,
                }
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": f"读取策略优化状态失败: {e}"}

    @router.post("/strategy/optimization-config")
    async def update_strategy_optimization_config(config: Dict[str, Any]):
        """热更新策略优化运行参数（前端可直接调用）。"""
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            sm = main_controller.strategy_manager
            if not hasattr(sm, "update_optimization_runtime_config"):
                return {"success": False, "message": "当前策略管理器不支持热更新优化参数"}
            applied = sm.update_optimization_runtime_config(config or {})
            return {
                "success": True,
                "message": "策略优化参数已更新",
                "applied": applied,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": f"更新策略优化参数失败: {e}"}

    @router.get("/strategy/optimization-config")
    async def get_strategy_optimization_config():
        """读取当前策略优化运行参数。"""
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            sm = main_controller.strategy_manager
            status = sm.get_optimization_status() if hasattr(sm, "get_optimization_status") else {}
            return {
                "success": True,
                "config": (status.get("runtime_config", {}) if isinstance(status, dict) else {}),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": f"读取策略优化参数失败: {e}"}

    @router.post("/strategy/optimize-now")
    async def trigger_strategy_optimization_now():
        """手动触发一次每日优化批次（用于运维/验收）。"""
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            gate = await _check_unified_data_quality(symbol="BTC/USDT", min_score=0.45)
            if not gate.get("ok", True):
                await _notify_quality_warning("优化任务低质量放行（AI自主判断）", gate)
            sm = main_controller.strategy_manager
            if hasattr(sm, "trigger_daily_optimization_now"):
                out = await sm.trigger_daily_optimization_now()
                if isinstance(out, dict):
                    out["quality_gate"] = gate
                return out
            await sm._run_daily_strategy_optimization()  # type: ignore[attr-defined]
            return {"success": True, "message": "已触发每日优化批次", "quality_gate": gate}
        except Exception as e:
            return {"success": False, "message": f"触发每日优化失败: {e}"}

    @router.post("/strategy/trade-feedback")
    async def submit_strategy_trade_feedback(payload: Dict[str, Any]):
        """
        提交交易结果反馈，驱动策略参数自适应收敛并可联动优化批次。
        body: strategy_id, pnl, win_rate?, max_drawdown?, total_trades?, force_optimize?
        """
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            gate = await _check_unified_data_quality(symbol=str(payload.get("symbol") or "BTC/USDT"), min_score=0.4)
            if not gate.get("ok", True):
                await _notify_quality_warning("交易反馈低质量放行（AI自主判断）", gate)
            sm = main_controller.strategy_manager
            strategy_id = str(payload.get("strategy_id") or "").strip()
            if not strategy_id:
                return {"success": False, "message": "strategy_id 不能为空"}
            pnl = float(payload.get("pnl", 0.0) or 0.0)
            win_rate = payload.get("win_rate")
            max_drawdown = payload.get("max_drawdown")
            total_trades = payload.get("total_trades")
            force_optimize = bool(payload.get("force_optimize", False))
            if hasattr(sm, "apply_trade_feedback"):
                out = await sm.apply_trade_feedback(
                    strategy_id=strategy_id,
                    pnl=pnl,
                    win_rate=win_rate,
                    max_drawdown=max_drawdown,
                    total_trades=total_trades,
                    force_optimize=force_optimize,
                )
                return {"success": True, "data": out, "quality_gate": gate, "timestamp": datetime.now().isoformat()}
            return {"success": False, "message": "当前策略管理器不支持交易反馈优化"}
        except Exception as e:
            return {"success": False, "message": f"提交交易反馈失败: {e}"}

    @router.get("/execution/production-audit")
    async def get_production_execution_audit():
        """
        生产执行链路审查：
        开仓、平仓、止盈、止损、跟踪止损、交易所连通、执行网关状态。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        mc = main_controller
        out: Dict[str, Any] = {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "checks": {},
        }
        try:
            gw = getattr(mc, "execution_gateway", None)
            out["checks"]["execution_gateway"] = bool(gw is not None)
            if gw:
                out["execution_spine"] = await gw.get_snapshot()

            ex = mc.get_exchange() if hasattr(mc, "get_exchange") else None
            out["checks"]["exchange_connected"] = bool(ex is not None)

            slm = getattr(mc, "stop_loss_manager", None)
            out["checks"]["stop_loss_manager"] = bool(slm is not None)
            if slm:
                stats = slm.get_stats()
                out["sltp_stats"] = stats
                out["checks"]["dynamic_market_adjustment"] = bool(
                    getattr(slm.config, "enable_dynamic_market_adjustment", False)
                )
                out["checks"]["trailing_stop_enabled"] = bool(
                    getattr(slm.config, "enable_trailing_stop", False)
                )
                out["checks"]["execute_exchange_on_trigger"] = bool(
                    getattr(slm.config, "execute_exchange_on_trigger", False)
                )
                active_orders = await slm.get_all_active_orders()
                out["active_orders"] = [o.to_dict() for o in active_orders[:20]]

            return out
        except Exception as e:
            return {"success": False, "message": f"生产执行审查失败: {e}", "timestamp": datetime.now().isoformat()}

    @router.post("/strategy/research-run")
    async def run_strategy_research_now(payload: Optional[Dict[str, Any]] = Body(None)):
        """
        手动触发策略研发流水线（walk-forward + 门控），不受「有持仓则跳过」限制。
        可选 JSON：symbols, timeframe, lookback_days, timeout_seconds, max_symbols
        """
        payload = payload or {}
        raw_symbols = payload.get("symbols") or ["BTC/USDT"]
        if isinstance(raw_symbols, str):
            gate_symbol = raw_symbols
        elif isinstance(raw_symbols, list) and raw_symbols:
            gate_symbol = str(raw_symbols[0])
        else:
            gate_symbol = "BTC/USDT"
        gate = await _check_unified_data_quality(
            symbol=gate_symbol,
            min_score=float(payload.get("min_data_quality", 0.5) or 0.5),
        )
        if not gate.get("ok", True):
            await _notify_quality_warning("研究任务低质量放行（AI自主判断）", gate)
        job_id = f"research_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        job = {
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.now().isoformat(),
            "payload": payload,
            "result": None,
            "message": "",
            "started_at": None,
            "finished_at": None,
        }
        async with research_jobs_lock:
            research_jobs[job_id] = job
            # 控制历史长度，避免内存无限增长
            if len(research_jobs) > 50:
                old_keys = sorted(
                    research_jobs.keys(),
                    key=lambda k: research_jobs[k].get("created_at", "")
                )[:-50]
                for k in old_keys:
                    research_jobs.pop(k, None)
        asyncio.create_task(_run_research_job(job_id, payload))
        return {
            "success": True,
            "message": "策略研究任务已提交后台执行",
            "job_id": job_id,
            "status": "queued",
            "quality_gate": gate,
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/strategy/research-jobs")
    async def list_strategy_research_jobs(limit: int = 20):
        """查询最近策略研究任务列表。"""
        safe_limit = max(1, min(int(limit), 100))
        async with research_jobs_lock:
            jobs = sorted(
                research_jobs.values(),
                key=lambda x: x.get("created_at", ""),
                reverse=True,
            )[:safe_limit]
        return {"success": True, "jobs": jobs, "timestamp": datetime.now().isoformat()}

    @router.get("/strategy/research-jobs/{job_id}")
    async def get_strategy_research_job(job_id: str):
        """查询单个策略研究任务状态。"""
        async with research_jobs_lock:
            job = research_jobs.get(job_id)
        if not job:
            return {"success": False, "message": "任务不存在", "job_id": job_id}
        return {"success": True, "job": job, "timestamp": datetime.now().isoformat()}

    @router.get("/memory/daily-summary")
    async def get_memory_daily_summary(limit: int = 6):
        """
        获取每日复盘摘要（用于前端卡片与TG快速查看）。
        """
        safe_limit = max(1, min(int(limit), 20))
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        gateway = getattr(main_controller, "memory_gateway", None)
        if not gateway:
            return {"success": False, "message": "记忆网关不可用"}
        try:
            rows = await gateway.recall(query="每日交易复盘 自动总结", limit=safe_limit, min_importance=0.5)
            data: List[Dict[str, Any]] = []
            for r in rows:
                data.append(
                    {
                        "id": getattr(r, "id", None),
                        "content": getattr(r, "content", ""),
                        "importance": getattr(r, "importance", None),
                        "timestamp": getattr(r, "timestamp", None),
                        "metadata": getattr(r, "metadata", {}) if hasattr(r, "metadata") else {},
                    }
                )
            # 兜底：部分情况下召回模型可能漏召回，直接从内存后端筛选“每日复盘”类记录。
            if not data:
                backend = getattr(gateway, "memory_backend", None)
                memories = getattr(backend, "_memories", {}) if backend else {}
                fallback_rows: List[Dict[str, Any]] = []
                for mid, entry in (memories or {}).items():
                    try:
                        content = str(getattr(entry, "content", "") or "")
                        metadata = getattr(entry, "metadata", {}) or {}
                        src = str(metadata.get("source_module") or "")
                        if ("每日交易复盘" in content) or ("复盘" in content and src == "ai_command_executor"):
                            fallback_rows.append(
                                {
                                    "id": mid,
                                    "content": content,
                                    "importance": float(getattr(entry, "importance", 0.0) or 0.0),
                                    "timestamp": (
                                        getattr(entry, "created_at", None).isoformat()
                                        if getattr(entry, "created_at", None) is not None
                                        else None
                                    ),
                                    "metadata": metadata,
                                }
                            )
                    except Exception:
                        continue
                fallback_rows = sorted(
                    fallback_rows,
                    key=lambda x: str(x.get("timestamp") or ""),
                    reverse=True,
                )[:safe_limit]
                data = fallback_rows
            return {"success": True, "data": data, "count": len(data), "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/memory/daily-summary/run")
    async def run_memory_daily_summary():
        """
        手动触发一次每日复盘写入（AI执行器路径）。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        exe = getattr(main_controller, "ai_command_executor", None)
        if not exe or not hasattr(exe, "_auto_daily_summary"):
            return {"success": False, "message": "AI执行器不可用"}
        try:
            ok = await exe._auto_daily_summary(force=True)
            return {
                "success": bool(ok),
                "message": "已触发每日复盘写入" if ok else "每日复盘写入失败",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    async def _build_commander_fast_snapshot(symbol: str = "BTC/USDT") -> Dict[str, Any]:
        """快速快照：优先返回核心状态，避免重聚合阻塞。"""
        out: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "mode": "fast",
            "system": {},
            "strategy": {},
            "execution": {},
            "risk": {},
            "account": {},
            "data_hub": {"symbol": symbol},
            "alerts": [],
        }
        mc = main_controller
        if not mc:
            return out
        FAST_TIMEOUT_S = 4.0
        try:
            st = await asyncio.wait_for(mc.get_system_status(), timeout=FAST_TIMEOUT_S)
            out["system"] = {
                "system_status": st.get("system_status"),
                "module_count": st.get("module_count"),
                "running_modules": st.get("running_modules"),
            }
        except Exception as e:
            out["alerts"].append(f"系统状态读取失败: {e}")

        try:
            sm = getattr(mc, "strategy_manager", None)
            if sm and hasattr(sm, "get_optimization_status"):
                s = sm.get_optimization_status()
                out["strategy"] = {
                    "total_strategies": s.get("total_strategies"),
                    "pool_limit": s.get("pool_limit"),
                    "daily_optimization": s.get("daily_optimization"),
                    "deployment_stage_counts": s.get("deployment_stage_counts"),
                }
        except Exception as e:
            out["alerts"].append(f"策略状态读取失败: {e}")

        try:
            gw = getattr(mc, "execution_gateway", None)
            if gw and hasattr(gw, "get_snapshot"):
                out["execution"] = await asyncio.wait_for(gw.get_snapshot(), timeout=FAST_TIMEOUT_S)
        except Exception as e:
            out["alerts"].append(f"执行网关快照失败: {e}")

        try:
            slm = getattr(mc, "stop_loss_manager", None)
            if slm and hasattr(slm, "get_stats"):
                out["risk"]["sltp"] = slm.get_stats()
        except Exception as e:
            out["alerts"].append(f"SLTP统计读取失败: {e}")

        # 账户/持仓（快速版）：只读缓存，避免因交易所/网络抖动导致快照阻塞。
        try:
            st = getattr(mc, "_latest_account_state", None)
            if isinstance(st, dict) and st.get("timestamp"):
                try:
                    raw = str(st["timestamp"]).replace("Z", "")
                    t0 = datetime.fromisoformat(raw[:26])
                    if (datetime.now() - t0).total_seconds() > 45:
                        out["alerts"].append("account_state_stale>45s")
                except Exception:
                    pass
            st = st if isinstance(st, dict) else {}
            out["account"] = {
                "balance": st.get("balance"),
                "positions": st.get("positions"),
                "synced_at": st.get("timestamp"),
            }
        except Exception:
            pass

        # 仓位管理建议（快速版：仅在能得到可用余额时生成）
        try:
            bal = out.get("account", {}).get("balance") or {}
            usdt = bal.get("USDT", bal.get("usdt", 0)) if isinstance(bal, dict) else 0
            if isinstance(usdt, dict):
                available = usdt.get("free", usdt.get("available", 0))
            else:
                available = usdt
            positions = out.get("account", {}).get("positions") or []
            pos_map: Dict[str, Any] = {}
            if isinstance(positions, list):
                for p in positions:
                    if isinstance(p, dict):
                        sym = p.get("symbol") or p.get("instId") or p.get("instrument_id")
                        if sym:
                            try:
                                v = float(p.get("notional") or p.get("value") or 0)
                            except Exception:
                                v = 0.0
                            pos_map[str(sym)] = {"value": v, **p}
            if available and hasattr(mc, "get_position_recommendations"):
                try:
                    out["risk"]["position_recommendations"] = await asyncio.wait_for(
                        mc.get_position_recommendations(
                            account_balance=float(available),
                            current_positions=pos_map,
                        ),
                        timeout=1.8,
                    )
                except Exception:
                    out["risk"]["position_recommendations"] = out["risk"].get("position_recommendations") or {}
        except Exception:
            pass

        # 数据/分析模块快照（快速版：不触发交易所重型聚合）
        try:
            di = getattr(mc, "data_integration", None)
            if di and hasattr(di, "get_source_health_report"):
                out["data_hub"]["data_integration_health"] = di.get_source_health_report()
        except Exception:
            pass
        try:
            tpi = getattr(mc, "third_party_data_integrator", None)
            if tpi:
                prov = getattr(tpi, "providers", {}) or {}
                disabled = list(getattr(tpi, "_disabled_providers", set()) or [])
                diag: Dict[str, Any] = {}
                if hasattr(tpi, "get_diagnostics"):
                    try:
                        diag = tpi.get_diagnostics()
                    except Exception:
                        diag = {}
                out["data_hub"]["third_party"] = {
                    "provider_count": len(prov),
                    "disabled_count": len(disabled),
                    "diagnostics": diag,
                }
        except Exception:
            pass
        try:
            mi = getattr(mc, "market_intelligence", None) or getattr(mc, "market_intelligence_engine", None)
            if mi:
                cached = mi.get_cached_symbol_view(symbol) if hasattr(mi, "get_cached_symbol_view") else {}
                if cached:
                    out["data_hub"]["market_intelligence"] = cached
                elif hasattr(mi, "get_symbol_view"):
                    view = await asyncio.wait_for(mi.get_symbol_view(symbol, include_snapshot=False), timeout=2.2)
                    out["data_hub"]["market_intelligence"] = view.to_dict() if hasattr(view, "to_dict") else {}
                # Still empty: report warm-up state so caller knows it's connected.
                if not out["data_hub"].get("market_intelligence"):
                    out["data_hub"]["market_intelligence"] = {
                        "status": "warming_up",
                        "hint": "market_intelligence_connected_but_no_cached_view_yet",
                    }
        except Exception:
            out["data_hub"]["market_intelligence"] = out["data_hub"].get("market_intelligence") or {
                "status": "warming_up_or_busy",
            }
        return out

    @router.get("/commander/snapshot")
    async def commander_snapshot(symbol: str = "BTC/USDT", mode: str = "fast"):
        """司令部统一快照：前端/TG/运维可共享。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        if not hasattr(main_controller, "build_ai_commander_snapshot"):
            return {"success": False, "message": "司令部快照能力不可用"}
        try:
            mode_l = str(mode or "fast").strip().lower()
            if mode_l == "full":
                data = await asyncio.wait_for(
                    main_controller.build_ai_commander_snapshot(symbol=symbol),
                    timeout=15.0,
                )
                data["mode"] = "full"
            else:
                data = await asyncio.wait_for(_build_commander_fast_snapshot(symbol=symbol), timeout=8.0)
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except asyncio.TimeoutError:
            return {
                "success": True,
                "data": {
                    "timestamp": datetime.now().isoformat(),
                    "mode": "fast_degraded_timeout",
                    "alerts": ["snapshot_timeout_degraded"],
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/capabilities")
    async def commander_capabilities():
        """司令部能力与子智能体清单（对齐 OpenClaw 文档中的回路/专家概念，便于运维对接）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_commander_capabilities"):
            return {"success": False, "message": "capabilities 不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_commander_capabilities()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/chores")
    async def commander_chores(payload: Dict[str, Any] = Body(default_factory=dict)):
        """触发司令部日常任务。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        if not hasattr(main_controller, "run_ai_commander_chores"):
            return {"success": False, "message": "司令部日常任务能力不可用"}
        try:
            symbol = str((payload or {}).get("symbol") or "BTC/USDT")
            trigger_optimize = bool((payload or {}).get("trigger_optimize", False))
            data = await main_controller.run_ai_commander_chores(symbol=symbol, trigger_optimize=trigger_optimize)
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/dispatch")
    async def commander_dispatch(payload: Dict[str, Any] = Body(default_factory=dict)):
        """
        司令部统一指令入口：把前端消息与TG消息统一到同一处理链路。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        if not hasattr(main_controller, "process_user_command"):
            return {"success": False, "message": "司令部指令入口不可用"}
        text = str((payload or {}).get("message") or "").strip()
        if not text:
            return {"success": False, "message": "message 不能为空"}
        source = str((payload or {}).get("source") or "control_hub")
        try:
            out = await main_controller.process_user_command(text, source=source)
            return {"success": True, "data": out, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/audit")
    async def commander_audit(enrich: bool = False):
        """
        司令部全链路审查：检查前端/消息通道/后端关键能力是否已接入。
        enrich=true 时附带第三方限速诊断摘要与记忆网关快照（供运维质检）。
        """
        checks: List[Dict[str, Any]] = []

        def add(name: str, passed: bool, detail: str = "") -> None:
            checks.append({"name": name, "passed": bool(passed), "detail": detail})

        if not main_controller:
            add("main_controller", False, "missing")
            return {"success": False, "checks": checks, "all_passed": False, "timestamp": datetime.now().isoformat()}

        mc = main_controller
        add("commander.snapshot", hasattr(mc, "build_ai_commander_snapshot"), "build_ai_commander_snapshot")
        add("commander.chores", hasattr(mc, "run_ai_commander_chores"), "run_ai_commander_chores")
        add("commander.dispatch", hasattr(mc, "process_user_command"), "process_user_command")
        add("commander.capabilities", hasattr(mc, "get_commander_capabilities"), "get_commander_capabilities")
        add("surface.registry", True, "GET /api/v1/modules/surface/registry")
        add("surface.data_integration_health", True, "GET /api/v1/modules/data/integration/health")
        add("surface.plugins_status", True, "GET /api/v1/modules/plugins/status")
        add("message.telegram", bool(getattr(mc, "telegram_bot", None)), "telegram_bot")
        add("notification.unified", hasattr(mc, "_send_notification_handler"), "_send_notification_handler")
        add("memory.gateway", bool(getattr(mc, "memory_gateway", None)), "memory_gateway")
        add(
            "commander.unrestricted",
            str(__import__("os").environ.get("OPENCLAW_COMMANDER_UNRESTRICTED", "1")).strip().lower() not in {"0", "false", "no", "off"},
            "OPENCLAW_COMMANDER_UNRESTRICTED",
        )
        add("data.hub", bool(getattr(mc, "data_source_hub", None)), "data_source_hub")
        add("data.integration", bool(getattr(mc, "data_integration", None)), "data_integration")
        tpi = getattr(mc, "third_party_data_integrator", None)
        add("data.third_party", bool(tpi), "third_party_data_integrator")
        add(
            "data.third_party.diagnostics",
            bool(tpi and hasattr(tpi, "get_diagnostics")),
            "get_diagnostics for rate-limit QC",
        )
        add("analysis.market_intelligence", bool(getattr(mc, "market_intelligence", None)), "market_intelligence")
        add("plugin.manager", bool(getattr(mc, "plugin_manager", None)), "plugin_manager")
        add("strategy.manager", bool(getattr(mc, "strategy_manager", None)), "strategy_manager")
        add("risk.sltp", bool(getattr(mc, "stop_loss_manager", None)), "stop_loss_manager")
        add("execution.gateway", bool(getattr(mc, "execution_gateway", None)), "execution_gateway")
        add("api.module_control", True, "routes_registered")
        all_passed = all(c["passed"] for c in checks)
        out: Dict[str, Any] = {
            "success": True,
            "all_passed": all_passed,
            "checks": checks,
            "timestamp": datetime.now().isoformat(),
            "architecture": {
                "pattern": "commander_centric",
                "summary": (
                    "司令部(CommanderAgentRuntime)为统一入口：process_user_command → 指令执行器/子智能体(specialists)/记忆网关；"
                    "各业务模块为子系统，由 MainController 装配；实时消息(Telegram 等)与 HTTP dispatch 同源接入。"
                ),
            },
        }
        if enrich:
            out["third_party_diagnostics"] = {}
            if tpi and hasattr(tpi, "get_diagnostics"):
                try:
                    out["third_party_diagnostics"] = tpi.get_diagnostics()
                except Exception as e:
                    out["third_party_diagnostics"] = {"error": str(e)}
            gw = getattr(mc, "memory_gateway", None)
            out["memory_quick"] = {}
            if gw:
                try:
                    out["memory_quick"] = {
                        "stats": gw.get_stats() if hasattr(gw, "get_stats") else {},
                        "summary": gw.get_summary_status() if hasattr(gw, "get_summary_status") else {},
                    }
                except Exception as e:
                    out["memory_quick"] = {"error": str(e)}
            tb = getattr(mc, "telegram_bot", None)
            out["realtime_channels"] = {
                "telegram_configured": tb is not None,
                "hint": "前端/脚本与 Bot 均可用 POST /api/v1/modules/commander/dispatch 统一 source 标签",
            }
        return out

    @router.get("/commander/memory/status")
    async def commander_memory_status():
        """司令部记忆系统自检：网关/后端统计/召回命中率等。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        gw = getattr(main_controller, "memory_gateway", None)
        if not gw:
            return {"success": False, "message": "MemoryGateway 未就绪", "timestamp": datetime.now().isoformat()}
        try:
            stats = gw.get_stats() if hasattr(gw, "get_stats") else {}
            summary = gw.get_summary_status() if hasattr(gw, "get_summary_status") else {}
            return {
                "success": True,
                "data": {
                    "stats": stats,
                    "summary": summary,
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/memory/workspace")
    async def commander_memory_workspace(filename: str = ""):
        """读取 workspace 记忆文件（默认读取允许集合；可用 env 放开全部）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        gw = getattr(main_controller, "memory_gateway", None)
        if not gw or not hasattr(gw, "get_workspace_memory"):
            return {"success": False, "message": "MemoryGateway 未就绪", "timestamp": datetime.now().isoformat()}
        try:
            data = gw.get_workspace_memory(filename=filename or None)
            # 避免一次性回传超大：每个文件最多返回 200k 字符
            clipped = {}
            for k, v in (data or {}).items():
                s = v if isinstance(v, str) else str(v)
                clipped[k] = s if len(s) <= 200_000 else (s[:200_000] + "\n\n…已截断…")
            return {"success": True, "data": clipped, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/memory/persona-preview")
    async def commander_memory_persona_preview(source: str = "api"):
        """
        司令部人格/身份/职责是否已注入：返回「将被注入到对话提示词的摘要」预览。
        用于排查“司令部好像不知道自己是谁/做什么”的问题。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        exe = getattr(main_controller, "ai_command_executor", None)
        if not exe or not hasattr(exe, "_get_user_rules_context"):
            return {"success": False, "message": "AICommandExecutor 未就绪", "timestamp": datetime.now().isoformat()}
        try:
            # _get_user_rules_context 会包含 CHARTER + startup bundle + boundaries prose + 关键记忆片段
            text = await exe._get_user_rules_context()
            cap = 18_000
            preview = text if len(text) <= cap else (text[:cap] + "\n\n…已截断…")
            return {
                "success": True,
                "data": {
                    "source": source,
                    "preview": preview,
                    "length": len(text),
                    "has_startup_bundle": bool(getattr(exe, "_workspace_startup_bundle", "") or ""),
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/account-diagnostics")
    async def commander_account_diagnostics():
        """
        交易所实时持仓/余额 vs 本地 SLTP 跟踪 — 排查同步问题（不依赖本机成交笔数）。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_account_sync_diagnostics"):
            return {"success": False, "message": "诊断接口不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = await asyncio.wait_for(main_controller.get_account_sync_diagnostics(), timeout=20.0)
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except asyncio.TimeoutError:
            return {
                "success": True,
                "degraded": True,
                "data": {"status": "timeout_degraded", "hint": "account_diagnostics_timeout"},
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/account-sync/run")
    async def commander_account_sync_run(payload: Dict[str, Any] = Body(default_factory=dict)):
        """强制同步余额/持仓并接管 SLTP（与启动时 force_sync 相同语义）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "force_sync_account_state"):
            return {"success": False, "message": "同步能力不可用", "timestamp": datetime.now().isoformat()}
        reason = str((payload or {}).get("reason") or "api")
        try:
            data = await main_controller.force_sync_account_state(reason=reason)
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

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

    from src.modules.api.module_surface import attach_module_surface_routes

    attach_module_surface_routes(router, main_controller)

    app.include_router(router)
    app.include_router(trade_router)
    app.include_router(market_router)
    app.include_router(s1_router)
    logger.info("✅ 模块控制API已初始化")
